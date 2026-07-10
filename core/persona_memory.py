# core/persona_memory.py
#
# Eigenes Gedächtnis pro Sprach-Persona (Ling Ling/zh, Jacqueline/fr, …).
#
# ── Die EINE Grenze: Tutor ↔ Core-KI fassen sich nie an ──────────────────
# Die meisten Personas reden über einen CLOUD-Anbieter (zh→qwen). Würde die
# Persona Sashas privaten Core-Graphen (data/ai_graph.json — das was Sasha dem
# lokalen Offline-Chat erzählt) anfassen, wäre das ein Bruch der Sandbox
# (core/tutor.py). Deshalb hat jede Persona ihren EIGENEN, getrennten Store:
# data/persona_mem_<lang>.json. Er enthält nur, was Sasha DIESER Persona erzählt
# hat. Das ist die einzige harte Garantie hier.
#
# ── GROB, nicht exakt (2026-07-10) ───────────────────────────────────────
# Der Store ist KEIN Konzept-Graph mehr (der von der Core-KI kopierte war eh nie
# gebaut worden) und KEIN Wortprotokoll — sondern eine kleine, gedeckelte Liste
# ungefährer Notizen (wichtige Fakten + Themen). Ein Mitbewohner merkt sich grob,
# nicht wann genau was gesagt wurde. Roher Verlauf wird NICHT mehr über Sessions
# persistiert (nur in-session, für Kohärenz).
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


# ── Gedächtnis: destillierte GROB-Notizen (kein Graph, kein Wortprotokoll) ──
# Sashas Design (2026-07-10): ein Mitbewohner braucht kein exaktes Gedächtnis mit
# Zeitstempeln, sondern nur UNGEFÄHRE Eindrücke — die wichtigsten Fakten über
# Sasha + worüber ihr grob schon geredet habt. Darum ersetzt hier ein kleiner,
# gedeckelter Notiz-Store den früher kopierten Core-KI-Konzept-Graphen (der war
# eh nie gebaut worden). Store: data/persona_mem_<lang>.json =
# {"facts": [kurze Sätze], "topics": [Stichworte]}. Auf CHINESISCH (der Block
# wandert in den zh-System-Prompt → hält qwen im Chinesischen).
_MEM_MAX_FACTS  = 12
_MEM_MAX_TOPICS = 12
_mem_lock = Lock()


def _load_notes(lang: str | None = None) -> dict:
    path = mem_path(lang)
    if not os.path.exists(path):
        return {"facts": [], "topics": []}
    try:
        with _mem_lock, open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return {"facts": [], "topics": []}
        return {"facts": list(d.get("facts") or [])[:_MEM_MAX_FACTS],
                "topics": list(d.get("topics") or [])[:_MEM_MAX_TOPICS]}
    except Exception:
        return {"facts": [], "topics": []}


def _save_notes(notes: dict, lang: str | None = None):
    path = mem_path(lang)
    out = {"facts": list(notes.get("facts") or [])[:_MEM_MAX_FACTS],
           "topics": list(notes.get("topics") or [])[:_MEM_MAX_TOPICS]}
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        tmp = path + '.tmp'
        with _mem_lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
    except Exception:
        pass


_DISTILL_SYS = (
    "你在帮玲玲记住关于她室友 Sasha 的大概情况（不是精确记录，不要时间戳、不要原话）。"
    "根据现有笔记和最新一轮对话，更新笔记：保留重要的、长期有用的事实，和你们聊过的话题。"
    f"事实最多 {_MEM_MAX_FACTS} 条、话题最多 {_MEM_MAX_TOPICS} 条，各条简短、去重，用中文。"
    "如果这一轮没有值得记的新东西，就原样返回。只输出 JSON，格式："
    '{"facts": ["…"], "topics": ["…"]}'
)


def remember(user_text: str, ai_text: str, lang: str | None = None,
             provider: str | None = None, model: str | None = None):
    """
    Destilliert einen Persona-Turn in die GROB-Notizen (nie den Core-Graphen).
    Ein leichter LLM-Pass fügt neue wichtige Fakten/Themen hinzu und deckelt.

    Backend KAPAZITÄTSBASIERT (ai_backends): lokales Ollama da → dort; sonst über
    den Cloud-Anbieter der Persona; nichts da → auslassen. Blockiert (~1s) → der
    Caller lässt das in einem Thread laufen. Ein Fehler darf das Gespräch nie
    kippen (Gedächtnis ist Beiwerk).
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
            return   # kein Backend → diesen Turn nicht merken

        notes = _load_notes(lang)
        user_msg = ("现有笔记：" + json.dumps(notes, ensure_ascii=False) +
                    f"\n最新一轮：\nSasha 说：{user_text}\n玲玲说：{ai_text}")
        raw = _distill(backend, provider, model, user_msg)
        if not raw:
            return
        new = _parse_notes(raw)
        if new is not None:
            _save_notes(new, lang)
    except Exception:
        pass


def _distill(backend: str, provider: str | None, model: str | None, user_msg: str) -> str:
    """Ein knapper, tool-loser LLM-Call → Roh-Text (erwartet JSON). Nutzt denselben
    Dispatch wie das Reden (Cloud openai-compat / lokal Ollama)."""
    msgs = [{"role": "user", "content": user_msg}]
    parts = []
    try:
        if backend == "cloud":
            import tutor_providers, tutor_openai_compat as oc
            prov = tutor_providers.get(provider) if provider else None
            if not prov:
                return ""
            mdl = model or prov.get("default_model")
            for tok in oc.chat_stream(msgs, model=mdl, system=_DISTILL_SYS,
                                      tools=None, tool_executor=None, _provider=prov):
                parts.append(tok)
        else:  # local ollama
            import ai
            for tok in ai.chat_stream(msgs, system=_DISTILL_SYS,
                                      tools=None, tool_executor=None):
                parts.append(tok)
    except Exception:
        return ""
    return "".join(parts)


def _parse_notes(raw: str):
    """JSON aus dem Roh-Text ziehen (auch aus ```-Fences) → {facts, topics} oder None."""
    s = raw.strip()
    if "```" in s:                       # Code-Fences abstreifen
        import re
        m = re.search(r'\{.*\}', s, re.DOTALL)
        if m:
            s = m.group(0)
    try:
        d = json.loads(s)
    except Exception:
        import re
        m = re.search(r'\{.*\}', s, re.DOTALL)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(d, dict):
        return None
    facts  = [str(x).strip() for x in (d.get("facts")  or []) if str(x).strip()]
    topics = [str(x).strip() for x in (d.get("topics") or []) if str(x).strip()]
    return {"facts": facts, "topics": topics}


def context(query: str | None, lang: str | None = None) -> str:
    """
    Kontext-Block 'Was du grob über Sasha weißt' aus den Notizen, zum Anhängen an
    den Persona-System-Prompt. Leerer Store → leerer String. Bewusst als UNGEFÄHR
    markiert, damit die Persona nicht so tut, als hätte sie ein exaktes Protokoll.
    """
    notes = _load_notes(lang)
    facts, topics = notes.get("facts") or [], notes.get("topics") or []
    if not facts and not topics:
        return ""
    parts = []
    if facts:
        parts.append("你大概记得：" + "；".join(facts))
    if topics:
        parts.append("你们聊过：" + "、".join(topics))
    return "（关于 Sasha（只是大概印象，不是精确记录）：" + " ".join(parts) + "）"


def mem_stats(lang: str | None = None) -> dict:
    """Anzahl Fakten/Themen im Notiz-Store (Debug/UI)."""
    notes = _load_notes(lang)
    return {"facts": len(notes.get("facts") or []),
            "topics": len(notes.get("topics") or [])}


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
