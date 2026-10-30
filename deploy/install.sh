#!/usr/bin/env bash
#
# GERENDERT aus deploy/install.sh.in von scripts/verteilung.py nach deploy/verteilung.toml
# (oeffentlich = false). Nicht von Hand ändern.
#
# ZENTRALE installieren (memory/betrieb/setup.md, „Installieren mit install.sh";
# Schalter: memory/betrieb/verteilung.md).
#
# Öffentlich unter <cloud>/install.sh. Solange deploy/verteilung.toml
# `oeffentlich = false` sagt, gibt es das Paket nur mit Einladungscode aus der
# Cloud; danach ohne Code aus der öffentlichen Quelle. Installiert nichts mit
# Root: fehlende Systempakete werden nur GENANNT (apt: Debian/Ubuntu/Pop!_OS,
# pacman: Arch/EndeavourOS).
#
#   bash install.sh [EINLADUNGSCODE]
#
# Legt an (wie zentrale_cli/aktualisieren.py):
#   ~/.local/share/zentrale/hub/<fassung>/   Programm + venv
#   ~/.local/share/zentrale/hub/aktuell      Verweis auf die Fassung
#   ~/.local/share/zentrale/data/            die Daten (bleiben bei Updates)
#   ~/.local/bin/zentrale                    Verweis auf hub/aktuell/bin/zentrale
#
# Ein vorhandenes ~/.local/bin/zentrale, das KEIN Verweis in
# ~/.local/share/zentrale ist, wird nie überschrieben (Entwickler-Rechner).

set -euo pipefail

# Adresse der Cloud: beim Rendern aus core/cloud_api.py (VORGABE), Env ZENTRALE_CLOUD gewinnt.
CLOUD_VORGABE=https://zentrale-cloud.sevendevs.workers.dev
CLOUD="${ZENTRALE_CLOUD:-$CLOUD_VORGABE}"
CLOUD="${CLOUD%/}"

# Woher das Paket kommt — beim Bauen aus deploy/verteilung.toml eingesetzt.
# __CLOUD__ und __VERSION__ füllt url_fuer() zur Laufzeit.
OEFFENTLICH=0
NEUESTE_VORLAGE=__CLOUD__/v1/paket
PAKET_VORLAGE=__CLOUD__/v1/paket/__VERSION__.tar.gz
url_fuer() {   # $1 = Vorlage, $2 = Fassung
  local u="${1//__CLOUD__/$CLOUD}"
  printf '%s' "${u//__VERSION__/$2}"
}

HEIM="${ZENTRALE_HEIM:-$HOME/.local/share/zentrale}"
BIN_DIR="${ZENTRALE_BIN_DIR:-$HOME/.local/bin}"
LINK="$BIN_DIR/zentrale"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  FETT=$'\033[1m'; GRUEN=$'\033[32m'; GELB=$'\033[33m'; ROT=$'\033[31m'; AUS=$'\033[0m'
else
  FETT=""; GRUEN=""; GELB=""; ROT=""; AUS=""
fi
sag()    { printf '%s\n' "$*"; }
gut()    { printf '%s✓%s %s\n' "$GRUEN" "$AUS" "$*"; }
warn()   { printf '%s!%s %s\n' "$GELB" "$AUS" "$*"; }
abbruch() { printf '%sError:%s %s\n' "$ROT" "$AUS" "$*" >&2; exit 1; }

sag "${FETT}ZENTRALE installer${AUS}"
sag ""

# ── Distribution erkennen ──────────────────────────────────────────────
FAMILIE="generic"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *" arch "*|*" endeavouros "*|*" manjaro "*) FAMILIE="pacman" ;;
    *" debian "*|*" ubuntu "*|*" pop "*)        FAMILIE="apt" ;;
  esac
fi

FEHLT=()
paket_fuer() {   # $1 = was fehlt → Paketname je Familie
  case "$FAMILIE:$1" in
    apt:python)    echo "python3" ;;
    apt:venv)      echo "python3-venv" ;;
    apt:curl)      echo "curl" ;;
    apt:tar)       echo "tar" ;;
    pacman:python) echo "python" ;;
    pacman:venv)   echo "python" ;;
    pacman:curl)   echo "curl" ;;
    pacman:tar)    echo "tar" ;;
    *)             echo "$1" ;;
  esac
}

# ── Voraussetzungen prüfen ─────────────────────────────────────────────
PY="$(command -v python3 || true)"
if [[ -z "$PY" ]]; then
  FEHLT+=("$(paket_fuer python)")
elif ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  abbruch "Python 3.11 or newer is needed (found $("$PY" -V 2>&1)). Please upgrade Python first."
elif ! "$PY" -c 'import venv, ensurepip' 2>/dev/null; then
  FEHLT+=("$(paket_fuer venv)")
fi
command -v curl >/dev/null 2>&1 || FEHLT+=("$(paket_fuer curl)")
command -v tar >/dev/null 2>&1 || FEHLT+=("$(paket_fuer tar)")

if (( ${#FEHLT[@]} )); then
  sag "Some system packages are missing: ${FETT}${FEHLT[*]}${AUS}"
  case "$FAMILIE" in
    apt)    sag "Install them with your package manager (apt), then run this installer again." ;;
    pacman) sag "Install them with your package manager (pacman), then run this installer again." ;;
    *)      sag "Install them with your distribution's package manager, then run this installer again." ;;
  esac
  exit 1
fi
gut "Python $("$PY" -c 'import platform; print(platform.python_version())'), venv and curl found ($FAMILIE)"

# Nicht nötig, aber hilfreich: Ton im Terminal-Klavier.
if [[ "$FAMILIE" == "apt" ]] && ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
  warn "Optional: install 'libportaudio2' for sound in the terminal piano."
elif [[ "$FAMILIE" == "pacman" ]] && ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
  warn "Optional: install 'portaudio' for sound in the terminal piano."
fi

# ── Verweis prüfen, BEVOR etwas heruntergeladen wird ───────────────────
if [[ -e "$LINK" || -L "$LINK" ]]; then
  if [[ ! -L "$LINK" ]]; then
    abbruch "$LINK already exists and is not a link from a ZENTRALE installation. It was left untouched. (On a developer machine this is expected — use your checkout there.)"
  fi
  ZIEL="$(readlink "$LINK")"
  case "$ZIEL" in
    "$HEIM"/*) ;;
    *) abbruch "$LINK points to $ZIEL, not into $HEIM. It was left untouched." ;;
  esac
fi

# ── Einladungscode (nur solange nicht öffentlich) ──────────────────────
ANHANG=""
OFFLINE_HINWEIS="Are you online?"
if [[ "$OEFFENTLICH" != 1 ]]; then
  CODE="${1:-}"
  if [[ -z "$CODE" ]]; then
    if [[ -r /dev/tty ]]; then
      printf 'Invite code: ' > /dev/tty
      read -r CODE < /dev/tty
    fi
  fi
  CODE="$(printf '%s' "$CODE" | tr -d '[:space:]')"
  [[ -n "$CODE" ]] || abbruch "An invite code is needed to download ZENTRALE."
  CODE_URL="$("$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$CODE")"
  ANHANG="?code=$CODE_URL"
  OFFLINE_HINWEIS="Is the invite code right, and are you online?"
fi

# ── Paket holen und prüfen ─────────────────────────────────────────────
ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT

NEUESTE_URL="$(url_fuer "$NEUESTE_VORLAGE" "")"
HOST="${NEUESTE_URL#*://}"
sag "Asking ${HOST%%/*} for the newest version …"
if ! curl -fsSL --proto '=https,http' -o "$ARBEIT/paket.json" "$NEUESTE_URL$ANHANG"; then
  abbruch "Could not get the package description. $OFFLINE_HINWEIS"
fi
read -r FASSUNG SHA GROESSE < <("$PY" -c '
import json, re, sys
d = json.load(open(sys.argv[1]))
v, s = str(d.get("version", "")), str(d.get("sha256", "")).lower()
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", v) or not re.fullmatch(r"[0-9a-f]{64}", s):
    sys.exit(1)
print(v, s, d.get("groesse") or 0)' "$ARBEIT/paket.json") || abbruch "The server sent an unreadable package description."
gut "Version $FASSUNG ($(( GROESSE / 1000000 )) MB)"

curl -fSL --progress-bar --proto '=https,http' -o "$ARBEIT/paket.tar.gz" \
  "$(url_fuer "$PAKET_VORLAGE" "$FASSUNG")$ANHANG" || abbruch "Download failed."
IST="$("$PY" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ARBEIT/paket.tar.gz")"
[[ "$IST" == "$SHA" ]] || abbruch "The download is damaged (checksum mismatch). Nothing was installed."
gut "Checksum verified"

# ── Auspacken: hub/<fassung>/ ──────────────────────────────────────────
mkdir -p "$HEIM/hub" "$HEIM/data"
ZIEL="$HEIM/hub/$FASSUNG"
mkdir -p "$ARBEIT/aus"
"$PY" - "$ARBEIT/paket.tar.gz" "$ARBEIT/aus" <<'PYEOF'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:gz") as tar:
    if hasattr(tarfile, "data_filter"):
        tar.extractall(sys.argv[2], filter="data")
    else:
        for m in tar.getmembers():
            if m.name.startswith("/") or ".." in m.name.split("/") or not (m.isfile() or m.isdir()):
                sys.exit("unsafe entry in package: " + m.name)
        tar.extractall(sys.argv[2])
PYEOF
OBEN=("$ARBEIT"/aus/*)
[[ ${#OBEN[@]} -eq 1 && -d "${OBEN[0]}" ]] || abbruch "The package has an unexpected layout."
rm -rf "$ZIEL"
mv "${OBEN[0]}" "$ZIEL"
ln -s ../../data "$ZIEL/data"
# Mitgelieferte Vorlagen (ASCII-Bilder) in die Daten, wo noch nichts liegt.
if [[ -d "$ZIEL/mitgeliefert/ascii" && ! -d "$HEIM/data/ascii" ]]; then
  cp -r "$ZIEL/mitgeliefert/ascii" "$HEIM/data/ascii"
fi
gut "Unpacked to $ZIEL"

if [[ -n "${ZENTRALE_REUSE_VENV:-}" ]]; then
  # Developer and test runs only (zentrale dev, tests): link an existing venv
  # instead of building one — seconds instead of minutes, no network.
  [[ -x "$ZENTRALE_REUSE_VENV/bin/python" ]] || abbruch "ZENTRALE_REUSE_VENV has no bin/python: $ZENTRALE_REUSE_VENV"
  ln -sfn "$ZENTRALE_REUSE_VENV" "$ZIEL/venv"
  gut "Python packages: reusing $ZENTRALE_REUSE_VENV"
else
  sag "Installing Python packages (this may take a few minutes) …"
  "$PY" -m venv "$ZIEL/venv"
  "$ZIEL/venv/bin/pip" install -q --upgrade pip >/dev/null
  "$ZIEL/venv/bin/pip" install -q -r "$ZIEL/requirements-basis.txt"
  gut "Python packages installed"
fi

# ── Umschalten und verlinken ───────────────────────────────────────────
ln -sfn "$FASSUNG" "$HEIM/hub/.aktuell-neu"
mv -T "$HEIM/hub/.aktuell-neu" "$HEIM/hub/aktuell"
mkdir -p "$BIN_DIR"
ln -sfn "$HEIM/hub/aktuell/bin/zentrale" "$LINK"
gut "Command installed: $LINK"

# ── Keeper: the background timers, before any login ────────────────────
# memory/hub/building_kit_plan.md 5.2: what keeps a node alive comes with the
# installer, not with a later `setup`. Before login the timers simply exit 0.
# Idempotent; every `zentrale update` runs it again from the new version.
"$LINK" timers install || warn "The background timers could not be set up. Try 'zentrale timers install' later."

# ── PATH ───────────────────────────────────────────────────────────────
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    sag ""
    warn "$BIN_DIR is not in your PATH yet. Add it once, then open a new terminal:"
    case "$(basename "${SHELL:-bash}")" in
      zsh)  sag "    add  export PATH=\"\$HOME/.local/bin:\$PATH\"  to ~/.zshrc" ;;
      fish) sag "    run  fish_add_path ~/.local/bin" ;;
      *)    sag "    add  export PATH=\"\$HOME/.local/bin:\$PATH\"  to ~/.bashrc" ;;
    esac
    ;;
esac

sag ""
"$LINK" welcome || true

# ── Setup wizard (building kit 5.1): account, cloud folder, auto-update,
# keep syncing when logged out, apps. Only with a person at a terminal —
# `curl … | bash` has the pipe as stdin, so the wizard reads the terminal.
if [[ -t 1 ]] && { : < /dev/tty; } 2>/dev/null; then
  sag ""
  "$LINK" setup < /dev/tty || warn "Setup did not finish. Run 'zentrale setup' to pick up where you left off."
fi
