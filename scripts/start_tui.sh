#!/usr/bin/env bash
#
# start_tui.sh — ZENTRALE als Terminal-Kassette (KEIN Browser).
#
# Fährt das Backend ki-frei hoch (ZENTRALE_KASSETTE=tui → kein Ollama-Warmup,
# kein News-Fetcher, KI-Endpoints abgeriegelt; siehe core/kassette.py) und
# startet dann die curses-TUI (tui/zentrale_tui.py).
#
# Layout (wenn tmux da ist): EIN tmux-Fenster, zwei Panes —
#   ┌─────────────────────────────┐
#   │  oben:  die TUI (Dashboard)  │
#   ├─────────────────────────────┤
#   │  unten: eine ECHTE bash      │  ← cd/ls/Tab/History/xdg-open, kein Fake
#   └─────────────────────────────┘
# Die untere bash ist ein vollwertiges Terminal: Dateien öffnen z.B. mit
# `xdg-open bericht.pdf` (PDF-Default ist zathura, via xdg-mime gesetzt).
# Pane FOKUSSIEREN (oben/unten): Maus-Klick, oder `Ctrl-b` dann nacktes ↑/↓
#   (Ctrl loslassen). Höhe der bash ÄNDERN: `Ctrl-b` dann Ctrl+↑/↓ (Ctrl
#   durchhalten), oder den Rand mit der MAUS ziehen.
# Beenden: 'q' in der TUI → schließt das ganze tmux-Fenster und stoppt alles.
# Ohne tmux: Fallback = TUI im Vollbild (wie früher), mit Install-Hinweis.
#
# Die Höhe der bash wird beim Beenden gemerkt und beim nächsten Start wieder
# hergestellt (~/.config/zentrale/tui_term_lines). Erzwingen: ZENTRALE_TERM_LINES.
#
# Das Backend-stdout geht in eine LOGDATEI, NICHT ins Terminal — sonst würde
# es die curses-Oberfläche zerschießen. Die Logs erscheinen ohnehin im
# stdout-Panel der TUI (über /api/state). Logdatei live mitlesen:
#     tail -f /tmp/zentrale-tui-backend.log

set -u

# ── Ins Projekt-Root (Skript liegt in scripts/, Symlink wird aufgelöst) ──
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/setup.md)." >&2
  exit 1
fi

export ZENTRALE_KASSETTE=tui
BACKEND_LOG="/tmp/zentrale-tui-backend.log"
SESSION="zentrale-tui"
# Gemerkte Höhe der unteren bash (über Sessions hinweg): beim Beenden der TUI
# geschrieben (--run-tui unten), beim nächsten Start wieder geladen.
STATE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/zentrale/tui_term_lines"

# ── Sub-Modus (läuft IM tmux-Pane 0): nur die TUI; danach die AKTUELLE Höhe der
#    unteren bash (pane 1) für die nächste Session merken, dann die Session zu. ─
if [[ "${1:-}" == "--run-tui" ]]; then
  "$PY" tui/zentrale_tui.py
  h="$(tmux display-message -p -t "${SESSION}.1" -F '#{pane_height}' 2>/dev/null || true)"
  if [[ "$h" =~ ^[0-9]+$ ]]; then
    mkdir -p "$(dirname "$STATE_FILE")" && printf '%s\n' "$h" > "$STATE_FILE"
  fi
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit 0
fi

# Höhe für den Split: Env-Override > gemerkte Höhe > Default 6.
SAVED=""
[[ -f "$STATE_FILE" ]] && read -r SAVED < "$STATE_FILE" 2>/dev/null || true
[[ "$SAVED" =~ ^[0-9]+$ ]] || SAVED=""
TERM_LINES="${ZENTRALE_TERM_LINES:-${SAVED:-6}}"   # Höhe der unteren echten bash

# ── Backend im Hintergrund, stdout in die Logdatei ──────────────────────
"$PY" core/main.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

cleanup() {
  command -v tmux >/dev/null && tmux kill-session -t "$SESSION" 2>/dev/null || true
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

# ── TUI starten ─────────────────────────────────────────────────────────
# Mit tmux: oben TUI, unten echte bash (gegen das, was die TUI selbst NICHT
# kann — Dateisystem navigieren + öffnen). Ohne tmux: TUI im Vollbild.
if command -v tmux >/dev/null; then
  # Frische Session (alte Reste weg), pane 0 = TUI. Wenn die TUI endet ('q'),
  # killt sie die ganze Session → attach kehrt zurück → cleanup stoppt Backend.
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  tmux new-session -d -s "$SESSION" -c "$PWD" "'$SELF' --run-tui"
  tmux set-option -t "$SESSION" -g mouse on        # Pane per Klick fokussieren + Rand ziehen
  tmux set-option -t "$SESSION" -g status off      # keine tmux-Statuszeile → mehr Platz
  # Untere bash live höher/niedriger: Ctrl GEDRÜCKT HALTEN → b → (Ctrl weiter
  # halten) ↑/↓. Das ist tmux-Standard (C-Up/C-Down in der Prefix-Tabelle).
  # Greift Pane 0 (die TUI) an → fokus-unabhängig. Wiederholbar (-r).
  # (Alt+Pfeil NICHT genommen — XFCE fängt das fürs Fenster-Tiling ab.)
  # Schrittweite 1 Zeile; Untergrenze ist von tmux aus 1 Zeile bash.
  tmux bind-key -r C-Up   resize-pane -t 0 -U 1    # bash höher (TUI schrumpft)
  tmux bind-key -r C-Down resize-pane -t 0 -D 1    # bash niedriger (TUI wächst)
  # Split ERST nach dem Attach, damit die Höhe relativ zur ECHTEN Terminal-
  # größe sitzt. '-d' lässt den Fokus oben auf der TUI; untere bash startet
  # im HOME (fühlt sich an wie ein frisch geöffnetes Terminal).
  tmux attach-session -t "$SESSION" \; \
       split-window -d -v -l "$TERM_LINES" -c "$HOME"
else
  echo "ZENTRALE (tui): tmux nicht installiert — TUI im Vollbild (kein unteres Terminal)." >&2
  echo "Für das angeklebte echte Terminal:  sudo apt install tmux" >&2
  sleep 2
  "$PY" tui/zentrale_tui.py
fi
