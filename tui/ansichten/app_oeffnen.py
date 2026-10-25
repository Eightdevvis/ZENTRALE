# tui/ansichten/app_oeffnen.py
#
# Eine App aus dem Schaufenster öffnen (2026-10-25, memory/hub/shop.md „Apps
# installieren"). Im Rad steht sie wie jede eigene App (eigene_apps.py); Enter
# geht über ihre Adresse zentrale://<name>/ an den Router und landet hier:
#   - eine eingerichtete Ansicht → gleich öffnen,
#   - mehrere → ein kleiner Kasten „wie öffnen?" (↑↓ enter, esc zurück).
#
# Die Ansichten (hub_bauplan.md „Ansichten"):
#   browser   der Hub startet die App (POST /api/apps/<name>/start, falls sie
#             nicht läuft), dann geht ihre Adresse im Browser auf
#   terminal  `[ansicht.terminal] start` läuft in DIESEM Terminal; die TUI
#             tritt so lange beiseite (wie beim Editor) und kommt danach zurück
#   fenster   `[ansicht.fenster] start` als eigenes Fenster (wie die Karte)
# Beide Starter gehen über scripts/open_app_window.py — die TUI kennt keinen
# Code einer App, sie liest nur, was /api/apps sagt.

import curses
import os
import subprocess
import threading

from .basis import PROJEKT, api_call, venv_python
from .chat_morgenblick import im_browser_oeffnen
from .tasten import Tasten

STARTER = os.path.join(PROJEKT, "scripts", "open_app_window.py")


class AppOeffnen:
    """Zustand in self.W (auch z.APPWAHL, damit fenster.py den Fokus sieht)."""

    def __init__(self, z, bz=None):
        self.z, self.bz = z, bz
        self.W = z.APPWAHL = {"active": False, "app": None, "sel": 0}
        # Hintergrund (Browser-Start wartet auf die App); Tests: gleich.
        self.starten = lambda f: threading.Thread(target=f, daemon=True).start()

    def _melden(self, text):
        if self.bz is not None:
            self.bz.cmd_msg = text

    # ── Öffnen ────────────────────────────────────────────────────────
    def oeffnen(self, app):
        """Router-Handler einer App: eine Ansicht direkt, mehrere zur Wahl."""
        ansichten = [a for a in (app.get("ansichten_installiert") or []) if isinstance(a, dict)]
        if not ansichten:
            self._melden("„%s\" hat keine ansicht eingerichtet — im shop wählen" % app.get("name"))
            return True
        if len(ansichten) == 1:
            self.ansicht_oeffnen(app, ansichten[0])
            return True
        self.W.update(active=True, app=dict(app, ansichten_installiert=ansichten), sel=0)
        return True

    def ansicht_oeffnen(self, app, ansicht):
        name, art = app.get("name"), ansicht.get("id")
        if art == "browser":
            self.starten(lambda: self._browser(name, ansicht.get("url")))
        elif art == "terminal":
            self._terminal(name)
        else:
            self._fenster(name, art)

    def _browser(self, name, url):
        if not url:
            self._melden("„%s\" hat keine adresse für den browser" % name)
            return
        self._melden("„%s\" startet …" % name)
        try:
            # openapi.yaml: /api/apps/{name}/start (der Routen-Wächter liest
            # nur den Anfang einer Zeichenkette, darum „/api/apps" + Rest)
            r = api_call("/api/apps" + "/%s/start" % name, "POST", {}, timeout=25) or {}
        except Exception as e:
            self._melden("„%s\" startet nicht: %s" % (name, getattr(e, "reason", e)))
            return
        if r.get("laeuft") is False:
            self._melden("„%s\" fährt noch hoch — gleich nochmal" % name)
            return
        if im_browser_oeffnen(url):
            self._melden("„%s\" geht im browser auf" % name)
        else:
            self._melden("kein browser hier (keine grafische sitzung) — %s" % url)

    def _terminal(self, name):
        """Im selben Terminal: curses beiseite, App laufen lassen, zurück."""
        stdscr = getattr(self.z, "stdscr", None)
        curses.def_prog_mode()
        curses.endwin()
        try:
            code = subprocess.call([venv_python(PROJEKT), STARTER, name, "--ansicht", "terminal"])
        except OSError as e:
            code = None
            self._melden("„%s\" startet nicht: %s" % (name, e))
        finally:
            curses.reset_prog_mode()
            if stdscr is not None:
                stdscr.clear()
                stdscr.refresh()
        if code not in (0, None):
            self._melden("„%s\" im terminal endete mit fehler %s" % (name, code))

    def _fenster(self, name, art):
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            self._melden("ein fenster braucht einen bildschirm (hier gibt es keinen)")
            return
        try:
            subprocess.Popen([venv_python(PROJEKT), STARTER, name, "--ansicht", art],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            self._melden("„%s\" geht auf (eigenes fenster)" % name)
        except OSError as e:
            self._melden("„%s\" startet nicht: %s" % (name, e))

    # ── Tasten (Tastentabelle) ────────────────────────────────────────
    TASTEN = Tasten({"wahl": [("↑↓", "waehlen", "select"), ("enter", "oeffnen", "open"),
                              ("esc", "zu", "back")]})

    def ansicht(self):
        return "wahl"

    def taste(self, ch):
        self.TASTEN.verteilen(self, self.ansicht(), ch)
        return None

    def aktion_waehlen(self, taste):
        n = len((self.W["app"] or {}).get("ansichten_installiert") or [])
        if n:
            self.W["sel"] = (self.W["sel"] + (-1 if taste == "up" else 1)) % n

    def aktion_oeffnen(self, _taste):
        app = self.W["app"]
        self.W.update(active=False)
        if app:
            self.ansicht_oeffnen(app, app["ansichten_installiert"][self.W["sel"]])

    def aktion_zu(self, _taste):
        self.W.update(active=False, app=None)

    # ── Zeichnen ──────────────────────────────────────────────────────
    def titel(self):
        app = self.W["app"] or {}
        return "%s öffnen" % (app.get("titel") or app.get("name") or "app")

    def draw(self, top, mx, h, w):
        W, C, z = self.W, self.z.C, self.z
        app = W["app"] or {}
        if h < 5 or w < 16:
            return
        x0 = mx + 2
        z.addclip(top + 2, x0, "wie soll „%s\" aufgehen?" % (app.get("titel") or app.get("name")),
                  w - 4, C["bright"] | curses.A_BOLD)
        for i, a in enumerate((app.get("ansichten_installiert") or [])[:max(0, h - 6)]):
            text = a.get("titel") or a.get("id")
            if i == W["sel"]:
                z.addclip(top + 4 + i, x0, (" " + text).ljust(min(w - 4, 24)), w - 4,
                          C["bright"] | curses.A_REVERSE)
            else:
                z.addclip(top + 4 + i, x0, " " + text, w - 4, C["dim"])
