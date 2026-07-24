#!/usr/bin/env bash
# =============================================================================
# install_term_theme.sh
# -----------------------------------------------------------------------------
# Richtet die Kopplung des xfce4-terminal an ZENTRALEs Tag/Nacht-Theme ein
# (Sashas Laptop, siehe memory/dashboard.md). Idempotent — mehrfach aufrufbar.
#
# WAS DAS SKRIPT MACHT:
#  1. Symlink ~/.local/bin/zentrale-term-theme -> scripts/zentrale-term-theme
#     (der Applier, der xfce4-terminal live per xfconf-query umfärbt).
#  2. Kopiert die systemd-USER-Units aus deploy/ nach ~/.config/systemd/user/
#     (system-weite Units gehen nicht, das ist eine pro-User-Grafiksession).
#  3. daemon-reload + enable --now des Timers (zieht das Theme jede Minute
#     nach → 05/21-Rotation greift auch ohne laufende TUI).
#  4. Seedet ~/.config/zentrale/theme mit 'auto', falls noch nicht da, und
#     wendet das Theme einmal sofort an.
#
# Diese Units sind USER-Units (kein sudo). Anders als der Pi-Kram in
# install_pi_services.sh läuft hier nichts als root.
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"

mkdir -p "$BIN" "$UNITS" "$HOME/.config/zentrale"

# 1. Applier-Symlink
ln -sf "$REPO/scripts/zentrale-term-theme" "$BIN/zentrale-term-theme"
echo "symlink: $BIN/zentrale-term-theme -> $REPO/scripts/zentrale-term-theme"

# 2. Units aus dem Repo installieren
for u in zentrale-term-theme.service zentrale-term-theme.timer; do
  install -m 0644 "$REPO/deploy/$u" "$UNITS/$u"
  echo "unit: $UNITS/$u"
done

# 3. Timer aktivieren
systemctl --user daemon-reload
systemctl --user enable --now zentrale-term-theme.timer
echo "timer: $(systemctl --user is-active zentrale-term-theme.timer)"

# 4. State seeden + einmal anwenden
[ -f "$HOME/.config/zentrale/theme" ] || printf 'auto\n' > "$HOME/.config/zentrale/theme"
"$BIN/zentrale-term-theme" || true
echo "state: $(cat "$HOME/.config/zentrale/theme")  → angewendet"
