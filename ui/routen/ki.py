# ui/routen/ki.py
#
# KI-Chat: der SSE-Stream /api/chat, Verlauf, Erlaubnis-Antwort, Status und
# Backend-Wahl, Devtools-Stream. Wer denken darf, sagt core/ai_backends.py;
# welchen Weg der Zug nimmt und ihn fahren, macht core/kern.py (kern.chat).
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import json
from flask import Blueprint, Response, jsonify, request, stream_with_context

import ai           # type: ignore
import ai_backends     # type: ignore  – AI-Backend-Verfügbarkeit (local/cloud, EXTERNAL-Box)
import kern            # type: ignore  – der eine Einstieg in den Chat (core/kern.py)
import ki_einstellungen  # type: ignore  – Einstellungen lesen/setzen mit Prüfung
import providers      # type: ignore  – Cloud-Registry des Kerns (base_url/kind)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

from ui.routen.gemeinsam import _ki_nicht_verfuegbar

bp = Blueprint('ki', __name__)


# ── AI / Chat ──────────────────────────────────────────────────────────

@bp.route('/api/chat', methods=['POST'])
def api_chat():
    """
    Nimmt eine Chat-Nachricht entgegen und streamt die AI-Antwort Token für Token.

    Antwortet als SSE (Server-Sent Events) – ein HTTP-Standard für Push-Streams.
    SSE-Format: jede Nachricht ist eine Zeile "data: <inhalt>\\n\\n"
    Gelesen wird der Stream von der TUI (tui/zentrale_tui.py, ai_stream).

    Ablauf:
      1. User-Nachricht in state.py speichern
      2. Chat-History holen (inkl. neuer Nachricht)
      3. Generator starten – kern.chat() wählt den Weg (lokal: ai.chat_stream,
         cloud: core/cloud.py bzw. core/cloud_openai.py)
         Token für Token
      4. Jeden Token als SSE-Event an den Client schicken; daneben die
         Nicht-Text-Events ascii, permission, werkzeug, reflect, cinema
      5. Nach dem letzten Token: komplette Antwort in state.py speichern
         + "done"-Event schicken, damit der Client weiß, dass es vorbei ist

    stream_with_context() ist Flask-spezifisch: es stellt sicher dass der
    Flask-Request-Context (für g, session etc.) im Generator noch verfügbar ist.
    """
    # Welcher Kern denkt diesen Turn — lokal (Ollama) oder Cloud?
    # chat_available() berücksichtigt beide Drosseln, die Erreichbarkeit,
    # Sashas Vorwahl (chat_backend) UND die Lokal-Regel. Kein Backend →
    # hart abriegeln, damit eine gesetzte Drossel wirklich drosselt.
    backend = ai_backends.chat_available()
    if backend is None:
        return jsonify({"error": "kein KI-Backend für den Chat verfügbar"}), 503
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
        # Stoppen (2026-10-07): der Zug bekommt eine Nummer und ein Abbruch-
        # Signal. Die Nummer geht als ERSTES Event an die TUI, damit ihr Esc
        # genau diesen Zug trifft (POST /api/chat/stop). Angemeldet erst
        # hier drin: nur dann läuft das Abmelden im finally sicher mit.
        strom_id, abbruch = state.chat_zug_beginnen()
        # Welcher Weg (lokal, Anthropic, OpenAI-kompatibel) — das entscheidet
        # kern.chat, die eine Stelle dafür. Alle Wege liefern dasselbe
        # Event-Protokoll; die Schleife hier merkt keinen Unterschied.
        stream = kern.chat(history, via_mic=via_mic, backend=backend,
                           abbruch=abbruch)
        try:
            yield f"data: {json.dumps({'strom': strom_id})}\n\n"
            yield from _sse_zug(stream)
        finally:
            # Auch wenn der Client wegbricht: Zug abmelden und den Kern-
            # Generator schließen, statt ihn bis zum GC weiterlaufen zu lassen.
            state.chat_zug_beenden(strom_id)
            stream.close()

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


# Vermerk hinter einer gestoppten Antwort im Verlauf. Steht dort auch für die
# KI: im nächsten Zug sieht sie, dass ihr Satz nicht zu Ende kam.
VERMERK_ABGEBROCHEN = "(abgebrochen)"


def _sse_zug(stream):
    """Die Events eines Kern-Zugs als SSE-Zeilen; am Ende die Antwort in den
    Verlauf. Generator."""
    # Tokens sammeln um am Ende die komplette Antwort zu speichern
    collected = []
    fehler_kam = False
    gestoppt = False

    for token in stream:
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
        # werkzeug-Event: ein Tool-Call beginnt oder ist fertig. Geht als
        # eigenes SSE 'werkzeug'-Event raus, damit im Chat sichtbar wird,
        # WAS sie tut — nicht nur, was sie hinterher darueber sagt. Kein
        # Antworttext -> nicht in collected.
        if isinstance(token, dict) and 'werkzeug' in token:
            yield f"data: {json.dumps({'werkzeug': token['werkzeug']})}\n\n"
            continue
        # reflect-Event: ein Stück des Denk-Stroms (Ollama `thinking`-Feld
        # bzw. Denk-Tokens der Cloud). Geht als eigenes SSE 'reflect'-Event
        # raus, das die TUI dim mitlaufen lässt ("ich schau kurz nach…").
        # KEIN Antworttext → nicht in collected (nicht gespeichert, nicht
        # gesprochen). Siehe ai.chat_stream / adaptives Thinking.
        if isinstance(token, dict) and 'reflect' in token:
            yield f"data: {json.dumps({'reflect': token['reflect']})}\n\n"
            continue
        # cinema-Event: eine News-Sendung beginnt (lies_news lief). Reines
        # UI-Signal (Sendungs-/Untertitel-Modus), kein Antworttext → nicht
        # in collected.
        if isinstance(token, dict) and 'cinema' in token:
            yield f"data: {json.dumps({'cinema': True})}\n\n"
            continue
        # gestoppt-Event: Sasha hat gestoppt (/api/chat/stop). Die
        # Schleife ist schon raus; hier nur merken, wie gespeichert wird.
        if isinstance(token, dict) and 'gestoppt' in token:
            gestoppt = True
            state.push_log("AI ■  gestoppt")
            yield f"data: {json.dumps({'gestoppt': True})}\n\n"
            continue
        # fehler-Event: Backend-Fehler, Ablehnung oder Rundengrenze (siehe
        # core/werkzeug_schleife.py). Geht DIREKT an Sasha (TUI-Statuszeile)
        # und NICHT in collected: frueher stand "[Cloud-Fehler: …]" danach
        # im Verlauf, und die KI las es im naechsten Zug als ihre eigene
        # Aussage.
        if isinstance(token, dict) and 'fehler' in token:
            fehler_kam = True
            state.push_log(f"AI ✗  {token['fehler']}")
            yield f"data: {json.dumps({'fehler': token['fehler']})}\n\n"
            continue
        collected.append(token)
        # SSE-Format: "data: " + JSON + zwei Newlines
        # JSON.dumps schützt vor Sonderzeichen (Newlines im Token, etc.)
        yield f"data: {json.dumps({'token': token})}\n\n"

    # Komplette Antwort in state speichern (für History beim nächsten Öffnen).
    # Ist der Zug an einem Fehler gescheitert, ohne dass Text kam, bleibt
    # die Frage unbeantwortet stehen — eine leere KI-Antwort waere eine
    # Behauptung ("ich habe nichts gesagt"), die nicht stimmt.
    # Gestoppt: was bis dahin da war, bleibt mit Vermerk stehen; ein
    # gestoppter Zug ohne Text landet gar nicht im Verlauf.
    text = "".join(collected)
    if gestoppt:
        if text.strip():
            state.push_chat_message(
                "assistant", text.rstrip() + "\n\n" + VERMERK_ABGEBROCHEN)
    elif collected or not fehler_kam:
        state.push_chat_message("assistant", text)

    # Abschluss-Signal für den Client
    yield f"data: {json.dumps({'done': True})}\n\n"


@bp.route('/api/chat/stop', methods=['POST'])
def api_chat_stop():
    """Den laufenden Chat-Zug stoppen (TUI: Esc während einer Antwort).

    Body {strom: <id aus dem ersten SSE-Event>} trifft genau diesen Zug;
    ohne strom jeden laufenden. Antwort {gestoppt: bool} — False heißt, es
    lief nichts (mehr), z. B. weil die Antwort gerade fertig wurde. Kein
    Fehler: Stoppen ist dann schlicht erledigt."""
    body = request.get_json(silent=True) or {}
    strom = body.get('strom')
    strom = str(strom) if strom else None
    return jsonify({"ok": True, "gestoppt": state.chat_zug_stoppen(strom)})


@bp.route('/api/chat/history')
def api_chat_history():
    """Gibt die aktuelle Chat-History zurück (für initiales Laden der Chat-View)."""
    if ai_backends.chat_available() is None:
        return jsonify([])   # kein Chat möglich → nichts anzuzeigen
    return jsonify(state.get_chat_history())


@bp.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """Löscht die gesamte Chat-History (per /clear Befehl im Chat-Input)."""
    state.clear_chat_history()
    return jsonify({"ok": True})


@bp.route('/api/permission_answer', methods=['POST'])
def api_permission_answer():
    """
    Nimmt die Ja/Nein-Antwort auf eine Erlaubnis-Rückfrage (Tool-Gate) entgegen.

    Die KI blockiert gerade in einem offenen /api/chat-Stream (in einem
    anderen Thread) auf state.wait_permission(). Dieser Request kommt vom
    Klick auf die JA/NEIN-Knöpfe, liefert die Wahl und entsperrt damit den
    wartenden Generator - der streamt dann den Rest der Antwort auf der
    bereits offenen SSE-Verbindung weiter. Funktioniert nur weil Flask
    multi-threaded läuft (siehe app.run(threaded=True) in ui/app.py).
    """
    # Muss überall dort offen sein, wo auch gechattet werden kann — sonst
    # blockiert ein Erlaubnis-Dialog den Stream für immer, weil niemand die
    # Antwort loswerden kann.
    if ai_backends.chat_available() is None:
        return _ki_nicht_verfuegbar()
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
# bereitgestellt (siehe memory/ki/ki_system.md).


@bp.route('/api/ai/status')
def api_ai_status():
    """
    Sagt, ob der Chat JETZT geht - und über welchen Kern. Wird vom Dashboard
    und von der TUI als Statusanzeige gepollt.

    Nicht mehr "läuft Ollama", sondern "kann ich chatten": unterwegs ist die
    Antwort Cloud, daheim lokal. Die Fronten sollen den Unterschied sehen
    können, statt bei fehlendem Ollama pauschal "KI aus" anzuzeigen.
    """
    import usage as _usage
    kosten = {"heute": _usage.heute_euro(), "monat": _usage.monat_euro(),
              "budget": ai_backends.budget_lage()}

    backend = ai_backends.chat_available()
    if backend == ai_backends.CLOUD:
        # Provider aus status() lesen, nicht neu ermitteln - sonst sehen
        # Endpoint und Backend-Wahl unterschiedliche Wahrheiten.
        prov = ai_backends.status().get("cloud_provider")
        return jsonify({
            "available": True,
            "backend":   "cloud",
            "url":       (providers.get(prov) or {}).get("base_url"),
            "model":     ai_backends.chat_model(prov) or "—",
            "provider":  prov,
            "effort":    ai_backends.chat_effort(),
            "kosten":    kosten,
        })
    if backend == ai_backends.LOCAL:
        return jsonify({
            "available": True,
            "backend":   "local",
            "url":       ai.OLLAMA_URL,
            "model":     ai.OLLAMA_MODEL,
            "kosten":    kosten,     # lokal kostet nichts, der Monat aber schon
        })
    return jsonify({"available": False, "backend": None, "url": None,
                    "model": "—", "kosten": kosten})


@bp.route('/api/ai/backends', methods=['GET', 'POST'])
def api_ai_backends():
    """Welche AI-Backends sind auf diesem Geraet erreichbar (local/cloud)?
    Speist die EXTERNAL-Box + das kapazitaetsbasierte Modul-Gating.

    POST {cloud_enabled: bool} legt den Cloud-Kill-Switch um (Datenschutz-/
    Kosten-Drossel), {local_enabled: bool} den Lokal-Kill-Switch (drosselt die
    lokale Ollama-Leitung) – beide persistiert in data/ai_config.json. GET
    liefert Status inkl. cloud_enabled/local_enabled. Frisch nach Toggle."""
    if request.method == 'POST':
        body = request.get_json() or {}
        if 'cloud_enabled' in body:
            ai_backends.set_cloud_enabled(bool(body['cloud_enabled']))
        if 'local_enabled' in body:
            ai_backends.set_local_enabled(bool(body['local_enabled']))
        return jsonify(ai_backends.status(fresh=True))
    return jsonify(ai_backends.status())


@bp.route('/api/ai/einstellungen', methods=['GET', 'POST'])
def api_ai_einstellungen():
    """Chat-Einstellungen lesen (GET) oder setzen (POST) — für die
    Slash-Befehle im TUI-Chat (/modell, /anbieter, /effort, /budget,
    /lokal, /cloud, /auto). POST nimmt beliebige der Felder
    {anbieter, modell, effort, budget, weg}, prüft alle und setzt sie
    dauerhaft (core/ki_einstellungen.py). Unsinn → 400 mit Klartext in
    'error'; dann ist NICHTS gesetzt."""
    if request.method == 'POST':
        body = request.get_json(silent=True)
        try:
            return jsonify(ki_einstellungen.setzen(body))
        except ki_einstellungen.Ungueltig as e:
            return jsonify({"error": str(e)}), 400
    return jsonify(ki_einstellungen.lesen())


@bp.route('/api/ai/debug/stream')
def api_ai_debug_stream():
    """Devtools-Stream (SSE) fuer die KERN-KI (scripts/ai_devtools.py).

    Schickt die Historie und danach live jedes Event: den VOLLEN Request
    (System-Prompt, alle Messages, Tool-Namen, wo die Cache-Breakpoints
    sitzen), die Roh-Antwort, jeden Tool-Call und was der Extraktor in den
    Graphen geschrieben hat.

    Der Bus ist normalerweise AUS — Verbinden schaltet ihn an, damit man ihn
    nicht vorher per Env scharfstellen muss. Er bleibt danach an; das ist
    gewollt (man will meist mehrere Sitzungen mitlesen) und kostet wenig.

    ⚠ Hier geht der komplette Prompt raus, inklusive Graph-Kontext — also
    Sashas Zustaende und Erlebnisse. So privat wie der Graph selbst; laeuft
    ueber dieselbe lokale API wie alles andere (memory/betrieb/sicherheit.md).
    """
    import kidebug

    kidebug.einschalten(True)

    def generate():
        yield 'data: ' + json.dumps(
            {'ts': kidebug._ts(), 'kind': 'hallo',
             'backend': ai_backends.chat_backend(),
             'provider': ai_backends.status().get('cloud_provider')},
            ensure_ascii=False) + '\n\n'
        for ev in kidebug.history():
            yield 'data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n'
        q = kidebug.subscribe()
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                    yield 'data: ' + json.dumps(ev, ensure_ascii=False) + '\n\n'
                except Exception:
                    yield ': keepalive\n\n'   # Heartbeat, damit die Verbindung lebt
        finally:
            kidebug.unsubscribe(q)

    return Response(stream_with_context(generate()), content_type='text/event-stream')
