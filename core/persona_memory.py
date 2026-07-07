# core/persona_memory.py
#
# Eigenes Gedächtnis pro Sprach-Persona (Ling Ling/zh, Jacqueline/fr, …).
#
# ── Warum getrennt vom Core-Graphen? ─────────────────────────────────────
# Die meisten Personas reden über einen CLOUD-Anbieter (zh→qwen). Würde die
# Persona Sashas privaten Core-Graphen (data/ai_graph.json) lesen und an die
# Cloud schicken, wäre das ein Bruch der Sandbox (core/tutor.py). Deshalb hat
# jede Persona ihren EIGENEN Graphen:  data/persona_mem_<lang>.json  — gleiche
# graph.py-Mechanik, aber ein anderer Store. Er enthält nur, was Sasha DIESER
# Persona erzählt hat.
#
# ── Privacy des Loops ────────────────────────────────────────────────────
#   Gespräch  → Cloud-Anbieter der Persona (tutor_session).
#   Verdichtung→ LOKALES Ollama (consolidation), egal welcher Anbieter redet.
#   Kontext   → nur der persona-eigene Graph zurück in ihren eigenen Prompt
#               (die Daten hat Sasha diesem Anbieter ohnehin schon geschickt).
# So bleibt Wissen, das nur die lokale Core-KI kennt, aus der Cloud.
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

def remember(user_text: str, ai_text: str, lang: str | None = None):
    """
    Verdichtet einen Persona-Turn in IHREN Graphen. Läuft über den lokalen
    Ollama-Extraktor (privacy-safe) und spiegelt NICHT in Sashas Kalender.

    Blockiert (LLM-Call ~1-2s): der Caller lässt das in einem Thread laufen.
    """
    try:
        consolidation.extract_turn_into_graph(
            user_text, ai_text,
            store=mem_path(lang),
            mirror_calendar=False,
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
