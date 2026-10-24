"""Kalender-TUI: das Fenster „advanced" über dem Termin-Formular.

Sasha, 11.10.2026: „bitte setz die stylebox unter ein eigenes fenster, also
im formular für nen termin kann man auf ‚advanced' klicken und dort ist dann
stylebox oder typus wählbar, mit typ ‚normal' und ‚list' verfügbar, dann wird
der listentermin zu nem termintypen und nicht zu so nem extra shortcut".

Darum steht im Formular (kalender_werkzeuge.py) nur noch EIN Feld „Advanced"
mit einer Zusammenfassung („typ normal · stil keine"). Enter darauf öffnet
dieses Fenster mit diesen Zeilen:

  Typ       ‹ normal › | ‹ liste › | ‹ deadline ›   (←→/Leertaste)
  Liste     gilt nur bei Typ liste: Enter öffnet den Kasten „welche Liste?"
            (bei Typ normal steht die Zeile gedämpft mit „—" und wird
            übersprungen — feste Plätze wie im Formular, 18.10.2026)
            (kalender_quellen.QuellenWahl — Listen ≡ und Projekte ◆)
  Vorwarnung  gilt nur bei Typ deadline (20.10.2026): ab wann sie rot
            leuchtet und erinnert — tippen wie „3d", „12h", „1d12h"
            (Vorgabe 3d); sonst gedämpft „—", übersprungen
  Soll      gilt nur bei Typ deadline (24.10.2026): die eigene Wunsch-Abgabe
            vor der Muss-Zeit — als Wochentag+Uhrzeit „Di 18:00" (= der
            letzte Di 18:00 vor/an der Muss-Zeit) ODER als Abstand „-2d18h";
            leer = keine Soll-Zeit. Gespeichert wird der Abstand (soll_abstand)
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

from . import kalender_deadline, kalender_kasten, kalender_quellen, kalender_stil
from .tasten import Tasten

NORMAL, LISTE, DEADLINE = "normal", "liste", "deadline"
TYPEN = (NORMAL, LISTE, DEADLINE)
# Ein mehrtägiger Termin kann keine Deadline sein (Kern: DEADLINE-SPANNE).
TYPEN_SPANNE = (NORMAL, LISTE)
COMMITTED, UNCOMMITTED = "committed", "uncommitted"
STATUS = (COMMITTED, UNCOMMITTED)

HILFE = {
    "typ": "normal = eigener Titel · liste = Titel ist der oberste offene Punkt"
           " · deadline = ein Zeitpunkt, leuchtet rot",
    "vorwarnung": "ab wann sie leuchtet + erinnert: 3d, 12h, 1d12h",
    "soll": "eigene abgabe: Di 18:00 oder -2d18h · leer = keine",
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
    typ = DEADLINE if kalender_deadline.ist(roh) else (LISTE if q else NORMAL)
    return {"typ": typ, "quelle": q, "stil": kalender_stil.von(roh or {}),
            "status": status, "vorwarnung": kalender_deadline.vorwarnung(roh or {}),
            "soll_abstand": kalender_deadline.soll_abstand(roh or {})}


def ist_deadline(wert) -> bool:
    return (wert or {}).get("typ") == DEADLINE


def _dauer_lesen(text):
    """„3d" → 4320 (wie core/kalender_deadline.dauer_lesen; die TUI darf den
    Kern nicht importieren — tests/test_kalender_deadline_tui.py prüft, dass
    beide gleich rechnen)."""
    import re
    s = str(text or "").strip().lower().replace(" ", "")
    if s.isdigit():
        return int(s)
    m = re.match(r"^(?:(\d+)(?:d|t|tage?n?))?(?:(\d+)h)?(?:(\d+)m(?:in)?)?$", s)
    if not s or not m or not any(m.groups()):
        return None
    d, h, mi = (int(x or 0) for x in m.groups())
    v = d * 1440 + h * 60 + mi
    return v if v <= 366 * 1440 else None


def dauer_text(minuten) -> str:
    """4320 → „3d", 2160 → „1d12h", 90 → „1h30m"."""
    d, rest = divmod(max(0, int(minuten)), 1440)
    h, m = divmod(rest, 60)
    return "".join([f"{d}d"] * bool(d) + [f"{h}h"] * bool(h) + [f"{m}m"] * bool(m)) or "0m"


# ── Soll-Zeit: „Di 18:00" oder „-2d18h" (24.10.2026) ──────────────────
# muss = (Wochentag 0–6, Minute des Tages) der Muss-Zeit, aus dem Formular.
_WT = ("mo", "di", "mi", "do", "fr", "sa", "so")
SOLL_HOECHSTENS = kalender_deadline.SOLL_TAGE * 1440


def soll_lesen(text, muss=None):
    """→ (Minuten ≤ 0 | None, fehler | ""). Leer = keine Soll-Zeit (None, "").
    „Di 18:00" / „di 18" = der letzte Di 18:00 vor oder an der Muss-Zeit;
    „-2d18h" oder „2d18h" = so lange vorher; „+…" liegt danach → Fehler."""
    import re
    s = str(text or "").strip().lower().replace("\u2212", "-")
    if not s:
        return None, ""
    m = re.match(r"^(mo|di|mi|do|fr|sa|so)[a-z]*\.?\s*(\d{1,2})(?:[:.](\d{2}))?(?:\s*uhr)?$", s)
    if m:
        if muss is None:
            return None, "erst tag und uhrzeit — oder als abstand wie -2d18h"
        h, mi = int(m.group(2)), int(m.group(3) or 0)
        if h > 23 or mi > 59:
            return None, "uhrzeit gibt es nicht"
        mw, mmin = muss
        abstand = -(((mw - _WT.index(m.group(1))) % 7) * 1440 + mmin - (h * 60 + mi))
        return (abstand - 7 * 1440 if abstand > 0 else abstand), ""
    if s.startswith("+"):
        return None, "soll liegt vor der muss-zeit (ohne +)"
    v = _dauer_lesen(s.lstrip("-").strip())
    if v is None or v > SOLL_HOECHSTENS:
        return None, "soll wie Di 18:00 oder -2d18h (höchstens %dd vorher)" % (
            SOLL_HOECHSTENS // 1440)
    return -v, ""


def soll_text(abstand, muss=None) -> str:
    """Minuten → was im Feld steht: mit Muss-Zeit „Di 18:00" (genau, solange
    weniger als eine Woche davor), sonst „-2d18h"; None → ""."""
    if not isinstance(abstand, int) or isinstance(abstand, bool):
        return ""
    if muss is not None and -7 * 1440 < abstand <= 0:
        ges = muss[0] * 1440 + muss[1] + abstand
        tag, minute = divmod(ges, 1440)
        return "%s %02d:%02d" % (_WT[tag % 7].capitalize(), minute // 60, minute % 60)
    return ("-" if abstand < 0 else "") + dauer_text(abs(abstand))


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
    if ist_deadline(wert):
        typ = "typ deadline · vorwarnung %s" % dauer_text((wert or {}).get(
            "vorwarnung", kalender_deadline.VORWARNUNG_STANDARD))
        soll = (wert or {}).get("soll")
        if soll is None:
            soll = soll_text((wert or {}).get("soll_abstand"))
        if soll:
            typ += " · soll %s" % soll
    aus = "%s · stil %s" % (typ, _stil_text((wert or {}).get("stil")))
    return aus + (" · uncommitted" if (wert or {}).get("status") == UNCOMMITTED else "")


class Advanced:
    """Der Kasten. `taste(ch)` → 'weiter' | 'fertig' | 'abbruch';
    nach 'fertig' steht das Ergebnis in `wert()`."""

    titel = "advanced"

    def __init__(self, wert: dict, quellen=None, text="", typen=TYPEN, muss=None):
        wert = wert or {}
        # muss: (Wochentag, Minute) der Muss-Zeit aus dem Formular — für
        # „Di 18:00" (soll_lesen); None = nur der Abstand geht.
        self.muss = muss
        soll = wert.get("soll")
        self.soll = soll if isinstance(soll, str) else soll_text(wert.get("soll_abstand"), muss)
        self.typen = tuple(typen)
        self.typ = wert.get("typ") if wert.get("typ") in self.typen else NORMAL
        v = wert.get("vorwarnung")
        self.vorwarnung = dauer_text(v if isinstance(v, int) else
                                     kalender_deadline.VORWARNUNG_STANDARD)
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
        v = _dauer_lesen(self.vorwarnung)
        w["vorwarnung"] = v if v is not None else kalender_deadline.VORWARNUNG_STANDARD
        w["soll"] = self.soll.strip()
        w["soll_abstand"] = soll_lesen(self.soll, self.muss)[0]
        if self.status:
            w["status"] = self.status
        return w

    def reihen(self) -> list:
        """Alle Zeilen, feste Plätze (die Zeilen „Liste" und „Vorwarnung"
        stehen immer da; Vorwarnung nur, wo es Deadlines geben kann)."""
        return (["typ", "liste"] + (["vorwarnung", "soll"] if DEADLINE in self.typen else [])
                + ["stil"] + (["status"] if self.status else []))

    def gilt(self) -> list:
        """Je Zeile: gilt sie gerade? („Liste" nur bei Typ liste,
        „Vorwarnung"/„Soll" nur bei Typ deadline)"""
        nur = {"liste": LISTE, "vorwarnung": DEADLINE, "soll": DEADLINE}
        return [r not in nur or self.typ == nur[r] for r in self.reihen()]

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
            hilfe = HILFE[r]
            if not g:
                b, w = {"vorwarnung": "Vorwarnung", "soll": "Soll"}.get(r, "Liste"), "—"
            elif r == "vorwarnung":
                b, w = "Vorwarnung", self.vorwarnung + ("_" if k == jetzt else "")
            elif r == "soll":
                b, w = "Soll", self.soll + ("_" if k == jetzt else "")
                hilfe = self._soll_hilfe()
            elif r == "typ":
                b, w = "Typ", "‹ %s ›" % self.typ
            elif r == "liste":
                b, w = "Liste", _quelle_text(self.quelle)
            elif r == "status":
                b, w = "Status", "‹ %s ›" % self.status
            else:
                b, w = "Stylebox", _stil_text(self.stil)
            aus.append((b, w, k == jetzt, hilfe))
        return aus

    def _soll_hilfe(self) -> str:
        """Was das Getippte heißt: „= 2d18h vor muss · Di 18:00"."""
        v, fehler = soll_lesen(self.soll, self.muss)
        if v is None:
            return fehler or HILFE["soll"]
        anders = soll_text(v, self.muss)
        return "= %s vor muss%s" % (dauer_text(-v) if v else "0m",
                                    " · " + anders if anders and anders != self.soll else "")

    # ── Tasten (Tabelle: Ansicht = die Zeile, auf der man steht) ────────
    # Liegt ein Kasten darüber (`unter`: QuellenWahl oder die Stylebox), bekommt
    # der die Taste — er verteilt aus seiner eigenen Tabelle.
    _ZEILE = [("↑↓", "zeile", "row"), ("tab/shift+tab", "zeile")]
    _ENDE = [("ctrl+s", "uebernehmen", "apply"), ("esc", "verwerfen", "discard")]
    TASTEN = Tasten({
        "typ": [("←→", "typ", "type"), ("space", "typ"), ("enter", "uebernehmen", "apply")]
        + _ZEILE + _ENDE,
        "liste": [("enter", "liste", "choose list"), ("space/→", "liste")] + _ZEILE + _ENDE,
        "vorwarnung": [("type", "tippen", "type"), ("⌫", "zeichen_weg", "delete"),
                       ("ctrl+u", "leeren", "clear"), ("enter", "uebernehmen", "apply")]
        + _ZEILE + _ENDE,
        "soll": [("type", "tippen", "type"), ("⌫", "zeichen_weg", "delete"),
                 ("ctrl+u", "leeren", "clear"), ("enter", "uebernehmen", "apply")]
        + _ZEILE + _ENDE,
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
        k = self.typen.index(self.typ) + (-1 if taste == "left" else 1)
        self.typ = self.typen[k % len(self.typen)]

    def aktion_tippen(self, zeichen):          # Zeilen „Vorwarnung" und „Soll"
        self.fehler = ""
        if self.reihe == "soll":
            if len(zeichen) == 1 and (zeichen.isalnum() or zeichen in " :.-+"):
                self.soll = (self.soll + zeichen)[:16]
        elif len(zeichen) == 1 and (zeichen.isalnum() or zeichen == " "):
            self.vorwarnung = (self.vorwarnung + zeichen)[:12]

    def aktion_zeichen_weg(self, _t):
        self.fehler = ""
        if self.reihe == "soll":
            self.soll = self.soll[:-1]
        else:
            self.vorwarnung = self.vorwarnung[:-1]

    def aktion_leeren(self, _t):
        self.fehler = ""
        if self.reihe == "soll":
            self.soll = ""
        else:
            self.vorwarnung = ""

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
        if self.typ == DEADLINE and _dauer_lesen(self.vorwarnung) is None:
            self.fehler = "vorwarnung wie 3d, 12h, 1d12h (höchstens 366d)"
            self.i = self.reihen().index("vorwarnung")
            return False
        if self.typ == DEADLINE and soll_lesen(self.soll, self.muss)[1]:
            self.fehler = soll_lesen(self.soll, self.muss)[1]
            self.i = self.reihen().index("soll")
            return False
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
