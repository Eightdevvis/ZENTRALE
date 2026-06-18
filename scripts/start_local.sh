#!/usr/bin/env bash
#
# start_local.sh — ZENTRALE auf dem PC starten (Entwicklung + Alltag).
#
# Seit der PC↔Pi-Migration laeuft das komplette Backend auf dem PC.
# Dieses Skript ist die Standard-Art ZENTRALE hier hochzufahren: es
# startet alle drei Prozesse (Event-Loop+Flask, Whisper, TTS) parallel
# in EINEM Terminal. Jede Log-Zeile wird pro Service farbig geprefixt,
# damit man auseinanderhalten kann wer was sagt.
#
# Default: OHNE sudo. Heisst: die Tastatur-Sensor-Simulation in
# core/sensors.py schweigt (keyboard-Lib braucht Root). Das Dashboard
# laeuft trotzdem voll - Sensoren manuell triggern per HTTP-Webhook:
#
#     curl -X POST http://localhost:5000/api/sensor/button
#     curl -X POST http://localhost:5000/api/sensor/motion
#     curl -X POST http://localhost:5000/api/sensor/light
#     curl -X POST http://localhost:5000/api/sensor/door
#
# Mit "--with-keyboard" wird core/main.py via sudo gestartet, dann geht
# auch die Tasten-Simulation (b/l/m im fokussierten Fenster).
#
# Ctrl+C beendet alle drei Prozesse sauber.

set -u

# ── Ins Projekt-Root wechseln (Skript liegt in scripts/) ───────────────
# readlink -f loest Symlinks auf, damit man das Skript auch via
# `~/.local/bin/zentrale -> .../scripts/start_local.sh` aufrufen kann
# und trotzdem das richtige Projekt-Root landet.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/setup.md)." >&2
  exit 1
fi

# ── Push-on-write: jede echte Daten-Änderung sofort zum Peer schieben ──
# (core/datasync.py stößt im Hintergrund zentrale-push-data an; no-op ohne dies).
# Hinweis: greift nur ohne sudo — mit --with-keyboard läuft main.py via plain
# sudo (Env wird verworfen), dann übernimmt der Boot-Sync den Abgleich.
export ZENTRALE_AUTOPUSH=1

# ── Optional: --with-keyboard schaltet sudo fuer main.py an ────────────
USE_SUDO=""
if [[ "${1:-}" == "--with-keyboard" ]]; then
  USE_SUDO="sudo"
  # sudo-Token vorab einsammeln, damit der Passwort-Prompt nicht mitten
  # im Service-Output landet und das Layout zerschiesst.
  sudo -v || { echo "sudo abgelehnt, breche ab." >&2; exit 1; }
fi

# ── Liste der Service-PIDs, die wir am Ende killen muessen ─────────────
PIDS=()

# Cleanup-Handler: erst freundlich SIGTERM an die Python-Prozesse, dann
# pkill -P $$ fuer eventuelle Reste (sed-Prefixer aus den >() process
# substitutions sind Kinder dieses Shells und ueberleben sonst kurz).
#
# Guard via MAIN_PID: die >()-Subshells erben den Trap. Ohne den Check
# wuerde jeder Sub-Shell-Exit den Cleanup-Banner erneut drucken (3x).
MAIN_PID=$$
CLEANED=0
cleanup() {
  [[ "$BASHPID" != "$MAIN_PID" ]] && return 0
  [[ "$CLEANED" == "1" ]] && return 0
  CLEANED=1
  echo ""
  echo "[start_local] shutting down..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  pkill -P "$MAIN_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# ── Prefix-Funktion: jede Zeile bekommt [tag] in Farbe vorgesetzt ──────
# sed -u = unbuffered, damit die Logs in Echtzeit ankommen und nicht
# erst beim Pipe-Flush des Service ausgegeben werden.
prefix() {
  local tag="$1" color="$2"
  sed -u "s/^/$(printf '\033')[${color}m[${tag}]$(printf '\033')[0m /"
}

# ── Banner ─────────────────────────────────────────────────────────────
echo "============================================================"
echo " ZENTRALE (PC) — main + whisper + tts"
echo "============================================================"
if [[ -n "$USE_SUDO" ]]; then
  echo " mode: core/main.py mit sudo (Tastatur-Sensor-Sim aktiv)"
else
  echo " mode: kein sudo (Tastatur-Sensor-Sim aus)"
  echo "       Sensor-Trigger: curl -X POST http://localhost:5000/api/sensor/<name>"
fi
echo " dashboard: http://localhost:5000"
echo " whisper:   http://localhost:5050"
echo " tts:       http://localhost:5051"
echo " Ctrl+C zum Beenden"
echo "============================================================"
echo ""

# ── Services starten ───────────────────────────────────────────────────
# Wir nutzen `> >(prefix ...) 2>&1` (bash process substitution) statt
# einer normalen Pipe `| prefix`. Vorteil: $! zeigt die PID des Python-
# Prozesses, nicht die des sed-Prefixers. Damit koennen wir die Services
# direkt killen.
#
# Farbcodes:
#   36 = cyan   (main)
#   33 = yellow (whisper)
#   35 = magenta(tts)

$USE_SUDO "$PY" core/main.py > >(prefix main 36) 2>&1 &
PIDS+=($!)

"$PY" services/whisper_service.py > >(prefix whisper 33) 2>&1 &
PIDS+=($!)

"$PY" services/tts_service.py > >(prefix tts 35) 2>&1 &
PIDS+=($!)

# wait blockiert bis alle Hintergrundprozesse fertig sind. Crasht einer,
# laufen die anderen weiter - so siehst du im Log was passiert ist,
# bevor du selber Ctrl+C drueckst. Wenn du "kill-on-first-crash" willst,
# muesste man hier `wait -n` plus erneutes cleanup haendeln.
wait
