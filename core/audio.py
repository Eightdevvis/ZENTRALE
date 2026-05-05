# core/audio.py
#
# HTTP-Client für die Audio-Services (Whisper STT + sherpa-onnx TTS).
#
# Die eigentliche Aufnahme und Wiedergabe passiert im Browser (MediaRecorder +
# Web Audio API) – audio.py ist nur der Vermittler zwischen Flask und den
# Services die auf dem Linux-PC laufen.
#
# Whisper-Service: http://<WHISPER_HOST>:5050/transcribe
# TTS-Service:     http://<TTS_HOST>:5051/speak
#
# Konfiguration via Umgebungsvariablen:
#   WHISPER_URL – default: http://localhost:5050
#   TTS_URL     – default: http://localhost:5051

import os
import urllib.request
import urllib.error
import json as _json
import state  # für Terminal-Logging

WHISPER_URL = os.environ.get("WHISPER_URL", "http://localhost:5050")
TTS_URL     = os.environ.get("TTS_URL",     "http://localhost:5051")


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Schickt rohe Audio-Bytes an den Whisper-Service und gibt den
    transkribierten Text zurück.

    audio_bytes: WAV-Datei als bytes (kommt vom Browser via Flask)
    filename:    Dateiname für den multipart-Upload (nur für Logging)
    Rückgabe:    erkannter Text auf Mandarin, oder Fehlermeldung
    """
    url = f"{WHISPER_URL}/transcribe"
    state.push_log(f"STT →  POST {url} ({len(audio_bytes)//1024} KB)")

    # multipart/form-data manuell bauen – urllib hat keine eingebaute Hilfe dafür.
    # boundary = Trennstring zwischen den Feldern
    boundary = b"----ZentraleBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="audio"; filename="' + filename.encode() + b'"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + audio_bytes + b"\r\n"
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


def synthesize(text: str, speed: float = 0.9, speaker: int = 0) -> bytes:
    """
    Schickt Text an den TTS-Service und gibt WAV-Audio-Bytes zurück.
    Flask proxied die Bytes direkt an den Browser.

    text:    Mandarin-Text der gesprochen werden soll
    speed:   Sprechgeschwindigkeit (0.9 = leicht langsamer, gut zum Lernen)
    speaker: Sprecher-ID 0–173 (vits-zh-aishell3 hat 174 Sprecher)
    Rückgabe: WAV-Datei als bytes, oder leeres bytes bei Fehler
    """
    url = f"{TTS_URL}/speak"
    state.push_log(f"TTS →  POST {url} '{text[:40]}'")

    payload = _json.dumps({"text": text, "speed": speed, "speaker": speaker}).encode("utf-8")
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
