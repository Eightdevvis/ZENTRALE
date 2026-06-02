#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <pi-user@pi-host> <remote-dir>"
  echo "Example: $0 pi@192.168.1.44 /opt/zentrale"
  exit 1
fi

TARGET="$1"
REMOTE_DIR="$2"

# Alle drei systemd-Units die wir auf dem Pi pflegen. zentrale.service
# ist der Core (Event-Loop + Flask), whisper/tts sind die Audio-Services
# mit Low-Prio-Scheduling. Reihenfolge ist relevant fuer den restart
# am Ende — Core zuerst.
SERVICES=("zentrale.service" "whisper.service" "tts.service")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "[1/6] Sync project to $TARGET:$REMOTE_DIR"
rsync -az --delete \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude '.venv' \
  "$PROJECT_ROOT/" "$TARGET:$REMOTE_DIR/"

echo "[2/6] Ensure Python venv exists"
ssh "$TARGET" "python3 -m venv '$REMOTE_DIR/.venv'"

echo "[3/6] Upgrade pip"
ssh "$TARGET" "'$REMOTE_DIR/.venv/bin/pip' install --upgrade pip"

echo "[4/6] Install requirements if present"
ssh "$TARGET" "if [[ -f '$REMOTE_DIR/requirements.txt' ]]; then '$REMOTE_DIR/.venv/bin/pip' install -r '$REMOTE_DIR/requirements.txt'; fi"

echo "[5/6] Install/refresh systemd services"
# User-Name fuer die Unit-Files aus dem SSH-Target ableiten. Die Templates
# in deploy/*.service haben Platzhalter "User=pi" — den ersetzen wir on-the-fly.
SERVICE_USER="${TARGET%@*}"

for SVC in "${SERVICES[@]}"; do
  echo "  -> $SVC (User=$SERVICE_USER)"
  TMP_SERVICE="$(mktemp)"
  sed "s|^User=.*$|User=$SERVICE_USER|" "$PROJECT_ROOT/deploy/$SVC" > "$TMP_SERVICE"
  scp -q "$TMP_SERVICE" "$TARGET:/tmp/$SVC"
  rm -f "$TMP_SERVICE"
  ssh "$TARGET" "sudo mv '/tmp/$SVC' '/etc/systemd/system/$SVC'"
done

# daemon-reload nur einmal nach allen Files — sonst dreimal das Gleiche.
ssh "$TARGET" "sudo systemctl daemon-reload"
for SVC in "${SERVICES[@]}"; do
  ssh "$TARGET" "sudo systemctl enable '$SVC'"
done

echo "[6/6] Restart services + status"
# Core zuerst (whisper/tts haben After=zentrale.service) damit beim
# Restart die Reihenfolge dem Boot-Verhalten entspricht.
for SVC in "${SERVICES[@]}"; do
  ssh "$TARGET" "sudo systemctl restart '$SVC' || true"
done
ssh "$TARGET" "sudo systemctl --no-pager --full status ${SERVICES[*]} || true"

echo
echo "Deploy complete. Tail logs with:"
echo "  ssh $TARGET \"sudo journalctl -u zentrale.service -f\""
echo "  ssh $TARGET \"sudo journalctl -u whisper.service -u tts.service -f\""
echo
echo "Einmalig auf dem Pi noch erledigen (falls noch nicht):"
echo "  ssh $TARGET 'sudo bash $REMOTE_DIR/scripts/install_pi_sudoers.sh'  # Notaus + autopull sudo"
echo "  ssh $TARGET 'ZENTRALE_BACKEND_URL=http://192.168.50.1:5000 bash $REMOTE_DIR/scripts/install_xfce_autostart.sh'   # Kiosk + Hotkey (URL = PC-LAN-IP, sonst localhost-Footgun!)"
