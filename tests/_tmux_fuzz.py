"""PTY-Fuzz-Harnisch für die DOPPEL-PANE-tmux-Kassette (das „Doppelfenster").

Die Python-TUI ist anderswo schon bombenfest gefuzzt (tests/test_tui_fuzz.py).
HIER geht es um die tmux-Schicht des Launchers `scripts/start_tui.sh`:

  • Switchen oben/unten  (Ctrl-b dann ↑/↓ — EGAL ob Ctrl gehalten wird)
  • Resizen der bash     (Ctrl+↑/↓ OHNE Prefix)
  • Detach-Schutz        (Ctrl-b d/D darf NICHT abkoppeln)
  • Invarianten          (Session lebt, GENAU 2 Panes, Client bleibt attached,
                          aktive Pane ∈ {0,1}, Pane-0-Höhe ≥ 1)

So testen wir EXAKT die Live-Belegung: das Skript setzt sie über sein
Sub-Kommando `--apply-keys` (gleiche Funktion wie im echten Start) — keine
driftende Kopie. Alles läuft auf einem WEGWERF-Socket (`-L`), berührt also
weder die laufende zentrale-tui-Session des Nutzers noch den Default-tmux.
KEIN Backend, KEINE echte TUI, KEIN Map-Fenster — Pane 0/1 sind nur `sleep`.
"""
import os
import fcntl
import struct
import termios
import subprocess
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_TUI = os.path.join(ROOT, "scripts", "start_tui.sh")
import sys
# Pane-Platzhalter: ignoriert tty-Signale (Ctrl-C/\/Z), genau wie die echten
# Panes (TUI im Raw-Modus, interaktive bash) — so killt Müll-Input nie den Stub.
PANE_STUB = f"{sys.executable} {os.path.join(os.path.dirname(os.path.abspath(__file__)), '_pane_stub.py')}"

# ── Tasten-Bytes, wie ein echtes Terminal sie an den tmux-Client schickt ──────
PREFIX = b"\x02"                 # Ctrl-b
UP, DOWN = b"\x1b[A", b"\x1b[B"  # nackte Pfeile
LEFT, RIGHT = b"\x1b[D", b"\x1b[C"
C_UP, C_DOWN = b"\x1b[1;5A", b"\x1b[1;5B"   # Ctrl+Pfeil (Modifier 5 = Ctrl)


def tmux_supported():
    if not hasattr(os, "openpty"):
        return False
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _set_winsize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class PaneSession:
    """Eine echte tmux-Session mit zwei Panes + angeklebtem PTY-Client.

    Pane 0 (oben) = TUI-Platzhalter, Pane 1 (unten) = bash-Platzhalter; beides
    nur `sleep`, damit nichts Echtes hochfährt. Die Tastenbelegung kommt 1:1 aus
    start_tui.sh (`--apply-keys`). Methoden: feed(), state(), wait_attached().
    """

    def __init__(self, seed, rows=40, cols=80, split_lines=6):
        self.sock = f"ztui-panes-{os.getpid()}-{seed}"
        self.rows, self.cols, self.split = rows, cols, split_lines
        self.master = None
        self.proc = None
        self._drain = None

    # — Socket-gebundenes tmux —
    def _tmux(self, *args, check=False, timeout=10):
        return subprocess.run(["tmux", "-L", self.sock, *args],
                              capture_output=True, text=True,
                              check=check, timeout=timeout)

    def __enter__(self):
        env = dict(os.environ)
        # Hook-Spawns (save-height) während des Tests vermeiden: der Hook würde
        # start_tui.sh --save-height auf dem DEFAULT-Socket aufrufen. Wir setzen
        # XDG_CONFIG_HOME auf Wegwerf, damit selbst ein Schreiben nie die echte
        # ~/.config/zentrale/tui_term_lines des Nutzers anfasst.
        env["XDG_CONFIG_HOME"] = f"/tmp/ztui-panes-cfg-{os.getpid()}"
        # Server + Pane 0 (TUI-Platzhalter)
        self._tmux("-f", "/dev/null", "new-session", "-d", "-s", "s",
                   "-x", str(self.cols), "-y", str(self.rows), PANE_STUB,
                   check=True)
        # EXAKT die Live-Belegung anwenden (über das Skript-Sub-Kommando)
        subprocess.run([START_TUI, "--apply-keys", "s"],
                       env={**env, "ZENTRALE_TMUX_L": self.sock},
                       capture_output=True, text=True, check=True, timeout=10)
        # Den Höhen-Hook für den Test neutralisieren (er zielt sonst cross-socket
        # auf den Default-tmux). Das Switchen/Resizen/Detach bleibt voll getestet.
        self._tmux("set-hook", "-u", "-t", "s", "after-resize-pane")
        # Pane 1 (bash-Platzhalter) unten dazu
        self._tmux("split-window", "-d", "-v", "-l", str(self.split), "-t", "s",
                   PANE_STUB, check=True)
        # Client im PTY ankleben
        self.master, slave = os.openpty()
        _set_winsize(slave, self.rows, self.cols)

        def _pre():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        self.proc = subprocess.Popen(
            ["tmux", "-L", self.sock, "attach-session", "-t", "s"],
            stdin=slave, stdout=slave, stderr=slave,
            preexec_fn=_pre, env={**env, "TERM": "xterm-256color"}, close_fds=True)
        os.close(slave)
        # Master leerlesen, sonst blockiert der Client beim Rendern
        self._drain = threading.Thread(target=self._drain_master, daemon=True)
        self._drain.start()
        return self

    def _drain_master(self):
        while True:
            try:
                if not os.read(self.master, 65536):
                    break
            except OSError:
                break

    def wait_attached(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.state().get("attached"):
                return True
            time.sleep(0.03)
        return False

    def feed(self, payload):
        os.write(self.master, payload)

    def state(self):
        """Momentaufnahme: existiert die Session, ist sie attached, Panes-Liste."""
        out = self._tmux("list-panes", "-t", "s",
                         "-F", "#{pane_index} #{pane_active} #{pane_height}")
        if out.returncode != 0:
            return {"exists": False, "attached": False, "npanes": 0,
                    "active": None, "pane0_height": None}
        panes = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) == 3:
                panes.append((int(parts[0]), int(parts[1]), int(parts[2])))
        att = self._tmux("display-message", "-p", "-t", "s", "-F",
                         "#{session_attached}")
        attached = att.returncode == 0 and att.stdout.strip() not in ("", "0")
        active = next((i for (i, a, _h) in panes if a == 1), None)
        h0 = next((h for (i, _a, h) in panes if i == 0), None)
        return {"exists": True, "attached": attached, "npanes": len(panes),
                "active": active, "pane0_height": h0, "panes": panes}

    def settle(self, delay=0.03):
        time.sleep(delay)

    def select_bottom(self):
        """Fokus deterministisch auf Pane 1 (unten) setzen — Ausgangslage."""
        self._tmux("select-pane", "-t", "s.1")

    def select_top(self):
        self._tmux("select-pane", "-t", "s.0")

    def __exit__(self, *exc):
        try:
            if self.proc:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        finally:
            try:
                if self.master is not None:
                    os.close(self.master)
            except OSError:
                pass
            self._tmux("kill-server")
            # Tote Socket-Datei mitnehmen, sonst sammeln sich bei vielen Sessions
            # hunderte Leichen in /tmp/tmux-<uid>/ an.
            sockdir = os.environ.get("TMUX_TMPDIR", "/tmp")
            try:
                os.unlink(os.path.join(sockdir, f"tmux-{os.getuid()}", self.sock))
            except OSError:
                pass


# ── Fuzz: zufällige Tastenfolgen, nach JEDER Aktion alle Invarianten prüfen ───
class Result:
    def __init__(self, ok, msg=""):
        self.ok, self.msg = ok, msg


# (Name, Bytes) — bewusst inkl. Müll, Prefix+Müll, Detach-Versuche, Pfeil-Salat.
def _alphabet(rnd):
    junk = bytes([rnd.randint(1, 255)])
    return rnd.choice([
        ("prefix-up",     PREFIX + UP),       # switch hoch
        ("prefix-down",   PREFIX + DOWN),     # switch runter
        ("prefix-cup",    PREFIX + C_UP),     # switch hoch MIT Ctrl gehalten (Fix)
        ("prefix-cdown",  PREFIX + C_DOWN),   # switch runter MIT Ctrl gehalten
        ("prefix-left",   PREFIX + LEFT),     # kein linker Pane → harmlos
        ("prefix-right",  PREFIX + RIGHT),
        ("root-cup",      C_UP),              # resize bash höher
        ("root-cdown",    C_DOWN),            # resize bash niedriger
        ("detach-d",      PREFIX + b"d"),     # darf NICHT abkoppeln
        ("detach-D",      PREFIX + b"D"),
        ("prefix-junk",   PREFIX + junk),     # Prefix + Zufallsbyte
        ("junk",          junk),              # roher Müll in die Pane
        ("resize-burst",  C_UP * 8),          # viele Resizes am Stück
        ("resize-burst2", C_DOWN * 8),
    ])


def run_fuzz_session(seed, n_actions=30):
    import random
    rnd = random.Random(seed)
    with PaneSession(seed) as ps:
        if not ps.wait_attached():
            return Result(False, f"Client nie attached (seed={seed})")
        for i in range(n_actions):
            name, payload = _alphabet(rnd)
            ps.feed(payload)
            ps.settle()
            st = ps.state()
            if not st["exists"]:
                return Result(False, f"Session WEG nach '{name}' (#{i}, seed={seed})")
            if st["npanes"] != 2:
                return Result(False, f"{st['npanes']} Panes (≠2) nach '{name}' "
                                     f"(#{i}, seed={seed})")
            if not st["attached"]:
                return Result(False, f"DETACHED nach '{name}' (#{i}, seed={seed}) "
                                     "— Detach-Schutz versagt?")
            if st["active"] not in (0, 1):
                return Result(False, f"aktive Pane {st['active']} ∉ {{0,1}} nach "
                                     f"'{name}' (#{i}, seed={seed})")
            if st["pane0_height"] is None or st["pane0_height"] < 1:
                return Result(False, f"Pane-0-Höhe {st['pane0_height']} < 1 nach "
                                     f"'{name}' (#{i}, seed={seed})")
        return Result(True, f"ok (seed={seed})")
