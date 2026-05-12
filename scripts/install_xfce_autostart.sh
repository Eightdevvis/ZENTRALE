#!/usr/bin/env bash
# =============================================================================
# install_xfce_autostart.sh
# -----------------------------------------------------------------------------
# Konfiguriert XFCE auf dem Pi als reinen Kiosk: KEIN Wallpaper, KEIN Panel,
# KEINE Desktop-Icons. Nur xfwm4 (Window Manager) + xfsettingsd (xrandr/
# theme-Daemon) laufen — Firefox-Kiosk legt sich sofort als einziges Fenster
# vollflaechig drueber.
#
# Hintergrund: vorher sah man zwischen lightdm-Login und Firefox-Start
# noch kurz das default XFCE-Setup (Wallpaper + Panel). Jetzt bleibt das
# Root-Window schwarz, bis Firefox kommt.
#
# WAS DAS SKRIPT MACHT:
# 1. Schreibt ~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml
#    mit einer Minimal-"Failsafe"-Session. Default-XFCE startet ueber den
#    Failsafe-Mechanismus xfwm4 + xfsettingsd + xfce4-panel + xfdesktop +
#    Thunar — wir kappen das auf xfwm4 + xfsettingsd. Damit ist Panel/
#    Wallpaper out-of-the-box weg, ohne pkill-Tricks.
#
# 2. xfwm4-autostart bleibt als Belt-and-Suspenders (~/.config/autostart/
#    xfwm4.desktop). Falls die xfce4-session.xml mal nicht greift, ist
#    xfwm4 trotzdem da, weil sonst Firefox-Kiosk-Fullscreen nicht sauber
#    sitzt.
#
# 3. Loescht das alte xfdesktop-autostart-File (falls von einer frueheren
#    Skriptversion da). xfdesktop wollen wir explizit NICHT mehr.
#
# 4. Schreibt ~/.xprofile mit xrandr-Force auf 1920x1080@60. Grund: nach
#    dem fkms-Umstieg (siehe memory/display_debug.md) wird der EDID-
#    preferred Mode des Pi-Monitors nicht zuverlaessig genommen.
#
# 5. Aktiviert den Kiosk-Autostart (~/.config/autostart/zentrale.desktop):
#    wartet bis ZENTRALE auf Port 5000 antwortet, dann firefox-esr --kiosk.
#
# 6. Verdrahtet den Notaus-Hotkey Ctrl+Alt+Esc auf emergency_exit.sh
#    (lightdm stoppen -> Pi auf TTY1). Klappt nur aus einer aktiven
#    XFCE-Session heraus, weil xfconf-query DBus braucht.
#
# AUFRUF (auf dem Pi, als sasha-User - NICHT root):
#   bash /opt/zentrale/scripts/install_xfce_autostart.sh
#
# Idempotent. Kann beliebig oft aufgerufen werden.
#
# DEINSTALLATION:
#   rm ~/.config/autostart/xfwm4.desktop ~/.config/autostart/zentrale.desktop
#   rm ~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml
#   rm ~/.xprofile
#   xfconf-query -c xfce4-keyboard-shortcuts -p '/commands/custom/<Primary><Alt>Escape' -r
# =============================================================================

set -euo pipefail

# Sanity-Check: nicht als root ausfuehren. ~/.config/... gehoert dem User,
# sonst wuerden die XDG-Mechaniken Files spaeter wegen falscher Permissions
# ignorieren.
if [ "$(id -u)" = "0" ]; then
    echo "FEHLER: bitte als normaler User (sasha) ausfuehren, NICHT mit sudo." >&2
    exit 1
fi

AUTOSTART_DIR="$HOME/.config/autostart"
XFCONF_DIR="$HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
mkdir -p "$AUTOSTART_DIR" "$XFCONF_DIR"

# --- xfce4-session: Minimal-Failsafe -----------------------------------------
# Diese Datei steuert was xfce4-session beim Start hochzieht. Default
# (aus /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml) hat
# Panel + xfdesktop + Thunar mit drin — alles sichtbarer UI-Krempel den
# wir nicht wollen. Wir ueberschreiben das per User-Datei mit einer
# Failsafe-Session die nur die zwei Komponenten enthaelt die WIRKLICH
# noetig sind:
#   - xfwm4        (Window-Manager, damit Firefox-Kiosk-Fullscreen sitzt)
#   - xfsettingsd  (Settings-Daemon, kuemmert sich u.a. um xrandr/theme)
# Kein Panel, kein xfdesktop -> Root-Window bleibt schwarz, bis Firefox
# uebernimmt. Genau was wir wollen.
cat > "$XFCONF_DIR/xfce4-session.xml" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>

<channel name="xfce4-session" version="1.0">
  <property name="general" type="empty">
    <property name="FailsafeSessionName" type="string" value="Failsafe"/>
    <property name="SaveOnExit" type="bool" value="false"/>
    <property name="AutoSave" type="bool" value="false"/>
    <property name="PromptOnLogout" type="bool" value="false"/>
  </property>
  <property name="sessions" type="empty">
    <property name="Failsafe" type="empty">
      <property name="IsFailsafe" type="bool" value="true"/>
      <property name="Count" type="int" value="2"/>
      <property name="Client0_Command" type="array">
        <value type="string" value="xfwm4"/>
      </property>
      <property name="Client0_PerScreen" type="bool" value="false"/>
      <property name="Client1_Command" type="array">
        <value type="string" value="xfsettingsd"/>
      </property>
      <property name="Client1_PerScreen" type="bool" value="false"/>
    </property>
  </property>
</channel>
EOF

# --- xfwm4 autostart (Backup) ------------------------------------------------
# Doppelt haelt besser: xfce4-session.xml SOLLTE xfwm4 starten, aber falls
# ein Update mal die Failsafe-Logik aendert, haben wir hier den zweiten
# Trigger. --replace damit ein evtl. anderer WM ersetzt wird.
cat > "$AUTOSTART_DIR/xfwm4.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=xfwm4
Comment=ZENTRALE backup-autostart fuer xfwm4 (falls xfce4-session.xml zickt)
Exec=xfwm4 --replace
OnlyShowIn=XFCE
X-GNOME-Autostart-enabled=true
EOF

# --- xfdesktop: explizit weg -------------------------------------------------
# Frueher haben wir hier ein xfdesktop.desktop angelegt, weil unter dem
# alten vc4-kms-Display-Bug das Root-Window sonst „komplett schwarz" blieb
# (HDMI gab einen leeren Frame raus). Mit fkms-Fix ist das geloest —
# „komplett schwarz" ist sogar das was wir wollen. Also: altes File weg.
rm -f "$AUTOSTART_DIR/xfdesktop.desktop"

# --- ~/.xprofile: HDMI-Mode forcieren ----------------------------------------
# Auf Pi 3 B + Bookworm wird der EDID-preferred Mode des Monitors nicht
# automatisch von fkms uebernommen. Ohne diesen xrandr-Aufruf landen wir
# in 1024x768 statt der nativen Aufloesung des Monitors -> verschobenes
# Bild, evtl. Pixel-Format-Mismatch (pinker Rand).
#
# .xprofile wird beim X-Login vor xfce4-session ausgefuehrt, damit Apps
# direkt in der korrekten Aufloesung spawnen.
cat > "$HOME/.xprofile" << 'EOF'
# Auto-generated by install_xfce_autostart.sh.
# Force HDMI output to the monitor's native 1080p mode (otherwise we
# land in 1024x768 with a shifted/pink image on the kiosk monitor).
xrandr --output HDMI-1 --mode 1920x1080 --rate 60 || true
EOF

# --- zentrale.desktop: Kiosk-Autostart ---------------------------------------
# Waehrend des Display-Debuggings war diese Datei nach .disabled umbenannt
# (siehe display_debug.md). Jetzt schreiben wir sie sauber neu, sodass
# der Pi nach Reboot wirklich direkt im Kiosk landet. Idempotent: alte
# Varianten (auch .disabled) werden geloescht und durch das frische
# File ersetzt.
#
# Der Exec wartet bis der Core auf Port 5000 antwortet, BEVOR Firefox
# startet — sonst sieht der User initial "Connection refused" und muesste
# manuell F5 druecken. Timeout 60s damit der Kiosk auch dann hochkommt
# wenn der Core spinnt; der User sieht dann zwar die Fehlerseite, kann
# aber den Hotkey nutzen statt einen dunklen Bildschirm zu kriegen.
rm -f "$AUTOSTART_DIR/zentrale.desktop.disabled"
cat > "$AUTOSTART_DIR/zentrale.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=ZENTRALE Kiosk
Comment=Firefox auf das ZENTRALE-Dashboard, nach Boot automatisch
Exec=bash -c 'for i in $(seq 1 60); do curl -fs http://localhost:5000/ >/dev/null && break; sleep 1; done; firefox-esr --kiosk http://localhost:5000'
X-GNOME-Autostart-enabled=true
EOF

# --- Notaus-Hotkey Ctrl+Alt+Esc ----------------------------------------------
# Setzt einen Custom-Command-Shortcut im XFCE-Keyboard-Channel. Funktioniert
# nur wenn xfconf-query gegen einen laufenden xfconfd reden kann, d.h.
# wir brauchen DBus-Session. Beim Aufruf aus einer Terminal-Session im
# XFCE-Login ist das gegeben; aus dem Autopull-Cron (kein DISPLAY/DBus)
# nicht — in dem Fall ueberspringen wir den Schritt und melden es.
HOTKEY='/commands/custom/<Primary><Alt>Escape'
HOTKEY_CMD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/emergency_exit.sh"

if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && command -v xfconf-query >/dev/null 2>&1; then
    # Erst alten Wert wegraeumen (falls schon mal gesetzt), dann frisch
    # anlegen. `-n` legt den Pfad an wenn er nicht existiert.
    xfconf-query -c xfce4-keyboard-shortcuts -p "$HOTKEY" -r 2>/dev/null || true
    xfconf-query -c xfce4-keyboard-shortcuts -p "$HOTKEY" -n -t string -s "$HOTKEY_CMD"
    echo "Notaus-Hotkey verdrahtet: Ctrl+Alt+Esc -> $HOTKEY_CMD"
else
    echo
    echo "HINWEIS: Hotkey NICHT gesetzt — DBUS_SESSION_BUS_ADDRESS fehlt"
    echo "         oder xfconf-query nicht installiert. Skript einmal"
    echo "         aus einem Terminal innerhalb der XFCE-Session ausfuehren."
fi

# --- Ausgabe ------------------------------------------------------------------
echo
echo "Installiert:"
ls -la "$XFCONF_DIR/xfce4-session.xml" \
       "$AUTOSTART_DIR/xfwm4.desktop" \
       "$AUTOSTART_DIR/zentrale.desktop"
echo
echo "Test mit:"
echo "  sudo systemctl restart lightdm"
echo "  # nach ~5s sollte Firefox-Kiosk drauf sein, KEIN Panel, KEIN Wallpaper"
echo
echo "Notaus testen (in der laufenden XFCE-Session):"
echo "  Ctrl+Alt+Esc  -> lightdm stoppt, Pi landet auf TTY1"
echo "  sudo systemctl start lightdm   # zurueck zum Kiosk"
