# core/werkzeug_erzeuger/allgemein.py
#
# Der ALLGEMEINE Adapter (2026-10-11): führt eine Anbindungs-Beschreibung
# aus (anbindung.py, anbindung.schema.json) und spricht dabei die Sprache des
# Werkzeug-Erzeugers (Schnittstelle: Kopf von __init__.py). Für ein neues
# Programm schreibt niemand mehr einen Adapter in Python — man füllt eine
# Beschreibung aus; die Schutzschichten (Schema-Prüfung, Gate, Nachlesen,
# Zurücknehmen, feste Satzform) kommen vom Erzeuger wie beim Kalender.
#
# Was dieser Adapter tut:
#   - Aufruf aus der Vorlage bauen (Platzhalter aus den Argumenten, der
#     Kennung, dem alten Stand), über den Transport senden (HTTP/MCP/Python);
#   - Antwort und Fehler nach den Regeln der Beschreibung auf Codes abbilden
#     (Ablehnung) — ein Fehler des Programms ist eine Ablehnung, nie ein Absturz;
#   - die Kennung bestimmen (aus der Antwort, aus einem Argument oder aus
#     Angaben zusammengesetzt, wenn das Programm keine eigene vergibt);
#   - nachlesen, vergleichen (vergleich.py), zurückbauen — und zwar nur, wo die
#     Beschreibung es kann (Stufen, anbindung.stufe): sonst ehrlich
#     „nicht belegt".
#
# Ein Fehler, nach dem unklar ist, ob das Programm geschrieben hat (Zeit-
# überschreitung NACH dem Senden), wird nie als „nichts geändert“ gemeldet
# (Ungewiss).

import json
import threading

from . import Quelle, anbindung, harness, schema as erz_schema, transport as tr
from . import vergleich, vorlage
from .harness import Ablehnung, Ergebnis, Ungewiss
from .vorlage import Kennung

MAX_TEXT = 8000          # Zeichen, die eine lesende Aktion höchstens an die KI gibt
MAX_ZEILEN = 50
ANTWORT_NICHTS = "Nichts gefunden."


# ── Fehler-Regeln ──────────────────────────────────────────────────────

def _trifft(wenn: dict, antwort: tr.Antwort) -> bool:
    if "status" in wenn:
        soll = wenn["status"] if isinstance(wenn["status"], list) else [wenn["status"]]
        if antwort.status not in soll:
            return False
    if "mcp_fehler" in wenn and antwort.mcp_fehler != wenn["mcp_fehler"]:
        return False
    if "text_enthaelt" in wenn and wenn["text_enthaelt"].casefold() not in (antwort.text or "").casefold():
        return False
    if "antwort" in wenn:
        werte = vorlage.zeiger_alle(antwort.daten, wenn["antwort"])
        if "vorhanden" in wenn and bool(werte) != wenn["vorhanden"]:
            return False
        if "gleich" in wenn and not (werte and werte[0] == wenn["gleich"]):
            return False
        if "vorhanden" not in wenn and "gleich" not in wenn and not werte:
            return False
    return True


def _kurz(text, n=240) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _grund_der_antwort(antwort: tr.Antwort) -> str:
    if isinstance(antwort.daten, dict):
        for k in ("error", "fehler", "message", "detail"):
            if isinstance(antwort.daten.get(k), str) and antwort.daten[k].strip():
                return _kurz(antwort.daten[k])
    return _kurz(antwort.text) or "keine Begründung"


# ── Der Adapter ────────────────────────────────────────────────────────

class AllgemeinerAdapter:
    def __init__(self, besch: dict, trans):
        self.besch, self.transport = besch, trans
        self.aktionen = {a["name"]: a for a in besch["aktionen"]}
        self.zone = besch.get("zeitzone")
        self._kontext = {}                     # kennung → {aktion, alt, args, nachlesen}
        self._lock = threading.Lock()

    # -- Stufen --
    def stufe(self, name: str) -> str:
        return anbindung.stufe(self.besch, self.aktionen[name])

    def frage_zusatz(self, name: str) -> str:
        st = self.stufe(name)
        if st == anbindung.GEFRAGT:
            return "(Ob es danach so dasteht, kann ZENTRALE bei diesem Programm nicht nachprüfen.)"
        if st == anbindung.EINMALIG:
            return ("(Das lässt sich danach nicht zurückholen und nicht nachprüfen — "
                    "darum nur dieses eine Mal.)")
        return ""

    def was(self, name: str, args: dict) -> str:
        a = self.aktionen.get(name) or {}
        alltag = (a.get(erz_schema.X) or {}).get("alltag")
        return (alltag[:1].upper() + alltag[1:]) if alltag else f"Aktion {name}"

    # -- Aufruf bauen und senden --
    def _rendern(self, aufruf: dict, ctx: dict, standard_args=None) -> dict:
        try:
            if "methode" in aufruf:
                raus = {"methode": aufruf["methode"],
                        "pfad": vorlage.text(aufruf["pfad"], ctx, "pfad")}
                if aufruf.get("abfrage"):
                    raus["abfrage"] = vorlage.fuellen(aufruf["abfrage"], ctx)
                if aufruf.get("body"):
                    raus["body"] = vorlage.fuellen(aufruf["body"], ctx)
                return raus
            raus = {k: aufruf[k] for k in ("werkzeug", "funktion") if k in aufruf}
            raus["argumente"] = (vorlage.fuellen(aufruf["argumente"], ctx) if "argumente" in aufruf
                                 else dict(standard_args or {}))
            return raus
        except vorlage.Fehlt as e:
            raise Ablehnung("PFLICHTFELD", f"{e} fehlt (wird für den Aufruf gebraucht)")

    def _senden(self, aufruf: dict, ctx: dict, a: dict | None, schreibt: bool,
                standard_args=None, nach_regeln=True) -> tr.Antwort:
        roh = self._rendern(aufruf, ctx, standard_args)
        try:
            antwort = self.transport.aufrufen(roh)
        except tr.TransportFehler as e:
            if e.gesendet and schreibt:
                raise Ungewiss(f"{e.grund} Ob das Programm es getan hat, ist unklar.")
            raise Ablehnung(e.code, e.grund)
        if nach_regeln:
            self._fehler_pruefen(a, antwort)
        return antwort

    def _fehler_pruefen(self, a, antwort: tr.Antwort):
        regeln = list((a or {}).get("fehler") or []) + list(self.besch.get("fehler") or [])
        for r in regeln:
            if _trifft(r["wenn"], antwort):
                grund = r.get("grund")
                if not grund and r.get("grund_aus"):
                    grund = vorlage.zeiger_eins(antwort.daten, r["grund_aus"])
                raise Ablehnung(r["code"], _kurz(grund) if grund else _grund_der_antwort(antwort))
        if antwort.fehler:
            raise Ablehnung("ABGELEHNT", "Das Programm hat abgelehnt: " + _grund_der_antwort(antwort))

    # -- Kennung --
    def _nl(self, a: dict):
        n = a.get("nachlesen")
        return (self.besch.get("nachlesen") or {}).get(n) if n else None

    def _kennung(self, text, teile) -> Kennung:
        text = str(text)
        if not teile:
            return Kennung(text)
        teil_werte = text.split("|")
        if len(teil_werte) != len(teile) or not all(t.strip() for t in teil_werte):
            raise Ablehnung("KENNUNG-UNGUELTIG",
                            f"Die Kennung besteht aus {len(teile)} Angaben mit | dazwischen "
                            f"({'|'.join(teile)}); bekommen: {text!r}")
        return Kennung(text, dict(zip(teile, (t.strip() for t in teil_werte))))

    def _kennung_neu(self, a: dict, nl, args: dict, antwort) -> Kennung:
        ka = a["kennung_aus"]
        if "teile" in ka:
            return self._kennung("|".join(str(args[t]) for t in ka["teile"]), ka["teile"])
        wert = vorlage.zeiger_eins(antwort.daten, ka["antwort"])
        if wert is None or wert == "":
            raise Ungewiss("Das Programm hat keine Kennung zurückgegeben — ob es angelegt ist, "
                           "ist nicht belegt.")
        return Kennung(str(wert))

    # -- Nachlesen --
    def _nicht_da(self, nl: dict, antwort: tr.Antwort) -> bool:
        bedingungen = nl.get("nicht_da") or [{"status": 404}]
        if any(_trifft(w, antwort) for w in bedingungen):
            return True
        return any(r["code"] == "NICHT-GEFUNDEN" and _trifft(r["wenn"], antwort)
                   for r in self.besch.get("fehler") or [])

    def lesen_eintrag(self, nl: dict, kennung) -> dict | None:
        """Der Eintrag zu einer Kennung, wie das Programm ihn jetzt hat; None,
        wenn es ihn nicht gibt. Mehrere Treffer → Ablehnung MEHRDEUTIG."""
        k = kennung if isinstance(kennung, Kennung) else self._kennung(kennung, nl.get("teile"))
        ctx = {"kennung": k}
        antwort = self._senden(nl["aufruf"], ctx, None, False, nach_regeln=False)
        if self._nicht_da(nl, antwort):
            return None
        self._fehler_pruefen(None, antwort)
        if antwort.daten in (None, "", [], {}):
            return None
        if nl.get("eintraege"):
            ziel = vorlage.text(nl["eintraege"], ctx, "zeiger")
            treffer = vorlage.zeiger_alle(antwort.daten, ziel)
        else:
            treffer = [antwort.daten]
        kandidaten = [e for t in treffer for e in (t if isinstance(t, list) else [t])]
        if nl.get("wo"):
            try:
                soll = {f: vorlage.text(v, ctx) for f, v in nl["wo"].items()}
            except vorlage.Fehlt as e:
                raise Ablehnung("KENNUNG-UNGUELTIG", f"{e} fehlt in der Kennung")
            kandidaten = [e for e in kandidaten if isinstance(e, dict)
                          and all(e.get(f) is not None
                                  and vergleich.normal("text", e[f]) == vergleich.normal("text", v)
                                  for f, v in soll.items())]
        # Dieselbe Serie erscheint an jedem ihrer Tage — gleiche Einträge zählen einmal.
        einmalig = {json.dumps(e, sort_keys=True, default=str): e for e in kandidaten if isinstance(e, dict)}
        kandidaten = list(einmalig.values())
        if not kandidaten:
            return None
        if len(kandidaten) > 1:
            raise Ablehnung("MEHRDEUTIG", f"{len(kandidaten)} Einträge passen auf diese Kennung")
        return kandidaten[0]

    def _zeile(self, nl, kennung, e: dict) -> str:
        if nl and nl.get("zeile"):
            return vorlage.text_nachsichtig(nl["zeile"], {"e": e, "kennung": kennung})
        return "Eintrag " + _kurz(json.dumps(e, ensure_ascii=False, default=str), 120)

    # -- Schnittstelle des Erzeugers --
    def ausfuehren(self, name: str, args: dict):
        a = self.aktionen[name]
        art = erz_schema.art(a)
        if art == "lesen":
            return self._lesen(a, args)
        return self._schreiben(a, art, args)

    def _lesen(self, a: dict, args: dict) -> Ergebnis:
        antwort = self._senden(a["aufruf"], dict(args), a, False, args)
        return Ergebnis(text=self._ausgabe(a, antwort, args))

    def _ausgabe(self, a: dict, antwort: tr.Antwort, args: dict) -> str:
        o = a.get("ausgabe")
        daten = antwort.daten if antwort.daten is not None else antwort.text
        if not o:
            text = json.dumps(daten, ensure_ascii=False, default=str) if not isinstance(daten, str) else daten
            return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " … (gekürzt)"
        try:
            ziel = vorlage.text(o["eintraege"], dict(args), "zeiger") if o.get("eintraege") else "/"
        except vorlage.Fehlt as e:
            raise Ablehnung("PFLICHTFELD", f"{e} fehlt")
        treffer = vorlage.zeiger_alle(daten, ziel)
        eintraege = [e for t in treffer for e in (t if isinstance(t, list) else [t])]
        if not eintraege:
            return o.get("leer") or ANTWORT_NICHTS
        grenze = o.get("hoechstens", MAX_ZEILEN)
        zeilen = [vorlage.text_nachsichtig(o["zeile"], {**args, "e": e}) for e in eintraege[:grenze]]
        kopf = vorlage.text_nachsichtig(o["kopf"], dict(args)) + "\n" if o.get("kopf") else ""
        mehr = f"\n… und {len(eintraege) - grenze} weitere" if len(eintraege) > grenze else ""
        text = kopf + "\n".join(zeilen) + mehr
        return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + " … (gekürzt)"

    def _merken(self, kennung, **werte):
        with self._lock:
            self._kontext[str(kennung)] = werte
            while len(self._kontext) > 200:
                self._kontext.pop(next(iter(self._kontext)))

    def _schreiben(self, a: dict, art: str, args: dict) -> Ergebnis:
        stufe = anbindung.stufe(self.besch, a)
        nl = self._nl(a)
        belegt = nl is not None and a.get("kennung_aus") is not None
        alt = kennung = None
        if art in ("aendern", "loeschen"):
            kennung = self._kennung((args[a["kennung_aus"]["argument"]]), (nl or {}).get("teile"))
            if belegt:
                alt = self.lesen_eintrag(nl, kennung)
                if alt is None:
                    raise Ablehnung("NICHT-GEFUNDEN", f"Zu „{kennung}“ gibt es nichts im Programm.")
            if art == "aendern" and len(args) < 2:
                raise Ablehnung("NICHTS-ZU-AENDERN", "Es ist kein Feld genannt, das sich ändern soll.")
        elif belegt and "teile" in a["kennung_aus"]:
            vorab = self._kennung("|".join(str(args[t]) for t in a["kennung_aus"]["teile"]), nl.get("teile"))
            if self.lesen_eintrag(nl, vorab) is not None:
                raise Ablehnung("GIBT-ES-SCHON", f"„{vorab}“ gibt es schon — nichts doppelt angelegt.")
        ctx = {**args, "kennung": kennung, "alt": alt or {}}
        antwort = self._senden(a["aufruf"], ctx, a, True, args)
        if stufe != anbindung.VOLL:
            return Ergebnis(art=art, unbelegt=True)
        if art == "anlegen":
            kennung = self._kennung_neu(a, nl, args, antwort)
        self._merken(kennung, aktion=a, alt=alt, args=dict(args), nachlesen=a["nachlesen"])
        regeln = a.get("vergleich") or {}
        return Ergebnis(
            kennung=str(kennung), art=art, vorher=alt,
            pruefe=(lambda e: vergleich.abweichungen(regeln, args, e, self.zone)) if regeln else None,
            subjekt=lambda e: self._zeile(nl, kennung, e))

    def nachlesen(self, kennung: str):
        """Schnittstelle des Erzeugers: der Eintrag zu einer Kennung."""
        with self._lock:
            k = self._kontext.get(str(kennung))
        specs = ([self.besch["nachlesen"][k["nachlesen"]]] if k else
                 list((self.besch.get("nachlesen") or {}).values()))
        for nl in specs:
            if nl.get("teile") and len(str(kennung).split("|")) != len(nl["teile"]):
                continue
            return self.lesen_eintrag(nl, kennung)
        return None

    def zurueckbauen(self, a: dict, kennung: str, args: dict, alt: dict | None) -> None:
        """Den Rückbau der Aktion senden: anlegen → loeschen, aendern →
        schreiben (mit dem alten Stand), loeschen → wiederherstellen."""
        z = a.get("zurueck") or {}
        (kind, aufruf), = z.items() if z else [(None, None)]
        if kind in (None, "keins"):
            raise Ablehnung("KEIN-RUECKBAU", "Für diese Aktion gibt es keinen Rückbau.")
        nl = self._nl(a)
        k = self._kennung(kennung, (nl or {}).get("teile"))
        self._senden(aufruf, {**args, "kennung": k, "alt": alt or {}}, a, True, args)

    def loeschen(self, kennung: str) -> None:
        k = self._kontext.get(str(kennung))
        if not k:
            raise Ablehnung("KENNUNG-UNBEKANNT", "Dazu liegt nichts zum Zurückbauen vor.")
        self.zurueckbauen(k["aktion"], kennung, k["args"], None)

    def wiederherstellen(self, kennung: str, vorher: dict) -> None:
        k = self._kontext.get(str(kennung))
        if not k:
            raise Ablehnung("KENNUNG-UNBEKANNT", "Dazu liegt nichts zum Zurückbauen vor.")
        self.zurueckbauen(k["aktion"], kennung, k["args"], vorher)

    def beschreiben(self, e: dict) -> str:
        return "Eintrag " + _kurz(json.dumps(e, ensure_ascii=False, default=str), 120)

    def kurz(self, kennung: str) -> str:
        return str(kennung)

    def ziel(self, kennung: str) -> str:
        """Was eine Kennung meint (für die Ja/Nein-Frage)."""
        try:
            for nl in (self.besch.get("nachlesen") or {}).values():
                if nl.get("teile") and len(str(kennung).split("|")) != len(nl["teile"]):
                    continue
                e = self.lesen_eintrag(nl, kennung)
                if e is not None:
                    return self._zeile(nl, self._kennung(kennung, nl.get("teile")), e)
        except Exception:       # noqa: BLE001 — die Frage darf nie an der Auflösung scheitern
            pass
        return f"#{kennung} (so nicht gefunden)"

    def schliessen(self):
        self.transport.schliessen()


# ── Aus der Beschreibung eine Quelle bauen ─────────────────────────────

def transport_aus(besch: dict, sender=None):
    t = besch["transport"]
    if t["art"] == "http":
        return tr.HttpTransport(t["basis"], t.get("auth"), t.get("zeitlimit", 15), sender=sender)
    if t["art"] == "mcp":
        return tr.McpTransport(t["kommando"], t.get("umgebung"), t.get("zeitlimit", 20))
    return tr.PythonTransport(t["modul"])


def _fuer_erzeuger(besch: dict) -> list:
    """Die Aktionen so, wie der Erzeuger sie liest: nur Schema + x-zentrale
    (die Teile der Anbindung bleiben im Adapter). Ohne Beleg-Stufe nie ein
    Dauer-Ja."""
    raus = []
    for a in besch["aktionen"]:
        e = {k: a[k] for k in ("name", "description", "inputSchema", "annotations") if k in a}
        x = dict(a.get(erz_schema.X) or {})
        if anbindung.stufe(besch, a) in (anbindung.GEFRAGT, anbindung.EINMALIG):
            x["immer_erlaubbar"] = False
        e[erz_schema.X] = x
        raus.append(e)
    return raus


def quelle_aus(besch: dict, trans=None, sender=None) -> Quelle:
    """Die Quelle für den Erzeuger. `trans` ersetzt den Transport (Tests,
    Probefahrt); `sender` ersetzt nur den HTTP-Absender."""
    adapter = AllgemeinerAdapter(besch, trans or transport_aus(besch, sender))
    return Quelle(name=besch["name"], praefix=besch["praefix"], bereich=besch["bereich"],
                  aktionen=_fuer_erzeuger(besch), adapter=adapter)
