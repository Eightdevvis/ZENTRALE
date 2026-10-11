# core/werkzeug_erzeuger/anbindung.py
#
# Die Anbindungs-Beschreibung: laden, STRENG prüfen, Stufe je Aktion ermitteln,
# Dateien finden (2026-10-11, Plan: memory/hub/hub_bauplan.md „Anbindungs-
# Pipe der Werkstatt"). Neue Programme werden nicht per Python-Adapter
# angebunden, sondern mit einer Datei, die der allgemeine Adapter
# (allgemein.py) ausführt. Später füllt die Werkstatt (eine KI) solche Dateien
# aus — deshalb ist die Prüfung hier der eigentliche Schutz: zuerst das JSON
# Schema (anbindung.schema.json, offener Standard), dann alles, was ein Schema
# nicht sagen kann (Platzhalter gibt es wirklich, Rückbau passt zur Art,
# Kennung und Nachlesen passen zusammen, kein Schlüssel in der Datei). Jede
# Meldung nennt die Stelle und ist so geschrieben, dass eine KI sie beheben kann.
#
# Wo Dateien liegen:
#   Vorlagen     core/anbindungen/<name>.json      mit dem Programm geliefert
#   Nutzerdaten  data/anbindungen/<name>.json      (Einstellung anbindungen_dir,
#                                                  Env ZENTRALE_ANBINDUNGEN_DIR)
# Eine Nutzer-Datei gleichen Namens ersetzt die Vorlage. Jede Anbindung ist
# standardmäßig AUS; Einstellung anbindung_<name> = an schaltet sie ein (das ist
# Sashas Freigabe). Transport "python" gilt nur in Vorlagen und Tests — eine
# Datei aus data/ (von der Werkstatt) darf kein Python laden.
#
# Stufen (automatisch, je Aktion):
#   lesen     Lesen frei.
#   voll      Kennung + Nachlesen + Rückbau da: volle Schutzschicht.
#   gefragt   Schreiben ohne Beleg: jedes Mal mit Rückfrage, Ergebnis „nicht
#             belegt", kein Zurückbauen.
#   einmalig  Löschen ohne Wiederherstellen: nur mit Erlaubnis „nur dieses mal".

import json
import os
import re
from dataclasses import dataclass, field

import ai_config

from . import schema as erz_schema
from . import vorlage

SCHEMA_DATEI = os.path.join(os.path.dirname(__file__), "anbindung.schema.json")
VORLAGEN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "anbindungen"))
FORMAT = "zentrale-anbindung/1"
FELDER_RESERVIERT = ("alt", "antwort", "e")        # feste Platzhalter-Namen

# Stufen
LESEN, VOLL, GEFRAGT, EINMALIG = "lesen", "voll", "gefragt", "einmalig"
STUFEN_TEXT = {
    LESEN: "Lesen, frei",
    VOLL: "volle Schutzschicht (Kennung, Nachlesen, Zurückbauen)",
    GEFRAGT: "jedes Mal gefragt, nicht belegt, kein Zurückbauen",
    EINMALIG: "Löschen ohne Wiederherstellen: nur mit Erlaubnis „nur dieses mal“",
}


class AnbindungFehler(ValueError):
    """Die Beschreibung ist nicht in Ordnung. `.meldungen` nennt jede Stelle."""

    def __init__(self, meldungen):
        self.meldungen = list(meldungen)
        super().__init__("; ".join(self.meldungen[:5]) + ("; …" if len(self.meldungen) > 5 else ""))


@dataclass
class Pruefung:
    fehler: list = field(default_factory=list)
    warnungen: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.fehler


# ── Dateien ────────────────────────────────────────────────────────────

def nutzer_ordner() -> str:
    eigen = ai_config.setting("anbindungen_dir")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                        "data", "anbindungen"))


def _dateien(ordner: str) -> dict:
    raus = {}
    if os.path.isdir(ordner):
        for n in sorted(os.listdir(ordner)):
            base, ext = os.path.splitext(n)
            if ext in (".json", ".yaml", ".yml") and re.fullmatch(r"[a-z][a-z0-9_]{1,30}", base):
                raus[base] = os.path.join(ordner, n)
    return raus


def auflisten() -> dict:
    """name → {pfad, herkunft: 'vorlage'|'nutzer'}; Nutzer ersetzt Vorlage."""
    raus = {n: {"pfad": p, "herkunft": "vorlage"} for n, p in _dateien(VORLAGEN_DIR).items()}
    raus.update({n: {"pfad": p, "herkunft": "nutzer"} for n, p in _dateien(nutzer_ordner()).items()})
    return raus


def eingeschaltet(name: str) -> bool:
    """Einstellung anbindung_<name> (an|aus, Standard aus)."""
    wert = ai_config.setting("anbindung_" + name, "aus")
    return str(wert or "aus").strip().lower() in ("an", "1", "true", "ja", "on")


def lesen_roh(pfad: str) -> dict:
    with open(pfad, encoding="utf-8") as f:
        if pfad.endswith((".yaml", ".yml")):
            import yaml
            daten = yaml.safe_load(f)
        else:
            daten = json.load(f)
    if not isinstance(daten, dict):
        raise AnbindungFehler([f"{os.path.basename(pfad)}: oberste Ebene muss ein Objekt sein"])
    return daten


def laden(pfad: str, vertrauen: bool = None) -> dict:
    """Datei lesen und prüfen; wirft AnbindungFehler. `vertrauen` (Python-
    Transport erlaubt) gilt standardmäßig nur für Dateien in core/anbindungen/."""
    if vertrauen is None:
        vertrauen = os.path.abspath(os.path.dirname(pfad)) == VORLAGEN_DIR
    try:
        besch = lesen_roh(pfad)
    except AnbindungFehler:
        raise
    except Exception as e:      # noqa: BLE001 — kaputtes JSON/YAML ist eine Meldung, kein Absturz
        raise AnbindungFehler([f"{os.path.basename(pfad)}: nicht lesbar ({e})"])
    p = pruefen(besch, vertrauen=vertrauen)
    if not p.ok:
        raise AnbindungFehler(p.fehler)
    return besch


# ── Prüfen ─────────────────────────────────────────────────────────────

_SCHLUESSEL = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|Bearer\s+\S{8,}|-----BEGIN [A-Z ]*KEY|"
                         r"(?:api[_-]?key|token|passwort|password|secret)\s*=\s*\S{8,})", re.I)


def _strings(wert, pfad=""):
    if isinstance(wert, str):
        yield pfad, wert
    elif isinstance(wert, dict):
        for k, v in wert.items():
            yield from _strings(v, f"{pfad}/{k}")
    elif isinstance(wert, list):
        for i, v in enumerate(wert):
            yield from _strings(v, f"{pfad}/{i}")


def _schema_meldungen(besch: dict) -> list:
    import jsonschema
    with open(SCHEMA_DATEI, encoding="utf-8") as f:
        s = json.load(f)
    fehler = []
    for e in sorted(jsonschema.Draft202012Validator(s).iter_errors(besch),
                    key=lambda e: [str(p) for p in e.absolute_path]):
        stelle = "/" + "/".join(str(p) for p in e.absolute_path)
        kern = e.message
        if e.context:                       # oneOf/anyOf: die beste Teilmeldung zeigen
            kern = jsonschema.exceptions.best_match(e.context).message
        fehler.append(f"{stelle}: {kern}"[:300])
    return fehler


def pruefen(besch: dict, vertrauen: bool = False) -> Pruefung:
    """Alles prüfen. Gibt ALLE Meldungen zurück (nicht nur die erste)."""
    p = Pruefung()
    p.fehler += _schema_meldungen(besch)
    if p.fehler:                            # ohne Grundform ergibt der Rest keinen Sinn
        return p
    _kopf(besch, p, vertrauen)
    namen = set()
    for i, a in enumerate(besch["aktionen"]):
        stelle = f"/aktionen/{i} ({a['name']})"
        if a["name"] in namen:
            p.fehler.append(f"{stelle}: Name kommt doppelt vor")
        namen.add(a["name"])
        _aktion(besch, a, stelle, p)
    for stelle, text in _strings(besch):
        if _SCHLUESSEL.search(text):
            p.fehler.append(f"{stelle}: sieht nach einem Schlüssel aus — Schlüssel gehören nie in die "
                            "Datei; auth verweist nur auf den NAMEN einer Einstellung")
    return p


def _kopf(besch, p, vertrauen):
    t = besch["transport"]
    if t["art"] == "python" and not vertrauen:
        p.fehler.append("/transport: Python-Transport ist nur in mitgelieferten Vorlagen erlaubt")
    if t["art"] == "http" and t.get("auth") and t["auth"]["art"] == "kopfzeile" and not t["auth"].get("kopfzeile"):
        p.fehler.append("/transport/auth: bei art 'kopfzeile' fehlt der Name der Kopfzeile")
    for n, nl in (besch.get("nachlesen") or {}).items():
        _aufruf(besch, nl["aufruf"], f"/nachlesen/{n}/aufruf", p)
        erlaubt = {"kennung"}
        _platzhalter(nl["aufruf"], erlaubt, None, f"/nachlesen/{n}/aufruf", p, nl.get("teile"))
        _platzhalter(nl.get("wo"), erlaubt, None, f"/nachlesen/{n}/wo", p, nl.get("teile"))
        _platzhalter(nl.get("eintraege"), erlaubt, None, f"/nachlesen/{n}/eintraege", p, nl.get("teile"))
        _platzhalter(nl.get("zeile"), {"e", "kennung"}, None, f"/nachlesen/{n}/zeile", p, nl.get("teile"))


def _aufruf(besch, aufruf, stelle, p):
    art = besch["transport"]["art"]
    passend = {"http": "methode", "mcp": "werkzeug", "python": "funktion"}[art]
    if passend not in aufruf:
        p.fehler.append(f"{stelle}: bei transport '{art}' muss der Aufruf '{passend}' nennen")


def _platzhalter(wert, fest, props, stelle, p, teile=None):
    """Jeder Platzhalter muss ein Argument der Aktion (props) oder ein fester
    Name (fest) sein; bei kennung.<teil> muss es den Teil geben."""
    for n in vorlage.alle_namen(wert):
        wurzel, _, rest = n.partition(".")
        if wurzel in fest:
            if wurzel == "kennung" and rest and (teile is None or rest.split(".")[0] not in teile):
                p.fehler.append(f"{stelle}: {{{n}}} — die Kennung hat keinen Teil '{rest}' "
                                f"(Teile: {', '.join(teile) if teile else 'keine'})")
        elif props is not None and wurzel in props:
            continue
        else:
            kennt = sorted(fest | set(props or ()))
            p.fehler.append(f"{stelle}: Platzhalter {{{n}}} gibt es hier nicht (erlaubt: {', '.join(kennt)})")


def _aktion(besch, a, stelle, p):
    import jsonschema
    art = erz_schema.art(a)
    props = set(erz_schema.felder(a))
    x = a.get(erz_schema.X) or {}
    nl = (besch.get("nachlesen") or {}).get(a.get("nachlesen")) if a.get("nachlesen") else None
    if not a["name"].startswith(besch["praefix"].lower() + "_"):
        p.fehler.append(f"{stelle}: der Name muss mit '{besch['praefix'].lower()}_' beginnen "
                        "(so kollidiert er mit keinem anderen Werkzeug)")
    try:
        jsonschema.Draft202012Validator.check_schema(a["inputSchema"])
    except jsonschema.SchemaError as e:
        p.fehler.append(f"{stelle}/inputSchema: kein gültiges JSON Schema ({e.message[:120]})")
    try:
        erz_schema.pruefen({k: v for k, v in a.items()})
    except erz_schema.SchemaFehler as e:
        p.fehler.append(f"{stelle}: {e}")
    for r in FELDER_RESERVIERT:
        if r in props:
            p.fehler.append(f"{stelle}/inputSchema: ein Feld darf nicht '{r}' heißen (fester Platzhalter-Name)")
    _aufruf(besch, a["aufruf"], f"{stelle}/aufruf", p)
    kennung_form = (nl or {}).get("teile")
    ka = a.get("kennung_aus")
    fest_aufruf = {"kennung"} if art in ("aendern", "loeschen") else set()
    _platzhalter(a["aufruf"], fest_aufruf, props, f"{stelle}/aufruf", p, kennung_form)
    _arten(besch, a, art, props, ka, nl, kennung_form, stelle, p)
    for feld, regel in (a.get("vergleich") or {}).items():
        if feld not in props:
            p.fehler.append(f"{stelle}/vergleich/{feld}: das Werkzeug hat kein Argument '{feld}'")
        if regel["norm"] == "zeitpunkt" and not besch.get("zeitzone"):
            p.fehler.append(f"{stelle}/vergleich/{feld}: 'zeitpunkt' braucht 'zeitzone' im Kopf der Beschreibung")
        if regel.get("muster"):
            try:
                if re.compile(regel["muster"]).groups != 1:
                    p.fehler.append(f"{stelle}/vergleich/{feld}/muster: genau EINE Gruppe nötig")
            except re.error as e:
                p.fehler.append(f"{stelle}/vergleich/{feld}/muster: kein gültiger Ausdruck ({e})")
    _ausgabe(a, props, stelle, p)
    _probe(besch, a, art, props, stelle, p)


def _arten(besch, a, art, props, ka, nl, kennung_form, stelle, p):
    z = a.get("zurueck")
    if art == "lesen":
        for k in ("kennung_aus", "nachlesen", "vergleich", "zurueck"):
            if k in a:
                p.fehler.append(f"{stelle}/{k}: eine lesende Aktion hat kein '{k}'")
        if not a.get("ausgabe") and "ausgabe" not in a:
            p.warnungen.append(f"{stelle}: ohne 'ausgabe' bekommt die KI die rohe Antwort (gekürzt)")
        return
    if "ausgabe" in a:
        p.fehler.append(f"{stelle}/ausgabe: nur lesende Aktionen haben eine 'ausgabe'")
    if a.get("nachlesen") and nl is None:
        p.fehler.append(f"{stelle}/nachlesen: '{a['nachlesen']}' steht nicht im Kopf unter 'nachlesen' "
                        f"(vorhanden: {', '.join(besch.get('nachlesen') or {}) or 'nichts'})")
    if a.get("vergleich") and not nl:
        p.warnungen.append(f"{stelle}: 'vergleich' ohne 'nachlesen' wird nie angewandt")
    if nl and not ka:
        p.fehler.append(f"{stelle}: 'nachlesen' braucht 'kennung_aus' (woher kommt die Kennung?)")
    if art in ("aendern", "loeschen"):
        if not ka or "argument" not in ka:
            p.fehler.append(f"{stelle}/kennung_aus: bei '{art}' muss die Kennung aus einem Argument kommen "
                            "(kennung_aus: {\"argument\": \"…\"})")
        else:
            arg = ka["argument"]
            if arg not in props:
                p.fehler.append(f"{stelle}/kennung_aus: Argument '{arg}' gibt es nicht")
            elif arg not in erz_schema.pflicht(a):
                p.fehler.append(f"{stelle}/kennung_aus: Argument '{arg}' muss Pflicht sein")
        if kennung_form:
            fest = [t for t in kennung_form if t in props]
            if art == "aendern" and fest:
                p.fehler.append(f"{stelle}/inputSchema: {', '.join(fest)} gehören zur Kennung und dürfen "
                                "nicht änderbar sein (sonst findet das Nachlesen den Eintrag nicht mehr)")
        if art == "aendern" and len(props) < 2:
            p.fehler.append(f"{stelle}/inputSchema: 'aendern' braucht außer der Kennung mindestens ein änderbares Feld")
    if ka and "teile" in ka:
        for t in ka["teile"]:
            if t not in props:
                p.fehler.append(f"{stelle}/kennung_aus/teile: Argument '{t}' gibt es nicht")
        if nl and kennung_form != ka["teile"]:
            p.fehler.append(f"{stelle}/kennung_aus: teile {ka['teile']} müssen dieselben sein wie im "
                            f"Nachlesen '{a.get('nachlesen')}' ({kennung_form})")
    if ka and "antwort" in ka and kennung_form:
        p.fehler.append(f"{stelle}/kennung_aus: eine Kennung aus der Antwort kann nicht aus 'teile' bestehen")
    if z is None:
        return
    erwartet = {"anlegen": ("loeschen", "keins"), "aendern": ("schreiben", "keins"),
                "loeschen": ("wiederherstellen", "keins")}[art]
    (kind, aufruf), = z.items()
    if kind not in erwartet:
        p.fehler.append(f"{stelle}/zurueck: bei '{art}' ist {' oder '.join(erwartet)} möglich, nicht '{kind}'")
    elif kind != "keins":
        _aufruf(besch, aufruf, f"{stelle}/zurueck/{kind}", p)
        fest = {"kennung", "alt"} if kind != "loeschen" else {"kennung"}
        _platzhalter(aufruf, fest, props, f"{stelle}/zurueck/{kind}", p, kennung_form)
        if not ka:
            p.fehler.append(f"{stelle}/zurueck: der Rückbau braucht 'kennung_aus'")


def _ausgabe(a, props, stelle, p):
    o = a.get("ausgabe")
    if not o:
        return
    for k in ("kopf", "leer"):
        _platzhalter(o.get(k), set(), props, f"{stelle}/ausgabe/{k}", p)
    _platzhalter(o.get("eintraege"), set(), props, f"{stelle}/ausgabe/eintraege", p)
    _platzhalter(o["zeile"], {"e"}, props, f"{stelle}/ausgabe/zeile", p)


def _probe(besch, a, art, props, stelle, p):
    pr = a.get("probe")
    if pr is None:
        p.warnungen.append(f"{stelle}: ohne 'probe' (Beispiel-Argumente) kann die Probefahrt die Aktion nicht prüfen")
        return
    for k in pr["argumente"]:
        if k not in props:
            p.fehler.append(f"{stelle}/probe/argumente/{k}: das Werkzeug hat kein Argument '{k}'")
    vorher = pr.get("vorher")
    ziel = next((b for b in besch["aktionen"] if b["name"] == vorher), None)
    if art in ("aendern", "loeschen") or vorher:
        if ziel is None or erz_schema.art(ziel) != "anlegen":
            p.fehler.append(f"{stelle}/probe/vorher: muss der Name einer anlegenden Aktion sein "
                            "(sie legt das Probe-Objekt an)")
    if pr.get("kennung_in") and pr["kennung_in"] not in props:
        p.fehler.append(f"{stelle}/probe/kennung_in: das Werkzeug hat kein Argument '{pr['kennung_in']}'")
    if art != "lesen" and (pr.get("kennung_in") or pr.get("erwartet")):
        p.fehler.append(f"{stelle}/probe: 'kennung_in' und 'erwartet' gibt es nur bei lesen")


# ── Stufen ─────────────────────────────────────────────────────────────

def stufe(besch: dict, a: dict) -> str:
    """Die Stufe einer Aktion (Kopf dieser Datei). Rein aus dem, was die
    Beschreibung sagt — nichts wird geraten."""
    art = erz_schema.art(a)
    if art == "lesen":
        return LESEN
    z = a.get("zurueck") or {}
    nl = (besch.get("nachlesen") or {}).get(a.get("nachlesen") or "")
    beleg = bool(a.get("kennung_aus") and nl)
    if art == "loeschen":
        return VOLL if beleg and "wiederherstellen" in z else EINMALIG
    rueck = "loeschen" if art == "anlegen" else "schreiben"
    return VOLL if beleg and rueck in z else GEFRAGT


def stufen(besch: dict) -> dict:
    return {a["name"]: stufe(besch, a) for a in besch["aktionen"]}
