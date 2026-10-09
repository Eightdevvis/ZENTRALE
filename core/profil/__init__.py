# core/profil/__init__.py
#
# Die Schienen-Registry: welcher Prompt und welches Tool-Set gehen an welches
# Modell.
#
# ── Das Bild ────────────────────────────────────────────────────────────
# Ein Zug, mehrere Schienen. Der Zug ist der Kern: Tool-Ausfuehrung, Kalender,
# Graph, Erlaubnis-Gate, Event-Protokoll, der Loop. Der ist fuer jedes Modell
# derselbe und wird nicht angefasst.
#
# Die Schiene ist alles, was die ANREDE ausmacht: Prompt-Texte, welche Tools
# ueberhaupt angeboten werden, wie sie beschrieben sind, wie sie heissen.
# Genau da unterscheiden sich Modelle — und genau da haben sie sich bisher
# gegenseitig im Weg gestanden.
#
#   klein  qwen3.5:9b und Verwandte. Braucht Krücken: ein `antwort`-Tool gegen
#          die "ich pruefe..."-und-Stopp-Aussetzer, Anti-Konfabulations-Regeln,
#          eine ausbuchstabierte Choreografie im Tool-Schema.
#   gross  Frontier-Modelle (Claude, GPT, Grok …). Braucht nichts davon und
#          zahlt es sonst bei JEDEM Turn mit.
#
# Wer spaeter mit weiteren Modellgroessen experimentiert, legt eine weitere
# Datei daneben, statt an einem gemeinsamen Prompt zu ziehen, an dem schon
# drei andere haengen.
#
# ── Tool-Namen: ein Vokabular fuer den Kern ─────────────────────────────
# Ein Profil darf seine Tools nennen wie es will. Der Kern soll aber nicht
# fuer jede Schiene eine eigene if-Kette haben. Also: der Kern spricht EIN
# (englisches) Vokabular, und `kanonisch()` uebersetzt darauf.
#
# Die Tabelle nimmt bewusst BEIDE Schreibweisen an. Deshalb laufen die vier
# scripts/bench_*.py, die den Tool-Loop eigenstaendig nachbauen und die
# deutschen Namen hart matchen, unveraendert weiter.

#
# Seit 2026-10-07 stehen die Namen im Werkzeug-Register
# (core/werkzeug_register.py, Feld klein_name); ALIASE und kanonisch() hier
# sind Durchreichen dorthin.

import werkzeug_register

from . import klein
from . import gross
from . import modelle

PROFILE = {
    "klein": klein,
    "gross": gross,
}

# Deutsche Alt-Namen → kanonische. Englische bleiben, wie sie sind.
ALIASE = werkzeug_register.ALIASE
kanonisch = werkzeug_register.kanonisch


def hol(name: str):
    """Ein Profil nach Namen. Unbekannt → klein (die vorsichtigere Schiene)."""
    return PROFILE.get(name) or klein


def fuer_backend(backend: str, modell: str | None = None):
    """Welche Schiene gehoert zu diesem Backend?

    lokal → klein, cloud → gross. Uebersteuerbar per `chat_profil` in
    data/ai_config.json bzw. ZENTRALE_CHAT_PROFIL — zuruecktauschen ist eine
    Zeile, das ist der Sinn der Sache.

    modell (2026-10-09): hat das Modell ein Profil (Einstellung
    `modell_profile`, profil/modelle/), kommt die Schiene mit Profil darüber
    zurück; sonst die Schiene selbst, unverändert.
    """
    wahl = _aus_config()
    if wahl:
        basis = hol(wahl)
    else:
        basis = gross if backend == "cloud" else klein
    return modelle.fuer(modell, basis) if modell else basis


def _aus_config() -> str | None:
    try:
        import ai_config
        wert = ai_config.setting("chat_profil")
        return str(wert) if wert else None
    except Exception:
        return None
