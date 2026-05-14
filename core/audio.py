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
# Konfiguration via Umgebungsvariablen:
#   WHISPER_URL    – default: http://localhost:5050
#   TTS_URL        – default: http://localhost:5051
#   DEFAULT_LANG   – default: 'de'  (Fallback wenn Aufrufer kein lang angibt)

import os
import urllib.request
import urllib.error
import json as _json
import state  # für Terminal-Logging

WHISPER_URL  = os.environ.get("WHISPER_URL",  "http://localhost:5050")
TTS_URL      = os.environ.get("TTS_URL",      "http://localhost:5051")
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "de")


def transcribe(audio_bytes: bytes, filename: str = "audio.wav",
               lang: str = None) -> str:
    """
    Schickt rohe Audio-Bytes an den Whisper-Service und gibt den
    transkribierten Text zurück.

    audio_bytes: WAV-Datei als bytes (kommt vom Browser via Flask)
    filename:    Dateiname für den multipart-Upload (nur für Logging)
    lang:        Sprach-Hint für Whisper. None → DEFAULT_LANG (env-bar).
                 Werte z.B. 'de' (deutsch), 'zh' (mandarin), 'en' (englisch).
    Rückgabe:    erkannter Text, oder Fehlermeldung
    """
    if lang is None:
        lang = DEFAULT_LANG

    url = f"{WHISPER_URL}/transcribe"
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
            state.push_log(f"STT ←  '{text}' (Konfidenz: {conf:.0%})")
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
               speed: float = 0.9, speaker: int = 0) -> bytes:
    """
    Schickt Text an den TTS-Service und gibt WAV-Audio-Bytes zurück.
    Flask proxied die Bytes direkt an den Browser.

    text:    der zu sprechende Text
    lang:    Zielsprache. None → DEFAULT_LANG. Werte: 'de', 'zh', …
             Welche Sprachen wirklich gehen, entscheidet tts_service.py
             (abhängig von den geladenen Modellen).
    speed:   Sprechgeschwindigkeit (0.9 = leicht langsamer, gut zum Lernen)
    speaker: Sprecher-ID (modellabhängig: vits-zh-aishell3 hat 174,
             Piper-Modelle haben typischerweise 1)
    Rückgabe: WAV-Datei als bytes, oder leeres bytes bei Fehler
    """
    if lang is None:
        lang = DEFAULT_LANG

    url = f"{TTS_URL}/speak"
    state.push_log(f"TTS →  POST {url} '{text[:40]}' (lang={lang})")

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
        urllib.request.urlopen(f"{WHISPER_URL}/health", timeout=2)
        return True
    except Exception:
        return False


def tts_available() -> bool:
    """Health-Check für TTS-Service."""
    try:
        urllib.request.urlopen(f"{TTS_URL}/health", timeout=2)
        return True
    except Exception:
        return False
