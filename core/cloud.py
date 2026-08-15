# core/cloud.py
#
# Cloud-Backend des KERNS (Anthropic). Drop-in für ai.chat_stream() — gleiche
# Signatur, gleiches Event-Protokoll, gleiches Erlaubnis-Gate.
#
# ── Verhältnis zu tutor/cloud.py ────────────────────────────────────────
# tutor/cloud.py war die Vorlage, konnte aber nur Text-Strings yielden und
# hatte bewusst weder Memory noch Gate (geschlossene Vokabel-Allowlist, keine
# lokalen Tools). Der Kern braucht das volle Programm:
#
#   {"reflect": …}     Denk-Tokens live ins HUD
#   {"ascii": …, "name": …}  Inline-Bild aus einem [[bild: …]]-Marker
#   {"permission": …}  JA/NEIN-Dialog, BLOCKIERT bis zum Klick
#   {"cinema": True}   Sendungs-Modus vor dem News-Briefing
#   "…"                der eigentliche Antworttext
#
# ── Was hier NICHT passiert ─────────────────────────────────────────────
# Tool-Ausführung. Der Modellwechsel betrifft, WER DENKT, nicht wer ausführt:
# _dispatch_tool/_execute_tool in ai.py bleiben unangetastet und laufen
# weiterhin lokal. Diese Datei übersetzt nur zwischen zwei Tool-Dialekten —
# aus geparsten Ollama-Textblöcken werden native tool_use-Blöcke und zurück.
#
# ── Isolations-Invariante ───────────────────────────────────────────────
# LOKAL SIEHT ALLES VON CLOUD. CLOUD SIEHT NICHTS VON LOKAL.
# Deshalb hat der Cloud-Pfad einen EIGENEN Graphen (data/ai_graph_cloud.json).
# Würde er graph.context_for_query() ohne store rufen, ginge Sashas kompletter
# Konzept-Graph mit jedem Turn an die API. Das lokale Modell darf den
# Cloud-Graphen später lesen und einen zweiten Layer darauf bauen; es schreibt
# nie hinein. Jetzt eine Zeile Konfiguration, in einem Jahr ein
# Entwirrungs-Albtraum.
#
# ── Was die Cloud trotzdem sieht ────────────────────────────────────────
# Tool-ERGEBNISSE gehen zurück ans Modell: Dateiinhalte aus read_file,
# Kalendereinträge, Mail-Betreffzeilen, News-Texte. Nicht nur die Frage. Der
# Erlaubnis-Dialog begrenzt SCHREIBENDE Aktionen, nicht den Abfluss lesender.
# Das ist bewusst so und gehört zum Bedrohungsmodell (memory/betrieb/sicherheit.md).
#
# ── Konfiguration ───────────────────────────────────────────────────────
#   ANTHROPIC_API_KEY        Pflicht (kommt via ai_config aus data/ai_config.json)
#   ZENTRALE_CLOUD_MODEL     Default 'claude-opus-5'
#   ZENTRALE_CLOUD_EFFORT    low|medium|high|xhigh|max, Default 'medium'
#   ZENTRALE_CLOUD_MAX_TOKENS Default 16000

import os

import ai        # Prompt-Blöcke, TOOLS, Gate, Tool-Ausführung — alles wiederverwendet
import graph

# ── Der getrennte Cloud-Graph ──────────────────────────────────────────
# Absoluter Pfad, damit derselbe String immer denselben _Store trifft (graph.py
# cacht Stores nach Pfad — zwei Schreibweisen wären zwei Locks auf einer Datei).
_DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data')
CLOUD_GRAPH = os.path.abspath(os.path.join(_DATA_DIR, 'ai_graph_cloud.json'))

_MODEL      = os.environ.get("ZENTRALE_CLOUD_MODEL", "claude-opus-5")

# Effort steuert Denk-Tiefe UND Token-Verbrauch. 'medium' als Default, weil der
# Kern ein Dashboard-Assistent ist: viele kurze Turns, Latenz sichtbar, Kosten
# laufen über die Menge. Für eine harte Analyse per Env auf 'high'/'xhigh'.
_EFFORT     = os.environ.get("ZENTRALE_CLOUD_EFFORT", "medium")

# max_tokens deckelt Denken UND Antwort zusammen. Zu knapp → die Antwort bricht
# mitten im Satz ab, nachdem das Denken das Budget aufgefressen hat. 16k ist
# reichlich für Dashboard-Antworten; es kostet nichts, was nicht erzeugt wird.
_MAX_TOKENS = int(os.environ.get("ZENTRALE_CLOUD_MAX_TOKENS", "16000"))

_MAX_ROUNDS = 8   # Sicherheitsnetz gegen Endlos-Tool-Schleifen

_client = None    # lazy: anthropic erst importieren, wenn wirklich genutzt


def _get_client():
    """Lazy-Init des Anthropic-Clients (ANTHROPIC_API_KEY aus der Env)."""
    global _client
    if _client is None:
        import anthropic  # type: ignore  – nur im Cloud-Pfad importiert
        _client = anthropic.Anthropic()
    return _client


_store_bereit = False


def prepare_store():
    """
    Meldet den Cloud-Graphen mit seinem Embedder an und zieht fehlende
    Vektoren nach. Einmal pro Prozess, lazy — nicht beim Import, weil die
    API-Keys erst über ai_config in die Env wandern.

    Warum überhaupt ein eigener Embedder: Ollama läuft nur daheim. Ohne
    Embeddings findet der Graph keine Entry-Points und die Cloud-KI ist
    unterwegs gedächtnislos — also genau dort blind, wo sie gebraucht wird.
    Gibt es einen Cloud-Embedder, läuft der Cloud-Graph über den; sonst
    bleibt es beim lokalen (dann eben nur daheim mit Gedächtnis).

    Der LOKALE Graph bleibt in jedem Fall bei Ollama. Ihn per Cloud zu
    embedden hieße, Sashas Konzeptnamen an einen Anbieter zu schicken.
    """
    global _store_bereit
    if _store_bereit:
        return
    import embeddings
    kind = "cloud" if embeddings.cloud_available() else "local"
    graph.register_store(CLOUD_GRAPH, kind)
    _store_bereit = True
    # Knoten, die ohne erreichbaren Embedder angelegt wurden, haben keinen
    # Vektor und wären für die Suche unsichtbar. Idempotent, no-op wenn nichts
    # fehlt.
    try:
        graph.reembed_missing(CLOUD_GRAPH)
    except Exception:
        pass


def is_available() -> bool:
    """Ist der Cloud-Pfad überhaupt benutzbar? (SDK installiert + Key gesetzt.)
    Sagt NICHTS über die Erreichbarkeit — dafür ist ai_backends zuständig."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


# ── Tool-Schema-Übersetzung ────────────────────────────────────────────

def _to_anthropic_tools(openai_tools: list) -> list:
    """
    Übersetzt das OpenAI/Ollama-Schema (ai.TOOLS) ins Anthropic-Format.

    OpenAI:    {"type": "function", "function": {"name", "description", "parameters"}}
    Anthropic: {"name", "description", "input_schema"}

    Reihenfolge bleibt wie in ai.TOOLS — Tools werden VOR dem System-Prompt
    gerendert und sind damit Teil des Cache-Präfixes. Umsortieren würde den
    Cache jedes Mal wegwerfen (siehe _system_blocks).
    """
    out = []
    for t in openai_tools or []:
        fn = t.get("function", t)          # toleriert beide Formen
        out.append({
            "name":         fn["name"],
            "description":  fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return out


# ── System-Prompt: statisch vorn (gecacht), Wechselndes hinten ─────────

def _system_blocks(system: str | None, mem_ctx: str, via_mic: bool,
                   tutor_mode: bool) -> list:
    """
    Baut den System-Prompt als ZWEI Blöcke:

      [0] statisch  — über alle Turns byte-identisch, mit cache_control
      [1] wechselnd — Graph-Kontext, Jetzt-Block, Alarme, Mic-Hinweis

    Warum getrennt: ein Cache-Treffer verlangt ein byte-identisches Präfix.
    Gerendert wird tools → system → messages, ein Breakpoint auf dem letzten
    statischen System-Block cacht also Tool-Schema UND statischen Prompt
    zusammen — genau die ~8.000 Token, die sonst bei JEDEM Turn und JEDER
    Tool-Runde voll bezahlt würden. Cache-Treffer kosten 10 % des Input-
    Preises; das ist der mit Abstand größte Kostenhebel im ganzen Umbau.
    Der Jetzt-Block enthält die Uhrzeit und darf deshalb NIEMALS in Block [0].
    (Die Reihenfolge im lokalen Pfad ist dieselbe, siehe _PROMPT_ORDER in ai.py.)
    """
    if tutor_mode:
        # Fremdes Tool-Set (Tutor): eigener vollständiger Prompt, kein Memory,
        # keine Bild-Marker. Trotzdem statisch/wechselnd getrennt.
        static = system or ai._SYSTEM_PROMPT
    else:
        static = (system or ai._SYSTEM_PROMPT) + "\n\n" + ai._CAPABILITIES_PROMPT
        static += ai.ANTWORT_SUFFIX
        static += ai._ASCII_MARKER_PROMPT
        if ai._DASHVIEW:
            static += ai._DASHBOARD_VIEW

    # Wechselnder Teil, gleiche Reihenfolge wie im lokalen Pfad.
    parts = []
    if mem_ctx:
        parts.append(mem_ctx)
    parts.append(ai._now_prompt())
    if not tutor_mode:
        alarm = ai._alarm_prompt()
        if alarm:
            parts.append(alarm)
        if via_mic:
            parts.append(ai._MIC_INPUT_HINT)

    return [
        {"type": "text", "text": static,
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "\n\n".join(parts)},
    ]


# ── History-Aufbereitung ───────────────────────────────────────────────

def _prepare_messages(messages: list) -> list:
    """
    Bringt die Verlauf-Liste in die Form, die Anthropic akzeptiert:
    nicht leer, beginnt mit 'user', nur user/assistant-Rollen.

    Der lokale Pfad hängt den System-Prompt als erste 'system'-Message in die
    Liste; bei Anthropic ist system ein EIGENES Feld. Solche Einsprengsel
    fliegen hier raus, statt eine 400 zu provozieren.
    """
    msgs = []
    for m in (messages or []):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if not content:
            continue          # leere Turns lehnt die API ab
        msgs.append({"role": role, "content": content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "(kein Text)"}]
    return msgs


def _text_of(blocks) -> str:
    """Klartext aus einer Anthropic-Content-Liste (thinking/tool_use ignoriert)."""
    return "".join(b.text for b in blocks if getattr(b, "type", None) == "text")


# ── Der Hauptpfad ──────────────────────────────────────────────────────

def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False):
    """
    Drop-in für ai.chat_stream() gegen die Anthropic-API.

    Gleiche Signatur, gleiches Event-Protokoll (siehe Kopf dieser Datei).
    tools/tool_executor: None → Kern-Tools (ai.TOOLS + ai._execute_tool).
    Ein fremdes Tool-Set (Tutor) schaltet Memory, Bild-Marker und Gate ab —
    exakt wie im lokalen Pfad.

    Ablauf pro Runde:
      1. Streaming-Call, Denk-Tokens live als {"reflect": …} durchreichen
      2. Antworttext PUFFERN (nicht sofort yielden)
      3. stop_reason != tool_use → gepufferter Text IST die Antwort, fertig
      4. sonst: Tools ausführen (Gate davor), Ergebnisse anhängen, zurück zu 1

    Warum der Text gepuffert wird: Text aus einer Runde, die mit einem
    Tool-Call endet, ist Vorgeplänkel ("Ich schau mal im Kalender…"). Der
    User würde es sehen UND per TTS vorgelesen bekommen. Gleiche Entscheidung
    wie im lokalen Pfad.
    """
    tutor_mode = tools is not None
    active_tools = tools         if tools         is not None else ai.TOOLS
    active_exec  = tool_executor if tool_executor is not None else ai._execute_tool
    store        = None if tutor_mode else CLOUD_GRAPH

    user_query = ai._last_user_query(messages)

    if tutor_mode:
        mem_ctx = ""
    else:
        # Embedder anmelden, Identity-Seed sicherstellen, dann Kontext von dort.
        prepare_store()
        ai._ensure_seed_once(store=store)
        mem_ctx = graph.context_for_query(user_query, store=store)

    sys_blocks   = _system_blocks(system, mem_ctx, via_mic, tutor_mode)
    anthro_msgs  = _prepare_messages(messages)
    anthro_tools = _to_anthropic_tools(active_tools)

    client = _get_client()

    for _ in range(_MAX_ROUNDS):
        round_text = []
        try:
            with client.messages.stream(
                model=model or _MODEL,
                max_tokens=_MAX_TOKENS,
                # display=summarized: sonst kommen die thinking-Blöcke mit
                # LEEREM Text und das HUD zeigt eine lange Pause statt "ich
                # schau kurz nach…". Kostet nichts extra — gedacht (und
                # abgerechnet) wird so oder so.
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": _EFFORT},
                system=sys_blocks,
                tools=anthro_tools,
                messages=anthro_msgs,
            ) as stream:
                for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    d = event.delta
                    if d.type == "thinking_delta":
                        # Innerer Monolog → HUD. Landet NICHT in round_text,
                        # also weder in der History noch im TTS.
                        yield {"reflect": d.thinking}
                    elif d.type == "text_delta":
                        round_text.append(d.text)
                final = stream.get_final_message()
        except Exception as e:
            yield f"[Cloud-Fehler: {e}]"
            return

        _log_usage(final)

        if final.stop_reason == "refusal":
            # Sicherheits-Klassifikator hat abgelehnt. Kein Fehler im Sinne der
            # API (HTTP 200), aber content ist leer oder abgeschnitten.
            yield "[Die Cloud-KI hat diese Anfrage abgelehnt.]"
            return

        tool_blocks = [b for b in final.content
                       if getattr(b, "type", None) == "tool_use"]

        # Fertig, wenn das Modell keine Tools mehr will — ODER wenn es
        # stop_reason=tool_use meldet, aber gar keinen tool_use-Block liefert.
        # Der zweite Fall sieht nach Haarspalterei aus, ist aber der Unterschied
        # zwischen "Antwort" und einer user-Message mit LEEREM content, die die
        # API mit 400 ablehnt — und einer Runde, die nichts tut außer zu kosten.
        if final.stop_reason != "tool_use" or not tool_blocks:
            answer = "".join(round_text) or _text_of(final.content)
            if tutor_mode:
                if answer:
                    yield answer
            else:
                yield from ai._answer_with_images(answer, user_query, store=store)
            return

        # ── Tool-Runde ────────────────────────────────────────────────
        # Assistant-Turn (inkl. tool_use-Blöcken) unverändert als Kontext
        # zurückhängen. final.content enthält auch die thinking-Blöcke; die
        # müssen beim selben Modell UNVERÄNDERT mitgeschickt werden.
        anthro_msgs.append({"role": "assistant", "content": final.content})

        results = []
        beendet = False
        for block in tool_blocks:
            ausgang = yield from run_tool(
                block.name, dict(block.input or {}),
                tutor_mode=tutor_mode, active_exec=active_exec,
                user_query=user_query, store=store)
            if ausgang[0] == "stop":
                beendet = True
                break
            _, text, fehler = ausgang
            results.append(_tool_result(block.id, text, is_error=fehler))
        if beendet:
            return

        # ALLE tool_results in EINER user-Message zurück. Auf mehrere
        # Nachrichten aufzuteilen bringt dem Modell bei, keine parallelen
        # Tool-Calls mehr zu machen.
        anthro_msgs.append({"role": "user", "content": results})

    yield "\n[Maximale Tool-Tiefe erreicht]"


# ── Ein Tool-Call, dialekt-unabhängig ──────────────────────────────────

def run_tool(name: str, args: dict, *, tutor_mode: bool, active_exec,
             user_query, store):
    """
    Behandelt EINEN Tool-Call: terminale Tools, Knopf-Dialog, Erlaubnis-Gate,
    Ausführung. Generator — yieldet die Events, mit `yield from` aufrufen.

    Rückgabe:
      ("stop",)                  Turn ist zu Ende (terminales Tool hat die
                                 Antwort schon geyieldet)
      ("result", text, is_error) Ergebnis, das als tool_result zurück soll

    Warum hier und nicht im Loop: es gibt ZWEI Cloud-Dialekte (Anthropic mit
    tool_use-Blöcken, OpenAI-kompatibel mit tool_calls). Was ein Tool-Call
    BEDEUTET — was terminal ist, was bestätigt werden muss — ist in beiden
    dasselbe und darf nicht zweimal gepflegt werden. Nur das Verpacken des
    Ergebnisses unterscheidet sich, und das macht der jeweilige Loop.
    """
    # antwort-Tool ist TERMINAL: der Text IST die finale Antwort.
    if not tutor_mode and name == "antwort":
        answer = str(args.get("text", "")).strip()
        yield from ai._answer_with_images(answer, user_query, store=store)
        return ("stop",)

    # lies_news ist TERMINAL: das Briefing ist schon moderiert und wird
    # direkt gestreamt, statt es nacherzählen zu lassen.
    if not tutor_mode and name == "lies_news":
        yield {"cinema": True}
        show = active_exec(name, args)
        if show.startswith("Sendung (Stand") and "\n\n" in show:
            show = show.split("\n\n", 1)[1]
        yield show
        return ("stop",)

    # frage_knopf: die KI baut selbst einen Knopf-Dialog.
    if not tutor_mode and name == "frage_knopf":
        wahl = yield from _ask_buttons(args)
        return ("result", f"Sasha hat gewählt: {wahl}.", False)

    # Erlaubnis-Gate: Python-seitig, NICHT modellgetrieben. Fremde Tool-Sets
    # (Tutor) gaten wir nicht.
    if not tutor_mode and name in ai.PERMISSION_REQUIRED_TOOLS:
        erlaubt = yield from _ask_permission(name, args)
        if not erlaubt:
            return ("result",
                    f"Sasha hat die Aktion '{name}' abgelehnt - NICHT "
                    f"ausführen, nichts eintragen. Kurz bestätigen dass du "
                    f"es lässt.", False)

    # Ein krachendes Tool darf den Turn nicht abreißen: die Runde ist bezahlt.
    # Das Modell soll den Fehler SEHEN und reagieren können, statt zu
    # behaupten, es hätte funktioniert. (Der lokale Ollama-Pfad wirft hier
    # weiter — sein Tool-Protokoll kennt keine Fehler-Markierung.)
    try:
        return ("result", active_exec(name, args), False)
    except Exception as e:
        return ("result", f"Tool '{name}' ist fehlgeschlagen: {e}", True)


# ── Helfer ─────────────────────────────────────────────────────────────

def _tool_result(tool_use_id: str, content, is_error: bool = False) -> dict:
    r = {"type": "tool_result", "tool_use_id": tool_use_id,
         "content": str(content)}
    if is_error:
        r["is_error"] = True
    return r


def _ask_buttons(args: dict):
    """frage_knopf: Knopf-Dialog auslösen, blockieren, Wahl zurückgeben.
    Generator (yieldet das permission-Event) — mit `yield from` aufrufen."""
    import state
    frage = str(args.get("frage", "")).strip() or "Wie soll ich weitermachen?"
    opts  = [str(o).strip() for o in (args.get("optionen") or []) if str(o).strip()]
    if len(opts) < 2:
        opts = ["ja", "nein"]
    opts = opts[:4]                       # Leiste fasst max 4 Knöpfe sauber
    state.push_log(f"AI →  FRAGE {opts}: {frage[:140]}")
    state.request_permission(options=opts, timeout_default="(keine Antwort)")
    yield {"permission": {"frage": frage, "optionen": opts}}
    wahl = state.wait_permission()        # BLOCKIERT bis Klick/Timeout
    state.push_log(f"AI ←  WAHL: {wahl}")
    return wahl


def _ask_permission(name: str, args: dict):
    """Erlaubnis-Gate: JA/NEIN-Dialog vor einem schreibenden Tool.
    Generator — mit `yield from` aufrufen. True = ausführen."""
    import state
    frage = ai._permission_question(name, args)
    state.push_log(f"AI →  ERLAUBNIS? {frage[:160]}")
    state.request_permission()
    yield {"permission": {"frage": frage}}
    antwort = state.wait_permission()     # BLOCKIERT bis Klick/Timeout
    state.push_log(f"AI ←  ERLAUBNIS: {antwort}")
    return antwort == "ja"


def _log_usage(final):
    """Token-Verbrauch pro Runde ins Dashboard-Terminal.

    cache_read > 0 heißt: das Präfix saß im Cache und kostete 10 %. Bleibt der
    Wert über mehrere Turns 0, ist der Cache kaputt — dann hat sich etwas im
    statischen Block verändert (siehe _system_blocks). Das ist der einzige
    verlässliche Weg, das zu merken; ein kaputter Cache fällt sonst nur auf
    der Monatsrechnung auf."""
    try:
        import state
        u = final.usage
        state.push_log(
            f"CLOUD ← in={u.input_tokens} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
            f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"out={u.output_tokens}")
    except Exception:
        pass
