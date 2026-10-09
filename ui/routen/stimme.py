# ui/routen/stimme.py
#
# Stimme: Sprechen (TTS) und Zuhören (Whisper), sprachneutral.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, Response, jsonify, request

import ai_backends     # type: ignore  – AI-Backend-Verfügbarkeit (local/cloud, EXTERNAL-Box)
import audio        # type: ignore

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
# Der Sprach-Tutor ist seit 2026-10-09 eine eigene App (Repo language-tutor)
# und redet über seinen eigenen Server mit den Stimm-Diensten. Wer hier
# eine andere Sprache will, ruft die API mit `lang='zh'` o. ä. auf.


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
    # Der Sprach-Tutor spricht seit 2026-10-09 über seinen eigenen Server
    # direkt mit dem TTS-Dienst; hier fragt nur noch ZENTRALE selbst.
    if ai_backends.lokale_ki_aus():
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
    if ai_backends.lokale_ki_aus():
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
