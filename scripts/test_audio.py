#!/usr/bin/env python3
# scripts/test_audio.py
#
# Testet die Audio-Pipeline isoliert – kein ZENTRALE nötig.
#
# Was getestet wird:
#   1. Whisper-Service (STT): Mikrofon-Aufnahme → Text
#   2. TTS-Service: Text → Mandarin-Audio → Wiedergabe
#   3. Beide zusammen: Mic → Whisper → TTS (kompletter Loop)
#
# Starten:
#   venv/bin/python scripts/test_audio.py
#   venv/bin/python scripts/test_audio.py --tts-only
#   venv/bin/python scripts/test_audio.py --whisper-only

import argparse
import io
import os
import sys
import time
import urllib.request
import urllib.error
import json

WHISPER_URL = "http://localhost:5050"
TTS_URL     = "http://localhost:5051"

# Aufnahme-Dauer in Sekunden. Per Env RECORD_SECONDS ueberschreibbar,
# damit man pro Test-Lauf flexibel zwischen kurzen Smoke-Checks (4s)
# und laengeren, anspruchsvolleren Saetzen (15-20s) wechseln kann ohne
# das Skript editieren zu muessen.
RECORD_SECONDS = int(os.environ.get("RECORD_SECONDS", "4"))


def check_service(name, url):
    """Prüft ob ein Service läuft, gibt True/False zurück."""
    try:
        urllib.request.urlopen(f"{url}/health", timeout=3)
        print(f"  ✓ {name} erreichbar ({url})")
        return True
    except urllib.error.URLError:
        print(f"  ✗ {name} NICHT erreichbar ({url})")
        print(f"    → Starte: venv/bin/python services/{'whisper' if 'whisper' in name.lower() else 'tts'}_service.py")
        return False
    except Exception as e:
        print(f"  ✗ {name} Fehler: {e}")
        return False


def record_audio(seconds=RECORD_SECONDS):
    """Nimmt Audio vom Standard-Mikrofon auf. Gibt WAV-Bytes zurück."""
    try:
        import sounddevice as sd
        import soundfile as sf
    except ImportError:
        print("FEHLER: sounddevice/soundfile nicht installiert")
        print("  → venv/bin/pip install sounddevice soundfile")
        sys.exit(1)

    print(f"\n[MIC] Aufnahme startet in 1 Sekunde – {seconds}s sprechen...")
    time.sleep(1)
    print(f"[MIC] ● AUFNAHME LÄUFT ({seconds}s)")

    # 16kHz Mono – Whisper-optimales Format
    sample_rate = 16000
    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate,
                   channels=1, dtype='float32')
    sd.wait()
    print("[MIC] Aufnahme fertig.")

    # Als WAV in Memory-Buffer schreiben
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return buf.read()


def send_to_whisper(wav_bytes):
    """Schickt WAV-Bytes an Whisper-Service. Gibt transkribierten Text zurück."""
    print(f"\n[STT] Sende {len(wav_bytes)//1024} KB an Whisper...")

    boundary = b"----TestBoundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="audio"; filename="test.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
        + wav_bytes + b"\r\n"
        b"--" + boundary + b"--\r\n"
    )
    headers = {
        "Content-Type":   f"multipart/form-data; boundary={boundary.decode()}",
        "Content-Length": str(len(body)),
    }

    try:
        req = urllib.request.Request(
            f"{WHISPER_URL}/transcribe", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            text = result.get("text", "").strip()
            conf = result.get("confidence", 0)
            lang = result.get("language", "?")
            print(f"[STT] Ergebnis: '{text}'")
            print(f"[STT] Sprache: {lang}, Konfidenz: {conf:.0%}")
            return text
    except Exception as e:
        print(f"[STT] Fehler: {e}")
        return None


def send_to_tts(text, play=True):
    """Schickt Text an TTS-Service. Spielt WAV ab (wenn play=True)."""
    print(f"\n[TTS] Synthesize: '{text}'")

    payload = json.dumps({"text": text, "speed": 0.9, "speaker": 0}).encode()
    headers = {"Content-Type": "application/json"}

    try:
        req = urllib.request.Request(
            f"{TTS_URL}/speak", data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            wav = resp.read()
            print(f"[TTS] Empfangen: {len(wav)//1024} KB WAV")

        if play and wav:
            play_wav(wav)
        return wav

    except Exception as e:
        print(f"[TTS] Fehler: {e}")
        return None


def play_wav(wav_bytes):
    """Spielt WAV-Bytes über Lautsprecher ab."""
    try:
        import sounddevice as sd
        import soundfile as sf
        buf = io.BytesIO(wav_bytes)
        data, sr = sf.read(buf)
        print(f"[PLAY] Spiele {len(data)/sr:.1f}s Audio ab...")
        sd.play(data, sr)
        sd.wait()
        print("[PLAY] Fertig.")
    except Exception as e:
        print(f"[PLAY] Wiedergabe-Fehler: {e}")


def test_whisper_only():
    print("=" * 50)
    print("TEST: Whisper STT")
    print("=" * 50)
    if not check_service("Whisper", WHISPER_URL):
        return False
    wav = record_audio()
    text = send_to_whisper(wav)
    return text is not None


def test_tts_only():
    print("=" * 50)
    print("TEST: TTS Ausgabe")
    print("=" * 50)
    if not check_service("TTS", TTS_URL):
        return False
    # Einfacher Mandarin-Testsatz
    test_texts = ["你好！", "今天天气怎么样？", "我在学习中文。"]
    for text in test_texts:
        wav = send_to_tts(text, play=True)
        if wav is None:
            return False
        time.sleep(0.5)
    return True


def test_full_loop():
    print("=" * 50)
    print("TEST: Kompletter Loop (Mic → STT → TTS)")
    print("=" * 50)
    w_ok = check_service("Whisper", WHISPER_URL)
    t_ok = check_service("TTS",     TTS_URL)
    if not (w_ok and t_ok):
        return False

    print("\nAblauf: Du sprichst Mandarin → Whisper transkribiert → TTS wiederholt es")
    wav  = record_audio()
    text = send_to_whisper(wav)
    if not text:
        print("Kein Text erkannt – war die Aufnahme leer?")
        return False

    print(f"\nWiederholen als Audio: '{text}'")
    send_to_tts(text, play=True)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZENTRALE Audio-Pipeline Test")
    parser.add_argument("--whisper-only", action="store_true", help="Nur STT testen")
    parser.add_argument("--tts-only",     action="store_true", help="Nur TTS testen")
    args = parser.parse_args()

    print("\nZENTRALE Audio-Pipeline Test")
    print("-----------------------------")
    print("Services prüfen:")

    if args.whisper_only:
        ok = test_whisper_only()
    elif args.tts_only:
        ok = test_tts_only()
    else:
        ok = test_full_loop()

    print("\n" + ("✓ Test bestanden" if ok else "✗ Test fehlgeschlagen"))
