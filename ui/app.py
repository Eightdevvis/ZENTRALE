# ui/app.py
#
# Flask-Backend für ZENTRALE.
#
# Flask ist ein minimales Python-Web-Framework.
# Es lauscht auf HTTP-Anfragen und leitet sie an die passende
# Python-Funktion weiter ("Routing").
#
# Dieses Modul läuft als eigener Thread neben dem Event-Loop (main.py).
# Die Kommunikation zwischen beiden Threads läuft ausschließlich
# über state.py (shared in-memory state, thread-safe via Lock).
#
# ── Architektur ───────────────────────────────────────────────────────
#   Browser  ──GET /api/state──▶  app.py  ──liest──▶  state.py
#   Browser  ──POST /api/chat──▶  app.py  ──ruft──▶   ai.py  ──▶  Ollama
# ──────────────────────────────────────────────────────────────────────

import sys
import os
import json

# core/ auf den Python-Suchpfad legen, damit wir state, categories
# und ai importieren können (die liegen in core/, nicht in ui/).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'core'))

from flask import Flask, jsonify, render_template, request, Response, stream_with_context, send_from_directory
from datetime import datetime, date
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import categories   # type: ignore
import graphs       # type: ignore  – dynamische Lifestyle-Graph-Registry
import lists        # type: ignore  – dynamische Listen-Registry (Todo/Sammel-Listen)
import kalender     # type: ignore  – Kalender-Layer (Woche/Monat, data/ai_calendar.json)
import ai           # type: ignore
import audio        # type: ignore
import tutor_session # type: ignore  – Sprach-Tutor (Addon auf der Core-KI, eigener Prompt/Tools)
import tutor_config   # type: ignore  – lokale Tutor-Config + Live-Umschalten (Provider/Modell)
import tutor_providers # type: ignore  – Provider-Registry (Flags, Liste)
import tutor_langs     # type: ignore  – Sprach-Profile (Liste)
import consolidation # type: ignore  – Phase E: STM → LTM Konsolidierung
import telemetry    # type: ignore  – PC-Host-Telemetrie (CPU/GPU/VRAM/Temp/RAM)
import kassette     # type: ignore  – welche Kassette läuft (monolith | laptop)
from map import base_features as map_base_features  # type: ignore  – Maps-System (core/map/)
from map import base_braille as map_base_braille  # type: ignore  – Maps-System (Braille-Füllung)
from map import layers as map_layers  # type: ignore  – Overlay-Layer (Achse 2, Handelsrouten)

app = Flask(__name__)

# Templates bei Änderung neu einlesen, ohne den ganzen Server neu zu starten.
# debug bleibt aus (use_reloader würde im Thread Probleme machen) – das hier
# betrifft NUR das Jinja-Template-Caching. Spart bei UI-Arbeit den Neustart;
# Kosten: ein stat() pro Render, bei Single-User-Dashboard vernachlässigbar.
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Absoluter Pfad zum data/-Verzeichnis (liegt im Projektroot, nicht in ui/).
# os.path.abspath + join macht den Pfad robust gegen "von wo starte ich das Skript".
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')


# ── Kassetten-Gate für KI-Endpoints ───────────────────────────────────
#
# In den KI-freien Kassetten (laptop, tui) ist die KI komplett raus (siehe
# core/kassette.py): kein Chat, kein TTS/STT, keine Permission-Antworten.
# Diese Endpoints werden hart mit 503 abgeriegelt, falls doch jemand sie
# aufruft. Die KI-freien Fronten kennen sie ohnehin nicht – das hier ist
# Defense-in-Depth, damit eine versehentliche Anfrage NIE die PC-KI anspricht.
def _ki_aus():
    return jsonify({"error": "KI in dieser Kassette deaktiviert"}), 503


# ── Dashboard ─────────────────────────────────────────────────────────

@app.route('/')
@app.route('/monolith')   # Alias: alte Kiosk-/Bookmark-/Deeplink-URL bleibt gueltig
def index():
    """
    Liefert das Dashboard der aktuell gefahrenen Kassette (core/kassette.py):
      - monolith (Default): das große Pi-Kiosk-Dashboard (KI-Kern, Chat, Audio).
      - laptop: die kleine, KI-freie Laptop-Kassette (ui/templates/laptop.html).
    Die Wahl kommt aus ZENTRALE_KASSETTE, gesetzt vom Start-Befehl. /monolith
    bleibt als Alias bestehen, damit der Pi-Kiosk und alte Bookmarks nicht brechen
    (zeigt ebenfalls die kassetten-aktive UI).

    Statische Assets (engine.js = Daten-Adapter, viz.js, ascii.js, fonts/) liegen
    in ui/static/ und werden von Flask automatisch unter /static/<file> bedient.
    """
    resp = render_template(kassette.template())
    from flask import make_response
    r = make_response(resp)
    # Cache deaktivieren: der Browser soll immer die aktuelle Version laden,
    # nicht eine gecachte – wichtig bei Entwicklung und Pi-Restart.
    r.headers['Cache-Control'] = 'no-store'
    return r


# ── State-Polling ──────────────────────────────────────────────────────

@app.route('/api/state')
def api_state():
    """
    Liefert den aktuellen System-State als JSON.
    Wird vom Browser jede Sekunde abgefragt (Polling-Loop in index.html).
    """
    snapshot = state.get_snapshot()
    # Datum wird hier im Backend formatiert statt im Frontend,
    # damit alle Clients (auch zukünftige) dasselbe Format bekommen.
    snapshot['time'] = datetime.now().strftime("%d. %B %Y")
    return jsonify(snapshot)


# ── Sensor-Webhook ─────────────────────────────────────────────────────
#
# POST /api/sensor/<name> – Eingangskanal fuer externe Sensor-Trigger.
#
# Seit der PC↔Pi-Topologie-Migration laeuft das Backend auf dem PC. Echte
# Sensoren (Pi-PIR, Tuersensor, Mikrocontroller) haengen aber physisch
# am Pi (oder spaeter direkt am LAN). Damit sie Events ins System bringen
# koennen, ohne dass main.py auf jedem Knoten laufen muss, schicken sie
# einen HTTP-POST an diesen Endpoint. Der Sensor-Name wird gequeued, der
# Event-Loop in main.py mapped ihn auf den jeweiligen Event.
#
# Whitelist gegen Tippfehler und gegen Querschuss aus dem LAN (Hotspot
# ist nicht streng abgeschottet). Bewusst nicht aus events.py generiert –
# Sensor-Namen sind die "physischen" Eingangskanaele, Events sind die
# internen logischen Ereignisse. Beide Welten getrennt halten.

_ALLOWED_SENSORS = {"button", "light", "motion", "door"}


# ── Telemetrie ─────────────────────────────────────────────────────────
#
# Zwei Maschinen, zwei Wege:
#   PC : lokal aus /proc + /sys + nvidia-smi (core/telemetry.pc_snapshot)
#   Pi : der Pi POSTet seine Werte an /api/telemetry/pi (FS read-only, kann
#        nicht selbst anzeigen) → wir halten den letzten Stand in state.py.
# GET /api/telemetry liefert beides kombiniert ans Dashboard.

# Welche Top-Level-Keys wir vom Pi akzeptieren (gegen Muell/Querschuss aus
# dem LAN). Werte werden nicht weiter geparst - der Pi baut die Shape selbst
# (scripts/pi_sensor_bridge.py), wir nehmen nur bekannte Schluessel.
_ALLOWED_PI_METRICS = {"cpu", "temp", "ram", "disk"}


@app.route('/api/telemetry')
def api_telemetry():
    """PC- und Pi-Telemetrie kombiniert. Wird vom Dashboard alle ~2s gepollt."""
    return jsonify({
        "pc": telemetry.pc_snapshot(),
        "pi": state.get_pi_telemetry(),   # {} solange der Pi noch nichts gesendet hat
    })


@app.route('/api/telemetry/pi', methods=['POST'])
def api_telemetry_pi():
    """
    Telemetrie-Push vom Pi entgegennehmen. Body (JSON) hat die gleiche
    Shape wie ein Meter-Block im Frontend, z.B.:
      {"cpu": {"v": 12.3}, "temp": {"v": 51.0},
       "ram": {"v": 38, "used": 0.6, "total": 1.0},
       "disk": {"v": 47, "used": 14.1, "total": 30.0}}
    Nur bekannte Schluessel werden uebernommen.
    """
    body = request.get_json(silent=True) or {}
    clean = {k: v for k, v in body.items() if k in _ALLOWED_PI_METRICS}
    state.set_pi_telemetry(clean)
    return jsonify({"ok": True})


@app.route('/api/sensor/<name>', methods=['POST'])
def api_sensor_trigger(name):
    """
    Externes Sensor-Signal entgegennehmen und in die Verarbeitungs-
    Queue stellen. Antwortet sofort – die eigentliche Verarbeitung
    macht der Event-Loop asynchron.

    Body wird aktuell ignoriert (reines Trigger-Signal reicht). Spaeter
    kann hier z.B. ein Wert (Helligkeit, Tueroffen-Dauer) mitgegeben
    werden – dann erweitern wir queue_sensor() um ein meta-Dict.
    """
    if name not in _ALLOWED_SENSORS:
        return jsonify({"error": f"unbekannter Sensor: {name}"}), 400
    state.queue_sensor(name)
    state.push_log(f"WEBHOOK: sensor/{name} von {request.remote_addr}")
    return jsonify({"ok": True})


# ── Data Collection ────────────────────────────────────────────────────

@app.route('/api/categories')
def api_categories():
    """Gibt alle verfügbaren Data-Collection-Kategorien zurück (aus categories.py)."""
    return jsonify(categories.CATEGORIES)


@app.route('/api/data/<category_id>')
def api_data(category_id):
    """
    Gibt alle gespeicherten Einträge einer Kategorie zurück.
    Die Daten liegen in data/<category_id>.json auf Disk.
    Leere Liste wenn noch keine Einträge existieren.
    """
    log_file = os.path.join(_DATA_DIR, f'{category_id}.json')
    if not os.path.exists(log_file):
        return jsonify([])
    with open(log_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


# ── Lifestyle-Graphen (dynamisch, vom Dashboard angelegt) ──────────────
#
# Definitionen liegen in data/graphs.json (core/graphs.py). Die Messwerte
# selbst teilen sich die Data-Collection-Infrastruktur: /api/log schreibt
# nach data/<graph_id>.json, /api/data/<graph_id> liest sie zurück. Hier
# gibt es nur die Verwaltung der Definitionen (Liste / anlegen / löschen).

@app.route('/api/graphs')
def api_graphs():
    """Alle Graph-Definitionen (für das Graph-Werkzeug und die lifestyle-Box)."""
    return jsonify(graphs.list_graphs())


@app.route('/api/graphs', methods=['POST'])
def api_graphs_create():
    """
    Neuen Graphen anlegen.
    Body (JSON): {"name": "Gewicht", "type": "number"|"scale", "unit": "kg"}
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.create_graph(body.get('name'), body.get('type', 'number'), body.get('unit', ''))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"GRAPH+: {g['id']} ({g['type']})")
    return jsonify(g)


@app.route('/api/graphs/<gid>', methods=['DELETE'])
def api_graphs_delete(gid):
    """Graph-Definition und seine Messwerte-Datei löschen."""
    graphs.delete_graph(gid)
    state.push_log(f"GRAPH-: {gid}")
    return jsonify({"ok": True})


# ── Listen (dynamisch, vom Dashboard angelegt) ─────────────────────────
#
# Pendant zu den Lifestyle-Graphen, aber für abhakbare Todo-/Sammel-Listen.
# Anders als die Graphen liegen Definition UND Einträge inline in
# data/lists.json (core/lists.py) – keine Zeitreihe, kein /api/log-Sharing.

@app.route('/api/lists')
def api_lists():
    """Alle Listen-Definitionen inkl. ihrer Einträge."""
    return jsonify(lists.list_lists())


@app.route('/api/lists', methods=['POST'])
def api_lists_create():
    """
    Neue Liste anlegen.
    Body (JSON): {"name": "Einkaufen"}
    """
    body = request.get_json(silent=True) or {}
    try:
        l = lists.create_list(body.get('name'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"LISTE+: {l['id']}")
    return jsonify(l)


@app.route('/api/lists/<lid>', methods=['DELETE'])
def api_lists_delete(lid):
    """Listen-Definition mit allen Einträgen löschen."""
    lists.delete_list(lid)
    state.push_log(f"LISTE-: {lid}")
    return jsonify({"ok": True})


@app.route('/api/lists/<lid>/rename', methods=['POST'])
def api_lists_rename(lid):
    """
    Anzeigenamen einer Liste ändern (id bleibt stabil).
    Body (JSON): {"name": "Neuer Name"}
    """
    body = request.get_json(silent=True) or {}
    try:
        lst = lists.rename_list(lid, body.get('name'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    return jsonify(lst)


@app.route('/api/lists/<lid>/items', methods=['POST'])
def api_lists_add_item(lid):
    """
    Eintrag an eine Liste hängen.
    Body (JSON): {"text": "Milch"} — optional {"parent": <iid>} macht ihn zum
    Unterpunkt des Eintrags <iid> (Liste wird so zum verschachtelten Mischtyp).
    """
    body = request.get_json(silent=True) or {}
    try:
        item = lists.add_item(lid, body.get('text'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    return jsonify(item)


@app.route('/api/lists/<lid>/nest', methods=['POST'])
def api_lists_nest(lid):
    """
    Eine ganze Liste IN eine andere einordnen — sie wird dort zum Eintrag und
    verschwindet aus der obersten Ebene.
    Body (JSON): {"into": <ziel-lid>} — optional {"parent": <iid>} hängt sie
    unter einen bestimmten Ziel-Eintrag statt ganz oben.
    """
    body = request.get_json(silent=True) or {}
    try:
        node = lists.nest_list(lid, body.get('into'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"LISTE~: {lid} → {body.get('into')}")
    return jsonify(node)


@app.route('/api/lists/<lid>/items/<int:iid>/toggle', methods=['POST'])
def api_lists_toggle_item(lid, iid):
    """Erledigt-Status eines Eintrags umschalten."""
    try:
        item = lists.toggle_item(lid, iid)
    except KeyError:
        return jsonify({"error": "unbekannt"}), 404
    return jsonify(item)


@app.route('/api/lists/<lid>/items/<int:iid>/rename', methods=['POST'])
def api_lists_rename_item(lid, iid):
    """
    Text eines Eintrags ändern (egal wie tief).
    Body (JSON): {"text": "Neuer Text"}
    """
    body = request.get_json(silent=True) or {}
    try:
        item = lists.rename_item(lid, iid, body.get('text'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannt"}), 404
    return jsonify(item)


@app.route('/api/lists/<lid>/items/<int:iid>/move', methods=['POST'])
def api_lists_move_item(lid, iid):
    """
    Einen Eintrag (samt Teilbaum) RAUS in eine andere (oder dieselbe) Liste
    verschieben.
    Body (JSON): {"into": <ziel-lid>} — optional {"parent": <iid>} hängt ihn
    unter einen bestimmten Ziel-Eintrag statt ganz oben.
    """
    body = request.get_json(silent=True) or {}
    try:
        node = lists.move_item(lid, iid, body.get('into'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"LISTE↦: {lid}/{iid} → {body.get('into')}")
    return jsonify(node)


@app.route('/api/lists/<lid>/items/<int:iid>', methods=['DELETE'])
def api_lists_delete_item(lid, iid):
    """Einen Eintrag aus einer Liste löschen."""
    try:
        lists.delete_item(lid, iid)
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    return jsonify({"ok": True})


@app.route('/api/map/base')
def api_map_base():
    """
    Basiskarte (Küstenlinien 1:110m) für den Viewport der anfragenden Front,
    fertig auf deren Zellraster projiziert. Front-agnostisch: TUI und Browser
    rufen denselben Endpoint, schicken nur ihr eigenes cols/rows/aspect mit.
    Alle Geo-Mathematik steckt in core/map/ (siehe memory/maps_system.md).

    Query: cx,cy (lon/lat Mittelpunkt), zoom (≥0), cols,rows (Zielraster),
           aspect (Zellbreite/Höhe; TUI ≈ 0.5, SVG = 1.0).
    NICHT KI-gegatet — die Karte gibt es in ALLEN Kassetten (auch tui/laptop).
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 120))
        rows = int(a.get('rows', 40))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_base_features(cx, cy, zoom, cols, rows, aspect))


@app.route('/api/map/braille')
def api_map_braille():
    """
    Basiskarte als GEFÜLLTES Land in Braille („kleine Punkte als Füllung") —
    fertige Braille-Zeilen für eine Terminal-Front, die sie nur druckt. 2×4
    Subpixel pro Zelle. Geo-/Rasterlogik komplett in core/map/render.py.

    Query: cx,cy (lon/lat), zoom (≥0), cols,rows (Zeichenraster der TUI-Box).
    NICHT KI-gegatet (Karte gibt es in allen Kassetten).
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 80))
        rows = int(a.get('rows', 30))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_base_braille(cx, cy, zoom, cols, rows))


@app.route('/api/map/layers')
def api_map_layers():
    """
    Registry der thematischen Overlay-Layer (Achse 2): welche Layer es gibt,
    je mit ihren Sub-Layern, Quelle (Provenienz) und ob sie eine Zeitachse
    haben (Achse 3). Die Front baut daraus ihr Layer-Menü.
    NICHT KI-gegatet (Karte gibt es in allen Kassetten).
    """
    return jsonify({"layers": map_layers.registry()})


@app.route('/api/map/layer/<layer_id>')
def api_map_layer(layer_id):
    """
    Features EINES Overlay-Layers für den Viewport der Front, fertig aufs
    Zellraster projiziert (gleiche viewport()-Mathematik wie /api/map/base, damit
    Overlay und Grundkarte passgenau sitzen). Trägt die Provenienz mit
    (source/vintage/retrieved_at) — für ein seriöses „wer sagt das, wann".

    Query: cx,cy,zoom,cols,rows,aspect wie /api/map/base; zusätzlich
           sub  = Sub-Layer (z.B. 'chokepoints'),
           at   = Zeitpunkt (Achse 3; Layer ohne Zeitachse ignorieren ihn).
    404 bei unbekanntem Layer. NICHT KI-gegatet.
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 120))
        rows = int(a.get('rows', 40))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    sub = a.get('sub') or None
    at = a.get('at') or None
    out = map_layers.layer_features(layer_id, cx, cy, zoom, cols, rows,
                                    aspect=aspect, sub=sub, at=at)
    if out is None:
        return jsonify({"error": "unbekannter layer/sub-layer"}), 404
    return jsonify(out)


@app.route('/api/calendar')
def api_calendar():
    """
    Kalender-Daten für die Mitte/Canvas JEDER Kassette: laufende Woche ODER
    Monat um `ref`, fertig nach Tag gruppiert. Front-agnostisch — TUI, monolith
    und laptop rufen denselben Endpoint und zeichnen nur (wie /api/map/*). NICHT
    KI-gegatet: der Kalender ist hier reine Anzeige, kein KI-Tool-Pfad, läuft
    also auch in der ki-freien Kassette. Die Datums-Arithmetik (Woche Mo-So /
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
        out = kalender.week_view(ref)
        start = date.fromisoformat(out['start'])
        end = date.fromisoformat(out['end'])
        out['label'] = f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.%Y')}"

    out['view'] = view
    out['ref'] = ref.isoformat()
    out['today'] = date.today().isoformat()
    # Offene Kalender-Alarme mitschicken (gleiche Quelle wie die Canvas-Ecke),
    # damit die Front pro Tag/Header dezent warnen kann. Defensiv: nie crashen.
    try:
        out['alarms'] = state.get_alarms() or []
    except Exception:
        out['alarms'] = []
    return jsonify(out)


@app.route('/api/calendar/entry', methods=['POST'])
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
    conflicts = kalender.conflicts_for_proposed(layer, day, label, time=time)
    ok = kalender.add_entry(layer, day, label, time=time, **extras)
    if not ok:
        return jsonify({"error": "eintrag abgelehnt (unbekannter layer?)"}), 400
    return jsonify({"ok": True, "conflicts": conflicts})


@app.route('/api/calendar/entry', methods=['DELETE'])
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


@app.route('/api/calendar/entry', methods=['PUT'])
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


@app.route('/api/calendar/routine/skip', methods=['POST'])
def api_calendar_routine_skip():
    """
    Einen EINZELNEN Routine-Termin deaktivieren bzw. wieder aktivieren
    (reversibel, pro Vorkommen) — über core/kalender.py:set_routine_skip. NICHT
    KI-gegatet (direkte Nutzeraktion). Body: {layer, label, day, off=true}.
    `off=true` deaktiviert, `off=false` aktiviert wieder. Antwort {changed:bool}.
    """
    body = request.get_json(silent=True) or {}
    layer = (body.get('layer') or 'routinen').strip() or 'routinen'
    label = (body.get('label') or '').strip()
    day = (body.get('day') or '').strip()
    if not label or not day:
        return jsonify({"error": "label und day nötig"}), 400
    off = body.get('off', True)
    changed = kalender.set_routine_skip(layer, label, day, off=bool(off))
    return jsonify({"changed": changed})


@app.route('/api/debug', methods=['POST'])
def api_debug():
    """
    Temporärer Debug-Endpoint (2026-06-01): Frontend kann beliebige JSON
    hierhin POSTen, landet zeilenweise in /tmp/zentrale_debug.log. Wird
    nur fürs Mic-Debugging gebraucht und sollte danach wieder raus.
    """
    payload = request.get_json(silent=True) or {}
    with open('/tmp/zentrale_debug.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps({"t": datetime.now().isoformat(), **payload}, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})


@app.route('/api/log', methods=['POST'])
def api_log():
    """
    Speichert einen neuen Data-Collection-Eintrag auf Disk.

    Erwartet JSON: {"category": "sleep_quality", "data": {"date": "...", "quality": 3}}
    Anhängt den Eintrag an data/<category>.json (erstellt die Datei wenn nötig).
    """
    entry       = request.get_json()
    category_id = entry.get('category')
    data        = entry.get('data', {})

    os.makedirs(_DATA_DIR, exist_ok=True)  # data/ erstellen falls noch nicht vorhanden
    log_file = os.path.join(_DATA_DIR, f'{category_id}.json')

    # Bestehende Einträge laden (oder leere Liste starten)
    logs = []
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)

    # Neuen Eintrag mit Zeitstempel anhängen und zurückschreiben
    logs.append({**data, 'logged_at': datetime.now().isoformat()})
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

    state.push_log(f"LOGGED: {category_id} → {data}")
    return jsonify({"ok": True})


# ── Fotos (Quelle für den ASCII-Bild-Filter) ──────────────────────────
#
# Bilder werden LOKAL vom Backend serviert (gleicher Origin wie das
# Dashboard), nicht direkt vom Netz geladen. Grund: nur same-origin-Bilder
# darf der Browser-Canvas per getImageData() auslesen - sonst ist der
# Canvas "tainted" und der ASCII-Filter (canvasToAscii) bekommt keine
# Pixel. Ordner per Env überschreibbar; Default data/photos/.
# (Das ist zugleich der erste echte Baustein von "Fotos zeigen".)

_PHOTO_DIR = os.environ.get(
    "ZENTRALE_PHOTO_DIR",
    os.path.join(_DATA_DIR, "photos"),
)
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


@app.route('/api/photos')
def api_photos():
    """Liste der verfügbaren Bild-Dateinamen (sortiert). Leere Liste wenn kein Ordner."""
    if not os.path.isdir(_PHOTO_DIR):
        return jsonify([])
    names = [f for f in sorted(os.listdir(_PHOTO_DIR))
             if f.lower().endswith(_PHOTO_EXTS)]
    return jsonify(names)


@app.route('/api/photos/<path:name>')
def api_photo_file(name):
    """
    Liefert eine einzelne Bild-Datei aus _PHOTO_DIR aus.
    send_from_directory schützt gegen Path-Traversal (../) - der Name darf
    den Ordner nicht verlassen.
    """
    return send_from_directory(_PHOTO_DIR, name)


# ── AI / Chat ──────────────────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    Nimmt eine Chat-Nachricht entgegen und streamt die AI-Antwort Token für Token.

    Antwortet als SSE (Server-Sent Events) – ein HTTP-Standard für Push-Streams.
    SSE-Format: jede Nachricht ist eine Zeile "data: <inhalt>\\n\\n"
    Der Browser liest den Stream mit der Fetch ReadableStream API.

    Ablauf:
      1. User-Nachricht in state.py speichern
      2. Chat-History holen (inkl. neuer Nachricht)
      3. Generator starten – ai.chat_stream() liefert Token für Token
      4. Jeden Token als SSE-Event an den Browser schicken
      5. Nach dem letzten Token: komplette Antwort in state.py speichern
         + "done"-Event schicken damit der Browser weiß dass es vorbei ist

    stream_with_context() ist Flask-spezifisch: es stellt sicher dass der
    Flask-Request-Context (für g, session etc.) im Generator noch verfügbar ist.
    """
    if kassette.ki_aus():
        return _ki_aus()
    body    = request.get_json()
    message = (body.get('message') or '').strip()
    # via_mic-Flag aus dem Body. True bedeutet: diese Message kam aus
    # Whisper-Transkription, nicht aus Tastatur. Wird an chat_stream()
    # durchgereicht, das daraus einen Mic-Hint an den System-Prompt
    # haengt - damit die KI bei Transkriptionsfehlern nachfragen kann
    # statt woertlich zu antworten. Default False fuer alle Legacy-
    # Clients die das Feld nicht mitschicken.
    via_mic = bool(body.get('via_mic', False))
    if not message:
        return jsonify({"error": "no message"}), 400

    state.push_chat_message("user", message)
    history = state.get_chat_history()

    def generate():
        # Tokens sammeln um am Ende die komplette Antwort zu speichern
        collected = []

        for token in ai.chat_stream(history, via_mic=via_mic):
            # zeige_ascii liefert ein Dict statt eines Text-Tokens: ein
            # Inline-Bild-Event. Es geht als eigenes SSE-Event 'ascii' raus
            # und NICHT in collected - es ist kein Antworttext, wird also
            # weder gesprochen noch in der History gespeichert.
            if isinstance(token, dict) and 'ascii' in token:
                yield f"data: {json.dumps({'ascii': token['ascii'], 'name': token.get('name')})}\n\n"
                continue
            # permission-Event: ein bestätigungspflichtiges Tool wurde abgefangen
            # und chat_stream blockiert jetzt (state.wait_permission). Frage als
            # SSE 'permission'-Event raus - das Frontend tauscht daraufhin die
            # Konsolen-Eingabe gegen JA/NEIN-Knöpfe und POSTet die Wahl an
            # /api/permission_answer, was den Stream hier wieder entsperrt. Kein
            # Antworttext → nicht in collected (nicht in die History-Schlussantwort).
            if isinstance(token, dict) and 'permission' in token:
                yield f"data: {json.dumps({'permission': token['permission']})}\n\n"
                continue
            # cinema-Event: eine News-Sendung beginnt (lies_news lief). Reines
            # UI-Signal (Sendungs-/Untertitel-Modus), kein Antworttext → nicht
            # in collected.
            if isinstance(token, dict) and 'cinema' in token:
                yield f"data: {json.dumps({'cinema': True})}\n\n"
                continue
            collected.append(token)
            # SSE-Format: "data: " + JSON + zwei Newlines
            # JSON.dumps schützt vor Sonderzeichen (Newlines im Token, etc.)
            yield f"data: {json.dumps({'token': token})}\n\n"

        # Komplette Antwort in state speichern (für History beim nächsten Öffnen)
        state.push_chat_message("assistant", "".join(collected))

        # Abschluss-Signal für den Browser
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            # Verhindert dass nginx/proxies den Stream puffern
            # (auf dem Pi ohne Proxy egal, aber schadet nicht)
            'X-Accel-Buffering': 'no',
        },
    )


@app.route('/api/chat/history')
def api_chat_history():
    """Gibt die aktuelle Chat-History zurück (für initiales Laden der Chat-View)."""
    if kassette.ki_aus():
        return jsonify([])   # Laptop-Kassette: kein Chat
    return jsonify(state.get_chat_history())


@app.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """Löscht die gesamte Chat-History (per /clear Befehl im Chat-Input)."""
    state.clear_chat_history()
    return jsonify({"ok": True})


@app.route('/api/permission_answer', methods=['POST'])
def api_permission_answer():
    """
    Nimmt die Ja/Nein-Antwort auf eine Erlaubnis-Rückfrage (Tool-Gate) entgegen.

    Die KI blockiert gerade in einem offenen /api/chat-Stream (in einem
    anderen Thread) auf state.wait_permission(). Dieser Request kommt vom
    Klick auf die JA/NEIN-Knöpfe, liefert die Wahl und entsperrt damit den
    wartenden Generator - der streamt dann den Rest der Antwort auf der
    bereits offenen SSE-Verbindung weiter. Funktioniert nur weil Flask
    multi-threaded läuft (siehe app.run(threaded=True) ganz unten).
    """
    if kassette.ki_aus():
        return _ki_aus()
    body    = request.get_json(silent=True) or {}
    answer  = (body.get('answer') or '').strip()
    # Gegen die aktuell angebotenen Knopf-Labels validieren (case-insensitiv,
    # aber das kanonische Label aus state durchreichen - so kommt z.B. "ja"
    # immer als "ja" beim Gate-Check an, egal wie das Frontend es schickt).
    options = state.get_permission_options()
    match   = next((o for o in options if o.lower() == answer.lower()), None)
    if match is None:
        return jsonify({"error": f"answer must be one of {options}"}), 400
    state.answer_permission(match)
    return jsonify({"ok": True})


# /api/memory und /api/memory/<id> entfielen mit dem Legacy-LTM-Pfad.
# Graph-Stats werden über graph.stats() bzw. den Konzept-Browser
# bereitgestellt (siehe ki_system.md).


@app.route('/api/ai/status')
def api_ai_status():
    """
    Prüft ob Ollama erreichbar ist und gibt Status + Konfiguration zurück.
    Wird vom Dashboard alle 30s gecheckt und als Statusanzeige genutzt.
    """
    if kassette.ki_aus():
        # KI-freie Kassette (laptop/tui): KI ist nicht "unerreichbar", sondern
        # bewusst aus. Ollama wird hier NICHT angepingt (ai.is_available() würde
        # einen HTTP-Call absetzen) – wir antworten direkt deaktiviert.
        return jsonify({"available": False, "url": None, "model": "—", "kassette": kassette.name()})
    return jsonify({
        "available": ai.is_available(),
        "url":       ai.OLLAMA_URL,
        "model":     ai.OLLAMA_MODEL,
    })


# ── Voice-Pipeline (sprachneutral) ─────────────────────────────────────
#
# Diese Endpoints sind die generische Voice-API der ZENTRALE. Sie
# nehmen einen `lang`-Parameter entgegen und reichen ihn an die
# Audio-Services durch. Welche Sprachen wirklich funktionieren, haengt
# vom geladenen TTS-/Whisper-Modell ab (siehe services/tts_service.py
# bzw. WHISPER_LANG-env in services/whisper_service.py).
#
# Die frueheren Tutor-Aliase (/api/tutor/speak, /api/tutor/transcribe)
# sind raus – der Mandarin-Tutor ist pausiert (siehe
# memory/tutor_system.md). Wer Mandarin sprechen will, ruft die
# generische API mit `lang='zh'` auf.


@app.route('/api/speak', methods=['POST'])
def api_speak():
    """
    Text -> WAV. Sprachneutral.

    Body (JSON):
      text     – Pflichtfeld
      lang     – Sprachcode (default 'de' via DEFAULT_LANG in core/audio.py)
      speed    – Sprechgeschwindigkeit (default 1.2 = ZENTRALE-Chat; 1.0 natuerlich, <1.0 langsamer)
      speaker  – Sprecher-ID (default 0; bedeutung modellabhaengig)

    Response: audio/wav, oder 503 wenn das Modell fuer die Sprache fehlt.
    """
    if kassette.ki_aus():
        return _ki_aus()
    body    = request.get_json() or {}
    text    = (body.get('text') or '').strip()
    lang    = (body.get('lang') or '').strip() or None
    speed   = float(body.get('speed', 1.2))
    speaker = int(body.get('speaker', 0))

    if not text:
        return jsonify({"error": "kein Text"}), 400

    wav = audio.synthesize(text, lang=lang, speed=speed, speaker=speaker)
    if not wav:
        # core/audio.py loggt den Grund. Wir geben dem Browser einen
        # einfachen 503 zurueck – das Mini-Log zeigt die Details.
        return jsonify({"error": "TTS nicht verfuegbar"}), 503

    return Response(wav, content_type='audio/wav')


@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """
    Audio (WAV) -> Text. Sprachneutral.

    multipart/form-data:
      audio    – WAV-Datei (Pflichtfeld)
      lang     – Sprachcode (default 'de'). Wird als Whisper-Hint genutzt.

    Response: JSON {"text": "..."}.
    """
    if kassette.ki_aus():
        return _ki_aus()
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld"}), 400

    audio_bytes = request.files['audio'].read()
    lang        = (request.form.get('lang') or '').strip() or None
    text        = audio.transcribe(audio_bytes, lang=lang)
    return jsonify({"text": text})


# ── Tutor ─────────────────────────────────────────────────────────────
#
# Mandarin-Sprachtutor: Addon auf der Core-KI mit EIGENEM System-Prompt
# (_TUTOR_PROMPT) und EIGENEM Tool-Set (TUTOR_TOOLS), sauber getrennt vom
# regulaeren Chat (siehe core/tutor_session.py + core/tutor.py).
#
# Start ist rein MANUELL ueber die Dashboard-Taste 'T' → POST /api/tutor/start.
# Es gibt KEINEN Presence-Auto-Trigger in brain.py (bewusst: erst Core-KI
# sauber, dann Addon – siehe memory/tutor_system.md).
#
# Audio laeuft ueber die generische Voice-API (/api/transcribe, /api/speak)
# mit lang='zh' – der Tutor besitzt die Pipeline nicht, er ruft sie nur auf.


@app.route('/api/tutor/status')
def api_tutor_status():
    """Gibt zurueck ob gerade eine Tutor-Session aktiv ist + Audio-Service-Status.
    privacy_warning != null → Provider trainiert auf Daten: im UI laut anzeigen."""
    return jsonify({
        "active":         tutor_session.is_active(),
        "whisper":        audio.whisper_available(),
        "tts":            audio.tts_available(),
        "privacy_warning": tutor_session.privacy_notice(),
    })


@app.route('/api/tutor/config', methods=['GET', 'POST'])
def api_tutor_config():
    """Liest/aendert die Live-Tutor-Konfiguration (Sprache/Provider/Modell) –
    so kann man das Modell IN ZENTRALE direkt umschalten, ohne Datei-Editieren.

    POST-Body (JSON, alle optional): {lang, provider, model, history_window, persist}.
    persist=true schreibt zusaetzlich in data/tutor_config.json (ueberlebt Neustart),
    sonst gilt der Wechsel nur fuer die laufende Instanz.
    GET liefert die aktuelle Aufloesung + waehlbare Provider/Sprachen.
    """
    if request.method == 'POST':
        body    = request.get_json() or {}
        persist = bool(body.get('persist'))
        for k in ('lang', 'provider', 'model', 'history_window'):
            if k in body:
                tutor_config.set_override(k, body[k], persist=persist)

    prof, pname, prov, model = tutor_session._resolve()
    return jsonify({
        "lang":           tutor_config.setting("lang", "zh"),
        "lang_name":      prof["name"],
        "provider":       pname,
        "model":          model,
        "trains_on_data": tutor_providers.trains_on_data(pname),
        "providers": [
            {"name": n, "default_model": p.get("default_model"),
             "trains_on_data": tutor_providers.trains_on_data(n),
             "jurisdiction": p.get("jurisdiction"), "enabled": p.get("enabled")}
            for n, p in tutor_providers.PROVIDERS.items()
        ],
        "langs": [
            {"code": c, "name": p["name"], "enabled": p.get("enabled")}
            for c, p in tutor_langs.PROFILES.items()
        ],
    })


@app.route('/api/tutor/start', methods=['POST'])
def api_tutor_start():
    """
    Startet eine Tutor-Session manuell (Dashboard-Taste 'T') und streamt die
    erste KI-Begruessung. Die KI laedt zu Beginn selbst die Vokabeln via
    get_confirmed_vocab()/get_testing_vocab() (Tool-Calls) und begruesst auf
    Mandarin.
    """
    if kassette.ki_aus():
        return _ki_aus()

    if not tutor_session.is_active():
        tutor_session.activate()

    def generate():
        # user_text=None → KI beginnt das Gespraech
        for token in tutor_session.respond_stream(user_text=None):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/tutor/respond', methods=['POST'])
def api_tutor_respond():
    """
    Nimmt transkribierten Text entgegen, schickt ihn an die KI (Tutor-Modus)
    und streamt die Antwort zurueck. Body: JSON {"text": "我很好"}.
    """
    if kassette.ki_aus():
        return _ki_aus()
    if not tutor_session.is_active():
        return jsonify({"error": "Keine aktive Tutor-Session"}), 400

    body      = request.get_json() or {}
    user_text = (body.get('text') or '').strip()
    if not user_text:
        return jsonify({"error": "kein Text"}), 400

    def generate():
        for token in tutor_session.respond_stream(user_text=user_text):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/api/tutor/stop', methods=['POST'])
def api_tutor_stop():
    """Beendet die aktive Tutor-Session."""
    tutor_session.deactivate()
    return jsonify({"ok": True})


# ── Start ──────────────────────────────────────────────────────────────

def start_ui(host='0.0.0.0', port=5000):
    """
    Startet den Flask-Server. Wird von main.py als Background-Thread gestartet.

    host='0.0.0.0' = auf allen Netzwerk-Interfaces lauschen (auch Pi → Browser im LAN)
    debug=False     = kein Debug-Modus (würde Threading-Probleme machen)
    use_reloader=False = kein Auto-Reload (läuft ja als Thread, kein eigener Prozess)
    threaded=True   = jeder Request einen eigenen Worker-Thread. Ist zwar Flasks
                      Default, aber wir setzen es EXPLIZIT, weil die Erlaubnis-
                      Rückfrage zwingend darauf baut: ein /api/chat-Stream
                      blockiert in state.wait_permission(), während parallel der
                      POST /api/permission_answer durchkommen muss, um ihn zu
                      wecken. Ohne Threading → Deadlock.
    """
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
