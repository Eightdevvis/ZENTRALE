# services/download_tts_model.py
#
# Lädt das chinesische TTS-Modell für sherpa-onnx herunter.
# Einmalig ausführen bevor tts_service.py gestartet wird.
#
# Modell: vits-zh-aishell3
#   - Mandarin, 174 Sprecher (wir nehmen Sprecher 0)
#   - ~120MB
#   - Qualität: gut, natürliche Töne
#   - Quelle: https://github.com/k2-fsa/sherpa-onnx (Apache 2.0)
#
# Starten:
#   python services/download_tts_model.py

import os
import urllib.request
import zipfile

MODEL_DIR  = os.path.join(os.path.dirname(__file__), '..', 'data', 'tts_model')
MODEL_URL  = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-zh-aishell3.tar.bz2"
MODEL_NAME = "vits-zh-aishell3"

def download():
    os.makedirs(MODEL_DIR, exist_ok=True)
    target = os.path.join(MODEL_DIR, MODEL_NAME)

    if os.path.exists(target):
        print(f"Modell schon vorhanden: {target}")
        return

    archive = os.path.join(MODEL_DIR, "model.tar.bz2")
    print(f"Lade Modell herunter (~120MB)...")
    print(f"URL: {MODEL_URL}")

    def progress(count, block_size, total_size):
        mb_done  = count * block_size / 1024 / 1024
        mb_total = total_size / 1024 / 1024
        print(f"\r  {mb_done:.1f} / {mb_total:.1f} MB", end='', flush=True)

    urllib.request.urlretrieve(MODEL_URL, archive, reporthook=progress)
    print("\nExtrahiere...")

    import tarfile
    with tarfile.open(archive, 'r:bz2') as tar:
        tar.extractall(MODEL_DIR)

    os.remove(archive)
    print(f"Fertig. Modell unter: {target}")

if __name__ == '__main__':
    download()
