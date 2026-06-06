# services/download_tts_model.py
#
# Laedt die TTS-Modelle herunter, die von services/tts_service.py
# zur Laufzeit erwartet werden. Einmalig pro Maschine ausfuehren.
#
# Aktuell zwei Modelle (eines pro Sprache):
#   - 'zh' – vits-zh-aishell3 (sherpa-onnx, ~120MB, 174 Sprecher, Apache 2.0)
#            Wird vom Tutor-Modus genutzt.
#   - 'de' – Piper-Voice via Env PIPER_DE_VOICE (Default de_DE-kerstin-low,
#            ~20MB, 1 Sprecher, MIT). Wird vom Haupt-Chat genutzt.
#
# Aufruf:
#   python services/download_tts_model.py            # beide laden
#   python services/download_tts_model.py zh         # nur Mandarin
#   python services/download_tts_model.py de         # nur Deutsch
#
# Bestehende Modelle werden uebersprungen (idempotent).

import os
import sys
import urllib.request

MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'tts_model')


def _progress_reporter(label, total_mb_hint=None):
    """Gibt einen reporthook-Callback fuer urlretrieve zurueck, der den
    Download-Fortschritt in einer Zeile ueberschreibt."""
    def hook(count, block_size, total_size):
        done_mb  = count * block_size / 1024 / 1024
        total_mb = total_size / 1024 / 1024 if total_size > 0 else (total_mb_hint or 0)
        if total_mb:
            print(f"\r  {label}: {done_mb:.1f} / {total_mb:.1f} MB", end='', flush=True)
        else:
            print(f"\r  {label}: {done_mb:.1f} MB", end='', flush=True)
    return hook


def download_zh():
    """Laedt vits-zh-aishell3 fuer den Tutor-Modus."""
    target = os.path.join(MODEL_DIR, "vits-zh-aishell3")
    if os.path.exists(target):
        print(f"zh: Modell schon vorhanden: {target}")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)
    archive = os.path.join(MODEL_DIR, "model_zh.tar.bz2")
    url     = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-aishell3.tar.bz2"

    print(f"zh: Lade vits-zh-aishell3 herunter (~120MB) von {url} ...")
    urllib.request.urlretrieve(url, archive, reporthook=_progress_reporter("zh", 120))
    print("\nzh: Extrahiere...")

    import tarfile
    with tarfile.open(archive, 'r:bz2') as tar:
        tar.extractall(MODEL_DIR)
    os.remove(archive)
    print(f"zh: Fertig. {target}")


# Welche deutsche Stimme geladen wird – exakt dieselbe Env-Var wie
# tts_service.py, damit Download und Service nie auseinanderlaufen.
DE_VOICE = os.environ.get("PIPER_DE_VOICE", "de_DE-kerstin-low")


def _piper_voice_url(voice):
    """Baut die HuggingFace-Basis-URL fuer eine Piper-Voice-ID.

    Die Voice-ID ist nach dem Schema '<locale>-<name>-<quality>' aufgebaut,
    z.B. 'de_DE-kerstin-low'. Im rhasspy/piper-voices-Repo liegt sie unter
    '<lang>/<locale>/<name>/<quality>/', also 'de/de_DE/kerstin/low/'.
    Wir zerlegen die ID einmal und setzen den Pfad daraus zusammen –
    so funktioniert der Downloader fuer jede Piper-Voice, nicht nur fuer
    eine fest verdrahtete.
    """
    locale, name, quality = voice.split("-")          # de_DE / kerstin / low
    lang = locale.split("_")[0]                        # de
    return (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            f"{lang}/{locale}/{name}/{quality}")


def download_de():
    """Laedt die deutsche Piper-Voice (DE_VOICE) fuer den Haupt-Chat.

    Piper-Modelle bestehen aus zwei Dateien:
      - .onnx       (Modellgewichte, ~20-60MB je nach Quality)
      - .onnx.json  (Config, ~5KB)
    Beide liegen flach im Voice-Ordner, kein Tar/Zip noetig.
    """
    target_dir = os.path.join(MODEL_DIR, DE_VOICE)
    onnx_file  = os.path.join(target_dir, f"{DE_VOICE}.onnx")
    json_file  = os.path.join(target_dir, f"{DE_VOICE}.onnx.json")

    if os.path.exists(onnx_file) and os.path.exists(json_file):
        print(f"de: Modell schon vorhanden: {target_dir}")
        return

    os.makedirs(target_dir, exist_ok=True)
    base = _piper_voice_url(DE_VOICE)

    print(f"de: Lade Piper-Voice '{DE_VOICE}' herunter von {base} ...")
    urllib.request.urlretrieve(
        f"{base}/{DE_VOICE}.onnx",
        onnx_file,
        reporthook=_progress_reporter("de onnx", 60),
    )
    print()
    urllib.request.urlretrieve(
        f"{base}/{DE_VOICE}.onnx.json",
        json_file,
    )
    print(f"de: Fertig. {target_dir}")


def main():
    # CLI: ohne Arg = beide; mit 'zh'/'de' = nur dieses Modell.
    requested = set(sys.argv[1:]) or {"zh", "de"}
    if "zh" in requested: download_zh()
    if "de" in requested: download_de()


if __name__ == '__main__':
    main()
