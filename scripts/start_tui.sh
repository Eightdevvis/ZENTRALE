#!/usr/bin/env bash
#
# start_tui.sh — ZENTRALE als Terminal-Kassette (KEIN Browser).
#
# Fährt das Backend ki-frei hoch (ZENTRALE_KASSETTE=tui → kein Ollama-Warmup,
# kein News-Fetcher, KI-Endpoints abgeriegelt; siehe core/kassette.py) und
# startet dann die curses-TUI (tui/zentrale_tui.py) im Vordergrund.
#
# Das Backend-stdout geht in eine LOGDATEI, NICHT ins Terminal — sonst würde
# es die curses-Oberfläche zerschießen. Die Logs erscheinen ohnehin im
# stdout-Panel der TUI (über /api/state). Logdatei live mitlesen:
#     tail -f /tmp/zentrale-tui-backend.log
#
# Beenden: 'q' in der TUI (oder Ctrl+C) — beides stoppt auch das Backend.

set -u

# ── Ins Projekt-Root (Skript liegt in scripts/, Symlink wird aufgelöst) ──
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/setup.md)." >&2
  exit 1
fi

export ZENTRALE_KASSETTE=tui
BACKEND_LOG="/tmp/zentrale-tui-backend.log"

# ── Backend im Hintergrund, stdout in die Logdatei ──────────────────────
"$PY" core/main.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# ── Auf die Flask-API warten (max ~15 s) ────────────────────────────────
echo "ZENTRALE (tui) — Backend startet, warte auf API …"
ready=0
for _ in $(seq 1 30); do
  if curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null; then ready=1; break; fi
  # Backend schon gestorben? Dann raus mit Log-Hinweis.
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "Backend abgebrochen — siehe $BACKEND_LOG:"; tail -n 20 "$BACKEND_LOG"; exit 1; }
  sleep 0.5
done
if [[ "$ready" != "1" ]]; then
  echo "API nicht erreichbar nach 15s — siehe $BACKEND_LOG:" >&2
  tail -n 20 "$BACKEND_LOG" >&2
  exit 1
fi

# ── TUI im Vordergrund (blockiert bis 'q'/Ctrl+C) ───────────────────────
"$PY" tui/zentrale_tui.py
