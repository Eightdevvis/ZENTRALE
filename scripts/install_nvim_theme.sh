#!/usr/bin/env bash
# =============================================================================
# install_nvim_theme.sh
# -----------------------------------------------------------------------------
# Hängt die nvim-Theme-Kopplung ein (Gegenstück zu install_term_theme.sh):
# nvim folgt derselben Datei ~/.config/zentrale/theme wie das xfce4-terminal —
# day → zentrale-paper, night → zentrale-cyber, auto → nach Uhrzeit.
#
# WAS DAS SKRIPT MACHT (idempotent, mehrfach aufrufbar, kein sudo):
#   Schreibt ~/.config/nvim/plugin/zentrale_theme.lua — nvim sourced ALLES in
#   plugin/ automatisch beim Start. Diese eine Datei hängt nur das ZENTRALE-Repo
#   in die runtimepath und ruft setup() auf.
#
# WICHTIG: Sashas init.lua wird NICHT angefasst (kein Einfügen in fremde
# Dateien, kein Marker-Block, nichts kaputtzumachen). Deinstallieren =
# die eine Datei löschen:  rm ~/.config/nvim/plugin/zentrale_theme.lua
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGDIR="${XDG_CONFIG_HOME:-$HOME/.config}/nvim/plugin"
HOOK="$PLUGDIR/zentrale_theme.lua"

command -v nvim >/dev/null 2>&1 || { echo "nvim nicht gefunden — nichts zu tun." >&2; exit 0; }

mkdir -p "$PLUGDIR" "${XDG_CONFIG_HOME:-$HOME/.config}/zentrale"

cat > "$HOOK" <<LUA
-- ZENTRALE-Theme-Kopplung — ERZEUGT von scripts/install_nvim_theme.sh.
-- Nicht hier editieren: der Code liegt im ZENTRALE-Repo unter nvim/.
-- Entfernen: diese Datei löschen.
vim.opt.runtimepath:append("$REPO/nvim")
pcall(function() require("zentrale_theme").setup() end)
LUA
echo "hook: $HOOK -> $REPO/nvim"

# Theme-State seeden (falls die TUI noch nie lief), damit resolve() etwas findet.
STATE="${XDG_CONFIG_HOME:-$HOME/.config}/zentrale/theme"
[ -f "$STATE" ] || printf 'auto\n' > "$STATE"
echo "state: $(cat "$STATE")"

# Rauchtest: headless laden und den aufgelösten Modus ausgeben. Schlägt das fehl,
# ist die Kopplung kaputt — besser JETZT sehen als beim nächsten Öffnen.
mode="$(nvim --headless -u NONE \
  --cmd "set rtp+=$REPO/nvim" \
  -c 'lua local t = require("zentrale_theme"); t.setup(); io.write(t.current or "?")' \
  -c q 2>/dev/null || true)"
echo "rauchtest: nvim löst auf → ${mode:-FEHLER}"
[ -n "$mode" ] && [ "$mode" != "?" ]
