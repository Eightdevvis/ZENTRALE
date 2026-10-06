# core/ai.py
#
# Lokale KI-Schiene (Ollama) – und der Werkzeugkasten, den alle Chat-Pfade teilen.
#
# ── Wer welchen Turn bedient ──────────────────────────────────────────
# Das entscheidet NICHT diese Datei, sondern ai_backends.chat_available()
# (gefragt von /api/chat in ui/app.py):
#   local → chat_stream() hier, gegen Ollama (Prompt-Schiene `klein`)
#   cloud → core/cloud.py (Anthropic) bzw. core/cloud_openai.py
#           (OpenAI-kompatibel), Prompt-Schiene `gross`
# Die Cloud-Module leihen sich von hier Prompt-Bausteine, das Erlaubnis-Gate
# und die Tool-Ausführung (_execute_tool): Werkzeuge laufen immer lokal,
# egal wer denkt.
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
# ── Gedächtnis ───────────────────────────────────────────────────────
# Der Konzept-Graph (core/graph.py) ist seit 18.08.2026 in beide Richtungen
# per Default aus: nicht mehr in den Prompt GELESEN (graph.context_for_query
# nur mit ZENTRALE_GRAPH_KONTEXT=1, siehe GRAPH_KONTEXT unten) und nicht mehr
# BESCHRIEBEN (Tripel-Extraktion nur mit ZENTRALE_GRAPH_EXTRAKTION=1, siehe
# core/consolidation.py). Pro Turn landet nur noch der Rohtext im Transkript
# (core/transkript.py); der Identity-Seed (_ensure_seed_once) läuft weiter. An seine Stelle trat das Datei-Gedächtnis
# (core/gedaechtnis.py) — bisher NUR auf dem Cloud-Pfad: Kopf-Block im
# gecachten System-Prompt (cloud._static_system) plus die Notiz-Werkzeuge
# aus core/profil/gross.py. Die lokale Schiene sieht davon heute nichts.
#
# ── Konfiguration ────────────────────────────────────────────────────
#   OLLAMA_URL   – default: http://localhost:11434
#   OLLAMA_MODEL – default: qwen3.5:9b

import os
import re
import time
import json as _json
import threading  # Phase D: Auto-Save läuft in Daemon-Threads
import datetime as _dt
from datetime import datetime  # für den Jetzt-Block (Fix Zeit-Blindheit)

import net           # HTTP-Wrapper mit Terminal-Logging
import context       # Whitelist-basierter Dateizugriff
import graph         # Phase G: Konzept-Graph Memory (assoziativ, primary)
import consolidation # Phase G: Graph-Extraktor
import kalender              # Kalender-Layer (Termine, Routinen, erlebt)
import ascii_lib             # ASCII-Bibliothek (KI "spricht" visuell, siehe zeige_ascii)
import web                   # Internet-Pipe: Web-Suche + Webseite holen (gegatet)
import news                  # Persönliche Tagesschau: News-Briefing (read_news)
import mail                  # Mail-Triage: Überblick + Review-Stapel (read_mail)
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


# Dashboard-Sicht-Experiment (2026-06-07): gibt der KI eine knappe Sicht auf das,
# was Sasha im Dashboard sieht (Layout + dass die offenen Erinnerungen = die
# ⚠-Warnsymbole sind), damit „was ist diese Warnung im Dashboard?" andockt statt
# ins „ich kenne dein Dashboard nicht" zu laufen. Default AN; per Env auf 0 für
# den A/B-Vergleich (ZENTRALE_DASHVIEW=0 = alte Baseline ohne Sicht).
_DASHVIEW = os.environ.get("ZENTRALE_DASHVIEW", "1") != "0"

# Der Konzept-Graph als Kontext-Quelle. DEFAULT AUS seit 18.08.2026.
#
# Er ging bei JEDEM Turn ungecacht mit raus (~2.500 Zeichen) und lieferte
# dafuer Rauschen: gemessen waren 42 von 104 Kanten reine Buchhaltung
# darueber, WANN geredet wurde, und unter den Fakten standen Saetze wie
# "Sasha wohnt-in Universitaet des Saarlandes". An seine Stelle tritt das
# Datei-Gedaechtnis (core/gedaechtnis.py): Steckbrief und Ziele stehen im
# GECACHTEN Kopf, alles andere holt sie per Werkzeug.
#
# Die Datei bleibt liegen, nichts geht verloren, und mit
# ZENTRALE_GRAPH_KONTEXT=1 ist er in einer Zeile zurueck.
GRAPH_KONTEXT = os.environ.get("ZENTRALE_GRAPH_KONTEXT", "0") == "1"


# ── _PROMPT_ORDER: Reihenfolge im System-Prompt ───────────────────────
# Erst alles, was über alle Turns GLEICH bleibt, dann alles, was sich pro
# Turn ändert:
#
#   System-Prompt · Capabilities · Antwort-Suffix · ASCII · Dashboard · Imprint
#   ─────────────── ab hier wechselnd ───────────────
#   Jetzt-Block · Alarme · Mic-Hinweis
#
# (Der Graph-Kontext stand bis 18.08.2026 vorne im Wechselnden. Er ist aus,
#  siehe GRAPH_KONTEXT; was sie ueber Sasha weiss, sitzt jetzt im GECACHTEN
#  Kopf — core/gedaechtnis.py.)
#
# Zwei Gründe, ein Handgriff:
#  * Prompt-Cache. Ein Cache-Treffer braucht ein byte-identisches Präfix.
#    Der Jetzt-Block enthält die UHRZEIT — stand er vorne, war das Präfix
#    bei jedem Turn und jeder Tool-Runde ein anderes und der Cache tot.
#    Bei einem Cloud-Modell ist das der größte einzelne Kostenposten.
#  * Recency. Was zuletzt im Prompt steht, sitzt am dichtesten an der
#    User-Message. Hinten ist der Jetzt-Block also nicht schwächer als
#    vorne, sondern präsenter — und er steht direkt hinter dem
#    Graph-Kontext, dessen Datums-Knoten er ja gerade korrigiert.
#
# ── Jetzt-Block ───────────────────────────────────────────────────────
# Wird bei JEDEM Turn frisch gebaut. Schließt die strukturelle Zeit-
# Blindheit: vorher lebte das heutige Datum nur als Aktivierungs-Anker
# im Graphen - die KI konnte Time-Nodes sehen, aber nicht wissen welche
# davon "jetzt" ist. Resultat war dass sie bei "welcher Tag ist heute"
# oder "wann war unsere letzte Konversation" aus den aktivierten
# Time-Knoten geraten hat - und das war oft historisches statt aktuelles.
#
# Hart und explizit reinschreiben ist billiger als ein Tool-Call und
# eindeutig: das LLM kann das nicht halluzinieren weg.
_WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag"]
_MONTHS_DE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _now_prompt() -> str:
    """
    Baut den Jetzt-Block: Datum und die Grenzen dessen, was sie ohne
    Werkzeug weiß.

    ── Warum die UHRZEIT hier nicht mehr steht (18.08.2026) ──
    Sie stand hier, und weil sie jede Runde eine andere war, rechnete das
    Modell jedes Mal nach, wie lange es noch bis zum nächsten Termin ist —
    "in 16 Minuten", "noch 3 Minuten", obwohl Sasha den Termin längst
    gesehen hatte. Eine Prompt-Regel dagegen ist eine Bitte; das hier ist
    eine Tatsache: was sie nicht weiß, kann sie nicht ausrechnen.

    Braucht sie die Uhrzeit, holt sie sie mit read_time — ZIEHEN statt
    DRÜCKEN. Und das aktive Erinnern kommt nicht mehr aus dem Prompt,
    sondern aus dem Takt: der stößt sie an, wenn ein Termin eine Stunde
    bzw. eine halbe Stunde entfernt ist (Sashas Entwurf).

    Das Datum bleibt: es wechselt einmal am Tag statt jede Minute, und
    ohne es wäre jede Aussage über "heute" ein Tool-Aufruf.
    """
    now = datetime.now()
    weekday = _WEEKDAYS_DE[now.weekday()]
    month   = _MONTHS_DE[now.month]
    head = (
        "## Jetzt\n"
        f"Heute ist {weekday}, der {now.day}. {month} {now.year}. "
        "Dieser Block ist die einzige verlässliche Zeitquelle - Daten, die "
        "in Notizen oder im Tagebuch stehen, sind Erinnerungen an frühere "
        "Tage, NICHT der aktuelle Tag.\n\n"
        "Die UHRZEIT steht hier bewusst nicht: du weißt nicht, wie spät es "
        "ist. Brauchst du sie wirklich - weil Sasha danach fragt oder weil "
        "es für eine Entscheidung zählt - ruf read_time. Rate nie, und "
        "rechne nichts aus dem Kopf aus."
    )
    # Der Kalender wird weiterhin NICHT als Ganzes mitgeschleppt — nur der
    # nahe Horizont steht als eigener Block direkt hinter diesem hier
    # (_imprint_prompt). Alles andere kommt über read_calendar.
    #
    # Der Satz war früher "du hast keine Termine im Kopf, ruf bei JEDER
    # Zeitfrage read_calendar". Mit dem Imprint stimmt das nicht mehr: die
    # Termine für heute und morgen STEHEN da, und das Tool trotzdem zu
    # verlangen erzwingt genau die Runde, die der Imprint einsparen soll.
    head += (
        "\n\nKalender/Termine: was heute und morgen ansteht, steht im Block "
        "'Was ansteht' - daraus darfst du direkt antworten. Alles andere "
        "(jeder weitere Zeitraum, ein bestimmtes Datum, die Vergangenheit) "
        "hast du NICHT im Kopf: dafür read_calendar rufen, nie raten, nie "
        "ohne Tool zurückfragen."
    )
    return head


def _imprint_prompt() -> str:
    """Der nahe Horizont (heute/morgen) als Prompt-Block.

    Dünner Wrapper um kalender.imprint_for_prompt — die Begründung steht
    dort. Hier nur die Kapselung: fällt der Kalender aus, darf der Chat
    nicht mitfallen, also Fehler schlucken und lieber ohne Block antworten.
    """
    try:
        import kalender
        return kalender.imprint_for_prompt()
    except Exception:
        return ""


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


# ── ASCII-Bilder als Inline-Marker: das Auslesen ───────────────────────
# Der PROMPT-Teil (die Anweisung, Marker zu tippen) gehoert zur Schiene und
# steht in profil/. Das Herausziehen aus dem Antworttext gehoert zum Kern und
# steht hier — es ist fuer jedes Modell dasselbe.

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


def _answer_with_images(answer: str, user_query: str, store: str | None = None):
    """
    Verarbeitet eine FINALE Antwort (regulaerer Chat): zieht Bild-Marker raus,
    feuert pro Treffer ein Inline-Bild-Event ({"ascii","name"}) - app.py macht
    daraus ein SSE 'ascii'-Event - und yieldet zum Schluss den bereinigten
    Text. Speichert den bereinigten Text (ohne Marker) in den Graphen.
    Generator: in chat_stream via `yield from` nutzen. Nur fuer tools is None
    aufrufen (Tutor kennt keine Marker).

    store: in WELCHEN Graphen der Turn gespeichert wird. None = Core-Graph
    (data/ai_graph.json, lokales Modell). Der Cloud-Pfad (core/cloud.py) reicht
    hier seinen eigenen Graphen durch - die Isolations-Invariante lautet
    "lokal sieht alles von cloud, cloud sieht nichts von lokal", und die
    steht und faellt damit, dass Cloud-Turns NICHT im Core-Graphen landen.
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
    _async_save_turn(user_query, clean, store=store)


# ── Bestätigungspflichtige Tools (Erlaubnis-Gate) ──────────────────────
# Tools deren Call das Backend VOR der Ausführung abfängt: es zeigt Sasha
# einen JA/NEIN-Dialog (Knöpfe im Dashboard) und führt das Tool nur bei
# „ja" aus. Die KI ruft ihr Tool ganz normal - das Gate kommt automatisch
# davor, ohne dass das Modell etwas davon wissen oder selbst nachfragen
# muss (bewusst NICHT modellgetrieben: ein 9b ruft sowas nicht zuverlässig
# von selbst). Aktuell die Kalender-Schreiber - sie verändern persistente
# Daten. Lesen/Auskunft (read_calendar, read_file, …) bleibt ungated.
# Die eigentliche Abfang-Logik sitzt in werkzeug_schleife.run_tool.
#
# KANONISCHE Namen (siehe profil.kanonisch): welche Schiene das Tool wie nennt,
# ist ihre Sache — hier steht der Name, den der Kern kennt. Geprüft wird immer
# gegen den normalisierten Namen, sonst rutschte ein Tool unter einem Alias am
# Gate vorbei. Das wäre der stillste denkbare Fehler.
PERMISSION_REQUIRED_TOOLS = {
    "add_calendar_entry",
    "add_calendar_routine",
    "add_calendar_pause",
    "delete_calendar_entry",   # Löschen ist destruktiv → immer bestätigen
    "edit_calendar_routine",   # ändert/löscht dauerhaft → immer bestätigen
    # Dossier komplett neu schreiben ist ebenfalls destruktiv. ANHÄNGEN
    # (write_note) ist es nicht und bleibt bewusst ungegatet: eine KI, die
    # vor jeder Notiz fragt, ist kein Sekretär, sondern eine Zumutung.
    "rewrite_note",
    # Holt etwas aus dem Netz UND legt es ab — beide Haelften wollen
    # bestaetigt sein: die Internet-Pipe wie bei fetch_url, und das
    # Schreiben, weil sonst ungefragt Dateien im Gedaechtnis landen.
    "fetch_document",
    # Neue Messkurve: ohne Gate wuerde aus jedem Tippfehler eine weitere
    # halbtote Reihe in Sashas Uebersicht.
    "create_series",
    # Internet-Pipe: jeder Call nach draußen wird bestätigt. ZENTRALE ist
    # sonst offline - was das LAN verlässt, gibt Sasha bewusst frei.
    "web_search",
    "fetch_url",
}


def braucht_erlaubnis(name: str) -> bool:
    """Muss dieser Tool-Call vor der Ausführung bestätigt werden?

    Ueber diese Funktion gehen, nicht direkt gegen die Menge pruefen: der Name
    kommt vom Modell und traegt die Schreibweise seiner Schiene.
    """
    return profil.kanonisch(name) in PERMISSION_REQUIRED_TOOLS


def _permission_question(name: str, args: dict) -> str:
    """
    Baut die menschenlesbare Ja/Nein-Frage für ein gegatetes Tool aus den
    Call-Argumenten (wird Sasha im Dialog gezeigt + vorgelesen). Pro Tool
    eine eigene Vorlage; generischer Fallback falls mal ein Tool ohne
    Vorlage in PERMISSION_REQUIRED_TOOLS landet.
    """
    name = profil.kanonisch(name)
    label = (args.get("label") or "").strip() or "diesen Eintrag"
    if name == "fetch_document":
        return (f'Soll ich {args.get("url", "das")} holen und als '
                f'"{args.get("name", "Dokument")}" ablegen?')
    if name == "create_series":
        return f'Soll ich eine neue Messkurve "{args.get("name", "?")}" anlegen?'
    if name == "rewrite_note":
        wie = (args.get("name") or "das Dossier").strip()
        return (f'Soll ich das Dossier "{wie}" komplett neu schreiben? '
                f'(Die bisherige Fassung bleibt als .bak liegen.)')
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
    if name == "edit_calendar_routine":
        if (args.get("aktion") or "").strip() == "loeschen":
            return f'Soll ich die Routine "{label}" wirklich dauerhaft löschen?'
        # Die Frage nennt, WAS sich aendert. "Soll ich die Routine aendern?"
        # waere nicht zustimmungsfaehig — Sasha drueckt ja auf einen Knopf,
        # ohne den Werkzeug-Aufruf zu sehen.
        teile = []
        for feld, wort in (("time", "Beginn"), ("ende", "Ende"),
                           ("ort", "Ort"), ("rrule", "Wiederholung"),
                           ("neuer_titel", "Titel")):
            wert = (args.get(feld) or "").strip()
            if wert:
                teile.append(f"{wort} {wert}")
        was = ", ".join(teile) if teile else "etwas"
        return f'Soll ich die Routine "{label}" ändern auf {was}?'
    if name == "delete_calendar_entry":
        day = (args.get("day") or "").strip()
        wann_txt = f' am {day}' if day else ''
        return f'Soll ich "{label}"{wann_txt} wirklich löschen?'
    if name == "web_search":
        q = (args.get("query") or "").strip()
        return f'Soll ich im Internet nach "{q}" suchen?' if q else "Soll ich im Internet suchen?"
    if name == "fetch_url":
        u = (args.get("url") or "").strip()
        return f'Soll ich die Seite {u} aus dem Internet laden?' if u else "Soll ich eine Webseite laden?"
    # Fallback für künftige Gate-Tools ohne eigene Vorlage
    return f'Soll ich die Aktion "{name}" wirklich ausführen?'


def _kalender_beweis(tag: str, label: str) -> str:
    """Nachlesen, was an dem Tag jetzt WIRKLICH steht. -> ein Satz.

    Der Nachpruef-Schritt im Code statt in einer zweiten Modell-Runde
    (Sasha, 20.08.2026: "kosten niedrig wie moeglich aber nich auf kosten
    von qualitaet"). Das Tool-Ergebnis geht ohnehin ans Modell zurueck —
    steht dort der Beweis statt "OK, eingetragen", hat sie nachgesehen,
    ohne dass ein Aufruf mehr anfaellt.

    Wichtig ist der Fall, in dem der Beweis NICHT aufgeht: dann steht das
    ausdruecklich da, statt dass sie einen Erfolg meldet.
    """
    try:
        from datetime import date as _date
        tage = kalender.entries_in_range(_date.fromisoformat(tag),
                                         _date.fromisoformat(tag))
    except Exception:
        return "OK, eingetragen."
    eintraege = tage.get(tag) or []
    treffer = [e for e in eintraege
               if (label or "").lower() in (e.get("label") or "").lower()]
    if not treffer:
        return ("[Eingetragen gemeldet, aber am %s steht es NICHT — sag "
                "das, statt einen Erfolg zu melden.]" % tag)
    wann = treffer[0].get("time") or "ganztags"
    return ("Steht jetzt am %s: %s (%s). Der Tag hat %d %s."
            % (tag, treffer[0].get("label"), wann, len(eintraege),
               "Eintrag" if len(eintraege) == 1 else "Eintraege"))


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

    Der Name wird zuerst auf das kanonische Vokabular gebracht: welche Schiene
    ihr Tool wie nennt, ist ihre Sache (siehe core/profil/). Die Uebersetzung
    nimmt beide Schreibweisen an, deshalb laufen auch die Bench-Skripte, die
    hier mit den alten deutschen Namen hereinkommen, unveraendert weiter.
    """
    name = profil.kanonisch(name)
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
        if not ok:
            return "[Fehler: Layer existiert nicht oder Eingabe ungültig]"
        return _kalender_beweis(args.get("day", ""), args.get("label", ""))
    elif name == "read_time":
        from datetime import datetime as _dt
        jetzt = _dt.now()
        zeile = (f"Es ist {jetzt.strftime('%H:%M')} "
                 f"({_WEEKDAYS_DE[jetzt.weekday()]}, "
                 f"{jetzt.day}. {_MONTHS_DE[jetzt.month]} {jetzt.year}).")
        n = kalender.naechster_termin(jetzt)
        if not n:
            return zeile + " Danach steht heute und morgen nichts mehr an."
        std, rest = divmod(n["minuten"], 60)
        abstand = (f"{std} Std {rest} min" if std else f"{rest} min")
        wann = ("morgen " if n["morgen"] else "") + f"um {n['time']}"
        return (f"{zeile} Als Nächstes: {n['label']} {wann} — "
                f"in {abstand}.")
    elif name == "add_calendar_routine":
        ok = kalender.add_routine(
            layer     = args.get("layer", "routinen"),
            label     = args.get("label", ""),
            rrule_str = args.get("rrule", ""),
            time      = args.get("time"),
        )
        if not ok:
            return "[Fehler: Layer existiert nicht oder rrule ungültig]"
        gefunden = kalender.routine_finden(args.get("label", ""))
        if len(gefunden) > 1:
            # Sie hat gerade eine ZWEITE Regel gleichen Namens angelegt. Das
            # ist der Geigenstunden-Fall vom 18.08.2026 — er soll ihr im
            # Ergebnis auffallen, nicht Sasha drei Tage spaeter.
            zeiten = ", ".join((r.get("time") or "ganztags")
                               for _l, _i, r in gefunden)
            return (f"Eingetragen — ABER es gibt jetzt {len(gefunden)} Regeln "
                    f"namens '{args.get('label','')}' ({zeiten}). Wollte er "
                    f"eine AENDERN? Dann die alte mit edit_calendar_routine "
                    f"loeschen und das sagen.")
        return f"OK, Routine eingetragen: {args.get('label','')}."
    elif name == "add_calendar_pause":
        ok = kalender.add_pause(
            label = args.get("label", ""),
            von   = args.get("von", ""),
            bis   = args.get("bis", ""),
            grund = args.get("grund"),
        )
        return "OK, Pause eingetragen." if ok else "[Fehler: ungültige Datumsangabe]"
    elif name == "edit_calendar_routine":
        label  = (args.get("label") or "").strip()
        aktion = (args.get("aktion") or "").strip()
        if not label:
            return "[Fehler: label ist nötig.]"
        if aktion == "loeschen":
            n = kalender.routine_loeschen(label)
            if n == 0:
                return f"Keine Routine '{label}' gefunden - nichts gelöscht."
            return f"{n} Routine(n) '{label}' gelöscht."
        if aktion != "aendern":
            return "[Fehler: aktion muss 'aendern' oder 'loeschen' sein.]"
        felder = {k: args.get(k) for k in ("time", "ende", "ort", "rrule")
                  if args.get(k)}
        neu_titel = (args.get("neuer_titel") or "").strip() or None
        if not felder and not neu_titel:
            return "[Fehler: nichts zu ändern - gib an, was neu ist.]"
        n = kalender.routine_aendern(label, neues_label=neu_titel, **felder)
        if n == 0:
            return (f"Keine Routine '{label}' geändert - entweder nicht "
                    f"gefunden oder die Wiederholungs-Regel war ungültig.")
        return f"OK, {n} Routine(n) '{label}' geändert."
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
    elif name == "web_search":
        return web.suche(args.get("query", ""))
    elif name == "fetch_url":
        return web.hole(args.get("url", ""))
    elif name == "read_news":
        return news.lies(args.get("tage", 0))
    elif name == "read_mail":
        return mail.lies(args.get("modus", ""))
    # ── Gedächtnis: Notizen statt Tripel (siehe core/gedaechtnis.py) ──
    elif name == "read_note":
        import gedaechtnis
        wie = (args.get("name") or "").strip()
        if wie.lower() in ("sasha", "steckbrief"):
            return gedaechtnis.steckbrief() or "[Steckbrief ist noch leer]"
        if wie.lower() in ("ziele", "goals"):
            return gedaechtnis.ziele() or "[Ziele sind noch leer]"
        if wie.lower() in ("hausregeln", "regeln"):
            return gedaechtnis.hausregeln() or "[Noch keine Hausregeln]"
        if wie.lower().startswith(("vorlage", "template")):
            # ueber vorlage() statt ueber die Datei: sie legt sie beim
            # ersten Zugriff an, damit ein frischer Rechner sofort eine hat.
            return gedaechtnis.vorlage(wie.split("/")[-1])
        if wie.lower() in ("tagebuch", "diary"):
            return gedaechtnis.tagebuch_lesen() or "[Heute noch nichts notiert]"
        inhalt = gedaechtnis.dossier_lesen(wie)
        if not inhalt:
            vorhanden = ", ".join(gedaechtnis.dossier_liste()) or "noch keine"
            return (f"[Kein Dossier {wie!r}. Vorhanden: {vorhanden}. "
                    f"Mit write_note legst du eins an.]")
        return inhalt
    elif name == "write_note":
        import gedaechtnis
        wie  = (args.get("name") or "").strip()
        text = args.get("text") or ""
        if wie.lower() in ("tagebuch", "diary", ""):
            return gedaechtnis.tagebuch_notieren(text)
        if wie.lower() in ("hausregeln", "regeln"):
            return gedaechtnis.regel_notieren(text)
        return gedaechtnis.dossier_notieren(wie, text)
    elif name == "rewrite_note":
        import gedaechtnis
        return gedaechtnis.dossier_ersetzen(args.get("name") or "",
                                            args.get("content") or "")
    elif name == "search_memory":
        import gedaechtnis
        return gedaechtnis.suchen(args.get("query") or "")
    elif name == "fetch_document":
        import gedaechtnis
        return gedaechtnis.dokument_holen(args.get("url") or "",
                                          args.get("name") or "")
    elif name == "create_series":
        return _create_series(args)
    elif name == "log_series":
        return _log_series(args)
    else:
        return f"[Unbekanntes Tool: {name}]"


def _create_series(args: dict) -> str:
    """Eine neue Messkurve anlegen (gegatet).

    Ohne Gate wuerde aus jedem Tippfehler eine weitere halbtote Reihe in
    Sashas Uebersicht — deshalb legt `log_series` nichts von selbst an und
    dieser Weg fragt einmal nach.
    """
    import graphs
    wie = (args.get("name") or "").strip()
    if not wie:
        return "[Fehler: kein Name]"
    if any(g.get("name", "").casefold() == wie.casefold()
           for g in graphs.list_graphs()):
        return f"[Die Reihe {wie!r} gibt es schon.]"
    try:
        graphs.create_graph(wie, gtype=(args.get("typ") or "number"),
                            unit=(args.get("einheit") or ""))
    except Exception as e:
        return f"[Anlegen fehlgeschlagen: {e}]"
    return (f"Messreihe {wie!r} angelegt. Trag Werte mit log_series ein und "
            f"verlink sie im Dossier der Sache.")


def _log_series(args: dict) -> str:
    """Einen Messwert ins Zyklus-Werkzeug schreiben (core/graphs.py).

    Der fuenfte Speicher: Schlaf, Stimmung, Trainingseinheiten, alles was
    ueber Monate eine KURVE ergeben soll. Bewusst NICHT im Gedaechtnis-
    Ordner — Zahlen ueber Zeit koennen die Zyklus-Graphen laengst, samt
    Anzeige in der TUI. Sie hier nochmal als Text abzulegen hiesse, zwei
    Wahrheiten ueber denselben Wert zu fuehren.

    Legt eine Reihe NICHT von selbst an: welche Kurven es gibt, ist Sashas
    Entscheidung, und eine KI, die bei jedem Tippfehler eine neue Reihe
    erzeugt, macht aus der Uebersicht eine Halde.
    """
    import graphs
    name = (args.get("series") or "").strip()
    wert = args.get("value")
    if not name:
        return "[Fehler: keine Reihe angegeben]"
    treffer = [g for g in graphs.list_graphs()
               if g.get("name", "").casefold() == name.casefold()
               or g.get("id") == name]
    if not treffer:
        da = ", ".join(g.get("name", "?") for g in graphs.list_graphs()) or "keine"
        return (f"[Keine Messreihe {name!r}. Vorhanden: {da}. "
                f"Neue Reihen legt Sasha selbst an.]")
    g = treffer[0]
    tag = (args.get("day") or "").strip() or _dt.date.today().isoformat()
    try:
        graphs.log_value(g["id"], tag, wert)
    except Exception as e:
        return f"[Fehler beim Eintragen: {e}]"
    return f"{g.get('name')} fuer {tag}: {wert} eingetragen."


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
            # 3. ALLE wartenden Turns entnehmen, nach Ziel-Graph gruppiert.
            #    Frueher genau einer pro Durchgang. Ein Call pro Turn heisst
            #    aber: die Extraktor-Anweisungen (rund 2.000 Zeichen) gehen
            #    fuenfmal statt einmal raus. Und der Extraktor sieht jeden
            #    Turn fuer sich, statt den Zusammenhang ueber das Gespraech.
            #    Gruppiert wird nach store, weil die Isolations-Invariante
            #    (lokal/cloud) unter keinen Umstaenden verwaessert werden darf.
            buendel = {}
            for u, a, s in _consol_pending:
                buendel.setdefault(s, []).append((u, a))
            _consol_pending.clear()
        # LLM-Extraktion AUSSERHALB des Locks (langer Call – darf das
        # Einreihen weiterer Turns nicht blockieren).
        # store reist mit den Turns mit: der Extraktor laeuft zwar bevorzugt
        # lokal (Ollama), schreibt aber in DEN Graphen, aus dem sie kamen.
        for store, turns in buendel.items():
            try:
                consolidation.extract_turn_into_graph(turns, None, store=store)
            except Exception as e:
                try:
                    import state
                    state.push_log(f"[auto-save] FEHLER: {e}")
                except Exception:
                    pass


def _async_save_turn(user_msg: str, ai_msg: str, store: str | None = None):
    """
    Turn für die spätere Konsolidierung vormerken (Phase G). Heute schreibt
    die nur das Transkript; die Graph-Extraktion ist per Default aus
    (consolidation.GRAPH_EXTRAKTION, seit 18.08.2026).

    store: Ziel-Graph (None = Core-Graph). Der Cloud-Pfad reicht seinen
    eigenen durch, damit Cloud-Turns nie im lokalen Graphen landen.

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
        _consol_pending.append((user_msg, ai_msg, store))
        _consol_last_ts = time.monotonic()   # Debounce-Frist neu setzen
        _consol_cv.notify()


_seed_done = set()   # Pfade (bzw. None fuer den Core-Graph), die schon geseedet sind

def _ensure_seed_once(store: str | None = None):
    """Lazy idempotent seed des Identity-Graphen. Bei erstem Chat ausgeführt.

    Pro Store einmal: der Cloud-Pfad hat einen EIGENEN Graphen und braucht
    denselben Identity-Seed, sonst weiss die Cloud-KI nicht, was sie kann und
    was nicht (die kann/kann-nicht-Kanten sind ihr Selbstbild)."""
    if store in _seed_done:
        return
    try:
        graph.ensure_seed(store=store)
        # Internet-Pipe (2026-06-07): bereits geseedete Graphen nachziehen -
        # Internet-Limits zu Fähigkeiten machen. Idempotent + no-op wenn schon
        # migriert (siehe graph.migrate_internet_access).
        graph.migrate_internet_access(store=store)
    except Exception as e:
        try:
            import state
            state.push_log(f"[seed] FEHLER: {e}")
        except Exception:
            pass
    _seed_done.add(store)


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False):
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
        # Graph-Kontext: per Default AUS (GRAPH_KONTEXT, seit 18.08.2026),
        # mem_ctx bleibt dann leer. Mit ZENTRALE_GRAPH_KONTEXT=1 kommt der
        # Aktivierungs-Spread aus dem Konzept-Graphen zurück in den Prompt.
        mem_ctx    = graph.context_for_query(user_query) if GRAPH_KONTEXT else ""
        # ── Statischer Kopf (byte-identisch über alle Turns, cachebar) ──
        # Kommt von der Schiene: hier läuft Ollama, also `klein` — mit
        # Antwort-Suffix und Bild-Markern, die ein 9B braucht. Der Cloud-Pfad
        # holt sich denselben Kopf von seiner eigenen Schiene.
        sys_prompt = profil.klein.system(system, dashview=_DASHVIEW)
        # Der Imprint (heute/morgen) gehört noch zum stabilen Teil: er ändert
        # sich mit dem Tag und mit echten Kalender-Änderungen, nicht mit dem
        # Turn. Im wechselnden Teil würde er bei jedem Turn ungecacht bezahlt.
        imprint = _imprint_prompt()
        if imprint:
            sys_prompt += "\n\n" + imprint
        # ── Ab hier wechselt es pro Turn (siehe _PROMPT_ORDER-Notiz oben) ──
        if mem_ctx:
            sys_prompt += "\n\n" + mem_ctx
        # Jetzt-Block direkt HINTER den Graph-Kontext: er widerspricht genau
        # dessen Datums-Knoten („das sind Erinnerungen, nicht heute"), und was
        # zuletzt steht, sitzt am dichtesten an der User-Message.
        sys_prompt += "\n\n" + _now_prompt()
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
        # Auch hier der statische Teil zuerst, der Jetzt-Block hinten dran.
        sys_prompt = (system or _SYSTEM_PROMPT) + "\n\n" + _now_prompt()

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
    want_think = ADAPTIVE_THINK and _should_think(messages)

    adapter = _OllamaAdapter(model, working_messages, active_tools, want_think)
    yield from werkzeug_schleife.laufen(
        adapter, tutor_mode=tools is not None, active_exec=active_exec,
        user_query=user_query, fehler_name="Ollama")


class _OllamaAdapter:
    """Ollama-Dialekt für die gemeinsame Werkzeug-Schleife (core/
    werkzeug_schleife.py): tool_calls irgendwo im Stream, Ergebnisse als
    role=tool ohne Call-Id."""

    def __init__(self, model, msgs, tools, want_think):
        self.modell, self.msgs, self.tools = model, msgs, tools
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
            # (siehe OLLAMA_NUM_CTX-Doku oben - Ursache fuers Chinesisch).
            "options":    {"num_ctx": OLLAMA_NUM_CTX, **QWEN_SAMPLING},
        }

        round_content = []  # Tokens dieser Runde sammeln
        tool_calls    = []

        for chunk in net.stream_post(f"{OLLAMA_URL}/api/chat", payload):
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
