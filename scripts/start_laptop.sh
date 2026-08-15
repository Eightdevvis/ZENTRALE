#!/usr/bin/env bash
#
# start_laptop.sh — ZENTRALE im LAPTOP-Modus (Kassette "laptop").
#
# "ZENTRALE in klein" für die 0rammachine. Unterschiede zum normalen
# start_local.sh (Monolith):
#
#   - KI komplett raus: ZENTRALE_KASSETTE=laptop schaltet in main.py den
#     Ollama-Warmup + News-Fetcher ab und in app.py die KI-Endpoints
#     (siehe core/kassette.py). Ollama wird NIE angesprochen.
#   - Nur EIN Prozess: core/main.py (Event-Loop + Flask). KEIN Whisper,
#     KEIN TTS — die braucht die KI-freie Kassette nicht, spart RAM.
#   - Eigenes Frontend: Flask liefert ui/templates/laptop.html statt
#     monolith.html (die Route wählt nach Kassette).
#
# Default OHNE sudo (keyboard-Lib bliebe stumm). Sensoren manuell triggern:
#
#     curl -X POST http://localhost:5000/api/sensor/button
#     curl -X POST http://localhost:5000/api/sensor/motion
#
# Mit "--with-keyboard" läuft main.py via sudo (Tasten-Sim b/l/m).
#
# Ctrl+C beendet sauber.

set -u

# ── Ins Projekt-Root wechseln (Skript liegt in scripts/) ───────────────
# readlink -f loest den ~/.local/bin/zentrale-laptop-Symlink auf, damit
# wir auch beim Aufruf über den Symlink im richtigen Projekt-Root landen.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/betrieb/setup.md)." >&2
  exit 1
fi

# ── DIE Kassetten-Wahl: hieran erkennt main.py + app.py den Laptop-Modus ──
export ZENTRALE_KASSETTE=laptop

# ── Push-on-write: jede echte Daten-Änderung sofort zum Peer schieben ──
# (core/datasync.py stößt im Hintergrund zentrale-push-data an; no-op ohne dies)
export ZENTRALE_AUTOPUSH=1

# ── Optional: --with-keyboard schaltet sudo fuer main.py an ────────────
# sudo -E, damit ZENTRALE_KASSETTE die Umgebung von root erreicht (sonst
# liefe das Backend versehentlich als Monolith mit KI).
USE_SUDO=""
if [[ "${1:-}" == "--with-keyboard" ]]; then
  USE_SUDO="sudo -E"
  sudo -v || { echo "sudo abgelehnt, breche ab." >&2; exit 1; }
fi

# ── Cleanup-Handler ────────────────────────────────────────────────────
MAIN_PID=$$
CLEANED=0
cleanup() {
  [[ "$BASHPID" != "$MAIN_PID" ]] && return 0
  [[ "$CLEANED" == "1" ]] && return 0
  CLEANED=1
  echo ""
  echo "[start_laptop] shutting down..."
  pkill -P "$MAIN_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# ── Prefix-Funktion: jede Zeile bekommt [main] in Farbe vorgesetzt ─────
prefix() {
  local tag="$1" color="$2"
  sed -u "s/^/$(printf '\033')[${color}m[${tag}]$(printf '\033')[0m /"
}

# ── Banner ─────────────────────────────────────────────────────────────
echo "============================================================"
echo " ZENTRALE (LAPTOP) — Kassette 'laptop', KI deaktiviert"
echo "============================================================"
if [[ -n "$USE_SUDO" ]]; then
  echo " mode: core/main.py mit sudo (Tastatur-Sensor-Sim aktiv)"
else
  echo " mode: kein sudo (Tastatur-Sensor-Sim aus)"
  echo "       Sensor-Trigger: curl -X POST http://localhost:5000/api/sensor/<name>"
fi
echo " dashboard: http://localhost:5000  (laptop.html)"
echo " whisper/tts: AUS (KI-frei)"
echo " Ctrl+C zum Beenden"
echo "============================================================"
echo ""

# ── EINZIGER Service: Event-Loop + Flask ───────────────────────────────
$USE_SUDO "$PY" core/main.py > >(prefix main 36) 2>&1 &

# wait blockiert bis der Prozess endet (oder Ctrl+C).
wait
