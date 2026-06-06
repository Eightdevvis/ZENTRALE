#!/usr/bin/env python3
"""
A/B-Vergleich deutscher Piper-Stimmen
=====================================

Synthetisiert DENSELBEN Satz mit mehreren deutschen Piper-Stimmen, damit man
sie per Ohr vergleichen kann. Hintergrund: thorsten ist die einzige *hoch-
wertige* DE-Piper-Stimme, aber von Sasha veto't. Alle anderen DE-Stimmen sind
dieselbe Low-Tier-Klasse - dieses Skript testet, ob eine andere KLANGFARBE
(Timbre) weniger nervt als kerstin, auch wenn die Qualitaet gleich bleibt.

Laedt fehlende Voices automatisch (rhasspy/piper-voices, gleiche Logik wie
services/download_tts_model.py), synthetisiert nach /tmp/tts_ab/<voice>.wav.

Aufruf:
  venv/bin/python scripts/tts_ab.py
  venv/bin/python scripts/tts_ab.py --voices de_DE-ramona-low de_DE-eva_k-x_low
"""

import argparse
import os
import sys
import urllib.request
import wave

import numpy as np

# Default-Auswahl: alle deutschen NICHT-thorsten-Stimmen + kerstin als
# Referenz (das aktuelle, nervige). eva_k ist x_low (niedrigste Stufe),
# der Rest low. karlsson/pavoque sind maennlich, eva_k/ramona/kerstin weiblich.
DEFAULT_VOICES = [
    "de_DE-kerstin-low",   # aktuell (Referenz - das nervige)
    "de_DE-eva_k-x_low",   # weiblich, andere Klangfarbe
    "de_DE-ramona-low",    # weiblich
    "de_DE-karlsson-low",  # maennlich (nicht thorsten)
    "de_DE-pavoque-low",   # maennlich (nicht thorsten)
]

# Repraesentativer ZENTRALE-Antwortsatz: umgangssprachlich, mit Zahl + Frage,
# damit man Betonung/Natuerlichkeit hoert - nicht nur ein nacktes Wort.
SENTENCE = (
    "Na klar. Dein naechster Termin ist morgen um halb drei beim Zahnarzt. "
    "Den Rest der Woche hast du frei - soll ich dir trotzdem was vormerken?"
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODEL_ROOT = os.path.join(_ROOT, "data", "tts_model")
_OUT_DIR = "/tmp/tts_ab"


def _voice_url(voice):
    """HuggingFace-Basis-URL fuer eine Piper-Voice-ID (wie download_tts_model)."""
    locale, name, quality = voice.split("-")      # de_DE / eva_k / x_low
    lang = locale.split("_")[0]                    # de
    return (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{lang}/{locale}/{name}/{quality}")


def ensure_voice(voice):
    """Laedt .onnx + .onnx.json falls noch nicht da. Gibt (model, cfg) zurueck."""
    vdir = os.path.join(_MODEL_ROOT, voice)
    onnx = os.path.join(vdir, f"{voice}.onnx")
    cfg = os.path.join(vdir, f"{voice}.onnx.json")
    if os.path.exists(onnx) and os.path.exists(cfg):
        return onnx, cfg
    os.makedirs(vdir, exist_ok=True)
    base = _voice_url(voice)
    print(f"  lade {voice} ...")
    urllib.request.urlretrieve(f"{base}/{voice}.onnx", onnx)
    urllib.request.urlretrieve(f"{base}/{voice}.onnx.json", cfg)
    return onnx, cfg


def synth(voice, onnx, cfg, text, out_path):
    """Synthetisiert text mit der Piper-Voice und schreibt eine PCM16-WAV."""
    from piper import PiperVoice
    voice_obj = PiperVoice.load(onnx, config_path=cfg)
    chunks = list(voice_obj.synthesize(text))   # Default-Speed
    if not chunks:
        print(f"  {voice}: keine Audio-Chunks (Fehler)")
        return False
    sample_rate = chunks[0].sample_rate
    samples = np.concatenate([c.audio_int16_array for c in chunks])
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)          # int16 = 2 Byte
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    dur = len(samples) / sample_rate
    print(f"  {voice:24} -> {out_path}  ({dur:.1f}s, {sample_rate} Hz)")
    return True


def main():
    ap = argparse.ArgumentParser(description="A/B deutscher Piper-Stimmen")
    ap.add_argument("--voices", nargs="+", default=DEFAULT_VOICES)
    ap.add_argument("--text", default=SENTENCE)
    args = ap.parse_args()

    os.makedirs(_OUT_DIR, exist_ok=True)
    print(f"Satz: {args.text!r}\n")
    done = []
    for voice in args.voices:
        try:
            onnx, cfg = ensure_voice(voice)
            out = os.path.join(_OUT_DIR, f"{voice}.wav")
            if synth(voice, onnx, cfg, args.text, out):
                done.append(out)
        except Exception as exc:
            print(f"  {voice}: FEHLER ({exc})")

    print("\nZum Anhoeren (nacheinander):")
    for p in done:
        print(f"  aplay {p}")
    if done:
        print("\nOder alle hintereinander:")
        print("  for f in " + " ".join(done) + '; do echo "== $f =="; aplay "$f"; sleep 1; done')


if __name__ == "__main__":
    main()
