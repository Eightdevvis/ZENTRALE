#!/usr/bin/env bash
# =============================================================================
# install_xfce_autostart.sh
# -----------------------------------------------------------------------------
# Konfiguriert XFCE auf dem Pi als reinen Kiosk: KEIN Wallpaper, KEIN Panel,
# KEINE Desktop-Icons. Nur xfwm4 (Window Manager) + xfsettingsd (xrandr/
# theme-Daemon) laufen — der Kiosk legt sich sofort als einziges Fenster
# vollflaechig drueber.
#
# ZWEI MODI (ZENTRALE_KIOSK_MODE, Default 'tui' seit 2026-06-27):
#   tui     — maximiertes xterm mit der curses-TUI (tui/zentrale_tui.py)
#             gegen das PC-Backend. KEIN Browser. Grund: der Pi 3 (1 GB RAM,
#             schwache VideoCore-IV-GPU) rendert das animierte 1080p-Dashboard
#             nur in Software -> ein CPU-Kern dauerhaft am Anschlag (gemessen
#             firefox-esr ~120 %CPU), sichtbar ruckelige Framerate. Die TUI
#             malt nur geaenderte Terminal-Zellen -> Last quasi null. ACHTUNG:
#             tui-Kassette ist KI-frei (kein Chat/Kino/Reflexion auf der Wand).
#   browser — der alte selbstheilende Firefox-Kiosk (volle KI-Optik / PC-Test).
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
#    dem fkms-Umstieg (siehe memory/betrieb/display_debug.md) wird der EDID-
#    preferred Mode des Pi-Monitors nicht zuverlaessig genommen.
#
# 5. Aktiviert den Kiosk-Autostart (~/.config/autostart/zentrale.desktop):
#    wartet bis ZENTRALE auf Port 5000 antwortet, dann firefox-esr --kiosk.
#
# 6. Verdrahtet den Notaus-Hotkey Ctrl+Alt+Esc auf emergency_exit.sh
#    (lightdm stoppen -> Pi auf TTY1). Klappt nur aus einer aktiven
#    XFCE-Session heraus, weil xfconf-query DBus braucht.
#
# 7. Mikrofon-Berechtigung fuer den Kiosk-Firefox:
#    a) Legt ein dediziertes Kiosk-Profil ~/.zentrale-kiosk-profile/ an
#       und schreibt da eine user.js mit den zwei Insecure-Origin-Prefs
#       (media.devices.insecure.enabled, media.getusermedia.insecure.enabled).
#       Diese muessen ueber user.js gesetzt werden — Mozilla erlaubt sie
#       NICHT ueber die Preferences-Policy. Eigenes Profil statt Default-
#       Profil, damit der Pfad deterministisch ist (Default-Profile heissen
#       <hash>.default-release und werden erst beim ersten Start angelegt).
#    b) Ruft install_firefox_mic_policy.sh per passwordless sudo auf, das
#       schreibt /etc/firefox-esr/policies/policies.json mit der Microphone-
#       Allow-Liste fuer die Kiosk-Origin.
#    Ohne (a) blockt Firefox getUserMedia komplett (insecure context),
#    ohne (b) zeigt es den Permission-Dialog den im Kiosk niemand klicken
#    kann.
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

# ---------------------------------------------------------------------
# Backend-URL fuer den Kiosk.
#
# Seit der Topologie-Migration laeuft das schwere Backend (Flask/AI/
# Whisper/TTS) NICHT mehr auf dem Pi, sondern auf dem PC. Der Pi ist
# nur noch Display-Klient + (kuenftig) Sensor-Bridge. Firefox-Kiosk
# muss deshalb auf den PC zeigen, nicht mehr auf localhost.
#
# Quelle der URL: env-Variable ZENTRALE_BACKEND_URL (z.B.
# "http://192.168.50.1:5000"). Default ist die feste PC-LAN-IP
# (192.168.50.1, siehe memory/system/topologie.md) — denn der Normalfall
# fuer dieses Skript IST der Pi-Kiosk, und der MUSS auf den PC zeigen,
# nicht auf sich selbst.
#
# Historie/Footgun: bis 2026-06-02 war der Default localhost. Wer
# install_xfce_autostart.sh ohne ZENTRALE_BACKEND_URL aufrief (genau so
# stand's in der deploy_pi.sh-Anleitung), bekam einen Kiosk der das
# Backend auf der Pi SELBST suchte -> "unable to connect" den ganzen
# Tag, egal wie gesund der PC war. Default jetzt = LAN-IP, damit der
# Footgun nicht mehr zuschlagen kann.
#   Solo-Test direkt am PC: ZENTRALE_BACKEND_URL=http://localhost:5000 setzen.
#
# Aenderung der IP: Skript neu aufrufen (ggf. mit neuer URL), die alte
# zentrale.desktop wird einfach ueberschrieben.
# ---------------------------------------------------------------------
BACKEND_URL="${ZENTRALE_BACKEND_URL:-http://192.168.50.1:5000}"
echo "Kiosk-Backend-URL: $BACKEND_URL"

# Kiosk-Modus: 'tui' (Default) = maximiertes xterm mit der curses-TUI,
# 'browser' = Firefox-Kiosk. Siehe Kopf-Kommentar. Umschalten z.B.:
#   ZENTRALE_KIOSK_MODE=browser bash install_xfce_autostart.sh
KIOSK_MODE="${ZENTRALE_KIOSK_MODE:-tui}"
# Schriftgroesse der TUI im xterm (Wand-Monitor aus Distanz -> eher gross).
TUI_FONTSIZE="${ZENTRALE_TUI_FONTSIZE:-16}"
echo "Kiosk-Modus: $KIOSK_MODE"

# Dediziertes Firefox-Profil fuer den Kiosk. Liegt unter $HOME, gehoert
# dem User, ist git-unabhaengig (wird hier programmatisch befuellt).
# Default-Profile heissen <hash>.default-release und werden erst beim
# ersten Firefox-Start angelegt — wir wollen aber JETZT eine user.js
# reinkippen koennen. Eigener fester Pfad loest das.
KIOSK_PROFILE_DIR="$HOME/.zentrale-kiosk-profile"
mkdir -p "$KIOSK_PROFILE_DIR"

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

# Bildschirm-Blanking: kein X-Screensaver, Monitor erst nach 20 min
# (1200s) per DPMS aus — statt der X-Defaults (waren 600s = 10 min).
# Das Wand-Dashboard soll lange anbleiben. Spaeter kann der Geraeusch-/
# PIR-Sensor den Schirm per Motion wieder aufwecken (dann ggf. wieder
# kuerzer stellen + Wake-on-Motion verdrahten).
xset s off || true
xset +dpms || true
xset dpms 0 0 1200 || true
EOF

# --- zentrale.desktop: Kiosk-Autostart ---------------------------------------
# Waehrend des Display-Debuggings war diese Datei nach .disabled umbenannt
# (siehe memory/betrieb/display_debug.md). Jetzt schreiben wir sie sauber neu, sodass
# der Pi nach Reboot wirklich direkt im Kiosk landet. Idempotent: alte
# Varianten (auch .disabled) werden geloescht und durch das frische
# File ersetzt.
#
# Der Exec ist eine SELBSTHEILENDE Schleife statt eines Einmal-Starts:
#
#   1. Warten bis der Core auf $BACKEND_URL antwortet (endlos, in 2s-
#      Schritten) BEVOR Firefox startet — sonst Firefox-Fehlerseite,
#      die nie von selbst neu laedt.
#   2. Firefox-Kiosk starten.
#   3. Solange Firefox laeuft, das Backend weiter pollen. Faellt es
#      3x in Folge (~30s) aus — PC im Suspend, Netz-Abriss, Deploy-
#      Restart — Firefox killen, zurueck zu Schritt 1. Sobald das
#      Backend wieder da ist, kommt der Kiosk frisch hoch.
#
# Warum nicht der alte "240s warten, dann EINMAL starten"-Ansatz:
# Die Pi bootet regelmaessig VOR dem PC (PC braucht BIOS + manuelle
# LUKS-Eingabe + Pop-Boot + Warmup). Lief das 240s-Fenster ab bevor
# der PC bereit war, hing Firefox FUER IMMER auf der Fehlerseite —
# genau der Bug vom 2026-06-02. Die Endlos-Schleife kennt kein
# Timeout und erholt sich auch nach spaetem PC-Start oder Suspend.
rm -f "$AUTOSTART_DIR/zentrale.desktop.disabled"

if [ "$KIOSK_MODE" = "tui" ]; then
    # --- TUI-Variante: maximiertes xterm mit der curses-TUI -----------------
    # Kein Browser. xterm (das einzige am Pi vorhandene Terminal), maximiert
    # auf den ganzen Schirm, darin python3 tui/zentrale_tui.py gegen das
    # PC-Backend ($BACKEND_URL).
    #
    # Warum -maximized und NICHT -fullscreen: ein echtes Fullscreen-Fenster
    # liegt bei xfwm4 in einem eigenen Layer GANZ oben — dann oeffnen die
    # Zusatzfenster der TUI (Karte 'w' -> scripts/map_window.py via pygame,
    # /slide-PDFs) DAHINTER und sind unerreichbar. -maximized ist ein ganz
    # normales Fenster auf voller Groesse -> neue Fenster stapeln sich normal
    # drueber und kommen nach vorn. Randlos macht es das xfconf-Setting
    # borderless_maximize weiter unten (sonst klebt eine Titelleiste dran).
    #
    # xterm-Flags:
    #   -u8                erzwingt UTF-8 unabhaengig von der Locale — die TUI
    #                      lebt von Box-/Block-/Braille-Zeichen
    #   -fa Monospace -fs N  TrueType (DejaVu) mit voller Unicode-Abdeckung,
    #                      Groesse aus $TUI_FONTSIZE
    #   -bg black -fg white  ruhiger Wand-Look
    # Im Kind: TERM=xterm-256color (curses braucht's fuer 256 Farben),
    # ZENTRALE_URL zeigt auf den PC. Die TUI ist stdlib-only -> system-python3
    # genuegt, KEIN venv noetig.
    #
    # Selbstheilung: aeussere Endlos-Schleife startet xterm neu, wenn es endet
    # (TUI-Crash oder jemand drueckt 'q'). Backend-weg faengt die TUI selbst ab
    # (Header '[backend ?]', kein Crash) -> keine curl-Warteschleife noetig.
    #
    # Heredoc OHNE Quotes -> $BACKEND_URL/$TUI_FONTSIZE jetzt eingebacken; die
    # Exec-Zeile enthaelt KEINE Runtime-$-Variablen, daher kein Escaping noetig.
    cat > "$AUTOSTART_DIR/zentrale.desktop" << EOF
[Desktop Entry]
Type=Application
Name=ZENTRALE Kiosk (TUI)
Comment=Maximiertes xterm mit der curses-TUI gegen das PC-Backend (KI-frei, browserlos)
Exec=bash -c 'while true; do xterm -maximized -u8 -fa Monospace -fs ${TUI_FONTSIZE} -bg black -fg white -e bash -c "export TERM=xterm-256color; export ZENTRALE_URL=${BACKEND_URL}; cd /opt/zentrale && exec python3 tui/zentrale_tui.py"; sleep 2; done'
X-GNOME-Autostart-enabled=true
EOF
    echo "Kiosk-Autostart (TUI, maximiertes xterm) geschrieben."
else
    # --- Browser-Variante: Firefox-Kiosk (selbstheilende Schleife) ----------
    # Heredoc OHNE Quotes -> $BACKEND_URL und $KIOSK_PROFILE_DIR werden JETZT
    # (zur Install-Zeit) eingebacken. Die Runtime-Variablen der Schleife
    # ($U, $P, $F, $n) muessen LITERAL ins File -> mit \$ escaped.
    # --profile <dir>: dediziertes Kiosk-Profil mit der user.js (Mic-Insecure-
    # Prefs). --no-remote: garantiert Start mit dem Kiosk-Profil.
    cat > "$AUTOSTART_DIR/zentrale.desktop" << EOF
[Desktop Entry]
Type=Application
Name=ZENTRALE Kiosk
Comment=Firefox auf das ZENTRALE-Dashboard, selbstheilend (wartet aufs Backend, laedt bei Abriss neu)
Exec=bash -c 'U=${BACKEND_URL}; P=${KIOSK_PROFILE_DIR}; while true; do until curl -fs "\$U/" >/dev/null 2>&1; do sleep 2; done; firefox-esr --no-remote --profile "\$P" --kiosk "\$U" & F=\$!; n=0; while kill -0 \$F 2>/dev/null; do if curl -fs "\$U/" >/dev/null 2>&1; then n=0; else n=\$((n+1)); [ \$n -ge 3 ] && { kill \$F 2>/dev/null; break; }; fi; sleep 10; done; sleep 2; done'
X-GNOME-Autostart-enabled=true
EOF
    echo "Kiosk-Autostart (Browser/Firefox) geschrieben."
fi

# --- Browser-Only: Mikrofon ueber HTTP (Profil-user.js + Policy) -------------
# Beides ergibt nur im Browser-Modus Sinn (im tui-Modus laeuft kein Firefox).
if [ "$KIOSK_MODE" = "browser" ]; then

# --- Kiosk-Profil: user.js fuer Mikrofon ueber HTTP -------------------------
# Firefox blockt navigator.mediaDevices.getUserMedia() per default komplett,
# wenn die Origin nicht "secure" ist (HTTPS oder localhost). Unser Kiosk
# laedt das PC-Backend ueber http://192.168.50.1:5000 — das ist eine
# "insecure" origin, ohne diesen Override gibt's also nichtmal einen
# Permission-Dialog, getUserMedia() lehnt sofort ab.
#
# Beide Prefs sind noetig:
# - media.devices.insecure.enabled: laesst enumerateDevices() ueber http
#   ueberhaupt das Mic-Device sehen.
# - media.getusermedia.insecure.enabled: laesst getUserMedia() ueber http
#   den Stream tatsaechlich oeffnen.
#
# Diese Prefs sind NICHT in der Whitelist der Preferences-Policy von
# Firefox-ESR (Mozilla erlaubt da nur bestimmte Praefixe wie browser.*,
# dom.*, network.*, ...). Deshalb nicht via policies.json, sondern hier
# als user.js im dedizierten Kiosk-Profil. policies.json kuemmert sich
# stattdessen um die Microphone-Allow-Liste (siehe naechster Abschnitt).
cat > "$KIOSK_PROFILE_DIR/user.js" << 'EOF'
// Auto-generated by install_xfce_autostart.sh.
// Erlaubt navigator.mediaDevices.getUserMedia() ueber HTTP-Origins
// (Kiosk laedt das Backend von der PC-LAN-IP, kein HTTPS).
// Permission-Whitelist fuer die konkrete Origin steht in
// /etc/firefox-esr/policies/policies.json (install_firefox_mic_policy.sh).
user_pref("media.devices.insecure.enabled", true);
user_pref("media.getusermedia.insecure.enabled", true);
EOF
echo "Kiosk-Profil + user.js: $KIOSK_PROFILE_DIR"

# --- Mikrofon-Permission systemweit ueber policies.json ---------------------
# Schreibt /etc/firefox-esr/policies/policies.json mit der Microphone-Allow-
# Liste. Braucht root, daher per passwordless sudo (siehe
# install_pi_sudoers.sh). Wenn der sudoers-Eintrag noch fehlt (erster
# Setup-Run, Reihenfolge stimmt nicht), kommt eine laute Warnung — aber
# das Skript bricht nicht ab, damit die anderen Schritte trotzdem
# durchlaufen.
MIC_POLICY_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install_firefox_mic_policy.sh"
if [ -x "$MIC_POLICY_SCRIPT" ]; then
    if sudo -n bash "$MIC_POLICY_SCRIPT" 2>/dev/null; then
        echo "Mikrofon-Policy via $MIC_POLICY_SCRIPT installiert."
    else
        echo
        echo "WARNUNG: Mikrofon-Policy NICHT installiert."
        echo "         Vermutlich fehlt der passwordless-sudo-Eintrag fuer"
        echo "         install_firefox_mic_policy.sh. Reihenfolge:"
        echo "           1) sudo bash $(dirname "$MIC_POLICY_SCRIPT")/install_pi_sudoers.sh"
        echo "           2) bash $0   # nochmal aufrufen"
    fi
else
    echo "WARNUNG: $MIC_POLICY_SCRIPT nicht ausfuehrbar — Mic-Policy uebersprungen."
fi

fi  # Ende Browser-Only (Mic-Profil + Policy)

# --- Hotkeys: Notaus + xterm-Toggle ------------------------------------------
# Setzt Custom-Command-Shortcuts im XFCE-Keyboard-Channel:
#
#   Ctrl+Alt+Esc  -> emergency_exit.sh (stoppt lightdm, Pi auf TTY1)
#   Ctrl+Alt+T    -> xterm (floating ueber Firefox-Kiosk, schliessen
#                    bringt einen zurueck in den Kiosk)
#
# xfconf-query braucht DBus-Session. Wenn DBUS_SESSION_BUS_ADDRESS nicht
# gesetzt ist (z.B. via SSH ohne X-Forwarding), versuchen wir die Session-
# Bus-Adresse aus /run/user/<uid>/bus zu raten — das funktioniert auf
# Debian/Bookworm + systemd-User-Sessions zuverlaessig.

if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    if [ -S "/run/user/$(id -u)/bus" ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
        echo "DBUS_SESSION_BUS_ADDRESS aus /run/user/$(id -u)/bus uebernommen"
    fi
fi

if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] && command -v xfconf-query >/dev/null 2>&1; then
    # Randlos beim Maximieren — nur im tui-Modus relevant (das Kiosk-xterm
    # laeuft maximiert; ohne das klebt eine Titelleiste am Wand-Bild). -n -t
    # legt die Property an, falls noch nicht vorhanden; sonst nur -s.
    if [ "$KIOSK_MODE" = "tui" ]; then
        xfconf-query -c xfwm4 -p /general/borderless_maximize -n -t bool -s true 2>/dev/null \
            || xfconf-query -c xfwm4 -p /general/borderless_maximize -s true || true
        echo "xfwm4: borderless_maximize = true (randloses Maximieren)"
    fi

    # Notaus
    EMERG_HOTKEY='/commands/custom/<Primary><Alt>Escape'
    EMERG_CMD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/emergency_exit.sh"
    xfconf-query -c xfce4-keyboard-shortcuts -p "$EMERG_HOTKEY" -r 2>/dev/null || true
    xfconf-query -c xfce4-keyboard-shortcuts -p "$EMERG_HOTKEY" -n -t string -s "$EMERG_CMD"
    echo "Notaus-Hotkey verdrahtet: Ctrl+Alt+Esc -> $EMERG_CMD"

    # xterm-Toggle. -fa/-fs setzt eine lesbare Schrift (Standard-xterm
    # ist tiny). -bg/-fg dunkles Theme, damit's am Wand-Monitor nicht
    # blendet. xfwm4 macht das Fenster floating, der Kiosk bleibt
    # darunter sichtbar — Schliessen via Ctrl+D oder Window-Close.
    TERM_HOTKEY='/commands/custom/<Primary><Alt>t'
    TERM_CMD='xterm -fa Monospace -fs 13 -bg black -fg white -title "ZENTRALE Pi terminal"'
    xfconf-query -c xfce4-keyboard-shortcuts -p "$TERM_HOTKEY" -r 2>/dev/null || true
    xfconf-query -c xfce4-keyboard-shortcuts -p "$TERM_HOTKEY" -n -t string -s "$TERM_CMD"
    echo "xterm-Hotkey verdrahtet: Ctrl+Alt+T -> $TERM_CMD"
else
    echo
    echo "HINWEIS: Hotkeys NICHT gesetzt — DBUS-Session nicht erreichbar"
    echo "         und auch nicht ueber /run/user/<uid>/bus aufzubauen."
fi

# --- Ausgabe ------------------------------------------------------------------
echo
echo "Installiert:"
INSTALLED_FILES=("$XFCONF_DIR/xfce4-session.xml" "$AUTOSTART_DIR/xfwm4.desktop" "$AUTOSTART_DIR/zentrale.desktop")
if [ "$KIOSK_MODE" = "browser" ]; then INSTALLED_FILES+=("$KIOSK_PROFILE_DIR/user.js"); fi
ls -la "${INSTALLED_FILES[@]}"
echo
echo "Test mit:"
echo "  sudo systemctl restart lightdm"
if [ "$KIOSK_MODE" = "tui" ]; then
    echo "  # nach ~5s sollte das maximierte TUI-xterm drauf sein, KEIN Panel/Titelleiste"
else
    echo "  # nach ~5s sollte Firefox-Kiosk drauf sein, KEIN Panel, KEIN Wallpaper"
fi
echo
echo "Notaus testen (in der laufenden XFCE-Session):"
echo "  Ctrl+Alt+Esc  -> lightdm stoppt, Pi landet auf TTY1"
echo "  sudo systemctl start lightdm   # zurueck zum Kiosk"
