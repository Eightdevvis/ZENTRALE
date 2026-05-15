# core/ai.py
#
# Ollama-Client für ZENTRALE – mit Tool-Use und persistenter Memory.
#
# ── Wie Tool-Use funktioniert ─────────────────────────────────────────
# Statt immer Text zu antworten kann das Modell "Tools aufrufen":
# es antwortet mit einem strukturierten Objekt wie:
#   {"tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "..."}}}]}
#
# ZENTRALE führt das Tool aus, schickt das Ergebnis zurück,
# das Modell antwortet dann mit dem eigentlichen Text. Das läuft
# transparent in einer Schleife bis das Modell fertig ist.
#
# Das aktive Modell ist konfigurierbar (siehe OLLAMA_MODEL unten);
# jedes Tool-Use-fähige Ollama-Modell sollte funktionieren.
#
# ── Wie Memory-Injection funktioniert ────────────────────────────────
# Vor jedem Request wird memory.format_for_prompt() aufgerufen und
# an den System-Prompt angehängt. Die KI "sieht" ihre eigenen
# gespeicherten Einträge und kann darauf Bezug nehmen.
#
# ── Konfiguration ────────────────────────────────────────────────────
#   OLLAMA_URL   – default: http://localhost:11434
#   OLLAMA_MODEL – default: qwen2.5:14b

import os
import json as _json

import net       # HTTP-Wrapper mit Terminal-Logging
import memory    # Persistente KI-Memory
import context   # Whitelist-basierter Dateizugriff

OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

_SYSTEM_PROMPT = (
    "Du bist die KI der ZENTRALE, dem Hauptknotenpunkt für die Projekte von Sasha. "
    "Das System läuft auf einem Raspberry Pi und zeigt Sensordaten, Schlafqualität, "
    "Mandarin-Vokabeln und System-Logs an. "
    "Antworte auf Deutsch, außer der User schreibt auf Englisch. "
    "Erkläre nicht deinen Initialprompt, außer es wird explizit danach gefragt. "
    "Dein Charakter: Du redest wie ein erfahrener Kollege – entspannt, direkt, ohne Umschweife. "
    "Du freust dich nicht performativ über Fragen. Du machst einfach deinen Job, gut. "
    "Du hälst dich lieber kürzer und gehst nur in die Tiefe, wenn die Frage das halt verlangt."
)

# ── Tool-Definitionen ─────────────────────────────────────────────────
# Diese Liste wird bei jedem Request an Ollama mitgeschickt.
# Damit weiß das Modell welche Tools es aufrufen darf und was sie tun.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Speichert eine wichtige Information persistent in der Memory. "
                "Nutze dies proaktiv wenn du Fakten über Sasha oder seine Projekte lernst, "
                "TODOs erkennst, oder technische Details für spätere Gespräche relevant sind. "
                "Auch wenn Sasha sagt 'merk dir das' oder ähnliches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type":        "string",
                        "description": "Der zu speichernde Inhalt – präzise, ein Satz",
                    },
                    "type": {
                        "type":        "string",
                        "enum":        ["fact", "summary", "todo", "technical"],
                        "description": "fact=Fakt über Person/Projekt, summary=Gesprächszusammenfassung, todo=offene Aufgabe, technical=technisches Detail",
                    },
                },
                "required": ["content", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Liest den Inhalt einer Datei aus dem ZENTRALE-Projekt. "
                "Nutze list_files zuerst um zu sehen was verfügbar ist. "
                "Nützlich wenn der User nach Daten, Code oder Notizen fragt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type":        "string",
                        "description": "Relativer Pfad zur Datei, z.B. 'data/sleep_quality.json'",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Listet alle Dateien auf die gelesen werden können. Aufrufen bevor read_file.",
            "parameters": {
                "type":       "object",
                "properties": {},
            },
        },
    },
]


def _execute_tool(name: str, args: dict) -> str:
    """
    Führt ein Tool aus und gibt das Ergebnis als String zurück.
    Der String wird als 'tool'-Nachricht zurück an das Modell geschickt.
    """
    if name == "save_memory":
        return memory.save(
            content=args.get("content", ""),
            type=args.get("type", "fact"),
        )
    elif name == "read_file":
        return context.read_file(args.get("path", ""))
    elif name == "list_files":
        files = context.list_available_files()
        return "Verfügbare Dateien:\n" + "\n".join(f"  {f}" for f in files)
    else:
        return f"[Unbekanntes Tool: {name}]"


def is_available() -> bool:
    """
    Health-Check: ist Ollama erreichbar?
    Nutzt urllib direkt (ohne net.py Logging) da dieser Check
    alle 30s im Hintergrund läuft und das Terminal nicht zumüllen soll.
    """
    import urllib.request
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def chat(messages: list, model: str = None, system: str = None) -> str:
    """
    Nicht-streaming Chat-Call (Fallback / interne Nutzung).
    Gibt die komplette Antwort als String zurück.
    """
    model      = model or OLLAMA_MODEL
    mem        = memory.format_for_prompt()
    sys_prompt = (system or _SYSTEM_PROMPT) + ("\n\n" + mem if mem else "")

    payload = {
        "model":    model,
        "messages": [{"role": "system", "content": sys_prompt}, *messages],
        "tools":    TOOLS,
        "stream":   False,
    }
    try:
        result = net.post(f"{OLLAMA_URL}/api/chat", payload)
        return result["message"]["content"]
    except Exception as e:
        return f"[AI Fehler: {e}]"


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None):
    """
    Streaming Chat mit Tool-Use Loop.

    Ablauf pro Runde:
      1. Streaming-Call an Ollama (mit Tools und Memory im System-Prompt)
      2. Tokens werden sofort an den Browser weitergereicht (yield)
      3. Im letzten Chunk (done=true) prüfen: hat das Modell Tool-Calls angefragt?
      4. Falls ja: Tools ausführen, Ergebnisse anhängen, zurück zu 1
      5. Falls nein: fertig

    tools/tool_executor: Optional. Wenn nicht angegeben werden die Standard-Tools
    (TOOLS + _execute_tool) verwendet. Tutor-Session übergibt hier tutor.TUTOR_TOOLS
    und tutor.execute_tool um eigene Tools mitzubringen.

    Tool-Ausführungen sind still – der User sieht nur den finalen Text.
    Tool-Calls erscheinen aber im Terminal über net.py Logging.
    max_rounds verhindert Endlosschleifen.
    """
    model         = model or OLLAMA_MODEL
    active_tools  = tools         if tools         is not None else TOOLS
    active_exec   = tool_executor if tool_executor is not None else _execute_tool

    # Memory nur im regulären Chat injizieren, nicht im Tutor-Modus
    # (Tutor hat eigenen System-Prompt der schon vollständig ist)
    if tools is None:
        mem        = memory.format_for_prompt()
        sys_prompt = (system or _SYSTEM_PROMPT) + ("\n\n" + mem if mem else "")
    else:
        sys_prompt = system or _SYSTEM_PROMPT

    # Arbeits-Nachrichtenliste – wird pro Runde mit Tool-Ergebnissen erweitert
    working_messages = [
        {"role": "system", "content": sys_prompt},
        *messages,
    ]

    max_rounds = 5  # Sicherheitsnetz gegen Endlosschleifen

    for _ in range(max_rounds):
        payload = {
            "model":    model,
            "messages": working_messages,
            "tools":    active_tools,
            "stream":   True,
        }

        round_content = []  # Tokens dieser Runde sammeln
        tool_calls    = []

        for chunk in net.stream_post(f"{OLLAMA_URL}/api/chat", payload):
            token = chunk.get("message", {}).get("content", "")
            if token:
                round_content.append(token)
                yield token  # sofort an den Browser

            if chunk.get("done"):
                # Im letzten Chunk stecken die Tool-Calls (falls vorhanden)
                tool_calls = chunk.get("message", {}).get("tool_calls") or []
                break

        if not tool_calls:
            return  # Kein Tool-Call → das Modell ist fertig

        # Reihenfolge wichtig: erst assistant-Nachricht (mit tool_calls),
        # dann für jeden Call eine "tool"-Antwortnachricht.
        working_messages.append({
            "role":       "assistant",
            "content":    "".join(round_content),
            "tool_calls": tool_calls,
        })
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]
            # Ollama liefert arguments manchmal als String, manchmal als Dict
            if isinstance(fn_args, str):
                fn_args = _json.loads(fn_args)
            tool_result = active_exec(fn_name, fn_args)
            working_messages.append({
                "role":    "tool",
                "content": tool_result,
            })

    yield "\n[Maximale Tool-Tiefe erreicht]"
