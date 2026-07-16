# tutor/openai_compat.py
#
# OpenAI-/v1-kompatibles Tutor-Backend — der Arbeitstier-Pfad für die
# Verteilung. Bedient JEDEN Provider mit OpenAI-kompatiblem Endpoint
# (Qwen, DeepSeek, Mistral, OpenAI, Groq, Gemini) UND lokales Ollama,
# nur durch Tausch von base_url + Key + Modell.
#
# ── Drop-in für ai.chat_stream() ────────────────────────────────────────
# Gleiche Signatur, yieldet Plain-Text-Tokens. Greift NICHT in core/ai.py
# ein (sauberes Addon). Tools = TUTOR_TOOLS sind bereits OpenAI-Schema, also
# OHNE Übersetzung direkt nutzbar (anders als der Anthropic-Pfad).
#
# ── Cloud→Lokal-Sandbox (Invariante) ────────────────────────────────────
# Dieses Modul importiert WEDER ai/graph/consolidation/context NOCH führt es
# selbst Tools aus – es reicht Tool-Calls nur an den übergebenen tool_executor
# (= tutor.execute_tool, geschlossene Vokabel-Allowlist) durch. Die Cloud-AI
# kann darüber NICHT in die lokale AI greifen (kein Memory-Graph, keine lokalen
# Tools, kein Datei-Zugriff). Diese Trennung NIE aufweichen.
#
# ── Streaming-Tool-Loop ─────────────────────────────────────────────────
# Streamt Text-Deltas; akkumuliert fragmentierte tool_calls-Deltas; bei
# finish_reason='tool_calls' werden die Tutor-Tools ausgeführt und die
# Runde wiederholt, bis das Modell fertig ist.

import os
import json as _json

# Zuverlässigkeits-Hebel (gegen echtes qwen verifiziert, 2026-07-07): der
# getunte Persona-Prompt allein hielt qwen NICHT stabil kurz+in-der-Zielsprache —
# es driftete je nach Sampling in deutsche Monologe. Eine niedrige Temperatur +
# ein max_tokens-Cap machen das Verhalten reproduzierbar kurz. Beide per Env
# übersteuerbar. Siehe memory/tutor_persona_tuning.md.
TUTOR_TEMPERATURE = float(os.getenv("TUTOR_TEMPERATURE", "0.4"))
TUTOR_MAX_TOKENS  = int(os.getenv("TUTOR_MAX_TOKENS", "200"))

_clients = {}  # provider-name → OpenAI-Client (lazy, gecacht)


def _client(provider: dict):
    """Lazy-Init eines OpenAI-Clients für base_url/key des Providers."""
    name = provider.get("base_url") or "default"
    if name not in _clients:
        from openai import OpenAI  # type: ignore – nur im Cloud-Pfad importiert
        key = os.environ.get(provider.get("key_env") or "", "") or "missing-key"
        _clients[name] = OpenAI(base_url=provider.get("base_url"), api_key=key)
    return _clients[name]


def _prepare_messages(messages: list, system: str) -> list:
    """System-Prompt voranstellen; bei leerer/assistant-only History eine
    Kickoff-user-Nachricht seeden (Begrüßung; Zielsprache kommt aus system)."""
    out = []
    if system:
        out.append({"role": "system", "content": system})
    hist = [dict(m) for m in (messages or [])]
    if not any(m.get("role") == "user" for m in hist):
        hist.append({"role": "user",
                     "content": "(Beginne die Tutor-Session mit einer kurzen Begrüßung.)"})
    out.extend(hist)
    return out


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False,
                *, _provider: dict = None):
    """
    Streamt Tutor-Antworten von einem OpenAI-kompatiblen Provider.
    yieldet Plain-Text-Tokens (Strings).

    _provider: Provider-Eintrag aus tutor_providers (base_url/key/kind).
    model:     Modell-ID (z.B. 'qwen-plus').
    """
    if _provider is None:
        raise ValueError("tutor_openai_compat.chat_stream braucht _provider")

    client = _client(_provider)
    msgs   = _prepare_messages(messages, system)

    # Begrenzung gegen Endlos-Tool-Loops (analog zur Tool-Tiefe in ai.py).
    for _ in range(12):
        stream = client.chat.completions.create(
            model=model,
            messages=msgs,
            tools=tools or None,          # TUTOR_TOOLS sind schon OpenAI-Schema
            stream=True,
            temperature=TUTOR_TEMPERATURE,   # niedrig = reproduzierbar kurz
            max_tokens=TUTOR_MAX_TOKENS,     # Cap gegen Monolog-Ausreißer
        )

        text_parts = []
        tool_calls = {}    # index → {id, name, args}
        finish     = None

        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta  = choice.delta

            if getattr(delta, "content", None):
                text_parts.append(delta.content)
                yield delta.content

            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = tool_calls.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["args"] += tc.function.arguments

            if choice.finish_reason:
                finish = choice.finish_reason

        # Kein Tool angefragt → fertig.
        if not tool_calls:
            return

        # Assistant-Turn (mit tool_calls) als Kontext anhängen.
        msgs.append({
            "role":    "assistant",
            "content": "".join(text_parts) or None,
            "tool_calls": [{
                "id":   s["id"],
                "type": "function",
                "function": {"name": s["name"], "arguments": s["args"] or "{}"},
            } for s in tool_calls.values()],
        })

        # Tools ausführen, Ergebnisse als role=tool zurück.
        for s in tool_calls.values():
            try:
                args = _json.loads(s["args"] or "{}")
            except Exception:
                args = {}
            out = tool_executor(s["name"], args) if tool_executor else ""
            msgs.append({
                "role":         "tool",
                "tool_call_id": s["id"],
                "content":      str(out),
            })

    yield "\n[Maximale Tool-Tiefe erreicht]"
