# core/profil/gross.py
#
# Die Schiene fuer GROSSE Modelle — Claude, GPT, Grok, Gemini und was sonst
# noch als Frontier-Modell durch den Cloud-Pfad kommt.
#
# ── Stand: noch identisch zu `klein` ────────────────────────────────────
# Bewusst so. Der Umzug nach profil/ (Schienen legen) und das Zuschneiden
# (Ballast abwerfen) sind zwei verschiedene Arbeiten, und sie in einem Schritt
# zu machen hiesse: wenn danach etwas kaputt ist, weiss keiner welcher der
# beiden Schritte es war. Also erst die Schienen, mit unveraendertem
# Verhalten, dann der Schnitt.
#
# Was hier weichen wird, sobald geschnitten wird — und warum:
#
#   `antwort`-Tool + ANTWORT_SUFFIX
#       Ein Konstrukt gegen die "ich pruefe..."-und-dann-Stopp-Aussetzer des
#       9B. Ein starkes Modell antwortet einfach. Spart das Schema UND eine
#       Tool-Runde pro Nutzung.
#
#   _ASCII_MARKER_PROMPT (755 Z.) + _DASHBOARD_VIEW (1.094 Z.)
#       Anweisungen an eine aufgegebene Front: die TUI verwirft ascii- und
#       cinema-Events (tui/zentrale_tui.py). Dafuer zahlt man sonst taeglich.
#
#   Die 9B-Belehrungen aus den Meta-Regeln
#       "nur reale Woerter", "vertraute APIs aus dem Pretraining", die
#       sechsfach wiederholten Tool-Ermahnungen. Was BLEIBT ist die
#       Subjekt-Grenze — das ist keine Modellgroesse, das ist der Unterschied
#       zwischen "du fuehlst dich einsam" und "ich bin einsam seit dem 19.
#       Mai".
#
#   Die ⚠-Eskalations-Choreografie in der read_calendar-Beschreibung
#       Gehoert nach Python: kalender.day_warnings rechnet die Warnungen
#       ohnehin schon aus.
#
# Bis dahin: alles von klein, unveraendert.

from .klein import (                              # noqa: F401
    _SYSTEM_PROMPT, _CAPABILITIES_PROMPT, _MIC_INPUT_HINT, _DASHBOARD_VIEW,
    ANTWORT_SUFFIX, _ASCII_MARKER_PROMPT, TOOLS,
    SYSTEM, CAPABILITIES, MIC_HINT, DASHBOARD,
    TERMINAL, MERKMALE, system,
)

NAME = "gross"
