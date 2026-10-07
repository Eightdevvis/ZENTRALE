"""Bildschirm-Vergleich der TUI: Mitschnitt in tmux (eigener Socket, 150×46).

Werkzeug für Umbauten, kein pytest-Test (wird nicht eingesammelt). Entstanden
beim Zerlegen von run_ui (06.10.2026, memory/system/tui_bauplan.md): jede
Ansicht per Tastenweg öffnen, den Bildschirm mit Farben mitschneiden, vorher
und nachher Zelle für Zelle vergleichen.

  1. Aufzeichnen (einmal, braucht das laufende Backend auf :5000 — nur GET,
     geschrieben wird nie):
       python tests/tui_schirm/lauf.py <code> /tmp/aufnahme
  2. Vorher (alter Code, z.B. per `git archive <rev> tui core` entpackt) und
     nachher (dieser Stand), beide nur aus dem Cache:
       ZTUI_NUR_CACHE=1 python tests/tui_schirm/lauf.py /tmp/alt /tmp/vorher
       ZTUI_NUR_CACHE=1 python tests/tui_schirm/lauf.py . /tmp/nachher
  3. python tests/tui_schirm/vergleich.py /tmp/vorher /tmp/nachher

Optional: Szenario-Namen als weitere Argumente (nur diese laufen).

Warum das deterministisch ist: das Backend spielt eingefrorene Antworten ab
(backend.py), die Uhr der TUI steht (sitecustomize.py, ZTUI_EINGEFROREN),
Laufschrift ist aus, Theme fest auf Nacht, kein DISPLAY (kein Fenster, kein
xset). Zwei Läufe desselben Codes ergeben dasselbe Bild.

Der Cache enthält ECHTE persönliche Daten (Kalender, Listen, Chat) und liegt
deshalb außerhalb des Repos (ZTUI_CACHE, Default ~/.cache/zentrale/).
"""
import os, sys, time, subprocess, shutil, tempfile

HIER = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SOCK = "ztui-schirm"
PORT = int(os.environ.get("ZTUI_PORT", "5987"))
FROZEN = "1791280800"   # 2026-10-06 12:00 Berlin — fest, nah an echten Daten
NAG_DATEI = os.environ.get("ZTUI_NAG_DATEI") or os.path.join(tempfile.gettempdir(), "ztui-schirm-nag.an")
os.environ["ZTUI_NAG_DATEI"] = NAG_DATEI   # das Backend erbt es

R = ["Right"]
# (name, [schritte]) — schritt: ("k", tasten...) | ("l", literal) | ("cap", name) | ("w", sek)
def rad(n):          # n-mal rechts, enter
    return [("k",) + ("Right",) * n, ("k", "Enter")] if n else [("k", "Enter")]

SZ = {
    "home": [],
    "home_slash": [("k", "/")],
    "help": [("l", "/help"), ("k", "Enter")],
    "klavier": rad(0) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("l", "yxc"), ("cap", "c")],
    "klavier2": rad(0) + [("w", 1), ("cap", "a"), ("l", "yxcv"), ("cap", "b"), ("l", "L"), ("cap", "c"),
                          ("k", "Right"), ("l", "sdg"), ("cap", "d"), ("k", "Space"), ("l", "bnm"), ("cap", "e"),
                          ("k", "Space"), ("cap", "f"), ("l", "lied"), ("cap", "g"), ("k", "Escape"), ("k", "Down"),
                          ("cap", "h"), ("l", "D"), ("cap", "i"), ("k", "Escape"), ("k", "BSpace"), ("cap", "j"),
                          ("l", "L"), ("l", "L"), ("cap", "k")],
    "post": rad(1) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("k", "Down"), ("k", "Enter"), ("cap", "c")],
    "post2": rad(1) + [("k", "Enter"), ("w", 1), ("cap", "a"), ("k", "Down"), ("cap", "b"), ("k", "Right"), ("cap", "c"),
                       ("l", "v"), ("cap", "d"), ("k", "Down"), ("cap", "e"), ("l", "s"), ("cap", "f"), ("k", "Escape"),
                       ("l", "e"), ("w", 1), ("cap", "g"), ("l", "a"), ("w", 1), ("cap", "h"), ("l", "Danke dir"),
                       ("k", "Enter"), ("l", "bis dann"), ("cap", "i"), ("k", "Escape"), ("cap", "j"),
                       ("l", "w"), ("k", "Escape"), ("l", "n"), ("cap", "k")],
    "kalender": rad(2) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("l", "m"), ("cap", "c"),
                          ("k", "Down"), ("k", "Down"), ("cap", "d"), ("k", "Tab"), ("cap", "e")],
    "kalender2": rad(2) + [("l", "x"), ("cap", "a"), ("l", "v"), ("cap", "b"), ("l", "0"), ("cap", "c"),
                           ("l", "v"), ("k", "Down"), ("k", "Down"), ("cap", "d"), ("l", "d"), ("cap", "e"),
                           ("k", "Escape"), ("l", "n"), ("cap", "f"), ("l", "a"), ("cap", "g"), ("k", "Tab"),
                           ("cap", "h"), ("k", "Tab"), ("cap", "i"), ("k", "Escape"), ("l", "l"), ("cap", "j"),
                           ("k", "Down"), ("cap", "k"), ("l", "s"), ("cap", "l"), ("k", "Escape"), ("l", "a"),
                           ("cap", "m"), ("k", "Escape"), ("k", "Escape"), ("k", "Left"), ("w", 1), ("cap", "n"),
                           ("l", "e"), ("cap", "o"), ("k", "Escape"), ("l", "x"), ("cap", "p")],
    "fokus": rad(3) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("k", "Down"), ("k", "Enter"), ("cap", "c"),
                       ("k", "Down"), ("k", "Enter"), ("cap", "d")],
    "fokus2": rad(3) + [("cap", "a"), ("k", "Down"), ("k", "Down"), ("cap", "b"), ("k", "Enter"), ("cap", "c"),
                        ("k", "Down"), ("cap", "d"), ("l", "a"), ("l", "test"), ("cap", "e"), ("k", "Escape"),
                        ("k", "Up"), ("k", "Up"), ("k", "Up"), ("k", "Up"), ("cap", "f"), ("k", "Enter"),
                        ("cap", "g"), ("k", "Escape"), ("cap", "h"), ("l", "m"), ("cap", "i"), ("k", "Down"),
                        ("cap", "j"), ("k", "Escape"), ("l", ">"), ("cap", "k"), ("k", "Down"), ("cap", "l"),
                        ("k", "Escape"), ("k", "Escape"), ("cap", "m"), ("l", "n"), ("l", "neu"), ("cap", "n"),
                        ("k", "Escape"), ("k", "Up"), ("l", "d"), ("cap", "o"), ("k", "Escape"), ("l", "r"),
                        ("cap", "p"), ("k", "Escape"), ("l", "m"), ("cap", "q"), ("k", "Escape")],
    "notizen": rad(4) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("cap", "c")],
    "notizen2": rad(4) + [("cap", "a"), ("l", "t"), ("cap", "b"), ("l", "hallo welt das ist ein text"), ("cap", "c"),
                          ("k", "Escape"), ("cap", "d"), ("l", "l"), ("cap", "e"), ("l", "punkt"), ("k", "Enter"),
                          ("l", "zwei"), ("k", "Tab"), ("cap", "f"), ("k", "Escape"), ("cap", "g"), ("l", "f"),
                          ("cap", "h"), ("l", "frei"), ("cap", "i"), ("k", "Escape"), ("k", "Up"), ("cap", "j"),
                          ("l", "r"), ("l", "neu"), ("cap", "k"), ("k", "Escape"), ("k", "Escape"), ("cap", "l"),
                          ("k", "Down"), ("cap", "m"), ("k", "Enter"), ("cap", "n"), ("l", "d"), ("cap", "o")],
    "graph": rad(5) + [("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("k", "Enter"), ("cap", "c"),
                       ("k", "Down"), ("cap", "d")],
    "graph2": rad(5) + [("cap", "a"), ("k", "Left"), ("k", "Left"), ("cap", "b"), ("k", "Right"), ("cap", "c"),
                        ("k", "Down"), ("cap", "d"), ("k", "Enter"), ("cap", "e"), ("k", "Down"), ("cap", "f"),
                        ("k", "Down"), ("cap", "g"), ("k", "Down"), ("cap", "h"), ("k", "Down"), ("cap", "i"),
                        ("k", "Left"), ("cap", "j"), ("k", "Escape"), ("l", "n"), ("cap", "k"), ("k", "Tab"),
                        ("cap", "l"), ("k", "Escape"), ("l", "r"), ("cap", "m")],
    "dash2": [("l", "/dashboard an"), ("k", "Enter"), ("w", 2), ("cap", "a"), ("resize", 120, 40), ("cap", "b"),
              ("resize", 200, 60), ("cap", "c")],
    "karte": rad(6) + [("w", 3), ("cap", "a"), ("k", "/"), ("cap", "b"), ("k", "Escape"), ("l", "+"), ("w", 2), ("cap", "c")],
    "karte2": rad(6) + [("w", 3), ("l", "+"), ("w", 2), ("k", "Right"), ("k", "Up"), ("w", 2), ("cap", "a"),
                        ("l", "o"), ("w", 3), ("cap", "b"), ("l", "o"), ("w", 3), ("cap", "c"), ("l", ","), ("w", 3),
                        ("cap", "d"), ("l", "."), ("l", "o"), ("w", 2), ("k", "M-Right"), ("w", 4), ("cap", "e"),
                        ("l", "-"), ("w", 3), ("cap", "f"), ("l", "0"), ("w", 3), ("cap", "g")],
    "tutor": rad(7) + [("cap", "a")],
    "elektronik": rad(8) + [("cap", "a"), ("k", "/"), ("cap", "b")],
    "ki": [("k", "Space"), ("w", 2), ("cap", "a"), ("k", "/"), ("cap", "b"), ("l", "hallo welt"), ("cap", "c"),
           ("k", "Up"), ("k", "Up"), ("cap", "d")],
    # Chat-Steuerung (Phase 1, 2026-10-07): Umlaute, Alt+Enter, Cursor,
    # Slash-Befehle, Auswahl, unbekannter Befehl, Esc.
    "ki_eingabe": [("k", "Space"), ("w", 2), ("l", "Grüße aus Köln"), ("k", "M-Enter"),
                   ("l", "zweite Zeile mit ß"), ("cap", "a"), ("k", "Left"), ("k", "Left"),
                   ("k", "BSpace"), ("k", "Home"), ("cap", "b"), ("k", "Up"), ("cap", "c"),
                   ("k", "M-Enter"), ("k", "M-Enter"), ("k", "M-Enter"), ("k", "M-Enter"),
                   ("k", "M-Enter"), ("l", "sieben"), ("cap", "d"), ("k", "Escape"), ("cap", "e")],
    "ki_befehle": [("k", "Space"), ("w", 2), ("l", "/hilfe"), ("k", "Enter"), ("cap", "a"),
                   ("l", "/modell"), ("k", "Enter"), ("w", 1), ("cap", "b"), ("k", "Down"),
                   ("cap", "c"), ("k", "Escape"), ("cap", "d"), ("l", "/effort"), ("k", "Enter"),
                   ("w", 1), ("cap", "e"), ("k", "Escape"), ("l", "/modl"), ("k", "Enter"),
                   ("cap", "f"), ("k", "Escape"), ("cap", "g")],
    # Gespräche (Phase 2, 2026-10-07): Denken auf/zu, Liste per Tab, wählen,
    # suchen, umbenennen, Archiv, Befehle.
    "ki_gespraeche": [("k", "Space"), ("w", 2), ("cap", "a"), ("k", "C-d"), ("cap", "b"),
                      ("k", "C-d"), ("k", "Tab"), ("w", 1), ("cap", "c"), ("k", "Down"),
                      ("cap", "d"), ("l", "/"), ("l", "steu"), ("cap", "e"), ("k", "Escape"),
                      ("k", "Down"), ("l", "r"), ("l", " neu"), ("cap", "f"), ("k", "Escape"),
                      ("l", "z"), ("w", 1), ("cap", "g"), ("l", "z"), ("w", 1), ("k", "Escape"),
                      ("l", "/titel"), ("k", "Enter"), ("cap", "h"), ("l", "/bearbeiten"),
                      ("k", "Enter"), ("w", 1), ("cap", "i"), ("k", "Escape"), ("l", "/liste"),
                      ("k", "Enter"), ("w", 1), ("k", "Down"), ("k", "Enter"), ("w", 1),
                      ("cap", "j")],
    # Gedächtnis (Phase 3, 2026-10-07): Abschnitte durchblättern, Skill
    # umschalten, Kernakte im „Editor" (ein Skript, das eine Zeile anhängt),
    # /skills springt zu den Skills.
    "ki_gedaechtnis": [("k", "Space"), ("w", 2), ("l", "/gedaechtnis"), ("k", "Enter"),
                       ("w", 1), ("cap", "a"), ("k", "Right"), ("cap", "b"), ("k", "Down"),
                       ("k", "Down"), ("cap", "c"), ("k", "Right"), ("cap", "d"),
                       ("k", "Right"), ("k", "Right"), ("cap", "e"), ("k", "Down"),
                       ("k", "Enter"), ("w", 1), ("cap", "f"), ("k", "Left"), ("k", "Left"),
                       ("k", "Left"), ("k", "Left"), ("l", "e"), ("w", 2), ("cap", "g"),
                       ("k", "Escape"), ("cap", "h"), ("l", "/skills"), ("k", "Enter"),
                       ("w", 1), ("cap", "i"), ("k", "Escape")],
    # Ablage (Phase 5, 2026-10-07): Liste, lesen, blättern, Fassung, zurück,
    # Anhang mit falschem Pfad.
    "ki_ablage": [("k", "Space"), ("w", 2), ("l", "/ablage"), ("k", "Enter"), ("w", 1),
                  ("cap", "a"), ("k", "Enter"), ("w", 1), ("cap", "b"), ("k", "NPage"),
                  ("cap", "c"), ("k", "Left"), ("w", 1), ("cap", "d"), ("k", "Escape"),
                  ("k", "Down"), ("cap", "e"), ("k", "Escape"), ("l", "/anhang /gibt/es/nicht.txt"),
                  ("k", "Enter"), ("cap", "f")],
    "tech_system": [("k", "M-Right"), ("k", "Enter"), ("cap", "a"), ("k", "/"), ("cap", "b")],
    "tech_stdout": [("k", "M-Right"), ("k", "Right"), ("k", "Enter"), ("cap", "a")],
    "tech_netz": [("k", "M-Right"), ("k", "Right"), ("k", "Right"), ("k", "Enter"), ("cap", "a")],
    "dash": [("l", "/dashboard an"), ("k", "Enter"), ("w", 2), ("cap", "a"), ("k", "Right"), ("k", "Enter"), ("cap", "b")],
    "befehle": [("l", "/xyz"), ("k", "Enter"), ("cap", "a"), ("l", "/lauf an"), ("k", "Enter"), ("cap", "b"),
                ("l", "/he"), ("cap", "c"), ("k", "BSpace"), ("k", "BSpace"), ("cap", "d"), ("k", "BSpace"),
                ("cap", "e"), ("l", "/cloud"), ("k", "Enter"), ("w", 1), ("cap", "f"), ("l", "/help"),
                ("k", "Enter"), ("cap", "g"), ("l", "x"), ("cap", "h"), ("l", "/da"), ("k", "Escape"), ("cap", "i")],
    "nag": [("cap", "a"), ("l", "x"), ("cap", "b"), ("l", "/"), ("cap", "c")],
    "nag2": [("l", "g"), ("w", 1), ("cap", "a")],
    "theme": [("l", "/theme day"), ("k", "Enter"), ("w", 1), ("cap", "a")],
    "klein": [("resize", 50, 13), ("cap", "a")],
}


def tmux(*a, check=True):
    return subprocess.run(["tmux", "-L", SOCK, "-f", "/dev/null"] + list(a),
                          capture_output=True, text=True, check=check)


def starte_backend():
    env = dict(os.environ)
    p = subprocess.Popen([PY, os.path.join(HIER, "backend.py"), str(PORT)], env=env)
    time.sleep(0.8)
    return p


def lauf(code, aus, namen, breite=150, hoehe=46):
    os.makedirs(aus, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="ztui-schirm-")
    for name in namen:
        schritte = SZ[name]
        st = os.path.join(tmp, name)
        os.makedirs(st, exist_ok=True)
        with open(os.path.join(st, "theme"), "w") as f:
            f.write("night\n")
        with open(os.path.join(st, "theme.now"), "w") as f:
            f.write("night\n")
        with open(os.path.join(st, "lauf"), "w") as f:
            f.write("aus\n")
        skript = os.path.join(st, "start.sh")
        env = {
            "ZENTRALE_URL": "http://127.0.0.1:%d" % PORT, "TERM": "xterm-256color",
            "ZENTRALE_TESTLAUF": "1", "ZTUI_EINGEFROREN": FROZEN,
            "PYTHONPATH": HIER, "ZENTRALE_NO_AUDIO": "1",
            "ZENTRALE_THEME_FILE": os.path.join(st, "theme"),
            "ZENTRALE_THEME_NOW": os.path.join(st, "theme.now"),
            "XDG_CACHE_HOME": os.path.join(st, "cache"),
            "ZENTRALE_TUI_LOG": os.path.join(st, "tui.log"),
            "ZENTRALE_TUI_CRASH_LOG": os.path.join(st, "crash.log"),
            "ZENTRALE_TUI_FRAME_ERR_LOG": os.path.join(st, "frame.log"),
            "ZENTRALE_PEER_STATUS": os.path.join(st, "peer.json"),
            "ZENTRALE_LAUF_FILE": os.path.join(st, "lauf"),
            "ZENTRALE_DASHBOARD_FILE": os.path.join(st, "dash"),
            "ZENTRALE_MAP_WINDOW_LOG": os.path.join(st, "map.log"),
            "ZENTRALE_ROOM_WINDOW_LOG": os.path.join(st, "room.log"),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "Europe/Berlin",
            # Gedächtnis-Ansicht: „Editor", der nur eine Zeile anhängt.
            "VISUAL": os.path.join(st, "editor.sh"),
        }
        with open(os.path.join(st, "editor.sh"), "w") as f:
            f.write('#!/bin/sh\necho "- neue zeile aus dem editor" >> "$1"\n')
        os.chmod(os.path.join(st, "editor.sh"), 0o755)
        with open(skript, "w") as f:
            f.write("#!/bin/sh\n")
            f.write("unset DISPLAY WAYLAND_DISPLAY ZENTRALE_TUI_SUPERVISED TMUX ZENTRALE_TUI_RELOADED ZENTRALE_TUI_RAD ZENTRALE_TUI_META ZENTRALE_ROOM_PARENT\n")
            for k, v in env.items():
                f.write("export %s='%s'\n" % (k, v))
            f.write("cd '%s'\nexec %s tui/zentrale_tui.py\n" % (code, PY))
        os.chmod(skript, 0o755)
        # Graph-Reminder nur für die nag-Szenarien (das Backend schaut auf die Datei)
        if name.startswith("nag"):
            open(NAG_DATEI, "w").close()
        elif os.path.exists(NAG_DATEI):
            os.remove(NAG_DATEI)
        sess = "s_" + name
        tmux("kill-session", "-t", sess, check=False)
        tmux("new-session", "-d", "-s", sess, "-x", str(breite), "-y", str(hoehe), skript)
        time.sleep(3.0)
        for s in schritte:
            if s[0] == "k":
                for k in s[1:]:
                    tmux("send-keys", "-t", sess, k)
                    time.sleep(0.5)
            elif s[0] == "l":
                tmux("send-keys", "-t", sess, "-l", s[1])
                time.sleep(0.5)
            elif s[0] == "w":
                time.sleep(s[1])
            elif s[0] == "resize":
                tmux("resize-window", "-t", sess, "-x", str(s[1]), "-y", str(s[2]))
                time.sleep(1.0)
            elif s[0] == "cap":
                time.sleep(1.2)
                out = tmux("capture-pane", "-p", "-e", "-t", sess).stdout
                with open(os.path.join(aus, "%s.%s.txt" % (name, s[1])), "w") as f:
                    f.write(out)
        time.sleep(1.2)
        out = tmux("capture-pane", "-p", "-e", "-t", sess).stdout
        with open(os.path.join(aus, "%s.zz.txt" % name), "w") as f:
            f.write(out)
        tmux("kill-session", "-t", sess, check=False)
        for log in ("crash.log", "frame.log"):
            p = os.path.join(st, log)
            if os.path.exists(p) and os.path.getsize(p):
                shutil.copy(p, os.path.join(aus, "%s.%s" % (name, log)))
        print("  ", name, flush=True)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    code, aus = sys.argv[1], sys.argv[2]
    namen = sys.argv[3:] or list(SZ)
    be = starte_backend()
    try:
        # Andere Größe zum Absturz-Prüfen (z. B. 80x24): ZTUI_GROESSE=80x24
        b, h = (int(x) for x in os.environ.get("ZTUI_GROESSE", "150x46").split("x"))
        lauf(os.path.abspath(code), os.path.abspath(aus), namen, b, h)
    finally:
        be.terminate()
        tmux("kill-server", check=False)
