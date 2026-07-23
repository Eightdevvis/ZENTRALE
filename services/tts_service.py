# services/tts_service.py
#
# Offline TTS-Service – läuft auf dem Linux-PC.
#
# Multi-Engine: pro Sprache kann ein anderes Modell geladen sein.
# Aktuell installiert:
#   - 'zh' (Mandarin)  – sherpa-onnx mit vits-zh-aishell3 (174 Sprecher,
#                         Apache 2.0, ~120MB)
#   - 'de' (Deutsch)   – Piper, Voice via Env PIPER_DE_VOICE
#                         (Default: de_DE-kerstin-low)
# Andere Sprachen → 503 mit klarer Fehlermeldung, damit der Aufrufer weiß
# dass die Pipeline existiert aber das Modell nicht.
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
#   Body: JSON {"text": "...", "lang": "de", "speed": 0.9, "speaker": 0}
#         lang     – ISO-Sprachcode. Default 'de'.
#         speed    – Sprechgeschwindigkeit (1.0 = normal).
#         speaker  – Sprecher-ID, modellabhängig.
#   Response (200): audio/wav  – generierte Sprache
#   Response (503): JSON-Error wenn für die Sprache kein Modell geladen ist
#
#   GET http://<PC-IP>:5051/health
#   Response: {"ok": true, "engines": {"zh": {...}, "de": {...}}}
#
# ── Warum sherpa-onnx für Mandarin? ────────────────────────────────────
#   Keine Systemabhängigkeiten (kein MeCab, kein espeak), CPU-only,
#   gute Mandarin-Qualität, freie Modelle. Für Deutsch wechseln wir
#   bewusst die Engine (Piper) statt zu versuchen sherpa-onnx
#   deutsche Stimmen einzusperren.

import io
import logging
import os
import tempfile

import soundfile as sf
from flask import Flask, request, jsonify, send_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)

_DATA_ROOT = os.path.join(os.path.dirname(__file__), '..', 'data', 'tts_model')

# Default-Sprache wenn der Aufrufer nichts schickt. Per env-var
# umstellbar (z.B. wenn das Setup primaer Mandarin nutzt).
DEFAULT_LANG = os.environ.get("TTS_DEFAULT_LANG", "de")

# Welche deutsche Piper-Stimme geladen wird. Voice-ID exakt wie im
# rhasspy/piper-voices-Repo (z.B. 'de_DE-kerstin-low',
# 'de_DE-thorsten-medium'). Der Ordnername unter data/tts_model/ und
# die Dateinamen leiten sich daraus ab. Stimme wechseln =
# download_tts_model.py mit gleicher Env-Var laufen lassen, dann hier
# umstellen – kein Code-Edit noetig.
DE_VOICE = os.environ.get("PIPER_DE_VOICE", "de_DE-kerstin-low")

# Spanisch (Tutor-Persona Lucía): sherpa-onnx-Piper-Voice, tauschbar wie
# DE_VOICE (Ordnername unter data/tts_model/). sharvard-medium hat 2 Sprecher
# (sid 0 = männlich ~122 Hz, sid 1 = weiblich ~204 Hz, gemessen) → Default 1,
# damit Lucía weiblich klingt. Sprecher-Wechsel per env, kein Code-Edit.
ES_VOICE   = os.environ.get("TUTOR_ES_VOICE", "vits-piper-es_ES-sharvard-medium-int8")
ES_SPEAKER = int(os.environ.get("TUTOR_ES_SPEAKER", "1"))

# Engine-Registry: lang -> Dict mit
#   - "speak"   Callable(text, speed, speaker) -> (samples_np, sample_rate)
#   - "info"    Dict fuer /health
# Wird beim Start befuellt. Eintrag fehlt = Sprache nicht verfuegbar -> 503.
_engines = {}


# ── Satzzeichen fuers Sprachenlernen: bessere Prosodie/Pausen ───────────
# Die zh-Modelle machen Betonung/Pausen an chinesischen Vollbreite-Zeichen
# (！？。，) — lateinische ! ? , und vor allem …/... verschlucken sie (OOV).
# Fuer die Artikulation (Sasha lernt) normalisieren wir vor der Synthese.
_ZH_PUNCT = {'!': '！', '?': '？', ',': '，', ';': '；', ':': '：',
             '(': '（', ')': '）'}


def _normalize_zh_punct(text: str) -> str:
    text = (text or '').replace('...', '。').replace('…', '。')
    for a, b in _ZH_PUNCT.items():
        text = text.replace(a, b)
    return text


# ── Engine: Mandarin via sherpa-onnx ──────────────────────────────────
# Beste Artikulation zuerst: matcha-icefall-zh-baker (22 kHz, flow-matching,
# Profi-Frauenstimme Baker) → braucht einen Vocoder (vocos-22khz-univ.onnx).
# Dann MeloTTS (44.1 kHz, vits), zuletzt aishell3 (8 kHz, telefonig). Modelle
# via services/download_tts_model.py.
def _try_load_sherpa_zh():
    """Laedt das beste vorhandene Mandarin-Modell (matcha-Baker > MeloTTS >
    aishell3) und registriert die Engine fuer lang='zh'. Stille No-Op, wenn
    kein Modell/Vocoder oder die Library fehlt."""
    try:
        import sherpa_onnx
    except ImportError:
        log.error("sherpa-onnx nicht installiert (pip install sherpa-onnx).")
        return

    matcha  = os.path.join(_DATA_ROOT, 'matcha-icefall-zh-baker')
    vocoder = os.path.join(_DATA_ROOT, 'vocos-22khz-univ.onnx')
    melo    = os.path.join(_DATA_ROOT, 'vits-melo-tts-zh_en')
    ai3     = os.path.join(_DATA_ROOT, 'vits-zh-aishell3')
    rule_fsts = ''
    model_cfg = None

    if os.path.exists(os.path.join(matcha, 'model-steps-3.onnx')) and os.path.exists(vocoder):
        model_dir = matcha
        mc = sherpa_onnx.OfflineTtsMatchaModelConfig(
            acoustic_model=os.path.join(matcha, 'model-steps-3.onnx'),
            vocoder=vocoder,
            lexicon=os.path.join(matcha, 'lexicon.txt'),
            tokens=os.path.join(matcha, 'tokens.txt'),
            dict_dir=os.path.join(matcha, 'dict'),
        )
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(matcha=mc, num_threads=2, debug=False)
        fsts = [os.path.join(matcha, f) for f in ('date.fst', 'phone.fst', 'number.fst')]
        rule_fsts = ','.join(p for p in fsts if os.path.exists(p))
        engine_name = "sherpa-onnx / matcha-icefall-zh-baker (22kHz, flow-matching)"
    elif os.path.exists(os.path.join(melo, 'model.onnx')):
        model_dir = melo
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=os.path.join(melo, 'model.onnx'),
            lexicon=os.path.join(melo, 'lexicon.txt'),
            tokens=os.path.join(melo, 'tokens.txt'),
            dict_dir=os.path.join(melo, 'dict'),
        )
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=2, debug=False)
        fsts = [os.path.join(melo, f) for f in ('date.fst', 'phone.fst', 'number.fst')]
        rule_fsts = ','.join(p for p in fsts if os.path.exists(p))
        engine_name = "sherpa-onnx / vits-melo-tts-zh_en (44.1kHz)"
    elif os.path.exists(os.path.join(ai3, 'vits-aishell3.onnx')):
        model_dir = ai3
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=os.path.join(ai3, 'vits-aishell3.onnx'),
            lexicon=os.path.join(ai3, 'lexicon.txt'),
            tokens=os.path.join(ai3, 'tokens.txt'),
            data_dir=os.path.join(ai3, 'espeak-ng-data'),
        )
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=2, debug=False)
        engine_name = "sherpa-onnx / vits-zh-aishell3 (8kHz)"
    else:
        log.warning("kein zh-TTS-Modell gefunden (matcha/MeloTTS/aishell3). "
                    "'python services/download_tts_model.py zh' ausfuehren.")
        return

    try:
        cfg = sherpa_onnx.OfflineTtsConfig(model=model_cfg, rule_fsts=rule_fsts)
        engine = sherpa_onnx.OfflineTts(cfg)
    except Exception as e:
        log.error(f"sherpa-onnx Ladefehler ({model_dir}): {e}")
        return

    nspk = engine.num_speakers

    def speak_zh(text, speed, speaker):
        text = _normalize_zh_punct(text)              # bessere Pausen/Betonung
        sid = speaker if (isinstance(speaker, int) and 0 <= speaker < nspk) else 0
        audio = engine.generate(text, sid=sid, speed=speed)
        return audio.samples, audio.sample_rate

    _engines["zh"] = {
        "speak": speak_zh,
        "info": {"engine": engine_name, "speakers": nspk},
    }
    log.info(f"TTS-Engine zh geladen ({engine_name}, {nspk} Sprecher).")


# ── Engine: Deutsch via Piper (Voice via PIPER_DE_VOICE env) ──────────
def _try_load_de():
    """Versucht das deutsche Piper-Modell zu laden und registriert die
    Engine fuer lang='de'. Stille No-Op wenn Modell oder Library fehlen –
    /speak gibt dann 503 mit klarer Meldung zurueck.

    Welche Stimme geladen wird steht in DE_VOICE (Env PIPER_DE_VOICE).

    Piper hat KEINE Sprecher-Auswahl wie sherpa-onnx (die Voices sind
    Single-Speaker). Der `speaker`-Param wird daher ignoriert.
    Die `speed`-Steuerung geht ueber SynthesisConfig.length_scale – das
    ist invers: niedriger Wert = schneller. Wir mappen daher
    length_scale = 1.0 / speed, damit der gleiche speed-Param vom
    Aufrufer wie bei sherpa-onnx funktioniert (1.0 = normal, 0.9 = leicht
    langsamer)."""
    model_dir  = os.path.join(_DATA_ROOT, DE_VOICE)
    model_file = os.path.join(model_dir, f'{DE_VOICE}.onnx')
    cfg_file   = os.path.join(model_dir, f'{DE_VOICE}.onnx.json')
    if not (os.path.exists(model_file) and os.path.exists(cfg_file)):
        log.warning(f"Piper-DE Modell nicht gefunden: {model_file}")
        log.warning("Fuer Deutsch: 'python services/download_tts_model.py de' ausfuehren.")
        return

    try:
        from piper import PiperVoice
        from piper.config import SynthesisConfig
    except ImportError:
        log.error("piper-tts nicht installiert (pip install piper-tts).")
        return

    try:
        voice = PiperVoice.load(model_file, config_path=cfg_file)
    except Exception as e:
        log.error(f"Piper-DE Ladefehler: {e}")
        return

    def speak_de(text, speed, speaker):
        # Piper streamt AudioChunks pro Satz – wir konkatenieren in ein
        # einziges numpy-Array, damit das Engine-Interface
        # (samples, sample_rate) konsistent bleibt.
        import numpy as np
        # length_scale ist der einzige Speed-Knopf, den Piper hat.
        # Werte > 1 = langsamer, < 1 = schneller.
        cfg = SynthesisConfig(length_scale=(1.0 / max(0.1, speed)))
        chunks = list(voice.synthesize(text, syn_config=cfg))
        if not chunks:
            return np.zeros(0, dtype="float32"), 22050
        sample_rate = chunks[0].sample_rate
        # AudioChunk.audio_int16_array ist ein numpy-Array (int16) –
        # soundfile schreibt int16 direkt sauber als PCM_16-WAV.
        # Falls die Property fehlen sollte, faellt das aufrufende
        # try/except in der /speak-Route den Fehler ab.
        samples = np.concatenate([c.audio_int16_array for c in chunks])
        return samples, sample_rate

    _engines["de"] = {
        "speak": speak_de,
        "info": {
            "engine":   f"piper / {DE_VOICE}",
            "speakers": 1,
        },
    }
    log.info(f"TTS-Engine de geladen (piper, {DE_VOICE}).")


# ── Engine: Spanisch via sherpa-onnx (Piper-Voice, espeak-ng-Phonemik) ──────
def _try_load_es():
    """Laedt die spanische Piper-Voice ueber sherpa-onnx (dieselbe Library wie
    zh — KEIN separates piper-tts noetig) und registriert lang='es' fuer die
    Tutor-Persona Lucía. Stille No-Op, wenn Modell oder Library fehlen –
    /speak gibt dann 503 zurueck. Modell/Sprecher via TUTOR_ES_VOICE/
    TUTOR_ES_SPEAKER umstellbar (siehe oben).

    Aufbau wie der aishell3-Zweig von zh: VITS-Modell + espeak-ng-data als
    data_dir (Phonemik). sharvard ist multi-speaker → num_speakers>1, wir
    waehlen ES_SPEAKER (weiblich), es sei denn der Aufrufer gibt explizit eine
    andere gueltige ID (das Zimmer schickt einen globalen zh-Default, der hier
    ausserhalb des Bereichs liegt und daher auf ES_SPEAKER zurueckfaellt)."""
    try:
        import sherpa_onnx
    except ImportError:
        log.error("sherpa-onnx nicht installiert (pip install sherpa-onnx).")
        return

    model_dir = os.path.join(_DATA_ROOT, ES_VOICE)
    onnx = os.path.join(model_dir, 'es_ES-sharvard-medium.onnx')
    if not os.path.exists(onnx):                       # Voice getauscht → erstes *.onnx nehmen
        import glob
        cands = sorted(glob.glob(os.path.join(model_dir, '*.onnx')))
        onnx = cands[0] if cands else onnx
    tokens = os.path.join(model_dir, 'tokens.txt')
    espeak = os.path.join(model_dir, 'espeak-ng-data')
    if not (os.path.exists(onnx) and os.path.exists(tokens) and os.path.isdir(espeak)):
        log.warning(f"kein es-TTS-Modell gefunden ({model_dir}). "
                    "'python services/download_tts_model.py es' ausfuehren.")
        return

    try:
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=onnx, tokens=tokens, data_dir=espeak)
        model_cfg = sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=2, debug=False)
        engine = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=model_cfg))
    except Exception as e:
        log.error(f"sherpa-onnx es Ladefehler ({model_dir}): {e}")
        return

    nspk = engine.num_speakers

    def speak_es(text, speed, speaker):
        sid = speaker if (isinstance(speaker, int) and 0 <= speaker < nspk) else ES_SPEAKER
        if not (0 <= sid < nspk):
            sid = 0
        audio = engine.generate(text, sid=sid, speed=speed)
        return audio.samples, audio.sample_rate

    _engines["es"] = {
        "speak": speak_es,
        "info": {"engine": f"sherpa-onnx / {ES_VOICE}", "speakers": nspk},
    }
    log.info(f"TTS-Engine es geladen (sherpa-onnx / {ES_VOICE}, {nspk} Sprecher, "
             f"Lucía=sid {ES_SPEAKER}).")


# Beim Modul-Start alle Versuche durchlaufen lassen.
_try_load_sherpa_zh()
_try_load_de()
_try_load_es()


@app.route('/speak', methods=['POST'])
def speak():
    """
    Generiert Sprache aus Text und gibt WAV-Audio zurueck.

    JSON-Body:
      text     – der zu sprechende Text (Pflicht)
      lang     – ISO-Sprachcode, default DEFAULT_LANG (env). Muss in
                 _engines registriert sein, sonst 503.
      speed    – Sprechgeschwindigkeit (default 0.9, leicht langsamer
                 als 1.0 fuer Klarheit). Modell-abhaengig ob das wirkt.
      speaker  – Sprecher-ID. Modell-abhaengig. Default 0.
    """
    data = request.get_json()
    if not data or not data.get('text'):
        return jsonify({"error": "kein 'text' in der Anfrage"}), 400

    text    = data['text']
    lang    = (data.get('lang') or DEFAULT_LANG).lower()
    speed   = float(data.get('speed', 0.9))
    speaker = int(data.get('speaker', 0))

    engine = _engines.get(lang)
    if not engine:
        available = sorted(_engines.keys()) or ["(keine)"]
        return jsonify({
            "error":   f"Kein TTS-Modell fuer lang='{lang}' geladen.",
            "available_langs": available,
            "hint":    "Modell installieren (siehe services/download_tts_model.py) oder anderen lang-Wert schicken.",
        }), 503

    log.info(f"TTS lang={lang} sprecher={speaker}: '{text[:60]}'")

    try:
        samples, sample_rate = engine["speak"](text, speed, speaker)
        # In WAV-Bytes umwandeln (in-memory, keine Temp-Datei noetig)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format='WAV', subtype='PCM_16')
        buf.seek(0)
        return send_file(buf, mimetype='audio/wav')

    except Exception as e:
        log.error(f"TTS Fehler: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/health')
def health():
    """Health-Check fuer ZENTRALE. Liefert pro Sprache die geladene Engine."""
    engines_info = {lang: e["info"] for lang, e in _engines.items()}
    return jsonify({
        "ok":            len(_engines) > 0,
        "default_lang":  DEFAULT_LANG,
        "engines":       engines_info,
    })


if __name__ == '__main__':
    # Port 5051 – kein Konflikt mit ZENTRALE (5000) oder Whisper (5050)
    # host="0.0.0.0" damit der Pi im Netzwerk drauf zugreifen kann
    app.run(host='0.0.0.0', port=5051, debug=False)
