#!/usr/bin/env bash
# =============================================================================
# install_theme_coupling.sh   (hieß bis 2026-07-25 install_term_theme.sh)
# -----------------------------------------------------------------------------
# Richtet die Kopplung der UMGEBUNG an ZENTRALEs Tag/Nacht-Theme ein
# (Sashas Laptop, siehe memory/system/dashboard.md). Idempotent — mehrfach aufrufbar.
#
# Alle Ziele hängen an EINER Datei: ~/.config/zentrale/theme (auto|day|night).
#
# WAS DAS SKRIPT MACHT:
#  1. Applier-Symlinks nach ~/.local/bin:
#       zentrale-term-theme    → xfce4-terminal live per xfconf-query umfärben
#       zentrale-browser-theme → Portal-Farbschema setzen; Brave (Flatpak) zieht
#                                live nach, UI + prefers-color-scheme
#       zentrale-desktop-theme → GTK-/Fensterrahmen-Theme (day: Mint-L-Sand,
#                                night: Mint-L-Darker-Aqua); --restore macht es
#                                rueckgaengig (Vorzustand ist gesichert)
#  2. Kopiert die systemd-USER-Units aus deploy/ nach ~/.config/systemd/user/
#     (system-weite Units gehen nicht, das ist eine pro-User-Grafiksession).
#     Alte Namen zentrale-term-theme.{service,timer} werden abgeräumt.
#  3. daemon-reload + enable --now des Timers (zieht das Theme jede Minute
#     nach → 05/21-Rotation greift auch ohne laufende TUI).
#  4. Seedet ~/.config/zentrale/theme mit 'auto', falls noch nicht da, und
#     wendet das Theme einmal sofort an.
#  5. Baut die Icon-Themes ZENTRALE-Cyber/-Paper (build_icon_themes.py) und
#     hängt nvim mit ein (install_nvim_theme.sh), falls nvim da ist.
#
# Diese Units sind USER-Units (kein sudo). Anders als der Pi-Kram in
# install_pi_services.sh läuft hier nichts als root.
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HOME/.local/bin"
UNITS="$HOME/.config/systemd/user"

mkdir -p "$BIN" "$UNITS" "$HOME/.config/zentrale"

# 1. Applier-Symlinks
for a in zentrale-term-theme zentrale-browser-theme zentrale-desktop-theme; do
  ln -sf "$REPO/scripts/$a" "$BIN/$a"
  echo "symlink: $BIN/$a -> $REPO/scripts/$a"
done

# 2. Alte Unit-Namen abräumen (hießen bis 2026-07-25 …-term-theme.*), dann neu
if systemctl --user list-unit-files 'zentrale-term-theme.*' 2>/dev/null | grep -q zentrale-term-theme; then
  systemctl --user disable --now zentrale-term-theme.timer 2>/dev/null || true
  rm -f "$UNITS/zentrale-term-theme.service" "$UNITS/zentrale-term-theme.timer"
  echo "aufgeräumt: alte zentrale-term-theme-Units entfernt"
fi
for u in zentrale-theme.service zentrale-theme.timer; do
  install -m 0644 "$REPO/deploy/$u" "$UNITS/$u"
  echo "unit: $UNITS/$u"
done

# 3. Timer aktivieren
systemctl --user daemon-reload
systemctl --user enable --now zentrale-theme.timer
echo "timer: $(systemctl --user is-active zentrale-theme.timer)"

# 4. State seeden + einmal anwenden
[ -f "$HOME/.config/zentrale/theme" ] || printf 'auto\n' > "$HOME/.config/zentrale/theme"
"$BIN/zentrale-term-theme"    || true
"$BIN/zentrale-browser-theme" || true
"$BIN/zentrale-desktop-theme" || true
echo "state: $(cat "$HOME/.config/zentrale/theme")  → angewendet"

# 5a. Icon-Themes bauen (Symlink-Overlay über Papirus, ein paar KB)
if [ -d /usr/share/icons/Papirus-Dark ]; then
  PY="$REPO/venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
  [ -n "$PY" ] && "$PY" "$REPO/scripts/build_icon_themes.py" || true
fi

# 5b. nvim mitnehmen (eigener Installer, weil er in ~/.config/nvim/plugin schreibt)
if command -v nvim >/dev/null 2>&1; then
  bash "$REPO/scripts/install_nvim_theme.sh"
fi
