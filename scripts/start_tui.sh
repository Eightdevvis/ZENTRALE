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
# Pane FOKUSSIEREN (oben/unten): Maus-Klick, oder `Ctrl-b` dann ↑/↓ — egal ob
#   Ctrl noch gehalten wird (beides switcht). Höhe der bash ÄNDERN: Ctrl+↑/↓
#   OHNE Prefix (Ctrl halten und ↑/↓ tippen), oder den Rand mit der MAUS ziehen.
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

# ── Boot-Höhe der unteren bash berechnen — PURE Funktion (keine Seiteneffekte,
#    damit testbar; siehe tests/test_start_tui_height.py). ───────────────────
# $1 = gemerkter Wert (oder leer/Müll), $2 = Terminalhöhe gesamt (oder leer wenn
# unbekannt). Override ZENTRALE_TERM_LINES sticht den gemerkten Wert. Garantiert:
# Untergrenze 3 (sonst unbrauchbar winzig) und Obergrenze so, dass dem TUI seine
# Mindesthöhe (14) + Split-Trenner (1) bleibt — sonst rendert es "Terminal zu
# klein". Echot die finale bash-Höhe.
TUI_MIN_LINES=14
compute_boot_lines() {
  local saved="$1" total="$2" lines
  [[ "$saved" =~ ^[0-9]+$ ]] || saved=""
  [[ -n "$saved" && "$saved" -lt 3 ]] && saved=3       # Untergrenze beim Boot
  lines="${ZENTRALE_TERM_LINES:-${saved:-6}}"          # Override > gemerkt > Default 6
  if [[ "$total" =~ ^[0-9]+$ ]]; then                  # Obergrenze: TUI behält ≥14
    local max_bash=$(( total - TUI_MIN_LINES - 1 ))
    (( max_bash < 1 )) && max_bash=1                   # Mini-Term: bash 1, TUI kriegt Rest
    (( lines > max_bash )) && lines="$max_bash"
  fi
  printf '%s\n' "$lines"
}

# ── Test-Subcommand (nur für die pytest-Suite): Cap-Logik isoliert ausrechnen.
#    Args: $2=gemerkter Wert, $3=Terminalhöhe. Keine venv/tmux-Abhängigkeit. ──
if [[ "${1:-}" == "--compute-boot-lines" ]]; then
  compute_boot_lines "${2:-}" "${3:-}"
  exit 0
fi

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "FEHLER (2): $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/setup.md)." >&2
  exit 2
fi

export ZENTRALE_KASSETTE=tui
BACKEND_LOG="/tmp/zentrale-tui-backend.log"
SESSION="zentrale-tui"
# ── Dedizierter tmux-Socket ─────────────────────────────────────────────────
# Die ganze Appliance-Härtung (Prefix-Tabelle LEEREN, status/mouse) läuft auf
# einem EIGENEN tmux-Server, NICHT auf dem Default-Socket des Nutzers. Grund:
# Keybindings und `status` sind in tmux server-global, nicht pro Session — auf
# dem Default-Socket leert `unbind-key -a -T prefix` also die Tastatur ALLER
# Sessions des Nutzers (Ctrl-b tut nichts mehr) und `status off` nimmt überall
# die Statusleiste. Ein eigener Socket ist die EINZIGE saubere Isolation. Live-
# Default 'zentrale'; die pytest-Suite überstimmt mit einem Wegwerf-Socket
# (ZENTRALE_TMUX_L, siehe tests/_tmux_fuzz.py). EXPORT → die Sub-Aufrufe
# (--run-tui/--save-height laufen als eigene Prozesse im Pane) erben den Socket.
: "${ZENTRALE_TMUX_L:=zentrale}"
export ZENTRALE_TMUX_L
TM=(tmux -L "$ZENTRALE_TMUX_L")
# Gemerkte Höhe der unteren bash (über Sessions hinweg): beim Beenden der TUI
# geschrieben (--run-tui unten), beim nächsten Start wieder geladen.
STATE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/zentrale/tui_term_lines"

# Aktuelle Höhe der unteren bash (pane 1) wegschreiben — validiert, schreibt nur
# bei gültiger Zahl (sonst alten Wert behalten, z.B. wenn pane 1 grad fehlt).
save_term_height() {
  local h
  h="$("${TM[@]}" display-message -p -t "${SESSION}.1" -F '#{pane_height}' 2>/dev/null || true)"
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

# ── tmux-Tastatur/Optionen/Hook für die Doppel-Pane-Kassette setzen. In EINER
#    Funktion, damit die pytest-Suite (tests/test_tmux_panes.py) EXAKT dieselbe
#    Belegung gegen einen Wegwerf-Socket prüfen kann — statt einer driftenden
#    Kopie. $1 = Session. Socket via ZENTRALE_TMUX_L überstimmbar (nur Tests;
#    live leer → Default-Socket). Erläuterungen siehe Aufruf weiter unten.
apply_tui_tmux_keys() {
  local sess="$1"
  local tm=(tmux); [[ -n "${ZENTRALE_TMUX_L:-}" ]] && tm=(tmux -L "$ZENTRALE_TMUX_L")
  "${tm[@]}" set-option -t "$sess" -g mouse on        # Pane per Klick fokussieren + Rand ziehen
  "${tm[@]}" set-option -t "$sess" -g status off      # keine tmux-Statuszeile → mehr Platz
  # APPLIANCE-HÄRTUNG: die GANZE Prefix-Tabelle leeren. Danach kann 'Ctrl-b
  # <irgendwas>' NICHTS Zerstörerisches mehr — kein kill-pane ('x'), kein
  # split ('"'/'%' → Drei-Pane-Chaos), kein new-window ('c'), kein detach ('d',
  # koppelt sonst ab → Eltern-Skript kehrt aus 'attach' zurück → cleanup killt
  # Backend). Genau diese Fat-Finger-Footguns hat der Pane-Fuzzer gefunden.
  # Raus geht's NUR über 'q' in der TUI. Danach NUR das Switchen wieder rein.
  "${tm[@]}" unbind-key -a -T prefix
  # SWITCHEN: Ctrl-b dann ↑/↓ — EGAL ob Ctrl noch gehalten wird (beide Varianten
  # auf select-pane). Vorher hing das Switchen daran, ob man Ctrl rechtzeitig
  # loslässt — sonst traf man Ctrl-b Ctrl-↑ = resize. Single-shot, kein -r.
  "${tm[@]}" bind-key -T prefix Up     select-pane -U
  "${tm[@]}" bind-key -T prefix Down   select-pane -D
  "${tm[@]}" bind-key -T prefix C-Up   select-pane -U
  "${tm[@]}" bind-key -T prefix C-Down select-pane -D
  # RESIZEN: Ctrl+↑/↓ OHNE Prefix (root-Tabelle), 1 Zeile/Schritt, greift fix
  # Pane 0 (TUI) → fokus-unabhängig. (Alt+Pfeil nicht — XFCE klaut das fürs Tiling.)
  "${tm[@]}" bind-key -n C-Up   resize-pane -t 0 -U 1 # bash höher (TUI schrumpft)
  "${tm[@]}" bind-key -n C-Down resize-pane -t 0 -D 1 # bash niedriger (TUI wächst)
  # Höhe LIVE merken: nach JEDEM Resize (Taste ODER Maus-Rand) die bash-Höhe
  # wegschreiben → nächste Session startet mit genau dieser Höhe. -b = Hintergrund.
  "${tm[@]}" set-hook -t "$sess" after-resize-pane \
    "run-shell -b 'ZENTRALE_TMUX_L=$ZENTRALE_TMUX_L \"$SELF\" --save-height'"
}

# ── Sub-Modus (nur pytest): exakt die Live-Belegung auf eine schon bestehende
#    Session anwenden, isoliert auf einem Wegwerf-Socket (ZENTRALE_TMUX_L). ──
if [[ "${1:-}" == "--apply-keys" ]]; then
  apply_tui_tmux_keys "${2:?Session-Name fehlt}"
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
    echo "Taste drücken zum Schließen… (schließt sich sonst nach 30 s selbst)" >&2
    read -rsn1 -t 30 || true   # Timeout: NIE ewig offen bleiben (sonst hängen
                               # Session + Backend fest und :5000 bleibt belegt)
  fi
  save_term_height          # Backup-Sicherung beim Beenden (der Hook macht's live)
  "${TM[@]}" kill-session -t "$SESSION" 2>/dev/null || true
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
command -v tmux >/dev/null && "${TM[@]}" kill-session -t "$SESSION" 2>/dev/null || true

# Höhe für den Split berechnen (gemerkter Wert + echte Terminalhöhe → gedeckelt,
# damit dem TUI ≥14 Zeilen bleiben). Logik in compute_boot_lines() oben.
# Die echte Terminalgröße JETZT festhalten (das Skript läuft noch im echten
# Terminal, vor tmux) — sie wird unten auch der Session aufgezwungen, siehe dort.
TPUT_LINES="$(tput lines 2>/dev/null || true)"
TPUT_COLS="$(tput cols  2>/dev/null || true)"
SAVED=""
[[ -f "$STATE_FILE" ]] && read -r SAVED < "$STATE_FILE" 2>/dev/null || true
TERM_LINES="$(compute_boot_lines "$SAVED" "$TPUT_LINES")"

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
  command -v tmux >/dev/null && "${TM[@]}" kill-session -t "$SESSION" 2>/dev/null || true
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
# HUP MUSS dabei sein: schließt man das Terminalfenster, kriegt dieses Skript
# (es hängt in `tmux attach-session`) ein SIGHUP. Ohne HUP im Trap stirbt es
# OHNE cleanup → Backend bleibt als Waise auf :5000 zurück ("läuft noch" beim
# nächsten Start). Mit HUP räumt es Session + Backend auch dann ab.
trap cleanup INT TERM HUP EXIT

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
  "${TM[@]}" kill-session -t "$SESSION" 2>/dev/null || true
  # Session SOFORT in der echten Terminalgröße erzeugen (-x/-y). SONST: eine
  # detached Session startet in der tmux-Default-Größe (80x24); das gleich danach
  # laufende `split-window -l N` (im attach unten) rechnet das N gegen diese 24
  # statt gegen die echten z.B. 40 Zeilen — und wenn der Client attached und das
  # Fenster auf 40 wächst, verteilt tmux den Zuwachs PROPORTIONAL auf beide Panes,
  # die untere bash wird also größer als N. Der after-resize-pane-Hook merkt sich
  # diesen aufgeblähten Wert → nächster Start noch höher → die bash kroch bei
  # jedem Neustart nach oben. Mit -x/-y gibt es kein Nachwachsen, N bleibt N.
  size_args=()
  [[ "$TPUT_COLS"  =~ ^[0-9]+$ ]] && size_args+=(-x "$TPUT_COLS")
  [[ "$TPUT_LINES" =~ ^[0-9]+$ ]] && size_args+=(-y "$TPUT_LINES")
  "${TM[@]}" new-session -d -s "$SESSION" "${size_args[@]}" -c "$PWD" "'$SELF' --run-tui"
  # Tastatur/Optionen/Hook setzen (switchen vs. resizen sauber getrennt, Detach
  # aus, Höhen-Hook). Eine Funktion → die pytest-Suite prüft EXAKT dasselbe.
  apply_tui_tmux_keys "$SESSION"
  # Split ERST nach dem Attach, damit die Höhe relativ zur ECHTEN Terminal-
  # größe sitzt. '-d' lässt den Fokus oben auf der TUI; untere bash startet
  # im HOME (fühlt sich an wie ein frisch geöffnetes Terminal).
  "${TM[@]}" attach-session -t "$SESSION" \; \
       split-window -d -v -l "$TERM_LINES" -c "$HOME"
else
  echo "ZENTRALE (tui): tmux nicht installiert — TUI im Vollbild (kein unteres Terminal)." >&2
  echo "Für das angeklebte echte Terminal:  sudo apt install tmux" >&2
  sleep 2
  "$PY" tui/zentrale_tui.py
fi
