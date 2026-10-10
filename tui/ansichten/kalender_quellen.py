"""Kalender-TUI: Termine, deren Titel aus einer Liste oder einem Projekt kommt.

Sasha, 10.10.2026: „das ganze kann man im kalender einfach mit shift a oder
sowas whatever dann machen, man wählt ja eigentlich einfach nur ne liste für
nen termin slot aus, ansonsten soll sich das ganze ganz normal als termin
bearbeiten lassen, also bleibt der rest vom formular genau gleich."

Darum steht hier nur, was eine Liste MEHR braucht als ein normaler Termin:
  * QuellenWahl — der Kasten „welche Liste?" (Name + was jetzt oben steht,
    Tippen filtert, ↑↓ wählt, Enter nimmt). Danach kommt das ganz normale
    Formular aus kalender_werkzeuge.py.
  * Abhaken des angezeigten Punkts und die Zeilen fürs Ansehen.
Kern: core/kalender_quelle.py (Auflösung live, nie geschrieben beim Abhaken),
Routen /api/calendar/quellen, /api/calendar/quelle (GET/POST/DELETE).

Reine Logik, kein curses, kein HTTP (wie kalender_werkzeuge.py): die
Bedienung holt die Daten und führt die Pläne aus.
"""
from __future__ import annotations

LISTE, PROJEKT = "liste", "projekt"
ZEICHEN = {LISTE: "≡", PROJEKT: "◆"}


def _plan(**k):
    from .kalender_werkzeuge import _plan as p      # spät: Werkzeuge importieren uns
    return p(**k)


def eintraege(auswahl) -> list:
    """GET /api/calendar/quellen → [{art, id, name, titel, zustand}] — erst
    die Listen, dann die Projekte (wie die Antwort sie ordnet)."""
    auswahl = auswahl if isinstance(auswahl, dict) else {}
    raus = []
    for schl in ("listen", "projekte"):
        for z in auswahl.get(schl) or []:
            if isinstance(z, dict) and z.get("art") in ZEICHEN and z.get("id"):
                raus.append(z)
    return raus


def quelle_von(roh: dict) -> dict | None:
    """Die Quelle eines API-Eintrags als {art, id, name} — oder None."""
    q = roh.get("quelle") if isinstance(roh, dict) else None
    if not isinstance(q, dict) or q.get("art") not in ZEICHEN or not q.get("id"):
        return None
    return {"art": q["art"], "id": q["id"],
            "name": roh.get("quelle_name") or roh.get("label") or q["id"]}


def wort(art: str) -> str:
    return "Projekt" if art == PROJEKT else "Liste"


# ── Der Kasten „welche Liste?" ─────────────────────────────────────────
class QuellenWahl:
    """Eine Zeile je Liste/Projekt: Zeichen, Name, was jetzt oben steht.
    Tippen filtert (alle Buchstaben sind Text, darum ↑↓ statt j/k),
    Enter nimmt → `waehlen(quelle)` liefert den nächsten Plan (meist das
    Formular als `weiter`). Esc darin führt hierher zurück."""

    liste = True                    # Bedienung.zeichne_kasten erkennt den Kasten daran
    leer_text = "keine liste gefunden"

    def __init__(self, auswahl, waehlen, titel="termin für eine liste"):
        self.alle = eintraege(auswahl)
        self.waehlen, self.titel = waehlen, titel
        self.suche = ""
        self.i = 0
        self.fehler = ""
        self._u8 = b""
        self._ergebnis = None
        self.bei_abbruch = None

    def treffer(self) -> list:
        s = self.suche.casefold().strip()
        if not s:
            return self.alle
        return [z for z in self.alle
                if s in str(z.get("name") or "").casefold()
                or s in str(z.get("titel") or "").casefold()]

    def liste_zeilen(self) -> list:
        """[(zeichen, rolle, text, aktiv)] für Bedienung._zeichne_liste."""
        reihe = self.treffer()
        self.i = max(0, min(self.i, len(reihe) - 1))
        breit = max([len(str(z.get("name") or "")) for z in reihe] + [4])
        breit = min(breit, 28)
        aus = []
        for k, z in enumerate(reihe):
            name = str(z.get("name") or z["id"])
            name = name if len(name) <= breit else name[:breit - 1] + "…"
            oben = ("alles erledigt" if z.get("zustand") == "leer"
                    else str(z.get("titel") or ""))
            aus.append((ZEICHEN[z["art"]], "k_akzent" if z["art"] == PROJEKT else "faint",
                        "%-*s  %s" % (breit, name, oben), k == self.i))
        return aus

    def hilfe(self) -> str:
        suche = "suche: %s_ · " % self.suche if self.suche else "tippen filtert · "
        return suche + "↑↓ wählen · enter nimmt · ≡ liste ◆ projekt · esc"

    def taste(self, ch: int) -> str:
        self.fehler = ""
        reihe = self.treffer()
        n = len(reihe)
        if ch == 27:
            return "abbruch"
        if ch in (259, 353) and n:                  # ↑, Shift-Tab
            self.i = (self.i - 1) % n
        elif ch in (258, 9) and n:                  # ↓, Tab
            self.i = (self.i + 1) % n
        elif ch in (10, 13, 343):
            if not n:
                self.fehler = "nichts gefunden — suche ändern (backspace)"
                return "weiter"
            z = reihe[max(0, min(self.i, n - 1))]
            self._ergebnis = self.waehlen({"art": z["art"], "id": z["id"],
                                           "name": z.get("name") or z["id"]})
            weiter = (self._ergebnis or {}).get("weiter")
            if weiter is not None and getattr(weiter, "bei_abbruch", None) is None:
                weiter.bei_abbruch = lambda: self     # Esc im Formular → zurück zur Wahl
            return "fertig"
        elif ch in (8, 127, 263):
            self.suche, self._u8, self.i = self.suche[:-1], b"", 0
        elif ch == 21:                              # Strg-U
            self.suche, self.i = "", 0
        elif 0x80 <= ch <= 0xFF:                    # Umlaute: UTF-8 Byte für Byte
            self._u8 += bytes([ch])
            try:
                zeichen = self._u8.decode("utf-8")
            except UnicodeDecodeError:
                if len(self._u8) >= 4:
                    self._u8 = b""
                return "weiter"
            self._u8 = b""
            self.suche, self.i = (self.suche + zeichen)[:60], 0
        elif 32 <= ch < 0x80:
            self.suche, self.i = (self.suche + chr(ch))[:60], 0
        return "weiter"

    def plan(self) -> dict:
        return self._ergebnis or _plan()


# ── Pläne ──────────────────────────────────────────────────────────────
def plan_setzen(roh: dict, q: dict) -> dict:
    """Bestehenden Termin an eine Liste hängen (per Kennung)."""
    return _plan(aufrufe=[("POST", "/api/calendar/quelle",
                           {"kennung": roh["kennung"], "art": q["art"], "id": q["id"]})],
                 meldung="titel kommt jetzt aus %s „%s“" % (wort(q["art"]).lower(), q["name"]))


def plan_loesen(roh: dict, uebernehmen: bool) -> dict:
    titel = roh.get("titel_live") or roh.get("label") or ""
    return _plan(aufrufe=[("DELETE", "/api/calendar/quelle",
                           {"kennung": roh["kennung"], "titel_uebernehmen": bool(uebernehmen)})],
                 meldung="von der liste gelöst: " + (titel if uebernehmen
                                                     else roh.get("label") or ""))


def plan_abhaken(roh: dict) -> dict | None:
    """! auf einem Quellen-Termin: den angezeigten Punkt abhaken (die
    vorhandene Listen-Route). None, wenn es nichts abzuhaken gibt."""
    e = roh.get("quelle_eintrag") if isinstance(roh, dict) else None
    if not isinstance(e, dict) or not e.get("liste") or e.get("id") is None:
        return None
    return _plan(aufrufe=[("POST", "/api/lists/%s/items/%s/toggle" % (e["liste"], e["id"]), {})])


def meldung_abgehakt(vorher: str, neu: dict | None) -> str:
    """„erledigt: X — jetzt: Y" aus dem frisch geladenen Eintrag."""
    if not neu:
        return "erledigt: %s" % vorher
    if neu.get("quelle_zustand") == "leer":
        return "erledigt: %s — %s ist leer" % (vorher, neu.get("quelle_name") or "die liste")
    return "erledigt: %s — jetzt: %s" % (vorher, neu.get("titel_live") or "?")


def finde(daten: dict, kennung) -> dict | None:
    """Den Eintrag mit dieser Kennung irgendwo in den Kalenderdaten."""
    tage = daten.get("days") if isinstance(daten, dict) else None
    for liste in (tage.values() if isinstance(tage, dict) else []):
        for e in liste if isinstance(liste, list) else []:
            if isinstance(e, dict) and kennung and e.get("kennung") == kennung:
                return e
    return None


def details_zeilen(roh: dict, vorschau: dict | None) -> list:
    """Fürs Ansehen: Liste, aktueller Punkt und die nächsten offenen
    (vorschau = GET /api/calendar/quelle, fehlt sie: nur der Titel)."""
    q = quelle_von(roh)
    if q is None:
        return []
    w = "%-8s " % wort(q["art"])
    zustand = (vorschau or {}).get("zustand") or roh.get("quelle_zustand")
    if zustand == "fehlt":
        return [w + "gibt es nicht mehr — Titel: " + str(roh.get("label") or "")]
    if zustand == "leer":
        return [w + q["name"] + " — alles erledigt"]
    zeilen = [w + q["name"]]
    punkte = list((vorschau or {}).get("punkte") or [roh.get("titel_live") or "?"])
    zeilen.append("Jetzt    " + str(punkte[0]))
    for k, p in enumerate(punkte[1:4]):
        zeilen.append(("Danach   " if k == 0 else "         ") + str(p))
    return zeilen
