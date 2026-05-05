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

from flask import Flask, jsonify, render_template, request, Response, stream_with_context
from datetime import datetime
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import categories   # type: ignore
import ai           # type: ignore
import memory       # type: ignore
import audio        # type: ignore
import tutor_session  # type: ignore

app = Flask(__name__)

# Absoluter Pfad zum data/-Verzeichnis (liegt im Projektroot, nicht in ui/).
# os.path.abspath + join macht den Pfad robust gegen "von wo starte ich das Skript".
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')


# ── Dashboard ─────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Liefert die Dashboard-HTML-Seite."""
    resp = render_template('index.html')
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
    body    = request.get_json()
    message = (body.get('message') or '').strip()
    if not message:
        return jsonify({"error": "no message"}), 400

    state.push_chat_message("user", message)
    history = state.get_chat_history()

    def generate():
        # Tokens sammeln um am Ende die komplette Antwort zu speichern
        collected = []

        for token in ai.chat_stream(history):
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
    return jsonify(state.get_chat_history())


@app.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """Löscht die gesamte Chat-History (per /clear Befehl im Chat-Input)."""
    state.clear_chat_history()
    return jsonify({"ok": True})


@app.route('/api/memory')
def api_memory_list():
    """Gibt alle gespeicherten Memory-Einträge zurück (für /memory Befehl im Chat)."""
    return jsonify(memory.load())


@app.route('/api/memory/<int:index>', methods=['DELETE'])
def api_memory_forget(index):
    """Löscht einen Memory-Eintrag nach ID (für /forget N Befehl im Chat)."""
    result = memory.forget(index)
    return jsonify({"ok": True, "message": result})


@app.route('/api/ai/status')
def api_ai_status():
    """
    Prüft ob Ollama erreichbar ist und gibt Status + Konfiguration zurück.
    Wird vom Dashboard alle 30s gecheckt und als Statusanzeige genutzt.
    """
    return jsonify({
        "available": ai.is_available(),
        "url":       ai.OLLAMA_URL,
        "model":     ai.OLLAMA_MODEL,
    })


# ── Tutor ─────────────────────────────────────────────────────────────

@app.route('/api/tutor/status')
def api_tutor_status():
    """Gibt zurück ob gerade eine Tutor-Session aktiv ist + Audio-Service-Status."""
    return jsonify({
        "active":  tutor_session.is_active(),
        "whisper": audio.whisper_available(),
        "tts":     audio.tts_available(),
    })


@app.route('/api/tutor/start', methods=['POST'])
def api_tutor_start():
    """
    Startet eine Tutor-Session manuell (oder bestätigt einen durch brain.py
    ausgelösten Start) und streamt die erste KI-Begrüßung.

    Die KI lädt zu Beginn automatisch die Vokabeln via get_confirmed_vocab()
    und get_testing_vocab() (Tool-Calls) und begrüßt dann auf Mandarin.
    """
    if not tutor_session.is_active():
        tutor_session.activate()

    def generate():
        full = []
        # user_text=None → KI beginnt das Gespräch
        for token in tutor_session.respond_stream(user_text=None):
            full.append(token)
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
    und streamt die Antwort zurück.

    Body: JSON {"text": "我很好"}
    """
    if not tutor_session.is_active():
        return jsonify({"error": "Keine aktive Tutor-Session"}), 400

    body      = request.get_json() or {}
    user_text = body.get('text', '').strip()
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


@app.route('/api/tutor/transcribe', methods=['POST'])
def api_tutor_transcribe():
    """
    Nimmt eine WAV-Datei vom Browser entgegen (MediaRecorder-Output),
    schickt sie an den Whisper-Service und gibt den transkribierten Text zurück.

    Browser sendet: multipart/form-data mit Feld 'audio'
    Response: JSON {"text": "我很好"}
    """
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld"}), 400

    audio_bytes = request.files['audio'].read()
    text        = audio.transcribe(audio_bytes)
    return jsonify({"text": text})


@app.route('/api/tutor/speak', methods=['POST'])
def api_tutor_speak():
    """
    Lässt den TTS-Service einen Text auf Mandarin sprechen und gibt
    die WAV-Datei direkt zurück – der Browser spielt sie mit Web Audio ab.

    Body: JSON {"text": "你好！", "speed": 0.9}
    Response: audio/wav
    """
    body  = request.get_json() or {}
    text  = body.get('text', '').strip()
    speed = float(body.get('speed', 0.9))

    if not text:
        return jsonify({"error": "kein Text"}), 400

    wav = audio.synthesize(text, speed=speed)
    if not wav:
        return jsonify({"error": "TTS nicht verfügbar"}), 503

    return Response(wav, content_type='audio/wav')


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
    """
    app.run(host=host, port=port, debug=False, use_reloader=False)
