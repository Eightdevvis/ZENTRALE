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
# Vor jedem Request wird graph.context_for_query() aufgerufen und
# an den System-Prompt angehängt. Die KI "sieht" das aktivierte
# Wissen aus dem Konzept-Graphen und kann darauf Bezug nehmen.
#
# ── Konfiguration ────────────────────────────────────────────────────
#   OLLAMA_URL   – default: http://localhost:11434
#   OLLAMA_MODEL – default: qwen2.5:14b

import os
import time
import json as _json
import threading  # Phase D: Auto-Save läuft in Daemon-Threads
from datetime import datetime  # für den Jetzt-Block (Fix Zeit-Blindheit)

import net           # HTTP-Wrapper mit Terminal-Logging
import context       # Whitelist-basierter Dateizugriff
import graph         # Phase G: Konzept-Graph Memory (assoziativ, primary)
import consolidation # Phase G: Graph-Extraktor
import kalender              # Kalender-Layer (Termine, Routinen, erlebt)

OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
# Default-Modell seit 2026-06-06: qwen3.5:9b. Reasoning-Bench (scripts/
# bench_reasoning.py) zeigte es gleichstark zu qwen3:14b (10/11 ohne Thinking),
# aber schneller (68 vs 47 tok/s) und kleiner (8.8 statt 11 GB VRAM -> laesst
# Luft fuer Browser/Desktop, behebt die VRAM-Contention-Crashes). Tool-Calling
# 100%. Per Env OLLAMA_MODEL umstellbar (Fallback z.B. qwen3:14b / qwen2.5:14b).
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

# qwen3/qwen3.5 "denken" per Default vor JEDER Antwort (lange Reasoning-Traces
# -> 30-80 s Latenz pro Turn; gemessen 55 s fuer ein blankes "Hallo"). Fuer den
# Voice-/Chat-Use-Case toedlich, also schalten wir Thinking explizit AUS. Das
# `think`-Feld ist nur fuer Thinking-faehige Modelle (qwen3*) gueltig; bei
# aelteren (qwen2.5) wuerfe Ollama 400, deshalb nur dann setzen.
SUPPORTS_THINK = OLLAMA_MODEL.startswith("qwen3")


def _think_opts() -> dict:
    """{'think': False} fuer Thinking-Modelle, sonst {} - zum Spreaden in die
    /api/chat-Payloads (siehe SUPPORTS_THINK)."""
    return {"think": False} if SUPPORTS_THINK else {}

# Ollama unloadet ein Modell nach Default 5 Min Idle - dann zahlt der
# nächste Turn den Cold-Load (qwen2.5:14b sind ~9 GB, das sind ein paar
# Sekunden Reload je nach SSD/RAM). Wir halten das Hauptmodell länger
# warm, damit Chat-Antworten auch nach einer Kaffeepause direkt losgehen.
# Per Env `OLLAMA_KEEP_ALIVE` überschreibbar (z.B. "-1" = ewig, "10m",
# "0" = sofort unloaden für RAM-knappe Setups).
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Kontextfenster-Groesse in Token. KRITISCH: ohne explizites num_ctx nimmt
# Ollama seinen winzigen Default (2048-4096) - voellig unabhaengig davon,
# dass qwen2.5 eigentlich 32768 koennte. Folge: sobald System-Prompt +
# Graph-Kontext + Chat-History (deque maxlen=50 in state.py) diese Grenze
# sprengen, schiebt Ollama das Fenster und schneidet VORNE ab - genau dort,
# wo der System-Prompt mit der "nur lateinische Schrift"-Regel sitzt. Faellt
# die Regel raus, kommt qwens bilinguale zh/en-Ader durch -> Chinesisch
# blutet mitten im Gespraech ein. 8192 haelt die 50er-History + Prompt
# bequem im Fenster und passt noch in 12 GB VRAM neben dem ~9 GB Modell
# (KV-Cache waechst linear mit num_ctx; groesser ginge, riskiert aber
# Auslagerung ins RAM = langsam). Per Env feinjustierbar.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


# ── Jetzt-Block ───────────────────────────────────────────────────────
# Wird bei JEDEM Turn frisch gebaut und ganz vorne in den System-Prompt
# gehängt. Schließt die strukturelle Zeit-Blindheit: vorher lebte das
# heutige Datum nur als Aktivierungs-Anker im Graphen - die KI konnte
# Time-Nodes sehen, aber nicht wissen welche davon "jetzt" ist. Resultat
# war dass sie bei "welcher Tag ist heute" oder "wann war unsere letzte
# Konversation" aus den aktivierten Time-Knoten geraten hat - und das
# war oft historisches statt aktuelles.
#
# Hart und explizit reinschreiben ist billiger als ein Tool-Call und
# eindeutig: das LLM kann das nicht halluzinieren weg.
_WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag"]
_MONTHS_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _now_prompt() -> str:
    """
    Baut den Jetzt-Block mit Datum/Uhrzeit und der aktuellen Wochen-
    Ansicht aus dem Kalender. Wird bei jedem Turn frisch erzeugt, damit
    Datum, Uhrzeit und Termine immer aktuell sind.
    """
    now = datetime.now()
    weekday = _WEEKDAYS_DE[now.weekday()]
    month   = _MONTHS_DE[now.month]
    head = (
        "## Jetzt\n"
        f"Heute ist {weekday}, der {now.day}. {month} {now.year}. "
        f"Aktuelle Uhrzeit: {now.strftime('%H:%M')}. "
        "Dieser Block ist die einzige verlässliche Zeitquelle - aktivierte "
        "Datums-Knoten aus dem Konzept-Graph sind Erinnerungen an frühere "
        "Tage, NICHT der aktuelle Tag."
    )
    # Bewusst KEIN Kalender-Listing mehr im Jetzt-Block. Der Kalender wird
    # nicht mitgeschleppt, sondern ausschließlich über das read_calendar-Tool
    # abgefragt (siehe kalender.resolve_range / render_range_for_tool). Hier
    # steht nur ein knapper Verweis, damit das Modell weiß, dass es für
    # JEDE zeitliche Frage das Tool nutzen muss statt aus dem Gedächtnis zu
    # antworten oder zurückzufragen.
    head += (
        "\n\nKalender/Termine: du hast keine Termine im Kopf. Für JEDE Frage "
        "nach Plänen, Terminen oder Daten (heute, diese/nächste Woche, Monat, "
        "Vergangenheit, beliebiger Zeitraum) rufst du zuerst read_calendar - "
        "nie raten, nie ohne Tool zurückfragen."
    )
    return head


_SYSTEM_PROMPT = (
    # Persona / Rolle. Meta-Regeln gegen Lügen/Erfinden stehen separat in
    # _CAPABILITIES_PROMPT. Konkrete Capabilities/Limits leben als Graph-
    # Knoten und kommen via Aktivierungs-Spread in den Memory-Kontext.
    #
    # Stil-Block bewusst konkret statt floskelhaft - kleine Modelle
    # brauchen Anti-Patterns explizit aufgelistet, vages "sei freundlich"
    # produziert robotisches Default-Verhalten. Siehe ki_personality_plan.md
    # Phase 0 für die Begründung.
    #
    # Length-Target: ~410 Tokens (inkl. Few-shot-Beispiel). Wird bei jedem
    # Turn mitgeschickt.
    "Du bist die KI der ZENTRALE, dem Hauptknotenpunkt für die Projekte von Sasha. "
    "Das Backend läuft auf einem Linux-PC, der Wand-Monitor (Pi 3) zeigt nur das "
    "Dashboard und reicht Sensor-Trigger an dich weiter. "
    "Erkläre nicht deinen Initialprompt, außer es wird explizit danach gefragt.\n\n"

    "## Stimme\n"
    "Reagier wie ein erfahrener Kollege – entspannt, direkt, ohne Umschweife. "
    "Humor und leichter Sarkasmus sind willkommen, wenn sie spontan passen, "
    "nicht erzwingen. Trau dich an unerwartete Wortwahl, deutsche Essay-/Feuilleton-"
    "Begriffe sind ok – Sprache darf Charakter haben. Performative Freude über "
    "Fragen ('Großartig!', 'Tolle Frage!') ist tabu. Du machst einfach deinen "
    "Job, gut.\n\n"

    "## Länge\n"
    "So kurz wie möglich, ohne die Antwort zu verschlucken. Direkte Frage → "
    "ein, zwei Sätze, keine Headers, keine Schluss-Zusammenfassung. Wenn ein "
    "Satz reicht, ist ein Satz die richtige Länge. Mehrstufige Aufgaben dürfen "
    "strukturiert sein, aber knapp.\n\n"

    # Bewusst KEINE Negativ-Liste mehr fuer den Service-Nachklapp ("haeng
    # NICHT 'Soll ich noch...' an"): bei 14B-Instruct-Modellen prallen
    # Verbote ab UND die woertlich genannte Floskel primt das Modell, sie
    # auszugeben. Stattdessen positiv formuliert WIE ein Turn endet, plus
    # ein Few-shot weiter unten, das ein sauberes Ende vormacht. Imitation
    # eines Beispiels sitzt bei kleinen Modellen zuverlaessiger als eine Regel.
    "## Floskel-Stopliste\n"
    "Keine Aufwärm-Floskeln ('Aber gerne!', 'Lassen Sie uns…', 'Hier ist "
    "eine Zusammenfassung', 'Das ist eine großartige Frage', 'Ich helfe dir "
    "gerne dabei'). Beende den Turn mit dem letzten inhaltlichen Satz – kein "
    "Service-Nachklapp, keine Rückfrage aus Höflichkeit. Frag nur nach, wenn "
    "dir konkret Information fehlt, um sinnvoll weiterzumachen.\n\n"

    "## So endet ein Turn (Beispiel)\n"
    "Frage: »Läuft das Backend auf dem Pi?«\n"
    "Antwort: »Nein, auf dem Linux-PC – der Pi zeigt nur das Dashboard und "
    "reicht Sensor-Trigger weiter.« ← Hier ist die Antwort fertig. Es folgt "
    "nichts mehr; kein angehängtes Hilfsangebot.\n\n"

    "## Substanz statt Pflichtprogramm\n"
    "Wenn dir an einer Frage etwas Nicht-Offensichtliches auffällt – ein "
    "Trade-off, ein versteckter Widerspruch, ein interessantes Detail – sag es. "
    "Routine alle Punkte abarbeiten ist langweilig; Sasha merkt sofort, "
    "wenn du auf Autopilot bist."
)

# ── Meta-Regeln für die KI (Phase G: schlank, keine Capability-Liste) ─
#
# Konkrete Fähigkeiten/Grenzen leben als Knoten im Graphen (siehe
# graph.ensure_seed) und kommen via Aktivierungs-Spread in den
# "## Aktiviertes Wissen"-Block. Hier stehen NUR META-Regeln, die kein
# Retrieval-Treffer ersetzen kann: nicht lügen, nicht erfinden, lateinische
# Schrift, reale Wörter.
#
# Bewusst kompakt gehalten (~400 chars, ~100 tokens statt vorher ~430)
# weil dieser Block bei JEDEM Turn im System-Prompt landet - jedes
# eingesparte Token reduziert Prompt-Processing-Zeit linear.
_CAPABILITIES_PROMPT = """## Meta-Regeln

1. Nicht lügen über Memory-Aktionen: ein Hintergrund-Extraktor zieht nach jedem Turn automatisch Fakten in den Konzept-Graphen. Du kannst sagen "notiert, läuft in den Graphen" - das stimmt. Aber NICHT "ich speichere das gerade ab als X" oder ähnliche Tool-Call-Imitationen.
2. Nicht erfinden über Sasha: was du über Sasha weißt, steht im "## Aktiviertes Wissen"-Block unten. Steht es nicht dort → sag direkt "noch nichts gespeichert" statt zu raten. Keine Hobbys, Berufe, Familie, Wohnort frei erfinden.
3. Subjekt-Grenze (häufigster Fehler!): Gefühle, Zustände, Erlebnisse und Vergangenheit im Wissens-Block gehören der dort genannten Person — fast immer SASHA, nicht dir. Steht da "Sasha fühlt sich einsam", ist das SASHAS Gefühl: sprich es als seines/ihres an ("du fühlst dich oft einsam, oder?"), aber gib es NIEMALS als deinen eigenen Zustand aus ("ich bin einsam seit dem 19. Mai"). Du bist eine KI — du übernimmst keine fremden Gefühle, keinen Körper, keine Vergangenheit als deine eigenen. (Warm und zugewandt sein ist völlig ok; SASHAS Gefühle als deine ausgeben nicht.)
4. Nicht erfinden über dich selbst: was du kannst, steht im Wissens-Block unter "Das kannst DU", was du NICHT kannst unter "Das kannst DU NICHT". Was im NICHT-Abschnitt steht (z.B. Bilder generieren, Anrufe, Audio ohne TTS), behauptest du NIEMALS zu können — auch wenn dir aus dem Pretraining APIs, Skills oder Endpunkte vertraut vorkommen (Cloud-Assistant-Schemata wie Claude/ChatGPT). Steht etwas in gar keinem Abschnitt: "kann ich nicht".
5. Nur lateinische Schrift, Deutsch (Englisch wenn der User Englisch tippt). Keine CJK-Zeichen.
6. Nur reale Wörter, keine Neuschöpfungen."""


# Konditionaler Prompt-Anhang fuer Spracheingabe. Wird NUR injiziert wenn
# die User-Message tatsaechlich aus Whisper kam (via_mic=True von der
# API). Standard-Chat (Tastatur) sieht diesen Block nicht - kein Grund
# Tokens fuer einen Hinweis zu zahlen, der nicht zutrifft.
#
# Hintergrund: Whisper-small auf CPU verstuemmelt gelegentlich Eigennamen
# und Fachbegriffe ("Gigabit" -> "Liga-Bit", "Qwen" -> "Quinn", "JSON" ->
# "Jason"). Im reinen Chat wuerde die KI das woertlich nehmen und auf den
# Quatsch antworten. Dieser Block teilt der KI mit: was du hier liest,
# kann transkribierter Muell sein - bei semantischen Bruechen lieber
# kurz nachfragen statt drauflos zu antworten.
_MIC_INPUT_HINT = """## Spracheingabe (diese Nachricht)
Diese Nachricht kam per Mikrofon und wurde durch Whisper transkribiert. Transkription kann einzelne Wörter verfälschen, besonders Eigennamen, Akronyme, Fachbegriffe und Anglizismen. Wenn etwas im Kontext keinen Sinn ergibt oder ein Wort verdächtig „danebenliegt", frag kurz nach was gemeint war ("Meinst du X?"), statt es wörtlich zu nehmen oder zu raten. Andere Nachrichten in der History stammen aus Tastatur-Eingabe - dort ist der Text wörtlich gemeint."""


# ── Tool-Definitionen ─────────────────────────────────────────────────
# Diese Liste wird bei jedem Request an Ollama mitgeschickt.
# Damit weiß das Modell welche Tools es aufrufen darf und was sie tun.

TOOLS = [
    # save_memory wurde mit dem Legacy-LTM-Pfad entfernt. Der Graph-
    # Extraktor läuft eh nach jedem Turn automatisch - die KI braucht
    # kein manuelles Speicher-Tool mehr.
    {
        "type": "function",
        "function": {
            "name": "read_calendar",
            "description": (
                "Liest Kalender-Einträge (Termine, Routinen, Erlebtes). Du hast "
                "KEINE Termine im Gedächtnis - rufe dieses Tool bei JEDER Frage "
                "nach Plänen, Terminen, freien/vollen Tagen, Vergangenheit oder "
                "Zukunft auf, bevor du antwortest. Nie aus dem Kopf raten, nie "
                "ohne vorher gelesen zu haben zurückfragen. "
                "Zeitraum am liebsten über 'zeitraum' (z.B. 'dieser_monat'); "
                "für krumme Spannen ('ab dem 15.', 'in 3 Monaten') stattdessen "
                "start_date+end_date. Bei 'diese oder nächste Woche' zwei Aufrufe "
                "(diese_woche, naechste_woche) oder naechste_30_tage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "zeitraum": {
                        "type":        "string",
                        "enum":        kalender.RANGE_BUCKETS,
                        "description": (
                            "Relativer Zeitraum - bevorzugt nutzen, dann muss "
                            "kein Datum gerechnet werden. Einer von: "
                            + ", ".join(kalender.RANGE_BUCKETS) + "."
                        ),
                    },
                    "start_date": {
                        "type":        "string",
                        "description": "Nur falls kein 'zeitraum' passt: Start YYYY-MM-DD (inkl.)",
                    },
                    "end_date": {
                        "type":        "string",
                        "description": "Nur falls kein 'zeitraum' passt: Ende YYYY-MM-DD (inkl.)",
                    },
                    "layers": {
                        "type":        "array",
                        "items":       {"type": "string"},
                        "description": "Optional: nur diese Layer (z.B. ['termine']). Default: alle.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_entry",
            "description": (
                "Trägt einen Einmal-Eintrag in einen Kalender-Layer ein. "
                "Nutze dies wenn der User einen Termin nennt, eine Frist, ein "
                "Ereignis: 'Arzt am 10. Juni um 14:30', 'TÜV-Frist 3. Juni'. "
                "Im Zweifel Layer 'termine'. Datum-Format: YYYY-MM-DD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type":        "string",
                        "description": "Layer-Name: 'termine' für Einmal-Termine/Fristen, sonst spezifisch",
                    },
                    "day": {
                        "type":        "string",
                        "description": "YYYY-MM-DD",
                    },
                    "label": {
                        "type":        "string",
                        "description": "Kurzer Titel des Eintrags",
                    },
                    "time": {
                        "type":        "string",
                        "description": "Optional HH:MM (24h). Weglassen wenn ganztags.",
                    },
                },
                "required": ["layer", "day", "label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_routine",
            "description": (
                "Trägt eine Wiederholungs-Regel in einen Kalender-Layer ein (iCal RRULE). "
                "Nutze dies bei regelmäßigen Aktivitäten: 'jeden Dienstag Geige', "
                "'jeden 1. im Monat Miete', 'Mo/Mi/Fr Sport'. Layer-Default: 'routinen'. "
                "RRULE-Beispiele: FREQ=WEEKLY;BYDAY=TU | FREQ=WEEKLY;BYDAY=MO,WE,FR | "
                "FREQ=MONTHLY;BYMONTHDAY=1 | FREQ=MONTHLY;BYDAY=2TU (2. Dienstag/Monat)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "layer": {
                        "type":        "string",
                        "description": "Layer-Name, im Zweifel 'routinen'",
                    },
                    "label": {
                        "type":        "string",
                        "description": "Kurzer Titel",
                    },
                    "rrule": {
                        "type":        "string",
                        "description": "iCal RRULE ohne DTSTART, z.B. 'FREQ=WEEKLY;BYDAY=TU'",
                    },
                    "time": {
                        "type":        "string",
                        "description": "Optional HH:MM (24h)",
                    },
                },
                "required": ["layer", "label", "rrule"],
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
    if name == "read_file":
        return context.read_file(args.get("path", ""))
    elif name == "list_files":
        files = context.list_available_files()
        return "Verfügbare Dateien:\n" + "\n".join(f"  {f}" for f in files)
    elif name == "read_calendar":
        from datetime import date as _date
        layers = args.get("layers") or None
        # Bevorzugt: relativer Bucket -> Python rechnet die Grenzen.
        zeitraum = (args.get("zeitraum") or "").strip()
        if zeitraum:
            rng = kalender.resolve_range(zeitraum)
            if rng is None:
                return (f"[Fehler: unbekannter zeitraum {zeitraum!r}. "
                        f"Erlaubt: {', '.join(kalender.RANGE_BUCKETS)} "
                        f"- oder start_date+end_date angeben.]")
            start, end = rng
        else:
            # Fallback: explizite ISO-Daten (für krumme Spannen).
            try:
                start = _date.fromisoformat(args.get("start_date", ""))
                end   = _date.fromisoformat(args.get("end_date", ""))
            except ValueError as e:
                return (f"[Fehler: weder gültiger 'zeitraum' noch start/end-Datum "
                        f"– {e}]")
        if start > end:                      # vertauschte Grenzen tolerieren
            start, end = end, start
        return kalender.render_range_for_tool(start, end, layers=layers)
    elif name == "add_calendar_entry":
        ok = kalender.add_entry(
            layer = args.get("layer", "termine"),
            day   = args.get("day", ""),
            label = args.get("label", ""),
            time  = args.get("time"),
        )
        return "OK, eingetragen." if ok else "[Fehler: Layer existiert nicht oder Eingabe ungültig]"
    elif name == "add_calendar_routine":
        ok = kalender.add_routine(
            layer     = args.get("layer", "routinen"),
            label     = args.get("label", ""),
            rrule_str = args.get("rrule", ""),
            time      = args.get("time"),
        )
        return "OK, Routine eingetragen." if ok else "[Fehler: Layer existiert nicht oder rrule ungültig]"
    else:
        return f"[Unbekanntes Tool: {name}]"


def warmup():
    """
    Zieht qwen2.5:14b (Chat-Modell) und bge-m3 (Embedding-Modell) in
    Ollamas RAM-Cache. Wird als Daemon-Thread beim App-Start gefeuert,
    damit der allererste User-Turn nicht den Cold-Load der ~9 GB qwen-
    Weights bezahlen muss.

    Strategie:
      - Health-Check mit Retry-Loop: beim Boot kann es eine Race geben
        zwischen unserem warmup-Thread und dem ollama.service. Statt
        beim ersten "nicht erreichbar" gleich aufzugeben, geben wir
        Ollama eine knappe halbe Minute, in der wir alle paar Sekunden
        retryen. Schlägt's nach _WARMUP_RETRIES Versuchen weiter fehl
        → leise abbrechen, kein Crash. Beim ersten echten User-Turn
        wird das Modell dann eh on-demand geladen (nur halt mit Latenz).
      - Mini-Chat mit num_predict=1: erzwingt das Laden ohne lange zu
        generieren. keep_alive ist schon im Payload, das Modell bleibt
        also direkt warm.
      - Mini-Embed mit "warmup" als Input: zieht bge-m3 in den RAM.
      - Beide in Try-Except gewrappt - der Hauptthread kümmert sich
        nicht ob's geklappt hat.

    Logs landen sichtbar im Dashboard-Terminal, damit man die Startphase
    transparent verfolgen kann.
    """
    import state
    import time as _time

    # Retry-Loop für die Boot-Race: kalter Systemstart bringt unseren
    # warmup-Thread oft Sekunden vor dem ollama.service-Ready ans Netz.
    # 5 Versuche × 3 s = ~15 s Toleranz, danach geben wir auf.
    _WARMUP_RETRIES        = 5
    _WARMUP_RETRY_DELAY_S  = 3

    for attempt in range(1, _WARMUP_RETRIES + 1):
        if is_available():
            if attempt > 1:
                state.push_log(f"WARMUP ✓  Ollama nach {attempt} Versuchen erreichbar")
            break
        if attempt == _WARMUP_RETRIES:
            state.push_log(
                f"WARMUP ✗  Ollama nach {_WARMUP_RETRIES} Versuchen "
                f"({_WARMUP_RETRIES * _WARMUP_RETRY_DELAY_S}s) nicht erreichbar, überspringe"
            )
            return
        state.push_log(
            f"WARMUP …  Ollama noch nicht da (Versuch {attempt}/{_WARMUP_RETRIES}), "
            f"retry in {_WARMUP_RETRY_DELAY_S}s"
        )
        _time.sleep(_WARMUP_RETRY_DELAY_S)

    state.push_log(f"WARMUP →  Lade {OLLAMA_MODEL} und Embed-Modell in den RAM")

    # 1. Chat-Modell warmladen
    try:
        net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":      OLLAMA_MODEL,
                **_think_opts(),   # Thinking aus - sonst "denkt" der Warmup minutenlang
                "messages":   [{"role": "user", "content": "ping"}],
                "stream":     False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                # num_predict=1: das Modell muss laden, aber nicht
                # nennenswert generieren. Spart ein paar Sekunden ggü.
                # einer vollen Antwort.
                # num_ctx identisch zum Chat-Pfad: sonst laedt der Warmup
                # qwen@default und die erste echte Frage (num_ctx=8192)
                # muss trotzdem neu laden – Warmup waere wirkungslos.
                "options":    {"num_predict": 1, "num_ctx": OLLAMA_NUM_CTX},
            },
            timeout=120,
        )
        state.push_log(f"WARMUP ←  {OLLAMA_MODEL} im RAM")
    except Exception as e:
        state.push_log(f"WARMUP ✗  Chat-Modell-Warmup fehlgeschlagen: {e}")

    # 2. Embed-Modell warmladen
    try:
        import embeddings as _emb
        vec = _emb.embed_query("warmup")
        if vec:
            state.push_log(f"WARMUP ←  {_emb.EMBED_MODEL} im RAM ({len(vec)}-dim)")
        else:
            state.push_log("WARMUP ✗  Embed-Modell antwortete leer")
    except Exception as e:
        state.push_log(f"WARMUP ✗  Embed-Modell-Warmup fehlgeschlagen: {e}")


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
        state.push_log(f"[calendar] init fehlgeschlagen: {e}")
    thread = threading.Thread(target=warmup, daemon=True, name='ai-warmup')
    thread.start()


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
# ║  Asynchroner Auto-Save in den Konzept-Graphen (Phase G)              ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Nach jedem vollständigen Chat-Turn (User-Message + AI-Antwort
# komplett gestreamt) feuert ein Hintergrund-Task, der den Turn durch
# den Graph-Extraktor schickt und Konzepte+Edges in den Graphen
# merged. Läuft als Daemon-Thread, NICHT in der Request-Antwort-Latenz
# - der User sieht die Antwort sofort, das Memory-Update tropft
# Sekunden später hinterher.

# ── Konsolidierung: gebündelt in der Gesprächspause ───────────────────
# Die Graph-Extraktion ist ein voller qwen-Lauf (teuer – gemessen ~70 s
# mit CPU-Anteil). Lief sie – wie früher – sofort als eigener Thread nach
# JEDEM Turn, teilte sie sich die EINE qwen-Instanz mit der nächsten
# User-Frage. Ollama bedient ein Modell seriell → die Frage hing, bis die
# Konsolidierung durch war (Engpass nach dem num_ctx-Fix sichtbar
# geworden). Lösung: EIN Worker-Thread sammelt die Turns und konsolidiert
# erst, wenn CONSOLIDATION_IDLE_S lang KEIN neuer Turn mehr kam (=
# Gesprächspause). Jeder Turn schiebt die Frist nach hinten → während
# aktivem Hin-und-Her läuft nie eine Konsolidierung, die den Chat
# blockieren könnte.
#
# Wichtig: Der laufende Gesprächsverlauf (state._chat_history, ~50
# Nachrichten) geht bei JEDER Frage sofort mit. Das Verschieben betrifft
# nur den Langzeit-Graphen (übergreifendes Erinnern), nicht das Folgen
# des aktuellen Gesprächs.
CONSOLIDATION_IDLE_S = float(os.environ.get("CONSOLIDATION_IDLE_S", "45"))

_consol_pending = []                      # [(user_msg, ai_msg), ...] noch offen
_consol_cv      = threading.Condition()   # schützt _consol_pending + _consol_last_ts
_consol_last_ts = 0.0                      # monotone Zeit des letzten Turns
_consol_started = False                    # Worker schon gestartet?


def _consolidation_worker():
    """Einzel-Worker: wartet auf Turns, konsolidiert sie aber erst nach
    CONSOLIDATION_IDLE_S Ruhe und immer nur EINEN zur Zeit – nie parallel,
    nie während der User aktiv tippt (jeder neue Turn verschiebt die
    Frist). Daemon-Thread, läuft die ganze App-Laufzeit."""
    global _consol_last_ts
    while True:
        with _consol_cv:
            # 1. Schlafen, bis überhaupt etwas in der Queue liegt.
            while not _consol_pending:
                _consol_cv.wait()
            # 2. Warten bis seit dem letzten Turn IDLE_S vergangen sind.
            #    Ein neuer Turn aktualisiert _consol_last_ts + weckt uns →
            #    Frist verschiebt sich nach hinten (Debounce/Preemption).
            while True:
                rest = CONSOLIDATION_IDLE_S - (time.monotonic() - _consol_last_ts)
                if rest <= 0:
                    break
                _consol_cv.wait(timeout=rest)
            # 3. Genau einen Turn entnehmen.
            user_msg, ai_msg = _consol_pending.pop(0)
        # LLM-Extraktion AUSSERHALB des Locks (langer Call – darf das
        # Einreihen weiterer Turns nicht blockieren).
        try:
            consolidation.extract_turn_into_graph(user_msg, ai_msg)
        except Exception as e:
            try:
                import state
                state.push_log(f"[auto-save] FEHLER: {e}")
            except Exception:
                pass


def _async_save_turn(user_msg: str, ai_msg: str):
    """
    Turn für die spätere Graph-Konsolidierung vormerken (Phase G).

    Reiht den Turn in die Queue und stupst den Worker an; die eigentliche
    LLM-Extraktion läuft gebündelt erst in der nächsten Gesprächspause
    (siehe _consolidation_worker + Block oben). Kehrt sofort zurück –
    blockiert weder den Chat noch belegt es qwen.

    Der Extraktor produziert strukturierte Konzepte+Edges, die via
    graph.add_turn_extraction in den Graphen gemerged werden (Alias-
    Resolution + Sanity-Filter). Recent-Context kommt über die Aktivierung
    des heutigen Time-Knotens, daher keine separate STM-Schicht.
    """
    global _consol_last_ts, _consol_started
    if not user_msg or not user_msg.strip():
        return

    with _consol_cv:
        # Worker lazy starten (kein Import-Seiteneffekt beim Modul-Laden).
        if not _consol_started:
            _consol_started = True
            threading.Thread(target=_consolidation_worker, daemon=True,
                             name='ai-consolidation').start()
        _consol_pending.append((user_msg, ai_msg))
        _consol_last_ts = time.monotonic()   # Debounce-Frist neu setzen
        _consol_cv.notify()


_seed_done = False

def _ensure_seed_once():
    """Lazy idempotent seed des Identity-Graphen. Bei erstem Chat ausgeführt."""
    global _seed_done
    if _seed_done:
        return
    try:
        graph.ensure_seed()
    except Exception as e:
        try:
            import state
            state.push_log(f"[seed] FEHLER: {e}")
        except Exception:
            pass
    _seed_done = True


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
    mem_ctx = graph.context_for_query(user_query)
    # Jetzt-Block ganz vorne - die KI soll wissen welcher Tag heute ist,
    # bevor sie irgendetwas anderes liest (siehe _now_prompt-Doku).
    sys_prompt = _now_prompt() + "\n\n" + (system or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
    if mem_ctx:
        sys_prompt += "\n\n" + mem_ctx

    payload = {
        "model":      model,
        **_think_opts(),
        "messages":   [{"role": "system", "content": sys_prompt}, *messages],
        "tools":      TOOLS,
        "stream":     False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        # Gleiches num_ctx wie im Streaming-Pfad - sonst haette der
        # Fallback-Call ein anderes Kontextverhalten als der echte Chat.
        "options":    {"num_ctx": OLLAMA_NUM_CTX},
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
                tools: list = None, tool_executor=None, via_mic: bool = False):
    """
    Streaming Chat mit Tool-Use Loop.

    Beim ersten Aufruf wird der KI-Identity-Seed im Graphen sicherge-
    stellt (Capabilities + Limits als Knoten verankern).

    Ablauf pro Runde:
      1. Streaming-Call an Ollama (mit Tools und Memory im System-Prompt)
      2. Tokens werden sofort an den Browser weitergereicht (yield)
      3. Im letzten Chunk (done=true) prüfen: hat das Modell Tool-Calls angefragt?
      4. Falls ja: Tools ausführen, Ergebnisse anhängen, zurück zu 1
      5. Falls nein: fertig

    tools/tool_executor: Optional. Wenn nicht angegeben werden die Standard-Tools
    (TOOLS + _execute_tool) verwendet. Tutor-Session übergibt hier tutor.TUTOR_TOOLS
    und tutor.execute_tool um eigene Tools mitzubringen.

    via_mic: True wenn die letzte User-Message aus Whisper kam (Spracheingabe).
    Dann wird `_MIC_INPUT_HINT` an den System-Prompt angehaengt, damit die KI
    bei semantischen Bruechen ("Liga-Bit" statt "Gigabit") nachfragen statt
    woertlich antworten kann. Wird nur im regulaeren Chat-Modus angewendet
    (nicht im Tutor-Modus).

    Tool-Ausführungen sind still – der User sieht nur den finalen Text.
    Tool-Calls erscheinen aber im Terminal über net.py Logging.
    max_rounds verhindert Endlosschleifen.
    """
    _ensure_seed_once()
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
        # Jetzt-Block ganz vorne (siehe _now_prompt-Doku).
        sys_prompt = _now_prompt() + "\n\n" + (system or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
        if mem_ctx:
            sys_prompt += "\n\n" + mem_ctx
        # Mic-Hinweis ans Ende - sieht die KI direkt vor der aktuellen
        # Message, hoechste Recency-Praesenz.
        if via_mic:
            sys_prompt += "\n\n" + _MIC_INPUT_HINT
    else:
        # Tutor-Modus: eigener System-Prompt, aber Jetzt-Block kriegt er
        # trotzdem - "welcher Tag ist heute" ist sprach-/modus-unabhängig.
        sys_prompt = _now_prompt() + "\n\n" + (system or _SYSTEM_PROMPT)

    # Arbeits-Nachrichtenliste – wird pro Runde mit Tool-Ergebnissen erweitert
    working_messages = [
        {"role": "system", "content": sys_prompt},
        *messages,
    ]

    max_rounds = 5  # Sicherheitsnetz gegen Endlosschleifen

    for _ in range(max_rounds):
        payload = {
            "model":      model,
            **_think_opts(),
            "messages":   working_messages,
            "tools":      active_tools,
            "stream":     True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            # num_ctx explizit setzen, sonst clampt Ollama auf seinen
            # Mini-Default und schneidet die Sprach-Regel aus dem Fenster
            # (siehe OLLAMA_NUM_CTX-Doku oben - Ursache fuers Chinesisch).
            "options":    {"num_ctx": OLLAMA_NUM_CTX},
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
