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
#   {"werkzeug": …}    Tool-Call start|fertig|fehler (nur Cloud, lokal nicht)
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
#   Modell + Denk-Tiefe kommen aus ai_backends (chat_model/chat_effort).
#   Modell: data/ai_config.json 'chat_models' → Code-Default claude-sonnet-5
#   (providers.py); ZENTRALE_CLOUD_MODEL greift hier NICHT, weil _model()
#   chat_model("claude") mit Provider fragt. Denk-Tiefe: ZENTRALE_CHAT_EFFORT
#   oder data/ai_config.json 'chat_effort', Default 'low'.
#   ZENTRALE_CLOUD_MAX_TOKENS Default 16000

import os

import ai        # Prompt-Blöcke, TOOLS, Gate, Tool-Ausführung — alles wiederverwendet
import graph
import kidebug   # Devtools-Bus: was WIRKLICH rausgeht (scripts/ai_devtools.py)
import werkzeug_schleife  # die EINE Tool-Schleife; hier steht nur der Anthropic-Adapter

# ── Der getrennte Cloud-Graph ──────────────────────────────────────────
# Absoluter Pfad, damit derselbe String immer denselben _Store trifft (graph.py
# cacht Stores nach Pfad — zwei Schreibweisen wären zwei Locks auf einer Datei).
_DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data')
CLOUD_GRAPH = os.path.abspath(os.path.join(_DATA_DIR, 'ai_graph_cloud.json'))

# Modell und Denk-Tiefe kommen aus ai_backends (pro Anbieter gespeichert,
# per Config umstellbar) — NICHT mehr aus eigenen Env-Vars hier. Sonst
# gäbe es zwei Wahrheiten darüber, welches Modell gerade läuft, und die
# Kostenrechnung würde eine davon nicht sehen.
def _model() -> str:
    import ai_backends
    return ai_backends.chat_model("claude") or "claude-sonnet-5"


def _effort() -> str:
    import ai_backends
    return ai_backends.chat_effort()


# Adaptives Denken (und der effort-Regler dazu) gibt es nicht auf jedem
# Modell. Haiku 4.5 quittiert es mit `400 adaptive thinking is not supported
# on this model` — und Haiku ist das naheliegende Billigmodell
# (providers.cheap_model). Stellt jemand den Chat darauf um (chat_models in
# data/ai_config.json), wäre er ohne diese Weiche schlicht kaputt statt
# billig. (Der Budget-Rückfall in ai_backends wechselt heute den ANBIETER,
# nicht das Modell; cheap_model nutzt nur der Cloud-Extraktor.)
#
# Bewusst als Positiv-Liste: ein unbekanntes Modell kriegt kein Denken
# geschickt und funktioniert damit auf jeden Fall. Andersherum (Negativ-
# Liste) wäre jedes neue Billigmodell ein 400er beim ersten Kontakt.
_DENKT_ADAPTIV = ("claude-opus-5", "claude-sonnet-5", "claude-opus-4.8")


def _denk_opts(mdl: str) -> dict:
    """Denk-Parameter für dieses Modell — oder gar keine."""
    if not any(mdl.startswith(m) for m in _DENKT_ADAPTIV):
        return {}
    return {
        # display=summarized: sonst kommen die thinking-Blöcke mit LEEREM
        # Text und das HUD zeigt eine lange Pause statt "ich schau kurz
        # nach…". Kostet nichts extra — gedacht (und abgerechnet) wird so
        # oder so.
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": _effort()},
    }

# max_tokens deckelt Denken UND Antwort zusammen. Zu knapp → die Antwort bricht
# mitten im Satz ab, nachdem das Denken das Budget aufgefressen hat. 16k ist
# reichlich für Dashboard-Antworten; es kostet nichts, was nicht erzeugt wird.
_MAX_TOKENS = int(os.environ.get("ZENTRALE_CLOUD_MAX_TOKENS", "16000"))

_MAX_ROUNDS = 8   # Sicherheitsnetz gegen Endlos-Tool-Schleifen

# Lebensdauer eines Cache-Eintrags. Default sind bei Anthropic 5 Minuten — wer
# zwischen zwei Nachrichten nachdenkt, liest oder telefoniert, hat den Cache
# verloren und schreibt ihn beim nächsten Turn komplett neu. Eine Stunde kostet
# beim SCHREIBEN 2× statt 1,25× des Input-Preises, geschrieben wird pro Turn
# aber nur das Delta — dafür überlebt der Präfix eine ganze Sitzung.
# "5m" für den Rückweg, falls sich das je als Fehlrechnung erweist.
_CACHE_TTL = os.environ.get("ZENTRALE_CACHE_TTL", "1h")

# Zeichenbudget für den Graph-Kontext — greift nur mit ZENTRALE_GRAPH_KONTEXT=1
# (ai.GRAPH_KONTEXT, seit 18.08.2026 per Default aus). Er ändert sich mit jeder Frage, geht
# also bei JEDEM Turn ungecacht raus — und `max_nodes` deckelt nur die Anzahl,
# über die Länge sagt eine Knotenzahl nichts.
_CTX_CHARS = int(os.environ.get("ZENTRALE_CLOUD_CTX_CHARS", "2500"))

# Obergrenze für EINE Verlauf-Nachricht. Die Zahl der Nachrichten ist längst
# gedeckelt (state._chat_history, maxlen=50), ihre Länge nicht: eine komplette
# News-Sendung reitet sonst fünfzig Turns lang mit.
#
# Bewusst NICHT das Fenster von vorne beschneiden. Vorne Nachrichten
# wegzuwerfen verschiebt den Präfix-Anfang und wirft bei jedem Rutsch genau
# den Cache weg, den der ganze Umbau gerade aufgebaut hat. Eine einzelne
# Nachricht zu kürzen ist dagegen deterministisch aus dem gespeicherten Text
# und damit über alle Turns byte-stabil.
_MSG_CHARS = int(os.environ.get("ZENTRALE_CLOUD_MSG_CHARS", "4000"))


def _cc() -> dict:
    """Ein Cache-Breakpoint.

    Anthropic cacht nicht den markierten Block, sondern ALLES davor
    (tools → system → messages, in dieser Reihenfolge gerendert). Ein
    Breakpoint sagt also: "bis hierher ist der Präfix stabil, merk ihn dir".
    Treffer kosten 10 % des Input-Preises.
    """
    return {"type": "ephemeral", "ttl": _CACHE_TTL}

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

def _static_system(system: str | None, tutor_mode: bool) -> str:
    """
    Der statische Kopf: über alle Turns einer Sitzung BYTE-IDENTISCH.

    Gerendert wird tools → system → messages. Ein Breakpoint hinter diesem
    Block cacht also Tool-Schema UND Prompt zusammen — die ~4.700 Token, die
    sonst bei jedem Turn und jeder Tool-Runde voll bezahlt würden.

    Hier darf nichts hinein, was sich PRO TURN ändert. Eine Uhrzeit an dieser
    Stelle macht den Cache zu einer reinen Kostensteigerung: jeder Turn
    schreibt neu, keiner trifft.

    Der Imprint (heute/morgen) darf trotzdem hier stehen — und gehört hierher.
    Er ändert sich nicht mit dem Turn, sondern nur, wenn der Tag umspringt
    oder am Kalender wirklich etwas passiert. Das sind ein, zwei
    Cache-Schreibvorgänge am Tag statt eines pro Turn; im wechselnden Teil
    hätte derselbe Text bei JEDEM Turn ungecacht bezahlt werden müssen.
    Bedingung dafür ist, dass er byte-stabil ist: deshalb Tages-Granularität
    (kein „ab jetzt", keine ablaufenden Uhrzeiten) und kein Blick zurück.
    """
    if tutor_mode:
        # Fremdes Tool-Set (Tutor): eigener vollständiger Prompt, kein Memory,
        # keine Bild-Marker. Faktisch eine eigene, dritte Schiene.
        return system or ai._SYSTEM_PROMPT

    # Die Schiene entscheidet, was hier drinsteht — nicht dieser Modul.
    # Hier draussen faehrt ein Frontier-Modell, also `gross`.
    teile = [_profil().system(system, dashview=ai._DASHVIEW)]
    # Das Datei-Gedaechtnis: Steckbrief, Ziele, Dossier-TITEL. Gehoert in
    # den gecachten Teil — es aendert sich fast nie, und genau darin liegt
    # der Unterschied zum alten Graph-Block, der bei jedem Turn neu und
    # ungecacht mitreiste.
    try:
        import gedaechtnis
        kopf = gedaechtnis.kopf_block()
    except Exception:
        kopf = ""
    if kopf:
        teile.append(kopf)
    imprint = ai._imprint_prompt()
    if imprint:
        teile.append(imprint)
    return "\n\n".join(teile)


def _profil():
    """Die Schiene für den Cloud-Pfad (siehe core/profil/)."""
    import profil
    return profil.fuer_backend("cloud")


def cloud_tools() -> list:
    """Das Tool-Set der Cloud-Schiene, im OpenAI-Schema wie ai.TOOLS."""
    return _profil().TOOLS


def _volatile_text(mem_ctx: str, via_mic: bool, tutor_mode: bool) -> str:
    """
    Das Wechselnde: Jetzt-Block, Alarme, Mic-Hinweis. Der Graph-Kontext
    stand bis 18.08.2026 hier und ist aus (ai.GRAPH_KONTEXT); Imprint und
    Gedaechtnis-Kopf gehoeren NICHT hierher, sondern in _static_system.

    Das steht NICHT mehr im System-Prompt. Dort saß es vor dem gesamten
    Verlauf — und weil die Uhr jeden Turn eine andere ist, hat es alles
    dahinter mitinvalidiert: der ganze Verlauf ging bei jedem Turn ungecacht
    raus (gemessen: in=7236, cache_read=0 für eine Drei-Wort-Antwort).

    Jetzt hängt es als letzter Block an der neuesten User-Nachricht, also
    hinter allem Cachebaren. Es bleibt ungecacht — aber nur es.
    Reihenfolge wie im lokalen Pfad (siehe _PROMPT_ORDER in ai.py).
    """
    parts = []
    if mem_ctx:
        parts.append(mem_ctx)
    parts.append(ai._now_prompt())
    if not tutor_mode:
        # Der Imprint steht NICHT hier, sondern im gecachten Kopf
        # (_static_system). Er ändert sich mit dem Tag, nicht mit dem Turn —
        # hier unten würde er bei jedem Turn ungecacht mitbezahlt.
        alarm = ai._alarm_prompt()
        if alarm:
            parts.append(alarm)
        if via_mic:
            parts.append(ai._MIC_INPUT_HINT)
    return "\n\n".join(parts)


def _system_blocks(system: str | None, mem_ctx: str, via_mic: bool,
                   tutor_mode: bool) -> list:
    """Beide Teile als System-Blöcke — nur noch für Aufrufer, die den Prompt
    am Stück wollen (Tests, Größen-Messung). Der Live-Pfad benutzt
    _static_system und _volatile_text getrennt."""
    return [
        {"type": "text", "text": _static_system(system, tutor_mode),
         "cache_control": _cc()},
        {"type": "text", "text": _volatile_text(mem_ctx, via_mic, tutor_mode)},
    ]


# ── History-Aufbereitung ───────────────────────────────────────────────

def kappen(text: str, grenze: int = None) -> str:
    """Eine einzelne Verlauf-Nachricht auf `grenze` Zeichen bringen.

    Deterministisch aus dem gespeicherten Text — dieselbe Nachricht ergibt in
    jedem Turn dieselben Bytes, sonst wäre der Cache-Präfix hin.

    Gekappt wird in der MITTE: der Anfang einer langen Nachricht sagt, worum
    es ging, das Ende trägt oft das Fazit. Wer nur vorne abschneidet, behält
    die Überschrift einer News-Sendung und verliert, was daraus folgte.

    state._chat_history bleibt unangetastet — die TUI zeigt weiter den
    vollen Text. Gekürzt wird nur, was an die API geht.
    """
    grenze = _MSG_CHARS if grenze is None else grenze
    if grenze <= 0 or len(text) <= grenze:
        return text
    marke = "\n…[gekürzt]…\n"
    rest  = grenze - len(marke)
    kopf  = rest * 2 // 3
    return text[:kopf] + marke + text[len(text) - (rest - kopf):]


def _prepare_messages(messages: list) -> list:
    """
    Bringt die Verlauf-Liste in die Form, die Anthropic akzeptiert:
    nicht leer, beginnt mit 'user', nur user/assistant-Rollen.

    Der lokale Pfad hängt den System-Prompt als erste 'system'-Message in die
    Liste; bei Anthropic ist system ein EIGENES Feld. Solche Einsprengsel
    fliegen hier raus, statt eine 400 zu provozieren.

    Jeder Text wird auf BLOCK-LISTEN-Form normalisiert. Klingt nach Kosmetik,
    ist aber Cache-Voraussetzung: käme dieselbe Nachricht mal als String und
    mal als Ein-Block-Liste, wäre der Präfix nicht mehr verlässlich derselbe.
    """
    msgs = []
    for m in (messages or []):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if not content:
            continue          # leere Turns lehnt die API ab
        if isinstance(content, str):
            content = [{"type": "text", "text": kappen(content)}]
        msgs.append({"role": role, "content": content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": [{"type": "text",
                                              "text": "(kein Text)"}]}]
    return msgs


def _append_volatile(msgs: list, volatile: str) -> None:
    """
    Hängt das Wechselnde als letzten Block an die neueste User-Nachricht und
    setzt den Cache-Breakpoint auf den Block DAVOR.

    Die Reihenfolge ist der ganze Trick: bis einschließlich des User-Textes
    ist der Präfix über die Turns stabil und wird gecacht; das Wechselnde
    steht dahinter und kostet als einziges vollen Preis.

    Ändert `msgs` in place.
    """
    if not msgs:
        return
    letzte = msgs[-1]
    if letzte.get("role") != "user" or not isinstance(letzte.get("content"), list):
        return
    blocks = letzte["content"]
    if blocks:
        blocks[-1]["cache_control"] = _cc()     # Breakpoint VOR dem Wechselnden
    if volatile:
        blocks.append({"type": "text", "text": volatile})


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
    # Tool-Set von der Schiene, nicht aus ai.TOOLS: dort haengt das
    # Set fuer KLEINE Modelle (siehe core/profil/).
    active_tools = tools if tools is not None else cloud_tools()
    active_exec  = tool_executor if tool_executor is not None else ai._execute_tool
    store        = None if tutor_mode else CLOUD_GRAPH

    user_query = ai._last_user_query(messages)

    if tutor_mode:
        mem_ctx = ""
    else:
        # Embedder anmelden, Identity-Seed sicherstellen, dann Kontext von dort.
        prepare_store()
        ai._ensure_seed_once(store=store)
        mem_ctx = (graph.context_for_query(user_query, store=store,
                                           max_chars=_CTX_CHARS)
                   if ai.GRAPH_KONTEXT else "")

    # Statischer Kopf ins system-Feld (gecacht), Wechselndes ans Ende der
    # neuesten User-Nachricht (ungecacht, aber hinter allem Cachebaren).
    sys_blocks = [{"type": "text", "text": _static_system(system, tutor_mode),
                   "cache_control": _cc()}]
    anthro_msgs = _prepare_messages(messages)
    _append_volatile(anthro_msgs, _volatile_text(mem_ctx, via_mic, tutor_mode))
    anthro_tools = _to_anthropic_tools(active_tools)

    adapter = _AnthropicAdapter(_get_client(), model or _model(),
                                sys_blocks, anthro_msgs, anthro_tools)
    yield from werkzeug_schleife.laufen(
        adapter, tutor_mode=tutor_mode, active_exec=active_exec,
        user_query=user_query, store=store)


class _AnthropicAdapter:
    """Anthropic-Dialekt für die gemeinsame Werkzeug-Schleife: tool_use-
    Blöcke, alle tool_results in EINER user-Message, wandernder Breakpoint."""

    grenze = _MAX_ROUNDS
    richtigstellung = False

    def __init__(self, client, mdl, sys_blocks, msgs, tools):
        self.client, self.mdl = client, mdl
        self.sys_blocks, self.msgs, self.tools = sys_blocks, msgs, tools
        # Dritter Breakpoint, der zwischen den Tool-Runden mitwandert: ohne ihn
        # zahlt Runde 3 die Ergebnisse von Runde 2 noch einmal voll. Der alte
        # wird vor dem Setzen des neuen entfernt — es sind maximal 4 erlaubt.
        self.runden_bp = None

    def runde(self):
        round_text = []
        # Devtools: den vollstaendigen Request mitschneiden, BEVOR er rausgeht
        # (siehe core/kidebug.py — aus, solange niemand zuschaut).
        kidebug.request(modell=self.mdl, schiene=_profil().NAME,
                        system=self.sys_blocks, messages=self.msgs,
                        tools=self.tools)
        with self.client.messages.stream(
            model=self.mdl,
            max_tokens=_MAX_TOKENS,
            system=self.sys_blocks,
            tools=self.tools,
            messages=self.msgs,
            **_denk_opts(self.mdl),
        ) as stream:
            for event in stream:
                if event.type != "content_block_delta":
                    continue
                d = event.delta
                if d.type == "thinking_delta":
                    # Innerer Monolog → HUD. Landet NICHT im Text,
                    # also weder in der History noch im TTS.
                    yield {"reflect": d.thinking}
                elif d.type == "text_delta":
                    round_text.append(d.text)
            final = stream.get_final_message()

        _log_usage(final, self.mdl)
        _debug_out(final, self.mdl)

        if final.stop_reason == "refusal":
            # Sicherheits-Klassifikator hat abgelehnt. Kein Fehler im Sinne der
            # API (HTTP 200), aber content ist leer oder abgeschnitten.
            raise werkzeug_schleife.Abbruch(
                "Die Cloud-KI hat diese Anfrage abgelehnt.")

        # Fertig, wenn das Modell keine Tools mehr will — ODER wenn es
        # stop_reason=tool_use meldet, aber gar keinen tool_use-Block liefert.
        # Der zweite Fall sieht nach Haarspalterei aus, ist aber der Unterschied
        # zwischen "Antwort" und einer user-Message mit LEEREM content, die die
        # API mit 400 ablehnt — und einer Runde, die nichts tut außer zu kosten.
        calls = []
        if final.stop_reason == "tool_use":
            calls = [(b.id, b.name, dict(b.input or {})) for b in final.content
                     if getattr(b, "type", None) == "tool_use"]
        text = "".join(round_text) or _text_of(final.content)
        return werkzeug_schleife.Runde(text, calls, roh=final)

    def assistent_anhaengen(self, runde):
        # Assistant-Turn (inkl. tool_use-Blöcken) unverändert als Kontext
        # zurückhängen. final.content enthält auch die thinking-Blöcke; die
        # müssen beim selben Modell UNVERÄNDERT mitgeschickt werden.
        self.msgs.append({"role": "assistant", "content": runde.roh.content})

    def ergebnisse_anhaengen(self, ergebnisse):
        # ALLE tool_results in EINER user-Message zurück. Auf mehrere
        # Nachrichten aufzuteilen bringt dem Modell bei, keine parallelen
        # Tool-Calls mehr zu machen.
        results = [_tool_result(cid, text, is_error=f)
                   for cid, text, f in ergebnisse]
        self.msgs.append({"role": "user", "content": results})
        # Breakpoint ans Ende der Runde nachziehen (alten abräumen).
        if self.runden_bp is not None:
            self.runden_bp.pop("cache_control", None)
        if results:
            results[-1]["cache_control"] = _cc()
            self.runden_bp = results[-1]


# ── Helfer ─────────────────────────────────────────────────────────────

def _tool_result(tool_use_id: str, content, is_error: bool = False) -> dict:
    r = {"type": "tool_result", "tool_use_id": tool_use_id,
         "content": str(content)}
    if is_error:
        r["is_error"] = True
    return r


def _debug_out(final, model: str) -> None:
    """Die ROH-Antwort in den Devtools-Bus — inklusive dem, was der Chat sonst
    versteckt (Denk-Blöcke, Vorgeplänkel vor einem Tool-Call)."""
    if not kidebug.an():
        return
    try:
        u = getattr(final, "usage", None)
        kidebug.emit(
            "ai.out", modell=model,
            stop_reason=getattr(final, "stop_reason", None),
            bloecke=[kidebug._text_von_block(b) for b in (final.content or [])],
            verbrauch={
                "in":          getattr(u, "input_tokens", 0),
                "out":         getattr(u, "output_tokens", 0),
                "cache_read":  getattr(u, "cache_read_input_tokens", 0),
                "cache_write": getattr(u, "cache_creation_input_tokens", 0),
            } if u else None)
    except Exception:
        pass


def _log_usage(final, model: str):
    """Token-Verbrauch UND geschätzte Kosten pro Runde ins Terminal, plus
    Buchung in data/ai_usage.json.

    cache_read > 0 heißt: das Präfix saß im Cache und kostete 10 %. Bleibt der
    Wert über mehrere Turns 0, ist der Cache kaputt — dann hat sich etwas im
    statischen Block verändert (siehe _system_blocks). Das ist der einzige
    verlässliche Weg, das zu merken; ein kaputter Cache fällt sonst nur auf
    der Monatsrechnung auf.

    Der €-Wert ist geschätzt (siehe core/prices.py). Er ist trotzdem das
    Wichtigste an dieser Zeile: ohne Zahl nach jedem Turn ist jede
    Sparmaßnahme Bauchgefühl."""
    try:
        import state
        import usage
        u = final.usage
        rd = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        wr = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        eur = usage.buchen(model,
                           input_tokens=int(u.input_tokens or 0),
                           output_tokens=int(u.output_tokens or 0),
                           cache_read=rd, cache_write=wr)
        state.push_log(
            f"CLOUD ← {model} in={u.input_tokens} cache_read={rd} "
            f"cache_write={wr} out={u.output_tokens} "
            f"≈{eur:.4f}€ (heute {usage.heute_euro():.2f}€)")
    except Exception:
        pass
