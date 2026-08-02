#!/usr/bin/env bash
# =============================================================================
# morgen_start.sh — das Fenster des Morgen-Messengers aufmachen.
#
# Der Messenger selbst (scripts/morgen_messenger.py) ist eine curses-App und
# braucht ein Terminal. Dieses Skript besorgt ihm eins: klein, mittig, ohne
# Menü- und Werkzeugleisten, und unter i3 als SCHWEBENDES Fenster — sonst
# reißt der Kachel-Manager den halben Bildschirm dafür auf, was für eine
# Morgen-Notiz albern wäre.
#
# Aufruf:
#   scripts/morgen_start.sh            # nur wenn fällig (der Normalfall)
#   scripts/morgen_start.sh --force    # immer, zum Anschauen/Testen
#
# Bewusst zwei getrennte Stellen: WANN aufgemacht wird, entscheidet
# core/morgen.py (is_due) bzw. der Watcher; WIE das Fenster aussieht, steht
# hier. Wer die Größe ändern will, ändert nur diese Datei.
# =============================================================================

set -u

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
TITLE="ZENTRALE · morgen"
# DIE Fenstergröße, in Zeichen. Der Kasten des Messengers füllt genau das aus,
# es gibt keinen Rand dazwischen — hier wird also die Fenstergröße bestimmt.
#   52 Spalten: die längste Tastenzeile ("enter erledigt · l später · …",
#               45 Zeichen) plus Rand.
#   12 Zeilen:  Rahmen, Kopf, Leerzeile, 6 Zeilen Inhalt, Rückmeldung,
#               Tastenzeile, Rahmen.
# Passt der Aufgabentext mal nicht in die 6 Zeilen, kürzt ihn der Messenger
# mit »…« — die Frage darunter bleibt IMMER stehen.
COLS=52
ROWS=12

FORCE=""
[[ "${1:-}" == "--force" ]] && FORCE="--force"

# Schon offen? Dann nicht ein zweites Fenster danebenstellen. (Der Watcher
# ruft lieber einmal zu viel auf — hier ist die Bremse.)
if pgrep -f "morgen_messenger.py" >/dev/null 2>&1; then
    exit 0
fi

# Nichts fällig → gar nicht erst ein Terminal starten. Der Messenger würde
# sich selbst auch sofort beenden, aber dann hätte das Fenster schon kurz
# aufgeblitzt. Der Check kostet nichts (liest zwei JSON-Dateien).
if [[ -z "$FORCE" ]]; then
    python3 - "$ROOT" <<'EOF' || exit 0
import sys, os
sys.path.insert(0, os.path.join(sys.argv[1], 'core'))
import morgen
sys.exit(0 if morgen.is_due() else 1)
EOF
fi

# --- Das Fenster schweben lassen und mittig setzen ---------------------------
#
# Unter i3 (Kachel-Manager) bekäme eine Morgen-Notiz sonst den halben Schirm.
# Gesetzt wird das NACHTRÄGLICH am fertigen Fenster, nicht per `for_window`:
# `for_window` ist eine reine Konfigurations-Direktive — i3-msg weist sie zur
# Laufzeit zurück (getestet, i3 4.23). Ein Kriterien-Kommando auf ein schon
# offenes Fenster geht dagegen. Also: im Hintergrund warten, bis das Fenster
# da ist, dann einmal setzen. Die i3-Konfiguration bleibt unangetastet.
#
# Der Umweg über xdotool statt „i3-msg und gucken, ob's geklappt hat": ein
# Kriterien-Kommando, das auf NICHTS passt, meldet i3 trotzdem als Erfolg —
# daran ließe sich nicht erkennen, ob das Fenster schon existiert.
# WICHTIG: hier wird NUR schweben und mittig gesetzt, NICHT die Größe. Die
# bringt das Terminal über --geometry (COLS×ROWS) schon mit, und i3 behält
# sie beim Umschalten auf schwebend bei. Ein `resize set` in Pixeln wäre
# genau der Fehler, den es hier schon gab: 680×340 px ergaben mit dieser
# Schrift 85×19 Zeichen statt der gewollten 60×14 — das Fenster war fast
# doppelt so groß wie gedacht. In Zeichen zu denken ist auch das einzige,
# was bei anderer Schriftgröße oder DPI noch stimmt.
place_window() {
    local i=0
    while [ $i -lt 50 ]; do                     # max. ~5 s, dann aufgeben
        if xdotool search --name "^${TITLE}\$" >/dev/null 2>&1; then
            if [ "$WM" = "i3" ]; then
                i3-msg -q "[title=\"^${TITLE}\$\"] floating enable, move position center" >/dev/null 2>&1
            else
                # Sonstige WMs setzen das Fenster ohnehin frei; hier nur mittig
                # rücken. -e 0,x,y,-1,-1 — die -1 lassen die Größe unangetastet.
                local geo sw sh wgeo ww wh
                geo="$(xdotool getdisplaygeometry 2>/dev/null)" || return
                sw="${geo% *}"; sh="${geo#* }"
                wgeo="$(xdotool search --name "^${TITLE}\$" getwindowgeometry --shell 2>/dev/null)" || return
                ww="$(sed -n 's/^WIDTH=//p' <<< "$wgeo")"
                wh="$(sed -n 's/^HEIGHT=//p' <<< "$wgeo")"
                [ -n "$ww" ] && [ -n "$wh" ] || return
                wmctrl -r "$TITLE" -e "0,$(( (sw - ww) / 2 )),$(( (sh - wh) / 2 )),-1,-1" 2>/dev/null
            fi
            return
        fi
        sleep 0.1
        i=$((i + 1))
    done
}

WM="other"
pgrep -x i3 >/dev/null 2>&1 && WM="i3"
if command -v xdotool >/dev/null 2>&1; then
    if [ "$WM" = "i3" ] && command -v i3-msg >/dev/null 2>&1; then
        place_window &
    elif command -v wmctrl >/dev/null 2>&1; then
        place_window &
    fi
fi

CMD="cd '$ROOT' && exec python3 scripts/morgen_messenger.py $FORCE"

# --- Terminal aussuchen ------------------------------------------------------
# Reihenfolge nach Eignung für ein kleines Fenster ohne Zierrat. xfce4-terminal
# braucht --disable-server, sonst hängt sich das neue Fenster an einen schon
# laufenden Terminal-Prozess und ignoriert Titel und Geometrie — und genau am
# Titel hängt oben die i3-Regel.
if command -v xfce4-terminal >/dev/null 2>&1; then
    exec xfce4-terminal --disable-server --title="$TITLE" \
        --geometry="${COLS}x${ROWS}" \
        --hide-menubar --hide-toolbar --hide-scrollbar \
        -x bash -c "$CMD"
elif command -v alacritty >/dev/null 2>&1; then
    exec alacritty --title "$TITLE" -o "window.dimensions.columns=$COLS" \
        -o "window.dimensions.lines=$ROWS" -e bash -c "$CMD"
elif command -v kitty >/dev/null 2>&1; then
    exec kitty --title "$TITLE" -o "initial_window_width=${COLS}c" \
        -o "initial_window_height=${ROWS}c" bash -c "$CMD"
elif command -v xterm >/dev/null 2>&1; then
    exec xterm -title "$TITLE" -geometry "${COLS}x${ROWS}" -u8 \
        -fa Monospace -fs 12 -e bash -c "$CMD"
elif command -v gnome-terminal >/dev/null 2>&1; then
    exec gnome-terminal --title="$TITLE" --geometry="${COLS}x${ROWS}" \
        -- bash -c "$CMD"
else
    # Kein Terminal-Emulator: nicht stumm sterben. Wenigstens eine Notiz auf
    # den Schirm, wenn es notify-send gibt — sonst nach stderr (Journal).
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "ZENTRALE" "morgen-messenger: kein terminal gefunden"
    fi
    echo "morgen_start: kein terminal-emulator gefunden" >&2
    exit 1
fi
