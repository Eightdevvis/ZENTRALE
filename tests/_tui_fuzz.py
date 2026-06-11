"""Support fürs TUI-Fuzzing (kein eigener Test — wird von test_tui_fuzz.py
importiert).

Startet die ECHTE TUI in einem Pseudo-Terminal (korrektes Controlling-TTY wie
im tmux-Pane), jagt ihr zufällige Tasten + Fenster-Resizes rein und meldet, ob
sie gestorben ist. „Gestorben" = die TUI hat ihr Crash-Log geschrieben (das
passiert NUR im except-Exception-Zweig; KeyboardInterrupt/q sind saubere Quits
und schreiben nichts). Eindeutig, unabhängig vom Exit-Code-Geschiebe beim
Teardown.

Zusätzlich kann ein adversariales Backend mitlaufen, das absichtlich gemeine,
aber plausible Daten liefert (None, Grenzwerte, fehlende Keys, falsche Typen,
Unicode, Null-Bytes) — so wird der Render-Pfad mit Daten gestresst, nicht nur
der Offline-Pfad.
"""
import os, sys, pty, time, json, errno, struct, select, signal, fcntl, random
import termios, threading, subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYBIN = sys.executable

# ── Tastatur-Alphabet + Fenstergrößen fürs Fuzzing ─────────────────────────
KEYS = [b'g', b'm', b'/', b'n', b'd', b't', b'j', b'k', b'h', b'l', b'q',
        b'+', b'-', b'0', b':', b'.', b'y', b'Y', b'1', b'5', b'\r', b'\n',
        b'\t', b'\x7f', b'\x08', b'\x1b', b'\x1b[A', b'\x1b[B', b'\x1b[C', b'\x1b[D',
        b'a', b'Z', b' ', b'\x00', b'\xff', b'\x1b[3~', b'x', b'w', b'2', b'9',
        b'G', b'M', b'N', b'D', b'T', b'p', b'r', b'3', b'4', b'8', b'_', b'=']
SIZES = [(1, 1), (2, 5), (3, 40), (5, 59), (13, 80), (14, 60), (10, 200),
         (40, 300), (24, 80), (50, 250), (60, 400), (8, 8), (200, 600), (15, 61)]


def _set_winsize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def run_session(seed, n_keys, url, deadline_s=12):
    """Eine Fuzz-Session. Rückgabe: (rc, crash_text|None, frame_err_text)."""
    rnd = random.Random(seed * 2654435761 & 0xffffffff)
    tag = f"{os.getpid()}-{seed}-{rnd.randint(0, 1 << 30)}"
    crashlog = f"/tmp/ztui-test-crash-{tag}.log"
    errlog = f"/tmp/ztui-test-frameerr-{tag}.log"
    for f in (crashlog, errlog):
        try: os.remove(f)
        except OSError: pass
    master, slave = pty.openpty()
    _set_winsize(slave, 30, 100)
    env = dict(os.environ, TERM="xterm-256color", ZENTRALE_URL=url,
               ZENTRALE_TUI_CRASH_LOG=crashlog, ZENTRALE_TUI_FRAME_ERR_LOG=errlog)
    # WICHTIG: KEIN DISPLAY für die getestete TUI. Der Fuzzer landet zwangsläufig
    # im Karten-Modus und drückt dort w/Enter, was m_window() → scripts/map_window.py
    # (natives pygame-Fenster) startet. Ohne DISPLAY greift der Guard in m_window()
    # und es wird NIE ein Fenster gespawnt — egal auf welcher Maschine der Test läuft.
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    def preexec():
        os.setsid(); fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    p = subprocess.Popen([PYBIN, "tui/zentrale_tui.py"], cwd=ROOT,
                         stdin=slave, stdout=slave, stderr=subprocess.DEVNULL,
                         env=env, close_fds=True, preexec_fn=preexec)
    os.close(slave)
    out = {"n": 0}; stop = threading.Event(); ready = threading.Event()
    def drain():
        while not stop.is_set():
            try:
                r, _, _ = select.select([master], [], [], 0.2)
                if r:
                    d = os.read(master, 65536)
                    out["n"] += len(d)
                    if out["n"] > 200:
                        ready.set()
            except OSError:
                break
    threading.Thread(target=drain, daemon=True).start()

    t_ready = time.time() + 8
    while not ready.is_set() and time.time() < t_ready:
        if p.poll() is not None:
            break
        time.sleep(0.02)

    end = time.time() + deadline_s
    for i in range(n_keys):
        if p.poll() is not None:
            break
        if i % 19 == 0:
            try: _set_winsize(master, *rnd.choice(SIZES))
            except OSError: pass
        k = rnd.choice(KEYS)
        try:
            os.write(master, k * (rnd.randint(1, 5) if rnd.random() < 0.2 else 1))
        except OSError:
            break
        if i % 200 == 0:
            time.sleep(0.003)
        if time.time() > end:
            break

    if p.poll() is None:
        p.send_signal(signal.SIGINT)        # springt die Input-Queue → sauberer Quit
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.write(master, b"\x1b\x1bqq")
            except OSError: pass
            try: p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()
    rc = p.returncode
    stop.set(); time.sleep(0.1)
    try: os.close(master)
    except OSError: pass

    def _read_del(path):
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                t = f.read()
            os.remove(path)
            return t
        return ""
    crash = _read_del(crashlog) or None
    frame = _read_del(errlog)
    return rc, crash, frame


# ── Adversariales Backend (meist gute, ~20 % transient kaputte Daten) ───────
_WEIRD_STR = ["", "x" * 4000, "ünïcödé 日本語 🚀", "NET ", "EVENT IN foo",
              "\x00\x01", "%s %d {}", "—" * 200, "\n\n", "GRAPH x"]
_WEIRD_NUM = [0, -1, -99999, 1e308, None, float("nan"), 1440, 1441,
              "nicht-zahl", True, [], {}]


class _AdvHandler(BaseHTTPRequestHandler):
    rnd = random.Random(0xC0FFEE)
    good_prob = 0.8

    def log_message(self, *a):  # still
        pass

    def _r(self):
        return self.rnd.random()

    def _pick(self, opts):
        return opts[self.rnd.randrange(len(opts))]

    # gute (realistische) Formen — Normalfall
    def _good(self, p):
        if p == "/api/state":
            return {"events": [{"event": "BOOT", "time": "07:00:01"}],
                    "sensors": {"button": False, "light": True, "motion": False, "door": False},
                    "vocab": {"word": "你好", "pinyin": "nǐ hǎo"},
                    "logs": [{"text": "KASSETTE tui", "time": "07:00:01"}],
                    "internet_logs": [], "uptime_s": 12345, "alarms": [], "time": "11. Juni 2026"}
        if p == "/api/telemetry":
            return {"pc": {"cpu": {"v": 23}, "ram": {"v": 41}, "temp": {"v": 52}}}
        if p == "/api/graphs":
            return [{"id": "g1", "name": "schlaf", "type": "period", "unit": ""},
                    {"id": "g2", "name": "gewicht", "type": "number", "unit": "kg"}]
        if p.startswith("/api/data/"):
            return [{"value": 70, "end": 450, "date": "2026-06-10"},
                    {"value": 72.5, "end": None, "date": "2026-06-11"}]
        if p == "/api/map/base":
            return {"bounds": [-180, -85, 180, 85],
                    "lines": [[[10, 5], [20, 8]], [[40, 12], [55, 15]]]}
        return {}

    # gemeine Formen
    def _adv(self, p):
        ws, wn = _WEIRD_STR, _WEIRD_NUM
        if p == "/api/state":
            keys = ["events", "sensors", "vocab", "logs", "internet_logs", "uptime_s", "alarms", "time"]
            d = {}
            for k in keys:
                if self._r() < 0.15:
                    continue
                if k in ("events", "logs", "internet_logs", "alarms"):
                    d[k] = ([self._pick(ws) for _ in range(self._pick([0, 1, 50]))]
                            if self._r() < 0.8 else self._pick(wn))
                elif k == "sensors":
                    d[k] = {s: self._pick([True, False, None, 1, "x"])
                            for s in ("button", "light", "motion", "door")} \
                        if self._r() < 0.8 else self._pick(wn)
                elif k == "uptime_s":
                    d[k] = self._pick(wn)
                elif k == "vocab":
                    d[k] = self._pick([None, {}, {"word": self._pick(ws)}, "x"])
                else:
                    d[k] = self._pick(ws + wn)
            return d
        if p == "/api/telemetry":
            if self._r() < 0.25:
                return self._pick([None, [], "kaputt", {"error": "x"}])
            return {"pc": {k: self._pick([None, {}, {"v": self._pick(wn)}, {"v": None}])
                          for k in ("cpu", "ram", "temp")} if self._r() < 0.8 else self._pick(wn)}
        if p == "/api/graphs":
            if self._r() < 0.25:
                return self._pick([None, {}, "x", [1, 2, 3]])
            out = []
            for i in range(self._pick([0, 1, 5])):
                g = {"id": self._pick(["", "g%d" % i, "ünî"]), "name": self._pick(ws),
                     "type": self._pick(["number", "scale", "time", "period", "bogus", None]),
                     "unit": self._pick(["", "kg", None])}
                if self._r() < 0.25:
                    del g[self._pick(list(g.keys()))]
                out.append(g)
            return out
        if p.startswith("/api/data/"):
            if self._r() < 0.25:
                return self._pick([None, {}, "x", 42])
            out = []
            for _ in range(self._pick([0, 1, 80])):
                e = {"value": self._pick(wn), "end": self._pick(wn + [None]),
                     "date": self._pick(["2026-06-10", None, 5])}
                if self._r() < 0.25:
                    e = self._pick([{}, {"value": None}, "x", None])
                out.append(e)
            return out
        if p == "/api/map/base":
            r = self._r()
            if r < 0.35:
                return self._pick([{"failed": True}, {}, None, {"bounds": "x"}, {"lines": "x"}])
            return {"bounds": self._pick([[-180, -85, 180, 85], [0, 0, 0, 0], [1, 2], "x"]),
                    "lines": self._pick([[], [[[0, 0], [1, 1]]], [[["a", "b"]]], "x"])}
        return self._pick([{}, None, "x"])

    def do_GET(self):
        p = self.path.split("?")[0]
        obj = self._good(p) if self._r() < self.good_prob else self._adv(p)
        self._send(obj)

    def do_POST(self):
        try:
            ln = int(self.headers.get("Content-Length", 0)); self.rfile.read(ln)
        except (ValueError, OSError):
            pass
        self._send(self._pick([{"id": "g1"}, {}, None, {"id": None}]))

    def do_DELETE(self):
        self._send(self._pick([{}, None]))

    def _send(self, obj):
        try:
            body = json.dumps(obj).encode("utf-8")
        except (ValueError, TypeError):
            body = b'{}'
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class AdversarialBackend:
    """Context-Manager: startet das gemeine Backend auf einem freien Port."""
    def __enter__(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _AdvHandler)
        self.port = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()
        return False


def pty_supported():
    """True, wenn diese Plattform pty + Controlling-TTY kann (Linux)."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        m, s = pty.openpty(); os.close(m); os.close(s)
        return True
    except OSError:
        return False
