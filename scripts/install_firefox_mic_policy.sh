#!/usr/bin/env bash
# =============================================================================
# install_firefox_mic_policy.sh
# -----------------------------------------------------------------------------
# Schreibt /etc/firefox-esr/policies/policies.json, sodass der Kiosk-Firefox
# ohne Permission-Dialog auf das Mikrofon zugreifen darf.
#
# WARUM EIGENES SKRIPT (und nicht ein cp aus deploy/):
# - Idempotenz: das File wird bei jedem Aufruf neu geschrieben, also bleibt
#   die Wahrheit im Repo (hier inline), nicht in einer manuell editierten
#   /etc-Datei die niemand mehr nachvollziehen kann.
# - Single-Source: die erlaubte Origin steht hier als ENV-Variable
#   (KIOSK_ORIGIN), default ist die feste LAN-IP des PC laut
#   memory/system/topologie.md. Wenn die IP sich aendert, hier einen Wert ueberschreiben
#   und neu aufrufen.
#
# WAS DAS NICHT MACHT:
# Die zwei Prefs `media.devices.insecure.enabled` und
# `media.getusermedia.insecure.enabled` werden NICHT hier gesetzt. Grund:
# diese Prefs sind nicht in der Whitelist der `Preferences`-Policy von
# Firefox-ESR (Mozilla erlaubt per Policy nur bestimmte Pref-Praefixe).
# Sie werden stattdessen ueber das Kiosk-Profil per user.js gesetzt
# (siehe install_xfce_autostart.sh, Abschnitt "Kiosk-Profil + user.js").
#
# AUFRUF (auf dem Pi):
#   sudo bash /opt/zentrale/scripts/install_firefox_mic_policy.sh
#   # oder mit anderer Origin:
#   sudo KIOSK_ORIGIN=http://192.168.50.1:5000 bash .../install_firefox_mic_policy.sh
#
# Wird automatisch vom install_xfce_autostart.sh via passwordless sudo
# (siehe install_pi_sudoers.sh) aufgerufen.
# =============================================================================

set -euo pipefail

# Muss als root laufen — wir schreiben unter /etc/firefox-esr/.
if [ "$(id -u)" -ne 0 ]; then
    echo "FEHLER: bitte mit sudo ausfuehren." >&2
    exit 1
fi

# Die erlaubte Origin. Default ist die feste LAN-IP des PC-Backends
# (memory/system/topologie.md, project_lan_migration_2026_05_19). Format: scheme://host:port,
# ohne trailing slash — Firefox matcht exakt auf diese Origin.
KIOSK_ORIGIN="${KIOSK_ORIGIN:-http://192.168.50.1:5000}"

POLICY_DIR="/etc/firefox-esr/policies"
POLICY_FILE="$POLICY_DIR/policies.json"

mkdir -p "$POLICY_DIR"

# Heredoc OHNE Quotes, damit $KIOSK_ORIGIN expandiert wird.
# BlockNewRequests=true: Firefox wird ueberhaupt KEINE weiteren
# Microphone-Permission-Dialoge zeigen, alles ausser der Allow-Liste
# ist implizit verboten. Im Kiosk wo wir keinen Mauszeiger haben
# und keinen Doorhanger-Click ausloesen koennen ist das genau richtig.
cat > "$POLICY_FILE" <<EOF
{
  "policies": {
    "Permissions": {
      "Microphone": {
        "Allow": ["${KIOSK_ORIGIN}"],
        "BlockNewRequests": true
      }
    }
  }
}
EOF

chmod 644 "$POLICY_FILE"

echo "OK: $POLICY_FILE geschrieben."
echo "    Microphone.Allow = [\"$KIOSK_ORIGIN\"]"
echo
echo "Firefox-Kiosk neu starten damit die Policy greift:"
echo "  sudo systemctl restart lightdm"
