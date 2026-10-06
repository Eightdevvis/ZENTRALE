# ui/routen/tutor.py
#
# Sprach-Tutor: alles unter /api/tutor/. Der Tutor ist ein eigenes Projekt und
# wird NUR über core/tutor_port.py angefasst.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import json
from flask import Blueprint, Response, jsonify, request, stream_with_context

import audio        # type: ignore
import tutor_port    # type: ignore  – EINZIGER Griff am Sprach-Tutor (Addon).
                     # Nicht tutor_* direkt importieren: der Port haelt den Tutor
                     # rausziehbar und wendet die ZENTRALE-Drossel an.

from ui.routen.gemeinsam import _tutor_unavail

bp = Blueprint('tutor', __name__)


# ── Tutor ─────────────────────────────────────────────────────────────
#
# Sprach-Tutor: Addon auf der Core-KI mit EIGENEM System-Prompt (pro Sprache
# tutor/langs/<code>/prompt.md) und EIGENEM Tool-Set (tutor.tools.tools_for(lang)),
# sauber getrennt vom regulaeren Chat. Der Kern fasst den Tutor NUR ueber
# core/tutor_port.py an; die Logik lebt in tutor/session.py + tutor/tools.py.
#
# Start ist rein MANUELL ueber Alt+T (Browser) bzw. Taste 'u' (TUI) → POST
# /api/tutor/start.
# Es gibt KEINEN Presence-Auto-Trigger in brain.py (bewusst: erst Core-KI
# sauber, dann Addon – siehe memory/tutor/tutor_system.md).
#
# Audio laeuft ueber die generische Voice-API (/api/transcribe, /api/speak)
# mit lang='zh' – der Tutor besitzt die Pipeline nicht, er ruft sie nur auf.


@bp.route('/api/tutor/status')
def api_tutor_status():
    """Kern-Sicht auf den Tutor + Audio-Service-Status. Fronten pollen das.

    Felder aus tutor_port.status():
      present   – ist der Tutor auf dieser Maschine ueberhaupt installiert?
      active    – laeuft gerade eine Session?
      available – installiert UND von der Drossel erlaubt UND Backend erreichbar
      reason    – WARUM nicht, im Klartext ("Cloud ist per Kill-Switch gedrosselt",
                  "Provider-Backend nicht erreichbar", "Tutor nicht installiert").
                  Leer, wenn available. Die Fronten SCHREIBEN das hin, statt zu
                  raten — bis 2026-07-17 warf dieser Endpunkt present+reason weg,
                  also konnte niemand "gedrosselt" von "weg" unterscheiden.
      privacy_warning – != null → Provider trainiert auf Daten: laut anzeigen.
    """
    st = tutor_port.status()
    st.update(whisper=audio.whisper_available(), tts=audio.tts_available())
    return jsonify(st)


@bp.route('/api/tutor/config', methods=['GET', 'POST'])
def api_tutor_config():
    """Liest/aendert die Live-Tutor-Konfiguration (Sprache/Provider/Modell) –
    so kann man das Modell IN ZENTRALE direkt umschalten, ohne Datei-Editieren.

    POST-Body (JSON, alle optional): {lang, provider, model, history_window, persist}.
    persist=true schreibt zusaetzlich in data/tutor_config.json (ueberlebt Neustart, gehoert dem Tutor),
    sonst gilt der Wechsel nur fuer die laufende Instanz.
    GET liefert die aktuelle Aufloesung + waehlbare Provider/Sprachen.
    """
    body    = request.get_json(silent=True) or {} if request.method == 'POST' else {}
    persist = bool(body.get('persist'))
    cfg     = tutor_port.config(changes=body, persist=persist)
    if not cfg.get("present"):
        return _tutor_unavail()
    return jsonify(cfg)


@bp.route('/api/tutor/start', methods=['POST'])
def api_tutor_start():
    """
    Startet eine Tutor-Session manuell (Dashboard-Taste 'T') und streamt die
    erste KI-Begruessung. Die KI laedt zu Beginn selbst die Vokabeln via
    get_confirmed_vocab()/get_testing_vocab() (Tool-Calls) und begruesst auf
    Mandarin.
    """
    if not tutor_port.available():
        return _tutor_unavail()

    # Aktivieren, wenn keine Session läuft ODER die laufende nicht zum aktiven
    # Spielstand passt (Sprache) — die alte gehört dann zum alten Stand.
    if not tutor_port.is_active() or not tutor_port.passt_zum_stand():
        tutor_port.activate()

    body  = request.get_json(silent=True) or {}
    focus = body.get('focus')   # Fenster fokussiert beim Öffnen? (Sensor)

    # still=True: Session nur AKTIVIEREN, keine Begruessung. Fuer das Zimmer an
    # der Wand, das rund um die Uhr laeuft: nach Deploy/Neustart soll Lucia
    # nicht in ein leeres Zimmer hinein gruessen — gesprochen wird erst, wenn
    # das Mikro jemanden hoert (Ankunft → /api/tutor/nudge arrival).
    if body.get('still'):
        return jsonify({"ok": True, "active": tutor_port.is_active()})

    def generate():
        # user_text=None → KI beginnt das Gespraech (Öffnen = Lage-Meldung)
        for token in tutor_port.respond_stream(user_text=None, focus=focus):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@bp.route('/api/tutor/respond', methods=['POST'])
def api_tutor_respond():
    """
    Nimmt transkribierten Text entgegen, schickt ihn an die KI (Tutor-Modus)
    und streamt die Antwort zurueck. Body: JSON {"text": "我很好"}.
    """
    if not tutor_port.available():
        return _tutor_unavail()
    if not tutor_port.is_active():
        return jsonify({"error": "Keine aktive Tutor-Session"}), 400

    body      = request.get_json() or {}
    user_text = (body.get('text') or '').strip()
    if not user_text:
        return jsonify({"error": "kein Text"}), 400

    def generate():
        for token in tutor_port.respond_stream(user_text=user_text):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@bp.route('/api/tutor/stop', methods=['POST'])
def api_tutor_stop():
    """Beendet die aktive Tutor-Session."""
    tutor_port.deactivate()
    return jsonify({"ok": True})


@bp.route('/api/tutor/room_state')
def api_tutor_room_state():
    """Aktueller Ausdrucks-Zustand der Persona (Haltung/Geste) fuers Zimmer-
    Fenster. Leichtgewichtig — das Fenster pollt das ein paar Mal pro Sekunde.
    Die Werte setzt die KI selbst ueber das express-Tool."""
    return jsonify(tutor_port.room_state())


@bp.route('/api/tutor/assessment')
def api_tutor_assessment():
    """Kern-Curriculum + Lernstand fuers Frontend-Drill (das harte Gate vor der
    Persona). DETERMINISTISCH — kein LLM: das Zimmer geht die Wortliste selbst
    Karte fuer Karte durch. Braucht KEINE aktive KI-Session (nur die lokalen
    Vokabel-Dateien), darum kein available()-Gate."""
    a = tutor_port.assessment()
    if not a.get("present"):
        return _tutor_unavail()
    return jsonify(a)


@bp.route('/api/tutor/assessment/answer', methods=['POST'])
def api_tutor_assessment_answer():
    """Eine Drill-Antwort verbuchen. Body: {word, result} mit
    result = known | learned | again. Gibt den neuen Stand + Deckung zurueck."""
    body   = request.get_json(silent=True) or {}
    word   = (body.get('word') or '').strip()
    result = (body.get('result') or '').strip()
    if not word or result not in ('known', 'learned', 'again'):
        return jsonify({"error": "word + result (known|learned|again) noetig"}), 400
    return jsonify(tutor_port.assessment_answer(word, result))


# ── Spielstaende ──────────────────────────────────────────────────────
#
# Mehrere Lernstaende nebeneinander, einer ist aktiv. Bis hierher hatte der
# Tutor genau einen; wer neu anfangen wollte, musste Dateien loeschen und war
# den alten Fortschritt los. Gewaehlt wird auf dem Willkommens-Schirm des
# Zimmers, bevor das Drill losgeht.
#
# Wie beim Drill KEIN available()-Gate: Spielstaende sind Dateien auf der
# Platte, dafuer muss keine KI erreichbar sein. Man soll seinen Stand auch
# dann wechseln koennen, wenn die Cloud gerade gedrosselt ist.


@bp.route('/api/tutor/staende')
def api_tutor_staende():
    """Alle Spielstaende + welcher gerade aktiv ist."""
    d = tutor_port.staende()
    if not d.get("present"):
        return _tutor_unavail()
    return jsonify(d)


@bp.route('/api/tutor/staende', methods=['POST'])
def api_tutor_stand_anlegen():
    """Neuen Spielstand anlegen und sofort aktivieren. Body: {name} (optional)."""
    body = request.get_json(silent=True) or {}
    d = tutor_port.stand_anlegen((body.get('name') or '').strip() or None,
                                 lang=(body.get('lang') or '').strip().lower() or None,
                                 level=int(body.get('level') or 0))
    return jsonify(d), (200 if d.get("ok") else 400)


@bp.route('/api/tutor/staende/waehlen', methods=['POST'])
def api_tutor_stand_waehlen():
    """Auf einen vorhandenen Spielstand umschalten. Body: {id}."""
    body = request.get_json(silent=True) or {}
    sid = (body.get('id') or '').strip()
    if not sid:
        return jsonify({"ok": False, "error": "id noetig"}), 400
    d = tutor_port.stand_waehlen(sid)
    return jsonify(d), (200 if d.get("ok") else 400)


@bp.route('/api/tutor/staende/loeschen', methods=['POST'])
def api_tutor_stand_loeschen():
    """Einen Spielstand samt allem Gelernten entfernen. Body: {id}.

    Bewusst POST mit id im Body statt DELETE auf einen Pfad: die Fronten hier
    sprechen alle nur GET/POST, und ein versehentlicher Aufruf per Browser-URL
    kann so nichts loeschen.
    """
    body = request.get_json(silent=True) or {}
    sid = (body.get('id') or '').strip()
    if not sid:
        return jsonify({"ok": False, "error": "id noetig"}), 400
    d = tutor_port.stand_loeschen(sid)
    return jsonify(d), (200 if d.get("ok") else 400)


@bp.route('/api/tutor/debug/stream')
def api_tutor_debug_stream():
    """Devtools-Stream (SSE) fuers Tutor-Terminal (scripts/tutor_devtools.py):
    schickt ZUERST einen Snapshot (User-Vokabel + Assessment-Routing), dann die
    Event-Historie, dann LIVE jedes Event (Vokabel-Statusaenderung + kompletter
    AI-Stream: voller System-Prompt, Roh-Ausgabe, Tool-Calls). Alles zeitgestempelt."""
    tutor_debug = tutor_port.debug_bus()
    if tutor_debug is None:
        return _tutor_unavail()

    def generate():
        snap = tutor_port.debug_snapshot()
        yield 'data: ' + json.dumps({'ts': tutor_debug._ts(), 'kind': 'snapshot', **snap},
                                     ensure_ascii=False) + '\n\n'
        for ev in tutor_debug.history():
            yield 'data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n'
        q = tutor_debug.subscribe()
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                    yield 'data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n'
                except Exception:
                    yield ': keepalive\n\n'   # Heartbeat, damit die Verbindung lebt
        finally:
            tutor_debug.unsubscribe(q)

    return Response(stream_with_context(generate()), content_type='text/event-stream')


@bp.route('/api/tutor/nudge', methods=['POST'])
def api_tutor_nudge():
    """Stille-Anstoss: Sasha hat eine Weile nichts gesagt → die Persona reagiert
    von selbst (schauen/winken/kurz nachfragen). Das Zimmer-Fenster loest das
    gedeckelt aus (einmal, dann Ruhe; alle ~15 min erneut). Streamt wie /respond;
    der Anstoss-Text wird NICHT in der History gespeichert."""
    if not tutor_port.available():
        return _tutor_unavail()
    if not tutor_port.is_active():
        return jsonify({"error": "Keine aktive Tutor-Session"}), 400

    body  = request.get_json(silent=True) or {}
    focus = body.get('focus')   # Fenster fokussiert? (Sensor aus dem Zimmer)
    sound = body.get('sound')   # Mikro hat jemanden gehört? (Zimmer, Anwesenheit)
    # arrival=True: Aktivität nach längerer Ruhe — jemand kommt rein. Die Persona
    # bekommt dann die Öffnungs-Lage („Sasha kommt gerade rein") statt der
    # Stille-Lage und spricht von sich aus an. Kerngedanke Wand-Tutor.
    arrival = bool(body.get('arrival'))

    def generate():
        for token in tutor_port.respond_stream(nudge=True, focus=focus,
                                               sound=sound, arrival=arrival):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
