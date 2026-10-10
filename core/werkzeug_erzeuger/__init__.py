# core/werkzeug_erzeuger/ — KI-Werkzeuge aus dem Schema ERZEUGEN.
#
# Sasha, 2026-10-10: „kalender api gibt format für termin anlegen — ki
# harness wird aus den feldern GEBAUT — ki tool ist so strukturiert damit ki
# keine scheiße macht — auch schwächere ki kann mit fremden kalender/anderem
# programm arbeiten, weil unser programm die schnittstelle zum fremden
# programm so ergänzt, dass die ki damit arbeiten MUSS." Plan:
# memory/system/hub_bauplan.md „KI-Werkzeuge aus dem Schema erzeugen";
# Mechanik und wie man eine Quelle anbindet: memory/ki/werkzeug_erzeuger.md.
#
#   Quelle (Aktions-Schemas, MCP-Form)  +  Adapter (Grundaktionen)
#        → werkzeuge(quelle): Werkzeug-Einträge fürs Register (gross),
#          jeder mit derselben Schutzschicht (harness.py).
#
# Ein Adapter ist SAUBER, wenn er
#   - jeden Eintrag über eine feste Kennung trifft (nie über einen Namen,
#     der zwei treffen kann),
#   - nachlesen(kennung) kann (sonst gibt es keinen Beleg — eine Quelle ohne
#     nachlesen bekommt nur ihre lesenden Aktionen frei),
#   - ablehnt statt still zu korrigieren: Ablehnung(code, grund).
#
# Adapter-Schnittstelle (Duck-Typing):
#   ausfuehren(name, args) -> Ergebnis      Pflicht
#   nachlesen(kennung) -> dict | None       Pflicht für Schreibendes
#   loeschen(kennung)                       Rückbau nach anlegen
#   wiederherstellen(kennung, vorher)       Rückbau nach aendern
#   beschreiben(eintrag) -> str             Satzanfang („Termin „X“ am …")
#   kurz(kennung) -> str                    Kennung, wie die KI sie liest
#   frage(name, args) -> str | None         eigene Ja/Nein-Frage (optional)
#   ziel(kennung) -> str                    was eine Kennung meint (Frage)
#   was(name, args) -> str                  Satzanfang eines Abbruchs
#
# Prompt-Cache: die Schemas einer Quelle sind Konstanten; werkzeuge() baut
# daraus bei jedem Aufruf dieselben Bytes. Das Register ruft es einmal beim
# Import (pro Prozess fest).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md): kennt kein Fach.

import copy
from dataclasses import dataclass

from werkzeug_eintrag import Werkzeug

from . import harness, schema
from .harness import Ablehnung, Ergebnis, passt  # noqa: F401  — öffentlich
from .schema import SchemaFehler  # noqa: F401


@dataclass
class Quelle:
    """Eine angebundene Quelle: Name, Vorsilbe ihrer Fehlercodes (K für den
    Kalender, core/fehlercodes.py), Bereich (core/ehrlichkeit.py BEREICH),
    die Aktions-Schemas und der Adapter."""
    name: str
    praefix: str
    bereich: str
    aktionen: list
    adapter: object


def _kann_belegen(adapter) -> bool:
    return callable(getattr(adapter, "nachlesen", None))


def werkzeuge(quelle: Quelle) -> list:
    """Die Werkzeug-Einträge der Quelle (nur gross: klein=None), in der
    Reihenfolge der Aktionen. Schreibende nur, wenn der Adapter nachlesen
    kann (Kopf dieser Datei)."""
    raus = []
    for aktion in quelle.aktionen:
        schema.pruefen(aktion)
        art = schema.art(aktion)
        if art != "lesen" and not _kann_belegen(quelle.adapter):
            continue
        raus.append(_eintrag(quelle, aktion, art))
    return raus


def _eintrag(quelle: Quelle, aktion: dict, art: str) -> Werkzeug:
    x = aktion.get(schema.X) or {}
    schreibt = art != "lesen"

    def ausfuehrer(args):
        return harness.ausfuehren(quelle, aktion, args)
    ausfuehrer.__name__ = f"erzeugt_{aktion['name']}"

    def frage(args):
        return harness.frage(quelle, aktion, args)

    worte = x.get("worte")
    return Werkzeug(
        name=aktion["name"],
        parameter=schema.fuer_modell(aktion),
        klein=None,
        gross=aktion["description"].strip(),
        erlaubnis=schreibt,
        frage=frage if schreibt else None,
        # „immer" nur fürs Anlegen: Ändern und Löschen überschreiben, ein
        # falsches Dauer-Ja kostete still Daten (core/werkzeug_fragen.py).
        immer_erlaubbar=x.get("immer_erlaubbar", art == "anlegen"),
        alltag=x.get("alltag"),
        schreibt=schreibt,
        beweis=x.get("beweis") or ("liest per Kennung nach, was jetzt dasteht"
                                   if schreibt else None),
        ausfuehrer=ausfuehrer,
        erzeugt=quelle.name,
        bereich=quelle.bereich,
        worte=tuple(worte) if worte else None,
        zuschnitt=schema.zuschnitt(aktion),
    )


# ── Ins Register einsetzen (an/aus) ────────────────────────────────────
# Einstellung `werkzeuge_erzeugt` (an|aus, Standard an; 2026-10-10): beim
# Import des Registers einmal gelesen — das Schema ist pro Prozess fest.

GROSS_FELDER = ("gross", "gross_parameter", "gross_ausfuehrer", "frage", "erzeugt",
                "bereich", "worte", "zuschnitt")


def eingeschaltet() -> bool:
    try:
        import ai_config
        wert = ai_config.setting("werkzeuge_erzeugt", "an")
    except Exception:
        wert = "an"
    return str(wert or "an").strip().lower() not in ("aus", "0", "false", "nein", "off")


def einsetzen(liste: list, nach_name: dict, erzeugt: list, an: bool, von_hand: dict) -> None:
    """Ein bestehender Eintrag behält seine klein-Seite byte-gleich und
    bekommt auf gross Beschreibung, Schema, Ausführer und Frage des
    Erzeugers (aus: die gemerkten handgeschriebenen zurück). Neue Werkzeuge
    kommen hinten an die Liste (aus: wieder weg)."""
    for neu in erzeugt:
        alt = nach_name.get(neu.name)
        if alt is None or alt is neu:
            if an and alt is None:
                liste.append(neu)
                nach_name[neu.name] = neu
            elif not an and alt is neu:
                liste.remove(neu)
                del nach_name[neu.name]
            continue
        if an:
            von_hand.setdefault(neu.name, {f: getattr(alt, f) for f in GROSS_FELDER})
            for f in GROSS_FELDER:
                setattr(alt, f, getattr(neu, {"gross_parameter": "parameter",
                                              "gross_ausfuehrer": "ausfuehrer"}.get(f, f)))
        elif neu.name in von_hand:
            for f, w in von_hand.pop(neu.name).items():
                setattr(alt, f, w)


# ── Zuschnitt je Modellprofil ──────────────────────────────────────────

def zuschneiden(tools: list, art: str, eintrag) -> list:
    """Die Werkzeug-Liste (OpenAI-Form) für eine Profil-Art („schwach"):
    Felder weg, einfachere Beschreibung — nur bei erzeugten Werkzeugen, die
    einen Zuschnitt mitbringen. `eintrag(name)` schlägt im Register nach.
    Kopien; die Liste der Schiene bleibt unberührt."""
    raus = []
    for t in tools:
        w = eintrag(t["function"]["name"])
        z = ((w.zuschnitt or {}).get(art) if w is not None and w.erzeugt else None)
        if z:
            t = copy.deepcopy(t)
            f = t["function"]
            for feld in z.get("weg", ()):
                f["parameters"]["properties"].pop(feld, None)
            if z.get("beschreibung"):
                f["description"] = z["beschreibung"]
        raus.append(t)
    return raus
