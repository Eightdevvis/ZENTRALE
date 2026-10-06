# core/kalender_spiegel.py
#
# Der git-Spiegel der Kalenderdaten — eine vollständige Geschichte jeder
# Änderung, AUSSERHALB von data/.
#
# Sasha, 2026-10-06: "daten können gern in ein extra git repo". Warum nicht
# direkt in data/: data/ wird zwischen PC und Laptop per rsync Datei für
# Datei abgeglichen, neueste Datei gewinnt. Schreiben beide Knoten in ein
# git-Repo dort, überschreibt der Sync refs und index dateiweise — das Repo
# wäre kaputt, genau dann, wenn man es braucht. Deshalb: ein Repo pro
# Knoten unter ~/.local/share/zentrale/kalender-git, ZENTRALE spiegelt nach
# jedem Schreiben hinein und committet.
#
# Regeln:
#   * Ein Fehler hier verhindert NIE das Schreiben eines Termins: der
#     Spiegel läuft nach dem Schreiben, im Hintergrund, und meldet Fehler
#     nur ins Log.
#   * Hier wird nie gepusht. Ein privates Remote richtet Sasha selbst ein
#     (memory/werkzeuge/kalender_ics_bauplan.md) und pusht von Hand.

import os
import shutil
import subprocess
import threading
from pathlib import Path

import state
from kalender_sicherung import knoten

_lock = threading.Lock()
_TIMEOUT_S = 30


def spiegeln(quellen: dict, ziel: Path, grund: str,
             warten: bool = False) -> threading.Thread | None:
    """Spiegelt `quellen` ({name im Repo: Pfad}) nach `ziel` und committet.

    warten=False (Normalfall): im Hintergrund-Thread, der Aufrufer (ein
    Termin wird gerade gespeichert) wartet nicht auf git. warten=True für
    Skripte und Tests."""
    def lauf():
        with _lock:                      # nie zwei git-Läufe gleichzeitig
            try:
                _spiegeln(quellen, Path(ziel), grund)
            except Exception as ex:
                state.push_log(f"[calendar] git-Spiegel: {ex}")
    if warten:
        lauf()
        return None
    t = threading.Thread(target=lauf, name="kalender-spiegel", daemon=True)
    t.start()
    return t


def _git(ziel: Path, *args) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], cwd=ziel, env=env,
                          capture_output=True, text=True, timeout=_TIMEOUT_S)


def _spiegeln(quellen: dict, ziel: Path, grund: str) -> None:
    if not shutil.which("git"):
        state.push_log("[calendar] git-Spiegel: git nicht installiert")
        return
    ziel.mkdir(parents=True, exist_ok=True)
    if not (ziel / ".git").exists():
        r = _git(ziel, "init", "-q")
        if r.returncode != 0:
            raise RuntimeError(f"git init: {r.stderr.strip()}")
        # Eigene Identität im Repo, damit ein Commit nie an einer fehlenden
        # globalen git-Konfiguration scheitert.
        _git(ziel, "config", "user.name", "ZENTRALE")
        _git(ziel, "config", "user.email", "zentrale@localhost")
    for name, quelle in quellen.items():
        _abgleichen(Path(quelle), ziel / name)
    _git(ziel, "add", "-A")
    if _git(ziel, "diff", "--cached", "--quiet").returncode == 0:
        return                           # nichts geändert, kein leerer Commit
    r = _git(ziel, "commit", "-q", "-m", f"{grund} ({knoten()})")
    if r.returncode != 0:
        raise RuntimeError(f"git commit: {r.stderr.strip() or r.stdout.strip()}")


def _uebergehen(name: str) -> bool:
    return name.startswith(".") or name.endswith(".tmp") or name.endswith(".lock")


def _abgleichen(quelle: Path, ziel: Path) -> None:
    """Ziel = Quelle: Dateien kopieren, die sich unterscheiden, und im Ziel
    löschen, was es in der Quelle nicht mehr gibt (die Geschichte dazu hat
    git). Fehlt die Quelle ganz, bleibt das Ziel unangetastet — ein
    verschwundener Ordner ist eher ein Fehler als eine Absicht."""
    if not quelle.exists():
        return
    if quelle.is_file():
        ziel.parent.mkdir(parents=True, exist_ok=True)
        if not ziel.exists() or ziel.read_bytes() != quelle.read_bytes():
            shutil.copy2(quelle, ziel)
        return
    ziel.mkdir(parents=True, exist_ok=True)
    gesehen = set()
    for wurzel, ordner, dateien in os.walk(quelle):
        ordner[:] = [o for o in ordner if not _uebergehen(o)]
        rel = Path(wurzel).relative_to(quelle)
        for d in dateien:
            if _uebergehen(d):
                continue
            q = Path(wurzel) / d
            z = ziel / rel / d
            gesehen.add(z)
            if not z.exists() or z.read_bytes() != q.read_bytes():
                z.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(q, z)
    for wurzel, _ordner, dateien in os.walk(ziel):
        for d in dateien:
            z = Path(wurzel) / d
            if z not in gesehen:
                z.unlink()
