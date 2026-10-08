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

from dataclasses import dataclass

import ai
import ai_backends
import cloud
import cloud_openai
import providers
import state
import werkzeug_schleife

# Welcher Cloud-Weg welchen Dialekt spricht (providers.py: `kind`). Ein neuer
# Dialekt ist eine Zeile hier und ein Adapter für die Werkzeug-Schleife.
CLOUD_WEGE = {
    "anthropic":     cloud,
    "openai_compat": cloud_openai,
}
# Alle Wege, das lokale Ollama eingeschlossen (für fahren()).
WEGE = {"ollama": ai, **CLOUD_WEGE}


# ── Die Straße: Fahrzeug + fahren (2026-10-08) ─────────────────────────
# Sasha: „anbieter, modell, lokal oder cloud … einfach nur wie variablen."
# fahrzeug() ist die EINE Stelle, die aus einem Anbieter-Namen (oder der
# aktuellen Wahl) und einem Modell den Weg auflöst. fahren() fährt ihn mit
# einem FREMDEN Prompt und Tool-Set — so fährt der Tutor (tutor/anbieter.py)
# auf derselben Straße wie der Chat, statt eigene Cloud-Schleifen zu halten.
# Der Chat selbst geht weiter über chat() (sein Prompt hängt an der Schiene).

@dataclass(frozen=True)
class Fahrzeug:
    anbieter: str          # 'local', 'claude', 'qwen', …
    art: str | None        # 'ollama' | 'anthropic' | 'openai_compat' | None (unbekannt)
    modell: str | None     # None = der Weg nimmt seinen Standard


def fahrzeug(anbieter: str | None = None, modell: str | None = None) -> Fahrzeug:
    """Anbieter + Modell → Fahrzeug. anbieter None/'auto' → wer gerade dran
    ist (Cloud-Anbieter laut ai_backends, sonst lokal). modell None → das für
    diesen Anbieter eingestellte (ai_backends.chat_model) bzw. sein Standard."""
    if anbieter in (None, "", "auto"):
        anbieter = ai_backends.cloud_provider() or providers.LOKAL
    e = providers.eintrag(anbieter)
    art = e.get("kind")
    if not modell and art in CLOUD_WEGE:
        modell = ai_backends.chat_model(anbieter) or e.get("default_model")
    return Fahrzeug(anbieter, art, modell or None)


def fahren(fz: Fahrzeug, verlauf, *, system: str, tools: list,
           tool_executor, max_tokens: int = None, temperatur: float = None,
           effort: str = None, abbruch=None):
    """Einen Zug mit fremdem Prompt + Tool-Set fahren (tools=[] = keine).
    Generator mit dem Event-Protokoll der Werkzeug-Schleife; ein unbekannter
    Anbieter gibt ein fehler-Event statt eines Absturzes. Kein Gate, kein
    Gedächtnis, keine Bild-Marker (tutor_mode der Wege). Ob der Aufrufer
    fahren DARF (Drossel), entscheidet er vorher (core/tutor_port.py)."""
    modul = WEGE.get(fz.art)
    if modul is None:
        yield werkzeug_schleife.fehler(
            f"Unbekannter Anbieter '{fz.anbieter}' — keine Straße dorthin.")
        return
    tools = list(tools or [])
    if fz.art == "ollama":
        yield from ai.chat_stream(verlauf, model=fz.modell, system=system,
                                  tools=tools, tool_executor=tool_executor,
                                  abbruch=abbruch)
    elif fz.art == "anthropic":
        yield from cloud.chat_stream(verlauf, model=fz.modell, system=system,
                                     tools=tools, tool_executor=tool_executor,
                                     abbruch=abbruch, max_tokens=max_tokens,
                                     effort=effort)
    else:
        yield from cloud_openai.chat_stream(
            verlauf, model=fz.modell, system=system, tools=tools,
            tool_executor=tool_executor, provider=fz.anbieter, abbruch=abbruch,
            max_tokens=max_tokens, temperatur=temperatur)


def cloud_modul():
    """Das Modul, das den Cloud-Chat für den AKTUELLEN Anbieter bedient —
    oder None, wenn der Kern dessen Dialekt nicht spricht."""
    return CLOUD_WEGE.get(ai_backends.chat_cloud_kind())


def chat(verlauf, *, via_mic=False, backend=None, abbruch=None, projekt=None):
    """Einen Chat-Zug fahren. Generator mit dem Event-Protokoll der
    Werkzeug-Schleife (Text-Tokens, reflect, werkzeug, permission, ascii,
    cinema, fehler).

    backend: schon gefragtes ai_backends.chat_available() (die Chat-Route
    fragt vorher, um bei „gar kein Backend" mit 503 zu antworten); None →
    hier fragen. Gibt es keins, kommt ein fehler-Event statt eines Absturzes.

    abbruch: threading.Event zum Stoppen (state.chat_zug_beginnen). Gesetzt
    → die Schleife hört vor der nächsten Runde bzw. dem nächsten Werkzeug
    auf, ein laufender Anbieter-Strom wird geschlossen, und es kommt ein
    {"gestoppt": True}-Event. None → nicht stoppbar (Takt).

    projekt: id des Projekts, zu dem das Gespräch gehört (core/projekte.py,
    Phase 6, 2026-10-07) — die Cloud-Wege setzen dessen Block in den festen
    Kopf und beschränken read_project_file darauf. Der lokale Weg kennt
    Projekte nicht (klein bleibt, wie es gemessen ist).
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
        extra = {"projekt": projekt} if projekt else {}
        yield from modul.chat_stream(verlauf, via_mic=via_mic, abbruch=abbruch, **extra)
        return
    yield from ai.chat_stream(verlauf, via_mic=via_mic, abbruch=abbruch)
