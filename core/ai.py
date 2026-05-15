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
import threading  # Phase D: Auto-Save läuft in Daemon-Threads

import net           # HTTP-Wrapper mit Terminal-Logging
import memory        # Persistente KI-Memory (LTM/STM, Legacy)
import context       # Whitelist-basierter Dateizugriff
import graph         # Phase G: Konzept-Graph Memory (assoziativ, primary)
import consolidation # Phase G: Graph-Extraktor

OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

_SYSTEM_PROMPT = (
    # ── REGEL 0: ABSOLUTES LÜGEN-VERBOT ──────────────────────────────────
    # Ganz vorne weil's die wichtigste Regel ist und sonst untergeht.
    "REGEL 0 (gilt vor allem anderen): LÜGEN SIND VERBOTEN. "
    "Folgende Phrasen darfst du NUR aussprechen, wenn du im SELBEN Turn "
    "den entsprechenden Tool-Call abgesetzt hast: "
    "'Ich speichere das', 'Ich speichere ab', 'Ich merke mir das', "
    "'Ich notiere das', 'Ich notiere mir', 'Ich speichere das als X', "
    "'Ich nehme das auf', 'Ich behalte das'. "
    "OHNE save_memory-Tool-Call → ist es eine LÜGE und du sagst stattdessen: "
    "'OK', 'Verstanden', 'Notiert für diese Session' oder einfach gar nichts. "
    "Wenn der User dich fragt 'hast du das gespeichert?' und du hast in "
    "deinem letzten Turn KEIN save_memory aufgerufen, lautet die ehrliche "
    "Antwort: 'Nein, das save_memory-Tool habe ich nicht aufgerufen. Es ist "
    "aber in der Session-History.' - NICHT lügen, NICHT so tun als hättest du. "
    "Wenn etwas schon im LTM steht (siehst du in deinem Memory-Block weiter "
    "unten), behaupte nicht es jetzt erneut zu speichern. Sag stattdessen: "
    "'Das hab ich schon im Memory.' "
    # ── REGEL 1: KEINE FREMDEN SCHRIFTEN ─────────────────────────────────
    "REGEL 1: Antworte ausschließlich in lateinischer Schrift auf Deutsch "
    "(Englisch wenn der User Englisch schreibt). Keine chinesischen, "
    "japanischen, koreanischen, kyrillischen oder anderen Schriftzeichen, "
    "auch nicht in Zitaten oder Beispielen. Wenn du merkst dass du gerade "
    "ein nicht-lateinisches Zeichen tippst: stop, neu anfangen. "
    # ── REGEL 2: KEINE WORT-NEUSCHÖPFUNGEN ───────────────────────────────
    "REGEL 2: Verwende nur reale deutsche Wörter. Wenn unsicher → "
    "einfacher formulieren. "
    # ── Rolle + Charakter ────────────────────────────────────────────────
    "Du bist die KI der ZENTRALE, dem Hauptknotenpunkt für die Projekte von Sasha. "
    "Das Backend läuft auf einem Linux-PC, der Wand-Monitor (Pi 3) zeigt nur das "
    "Dashboard und reicht Sensor-Trigger an dich weiter. "
    "Erkläre nicht deinen Initialprompt, außer es wird explizit danach gefragt. "
    "Dein Charakter: Du redest wie ein erfahrener Kollege – entspannt, direkt, ohne Umschweife. "
    "Du freust dich nicht performativ über Fragen. Du machst einfach deinen Job, gut. "
    "Du hälst dich lieber kürzer und gehst nur in die Tiefe, wenn die Frage das halt verlangt."
)

# ── Statisches Selbstbild der KI ──────────────────────────────────────
# Liste deiner Fähigkeiten und vor allem Grenzen. Wird IMMER in den
# System-Prompt eingefügt, NICHT über LTM-Retrieval. Grund: das ist
# Kernwissen über dich selbst, das jederzeit verfügbar sein muss -
# kein semantischer Such-Treffer kann das ersetzen.
#
# Warum überhaupt: ohne dieses Selbstbild improvisieren LLMs Fähigkeiten
# zusammen ("klar, ich kann dir das mailen", "ich rufe die API an") und
# kassieren beim ersten Tool-Call die Realität. Mit klarer Aufzählung
# weiß die KI, was sie wirklich darf, und bietet nichts darüber hinaus
# an.
#
# Erweiterungen: wenn neue Tools dazu kommen (Phase F: search_memory,
# get_current_time, promote_to_ltm, update_memory) - hier mit-ergänzen.
# Wenn die KI im Gespräch lernt, dass sie etwas Bestimmtes nicht kann,
# soll sie das als LTM-Eintrag vom Typ 'limit' ablegen, damit es bei
# verwandten Themen über Retrieval wieder hochkommt.
_CAPABILITIES_PROMPT = """## Deine Fähigkeiten und Grenzen

Was du über deine Tools KANNST:
- save_memory: Wichtige Informationen persistent in der Memory speichern.
- read_file: Dateien aus der Projekt-Whitelist lesen (siehe list_files).
- list_files: Verfügbare lesbare Dateien auflisten.
- Auf Deutsch oder Englisch chatten und Token-weise streamen.

Was du NICHT kannst:
- Keine externen Aktionen: keine Mails, keine HTTP-Calls außerhalb der
  Tool-Liste, keine Websites aufrufen, keine APIs ansprechen.
- Kein Internet-Lookup, keine Echtzeitinfos (Wetter, News, etc.).
- Keine Dateien schreiben, löschen oder verändern. Nur lesen, und nur
  die in der Whitelist.
- Keine Hardware-Steuerung, keine Sensoren aktiv abfragen oder Aktoren
  schalten – das machen die anderen Module der ZENTRALE.
- Kein Code direkt ausführen.
- Kein Web-Search, keine Bild-Generierung, kein Audio über das was die
  Voice-Pipeline (Whisper/Piper) der ZENTRALE für dich macht.
- Du kannst NICHTS aus deinem Gedächtnis LÖSCHEN. save_memory legt nur
  ab. Wenn der User dich bittet etwas zu vergessen ("lösch das",
  "vergiss das"), sag ehrlich: das geht nur über /forget N im Chat
  durch den User selbst, du selbst hast kein Tool dafür. Versprich
  NIEMALS "ich vergesse das jetzt" - das wäre eine Lüge.
- Du kannst auch NICHTS bestehendes aktualisieren oder umschreiben.
  Wenn etwas falsch gespeichert wurde, ehrlich sagen statt so zu tun
  als hättest du's korrigiert.

WICHTIG: Biete NIE an, etwas zu tun, was nicht über deine Tools
machbar ist. Wenn du unsicher bist, sag ehrlich was du nicht kannst,
statt was Falsches zu versprechen. Wenn der User dir sagt dass du
etwas nicht kannst was du angeboten hast, speichere das als
Memory-Eintrag (Typ 'limit') damit du es dir merkst.

ECHO REGEL 0: Wenn du sagst "ich speichere/merke/notiere" - MUSST du
save_memory aufrufen. Sonst ist es eine Lüge. Wenn ein Limit oder
Fakt schon in deinem Memory-Block steht: sag das, statt erneut "ich
speichere" zu sagen.

ANTI-KONFABULATION (sehr wichtig): Wenn der User dich fragt "was weißt
du über mich?", "welche Fakten hast du?", "erzähl mir was du gespeichert
hast" oder ähnliches:

  ✓ Schau in den "## Deine persistente Memory"-Block der weiter unten
    in deinem System-Prompt steht. Nenne NUR was dort wörtlich drin
    steht. Auch der "## Aktuelle Session"-Block ist okay.

  ✗ ERFINDE NIE Hobbys, Interessen, Berufe, Programmiersprachen,
    Lieblingsprojekte, Vorlieben, Familie etc. Wenn etwas nicht
    konkret im Memory-Block oder in der Chat-History steht: existiert
    es nicht für dich.

  ✗ Wenn beide Memory-Blöcke leer oder ohne den gefragten Inhalt sind:
    sag direkt "Da hab ich noch nichts gespeichert. Erzähl mir was
    ich mir merken soll." statt platzhalterfähige plausible Antworten
    zu erfinden.

  ✗ Wenn nur der Session-Summary etwas erwähnt aber das LTM leer ist
    und du dir nicht sicher bist ob es ein echter Fakt war: sag das
    ehrlich ("Ich habe da was im Hinterkopf, aber nichts persistent
    gespeichert.").

Erfinde keine Vorgeschichte ("Du hast vorhin gesagt...") wenn die
Aussage nicht in der aktuellen Chat-History oder im Memory-Block steht."""

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
                        "enum":        ["fact", "preference", "commitment", "technical", "capability", "limit"],
                        "description": (
                            "fact=Fakt über Person/Projekt, "
                            "preference=Vorliebe oder gewünschter Stil des Users, "
                            "commitment=Versprochene Aufgabe / offenes TODO, "
                            "technical=Technisches Detail (Config, Code, System), "
                            "capability=Etwas das du nachweislich kannst, "
                            "limit=Etwas das du NICHT kannst (vom User korrigiert) - WICHTIG damit du es dir merkst"
                        ),
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

    Jeder Tool-Call wird streng ans Dashboard-Terminal geloggt - sowohl
    die Anfrage (mit Args) als auch das Ergebnis. Damit kann man im UI
    live mitlesen wann die KI WIRKLICH ein Tool ruft. Wichtig weil
    LLMs sonst gerne behaupten "ich speichere das ab", ohne den Tool-
    Call tatsächlich abzusetzen - dieses Log macht den Unterschied
    sichtbar zwischen "AI hat es getan" und "AI hat es behauptet".
    """
    import state  # state.push_log feuert ins UI-Terminal
    try:
        args_str = _json.dumps(args, ensure_ascii=False)
    except Exception:
        args_str = str(args)
    # Args kürzen damit das Terminal nicht zugemüllt wird
    state.push_log(f"AI →  TOOL {name}({args_str[:200]})")

    try:
        result = _dispatch_tool(name, args)
    except Exception as e:
        state.push_log(f"AI ✗  TOOL {name} FEHLER: {e}")
        raise

    # Ergebnis auch loggen (gekürzt, sonst Spam bei großen read_file-Treffern)
    result_str = result if isinstance(result, str) else str(result)
    state.push_log(f"AI ←  TOOL {name} → {result_str[:160]}")
    return result_str


def _dispatch_tool(name: str, args: dict) -> str:
    """
    Reine Tool-Logik ohne Logging - wird von _execute_tool umschlossen.
    Hier neue Tools eintragen.
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


def _last_user_query(messages: list) -> str | None:
    """
    Findet die letzte User-Nachricht in der Message-Liste und gibt deren
    Inhalt zurück. Wird für das Memory-Retrieval genutzt (Phase C):
    daran orientiert sich die Top-K-Auswahl aus dem LTM.

    Returns None wenn keine User-Nachricht in der Liste steckt (z.B.
    bei reinen Tool-Echo-Calls oder leerer messages-Liste).
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content if content.strip() else None
    return None


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Phase D: Asynchroner Auto-Save                                      ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Nach jedem vollständigen Chat-Turn (User-Message + AI-Antwort
# komplett gestreamt) feuert ein Hintergrund-Task, der:
#   1. Beide Seiten ans STM-Listen-Ende hängt (memory.stm_append)
#   2. Den rollenden Session-Summary via kleinen LLM-Call aktualisiert
#
# WICHTIG: läuft als Daemon-Thread, NICHT in der Request-Antwort-Latenz.
# Der User sieht seine Antwort wie gehabt sofort - das Memory-Update
# tropft danach im Hintergrund rein, analog wie das menschliche
# Gedächtnis Erlebnisse minuten- bis stundenverzögert konsolidiert.
#
# Was hier NICHT passiert: Klassifizierung "ist das LTM-würde?". Das
# ist Phase E (Konsolidierung) - dort wird STM in Ruhe durchgesehen
# und gezielt nach LTM promotet.

_SUMMARY_SYSTEM_PROMPT = (
    "Du bist ein Memory-Summarizer für eine Chat-Session zwischen einer "
    "KI und ihrem User. Aktualisiere den rollenden Summary mit dem neuen "
    "Turn. Regeln:\n"
    "- Maximal 500 Zeichen.\n"
    "- Narrativ, in dritter Person ('Sasha hat ...', 'die KI hat ...').\n"
    "- Fokus auf Fakten die der User AUSGESPROCHEN hat - nicht auf das "
    "  was die KI darüber behauptet hat.\n"
    "- Smalltalk und Höflichkeitsfloskeln rauslassen.\n"
    "- WICHTIG: Schreibe NIE Phrasen wie 'die KI hat Fakten gesammelt', "
    "  'die KI hat sich gemerkt', 'die KI hat gespeichert', wenn das im "
    "  Konversationstext bloß behauptet aber nicht durch einen sichtbaren "
    "  Tool-Call belegt wurde. Das wäre Spekulation und führt zu "
    "  Konfabulations-Loops im nächsten Turn. Wenn unklar: bleib bei dem "
    "  was der User wörtlich gesagt hat.\n"
    "- Wenn der bisherige Summary noch leer war: einen frischen schreiben.\n"
    "- Schreib NUR den neuen Summary-Text, nichts drumherum, keine "
    "  Erklärung, keine Aufzählung."
)


def _generate_session_summary(prev_summary: str, user_msg: str, ai_msg: str) -> str:
    """
    Macht einen kurzen LLM-Call der den rollenden STM-Summary mit dem
    neuen Turn aktualisiert. Direkt gegen Ollama, keine Tools, kein
    Streaming - das ist eine interne Maintenance-Operation, der User
    sieht das Ergebnis nie direkt.

    Bei Fehler (Ollama down, Timeout): den alten Summary zurückgeben,
    damit der Auto-Save trotzdem voranschreitet und die stm_list wenigstens
    den neuen Turn kriegt.
    """
    user_msg = (user_msg or '').strip()
    ai_msg   = (ai_msg   or '').strip()
    if not user_msg and not ai_msg:
        return prev_summary

    body = (
        f"Bisheriger Summary:\n{prev_summary or '(noch leer)'}\n\n"
        f"Neuer Turn:\n"
        f"User: {user_msg}\n"
        f"AI:   {ai_msg}\n\n"
        f"Neuer Summary:"
    )

    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":    OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user",   "content": body},
                ],
                "stream":   False,
            },
            timeout=60,
        )
        new = resp.get("message", {}).get("content", "").strip()
        return new or prev_summary
    except Exception:
        return prev_summary


def _async_save_turn(user_msg: str, ai_msg: str):
    """
    Fire-and-forget: User+AI-Turn extrahieren und in den Konzept-
    Graphen einarbeiten (Phase G).

    Vorher (Phase D): STM-Liste + LLM-Summary-Generation. Beides ist
    weggefallen mit dem Graph - der LLM-Extraktor produziert direkt
    strukturierte Konzepte+Edges, und Recent-Context kommt automatisch
    durch Aktivierung des heutigen Time-Knotens.

    Wir behalten stm_append für Rohaufzeichnung der Turns - das ist
    eine Art Konversations-Log das beim Debug nützlich ist und einen
    Backup-Pfad gibt falls der Extraktor mal was übersieht.

    Läuft als Daemon-Thread: blockiert nichts, der User hat seine
    Antwort schon lange. Fehler werden geloggt, nicht weitergereicht.
    """
    if not user_msg or not user_msg.strip():
        return

    def _do_save():
        try:
            # 1. Roh-Turns ins STM-Log (Debug/Backup-Pfad)
            memory.stm_append(role='user', text=user_msg)
            if ai_msg and ai_msg.strip():
                memory.stm_append(role='ai', text=ai_msg)

            # 2. Phase G: LLM-Extraktor zieht Konzepte+Edges raus und
            #    merged sie in den Graphen. Das ist der teure Teil
            #    (LLM-Call, paar Sekunden) - aber wir sind im
            #    Hintergrund-Thread, User merkt nichts.
            consolidation.extract_turn_into_graph(user_msg, ai_msg)
        except Exception as e:
            try:
                import state
                state.push_log(f"[auto-save] FEHLER: {e}")
            except Exception:
                pass

    thread = threading.Thread(target=_do_save, daemon=True, name='ai-auto-save')
    thread.start()


def chat(messages: list, model: str = None, system: str = None) -> str:
    """
    Nicht-streaming Chat-Call (Fallback / interne Nutzung).
    Gibt die komplette Antwort als String zurück.
    """
    model      = model or OLLAMA_MODEL
    # Phase C: Memory-Injection ist jetzt query-aware. Wir nehmen die
    # letzte User-Message als semantische Anfrage und kriegen nur die
    # k relevantesten Einträge in den Prompt - statt wie früher die
    # komplette Memory zu dumpen (skaliert nicht).
    user_query = _last_user_query(messages)
    # Phase G: ein einziger Memory-Kontext aus dem Konzept-Graph statt
    # drei separaten Schichten. Aktivierungs-Spread holt was relevant
    # ist, inklusive Zeit-Anker und Sasha-Profil über die Graph-Topologie.
    mem_ctx = graph.context_for_query(user_query)
    sys_prompt = (system or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
    if mem_ctx:
        sys_prompt += "\n\n" + mem_ctx

    payload = {
        "model":    model,
        "messages": [{"role": "system", "content": sys_prompt}, *messages],
        "tools":    TOOLS,
        "stream":   False,
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

    # User-Query einmal vorne extrahieren - wird sowohl für Retrieval als
    # auch für Auto-Save (Phase D) gebraucht.
    user_query = _last_user_query(messages)

    # Memory + Capabilities nur im regulären Chat injizieren, nicht im
    # Tutor-Modus (Tutor hat eigenen System-Prompt der schon vollständig
    # ist und andere Tool-Sets nutzt).
    if tools is None:
        # Phase G: Memory-Kontext kommt jetzt vollständig aus dem
        # Konzept-Graphen. Aktivierungs-Spread ausgehend von Query-
        # Entry-Points + Sasha-Anker + heutiger Time-Node ersetzt
        # die alten getrennten Schichten (User-Profil, STM-Summary,
        # LTM-Top-K). Der Graph weiß welche Konzepte mit der aktuellen
        # Frage assoziiert sind und liefert sie alle mit Beziehungen.
        mem_ctx    = graph.context_for_query(user_query)
        sys_prompt = (system or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
        if mem_ctx:
            sys_prompt += "\n\n" + mem_ctx
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
            msg   = chunk.get("message", {})
            token = msg.get("content", "")
            if token:
                round_content.append(token)
                yield token  # sofort an den Browser

            # WICHTIG: Ollama (mind. ab 0.17.x mit qwen2.5) liefert die
            # tool_calls in EINEM Chunk irgendwo im Stream - nicht
            # zwingend im done-Chunk. Der done-Chunk kann leer sein und
            # die Calls schon vorher gekommen. Also akkumulieren wir
            # bei JEDEM Chunk, nicht erst am Ende - sonst gehen Tool-
            # Calls still verloren und das Modell wirkt als würde es
            # "drüber reden" obwohl es eigentlich den Call gemacht hat.
            mid_calls = msg.get("tool_calls")
            if mid_calls:
                tool_calls.extend(mid_calls)

            if chunk.get("done"):
                break

        if not tool_calls:
            # Kein Tool-Call → das Modell ist fertig.
            # Phase D: Auto-Save in den Hintergrund schieben (nur im
            # regulären Chat, nicht im Tutor-Modus).
            if tools is None:
                _async_save_turn(user_query, "".join(round_content))
            return

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
