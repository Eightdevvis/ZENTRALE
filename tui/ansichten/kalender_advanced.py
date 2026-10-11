"""Kalender-TUI: das Fenster „advanced" über dem Termin-Formular.

Sasha, 11.10.2026: „bitte setz die stylebox unter ein eigenes fenster, also
im formular für nen termin kann man auf ‚advanced' klicken und dort ist dann
stylebox oder typus wählbar, mit typ ‚normal' und ‚list' verfügbar, dann wird
der listentermin zu nem termintypen und nicht zu so nem extra shortcut".

Darum steht im Formular (kalender_werkzeuge.py) nur noch EIN Feld „Advanced"
mit einer Zusammenfassung („typ normal · stil keine"). Enter darauf öffnet
dieses Fenster mit drei Zeilen:

  Typ       ‹ normal › | ‹ liste ›   (←→/Leertaste)
  Liste     nur bei Typ liste: Enter öffnet den Kasten „welche Liste?"
            (kalender_quellen.QuellenWahl — Listen ≡ und Projekte ◆)
  Stylebox  Vorschau; Enter öffnet die Stylebox (tui/bausteine/stylebox.py),
            ⌫/Entf = kein Stil

Tasten wie im Formular und in der Stylebox: ↑↓/Tab Zeile, Enter auf „Typ"
oder Strg-S = übernehmen und zurück ins Formular, Esc = alles hier
verwerfen. Liste und Stylebox liegen als eigene Kasten darüber (`unter`);
ihr Esc führt nur hierher zurück. Gespeichert wird erst mit dem Formular.

Reine Logik, kein curses, kein HTTP: die Listen holt die Bedienung über
`quellen()` (→ Antwort von GET /api/calendar/quellen oder None).
"""
from __future__ import annotations

from . import kalender_quellen, kalender_stil

NORMAL, LISTE = "normal", "liste"
TYPEN = (NORMAL, LISTE)

ENTER = (10, 13, 343)
STRG_S = 19
WEG = (8, 127, 263, 330)            # ⌫ / Entf
KEINE_TASTE = (-1, 410)             # Takt der Hauptschleife / KEY_RESIZE

HILFE = {
    "typ": "normal = eigener Titel · liste = Titel ist der oberste offene Punkt",
    "liste": "enter wählt die liste oder das projekt",
    "stil": "enter öffnet die Stylebox · ⌫ kein stil",
}
FUSS = "↑↓ zeile · ←→ typ · enter öffnen/übernehmen · strg-s übernehmen · esc verwerfen"


def wert_von(roh=None) -> dict:
    """Der Anfangswert aus einem API-Eintrag (oder leer für Neues):
    {"typ", "quelle": {art, id, name}|None, "stil": dict}."""
    q = kalender_quellen.quelle_von(roh or {})
    return {"typ": LISTE if q else NORMAL, "quelle": q, "stil": kalender_stil.von(roh or {})}


def quelle(wert: dict):
    """Die Quelle, die gilt — nur bei Typ liste."""
    wert = wert or {}
    return wert.get("quelle") if wert.get("typ") == LISTE else None


def _quelle_text(q) -> str:
    if not q:
        return "‹ wählen … ›"
    return "%s %s" % (kalender_quellen.ZEICHEN.get(q["art"], "≡"), q["name"])


def _stil_text(st) -> str:
    return kalender_stil.vorschau_text(st) if st else "keine"     # ein „nichts" (be1e76b): keine


def zusammenfassung(wert: dict) -> str:
    """Die Zeile im Formular: „typ normal · stil keine" bzw.
    „typ liste: todo · stil ╔═╗ rand #ff8800"."""
    q = quelle(wert)
    typ = "typ liste: %s" % q["name"] if q else "typ normal"
    return "%s · stil %s" % (typ, _stil_text((wert or {}).get("stil")))


class Advanced:
    """Der Kasten. `taste(ch)` → 'weiter' | 'fertig' | 'abbruch';
    nach 'fertig' steht das Ergebnis in `wert()`."""

    titel = "advanced"

    def __init__(self, wert: dict, quellen=None, text=""):
        wert = wert or {}
        self.typ = wert.get("typ") if wert.get("typ") in TYPEN else NORMAL
        self.quelle = wert.get("quelle")      # bleibt gemerkt, auch wenn Typ normal
        self.stil = dict(wert.get("stil") or {})
        self.quellen, self.text = quellen, text
        self.i = 0
        self.fehler = ""
        self.unter = None                     # offene Stylebox oder QuellenWahl

    def wert(self) -> dict:
        return {"typ": self.typ, "quelle": self.quelle if self.typ == LISTE else None,
                "stil": dict(self.stil)}

    def reihen(self) -> list:
        return ["typ"] + (["liste"] if self.typ == LISTE else []) + ["stil"]

    @property
    def reihe(self) -> str:
        r = self.reihen()
        self.i = max(0, min(self.i, len(r) - 1))
        return r[self.i]

    def zeilen(self) -> list:
        """[(beschriftung, wert, aktiv, hilfe)] — wie Formular.zeilen."""
        aus = []
        for k, r in enumerate(self.reihen()):
            if r == "typ":
                b, w = "Typ", "‹ %s ›" % self.typ
            elif r == "liste":
                b, w = "Liste", _quelle_text(self.quelle)
            else:
                b, w = "Stylebox", _stil_text(self.stil)
            aus.append((b, w, k == self.i, HILFE[r]))
        return aus

    # ── Tasten ─────────────────────────────────────────────────────────
    def taste(self, ch: int) -> str:
        if ch in KEINE_TASTE:
            return "weiter"
        if self.unter is not None:
            return self._unter_taste(ch)
        if ch == 27:
            return "abbruch"
        r = self.reihe
        n = len(self.reihen())
        if ch == STRG_S or (ch in ENTER and r == "typ"):
            return "fertig" if self._pruefen() else "weiter"
        self.fehler = ""
        if ch in (9, 258):                    # Tab, ↓
            self.i = (self.i + 1) % n
        elif ch in (353, 259):                # Shift-Tab, ↑
            self.i = (self.i - 1) % n
        elif r == "typ" and ch in (260, 261, 32):
            k = TYPEN.index(self.typ) + (-1 if ch == 260 else 1)
            self.typ = TYPEN[k % len(TYPEN)]
        elif r == "liste" and ch in ENTER + (32, 261):
            self._liste_oeffnen()
        elif r == "stil" and ch in ENTER + (32, 261):
            self._box_oeffnen()
        elif r == "stil" and ch in WEG:
            self.stil = {}
        return "weiter"

    def _pruefen(self) -> bool:
        if self.typ == LISTE and not self.quelle:
            self.fehler = "erst eine liste wählen (enter) — oder typ normal"
            self.i = self.reihen().index("liste")
            return False
        return True

    def _liste_oeffnen(self):
        auswahl = self.quellen() if self.quellen else None
        if auswahl is None:
            self.fehler = "listen nicht erreichbar — backend?"
            return
        if not kalender_quellen.eintraege(auswahl):
            self.fehler = "keine listen gefunden"
            return

        def waehlen(q):
            self.quelle = q
            return kalender_quellen._plan()
        self.unter = kalender_quellen.QuellenWahl(auswahl, waehlen,
                                                  titel="welche liste?")

    def _box_oeffnen(self):
        try:
            from tui.bausteine.stylebox import Stylebox
        except ImportError:             # als Skript gestartet: tui/ liegt im Pfad
            from bausteine.stylebox import Stylebox
        # Vorschau mit dem Titel; noch keiner, aber Typ liste: der Name der Liste
        q = self.quelle if self.typ == LISTE else None
        text = self.text or (q or {}).get("name") or "Termin"
        self.unter = Stylebox(self.stil, list(kalender_stil.ANGEBOT), titel="stylebox",
                              text=text)

    def _unter_taste(self, ch) -> str:
        u = self.unter
        if isinstance(u, kalender_quellen.QuellenWahl):
            if u.taste(ch) in ("fertig", "abbruch"):     # waehlen() hat schon gesetzt
                self.unter = None
            return "weiter"
        erg = u.taste(ch)                                # Stylebox
        if erg and erg[0] == "fertig":
            # Wert None = Eigenschaft entfernt (Stylebox seit af5915e); anwenden
            # lässt sie weg, statt None hineinzuschreiben.
            self.stil = kalender_stil.stil_kern.anwenden(self.stil, erg[1])
        if erg:
            self.unter = None
        return "weiter"
