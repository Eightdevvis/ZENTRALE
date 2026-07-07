# core/persona_memory.py
#
# Eigenes Gedächtnis pro Sprach-Persona (Ling Ling/zh, Jacqueline/fr, …).
#
# ── Die EINE Grenze: Tutor ↔ Core-KI fassen sich nie an ──────────────────
# Die meisten Personas reden über einen CLOUD-Anbieter (zh→qwen). Würde die
# Persona Sashas privaten Core-Graphen (data/ai_graph.json — das was Sasha dem
# lokalen Offline-Chat erzählt) lesen und an die Cloud schicken, wäre das ein
# Bruch der Sandbox (core/tutor.py). Deshalb hat jede Persona ihren EIGENEN
# Graphen: data/persona_mem_<lang>.json — gleiche graph.py-Mechanik, anderer
# Store. Er enthält nur, was Sasha DIESER Persona erzählt hat. Das ist die
# einzige harte Garantie hier.
#
# ── Was NICHT privat ist (ehrlich) ───────────────────────────────────────
# Läuft die Persona über die Cloud, liegt ihr Gesprächs- UND Memory-Inhalt beim
# Anbieter — das Reden läuft dort, und der Kontext-Block geht jede Session wieder
# mit. Kein Versteck. Die Verdichtung KAPAZITÄTSBASIERT (ai_backends): Ollama da
# → lokal; sonst → Cloud (derselbe Anbieter, der redet); nichts da → auslassen.
# Lokal ist KEIN Privacy-Schutz fürs Tutor-Material (das war eh beim Anbieter),
# nur billiger + offline-fähig, wenn Ollama da ist.
#
# ── Kein Fake-Mensch ─────────────────────────────────────────────────────
# Der Store ist Wissen ÜBER SASHA (aus euren Chats), KEINE erfundene Persona-
# Biografie. Die Persona erinnert sich an dich, spielt aber keinen Menschen
# mit Vergangenheit (siehe tutor_langs.py).

import os
import json
from threading import Lock

import graph
import consolidation
import tutor_langs

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# History wird auf Disk gehalten, damit die Persona dich zwischen Sessions
# nicht vergisst. Storage-Cap großzügig; gesendet wird eh nur ein Fenster
# (tutor_session._history_window).
_HIST_MAX = 200

_hist_lock = Lock()   # serialisiert History-Writes über Personas hinweg


def _lang(lang: str | None) -> str:
    """Sprachcode normalisieren: übergebener Code, sonst TUTOR_LANG, sonst zh."""
    return (lang or os.getenv("TUTOR_LANG", "zh")).lower()


def mem_path(lang: str | None = None) -> str:
    """Pfad des Persona-Graphen (Wissen über Sasha) für eine Sprache."""
    return os.path.join(_DATA_DIR, f"persona_mem_{_lang(lang)}.json")


def hist_path(lang: str | None = None) -> str:
    """Pfad der persistenten Gesprächs-History einer Persona."""
    return os.path.join(_DATA_DIR, f"persona_hist_{_lang(lang)}.json")


# ── Gedächtnis (Graph) ───────────────────────────────────────────────────

def remember(user_text: str, ai_text: str, lang: str | None = None,
             provider: str | None = None, model: str | None = None):
    """
    Verdichtet einen Persona-Turn in IHREN Graphen (nie den Core-Graphen).

    Backend KAPAZITÄTSBASIERT (ai_backends): ist ein lokales Ollama erreichbar
    (daheim / PC via zentrale-remote), läuft die Verdichtung dort — sonst über
    den Cloud-Anbieter der Persona, damit die Memory auch unterwegs baut (Laptop
    ohne Zuhause). Ist gar kein Backend da: diesen Turn überspringen. Der lokale
    Extraktor ist KEIN Privacy-Schutz fürs Tutor-Material (das lag beim Reden eh
    beim Anbieter) — er ist billiger und hält alles offline, wenn Ollama da ist.

    Blockiert (LLM-Call ~1-2s): der Caller lässt das in einem Thread laufen.
    """
    try:
        import ai_backends
        st = ai_backends.status()
        if st.get("local"):
            backend = "local"
        elif st.get("cloud"):
            backend  = "cloud"
            provider = provider or st.get("cloud_provider")
        else:
            return   # kein Backend erreichbar → Gedächtnis diesen Turn auslassen
        consolidation.extract_turn_into_graph(
            user_text, ai_text,
            store=mem_path(lang),
            mirror_calendar=False,
            backend=backend, provider=provider, model=model,
        )
    except Exception:
        # Gedächtnis ist Beiwerk — ein Extraktor-Fehler darf das Gespräch nie
        # kippen.
        pass


def context(query: str | None, lang: str | None = None) -> str:
    """
    Kontext-Block 'Was du über Sasha weißt' aus dem Persona-Graphen, zum
    Anhängen an den Persona-System-Prompt. Leerer Store → leerer String.
    """
    prof = tutor_langs.get(lang)
    try:
        return graph.context_for_persona(
            query, store=mem_path(lang),
            persona_name=prof.get("persona_name", "du"),
        )
    except Exception:
        return ""


def mem_stats(lang: str | None = None) -> dict:
    """Knoten/Kanten-Zahl des Persona-Graphen (Debug/UI)."""
    try:
        return graph.stats(store=mem_path(lang))
    except Exception:
        return {"nodes": 0, "edges": 0}


# ── Persistente History ──────────────────────────────────────────────────

def load_history(lang: str | None = None) -> list:
    """Gespeicherte Gesprächs-History der Persona laden (Liste von
    {role, content}). Fehlt/kaputt → leere Liste."""
    path = hist_path(lang)
    if not os.path.exists(path):
        return []
    try:
        with _hist_lock, open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history: list, lang: str | None = None):
    """History atomar auf Disk schreiben (letzte _HIST_MAX Turns)."""
    path = hist_path(lang)
    trimmed = list(history)[-_HIST_MAX:]
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = path + '.tmp'
        with _hist_lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(trimmed, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
    except Exception:
        pass
