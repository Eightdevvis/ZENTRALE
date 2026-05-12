#!/usr/bin/env bash
# =============================================================================
# display_debug.sh
# -----------------------------------------------------------------------------
# Display-Debug-Snapshot fuer den ZENTRALE-Pi (Pi 3 B, Bookworm, KMS/vc4).
#
# WARUM ES DAS GIBT:
# Beim Hochfahren der Kiosk-Session (lightdm -> XFCE -> Firefox-Kiosk) wird
# der HDMI-Monitor schwarz. KMS liefert vor X-Start einen sichtbaren
# 1920x1080-Framebuffer (Boot-Rainbow, Konsole), aber sobald X uebernimmt,
# greift der modesetting-Treiber zu einem ungewoehnlichen 1024x768@99.97Hz-
# Mode, den der HDMI-Encoder oder der Monitor nicht sauber ausgibt.
# Nach X-Stop bleibt der Encoder im broken state -> Konsole bleibt schwarz,
# erst ein Reboot setzt zurueck. Siehe memory/display_debug.md.
#
# WAS DAS SKRIPT MACHT:
# Schreibt einen vollstaendigen Snapshot des Display-States in eine
# Log-Datei. Wird per lightdm-Hook (display-setup-script) automatisch bei
# jedem X-Start aufgerufen, kann aber auch manuell mit einem freien Label
# aufgerufen werden:
#
#   ./display_debug.sh                  # Label "manual"
#   ./display_debug.sh vor_xrandr_fix   # Label "vor_xrandr_fix"
#
# IM AUTO-MODUS (Aufruf-Argument "autostart") werden DREI Snapshots gemacht:
#   * T+0s  - direkt vom display-setup-script ausgeloest (X gerade hoch)
#   * T+5s  - X hat den Mode gesetzt, Greeter / Auto-Login durch
#   * T+15s - falls etwas spaeter umschaltet (Compositor, Kiosk-Firefox)
#
# AUSGABE:
# Alle Snapshots gehen in $LOG_FILE (Default: /home/sasha/zentrale-display-debug.log).
# Wenn das Skript als root via lightdm laeuft, wird das Logfile am Ende auf
# sasha:sasha zurueckchowned, damit man es per SSH ohne sudo lesen kann.
# =============================================================================

# Bewusst KEIN `set -e`: wenn ein einzelner Diagnose-Befehl (xrandr ohne X,
# vcgencmd-Subkommando das auf neuerem Bookworm leer kommt) fehlschlaegt,
# soll der Rest des Snapshots trotzdem durchlaufen. Wir wollen sehen WAS
# fehlt, nicht nach dem ersten Stolperer abbrechen.
set -uo pipefail

# -----------------------------------------------------------------------------
# Konfiguration
# -----------------------------------------------------------------------------

# Ziel-Logfile. Bewusst HARTCODIERT auf sasha-Home (statt $HOME), damit
# root-Aufrufe via lightdm beim selben File landen wie manuelle Aufrufe.
LOG_FILE="${LOG_FILE:-/home/sasha/zentrale-display-debug.log}"

# Mogliche Xauthority-Pfade. Vor User-Login legt lightdm den Greeter-Auth
# unter /var/run/lightdm/root/:0 ab. Nach Auto-Login wechselt der Auth zu
# ~sasha/.Xauthority. Wir probieren beide, damit xrandr in jeder Phase
# einen passenden Token findet.
LIGHTDM_AUTH="/var/run/lightdm/root/:0"
USER_AUTH="/home/sasha/.Xauthority"

# Erstes Argument = Label. Default "manual" fuer SSH-Aufruf ohne Argument.
LABEL="${1:-manual}"

# -----------------------------------------------------------------------------
# Helfer
# -----------------------------------------------------------------------------

# Eine Zeile ins Log schreiben. Kein echo auf stdout - der Auto-Aufruf
# ueber lightdm hat sowieso kein Terminal, und manuell laesst sich der
# Output mit `tail -f` verfolgen.
log() {
    echo "$@" >> "$LOG_FILE"
}

# Sektion-Header mit Trennzeile davor.
section() {
    log ""
    log "--- $1 ---"
}

# Datei in den Log spiegeln, mit zwei Spaces Einrueckung damit die Sektion
# optisch geschlossen wirkt. Wenn die Datei fehlt: einen Hinweis loggen.
dump_file() {
    local path="$1"
    if [ -r "$path" ]; then
        sed 's/^/  /' "$path" >> "$LOG_FILE"
    else
        log "  (nicht lesbar: $path)"
    fi
}

# Kommando ausfuehren, Output mit zwei Spaces einruecken. stderr wird
# mit reingezogen, weil viele Diagnose-Tools Errors auf stderr werfen
# und genau die wollen wir sehen.
dump_cmd() {
    "$@" 2>&1 | sed 's/^/  /' >> "$LOG_FILE"
}

# Einen vollstaendigen Snapshot aufnehmen. Argument: sublabel (z.B.
# "T+0_xstart", "manual", "_autostart_T5") - landet im Snapshot-Header.
snapshot() {
    local sublabel="$1"

    # Snapshot-Header mit Zeitstempel. Wir benutzen `date` statt $EPOCHSECONDS
    # damit man's beim Lesen ohne Konvertierung versteht.
    log ""
    log "============================================================"
    log "[$(date '+%Y-%m-%d %H:%M:%S')] LABEL=$LABEL SUB=$sublabel"
    log "============================================================"

    # --- Systemd / X-Prozess ---------------------------------------------
    # Wer ist gerade aktiv? lightdm-Status + Xorg-Prozessliste. Der
    # Xorg-Prozess hat die spannenden Argumente in der Command-Line
    # (welche VT, welcher Auth-Pfad, -nolisten etc.), darum -af.
    section "Systemd / X-Prozess"
    log "lightdm: $(systemctl is-active lightdm 2>/dev/null) ($(systemctl is-enabled lightdm 2>/dev/null))"
    log "zentrale: $(systemctl is-active zentrale 2>/dev/null) ($(systemctl is-enabled zentrale 2>/dev/null))"
    log "X-Prozess(e):"
    if pgrep -af "Xorg|xinit" >/dev/null 2>&1; then
        pgrep -af "Xorg|xinit" 2>/dev/null | sed 's/^/  /' >> "$LOG_FILE"
    else
        log "  (kein X)"
    fi

    # --- KMS Connector-State (unabhaengig von X) -------------------------
    # Das ist die Wahrheit der Kernel-Seite: was sieht KMS am HDMI-Port?
    # "status" sagt connected/disconnected, "enabled" ob der Connector
    # aktiv geschaltet ist, "modes" listet die KMS-bekannten Modi
    # (preferred zuerst).
    section "DRM/KMS Connector-State (sysfs)"
    for f in status enabled modes; do
        log "card0-HDMI-A-1/$f:"
        dump_file "/sys/class/drm/card0-HDMI-A-1/$f"
    done

    # --- Framebuffer -----------------------------------------------------
    # fbset -i zeigt was die DRM-FB-Schicht aktuell als Mode haelt. Das
    # ist der "Console-Mode" und genau der wechselt nach X-Stop nicht
    # zurueck auf 1920x1080 (Encoder-Hang).
    section "Framebuffer (fbset -i)"
    dump_cmd fbset -i

    # --- Pi-Firmware-View ueber vcgencmd ---------------------------------
    # Pi-spezifische Tools die nochmal eine andere Sicht haben. Auf
    # neuerem Bookworm liefern einige davon nur noch Stubs, aber
    # display_power=1/0 und get_throttled bleiben relevant (Encoder an,
    # Stromversorgung clean).
    section "vcgencmd (Pi-Firmware)"
    for cmd in display_power get_lcd_info hdmi_status_show "get_mem gpu" measure_temp get_throttled; do
        log "  vcgencmd $cmd: $(vcgencmd $cmd 2>&1)"
    done

    # --- X-Display Snapshot ----------------------------------------------
    # Wenn X laeuft: xrandr und xset q. Wir probieren beide moeglichen
    # Xauthorities, weil sich der Pfad nach Auto-Login aendert. xrandr
    # ohne --verbose, sonst wird das Log zu lang - wenn man die EDID
    # braucht, manuell `--verbose` aufrufen.
    section "X-Display (xrandr / xset)"
    if pgrep -x Xorg >/dev/null 2>&1; then
        if [ -r "$LIGHTDM_AUTH" ]; then
            log "[via lightdm-auth $LIGHTDM_AUTH]"
            DISPLAY=:0 XAUTHORITY="$LIGHTDM_AUTH" xrandr 2>&1 | sed 's/^/  /' >> "$LOG_FILE"
        fi
        if [ -r "$USER_AUTH" ]; then
            log "[via user-auth $USER_AUTH]"
            DISPLAY=:0 XAUTHORITY="$USER_AUTH" xrandr 2>&1 | sed 's/^/  /' >> "$LOG_FILE"
            log "[xset q]"
            DISPLAY=:0 XAUTHORITY="$USER_AUTH" xset q 2>&1 | sed 's/^/  /' >> "$LOG_FILE"
        fi
    else
        log "  (kein Xorg-Prozess - X-Snapshot nicht verfuegbar)"
    fi

    # --- dmesg-Tail ------------------------------------------------------
    # Nur die letzten ~30 drm/hdmi/vc4-Zeilen. Wenn KMS waehrend des
    # X-Mode-Switches einen Encoder-Fehler wirft, taucht der hier auf.
    section "dmesg (drm/hdmi/vc4, letzte 30 Zeilen)"
    dmesg 2>/dev/null | grep -iE "drm|hdmi|v3d|vc4" | tail -30 | sed 's/^/  /' >> "$LOG_FILE"

    # --- Xorg.0.log Fehler/Warnungen -------------------------------------
    # Letzte 30 (EE)/(WW)/modesetting/vc4/kms-Zeilen. Wenn der X-Mode-
    # Switch eine Fehlermeldung erzeugt, ist sie hier.
    section "Xorg.0.log (EE/WW/modesetting/vc4/kms - letzte 30)"
    if [ -r /var/log/Xorg.0.log ]; then
        grep -iE "\(EE\)|\(WW\)|modesetting|vc4|kms" /var/log/Xorg.0.log 2>/dev/null \
            | tail -30 | sed 's/^/  /' >> "$LOG_FILE"
    else
        log "  (kein Xorg.0.log)"
    fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

# Logfile vorsichtshalber anlegen (touch ist idempotent). Sonst koennte
# der erste Aufruf failen, wenn der Pfad noch nicht existiert.
touch "$LOG_FILE"

# Modus-Switch:
#   autostart -> drei Snapshots T+0/T+5s/T+15s (vom lightdm-Hook)
#   alles andere -> ein einzelner Snapshot mit diesem Label
#
# Die Background-Sleeps werden mit `(...) &` abgesetzt und ueberleben
# das Skript-Ende. Wichtig damit lightdm den display-setup-script nicht
# 15 Sekunden lang blockiert (dann wuerde der Greeter haengen).
case "$LABEL" in
    autostart)
        snapshot "T+0_xstart"
        # Recursive selbst-Aufrufe im Hintergrund. Andere Labels, damit
        # die nicht erneut in den autostart-Branch laufen.
        ( sleep 5  && LOG_FILE="$LOG_FILE" "$0" "_autostart_T5"  ) &
        ( sleep 15 && LOG_FILE="$LOG_FILE" "$0" "_autostart_T15" ) &
        ;;
    *)
        snapshot "$LABEL"
        ;;
esac

# Wenn als root aufgerufen (lightdm-Hook), File-Owner auf sasha zurueck-
# setzen damit der User es per SSH ohne sudo lesen kann. || true weil
# auf einem anderen Setup ohne sasha-User der Fehler nicht stoeren soll.
if [ "$(id -u)" = "0" ]; then
    chown sasha:sasha "$LOG_FILE" 2>/dev/null || true
fi
