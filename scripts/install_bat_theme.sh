#!/usr/bin/env bash
# =============================================================================
# install_bat_theme.sh
# -----------------------------------------------------------------------------
# Hängt bat (auf Debian/Mint heißt das Binary `batcat`) an ZENTRALEs
# Tag/Nacht-Theme. Idempotent — mehrfach aufrufbar.
#
# WAS DAS SKRIPT MACHT:
#  1. Kopiert bat/themes/*.tmTheme nach ~/.config/bat/themes/.
#     KOPIE, kein Symlink: `bat cache --build` liest die Dateien einmal ein und
#     backt sie in themes.bin — ein Symlink brächte keinen Vorteil, aber die
#     Verwirrung, dass ein Repo-Update ohne Cache-Neubau nichts tut.
#  2. Baut den bat-Cache neu (sonst kennt bat die Themes nicht).
#  3. Setzt die --theme-Zeile in ~/.config/bat/config auf den aktuellen Modus.
#
# Wird von install_theme_coupling.sh mit aufgerufen; einzeln aufrufbar, wenn
# sich die Palette geändert hat (dann vorher scripts/build_bat_themes.py).
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Debian/Mint nennen das Binary batcat (Namenskollision mit dem Paket `bat`),
# überall sonst heißt es bat. Wer keins von beidem hat, ist hier fertig.
BAT="$(command -v batcat || command -v bat || true)"
if [ -z "$BAT" ]; then
  echo "bat/batcat nicht installiert — übersprungen"
  exit 0
fi

THEME_SRC="$REPO/bat/themes"
THEME_DST="${BAT_CONFIG_DIR:-$HOME/.config/bat}/themes"

if [ ! -d "$THEME_SRC" ]; then
  echo "FEHLER: $THEME_SRC fehlt — erst scripts/build_bat_themes.py laufen lassen" >&2
  exit 1
fi

# 1. Themes ablegen
mkdir -p "$THEME_DST"
cp -f "$THEME_SRC"/*.tmTheme "$THEME_DST/"
echo "themes: $THEME_DST ($(ls -1 "$THEME_DST"/*.tmTheme | wc -l) Dateien)"

# 2. Cache bauen — ohne das kennt bat nur seine eingebauten Themes.
"$BAT" cache --build >/dev/null 2>&1 || {
  echo "FEHLER: '$BAT cache --build' fehlgeschlagen" >&2
  exit 1
}
echo "cache : neu gebaut"

# 3. Applier verlinken und einmal anwenden
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
ln -sf "$REPO/scripts/zentrale-bat-theme" "$BIN/zentrale-bat-theme"
echo "symlink: $BIN/zentrale-bat-theme -> $REPO/scripts/zentrale-bat-theme"
"$BIN/zentrale-bat-theme" || true
echo "state : $("$BIN/zentrale-bat-theme" --dry-run)"

# Kurze Sichtprüfung, dass bat die Themes wirklich geschluckt hat.
if ! "$BAT" --list-themes 2>/dev/null | grep -q '^zentrale-'; then
  echo "WARNUNG: bat listet keine zentrale-Themes — Cache-Pfad prüfen" >&2
fi
