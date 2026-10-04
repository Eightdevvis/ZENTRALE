# Archiv: ai.chat() — nicht-streamender Ollama-Chat

**Stand 2026-10-04:** aus dem Live-Code entfernt.

- **Was es tat:** Ein einzelner, blockierender Chat-Call an Ollama
  (`stream: False`) mit demselben System-Prompt-Aufbau wie `chat_stream`
  (Persona + Capabilities + Graph-Kontext + Jetzt-Block) und Tools im
  Payload — die Tool-Calls wurden aber NICHT ausgeführt, es zählte nur
  `message.content`. Speicherte den Turn im Hintergrund ins Gedächtnis.
- **Warum archiviert:** Kein Aufrufer mehr — weder Backend, TUI, Skripte noch
  Tests. Alle Fronten laufen über `chat_stream` (bzw. `core/cloud.py`).
- **Wann wieder nützlich:** Für einen One-Shot-Aufruf ohne SSE (z. B. ein
  Skript/Benchmark, das nur die fertige Antwort braucht). Dann aber bewusst
  entscheiden, ob Tools ausgeführt werden sollen — hier wurden sie
  stillschweigend ignoriert.
- **Abhängigkeiten (alle in `core/ai.py`, bleiben bestehen):**
  `_ensure_seed_once`, `OLLAMA_MODEL`, `_last_user_query`, `graph` +
  `GRAPH_KONTEXT`, `_SYSTEM_PROMPT`, `_CAPABILITIES_PROMPT`, `_now_prompt`,
  `_think_opts`, `TOOLS`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_NUM_CTX`,
  `QWEN_SAMPLING`, `net.post`, `OLLAMA_URL`, `_async_save_turn`.

## core/ai.py Z. 1120–1161 (Commit e063fab)

```python
def chat(messages: list, model: str = None, system: str = None) -> str:
    """
    Nicht-streaming Chat-Call (Fallback / interne Nutzung).
    Gibt die komplette Antwort als String zurück.
    """
    _ensure_seed_once()
    model      = model or OLLAMA_MODEL
    # Phase C: Memory-Injection ist jetzt query-aware. Wir nehmen die
    # letzte User-Message als semantische Anfrage und kriegen nur die
    # k relevantesten Einträge in den Prompt - statt wie früher die
    # komplette Memory zu dumpen (skaliert nicht).
    user_query = _last_user_query(messages)
    # Phase G: ein einziger Memory-Kontext aus dem Konzept-Graph statt
    # drei separaten Schichten. Aktivierungs-Spread holt was relevant
    # ist, inklusive Zeit-Anker und Sasha-Profil über die Graph-Topologie.
    mem_ctx = graph.context_for_query(user_query) if GRAPH_KONTEXT else ""
    # Statisches zuerst, Wechselndes ans Ende (siehe _PROMPT_ORDER-Notiz oben).
    sys_prompt = (system or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
    if mem_ctx:
        sys_prompt += "\n\n" + mem_ctx
    sys_prompt += "\n\n" + _now_prompt()

    payload = {
        "model":      model,
        **_think_opts(),
        "messages":   [{"role": "system", "content": sys_prompt}, *messages],
        "tools":      TOOLS,
        "stream":     False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        # Gleiches num_ctx wie im Streaming-Pfad - sonst haette der
        # Fallback-Call ein anderes Kontextverhalten als der echte Chat.
        "options":    {"num_ctx": OLLAMA_NUM_CTX, **QWEN_SAMPLING},
    }
    try:
        result   = net.post(f"{OLLAMA_URL}/api/chat", payload)
        content  = result["message"]["content"]
        # Phase D: Auto-Save in den Hintergrund schieben. Eigene Aussage
        # mitspeichern ist der Kern-Schutz gegen Selbst-Widersprüche.
        _async_save_turn(user_query, content)
        return content
    except Exception as e:
        return f"[AI Fehler: {e}]"
```
