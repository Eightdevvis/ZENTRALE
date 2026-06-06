# core/calendar.py
#
# Kalender-System mit Layer-Struktur – zeitliche Klammer um den
# assoziativen Graph (siehe ki_system.md).
#
# Idee: der Konzept-Graph ist assoziativ und gut darin "wer mag was,
# wer kennt wen, was hängt mit was zusammen" abzubilden. Was er
# strukturell NICHT gut kann ist "welcher Tag war wann", "was kommt
# noch", "regelmäßige Termine". Dafür gibt es jetzt diese Schicht:
# eine eigene Datei `data/ai_calendar.json` mit benannten Layern,
# die unabhängig sichtbar/unsichtbar geschaltet werden können.
#
# Layer-Modell (initial drei, weitere via add_layer erweiterbar):
#
#   termine    – manuelle Einmal-Events (Arzt, Frist, Geburtstag)
#   routinen   – Wiederholungs-Regeln (Geige jeden Di, Miete am 1.)
#   erlebt     – auto-captured aus dem Graph-Extraktor (Spiegelung
#                aller geschah-am-Edges → eine "war da was?"-Übersicht)
#
# Geplant: ernaehrung, schlaf, training – jeder Tracker bekommt einen
# eigenen Layer mit eigenem Tool, Daten kollidieren nicht.
#
# Cross-Reference zum Graph:
#
#   Graph: Geige ─[geschah-am]─► 2026-05-26
#   Kalender (routinen): Geige | RRULE=FREQ=WEEKLY;BYDAY=TU | 18:00
#
#   "wie war Geige letztes Mal?" → Kalender liefert "letzter Di = 26.5.",
#   Graph-Aktivierung um den 26.5. liefert verknüpfte Konzepte
#   (Stimmung, was danach kam). Verbindung läuft über das ISO-Datum
#   als gemeinsamer Schlüssel - keine harte Referenz, beide Systeme
#   bleiben unabhängig wartbar.

import json
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil.rrule import rrulestr

import state  # Logging in den UI-Terminal-Stream

# ── Pfad & Locking ─────────────────────────────────────────────────────
CAL_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_calendar.json"
_lock    = threading.Lock()

# ── Default-Layer beim ersten Boot ────────────────────────────────────
# Farben sind als Hinweis für späteres UI gedacht (Konzept-Browser,
# Wochen-Widget). Backend selbst rendert keine Farbe.
_DEFAULT_LAYERS = {
    "termine": {
        "label":           "Termine",
        "color":           "#ff5500",
        "default_visible": True,
        "entries":         {},   # {date_iso: [{label, time?, ...}, ...]}
        "routines":        [],   # in dieser Layer-Klasse ungenutzt
    },
    "routinen": {
        "label":           "Routinen",
        "color":           "#5577ff",
        "default_visible": True,
        "entries":         {},   # Einmal-Ausnahmen sind hier auch erlaubt
        "routines":        [],   # [{label, rrule, time?, ...}]
    },
    "erlebt": {
        "label":           "Erlebt (auto)",
        "color":           "#888888",
        "default_visible": False,  # default ausgeblendet, sonst noisy
        "entries":         {},
        "routines":        [],
    },
}

_WEEKDAYS_SHORT_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_WEEKDAYS_FULL_DE  = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                      "Freitag", "Samstag", "Sonntag"]


# ── Persistenz ─────────────────────────────────────────────────────────
def _load_raw() -> dict:
    if not CAL_PATH.exists():
        return {"version": 1, "layers": {k: dict(v) for k, v in _DEFAULT_LAYERS.items()}}
    with CAL_PATH.open() as f:
        return json.load(f)


def _save_raw(data: dict) -> None:
    CAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CAL_PATH.open("w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_init() -> None:
    """
    Stellt sicher dass die Kalender-Datei existiert und alle Default-
    Layer da sind. Idempotent - kann beim Boot mehrfach gerufen werden.
    Migrations-sicher: fehlende Default-Layer werden ergänzt, vorhandene
    benutzerdefinierte Layer bleiben unberührt.
    """
    with _lock:
        if not CAL_PATH.exists():
            _save_raw({"version": 1, "layers": {k: dict(v) for k, v in _DEFAULT_LAYERS.items()}})
            return
        data = _load_raw()
        layers = data.setdefault("layers", {})
        changed = False
        for name, default in _DEFAULT_LAYERS.items():
            if name not in layers:
                layers[name] = dict(default)
                changed = True
        if changed:
            _save_raw(data)


# ── Schreib-API ────────────────────────────────────────────────────────
def add_entry(layer: str, day: str, label: str,
              time: str | None = None, **extras) -> bool:
    """
    Trägt einen Einmal-Eintrag in einen Layer ein.

      layer  – Layer-Name, muss existieren (sonst False)
      day    – YYYY-MM-DD
      label  – kurzer Titel
      time   – HH:MM (optional, sonst ganztags)
      extras – beliebige Zusatzfelder (tags, location, ...)
    """
    with _lock:
        data = _load_raw()
        if layer not in data.get("layers", {}):
            state.push_log(f"[calendar] unbekannter Layer: {layer}")
            return False
        entries = data["layers"][layer].setdefault("entries", {})
        entry: dict = {"label": label}
        if time:
            entry["time"] = time
        entry.update(extras)
        entries.setdefault(day, []).append(entry)
        _save_raw(data)
        return True


def add_routine(layer: str, label: str, rrule_str: str,
                time: str | None = None, **extras) -> bool:
    """
    Trägt eine Wiederholungs-Regel ein (iCal RRULE-Syntax).

    Beispiele:
      FREQ=WEEKLY;BYDAY=TU                  – jeden Dienstag
      FREQ=WEEKLY;BYDAY=MO,WE,FR            – Mo/Mi/Fr
      FREQ=MONTHLY;BYMONTHDAY=1             – jeder 1. im Monat
      FREQ=MONTHLY;BYDAY=2TU                – zweiter Dienstag im Monat
      FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25  – jedes Jahr 25.12.

    Validierung läuft via dateutil; ungültige Regeln werden abgewiesen
    und geloggt, damit nichts kaputtes persistiert wird.
    """
    try:
        # Dummy DTSTART zum Parsen – wird beim Lesen pro Range neu gesetzt.
        rrulestr(
            f"DTSTART:{date.today().strftime('%Y%m%dT000000')}\n"
            f"RRULE:{rrule_str}"
        )
    except Exception as e:
        state.push_log(f"[calendar] ungültige rrule {rrule_str!r}: {e}")
        return False

    with _lock:
        data = _load_raw()
        if layer not in data.get("layers", {}):
            state.push_log(f"[calendar] unbekannter Layer: {layer}")
            return False
        routine: dict = {"label": label, "rrule": rrule_str}
        if time:
            routine["time"] = time
        routine.update(extras)
        data["layers"][layer].setdefault("routines", []).append(routine)
        _save_raw(data)
        return True


def add_layer(name: str, label: str, color: str = "#999999",
              default_visible: bool = True) -> bool:
    """
    Legt einen neuen Layer an (z.B. 'ernaehrung', 'training'). Idempotent:
    wenn er schon existiert, wird er nicht überschrieben.
    """
    with _lock:
        data = _load_raw()
        layers = data.setdefault("layers", {})
        if name in layers:
            return False
        layers[name] = {
            "label":           label,
            "color":           color,
            "default_visible": default_visible,
            "entries":         {},
            "routines":        [],
        }
        _save_raw(data)
        return True


# ── Auto-Capture aus dem Graph ─────────────────────────────────────────
def auto_capture(concept: str, day_iso: str) -> None:
    """
    Wird vom Graph-Extraktor aufgerufen wenn er einen geschah-am-Edge
    extrahiert hat. Spiegelt das Konzept in den `erlebt`-Layer für den
    Tag. Dedup: wenn derselbe Concept+Day schon drin ist, nicht
    nochmal anhängen - wir wollen nicht "Geige" dreimal sehen weil es
    in drei Turns erwähnt wurde.

    Stilles No-Op wenn der Layer nicht existiert (z.B. weil jemand ihn
    explizit gelöscht hat) - kein Fehler nach oben, der Graph-Pfad ist
    der Hauptpfad und darf an Auto-Capture nicht hängen.
    """
    with _lock:
        try:
            data = _load_raw()
        except Exception:
            return
        layer = data.get("layers", {}).get("erlebt")
        if not layer:
            return
        entries = layer.setdefault("entries", {})
        day_entries = entries.setdefault(day_iso, [])
        if any(e.get("label") == concept for e in day_entries):
            return
        day_entries.append({"label": concept})
        try:
            _save_raw(data)
        except Exception:
            pass


# ── Lese-API ───────────────────────────────────────────────────────────
def entries_in_range(start: date, end: date,
                     layers: list[str] | None = None) -> dict:
    """
    Liefert alle Einträge im Zeitraum [start, end] (inklusive), nach
    Datum gruppiert. Wenn `layers` angegeben: nur diese Layer.

    Routinen werden via rrule expandiert - jedes Vorkommen in dem
    Range wird als eigener Eintrag zurückgegeben.

    Return-Form:
      {
        "2026-05-26": [
          {"layer": "routinen", "label": "Geige", "time": "18:00"},
          ...
        ],
        ...
      }
    sortiert nach Datum, innerhalb Tag nach Zeit.
    """
    data = _load_raw()
    target = layers if layers else list(data.get("layers", {}).keys())
    out: dict[str, list[dict]] = {}

    for layer_name in target:
        layer = data["layers"].get(layer_name)
        if not layer:
            continue

        # 1. Einmal-Einträge
        for day_iso, day_entries in layer.get("entries", {}).items():
            try:
                d = date.fromisoformat(day_iso)
            except ValueError:
                continue
            if start <= d <= end:
                for e in day_entries:
                    out.setdefault(day_iso, []).append({
                        "layer": layer_name,
                        **e,
                    })

        # 2. Routinen expandieren
        for r in layer.get("routines", []):
            try:
                rule = rrulestr(
                    f"DTSTART:{datetime.combine(start, datetime.min.time()).strftime('%Y%m%dT%H%M%S')}\n"
                    f"RRULE:{r['rrule']}"
                )
                until = datetime.combine(end, datetime.max.time())
                for occ in rule:
                    if occ > until:
                        break
                    day_iso = occ.date().isoformat()
                    entry: dict = {"layer": layer_name, "label": r["label"]}
                    if r.get("time"):
                        entry["time"] = r["time"]
                    out.setdefault(day_iso, []).append(entry)
            except Exception as e:
                state.push_log(
                    f"[calendar] rrule expand fail layer={layer_name} "
                    f"label={r.get('label')!r}: {e}"
                )

    for day_iso in out:
        out[day_iso].sort(key=lambda e: e.get("time", "00:00"))

    return dict(sorted(out.items()))


def week_view(reference: date | None = None,
              only_default_visible: bool = True) -> dict:
    """
    Liefert die laufende Woche (Mo-So) um `reference` herum.

    only_default_visible=True (Default) zeigt nur Layer mit
    default_visible=True - sonst würde der `erlebt`-Auto-Layer den
    Jetzt-Block bei jeder Antwort fluten. Wenn der User explizit
    nach Erlebtem fragt, ruft die KI das read_calendar-Tool.
    """
    if reference is None:
        reference = date.today()
    monday = reference - timedelta(days=reference.weekday())
    sunday = monday + timedelta(days=6)
    layers = None
    if only_default_visible:
        data = _load_raw()
        layers = [
            name for name, lyr in data.get("layers", {}).items()
            if lyr.get("default_visible", True)
        ]
    return {
        "start": monday.isoformat(),
        "end":   sunday.isoformat(),
        "days":  entries_in_range(monday, sunday, layers=layers),
    }


# ── Range-Auflösung & Tool-Renderer ────────────────────────────────────
#
# Designentscheidung (2026-06): der Kalender wird NICHT mehr in den Prompt
# geklebt. Die KI greift ihn ausschließlich über das read_calendar-Tool ab
# - für JEDEN Zeitraum (Woche, Monat, Quartal, Vergangenheit). Grund: Glue
# skaliert nicht ("was steht in 3 Monaten an?" lässt sich nicht mitkleben)
# und erzeugt einen faulen Halb-Weg, auf dem das 14B-Modell aus dem
# geklebten Block antwortet statt das Tool zu rufen → unnötige Rückfragen.
#
# Die Datums-Arithmetik macht hier Python, NICHT das Modell. Ein 14B kann
# eine Frage gut in einen Bucket KLASSIFIZIEREN ("den Monat" → dieser_monat),
# aber schlecht ISO-Grenzen RECHNEN. Also: Modell wählt den Bucket, resolve_range
# liefert die exakten Daten. Beliebige Sonderfälle ("ab dem 15." / weit in der
# Zukunft) gehen weiter über explizite start/end-Daten.

# Erlaubte Buckets für das `zeitraum`-Arg von read_calendar. Reihenfolge =
# Reihenfolge im Tool-Enum. Werte sind bewusst sprechend, damit das Modell
# sie aus der User-Frage ableiten kann.
RANGE_BUCKETS = [
    "heute", "morgen", "gestern",
    "diese_woche", "naechste_woche", "diese_und_naechste_woche", "letzte_woche",
    "dieser_monat", "naechster_monat", "letzter_monat",
    "naechste_7_tage", "naechste_30_tage", "naechste_90_tage",
    "letzte_7_tage", "letzte_30_tage",
]


def _month_last_day(d: date) -> date:
    """Letzter Tag des Monats, in dem `d` liegt (über 1. des Folgemonats - 1)."""
    if d.month == 12:
        first_next = date(d.year + 1, 1, 1)
    else:
        first_next = date(d.year, d.month + 1, 1)
    return first_next - timedelta(days=1)


def resolve_range(zeitraum: str, reference: date | None = None
                  ) -> tuple[date, date] | None:
    """
    Übersetzt einen relativen Bucket-Namen in ein konkretes (start, end)-Paar
    (beide inklusive). Gibt None zurück wenn der Bucket unbekannt ist - dann
    soll der Aufrufer auf explizite start/end-Daten zurückfallen.

    "Aktuelle"-Buckets (diese_woche, dieser_monat) starten bei HEUTE, nicht
    am Perioden-Anfang: wer "was steht diese Woche an?" fragt, will keine
    bereits vergangenen Tage. Vergangenes holt man gezielt über start/end.
    """
    today = reference or date.today()
    if zeitraum == "heute":
        return today, today
    if zeitraum == "morgen":
        t = today + timedelta(days=1)
        return t, t
    if zeitraum == "gestern":
        t = today - timedelta(days=1)
        return t, t
    if zeitraum == "diese_woche":
        sunday = today + timedelta(days=6 - today.weekday())
        return today, sunday
    if zeitraum == "naechste_woche":
        next_monday = today + timedelta(days=7 - today.weekday())
        return next_monday, next_monday + timedelta(days=6)
    if zeitraum == "diese_und_naechste_woche":
        # heute bis Sonntag der NÄCHSTEN Woche - die häufigste Frage
        # ("steht diese oder nächste Woche was an?") in einem Call.
        return today, today + timedelta(days=13 - today.weekday())
    if zeitraum == "letzte_woche":
        prev_monday = today - timedelta(days=today.weekday() + 7)
        return prev_monday, prev_monday + timedelta(days=6)
    if zeitraum == "dieser_monat":
        return today, _month_last_day(today)
    if zeitraum == "naechster_monat":
        first_next = _month_last_day(today) + timedelta(days=1)
        return first_next, _month_last_day(first_next)
    if zeitraum == "letzter_monat":
        last_prev  = date(today.year, today.month, 1) - timedelta(days=1)
        first_prev = date(last_prev.year, last_prev.month, 1)
        return first_prev, last_prev
    if zeitraum == "naechste_7_tage":
        return today, today + timedelta(days=6)
    if zeitraum == "naechste_30_tage":
        return today, today + timedelta(days=29)
    if zeitraum == "naechste_90_tage":
        return today, today + timedelta(days=89)
    if zeitraum == "letzte_7_tage":
        return today - timedelta(days=6), today
    if zeitraum == "letzte_30_tage":
        return today - timedelta(days=29), today
    return None


def render_range_for_tool(start: date, end: date,
                          layers: list[str] | None = None,
                          suche: str | None = None) -> str:
    """
    Formatiert die Einträge in [start, end] als Tool-Antwort für die KI.

    Kernpunkt gegen die Wochentag-Halluzination: jeder Tag kommt MIT
    ausgeschriebenem Wochentag ("Dienstag, 09.06.2026: …"). Vorher gab das
    Tool nackte ISO-Daten zurück und das Modell rechnete den Wochentag selbst
    aus - und verrechnete sich regelmäßig ("Montag" statt "Dienstag"). Steht
    der Wochentag fertig da, muss das Modell nur noch abschreiben.

    `suche`: optionaler Label-Substring-Filter (case-insensitive). Bei Fragen
    nach EINER Aktivität ("wann hab ich Fahrschule?") gibt das Tool damit nur
    die passenden Zeilen zurück, statt der ganzen Monatswand. Grund: schwache
    Modelle (qwen3-Familie) scheitern daran, eine lange Liste selbst nach
    einem Begriff zu durchsuchen - sie sagen dann "keine gefunden" obwohl der
    Eintrag dasteht, kotzen die Rohliste aus oder übersehen Treffer (z.B. den
    Donnerstag). Filtern ist deterministische Arbeit → macht Python, nicht das
    Modell. Selbes Prinzip wie resolve_range fürs Datums-Rechnen.

    Leerer Zeitraum → klare Ansage, damit die KI "nichts geplant" von
    "weiß ich nicht" unterscheiden kann.
    """
    days = entries_in_range(start, end, layers=layers)
    # Label-Filter in Python anwenden, BEVOR gerendert wird.
    if suche:
        needle = suche.casefold()
        days = {
            day_iso: matches
            for day_iso, entries in days.items()
            if (matches := [e for e in entries
                            if needle in e.get("label", "").casefold()])
        }
    span = (f"Kalender {start.strftime('%d.%m.%Y')} bis "
            f"{end.strftime('%d.%m.%Y')}")
    head = f"{span} (gefiltert nach {suche!r}):" if suche else f"{span}:"
    if not days:
        leer = (f"Keine Einträge mit {suche!r} in diesem Zeitraum."
                if suche else "Keine Einträge in diesem Zeitraum.")
        return head + "\n" + leer
    lines = [head]
    for day_iso, entries in days.items():
        d = date.fromisoformat(day_iso)
        wd = _WEEKDAYS_FULL_DE[d.weekday()]
        lines.append(f"{wd}, {d.strftime('%d.%m.%Y')}:")
        for e in entries:
            t = f"{e['time']} " if e.get("time") else ""
            lines.append(f"  [{e['layer']}] {t}{e['label']}")
    return "\n".join(lines)
