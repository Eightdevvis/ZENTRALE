#!/usr/bin/env bash
# =============================================================================
# install_morgen_autostart.sh — den Morgen-Messenger in die Sitzung hängen.
#
# Schreibt ~/.config/autostart/zentrale-morgen.desktop. Der Eintrag startet
# scripts/morgen_watcher.py — den Daemon, der das Aufklappen des Laptops
# bemerkt und dann das Messenger-Fenster aufmacht.
#
# Warum XDG-Autostart und nicht systemd oder cron:
#   - Der Messenger braucht eine GRAFISCHE Sitzung ($DISPLAY) — er macht ein
#     Fenster auf. Ein systemd-Timer läuft ohne die und müsste sich das
#     Display zusammensuchen.
#   - i3 startet die XDG-Einträge über `dex --autostart --environment i3`
#     (steht so in ~/.config/i3/config), XFCE von Haus aus. Ein Eintrag,
#     beide Sitzungen — deshalb steht hier ausdrücklich KEIN OnlyShowIn.
#   - cron kennt weder Sitzung noch Suspend. Die Erkennung des Aufklappens
#     macht der Watcher selbst (siehe dessen Kopf-Kommentar).
#
# Aufruf (als normaler User, nicht root):
#   bash scripts/install_morgen_autostart.sh
#
# Idempotent — beliebig oft aufrufbar, überschreibt den Eintrag.
#
# Wieder loswerden:
#   rm ~/.config/autostart/zentrale-morgen.desktop
#   pkill -f morgen_watcher.py
# =============================================================================

set -euo pipefail

if [ "$(id -u)" = "0" ]; then
    echo "FEHLER: bitte als normaler User ausführen, NICHT mit sudo." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP="$AUTOSTART_DIR/zentrale-morgen.desktop"
LOG="${ZENTRALE_MORGEN_LOG:-/tmp/zentrale-morgen.log}"

mkdir -p "$AUTOSTART_DIR"

cat > "$DESKTOP" << EOF
[Desktop Entry]
Type=Application
Name=ZENTRALE Morgen-Messenger
Comment=Meldet sich beim Aufklappen des Laptops: Schlafzeiten + erste Aufgabe
Exec=bash -c 'exec python3 "$ROOT/scripts/morgen_watcher.py" >> "$LOG" 2>&1'
X-GNOME-Autostart-enabled=true
StartupNotify=false
Terminal=false
EOF

echo "Autostart geschrieben: $DESKTOP"
echo "Log:                   $LOG"
echo
echo "Jetzt starten (ohne neu anzumelden):"
echo "  python3 $ROOT/scripts/morgen_watcher.py >> $LOG 2>&1 &"
echo
echo "Fenster sofort anschauen (auch wenn nichts fällig ist):"
echo "  bash $ROOT/scripts/morgen_start.sh --force"
