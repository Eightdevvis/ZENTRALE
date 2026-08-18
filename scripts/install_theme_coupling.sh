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
#     (zentrale-bat-theme wird von install_bat_theme.sh verlinkt, s.u. Punkt 5)
#  2. Kopiert die systemd-USER-Units aus deploy/ nach ~/.config/systemd/user/
#     (system-weite Units gehen nicht, das ist eine pro-User-Grafiksession).
#     Alte Namen zentrale-term-theme.{service,timer} werden abgeräumt.
#  3. daemon-reload + enable --now des Timers (zieht das Theme jede Minute
#     nach → 05/21-Rotation greift auch ohne laufende TUI).
#  4. Seedet ~/.config/zentrale/theme mit 'auto', falls noch nicht da, und
#     wendet das Theme einmal sofort an.
#  5. Baut die Icon-Themes ZENTRALE-Cyber/-Paper (build_icon_themes.py), hängt
#     nvim mit ein (install_nvim_theme.sh) und bat (install_bat_theme.sh),
#     jeweils falls das Programm da ist.
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
for a in zentrale-themed zentrale-term-theme zentrale-browser-theme \
         zentrale-desktop-theme zentrale-tmux-theme zentrale-theme-watch; do
  ln -sf "$REPO/scripts/$a" "$BIN/$a"
  echo "symlink: $BIN/$a -> $REPO/scripts/$a"
done

# 2. Alte Units abräumen. Bis 2026-07-25 hiessen sie …-term-theme.*; bis
#    2026-08-18 gab es zentrale-theme.{service,timer}, einen Minuten-Timer, der
#    jede Minute alle Applier anwarf. Den ersetzt jetzt EIN Dienst
#    (zentrale-themed), der nur bei echten Wechseln laeuft.
for alt in zentrale-term-theme zentrale-theme; do
  if systemctl --user list-unit-files "$alt.*" 2>/dev/null | grep -q "$alt"; then
    systemctl --user disable --now "$alt.timer" 2>/dev/null || true
    systemctl --user disable --now "$alt.service" 2>/dev/null || true
    rm -f "$UNITS/$alt.service" "$UNITS/$alt.timer"
    echo "aufgeräumt: alte $alt-Units entfernt"
  fi
done
install -m 0644 "$REPO/deploy/zentrale-themed.service" "$UNITS/zentrale-themed.service"
echo "unit: $UNITS/zentrale-themed.service"

# 3. Dienst aktivieren — er loest auf, schreibt theme.now und stoesst die
#    Applier an. Alle anderen Teilnehmer lesen nur noch theme.now.
systemctl --user daemon-reload
systemctl --user enable --now zentrale-themed.service
echo "dienst: $(systemctl --user is-active zentrale-themed.service)"

# 3b. Beobachter: protokolliert, WER die Theme-Datei aendert. Braucht
#     inotifywait; ohne das Paket wird er einfach nicht aktiviert.
if command -v inotifywait >/dev/null 2>&1; then
  install -m 0644 "$REPO/deploy/zentrale-theme-watch.service" \
                  "$UNITS/zentrale-theme-watch.service"
  systemctl --user daemon-reload
  systemctl --user enable --now zentrale-theme-watch.service
  echo "watch: $(systemctl --user is-active zentrale-theme-watch.service)"
else
  echo "watch: uebersprungen (inotifywait fehlt, Paket inotify-tools)"
fi

# 4. Wunsch-Datei seeden (auto) und den Dienst einmal rechnen lassen. Die
#    Applier ruft er selbst — hier stand frueher eine Liste, die man bei jedem
#    neuen Applier mitpflegen musste.
[ -f "$HOME/.config/zentrale/theme" ] || printf 'auto\n' > "$HOME/.config/zentrale/theme"
"$BIN/zentrale-themed" --once || true
echo "state: wunsch=$(cat "$HOME/.config/zentrale/theme")  ergebnis=$(cat "$HOME/.config/zentrale/theme.now" 2>/dev/null)"

# 5a. Icon-Themes bauen (Symlink-Overlay über Papirus, ein paar KB)
if [ -d /usr/share/icons/Papirus-Dark ]; then
  PY="$REPO/venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
  [ -n "$PY" ] && "$PY" "$REPO/scripts/build_icon_themes.py" || true
fi

# 5b. nvim mitnehmen (eigener Installer, weil er in ~/.config/nvim/plugin schreibt)
if command -v nvim >/dev/null 2>&1; then
  bash "$REPO/scripts/install_nvim_theme.sh"
fi

# 5c. bat mitnehmen (eigener Installer: legt die Themes ab und baut den
#     bat-Cache neu — ohne Cache-Neubau kennt bat eigene Themes nicht).
if command -v batcat >/dev/null 2>&1 || command -v bat >/dev/null 2>&1; then
  bash "$REPO/scripts/install_bat_theme.sh"
fi
