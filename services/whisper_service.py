# services/whisper_service.py
#
# Whisper STT-Service – läuft auf dem Linux-PC, nicht auf dem Pi.
#
# Der Browser nimmt Audio auf und schickt die .wav-Datei an diesen Service.
# Whisper transkribiert sie und gibt den Text zurück.
#
# ── Starten ───────────────────────────────────────────────────────────
#   pip install faster-whisper flask
#   python services/whisper_service.py
#
# ── Endpoint ──────────────────────────────────────────────────────────
#   POST http://<PC-IP>:5050/transcribe
#   Body: multipart/form-data mit
#     audio  – WAV-Datei (Pflichtfeld)
#     lang   – ISO-Sprachcode wie 'de', 'zh', 'en'. Default: WHISPER_LANG
#              (env-Variable, default 'de'). Wird als language-Hint an
#              faster-whisper durchgereicht.
#   Response: {"text": "...", "language": "de", "confidence": 0.95}
#
# ── Warum sprache als param? ──────────────────────────────────────────
#   Whisper kann die Sprache theoretisch raten. Bei kurzen Samples (1–2 Sek)
#   landet das aber gerne mal in der falschen Sprache, vor allem zwischen
#   ähnlich klingenden Lauten. Der Aufrufer weiß sicher, was er will
#   (Tutor → 'zh', Main-Chat → 'de'), also packen wir's rein.
#
# ── Warum faster-whisper statt openai-whisper? ────────────────────────
#   faster-whisper ist eine Reimplementierung in CTranslate2 –
#   deutlich schneller auf CPU, gleiche Qualität.
#   Modell-Optionen: tiny, base, small, medium (Größe vs. Qualität)
#   Multilingual ab "small" sinnvoll (ca. 500MB).

import os
import tempfile
import logging

from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Modell laden (einmalig beim Start) ────────────────────────────────
# "small" ist gut multilingual auf CPU. "medium" ist besser aber langsamer.
# device="cpu", compute_type="int8" = schnellste CPU-Variante.
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")
WHISPER_LANG_DEFAULT = os.environ.get("WHISPER_LANG", "de")
log.info(f"Lade Whisper-Modell '{WHISPER_MODEL_SIZE}' (erster Start dauert etwas – Download)...")
model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
log.info(f"Whisper bereit. Default-Sprache: {WHISPER_LANG_DEFAULT}")


@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    Nimmt eine Audio-Datei entgegen und gibt den transkribierten Text zurück.

    Erwartet: multipart/form-data mit
      audio – WAV/MP3-Datei (Pflichtfeld)
      lang  – Sprachcode (optional, default WHISPER_LANG_DEFAULT). Wird als
              language-Hint an faster-whisper gereicht.

    Gibt zurück: JSON {"text": "...", "language": "...", "confidence": 0.95}
    """
    if 'audio' not in request.files:
        return jsonify({"error": "kein 'audio'-Feld in der Anfrage"}), 400

    audio_file = request.files['audio']
    # Sprachcode aus dem multipart-Form ziehen, sonst Default.
    # request.form.get gibt None zurück wenn das Feld fehlt – wir akzeptieren
    # nur kurze Codes (max 5 Zeichen) als billiger Validierungs-Sanity-Check.
    lang_raw = (request.form.get('lang') or '').strip().lower()
    lang     = lang_raw if (1 <= len(lang_raw) <= 5) else WHISPER_LANG_DEFAULT

    # Temporäre Datei auf Disk schreiben (faster-whisper braucht einen Dateipfad)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        audio_file.save(tmp.name)
        tmp_path = tmp.name

    try:
        log.info(f"Transkribiere '{audio_file.filename}' lang={lang} ...")

        # language=<lang> zwingt Whisper auf eine konkrete Sprache.
        # beam_size=5 = bessere Qualität auf Kosten von etwas mehr Zeit.
        segments, info = model.transcribe(
            tmp_path,
            language=lang,
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
