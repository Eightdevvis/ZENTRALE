"""Kalender-TUI: das Fenster „advanced" über dem Termin-Formular.

Sasha, 11.10.2026: „bitte setz die stylebox unter ein eigenes fenster, also
im formular für nen termin kann man auf ‚advanced' klicken und dort ist dann
stylebox oder typus wählbar, mit typ ‚normal' und ‚list' verfügbar, dann wird
der listentermin zu nem termintypen und nicht zu so nem extra shortcut".

Darum steht im Formular (kalender_werkzeuge.py) nur noch EIN Feld „Advanced"
mit einer Zusammenfassung („typ normal · stil keine"). Enter darauf öffnet
dieses Fenster mit diesen Zeilen:

  Typ       ‹ normal › | ‹ liste ›   (←→/Leertaste)
  Liste     gilt nur bei Typ liste: Enter öffnet den Kasten „welche Liste?"
            (bei Typ normal steht die Zeile gedämpft mit „—" und wird
            übersprungen — feste Plätze wie im Formular, 18.10.2026)
            (kalender_quellen.QuellenWahl — Listen ≡ und Projekte ◆)
  Stylebox  Vorschau; Enter öffnet die Stylebox (tui/bausteine/stylebox.py),
            ⌫/Entf = kein Stil
  Status    ‹ committed › | ‹ uncommitted › (←→/Leertaste). Sasha, 11.10.2026:
            „pack den committed/uncommitted status unter advanced im
            formular. lass den shortcut dazu aber drin" — u bleibt.

Tasten wie im Formular und in der Stylebox: ↑↓/Tab Zeile, Enter auf „Typ"
oder „Status" oder Strg-S = übernehmen und zurück ins Formular, Esc = alles hier
verwerfen. Liste und Stylebox liegen als eigene Kasten darüber (`unter`);
ihr Esc führt nur hierher zurück. Gespeichert wird erst mit dem Formular.

Tasten: Tastentabelle `Advanced.TASTEN`, eine Ansicht je Zeile (typ, liste,
stil, status); die Leiste ganz unten zeigt sie (nicht mehr der Kasten).

Reine Logik, kein Zeichnen, kein HTTP: die Listen holt die Bedienung über
`quellen()` (→ Antwort von GET /api/calendar/quellen oder None).
"""
from __future__ import annotations

from . import kalender_kasten, kalender_quellen, kalender_stil
from .tasten import Tasten

NORMAL, LISTE = "normal", "liste"
TYPEN = (NORMAL, LISTE)
COMMITTED, UNCOMMITTED = "committed", "uncommitted"
STATUS = (COMMITTED, UNCOMMITTED)

HILFE = {
    "typ": "normal = eigener Titel · liste = Titel ist der oberste offene Punkt",
    "liste": "die liste oder das projekt, aus dem der titel kommt",
    "stil": "rahmen, farben und muster des kastens",
    "status": "uncommitted = blass, nicht fest",
}


def wert_von(roh=None) -> dict:
    """Der Anfangswert aus einem API-Eintrag (oder leer für Neues):
    {"typ", "quelle": {art, id, name}|None, "stil": dict, "status"}.
    Status aus der Ebene (`layer` uncommitted → uncommitted)."""
    q = kalender_quellen.quelle_von(roh or {})
    status = UNCOMMITTED if (roh or {}).get("layer") == UNCOMMITTED else COMMITTED
    return {"typ": LISTE if q else NORMAL, "quelle": q, "stil": kalender_stil.von(roh or {}),
            "status": status}


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
    „typ liste: todo · stil ╔═╗ rand #ff8800" (+ „ · uncommitted")."""
    q = quelle(wert)
    typ = "typ liste: %s" % q["name"] if q else "typ normal"
    aus = "%s · stil %s" % (typ, _stil_text((wert or {}).get("stil")))
    return aus + (" · uncommitted" if (wert or {}).get("status") == UNCOMMITTED else "")


class Advanced:
    """Der Kasten. `taste(ch)` → 'weiter' | 'fertig' | 'abbruch';
    nach 'fertig' steht das Ergebnis in `wert()`."""

    titel = "advanced"

    def __init__(self, wert: dict, quellen=None, text=""):
        wert = wert or {}
        self.typ = wert.get("typ") if wert.get("typ") in TYPEN else NORMAL
        self.quelle = wert.get("quelle")      # bleibt gemerkt, auch wenn Typ normal
        self.stil = dict(wert.get("stil") or {})
        # Ohne „status" im Wert keine Zeile (z.B. ein Formular ohne Ebene)
        self.status = wert.get("status") if wert.get("status") in STATUS else None
        self.quellen, self.text = quellen, text
        self.i = 0
        self.fehler = ""
        self.unter = None                     # offene Stylebox oder QuellenWahl

    def wert(self) -> dict:
        w = {"typ": self.typ, "quelle": self.quelle if self.typ == LISTE else None,
             "stil": dict(self.stil)}
        if self.status:
            w["status"] = self.status
        return w

    def reihen(self) -> list:
        """Alle Zeilen, feste Plätze (die Zeile „Liste" steht immer da)."""
        return ["typ", "liste", "stil"] + (["status"] if self.status else [])

    def gilt(self) -> list:
        """Je Zeile: gilt sie gerade? („Liste" nur bei Typ liste)"""
        return [r != "liste" or self.typ == LISTE for r in self.reihen()]

    def _auf_aktive(self, schritt):
        g = self.gilt()
        self.i = max(0, min(self.i, len(g) - 1))
        for _ in range(len(g)):
            if g[self.i]:
                return
            self.i = (self.i + schritt) % len(g)

    @property
    def reihe(self) -> str:
        self._auf_aktive(1)
        return self.reihen()[self.i]

    def zeilen(self) -> list:
        """[(beschriftung, wert, aktiv, hilfe)] — wie Formular.zeilen;
        eine Zeile, die nicht gilt, hat den Wert „—"."""
        aus = []
        jetzt = self.reihen().index(self.reihe)
        for k, (r, g) in enumerate(zip(self.reihen(), self.gilt())):
            if not g:
                b, w = "Liste", "—"
            elif r == "typ":
                b, w = "Typ", "‹ %s ›" % self.typ
            elif r == "liste":
                b, w = "Liste", _quelle_text(self.quelle)
            elif r == "status":
                b, w = "Status", "‹ %s ›" % self.status
            else:
                b, w = "Stylebox", _stil_text(self.stil)
            aus.append((b, w, k == jetzt, HILFE[r]))
        return aus

    # ── Tasten (Tabelle: Ansicht = die Zeile, auf der man steht) ────────
    # Liegt ein Kasten darüber (`unter`: QuellenWahl oder die Stylebox), bekommt
    # der die Taste — er verteilt aus seiner eigenen Tabelle.
    _ZEILE = [("↑↓", "zeile", "row"), ("tab/shift+tab", "zeile")]
    _ENDE = [("ctrl+s", "uebernehmen", "apply"), ("esc", "verwerfen", "discard")]
    TASTEN = Tasten({
        "typ": [("←→", "typ", "type"), ("space", "typ"), ("enter", "uebernehmen", "apply")]
        + _ZEILE + _ENDE,
        "liste": [("enter", "liste", "choose list"), ("space/→", "liste")] + _ZEILE + _ENDE,
        "stil": [("enter", "stylebox", "stylebox"), ("space/→", "stylebox"),
                 ("⌫/del", "kein_stil", "no style")] + _ZEILE + _ENDE,
        "status": [("←→", "status", "commit"), ("space", "status"),
                   ("enter", "uebernehmen", "apply")] + _ZEILE + _ENDE,
    })

    def __repr__(self):
        return kalender_kasten.zustand(self)

    def ansicht(self) -> str:
        return self.reihe

    def taste(self, ch: int) -> str:
        if self.unter is not None:
            return self._unter_taste(ch)
        return self.TASTEN.verteilen(self, self.ansicht(), ch) or "weiter"

    def aktion_verwerfen(self, _t):
        return "abbruch"

    def aktion_uebernehmen(self, _t):
        return "fertig" if self._pruefen() else "weiter"

    def aktion_zeile(self, taste):
        self.fehler = ""
        schritt = 1 if taste in ("tab", "down") else -1
        self.i = (self.i + schritt) % len(self.reihen())
        self._auf_aktive(schritt)             # „Liste" bei Typ normal: übersprungen

    def aktion_typ(self, taste):
        self.fehler = ""
        k = TYPEN.index(self.typ) + (-1 if taste == "left" else 1)
        self.typ = TYPEN[k % len(TYPEN)]

    def aktion_status(self, _t):
        self.fehler = ""
        self.status = STATUS[(STATUS.index(self.status) + 1) % len(STATUS)]

    def aktion_liste(self, _t):
        self.fehler = ""
        self._liste_oeffnen()

    def aktion_stylebox(self, _t):
        self.fehler = ""
        self._box_oeffnen()

    def aktion_kein_stil(self, _t):
        self.fehler = ""
        self.stil = {}

    def _pruefen(self) -> bool:
        if self.typ == LISTE and not self.quelle:
            self.fehler = "erst eine liste wählen — oder typ normal"
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
        erg = u.taste(ch)                    # die Stylebox verteilt aus ihrer Tabelle
        if erg and erg[0] == "fertig":
            # Wert None = Eigenschaft entfernt (Stylebox seit af5915e); anwenden
            # lässt sie weg, statt None hineinzuschreiben.
            self.stil = kalender_stil.stil_kern.anwenden(self.stil, erg[1])
        if erg:
            self.unter = None
        return "weiter"
