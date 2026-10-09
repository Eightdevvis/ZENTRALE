# ui/routen/stimme.py
#
# Stimme: Sprechen (TTS) und Zuhören (Whisper), sprachneutral für Kern und Tutor.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, Response, jsonify, request

import ai_backends     # type: ignore  – AI-Backend-Verfügbarkeit (local/cloud, EXTERNAL-Box)
import audio        # type: ignore
import tutor_port    # type: ignore  – EINZIGER Griff am Sprach-Tutor (Addon).
                     # Nicht tutor_* direkt importieren: der Port haelt den Tutor
                     # rausziehbar und wendet die ZENTRALE-Drossel an.

from ui.routen.gemeinsam import _ki_nicht_verfuegbar

bp = Blueprint('stimme', __name__)


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
# memory/tutor/tutor_system.md). Wer Mandarin sprechen will, ruft die
# generische API mit `lang='zh'` auf.


@bp.route('/api/speak', methods=['POST'])
def api_speak():
    """
    Text -> WAV. Sprachneutral.

    Body (JSON):
      text     – Pflichtfeld
      lang     – Sprachcode (default: Einstellung default_lang, core/audio.py)
      speed    – Sprechgeschwindigkeit (default 1.2 = ZENTRALE-Chat; 1.0 natuerlich, <1.0 langsamer)
      speaker  – Sprecher-ID (default 0; bedeutung modellabhaengig)

    Response: audio/wav, oder 503 wenn das Modell fuer die Sprache fehlt.
    """
    # TTS ist LOKALE Synthese (sherpa/Piper) und der Sprach-Tutor laeuft
    # kapazitaetsbasiert ueber die Cloud – unabhaengig von der lokalen KI.
    # Nur blocken, wenn AUCH der Tutor kein Backend hat; sonst kriegt die Persona-
    # Stimme keinen Ton, obwohl der Tutor laeuft (verifiziert: /api/speak gab 503
    # 'KI deaktiviert', obwohl der Cloud-Tutor verfuegbar war).
    if ai_backends.lokale_ki_aus() and not tutor_port.available():
        return _ki_nicht_verfuegbar()
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


@bp.route('/api/transcribe', methods=['POST'])
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
    if ai_backends.lokale_ki_aus() and not tutor_port.available():
        return _ki_nicht_verfuegbar()
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld"}), 400

    audio_bytes = request.files['audio'].read()
    lang        = (request.form.get('lang') or '').strip() or None
    text        = audio.transcribe(audio_bytes, lang=lang)
    # audio.transcribe liefert Fehler als '[STT …]'-Text zurueck. Der darf NIE
    # als Aussage beim Tutor landen (2026-09-19: Ling Ling antwortete auf
    # '[STT nicht erreichbar: …]') — hier wird daraus ein echter Fehler.
    if text.startswith("[STT"):
        return jsonify({"error": text.strip("[]"), "text": ""}), 503
    return jsonify({"text": text})
