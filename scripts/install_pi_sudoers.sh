#!/usr/bin/env bash
# =============================================================================
# install_pi_sudoers.sh
# -----------------------------------------------------------------------------
# Schreibt eine sudoers-Drop-In-Datei nach /etc/sudoers.d/zentrale.
# Damit darf der aktuelle User OHNE Passwort folgende Befehle absetzen:
#
#   - systemctl restart zentrale.service     (fuer pi_autopull.sh)
#   - systemctl restart whisper.service      (autopull)
#   - systemctl restart tts.service          (autopull)
#   - systemctl stop lightdm                 (fuer emergency_exit.sh)
#   - chvt 1                                 (emergency_exit -> TTY1)
#   - install_pi_services.sh                 (autopull patcht systemd-Units)
#   - install_firefox_mic_policy.sh          (install_xfce_autostart.sh
#                                             schreibt damit policies.json
#                                             fuer Kiosk-Mikrofon-Permission)
#
# BEWUSST ENG GESCHNITTEN: kein Generalfreibrief, nur exakt diese
# Kommandos. Wenn neue gebraucht werden, dieses File erweitern
# und nicht einfach "ALL" eintragen.
#
# AUFRUF (auf dem Pi):
#   sudo bash /opt/zentrale/scripts/install_pi_sudoers.sh
#
# ABLOESUNG der alten /etc/sudoers.d/zentrale-autopull-Datei (falls
# vorhanden) ist OK — die neue Datei deckt deren Befehl mit ab.
# =============================================================================

set -euo pipefail

# Muss als root laufen — wir schreiben in /etc/sudoers.d.
if [ "$(id -u)" -ne 0 ]; then
    echo "FEHLER: bitte mit sudo ausfuehren." >&2
    exit 1
fi

# Der User, dem wir die Rechte geben wollen. SUDO_USER wird von sudo
# automatisch auf den aufrufenden User gesetzt — genau was wir wollen.
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    echo "FEHLER: SUDO_USER nicht gesetzt oder root. Skript NICHT als root direkt ausfuehren," >&2
    echo "        sondern als normaler User mit 'sudo bash ...'." >&2
    exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/zentrale"

# Drop-In schreiben. visudo-Syntax: <user> <host>=(<runas>) NOPASSWD: <cmd>, <cmd>...
# Mehrere Befehle in einer Zeile sind erlaubt und uebersichtlicher als
# einzelne Zeilen.
#
# Die installierten Befehle:
#  - systemctl restart {zentrale,whisper,tts}.service  -> autopull-Restart
#  - systemctl stop lightdm                            -> Notaus-Hotkey
#  - chvt 1                                            -> Notaus -> TTY1
#  - install_pi_services.sh                            -> autopull patcht
#                                                         Unit-Files wenn
#                                                         sich deploy/*.service
#                                                         im Repo aendert
#  - install_firefox_mic_policy.sh                     -> install_xfce_autostart.sh
#                                                         laesst damit das
#                                                         Kiosk-Mikrofon
#                                                         pre-allowen
#                                                         (policies.json)
cat > "$SUDOERS_FILE" <<EOF
# Auto-generiert von scripts/install_pi_sudoers.sh.
# Gibt dem User '$TARGET_USER' passwordless sudo fuer genau die
# Befehle die ZENTRALE-Automatisierung braucht (autopull + Notaus +
# Kiosk-Mic-Policy).
$TARGET_USER ALL=(ALL) NOPASSWD: /bin/systemctl restart zentrale.service, /bin/systemctl restart whisper.service, /bin/systemctl restart tts.service, /bin/systemctl stop lightdm, /usr/bin/chvt 1, /opt/zentrale/scripts/install_pi_services.sh, /opt/zentrale/scripts/install_firefox_mic_policy.sh
EOF

# Permissions wie sudoers es verlangt — sonst ignoriert sudo das File
# stillschweigend und der ganze Aufwand bringt nichts.
chmod 440 "$SUDOERS_FILE"

# Syntax-Check vor dem Beenden. Wenn visudo hier meckert, das File
# loeschen — sonst ist sudo evtl. ganz kaputt.
if ! visudo -c -f "$SUDOERS_FILE" >/dev/null; then
    echo "FEHLER: visudo-Syntaxcheck fehlgeschlagen, entferne kaputtes File." >&2
    rm -f "$SUDOERS_FILE"
    exit 1
fi

# Alten autopull-Eintrag wegraeumen — neuer Eintrag deckt den ab.
# Stilles loeschen ist ok wenn der Alte gar nicht existiert.
rm -f /etc/sudoers.d/zentrale-autopull

echo "OK: $SUDOERS_FILE geschrieben fuer User '$TARGET_USER'."
echo "Test mit:  sudo -n -l    # sollte die Befehle listen"
