#!/usr/bin/env python3
# scripts/morgen_watcher.py
#
# Der Wächter des Morgen-Messengers: der kleine Daemon, der merkt, dass der
# Laptop aufgeklappt wurde, und dann das Fenster (scripts/morgen_start.sh)
# aufmacht. Läuft aus dem XDG-Autostart, also in JEDER Sitzung — auch wenn
# ZENTRALE selbst gar nicht gestartet wurde. Das ist der ganze Punkt: die
# Schlaf-Abfrage nagte bisher nur DRIN, im Dashboard und in der TUI.
#
# Wie das Aufklappen erkannt wird — ohne root, ohne dbus, ohne systemd-Hook:
# CLOCK_MONOTONIC (time.monotonic) steht während Suspend STILL, die Wanduhr
# (time.time) läuft weiter. Klaffen die beiden zwischen zwei Runden weiter
# auseinander als die Rundenzeit, war die Maschine schlafen — und ist es
# jetzt nicht mehr. Das funktioniert auf jedem Linux, ist nicht an logind
# oder eine Desktop-Umgebung gebunden und braucht keine Rechte.
#
# Zwei Anlässe, nachzuschauen:
#   1. Aufwachen aus Suspend (der Normalfall: Deckel auf).
#   2. Der Minutentakt — deckt Kaltstart, Anmeldung und den Fall ab, dass es
#      beim Aufwachen noch vor der Weckzeit war (5 Uhr, siehe core/morgen.py).
#
# Aufgemacht wird höchstens EINMAL pro Aufwach-Ereignis: wer das Fenster
# wegklickt, ohne zu antworten, soll nicht alle 30 Sekunden wieder eins
# bekommen. Beim nächsten Deckel-Auf ist der Messenger wieder da.
#
# Aufruf:
#   python3 scripts/morgen_watcher.py            # Dauerlauf (Autostart)
#   python3 scripts/morgen_watcher.py --once     # einmal prüfen, dann raus

import os
import sys
import time
import subprocess
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'core'))

import morgen  # noqa: E402

TICK = 30                 # Sekunden zwischen zwei Runden
SUSPEND_SLACK = 90        # Wanduhr-Vorsprung ab dem wir von Suspend ausgehen
START = os.path.join(_ROOT, 'scripts', 'morgen_start.sh')


def log(msg):
    """Eine Zeile nach stdout — der Autostart schiebt das ins Journal bzw. in
    die Log-Datei, die das .desktop-File angibt. Bewusst kein eigenes
    Log-Framework für einen Daemon, der drei Zeilen pro Tag schreibt."""
    print('[morgen-watcher %s] %s' % (time.strftime('%H:%M:%S'), msg), flush=True)


def open_window():
    """Fenster aufmachen. Der Starter prüft selbst nochmal, ob wirklich was
    fällig ist und ob nicht schon eins offen steht — hier wird nur gerufen."""
    try:
        subprocess.Popen(['bash', START],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError as e:
        log('start fehlgeschlagen: %s' % e)
        return False


def main():
    once = '--once' in sys.argv
    if once:
        if morgen.is_due():
            open_window()
            log('fällig → fenster auf')
        else:
            log('nichts fällig')
        return 0

    log('läuft (weckzeit %s, tick %ds)' % (morgen.earliest_time(), TICK))
    last_wall, last_mono = time.time(), time.monotonic()
    opened_on = None          # Datum, an dem zuletzt aufgemacht wurde

    while True:
        time.sleep(TICK)
        wall, mono = time.time(), time.monotonic()
        # Wanduhr weiter gesprungen als die laufende Uhr → dazwischen lag
        # Suspend. Der Vorsprung ist zugleich die Schlafdauer.
        gap = (wall - last_wall) - (mono - last_mono)
        last_wall, last_mono = wall, mono
        if gap > SUSPEND_SLACK:
            log('aufgewacht (%d min geschlafen)' % (gap // 60))
            opened_on = None          # neues Aufwachen → wieder eine Chance

        today = date.today()
        if opened_on == today:
            continue
        if not morgen.is_due():
            continue
        if open_window():
            opened_on = today
            log('fällig → fenster auf')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
