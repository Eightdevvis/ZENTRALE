"""Platzhalter-Prozess für eine tmux-Test-Pane.

Steht für das, was in der echten Kassette in den Panes läuft (oben die curses-
TUI im Raw-Modus, unten eine interaktive bash) — die tty-erzeugten Signale
Ctrl-C/Ctrl-\/Ctrl-Z bringen KEINE davon zum Sterben. Genau das bildet dieser
Stub nach: Signale ignorieren und endlos schlafen, damit der Pane-Fuzzer die
tmux-SCHICHT testet (switchen/resizen/Lockdown) und nicht versehentlich nur den
Platzhalter abschießt.
"""
import signal
import time

for _s in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP):
    try:
        signal.signal(_s, signal.SIG_IGN)
    except (OSError, ValueError):
        pass

while True:
    time.sleep(3600)
