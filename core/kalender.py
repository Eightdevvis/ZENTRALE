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


# ── Prompt-Renderer ────────────────────────────────────────────────────
def render_week_for_prompt(reference: date | None = None) -> str:
    """
    Baut einen kompakten Block für ai._now_prompt: heute + Rest der
    laufenden Woche (bis Sonntag). Vergangene Tage werden bewusst NICHT
    gezeigt - wenn der User "was steht an" fragt, soll die KI nicht
    erst alte Termine durchgehen müssen (und stolpert dann beim Tempus).
    Vergangenes hat seinen Platz im `erlebt`-Layer und kann per
    read_calendar-Tool gezielt geholt werden.

    Pro Tag eine Zeile, leere Tage als "(leer)" - damit die KI den
    Unterschied "nichts geplant" vs. "weiß ich nicht" sieht.
    """
    if reference is None:
        reference = date.today()
    monday = reference - timedelta(days=reference.weekday())
    sunday = monday + timedelta(days=6)
    today = date.today()

    # Range = von heute (oder reference) bis Sonntag der laufenden Woche
    range_start = max(reference, today)
    if range_start > sunday:
        # reference liegt in einer kommenden Woche - dann eben die ganze
        # Woche von reference.monday bis reference.sunday
        range_start = monday
    # Nur default-sichtbare Layer (sonst flutet der auto-erlebt-Layer
    # bei jedem Turn den Prompt).
    raw = _load_raw()
    visible_layers = [
        name for name, lyr in raw.get("layers", {}).items()
        if lyr.get("default_visible", True)
    ]
    days = entries_in_range(range_start, sunday, layers=visible_layers)

    lines = ["## Heute und der Rest der Woche"]
    d = range_start
    while d <= sunday:
        iso = d.isoformat()
        wd = _WEEKDAYS_SHORT_DE[d.weekday()]
        marker = " (heute)" if d == today else ""
        if iso in days and days[iso]:
            parts = []
            for e in days[iso]:
                t = f"{e['time']} " if e.get("time") else ""
                parts.append(f"{t}{e['label']}")
            lines.append(f"{wd} {d.day}.{d.month}.{marker} — " + ", ".join(parts))
        else:
            lines.append(f"{wd} {d.day}.{d.month}.{marker} — (leer)")
        d += timedelta(days=1)
    lines.append("")
    lines.append(
        "Frühere Tage stehen nicht hier - wenn der User danach fragt, "
        "ruf das read_calendar-Tool mit Vergangenheits-Range."
    )
    return "\n".join(lines)
