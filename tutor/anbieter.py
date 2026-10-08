# tutor/anbieter.py
#
# Die Naht des Tutors zur EINEN Straße des Kerns (seit 2026-10-08).
#
# Vorher hatte der Tutor eine eigene Anbieter-Liste (tutor/providers.py) und
# zwei eigene Cloud-Schleifen (tutor/cloud.py für Anthropic,
# tutor/openai_compat.py für Qwen & Co.) — eine zweite Wahrheit über Endpunkte
# und Modelle, und jede Verbesserung am Kern (Kosten buchen, Stoppen, Fehler
# als Event statt Antworttext, Tool-Fehler fangen) kam beim Tutor nie an.
# Sasha: „eine straße, wo jedes auto drauf fahren könnte".
#
# Jetzt: Anbieter-Liste = core/providers.py (inkl. Datenschutz-Angabe), Weg =
# kern.fahrzeug()/kern.fahren(). Dieses Modul ist das EINZIGE im Tutor, das
# diese beiden Kern-Module anfasst — wer den Tutor je wieder rausziehen will,
# ersetzt nur diese Datei.
#
# Sandbox bleibt: fahren() bekommt die Vokabel-Tools des Tutors und
# tutor.tools.execute_tool (geschlossene Allowlist). Der Kern schaltet für ein
# fremdes Tool-Set Gedächtnis, Gate und Bild-Marker ab.
#
# Einstellungen (tutor/config.py, Env TUTOR_<NAME>):
#   max_tokens   harter Deckel je Antwort. Standard je Art: OpenAI-kompatibel
#                140 (gegen echtes qwen gemessen, memory/tutor/
#                tutor_persona_tuning.md), Anthropic 2000 (Denken zählt mit).
#                Ein Wert im Sprachprofil (max_tokens) geht vor.
#   temperature  0.4 (nur OpenAI-kompatibel; Anthropic lehnt sie ab Opus 4.7 ab)
#   effort       'low' (nur Anthropic)

import kern          # basic core: die Straße
import providers     # basic core: die eine Anbieter-Liste

from . import config

LOKAL = providers.LOKAL

_MAX_TOKENS_JE_ART = {"openai_compat": 140, "anthropic": 2000}


def eintrag(name: str) -> dict:
    """Anbieter-Eintrag (lokal oder Cloud); unbekannt → der lokale."""
    return providers.eintrag(name) or providers.eintrag(LOKAL)


def bekannt(name: str) -> bool:
    return bool(providers.eintrag(name))


def trains_on_data(name: str) -> bool:
    return providers.trains_on_data(name)


def default_model(name: str):
    return eintrag(name).get("default_model")


def waehlbar(name: str) -> bool:
    """Kann der Tutor diesen Anbieter jetzt nehmen? Lokal immer; Cloud nur
    mit Key. (Ersetzt das alte `enabled` der Tutor-Liste: dort hieß es
    „verdrahtet" — auf der einen Straße ist jeder Anbieter verdrahtet.)"""
    import os
    e = eintrag(name)
    if e.get("kind") == "ollama":
        return True
    return bool(os.environ.get(e.get("key_env") or ""))


def liste() -> list:
    """Alle Anbieter fürs UI (Einstellungen im Zimmer)."""
    return [{"name": n, "default_model": e.get("default_model"),
             "trains_on_data": providers.trains_on_data(n),
             "jurisdiction": e.get("jurisdiction"), "enabled": waehlbar(n)}
            for n, e in providers.alle().items()]


def _zahl(name, standard, art=float):
    try:
        v = config.setting(name, None)
        return art(v) if v not in (None, "") else standard
    except (TypeError, ValueError):
        return standard


def fahren(anbieter: str, modell, verlauf: list, *, system: str, tools: list,
           tool_executor, max_tokens: int = None):
    """Einen Tutor-Zug fahren. Generator mit dem Event-Protokoll des Kerns
    (Text-Tokens + dicts: werkzeug, reflect, fehler) — der Aufrufer filtert.
    max_tokens: Wert aus dem Sprachprofil (None → Einstellung → Standard je Art)."""
    fz = kern.fahrzeug(anbieter if bekannt(anbieter) else LOKAL, modell)
    # Reihenfolge wie vorher: Sprachprofil > Einstellung > Standard je Art.
    deckel = max_tokens or _zahl("max_tokens", None, int) \
        or _MAX_TOKENS_JE_ART.get(fz.art)
    yield from kern.fahren(
        fz, verlauf, system=system, tools=tools, tool_executor=tool_executor,
        max_tokens=deckel, temperatur=_zahl("temperature", 0.4),
        effort=str(config.setting("effort", "low") or "low"))
