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

# ── Exit-Codes (damit ein Fehlstart diagnostizierbar ist statt "exited") ──
#   0  sauberer Quit (oder schon laufende Session attached)
#   2  venv/Python fehlt
#   3  Port :5000 schon belegt (verwaiste/fremde ZENTRALE) — NICHT zweimal starten
#   4  Backend beim Hochfahren gestorben (Import-/Code-Fehler → Backend-Log)
#   5  Backend-API nach 15 s nicht erreichbar (hängt → Backend-Log)
#   1  TUI selbst abgestürzt (kein sauberer Quit → /tmp/zentrale-tui-crash.log)
# Bei 1/4/5 zeigt das Skript das passende Log; die TUI schreibt ihren Traceback
# zusätzlich nach /tmp/zentrale-tui-crash.log (sonst killt tmux die Pane samt
# Fehlermeldung).

# ── Ins Projekt-Root (Skript liegt in scripts/, Symlink wird aufgelöst) ──
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "FEHLER (2): $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/setup.md)." >&2
  exit 2
fi

export ZENTRALE_KASSETTE=tui
BACKEND_LOG="/tmp/zentrale-tui-backend.log"
SESSION="zentrale-tui"
# Gemerkte Höhe der unteren bash (über Sessions hinweg): beim Beenden der TUI
# geschrieben (--run-tui unten), beim nächsten Start wieder geladen.
STATE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/zentrale/tui_term_lines"

# Aktuelle Höhe der unteren bash (pane 1) wegschreiben — validiert, schreibt nur
# bei gültiger Zahl (sonst alten Wert behalten, z.B. wenn pane 1 grad fehlt).
save_term_height() {
  local h
  h="$(tmux display-message -p -t "${SESSION}.1" -F '#{pane_height}' 2>/dev/null || true)"
  [[ "$h" =~ ^[0-9]+$ ]] || return 0
  mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null && printf '%s\n' "$h" > "$STATE_FILE"
}

# ── Sub-Modus für den after-resize-pane-Hook: nur die bash-Höhe LIVE sichern. ─
# So ist die Höhe nach JEDEM Resize (Taste oder Maus) sofort gemerkt — egal wie
# die Session endet (q, Crash, Fenster zu). Kein Abhängen vom sauberen Quit.
if [[ "${1:-}" == "--save-height" ]]; then
  save_term_height
  exit 0
fi

# ── Sub-Modus (läuft IM tmux-Pane 0): nur die TUI; danach die AKTUELLE Höhe der
#    unteren bash (pane 1) für die nächste Session merken, dann die Session zu. ─
if [[ "${1:-}" == "--run-tui" ]]; then
  "$PY" tui/zentrale_tui.py
  rc=$?
  # Kein sauberer Quit (rc≠0)? Dann den Fehler ZEIGEN und auf eine Taste warten,
  # BEVOR tmux die Pane (und damit jede Meldung) killt. Genau das hat bisher
  # gefehlt: die TUI "verschwand" ohne Spur.
  if [[ "$rc" -ne 0 ]]; then
    echo >&2
    echo "════ ZENTRALE-TUI mit Code $rc beendet — kein sauberer Quit ════" >&2
    if [[ -f /tmp/zentrale-tui-crash.log ]]; then
      echo "── TUI-Crash-Log ─────────────────────────────────" >&2
      cat /tmp/zentrale-tui-crash.log >&2
    fi
    echo "── Backend-Log ($BACKEND_LOG), letzte Zeilen ─────" >&2
    tail -n 15 "$BACKEND_LOG" 2>/dev/null >&2
    echo >&2
    echo "Taste drücken zum Schließen…" >&2
    read -rsn1 || true
  fi
  save_term_height          # Backup-Sicherung beim Beenden (der Hook macht's live)
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  exit "$rc"
fi

# ── Immer ein FRISCHER, sauberer Start ──────────────────────────────────
# Keine "Session-Wiederverwendung" mehr: die war fehleranfällig (globales
# pgrep, verwaiste Sessions, Fehltreffer → mal "läuft schon" gelogen, mal die
# laufende Session gekillt). `zentrale-tui` heißt jetzt schlicht: gib mir hier
# ein frisches Dashboard. Alte zentrale-tui-Reste werden weggeräumt (Session
# unten; ein verwaistes ki-frei-Backend holt der Port-Check weiter unten zurück).
#
# EINZIGER Schutz: nicht aus der EIGENEN tmux-Session heraus neu starten — sonst
# träfe das Aufräumen die Session, in der man gerade sitzt (Self-Kill-Footgun).
if [[ -n "${TMUX:-}" ]]; then
  cur="$(tmux display-message -p '#{session_name}' 2>/dev/null)"
  if [[ "$cur" == "$SESSION" ]]; then
    echo "Du bist schon in der ZENTRALE-tmux-Session — 'q' beendet die TUI." >&2
    echo "Neustart: dieses Fenster schließen, dann aus einem FRISCHEN Terminal 'zentrale-tui'." >&2
  else
    echo "Du bist in einer anderen tmux-Session ('$cur'). zentrale-tui braucht ein" >&2
    echo "normales Terminal (tmux-in-tmux geht nicht) — starte es außerhalb von tmux." >&2
  fi
  exit 0
fi

# Außerhalb von tmux: evtl. vorhandene zentrale-tui-Session wegräumen (frisch).
command -v tmux >/dev/null && tmux kill-session -t "$SESSION" 2>/dev/null || true

# Höhe für den Split: Env-Override > gemerkte Höhe > Default 6.
SAVED=""
[[ -f "$STATE_FILE" ]] && read -r SAVED < "$STATE_FILE" 2>/dev/null || true
[[ "$SAVED" =~ ^[0-9]+$ ]] || SAVED=""
# Beim BOOTEN nie unbrauchbar winzig (gemerkter Mini-Wert): Untergrenze 3 Zeilen.
# Live runterziehen bis 1 bleibt erlaubt — das hier betrifft nur den Start.
[[ -n "$SAVED" && "$SAVED" -lt 3 ]] && SAVED=3
TERM_LINES="${ZENTRALE_TERM_LINES:-${SAVED:-6}}"   # Höhe der unteren echten bash

# Beim BOOTEN nie so hoch, dass dem TUI (Pane 0) zu wenig bleibt. Hat man die
# bash mal fast über den ganzen Schirm gezogen (TUI auf 1 Zeile), würde sonst
# genau dieser Riesenwert wiederhergestellt → TUI rendert "Terminal zu klein".
# Obergrenze: echte Terminalhöhe minus TUI-Mindesthöhe (14) minus Split-Trenner.
# (Live hochziehen bleibt erlaubt — das hier betrifft nur den Start.)
TUI_MIN_LINES=14
TERM_TOTAL="$(tput lines 2>/dev/null || true)"
if [[ "$TERM_TOTAL" =~ ^[0-9]+$ ]]; then
  MAX_BASH=$(( TERM_TOTAL - TUI_MIN_LINES - 1 ))
  (( MAX_BASH < 1 )) && MAX_BASH=1          # Mini-Terminal: bash 1 Zeile, TUI kriegt den Rest
  (( TERM_LINES > MAX_BASH )) && TERM_LINES="$MAX_BASH"
fi

# ── Ist :5000 schon belegt? KLARE Ansage statt stillem Zweit-Backend ─────
# Hierher kommen wir nur, wenn KEINE 'zentrale-tui'-Session läuft (sonst oben
# attached). Antwortet trotzdem etwas auf :5000, ist es ein verwaistes oder
# fremdes Backend. Würden wir jetzt ein zweites starten, könnte es den Port
# nicht binden (Flask-Thread stirbt still), die Readiness-Prüfung träfe das
# FALSCHE Backend, und die TUI liefe gegen veralteten Code — genau die Art
# "läuft nicht, keine Ahnung warum". Lieber hart abbrechen mit Aufräum-Tipp.
if curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null; then
  # Ist es UNSER verwaistes ki-frei-Backend (von einer toten TUI-Session)? Dann
  # zurückholen statt abbrechen. Erkennung: ZENTRALE_KASSETTE=tui im Prozess-
  # Environ — so treffen wir NIE ein fremdes/monolith-Backend.
  reclaimed=0
  for pid in $(pgrep -f 'core/main\.py' 2>/dev/null); do
    if tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | grep -qx 'ZENTRALE_KASSETTE=tui'; then
      kill "$pid" 2>/dev/null && reclaimed=1
    fi
  done
  if [[ "$reclaimed" == 1 ]]; then
    echo "Verwaistes ki-frei-Backend auf :5000 zurückgeholt — starte frisch." >&2
    for _ in $(seq 1 20); do curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null || break; sleep 0.2; done
  else
    echo "FEHLER (3): Auf http://localhost:5000 antwortet bereits eine ZENTRALE (fremd/monolith)." >&2
    echo "  Backend-PID(s): $(pgrep -f 'core/main.py' 2>/dev/null | tr '\n' ' ')" >&2
    echo "  Aufräumen:  pkill -f 'core/main.py'   — dann erneut: zentrale-tui" >&2
    exit 3
  fi
fi

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
  # Backend schon gestorben? Dann raus mit Log-Hinweis (Code 4 = Code-/Import-Fehler).
  kill -0 "$BACKEND_PID" 2>/dev/null || { echo "FEHLER (4): Backend abgebrochen — siehe $BACKEND_LOG:" >&2; tail -n 20 "$BACKEND_LOG" >&2; exit 4; }
  sleep 0.5
done
if [[ "$ready" != "1" ]]; then
  echo "FEHLER (5): Backend-API nach 15s nicht erreichbar — siehe $BACKEND_LOG:" >&2
  tail -n 20 "$BACKEND_LOG" >&2
  exit 5
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
  # Untere bash live höher/niedriger, 1 Zeile pro Schritt, greift Pane 0 (TUI)
  # → fokus-unabhängig. Untergrenze ist von tmux aus 1 Zeile bash.
  # PRIMÄR ohne Prefix (root-Tabelle): Ctrl gedrückt HALTEN und ↑/↓ dauerfeuern —
  # geht endlos, kein 500-ms-Repeat-Timeout, kein erneutes 'b' nötig.
  # (Alt+Pfeil NICHT genommen — XFCE fängt das fürs Fenster-Tiling ab.)
  tmux bind-key -n C-Up   resize-pane -t 0 -U 1    # bash höher (TUI schrumpft)
  tmux bind-key -n C-Down resize-pane -t 0 -D 1    # bash niedriger (TUI wächst)
  # Zusätzlich unter dem Prefix (Ctrl-b dann Ctrl+↑/↓), wiederholbar; das
  # Repeat-Fenster großzügig, falls man doch über das Prefix geht.
  tmux set-option -t "$SESSION" -g repeat-time 1000
  tmux bind-key -r C-Up   resize-pane -t 0 -U 1
  tmux bind-key -r C-Down resize-pane -t 0 -D 1
  # Detach abschalten: 'Ctrl-b d' (tmux-Default) koppelt sofort & ohne Rückfrage
  # ab — und weil das Eltern-Skript dann aus 'attach' zurückkehrt, killt cleanup
  # Backend+Session. Genau dieser Fummel-Footgun. Raus geht's NUR via 'q'.
  tmux unbind-key -T prefix d
  tmux unbind-key -T prefix D
  # Höhe LIVE merken: nach JEDEM Resize (Taste ODER Maus-Rand) die bash-Höhe
  # wegschreiben → nächste Session startet mit genau dieser Höhe, egal wie diese
  # hier endet. -b = im Hintergrund, blockiert das Resizen nicht.
  tmux set-hook -t "$SESSION" after-resize-pane "run-shell -b '\"$SELF\" --save-height'"
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
