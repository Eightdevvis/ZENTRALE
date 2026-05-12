#!/usr/bin/env bash
# =============================================================================
# install_pi_services.sh
# -----------------------------------------------------------------------------
# Synchronisiert ALLE Root-Level-Konfigurationen die der ZENTRALE-Pi-Kiosk
# braucht:
#
#  1. systemd-Units: zentrale.service + whisper.service + tts.service
#     aus deploy/*.service nach /etc/systemd/system/. Patcht dabei User=
#     auf den aktuellen Pi-User.
#  2. lightdm-Drop-in: deploy/lightdm-zentrale.conf nach
#     /etc/lightdm/lightdm.conf.d/10-zentrale.conf. Setzt aktuell
#     "xserver-command=X -nocursor" (kein Maus-Cursor weil keine Maus).
#
# Hinten dran: daemon-reload + enable der Units. Kein restart — das
# uebernimmt der Aufrufer (pi_autopull tut das ohnehin im letzten Schritt).
# lightdm wird auch nicht restartet, weil das die aktive Kiosk-Session
# zerschiessen wuerde; die neue lightdm-Config greift beim naechsten Boot.
#
# WANN AUFGERUFEN:
# 1. Vom autopull-Cron (pi_autopull.sh) wenn sich eine *.service- oder
#    lightdm-*.conf-Datei im Repo geaendert hat — das passiert via
#    passwordless sudo, daher muss der Pfad zu diesem Skript in
#    /etc/sudoers.d/zentrale stehen (install_pi_sudoers.sh erledigt das).
# 2. Manuell beim Erst-Rollout:
#       sudo bash /opt/zentrale/scripts/install_pi_services.sh
# =============================================================================

set -euo pipefail

# Muss als root laufen — wir schreiben in /etc/systemd/system/.
if [ "$(id -u)" -ne 0 ]; then
    echo "FEHLER: bitte mit sudo ausfuehren." >&2
    exit 1
fi

# Service-User aus SUDO_USER (vom sudo gesetzt). Fallback 'pi' wenn
# das Skript wirklich aus einer root-Shell ohne sudo aufgerufen wurde,
# damit die Units nicht mit kaputtem User=root landen.
TARGET_USER="${SUDO_USER:-pi}"
if [ "$TARGET_USER" = "root" ]; then
    TARGET_USER="pi"
fi

# Wo das Repo liegt. Default matched deploy_pi.sh + pi_autopull.sh.
REPO_DIR="${REPO_DIR:-/opt/zentrale}"

# Reihenfolge: zentrale zuerst, weil whisper/tts ein After=zentrale.service
# haben — daemon-reload sortiert das hinterher selbst, aber enable einzeln
# liest klarer.
SERVICES=(zentrale.service whisper.service tts.service)

for SVC in "${SERVICES[@]}"; do
    SRC="$REPO_DIR/deploy/$SVC"
    DST="/etc/systemd/system/$SVC"

    if [ ! -f "$SRC" ]; then
        echo "WARN: $SRC fehlt, ueberspringe $SVC" >&2
        continue
    fi

    # Template hat "User=pi" als Platzhalter — durch echten User ersetzen.
    # Schreiben in /etc/systemd direkt, daemon-reload faengt das auf.
    sed "s|^User=.*$|User=$TARGET_USER|" "$SRC" > "$DST"
    chmod 644 "$DST"
    echo "installed: $DST (User=$TARGET_USER)"
done

systemctl daemon-reload

for SVC in "${SERVICES[@]}"; do
    systemctl enable "$SVC" >/dev/null
done

# --- lightdm-Drop-in ---------------------------------------------------------
# Wir verfrachten deploy/lightdm-zentrale.conf nach
# /etc/lightdm/lightdm.conf.d/10-zentrale.conf. Default-lightdm laedt
# alles in lightdm.conf.d/ alphabetisch — der 10er-Prefix laesst uns
# spaeter ggf. weitere Drop-Ins davor/dahinter einsortieren.
#
# Restart von lightdm machen wir BEWUSST NICHT: das wuerde mitten in der
# laufenden Kiosk-Session alles wegreissen. Die neue Config greift beim
# naechsten Boot — bzw. wenn der User absichtlich emergency_exit fuert
# und lightdm wieder hochfaehrt.
LIGHTDM_SRC="$REPO_DIR/deploy/lightdm-zentrale.conf"
LIGHTDM_DST="/etc/lightdm/lightdm.conf.d/10-zentrale.conf"

if [ -f "$LIGHTDM_SRC" ]; then
    mkdir -p "$(dirname "$LIGHTDM_DST")"
    install -m 644 "$LIGHTDM_SRC" "$LIGHTDM_DST"
    echo "installed: $LIGHTDM_DST"
else
    echo "WARN: $LIGHTDM_SRC fehlt, ueberspringe lightdm-Drop-in" >&2
fi

echo "OK: Units + lightdm-Config synchronisiert. Restart bleibt dem Aufrufer ueberlassen."
