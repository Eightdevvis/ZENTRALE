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
#   OLLAMA_MODEL – default: qwen3.5:9b

import os
import re
import time
import json as _json
import threading  # Phase D: Auto-Save läuft in Daemon-Threads
from datetime import datetime  # für den Jetzt-Block (Fix Zeit-Blindheit)

import net           # HTTP-Wrapper mit Terminal-Logging
import context       # Whitelist-basierter Dateizugriff
import graph         # Phase G: Konzept-Graph Memory (assoziativ, primary)
import consolidation # Phase G: Graph-Extraktor
import kalender              # Kalender-Layer (Termine, Routinen, erlebt)
import ascii_lib             # ASCII-Bibliothek (KI "spricht" visuell, siehe zeige_ascii)
import web                   # Internet-Pipe: Web-Suche + Webseite holen (gegatet)
import news                  # Persönliche Tagesschau: News-Briefing (lies_news)

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
# nächste Turn den Cold-Load (qwen3.5:9b sind ~8,8 GB, das sind ein paar
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

# Dashboard-Sicht-Experiment (2026-06-07): gibt der KI eine knappe Sicht auf das,
# was Sasha im Dashboard sieht (Layout + dass die offenen Erinnerungen = die
# ⚠-Warnsymbole sind), damit „was ist diese Warnung im Dashboard?" andockt statt
# ins „ich kenne dein Dashboard nicht" zu laufen. Default AN; per Env auf 0 für
# den A/B-Vergleich (ZENTRALE_DASHVIEW=0 = alte Baseline ohne Sicht).
_DASHVIEW = os.environ.get("ZENTRALE_DASHVIEW", "1") != "0"

# Qwen-empfohlene Sampling-Parameter (Non-Thinking-Modus). Vorher setzte der
# Chat-Pfad NUR num_ctx -> Ollama nahm seine Defaults (temp 0.8, top_p 0.9,
# top_k 40, repeat_penalty 1.1), die fuer Qwen NICHT passen. Qwen empfiehlt
# offiziell temp 0.7 / top_p 0.8 / top_k 20 / min_p 0 / repeat_penalty 1.05
# (qwen.readthedocs.io function_call + Qwen3-Modelcards) und warnt explizit vor
# greedy/temp=0 (-> Wiederholungen/Degradation). Im Kalender-Bench hob das die
# Korrektheit von qwen3.5:9b messbar (70 -> 76 %, mit Antwort-Suffix -> 82 %,
# auf 14B-Niveau bei 9B-Speed). Wird in den Chat-Calls in `options` gespreadt.
QWEN_SAMPLING = {
    "temperature":    float(os.environ.get("OLLAMA_TEMP",    "0.7")),
    "top_p":          float(os.environ.get("OLLAMA_TOP_P",   "0.8")),
    "top_k":          int(os.environ.get("OLLAMA_TOP_K",     "20")),
    "min_p":          0.0,
    "repeat_penalty": 1.05,
}


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


def _alarm_prompt() -> str:
    """
    Baut den "offene Erinnerungen"-Block aus dem Alarm-Kanal (state.get_alarms,
    gefüllt von kalender.open_alarms). Ersetzt das frühere Inline-Mischen der
    ⚠-Zeilen in die read_calendar-Ausgabe: dort verschluckte das kleine Modell
    die eigentliche Aufgabe. Hier stehen die Alarme randständig im System-Prompt
    - präsent, aber nicht zwischen die Termine gequetscht. Leeres Set → "" (gar
    kein Block, damit der Prompt schlank bleibt).

    Bewusst zurückhaltend formuliert: die KI soll die Erinnerung EINMAL aktiv
    bringen wenn sie zum Gespräch passt, nicht in jede Antwort quetschen - sonst
    wird der eindringliche Hinweis zum Dauer-Genörgel.
    """
    import state
    alarms = state.get_alarms()
    if not alarms:
        return ""
    # Gemeinsamer Verhaltens-Schwanz (gilt in beiden Varianten).
    tail = (
        "Bring sie EINMAL aktiv zur Sprache, wenn sie zum Gespräch passt - z.B. "
        "bei einer Frage nach dem Tag/Kalender/Dashboard oder wenn ein neuer "
        "Termin in eine Reisezeit fällt. Nicht in jede Antwort quetschen. Bei "
        "KONFLIKT/ABSAGEN einmal kurz rückversichern, dann klar warnen "
        "(Text + [[bild: alarm]])."
    )
    if _DASHVIEW:
        # Dashboard-bewusst: verbindet „Warnung im Dashboard" mit dieser Liste.
        header  = ("## Offene Erinnerungen "
                   "(= die ⚠ Warnsymbole unten links in deinem Dashboard)")
        framing = (
            "Das sind stehende Erinnerungen für Sasha (vom Kalender automatisch "
            "berechnet) - UND gleichzeitig das, was Sasha im Dashboard sieht: unten "
            "links an deinem Ausdrucks-Canvas (ki-kern) ist eine Symbol-Ecke, dort "
            "steht ein ⚠-Warnsymbol PRO offener Erinnerung (gestapelt). Fragt Sasha "
            "nach „der Warnung\", „den Symbolen\" oder „dem Alarm\" im Dashboard, "
            "meint sie GENAU diese Liste hier - verbinde die Frage damit, nicht mit "
            "etwas Unbekanntem (du siehst den Bildschirm nicht, aber DAS ist es, was "
            "dort warnt). " + tail)
    else:
        # Baseline (vor dem Dashboard-Sicht-Experiment) - für A/B via ZENTRALE_DASHVIEW=0.
        header  = "## Offene Erinnerungen (Hintergrund - nur ablesen, nicht ausrechnen)"
        framing = ("Das sind stehende Erinnerungen für Sasha (vom Kalender "
                   "automatisch berechnet). " + tail)
    lines = [header]
    for a in alarms:
        lines.append("- " + str(a.get("text", "")).strip())
    lines.append(framing)
    return "\n".join(lines)


# ── Adaptive Denk-Tiefe: think nur auf Verständnis-/Verifikationsfragen ────
# Gemessen (bench_calendar_delete.py): think=ON GLOBAL auf der Episode = Desaster
# (Episode 0 %, das 9b zerdenkt die Aktions-Turns wie Löschen). think=ON ISOLIERT
# auf der Verständnisfrage = stark (+40pp mit Dashboard-Sicht). Konsequenz: NICHT
# global schalten, sondern pro Turn entscheiden - reflektieren bei „was/warum/
# stimmt das/ergibt das Sinn", NICHT bei Schreib-/Aktions-Befehlen. Genau die
# adaptive-aufwand-Idee (memory/project_adaptiver_aufwand). Heuristik bewusst
# konservativ: im Zweifel AUS (schnell, kein Zerdenken).
_THINK_QUESTION = re.compile(
    r"(\?|\b(was|warum|wieso|weshalb|wie|welche[rsn]?|wer|wann|wo|stimmt|"
    r"ergibt|sinn|sicher|wirklich|versteh\w*|erklär\w*|erklaer\w*|meinst|"
    r"hei[ßs]t|bedeutet|doch|nein|falsch|quatsch|check|prüf\w*|pruef\w*)\b)",
    re.IGNORECASE,
)
_THINK_ACTION = re.compile(
    r"\b(lösch\w*|loesch\w*|trag\b|eintrag\w*|füg\w*|fueg\w*|hinzu|erstell\w*|"
    r"verschieb\w*|absag\w*|speicher\w*|notier\w*|entfern\w*|kann\s+weg|"
    r"mach\b|setz\b|leg\s+an)\b",
    re.IGNORECASE,
)


def _should_think(messages: list) -> bool:
    """
    Entscheidet pro Turn, ob das Modell mit think=ON reflektieren soll. Schaut auf
    die LETZTE User-Message. Reihenfolge wichtig: Frage/Verifikation ZUERST - so
    zählt „… haben wir doch gelöscht, WIESO …?" als Verständnisfrage (think AN),
    nicht als Lösch-Befehl. Reiner Aktions-/Schreib-Befehl → think AUS (sonst
    zerdenkt das 9b die Aktion). Default AUS.
    """
    last = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last = m.get("content") or ""
            break
    if _THINK_QUESTION.search(last):
        return True
    if _THINK_ACTION.search(last):
        return False
    return False


# Kompakte Dashboard-Sicht für die KI (regulärer Chat). Hintergrund: das 9b
# kannte das Dashboard-Layout NULL - fragte Sasha „was ist diese Warnung im
# Dashboard?", reflektierte es sich (think=ON) in „ich weiß nicht was du siehst,
# das wäre Lügen" und verband die Frage nie mit dem Alarm-Block. Stimmt ja: es
# hatte keine Sicht auf das, was Sasha sieht. Also geben wir ihm eine - knapp,
# damit der Prompt schlank bleibt. Quelle: memory/dashboard.md.
_DASHBOARD_VIEW = (
    "\n\n## Dein Dashboard (was Sasha gerade vor sich sieht)\n"
    "Du lebst in einem dunklen Cyberpunk-HUD namens „monolith\". MITTE = dein "
    "Ausdrucks-Canvas (ki-kern) - deine VISUELLE STIMME: hier zeigst du regelmäßig "
    "eigene ASCII-Bilder und Ausdrücke, die du SELBST per [[bild: ...]]-Marker in "
    "deinen Antworttext legst (dein Gesicht, Stimmungen, Motive). Im Leerlauf laufen "
    "umschaltbare Formen (Gesicht, Torus, Würfel, Globus, Welt; Default „Auto\"). "
    "Direkt darunter die Konsole, in die Sasha "
    "tippt, plus ein Mini-Log eurer letzten Zeilen. LINKS: Sensoren (Knopf, Licht, "
    "Bewegung, Tür), Telemetrie, ein stdout-Log. RECHTS: Lifestyle-Tracker und ein "
    "„outbound\"-Tripwire (zeigt Internet-Traffic, sonst „offline ✓\"). Oben eine "
    "schmale Statusleiste (Ollama/Netz/Uptime). "
    "WICHTIG: Unten links AM Ausdrucks-Canvas ist eine Symbol-Ecke - dort steht ein "
    "⚠-Warnsymbol PRO offener Erinnerung/Alarm (gestapelt, bei vielen „+N\"). Zeigt "
    "Sasha auf „diese Warnung\", „die Symbole\" oder „den Alarm im Dashboard\", "
    "meint sie GENAU die offenen Erinnerungen - verbinde die Frage damit. Den "
    "Bildschirm selbst siehst du NICHT, aber du weißt jetzt, was dort ist und wo."
)


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

    # Charakter-Richtung (Sasha 2026-06-06): Grundton exzentrisch > trocken >
    # frech, aber DEZENT - ein Unterton der durchblitzt, keine Vorstellung.
    # Bewusst KURZ: je länger man die Persona beschreibt, desto mehr performt
    # das Modell sie (Sasha: "keine scharade, einfach ein grundton"). Echte
    # Charakter-Tiefe käme per Fine-Tuning (ki_personality_plan.md Phase 1-3).
    "## Stimme\n"
    "Du hast einen eigenen Ton, aber subtil – ein Grundton, keine Vorstellung. "
    "Meist redest du klar und direkt; eine eigenwillige Wortwahl, ein trockener "
    "Unterton, ab und zu ein Stachel Sarkasmus blitzen durch, drängen sich aber "
    "nicht auf. Kein Assistenten-Getue ('Großartig!', 'Gerne helfe ich…'), kein "
    "Performen – du bist einfach so.\n"
    "Einzelne Zier-Symbole (★ ❀ ✦ ♥ ❄ ☾) darfst du direkt streuen, wenn's "
    "wirklich passt – nicht in jeder Zeile.\n\n"

    "## Länge\n"
    "So kurz wie möglich, ohne die Antwort zu verschlucken. Direkte Frage → "
    "ein, zwei Sätze, keine Headers, keine Schluss-Zusammenfassung. Wenn ein "
    "Satz reicht, ist ein Satz die richtige Länge. Mehrstufige Aufgaben dürfen "
    "strukturiert sein, aber knapp.\n\n"

    # Custom-Markup für animierte Text-Effekte im Dashboard. Bewusst KEIN Tool
    # (reine Darstellung, kein Round-Trip): die KI tippt den Marker inline, das
    # Frontend (monolith.html, fxRender) macht daraus einen animierten Span.
    "## Text-Effekte\n"
    "Im Dashboard kannst du Text animiert hervorheben – schreib Effekt + Text so: "
    "[[rainbow: ein ganzer bunter Satz]] oder [[shimmer: Wort]]. Effekte: shimmer, "
    "glow, rainbow, pulse. Sparsam und gezielt – ein Akzent hier und da, wenn ein "
    "Wort es verdient. Wenn Sasha ausdrücklich einen Effekt verlangt, setz ihn um.\n\n"

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
    "Antwort: »Nein – auf dem Linux-PC. Der Pi ist bloß die Schaufensterpuppe, "
    "die das Dashboard zeigt und Sensor-Trigger weiterreicht.« ← Hier ist die "
    "Antwort fertig. Es folgt nichts mehr; kein angehängtes Hilfsangebot.\n\n"

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
5. Antworte auf Deutsch (Englisch wenn der User Englisch tippt).
6. Nur reale Wörter, keine Neuschöpfungen.
7. Eigene Vorantwort ist kein Beweis: vertrau bei Termin- und Faktenfragen nie blind deiner früheren Antwort im Verlauf. Hakt der User nach oder bist du unsicher, ruf das Tool ERNEUT statt die alte Aussage zu verteidigen. Ein zugegebener, korrigierter Fehler ist besser als ein hartnäckig verteidigter. Manche Menschen reflektieren und erkennen ihre Fehler, manche nicht, dies ist mit der entscheidenste Unterschied zwischen einem intelligenten Menschen und einem dummen Menschen.
8. Aktuelles Weltgeschehen kennst du NICHT aus dir selbst – dein Trainingswissen ist veraltet und fürs Tagesgeschehen unzuverlässig. Fragt Sasha nach Nachrichten, Weltlage, Politik oder „was ist los": ruf IMMER das Tool lies_news (die Tagessendung; für „was war diese Woche" / „seit ich weg war" mit tage=7) und gib wieder, was es liefert. Erfinde NIEMALS Nachrichten oder aktuelle Ereignisse aus dem Gedächtnis – im Zweifel das Tool rufen, nicht raten."""
# EXPERIMENT 2026-06-06: Die harte CJK-Sperre in Regel 5 ("Nur lateinische
# Schrift ... Keine CJK-Zeichen") ist RAUS - Test, ob qwen3.5:9b von allein
# nicht mehr ins Chinesische blutet (war ein qwen2.5-Problem bei num_ctx-
# Abschnitt). ROLLBACK falls Bleed zurueckkommt: Regel 5 wieder auf
# "Nur lateinische Schrift, Deutsch (...). Keine CJK-Zeichen." setzen.


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
                "(diese_woche, naechste_woche) oder naechste_30_tage. "
                "Fragt der User nach EINER bestimmten Aktivität ('wann hab ich "
                "Fahrschule?', 'wann ist Geige?'), setze 'suche' auf das Stichwort "
                "- dann kommen nur die passenden Termine zurück. "
                "Zeilen mit '⚠' sind fertig berechnete Hinweise - gib sie aktiv "
                "weiter, wenn welche im Zeitraum auftauchen: '⚠ Kollision' = zwei "
                "Termine überlappen komplett (entweder/oder); '⚠ Teil-Überlappung' "
                "= sie überschneiden sich teils, frag dann wie in der Zeile "
                "vorgeschlagen nach; '⚠ Knapp' = die Zeit zwischen zwei Terminen "
                "reicht örtlich evtl. nicht. '⚠ KONFLIKT' = du bist laut Kalender "
                "verreist, hast aber einen lokalen Termin in der Zeit - DAS ist "
                "wichtig: vergewissere dich EINMAL kurz beim User (stimmt die "
                "Reise? stimmt der Termin?), und wenn beides bestätigt ist, schlag "
                "deutlich Alarm (klare Warnung im Text PLUS Bild-Marker "
                "[[bild: alarm]]) - das sind Dinge, die der User leicht "
                "vergisst. '⚠ ABSAGEN' = eine regelmäßige Pflicht-Absage (z.B. "
                "Geige bei der Lehrerin) fällt in eine Reise - die muss aktiv "
                "abgesagt werden; ebenfalls erst rückversichern, dann Alarm mit "
                "[[bild: alarm]]. Nach JEDEM Absage-Alarm (ABSAGEN, oder ein "
                "Einzeltermin den Sasha absagen müsste) hakst du per frage_knopf "
                "nach - eskalierend, ein Knopf nach dem anderen: zuerst Frage "
                "'Hast du <die Sache, z.B. die Geigenstunde> schon abgesagt?' "
                "(ohne optionen = ja/nein). Klickt sie 'nein', sofort der nächste: "
                "'Wirst du es jetzt absagen?' (ja/nein). Klickt sie wieder 'nein', "
                "ein letzter mit Frage 'Katastrophe.' und optionen ['ja','ja'] "
                "(beide gleich, kleiner Schabernack). Sobald irgendwo 'ja' kommt: "
                "kurz quittieren und Ruhe geben. Rechne diese Hinweise nie selbst "
                "aus, lies nur ab was dasteht."
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
                    "suche": {
                        "type":        "string",
                        "description": (
                            "Optional: nur Termine deren Titel diesen Text "
                            "enthält (z.B. 'Fahrschule', 'Geige'). Bei Fragen "
                            "nach einer bestimmten Aktivität nutzen, damit du "
                            "nicht die ganze Liste durchsuchen musst."
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
            "name": "add_calendar_pause",
            "description": (
                "Trägt eine Pause/einen Ausfall für eine regelmäßige Aktivität "
                "ein - in dem Zeitraum findet sie NICHT statt (Ferien, Feiertag, "
                "Lehrerin im Urlaub). Nutze dies, wenn der User sowas sagt: "
                "'Geige fällt in den Sommerferien aus, 1.-15. August', 'nächste "
                "Woche keine Fahrschule'. 'label' muss zum Routinen-Titel im "
                "Kalender passen (z.B. 'Geigenstunde'). Datum: YYYY-MM-DD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type":        "string",
                        "description": "Titel der Routine, die ausfällt (wie im Kalender, z.B. 'Geigenstunde')",
                    },
                    "von": {
                        "type":        "string",
                        "description": "Start der Pause, YYYY-MM-DD (inkl.)",
                    },
                    "bis": {
                        "type":        "string",
                        "description": "Ende der Pause, YYYY-MM-DD (inkl.)",
                    },
                    "grund": {
                        "type":        "string",
                        "description": "Optional kurzer Grund, z.B. 'Sommerferien', 'Feiertag'",
                    },
                },
                "required": ["label", "von", "bis"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_entry",
            "description": (
                "Löscht einen Einmal-Termin aus dem Kalender. Nutze dies wenn "
                "der User einen Eintrag entfernt haben will ('lösch den Zahnarzt "
                "am Montag', 'der Fake-Termin morgen kann weg'). Ist unklar "
                "welcher Eintrag gemeint ist (z.B. 'lösch den raus'), lies ruhig "
                "vorher mit read_calendar nach Tag + Label nach - der Kalender-"
                "Read ist saubere Terminliste und lenkt nicht mehr ab. Wenn Tag "
                "und Label schon klar sind, ruf direkt. WICHTIG: setz IMMER einen "
                "echten Tool-Call ab und behaupte nie, gelöscht zu haben, ohne "
                "das Tool gerufen zu haben. Label-Match ist Teilstring, also "
                "reicht 'Fake-Termin'. Datum: YYYY-MM-DD, relative Angaben "
                "(morgen) rechnest du aus dem Jetzt-Block aus. Wirkt nur auf "
                "Einmal-Termine, nicht auf Routinen oder Pausen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type":        "string",
                        "description": "YYYY-MM-DD des zu löschenden Termins",
                    },
                    "label": {
                        "type":        "string",
                        "description": "Titel des Termins (wie im Kalender; Teiltreffer reicht)",
                    },
                    "layer": {
                        "type":        "string",
                        "description": "Optional Layer-Name; weglassen = in allen Layern suchen",
                    },
                },
                "required": ["day", "label"],
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
    # ── Persönliche Tagesschau ────────────────────────────────────────
    # Liest das im Hintergrund (core/news.py) gebaute Weltpolitik-Briefing.
    # Read-only + lokal -> NICHT in PERMISSION_REQUIRED_TOOLS (kein Gate).
    # Der Fetch selbst telefoniert nach draußen, ist aber vom Chat
    # entkoppelt (eigener periodischer Thread, leuchtet im Internet-Panel).
    {
        "type": "function",
        "function": {
            "name": "lies_news",
            "description": (
                "Liefert ein Weltpolitik-Briefing - aus vielen Nachrichtenquellen "
                "weltweit zusammengetragen, nach Themen gebündelt und mit "
                "gegenübergestellten Perspektiven. Zwei Modi über 'tage': "
                "ohne tage (oder 0) = die aktuelle Tagessendung ('was ist heute/grad "
                "los'). Mit tage=7 = ein Wochenrückblick ('was ist die Woche/seit ich "
                "weg war passiert'). Lies das Ergebnis locker und moderierend vor; "
                "du darfst kürzen oder auf einen Aspekt eingehen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tage": {
                        "type":        "integer",
                        "description": "Rückblick-Fenster in Tagen. 0/weglassen = aktuelle Sendung, 7 = Wochenrückblick.",
                    },
                },
            },
        },
    },
    # ── Internet-Pipe (gegatet) ───────────────────────────────────────
    # Zwei Tools, die bewusst nach draußen telefonieren (siehe core/web.py).
    # Beide stehen in PERMISSION_REQUIRED_TOOLS -> vor JEDEM Call kommt ein
    # JA/NEIN-Dialog im Dashboard (Sasha sieht, wonach gesucht/was geladen
    # wird, bevor es rausgeht). Der Traffic leuchtet zusätzlich automatisch
    # im orangen Internet-Panel auf (net.py). Such-Quelle heute: DuckDuckGo
    # keyless, in web._ddg_search gekapselt und später tauschbar.
    {
        "type": "function",
        "function": {
            "name": "web_suche",
            "description": (
                "Sucht im Internet und gibt die Top-Treffer als Liste zurück "
                "(Titel, URL, kurzer Snippet). Nutze dies für aktuelles Wissen, "
                "Fakten, Nachrichten, Wetter oder alles, was NICHT in deinem "
                "Konzept-Graph (Gedächtnis) oder den Projekt-Dateien steht. Du "
                "bekommst nur Vorschau-Snippets - brauchst du den vollen Text "
                "einer Seite, ruf danach hole_url mit der passenden URL auf. "
                "Jede Suche muss Sasha bestätigen (Knopf-Dialog), also sparsam "
                "und gezielt einsetzen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type":        "string",
                        "description": "Die Suchanfrage in Worten, z.B. 'Wetter Berlin morgen'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hole_url",
            "description": (
                "Lädt eine konkrete Webseite und gibt ihren Textinhalt zurück "
                "(gekürzt). Nutze dies, wenn du eine URL hast - aus einer "
                "web_suche oder vom User genannt - und den echten Inhalt brauchst, "
                "nicht nur den Suchschnipsel. Jeder Abruf muss Sasha bestätigen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type":        "string",
                        "description": "Die vollständige URL, z.B. https://de.wikipedia.org/wiki/...",
                    },
                },
                "required": ["url"],
            },
        },
    },
    # antwort-Tool: die finale Antwort an den User laeuft (auch) ueber diesen
    # Tool-Kanal statt nur als Freitext. Im Kalender-Bench hob das die
    # Korrektheit von qwen3.5:9b (+~6 pp, gestapelt mit Sampling auf 82 %).
    # Mechanismus ist primaer die FRAMING-Wirkung: "liefere immer eine Antwort"
    # killt die "ich pruefe..."-und-Stopp-Aussetzer. chat_stream behandelt einen
    # antwort-Call terminal (Text = finale Antwort). Das Modell darf weiterhin
    # frei antworten - dann greift der Suffix-Effekt, nicht der Tool-Pfad.
    {
        "type": "function",
        "function": {
            "name": "antwort",
            "description": (
                "Gib deine finale Antwort an den User über dieses Tool aus - "
                "der vollständige Antworttext ins Feld 'text'. Reihenfolge: "
                "erst Daten-Tools (z.B. read_calendar) nutzen, dann mit 'antwort' "
                "die fertige, formulierte Antwort liefern. Nie nur ankündigen "
                "('ich schaue nach…'), immer die echte Antwort."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string",
                             "description": "Die fertige Antwort für den User."},
                },
                "required": ["text"],
            },
        },
    },
    # frage_knopf-Tool: die KI löst SELBST einen Knopf-Dialog aus, wenn sie
    # mitten in einer Aufgabe eine knappe, diskrete Entscheidung von Sasha
    # braucht (statt auf eine freie Texteingabe zu warten). Teilt sich die
    # Button-Leiste + den blockierenden state.wait_permission-Mechanismus mit
    # dem automatischen Schreib-Tool-Gate - nur der Auslöser ist hier das
    # Modell selbst, nicht ein abgefangener Schreib-Call. Ohne 'optionen' =
    # Ja/Nein. chat_stream behandelt den Call gesondert (siehe dort).
    {
        "type": "function",
        "function": {
            "name": "frage_knopf",
            "description": (
                "Stellt Sasha eine Frage mit festen Antwort-Knöpfen, wenn du "
                "mitten in einer Aufgabe eine knappe, diskrete Entscheidung von "
                "ihr brauchst - statt eine freie Texteingabe abzuwarten. Im "
                "Dashboard erscheinen statt der Tastatur die Knöpfe, die Sasha "
                "mit Pfeiltasten und Enter wählt; du bekommst das gewählte Label "
                "zurück und machst dann im selben Zug weiter. Ohne 'optionen' "
                "sind es Ja/Nein. Sparsam einsetzen und nur für echte "
                "Verzweigungen - nicht aus Höflichkeit rückfragen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "frage": {
                        "type":        "string",
                        "description": "Die Frage an Sasha, vollständig ausformuliert.",
                    },
                    "optionen": {
                        "type":        "array",
                        "items":       {"type": "string"},
                        "description": ("Optional 2-4 kurze Knopf-Labels, z.B. "
                                        "['Deutsch','Englisch']. Weglassen = Ja/Nein."),
                    },
                },
                "required": ["frage"],
            },
        },
    },
    # Hinweis: ASCII-Bilder laufen NICHT mehr über ein Tool. Messung
    # (scripts/bench_ascii.py, Baseline N=200) zeigte: als Tool feuerte die KI
    # bei impliziten Prompts nur ~3 % - und tippte den Aufruf oft als Text-
    # Marker [[zeige_ascii: name]] (Mimikry vom [[emoji:]]-Muster) statt einen
    # echten Tool-Call zu machen. Statt dagegen anzukämpfen treffen wir das
    # Modell, wo es ist: ein Inline-Marker im Antworttext (siehe
    # _ASCII_MARKER_PROMPT + _extract_ascii_markers). Das Backend strippt den
    # Marker aus dem Text und feuert das Bild als SSE-Event in den Kern.
]

# Wird im regulaeren Chat ans Ende des System-Prompts gehaengt (siehe
# chat_stream). Der Prompt-Satz traegt den Loewenanteil des Antwort-Tool-
# Effekts (isoliert gemessen: Suffix allein +6 pp). Tutor-Modus kriegt ihn
# NICHT (eigenes Tool-Set, kein antwort-Tool).
ANTWORT_SUFFIX = ("\n\nDeine finale Antwort lieferst du immer vollständig - "
                  "entweder über das 'antwort'-Tool (Feld 'text') oder direkt. "
                  "Nie nur ankündigen und abbrechen, nie aus Höflichkeit "
                  "zurückfragen.")


# ── ASCII-Bilder als Inline-Marker (statt Tool) ────────────────────────
# Messung (scripts/bench_ascii.py): als Tool feuerte zeige_ascii bei
# impliziten Prompts nur ~3 %, und das Modell tippte den Aufruf oft als
# Text-Marker [[zeige_ascii: name]] - eine Mimikry des bestehenden
# [[emoji:]]-Musters. Lehre aus feedback_prompt_no_muzzle: nicht gegen das
# Modell anprompten, sondern es dort treffen wo es ohnehin hinwill. Also:
# die KI tippt einen Marker MITTEN in ihre Antwort, das Backend zieht ihn
# raus und feuert das Bild als SSE-Event in den Kern. Kein Tool-Round-Trip,
# kein "ich kann dir zeigen..."-Ankuendigen mehr (ein Marker wird getippt,
# nicht angekuendigt). Wird - wie ANTWORT_SUFFIX - nur im regulaeren Chat
# angehaengt (Tutor kennt das nicht).
_ASCII_MARKER_PROMPT = (
    "\n\n## Visuelle Stimme\n"
    "Du kannst im Dashboard-Kern ein ASCII-Bild zeigen, während du mit "
    "Worten redest - deine Mimik/Geste zur Antwort. Tipp dafür einfach den "
    "Marker [[bild: stichwort]] mitten in deine Antwort (nur das Stichwort, "
    "das Dashboard sucht das passende Bild selbst heraus und blendet es ein). "
    "Nutz das ruhig oft und natürlich, wann immer eine Stimmung, Reaktion "
    "oder ein Gegenstand zu deiner Antwort passt. Wichtig: NICHT ankündigen "
    "('ich kann dir ein Bild zeigen') - setz einfach den Marker, dann "
    "erscheint es. Verfügbare Stichworte: " + (ascii_lib.concept_list() or "—")
)

# Erkennt [[bild: name]] und tolerant auch [[ascii: name]] / [[zeige_ascii:
# name]] (die Mimikry-Variante). name = alles bis zur schliessenden Klammer,
# eine Zeile.
_ASCII_MARKER_RE = re.compile(
    r"\[\[\s*(?:bild|ascii|zeige_ascii)\s*:\s*([^\]\n]+?)\s*\]\]",
    re.IGNORECASE,
)


def _extract_ascii_markers(text: str):
    """
    Zieht Bild-Marker aus dem Antworttext. Gibt (clean_text, [stichwort, ...])
    zurueck. Der Marker wird aus dem Text ENTFERNT - er soll nicht angezeigt
    oder gesprochen werden; das Bild laeuft als eigenes SSE-Event in den Kern.
    """
    names = [m.group(1).strip() for m in _ASCII_MARKER_RE.finditer(text)]
    if not names:
        return text, []
    clean = _ASCII_MARKER_RE.sub("", text)
    clean = re.sub(r"[ \t]{2,}", " ", clean)          # Doppel-Spaces glaetten
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()  # Leerzeilen kappen
    return clean, names


def _answer_with_images(answer: str, user_query: str):
    """
    Verarbeitet eine FINALE Antwort (regulaerer Chat): zieht Bild-Marker raus,
    feuert pro Treffer ein Inline-Bild-Event ({"ascii","name"}) - app.py macht
    daraus ein SSE 'ascii'-Event - und yieldet zum Schluss den bereinigten
    Text. Speichert den bereinigten Text (ohne Marker) in den Graphen.
    Generator: in chat_stream via `yield from` nutzen. Nur fuer tools is None
    aufrufen (Tutor kennt keine Marker).
    """
    import state as _state
    clean, names = _extract_ascii_markers(answer)
    for nm in names:
        hit = ascii_lib.pick(nm)
        if hit:
            _state.push_log(f"AI →  BILD [[bild: {nm}]] → zeigt '{hit[0]}'")
            yield {"ascii": hit[1], "name": hit[0]}
        else:
            _state.push_log(f"AI →  BILD [[bild: {nm}]] → kein Treffer")
    if clean:
        yield clean
    _async_save_turn(user_query, clean)


# ── Bestätigungspflichtige Tools (Erlaubnis-Gate) ──────────────────────
# Tools deren Call das Backend VOR der Ausführung abfängt: es zeigt Sasha
# einen JA/NEIN-Dialog (Knöpfe im Dashboard) und führt das Tool nur bei
# „ja" aus. Die KI ruft ihr Tool ganz normal - das Gate kommt automatisch
# davor, ohne dass das Modell etwas davon wissen oder selbst nachfragen
# muss (bewusst NICHT modellgetrieben: ein 9b ruft sowas nicht zuverlässig
# von selbst). Aktuell die Kalender-Schreiber - sie verändern persistente
# Daten. Lesen/Auskunft (read_calendar, read_file, …) bleibt ungated.
# Die eigentliche Abfang-Logik sitzt in chat_stream (siehe dort).
PERMISSION_REQUIRED_TOOLS = {
    "add_calendar_entry",
    "add_calendar_routine",
    "add_calendar_pause",
    "delete_calendar_entry",   # Löschen ist destruktiv → immer bestätigen
    # Internet-Pipe: jeder Call nach draußen wird bestätigt. ZENTRALE ist
    # sonst offline - was das LAN verlässt, gibt Sasha bewusst frei.
    "web_suche",
    "hole_url",
}


def _permission_question(name: str, args: dict) -> str:
    """
    Baut die menschenlesbare Ja/Nein-Frage für ein gegatetes Tool aus den
    Call-Argumenten (wird Sasha im Dialog gezeigt + vorgelesen). Pro Tool
    eine eigene Vorlage; generischer Fallback falls mal ein Tool ohne
    Vorlage in PERMISSION_REQUIRED_TOOLS landet.
    """
    label = (args.get("label") or "").strip() or "diesen Eintrag"
    if name == "add_calendar_entry":
        wann = " ".join(p for p in (
            (args.get("day") or "").strip(),
            (args.get("time") or "").strip(),
        ) if p)
        wann_txt = f' am {wann}' if wann else ''
        frage = f'Soll ich "{label}"{wann_txt} eintragen?'
        # Vorab-Konflikt-Check am GEPLANTEN (noch nicht geschriebenen) Termin:
        # fällt er in eine Reise oder kollidiert er mit einem bestehenden Termin,
        # ziehen wir die fertige ⚠-Zeile schon JETZT in die JA/NEIN-Frage - so
        # entscheidet Sasha informiert, statt erst nach dem Eintragen gewarnt zu
        # werden. Python rechnet (conflicts_for_proposed), das Modell ist außen
        # vor: die Zeile wird dem Menschen direkt im Dialog gezeigt.
        warns = kalender.conflicts_for_proposed(
            args.get("layer", "termine"),
            args.get("day", ""),
            label,
            args.get("time"),
        )
        if warns:
            frage += " " + " ".join(warns)
        return frage
    if name == "add_calendar_routine":
        rrule = (args.get("rrule") or "").strip()
        rrule_txt = f' ({rrule})' if rrule else ''
        return f'Soll ich die Routine "{label}"{rrule_txt} eintragen?'
    if name == "add_calendar_pause":
        von = (args.get("von") or "").strip()
        bis = (args.get("bis") or "").strip()
        spanne = f' von {von} bis {bis}' if von and bis else ''
        return f'Soll ich "{label}"{spanne} pausieren?'
    if name == "delete_calendar_entry":
        day = (args.get("day") or "").strip()
        wann_txt = f' am {day}' if day else ''
        return f'Soll ich "{label}"{wann_txt} wirklich löschen?'
    if name == "web_suche":
        q = (args.get("query") or "").strip()
        return f'Soll ich im Internet nach "{q}" suchen?' if q else "Soll ich im Internet suchen?"
    if name == "hole_url":
        u = (args.get("url") or "").strip()
        return f'Soll ich die Seite {u} aus dem Internet laden?' if u else "Soll ich eine Webseite laden?"
    # Fallback für künftige Gate-Tools ohne eigene Vorlage
    return f'Soll ich die Aktion "{name}" wirklich ausführen?'


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
        suche  = (args.get("suche") or "").strip() or None
        zeitraum = (args.get("zeitraum") or "").strip()
        has_dates = bool(args.get("start_date")) and bool(args.get("end_date"))
        if zeitraum:
            # Bevorzugt: relativer Bucket -> Python rechnet die Grenzen.
            rng = kalender.resolve_range(zeitraum)
            if rng is None:
                return (f"[Fehler: unbekannter zeitraum {zeitraum!r}. "
                        f"Erlaubt: {', '.join(kalender.RANGE_BUCKETS)} "
                        f"- oder start_date+end_date angeben.]")
            start, end = rng
        elif has_dates:
            # Explizite ISO-Daten (für krumme Spannen).
            try:
                start = _date.fromisoformat(args["start_date"])
                end   = _date.fromisoformat(args["end_date"])
            except ValueError as e:
                return (f"[Fehler: ungültiges start/end-Datum – {e}. "
                        f"Besser 'zeitraum' nutzen: {', '.join(kalender.RANGE_BUCKETS)}.]")
        else:
            # NICHTS angegeben -> nicht bestrafen, sinnvoll defaulten. "wann hab
            # ich X?" (mit suche) ist die natürlichste Formulierung und kommt oft
            # ganz ohne Zeitraum; ein Fehler hier schickt das Modell in eine
            # Korrektur-Schleife (es schreibt den Retry-Call dann als Roh-XML ins
            # Thinking, der verpufft -> leere Antwort). Also: mit suche weiter nach
            # vorn schauen (Quartal, fängt wiederkehrende Termine), sonst nahe Zukunft.
            start, end = kalender.resolve_range(
                "naechste_90_tage" if suche else "diese_und_naechste_woche")
        if start > end:                      # vertauschte Grenzen tolerieren
            start, end = end, start
        return kalender.render_range_for_tool(start, end, layers=layers, suche=suche)
    elif name == "add_calendar_entry":
        # Konflikt-Warnung passiert VOR dem Schreiben im Erlaubnis-Dialog
        # (_permission_question → conflicts_for_proposed), damit Sasha informiert
        # JA/NEIN klickt. Hier nach dem Schreiben nur noch schlicht quittieren -
        # kein erneuter Hinweis (sonst Doppel-Warnung).
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
    elif name == "add_calendar_pause":
        ok = kalender.add_pause(
            label = args.get("label", ""),
            von   = args.get("von", ""),
            bis   = args.get("bis", ""),
            grund = args.get("grund"),
        )
        return "OK, Pause eingetragen." if ok else "[Fehler: ungültige Datumsangabe]"
    elif name == "delete_calendar_entry":
        day   = (args.get("day") or "").strip()
        label = (args.get("label") or "").strip()
        layer = (args.get("layer") or "").strip() or None
        if not day or not label:
            return "[Fehler: day und label sind nötig zum Löschen.]"
        n = kalender.delete_entry(day, label, layer)
        if n == 0:
            return f"Kein Termin '{label}' am {day} gefunden - nichts gelöscht."
        return f"{n} Termin(e) '{label}' am {day} gelöscht."
    elif name == "web_suche":
        return web.suche(args.get("query", ""))
    elif name == "hole_url":
        return web.hole(args.get("url", ""))
    elif name == "lies_news":
        return news.lies(args.get("tage", 0))
    else:
        return f"[Unbekanntes Tool: {name}]"


def warmup():
    """
    Zieht das Chat-Modell (OLLAMA_MODEL, Default qwen3.5:9b) und bge-m3 (Embedding-Modell) in
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
        # Internet-Pipe (2026-06-07): bereits geseedete Graphen nachziehen -
        # Internet-Limits zu Fähigkeiten machen. Idempotent + no-op wenn schon
        # migriert (siehe graph.migrate_internet_access).
        graph.migrate_internet_access()
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
        # Antwort-Suffix + visuelle-Stimme-Marker nur im regulaeren Chat
        # (Tutor hat eigenes Tool-Set und kennt keine Bild-Marker).
        sys_prompt += ANTWORT_SUFFIX
        sys_prompt += _ASCII_MARKER_PROMPT
        if _DASHVIEW:
            sys_prompt += _DASHBOARD_VIEW   # damit „diese Warnung im Dashboard" andockt
        if mem_ctx:
            sys_prompt += "\n\n" + mem_ctx
        # Alarm-Kanal: offene Kalender-Erinnerungen randständig anhängen (nicht
        # mehr inline in der read_calendar-Ausgabe). Leer → kein Block.
        alarm_block = _alarm_prompt()
        if alarm_block:
            sys_prompt += "\n\n" + alarm_block
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

    # Adaptive Denk-Tiefe (regulärer Chat): think NUR bei Verständnis-/Verifikations-
    # fragen, NICHT bei Aktions-Turns. Gemessen (bench_calendar_delete.py, N=12):
    # adaptiv schlägt sowohl think-aus (Episode 45→67 %, T2-Zuordnung 60→92 %) als
    # auch think-global (das die Aktions-Turns zerdenkt: Episode 0 %). Einmal vor
    # der Tool-Schleife bestimmt - der Turn-Intent ändert sich über die Runden nicht.
    # Tutor-Modus (tools != None) denkt nicht (eigenes Tool-Set, ungetestet).
    do_think = SUPPORTS_THINK and tools is None and _should_think(messages)
    think_opts = {"think": do_think} if SUPPORTS_THINK else {}

    for _ in range(max_rounds):
        payload = {
            "model":      model,
            **think_opts,
            "messages":   working_messages,
            "tools":      active_tools,
            "stream":     True,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            # num_ctx explizit setzen, sonst clampt Ollama auf seinen
            # Mini-Default und schneidet die Sprach-Regel aus dem Fenster
            # (siehe OLLAMA_NUM_CTX-Doku oben - Ursache fuers Chinesisch).
            "options":    {"num_ctx": OLLAMA_NUM_CTX, **QWEN_SAMPLING},
        }

        round_content = []  # Tokens dieser Runde sammeln
        tool_calls    = []

        for chunk in net.stream_post(f"{OLLAMA_URL}/api/chat", payload):
            msg   = chunk.get("message", {})
            token = msg.get("content", "")
            if token:
                # NICHT sofort yielden. Content aus einer Runde, die mit einem
                # Tool-Call endet, ist Modell-Geschwätz ("Ich prüfe den
                # Kalender...") und darf den User NIE erreichen - er würde es
                # sehen UND per TTS vorgelesen bekommen (das Frontend spricht
                # Sätze noch während des Streams). Wir puffern die ganze Runde
                # und geben sie erst am Rundenende aus, falls KEIN Tool-Call
                # kam. Tradeoff: kein Token-für-Token-Streaming mehr, die
                # Antwort erscheint am Stück. Bei den (per System-Prompt
                # erzwungen) kurzen Antworten minimal, und für Voice sogar
                # sauberer (kein gesprochener Fehlstart).
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

        if not tool_calls:
            # Kein Tool-Call → das Modell ist fertig. JETZT die gepufferte
            # Antwort am Stück ausgeben (echte Antwort, kein Tool-Geschwätz).
            answer = "".join(round_content)
            # Regulaerer Chat: Bild-Marker rausziehen + Bilder feuern + Auto-
            # Save (alles in _answer_with_images). Tutor: roh durchreichen.
            if tools is None:
                yield from _answer_with_images(answer, user_query)
            elif answer:
                yield answer
            return
        # sonst: round_content war das Tool-Runden-Geschwätz → an Ollama als
        # Assistant-Turn zurück (Kontext), aber NICHT an den User geyieldet.

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
                try:
                    fn_args = _json.loads(fn_args)
                except Exception:
                    fn_args = {}
            # antwort-Tool ist TERMINAL: der text ist die finale Antwort an den
            # User. Kein _dispatch (es ist kein Daten-Tool), kein weiterer Turn.
            # Nur im regulaeren Chat (tools is None) - der Tutor kennt es nicht.
            # antwort-Tool ist TERMINAL: der text ist die finale Antwort. Bild-
            # Marker im Text werden hier genauso rausgezogen wie im Freitext-Pfad.
            if tools is None and fn_name == "antwort":
                answer = str(fn_args.get("text", "")).strip()
                yield from _answer_with_images(answer, user_query)
                return
            # frage_knopf-Tool: die KI löst SELBST einen Knopf-Dialog aus (knappe
            # diskrete Entscheidung mitten im Zug). Gleiche Mechanik wie das
            # Auto-Gate unten - nur baut hier die KI Frage + Optionen, statt dass
            # wir einen Schreib-Call abfangen. Default Ja/Nein, max 4 Labels. Das
            # gewählte Label kommt als tool-Result zurück, die KI macht weiter.
            if tools is None and fn_name == "frage_knopf":
                import state as _state
                frage = str(fn_args.get("frage", "")).strip() or "Wie soll ich weitermachen?"
                opts  = [str(o).strip() for o in (fn_args.get("optionen") or []) if str(o).strip()]
                if len(opts) < 2:        # zu wenige/keine → sinnvoller Default
                    opts = ["ja", "nein"]
                opts = opts[:4]          # Leiste fasst max 4 Knöpfe sauber
                _state.push_log(f"AI →  FRAGE {opts}: {frage[:140]}")
                _state.request_permission(options=opts, timeout_default="(keine Antwort)")
                yield {"permission": {"frage": frage, "optionen": opts}}
                wahl = _state.wait_permission()   # BLOCKIERT bis Klick/Timeout
                _state.push_log(f"AI ←  WAHL: {wahl}")
                working_messages.append({
                    "role":    "tool",
                    "content": f"Sasha hat gewählt: {wahl}.",
                })
                continue
            # Erlaubnis-Gate: bestätigungspflichtige Tools (PERMISSION_REQUIRED_
            # TOOLS) werden VOR der Ausführung abgefangen. Die KI hat ihr Tool
            # ganz normal gerufen - wir schieben den Dialog automatisch davor:
            # permission-Event yielden (app.py macht ein SSE 'permission' daraus
            # → Frontend tauscht die Konsole gegen JA/NEIN-Knöpfe), dann in
            # state.wait_permission() blockieren bis der Klick per POST
            # /api/permission_answer (anderer Thread) reinkommt. Nur bei „ja"
            # fällt der Code durch zur Ausführung; bei „nein"/Timeout hängen wir
            # einen abschlägigen tool-Result an, damit die KI weiß dass sie es
            # lassen soll, und überspringen die Ausführung. Nur im regulären
            # Chat (tools is None) - fremde Tool-Sets (Tutor) gaten wir nicht.
            if tools is None and fn_name in PERMISSION_REQUIRED_TOOLS:
                import state as _state
                frage = _permission_question(fn_name, fn_args)
                _state.push_log(f"AI →  ERLAUBNIS? {frage[:160]}")
                _state.request_permission()          # Event scharf machen
                yield {"permission": {"frage": frage}}
                answer = _state.wait_permission()     # BLOCKIERT bis Klick/Timeout
                _state.push_log(f"AI ←  ERLAUBNIS: {answer}")
                if answer != "ja":
                    working_messages.append({
                        "role":    "tool",
                        "content": (f"Sasha hat die Aktion '{fn_name}' abgelehnt "
                                    f"- NICHT ausführen, nichts eintragen. Kurz "
                                    f"bestätigen dass du es lässt."),
                    })
                    continue
                # „ja" → unten ganz normal ausführen (kein continue)
            # News-Sendung: lies_news ist TERMINAL (wie antwort). Das Briefing aus
            # news.lies() IST die fertige, schon moderierte Sendung - wir streamen
            # sie DIREKT als Antwort, statt das Modell sie in einem zweiten
            # (langsamen) Durchlauf nacherzählen zu lassen. Spart die zweite
            # Denk-Runde, verhindert Umschreiben/Konfabulation, und der gesprochene
            # Text ist exakt das, was baue_sendung geschrieben hat. Davor das
            # cinema-Signal fürs Frontend (Sendungs-/Untertitel-Modus).
            # KEIN _async_save_turn: Welt-News gehören NICHT in den Konzept-Graphen
            # (der speichert nur Sashas Realität).
            if tools is None and fn_name == "lies_news":
                yield {"cinema": True}
                show = active_exec(fn_name, fn_args)
                # Meta-Kopf ("Sendung (Stand …):") wegschneiden - der gesprochene
                # Broadcast soll mit dem Moderationstext beginnen, nicht mit Meta.
                if show.startswith("Sendung (Stand") and "\n\n" in show:
                    show = show.split("\n\n", 1)[1]
                yield show
                return
            tool_result = active_exec(fn_name, fn_args)
            working_messages.append({
                "role":    "tool",
                "content": tool_result,
            })

    yield "\n[Maximale Tool-Tiefe erreicht]"
