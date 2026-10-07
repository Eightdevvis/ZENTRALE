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
import kalender_bearbeiten  # type: ignore  – Wiederholung, „nur dieser Tag", Spannen
import kalender_sicherung  # type: ignore  – Schutzsperren (Massenlöschung, Rückfall)
import lists        # type: ignore  – dynamische Listen-Registry (Todo/Sammel-Listen)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('kalender', __name__)


@bp.errorhandler(kalender_sicherung.KalenderGesperrt)
def _gesperrt(e):
    """Eine Schutzsperre des Kalenders (Massenlöschung, Rückfall auf den alten
    Speicher) ist kein Absturz, sondern eine Ansage: 409 mit dem Grund, damit
    die TUI ihn zeigen kann. Vorher kam ein nackter 500er."""
    state.push_log(f"KALENDER ✗  gesperrt: {e}")
    return jsonify({"error": str(e), "gesperrt": True}), 409


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
    if body.get('freq'):
        # calcurse „r": Typ (t/w/m/j), alle wie viele, Ende, ab dem gewählten Tag.
        ok = kalender_bearbeiten.routine_neu(
            (body.get('layer') or 'routinen'), label, body.get('seit') or '',
            body.get('freq'), body.get('intervall') or 1, body.get('bis') or None,
            body.get('wochentage') or None, body.get('time') or None,
            body.get('ende') or None, body.get('ort') or None)
        return (jsonify({"ok": True}) if ok
                else (jsonify({"error": "wiederholung abgelehnt"}), 400))
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


# ── Bearbeiten wie calcurse / Handy-Kalender (seit 07.10.2026) ─────────
# Dünne Adapter auf core/kalender_bearbeiten.py; die TUI-Ansichten A/B/C
# benutzen sie alle gleich (ein Kalender, mehrere Ansichten).
def _antwort(ok, fehler):
    return jsonify({"ok": True}) if ok else (jsonify({"error": fehler}), 400)


@bp.route('/api/calendar/routine', methods=['PUT'])
def api_calendar_edit_routine():
    """ALLE Vorkommen einer Routine ändern. Body: {layer, label, day, time?,
    new:{label?, time?, ende?, ort?, wiederholung?:{freq, intervall, bis,
    wochentage}}}. day/time bestimmen, WELCHE Routine gemeint ist."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.routine_bearbeiten(
        b.get('layer') or 'routinen', b.get('label') or '', b.get('day') or '',
        b.get('time') or None, b.get('new') or {}), "routine nicht gefunden/abgelehnt")


@bp.route('/api/calendar/routine/abweichung', methods=['POST'])
def api_calendar_routine_abweichung():
    """NUR dieses Vorkommen ändern. Body: {layer, label, day, time?,
    new:{tag?, time?, ende?, label?, ort?}}."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.routine_abweichung(
        b.get('layer') or 'routinen', b.get('label') or '', b.get('day') or '',
        b.get('time') or None, b.get('new') or {}), "vorkommen nicht gefunden/abgelehnt")


@bp.route('/api/calendar/spanne', methods=['POST'])
def api_calendar_spanne_neu():
    """Mehrtägig anlegen. Body: {layer?, von, bis, label, start_zeit?,
    end_zeit?, tageszeit?:[von, bis], ort?}."""
    b = request.get_json(silent=True) or {}
    tz = b.get('tageszeit')
    return _antwort(kalender_bearbeiten.spanne_neu(
        b.get('layer') or 'termine', b.get('von') or '', b.get('bis') or '',
        b.get('label') or '', b.get('start_zeit') or None, b.get('end_zeit') or None,
        tuple(tz) if isinstance(tz, list) and len(tz) == 2 else None,
        b.get('ort') or None), "spanne abgelehnt")


@bp.route('/api/calendar/spanne', methods=['PUT'])
def api_calendar_spanne_aendern():
    """Alle Tage einer Spanne. Body: {layer?, von, label, new:{label?, ort?,
    verschieben?, bis?}}."""
    b = request.get_json(silent=True) or {}
    n = b.get('new') or {}
    try:
        schub = int(n.get('verschieben') or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "verschieben muss eine Zahl sein"}), 400
    return _antwort(kalender_bearbeiten.spanne_aendern(
        b.get('layer') or 'termine', b.get('von') or '', b.get('label') or '',
        n.get('label') or None, schub, n.get('bis') or None, n.get('ort')),
        "spanne nicht gefunden/abgelehnt")


@bp.route('/api/calendar/spanne/tag', methods=['POST'])
def api_calendar_spanne_tag():
    """Uhrzeit EINES Tages einer Spanne. Body: {layer?, von, label, day,
    time?, ende?} — leer = an dem Tag ganztägig."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.spanne_tag(
        b.get('layer') or 'termine', b.get('von') or '', b.get('label') or '',
        b.get('day') or '', b.get('time') or None, b.get('ende') or None),
        "spannen-tag nicht gefunden")


@bp.route('/api/calendar/konflikte', methods=['POST'])
def api_calendar_konflikte():
    """VOR dem Speichern prüfen, ob ein geplanter Termin kollidiert (gleiche
    Logik wie die KI-Rückfrage). Body: {layer?, day, label, time?, ende?} —
    ohne Ende kein Intervall, also keine Überlappung (find_collisions).
    Antwort {konflikte:[zeile, …]} — schreibt nichts."""
    b = request.get_json(silent=True) or {}
    try:
        k = kalender.conflicts_for_proposed(b.get('layer') or 'termine',
                                            b.get('day') or '', b.get('label') or '',
                                            time=b.get('time') or None,
                                            ende=b.get('ende') or None)
    except Exception as e:
        return jsonify({"konflikte": [], "error": str(e)})
    return jsonify({"konflikte": k})


@bp.route('/api/calendar/eintrag', methods=['DELETE'])
def api_calendar_eintrag_loeschen():
    """GENAU einen Einmal-Termin (bzw. eine Spanne an ihrem Start-Tag)
    löschen — exakter Titel, bei Gleichnamigen die Uhrzeit. Body: {layer?,
    day, label, time?}. Anders als DELETE /api/calendar/entry kein
    Teilstring-Treffer."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.eintrag_loeschen(
        b.get('layer') or 'termine', b.get('day') or '', b.get('label') or '',
        b.get('time') or None), "termin nicht gefunden")


@bp.route('/api/calendar/eintrag', methods=['PUT'])
def api_calendar_eintrag_aendern():
    """Einen Einmal-Termin ändern, andere Felder bleiben. Body: {layer?, day,
    label, time?, new:{day?, label?, time?, ende?, ort?}}."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.eintrag_aendern(
        b.get('layer') or 'termine', b.get('day') or '', b.get('label') or '',
        b.get('time') or None, b.get('new') or {}), "termin nicht gefunden/abgelehnt")
