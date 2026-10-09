# core/audio.py
#
# HTTP-Client für die Audio-Services (Whisper STT + TTS-Engines).
#
# Die eigentliche Aufnahme und Wiedergabe passiert im Browser (MediaRecorder +
# Web Audio API) – audio.py ist nur der Vermittler zwischen Flask und den
# Services die auf dem Linux-PC laufen.
#
# Sprach-neutral: jede Funktion nimmt ein `lang`-Argument ('de', 'zh', …),
# das an die Services durchgereicht wird. Der Tutor (Mandarin) ist nur ein
# Aufrufer mit `lang='zh'` – Voice-Pipeline ist NICHT mehr tutor-spezifisch.
# Frühere Annahme „alles Mandarin" gilt nicht, der Mandarin-Pfad ist jetzt
# ein Spezialfall.
#
# Whisper-Service: http://<WHISPER_HOST>:5050/transcribe
# TTS-Service:     http://<TTS_HOST>:5051/speak
#
# Einstellungen (ai_config.setting, Env ZENTRALE_<NAME>, seit 2026-10-08;
# vorher eigene Env-Namen ohne ZENTRALE_, die gelten übergangsweise noch):
#   whisper_url    – default: http://localhost:5050
#   tts_url        – default: http://localhost:5051
#   default_lang   – default: 'de'  (Fallback wenn Aufrufer kein lang angibt)
# Gelesen bei JEDEM Aufruf, nicht beim Import — so greift Live-Umschalten.

import os
import urllib.request
import urllib.error
import json as _json
import ai_config
import state  # für Terminal-Logging


def _whisper_url() -> str:
    return str(ai_config.setting("whisper_url", "http://localhost:5050")).rstrip("/")


def _tts_url() -> str:
    return str(ai_config.setting("tts_url", "http://localhost:5051")).rstrip("/")


def _default_lang() -> str:
    return str(ai_config.setting("default_lang", "de"))


def transcribe(audio_bytes: bytes, filename: str = "audio.wav",
               lang: str = None) -> str:
    """
    Schickt rohe Audio-Bytes an den Whisper-Service und gibt den
    transkribierten Text zurück.

    audio_bytes: WAV-Datei als bytes (kommt vom Browser via Flask)
    filename:    Dateiname für den multipart-Upload (nur für Logging)
    lang:        Sprach-Hint für Whisper. None → Einstellung default_lang.
                 Werte z.B. 'de' (deutsch), 'zh' (mandarin), 'en' (englisch).
    Rückgabe:    erkannter Text, oder Fehlermeldung
    """
    if lang is None:
        lang = _default_lang()

    url = f"{_whisper_url()}/transcribe"
    state.push_log(f"STT →  POST {url} ({len(audio_bytes)//1024} KB, lang={lang})")

    # multipart/form-data manuell bauen – urllib hat keine eingebaute Hilfe dafür.
    # Wir packen das audio-File UND ein zweites Feld "lang" rein, damit
    # whisper_service.py die Sprache nicht raten muss (kurze Samples landen
    # sonst gerne in der falschen Sprache).
    boundary = b"----ZentraleBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="audio"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + audio_bytes + b"\r\n"
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="lang"\r\n\r\n'
        + lang.encode() + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    headers = {
        "Content-Type":   f"multipart/form-data; boundary={boundary.decode()}",
        "Content-Length": str(len(body)),
    }

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read().decode("utf-8"))
            text   = result.get("text", "").strip()
            conf   = result.get("confidence", 0)
            state.push_log(f"STT ←  '{' / '.join(text.splitlines())[:80]}' (Konfidenz: {conf:.0%})")
            return text
    except urllib.error.URLError as e:
        msg = f"[STT nicht erreichbar: {e.reason}]"
        state.push_log(msg)
        return msg
    except Exception as e:
        msg = f"[STT Fehler: {e}]"
        state.push_log(msg)
        return msg


def synthesize(text: str, lang: str = None,
               speed: float = 1.2, speaker: int = 0) -> bytes:
    """
    Schickt Text an den TTS-Service und gibt WAV-Audio-Bytes zurück.
    Flask proxied die Bytes direkt an den Browser.

    text:    der zu sprechende Text
    lang:    Zielsprache. None → Einstellung default_lang. Werte: 'de', 'zh', …
             Welche Sprachen wirklich gehen, entscheidet tts_service.py
             (abhängig von den geladenen Modellen).
    speed:   Sprechgeschwindigkeit (ZENTRALE-Chat-Default 1.2 = etwas flotter;
             1.0 = natuerlich, <1.0 dehnt/langsamer, z.B. 0.9 fuer den Tutor)
    speaker: Sprecher-ID (modellabhängig: vits-zh-aishell3 hat 174,
             Piper-Modelle haben typischerweise 1)
    Rückgabe: WAV-Datei als bytes, oder leeres bytes bei Fehler
    """
    if lang is None:
        lang = _default_lang()

    url = f"{_tts_url()}/speak"
    kurz = " / ".join(t.strip() for t in text.splitlines() if t.strip())[:60]
    state.push_log(f"TTS →  POST {url} '{kurz}' (lang={lang})")

    payload = _json.dumps({
        "text":    text,
        "lang":    lang,
        "speed":   speed,
        "speaker": speaker,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            wav = resp.read()
            state.push_log(f"TTS ←  {len(wav)//1024} KB WAV")
            return wav
    except urllib.error.URLError as e:
        state.push_log(f"[TTS nicht erreichbar: {e.reason}]")
        return b""
    except Exception as e:
        state.push_log(f"[TTS Fehler: {e}]")
        return b""


def whisper_available() -> bool:
    """Health-Check für Whisper-Service."""
    try:
        urllib.request.urlopen(f"{_whisper_url()}/health", timeout=2)
        return True
    except Exception:
        return False


def tts_available() -> bool:
    """Health-Check für TTS-Service."""
    try:
        urllib.request.urlopen(f"{_tts_url()}/health", timeout=2)
        return True
    except Exception:
        return False
