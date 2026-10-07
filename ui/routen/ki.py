# ui/routen/ki.py
#
# KI-Chat: der SSE-Stream /api/chat (+ wiederholen), Verlauf, Erlaubnis-
# Antwort, Status und Backend-Wahl, Devtools-Stream. Gesprächs-Verwaltung
# (Liste, umbenennen, archivieren): ui/routen/gespraeche.py. Wer denken
# darf, sagt core/ai_backends.py; welchen Weg der Zug nimmt und ihn fahren,
# macht core/kern.py (kern.chat).
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import json
from flask import Blueprint, Response, jsonify, request, stream_with_context

import ai           # type: ignore
import ai_backends     # type: ignore  – AI-Backend-Verfügbarkeit (local/cloud, EXTERNAL-Box)
import anhang          # type: ignore  – Anhänge: Verweise prüfen, in den Verlauf einsetzen
import cloud           # type: ignore  – Längen-Grenze einer Nachricht (nutzer_grenze)
import erlaubnis       # type: ignore  – Erlaubnis-Gate: Geltungsbereiche, /erlaubnis
import gespraeche      # type: ignore  – Gespräche: Ordner pro Gespräch, Datei pro Rechner
import gespraech_titel # type: ignore  – automatischer Titel (billiges Modell)
import projekte        # type: ignore  – Projekte (Phase 6): /neu bleibt im Projekt
import kern            # type: ignore  – der eine Einstieg in den Chat (core/kern.py)
import ki_einstellungen  # type: ignore  – Einstellungen lesen/setzen mit Prüfung
import providers      # type: ignore  – Cloud-Registry des Kerns (base_url/kind)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import zug           # type: ignore  – der laufende Zug: Gespräch + Ereignisse der Werkzeuge

from ui.routen.gemeinsam import _ki_nicht_verfuegbar

bp = Blueprint('ki', __name__)


# ── AI / Chat ──────────────────────────────────────────────────────────

@bp.route('/api/chat', methods=['POST'])
def api_chat():
    """
    Nimmt eine Chat-Nachricht entgegen und streamt die Antwort als SSE
    (Server-Sent Events: jede Nachricht eine Zeile "data: <json>\\n\\n").
    Gelesen wird der Stream von der TUI (tui/ansichten/chat.py, ai_stream).

    Body: {message, via_mic?, gespraech?, ersetzt?, anhaenge?}
      gespraech: in dieses Gespräch (sonst das aktive dieses Rechners; gibt
                 es keins, wird eins angelegt). Unbekannt → 404.
      ersetzt:   Nachricht-id einer eigenen Nachricht — „bearbeiten": sie und
                 alles danach zählt nicht mehr, dann geht message normal raus.
                 Ihre Anhänge gehen mit, wenn keine neuen kommen.
      anhaenge:  Ablage-ids (POST /api/anhang, Phase 5). Bild + lokale KI → 400.

    Seit 2026-10-07 (Claude-Web-Plan Phase 2) lebt der Verlauf in
    core/gespraeche.py statt im RAM: die Nachricht wird dort angehängt, an
    kern.chat geht das Fenster des Gesprächs, die Antwort (mit Denken)
    landet wieder dort.
    """
    # Welcher Kern denkt diesen Turn — lokal (Ollama) oder Cloud?
    # chat_available() berücksichtigt beide Drosseln, die Erreichbarkeit,
    # Sashas Vorwahl (chat_backend) UND die Lokal-Regel. Kein Backend →
    # hart abriegeln, damit eine gesetzte Drossel wirklich drosselt.
    backend = ai_backends.chat_available()
    if backend is None:
        return jsonify({"error": "kein KI-Backend für den Chat verfügbar"}), 503
    body    = request.get_json(silent=True) or {}
    message = (body.get('message') or '').strip()
    # via_mic: die Nachricht kam aus Whisper, nicht von der Tastatur — der
    # Kern hängt dann einen Hinweis an, damit die KI bei Hörfehlern nachfragt.
    via_mic = bool(body.get('via_mic', False))
    if not message:
        return jsonify({"error": "no message"}), 400
    # Länge (2026-10-07): bis zur Grenze kommt eine Nachricht VOLLSTÄNDIG bei
    # der KI an (cloud.nutzer_grenze, Standard 20 000). Darüber lieber
    # ehrlich ablehnen als still in der Mitte kürzen.
    grenze = cloud.nutzer_grenze()
    if len(message) > grenze:
        def zahl(n):
            return f"{n:,}".replace(",", ".")
        return jsonify({"error": f"Die Nachricht ist zu lang ({zahl(len(message))} "
                                 f"Zeichen, höchstens {zahl(grenze)}). Längeres "
                                 f"als Datei: /anhang <pfad>."}), 400
    try:
        verweise = anhang.verweise(body.get('anhaenge') or [])
    except anhang.Abgelehnt as e:
        return jsonify({"error": str(e)}), 400

    gid, fehler = _gespraech_waehlen(body)
    if fehler:
        return fehler
    ersetzt = body.get('ersetzt')
    if ersetzt:
        ziel = next((n for n in gespraeche.nachrichten(gid) if n["id"] == ersetzt),
                    None) if gid else None
        if ziel is None:
            return jsonify({"error": "Diese Nachricht gibt es in dem Gespräch nicht."}), 404
        if ziel["rolle"] != "user":
            return jsonify({"error": "Bearbeiten geht nur mit einer eigenen Nachricht."}), 400
        verweise = verweise or ziel.get("anhaenge") or []
    if anhang.hat_bild(verweise) and backend != ai_backends.CLOUD:
        return jsonify({"error": "Bilder gehen nur mit der Cloud-KI — /cloud schaltet um."}), 400
    if gid is None:
        # /neu aus einem Projekt heraus: das neue Gespräch bleibt darin (Phase 6).
        gid = gespraeche.neu(projekt=gespraeche.neu_projekt())
    gespraeche.aktiv_setzen(gid)
    if ersetzt:
        gespraeche.verwerfen_ab(gid, ersetzt)
    return _zug_starten(gid, message, backend, via_mic, verweise)


@bp.route('/api/chat/wiederholen', methods=['POST'])
def api_chat_wiederholen():
    """Die letzte Antwort neu erzeugen: alles ab der letzten eigenen
    Nachricht verwerfen und dieselbe Nachricht noch einmal schicken. SSE wie
    /api/chat. Body {gespraech?}; ohne: das aktive."""
    backend = ai_backends.chat_available()
    if backend is None:
        return jsonify({"error": "kein KI-Backend für den Chat verfügbar"}), 503
    gid, fehler = _gespraech_waehlen(request.get_json(silent=True) or {})
    if fehler:
        return fehler
    letzte = gespraeche.letzte_nutzer_nachricht(gid) if gid else None
    if letzte is None:
        return jsonify({"error": "In diesem Gespräch gibt es noch nichts zu wiederholen."}), 400
    verweise = letzte.get("anhaenge") or []
    if anhang.hat_bild(verweise) and backend != ai_backends.CLOUD:
        return jsonify({"error": "Bilder gehen nur mit der Cloud-KI — /cloud schaltet um."}), 400
    gespraeche.aktiv_setzen(gid)
    gespraeche.verwerfen_ab(gid, letzte["id"])
    return _zug_starten(gid, letzte["text"], backend, False, verweise)


def _gespraech_waehlen(body):
    """Gespräch aus dem Body oder das aktive. -> (gid|None, fehler-Antwort|None)"""
    gid = body.get('gespraech')
    if gid:
        if not gespraeche.gibt_es(str(gid)):
            return None, (jsonify({"error": "Dieses Gespräch gibt es nicht."}), 404)
        return str(gid), None
    return gespraeche.aktiv(), None


def _zug_starten(gid, message, backend, via_mic, verweise=None):
    """Nachricht anhängen und den Zug als SSE-Antwort fahren. verweise:
    Anhänge ([{id, titel, art, fassung}]) — im Gespräch steht nur der
    Verweis, den Inhalt setzt anhang.verlauf_einsetzen für die KI ein."""
    erster = not any(n["rolle"] == "assistant" for n in gespraeche.nachrichten(gid))
    frage = gespraeche.anhaengen(gid, "user", message, anhaenge=verweise or None)
    # Sofort ein Titel aus den ersten Wörtern — die Liste zeigt nie ein
    # namenloses Gespräch; das Modell darf ihn nach der Antwort verbessern.
    gespraech_titel.erster_titel(gid, message)
    history = anhang.verlauf_einsetzen(gespraeche.verlauf_fuer_ki(gid),
                                       cloud=(backend == ai_backends.CLOUD))

    def generate():
        # Stoppen (2026-10-07): der Zug bekommt eine Nummer und ein Abbruch-
        # Signal. Die Nummer geht als ERSTES Event an die TUI, damit ihr Esc
        # genau diesen Zug trifft (POST /api/chat/stop). Angemeldet erst
        # hier drin: nur dann läuft das Abmelden im finally sicher mit.
        strom_id, abbruch = state.chat_zug_beginnen()
        # Der Zug für die Werkzeuge (core/zug.py, Phase 5): Gesprächs-id für
        # run_code/Ablage, und was sie an die TUI melden (Event 'ablage').
        # Das Abbruch-Signal geht mit (2026-10-07): run_code stoppt damit
        # einen laufenden Prozess sofort.
        marke = zug.beginnen(gid, abbruch=abbruch)
        # „Für dieses Gespräch" erlaubt gilt nur, solange es DIESES ist.
        erlaubnis.gespraech_beginnt(gid)
        # Welcher Weg (lokal, Anthropic, OpenAI-kompatibel) — das entscheidet
        # kern.chat, die eine Stelle dafür. Alle Wege liefern dasselbe
        # Event-Protokoll; die Schleife hier merkt keinen Unterschied.
        # Das Projekt des Gesprächs (Phase 6) geht als Parameter mit — der
        # Kern setzt dessen Block in den festen Kopf.
        stream = kern.chat(history, via_mic=via_mic, backend=backend,
                           abbruch=abbruch, projekt=gespraeche.projekt_von(gid))
        try:
            yield _sse({'strom': strom_id})
            # Welches Gespräch, welche Nachricht — die TUI braucht die id
            # eines eben angelegten Gesprächs (Liste, Titel, Bearbeiten).
            yield _sse({'gespraech': gid, 'nachricht': frage['id']})
            yield from _sse_zug(stream, gid, backend, message, erster)
        finally:
            # Auch wenn der Client wegbricht: Zug abmelden und den Kern-
            # Generator schließen, statt ihn bis zum GC weiterlaufen zu lassen.
            state.chat_zug_beenden(strom_id)
            stream.close()
            zug.beenden(marke)

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


# Vermerk hinter einer gestoppten Antwort — steht seit 2026-10-07 in
# core/gespraeche.py (gespeichert wird abgebrochen=True, der Vermerk kommt
# beim Lesen dazu). Der Name bleibt für alte Leser.
VERMERK_ABGEBROCHEN = gespraeche.VERMERK_ABGEBROCHEN

# So lange wartet der erste Zug nach der Antwort höchstens auf den Titel vom
# billigen Modell, um ihn noch im Strom zu melden. Die Antwort ist da schon
# vollständig angekommen; kommt er später, holt ihn die Gesprächsliste.
TITEL_WARTEN = 1.5


def _sse(obj):
    return f"data: {json.dumps(obj)}\n\n"


# So viel vom Ergebnis eines Werkzeugs bleibt im Verlauf (2026-10-07): die
# TUI klappt einen Schritt „Used memory ›" auf und zeigt es gekürzt — wie
# Claude Web. Mehr braucht die Anzeige nicht, und der Verlauf bleibt klein.
ERGEBNIS_MAX = 300


def _werkzeug_merken(werkzeuge, w):
    """Kurze Zusammenfassung der Werkzeuge eines Zugs für den Verlauf."""
    if w.get("phase") == "start":
        args = ", ".join("%s=%s" % (k, " ".join(str(v).split())[:60])
                         for k, v in (w.get("args") or {}).items())
        werkzeuge.append({"name": str(w.get("name") or "?"), "args": args[:200]})
    elif w.get("phase") in ("fertig", "fehler") and werkzeuge:
        if w.get("phase") == "fehler":
            werkzeuge[-1]["fehler"] = True
        text = " ".join(str(w.get("text") or "").split())
        if text:
            werkzeuge[-1]["ergebnis"] = (text[:ERGEBNIS_MAX - 1] + "…"
                                         if len(text) > ERGEBNIS_MAX else text)


def _wer_antwortet(backend):
    """(anbieter, modell) für den Verlauf — wer diese Antwort geschrieben hat."""
    try:
        if backend == ai_backends.CLOUD:
            prov = ai_backends.cloud_provider()
            return prov, ai_backends.chat_model(prov)
        return "lokal", ai.OLLAMA_MODEL
    except Exception:
        return None, None


def _sse_zug(stream, gid, backend, frage, erster):
    """Die Events eines Kern-Zugs als SSE-Zeilen; am Ende die Antwort ins
    Gespräch. Generator."""
    collected = []
    denken = []
    werkzeuge = []
    dokumente = []
    fehler_kam = False
    gestoppt = False

    for token in stream:
        if isinstance(token, dict):
            # ascii: Inline-Bild. permission: Erlaubnis-Frage, der Stream
            # blockiert bis /api/permission_answer. werkzeug: ein Tool-Call
            # beginnt/endet — sichtbar, WAS sie tut. cinema: News-Sendung
            # beginnt. Alles kein Antworttext → nicht in collected.
            if 'ascii' in token:
                yield _sse({'ascii': token['ascii'], 'name': token.get('name')})
            elif 'permission' in token:
                yield _sse({'permission': token['permission']})
            elif 'werkzeug' in token:
                _werkzeug_merken(werkzeuge, token['werkzeug'])
                yield _sse({'werkzeug': token['werkzeug']})
                # Was das Werkzeug gemeldet hat (core/zug.py): ein Dokument
                # in der Ablage → Event 'ablage', gemerkt mit der Antwort.
                for ereignis in zug.abholen():
                    if 'ablage' in ereignis:
                        dokumente.append(ereignis['ablage'])
                    yield _sse(ereignis)
            elif 'reflect' in token:
                # Denk-Strom: live an die TUI und seit 2026-10-07 auch mit
                # der Antwort gespeichert (Sashas Entscheidung 6).
                denken.append(str(token['reflect']))
                yield _sse({'reflect': token['reflect']})
            elif 'cinema' in token:
                yield _sse({'cinema': True})
            elif 'gestoppt' in token:
                # Sasha hat gestoppt (/api/chat/stop); die Schleife ist raus.
                gestoppt = True
                state.push_log("AI ■  gestoppt")
                yield _sse({'gestoppt': True})
            elif 'fehler' in token:
                # Backend-Fehler, Ablehnung, Rundengrenze: DIREKT an Sasha,
                # NICHT in den Verlauf — sonst läse die KI "[Cloud-Fehler: …]"
                # im nächsten Zug als ihre eigene Aussage.
                fehler_kam = True
                state.push_log(f"AI ✗  {token['fehler']}")
                yield _sse({'fehler': token['fehler']})
            continue
        collected.append(token)
        yield _sse({'token': token})

    # Ist der Zug an einem Fehler gescheitert, ohne dass Text kam, bleibt die
    # Frage unbeantwortet stehen — eine leere Antwort wäre eine Behauptung
    # ("ich habe nichts gesagt"), die nicht stimmt. Gestoppt: was da war,
    # bleibt mit abgebrochen=True; ohne Text landet nichts im Verlauf.
    text = "".join(collected)
    speichern = bool(text.strip()) if gestoppt else bool(collected or not fehler_kam)
    if speichern:
        anbieter, modell = _wer_antwortet(backend)
        gespraeche.anhaengen(
            gid, "assistant", text.rstrip() if gestoppt else text,
            denken="".join(denken), werkzeuge=werkzeuge, anbieter=anbieter,
            modell=modell, abgebrochen=gestoppt, dokumente=dokumente or None)
        # Sasha hat zugeschaut, also gelesen.
        gespraeche.gelesen_setzen(gid)
        if erster:
            if gespraech_titel.braucht_modell(gid):
                t = gespraech_titel.im_hintergrund(
                    gid, frage, text, cloud=(backend == ai_backends.CLOUD))
                t.join(TITEL_WARTEN)
            titel = gespraeche.kopf(gid).get("titel")
            if titel:
                yield _sse({'titel': titel, 'gespraech': gid})

    # Abschluss-Signal für den Client
    yield _sse({'done': True})


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
    """Die Nachrichten eines Gesprächs für die Anzeige (?gespraech=<id>,
    sonst das aktive dieses Rechners). Liste von {id, role, content, ts}
    plus denken, werkzeuge, abgebrochen, anbieter, modell, wenn vorhanden.
    Markiert das Gespräch als gelesen — wer das holt, zeigt es an.

    Seit 2026-10-07 auch ohne KI-Backend: alte Gespräche lesen braucht
    keins (vorher: [] ohne Backend)."""
    gid = request.args.get('gespraech')
    if gid and not gespraeche.gibt_es(gid):
        return jsonify({"error": "Dieses Gespräch gibt es nicht."}), 404
    gid = gid or gespraeche.aktiv()
    if not gid:
        return jsonify([])
    raus = []
    for n in gespraeche.nachrichten(gid):
        m = {"id": n["id"], "role": n["rolle"], "ts": n["ts"],
             "content": gespraeche.text_fuer_ki(n)}
        for feld in ("denken", "werkzeuge", "abgebrochen", "anbieter", "modell",
                     "anhaenge", "dokumente"):
            if n.get(feld):
                m[feld] = n[feld]
        raus.append(m)
    gespraeche.gelesen_setzen(gid)
    return jsonify(raus)


@bp.route('/api/chat/clear', methods=['POST'])
def api_chat_clear():
    """Neues Gespräch (/neu im Chat). Seit 2026-10-07 wird nichts mehr
    gelöscht: das alte bleibt in der Liste, das nächste Senden legt ein
    neues an. Gehört das offene Gespräch zu einem Projekt, gehört das neue
    auch dazu (Phase 6) — Body {projekt: id|null} setzt es ausdrücklich."""
    body = request.get_json(silent=True) or {}
    if "projekt" in body:
        projekt = body.get("projekt") or None
        if projekt and not projekte.gibt_es(str(projekt)):
            return jsonify({"error": "Dieses Projekt gibt es nicht."}), 404
    else:
        alt = gespraeche.aktiv()
        projekt = gespraeche.projekt_von(alt) if alt else gespraeche.neu_projekt()
    gespraeche.aktiv_setzen(None, projekt=projekt)
    erlaubnis.gespraech_beginnt(None)     # neues Gespräch: Gesprächs-Erlaubnis weg
    return jsonify({"ok": True, "projekt": projekt,
                    "name": projekte.name(projekt) if projekt else None})


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
    if match is None and answer.lower() == "ja":
        # Rückwärts (2026-10-07): die Erlaubnis-Frage hat jetzt Knöpfe mit
        # Geltung („ja, nur dieses mal" …). Ein Client, der nur „ja" kennt,
        # meint das einmalige Ja — das steht vorn.
        match = next((o for o in options if o.lower().startswith("ja, ")), None)
    if match is None:
        return jsonify({"error": f"answer must be one of {options}"}), 400
    state.answer_permission(match)
    return jsonify({"ok": True})


@bp.route('/api/erlaubnis', methods=['GET'])
def api_erlaubnis():
    """Was gerade ohne Frage erlaubt ist (2026-10-07, /erlaubnis im Chat):
    {immer: [{name, was}], gespraech: [{name, was}], gespraech_id}."""
    return jsonify(erlaubnis.uebersicht())


@bp.route('/api/erlaubnis/zuruecknehmen', methods=['POST'])
def api_erlaubnis_zuruecknehmen():
    """Body {werkzeug: name} oder {alle: true}. -> {weg: [namen], …übersicht}.
    Nichts zurückzunehmen ist kein Fehler (weg = [])."""
    body = request.get_json(silent=True) or {}
    name = str(body.get('werkzeug') or '').strip()
    if not name and not body.get('alle'):
        return jsonify({"error": "Welches Werkzeug? (werkzeug oder alle)"}), 400
    weg = erlaubnis.zuruecknehmen(None if body.get('alle') else name)
    return jsonify(dict(erlaubnis.uebersicht(), weg=weg))


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
