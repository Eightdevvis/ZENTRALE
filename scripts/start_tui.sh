#!/usr/bin/env bash
#
# start_tui.sh — ZENTRALE als Terminal-Kassette (KEIN Browser).
#
# Fährt das Backend ki-frei hoch (ZENTRALE_KASSETTE=tui → kein Ollama-Warmup,
# kein News-Fetcher, KI-Endpoints abgeriegelt; siehe core/kassette.py) und
# startet dann die curses-TUI (tui/zentrale_tui.py) im VOLLBILD des aktuellen
# Terminals. Kein tmux, kein Split, kein angeklebtes zweites Terminal —
# einfach das Dashboard in dem Terminal, in dem der Befehl abgesetzt wurde.
#
# Beenden mit 'q': schließt das FENSTER. Läuft das Backend als Dienst
# (zentrale-kern.service, der Normalfall seit 19.08.2026), bleibt es stehen —
# sonst wäre der Takt tot, sobald kein Fenster offen ist. Nur ein Backend, das
# dieses Skript selbst gestartet hat, wird beim Beenden mitgenommen.
#
# Das Backend-stdout geht in eine LOGDATEI, NICHT ins Terminal — sonst würde
# es die curses-Oberfläche zerschießen. Die Logs erscheinen ohnehin im
# stdout-Panel der TUI (über /api/state). Logdatei live mitlesen:
#     tail -f /tmp/zentrale-tui-backend.log

set -u

# ── Exit-Codes (damit ein Fehlstart diagnostizierbar ist statt "exited") ──
#   0  sauberer Quit
#   2  venv/Python fehlt
#   3  Port :5000 schon belegt (verwaiste/fremde ZENTRALE) — NICHT zweimal starten
#   4  Backend beim Hochfahren gestorben (Import-/Code-Fehler → Backend-Log)
#   5  Backend-API nach 15 s nicht erreichbar (hängt → Backend-Log)
#   1  TUI selbst abgestürzt (kein sauberer Quit → /tmp/zentrale-tui-crash.log)

# ── Ins Projekt-Root (Skript liegt in scripts/, Symlink wird aufgelöst) ──
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "FEHLER (2): $PY nicht gefunden. Bitte erst venv aufsetzen (siehe memory/betrieb/setup.md)." >&2
  exit 2
fi

# ── Test-Riegel einhaengen, falls er hier noch fehlt ─────────────────────
# Der Riegel (scripts/zentrale_testguard.py) haelt Testlaeufe aus veralteten
# Arbeitsverzeichnissen davon ab, die LAUFENDE ~/.config/zentrale/theme
# umzuschalten — der Grund steht in memory/system/dashboard.md.
#
# Er haengt im venv, und das venv liegt NICHT in git. Auf jedem Knoten (Laptop,
# PC, Pi) muss er also einmal eingehaengt werden. Genau das wird vergessen:
# der Riegel war auf einer Maschine scharf und auf der naechsten nicht, und
# dort sprang das Theme munter weiter. Deshalb haengt er sich hier selbst ein,
# still und idempotent — der Start ist die Stelle, die auf JEDEM Knoten laeuft.
if ! compgen -G "venv/lib/python*/site-packages/zentrale_testguard.pth" >/dev/null; then
  scripts/zentrale-venv-guard >/dev/null 2>&1 || true
fi

export ZENTRALE_KASSETTE=tui
BACKEND_LOG="/tmp/zentrale-tui-backend.log"

# ── Ist :5000 schon belegt? KLARE Ansage statt stillem Zweit-Backend ─────
# Antwortet etwas auf :5000, ist es ein verwaistes oder fremdes Backend. Würden
# wir jetzt ein zweites starten, könnte es den Port nicht binden (Flask-Thread
# stirbt still), die Readiness-Prüfung träfe das FALSCHE Backend, und die TUI
# liefe gegen veralteten Code — genau die Art "läuft nicht, keine Ahnung warum".
# Lieber hart abbrechen mit Aufräum-Tipp.
ATTACHED=0
if curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null; then
  # ── Seit 19.08.2026: ANHÄNGEN ist der Normalfall ──────────────────────
  # ZENTRALE ist eine Systemeinheit geworden: das Backend läuft als
  # Benutzer-Dienst (zentrale-kern.service) und muss weiterlaufen, wenn kein
  # Fenster offen ist — sonst stirbt der Takt, sobald Sasha die TUI zumacht,
  # und sie erinnert nie wieder an etwas, während er woanders arbeitet.
  #
  # Vorher hat dieses Skript ein laufendes Backend ZURÜCKGEHOLT, also
  # abgeschossen und neu gestartet. Gegen einen Dienst wäre das ein Kampf:
  # jede TUI würde ihn killen, systemd startet ihn neu, und der Takt-
  # Tageszustand wäre bei jedem Fensteröffnen frisch.
  #
  # Also: antwortet dort etwas Gesundes, hängen wir uns dran und fassen es
  # nicht an — weder beim Start noch beim Beenden.
  if [[ "${ZENTRALE_TUI_FRESH:-}" != "1" ]]; then
    echo "ZENTRALE (tui) — Backend läuft bereits, hänge mich dran."
    ATTACHED=1
  fi
fi

if [[ "$ATTACHED" != "1" ]] && curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null; then
  # ZENTRALE_TUI_FRESH=1: bewusst frisch starten (Entwicklung — die TUI soll
  # gegen NEUEN Backend-Code laufen, nicht gegen den seit Stunden laufenden).
  # Erkennung wie bisher: ZENTRALE_KASSETTE=tui im Prozess-Environ, damit wir
  # NIE ein fremdes/monolith-Backend treffen.
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
BACKEND_PID=""
if [[ "$ATTACHED" != "1" ]]; then
  "$PY" core/main.py > "$BACKEND_LOG" 2>&1 &
  BACKEND_PID=$!
fi

cleanup() {
  # NUR beenden, was wir selbst gestartet haben. Ein Backend, an das wir uns
  # nur drangehängt haben, gehört dem Dienst — es hier zu killen wäre genau
  # der Fehler, den die Systemeinheit beseitigen soll.
  [[ -n "$BACKEND_PID" ]] || return 0
  kill "$BACKEND_PID" 2>/dev/null || true
  wait "$BACKEND_PID" 2>/dev/null || true
}
# HUP MUSS dabei sein: schließt man das Terminalfenster, kriegt dieses Skript
# ein SIGHUP. Ohne HUP im Trap stirbt es OHNE cleanup → Backend bleibt als
# Waise auf :5000 zurück ("läuft noch" beim nächsten Start).
trap cleanup INT TERM HUP EXIT

# ── Auf die Flask-API warten (max ~15 s) ────────────────────────────────
ready=0
if [[ "$ATTACHED" == "1" ]]; then
  ready=1
else
  echo "ZENTRALE (tui) — Backend startet, warte auf API …"
  for _ in $(seq 1 30); do
    if curl -sf -o /dev/null http://localhost:5000/api/state 2>/dev/null; then ready=1; break; fi
    # Backend schon gestorben? Dann raus mit Log-Hinweis (Code 4 = Code-/Import-Fehler).
    kill -0 "$BACKEND_PID" 2>/dev/null || { echo "FEHLER (4): Backend abgebrochen — siehe $BACKEND_LOG:" >&2; tail -n 20 "$BACKEND_LOG" >&2; exit 4; }
    sleep 0.5
  done
fi
if [[ "$ready" != "1" ]]; then
  echo "FEHLER (5): Backend-API nach 15s nicht erreichbar — siehe $BACKEND_LOG:" >&2
  tail -n 20 "$BACKEND_LOG" >&2
  exit 5
fi

# ── TUI im Vollbild ─────────────────────────────────────────────────────
"$PY" tui/zentrale_tui.py
rc=$?

# Kein sauberer Quit? Dann die Logs zeigen — curses hat das Terminal beim
# Beenden zurückgesetzt, die Meldungen bleiben also im Terminal lesbar stehen
# (früher killte tmux die Pane samt Fehlermeldung, deshalb die Warte-Taste).
if [[ "$rc" -ne 0 ]]; then
  echo >&2
  echo "════ ZENTRALE-TUI mit Code $rc beendet — kein sauberer Quit ════" >&2
  if [[ -f /tmp/zentrale-tui-crash.log ]]; then
    echo "── TUI-Crash-Log ─────────────────────────────────" >&2
    cat /tmp/zentrale-tui-crash.log >&2
  fi
  echo "── Backend-Log ($BACKEND_LOG), letzte Zeilen ─────" >&2
  tail -n 15 "$BACKEND_LOG" 2>/dev/null >&2
fi

exit "$rc"
