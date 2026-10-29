# ui/routen/kalender.py
#
# Kalender: Ansicht, Einträge, Zeitspannen, Routinen.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from datetime import date, datetime
from flask import Blueprint, jsonify, request

import calendar_colours  # type: ignore  – colour key/slot per entry (one rule for all fronts)
import cycle        # type: ignore  – Zyklus/PMS-Vorhersage aus dem »periode«-Graphen
import kalender     # type: ignore  – Kalender-Layer (Woche/Monat, data/ai_calendar.json)
import kalender_kennung  # type: ignore  – Fehler-Codes (KalenderAbgelehnt)
import kalender_bearbeiten  # type: ignore  – Wiederholung, „nur dieser Tag", Spannen
import kalender_kategorie  # type: ignore  – Gruppen-Katalog (CATEGORIES)
import kalender_quelle  # type: ignore  – Titel live aus Liste/Projekt
import kalender_rhythmus  # type: ignore  – Motive der Phasen (Tagesrhythmus)
import kalender_sicherung  # type: ignore  – Schutzsperren (Massenlöschung, Rückfall)
import kalender_speicher  # type: ignore  – calendar paths (colour table)
import kalender_sync_zustand  # type: ignore  – Stand des Google-Syncs
import lists        # type: ignore  – dynamische Listen-Registry (Todo/Sammel-Listen)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import uhr  # die eine Uhr (core/uhr.py)

bp = Blueprint('kalender', __name__)


@bp.errorhandler(kalender_kennung.KalenderAbgelehnt)
def _abgelehnt(e):
    """Abgelehnt statt still korrigiert (seit 09.10.2026): 400 mit festem
    Code und lesbarem Grund — die TUI zeigt den Grund an."""
    return jsonify({"error": e.grund, "code": e.code}), 400


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
        ref = datetime.strptime(ref_s, '%Y-%m-%d').date() if ref_s else uhr.heute()
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
    out['today'] = uhr.heute().isoformat()
    # Zyklus-Marker für die sichtbaren Tage (abgeleitet aus dem »periode«-
    # Graphen, KEIN Kalender-Layer und nichts Gespeichertes): {iso: 'pms'|
    # 'next'}. Die Front tönt die Tage nur ein. Nie crashen — aber auch nie
    # stumm: ohne Vorhersage steht der Grund als {"fehler": …} drin, ein
    # Absturz der Rechnung landet zusätzlich im Log (gefahrzonen.md).
    try:
        c_start = date.fromisoformat(out['start'])
        c_end = date.fromisoformat(out['end'])
        out['cycle'] = cycle.kalender_marken(c_start, c_end)
    except Exception as e:
        state.push_log(f"ZYKLUS ✗  Vorhersage fehlgeschlagen: {type(e).__name__}: {e}")
        out['cycle'] = {"fehler": f"Vorhersage fehlgeschlagen ({type(e).__name__})"}
    # Offene Kalender-Alarme mitschicken (gleiche Quelle wie die Canvas-Ecke),
    # damit die Front pro Tag/Header dezent warnen kann. Defensiv: nie crashen.
    try:
        out['alarms'] = state.get_alarms() or []
    except Exception:
        out['alarms'] = []
    # Stand des Google-Syncs (16.10.2026): die Ansichten zeigen bei einem
    # Problem eine Warnzeile, ohne Problem höchstens leise „google ✓ 16:31".
    try:
        out['sync'] = kalender_sync_zustand.bewerten()
    except Exception:
        out['sync'] = {"bekannt": False, "problem": False}
    # Jede Zeile nennt Ebene (`layer`) und Gruppe (`kategorie`, „keine" wenn
    # leer); Phasen des Tagesrhythmus dazu `motiv` (aus dem Kern).
    for liste in (out.get('days') or {}).values():
        for e in liste:
            e.setdefault('kategorie', 'keine')
    # Colour of every entry (core/calendar_colours.py): `colour` = {key, slot,
    # group_key, group_slot}; new recurring courses get their fixed slot in
    # the synced table here. The fronts only draw t<slot>. Never crash the view.
    try:
        calendar_colours.annotate_view(out, kalender_speicher.pfade(kalender.CAL_PATH)["colours"])
    except Exception as e:
        state.push_log(f"KALENDER ✗  colours: {type(e).__name__}: {e}")
    return jsonify(out)


@bp.route('/api/calendar/sync')
def api_calendar_sync():
    """Stand des Google-Abgleichs (scripts/kalender_sync.py schreibt ihn nach
    jedem Lauf): {bekannt, letzter_versuch, letzter_erfolg, ok, art, fehler,
    seit, exit, alt, problem, hinweis, kurz}. `bekannt` false: auf diesem
    Rechner lief nie ein Sync. `alt`: seit > ALT_MIN Minuten kein Erfolg
    oder kein Versuch. Doku: memory/werkzeuge/kalender_sync_zustand.md."""
    return jsonify(kalender_sync_zustand.bewerten())


def _alle_kennungen() -> set:
    return {e.get("kennung") for e in kalender_kennung.alle_eintraege()}


def _neue_kennung(vorher: set):
    """Die Kennung des gerade Angelegten (für fremde Anbindungen: nachlesen
    per Kennung; Wunsch von ASSISTANT, 11.10.2026). None, wenn nicht eindeutig."""
    neu = _alle_kennungen() - vorher
    return next(iter(neu)) if len(neu) == 1 else None


def _typ_extras(body: dict, extras: dict) -> None:
    """Termintyp deadline (20.10.2026): `typ` ("deadline"|"normal") und
    `vorwarnung` (Minuten oder „3d") weiterreichen — geprüft wird im Kern
    (kalender_deadline; Ablehnung 400 mit code)."""
    if body.get('typ'):
        extras['typ'] = body['typ']
    if body.get('vorwarnung') is not None:
        extras['vorwarnung'] = body['vorwarnung']
    if body.get('soll_abstand') not in (None, ''):          # Soll-Zeit (24.10.2026)
        extras['soll_abstand'] = body['soll_abstand']


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
    if not label and not body.get('quelle'):
        return jsonify({"error": "label fehlt"}), 400
    try:
        date.fromisoformat(day)
    except (TypeError, ValueError):
        return jsonify({"error": "day muss YYYY-MM-DD sein"}), 400
    time = (body.get('time') or '').strip() or None
    layer = (body.get('layer') or 'termine').strip() or 'termine'
    extras = {}
    for k in ('ende', 'ort', 'kategorie', 'kategorie_name'):
        v = (body.get(k) or '').strip()
        if v:
            extras[k] = v
    if body.get('quelle'):
        extras['quelle'] = body['quelle']    # {art, id}; label darf dann fehlen
    if body.get('stil'):
        extras['stil'] = body['stil']        # {css: wert}, geprüft in kalender.add_*
    _typ_extras(body, extras)                # typ deadline + vorwarnung (20.10.2026)
    # Mehrtägiger (ganztägiger) Termin: `bis`-Datum gesetzt → Spanne statt
    # Einmal-Termin. Kein Konflikt-Check (ganztägig, kein Zeit-Slot).
    bis = (body.get('bis') or '').strip()
    if bis:
        try:
            date.fromisoformat(bis)
        except (TypeError, ValueError):
            return jsonify({"error": "bis muss YYYY-MM-DD sein"}), 400
        vorher = _alle_kennungen()
        ok = kalender.add_span(layer, day, bis, label, **extras)
        if not ok:
            return jsonify({"error": "spanne abgelehnt (bis<von? layer?)"}), 400
        return jsonify({"ok": True, "conflicts": [], "spanning": True,
                        "kennung": _neue_kennung(vorher)})
    time = kalender.uhrzeit_weich(time) if time else time
    conflicts = kalender.conflicts_for_proposed(layer, day, label, time=time)
    vorher = _alle_kennungen()
    ok = kalender.add_entry(layer, day, label, time=time, **extras)
    if not ok:
        return jsonify({"error": "eintrag abgelehnt (unbekannter layer?)"}), 400
    return jsonify({"ok": True, "conflicts": conflicts, "kennung": _neue_kennung(vorher)})


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
    layer = (body.get('layer') or 'termine').strip() or 'termine'
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
    Antwort {ok:true} bzw. 400. Default-Layer `termine` (ein Kalender, seit 07.10.2026).
    """
    body = request.get_json(silent=True) or {}
    label = (body.get('label') or '').strip()
    if not label:
        return jsonify({"error": "label fehlt"}), 400
    if body.get('freq'):
        # calcurse „r": Typ (t/w/m/j), alle wie viele, Ende, ab dem gewählten Tag.
        vorher = _alle_kennungen()
        ok = kalender_bearbeiten.routine_neu(
            (body.get('layer') or 'termine'), label, body.get('seit') or '',
            body.get('freq'), body.get('intervall') or 1, body.get('bis') or None,
            body.get('wochentage') or None, body.get('time') or None,
            body.get('ende') or None, body.get('ort') or None,
            body.get('kategorie') or None, body.get('kategorie_name') or None,
            body.get('quelle') or None, stil=body.get('stil') or None,
            typ=body.get('typ') or None, vorwarnung=body.get('vorwarnung'),
            soll_abstand=body.get('soll_abstand'))
        return (jsonify({"ok": True, "kennung": _neue_kennung(vorher)}) if ok
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
    layer = (body.get('layer') or 'termine').strip() or 'termine'
    extras = {}
    for k in ('ende', 'ort', 'kategorie', 'kategorie_name'):
        v = (body.get(k) or '').strip()
        if v:
            extras[k] = v
    if body.get('quelle'):
        extras['quelle'] = body['quelle']
    if body.get('stil'):
        extras['stil'] = body['stil']
    _typ_extras(body, extras)
    vorher = _alle_kennungen()
    ok = kalender.add_routine(layer, label, rrule, time=time, **extras)
    if not ok:
        return jsonify({"error": "routine abgelehnt (layer/rrule?)"}), 400
    return jsonify({"ok": True, "kennung": _neue_kennung(vorher)})


@bp.route('/api/calendar/routine', methods=['DELETE'])
def api_calendar_delete_routine():
    """
    Eine GANZE Routine (Wiederholungs-Regel) löschen — alle Vorkommen weg.
    Gegenstück zum einzelnen Deaktivieren (.../routine/skip). NICHT KI-gegatet
    (direkte Nutzeraktion). Body: {layer, label, day?, time?}. `day`/`time`
    treffen bei gleichnamigen Routinen nur die, die an dem Tag vorkommt (sonst
    werden Serien gleichen Namens an anderen Wochentagen mitgelöscht).
    Antwort {deleted:n}. Mit `kennung` im Body genau diese Routine löschen
    (kalender_kennung.routine_loeschen), Antwort dann {ok:true}.
    """
    body = request.get_json(silent=True) or {}
    if body.get('kennung'):
        kalender_kennung.routine_loeschen(body['kennung'])
        return jsonify({"ok": True})
    layer = (body.get('layer') or 'termine').strip() or 'termine'
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
    wochentage}}}. day/time bestimmen, WELCHE Routine gemeint ist.
    Mit `kennung` im Body genau diese Routine (siehe _routine_per_kennung);
    Antwort dann {ok, eintrag}."""
    b = request.get_json(silent=True) or {}
    if b.get('kennung'):
        return _routine_per_kennung(b['kennung'], b.get('new') or {})
    return _antwort(kalender_bearbeiten.routine_bearbeiten(
        b.get('layer') or 'termine', b.get('label') or '', b.get('day') or '',
        b.get('time') or None, b.get('new') or {}), "routine nicht gefunden/abgelehnt")


@bp.route('/api/calendar/routine/abweichung', methods=['POST'])
def api_calendar_routine_abweichung():
    """NUR dieses Vorkommen ändern. Body: {layer, label, day, time?,
    new:{tag?, time?, ende?, label?, ort?}}."""
    b = request.get_json(silent=True) or {}
    return _antwort(kalender_bearbeiten.routine_abweichung(
        b.get('layer') or 'termine', b.get('label') or '', b.get('day') or '',
        b.get('time') or None, b.get('new') or {}), "vorkommen nicht gefunden/abgelehnt")


@bp.route('/api/calendar/spanne', methods=['POST'])
def api_calendar_spanne_neu():
    """Mehrtägig anlegen. Body: {layer?, von, bis, label, start_zeit?,
    end_zeit?, tageszeit?:[von, bis], ort?, kategorie?, kategorie_name?,
    quelle?: {art, id}, stil?: {css: wert}}."""
    b = request.get_json(silent=True) or {}
    tz = b.get('tageszeit')
    return _antwort(kalender_bearbeiten.spanne_neu(
        b.get('layer') or 'termine', b.get('von') or '', b.get('bis') or '',
        b.get('label') or '', b.get('start_zeit') or None, b.get('end_zeit') or None,
        tuple(tz) if isinstance(tz, list) and len(tz) == 2 else None,
        b.get('ort') or None, b.get('kategorie') or None,
        b.get('kategorie_name') or None, b.get('quelle') or None,
        stil=b.get('stil') or None), "spanne abgelehnt")


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
    Logik wie die KI-Rückfrage). Body: {layer?, day, label, time?, ende?,
    ausser?} — ohne Ende kein Intervall, also keine Überlappung
    (find_collisions); `ausser` = Kennung des Eintrags, der gerade bearbeitet
    wird (zählt nicht mit, sonst kollidiert er mit sich selbst).
    Antwort {konflikte:[zeile, …]} — schreibt nichts."""
    b = request.get_json(silent=True) or {}
    try:
        k = kalender.conflicts_for_proposed(b.get('layer') or 'termine',
                                            b.get('day') or '', b.get('label') or '',
                                            time=b.get('time') or None,
                                            ende=b.get('ende') or None,
                                            ausser=b.get('ausser') or None)
    except Exception as e:
        return jsonify({"konflikte": [], "error": str(e)})
    return jsonify({"konflikte": k})


# ── Per Kennung (seit 11.10.2026, Wunsch ASSISTANT) ────────────────────
# PUT/DELETE /api/calendar/eintrag und /routine nehmen zusätzlich `kennung`:
# dann trifft es GENAU diesen Eintrag (kalender_kennung), sonst wie bisher
# Tag+Titel. Ablehnung = 400 {error, code} (Fehlerhandler oben), auch für
# eine unbekannte Kennung (KENNUNG-UNBEKANNT) — wie bei allen Kennung-Routen.
# Felder in `new`: fehlend = unverändert, "" = löschen.
_EINTRAG_NEU = {'day': 'tag', 'label': 'label', 'time': 'time', 'ende': 'ende',
                'ort': 'ort', 'von': 'von', 'bis': 'bis', 'times': 'times',
                'enden': 'enden', 'kategorie': 'kategorie',
                'kategorie_name': 'kategorie_name', 'typ': 'typ', 'vorwarnung': 'vorwarnung',
                'soll_abstand': 'soll_abstand'}
_ROUTINE_NEU = {k: k for k in ('label', 'time', 'ende', 'ort', 'rrule', 'seit', 'bis',
                               'motiv', 'kategorie', 'kategorie_name', 'typ', 'vorwarnung',
                               'soll_abstand')}


def _felder(new: dict, erlaubt: dict) -> dict:
    """`new` aus dem Body → Parameter für kalender_kennung; ein unbekanntes
    Feld wird abgelehnt statt still übergangen."""
    if not isinstance(new, dict):
        raise kalender_kennung.KalenderAbgelehnt("UNBEKANNTES-FELD", "new muss ein Objekt sein")
    fremd = sorted(set(new) - set(erlaubt))
    if fremd:
        raise kalender_kennung.KalenderAbgelehnt(
            "UNBEKANNTES-FELD", f"unbekannt in new: {', '.join(fremd)}")
    return {erlaubt[k]: v for k, v in new.items() if v is not None}


def _routine_per_kennung(k: str, new: dict):
    """`new.wiederholung` {freq, intervall, bis, wochentage} wird wie beim
    Anlegen zur Regel (ab dem `seit` der Routine); Aus-Tage und Abweichungen
    bleiben dabei — anders als auf dem Weg über Tag+Titel."""
    new = dict(new) if isinstance(new, dict) else new
    w = new.pop('wiederholung', None) if isinstance(new, dict) else None
    felder = _felder(new, _ROUTINE_NEU)
    if w is not None:
        if 'rrule' in felder or 'bis' in felder or not isinstance(w, dict):
            raise kalender_kennung.KalenderAbgelehnt(
                "UNBEKANNTES-FELD", "wiederholung {…} nicht zusammen mit rrule/bis")
        alt = kalender_kennung.eintrag(k)
        seit_s = felder.get('seit') or alt.get('seit') or uhr.heute().isoformat()
        try:
            seit = date.fromisoformat(seit_s)
            ende = date.fromisoformat(w['bis']) if w.get('bis') else None
        except (TypeError, ValueError):
            raise kalender_kennung.KalenderAbgelehnt("DATUM-UNGUELTIG")
        regel = kalender_bearbeiten.regel_bauen(w.get('freq'), seit, w.get('intervall', 1),
                                                ende, w.get('wochentage'))
        if not regel:
            raise kalender_kennung.KalenderAbgelehnt("RRULE-UNGUELTIG")
        felder['rrule'] = regel
    return jsonify({"ok": True, "eintrag": kalender_kennung.routine_aendern(k, **felder)})


@bp.route('/api/calendar/eintrag')
def api_calendar_eintrag_lesen():
    """?kennung=… → das Eintrags-Dict (kalender_kennung.eintrag: kennung,
    art, layer, kategorie, tag/von, …). Unbekannt → 400 KENNUNG-UNBEKANNT."""
    return jsonify(kalender_kennung.eintrag(request.args.get('kennung') or ''))


@bp.route('/api/calendar/eintrag', methods=['DELETE'])
def api_calendar_eintrag_loeschen():
    """GENAU einen Einmal-Termin (bzw. eine Spanne an ihrem Start-Tag)
    löschen — exakter Titel, bei Gleichnamigen die Uhrzeit. Body: {layer?,
    day, label, time?}. Anders als DELETE /api/calendar/entry kein
    Teilstring-Treffer. Mit `kennung` im Body genau diesen Termin bzw. diese
    Spanne (kalender_kennung.eintrag_loeschen), Antwort {ok:true}."""
    b = request.get_json(silent=True) or {}
    if b.get('kennung'):
        kalender_kennung.eintrag_loeschen(b['kennung'])
        return jsonify({"ok": True})
    return _antwort(kalender_bearbeiten.eintrag_loeschen(
        b.get('layer') or 'termine', b.get('day') or '', b.get('label') or '',
        b.get('time') or None), "termin nicht gefunden")


@bp.route('/api/calendar/eintrag', methods=['PUT'])
def api_calendar_eintrag_aendern():
    """Einen Einmal-Termin ändern, andere Felder bleiben. Body: {layer?, day,
    label, time?, new:{day?, label?, time?, ende?, ort?}}. Mit `kennung` im
    Body genau diesen Termin bzw. diese Spanne (_EINTRAG_NEU); Antwort dann
    {ok, eintrag}."""
    b = request.get_json(silent=True) or {}
    if b.get('kennung'):
        felder = _felder(b.get('new') or {}, _EINTRAG_NEU)
        return jsonify({"ok": True,
                        "eintrag": kalender_kennung.eintrag_aendern(b['kennung'], **felder)})
    return _antwort(kalender_bearbeiten.eintrag_aendern(
        b.get('layer') or 'termine', b.get('day') or '', b.get('label') or '',
        b.get('time') or None, b.get('new') or {}), "termin nicht gefunden/abgelehnt")


@bp.route('/api/calendar/ebene', methods=['POST'])
def api_calendar_ebene():
    """Einen Eintrag per Kennung zwischen committed („termine") und
    „uncommitted" verschieben. Body: {kennung, ziel?} — ohne ziel umschalten."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.ebene_wechseln(b.get('kennung') or '', b.get('ziel') or None))


# ── Tagesrhythmus (Phasen) und Gruppen, seit 10.10.2026 ────────────────
# Alle Antworten mit Eintrag sind das Dict aus kalender_kennung.eintrag
# (kennung, art, layer, kategorie, bei Phasen motiv); Ablehnung = 400 mit
# {error, code} (Fehlerhandler oben).
_PHASE_FELDER = ('time', 'ende', 'label', 'ort', 'motiv', 'rrule', 'von', 'bis',
                 'kategorie', 'kategorie_name')


@bp.route('/api/calendar/motive')
def api_calendar_motive():
    """Der feste Katalog der Motive für Phasen: [{schluessel, name, was}]."""
    return jsonify({"motive": kalender_rhythmus.motive(), "ebene": kalender_rhythmus.EBENE})


@bp.route('/api/calendar/kategorien')
def api_calendar_kategorien():
    """Der feste Katalog der Gruppen: [{schluessel, name}] inkl. keine/custom."""
    return jsonify({"kategorien": kalender_kategorie.katalog()})


@bp.route('/api/calendar/phasen')
def api_calendar_phasen():
    """Alle Phasen wie gespeichert (mit Kennung, Regel, Abweichungen)."""
    return jsonify({"phasen": kalender_kennung.phasen()})


@bp.route('/api/calendar/phase', methods=['POST'])
def api_calendar_phase_neu():
    """Body: {label, time, motiv, ende?, rrule? (Standard FREQ=DAILY), von?,
    bis? (leer = bis auf Weiteres), ort?, kategorie?, kategorie_name?}."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.phase_anlegen(
        b.get('label') or '', b.get('time') or '', motiv=b.get('motiv') or '',
        ende=b.get('ende') or None, rrule=b.get('rrule') or 'FREQ=DAILY',
        von=b.get('von') or None, bis=b.get('bis') or None, ort=b.get('ort') or None,
        kategorie=b.get('kategorie'), kategorie_name=b.get('kategorie_name')))


@bp.route('/api/calendar/phase', methods=['PUT'])
def api_calendar_phase_aendern():
    """Ab jetzt ändern. Body: {kennung, time?, ende?, label?, ort?, motiv?,
    rrule?, von?, bis?, kategorie?, kategorie_name?} — "" löscht ein Feld
    (bis "" = bis auf Weiteres), fehlend = unverändert."""
    b = request.get_json(silent=True) or {}
    felder = {k: b[k] for k in _PHASE_FELDER if k in b and b[k] is not None}
    return jsonify(kalender_kennung.phase_aendern(b.get('kennung') or '', **felder))


@bp.route('/api/calendar/phase', methods=['DELETE'])
def api_calendar_phase_loeschen():
    """Body: {kennung}."""
    b = request.get_json(silent=True) or {}
    kalender_kennung.phase_loeschen(b.get('kennung') or '')
    return jsonify({"ok": True})


@bp.route('/api/calendar/routine/zeitraum', methods=['POST'])
def api_calendar_routine_zeitraum():
    """Alle Vorkommen in [von, bis] einer Routine/Phase ändern („3 Tage um 2
    ins Bett"). Body: {kennung, von, bis, time?, ende?, label?, ort?} — ""
    = an diesen Tagen wieder wie die Regel."""
    b = request.get_json(silent=True) or {}
    felder = {k: b[k] for k in ('time', 'ende', 'label', 'ort') if b.get(k) is not None}
    return jsonify(kalender_kennung.routine_zeitraum_aendern(
        b.get('kennung') or '', b.get('von') or '', b.get('bis') or '', **felder))


@bp.route('/api/calendar/kategorie', methods=['POST'])
def api_calendar_kategorie():
    """Gruppe eines Eintrags. Body: {kennung, kategorie, kategorie_name?}."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.kategorie_setzen(
        b.get('kennung') or '', b.get('kategorie'), b.get('kategorie_name')))


@bp.route('/api/calendar/kategorie/kurs', methods=['POST'])
def api_calendar_kategorie_kurs():
    """Gruppe für alle Einträge eines Kurses (calendar_colours.course_key). Body:
    {schluessel, kategorie, kategorie_name?, probe?} — probe: nur zeigen."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.kategorie_fuer_kurs(
        b.get('schluessel') or '', b.get('kategorie'), b.get('kategorie_name'),
        probe=bool(b.get('probe'))))


# ── Titel aus Liste/Projekt (quelle, seit 10.10.2026) ──────────────────
# Ein Zeitfenster wählt eine Liste bzw. ein Projekt; der Titel ist live der
# oberste offene Punkt (core/kalender_quelle.py). Antworten wie
# kalender_kennung.eintrag (+ quelle, titel_live, quelle_name,
# quelle_zustand, quelle_eintrag); Ablehnung 400 {error, code}.
@bp.route('/api/calendar/quellen')
def api_calendar_quellen():
    """Zur Auswahl: {listen: [...], projekte: [...]}, je {art, id, name,
    titel (was jetzt oben steht), zustand}."""
    return jsonify(kalender_quelle.auswahl())


@bp.route('/api/calendar/quelle')
def api_calendar_quelle_vorschau():
    """?art=liste|projekt&id=…&n=4 → {name, zustand, punkte: [die ersten n
    offenen Punkte]} — fürs Ansehen eines Quellen-Termins (TUI)."""
    a = request.args
    try:
        n = int(a.get('n') or 4)
    except ValueError:
        n = 4
    return jsonify(kalender_quelle.vorschau({"art": a.get('art'), "id": a.get('id')}, n))


@bp.route('/api/calendar/quelle', methods=['POST'])
def api_calendar_quelle_setzen():
    """Body: {kennung, art: liste|projekt, id, label?} — label = Rückfall-
    Titel (Standard: Name der Liste/des Projekts)."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.quelle_setzen(
        b.get('kennung') or '', b.get('art'), b.get('id'), label=b.get('label')))


@bp.route('/api/calendar/quelle', methods=['DELETE'])
def api_calendar_quelle_loesen():
    """Body: {kennung, titel_uebernehmen?} — ohne Quelle heißt der Termin
    wieder label; titel_uebernehmen schreibt vorher den aktuellen Titel fest."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.quelle_loesen(
        b.get('kennung') or '', titel_uebernehmen=bool(b.get('titel_uebernehmen'))))


# ── Aussehen des Kastens (stil, seit 10.10.2026) ───────────────────────
# Die Stylebox der TUI: ein dict aus CSS-Eigenschaften (core/stil.py,
# Angebot stil.KASTEN). Gilt für den ganzen Eintrag bzw. die ganze Serie.
@bp.route('/api/calendar/stil', methods=['POST'])
def api_calendar_stil():
    """Body: {kennung, stil: {css: wert}} — ERSETZT den Stil; {} entfernt
    ihn. Antwort wie kalender_kennung.eintrag; Ablehnung 400 {error, code}
    (STIL-UNGUELTIG, IST-PHASE, KENNUNG-UNBEKANNT)."""
    b = request.get_json(silent=True) or {}
    stil = b.get('stil')
    return jsonify(kalender_kennung.stil_setzen(
        b.get('kennung') or '', {} if stil is None else stil))


# ── Termintyp deadline (seit 20.10.2026) ───────────────────────────────
# Ein Zeitpunkt mit Vorwarnung (core/kalender_deadline.py): Uhrzeit Pflicht,
# kein Ende, nie mehrtägig; leuchtet in den Ansichten, kollidiert nie.
@bp.route('/api/calendar/typ', methods=['POST'])
def api_calendar_typ():
    """Body: {kennung, typ: "deadline"|"normal", vorwarnung?: Minuten|"3d",
    soll_abstand?: Minuten ≤ 0|"-3d18h"|"" (weg)} — normal entfernt alles. Antwort: der Eintrag (kennung, art,
    layer, typ, vorwarnung …); Ablehnung 400 {error, code}."""
    b = request.get_json(silent=True) or {}
    return jsonify(kalender_kennung.typ_setzen(
        b.get('kennung') or '', b.get('typ'), vorwarnung=b.get('vorwarnung'),
        soll_abstand=b.get('soll_abstand')))
