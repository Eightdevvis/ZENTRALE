#!/usr/bin/env bash
# =============================================================================
# install_xfce_autostart.sh
# -----------------------------------------------------------------------------
# Repariert den ZENTRALE-Pi-Kiosk: xfce4-session startete bislang ohne
# xfwm4 (Window Manager) und xfdesktop (Desktop-Renderer), dadurch wurde
# der echte HDMI-Output schwarz. Ohne WM und Desktop-Renderer malt nichts
# aufs Root-Window -> der Encoder schickt einen schwarzen Frame raus.
#
# WAS DAS SKRIPT MACHT:
# 1. Legt zwei autostart-.desktop-Files in ~/.config/autostart/ an, die
#    XDG-Autostart-konform xfwm4 und xfdesktop nach dem XFCE-Session-Start
#    feuern. Damit umgehen wir die Frage warum xfce4-session die Failsafe-
#    Defaults aus /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml
#    nicht selbst lädt - mit autostart sind die Komponenten unabhängig
#    von der xfce-Session-Choreographie immer da.
#
# 2. Idempotent: kann beliebig oft aufgerufen werden, ueberschreibt die
#    Files jedes Mal mit dem aktuellen Inhalt.
#
# AUFRUF (auf dem Pi, als sasha-User - NICHT root):
#   bash /opt/zentrale/scripts/install_xfce_autostart.sh
#
# DEINSTALLATION:
#   rm ~/.config/autostart/xfwm4.desktop ~/.config/autostart/xfdesktop.desktop
# =============================================================================

set -euo pipefail

# Sanity-Check: nicht als root ausfuehren. ~/.config/autostart gehoert
# dem User, sonst wuerde xfce4-session die Files spaeter wegen falscher
# Permissions ignorieren.
if [ "$(id -u)" = "0" ]; then
    echo "FEHLER: bitte als normaler User (sasha) ausfuehren, NICHT mit sudo." >&2
    exit 1
fi

# Ziel-Verzeichnis sicherstellen. -p falls schon da.
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

# --- xfwm4 autostart ---------------------------------------------------------
# xfwm4 ist der XFCE-Window-Manager. Ohne ihn kein Fenster-Drawing, keine
# _NET_*-Properties (die wir vorher in .xsession-errors als fehlend sahen),
# kein sichtbares Greeter/Login-Panel. --replace damit ein evtl. schon
# laufender WM (z.B. mutter, falls XFCE einen anderen vorher gestartet
# hat) ersetzt wird.
cat > "$AUTOSTART_DIR/xfwm4.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=xfwm4
Comment=ZENTRALE force-autostart: xfce4-session startet xfwm4 nicht zuverlaessig
Exec=xfwm4 --replace
OnlyShowIn=XFCE
X-GNOME-Autostart-enabled=true
EOF

# --- xfdesktop autostart -----------------------------------------------------
# xfdesktop zeichnet den Desktop-Hintergrund (Tapete, Icons). Ohne ihn
# bleibt das Root-Window komplett schwarz auch bei laufendem xfwm4.
cat > "$AUTOSTART_DIR/xfdesktop.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=xfdesktop
Comment=ZENTRALE force-autostart: Desktop-Hintergrund + Icons
Exec=xfdesktop
OnlyShowIn=XFCE
X-GNOME-Autostart-enabled=true
EOF

# --- Ausgabe ------------------------------------------------------------------
echo "Installiert:"
ls -la "$AUTOSTART_DIR/xfwm4.desktop" "$AUTOSTART_DIR/xfdesktop.desktop"
echo
echo "Test mit:"
echo "  sudo systemctl start lightdm"
echo "  # 10s warten, dann pgrep -af xfwm4|xfdesktop"
echo "  # plus Screenshot per scrot, siehe scripts/display_debug.sh"
echo
echo "Falls erfolgreich: Kiosk-Autostart reaktivieren via"
echo "  mv ~/.config/autostart/zentrale.desktop.disabled ~/.config/autostart/zentrale.desktop"
