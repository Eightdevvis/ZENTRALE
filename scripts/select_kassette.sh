#!/usr/bin/env bash
#
# select_kassette.sh — Einstieg für `zentrale`: zeigt das Kassetten-Menü.
#
# Das Menü (tui/select_kassette.py) lässt per ↑/↓ + Enter eine Kassette wählen,
# spielt einen Regenbogen-Ladebalken und exec't dann in das passende Start-
# Skript (start_local.sh / start_laptop.sh / start_tui.sh).
#
# Direkt ohne Menü: `zentrale-laptop` bzw. `zentrale-tui`.

set -u
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$SCRIPT_DIR/.."

PY="venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY nicht gefunden (siehe memory/betrieb/setup.md)." >&2
  exit 1
fi

exec "$PY" tui/select_kassette.py
