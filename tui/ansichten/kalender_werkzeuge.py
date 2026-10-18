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

Reine Logik, kein Zeichnen, kein HTTP: ein Dialog sammelt Antworten, `plan()`
macht daraus Aufrufe [(methode, pfad, body)], die die Ansicht ausführt.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import kalender_advanced, kalender_gruppen, kalender_kasten, kalender_quellen, kalender_stil
from .kalender_ansichten import _tag_eintraege, monat_eintraege
from .tasten import Tasten

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
def eintraege(daten: dict, tag: date, erledigte: bool, monat: bool = False) -> list:
    """Die Termine eines Tages, so wie die Ansicht sie zeigt (gleiche
    Reihenfolge, gleiche Filter). Jeder hat t["roh"] = API-Eintrag. `monat`:
    die Liste von B, in der eine Gruppe EINE Zeile ist (roh["gruppe"])."""
    holen = monat_eintraege if monat else _tag_eintraege
    return holen(daten if isinstance(daten, dict) else {}, tag.isoformat(), erledigte)


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
    """Kurze Rückfragen (löschen?, nur dieser Tag?, gehe zu …) als
    kleiner Kasten. Schritte nacheinander abfragen. `plan` (antworten → Plan) wird erst
    gerufen, wenn alle beantwortet sind. Esc bricht ab.

    Tasten aus der Tabelle (kalender_kasten.py): ein Text-Schritt nimmt
    Freitext, eine Wahl die Buchstaben ihrer Antworten — je Satz von
    Antworten eine Ansicht, damit die Leiste sagt, was j, t oder a heißt."""

    _ESC = ("esc", "abbrechen", "cancel")
    TASTEN = Tasten({
        "text": [("type", "tippen", "type"), ("enter", "ok", "ok"),
                 ("⌫", "zeichen_weg", "delete"), ("ctrl+u", "leeren", "clear"), _ESC],
        "jn": [("j", "waehlen", "yes"), ("n", "waehlen", "no"), ("J/N", "waehlen"),
               _ESC, ("any key", "falsch")],
        "at": [("t", "waehlen", "this day"), ("a", "waehlen", "all"), ("T/A", "waehlen"),
               _ESC, ("any key", "falsch")],
        "ant": [("a", "waehlen", "all"), ("t", "waehlen", "this day"),
                ("n", "waehlen", "nothing"), ("A/T/N", "waehlen"), _ESC,
                ("any key", "falsch")],
        # Rückfall für einen Satz Antworten, den es oben (noch) nicht gibt
        "wahl": [("type", "waehlen", "answer"), ("enter", "waehlen"), _ESC,
                 ("any key", "falsch")],
    })

    def __init__(self, titel, schritte, plan):
        self.titel, self.schritte, self._plan = titel, schritte, plan
        self.antworten: dict = {}
        self.i = -1
        self.eingabe = ""
        self.fehler = ""
        self._u8 = b""          # angefangenes UTF-8-Zeichen (curses liefert Bytes)
        self._weiter()

    def __repr__(self):
        return kalender_kasten.zustand(self)

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

    def ansicht(self) -> str:
        s = self.schritt
        if s is None or s.art != "wahl":
            return "text"
        satz = "".join(sorted(k for k in s.wahl if k))
        return satz if satz in self.TASTEN.ansichten() and "" not in s.wahl else "wahl"

    def taste(self, ch: int) -> str:
        """→ 'weiter' | 'fertig' | 'abbruch'."""
        if self.schritt is None:
            return "fertig"
        if 0x80 <= ch <= 0xFF and self.schritt.art == "text":     # Umlaute
            z = kalender_kasten.tippen_byte(self, ch)
            return self.aktion_tippen(z) if z else "weiter"
        return self.TASTEN.verteilen(self, self.ansicht(), ch) or "weiter"

    def _stand(self) -> str:
        return "fertig" if self.fertig else "weiter"

    def aktion_abbrechen(self, _t):
        return "abbruch"

    def aktion_waehlen(self, taste):
        s = self.schritt
        k = "" if taste == "enter" else taste.lower()
        if k not in s.wahl:
            return self.aktion_falsch(taste)
        self.antworten[s.name] = s.wahl[k]
        self._weiter()
        return self._stand()

    def aktion_falsch(self, _t):
        self.fehler = "bitte " + "/".join(x for x in self.schritt.wahl if x)
        return "weiter"

    def aktion_ok(self, _t):
        s = self.schritt
        ok, wert = s.lesen(self.eingabe)
        if not ok:
            self.fehler = wert
            return "weiter"
        self.antworten[s.name] = wert
        self._weiter()
        return self._stand()

    def aktion_tippen(self, zeichen):
        if len(self.eingabe) < 200:
            self.eingabe += zeichen
        return "weiter"

    def aktion_zeichen_weg(self, _t):
        self.eingabe = self.eingabe[:-1]
        self._u8 = b""
        return "weiter"

    def aktion_leeren(self, _t):          # Strg-U wie in der Shell
        self.eingabe = ""
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


def _plan(aufrufe=(), meldung="", konflikt=None, danach=None, weiter=None,
          vorab=None, zurueck=None):
    """aufrufe: [(methode, pfad, body)]; konflikt: Body für die Vorprüfung
    (/api/calendar/konflikte) — kommt etwas zurück, fragt die Ansicht erst
    nach; danach: {"tag": date} o.ä. für die Auswahl nach dem Speichern.
    vorab: {"aufruf": (methode, pfad, body), "dann": antwort → Dialog|Plan}
    — erst fragen, dann entscheiden (Gruppe für den Kurs: Probe, dann j/n).
    zurueck: () → Dialog, der nach den Aufrufen wieder aufgeht (der
    Rhythmus-Kasten nach dem Speichern einer Phase)."""
    return {"aufrufe": list(aufrufe), "meldung": meldung,
            "konflikt": konflikt, "danach": danach or {}, "weiter": weiter,
            "vorab": vorab, "zurueck": zurueck}


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
# Enter speichert, Esc bricht ab.
# Feste Plätze (Sasha, 18.10.2026: „plötzlich wechseln die optionen den
# platz … das sollte eigentlich nie passieren"): ALLE Felder stehen immer
# da, der Kasten ändert seine Höhe nie. Was gerade nicht gilt (Uhrzeit bei
# ganztägig, Wochentage ohne wöchentlich — `Feld.aktiv`), steht gedämpft
# mit „—", wird beim Durchgehen übersprungen und beim Speichern ignoriert.
NICHT_AKTIV = "—"                       # Wert eines Feldes, das gerade nicht gilt
WIEDERHOLUNG = ("keine", "täglich", "wöchentlich", "monatlich", "jährlich")
_FREQ_KURZ = {"täglich": "t", "wöchentlich": "w", "monatlich": "m", "jährlich": "j"}
_KURZ_FREQ = {"DAILY": "täglich", "WEEKLY": "wöchentlich", "MONTHLY": "monatlich",
              "YEARLY": "jährlich"}


class Feld:
    """art: 'text' (tippen), 'wahl' (←→ zwischen `optionen`) oder 'advanced'
    (Enter öffnet das Fenster „advanced", Wert = {typ, quelle, stil} —
    kalender_advanced.py). `lesen(text)` → (ok, wert|fehlertext);
    `aktiv(werte)` → gilt gerade? (sonst gedämpft, übersprungen, beim
    Speichern ignoriert — das Feld bleibt aber stehen); `hilfe` Text oder
    (werte) → Text."""

    def __init__(self, name, beschriftung, art="text", wert="", optionen=(),
                 lesen=None, aktiv=None, hilfe=""):
        self.name, self.beschriftung, self.art = name, beschriftung, art
        self.text = str(wert or "") if art == "text" else ""
        self.adv = dict(wert or {}) if art == "advanced" else None
        self.quellen = None             # art 'advanced': () → GET /api/calendar/quellen
        self.optionen = tuple(optionen)
        self.wahl = self.optionen.index(wert) if wert in self.optionen else 0
        self.lesen = lesen or (lambda s: (True, s.strip()))
        self.aktiv = aktiv or (lambda w: True)
        self.hilfe = hilfe

    def roh(self):
        if self.art == "advanced":
            return dict(self.adv)
        return self.optionen[self.wahl] if self.art == "wahl" else self.text


class Formular:
    """Mehrere Felder in einem Kasten. `plan(werte)` macht daraus die Aufrufe,
    `pruefen(werte)` darf Feldübergreifendes ablehnen → (feld, fehler)|None.
    Das Feld „advanced" breitet sich in den Werten aus: typ, quelle, stil."""

    modal = True

    def __init__(self, titel, felder, plan, pruefen=None, fokus=None):
        self.titel, self.felder, self._plan = titel, felder, plan
        self._pruefen = pruefen or (lambda w: None)
        self.fehler, self.fehler_feld = "", None
        self._u8 = b""
        self.fertig = False
        self.antworten: dict = {}
        self.box = None                 # offenes Fenster „advanced" (Feld art 'advanced')
        # self.i zeigt in self.felder (alle, feste Plätze), steht nie auf
        # einem Feld, das gerade nicht gilt.
        self.i = next((k for k, f in enumerate(felder) if f.name == fokus), 0)
        self._auf_aktives(1)

    def roh_werte(self) -> dict:
        return {f.name: f.roh() for f in self.felder}

    def gilt(self) -> list:
        """Je Feld (in self.felder): gilt es gerade?"""
        w = self.roh_werte()
        return [bool(f.aktiv(w)) for f in self.felder]

    def aktive(self) -> list:
        return [f for f, g in zip(self.felder, self.gilt()) if g]

    def _auf_aktives(self, schritt):
        """Steht i auf einem Feld, das nicht gilt: in Richtung `schritt`
        zum nächsten, das gilt (das erste Feld, der Titel, gilt immer)."""
        g, n = self.gilt(), len(self.felder)
        self.i = max(0, min(self.i, n - 1))
        for _ in range(n):
            if g[self.i]:
                return
            self.i = (self.i + schritt) % n

    @property
    def feld(self):
        self._auf_aktives(1)
        return self.felder[self.i]

    def _speichern(self) -> bool:
        werte = {}
        for f in self.aktive():
            ok, wert = f.lesen(f.roh())
            if not ok:
                self.fehler, self.fehler_feld = wert, f.name
                self.i = self.felder.index(f)
                return False
            if f.art == "advanced":
                werte.update(wert)
            else:
                werte[f.name] = wert
        p = self._pruefen(werte)
        if p:
            name, self.fehler = p
            self.fehler_feld = name
            namen = [f.name for f in self.aktive()]
            if name in namen:
                self.i = [f.name for f in self.felder].index(name)
            return False
        self.antworten = werte
        self.fertig = True
        return True

    # ── Tasten (Tabelle: Ansicht = Art des Feldes, das gerade dran ist) ──
    _FELD = [("↑↓", "feld", "field"), ("tab/shift+tab", "feld")]
    _ESC = ("esc", "abbrechen", "cancel")
    TASTEN = Tasten({
        "text": [("type", "tippen", "type")] + _FELD + [
            ("enter", "speichern", "save"), ("ctrl+s", "speichern"),
            ("⌫", "zeichen_weg", "delete"), ("ctrl+u", "leeren", "clear"), _ESC],
        "wahl": [("←→", "waehlen", "choose"), ("space", "waehlen")] + _FELD + [
            ("enter", "speichern", "save"), ("ctrl+s", "speichern"), _ESC],
        # Enter/Leertaste/→ öffnen das Fenster „advanced", speichern mit Strg-S
        "advanced": [("enter", "advanced", "open")] + _FELD + [
            ("space/→", "advanced"), ("ctrl+s", "speichern", "save"), _ESC],
    })

    def __repr__(self):
        return kalender_kasten.zustand(self)

    def ansicht(self) -> str:
        return self.feld.art if self.feld.art in ("wahl", "advanced") else "text"

    def taste(self, ch: int) -> str:
        """→ 'weiter' | 'fertig' | 'abbruch'."""
        if self.box is not None:
            return self._box_taste(ch)
        if 0x80 <= ch <= 0xFF and self.feld.art == "text":        # Umlaute
            z = kalender_kasten.tippen_byte(self, ch)
            return self.aktion_tippen(z) if z else "weiter"
        return self.TASTEN.verteilen(self, self.ansicht(), ch) or "weiter"

    def _fehler_weg(self):
        """Wer das Feld mit dem Fehler ändert, sieht den Fehler nicht mehr."""
        if self.fehler_feld == self.feld.name:
            self.fehler, self.fehler_feld = "", None

    def aktion_abbrechen(self, _t):
        return "abbruch"

    def aktion_advanced(self, _t):
        self._box_oeffnen(self.feld)
        return "weiter"

    def aktion_speichern(self, _t):
        return "fertig" if self._speichern() else "weiter"

    def aktion_feld(self, taste):
        schritt = 1 if taste in ("tab", "down") else -1
        self.i = (self.i + schritt) % len(self.felder)
        self._auf_aktives(schritt)             # was nicht gilt, wird übersprungen
        return "weiter"

    def aktion_waehlen(self, taste):
        f = self.feld
        f.wahl = (f.wahl + (-1 if taste == "left" else 1)) % len(f.optionen)
        self._fehler_weg()
        return "weiter"

    def aktion_tippen(self, zeichen):
        f = self.feld
        f.text = (f.text + zeichen)[:200]
        self._fehler_weg()
        return "weiter"

    def aktion_zeichen_weg(self, _t):
        f = self.feld
        f.text = f.text[:-1]
        self._u8 = b""
        self._fehler_weg()
        return "weiter"

    def aktion_leeren(self, _t):
        self.feld.text = ""
        self._fehler_weg()
        return "weiter"

    # ── Fenster „advanced" über dem Formular (11.10.2026) ──────────────
    # Sasha: „im formular für nen termin kann man auf ‚advanced' klicken und
    # dort ist dann stylebox oder typus wählbar". Solange es offen ist, gehen
    # alle Tasten an das Fenster (kalender_advanced.Advanced, darin ggf. die
    # Stylebox oder „welche Liste?"); „fertig" übernimmt ins Feld, „abbruch"
    # lässt es, wie es war. Gespeichert wird erst mit dem Formular.
    def _box_oeffnen(self, f):
        text = (self.roh_werte().get("titel") or "").strip()
        self.box = kalender_advanced.Advanced(f.adv, quellen=f.quellen, text=text)
        self._box_feld = f

    def _box_taste(self, ch) -> str:
        erg = self.box.taste(ch)
        if erg == "fertig":
            f = self._box_feld
            alt, neu = kalender_advanced.quelle(f.adv), self.box.wert()
            f.adv = neu
            q = kalender_advanced.quelle(neu)
            titel = next((x for x in self.felder if x.name == "titel"), None)
            # Neue Liste: der Titel wird ihr Name, solange er leer ist oder noch
            # der Name der alten Liste (wie vorher bei A vorbelegt).
            if q and titel is not None and q != alt and \
                    titel.text.strip() in ("", (alt or {}).get("name", "")):
                titel.text = q["name"]
        if erg in ("fertig", "abbruch"):
            self.box = None
        return "weiter"

    def zeilen(self) -> list:
        """[(beschriftung, wert, aktiv, hilfe)] für den Kasten — für ALLE
        Felder; was nicht gilt (gilt()), hat den Wert „—" (gedämpft gezeichnet)."""
        aus = []
        w = self.roh_werte()
        k_jetzt = self.felder.index(self.feld)
        for k, (f, g) in enumerate(zip(self.felder, self.gilt())):
            if not g:
                wert = NICHT_AKTIV
            elif f.art == "advanced":
                # Keine Vorschau mehr in der Zeile, nur der Hinweis (Sasha,
                # 11.10.2026: „ohne vorschau … einfach nur mini erklärung").
                wert = ADVANCED_HINWEIS
            elif f.art == "wahl":
                wert = "‹ %s ›" % f.roh()
            else:
                wert = f.text
            hilfe = f.hilfe(w) if callable(f.hilfe) else f.hilfe
            aus.append((f.beschriftung, wert, k == k_jetzt, hilfe))
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


# ── Gruppe (CATEGORIES, 10.10.2026) ────────────────────────────────────
# Sasha: „in der monatsansicht seh ich einfach lieber uni uni uni". Das Feld
# „Gruppe" im Formular; die Namen kommen aus kalender_gruppen.NAMEN (vom
# Backend nachgeladen). Gilt für den ganzen Eintrag/die ganze Serie — darum
# nicht im Kasten „nur dieser Tag".
GRUPPE_KEINE, GRUPPE_EIGENE = "keine", "eigene"


def _gruppe_optionen() -> tuple:
    return (GRUPPE_KEINE,) + tuple(kalender_gruppen.NAMEN.values()) + (GRUPPE_EIGENE,)


def _gruppe_felder(roh=None) -> list:
    k = (roh or {}).get("kategorie") or kalender_gruppen.KEINE
    name = ""
    if k == kalender_gruppen.CUSTOM:
        wert, name = GRUPPE_EIGENE, (roh.get("kategorie_name") or "")
    else:
        wert = kalender_gruppen.NAMEN.get(k, GRUPPE_KEINE)
    ist_eigene = lambda w: w.get("gruppe") == GRUPPE_EIGENE
    return [Feld("gruppe", "Gruppe", art="wahl", wert=wert, optionen=_gruppe_optionen(),
                 hilfe="der Monat zeigt eine Gruppe je Tag als eine Zeile"),
            Feld("gruppe_name", "Name der Gruppe", wert=name, aktiv=ist_eigene,
                 lesen=lambda s: (True, s.strip()) if s.strip() else (False, "name fehlt"))]


def _gruppe_wert(w) -> tuple:
    """Formularwerte → (kategorie, kategorie_name) wie die API sie nimmt."""
    g = w.get("gruppe") or GRUPPE_KEINE
    if g == GRUPPE_EIGENE:
        return kalender_gruppen.CUSTOM, w.get("gruppe_name") or ""
    for k, n in kalender_gruppen.NAMEN.items():
        if n == g:
            return k, None
    return kalender_gruppen.KEINE, None


def _gruppe_body(w) -> dict:
    """Zusatzfelder für einen NEUEN Eintrag (leer = keine Gruppe)."""
    if "gruppe" not in w:
        return {}
    k, n = _gruppe_wert(w)
    if k == kalender_gruppen.KEINE:
        return {}
    return {"kategorie": k, **({"kategorie_name": n} if n else {})}


def _gruppe_aufruf(roh, w) -> list:
    """Hat sich die Gruppe eines bestehenden Eintrags geändert → ein Aufruf
    per Kennung (POST /api/calendar/kategorie), sonst keiner."""
    if "gruppe" not in w or not roh.get("kennung"):
        return []
    k, n = _gruppe_wert(w)
    alt_k = roh.get("kategorie") or kalender_gruppen.KEINE
    alt_n = roh.get("kategorie_name") if alt_k == kalender_gruppen.CUSTOM else None
    if (k, n or None) == (alt_k, alt_n or None):
        return []
    body = {"kennung": roh["kennung"], "kategorie": k}
    if n:
        body["kategorie_name"] = n
    return [("POST", "/api/calendar/kategorie", body)]


# ── Feld „Advanced": Typ (normal/liste) und Stylebox (11.10.2026) ─────
# Sasha: „bitte setz die stylebox unter ein eigenes fenster … mit typ
# ‚normal' und ‚list' verfügbar, dann wird der listentermin zu nem
# termintypen". EIN Feld statt „Stylebox" und „Liste"; das Fenster steht in
# kalender_advanced.py. Gilt wie die Gruppe für den ganzen Eintrag/die ganze
# Serie — darum nicht im Kasten „nur dieser Tag". Beim Speichern breitet es
# sich in den Werten aus: typ, quelle (nur bei liste, sonst None), stil,
# status (committed/uncommitted — seit 11.10.2026 hier statt „Verbindlich").
ADVANCED_HILFE = "typ (normal/liste), stylebox, status"
_QUELLE_TITEL_HILFE = "nur Rückfall, falls die Liste fehlt — es steht der oberste offene Punkt da"


ADVANCED_HINWEIS = "see for more options"


def _advanced_feld(roh, titel_feld, quellen=None) -> Feld:
    """Das Feld, vorbelegt aus `roh`; der Titel daneben darf bei Typ liste
    leer bleiben (= Name der Liste) und sagt dann, dass er nur Rückfall ist."""
    f = Feld("advanced", "Advanced", art="advanced", wert=kalender_advanced.wert_von(roh),
             lesen=lambda d: (True, {"typ": d.get("typ"), "quelle": kalender_advanced.quelle(d),
                                     "stil": dict(d.get("stil") or {}),
                                     **({"status": d["status"]} if d.get("status") else {})}),
             hilfe=ADVANCED_HILFE)
    f.quellen = quellen

    def titel_lesen(s):
        q = kalender_advanced.quelle(f.adv)
        return (True, s.strip() or q["name"]) if q else _l_titel(s)
    titel_feld.lesen = titel_lesen
    titel_feld.hilfe = lambda w: _QUELLE_TITEL_HILFE if kalender_advanced.quelle(f.adv) else ""
    return f


def _stil_body(w) -> dict:
    """Zusatzfeld für einen NEUEN Eintrag (leer = keins)."""
    return {"stil": dict(w["stil"])} if w.get("stil") else {}


def _stil_aufruf(roh, w) -> list:
    """Hat sich der Stil eines bestehenden Eintrags geändert → EIN Aufruf
    per Kennung (POST /api/calendar/stil ersetzt ihn; {} entfernt)."""
    if "stil" not in w or not roh.get("kennung"):
        return []
    if dict(w["stil"] or {}) == kalender_stil.von(roh):
        return []
    return [("POST", "/api/calendar/stil", {"kennung": roh["kennung"], "stil": dict(w["stil"] or {})})]


def _termin_felder(tag, heute, *, titel="", ganz=False, von="", bis="", ort="",
                   wiederholung="keine", alle="1", wtage="", wbis="",
                   mit_regel=True, mit_ganz=True, mit_tage=None, mit_datum=True,
                   datum_name="Tag", mit_gruppe=True, roh=None, quellen=None):
    """Die Felder des Termin-Kastens. `mit_tage` (Vorgabe: wie `mit_ganz`):
    das Feld „Tage" (ganztägig über mehrere Tage) — nicht bei Serien."""
    mit_tage = mit_ganz if mit_tage is None else mit_tage
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
             aktiv=lambda w: not ganz_an(w), hilfe="hh:mm"),
        Feld("bis", "Bis", wert=bis, lesen=_l_ende, aktiv=lambda w: not ganz_an(w),
             hilfe="hh:mm oder +1h, +2d20h"),
    ]
    if mit_tage:
        felder.append(Feld("tage", "Tage", wert="1", lesen=_l_zahl(),
                           aktiv=lambda w: ganz_an(w) and not regel_an(w)))
    if mit_regel:
        felder += [
            Feld("wied", "Wiederholung", art="wahl", wert=wiederholung, optionen=WIEDERHOLUNG),
            Feld("alle", "Abstand", wert=alle, lesen=_l_zahl(), aktiv=regel_an,
                 hilfe="1 = jedes Mal, 2 = jedes zweite Mal (z.B. jede 2. Woche)"),
            Feld("wtage", "An Tagen", wert=wtage, lesen=_l_wtage,
                 aktiv=lambda w: w.get("wied") == "wöchentlich",
                 hilfe="leer = %s; z.B. di do, mo-fr" % WT_KURZ[tag.weekday()]),
            Feld("wbis", "Wiederholen bis", wert=wbis, lesen=_l_datum(heute),
                 aktiv=regel_an, hilfe="leer = endlos"),
        ]
    felder.append(Feld("ort", "Ort", wert=ort))
    if mit_gruppe:
        felder += _gruppe_felder(roh) + [_advanced_feld(roh, felder[0], quellen)]
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


def _neu_plan(w, tag, layer="termine", quelle=None):
    """Aufrufe für einen neuen Eintrag aus Formularwerten (ohne Altes zu
    löschen). Täglich ohne Intervall mit Ende = Spanne (bleibt als Block
    sichtbar, Tage einzeln änderbar); sonst Wiederholung = Routine.
    `quelle` ({art, id, name}): Titel live aus der Liste — geht in jeden
    Body mit; ein leerer Titel wird ihr Name (der Rückfall)."""
    tag = w.get("datum") or tag
    titel, ort = (w.get("titel") or (quelle or {}).get("name") or ""), (w.get("ort") or None)
    gruppe = {**_gruppe_body(w), **_stil_body(w)}
    if quelle:
        gruppe = {**gruppe, "quelle": {"art": quelle["art"], "id": quelle["id"]}}
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
            body.update(gruppe)
            return [("POST", "/api/calendar/spanne", body)], "täglich bis %s: %s" % (
                datum_text(w["wbis"]), titel), None
        body = {"layer": layer, "label": titel, "seit": tag.isoformat(),
                "freq": _FREQ_KURZ[wied], "intervall": alle,
                "bis": w["wbis"].isoformat() if w.get("wbis") else None,
                "wochentage": w.get("wtage") or None, "time": start,
                "ende": ende if (e_dt and e_dt.date() == tag) else None, "ort": ort,
                **gruppe}
        return [("POST", "/api/calendar/routine", body)], "wiederholt sich: " + titel, None
    if start is None:
        n = w.get("tage") or 1
        if n == 1:
            body = {"layer": layer, "day": tag.isoformat(), "label": titel, **gruppe}
            if ort:
                body["ort"] = ort
            return [("POST", "/api/calendar/entry", body)], "angelegt: " + titel, None
        bis = tag + timedelta(days=n - 1)
        body = {"layer": layer, "von": tag.isoformat(), "bis": bis.isoformat(), "label": titel,
                **gruppe}
        if ort:
            body["ort"] = ort
        return [("POST", "/api/calendar/spanne", body)], "angelegt: %s bis %s" % (
            titel, datum_text(bis)), None
    if e_dt is not None and e_dt.date() > tag:
        body = {"layer": layer, "von": tag.isoformat(), "bis": e_dt.date().isoformat(),
                "label": titel, "start_zeit": start, "end_zeit": ende, **gruppe}
        if ort:
            body["ort"] = ort
        return [("POST", "/api/calendar/spanne", body)], "angelegt: %s bis %s %s" % (
            titel, WT_KURZ[e_dt.weekday()], ende), None
    body = {"layer": layer, "day": tag.isoformat(), "label": titel, "time": start, **gruppe}
    if ende:
        body["ende"] = ende
    if ort:
        body["ort"] = ort
    kon = {k: body[k] for k in ("day", "label", "time", "ende") if k in body} if ende else None
    return [("POST", "/api/calendar/entry", body)], "angelegt: " + titel, kon


def formular_neu(tag: date, heute: date, quellen=None) -> Formular:
    """a: neuer Termin am gewählten Tag (calcurse: der Tag im Kalender).
    Ein Listen-Termin ist seit 11.10.2026 kein eigener Weg mehr (früher
    Taste A), sondern Advanced → Typ liste in GENAU diesem Formular; der
    Titel wird dann der Name der Liste (leer = ihr Name), angezeigt wird live
    ihr oberster offener Punkt. `quellen()` → die Listen (von der Bedienung)."""
    def plan(w):
        layer = _ziel_ebene(w)
        aufrufe, meldung, kon = _neu_plan(w, tag, layer, w.get("quelle"))
        if layer == UNVERBINDLICH:
            kon = None                    # uncommitted: Kollision nur Hinweis, keine Rückfrage
        return _plan(aufrufe, meldung, konflikt=kon, danach={"tag": w.get("datum") or tag})
    # committed (Standard) oder uncommitted: Advanced → Status (seit
    # 11.10.2026, vorher eigenes Feld „Verbindlich"); umschalten auch mit u.
    return Formular("neuer termin", _termin_felder(tag, heute, quellen=quellen), plan)


# ── Typ liste beim Bearbeiten (Feld „Advanced", 11.10.2026) ────────────
# Vorher ein eigenes Feld „Liste" mit bleibt/keine/wählen …; jetzt steht die
# Wahl im Fenster „advanced". Beim Speichern eines bestehenden Eintrags:
# neue/andere Liste → POST /api/calendar/quelle per Kennung; Typ zurück auf
# normal → danach „aktuellen Titel übernehmen? (j/n)" (DELETE …/quelle).
def _gleiche_quelle(a, b) -> bool:
    return (a or {}).get("art") == (b or {}).get("art") and (a or {}).get("id") == (b or {}).get("id")


def _quelle_aufruf(roh, w) -> list:
    """Neue oder andere Liste für einen bestehenden Eintrag → EIN Aufruf."""
    if "typ" not in w or not roh.get("kennung"):
        return []
    neu, alt = w.get("quelle"), kalender_quellen.quelle_von(roh)
    if not neu or _gleiche_quelle(neu, alt):
        return []
    return kalender_quellen.plan_setzen(roh, neu)["aufrufe"]


def _quelle_folge(roh, w):
    """Nach dem Speichern: Typ liste → normal? → () → Rückfrage-Kasten,
    den die Bedienung nach den Aufrufen öffnet; sonst None."""
    if "typ" not in w or not roh.get("kennung"):
        return None
    if w.get("quelle") or kalender_quellen.quelle_von(roh) is None:
        return None
    live = roh.get("titel_live") or roh.get("label") or ""
    return lambda: Dialog("liste lösen", [Schritt(
        "ok", "aktuellen Titel „%s“ übernehmen?" % live, art="wahl",
        wahl={"j": True, "n": False})],
        lambda a: kalender_quellen.plan_loesen(roh, a["ok"]))


def _quelle_bleibt(roh, w):
    """Beim Neu-Anlegen statt Ändern (Einmal → Wiederholung): die Quelle aus
    dem Fenster (Typ normal = keine)."""
    if "typ" in w:
        return w.get("quelle")
    return kalender_quellen.quelle_von(roh)


UNVERBINDLICH = "uncommitted"


def _ziel_ebene(w, alt="termine"):
    """Die Ebene aus Advanced → Status; ohne Status bleibt `alt`."""
    s = w.get("status")
    if s is None:
        return alt
    return UNVERBINDLICH if s == kalender_advanced.UNCOMMITTED else "termine"


def _ebene_aufruf(roh, w) -> list:
    """Status in Advanced geändert → nach den anderen Aufrufen EIN Aufruf
    per Kennung (POST /api/calendar/ebene mit ziel)."""
    if not roh.get("kennung"):
        return []
    alt = roh.get("layer") or "termine"
    ziel = _ziel_ebene(w, alt)
    if ziel == alt:
        return []
    return [("POST", "/api/calendar/ebene", {"kennung": roh["kennung"], "ziel": ziel})]


def plan_ebene(roh: dict) -> dict | None:
    """u: zwischen committed und uncommitted umschalten (per Kennung)."""
    k = roh.get("kennung")
    if not k:
        return None
    nach = "committed" if roh.get("layer") == UNVERBINDLICH else "uncommitted"
    return _plan([("POST", "/api/calendar/ebene", {"kennung": k})],
                 "%s: %s" % (nach, roh.get("label", "")))


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


# ── Tasten in Rückfragen: EIN Schema für alle Kalenderfunktionen ──────
# Sasha, 10.10.2026: „wenn man löscht ist 1 = alle das ist inkonsistent …
# mach sie konsistent, a for all find ich gut". Also überall:
#   j / n      ja / nein          (Esc = abbrechen, wie n)
#   a          alle (ganze Serie/Spanne)
#   t          nur dieser Tag     (wie t im Rhythmus-Kasten)
#   z          ein Zeitraum       (Rhythmus-Kasten)
#   Auswahl    Anfangsbuchstabe (u Uni, k keine, e eigene …), nie Ziffern
def _wahl_umfang(roh):
    return Schritt("umfang", "„%s“ ändern: nur dieser Tag oder alle?" % roh.get("label", ""),
                   art="wahl", wahl={"t": "dieser", "a": "alle"})


def formular_bearbeiten(roh: dict, tag: date, heute: date, fokus=None, quellen=None):
    """e (und r): derselbe Kasten, vorbelegt. Routinen und Spannen fragen
    vorher „nur dieser Tag oder alle?" (Handy-Kalender) — dann ist das
    Ergebnis ein kleiner Dialog, dessen Plan den Kasten als `weiter` bringt.
    `quellen()` → die Listen für Advanced → Typ liste (von der Bedienung,
    die sie holt); ohne sie lässt sich eine Liste nur lösen."""
    a_ = art(roh)
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, e0, ort0 = roh.get("time") or "", roh.get("ende") or "", roh.get("ort") or ""
    iso = tag.isoformat()

    if a_ == "einmal":
        def plan(w):
            if w.get("wied", "keine") != "keine":       # wird zur Wiederholung
                aufrufe, meldung, _k = _neu_plan(w, tag, _ziel_ebene(w, layer),
                                                 _quelle_bleibt(roh, w))
                weg = ("DELETE", "/api/calendar/eintrag",
                       {"layer": layer, "day": iso, "label": label, "time": t0 or None})
                return _plan(aufrufe + [weg], meldung)
            start, e_dt = _zeiten(w["datum"], w)
            if e_dt and e_dt.date() > w["datum"]:       # über Mitternacht → Spanne
                aufrufe, meldung, _k = _neu_plan(w, tag, _ziel_ebene(w, layer),
                                                 _quelle_bleibt(roh, w))
                weg = ("DELETE", "/api/calendar/eintrag",
                       {"layer": layer, "day": iso, "label": label, "time": t0 or None})
                return _plan(aufrufe + [weg], meldung, danach={"tag": w["datum"]})
            neu = {"day": w["datum"].isoformat(), "label": w["titel"],
                   "time": start or "", "ende": e_dt.strftime("%H:%M") if e_dt else "",
                   "ort": w.get("ort") or ""}
            kon = ({"day": neu["day"], "label": neu["label"], "time": neu["time"],
                    "ende": neu["ende"]} if neu["time"] and neu["ende"]
                   and _ziel_ebene(w, layer) != UNVERBINDLICH else None)
            return _plan([("PUT", "/api/calendar/eintrag",
                           {"layer": layer, "day": iso, "label": label,
                            "time": t0 or None, "new": neu})] + _gruppe_aufruf(roh, w)
                         + _stil_aufruf(roh, w) + _quelle_aufruf(roh, w)
                         + _ebene_aufruf(roh, w),
                         "geändert: " + w["titel"], konflikt=kon, danach={"tag": w["datum"]},
                         zurueck=_quelle_folge(roh, w))
        felder = _termin_felder(tag, heute, titel=label, ganz=not t0, von=t0, bis=e0,
                                ort=ort0, roh=roh, quellen=quellen)
        return Formular("termin ändern", felder, plan, fokus=fokus)

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
                         "time": t0 or None, "new": neu})] + _gruppe_aufruf(roh, w) \
                + _stil_aufruf(roh, w) + _quelle_aufruf(roh, w) + _ebene_aufruf(roh, w)
            if wied == "keine":                         # Wiederholung aus = ganz löschen?
                return _plan(meldung="Wiederholung „keine“: zum Löschen d benutzen")
            return _plan(aufrufe, "alle geändert: " + w["titel"],
                         zurueck=_quelle_folge(roh, w))

        r = _regel_felder(roh.get("rrule"))
        # Ganztägig auch hier (18.10.2026): vorher fehlte das Feld bei Serien,
        # „Von" war Pflicht — eine ganztägige Serie ließ sich nicht mehr
        # speichern („uhrzeit fehlt"), z.B. nach Advanced → Stylebox. „Nur
        # dieser Tag" einer Serie MIT Uhrzeit kann nicht ganztägig werden
        # (die Abweichung erbt die Zeit der Regel) — dort bleibt es weg.
        form_dieser = lambda: Formular("nur dieser tag · " + datum_text(tag), _termin_felder(
            tag, heute, titel=label, ganz=not t0, von=t0, bis=e0, ort=ort0, mit_regel=False,
            mit_ganz=not t0, mit_tage=False, datum_name="Verschieben auf", mit_gruppe=False),
            nur_dieser, fokus=fokus)
        def form_alle():
            felder = _termin_felder(
                tag, heute, titel=label, ganz=not t0, von=t0, bis=e0, ort=ort0,
                mit_tage=False, mit_datum=False, wiederholung=r["wiederholung"], alle=r["alle"],
                wtage=r["wtage"], wbis=r["wbis"], roh=roh, quellen=quellen)
            return Formular("alle termine der serie", felder, alle, fokus=fokus)
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
                       {"layer": layer, "von": von_iso, "label": label, "new": neu})]
                     + _gruppe_aufruf(roh, w) + _stil_aufruf(roh, w) + _quelle_aufruf(roh, w)
                     + _ebene_aufruf(roh, w),
                     "alle tage geändert: " + w["titel"], danach={"tag": w["erster"]},
                     zurueck=_quelle_folge(roh, w))

    def alle_pruefen(w):
        if w["letzter"] < w["erster"]:
            return "letzter", "letzter tag vor dem ersten"
        return None

    form_tag = lambda: Formular("nur dieser tag · " + datum_text(tag), [
        Feld("ganz", "Ganztägig", art="wahl", wert="nein" if t0 else "ja", optionen=("nein", "ja")),
        Feld("von", "Von", wert=t0, lesen=_l_zeit(leer_ok=False),
             aktiv=lambda w: w.get("ganz") != "ja", hilfe="hh:mm"),
        Feld("bis", "Bis", wert=e0, lesen=_l_ende,
             aktiv=lambda w: w.get("ganz") != "ja", hilfe="hh:mm, leer = ohne"),
    ], tag_plan)
    def form_alle():
        titel = Feld("titel", "Titel", wert=label, lesen=_l_titel)
        return Formular("ganze spanne", [
            titel,
            Feld("erster", "Erster Tag", wert=datum_text(von_d), lesen=_l_datum(heute)),
            Feld("letzter", "Letzter Tag", wert=datum_text(bis_d), lesen=_l_datum(heute)),
            Feld("ort", "Ort", wert=ort0),
        ] + _gruppe_felder(roh) + [_advanced_feld(roh, titel, quellen)], alle_plan,
            pruefen=alle_pruefen)
    return Dialog("ändern", [_wahl_umfang(roh)], lambda a: _plan(
        weiter=form_tag() if a["umfang"] == "dieser" else form_alle()))


def formular_wiederholen(roh: dict, tag: date, heute: date, quellen=None):
    """r (calcurse „repeat"): der Bearbeiten-Kasten, gleich auf
    „Wiederholung"; eine Spanne wiederholt sich nicht (None)."""
    if art(roh) == "spanne":
        return None
    return formular_bearbeiten(roh, tag, heute, fokus="wied", quellen=quellen)


# ── d: Löschen ─────────────────────────────────────────────────────────
def dialog_loeschen(roh: dict, tag: date) -> Dialog:
    a_ = art(roh)
    label, layer = roh.get("label", ""), roh.get("layer") or "termine"
    t0, iso = roh.get("time") or None, tag.isoformat()
    if a_ == "routine":
        if roh.get("deaktiviert"):
            return Dialog("wieder an", [Schritt(
                "ok", "„%s“ am %s wieder aktivieren?" % (label, datum_text(tag)),
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
            "wie", "„%s“ löschen: alle oder nur dieser Tag?" % label,
            art="wahl", wahl={"a": "alle", "t": "dieses", "n": None})], plan)
    day = roh.get("von") or iso if a_ == "spanne" else iso
    frage = ("Ganze Spanne „%s“ löschen?" if a_ == "spanne"
             else "„%s“ löschen?") % label
    return Dialog("löschen", [Schritt("ok", frage, art="wahl", wahl={"j": True, "n": False})],
                  lambda a: _plan([("DELETE", "/api/calendar/eintrag",
                                    {"layer": layer, "day": day, "label": label,
                                     "time": None if a_ == "spanne" else t0})]
                                  if a["ok"] else [], "gelöscht: " + label if a["ok"] else ""))


# ── c / p: Kopieren, Einfügen ──────────────────────────────────────────
def kopie(roh: dict) -> dict:
    """calcurse „c": was beim Einfügen wieder entsteht (immer ein Einmal-
    Termin am gewählten Tag, auch aus einer Routine)."""
    k = {f: roh[f] for f in ("label", "time", "ende", "ort", "layer") if roh.get(f)}
    if kalender_gruppen.schluessel(roh):       # die Gruppe kommt mit
        k.update({f: roh[f] for f in ("kategorie", "kategorie_name") if roh.get(f)})
    q = kalender_quellen.quelle_von(roh)
    if q:                                      # die Liste kommt mit (Titel bleibt live)
        k["quelle"] = {"art": q["art"], "id": q["id"]}
    if kalender_stil.von(roh):                 # das Aussehen kommt mit
        k["stil"] = kalender_stil.von(roh)
    return k


def plan_einfuegen(k: dict, tag: date) -> dict:
    body = {"layer": "termine", "day": tag.isoformat(), **k}     # k trägt seine Ebene mit
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
    return Dialog("löschen", [Schritt("ok", "„%s“ löschen?" % item.get("text", ""),
                                      art="wahl", wahl={"j": True, "n": False})],
                  lambda a: _plan([("DELETE", "/api/lists/%s/items/%s" % (lid, item["id"]), None)]
                                  if a["ok"] else [], "gelöscht" if a["ok"] else ""))


# ── Enter: Ansehen ─────────────────────────────────────────────────────
def details(roh: dict, tag: date, vorschau: dict | None = None) -> list:
    """Alles über einen Termin, für das Ansehen-Fenster (calcurse „v").
    Quellen-Termin: oben der Live-Titel, dazu Liste, aktueller und die
    nächsten offenen Punkte (vorschau = GET /api/calendar/quelle)."""
    quelle = kalender_quellen.details_zeilen(roh, vorschau)
    zeilen = [(roh.get("titel_live") if quelle else None) or roh.get("label", "?"), ""]
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
    if kalender_gruppen.anzeige(roh):
        zeilen.append("Gruppe   " + kalender_gruppen.anzeige(roh))
    zeilen += quelle
    if kalender_stil.von(roh):
        zeilen.append("Stil     " + kalender_stil.vorschau_text(kalender_stil.von(roh)))
    zeilen.append("Ebene    " + str(roh.get("layer", "")))
    return zeilen


def details_gruppe(roh: dict, tag: date) -> list:
    """Enter auf einer Gruppe in B: was sie zusammenfasst."""
    zeilen = ["%s  %s%s" % (roh.get("label", "?"), roh.get("time") or "",
                             ("–" + roh["ende"]) if roh.get("ende") else ""),
              "%s, %s · %d Termine" % (WT_LANG[tag.weekday()], datum_text(tag),
                                       len(roh.get("glieder") or [])), ""]
    for g in roh.get("glieder") or []:
        t, e = g.get("time") or "", g.get("ende") or ""
        zeilen.append("%-11s %s" % (t + ("–" + e if e else ""), g.get("label", "?")))
    zeilen += ["", "einzeln ändern: v (Liste oder Woche)"]
    return zeilen
