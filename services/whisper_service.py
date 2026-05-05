# services/whisper_service.py
#
# Whisper STT-Service – läuft auf dem Linux-PC, nicht auf dem Pi.
#
# Der Pi nimmt Audio auf und schickt die .wav-Datei an diesen Service.
# Whisper transkribiert sie und gibt den Text zurück.
#
# ── Starten ───────────────────────────────────────────────────────────
#   pip install faster-whisper flask
#   python services/whisper_service.py
#
# ── Endpoint ──────────────────────────────────────────────────────────
#   POST http://<PC-IP>:5050/transcribe
#   Body: multipart/form-data mit Feld "audio" (WAV-Datei)
#   Response: {"text": "...", "language": "zh"}
#
# ── Warum faster-whisper statt openai-whisper? ────────────────────────
#   faster-whisper ist eine reimplementierung in CTranslate2 –
#   deutlich schneller auf CPU, gleiche Qualität.
#   Modell-Optionen: tiny, base, small, medium (Größe vs. Qualität)
#   Für Mandarin: "small" ist ein guter Kompromiss (ca. 500MB, gut auf CPU).

import os
import tempfile
import logging

from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Modell laden (einmalig beim Start) ────────────────────────────────
# "small" ist gut für Mandarin auf CPU. "medium" ist besser aber langsamer.
# device="cpu", compute_type="int8" = schnellste CPU-Variante.
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
log.info(f"Lade Whisper-Modell '{WHISPER_MODEL_SIZE}' (erster Start dauert etwas – Download)...")
model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
log.info("Whisper bereit.")


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    Nimmt eine Audio-Datei entgegen und gibt den transkribierten Text zurück.

    Erwartet: multipart/form-data mit Feld 'audio' (WAV oder MP3).
    Gibt zurück: JSON {"text": "...", "language": "zh", "duration_s": 2.3}

    language="zh" zwingt Whisper zu Mandarin.
    Ohne diesen Hint würde Whisper die Sprache raten – bei kurzem Input
    kann das danebengehen besonders bei Mandarin.
    """
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld in der Anfrage"}), 400

    audio_file = request.files['audio']

    # Temporäre Datei auf Disk schreiben (faster-whisper braucht einen Dateipfad)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        log.info(f"Transkribiere '{audio_file.filename}' ...")

        # language="zh" = Mandarin erzwingen
        # beam_size=5 = bessere Qualität auf Kosten von etwas mehr Zeit
        segments, info = model.transcribe(
            tmp_path,
            language="zh",
            beam_size=5,
        )

        # Segments sind ein Generator – zusammensetzen
        text = "".join(seg.text for seg in segments).strip()

        log.info(f"Ergebnis: '{text}' (Sprache erkannt: {info.language}, Konfidenz: {info.language_probability:.2f})")
        return jsonify({
            "text":       text,
            "language":   info.language,
            "confidence": round(info.language_probability, 2),
        })
    finally:
        # Temporäre Datei immer löschen, auch bei Fehler
        os.unlink(tmp_path)


@app.route('/health')
def health():
    """Einfacher Health-Check – ZENTRALE fragt damit ob der Service läuft."""
    return jsonify({"ok": True, "model": WHISPER_MODEL_SIZE})


if __name__ == '__main__':
    # Läuft auf Port 5050 (Flask ZENTRALE nutzt 5000, kein Konflikt).
    # host="0.0.0.0" damit der Pi im gleichen Netzwerk drauf zugreifen kann.
    app.run(host='0.0.0.0', port=5050, debug=False)
