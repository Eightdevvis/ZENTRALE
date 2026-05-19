#!/usr/bin/env bash
# =============================================================================
# wake_pc.sh
# -----------------------------------------------------------------------------
# Schickt vom Pi ein Wake-on-LAN-Magic-Packet an den ZENTRALE-PC, damit
# der aus S5 (soft-off) hochfaehrt. Gedacht als Baustein fuer
# „Pi merkt User kommt heim → PC bootet → ZENTRALE startet via systemd".
#
# Verwendet das Debian-Paket `wakeonlan` (perl-skript, sendet UDP/9-
# Broadcast mit 6x 0xFF + 16x MAC). Alternativen waeren etherwake oder
# direkt python.
#
# Idempotent: prueft erst ob das ZENTRALE-Dashboard schon antwortet,
# bevor das Paket geschickt wird. Mehrfach hintereinander aufrufen
# schadet nichts.
#
# AUFRUF (auf dem Pi):
#   bash /opt/zentrale/scripts/wake_pc.sh
#
# Konfig per Env-Variablen ueberschreibbar:
#   PC_MAC          — Ziel-MAC (default: eth-MAC vom aktuellen PC)
#   LAN_BROADCAST   — Broadcast-Adresse im LAN-Subnetz
#   PROBE_URL       — was zum Erreichbarkeits-Check abgefragt wird
# =============================================================================

set -u

PC_MAC="${PC_MAC:-a8:a1:59:ab:c0:02}"
LAN_BROADCAST="${LAN_BROADCAST:-192.168.50.255}"
PROBE_URL="${PROBE_URL:-http://192.168.50.1:5000/}"

# Schon erreichbar? Dann nichts tun. Schneller Check mit 2s Timeout —
# wenn der PC up ist, antwortet Flask in <50 ms.
if curl -fsS -o /dev/null --max-time 2 "$PROBE_URL"; then
    echo "PC ist schon erreichbar ($PROBE_URL), nichts zu tun."
    exit 0
fi

# wakeonlan vorhanden?
if ! command -v wakeonlan >/dev/null 2>&1; then
    echo "FEHLER: 'wakeonlan' nicht installiert. Bitte 'sudo apt install -y wakeonlan'." >&2
    exit 1
fi

echo "Sende Magic-Packet an $PC_MAC (Broadcast $LAN_BROADCAST) ..."
wakeonlan -i "$LAN_BROADCAST" "$PC_MAC"

# Optional: kurz pollen ob er hochkommt. Wir warten bis zu 90s
# (typischer PC-Boot + systemd-Service-Start liegt darunter), brechen
# beim ersten erfolgreichen HTTP-Response ab.
echo -n "Warte auf ZENTRALE"
for i in $(seq 1 90); do
    if curl -fsS -o /dev/null --max-time 1 "$PROBE_URL"; then
        echo
        echo "PC ist nach ${i}s da, ZENTRALE antwortet."
        exit 0
    fi
    echo -n "."
    sleep 1
done
echo
echo "WARNUNG: nach 90s keine Antwort von $PROBE_URL. BIOS-WoL aktiv?" >&2
exit 2
