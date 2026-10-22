# core/ehrlichkeit_kalender.py
#
# Nachprüfung nach Kalender-Schreibaufrufen — reines Python, Teil des
# Live-Prüfers (core/ehrlichkeit.py ruft `befunde`; Doku
# memory/ki/ehrlichkeit_live.md, Bibel PR-10 und PR-12).
#
# Anlass 22.10.2026, Gespräch 20261022-111358-dd6127 (qwen-plus im
# Budget-Rückfall): Sasha gab vier Sprechstunden mit Wochentag und Uhrzeit,
# ohne Zeitraum. qwen trug sie mit von=2026-10-26, bis=2026-12-20 ein (nie
# genannt) und schrieb „alle mit 'uncommitted'", obwohl kein Aufruf ein
# layer hatte. Der Prüfer sah nur, DASS geschrieben wurde, nicht WAS.
#
# Zwei Arten Befund:
#
#   grundlos     Ein Aufruf setzt bis, von oder ende, das in Sashas Text
#                nirgends steht — weder als Datum/Uhrzeit (auch „26.10.",
#                „halb sechs", „17 Uhr") noch als ungefähre Angabe („ab
#                nächster Woche", „bis Semesterende", „zwei Stunden"). Steht
#                so etwas Ungefähres da, gibt es KEINEN Befund: rechnen kann
#                die KI, erfinden soll sie nicht. von zwischen heute und in
#                sieben Tagen gilt als „ab jetzt" (der nächste Termin), nicht
#                als erfunden. Grundlage sind auch das Gespräch davor und
#                die Ergebnisse lesender Werkzeuge (eine Websuche nach der
#                Vorlesungszeit belegt ein bis). EINE Korrekturrunde je Zug
#                (gespeichert ist es schon; die KI soll es sagen und
#                nachfragen), danach eine Warnung, falls die Antwort den Wert
#                nicht nennt.
#   behauptung   Die Antwort sagt über die eben geschriebenen Einträge etwas,
#                das in keinem Aufruf und keinem Ergebnis steht: Ebene
#                vielleicht/uncommitted, Typ Deadline, mehr Einträge als
#                geschrieben, eine Zeitspanne, die nirgends vorkommt.
#                Korrekturrunden wie bei „tat", danach Warnung.
#
# Nur wenn in diesem Zug ein Kalender-Werkzeug geschrieben hat (ok) — ein
# Plauder-Zug kostet nichts. Den Wochentag im Titel prüft der Adapter VOR
# dem Speichern (K-TITEL-WOCHENTAG, core/titel_wochentag.py).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import re
from datetime import date, timedelta

import ehrlichkeit_erkennen as erkennen
import uhr

# Befund-Arten, die höchstens EINE Korrekturrunde je Zug bekommen, aber
# (anders als ehrlichkeit.WEICH) danach als Warnung zu Sasha gehen.
EINMAL = ("grundlos",)

SCHREIBEN = {"add_calendar_entry", "add_calendar_routine", "edit_calendar_routine",
             "edit_calendar_entry", "add_calendar_pause", "delete_calendar_entry",
             "set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase",
             "set_calendar_group", "set_calendar_layer", "set_calendar_style",
             "set_calendar_source", "clear_calendar_source"}
ANLEGEN = {"add_calendar_entry", "add_calendar_routine", "set_calendar_phase"}

# Welche Felder welches Werkzeugs nachgeprüft werden. ende nur beim Anlegen:
# beim Ändern darf das Ende mit dem Beginn wandern (gleiche Dauer).
FELDER = {"add_calendar_routine": ("von", "bis", "ende"),
          "add_calendar_entry": ("ende",),
          "edit_calendar_routine": ("von", "bis")}

_MONATE = {"januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3,
           "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
           "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "oktober": 10,
           "okt": 10, "november": 11, "nov": 11, "dezember": 12, "dez": 12}
_MONAT = r"(?:" + "|".join(sorted(_MONATE, key=len, reverse=True)) + r")"
_ZAHLWORT = {"eins": 1, "ein": 1, "eine": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
             "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
             "zwölf": 12}
_ZAHL = r"(?:\d{1,2}|" + "|".join(_ZAHLWORT) + r")"

# Ungefähre Angaben: steht so etwas in Sashas Nachricht, wird nicht geprüft.
_UNGEFAEHR_VON = re.compile(
    r"\bab\s+(?!\d{1,2}(?:[:.]\d{2})?\s*(?:uhr|h)\b)|\bseit\b|\bbeginn\w*|\bstart\w*|"
    r"\banfang\w*|\bsemester\w*|\bvorlesungs\w*|\bnächst\w*\s+woche|\bkommend\w*\s+woche|"
    r"\bübernächst\w*|\bmorgen\b|\bübermorgen\b|\b" + _MONAT + r"\b")
_UNGEFAEHR_BIS = re.compile(
    r"\bbis\s+(?!\d{1,2}(?:[:.]\d{2})?\s*(?:uhr|h)?(?:\s|$|[,;)]))|\bsemester\w*|"
    r"\bvorlesungs\w*|\bferien\b|\bweihnacht\w*|\bostern\b|\bsilvester\b|\bjahresende\b|"
    r"\bmonatsende\b|\bende\s+(?:des|der|vom|im|nächst\w*)\b|\b" + _ZAHL
    + r"\s+(?:woche|wochen|monat|monate|monaten)\b|\b(?:wochen|monate)\s+lang\b|"
    r"\b" + _MONAT + r"\b")
_DAUER = re.compile(r"\b\d+\s*(?:min|minuten|h|std|stunden?)\b|\b(?:eine|zwei|drei|vier|"
                    r"halbe|anderthalb|einhalb|dreiviertel)\s*stunden?\b|\bdauer\w*|"
                    r"\bdauert\b|\blang\b|\bopen end\b")


# ── Daten und Uhrzeiten in einem Text ───────────────────────────────────

def daten(text: str) -> set:
    """(tag, monat) aller Daten im Text — Jahr egal, auf der vorsichtigen Seite."""
    t = (text or "").casefold()
    raus = set()
    for j, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t):
        raus.add((int(d), int(m)))
    for d, m in re.findall(r"(?<![\d.:])(\d{1,2})\.(\d{1,2})(?![:\d])", t):
        if 1 <= int(d) <= 31 and 1 <= int(m) <= 12:
            raus.add((int(d), int(m)))
    for d, m in re.findall(r"(?<![\d.])(\d{1,2})\.?\s*(" + _MONAT + r")\b", t):
        if 1 <= int(d) <= 31:
            raus.add((int(d), _MONATE[m]))
    return raus


def _beide(h: int, m: int) -> set:
    if not (0 <= h <= 24 and 0 <= m < 60):
        return set()
    return {(h % 24, m), ((h + 12) % 24, m)}


_SPRECH = re.compile(r"\b(halb|viertel nach|viertel vor|dreiviertel)\s+(" + _ZAHL + r")\b")


def uhrzeiten(text: str) -> set:
    """(stunde, minute) aller Uhrzeiten im Text, je auch +12 h („5 Uhr" kann
    17:00 heißen) — auf der vorsichtigen Seite."""
    t = (text or "").casefold()
    raus = set()
    for h, m in re.findall(r"(?<![\d.])(\d{1,2})[:.](\d{2})(?!\d)", t):
        raus |= _beide(int(h), int(m))
    for h in re.findall(r"(?<![\d.:])(\d{1,2})\s*(?:uhr|h)\b", t):
        raus |= _beide(int(h), 0)
    for a, b in re.findall(r"(?<![\d.:])(\d{1,2})\s*(?:-|–|bis)\s*(\d{1,2})(?![\d.:])", t):
        raus |= _beide(int(a), 0) | _beide(int(b), 0)
    for h in re.findall(r"\bum\s+(\d{1,2})(?![\d.:])", t):
        raus |= _beide(int(h), 0)
    for h in re.findall(r"\b(?:um|bis|ab|von)\s+(" + "|".join(_ZAHLWORT) + r")\b", t):
        raus |= _beide(_ZAHLWORT[h], 0)
    for h in re.findall(r"\b(" + "|".join(_ZAHLWORT) + r")\s+uhr\b", t):
        raus |= _beide(_ZAHLWORT[h], 0)
    for art, zahl in _SPRECH.findall(t):
        n = int(zahl) if zahl.isdigit() else _ZAHLWORT[zahl]
        h, m = {"halb": (n - 1, 30), "viertel nach": (n, 15), "viertel vor": (n - 1, 45),
                "dreiviertel": (n - 1, 45)}[art]
        raus |= _beide(h, m)
    return raus


def _zeit(wert: str):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(wert or ""))
    return (int(m.group(1)) % 24, int(m.group(2))) if m else None


def _datum(wert: str):
    try:
        return date.fromisoformat(str(wert or "").strip()[:10])
    except ValueError:
        return None


# ── grundlos ────────────────────────────────────────────────────────────

def _grundlos(schritt, feld: str, wert: str, nutzer: str, grund_daten: set,
              grund_zeiten: set, heute: date) -> bool:
    if feld == "ende":
        z = _zeit(wert)
        return z is not None and z not in grund_zeiten and not _DAUER.search(nutzer)
    d = _datum(wert)
    if d is None or (d.day, d.month) in grund_daten:
        return False
    if feld == "von":
        if heute <= d <= heute + timedelta(days=7):
            return False                     # „ab jetzt": der nächste Termin
        return not _UNGEFAEHR_VON.search(nutzer)
    return not _UNGEFAEHR_BIS.search(nutzer)


def _wert_text(feld: str, wert: str) -> str:
    d = _datum(wert)
    return d.strftime("%d.%m.%Y") if d and feld != "ende" else str(wert)


def grundlos_befunde(antwort: str, protokoll: list, nutzer_text: str, grundlage: str,
                     heute: date | None = None) -> list:
    heute = heute or uhr.heute()
    nutzer = (nutzer_text or "").casefold()
    lesend = "\n".join(str(s.text) for s in protokoll if s.name not in SCHREIBEN)
    gesamt = "\n".join((nutzer_text or "", grundlage or "", lesend))
    grund_daten, grund_zeiten = daten(gesamt), uhrzeiten(gesamt)
    raus = []
    for s in protokoll:
        if s.status != "ok" or s.name not in FELDER:
            continue
        args = s.args if isinstance(s.args, dict) else {}
        if s.name == "edit_calendar_routine" and args.get("aktion") == "loeschen":
            continue
        for feld in FELDER[s.name]:
            wert = str(args.get(feld) or "").strip()
            if wert and _grundlos(s, feld, wert, nutzer, grund_daten, grund_zeiten, heute):
                wen = str(args.get("label") or args.get("kennung") or "").strip()
                gleich = next((b for b in raus if (b["werkzeug"], b["feld"], b["wert"])
                               == (s.name, feld, wert)), None)
                if gleich:                    # derselbe Wert an mehreren: ein Befund
                    gleich["wen"].append(wen)
                else:
                    raus.append({"art": "grundlos", "feld": feld, "wert": wert,
                                 "werkzeug": s.name, "wen": [wen]})
    for b in raus:
        b["satz"] = (f"{b['feld']} {_wert_text(b['feld'], b['wert'])} bei "
                     + ", ".join(f"„{w}“" for w in b["wen"]))
    return raus


# ── behauptung ──────────────────────────────────────────────────────────

_VERNEINT = r"\b(?:nicht|kein\w*|ohne)\b[^.!?]{0,40}"
_EBENE = re.compile(r"\buncommitted\b|\bunverbindlich\w*|\b(?:als|auf|ebene)\s+['\"„‚]?"
                    r"vielleicht\b|\bvorläufig\w*\s+(?:eingetragen|angelegt)")
_DEADLINE = re.compile(r"\bdeadlines?\b|\bals\s+frist\b")
_ERLEDIGT = re.compile(r"\b(eingetragen|angelegt|hinzugefügt|gelöscht|geändert|verschoben)\b")
_ANZAHL = re.compile(r"(?<![\w.:])(" + _ZAHL + r")(?:\s+\w+){0,2}?\s+(termin\w*|eintr[aä]g\w*|"
                     r"routine\w*|serien?|sprechstunden?|veranstaltung\w*|kurse?|"
                     r"vorlesung\w*|übung\w*|deadlines?|fristen?|phasen?)\b")
_SPANNE = re.compile(r"(?<![\d.:])(\d{1,2})(?:[:.](\d{2}))?\s*(?:uhr\s*)?(?:–|-|—|bis)\s*"
                     r"(\d{1,2})(?:[:.](\d{2}))?(?![\d])")


def _spannen(text: str) -> set:
    """Zeitspannen (h, m, h, m); mindestens eine Seite mit Minuten („18:10-19")."""
    raus = set()
    for a, b, c, d in _SPANNE.findall((text or "").casefold()):
        if (b or d) and int(a) <= 24 and int(c) <= 24:
            raus.add((int(a) % 24, int(b or 0), int(c) % 24, int(d or 0)))
    return raus


def _behauptet(muster, satz) -> bool:
    if satz.frage or not muster.search(satz.klein):
        return False
    return not re.search(_VERNEINT + "(?:" + muster.pattern + ")", satz.klein)


def _args_text(protokoll: list) -> str:
    teile = []
    for s in protokoll:
        args = s.args if isinstance(s.args, dict) else {}
        teile.append(" ".join(f"{k}={v}" for k, v in args.items()))
        teile.append(str(s.text))
    return "\n".join(teile).casefold()


def _anzahl(wort: str) -> int:
    return int(wort) if wort.isdigit() else _ZAHLWORT.get(wort, 0)


def behauptung_befunde(antwort: str, protokoll: list, grundlage: str = "") -> list:
    geschrieben = [s for s in protokoll if s.name in SCHREIBEN and s.status == "ok"]
    belege = _args_text(protokoll)
    angelegt = sum(1 for s in geschrieben if s.name in ANLEGEN)
    belegt_spannen = _spannen(belege) | _spannen(grundlage)
    raus = []
    for satz in erkennen.saetze(antwort):
        if _behauptet(_EBENE, satz) and "uncommitted" not in belege:
            raus.append({"art": "behauptung", "satz": satz.text,
                         "was": "die Ebene vielleicht (uncommitted)",
                         "tipp": "layer 'uncommitted' beim Anlegen bzw. set_calendar_layer"})
        if _behauptet(_DEADLINE, satz) and "deadline" not in belege:
            raus.append({"art": "behauptung", "satz": satz.text, "was": "den Typ Deadline",
                         "tipp": "typ 'deadline'"})
        if not satz.frage and _ERLEDIGT.search(satz.klein) \
                and not re.search(r"\b(?:nicht|kein\w*)\b", satz.klein):
            for zahl, _ in _ANZAHL.findall(satz.klein):
                n = _anzahl(zahl)
                if angelegt < n <= 50 and re.search(r"\b(eingetragen|angelegt|hinzugefügt)\b",
                                                    satz.klein):
                    raus.append({"art": "behauptung", "satz": satz.text,
                                 "was": f"{n} angelegte Einträge (angelegt: {angelegt})",
                                 "tipp": "die fehlenden eintragen"})
                    break
        if not satz.frage:
            fremd = _spannen(satz.klein) - belegt_spannen
            if fremd:
                a, b, c, d = sorted(fremd)[0]
                raus.append({"art": "behauptung", "satz": satz.text,
                             "was": f"die Zeit {a}:{b:02d}–{c}:{d:02d}",
                             "tipp": "die Zeit aus dem Werkzeug-Ergebnis nennen"})
    return raus


# ── für den Prüfer ──────────────────────────────────────────────────────

def befunde(antwort: str, protokoll: list, *, nutzer_text: str = "",
            grundlage: str = "", heute: date | None = None) -> list:
    """Alle Kalender-Befunde einer Antwort. Leer, wenn in diesem Zug kein
    Kalender-Werkzeug geschrieben hat."""
    if not any(s.name in SCHREIBEN and s.status == "ok" for s in protokoll):
        return []
    raus = grundlos_befunde(antwort, protokoll, nutzer_text, grundlage, heute)
    raus += behauptung_befunde(antwort, protokoll, "\n".join((nutzer_text or "",
                                                               grundlage or "")))
    for b in raus:
        b["zeile"], b["warnung"] = zeile(b), warnung(b, antwort)
    return raus


def zeile(b: dict) -> str:
    """Der Hinweis an die KI (eine Zeile im Prüf-Hinweis)."""
    if b["art"] == "grundlos":
        wo = "edit_calendar_routine" if b["werkzeug"] != "add_calendar_entry" \
            else "edit_calendar_entry"
        return (f"- Du hast {b['satz']} eingetragen — das hat Sasha nicht gesagt (weder als "
                f"Datum noch ungefähr wie „ab nächster Woche“). Sag ihm in der Antwort, dass "
                f"dieser Wert angenommen ist, und frag nach dem richtigen; nennt er ihn, "
                f"ändere es mit {wo}. Keinen neuen Wert erfinden.")
    return (f"- Du schreibst „{b['satz']}“ — aber kein Werkzeug-Aufruf dieses Zugs zeigt "
            f"{b['was']}. Schreib nur, was in den Aufrufen und Ergebnissen steht, oder hol "
            f"es jetzt mit dem Werkzeug nach ({b['tipp']}).")


def warnung(b: dict, antwort: str) -> str:
    """Satz für Sasha, wenn der Befund nach den Runden noch steht ('' = keine)."""
    if b["art"] == "grundlos":
        a = (antwort or "").casefold()
        d = _datum(b["wert"])
        genannt = (d and ((d.day, d.month) in daten(a))) or (
            b["feld"] == "ende" and _zeit(b["wert"]) in uhrzeiten(a))
        if genannt:
            return ""                         # Sasha sieht den Wert in der Antwort
        return (f"⚠ Angenommen, nicht von dir: {b['satz']} — bitte prüfen.")
    return f"⚠ Ohne Beleg: „{_kurz(b['satz'])}“ — {b['was']} steht in keinem Werkzeug-Aufruf."


def _kurz(satz, n: int = 90) -> str:
    t = " ".join(str(satz or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"
