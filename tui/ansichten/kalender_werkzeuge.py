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
    """Schritte nacheinander abfragen. `plan` (antworten → Plan) wird erst
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


def _plan(aufrufe=(), meldung="", konflikt=None, danach=None):
    """aufrufe: [(methode, pfad, body)]; konflikt: Body für die Vorprüfung
    (/api/calendar/konflikte) — kommt etwas zurück, fragt die Ansicht erst
    nach; danach: {"tag": date} o.ä. für die Auswahl nach dem Speichern."""
    return {"aufrufe": list(aufrufe), "meldung": meldung,
            "konflikt": konflikt, "danach": danach or {}}


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


# ── a: Anlegen ─────────────────────────────────────────────────────────
def dialog_anlegen(tag: date) -> Dialog:
    """calcurse: Startzeit (leer = ganztägig) → Ende/Dauer → Titel.
    Ergänzung: ganztägig über mehrere Tage (calcurse kann das nicht)."""
    def l_ende(s):
        s = s.strip()
        if not s:
            return True, None
        if s.startswith("+"):
            m = dauer(s)
            return (True, ("dauer", m)) if m else (False, "dauer wie +45, +1:30, +2d20h")
        z = zeit(s)
        return (True, ("zeit", z)) if z else (False, "ende wie 18:00 oder +1h")

    def plan(a):
        titel, start = a["titel"], a.get("start")
        if not start:
            n = a.get("tage") or 1
            if n == 1:
                return _plan([("POST", "/api/calendar/entry",
                               {"layer": "termine", "day": tag.isoformat(), "label": titel})],
                             "angelegt: " + titel)
            bis = tag + timedelta(days=n - 1)
            return _plan([("POST", "/api/calendar/spanne",
                           {"von": tag.isoformat(), "bis": bis.isoformat(), "label": titel})],
                         "angelegt: %s bis %s" % (titel, datum_text(bis)))
        s_dt = datetime.combine(tag, datetime.strptime(start, "%H:%M").time())
        ende = a.get("ende")
        if ende is None:
            e_dt = None
        elif ende[0] == "dauer":
            e_dt = s_dt + timedelta(minutes=ende[1])
        else:
            e_dt = datetime.combine(tag, datetime.strptime(ende[1], "%H:%M").time())
            if e_dt <= s_dt:              # calcurse: Ende vor Start = nächster Tag
                e_dt += timedelta(days=1)
        if e_dt is not None and e_dt.date() > tag:
            return _plan([("POST", "/api/calendar/spanne",
                           {"von": tag.isoformat(), "bis": e_dt.date().isoformat(),
                            "label": titel, "start_zeit": start,
                            "end_zeit": e_dt.strftime("%H:%M")})],
                         "angelegt: %s bis %s %s" % (titel, WT_KURZ[e_dt.weekday()],
                                                     e_dt.strftime("%H:%M")))
        body = {"layer": "termine", "day": tag.isoformat(), "label": titel, "time": start}
        if e_dt is not None:
            body["ende"] = e_dt.strftime("%H:%M")
        return _plan([("POST", "/api/calendar/entry", body)], "angelegt: " + titel,
                     konflikt={k: body[k] for k in ("day", "label", "time", "ende") if k in body})

    return Dialog("neuer termin · " + datum_text(tag), [
        Schritt("start", "Startzeit [hh:mm], leer = ganztägig", lesen=_l_zeit()),
        Schritt("ende", "Ende [hh:mm] oder Dauer [+1h, +2d20h], leer = ohne",
                lesen=l_ende, wenn=lambda a: a.get("start")),
        Schritt("tage", "Wie viele Tage? [1]", lesen=_l_zahl(),
                wenn=lambda a: not a.get("start")),
        Schritt("titel", "Titel", lesen=_l_titel),
    ], plan)


# ── e: Bearbeiten ──────────────────────────────────────────────────────
def _wahl_umfang(roh):
    return Schritt("umfang", "„%s“ ändern: (d) nur dieser Tag  (a) alle" % roh.get("label", ""),
                   art="wahl", wahl={"d": "dieser", "a": "alle"})


def dialog_bearbeiten(roh: dict, tag: date, heute: date) -> Dialog | None:
    """calcurse „e": erst WAS (Startzeit/Ende/Titel/…), dann der neue Wert,
    vorbelegt mit dem jetzigen. Bei Routinen/Spannen vorher „nur dieser Tag
    oder alle?" wie im Handy-Kalender."""
    a_ = art(roh)
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, e0, ort0 = roh.get("time") or "", roh.get("ende") or "", roh.get("ort") or ""
    iso = tag.isoformat()

    menue_einmal = {"1": "start", "2": "ende", "3": "titel", "4": "ort", "5": "datum"}
    menue_dieser = menue_einmal
    menue_routine = {"1": "start", "2": "ende", "3": "titel", "4": "ort", "6": "regel"}
    menue_sp_tag = {"1": "start", "2": "ende"}
    menue_sp_alle = {"3": "titel", "4": "ort", "5": "schieben", "6": "bis"}
    namen = {"start": "Startzeit", "ende": "Ende", "titel": "Titel", "ort": "Ort",
             "datum": "Verschieben", "regel": "Wiederholung", "schieben": "Verschieben",
             "bis": "Letzter Tag"}

    def menue_schritt(name, menue, wenn=None):
        txt = "  ".join("(%s) %s" % (k, namen[v]) for k, v in menue.items())
        return Schritt(name, "Ändern: " + txt, art="wahl", wahl=menue, wenn=wenn)

    def feld(a):
        return a.get("was") or a.get("was_d") or a.get("was_a")

    werte = [
        Schritt("start", "Startzeit [hh:mm], leer = ganztägig", vorgabe=t0,
                lesen=_l_zeit(), wenn=lambda a: feld(a) == "start"),
        Schritt("ende", "Ende [hh:mm], leer = ohne", vorgabe=e0,
                lesen=_l_zeit(), wenn=lambda a: feld(a) == "ende"),
        Schritt("titel", "Titel", vorgabe=label, lesen=_l_titel,
                wenn=lambda a: feld(a) == "titel"),
        Schritt("ort", "Ort, leer = keiner", vorgabe=ort0,
                wenn=lambda a: feld(a) == "ort"),
        Schritt("datum", "Neues Datum [TT.MM.JJJJ]", vorgabe=datum_text(tag),
                lesen=_l_datum(heute), wenn=lambda a: feld(a) == "datum"),
        Schritt("schieben", "Um wie viele Tage verschieben? [+3, -1]",
                lesen=lambda s: (True, int(s)) if re.fullmatch(r"[+-]?\d+", s.strip())
                else (False, "zahl wie +3 oder -1"),
                wenn=lambda a: feld(a) == "schieben"),
        Schritt("bis", "Letzter Tag [TT.MM.JJJJ]", vorgabe=roh.get("bis") and
                datum_text(date.fromisoformat(roh["bis"])) or "",
                lesen=_l_datum(heute), wenn=lambda a: feld(a) == "bis"),
    ]

    def neu_aus(a):
        f = feld(a)
        if f == "start":
            return {"time": a["start"] or ""}
        if f == "ende":
            return {"ende": a["ende"] or ""}
        if f == "titel":
            return {"label": a["titel"]}
        if f == "ort":
            return {"ort": a["ort"] or ""}
        if f == "datum":
            return {"tag" if a_ == "routine" else "day": a["datum"].isoformat()}
        return {}

    if a_ == "einmal":
        def plan(a):
            neu = neu_aus(a)
            body = {"layer": layer, "day": iso, "label": label, "time": t0 or None, "new": neu}
            k = None
            t1, e1 = neu.get("time", t0), neu.get("ende", e0)
            if t1 and e1:
                k = {"day": neu.get("day", iso), "label": neu.get("label", label),
                     "time": t1, "ende": e1}
            return _plan([("PUT", "/api/calendar/eintrag", body)], "geändert: " + label,
                         konflikt=k, danach={"tag": date.fromisoformat(neu.get("day", iso))})
        return Dialog("bearbeiten", [menue_schritt("was", menue_einmal)] + werte, plan)

    if a_ == "routine":
        regel = dialog_wiederholen_schritte(tag, wenn=lambda a: a.get("was_a") == "regel")

        def plan(a):
            if a["umfang"] == "dieser":
                neu = neu_aus(a)
                return _plan([("POST", "/api/calendar/routine/abweichung",
                               {"layer": layer, "label": label, "day": iso,
                                "time": t0 or None, "new": neu})],
                             "nur %s geändert: %s" % (datum_text(tag), label))
            if a.get("was_a") == "regel":
                neu = {"wiederholung": _regel_aus(a, tag)}
            else:
                neu = neu_aus(a)
            return _plan([("PUT", "/api/calendar/routine",
                           {"layer": layer, "label": label, "day": iso,
                            "time": t0 or None, "new": neu})],
                         "alle geändert: " + label)
        return Dialog("routine bearbeiten", [
            _wahl_umfang(roh),
            menue_schritt("was_d", menue_dieser, wenn=lambda a: a["umfang"] == "dieser"),
            menue_schritt("was_a", menue_routine, wenn=lambda a: a["umfang"] == "alle"),
        ] + werte + regel, plan)

    # Spanne
    von = roh.get("von") or iso

    def plan(a):
        if a["umfang"] == "dieser":
            f = feld(a)
            t1 = a["start"] if f == "start" else (t0 or None)
            e1 = a["ende"] if f == "ende" else (e0 or None)
            return _plan([("POST", "/api/calendar/spanne/tag",
                           {"layer": layer, "von": von, "label": label, "day": iso,
                            "time": t1, "ende": e1})],
                         "nur %s geändert: %s" % (datum_text(tag), label))
        f, neu = feld(a), {}
        if f == "titel":
            neu["label"] = a["titel"]
        elif f == "ort":
            neu["ort"] = a["ort"] or ""
        elif f == "schieben":
            neu["verschieben"] = a["schieben"]
        elif f == "bis":
            neu["bis"] = a["bis"].isoformat()
        return _plan([("PUT", "/api/calendar/spanne",
                       {"layer": layer, "von": von, "label": label, "new": neu})],
                     "alle tage geändert: " + label)
    return Dialog("spanne bearbeiten", [
        _wahl_umfang(roh),
        menue_schritt("was_d", menue_sp_tag, wenn=lambda a: a["umfang"] == "dieser"),
        menue_schritt("was_a", menue_sp_alle, wenn=lambda a: a["umfang"] == "alle"),
    ] + werte, plan)


# ── r: Wiederholen ─────────────────────────────────────────────────────
def dialog_wiederholen_schritte(tag: date, wenn=None):
    """calcurse „r": Typ (t/w/m/j), alle wie viele, Ende (leer = endlos).
    Ergänzung wie im Handy-Kalender: bei wöchentlich die Wochentage."""
    w = wenn or (lambda a: True)
    return [
        Schritt("freq", "Wiederholen: (t)äglich (w)öchentlich (m)onatlich (j)ährlich",
                art="wahl", wahl={"t": "t", "w": "w", "m": "m", "j": "j"}, wenn=w),
        Schritt("intervall", "Alle wie viele? [1]", lesen=_l_zahl(), wenn=w),
        Schritt("wtage", "An welchen Tagen? [%s] (z.B. di do, mo-fr)" % WT_KURZ[tag.weekday()],
                lesen=lambda s: (True, wochentage(s)) if wochentage(s) is not None
                else (False, "tage wie di do oder mo-fr"),
                wenn=lambda a: w(a) and a.get("freq") == "w"),
        Schritt("rbis", "Bis [TT.MM.JJJJ], leer = endlos", lesen=_l_datum(tag),
                wenn=w),
    ]


def _regel_aus(a, tag):
    return {"freq": a["freq"], "intervall": a.get("intervall") or 1,
            "bis": a["rbis"].isoformat() if a.get("rbis") else None,
            "wochentage": a.get("wtage") or None}


def dialog_wiederholen(roh: dict, tag: date, heute: date) -> Dialog | None:
    """Einen Einmal-Termin zur Wiederholung machen. Täglich mit Ende wird
    eine Spanne (bleibt als zusammenhängender Block markiert, einzelne Tage
    lassen sich anpassen); alles andere eine Routine ab diesem Tag."""
    a_ = art(roh)
    if a_ == "routine":
        d = dialog_bearbeiten(roh, tag, heute)
        d.antworten.update({"umfang": "alle", "was_a": "regel"})
        d.i = -1
        d.schritte = d.schritte[3:]            # gleich zur Regel
        d._weiter()
        return d
    if a_ == "spanne":
        return None
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, e0 = roh.get("time") or None, roh.get("ende") or None

    def plan(a):
        weg = ("DELETE", "/api/calendar/eintrag",
               {"layer": layer, "day": tag.isoformat(), "label": label, "time": t0})
        r = _regel_aus(a, tag)
        if r["freq"] == "t" and r["intervall"] == 1 and r["bis"]:
            neu = {"von": tag.isoformat(), "bis": r["bis"], "label": label}
            if t0:
                neu["tageszeit"] = [t0, e0]
            if roh.get("ort"):
                neu["ort"] = roh["ort"]
            return _plan([("POST", "/api/calendar/spanne", neu), weg],
                         "jetzt täglich bis %s: %s" % (datum_text(a["rbis"]), label))
        neu = {"label": label, "seit": tag.isoformat(), "time": t0, "ende": e0,
               "ort": roh.get("ort"), **r}
        return _plan([("POST", "/api/calendar/routine", neu), weg],
                     "wiederholt sich jetzt: " + label)
    return Dialog("wiederholen", dialog_wiederholen_schritte(tag), plan)


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
