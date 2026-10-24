"""Die Timer eines Geräts (memory/betrieb/setup.md, „Timer"): systemd-USER-
Einheiten, die regelmäßig `zentrale sync --automatic` (alle 5 min) und
`zentrale adapter run` (alle 3 min, die Kalender-Brücke) aufrufen.

Warum gerendert statt verlinkt: die alten Einheiten in deploy/ tragen den Pfad
von Sashas Checkout (%h/codicus/ZENTRALE). Hier steht stattdessen der Befehl
`zentrale` des Geräts drin, je Kanal der Pfad, der jedes Update überlebt:

    script   ~/.local/share/zentrale/hub/aktuell/bin/zentrale  (aktuell dreht mit)
    apt/pacman  /usr/bin/zentrale                              (der Starter)
    dev      <checkout>/bin/zentrale

Gleiche Namen wie die alten Einheiten (zentrale-abgleich, zentrale-kalender-
sync): `zentrale timers install` ersetzt einen alten Verweis nach deploy/ durch
die gerenderte Datei — nie durch den Verweis hindurch. Idempotent; nie sudo.
Ohne systemd --user: ein Satz, sonst nichts.

Tests: ZENTRALE_SYSTEMCTL (Programm oder „aus") und ZENTRALE_SYSTEMD_USER_DIR
lenken um; unter pytest ohne Umlenkung gilt systemd als nicht da — ein
Testlauf schaltet nie Sashas echte Timer um.
"""

import os
import shutil
import subprocess
import sys

from zentrale_cli import WURZEL
from zentrale_cli.aktualisieren import heim, kanal

MARKE = "# Rendered by `zentrale timers install`"
STARTER = "/usr/bin/zentrale"
KERN = "zentrale-kern.service"
WORKTREE = os.sep + os.path.join(".claude", "worktrees") + os.sep
PFAD = "PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin"

# name → (Beschreibung, Unterbefehl, Zeitplan, Zeitlimit s)
TIMER = {
    "zentrale-abgleich": ("ZENTRALE: sync with the cloud", "sync --automatic", "*:0/5", 300),
    "zentrale-kalender-sync": ("ZENTRALE: calendar bridge (Google via vdirsyncer)",
                               "adapter run", "*:0/3", 600),
}


# ── Pfade ──────────────────────────────────────────────────────────────

def befehl(wurzel=WURZEL) -> str:
    """Der Pfad des Befehls `zentrale`, der jedes Update überlebt."""
    k = kanal(wurzel)
    if k in ("apt", "pacman"):
        return STARTER
    if k == "script":
        return os.path.join(heim(), "hub", "aktuell", "bin", "zentrale")
    return os.path.join(os.path.realpath(wurzel), "bin", "zentrale")


def ordner() -> str:
    eigen = os.environ.get("ZENTRALE_SYSTEMD_USER_DIR")
    if eigen:
        return os.path.expanduser(eigen)
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(xdg, "systemd", "user")


# ── Rendern ────────────────────────────────────────────────────────────

def _exe(pfad):
    return f'"{pfad}"' if any(c.isspace() for c in pfad) else pfad


def einheiten(wurzel=WURZEL) -> dict:
    """Dateiname → Inhalt, für alle Timer und ihre Dienste."""
    exe = _exe(befehl(wurzel))
    raus = {}
    for name, (was, unter, wann, limit) in TIMER.items():
        raus[name + ".service"] = (
            f"{MARKE} — do not edit; run it again instead.\n"
            f"[Unit]\nDescription={was}\n"
            "Wants=network-online.target\nAfter=network-online.target\n\n"
            "[Service]\nType=oneshot\nWorkingDirectory=%h\n"
            f"Environment={PFAD}\n"
            f"ExecStart={exe} {unter}\n"
            f"Nice=10\nTimeoutStartSec={limit}\n")
        # OnCalendar, nicht OnBootSec: der Benutzer-systemd startet erst nach
        # dem Anmelden (deploy/zentrale-kalender-sync.timer, 13.10.2026).
        raus[name + ".timer"] = (
            f"{MARKE} — do not edit; run it again instead.\n"
            f"[Unit]\nDescription={was} (every {wann.split('/')[-1]} min)\n\n"
            f"[Timer]\nOnCalendar={wann}\nPersistent=true\nAccuracySec=30s\n\n"
            "[Install]\nWantedBy=timers.target\n")
    return raus


# ── systemctl ──────────────────────────────────────────────────────────

def _programm():
    eigen = os.environ.get("ZENTRALE_SYSTEMCTL")
    if eigen is not None:
        return None if eigen in ("", "aus") else eigen
    if "pytest" in sys.modules:
        return None                       # Testlauf ohne Umlenkung: nie das echte
    return shutil.which("systemctl")


def systemctl(*args) -> subprocess.CompletedProcess:
    prog = _programm()
    if not prog:
        return subprocess.CompletedProcess(args, 127, "", "systemctl not available")
    try:
        return subprocess.run([prog, "--user", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))


def verfuegbar() -> bool:
    """Läuft ein systemd für diesen Benutzer, den wir erreichen?"""
    return _programm() is not None and systemctl("show-environment").returncode == 0


# ── Installieren, entfernen, ansehen ───────────────────────────────────

def _art(pfad) -> str:
    """fehlt | eigen (von uns gerendert) | verweis (alter Verweis, z. B. nach deploy/) | fremd"""
    if os.path.islink(pfad):
        return "verweis"
    if not os.path.exists(pfad):
        return "fehlt"
    try:
        with open(pfad, encoding="utf-8") as f:
            return "eigen" if f.read().startswith(MARKE) else "fremd"
    except OSError:
        return "fremd"


def _schreiben(pfad, inhalt):
    tmp = pfad + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.replace(tmp, pfad)           # ersetzt einen Verweis selbst, nie sein Ziel


def installieren(wurzel=WURZEL) -> dict:
    """Einheiten schreiben (nur wo sie sich ändern), neu einlesen, Timer an.
    → {"da": bool, "geschrieben": [...], "ersetzt": [...], "fehler": str}"""
    raus = {"da": verfuegbar(), "geschrieben": [], "ersetzt": [], "fehler": ""}
    if not raus["da"]:
        return raus
    if WORKTREE in befehl(wurzel):
        # Ein Worktree verschwindet nach dem Merge — die Timer liefen ins Leere.
        raus["fehler"] = "this is a git worktree; run it from the main checkout"
        return raus
    os.makedirs(ordner(), exist_ok=True)
    for datei, inhalt in einheiten(wurzel).items():
        pfad = os.path.join(ordner(), datei)
        art = _art(pfad)
        if art == "eigen":
            with open(pfad, encoding="utf-8") as f:
                if f.read() == inhalt:
                    continue
        if art in ("verweis", "fremd"):
            raus["ersetzt"].append(datei)
        _schreiben(pfad, inhalt)
        raus["geschrieben"].append(datei)
    if raus["geschrieben"]:
        systemctl("daemon-reload")
    timer = [n + ".timer" for n in TIMER]
    # reenable, wo ein alter Verweis war: dessen .wants-Verweis zeigte auf deploy/.
    neu = [d for d in timer if d in raus["ersetzt"]]
    if neu:
        systemctl("reenable", *neu)
    r = systemctl("enable", "--now", *timer)
    if r.returncode != 0:
        raus["fehler"] = (r.stderr or r.stdout or "").strip()[:300]
    return raus


def entfernen() -> dict:
    """Timer aus, eigene Dateien weg. Fremde Dateien und alte Verweise
    bleiben liegen (nur abgeschaltet). → {"da", "entfernt", "liegen"}"""
    raus = {"da": verfuegbar(), "entfernt": [], "liegen": []}
    if not raus["da"]:
        return raus
    systemctl("disable", "--now", *[n + ".timer" for n in TIMER])
    for datei in sorted(einheiten()):
        pfad = os.path.join(ordner(), datei)
        art = _art(pfad)
        if art == "eigen":
            os.remove(pfad)
            raus["entfernt"].append(datei)
        elif art != "fehlt":
            raus["liegen"].append(datei)
    systemctl("daemon-reload")
    return raus


def _wert(*args) -> str:
    r = systemctl(*args)
    return (r.stdout or "").strip() or "?"


def zustand(wurzel=WURZEL) -> dict:
    """Je Timer: Datei (fehlt/eigen/verweis/fremd), aktuell (Inhalt wie
    gerendert), eingeschaltet, aktiv, nächster Lauf, Ergebnis des letzten."""
    raus = {"da": verfuegbar(), "befehl": befehl(wurzel), "timer": {}}
    soll = einheiten(wurzel)
    for name in TIMER:
        z = {}
        for endung in ("service", "timer"):
            pfad = os.path.join(ordner(), f"{name}.{endung}")
            z[endung] = _art(pfad)
            if z[endung] == "eigen":
                with open(pfad, encoding="utf-8") as f:
                    if f.read() != soll[f"{name}.{endung}"]:
                        z[endung] = "alt"
        if raus["da"]:
            z["an"] = _wert("is-enabled", name + ".timer")
            z["aktiv"] = _wert("is-active", name + ".timer")
            z["naechster"] = _wert("show", "-p", "NextElapseUSecRealtime", "--value", name + ".timer")
            z["ergebnis"] = _wert("show", "-p", "Result", "--value", name + ".service")
        raus["timer"][name] = z
    return raus


def kern_neu_starten() -> bool:
    """Läuft der Kern als Dienst, neu starten (er liest die KI-Schlüssel nur
    beim Start). → ob er neu gestartet wurde."""
    if not verfuegbar() or systemctl("is-active", "--quiet", KERN).returncode != 0:
        return False
    return systemctl("try-restart", KERN).returncode == 0


# ── vdirsyncer (die Kalender-Brücke) ───────────────────────────────────

def paketverwaltung() -> str:
    """pacman | apt | sonst — nach dem, was auf dem Gerät liegt."""
    for prog, name in (("pacman", "pacman"), ("apt-get", "apt")):
        if shutil.which(prog):
            return name
    return "sonst"


def vdirsyncer_da() -> bool:
    pfad = os.pathsep.join([os.path.expanduser("~/.local/bin"), os.environ.get("PATH", "")])
    return bool(shutil.which("vdirsyncer", path=pfad))
