# core/dateien.py
#
# Dateien so schreiben, dass sie danach entweder die alte oder die neue
# Fassung enthalten — nie eine halbe.
#
# ── Warum es diese Datei gibt ───────────────────────────────────────────
# Bis 2026-10-07 schrieben Listen, Notizen, Messreihen, Melodien, News und
# sogar der Key-Speicher (ai_config.json) mit einem nackten open(..., "w"):
# erst wird die Datei geleert, dann gefüllt. Ein Absturz, ein voller
# Datenträger oder ein Stromausfall genau dazwischen — und Sashas Listen sind
# eine leere Datei, die der Sync (neueste gewinnt) auch noch auf den anderen
# Rechner trägt. Andere Module hatten es halb richtig (Zwischendatei, aber
# mit festem Namen `.tmp` — zwei Threads gleichzeitig überschreiben sich die
# Zwischendatei). Der saubere Weg stand nur in kalender_sicherung. Jetzt
# steht er HIER, einmal, und kalender_sicherung nutzt ihn mit.

import json
import os
import re
import socket
import time
from pathlib import Path


def atomar_schreiben(pfad, inhalt) -> None:
    """Schreibt `inhalt` (str oder bytes) atomar nach `pfad`.

    Weg: Zwischendatei im SELBEN Ordner (sonst ist os.replace kein atomares
    Umbenennen, sondern ein Kopieren über Dateisysteme), fsync, os.replace.
    Der Name der Zwischendatei beginnt mit einem Punkt und endet NICHT auf
    .json/.ics — Sync und vdirsyncer sehen sie so nie als Datendatei, falls
    ein Absturz sie liegen lässt. Er trägt Prozess-Id und Zeit, damit zwei
    Schreiber sich nicht gegenseitig die Zwischendatei wegnehmen.

    Die Rechte einer schon vorhandenen Datei bleiben erhalten (os.replace
    setzt sonst die Standardrechte der neuen Datei durch)."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    daten = inhalt.encode("utf-8") if isinstance(inhalt, str) else bytes(inhalt)
    tmp = pfad.parent / f".{pfad.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(daten)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, pfad.stat().st_mode & 0o7777)
        except FileNotFoundError:
            pass
        os.replace(tmp, pfad)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def json_schreiben(pfad, daten, indent: int = 2) -> None:
    """JSON atomar schreiben, mit Umlauten im Klartext (ensure_ascii=False) —
    so, wie die Module es vorher mit json.dump getan haben."""
    atomar_schreiben(pfad, json.dumps(daten, indent=indent, ensure_ascii=False))


# ── Rechnername ─────────────────────────────────────────────────────────
# Wer auf mehreren Rechnern schreibt, braucht EINDEUTIGE Dateinamen pro
# Rechner: der Sync (rsync, neueste Datei gewinnt) würde sonst eine Fassung
# überschreiben. Bis 2026-10-07 stand das in kalender_sicherung; seit die
# Gespräche (core/gespraeche.py) dasselbe brauchen, steht es hier einmal.

def knoten() -> str:
    """Name dieses Rechners, dateinamen-tauglich (wie scripts/daten_sichern.py:
    socket.gethostname()). Steht in Verlaufs-, Snapshot- und Gesprächs-
    Dateinamen, damit PC und Laptop nie denselben Namen erzeugen."""
    return sicherer_name(socket.gethostname() or "knoten")


def sicherer_name(text: str) -> str:
    """Alles außer Buchstaben, Ziffern, '@', '.', '-' wird '_'. Kein '~' —
    das ist das Trennzeichen in den Kalender-Verlaufs-Namen."""
    s = re.sub(r"[^A-Za-z0-9@.\-]", "_", str(text))
    return s.strip(".") or "_"
