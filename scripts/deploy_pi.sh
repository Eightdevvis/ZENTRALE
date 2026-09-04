#!/usr/bin/env bash
set -euo pipefail

# deploy_pi.sh — einen Knoten bespielen.
#
# ZWEI MODI, weil es zwei Sorten Knoten gibt:
#
#   aussenposten (DEFAULT)  Anzeige + Ton + Sensorik, KEIN Backend. Bekommt
#                           nur die Positivliste deploy/aussenposten.txt und
#                           die kurze deploy/requirements-aussenposten.txt.
#                           Keine systemd-Units — die laufen auf dem PC.
#
#   --voll                  Vollwertiger Backend-Host (Core + Flask + Audio).
#                           Spiegelt das ganze Projekt und installiert die
#                           komplette requirements.txt. Das war frueher der
#                           einzige Modus.
#
# WARUM DER SCHNITT: seit der PC<->Pi-Migration hostet der Pi kein Backend
# mehr (memory/system/topologie.md); zentrale/whisper/tts sind dort disabled.
# Der alte Vollspiegel schob trotzdem ALLES rueber — inklusive
# data/tts_model/ (1,0 GB Sprachmodelle) und core/map/ (37 MB) — und
# installierte faster-whisper/sherpa-onnx/piper-tts in den Pi-venv. Auf einem
# Pi 3 mit 1 GB RAM und 32-bit-ARM ist das ein langer Build fuer Code, der
# dort nie laeuft.

usage() {
  echo "Usage: $0 [--voll] <user@host> <remote-dir>"
  echo "  $0 sasha@192.168.50.10 /opt/zentrale        # Aussenposten (default)"
  echo "  $0 --voll sasha@192.168.50.10 /opt/zentrale # kompletter Backend-Host"
  exit 1
}

MODE="aussenposten"
if [[ "${1:-}" == "--voll" ]]; then
  MODE="voll"; shift
fi
[[ $# -lt 2 ]] && usage

TARGET="$1"
REMOTE_DIR="$2"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Alle drei systemd-Units die wir auf einem BACKEND-Host pflegen. zentrale.service
# ist der Core (Event-Loop + Flask), whisper/tts sind die Audio-Services
# mit Low-Prio-Scheduling. Reihenfolge ist relevant fuer den restart
# am Ende — Core zuerst.
SERVICES=("zentrale.service" "whisper.service" "tts.service")

LISTE="$PROJECT_ROOT/deploy/aussenposten.txt"
REQ_AUSSEN="deploy/requirements-aussenposten.txt"

echo "=== Modus: $MODE  ->  $TARGET:$REMOTE_DIR"

# ── 1) Dateien ───────────────────────────────────────────────────────────
if [[ "$MODE" == "aussenposten" ]]; then
  [[ -f "$LISTE" ]] || { echo "FEHLER: $LISTE fehlt"; exit 1; }
  echo "[1/4] Positivliste uebertragen ($(grep -cve '^\s*#' -e '^\s*$' "$LISTE") Eintraege)"
  # --files-from nimmt die Liste; Kommentare/Leerzeilen filtern wir raus.
  # -r ist noetig, weil --files-from die Rekursion sonst abschaltet.
  # KEIN --delete: bei einer Positivliste besitzen wir den Zielbaum nicht,
  # --delete wuerde dort alles ausserhalb der Liste wegraeumen (u.a. .venv
  # und lokale Configs).
  grep -ve '^\s*#' -e '^\s*$' "$LISTE" \
    | rsync -az -r --files-from=- "$PROJECT_ROOT/" "$TARGET:$REMOTE_DIR/"
  # Marker: sagt pi_autopull.sh, dass hier die kurze Requirements-Liste gilt.
  ssh "$TARGET" "touch '$REMOTE_DIR/.aussenposten'"
else
  echo "[1/4] Projekt komplett spiegeln"
  rsync -az --delete \
    --exclude '__pycache__' \
    --exclude '.git' \
    --exclude '.venv' \
    "$PROJECT_ROOT/" "$TARGET:$REMOTE_DIR/"
  ssh "$TARGET" "rm -f '$REMOTE_DIR/.aussenposten'"
fi

# ── 2) venv ──────────────────────────────────────────────────────────────
echo "[2/4] venv sicherstellen + pip aktualisieren"
ssh "$TARGET" "python3 -m venv '$REMOTE_DIR/.venv' && '$REMOTE_DIR/.venv/bin/pip' install --upgrade pip -q"

# ── 3) Abhaengigkeiten ───────────────────────────────────────────────────
if [[ "$MODE" == "aussenposten" ]]; then
  echo "[3/4] Abhaengigkeiten (kurze Aussenposten-Liste)"
  ssh "$TARGET" "'$REMOTE_DIR/.venv/bin/pip' install -r '$REMOTE_DIR/$REQ_AUSSEN'"
else
  echo "[3/4] Abhaengigkeiten (komplette requirements.txt)"
  ssh "$TARGET" "if [[ -f '$REMOTE_DIR/requirements.txt' ]]; then '$REMOTE_DIR/.venv/bin/pip' install -r '$REMOTE_DIR/requirements.txt'; fi"
fi

# ── 4) systemd — nur auf einem Backend-Host ──────────────────────────────
if [[ "$MODE" == "aussenposten" ]]; then
  echo "[4/4] systemd uebersprungen (Aussenposten hostet kein Backend)"
else
  echo "[4/4] systemd-Units installieren + neu starten"
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
  # Core zuerst (whisper/tts haben After=zentrale.service) damit beim
  # Restart die Reihenfolge dem Boot-Verhalten entspricht.
  for SVC in "${SERVICES[@]}"; do
    ssh "$TARGET" "sudo systemctl restart '$SVC' || true"
  done
  ssh "$TARGET" "sudo systemctl --no-pager --full status ${SERVICES[*]} || true"
fi

echo
echo "Fertig ($MODE)."
if [[ "$MODE" == "aussenposten" ]]; then
  echo "Das war die ERST-Bespielung. Ab jetzt haelt der Knoten sich selbst"
  echo "aktuell — er holt sein Paket per HTTP vom Backend ab, sobald sich"
  echo "dessen Inhalts-Hash aendert. Dafuer einmalig den Cron eintragen:"
  echo "    crontab $REMOTE_DIR/deploy/aussenposten-update.cron"
  echo "    $REMOTE_DIR/scripts/aussenposten_update.py --pruefen   # Sichtpruefung"
  echo
  echo "Ausserdem einmalig (falls noch nicht):"
  echo "  Kiosk + Hotkeys (BACKEND_URL = LAN-IP des PC, sonst localhost-Footgun):"
  echo "    ZENTRALE_BACKEND_URL=http://192.168.50.1:5000 bash $REMOTE_DIR/scripts/install_xfce_autostart.sh"
  echo "  Sudo-Rechte fuer den Notaus: sudo bash $REMOTE_DIR/scripts/install_pi_sudoers.sh"
else
  echo "Logs: journalctl -u zentrale.service -f"
fi
