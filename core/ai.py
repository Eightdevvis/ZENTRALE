# core/ai.py
#
# Lokale KI-Schiene (Ollama) – und der Werkzeugkasten, den alle Chat-Pfade teilen.
#
# ── Wer welchen Turn bedient ──────────────────────────────────────────
# Das entscheidet NICHT diese Datei, sondern core/kern.py: kern.chat() fragt
# ai_backends.chat_available(), WER denken darf, und fährt dann den Weg
# (seit 2026-10-06; vorher stand die Weiche in der Chat-Route):
#   local → chat_stream() hier, gegen Ollama (Prompt-Schiene `klein`)
#   cloud → kern.cloud_modul(): core/cloud.py (Anthropic) bzw.
#           core/cloud_openai.py (OpenAI-kompatibel), Prompt-Schiene `gross`
# Prompt-Bausteine, Erlaubnis-Gate und Tool-Ausführung liegen nicht mehr
# hier, sondern in core/ki_prompt.py, core/erlaubnis.py und
# core/ki_werkzeuge.py (unten nur noch als Durchreiche): Werkzeuge laufen
# immer lokal, egal wer denkt.
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
# Das aktive Modell ist konfigurierbar (OLLAMA_MODEL, steht in core/ollama.py);
# jedes Tool-Use-fähige Ollama-Modell sollte funktionieren.
#
# ── Gedächtnis ───────────────────────────────────────────────────────
# Der Konzept-Graph (core/graph.py) ist seit 18.08.2026 in beide Richtungen
# per Default aus: nicht mehr in den Prompt GELESEN (graph.context_for_query
# nur mit ZENTRALE_GRAPH_KONTEXT=1, siehe GRAPH_KONTEXT unten) und nicht mehr
# BESCHRIEBEN (Tripel-Extraktion nur mit ZENTRALE_GRAPH_EXTRAKTION=1, siehe
# core/consolidation.py). Pro Turn landet nur noch der Rohtext im Transkript
# (core/transkript.py); der Identity-Seed (graph.einmal_seeden) läuft weiter. An seine Stelle trat das Datei-Gedächtnis
# (core/gedaechtnis.py) — bisher NUR auf dem Cloud-Pfad: Kopf-Block im
# gecachten System-Prompt (cloud._static_system) plus die Notiz-Werkzeuge
# aus core/profil/gross.py. Die lokale Schiene sieht davon heute nichts.
#
# ── Konfiguration ────────────────────────────────────────────────────
#   OLLAMA_URL, OLLAMA_MODEL, OLLAMA_NUM_CTX usw. – seit 2026-10-06 in
#   core/ollama.py (Defaults und Begründungen dort).

import os
import json as _json   # Tool-Argumente, die Ollama als String liefert
import threading  # Phase D: Auto-Save läuft in Daemon-Threads

import net           # HTTP-Wrapper mit Terminal-Logging
import graph         # Phase G: Konzept-Graph Memory (assoziativ, primary)
import kalender              # Kalender-Layer (Termine, Routinen, erlebt)
import profil                # Prompt-Schienen: welcher Prompt für welches Modell
import werkzeug_schleife      # die EINE Tool-Schleife (lokal, Anthropic, OpenAI)

# ── Ollama-Anbindung: core/ollama.py ─────────────────────────────────
# Adresse, Modell, Kontext, Sampling, Denk-Schalter, Erreichbarkeit und
# Warmup stehen seit 2026-10-06 EINMAL in core/ollama.py. Die Namen bleiben
# hier als Durchreiche stehen: Bench-Skripte, der Tutor und die Status-Route
# lesen sie als ai.OLLAMA_URL usw. Neuer Code nimmt ollama.* direkt.
from ollama import (                 # noqa: E402
    OLLAMA_URL, OLLAMA_MODEL, SUPPORTS_THINK, OLLAMA_KEEP_ALIVE,
    OLLAMA_NUM_CTX, QWEN_SAMPLING, is_available, warmup,
)
from ollama import think_opts as _think_opts   # noqa: E402,F401

# Adaptives Thinking im Live-Chat (chat_stream): pro Turn entscheidet
# _should_think() anhand der letzten User-Message, ob das Modell reflektieren
# soll (Frage/Verifikation -> AN, Schreib-/Aktions-Befehl -> AUS). Gemessen
# (bench_abstention.py 2026-06-08): Reflexion hebt ehrliches "weiss ich nicht"
# um ~9pp (v.a. Bildschirm-Inhalt-Konfabulation 30%->0%), schadet den Aktions-
# Turns nicht (die bleiben think=AUS). Der think-Stream wird sichtbar ins HUD
# gespiegelt (ki-kern), damit die ~3x Latenz UX-Gewinn statt -Verlust wird
# ("warte, ich schau kurz nach"). Kill-Switch fuer A/B + Rollback:
# ZENTRALE_THINK=0 -> komplett aus (Verhalten wie vor dem Feature, think immer
# False). Default an. Greift nur bei Thinking-faehigen Modellen (qwen3*).
ADAPTIVE_THINK = SUPPORTS_THINK and os.environ.get("ZENTRALE_THINK", "1") != "0"


# ── Prompt-Bausteine, Werkzeug-Ausführung, Graph-Seed ──────────────────
# Seit 2026-10-06 in core/ki_prompt.py, core/ki_werkzeuge.py und
# graph.einmal_seeden. Die alten Namen bleiben als Durchreiche zum LESEN und
# AUFRUFEN (Bench-Skripte, Tests). Wer etwas ERSETZEN will, ersetzt das
# Original: ki_prompt.<name>, ki_werkzeuge.ausfuehren, graph.einmal_seeden —
# auch der lokale Weg unten ruft sie über das Modul.
import ki_prompt      # noqa: E402
import ki_werkzeuge   # noqa: E402
from ki_prompt import (                                               # noqa: E402,F401
    _DASHVIEW, GRAPH_KONTEXT, _WEEKDAYS_DE, _MONTHS_DE, _now_prompt,
    _imprint_prompt, _alarm_prompt, _should_think, _last_user_query,
)
from ki_werkzeuge import ausfuehren as _execute_tool                  # noqa: E402,F401
from ki_werkzeuge import _verteilen as _dispatch_tool                  # noqa: E402,F401


# ── Prompt-Bausteine und Tool-Set: siehe core/profil/ ─────────────────
# Diese Texte leben nicht mehr hier. Ein 9B-Modell und ein Frontier-Modell
# brauchen verschiedene Prompts, und solange beide denselben benutzten, war
# jede Anpassung fuer das eine Ballast fuer das andere. Jetzt hat jedes seine
# eigene Schiene (profil/klein.py, profil/gross.py); der Kern hier ist fuer
# beide derselbe.
#
# Die Namen bleiben als Modul-Attribute stehen, damit der lokale Pfad, die
# Bench-Skripte und die Tests unveraendert weiterlaufen — sie zeigen nur
# woanders hin.
from profil.klein import (           # noqa: E402  (nach den anderen Imports)
    _SYSTEM_PROMPT, _CAPABILITIES_PROMPT, _MIC_INPUT_HINT, _DASHBOARD_VIEW,
    ANTWORT_SUFFIX, _ASCII_MARKER_PROMPT, TOOLS,
)


# ── Erlaubnis-Gate und Antwort-Nachbereitung ───────────────────────────
# Seit 2026-10-06 in core/erlaubnis.py und core/ki_antwort.py; das Merken
# nach dem Zug in core/consolidation.py (zug_vormerken). Die Gate-Namen
# bleiben hier als Durchreiche für Bench-Skripte und Tests, die sie LESEN.
# Wer etwas ERSETZEN will (monkeypatch), muss das Original treffen.
from erlaubnis import PERMISSION_REQUIRED_TOOLS, braucht_erlaubnis   # noqa: E402,F401
from erlaubnis import frage as _permission_question                  # noqa: E402,F401
from ki_antwort import marker_ziehen as _extract_ascii_markers       # noqa: E402,F401
from ki_antwort import mit_bildern as _answer_with_images            # noqa: E402,F401


def warmup_async():
    """
    Feuert warmup() in einem Daemon-Thread. Non-blocking - der Caller
    läuft sofort weiter. Wird in core/main.py beim Boot aufgerufen.

    Zusätzlich: Kalender-Datei + Default-Layer sicherstellen, sodass
    der Jetzt-Block beim ersten Chat schon eine Wochen-Ansicht hat.
    """
    try:
        kalender.ensure_init()
    except Exception as e:
        import state     # bis 2026-10-06 fehlte dieser Import: der Fehlerpfad warf NameError
        state.push_log(f"[calendar] init fehlgeschlagen: {e}")
    thread = threading.Thread(target=warmup, daemon=True, name='ai-warmup')
    thread.start()


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False,
                *, abbruch=None):
    """
    Streaming Chat mit Tool-Use Loop.

    Beim ersten Aufruf wird der KI-Identity-Seed im Graphen sicherge-
    stellt (Capabilities + Limits als Knoten verankern).

    Hier wird nur der Prompt gebaut. Die Runden (Modell fragen → Tools →
    zurück) dreht core/werkzeug_schleife.py, dieselbe Schleife wie für die
    Cloud; der Ollama-Dialekt steckt in _OllamaAdapter unten.

    tools/tool_executor: Optional. Wenn nicht angegeben werden die Standard-Tools
    (TOOLS + _execute_tool) verwendet. Die Tutor-Session übergibt hier
    tutor.tools.tools_for(lang) und tutor.tools.execute_tool, um ihre eigenen
    (sprach-abhängigen) Tools mitzubringen.

    via_mic: True wenn die letzte User-Message aus Whisper kam (Spracheingabe).
    Dann wird `_MIC_INPUT_HINT` an den System-Prompt angehaengt, damit die KI
    bei semantischen Bruechen ("Liga-Bit" statt "Gigabit") nachfragen statt
    woertlich antworten kann. Wird nur im regulaeren Chat-Modus angewendet
    (nicht im Tutor-Modus).

    Tool-Calls erscheinen als werkzeug-Events im Chat; Fehler und die
    Rundengrenze als {"fehler": …}, nicht als Antworttext.
    """
    graph.einmal_seeden()
    model         = model or OLLAMA_MODEL
    active_tools  = tools         if tools         is not None else TOOLS
    active_exec   = tool_executor if tool_executor is not None else ki_werkzeuge.ausfuehren

    # User-Query einmal vorne extrahieren - wird sowohl für Retrieval als
    # auch für Auto-Save (Phase D) gebraucht.
    user_query = ki_prompt._last_user_query(messages)

    # Memory + Capabilities nur im regulären Chat injizieren, nicht im
    # Tutor-Modus (Tutor hat eigenen System-Prompt der schon vollständig
    # ist und andere Tool-Sets nutzt).
    if tools is None:
        # Graph-Kontext: per Default AUS (GRAPH_KONTEXT, seit 18.08.2026),
        # mem_ctx bleibt dann leer. Mit ZENTRALE_GRAPH_KONTEXT=1 kommt der
        # Aktivierungs-Spread aus dem Konzept-Graphen zurück in den Prompt.
        mem_ctx    = graph.context_for_query(user_query) if ki_prompt.GRAPH_KONTEXT else ""
        # ── Statischer Kopf (byte-identisch über alle Turns, cachebar) ──
        # Kommt von der Schiene: hier läuft Ollama, also `klein` — mit
        # Antwort-Suffix und Bild-Markern, die ein 9B braucht. Der Cloud-Pfad
        # holt sich denselben Kopf von seiner eigenen Schiene.
        sys_prompt = profil.klein.system(system, dashview=ki_prompt._DASHVIEW,
                                         graph=ki_prompt.GRAPH_KONTEXT)
        # Der Imprint (heute/morgen) gehört noch zum stabilen Teil: er ändert
        # sich mit dem Tag und mit echten Kalender-Änderungen, nicht mit dem
        # Turn. Im wechselnden Teil würde er bei jedem Turn ungecacht bezahlt.
        imprint = ki_prompt._imprint_prompt()
        if imprint:
            sys_prompt += "\n\n" + imprint
        # ── Ab hier wechselt es pro Turn (siehe _PROMPT_ORDER-Notiz in core/ki_prompt.py) ──
        if mem_ctx:
            sys_prompt += "\n\n" + mem_ctx
        # Jetzt-Block direkt HINTER den Graph-Kontext: er widerspricht genau
        # dessen Datums-Knoten („das sind Erinnerungen, nicht heute"), und was
        # zuletzt steht, sitzt am dichtesten an der User-Message.
        sys_prompt += "\n\n" + ki_prompt._now_prompt()
        # Alarm-Kanal: offene Kalender-Erinnerungen randständig anhängen (nicht
        # mehr inline in der read_calendar-Ausgabe). Leer → kein Block.
        alarm_block = ki_prompt._alarm_prompt()
        if alarm_block:
            sys_prompt += "\n\n" + alarm_block
        # Mic-Hinweis ans Ende - sieht die KI direkt vor der aktuellen
        # Message, hoechste Recency-Praesenz.
        if via_mic:
            sys_prompt += "\n\n" + _MIC_INPUT_HINT
    else:
        # Tutor-Modus: eigener System-Prompt, aber Jetzt-Block kriegt er
        # trotzdem - "welcher Tag ist heute" ist sprach-/modus-unabhängig.
        # Auch hier der statische Teil zuerst, der Jetzt-Block hinten dran.
        sys_prompt = (system or _SYSTEM_PROMPT) + "\n\n" + ki_prompt._now_prompt()

    # Arbeits-Nachrichtenliste – wird pro Runde mit Tool-Ergebnissen erweitert
    working_messages = [
        {"role": "system", "content": sys_prompt},
        *messages,
    ]

    # Adaptive Denk-Tiefe (ADAPTIVE_THINK, oben dokumentiert): _should_think()
    # schaut auf die letzte User-Message und entscheidet, ob dieser Turn mit
    # Reflexion läuft. Frage/Verifikation → AN (hebt ehrliche Abstinenz, der
    # think-Stream wird sichtbar ins HUD gespiegelt), reiner Schreib-/Aktions-
    # Befehl → AUS (sonst zerdenkt das 9b die Aktion, gemessen Episode 0 %).
    # Kill-Switch ZENTRALE_THINK=0 → want_think False → wie früher.
    want_think = ADAPTIVE_THINK and ki_prompt._should_think(messages)

    adapter = _OllamaAdapter(model, working_messages, active_tools, want_think,
                             abbruch=abbruch)
    yield from werkzeug_schleife.laufen(
        adapter, tutor_mode=tools is not None, active_exec=active_exec,
        user_query=user_query, fehler_name="Ollama", abbruch=abbruch)


class _OllamaAdapter:
    """Ollama-Dialekt für die gemeinsame Werkzeug-Schleife (core/
    werkzeug_schleife.py): tool_calls irgendwo im Stream, Ergebnisse als
    role=tool ohne Call-Id."""

    def __init__(self, model, msgs, tools, want_think, abbruch=None):
        self.modell, self.msgs, self.tools = model, msgs, tools
        self.abbruch = abbruch      # threading.Event: Sasha hat gestoppt
        self.want_think = want_think
        # WICHTIG gegen den qwen3.5-Template-Bug (#10976): nach dem ERSTEN
        # Tool-Call think=AUS, weil die Synthese-Runde mit think die ganze
        # Antwort ins `thinking`-Feld kippt (content leer). Reine
        # Verständnis-Turns (kein Tool) reflektieren voll.
        self.tool_used = False

    def runde(self):
        # Nur denken, solange kein Tool gelaufen ist; danach Synthese ohne think.
        think_now = self.want_think and not self.tool_used
        think_opts = {"think": think_now} if SUPPORTS_THINK else {}
        payload = {
            "model":      self.modell,
            **think_opts,
            "messages":   self.msgs,
            "tools":      self.tools,
            "stream":     True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            # num_ctx explizit setzen, sonst clampt Ollama auf seinen
            # Mini-Default und schneidet die Sprach-Regel aus dem Fenster
            # (siehe OLLAMA_NUM_CTX-Doku in core/ollama.py - Ursache fuers Chinesisch).
            "options":    {"num_ctx": OLLAMA_NUM_CTX, **QWEN_SAMPLING},
        }

        round_content = []  # Tokens dieser Runde sammeln
        tool_calls    = []

        strom = net.stream_post(f"{OLLAMA_URL}/api/chat", payload)
        for chunk in strom:
            if werkzeug_schleife.gestoppt(self.abbruch):
                # Generator schließen → urlopen schließt die Verbindung, und
                # Ollama bricht die Erzeugung ab, sobald der Client weg ist.
                # Lokal kostet kein Geld, aber die GPU.
                strom.close()
                raise werkzeug_schleife.Gestoppt("".join(round_content))
            msg   = chunk.get("message", {})
            # Reflexions-Stream: Ollama liefert die Denk-Tokens getrennt im
            # `thinking`-Feld. Live als {"reflect": ...}-Event rausgeben.
            # NICHT in round_content → landet weder in der History noch im TTS.
            reflect_tok = msg.get("thinking")
            if reflect_tok:
                yield {"reflect": reflect_tok}
            token = msg.get("content", "")
            if token:
                # NICHT sofort yielden. Content aus einer Runde, die mit einem
                # Tool-Call endet, ist Modell-Geschwätz ("Ich prüfe den
                # Kalender...") und darf den User NIE erreichen - er würde es
                # sehen UND per TTS vorgelesen bekommen. Die Schleife gibt den
                # Text erst aus, wenn KEIN Tool-Call kam. Tradeoff: kein
                # Token-für-Token-Streaming, die Antwort erscheint am Stück.
                round_content.append(token)

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

        calls = []
        for tc in tool_calls:
            fn_args = tc["function"]["arguments"]
            # Ollama liefert arguments manchmal als String, manchmal als Dict
            if isinstance(fn_args, str):
                try:
                    fn_args = _json.loads(fn_args)
                except Exception:
                    fn_args = {}
            calls.append((None, tc["function"]["name"], fn_args))
        return werkzeug_schleife.Runde("".join(round_content), calls,
                                       roh=tool_calls)

    def assistent_anhaengen(self, runde):
        # round_content war Tool-Runden-Geschwätz → an Ollama als Assistant-
        # Turn zurück (Kontext), aber NICHT an den User geyieldet. Reihenfolge
        # wichtig: erst assistant-Nachricht (mit tool_calls), dann für jeden
        # Call eine "tool"-Antwortnachricht.
        self.tool_used = True  # ab jetzt Synthese ohne think (Template-Bug, s.o.)
        self.msgs.append({
            "role":       "assistant",
            "content":    runde.text,
            "tool_calls": runde.roh,
        })

    def ergebnisse_anhaengen(self, ergebnisse):
        for _, text, _ in ergebnisse:
            self.msgs.append({"role": "tool", "content": text})
