# core/tutor_cloud.py
#
# Cloud-Backend für den Mandarin-Tutor (Anthropic Claude).
#
# ── Warum ───────────────────────────────────────────────────────────────
# VERIFIKATIONS-Phase: die Tutor-Konzeptidee (Vokabel-Pools, 80/20-Mischung,
# Pinyin-Flow) soll mit einer SMARTEN KI getestet werden, damit Schwächen am
# Konzept liegen – nicht am schwachen lokalen Ollama-Modell. Sobald das
# Konzept trägt, ist klar, was später am lokalen Modell zu tun ist.
#
# ── Sauberes Addon ──────────────────────────────────────────────────────
# Dieses Modul ist ein DROP-IN für ai.chat_stream() mit identischer Signatur.
# Es webt NICHTS in den Core-KI-Layer (core/ai.py) ein.
#
# ── Cloud→Lokal-Sandbox (Invariante) ────────────────────────────────────
# Importiert WEDER ai/graph/consolidation NOCH führt es selbst Tools aus –
# Tool-Calls gehen nur an den übergebenen tool_executor (= tutor.execute_tool,
# geschlossene Vokabel-Allowlist). Die Cloud-AI kann darüber NICHT in die
# lokale AI greifen (kein Graph, keine lokalen Tools, kein Datei-Zugriff).
#
# ── Offline-Prinzip ─────────────────────────────────────────────────────
# ZENTRALE ist normalerweise vollständig offline. Dieses Backend bricht das
# BEWUSST und nur als Opt-in (TUTOR_BACKEND=cloud). Default bleibt 'local'.
#
# ── Konfiguration (Env-Vars) ────────────────────────────────────────────
#   ANTHROPIC_API_KEY   – Pflicht. Secret, NIE committen.
#   TUTOR_CLOUD_MODEL   – optional, Default 'claude-opus-4-8' (fähigstes Opus).

import os

# Default-Modell: Opus 4.8 = Anthropics fähigstes Opus, ideal um das Konzept
# ohne Schwachmodell-Faktor zu verifizieren. Per Env überschreibbar.
_MODEL = os.getenv("TUTOR_CLOUD_MODEL", "claude-opus-4-8")

# Tutor-Antworten sollen KURZ sein (1-2 Sätze). Cap + niedrige Temperatur halten
# das Verhalten reproduzierbar knapp (wie beim openai_compat-Pfad, siehe dort +
# memory/tutor_persona_tuning.md). Beide per Env übersteuerbar.
_MAX_TOKENS   = int(os.getenv("TUTOR_MAX_TOKENS", "200"))
_TEMPERATURE  = float(os.getenv("TUTOR_TEMPERATURE", "0.4"))

_client = None  # lazy: anthropic erst importieren/instanziieren wenn wirklich genutzt


def _get_client():
    """Lazy-Init des Anthropic-Clients. Liest ANTHROPIC_API_KEY aus der Env."""
    global _client
    if _client is None:
        import anthropic  # type: ignore  – nur im Cloud-Pfad importiert
        _client = anthropic.Anthropic()  # nimmt ANTHROPIC_API_KEY aus der Env
    return _client


def _to_anthropic_tools(openai_tools: list) -> list:
    """
    Übersetzt das OpenAI/Ollama-Tool-Schema (TUTOR_TOOLS) ins Anthropic-Format.

    OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
    Anthropic: {"name", "description", "input_schema"}
    """
    out = []
    for t in openai_tools or []:
        fn = t.get("function", t)  # toleriert beide Formen
        out.append({
            "name":         fn["name"],
            "description":  fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


def _prepare_messages(messages: list) -> list:
    """
    Bereitet die History für die Anthropic-API auf.

    Anthropic verlangt eine NICHT-leere messages-Liste, die mit einer
    user-Nachricht beginnt. Bei Session-Beginn (history leer, KI soll
    grüßen) seeden wir eine Kickoff-user-Nachricht.
    """
    msgs = [dict(m) for m in (messages or [])]
    if not msgs or msgs[0].get("role") != "user":
        # Kickoff: KI soll die Session auf Mandarin eröffnen (siehe _TUTOR_PROMPT).
        msgs.insert(0, {
            "role": "user",
            "content": "(Beginne die Tutor-Session mit einer kurzen Begrüßung auf Mandarin.)",
        })
    return msgs


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False):
    """
    Drop-in für ai.chat_stream(): streamt Tutor-Antworten von Claude.

    Yieldet Plain-Text-Tokens (Strings) – passend zum Tutor-Pfad, der nur
    Text erwartet (keine ascii/permission/cinema-Events).

    Manuelle Tool-Use-Loop: streamt Text, führt bei stop_reason=='tool_use'
    die Tutor-Tools (get_confirmed_vocab etc.) aus und streamt weiter, bis
    die KI fertig ist.
    """
    client       = _get_client()
    anthro_msgs  = _prepare_messages(messages)
    anthro_tools = _to_anthropic_tools(tools) if tools else None

    # Begrenzung gegen Endlos-Tool-Loops (analog zur Tool-Tiefe in ai.py).
    for _ in range(12):
        with client.messages.stream(
            model=model or _MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system or "",
            tools=anthro_tools,
            messages=anthro_msgs,
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()

        if final.stop_reason != "tool_use":
            return  # fertig – kein Tool-Call mehr

        # Assistant-Turn (inkl. tool_use-Blöcken) als Kontext anhängen.
        anthro_msgs.append({"role": "assistant", "content": final.content})

        # Alle angefragten Tools ausführen, Ergebnisse als tool_result zurück.
        results = []
        for block in final.content:
            if block.type == "tool_use":
                out = ""
                if tool_executor:
                    out = tool_executor(block.name, dict(block.input or {}))
                results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     str(out),
                })
        anthro_msgs.append({"role": "user", "content": results})

    yield "\n[Maximale Tool-Tiefe erreicht]"
