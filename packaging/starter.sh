#!/bin/bash
#
# /usr/bin/zentrale — Starter eines per apt oder pacman installierten ZENTRALE
# (memory/betrieb/verteilung.md, „Paketverwaltung").
#
# Die Paketverwaltung legt das Programm schreibgeschützt nach /usr/lib/zentrale
# (dazu KANAL = apt|pacman). Der Kern sucht seine Daten neben dem Programm
# (<wurzel>/data) — deshalb bekommt jeder Nutzer beim ersten Start einer Fassung
# eine eigene Kopie, aufgebaut wie ein Hub aus install.sh:
#
#   ~/.local/share/zentrale/paket/<fassung>/        Kopie von /usr/lib/zentrale
#   ~/.local/share/zentrale/paket/<fassung>/data -> ../../data
#   ~/.local/share/zentrale/paket/<fassung>/venv -> ../venv
#   ~/.local/share/zentrale/paket/venv/            Python-Pakete (pip, nur hier)
#   ~/.local/share/zentrale/data/                  die Daten (wie bei install.sh)
#
# Nie pip ins System-Python, nie Netz während apt/pacman: das venv entsteht
# beim ersten Start als der Nutzer selbst. Neu gebaut wird es nur, wenn sich
# requirements-basis.txt oder das Python ändert. Updates kommen über die
# Paketverwaltung; `zentrale update` verweigert sich (KANAL).

set -euo pipefail

PAKET="${ZENTRALE_PAKET:-/usr/lib/zentrale}"
HEIM="${ZENTRALE_HEIM:-$HOME/.local/share/zentrale}"
PY="${ZENTRALE_PYTHON:-/usr/bin/python3}"
ORT="$HEIM/paket"

[[ -r "$PAKET/VERSION" ]] || { echo "Error: $PAKET is incomplete — reinstall the zentrale package." >&2; exit 1; }
FASSUNG="$(tr -d '[:space:]' < "$PAKET/VERSION")"
ZIEL="$ORT/$FASSUNG"

einrichten() {
  mkdir -p "$ORT" "$HEIM/data"

  # Python-Pakete: ein venv für alle Fassungen, neu nur bei neuen Anforderungen.
  local stempel
  stempel="$("$PY" -c 'import sys; print(sys.version.split()[0])') $(sha256sum < "$PAKET/requirements-basis.txt" | cut -d' ' -f1)"
  if [[ "$(cat "$ORT/venv/.stempel" 2>/dev/null)" != "$stempel" ]]; then
    echo "ZENTRALE: installing Python packages for your user (first start, a few minutes) …" >&2
    rm -rf "$ORT/venv"
    if ! "$PY" -m venv "$ORT/venv" || \
       ! "$ORT/venv/bin/pip" install -q --upgrade pip >/dev/null || \
       ! "$ORT/venv/bin/pip" install -q -r "$PAKET/requirements-basis.txt"; then
      rm -rf "$ORT/venv"
      echo "Error: installing the Python packages failed. Are you online? Run 'zentrale' again to retry." >&2
      exit 1
    fi
    printf '%s\n' "$stempel" > "$ORT/venv/.stempel"
  fi

  # Programm-Kopie dieser Fassung.
  rm -rf "$ZIEL.teil"
  cp -R "$PAKET" "$ZIEL.teil"
  ln -s ../../data "$ZIEL.teil/data"
  ln -s ../venv "$ZIEL.teil/venv"
  if [[ -d "$ZIEL.teil/mitgeliefert/ascii" && ! -d "$HEIM/data/ascii" ]]; then
    cp -R "$ZIEL.teil/mitgeliefert/ascii" "$HEIM/data/ascii"
  fi
  : > "$ZIEL.teil/.fertig"
  rm -rf "$ZIEL"
  mv "$ZIEL.teil" "$ZIEL"

  # Kopien älterer Fassungen weg (die Daten liegen außerhalb).
  local d
  for d in "$ORT"/*/; do
    d="${d%/}"
    case "${d##*/}" in venv|"$FASSUNG") ;; *) rm -rf "$d" ;; esac
  done
}

if [[ ! -e "$ZIEL/.fertig" ]]; then
  mkdir -p "$ORT"
  exec 9> "$ORT/.sperre"
  flock 9                                   # zwei erste Starts gleichzeitig: einer wartet
  [[ -e "$ZIEL/.fertig" ]] || einrichten
  exec 9>&-
fi

exec "$ZIEL/bin/zentrale" "$@"
