# core/kern.py
#
# Der eine Einstieg in den KI-Chat: kern.chat(verlauf) wählt den Weg und
# fährt ihn. Jeder, der einen Chat-Zug braucht — die Chat-Route, der Takt —
# ruft NUR das hier.
#
# Bis 2026-10-06 entschied jeder Aufrufer selbst: „Cloud? Dann hol dir von
# ai_backends das passende Modul, sonst nimm ai.chat_stream." Dieselbe
# Weiche stand in der Chat-Route und im Takt-Treiber, und ai_backends musste
# dafür die Cloud-Wege importieren, die ihrerseits ai_backends nach Modell
# und Effort fragen — die letzten acht Kanten im Import-Kreis.
#
# Ab hier gilt: ai_backends sagt, WER denken darf (Einstellungen, Erreichbar-
# keit). Dieses Modul entscheidet, WELCHER WEG das ist, und fährt ihn.
# Sasha: „eine straße, wo jedes auto drauf fahren könnte."
#
# Oberstes Modul des KI-Kerns (Schicht 3, memory/system/bauplan_kern.md).
# Aufbau: memory/ki/kern_aufbau.md.

import ai
import ai_backends
import cloud
import cloud_openai
import state
import werkzeug_schleife

# Welcher Cloud-Weg welchen Dialekt spricht (providers.py: `kind`). Ein neuer
# Dialekt ist eine Zeile hier und ein Adapter für die Werkzeug-Schleife.
CLOUD_WEGE = {
    "anthropic":     cloud,
    "openai_compat": cloud_openai,
}


def cloud_modul():
    """Das Modul, das den Cloud-Chat für den AKTUELLEN Anbieter bedient —
    oder None, wenn der Kern dessen Dialekt nicht spricht."""
    return CLOUD_WEGE.get(ai_backends.chat_cloud_kind())


def chat(verlauf, *, via_mic=False, backend=None):
    """Einen Chat-Zug fahren. Generator mit dem Event-Protokoll der
    Werkzeug-Schleife (Text-Tokens, reflect, werkzeug, permission, ascii,
    cinema, fehler).

    backend: schon gefragtes ai_backends.chat_available() (die Chat-Route
    fragt vorher, um bei „gar kein Backend" mit 503 zu antworten); None →
    hier fragen. Gibt es keins, kommt ein fehler-Event statt eines Absturzes.
    """
    if backend is None:
        backend = ai_backends.chat_available()
    if backend is None:
        yield werkzeug_schleife.fehler("Kein KI-Backend erreichbar.")
        return
    if backend == ai_backends.CLOUD:
        modul = cloud_modul()
        if modul is None:
            # Vorher: AttributeError auf None mitten im Stream.
            yield werkzeug_schleife.fehler(
                f"Der Kern spricht den Dialekt des Anbieters "
                f"'{ai_backends.cloud_provider()}' nicht.")
            return
        state.push_log(f"AI →  KERN: Cloud ({ai_backends.cloud_provider()})")
        yield from modul.chat_stream(verlauf, via_mic=via_mic)
        return
    yield from ai.chat_stream(verlauf, via_mic=via_mic)
