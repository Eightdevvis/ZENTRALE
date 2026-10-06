# ui/routen/kalender.py
#
# Kalender: Ansicht, Einträge, Zeitspannen, Routinen.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from datetime import date, datetime
from flask import Blueprint, jsonify, request

import cycle        # type: ignore  – Zyklus/PMS-Vorhersage aus dem »periode«-Graphen
import kalender     # type: ignore  – Kalender-Layer (Woche/Monat, data/ai_calendar.json)
import lists        # type: ignore  – dynamische Listen-Registry (Todo/Sammel-Listen)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('kalender', __name__)


@bp.route('/api/calendar')
def api_calendar():
    """
    Kalender-Daten für die Mitte/Canvas: laufende Woche ODER
    Monat um `ref`, fertig nach Tag gruppiert. Front-agnostisch — TUI, monolith
    und laptop rufen denselben Endpoint und zeichnen nur (wie /api/map/*). NICHT
    KI-gegatet: der Kalender ist hier reine Anzeige, kein KI-Tool-Pfad, läuft
    also auch ohne lokale KI. Die Datums-Arithmetik (Woche Mo-So /
    Monatsgitter) macht Python in core/kalender.py, die Front klassifiziert nur
    `view` und blättert über `ref` — dieselbe Linie wie resolve_range.

    Query: view = 'week' (Default) | 'month';  ref = YYYY-MM-DD (Default heute).
    Antwort: {view, ref, today, label, start, end, days:{iso:[entries]}, alarms,
             (month: first/last/month nur bei view=month)}.
    """
    a = request.args
    view = (a.get('view') or 'week').lower()
    ref_s = a.get('ref')
    try:
        ref = datetime.strptime(ref_s, '%Y-%m-%d').date() if ref_s else date.today()
    except (TypeError, ValueError):
        return jsonify({"error": "ungültiges ref-datum (YYYY-MM-DD)"}), 400

    if view == 'month':
        out = kalender.month_view(ref)
    else:
        view = 'week'                       # alles != month → Woche (robust)
        out = kalender.week_view(ref)       # immer Mo-So
        start = date.fromisoformat(out['start'])
        end = date.fromisoformat(out['end'])
        out['label'] = f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')}"

    # Kalender-Sidebar-Liste (die flache »week«-Liste). Wochenunabhängiger
    # Vorrat → in BEIDER Ansicht gleich; Form {lid, items:[{id,text,done,
    # linked}]}. Nur Anzeige/Bearbeitung über die vorhandenen /api/lists-
    # Endpoints; defensiv, nie crashen.
    try:
        out['weekplan'] = lists.week_items()
    except Exception:
        out['weekplan'] = {"lid": None, "items": []}

    out['view'] = view
    out['ref'] = ref.isoformat()
    out['today'] = date.today().isoformat()
    # Zyklus-Marker für die sichtbaren Tage (abgeleitet aus dem »periode«-
    # Graphen, KEIN Kalender-Layer und nichts Gespeichertes): {iso: 'pms'|
    # 'next'}. Die Front tönt die Tage nur ein. Defensiv: nie crashen.
    try:
        c_start = date.fromisoformat(out['start'])
        c_end = date.fromisoformat(out['end'])
        out['cycle'] = cycle.day_marks(c_start, c_end)
    except Exception:
        out['cycle'] = {}
    # Offene Kalender-Alarme mitschicken (gleiche Quelle wie die Canvas-Ecke),
    # damit die Front pro Tag/Header dezent warnen kann. Defensiv: nie crashen.
    try:
        out['alarms'] = state.get_alarms() or []
    except Exception:
        out['alarms'] = []
    return jsonify(out)


@bp.route('/api/calendar/entry', methods=['POST'])
def api_calendar_add_entry():
    """
    Einen Einmal-Termin direkt aus der Kalender-Mitte anlegen (TUI/Browser).
    NICHT KI-gegatet: das ist eine DIREKTE Nutzeraktion aus der UI (wie
    `/api/log` beim Graph-Werkzeug), kein KI-Schreibpfad — das Permission-Gate
    der KI bleibt davon unberührt. Schreibt über `core/kalender.py:add_entry`.

    Body (JSON): day=YYYY-MM-DD (Pflicht), label (Pflicht), time=HH:MM (opt),
    ende=HH:MM (opt), ort (opt), layer (Default 'termine'). Routinen
    (Wiederholungen) laufen weiter über die KI — hier bewusst nur Einmal-Termine.

    Antwort: {ok, conflicts:[…]} — die Konflikt-Zeilen (Reise/Kollision/Knapp)
    werden VOR dem Schreiben gesammelt und nur als HINWEIS zurückgegeben (kein
    Block; gleiche Rechnung wie das KI-Gate via conflicts_for_proposed).
    """
    body = request.get_json(silent=True) or {}
    label = (body.get('label') or '').strip()
    day = (body.get('day') or '').strip()
    if not label:
        return jsonify({"error": "label fehlt"}), 400
    try:
        date.fromisoformat(day)
    except (TypeError, ValueError):
        return jsonify({"error": "day muss YYYY-MM-DD sein"}), 400
    time = (body.get('time') or '').strip() or None
    layer = (body.get('layer') or 'termine').strip() or 'termine'
    extras = {}
    for k in ('ende', 'ort'):
        v = (body.get(k) or '').strip()
        if v:
            extras[k] = v
    # Mehrtägiger (ganztägiger) Termin: `bis`-Datum gesetzt → Spanne statt
    # Einmal-Termin. Kein Konflikt-Check (ganztägig, kein Zeit-Slot).
    bis = (body.get('bis') or '').strip()
    if bis:
        try:
            date.fromisoformat(bis)
        except (TypeError, ValueError):
            return jsonify({"error": "bis muss YYYY-MM-DD sein"}), 400
        ok = kalender.add_span(layer, day, bis, label, **extras)
        if not ok:
            return jsonify({"error": "spanne abgelehnt (bis<von? layer?)"}), 400
        return jsonify({"ok": True, "conflicts": [], "spanning": True})
    conflicts = kalender.conflicts_for_proposed(layer, day, label, time=time)
    ok = kalender.add_entry(layer, day, label, time=time, **extras)
    if not ok:
        return jsonify({"error": "eintrag abgelehnt (unbekannter layer?)"}), 400
    return jsonify({"ok": True, "conflicts": conflicts})


@bp.route('/api/calendar/entry', methods=['DELETE'])
def api_calendar_delete_entry():
    """
    Einmal-Termin(e) an einem Tag löschen — Label-Match wie das KI-Tool
    (case-insensitiv, exakt oder Teilstring). Wirkt NUR auf Einmal-Einträge,
    nicht auf Routinen. Body: {day, label, layer?}. Antwort: {deleted:n}.
    """
    body = request.get_json(silent=True) or {}
    day = (body.get('day') or '').strip()
    label = (body.get('label') or '').strip()
    if not day or not label:
        return jsonify({"error": "day und label nötig"}), 400
    n = kalender.delete_entry(day, label, layer=(body.get('layer') or None))
    return jsonify({"deleted": n})


@bp.route('/api/calendar/entry', methods=['PUT'])
def api_calendar_edit_entry():
    """
    Einen bestehenden Einmal-Termin ÄNDERN: löscht den alten (`day`,`label`,
    `layer?`) und legt den neuen an. Body:
      {day, label, layer?, new:{day, label, time?, ende?, ort?}}
    `new.day`/`new.label` Pflicht. Antwort {ok, conflicts:[…]} wie beim Anlegen.
    Bewusst delete+add (kein In-Place-Patch): Einmal-Termine sind klein und der
    Match läuft über Label - so bleibt es dieselbe Logik wie POST/DELETE.
    """
    body = request.get_json(silent=True) or {}
    old_day = (body.get('day') or '').strip()
    old_label = (body.get('label') or '').strip()
    layer = (body.get('layer') or 'termine').strip() or 'termine'
    new = body.get('new') or {}
    new_day = (new.get('day') or '').strip()
    new_label = (new.get('label') or '').strip()
    if not old_day or not old_label:
        return jsonify({"error": "alter day/label nötig"}), 400
    if not new_label:
        return jsonify({"error": "neuer label fehlt"}), 400
    try:
        date.fromisoformat(new_day)
    except (TypeError, ValueError):
        return jsonify({"error": "new.day muss YYYY-MM-DD sein"}), 400
    new_time = (new.get('time') or '').strip() or None
    extras = {}
    for k in ('ende', 'ort'):
        v = (new.get(k) or '').strip()
        if v:
            extras[k] = v
    kalender.delete_entry(old_day, old_label, layer=layer)
    conflicts = kalender.conflicts_for_proposed(layer, new_day, new_label, time=new_time)
    ok = kalender.add_entry(layer, new_day, new_label, time=new_time, **extras)
    if not ok:
        return jsonify({"error": "neuer eintrag abgelehnt"}), 400
    return jsonify({"ok": True, "conflicts": conflicts})


@bp.route('/api/calendar/entry/spantime', methods=['POST'])
def api_calendar_span_time():
    """
    Für EINEN Tag einer mehrtägigen Spanne eine Uhrzeit setzen/löschen (leeres
    `time` = wieder ganztägig). Die Spanne wird über `von` (Start-Tag) + `label`
    + `layer` gefunden. Body: {layer?, von, label, day, time?}. Antwort {ok}.
    """
    body = request.get_json(silent=True) or {}
    von = (body.get('von') or '').strip()
    label = (body.get('label') or '').strip()
    day = (body.get('day') or '').strip()
    layer = (body.get('layer') or 'termine').strip() or 'termine'
    time = (body.get('time') or '').strip() or None
    if not von or not label or not day:
        return jsonify({"error": "von, label, day nötig"}), 400
    ok = kalender.set_span_time(layer, von, label, day, time)
    return jsonify({"ok": bool(ok)})


@bp.route('/api/calendar/routine/skip', methods=['POST'])
def api_calendar_routine_skip():
    """
    Einen EINZELNEN Routine-Termin deaktivieren bzw. wieder aktivieren
    (reversibel, pro Vorkommen) — über core/kalender.py:set_routine_skip. NICHT
    KI-gegatet (direkte Nutzeraktion). Body: {layer, label, day, off=true, time?}.
    `off=true` deaktiviert, `off=false` aktiviert wieder. `time` grenzt bei
    gleichnamigen Routinen die richtige ein. Antwort {changed:bool}.
    """
    body = request.get_json(silent=True) or {}
    layer = (body.get('layer') or 'routinen').strip() or 'routinen'
    label = (body.get('label') or '').strip()
    day = (body.get('day') or '').strip()
    if not label or not day:
        return jsonify({"error": "label und day nötig"}), 400
    off = body.get('off', True)
    time = (body.get('time') or '').strip() or None
    changed = kalender.set_routine_skip(layer, label, day, off=bool(off), time=time)
    return jsonify({"changed": changed})


_WEEKDAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


@bp.route('/api/calendar/routine', methods=['POST'])
def api_calendar_add_routine():
    """
    Eine neue WÖCHENTLICHE Routine anlegen (ohne dass der User RRULE tippen muss).
    Body: {label, byday, time?, ende?, ort?, layer?}. `byday` = ein oder mehrere
    Wochentage als MO..SU (Liste ODER kommagetrennt). Daraus bauen wir
    `FREQ=WEEKLY;BYDAY=…`; krummere Wiederholungen (monatlich/jährlich) bleiben
    dem KI-Tool vorbehalten. NICHT KI-gegatet (direkte Nutzeraktion).
    Antwort {ok:true} bzw. 400. Default-Layer `routinen`.
    """
    body = request.get_json(silent=True) or {}
    label = (body.get('label') or '').strip()
    if not label:
        return jsonify({"error": "label fehlt"}), 400
    raw = body.get('byday')
    if isinstance(raw, list):
        cand = [str(x).strip().upper() for x in raw]
    else:
        cand = [d.strip().upper() for d in str(raw or '').split(',')]
    days = [d for d in cand if d in _WEEKDAY_CODES]
    if not days:
        return jsonify({"error": "byday (MO..SU) nötig"}), 400
    rrule = "FREQ=WEEKLY;BYDAY=" + ",".join(days)
    time = (body.get('time') or '').strip() or None
    layer = (body.get('layer') or 'routinen').strip() or 'routinen'
    extras = {}
    for k in ('ende', 'ort'):
        v = (body.get(k) or '').strip()
        if v:
            extras[k] = v
    ok = kalender.add_routine(layer, label, rrule, time=time, **extras)
    if not ok:
        return jsonify({"error": "routine abgelehnt (layer/rrule?)"}), 400
    return jsonify({"ok": True})


@bp.route('/api/calendar/routine', methods=['DELETE'])
def api_calendar_delete_routine():
    """
    Eine GANZE Routine (Wiederholungs-Regel) löschen — alle Vorkommen weg.
    Gegenstück zum einzelnen Deaktivieren (.../routine/skip). NICHT KI-gegatet
    (direkte Nutzeraktion). Body: {layer, label, day?, time?}. `day`/`time`
    treffen bei gleichnamigen Routinen nur die, die an dem Tag vorkommt (sonst
    werden Serien gleichen Namens an anderen Wochentagen mitgelöscht).
    Antwort {deleted:n}.
    """
    body = request.get_json(silent=True) or {}
    layer = (body.get('layer') or 'routinen').strip() or 'routinen'
    label = (body.get('label') or '').strip()
    if not label:
        return jsonify({"error": "label nötig"}), 400
    day = (body.get('day') or '').strip() or None
    time = (body.get('time') or '').strip() or None
    n = kalender.delete_routine(layer, label, day=day, time=time)
    return jsonify({"deleted": n})
