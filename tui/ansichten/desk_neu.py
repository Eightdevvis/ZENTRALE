# tui/ansichten/desk_neu.py
#
# Was `+` auf dem Desk außer den Arten des Bausteins anbietet (2026-10-10):
# die Kalender-Kachel. Der Wähler hinter `+` ist EINE Registrierung — die
# Arten des Canvas mit `neu_label` (canvas.Arten.anlegbar(), Zettel zuerst,
# dann Bild …). Eine Wahl, die erst fragen muss, hat `neu_dialog()`: die
# Ansicht zeigt das Modal und legt danach `neu(eid, x, y, werte)` hin.
#
# Die Kalender-Wahl ist keine eigene Element-Art: sie trägt sich unter dem
# Namen „kachel:kalender" ein (kein Element heißt so) und legt Elemente der
# allgemeinen Art „kachel" an (canvas_arten.Kachel) — eine Kachel ist ein
# Verweis auf ein Objekt einer anderen App, hier ein Stück Kalender.
#
# Kalender-Kachel: Bereich mitlaufend (ab heute N Tage) oder fest (von–bis),
# höchstens 31 Tage; Standard mitlaufend 7 Tage (Sasha, 2026-10-10). Bis 7
# Tage zeichnet die App eine Woche, darüber ein Monatsraster
# (core/kachel_kalender.py) — die Startgröße hier passt zu beidem.

import curses
from datetime import date, timedelta

GRENZE_TAGE = 31
SPALTE = 12                      # Woche: Breite einer Tages-Spalte
ZELLE_B, ZELLE_H = 11, 3         # Monat: eine Tageszelle


# ── Kalender ──────────────────────────────────────────────────────────

def tage_von(ref, heute):
    """Anzahl Tage eines Bezugs (wie core/kachel_kalender.bereich)."""
    if ref.get("modus") == "mitlaufend":
        return int(ref["tage"])
    return (date.fromisoformat(ref["bis"]) - date.fromisoformat(ref["von"])).days + 1


def kalender_groesse(ref, heute=None):
    """Startgröße (außen, mit Rahmen). Mitlaufend: für die meisten Wochen,
    die der Bereich je nach Wochentag schneiden kann — die Größe bleibt
    stehen, der Bereich wandert."""
    heute = heute or date.today()
    n = tage_von(ref, heute)
    if n <= 7:
        return n * (SPALTE + 1) - 1 + 2, 1 + 6 + 2
    if ref.get("modus") == "fest":
        von, bis = date.fromisoformat(ref["von"]), date.fromisoformat(ref["bis"])
        wochen = ((bis - (von - timedelta(days=von.weekday()))).days // 7) + 1
    else:
        wochen = (n + 6 + 6) // 7
    return 7 * ZELLE_B + 6 + 2, 1 + wochen * ZELLE_H + 2


def bezug_pruefen(modus, tage, von, bis):
    """Eingaben des Dialogs → (ref, None) oder (None, grund)."""
    if modus == "mitlaufend":
        if not tage.isdigit() or int(tage) < 1:
            return None, "wie viele tage? (1 bis %d)" % GRENZE_TAGE
        if int(tage) > GRENZE_TAGE:
            return None, "höchstens %d tage — bitte kürzer" % GRENZE_TAGE
        return {"modus": "mitlaufend", "tage": int(tage)}, None
    try:
        d0, d1 = date.fromisoformat(von), date.fromisoformat(bis)
    except ValueError:
        return None, "datum als JJJJ-MM-TT"
    if d1 < d0:
        return None, "„bis\" liegt vor „von\""
    if (d1 - d0).days + 1 > GRENZE_TAGE:
        return None, "höchstens %d tage — bitte kürzer" % GRENZE_TAGE
    return {"modus": "fest", "von": d0.isoformat(), "bis": d1.isoformat()}, None


class KalenderDialog:
    """Klein, nur Tastatur: ↑↓ Feld, ←→ mitlaufend/fest, Ziffern und „-"
    tippen, ⌫, enter legt an, esc bricht ab."""
    titel = "kalender"
    kopf = "kalender auf den desk"
    breite, hoehe = 48, 10           # klein: fünf Zeilen Inhalt + Tasten

    def __init__(self, heute=None):
        heute = heute or date.today()
        self.modus = "mitlaufend"
        self.werte = {"tage": "7", "von": heute.isoformat(),
                      "bis": (heute + timedelta(days=6)).isoformat()}
        self.feld = 0
        self.fehler = ""
        self.ref = None

    def felder(self):
        return ["modus"] + (["tage"] if self.modus == "mitlaufend" else ["von", "bis"])

    def taste(self, ch):
        felder = self.felder()
        name = felder[min(self.feld, len(felder) - 1)]
        if ch == 27:
            return "abbrechen"
        if ch in (10, 13, curses.KEY_ENTER, 19):
            self.ref, self.fehler = bezug_pruefen(self.modus, self.werte["tage"],
                                                  self.werte["von"], self.werte["bis"])
            return "speichern" if self.ref else None
        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            self.feld = (self.feld - 1) % len(felder)
        elif ch in (curses.KEY_DOWN, 9):
            self.feld = (self.feld + 1) % len(felder)
        elif name == "modus" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
            self.modus = "fest" if self.modus == "mitlaufend" else "mitlaufend"
        elif name != "modus" and ch in (curses.KEY_BACKSPACE, 127, 8):
            self.werte[name] = self.werte[name][:-1]
        elif name != "modus" and 0 <= ch < 256 and (chr(ch).isdigit() or chr(ch) == "-") \
                and len(self.werte[name]) < (2 if name == "tage" else 10):
            self.werte[name] += chr(ch)
        else:
            return None
        self.fehler = ""
        return None

    def anzeige(self, breite, hoehe):
        felder = self.felder()
        zeilen = ["art   ‹ %s ›" % self.modus]
        if self.modus == "mitlaufend":
            zeilen += ["tage  " + self.werte["tage"], "      ab heute, jeden tag neu"]
        else:
            zeilen += ["von   " + self.werte["von"], "bis   " + self.werte["bis"]]
        zeilen.append("")
        ref, grund = bezug_pruefen(self.modus, self.werte["tage"], self.werte["von"],
                                   self.werte["bis"])
        if self.fehler or grund:
            zeilen.append(self.fehler or grund)
        else:
            n = tage_von(ref, date.today())
            zeilen.append("%d tage · %s" % (n, "woche" if n <= 7 else "monat"))
        name = felder[min(self.feld, len(felder) - 1)]
        zeile = {"modus": 0, "tage": 1, "von": 1, "bis": 2}[name]
        spalte = 6 if name == "modus" else 6 + len(self.werte[name])
        return [z[:breite] for z in zeilen[:hoehe]], (zeile, min(spalte, max(0, breite - 1)))

    def tasten(self):
        return [("↑↓", "field"), ("←→", "mode"), ("enter", "add"), ("esc", "cancel")]

    def aenderungen(self):
        return {"ref": self.ref}


class KalenderWahl:
    """Eintrag „kalender" im Wähler hinter `+` → Kachel der App `kalender`,
    Art `ausschnitt` — ein Verweis, keine Kopie."""
    name = "kachel:kalender"
    neu_label = "kalender"

    def neu_dialog(self):
        return KalenderDialog()

    def neu(self, eid, x, y, werte=None):
        ref = (werte or {}).get("ref") or {"modus": "mitlaufend", "tage": 7}
        w, h = kalender_groesse(ref)
        return {"id": eid, "art": "kachel", "x": x, "y": y, "w": w, "h": h,
                "kachel": {"v": 1, "app": "kalender", "art": "ausschnitt", "ref": ref},
                "typ": "kachel · kalender/ausschnitt", "titel": ""}

    def zeichne(self, element, w, h):        # nie gebraucht: kein Element heißt so
        return []

    def modal(self, element):
        return None
