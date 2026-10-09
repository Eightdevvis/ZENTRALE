# tui/ansichten/app_start.py
#
# Eine App aus der TUI starten — heute nur den Sprach-Tutor (Taste 'u').
#
# Seit 2026-10-09 ist der Tutor eine eigene App (Repo language-tutor, siehe
# memory/system/hub_bauplan.md). Die TUI kennt seinen Code nicht und redet
# nicht mit ihm: sie ruft nur den Starter scripts/open_tutor_room.py auf.
# Der findet die App, fährt Stimm-Dienste und Tutor-Server bei Bedarf hoch
# und öffnet das Zimmer. Bis hierher stand an dieser Stelle das Text-Panel
# des Tutors (tui/ansichten/sprachtutor.py) — das ist mit dem Umzug weg.

import os
import subprocess
import threading

from .basis import BASE_URL, PROJEKT, venv_python

STARTER = os.path.join(PROJEKT, "scripts", "open_tutor_room.py")


class AppStart:
    """Startet das Zimmer des Tutors als eigenen Prozess. Meldungen landen in
    der Befehlszeile (bz.cmd_msg)."""

    def __init__(self, z, bz=None):
        self.z = z
        self.bz = bz           # Befehlszeile: dort stehen die Meldungen
        self.proc = None

    def _melden(self, text):
        if self.bz is not None:
            self.bz.cmd_msg = text

    def pruefen(self):
        """Ist die App da? → '' oder ein Satz für Sasha."""
        if not os.path.exists(STARTER):
            return "der starter für den sprach-tutor fehlt"
        try:
            r = subprocess.run([venv_python(PROJEKT), STARTER, "--pruefen"],
                               capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.SubprocessError) as exc:
            return "sprach-tutor nicht prüfbar: %s" % exc
        return "" if r.returncode == 0 else (r.stdout.strip() or r.stderr.strip()
                                             or "sprach-tutor nicht startbar")

    def tutor_oeffnen(self):
        """Taste 'u': das Zimmer aufmachen (im Hintergrund, die TUI läuft weiter)."""
        if not os.environ.get("DISPLAY"):
            self._melden("das zimmer braucht einen bildschirm (hier gibt es keinen)")
            return
        if self.proc is not None and self.proc.poll() is None:
            self._melden("zimmer läuft schon")
            return
        threading.Thread(target=self._starten, daemon=True).start()

    def _starten(self):
        grund = self.pruefen()
        if grund:
            self._melden(grund)
            return
        try:
            log = os.environ.get("ZENTRALE_ROOM_WINDOW_LOG") or "/tmp/zentrale-tutor-room.log"
            with open(log, "a", encoding="utf-8") as errf:
                self.proc = subprocess.Popen(
                    [venv_python(PROJEKT), STARTER, "--hub", BASE_URL],
                    stdout=subprocess.DEVNULL, stderr=errf, start_new_session=True)
            self._melden("zimmer geht auf (eigenes fenster)")
        except OSError as exc:
            self._melden("zimmer-start: %s" % exc)
