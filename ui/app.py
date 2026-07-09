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
import notes        # type: ignore  – Notiz-Registry (Text-/Listen-/Float-Blöcke, TUI-Werkzeug)
import kalender     # type: ignore  – Kalender-Layer (Woche/Monat, data/ai_calendar.json)
import ai           # type: ignore
import audio        # type: ignore
import tutor_session # type: ignore  – Sprach-Tutor (Addon auf der Core-KI, eigener Prompt/Tools)
import tutor_config   # type: ignore  – lokale Tutor-Config + Live-Umschalten (Provider/Modell)
import tutor_providers # type: ignore  – Provider-Registry (Flags, Liste)
import tutor_langs     # type: ignore  – Sprach-Profile (Liste)
import ai_backends     # type: ignore  – AI-Backend-Verfügbarkeit (local/cloud, EXTERNAL-Box)
import consolidation # type: ignore  – Phase E: STM → LTM Konsolidierung
import telemetry    # type: ignore  – PC-Host-Telemetrie (CPU/GPU/VRAM/Temp/RAM)
import kassette     # type: ignore  – welche Kassette läuft (monolith | laptop)
import mail         # type: ignore  – Mail-Triage (read-only Panel + Live-Poll)
import mail_secrets # type: ignore  – verschlüsselter Zugangsdaten-Speicher
import threading    # für den Hintergrund-Poll (blockiert den Request nicht)
import time         # für das Alter des Live-Ordnerzähl-Caches
from map import base_features as map_base_features  # type: ignore  – Maps-System (core/map/)
from map import base_braille as map_base_braille  # type: ignore  – Maps-System (Braille-Füllung)
from map import layers as map_layers  # type: ignore  – Overlay-Layer (Achse 2, Handelsrouten)
from map import country_outlines as map_country_outlines  # type: ignore  – Länder-Auswahl (TUI)

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


# Tutor-spezifisch: NICHT kassetten-hart, sondern kapazitaetsbasiert. Der Tutor
# laeuft, sobald das Backend seines Providers da ist (lokal ODER cloud) – auch
# auf laptop/tui. Fehlt es, sagen wir das ehrlich ("backend not here").
def _tutor_unavail():
    return jsonify({"error": "backend not here",
                    "detail": "Tutor-Backend nicht erreichbar (Provider-Backend fehlt "
                              "oder Cloud gedrosselt)."}), 503


# ── Dashboard ─────────────────────────────────────────────────────────

@app.route('/')
@app.route('/monolith')   # Alias: alte Kiosk-/Bookmark-/Deeplink-URL bleibt gueltig
def index():
    """
    Liefert das EINE Dashboard-Template (monolith.html) für alle Browser-Fronten.
    Der Unterschied zwischen den Kassetten (core/kassette.py) ist allein der
    ki_aus-Flag, den wir hier ans Template durchreichen:
      - monolith (Default): voll, mit KI-Kern (Chat, Audio, News).
      - laptop / tui:       ki_aus=True → die KI-Blöcke werden nicht gerendert,
                            stattdessen erscheint unten die Shortcut-Übersicht.
    Die Wahl kommt aus ZENTRALE_KASSETTE, gesetzt vom Start-Befehl. /monolith
    bleibt als Alias bestehen, damit der Pi-Kiosk und alte Bookmarks nicht brechen.

    Statische Assets (engine.js = Daten-Adapter, viz.js, ascii.js, fonts/) liegen
    in ui/static/ und werden von Flask automatisch unter /static/<file> bedient.
    """
    resp = render_template(kassette.template(),
                           ki_aus=kassette.ki_aus(),
                           kassette=kassette.name())
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
    Body (JSON): {"name": "Gewicht", "type": "number"|"scale", "unit": "kg",
                  "remind": true|false, "remind_at": "HH:MM"}
    remind/remind_at optional → Tages-Reminder gleich beim Anlegen mitgeben.
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.create_graph(body.get('name'), body.get('type', 'number'), body.get('unit', ''),
                                remind=bool(body.get('remind')), remind_at=body.get('remind_at', ''))
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


@app.route('/api/graphs/<gid>/predict', methods=['POST'])
def api_graphs_set_predict(gid):
    """
    Vorhersage-Flag eines Graphen setzen/löschen — steuert, ob die lifestyle-Box
    fehlende Tage aus dem Schnitt schätzt (blass/schraffiert). Default aus.
    Body (JSON): {"predict": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.set_predict(gid, bool(body.get('predict')))
    except KeyError:
        return jsonify({"error": "unbekannter graph"}), 404
    state.push_log(f"GRAPH~predict {'an' if g.get('predict') else 'aus'}: {gid}")
    return jsonify(g)


@app.route('/api/graphs/<gid>/remind', methods=['POST'])
def api_graphs_set_remind(gid):
    """
    Tages-Reminder eines Graphen setzen/löschen. Ab `at` erinnern die Fronten
    täglich ans Eintragen, bis für den Tag ein Wert da ist. Default aus.
    Body (JSON): {"remind": true|false, "at": "HH:MM"} (at optional → unverändert)
    """
    body = request.get_json(silent=True) or {}
    try:
        g = graphs.set_remind(gid, bool(body.get('remind')), body.get('at'))
    except KeyError:
        return jsonify({"error": "unbekannter graph"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"GRAPH~remind {('an ' + g.get('remind_at', '')) if g.get('remind') else 'aus'}: {gid}")
    return jsonify(g)


@app.route('/api/graphs/reminders')
def api_graphs_reminders():
    """
    Graphen mit JETZT fälligem Tages-Reminder (remind an, Uhrzeit erreicht, heute
    noch nicht geloggt). Geteilte Quelle: monolith/laptop ziehen daraus das
    »bitte eintragen«-Modal, die TUI ihren Nag. Liefert [{id, name, remind_at}].
    """
    return jsonify(graphs.due_reminders())


# ── Listen (dynamisch, vom Dashboard angelegt) ─────────────────────────
#
# Pendant zu den Lifestyle-Graphen, aber für abhakbare Todo-/Sammel-Listen.
# Anders als die Graphen liegen Definition UND Einträge inline in
# data/lists.json (core/lists.py) – keine Zeitreihe, kein /api/log-Sharing.

@app.route('/api/lists')
def api_lists():
    """Alle Listen-Definitionen inkl. ihrer Einträge."""
    return jsonify(lists.list_lists())


@app.route('/api/projects')
def api_projects():
    """
    Als Projekt markierte KNOTEN (Listen UND Einträge) als VERSCHACHTELTER Baum:
    geflaggte Top-Level-Liste = Wurzel, ihre geflaggten Unter-Einträge hängen
    rekursiv als `children` darunter (`{id,name,done,total,children:[…]}`).
    Quelle für die PROJECTS-Box in ALLEN Fronten — die Fortschrittslogik bleibt
    an einer Stelle (core/lists), die Fronten rendern nur. Ein Knoten ohne
    children → normal (Titel+Leiste), mit children → gerahmter Kasten.
    NICHT KI-gegatet (gibt es in allen Kassetten).
    """
    return jsonify(lists.projects_tree())


@app.route('/api/projects/focused')
def api_projects_focused():
    """
    Der aktuell fokussierte Projekt-Teilbaum (voller Knoten inkl. children /
    Fortschritt) — oder null. QUELLE DER FOCUS-BOX in allen Fronten: die zeigt
    NUR noch dieses eine Projekt (oder nichts). Die volle Projekt-Übersicht gibt
    es ausschließlich über /api/projects (die neue Projektansicht der TUI).
    NICHT KI-gegatet (gibt es in allen Kassetten).
    """
    return jsonify(lists.focused_subtree())


@app.route('/api/projects/focus', methods=['GET', 'POST'])
def api_projects_focus():
    """
    Projekt-FOKUS: genau EIN Projekt allein am Rand rendern.
    GET  → das aktuell fokussierte Projekt `{lid,iid,name}` oder null.
    POST → Fokus setzen (Toggle) bzw. löschen. Quelle für die »Projektansicht«
    der TUI (Taste 'f'); ist ein Fokus gesetzt, zeigen die Fronten in der
    PROJECTS-Box NUR dieses Projekt. Höchstens einer gleichzeitig.
    Body (JSON): {"lid": "...", "iid": 3|null}  → diesen Knoten togglen
                 {"clear": true}                 → Fokus ganz aus
    """
    if request.method == 'GET':
        return jsonify(lists.get_focus())
    body = request.get_json(silent=True) or {}
    if body.get('clear'):
        lists.clear_focus()
        state.push_log("FOKUS-: (aus)")
        return jsonify(None)
    lid = body.get('lid')
    if not lid:
        return jsonify({"error": "lid fehlt"}), 400
    iid = body.get('iid')
    try:
        foc = lists.set_focus(lid, iid if iid is not None else None)
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"FOKUS{'+' if foc else '-'}: {lid}" + (f"/{iid}" if iid is not None else ""))
    return jsonify(foc)


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


@app.route('/api/lists/<lid>/project', methods=['POST'])
def api_lists_set_project(lid):
    """
    Projekt-Flag einer Liste setzen/löschen — bestimmt, ob sie in der
    PROJECTS-Box der Fronten erscheint.
    Body (JSON): {"project": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        lst = lists.set_project(lid, bool(body.get('project')))
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    state.push_log(f"PROJEKT{'+' if lst.get('project') else '-'}: {lid}")
    return jsonify(lst)


@app.route('/api/lists/<lid>/items/<int:iid>/project', methods=['POST'])
def api_lists_set_item_project(lid, iid):
    """
    Projekt-Flag auf einem Eintrag setzen/löschen (Pendant zu /project für
    Listen — jeder Knoten ist als Projekt markierbar).
    Body (JSON): {"project": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        it = lists.set_item_project(lid, iid, bool(body.get('project')))
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"PROJEKT{'+' if it.get('project') else '-'}: {lid}/{iid}")
    return jsonify(it)


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
    """Erledigt-Status eines Blatt-Eintrags umschalten. Ordner sind nicht
    direkt abhakbar (Status abgeleitet) → 400."""
    try:
        item = lists.toggle_item(lid, iid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
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


@app.route('/api/lists/<lid>/items/<int:iid>/reorder', methods=['POST'])
def api_lists_reorder_item(lid, iid):
    """
    Einen Eintrag INNERHALB seiner Geschwister-Ebene verschieben (Reihenfolge).
    Body (JSON): {"delta": -1|+1} — rauf/runter, geklemmt am Rand.
    """
    body = request.get_json(silent=True) or {}
    try:
        moved = lists.reorder_item(lid, iid, body.get('delta', 0))
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    return jsonify({"moved": bool(moved)})


@app.route('/api/lists/<lid>/items/<int:iid>', methods=['DELETE'])
def api_lists_delete_item(lid, iid):
    """Einen Eintrag aus einer Liste löschen."""
    try:
        lists.delete_item(lid, iid)
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    return jsonify({"ok": True})


# ── Notizen (dynamisch, vom Dashboard angelegt) ────────────────────────
#
# Freie Notizen aus gestapelten Blöcken (text/list/float), Inhalt inline in
# data/notes.json (core/notes.py). Aktuell nur vom TUI-Werkzeug bespielt; die
# Browser-Front kommt später. Dünner Adapter — alle Logik in core/notes.

@app.route('/api/notes')
def api_notes():
    """Übersicht aller Notizen (ohne Block-Inhalte), neueste zuerst."""
    return jsonify(notes.list_notes())


@app.route('/api/notes', methods=['POST'])
def api_notes_create():
    """Neue (leere) Notiz anlegen. Body (JSON): {"title": "..."} (optional)."""
    body = request.get_json(silent=True) or {}
    n = notes.create_note(body.get('title', ''))
    state.push_log(f"NOTIZ+: {n['id']}")
    return jsonify(n)


@app.route('/api/notes/<nid>')
def api_notes_get(nid):
    """Vollständige Notiz mit allen Blöcken."""
    n = notes.get_note(nid)
    if n is None:
        return jsonify({"error": "unbekannte notiz"}), 404
    return jsonify(n)


@app.route('/api/notes/<nid>', methods=['PUT'])
def api_notes_save(nid):
    """
    Notiz-Inhalt ersetzen. Body (JSON): {"title": "...", "blocks": [...]}.
    Beide Felder optional; nur übergebene werden angefasst. Blöcke werden
    serverseitig normalisiert (siehe core/notes._clean_blocks).
    """
    body = request.get_json(silent=True) or {}
    try:
        n = notes.save_note(nid, title=body.get('title'), blocks=body.get('blocks'))
    except KeyError:
        return jsonify({"error": "unbekannte notiz"}), 404
    return jsonify(n)


@app.route('/api/notes/<nid>', methods=['DELETE'])
def api_notes_delete(nid):
    """Notiz löschen."""
    notes.delete_note(nid)
    state.push_log(f"NOTIZ-: {nid}")
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


@app.route('/api/map/countries')
def api_map_countries():
    """
    Länder für die Auswahl/Fokussierung in einer Front: alle Länder-Mittelpunkte
    (für die Richtungs-Navigation) + der projizierte Umriss des fokussierten
    Landes (Border zum Zeichnen). Geo-Logik in core/map/render.country_outlines.

    Query: cx,cy,zoom,cols,rows,aspect wie /api/map/base; zusätzlich
           focus = Name des fokussierten Landes (für dessen Umriss).
    NICHT KI-gegatet (Karte gibt es in allen Kassetten).
    """
    a = request.args
    try:
        cx = float(a.get('cx', 0.0))
        cy = float(a.get('cy', 20.0))
        zoom = float(a.get('zoom', 0.0))
        cols = int(a.get('cols', 80))
        rows = int(a.get('rows', 30))
        aspect = float(a.get('aspect', 0.5))
    except (TypeError, ValueError):
        return jsonify({"error": "ungültige map-parameter"}), 400
    return jsonify(map_country_outlines(cx, cy, zoom, cols, rows, aspect,
                                        a.get('focus') or None))


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


@app.route('/api/calendar/entry/spantime', methods=['POST'])
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


@app.route('/api/calendar/routine/skip', methods=['POST'])
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


@app.route('/api/calendar/routine', methods=['POST'])
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


@app.route('/api/calendar/routine', methods=['DELETE'])
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
    upsert      = bool(entry.get('upsert'))   # True → Eintrag mit gleichem Datum ersetzen

    os.makedirs(_DATA_DIR, exist_ok=True)  # data/ erstellen falls noch nicht vorhanden
    log_file = os.path.join(_DATA_DIR, f'{category_id}.json')

    # Bestehende Einträge laden (oder leere Liste starten)
    logs = []
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)

    # upsert: vorhandene Einträge desselben Datums entfernen (Nachtragen/Ändern
    # im Graph-Werkzeug soll genau EINEN Eintrag pro Tag halten, kein Duplikat).
    if upsert and data.get('date') is not None:
        logs = [e for e in logs if not (isinstance(e, dict) and e.get('date') == data['date'])]

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
    # Lokal-Drossel (Pendant zum Cloud-Kill-Switch): bewusst aus → hier hart
    # abriegeln, damit die Drossel wirklich drosselt (nicht nur die Anzeige).
    if not ai_backends.local_enabled():
        return jsonify({"error": "lokale KI gedrosselt"}), 503
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
            # reflect-Event: ein Stück des Denk-/Reflexions-Stroms (Ollama
            # `thinking`-Feld). Geht als eigenes SSE 'reflect'-Event raus, das
            # das Frontend im ki-kern live mitlaufen lässt ("ich schau kurz
            # nach…"). KEIN Antworttext → nicht in collected (nicht gespeichert,
            # nicht gesprochen). Siehe ai.chat_stream / adaptives Thinking.
            if isinstance(token, dict) and 'reflect' in token:
                yield f"data: {json.dumps({'reflect': token['reflect']})}\n\n"
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
    # TTS ist LOKALE Synthese (sherpa/Piper) und der Sprach-Tutor laeuft
    # kapazitaetsbasiert ueber die Cloud – unabhaengig von der lokalen KI-Kassette.
    # Nur blocken, wenn AUCH der Tutor kein Backend hat; sonst kriegt die Persona-
    # Stimme keinen Ton, obwohl der Tutor laeuft (verifiziert: /api/speak gab 503
    # 'KI in dieser Kassette deaktiviert', obwohl der Cloud-Tutor verfuegbar war).
    if kassette.ki_aus() and not tutor_session.available():
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
    # STT ist lokale Erkennung; der Sprach-Tutor laeuft kapazitaetsbasiert. Nur
    # blocken, wenn AUCH der Tutor kein Backend hat — sonst kann das Persona-
    # Zimmer nicht zuhoeren, obwohl der Tutor laeuft (wie bei /api/speak).
    if kassette.ki_aus() and not tutor_session.available():
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
    privacy_warning != null → Provider trainiert auf Daten: im UI laut anzeigen.
    available = ist das aufgeloeste Backend (ollama vs cloud) gerade erreichbar?
    → Fronten (TUI/Browser) koennen ohne Start-Versuch zeigen, ob der Tutor geht
    (sonst z.B. toter Smiley statt Fehler beim /start)."""
    return jsonify({
        "active":         tutor_session.is_active(),
        "available":      tutor_session.available(),
        "whisper":        audio.whisper_available(),
        "tts":            audio.tts_available(),
        "privacy_warning": tutor_session.privacy_notice(),
    })


@app.route('/api/ai/backends', methods=['GET', 'POST'])
def api_ai_backends():
    """Welche AI-Backends sind auf diesem Geraet erreichbar (local/cloud)?
    Speist die EXTERNAL-Box + das kapazitaetsbasierte Modul-Gating.

    POST {cloud_enabled: bool} legt den Cloud-Kill-Switch um (Datenschutz-/
    Kosten-Drossel), {local_enabled: bool} den Lokal-Kill-Switch (drosselt die
    lokale Ollama-Leitung) – beide persistiert in data/tutor_config.json. GET
    liefert Status inkl. cloud_enabled/local_enabled. Frisch nach Toggle."""
    if request.method == 'POST':
        body = request.get_json() or {}
        if 'cloud_enabled' in body:
            ai_backends.set_cloud_enabled(bool(body['cloud_enabled']))
        if 'local_enabled' in body:
            ai_backends.set_local_enabled(bool(body['local_enabled']))
        return jsonify(ai_backends.status(fresh=True))
    return jsonify(ai_backends.status())


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
        "persona_name":   prof.get("persona_name", prof["name"]),
        "country":        prof.get("country", ""),
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
            {"code": c, "name": p["name"], "enabled": p.get("enabled"),
             "persona_name": p.get("persona_name", p["name"]),
             "country": p.get("country", "")}
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
    if not tutor_session.available():
        return _tutor_unavail()

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
    if not tutor_session.available():
        return _tutor_unavail()
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


@app.route('/api/tutor/room_state')
def api_tutor_room_state():
    """Aktueller Ausdrucks-Zustand der Persona (Haltung/Geste) fuers Zimmer-
    Fenster. Leichtgewichtig — das Fenster pollt das ein paar Mal pro Sekunde.
    Die Werte setzt die KI selbst ueber das express-Tool."""
    return jsonify(tutor_session.room_state())


@app.route('/api/tutor/nudge', methods=['POST'])
def api_tutor_nudge():
    """Stille-Anstoss: Sasha hat eine Weile nichts gesagt → die Persona reagiert
    von selbst (schauen/winken/kurz nachfragen). Das Zimmer-Fenster loest das
    gedeckelt aus (einmal, dann Ruhe; alle ~15 min erneut). Streamt wie /respond;
    der Anstoss-Text wird NICHT in der History gespeichert."""
    if not tutor_session.available():
        return _tutor_unavail()
    if not tutor_session.is_active():
        return jsonify({"error": "Keine aktive Tutor-Session"}), 400

    def generate():
        for token in tutor_session.respond_stream(nudge=True):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ── Mail-Triage (read-only Panel + expliziter Live-Poll) ────────────────
# Das Panel selbst ist KEY-FREI: Kategorie-Übersicht + Mails lesen nur den
# lokalen Triage-Stand (data/mail_state.json, unverschlüsselt). Die Passphrase
# (Env ODER OS-Keyring) braucht NUR der Live-Poll, der echte IMAP-Aktionen tut.

_mail_poll_lock = threading.Lock()
_mail_poll_running = {"on": False}

_mail_reconcile_lock = threading.Lock()
_mail_reconcile_running = {"on": False}

# Cache der LIVE-Ordnerzählung (IMAP STATUS). Wird nicht-blockierend im
# Hintergrund aufgefrischt (POST /api/mail/refresh-counts) und von /api/mail
# nur GELESEN — so bleibt das Panel schnell, während die echten Zahlen
# nachtröpfeln. {kat: anzahl}; leer, solange noch nie/ohne Key aufgefrischt.
# PERSISTIERT auf Disk (data/mail_counts.json): sonst zeigt das Panel nach jedem
# Backend-Neustart erst den mageren lokalen Schnappschuss (nur letzte ~200 Mails
# → z.B. „171") und muss die echten Zahlen (z.B. 1000+) neu ersweepen. Mit
# Persistenz stehen die letzten ECHTEN Zahlen sofort da; die TTL frischt sie
# danach im Hintergrund einmal auf.
_mail_live = {"counts": {}, "ts": 0.0, "refreshing": False}
_mail_live_lock = threading.Lock()
_MAIL_COUNTS_FILE = os.path.join(_DATA_DIR, "mail_counts.json")


def _mail_counts_load():
    """Zuletzt persistierte Live-Zahlen beim Start in den Cache holen (best
    effort — fehlt/kaputt die Datei, bleibt der Cache einfach leer)."""
    try:
        with open(_MAIL_COUNTS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d.get("counts"), dict):
            _mail_live["counts"] = d["counts"]
            _mail_live["ts"] = float(d.get("ts") or 0.0)
    except Exception:
        pass


def _mail_counts_save():
    """Den frischen Zähl-Stand atomar auf Disk schreiben (überlebt Neustart)."""
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = _MAIL_COUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"counts": _mail_live["counts"], "ts": _mail_live["ts"]},
                      f, ensure_ascii=False)
        os.replace(tmp, _MAIL_COUNTS_FILE)
    except Exception as e:
        state.push_log(f"MAIL: Zähl-Cache speichern — {type(e).__name__}: {e}")


_mail_counts_load()


# ── Ordner-Inhalts-Cache (Header-Listen je Kategorie) ────────────────────
# Jeder Ordner-Aufruf machte bisher einen vollen IMAP SELECT+SEARCH+FETCH → das
# spürbare „lädt ordner…" bei JEDEM Öffnen. Jetzt: den Inhalt je Kategorie cachen,
# beim Öffnen SOFORT aus dem Cache liefern und (erst wenn abgelaufen) im Hinter-
# grund auffrischen. Persistiert auf Disk (data/mail_folders.json) → auch das
# erste Öffnen nach Neustart ist instant. {cat: {"mails":[...], "ts":float}}.
_mail_folders = {}
_mail_folders_lock = threading.Lock()
_mail_folders_refreshing = set()
_MAIL_FOLDERS_FILE = os.path.join(_DATA_DIR, "mail_folders.json")


def _mail_folders_load():
    try:
        with open(_MAIL_FOLDERS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for cat, ent in d.items():
                if isinstance(ent, dict) and isinstance(ent.get("mails"), list):
                    _mail_folders[cat] = {"mails": ent["mails"],
                                          "ts": float(ent.get("ts") or 0.0)}
    except Exception:
        pass


def _mail_folders_save():
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with _mail_folders_lock:
            snap = {c: {"mails": e["mails"], "ts": e["ts"]}
                    for c, e in _mail_folders.items()}
        tmp = _MAIL_FOLDERS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, _MAIL_FOLDERS_FILE)
    except Exception as e:
        state.push_log(f"MAIL: Ordner-Cache speichern — {type(e).__name__}: {e}")


_mail_folders_load()


def _folder_fetch_store(cat):
    """Ordner-Inhalt LIVE holen und in Cache + auf Disk ablegen; gibt die
    Mail-Liste zurück."""
    mails = mail.folder_mails(cat, limit=200)
    with _mail_folders_lock:
        _mail_folders[cat] = {"mails": mails, "ts": time.time()}
    _mail_folders_save()
    return mails


def _folder_refresh_async(cat):
    """Ordner im Hintergrund auffrischen (dedup je Kategorie). True, wenn ein
    Refresh läuft bzw. gestartet wurde."""
    with _mail_folders_lock:
        if cat in _mail_folders_refreshing:
            return True
        _mail_folders_refreshing.add(cat)

    def _run():
        try:
            _folder_fetch_store(cat)
        except Exception as e:
            state.push_log(f"MAIL: Ordner-Auffrischung ({cat}) — "
                           f"{type(e).__name__}: {e}")
        finally:
            with _mail_folders_lock:
                _mail_folders_refreshing.discard(cat)

    threading.Thread(target=_run, daemon=True, name="mail-folder").start()
    return True


def _folder_cache_drop(*cats):
    """Cache einzelner Kategorien verwerfen (nach Umsortieren/Poll) → das nächste
    Öffnen holt garantiert frisch."""
    changed = False
    with _mail_folders_lock:
        for c in cats:
            if c and _mail_folders.pop(c, None) is not None:
                changed = True
    if changed:
        _mail_folders_save()


def _folder_cache_remove_uid(cat, uid):
    """Eine gelöschte Mail SOFORT aus dem Cache nehmen, damit sie beim nächsten
    (gecachten) Öffnen nicht wieder auftaucht."""
    with _mail_folders_lock:
        ent = _mail_folders.get(cat)
        if ent:
            ent["mails"] = [m for m in ent["mails"] if m.get("uid") != uid]
        else:
            return
    _mail_folders_save()


@app.route('/api/mail')
def api_mail():
    """Alles fürs Mail-Panel in einem Rutsch, Drill-down-freundlich:
    `categories` = Ebene 1 (alle Kategorien zum Auswählen). `count` ist der
    lokale Schnappschuss; `live_counts` (separat) trägt die ECHTE Ordnergröße
    aus dem Cache, sobald aufgefrischt. `can_poll` = Passphrase vorhanden,
    `polling`/`counts_refreshing` = Hintergrund-Aktivität läuft."""
    try:
        return jsonify({
            "categories": mail.category_overview(),
            "recent": mail.recent(limit=200),
            "live_counts": _mail_live["counts"],
            "counts_age_s": (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None,
            "counts_refreshing": _mail_live["refreshing"],
            "can_poll": mail_secrets.available(),
            "polling": _mail_poll_running["on"],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/refresh-counts', methods=['POST'])
def api_mail_refresh_counts():
    """Frischt den LIVE-Ordnerzähl-Cache im Hintergrund auf (IMAP STATUS-Sweep).
    Kehrt sofort zurück; das Ergebnis erscheint beim nächsten /api/mail. Key-
    gegatet, Parallel-Refresh verhindert."""
    if not mail_secrets.available():
        return jsonify({"ok": False, "error": "kein key"}), 409
    # Frische Zahlen nicht unnötig neu sweepen: ein STATUS-Sweep über alle
    # Kategorie-Ordner belegt die (eine) gepoolte Verbindung und lässt einen
    # gleichzeitigen Ordner-Aufruf warten. Innerhalb der TTL → Cache behalten,
    # außer `?force=1` (bewusstes Auffrischen, z.B. nach Poll/Umsortieren).
    ttl = float(os.environ.get("MAIL_COUNTS_TTL_S", "90"))
    if not request.args.get("force"):
        age = (time.time() - _mail_live["ts"]) if _mail_live["ts"] else None
        if age is not None and age < ttl and _mail_live["counts"]:
            return jsonify({"ok": True, "cached": True, "age_s": age})
    with _mail_live_lock:
        if _mail_live["refreshing"]:
            return jsonify({"ok": True, "already": True})
        _mail_live["refreshing"] = True

    def _run():
        try:
            fresh = mail.folder_counts()
            # Ein gedrosselter/abgebrochener STATUS-Sweep liefert eine LEERE
            # oder LÜCKENHAFTE Zählung (ein Ordner, der Outlook-throttlet, fehlt
            # einfach). Die dürfen die guten persistierten Zahlen NICHT platt-
            # machen — sonst zeigt das Panel nach Neustart wieder den mageren
            # 171er-Schnappschuss und muss neu zählen. Regeln:
            #   • leeres Ergebnis (Totalausfall) → gar nichts überschreiben.
            #   • sonst frisch ÜBER alt mergen: ein Ordner, der diesmal nicht
            #     geantwortet hat, behält seinen letzten echten Wert.
            # Auf gültige Kategorien beschränken, damit gelöschte nicht spuken.
            if fresh:
                valid = {c["name"] for c in mail.category_overview()}
                merged = dict(_mail_live["counts"])
                merged.update(fresh)
                merged = {k: v for k, v in merged.items() if k in valid}
                _mail_live["counts"] = merged
                _mail_live["ts"] = time.time()
                _mail_counts_save()      # echte Zahlen überleben den Neustart
            else:
                state.push_log("MAIL: Ordnerzählung leer (throttle?) — "
                               "behalte alten Zähl-Stand")
        except Exception as e:
            state.push_log(f"MAIL: Ordnerzählung — {type(e).__name__}: {e}")
        finally:
            _mail_live["refreshing"] = False

    threading.Thread(target=_run, daemon=True, name="mail-counts").start()
    return jsonify({"ok": True, "started": True})


@app.route('/api/mail/folder')
def api_mail_folder():
    """Die Mails EINER Kategorie. Serviert SOFORT aus dem Ordner-Cache (kein
    Warten aufs IMAP) und frischt bei abgelaufenem Cache im Hintergrund auf; nur
    der allererste Aufruf je Kategorie (kalter Cache) holt synchron. `?force=1`
    umgeht den Cache und holt synchron frisch (nach Umsortieren/Löschen). Ohne
    Key oder ohne eigenen Ordner: lokaler Schnappschuss. `cached`/`refreshing`
    sagen, ob die Liste aus dem Cache kam und ob im Hintergrund nachgezogen wird."""
    cat = request.args.get('cat', '')
    if not cat:
        return jsonify({"error": "cat fehlt"}), 400
    force = bool(request.args.get('force'))
    ttl = float(os.environ.get("MAIL_FOLDER_TTL_S", "120"))
    try:
        if not mail_secrets.available():
            mails = mail.in_category(cat, limit=200)
            return jsonify({"cat": cat, "mails": mails, "live": False,
                            "source": "snapshot"})
        if force:                       # bewusst frisch (nach Mutation)
            mails = _folder_fetch_store(cat)
            return jsonify({"cat": cat, "mails": mails, "live": True,
                            "source": "live", "cached": False, "refreshing": False})
        with _mail_folders_lock:
            ent = _mail_folders.get(cat)
            ent = {"mails": ent["mails"], "ts": ent["ts"]} if ent else None
        if ent is not None:             # instant aus Cache, ggf. Hintergrund-Refresh
            age = time.time() - ent["ts"]
            refreshing = _folder_refresh_async(cat) if age >= ttl else False
            return jsonify({"cat": cat, "mails": ent["mails"], "live": True,
                            "source": "cache", "cached": True,
                            "age_s": age, "refreshing": refreshing})
        mails = _folder_fetch_store(cat)   # kalt: einmal synchron, dann gecacht
        return jsonify({"cat": cat, "mails": mails, "live": True,
                        "source": "live", "cached": False, "refreshing": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/body')
def api_mail_body():
    """Voller Text + Header EINER Mail (Lesemodus). LIVE aus dem Ordner; braucht
    Key. Query: `cat`, `uid`, optional `account`, optional `prefetch` (Komma-
    Liste von Nachbar-uids → werden im Hintergrund in den Body-Cache geholt,
    damit n/N im Panel instant ist)."""
    cat = request.args.get('cat', '')
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        body = mail.mail_body(cat, uid, account_name=account)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    # Nachbarn vorwärmen (best-effort, nie blockierend) — die nächste/vorige
    # Mail liegt dann schon im Cache, wenn der Nutzer weiterblättert.
    pf = request.args.get('prefetch', '')
    neigh = [int(x) for x in pf.split(',') if x.strip().lstrip('-').isdigit()]
    if neigh:
        threading.Thread(
            target=lambda: mail.prefetch_bodies(cat, neigh, account_name=account),
            daemon=True, name="mail-prefetch").start()
    return jsonify(body)


@app.route('/api/mail/assign', methods=['POST'])
def api_mail_assign():
    """Den ABSENDER einer Kategorie zuordnen (Keymap) UND **alle** seine
    vorhandenen Mails (alt + neu) in den Kategorie-Ordner verschieben — Sashas
    Modell: pro Absender EINE Kategorie. Mit Key: live umsortiert (`moved` zählt);
    ohne Key: nur Keymap (künftige Mails). Body: `{sender, category}`."""
    body = request.get_json(silent=True) or {}
    sender = (body.get('sender') or '').strip()
    category = (body.get('category') or '').strip()
    if not sender or not category:
        return jsonify({"error": "sender/category fehlt"}), 400
    try:
        res = mail.refile_sender(sender, category)
        # Der Umzug ist jetzt keymap-getrieben und kann aus MEHREREN Ordnern
        # gezogen haben (INBOX + jeder move-Ordner). Statt einzelne Herkünfte zu
        # raten den ganzen Ordner-Cache verwerfen — das nächste Öffnen holt frisch.
        with _mail_folders_lock:
            _mail_folders.clear()
        _mail_folders_save()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/delete', methods=['POST'])
def api_mail_delete():
    """Eine Mail in den Papierkorb verschieben (umkehrbar). LIVE; braucht Key.
    Body: `{cat, uid, account?}`."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — löschen nur live"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    account = body.get('account') or None
    if not cat or uid is None:
        return jsonify({"error": "cat/uid fehlt"}), 400
    try:
        ok = mail.delete_mail(cat, int(uid), account_name=account)
        if ok:                          # gelöschte Mail sofort aus dem Cache nehmen
            _folder_cache_remove_uid(cat, int(uid))
        return jsonify({"ok": bool(ok)}), (200 if ok else 502)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/reply', methods=['POST'])
def api_mail_reply():
    """Antwort auf eine Mail. LIVE; braucht Key. Body: `{cat, uid, text,
    account?, draft?}`. To/Betreff/Threading leitet das Backend aus der
    Original-Mail ab. `draft:true` → speichert die Antwort als ENTWURF im
    Drafts-Ordner (IMAP APPEND) statt sie per SMTP zu senden."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — senden nicht möglich"}), 409
    body = request.get_json(silent=True) or {}
    cat = (body.get('cat') or '').strip()
    uid = body.get('uid')
    text = body.get('text') or ''
    account = body.get('account') or None
    draft = bool(body.get('draft'))
    if not cat or uid is None or not text.strip():
        return jsonify({"error": "cat/uid/text fehlt"}), 400
    if draft:
        res = mail.draft_reply(cat, int(uid), text, account_name=account)
    else:
        res = mail.reply_to_mail(cat, int(uid), text, account_name=account)
    if res.get("error"):
        return jsonify(res), 502
    return jsonify(res)


@app.route('/api/mail/poll', methods=['POST'])
def api_mail_poll():
    """Stößt einen LIVE-Poll im Hintergrund an (explizite Nutzer-Aktion =
    Einwilligung; Move/Trash sind umkehrbar). Kehrt sofort zurück — der
    Fortschritt läuft über die normalen Log-Streams. Verhindert Parallel-Polls."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Live-Poll möglich"}), 409
    with _mail_poll_lock:
        if _mail_poll_running["on"]:
            return jsonify({"ok": True, "already": True})
        _mail_poll_running["on"] = True

    def _run():
        try:
            mail.poll_all(dry_run=False)
            # Der Poll hat Mails in ihre Ordner geräumt → alle Ordner-Caches sind
            # veraltet. Komplett verwerfen; das nächste Öffnen holt frisch.
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Poll abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_poll_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-poll").start()
    return jsonify({"ok": True, "started": True})


@app.route('/api/mail/reconcile', methods=['POST'])
def api_mail_reconcile():
    """Gleicht die Server-Ordner an die Keymap an (bereits einsortierte Mail
    nachziehen) — im Hintergrund-Thread, kehrt SOFORT zurück, blockiert die GUI
    also nie. Explizite Nutzer-Aktion = Einwilligung (Move/Trash umkehrbar). Key-
    gegatet, Parallel-Reconcile via Lock verhindert. Fortschritt läuft über die
    Log-Streams; das Panel bleibt bedienbar."""
    if not mail_secrets.available():
        return jsonify({"error": "keine Passphrase (Env oder OS-Keyring) — "
                                 "kein Abgleich möglich"}), 409
    with _mail_reconcile_lock:
        if _mail_reconcile_running["on"]:
            return jsonify({"ok": True, "already": True})
        _mail_reconcile_running["on"] = True

    def _run():
        try:
            mail.reconcile_all(dry_run=False)
            # Mails wurden umgeräumt → alle Ordner-Caches sind veraltet.
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        except Exception as e:
            state.push_log(f"MAIL: Hintergrund-Reconcile abgebrochen — "
                           f"{type(e).__name__}: {e}")
        finally:
            _mail_reconcile_running["on"] = False

    threading.Thread(target=_run, daemon=True, name="mail-reconcile").start()
    return jsonify({"ok": True, "started": True})


@app.route('/api/mail/inbox')
def api_mail_inbox():
    """Der Eingang-Tray: die INBOX mit Gelesen-Flag (`\\Seen`) + vermuteter
    Kategorie je Mail. LIVE; braucht Key (ohne → leer). Neue/ungelesene Mail liegt
    hier, bis Sasha sie liest — dann sortiert sie sich (bekannter Absender) ein."""
    if not mail_secrets.available():
        return jsonify({"mails": [], "live": False, "source": "kein key"})
    try:
        return jsonify({"mails": mail.inbox_tray(limit=200), "live": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/inbox-body')
def api_mail_inbox_body():
    """Voller Text EINER Eingang-Mail (INBOX). LIVE; braucht Key. Query: `uid`,
    optional `account`. Read-only (PEEK) → hakt die Mail NICHT ab."""
    uid = request.args.get('uid', type=int)
    account = request.args.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    if not mail_secrets.available():
        return jsonify({"error": "kein key — Body nur live lesbar"}), 409
    try:
        return jsonify(mail.inbox_body(uid, account_name=account))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/mail/read', methods=['POST'])
def api_mail_read():
    """Eine Eingang-Mail abhaken: als gelesen markieren (`\\Seen`) und, wenn der
    Absender bekannt ist, sofort einsortieren. LIVE; braucht Key. Body:
    `{uid, account?}`. Sortiert sie ein → alle Ordner-Caches verwerfen."""
    if not mail_secrets.available():
        return jsonify({"error": "kein key — abhaken nur live"}), 409
    body = request.get_json(silent=True) or {}
    uid = body.get('uid')
    account = body.get('account') or None
    if uid is None:
        return jsonify({"error": "uid fehlt"}), 400
    try:
        res = mail.mark_seen_and_file(int(uid), account_name=account)
        if res.get("filed"):        # Mail wanderte in einen Ordner → Caches stale
            with _mail_folders_lock:
                _mail_folders.clear()
            _mail_folders_save()
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
