# core/ki_prompt.py
#
# Die Prompt-Bausteine, die jeder Weg braucht: Jetzt-Block, naher Horizont
# (Imprint), offene Erinnerungen, die Denk-Heuristik, die letzte Frage — und
# die Schalter Dashboard-Sicht und Graph-Kontext.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 standen
# sie in core/ai.py, und beide Cloud-Wege importierten dafür den lokalen Weg —
# Knoten im Import-Kreis. Die TEXTE der Schienen (Persona, Tool-Beschreibungen)
# stehen weiter in core/profil/; hier steht, was für jedes Modell gleich ist.
# Aufbau des KI-Kerns: memory/ki/kern_aufbau.md.

import os
import re
from datetime import datetime

# Die beiden Schienen-Texte, die die Cloud-Wege als Rückfall bzw. Mikro-Hinweis
# brauchen — von hier aus, damit niemand dafür den lokalen Weg importiert.
from profil.klein import _SYSTEM_PROMPT, _MIC_INPUT_HINT   # noqa: F401


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
