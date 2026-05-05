# services/tts_service.py
#
# Offline Mandarin-TTS mit sherpa-onnx – läuft auf dem Linux-PC.
#
# Modell: vits-zh-aishell3 (Apache 2.0, 174 Sprecher, ~120MB)
# Kein Internet nötig nach dem einmaligen Modell-Download.
#
# ── Setup (einmalig) ──────────────────────────────────────────────────
#   pip install sherpa-onnx soundfile
#   python services/download_tts_model.py
#
# ── Starten ───────────────────────────────────────────────────────────
#   python services/tts_service.py
#
# ── Endpoint ──────────────────────────────────────────────────────────
#   POST http://<PC-IP>:5051/speak
#   Body: JSON {"text": "你好，今天天气怎么样？", "speed": 1.0, "speaker": 0}
#   Response: audio/wav
#
#   GET http://<PC-IP>:5051/health
#   Response: {"ok": true, "engine": "sherpa-onnx", "speakers": 174}
#
# ── Warum sherpa-onnx? ────────────────────────────────────────────────
#   Keine Systemabhängigkeiten (kein MeCab, kein espeak).
#   Läuft auf CPU, gute Mandarin-Qualität, MIT/Apache-Modelle.
#   Wenn MeloTTS später installiert ist, kann man auf dieses wechseln.

import io
import logging
import os
import tempfile

import soundfile as sf
from flask import Flask, request, jsonify, send_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# Pfad zum heruntergeladenen Modell (download_tts_model.py legt es dort ab)
_MODEL_DIR  = os.path.join(os.path.dirname(__file__), '..', 'data', 'tts_model', 'vits-zh-aishell3')
_MODEL_FILE = os.path.join(_MODEL_DIR, 'vits-aishell3.onnx')
_LEXICON    = os.path.join(_MODEL_DIR, 'lexicon.txt')
_TOKENS     = os.path.join(_MODEL_DIR, 'tokens.txt')

# ── TTS-Modell laden ──────────────────────────────────────────────────
tts = None
try:
    import sherpa_onnx
    if os.path.exists(_MODEL_FILE):
        tts_config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=_MODEL_FILE,
                    lexicon=_LEXICON,
                    tokens=_TOKENS,
                    # data_dir enthält weitere Ressourcen des Modells
                    data_dir=os.path.join(_MODEL_DIR, 'espeak-ng-data'),
                ),
                # Anzahl Threads für Inferenz (2–4 gut für CPU)
                num_threads=2,
                # debug=False damit kein Spam in der Konsole
                debug=False,
            ),
        )
        tts = sherpa_onnx.OfflineTts(tts_config)
        log.info(f"sherpa-onnx TTS geladen. Sprecher verfügbar: {tts.num_speakers}")
    else:
        log.warning(f"Modell nicht gefunden: {_MODEL_FILE}")
        log.warning("Bitte 'python services/download_tts_model.py' ausführen.")
except ImportError:
    log.error("sherpa-onnx nicht installiert. 'pip install sherpa-onnx' ausführen.")
except Exception as e:
    log.error(f"TTS-Ladefehler: {e}")


@app.route('/speak', methods=['POST'])
def speak():
    """
    Generiert Mandarin-Sprache aus Text und gibt WAV-Audio zurück.

    JSON-Body:
      text     – der zu sprechende Text (Mandarin)
      speed    – Sprechgeschwindigkeit (default 0.9, langsamer als 1.0 für Klarheit)
      speaker  – Sprecher-ID 0–173 (default 0)
    """
    if tts is None:
        return jsonify({"error": "TTS-Modell nicht geladen. download_tts_model.py ausführen."}), 503

    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({"error": "kein 'text' in der Anfrage"}), 400

    text     = data['text']
    speed    = float(data.get('speed', 0.9))    # leicht langsamer für Lern-Kontext
    speaker  = int(data.get('speaker', 0))

    log.info(f"TTS Sprecher {speaker}: '{text[:60]}'")

    try:
        # audio.samples = numpy-Array (float32), audio.sample_rate = 22050
        audio = tts.generate(text, sid=speaker, speed=speed)

        # In WAV-Bytes umwandeln (in-memory, keine Temp-Datei nötig)
        buf = io.BytesIO()
        sf.write(buf, audio.samples, audio.sample_rate, format='WAV', subtype='PCM_16')
        buf.seek(0)

        return send_file(buf, mimetype='audio/wav')

    except Exception as e:
        log.error(f"TTS Fehler: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health')
def health():
    """Health-Check für ZENTRALE."""
    return jsonify({
        "ok":      tts is not None,
        "engine":  "sherpa-onnx / vits-zh-aishell3",
        "speakers": tts.num_speakers if tts else 0,
    })


if __name__ == '__main__':
    # Port 5051 – kein Konflikt mit ZENTRALE (5000) oder Whisper (5050)
    # host="0.0.0.0" damit der Pi im Netzwerk drauf zugreifen kann
    app.run(host='0.0.0.0', port=5051, debug=False)
