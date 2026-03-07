#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <pi-user@pi-host> <remote-dir>"
  echo "Example: $0 pi@192.168.1.44 /opt/zentrale"
  exit 1
fi

TARGET="$1"
REMOTE_DIR="$2"
SERVICE_NAME="zentrale.service"

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

echo "[5/6] Install/refresh systemd service"
ssh "$TARGET" "true"

# Set service user dynamically from target prefix (user@host -> user)
SERVICE_USER="${TARGET%@*}"
TMP_SERVICE="$(mktemp)"
sed "s|^User=.*$|User=$SERVICE_USER|" "$PROJECT_ROOT/deploy/$SERVICE_NAME" > "$TMP_SERVICE"

scp "$TMP_SERVICE" "$TARGET:/tmp/$SERVICE_NAME"
rm -f "$TMP_SERVICE"

ssh "$TARGET" "sudo mv '/tmp/$SERVICE_NAME' '/etc/systemd/system/$SERVICE_NAME'"
ssh "$TARGET" "sudo systemctl daemon-reload"
ssh "$TARGET" "sudo systemctl enable '$SERVICE_NAME'"

echo "[6/6] Restart service + status"
ssh "$TARGET" "sudo systemctl restart '$SERVICE_NAME'"
ssh "$TARGET" "sudo systemctl --no-pager --full status '$SERVICE_NAME' || true"

echo "Deploy complete. Tail logs with:"
echo "ssh $TARGET \"sudo journalctl -u $SERVICE_NAME -f\""
