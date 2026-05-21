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
import consolidation # type: ignore  – Phase E: STM → LTM Konsolidierung
import threading

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
    # via_mic-Flag aus dem Body. True bedeutet: diese Message kam aus
    # Whisper-Transkription, nicht aus Tastatur. Wird an chat_stream()
    # durchgereicht, das daraus einen Mic-Hint an den System-Prompt
    # haengt - damit die KI bei Transkriptionsfehlern nachfragen kann
    # statt woertlich zu antworten. Default False fuer alle Legacy-
    # Clients die das Feld nicht mitschicken.
    via_mic = bool(body.get('via_mic', False))
    if not message:
        return jsonify({"error": "no message"}), 400

    # ── /sleep-Command: STM → LTM Konsolidierung (Phase E) ────────────
    # Wir nehmen den User-Trigger als sichtbaren Chat-Turn auf damit es
    # in der History erkennbar ist, und antworten mit einem Status-Text
    # statt einem normalen AI-Generate.
    if message.lower().strip() in ('/sleep', '/sleep ', '/konsolidieren'):
        state.push_chat_message("user", message)

        def sleep_generate():
            yield f"data: {json.dumps({'token': '[Konsolidierung läuft – extrahiere Fakten aus STM...]\\n'})}\n\n"
            stats   = consolidation.consolidate_stm()
            summary = (
                f"OK. {stats['turns_seen']} Turns gesehen, "
                f"{stats['facts_extracted']} Fakten extrahiert, "
                f"{stats['facts_saved']} ins LTM gespeichert. "
                f"STM ist jetzt leer."
            )
            yield f"data: {json.dumps({'token': summary})}\n\n"
            state.push_chat_message("assistant", summary)
            yield f"data: {json.dumps({'done': True})}\n\n"

        return Response(
            stream_with_context(sleep_generate()),
            content_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    # ── Lazy-Inaktivitäts-Check ───────────────────────────────────────
    # Wenn seit dem letzten User-Turn >30 Min vergangen sind, im
    # Hintergrund konsolidieren bevor wir die neue Nachricht verarbeiten.
    # Reihenfolge wichtig: erst maybe_consolidate (vergleicht gegen
    # alten Timestamp), dann note_user_turn (setzt neuen Timestamp).
    def _bg_inactivity_check():
        try:
            consolidation.maybe_consolidate_due_to_inactivity()
        except Exception as e:
            state.push_log(f"[consolidation] FEHLER: {e}")
    threading.Thread(target=_bg_inactivity_check, daemon=True, name='ai-inactivity-check').start()
    consolidation.note_user_turn()

    state.push_chat_message("user", message)
    history = state.get_chat_history()

    def generate():
        # Tokens sammeln um am Ende die komplette Antwort zu speichern
        collected = []

        for token in ai.chat_stream(history, via_mic=via_mic):
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
    """
    Gibt alle gespeicherten Memory-Einträge zurück (für /memory Befehl im Chat).

    Embeddings (1024 floats pro Eintrag bei bge-m3) werden vor dem Versand
    rausgestrippt - der User braucht die im UI nicht sehen, und sie würden
    die JSON-Response um Faktor ~50 aufblähen.
    """
    entries = memory.load()
    slim    = [{k: v for k, v in e.items() if k != 'embedding'} for e in entries]
    return jsonify(slim)


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
      speed    – Sprechgeschwindigkeit (default 0.9)
      speaker  – Sprecher-ID (default 0; bedeutung modellabhaengig)

    Response: audio/wav, oder 503 wenn das Modell fuer die Sprache fehlt.
    """
    body    = request.get_json() or {}
    text    = (body.get('text') or '').strip()
    lang    = (body.get('lang') or '').strip() or None
    speed   = float(body.get('speed', 0.9))
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
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld"}), 400

    audio_bytes = request.files['audio'].read()
    lang        = (request.form.get('lang') or '').strip() or None
    text        = audio.transcribe(audio_bytes, lang=lang)
    return jsonify({"text": text})


# ── Tutor ─────────────────────────────────────────────────────────────
#
# Der Mandarin-Tutor ist pausiert (siehe memory/tutor_system.md). Die
# frueheren Endpoints /api/tutor/{status,start,respond,transcribe,speak,
# stop} sind raus. core/tutor.py, core/tutor_session.py und
# data/vocab_mandarin.json bleiben unangetastet – fuers spaetere Wieder-
# Anschalten reicht es, die Routes plus den brain-Trigger zurueckzu-
# holen (git-History) und tutor_session wieder zu importieren.


# ── Start ──────────────────────────────────────────────────────────────

def start_ui(host='0.0.0.0', port=5000):
    """
    Startet den Flask-Server. Wird von main.py als Background-Thread gestartet.

    host='0.0.0.0' = auf allen Netzwerk-Interfaces lauschen (auch Pi → Browser im LAN)
    debug=False     = kein Debug-Modus (würde Threading-Probleme machen)
    use_reloader=False = kein Auto-Reload (läuft ja als Thread, kein eigener Prozess)
    """
    app.run(host=host, port=port, debug=False, use_reloader=False)
