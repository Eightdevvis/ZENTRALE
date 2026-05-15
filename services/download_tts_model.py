# services/download_tts_model.py
#
# Laedt die TTS-Modelle herunter, die von services/tts_service.py
# zur Laufzeit erwartet werden. Einmalig pro Maschine ausfuehren.
#
# Aktuell zwei Modelle (eines pro Sprache):
#   - 'zh' – vits-zh-aishell3 (sherpa-onnx, ~120MB, 174 Sprecher, Apache 2.0)
#            Wird vom Tutor-Modus genutzt.
#   - 'de' – de_DE-thorsten-medium (Piper, ~60MB, 1 Sprecher, MIT)
#            Wird vom Haupt-Chat (KI-Antworten) genutzt.
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


def download_de():
    """Laedt das Piper-Modell de_DE-thorsten-medium fuer den Haupt-Chat.

    Piper-Modelle bestehen aus zwei Dateien:
      - .onnx       (Modellgewichte, ~60MB)
      - .onnx.json  (Config, ~5KB)
    Beide liegen flach im Voice-Ordner, kein Tar/Zip noetig.
    """
    target_dir = os.path.join(MODEL_DIR, "de_DE-thorsten-medium")
    onnx_file  = os.path.join(target_dir, "de_DE-thorsten-medium.onnx")
    json_file  = os.path.join(target_dir, "de_DE-thorsten-medium.onnx.json")

    if os.path.exists(onnx_file) and os.path.exists(json_file):
        print(f"de: Modell schon vorhanden: {target_dir}")
        return

    os.makedirs(target_dir, exist_ok=True)
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium"

    print(f"de: Lade Piper-Modell herunter (~60MB) von {base} ...")
    urllib.request.urlretrieve(
        f"{base}/de_DE-thorsten-medium.onnx",
        onnx_file,
        reporthook=_progress_reporter("de onnx", 60),
    )
    print()
    urllib.request.urlretrieve(
        f"{base}/de_DE-thorsten-medium.onnx.json",
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
