# tui/bausteine/feld_dialog.py
#
# Ein kleiner Dialog, gebaut aus einer Feld-Beschreibung (2026-10-10). Die
# Felder kommen aus dem Katalog des Hubs (`GET /api/kacheln`, je Eintrag
# `felder`; Form: core/kachel_felder.py, memory/system/hub_bauplan.md
# „Katalog") — der Dialog kennt keine App. So bringt eine neue App ihren
# Anlege-Dialog mit, ohne dass die TUI etwas über sie weiß; die Regeln (z. B.
# „höchstens 31 Tage" beim Kalender) stehen in den Feldern, nicht hier. Der
# Hub prüft dieselben Regeln noch einmal.
#
# Nur Tastatur, wie der Kalender-Dialog davor: ↑↓ (tab) Feld, ←→ (leertaste)
# wählt bei wahl/bool, Ziffern/„-"/Text tippen, ⌫ löscht, enter (ctrl+s)
# legt an, esc bricht ab. Ein Modal im Sinn von canvas_arten.py (titel,
# taste, anzeige, tasten, aenderungen).

import curses
from datetime import date, timedelta

TIPPEN = ("zahl", "datum", "text")


def vorgabe(feld, heute):
    """Startwert; datum versteht „heute" und „heute+N"."""
    v = feld.get("vorgabe")
    if feld.get("typ") == "datum" and isinstance(v, str) and v.startswith("heute"):
        try:
            return (heute + timedelta(days=int(v[len("heute"):] or 0))).isoformat()
        except ValueError:
            return heute.isoformat()
    return v


def gilt(feld, werte):
    return all(werte.get(k) == v for k, v in (feld.get("wenn") or {}).items())


def _titel(feld):
    return str(feld.get("titel") or feld.get("name"))


def _wert(feld, roh):
    """Eingabe → (wert, None) oder (None, grund)."""
    typ = feld.get("typ")
    if typ == "zahl":
        s = str(roh).strip()
        if not s.lstrip("-").isdigit():
            g = feld.get("grenzen") or {}
            spanne = " (%s bis %s)" % (g.get("min", "…"), g.get("max", "…")) if g else ""
            return None, "%s: eine ganze zahl%s" % (_titel(feld), spanne)
        return int(s), None
    if typ == "datum":
        try:
            return date.fromisoformat(str(roh)).isoformat(), None
        except ValueError:
            return None, "%s: datum als JJJJ-MM-TT" % _titel(feld)
    return roh, None


def _grenze(feld, wert, werte):
    g, typ = feld.get("grenzen") or {}, feld.get("typ")
    if typ == "zahl" and "max" in g and wert > g["max"]:
        return "höchstens %s %s" % (g["max"], _titel(feld))
    if typ == "zahl" and "min" in g and wert < g["min"]:
        return "%s: mindestens %s" % (_titel(feld), g["min"])
    if typ == "text" and "max_laenge" in g and len(wert) > g["max_laenge"]:
        return "%s: höchstens %d zeichen" % (_titel(feld), g["max_laenge"])
    if typ == "datum" and g.get("nicht_vor") in werte:
        ab, d = date.fromisoformat(werte[g["nicht_vor"]]), date.fromisoformat(wert)
        if d < ab:
            return "„%s\" liegt vor „%s\"" % (_titel(feld), g["nicht_vor"])
        if "tage_max" in g and (d - ab).days + 1 > g["tage_max"]:
            return "höchstens %d tage — bitte kürzer" % g["tage_max"]
    return None


class FeldDialog:
    """Dialog aus `felder` (Katalog). aenderungen() → {"werte": {name: wert}}
    mit getypten Werten, nur Felder, die gerade gelten."""
    breite = 52                         # die Tastenzeile passt ganz hinein

    def __init__(self, felder, titel="neu", kopf=None, heute=None):
        heute = heute or date.today()
        self.felder = [f for f in felder if isinstance(f, dict) and f.get("name")]
        self.titel = titel
        self.kopf = kopf or titel
        self.eingabe = {}                    # name → Text (tippen) oder Wert (wahl/bool)
        for f in self.felder:
            v = vorgabe(f, heute)
            if f.get("typ") == "wahl":
                werte = [w.get("wert") for w in f.get("werte") or []]
                self.eingabe[f["name"]] = v if v in werte else (werte[0] if werte else None)
            elif f.get("typ") == "bool":
                self.eingabe[f["name"]] = bool(v)
            else:
                self.eingabe[f["name"]] = "" if v is None else str(v)
        self.feld = 0
        self.fehler = ""                     # auch von außen (Hub sagt nein)
        self.werte = None

    @property
    def hoehe(self):
        hilfe = sum(1 for f in self.felder if f.get("hilfe"))
        return len(self.felder) + hilfe + 6

    # ── Zustand ───────────────────────────────────────────────────────
    def sichtbar(self):
        """Die Felder, die bei den jetzigen Eingaben gelten (wenn)."""
        werte, raus = {}, []
        for f in self.felder:
            if gilt(f, werte):
                raus.append(f)
                werte[f["name"]] = self.eingabe[f["name"]]
        return raus

    def pruefen(self):
        """→ (werte, None) oder (None, grund) — dieselben Regeln wie der Hub."""
        werte = {}
        for f in self.sichtbar():
            roh = self.eingabe[f["name"]]
            if f.get("typ") in ("zahl", "datum") and roh == "":
                return None, "%s fehlt" % _titel(f)
            wert, grund = _wert(f, roh)
            if grund:
                return None, grund
            werte[f["name"]] = wert
        for f in self.sichtbar():
            grund = _grenze(f, werte[f["name"]], werte)
            if grund:
                return None, grund
        return werte, None

    def _aktuell(self):
        felder = self.sichtbar()
        self.feld = max(0, min(self.feld, len(felder) - 1))
        return felder[self.feld] if felder else None

    # ── Tasten ────────────────────────────────────────────────────────
    def taste(self, ch):
        f = self._aktuell()
        n = len(self.sichtbar())
        if ch == 27:
            return "abbrechen"
        if ch in (10, 13, curses.KEY_ENTER, 19):
            self.werte, self.fehler = self.pruefen()
            self.fehler = self.fehler or ""
            return "speichern" if self.werte is not None else None
        if f is None:
            return None
        typ, name = f.get("typ"), f["name"]
        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            self.feld = (self.feld - 1) % n
        elif ch in (curses.KEY_DOWN, 9):
            self.feld = (self.feld + 1) % n
        elif typ == "wahl" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
            werte = [w.get("wert") for w in f.get("werte") or []]
            i = werte.index(self.eingabe[name]) if self.eingabe[name] in werte else 0
            self.eingabe[name] = werte[(i + (-1 if ch == curses.KEY_LEFT else 1)) % len(werte)]
        elif typ == "bool" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
            self.eingabe[name] = not self.eingabe[name]
        elif typ in TIPPEN and ch in (curses.KEY_BACKSPACE, 127, 8):
            self.eingabe[name] = self.eingabe[name][:-1]
        elif typ in TIPPEN and self._passt(f, ch):
            self.eingabe[name] += chr(ch)
        else:
            return None
        self.fehler = ""
        return None

    def _passt(self, f, ch):
        """Darf dieses Zeichen in dieses Feld?"""
        if not 32 <= ch < 127:
            return False
        c, text, typ = chr(ch), self.eingabe[f["name"]], f.get("typ")
        if typ == "zahl":
            return (c.isdigit() or c == "-" and not text) and len(text) < 9
        if typ == "datum":
            return (c.isdigit() or c == "-") and len(text) < 10
        return len(text) < (f.get("grenzen") or {}).get("max_laenge", 200)

    # ── Zeichnen ──────────────────────────────────────────────────────
    def _zeigen(self, f):
        v = self.eingabe[f["name"]]
        if f.get("typ") == "wahl":
            t = next((w.get("titel") or w.get("wert") for w in f.get("werte") or []
                      if w.get("wert") == v), v)
            return "‹ %s ›" % t
        if f.get("typ") == "bool":
            return "‹ %s ›" % ("ja" if v else "nein")
        return str(v)

    def anzeige(self, breite, hoehe):
        felder = self.sichtbar()
        aktuell = self._aktuell()
        rand = max([len(_titel(f)) for f in self.felder] + [3]) + 2
        zeilen, cursor = [], (0, 0)
        for f in felder:
            if f is aktuell:
                spalte = rand if f.get("typ") not in TIPPEN else rand + len(self.eingabe[f["name"]])
                cursor = (len(zeilen), spalte)
            zeilen.append(_titel(f).ljust(rand) + self._zeigen(f))
            if f.get("hilfe"):
                zeilen.append(" " * rand + str(f["hilfe"]))
        zeilen.append("")
        _w, grund = self.pruefen()
        zeilen.append(self.fehler or grund or "")
        zr, zs = cursor
        return [z[:breite] for z in zeilen[:hoehe]], (zr, min(zs, max(0, breite - 1)))

    def tasten(self):
        return [("↑↓", "field"), ("←→", "choose"), ("enter", "add"), ("esc", "cancel")]

    def aenderungen(self):
        return {"werte": self.werte if self.werte is not None else (self.pruefen()[0] or {})}
