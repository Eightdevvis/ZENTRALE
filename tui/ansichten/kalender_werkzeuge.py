"""Kalender-Werkzeuge: Auswahl, Fragen in der untersten Zeile, Aufrufe.

Sasha, 07.10.2026: „bearbeiten und löschen einfach wie bei calcurse,
generell übernehm so viel du kannst von den anderen programmen". Darum:

- Tasten und Abläufe wie calcurse (a anlegen, e bearbeiten, d löschen,
  r wiederholen, Enter ansehen, c/p kopieren/einfügen, g gehe zu, Tab
  wechselt den Kasten, t/T w/W m/M y/Y springen). Fragen erscheinen wie
  dort Schritt für Schritt in der untersten Zeile.
- „nur dieser Tag oder alle?" bei Routinen und Spannen wie im Handy-Kalender.

EIN Kalender, mehrere Ansichten: A/B/C zeichnen nur. Auswahl, Dialoge und
die Backend-Aufrufe stehen allein hier — und die Reihenfolge der Termine
eines Tages kommt aus derselben Funktion, mit der die Ansicht zeichnet
(kalender_ansichten._tag_eintraege). „Der dritte Termin" ist also immer
der, den man sieht.

Reine Logik, kein curses, kein HTTP: ein Dialog sammelt Antworten, `plan()`
macht daraus Aufrufe [(methode, pfad, body)], die die Ansicht ausführt.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .kalender_ansichten import _tag_eintraege

WT_KURZ = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
WT_CODE = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
WT_LANG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
           "Samstag", "Sonntag")
FREQ_TEXT = {"DAILY": "täglich", "WEEKLY": "wöchentlich", "MONTHLY": "monatlich",
             "YEARLY": "jährlich"}


# ── Eingaben lesen ─────────────────────────────────────────────────────
def zeit(s: str) -> str | None:
    """'9' '9:30' '930' '18.00' → 'HH:MM'; sonst None."""
    s = (s or "").strip().replace(".", ":")
    if not s:
        return None
    if ":" in s:
        h, _, m = s.partition(":")
    elif s.isdigit() and len(s) in (3, 4):
        h, m = s[:-2], s[-2:]
    elif s.isdigit():
        h, m = s, "0"
    else:
        return None
    try:
        h, m = int(h), int(m)
    except ValueError:
        return None
    return "%02d:%02d" % (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def dauer(s: str) -> int | None:
    """calcurse-Dauer → Minuten: '+45' '+1:30' '+2h' '+2d20h' '+1h30m'."""
    s = (s or "").strip().lower()
    if not s.startswith("+"):
        return None
    s = s[1:].strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    m = re.fullmatch(r"(\d+):(\d{1,2})", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", s)
    if m and any(m.groups()):
        d, h, mi = (int(x) if x else 0 for x in m.groups())
        return d * 1440 + h * 60 + mi
    return None


def datum(s: str, heute: date) -> date | None:
    """'14.10.' '14.10.2026' '14.10.26' '2026-10-14' → Datum. Ohne Jahr: das
    nächste solche Datum ab heute (wie man es meint)."""
    s = (s or "").strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?", s)
    if not m:
        return None
    t, mo, j = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        if j:
            j = int(j)
            return date(j + 2000 if j < 100 else j, mo, t)
        d = date(heute.year, mo, t)
        return d if d >= heute else date(heute.year + 1, mo, t)
    except ValueError:
        return None


def wochentage(s: str) -> list | None:
    """'di do' 'Di,Do' 'mo-fr' → ['TU','TH'] …; leer → []; Murks → None."""
    s = (s or "").strip().lower()
    if not s:
        return []
    kurz = [w.lower() for w in WT_KURZ]
    out = []
    for teil in re.split(r"[,\s]+", s):
        if "-" in teil:
            a, _, b = teil.partition("-")
            if a[:2] not in kurz or b[:2] not in kurz:
                return None
            i, j = kurz.index(a[:2]), kurz.index(b[:2])
            out += [WT_CODE[k] for k in range(i, j + 1)] if i <= j else [None]
        elif teil[:2] in kurz:
            out.append(WT_CODE[kurz.index(teil[:2])])
        else:
            return None
    return None if None in out else sorted(set(out), key=WT_CODE.index)


def datum_text(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def regel_text(rrule: str | None) -> str:
    """'FREQ=WEEKLY;BYDAY=TU,TH' → 'wöchentlich: Di, Do' — fürs Ansehen."""
    if not rrule:
        return ""
    teile = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    f = FREQ_TEXT.get(teile.get("FREQ", ""), teile.get("FREQ", "?").lower())
    n = int(teile.get("INTERVAL", "1") or 1)
    if n > 1:
        f = {"täglich": "alle %d Tage", "wöchentlich": "alle %d Wochen",
             "monatlich": "alle %d Monate", "jährlich": "alle %d Jahre"}.get(f, f + " ×%d") % n
    if teile.get("BYDAY"):
        f += ": " + ", ".join(WT_KURZ[WT_CODE.index(c[-2:])] for c in teile["BYDAY"].split(",")
                              if c[-2:] in WT_CODE)
    elif teile.get("BYMONTHDAY") and not teile.get("BYMONTH"):
        f += " am %s." % teile["BYMONTHDAY"]
    elif teile.get("BYMONTH") and teile.get("BYMONTHDAY"):
        f += " am %s.%s." % (teile["BYMONTHDAY"], teile["BYMONTH"])
    if teile.get("UNTIL"):
        try:
            f += " bis " + datum_text(datetime.strptime(teile["UNTIL"][:8], "%Y%m%d").date())
        except ValueError:
            pass
    return f


# ── Was ist ausgewählt? ────────────────────────────────────────────────
def eintraege(daten: dict, tag: date, erledigte: bool) -> list:
    """Die Termine eines Tages, so wie die Ansicht sie zeigt (gleiche
    Reihenfolge, gleiche Filter). Jeder hat t["roh"] = API-Eintrag."""
    return _tag_eintraege(daten if isinstance(daten, dict) else {},
                          tag.isoformat(), erledigte)


def art(roh: dict) -> str:
    """'einmal' | 'routine' | 'spanne'."""
    if roh.get("recurring"):
        return "routine"
    if roh.get("spanning"):
        return "spanne"
    return "einmal"


def todo_punkte(daten: dict) -> tuple:
    """(lid, [items]) der Wochenliste, in Listen-Reihenfolge."""
    wp = daten.get("weekplan") if isinstance(daten, dict) else None
    if not isinstance(wp, dict):
        return None, []
    items = [i for i in (wp.get("items") or []) if isinstance(i, dict)]
    return wp.get("lid"), items


# ── Dialog: Fragen in der untersten Zeile ──────────────────────────────
class Schritt:
    """Eine Frage. art='text' (tippen, Enter) oder 'wahl' (eine Taste aus
    `wahl`). `lesen(text)` → (ok, wert_oder_fehlertext). `wenn(antworten)`
    entscheidet, ob die Frage überhaupt kommt."""

    def __init__(self, name, frage, art="text", vorgabe="", wahl=None,
                 lesen=None, wenn=None):
        self.name, self.frage, self.art = name, frage, art
        self.vorgabe, self.wahl = vorgabe or "", wahl or {}
        self.lesen = lesen or (lambda s: (True, s.strip()))
        self.wenn = wenn or (lambda a: True)


class Dialog:
    """Kurze Rückfragen (löschen? j/n, nur dieser Tag?, gehe zu …) als
    kleiner Kasten. Schritte nacheinander abfragen. `plan` (antworten → Plan) wird erst
    gerufen, wenn alle beantwortet sind. Esc bricht ab."""

    def __init__(self, titel, schritte, plan):
        self.titel, self.schritte, self._plan = titel, schritte, plan
        self.antworten: dict = {}
        self.i = -1
        self.eingabe = ""
        self.fehler = ""
        self._u8 = b""          # angefangenes UTF-8-Zeichen (curses liefert Bytes)
        self._weiter()

    def _weiter(self):
        self.i += 1
        while self.i < len(self.schritte) and not self.schritte[self.i].wenn(self.antworten):
            self.i += 1
        if self.i < len(self.schritte):
            self.eingabe = self.schritte[self.i].vorgabe
            self.fehler = ""

    @property
    def fertig(self) -> bool:
        return self.i >= len(self.schritte)

    @property
    def schritt(self):
        return None if self.fertig else self.schritte[self.i]

    def taste(self, ch: int) -> str:
        """→ 'weiter' | 'fertig' | 'abbruch'."""
        s = self.schritt
        if s is None:
            return "fertig"
        if ch == 27:
            return "abbruch"
        if s.art == "wahl":
            k = chr(ch).lower() if 0 <= ch < 0x110000 else ""
            if k in s.wahl:
                self.antworten[s.name] = s.wahl[k]
                self._weiter()
            elif ch in (10, 13) and "" in s.wahl:
                self.antworten[s.name] = s.wahl[""]
                self._weiter()
            else:
                self.fehler = "bitte " + "/".join(x for x in s.wahl if x)
            return "fertig" if self.fertig else "weiter"
        if ch in (10, 13):
            ok, wert = s.lesen(self.eingabe)
            if not ok:
                self.fehler = wert
                return "weiter"
            self.antworten[s.name] = wert
            self._weiter()
            return "fertig" if self.fertig else "weiter"
        if ch in (8, 127, 263):           # Backspace (263 = curses.KEY_BACKSPACE)
            self.eingabe = self.eingabe[:-1]
            self._u8 = b""
        elif ch == 21:                    # Strg-U: Zeile leeren
            self.eingabe = ""
        elif 0x80 <= ch <= 0xFF:          # Umlaute: getch liefert UTF-8 Byte für Byte
            self._u8 += bytes([ch])
            try:
                zeichen = self._u8.decode("utf-8")
            except UnicodeDecodeError:
                if len(self._u8) >= 4:
                    self._u8 = b""
                return "weiter"
            self._u8 = b""
            if len(self.eingabe) < 200:
                self.eingabe += zeichen
        elif 32 <= ch < 0x80:
            if len(self.eingabe) < 200:
                self.eingabe += chr(ch)
        return "weiter"

    def zeile(self) -> str:
        s = self.schritt
        if s is None:
            return ""
        txt = "%s: %s" % (s.frage, self.eingabe if s.art == "text" else "")
        if s.art == "text":
            txt += "_"
        if self.fehler:
            txt += "   ⚠ " + self.fehler
        return txt

    def plan(self) -> dict:
        return self._plan(self.antworten)


def _plan(aufrufe=(), meldung="", konflikt=None, danach=None, weiter=None):
    """aufrufe: [(methode, pfad, body)]; konflikt: Body für die Vorprüfung
    (/api/calendar/konflikte) — kommt etwas zurück, fragt die Ansicht erst
    nach; danach: {"tag": date} o.ä. für die Auswahl nach dem Speichern."""
    return {"aufrufe": list(aufrufe), "meldung": meldung,
            "konflikt": konflikt, "danach": danach or {}, "weiter": weiter}


def _l_zeit(leer_ok=True):
    def lesen(s):
        if not s.strip():
            return (True, None) if leer_ok else (False, "uhrzeit fehlt")
        z = zeit(s)
        return (True, z) if z else (False, "uhrzeit wie 18:00")
    return lesen


def _l_titel(s):
    s = s.strip()
    return (True, s) if s else (False, "titel fehlt")


def _l_datum(heute, leer=None):
    def lesen(s):
        if not s.strip():
            return (True, leer)
        d = datum(s, heute)
        return (True, d) if d else (False, "datum wie 14.10. oder 14.10.2026")
    return lesen


def _l_zahl(mini=1, leer=1):
    def lesen(s):
        if not s.strip():
            return True, leer
        try:
            n = int(s.strip())
        except ValueError:
            return False, "eine zahl"
        return (True, n) if n >= mini else (False, "mindestens %d" % mini)
    return lesen


# ── Formular: der Kasten zum Anlegen und Bearbeiten ───────────────────
# Sasha, 07.10.2026: „eigentlich sollte es ja ein modal geben wo man nen
# termin einträgt". Alle Felder auf einmal wie „Termin erstellen" im
# Google-Kalender; ↑↓/Tab wechselt das Feld, ←→ blättert in Auswahlfeldern,
# Enter speichert, Esc bricht ab. Felder, die gerade keinen Sinn ergeben
# (Uhrzeit bei ganztägig, Wochentage ohne wöchentlich), sind ausgeblendet.
WIEDERHOLUNG = ("keine", "täglich", "wöchentlich", "monatlich", "jährlich")
_FREQ_KURZ = {"täglich": "t", "wöchentlich": "w", "monatlich": "m", "jährlich": "j"}
_KURZ_FREQ = {"DAILY": "täglich", "WEEKLY": "wöchentlich", "MONTHLY": "monatlich",
              "YEARLY": "jährlich"}


class Feld:
    """art: 'text' (tippen) oder 'wahl' (←→ zwischen `optionen`).
    `lesen(text)` → (ok, wert|fehlertext); `zeigen(werte)` → sichtbar?"""

    def __init__(self, name, beschriftung, art="text", wert="", optionen=(),
                 lesen=None, zeigen=None, hilfe=""):
        self.name, self.beschriftung, self.art = name, beschriftung, art
        self.text = str(wert or "") if art == "text" else ""
        self.optionen = tuple(optionen)
        self.wahl = self.optionen.index(wert) if wert in self.optionen else 0
        self.lesen = lesen or (lambda s: (True, s.strip()))
        self.zeigen = zeigen or (lambda w: True)
        self.hilfe = hilfe

    def roh(self):
        return self.optionen[self.wahl] if self.art == "wahl" else self.text


class Formular:
    """Mehrere Felder in einem Kasten. `plan(werte)` macht daraus die Aufrufe,
    `pruefen(werte)` darf Feldübergreifendes ablehnen → (feld, fehler)|None."""

    modal = True

    def __init__(self, titel, felder, plan, pruefen=None, fokus=None):
        self.titel, self.felder, self._plan = titel, felder, plan
        self._pruefen = pruefen or (lambda w: None)
        self.fehler, self.fehler_feld = "", None
        self._u8 = b""
        self.fertig = False
        self.antworten: dict = {}
        sicht = self.sichtbar()
        self.i = next((k for k, f in enumerate(sicht) if f.name == fokus), 0)

    def roh_werte(self) -> dict:
        return {f.name: f.roh() for f in self.felder}

    def sichtbar(self) -> list:
        w = self.roh_werte()
        return [f for f in self.felder if f.zeigen(w)]

    @property
    def feld(self):
        s = self.sichtbar()
        self.i = max(0, min(self.i, len(s) - 1))
        return s[self.i]

    def _speichern(self) -> bool:
        werte = {}
        for f in self.sichtbar():
            ok, wert = f.lesen(f.roh())
            if not ok:
                self.fehler, self.fehler_feld = wert, f.name
                self.i = self.sichtbar().index(f)
                return False
            werte[f.name] = wert
        p = self._pruefen(werte)
        if p:
            name, self.fehler = p
            self.fehler_feld = name
            namen = [f.name for f in self.sichtbar()]
            if name in namen:
                self.i = namen.index(name)
            return False
        self.antworten = werte
        self.fertig = True
        return True

    def taste(self, ch: int) -> str:
        """→ 'weiter' | 'fertig' | 'abbruch'."""
        if ch == 27:
            return "abbruch"
        f = self.feld
        n = len(self.sichtbar())
        if ch in (10, 13, 343, 19):              # Enter / KEY_ENTER / Strg-S
            return "fertig" if self._speichern() else "weiter"
        if ch in (9, 258):                       # Tab, ↓
            self.i = (self.i + 1) % n
        elif ch in (353, 259):                   # Shift-Tab, ↑
            self.i = (self.i - 1) % n
        elif f.art == "wahl" and ch in (260, 261, 32):     # ←, →, Leertaste
            f.wahl = (f.wahl + (-1 if ch == 260 else 1)) % len(f.optionen)
        elif f.art == "text":
            if ch in (8, 127, 263):
                f.text = f.text[:-1]
                self._u8 = b""
            elif ch == 21:
                f.text = ""
            elif 0x80 <= ch <= 0xFF:             # Umlaute: UTF-8 Byte für Byte
                self._u8 += bytes([ch])
                try:
                    z = self._u8.decode("utf-8")
                except UnicodeDecodeError:
                    if len(self._u8) >= 4:
                        self._u8 = b""
                    return "weiter"
                self._u8 = b""
                f.text = (f.text + z)[:200]
            elif 32 <= ch < 0x80:
                f.text = (f.text + chr(ch))[:200]
        if self.fehler_feld == f.name and ch not in (9, 258, 353, 259):
            self.fehler, self.fehler_feld = "", None
        return "weiter"

    def zeilen(self) -> list:
        """[(beschriftung, wert, aktiv, hilfe)] für den Kasten."""
        aus = []
        for k, f in enumerate(self.sichtbar()):
            if f.art == "wahl":
                wert = "‹ %s ›" % f.roh()
            else:
                wert = f.text
            aus.append((f.beschriftung, wert, k == self.i, f.hilfe))
        return aus

    def plan(self) -> dict:
        return self._plan(self.antworten)


def _l_ende(s):
    s = s.strip()
    if not s:
        return True, None
    if s.startswith("+"):
        m = dauer(s)
        return (True, ("dauer", m)) if m else (False, "dauer wie +45, +1:30, +2d20h")
    z = zeit(s)
    return (True, ("zeit", z)) if z else (False, "ende wie 18:00 oder +1h")


def _l_wtage(s):
    w = wochentage(s)
    return (True, w) if w is not None else (False, "tage wie di do oder mo-fr")


def _termin_felder(tag, heute, *, titel="", ganz=False, von="", bis="", ort="",
                   wiederholung="keine", alle="1", wtage="", wbis="",
                   mit_regel=True, mit_ganz=True, mit_datum=True, datum_name="Tag"):
    ganz_an = lambda w: w.get("ganz") == "ja"
    regel_an = lambda w: w.get("wied", "keine") != "keine"
    felder = [Feld("titel", "Titel", wert=titel, lesen=_l_titel)]
    if mit_datum:
        felder.append(Feld("datum", datum_name, wert=datum_text(tag),
                           lesen=_l_datum(heute), hilfe="TT.MM.JJJJ"))
    if mit_ganz:
        felder.append(Feld("ganz", "Ganztägig", art="wahl", wert="ja" if ganz else "nein",
                           optionen=("nein", "ja")))
    felder += [
        Feld("von", "Von", wert=von, lesen=_l_zeit(leer_ok=False),
             zeigen=lambda w: not ganz_an(w), hilfe="hh:mm"),
        Feld("bis", "Bis", wert=bis, lesen=_l_ende, zeigen=lambda w: not ganz_an(w),
             hilfe="hh:mm oder +1h, +2d20h"),
    ]
    if mit_ganz:
        felder.append(Feld("tage", "Tage", wert="1", lesen=_l_zahl(),
                           zeigen=lambda w: ganz_an(w) and not regel_an(w)))
    if mit_regel:
        felder += [
            Feld("wied", "Wiederholung", art="wahl", wert=wiederholung, optionen=WIEDERHOLUNG),
            Feld("alle", "Alle wie viele", wert=alle, lesen=_l_zahl(), zeigen=regel_an),
            Feld("wtage", "An Tagen", wert=wtage, lesen=_l_wtage,
                 zeigen=lambda w: w.get("wied") == "wöchentlich",
                 hilfe="leer = %s; z.B. di do, mo-fr" % WT_KURZ[tag.weekday()]),
            Feld("wbis", "Wiederholen bis", wert=wbis, lesen=_l_datum(heute),
                 zeigen=regel_an, hilfe="leer = endlos"),
        ]
    felder.append(Feld("ort", "Ort", wert=ort))
    return felder


def _zeiten(tag, w):
    """(start 'HH:MM'|None, ende_datetime|None) aus den Formularwerten."""
    if w.get("ganz") == "ja" or not w.get("von"):
        return None, None
    s_dt = datetime.combine(tag, datetime.strptime(w["von"], "%H:%M").time())
    b = w.get("bis")
    if b is None:
        return w["von"], None
    if b[0] == "dauer":
        return w["von"], s_dt + timedelta(minutes=b[1])
    e_dt = datetime.combine(tag, datetime.strptime(b[1], "%H:%M").time())
    if e_dt <= s_dt:                      # calcurse: Ende vor Start = nächster Tag
        e_dt += timedelta(days=1)
    return w["von"], e_dt


def _neu_plan(w, tag, layer="termine"):
    """Aufrufe für einen neuen Eintrag aus Formularwerten (ohne Altes zu
    löschen). Täglich ohne Intervall mit Ende = Spanne (bleibt als Block
    sichtbar, Tage einzeln änderbar); sonst Wiederholung = Routine."""
    tag = w.get("datum") or tag
    titel, ort = w["titel"], (w.get("ort") or None)
    start, e_dt = _zeiten(tag, w)
    ende = e_dt.strftime("%H:%M") if e_dt else None
    wied = w.get("wied", "keine")
    if wied != "keine":
        alle = w.get("alle") or 1
        if wied == "täglich" and alle == 1 and w.get("wbis") and (e_dt is None or e_dt.date() == tag):
            body = {"layer": layer, "von": tag.isoformat(), "bis": w["wbis"].isoformat(),
                    "label": titel}
            if start:
                body["tageszeit"] = [start, ende]
            if ort:
                body["ort"] = ort
            return [("POST", "/api/calendar/spanne", body)], "täglich bis %s: %s" % (
                datum_text(w["wbis"]), titel), None
        body = {"layer": layer, "label": titel, "seit": tag.isoformat(),
                "freq": _FREQ_KURZ[wied], "intervall": alle,
                "bis": w["wbis"].isoformat() if w.get("wbis") else None,
                "wochentage": w.get("wtage") or None, "time": start,
                "ende": ende if (e_dt and e_dt.date() == tag) else None, "ort": ort}
        return [("POST", "/api/calendar/routine", body)], "wiederholt sich: " + titel, None
    if start is None:
        n = w.get("tage") or 1
        if n == 1:
            body = {"layer": layer, "day": tag.isoformat(), "label": titel}
            if ort:
                body["ort"] = ort
            return [("POST", "/api/calendar/entry", body)], "angelegt: " + titel, None
        bis = tag + timedelta(days=n - 1)
        body = {"layer": layer, "von": tag.isoformat(), "bis": bis.isoformat(), "label": titel}
        if ort:
            body["ort"] = ort
        return [("POST", "/api/calendar/spanne", body)], "angelegt: %s bis %s" % (
            titel, datum_text(bis)), None
    if e_dt is not None and e_dt.date() > tag:
        body = {"layer": layer, "von": tag.isoformat(), "bis": e_dt.date().isoformat(),
                "label": titel, "start_zeit": start, "end_zeit": ende}
        if ort:
            body["ort"] = ort
        return [("POST", "/api/calendar/spanne", body)], "angelegt: %s bis %s %s" % (
            titel, WT_KURZ[e_dt.weekday()], ende), None
    body = {"layer": layer, "day": tag.isoformat(), "label": titel, "time": start}
    if ende:
        body["ende"] = ende
    if ort:
        body["ort"] = ort
    kon = {k: body[k] for k in ("day", "label", "time", "ende") if k in body} if ende else None
    return [("POST", "/api/calendar/entry", body)], "angelegt: " + titel, kon


def formular_neu(tag: date, heute: date) -> Formular:
    """a: neuer Termin am gewählten Tag (calcurse: der Tag im Kalender)."""
    def plan(w):
        aufrufe, meldung, kon = _neu_plan(w, tag)
        return _plan(aufrufe, meldung, konflikt=kon, danach={"tag": w.get("datum") or tag})
    return Formular("neuer termin", _termin_felder(tag, heute), plan)


def _regel_felder(rrule):
    """Formularwerte aus einer RRULE (fürs Vorbelegen)."""
    teile = dict(p.split("=", 1) for p in (rrule or "").split(";") if "=" in p)
    wied = _KURZ_FREQ.get(teile.get("FREQ", ""), "keine")
    wt = [WT_KURZ[WT_CODE.index(c[-2:])].lower() for c in teile.get("BYDAY", "").split(",")
          if c[-2:] in WT_CODE]
    bis = ""
    if teile.get("UNTIL"):
        try:
            bis = datum_text(datetime.strptime(teile["UNTIL"][:8], "%Y%m%d").date())
        except ValueError:
            pass
    return {"wiederholung": wied, "alle": teile.get("INTERVAL", "1"),
            "wtage": " ".join(wt), "wbis": bis}


def _wahl_umfang(roh):
    return Schritt("umfang", "„%s“ ändern: (d) nur dieser Tag  (a) alle" % roh.get("label", ""),
                   art="wahl", wahl={"d": "dieser", "a": "alle"})


def formular_bearbeiten(roh: dict, tag: date, heute: date, fokus=None):
    """e (und r): derselbe Kasten, vorbelegt. Routinen und Spannen fragen
    vorher „nur dieser Tag oder alle?" (Handy-Kalender) — dann ist das
    Ergebnis ein kleiner Dialog, dessen Plan den Kasten als `weiter` bringt."""
    a_ = art(roh)
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, e0, ort0 = roh.get("time") or "", roh.get("ende") or "", roh.get("ort") or ""
    iso = tag.isoformat()

    if a_ == "einmal":
        def plan(w):
            if w.get("wied", "keine") != "keine":       # wird zur Wiederholung
                aufrufe, meldung, _k = _neu_plan(w, tag, layer)
                weg = ("DELETE", "/api/calendar/eintrag",
                       {"layer": layer, "day": iso, "label": label, "time": t0 or None})
                return _plan(aufrufe + [weg], meldung)
            start, e_dt = _zeiten(w["datum"], w)
            if e_dt and e_dt.date() > w["datum"]:       # über Mitternacht → Spanne
                aufrufe, meldung, _k = _neu_plan(w, tag, layer)
                weg = ("DELETE", "/api/calendar/eintrag",
                       {"layer": layer, "day": iso, "label": label, "time": t0 or None})
                return _plan(aufrufe + [weg], meldung, danach={"tag": w["datum"]})
            neu = {"day": w["datum"].isoformat(), "label": w["titel"],
                   "time": start or "", "ende": e_dt.strftime("%H:%M") if e_dt else "",
                   "ort": w.get("ort") or ""}
            kon = ({"day": neu["day"], "label": neu["label"], "time": neu["time"],
                    "ende": neu["ende"]} if neu["time"] and neu["ende"] else None)
            return _plan([("PUT", "/api/calendar/eintrag",
                           {"layer": layer, "day": iso, "label": label,
                            "time": t0 or None, "new": neu})],
                         "geändert: " + w["titel"], konflikt=kon, danach={"tag": w["datum"]})
        return Formular("termin ändern", _termin_felder(
            tag, heute, titel=label, ganz=not t0, von=t0, bis=e0, ort=ort0), plan, fokus=fokus)

    if a_ == "routine":
        def nur_dieser(w):
            start, e_dt = _zeiten(w["datum"], w)
            neu = {"label": w["titel"], "ort": w.get("ort") or ""}
            if w["datum"] != tag:
                neu["tag"] = w["datum"].isoformat()
            if start:
                neu["time"] = start
            if e_dt:
                neu["ende"] = e_dt.strftime("%H:%M")
            return _plan([("POST", "/api/calendar/routine/abweichung",
                           {"layer": layer, "label": label, "day": iso,
                            "time": t0 or None, "new": neu})],
                         "nur %s geändert: %s" % (datum_text(tag), w["titel"]),
                         danach={"tag": w["datum"]})

        def alle(w):
            start, e_dt = _zeiten(tag, w)
            neu = {"label": w["titel"], "time": start or "",
                   "ende": e_dt.strftime("%H:%M") if e_dt else "", "ort": w.get("ort") or ""}
            r = _regel_felder(roh.get("rrule"))
            wied = w.get("wied", "keine")
            if wied != "keine":
                neu_regel = {"freq": _FREQ_KURZ[wied], "intervall": w.get("alle") or 1,
                             "bis": w["wbis"].isoformat() if w.get("wbis") else None,
                             "wochentage": w.get("wtage") or None}
                alt_regel = {"freq": _FREQ_KURZ.get(r["wiederholung"]),
                             "intervall": int(r["alle"] or 1),
                             "bis": datum(r["wbis"], heute).isoformat() if r["wbis"] else None,
                             "wochentage": wochentage(r["wtage"]) or None}
                if neu_regel != alt_regel:
                    neu["wiederholung"] = neu_regel
            aufrufe = [("PUT", "/api/calendar/routine",
                        {"layer": layer, "label": label, "day": iso,
                         "time": t0 or None, "new": neu})]
            if wied == "keine":                         # Wiederholung aus = ganz löschen?
                return _plan(meldung="Wiederholung „keine“: zum Löschen d benutzen")
            return _plan(aufrufe, "alle geändert: " + w["titel"])

        r = _regel_felder(roh.get("rrule"))
        form_dieser = lambda: Formular("nur dieser tag · " + datum_text(tag), _termin_felder(
            tag, heute, titel=label, von=t0, bis=e0, ort=ort0, mit_regel=False,
            mit_ganz=False, datum_name="Verschieben auf"), nur_dieser, fokus=fokus)
        form_alle = lambda: Formular("alle termine der serie", _termin_felder(
            tag, heute, titel=label, von=t0, bis=e0, ort=ort0, mit_ganz=False,
            mit_datum=False, wiederholung=r["wiederholung"], alle=r["alle"],
            wtage=r["wtage"], wbis=r["wbis"]), alle, fokus=fokus)
        if fokus == "wied":
            return form_alle()
        return Dialog("ändern", [_wahl_umfang(roh)], lambda a: _plan(
            weiter=form_dieser() if a["umfang"] == "dieser" else form_alle()))

    # Spanne
    von_iso = roh.get("von") or iso
    try:
        von_d, bis_d = date.fromisoformat(von_iso), date.fromisoformat(roh.get("bis") or iso)
    except ValueError:
        von_d = bis_d = tag

    def tag_plan(w):
        start, e_dt = _zeiten(tag, w)
        return _plan([("POST", "/api/calendar/spanne/tag",
                       {"layer": layer, "von": von_iso, "label": label, "day": iso,
                        "time": start, "ende": e_dt.strftime("%H:%M") if e_dt else None})],
                     "nur %s geändert: %s" % (datum_text(tag), label))

    def alle_plan(w):
        schub = (w["erster"] - von_d).days
        neu = {"label": w["titel"], "ort": w.get("ort") or ""}
        if schub:
            neu["verschieben"] = schub
        if w["letzter"] != bis_d + timedelta(days=schub):
            neu["bis"] = (w["letzter"] - timedelta(days=schub)).isoformat()
        return _plan([("PUT", "/api/calendar/spanne",
                       {"layer": layer, "von": von_iso, "label": label, "new": neu})],
                     "alle tage geändert: " + w["titel"], danach={"tag": w["erster"]})

    def alle_pruefen(w):
        if w["letzter"] < w["erster"]:
            return "letzter", "letzter tag vor dem ersten"
        return None

    form_tag = lambda: Formular("nur dieser tag · " + datum_text(tag), [
        Feld("ganz", "Ganztägig", art="wahl", wert="nein" if t0 else "ja", optionen=("nein", "ja")),
        Feld("von", "Von", wert=t0, lesen=_l_zeit(leer_ok=False),
             zeigen=lambda w: w.get("ganz") != "ja", hilfe="hh:mm"),
        Feld("bis", "Bis", wert=e0, lesen=_l_ende,
             zeigen=lambda w: w.get("ganz") != "ja", hilfe="hh:mm, leer = ohne"),
    ], tag_plan)
    form_alle = lambda: Formular("ganze spanne", [
        Feld("titel", "Titel", wert=label, lesen=_l_titel),
        Feld("erster", "Erster Tag", wert=datum_text(von_d), lesen=_l_datum(heute)),
        Feld("letzter", "Letzter Tag", wert=datum_text(bis_d), lesen=_l_datum(heute)),
        Feld("ort", "Ort", wert=ort0),
    ], alle_plan, pruefen=alle_pruefen)
    return Dialog("ändern", [_wahl_umfang(roh)], lambda a: _plan(
        weiter=form_tag() if a["umfang"] == "dieser" else form_alle()))


def formular_wiederholen(roh: dict, tag: date, heute: date):
    """r (calcurse „repeat"): der Bearbeiten-Kasten, gleich auf
    „Wiederholung"; eine Spanne wiederholt sich nicht (None)."""
    if art(roh) == "spanne":
        return None
    return formular_bearbeiten(roh, tag, heute, fokus="wied")


# ── d: Löschen ─────────────────────────────────────────────────────────
def dialog_loeschen(roh: dict, tag: date) -> Dialog:
    a_ = art(roh)
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, iso = roh.get("time") or None, tag.isoformat()
    if a_ == "routine":
        if roh.get("deaktiviert"):
            return Dialog("wieder an", [Schritt(
                "ok", "„%s“ am %s wieder aktivieren? (j/n)" % (label, datum_text(tag)),
                art="wahl", wahl={"j": True, "n": False})],
                lambda a: _plan([("POST", "/api/calendar/routine/skip",
                                  {"layer": layer, "label": label, "day": iso,
                                   "time": t0, "off": False})] if a["ok"] else [],
                                "wieder an: " + label if a["ok"] else ""))
        # calcurse: „alle Vorkommen oder nur dieses?"
        def plan(a):
            if a["wie"] == "alle":
                return _plan([("DELETE", "/api/calendar/routine",
                               {"layer": layer, "label": label, "day": iso, "time": t0})],
                             "routine gelöscht: " + label)
            if a["wie"] == "dieses":
                return _plan([("POST", "/api/calendar/routine/skip",
                               {"layer": layer, "label": label, "day": iso,
                                "time": t0, "off": True})],
                             "nur %s gelöscht: %s" % (datum_text(tag), label))
            return _plan()
        return Dialog("löschen", [Schritt(
            "wie", "„%s“ löschen: (1) alle Vorkommen  (2) nur dieses  (n) nichts" % label,
            art="wahl", wahl={"1": "alle", "2": "dieses", "n": None})], plan)
    day = roh.get("von") or iso if a_ == "spanne" else iso
    frage = ("Ganze Spanne „%s“ löschen? (j/n)" if a_ == "spanne"
             else "„%s“ löschen? (j/n)") % label
    return Dialog("löschen", [Schritt("ok", frage, art="wahl", wahl={"j": True, "n": False})],
                  lambda a: _plan([("DELETE", "/api/calendar/eintrag",
                                    {"layer": layer, "day": day, "label": label,
                                     "time": None if a_ == "spanne" else t0})]
                                  if a["ok"] else [], "gelöscht: " + label if a["ok"] else ""))


# ── c / p: Kopieren, Einfügen ──────────────────────────────────────────
def kopie(roh: dict) -> dict:
    """calcurse „c": was beim Einfügen wieder entsteht (immer ein Einmal-
    Termin am gewählten Tag, auch aus einer Routine)."""
    return {k: roh[k] for k in ("label", "time", "ende", "ort") if roh.get(k)}


def plan_einfuegen(k: dict, tag: date) -> dict:
    body = {"layer": "termine", "day": tag.isoformat(), **k}
    kon = ({"day": body["day"], "label": body["label"], "time": body["time"],
            "ende": body["ende"]} if body.get("time") and body.get("ende") else None)
    return _plan([("POST", "/api/calendar/entry", body)],
                 "eingefügt: %s am %s" % (k.get("label", ""), datum_text(tag)), konflikt=kon)


# ── g: Gehe zu ─────────────────────────────────────────────────────────
def dialog_gehe_zu(heute: date) -> Dialog:
    return Dialog("gehe zu", [Schritt("ziel", "Gehe zu [TT.MM.JJJJ], leer = heute",
                                      lesen=_l_datum(heute, leer=heute))],
                  lambda a: _plan(danach={"tag": a["ziel"]}))


# ── TODO (die Wochenliste) ─────────────────────────────────────────────
def dialog_todo_neu(lid) -> Dialog:
    return Dialog("neue aufgabe", [Schritt("text", "Neue Aufgabe", lesen=_l_titel)],
                  lambda a: _plan([("POST", "/api/lists/%s/items" % lid, {"text": a["text"]})],
                                  "aufgabe: " + a["text"]))


def dialog_todo_bearbeiten(lid, item) -> Dialog:
    return Dialog("aufgabe", [Schritt("text", "Aufgabe", vorgabe=str(item.get("text") or ""),
                                      lesen=_l_titel)],
                  lambda a: _plan([("POST", "/api/lists/%s/items/%s/rename" % (lid, item["id"]),
                                    {"text": a["text"]})], "geändert"))


def dialog_todo_loeschen(lid, item) -> Dialog:
    return Dialog("löschen", [Schritt("ok", "„%s“ löschen? (j/n)" % item.get("text", ""),
                                      art="wahl", wahl={"j": True, "n": False})],
                  lambda a: _plan([("DELETE", "/api/lists/%s/items/%s" % (lid, item["id"]), None)]
                                  if a["ok"] else [], "gelöscht" if a["ok"] else ""))


# ── Enter: Ansehen ─────────────────────────────────────────────────────
def details(roh: dict, tag: date) -> list:
    """Alles über einen Termin, für das Ansehen-Fenster (calcurse „v")."""
    zeilen = [roh.get("label", "?"), ""]
    zeilen.append("Tag      %s, %s" % (WT_LANG[tag.weekday()], datum_text(tag)))
    t, e = roh.get("time"), roh.get("ende")
    if t or e:
        zeilen.append("Zeit     %s%s" % (t or "..:..", (" -> " + e) if e else ""))
    else:
        zeilen.append("Zeit     ganztägig")
    if roh.get("spanning"):
        try:
            v, b = date.fromisoformat(roh["von"]), date.fromisoformat(roh["bis"])
            zeilen.append("Spanne   %s bis %s" % (datum_text(v), datum_text(b)))
        except (KeyError, ValueError):
            pass
    if roh.get("recurring"):
        zeilen.append("Wiederh. " + (regel_text(roh.get("rrule")) or "ja"))
    if roh.get("ort"):
        zeilen.append("Ort      " + roh["ort"])
    if roh.get("ausfall"):
        zeilen.append("Fällt aus: " + str(roh["ausfall"]))
    if roh.get("deaktiviert"):
        zeilen.append("An diesem Tag ausgeschaltet")
    zeilen.append("Ebene    " + str(roh.get("layer", "")))
    return zeilen
