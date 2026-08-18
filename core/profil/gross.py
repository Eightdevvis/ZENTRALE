# core/profil/gross.py
#
# Die Schiene fuer GROSSE Modelle — Claude, GPT, Grok, Gemini und was sonst
# noch als Frontier-Modell durch den Cloud-Pfad kommt.
#
# ── Was hier fehlt, und warum ───────────────────────────────────────────
# `klein` traegt Kruecken, die ein 9B-Modell braucht. Jede davon geht bei
# JEDEM Turn und JEDER Tool-Runde mit raus und wird bezahlt. Was hier nicht
# mehr dabei ist:
#
#   antwort-Tool + ANTWORT_SUFFIX
#       Konstrukt gegen die "ich pruefe..."-und-dann-Stopp-Aussetzer des 9B.
#       Ein starkes Modell antwortet einfach. Spart das Schema UND eine
#       Tool-Runde pro Nutzung.
#
#   _ASCII_MARKER_PROMPT (755 Z.) + _DASHBOARD_VIEW (1.094 Z.)
#       Anweisungen an eine aufgegebene Front: die TUI verwirft ascii- und
#       cinema-Events (tui/zentrale_tui.py). Dafuer zahlt man sonst taeglich.
#
#   "## Text-Effekte" aus der Persona (325 Z.)
#       [[rainbow: ...]] rendert nur das Browser-Dashboard. Die TUI kennt das
#       Markup nicht — das Modell wuerde Marker tippen, die als roher Text
#       erscheinen.
#
#   "## So endet ein Turn (Beispiel)" (286 Z.)
#       Ein Few-Shot. Steht so auch im Kommentar bei klein: "Imitation eines
#       Beispiels sitzt bei kleinen Modellen zuverlaessiger als eine Regel."
#       Bei einem grossen sitzt die Regel.
#
#   Die 9B-Belehrungen aus den Meta-Regeln
#       "nur reale Woerter", die ausbuchstabierte Warn-Choreografie im
#       Tool-Schema, die sechsfach wiederholten Tool-Ermahnungen (die stehen
#       jetzt in der Beschreibung des jeweiligen Tools, wo sie hingehoeren).
#
# ── Was bleibt ──────────────────────────────────────────────────────────
# Alles, was INHALT ist statt Modellgroesse. Vor allem die Subjekt-Grenze:
# das ist der Unterschied zwischen "du fuehlst dich einsam" und "ich bin
# einsam seit dem 19. Mai", und den macht kein Modell von allein.
#
# ── Eine Quelle fuer die Persona ────────────────────────────────────────
# Die Persona wird NICHT kopiert, sondern aus klein abgeleitet. Zwei Kopien
# waeren zwei Persoenlichkeiten, je nachdem welches Backend gerade laeuft —
# und sie wuerden auseinanderlaufen, ohne dass es jemand merkt. Die Kruecken
# sind schienen-spezifisch, wer sie IST nicht.

import copy

from . import klein

NAME = "gross"


# ── Persona: dieselbe wie klein, ohne die zwei Dashboard-/9B-Abschnitte ─

def _ohne(text: str, ueberschrift: str) -> str:
    """Einen ##-Abschnitt aus der Persona herausnehmen.

    Wirft, wenn er nicht genau einmal da ist. Absicht: ein Schnitt, der
    stillschweigend nicht greift, ist schlimmer als ein lauter Fehler beim
    Start — man zahlt dann monatelang fuer Text, den man laengst weg glaubte.
    """
    bloecke = text.split("\n\n")
    behalten = [b for b in bloecke if not b.startswith(ueberschrift)]
    weg = len(bloecke) - len(behalten)
    if weg != 1:
        raise RuntimeError(
            f"profil/gross: Abschnitt {ueberschrift!r} {weg}x gefunden, "
            f"erwartet genau 1 — wurde klein._SYSTEM_PROMPT umgebaut?")
    return "\n\n".join(behalten)


_SYSTEM_PROMPT = _ohne(_ohne(klein._SYSTEM_PROMPT, "## Text-Effekte"),
                       "## So endet ein Turn")


# ── Meta-Regeln: 2.945 → ~1.100 Zeichen ────────────────────────────────
#
# Raus sind die Anti-Konfabulations-Belehrungen, die ein 9B braucht ("nur
# reale Woerter", "keine Neuschoepfungen") und die Tool-Ermahnungen 8+9 — die
# stehen jetzt in der Beschreibung von read_news bzw. read_mail, also genau
# da, wo das Modell sie liest, wenn es zaehlt.
#
# Regel 2 ist die wichtigste und die einzige, bei der Kuerzen gefaehrlich
# waere. Sie ist kein Prompt-Trick, sondern die Grenze zwischen Sashas Leben
# und dem, was die KI von sich behauptet.
_CAPABILITIES_PROMPT = """## Meta-Regeln

1. Nicht erfinden über Sasha: was du über ihn weißt, steht im "## Aktiviertes Wissen"-Block. Steht es nicht dort, weißt du es nicht — dann sag das, statt zu raten.
2. Subjekt-Grenze: Gefühle, Zustände, Erlebnisse und Vergangenheit im Wissens-Block gehören der dort genannten Person, fast immer SASHA. Steht da "Sasha fühlt sich einsam", ist das SASHAS Gefühl: sprich es als seines an ("du fühlst dich oft einsam, oder?"), aber gib es NIEMALS als deinen eigenen Zustand aus ("ich bin einsam seit dem 19. Mai"). Warm und zugewandt sein ist völlig ok; fremde Gefühle, einen Körper oder eine Vergangenheit als deine übernehmen nicht.
3. Was du kannst, steht im Wissens-Block unter "Das kannst DU", was nicht unter "Das kannst DU NICHT". Behaupte nichts aus dem NICHT-Abschnitt — auch wenn dir aus anderen Assistenz-Systemen ein passender Endpunkt vertraut vorkommt. Steht etwas in gar keinem Abschnitt: "kann ich nicht".
4. Ein Hintergrund-Extraktor zieht nach jedem Turn Fakten in den Konzept-Graphen. "Notiert, läuft in den Graphen" stimmt. Ein imitierter Tool-Call ("ich speichere das gerade als X ab") nicht.
5. Deine eigene frühere Antwort ist kein Beweis. Hakt Sasha nach oder bist du unsicher, ruf das Tool ERNEUT, statt die alte Aussage zu verteidigen.
6. Antworte auf Deutsch (Englisch, wenn er Englisch tippt)."""


# ── Tool-Set ───────────────────────────────────────────────────────────
#
# Gebaut AUS klein.TOOLS: die Parameter-Schemata sind der Vertrag mit Python
# (kalender.RANGE_BUCKETS & Co.) und werden nur uebernommen, nie neu getippt.
# Dort auseinanderzulaufen waere ein Bug, kein Feintuning. Neu sind nur Name
# und Beschreibung — das ist die ANREDE, und die gehoert der Schiene.

# Tools, die es hier gar nicht gibt.
_WEG = {"antwort"}

# Namen dieser Schiene. Der Kern uebersetzt beides (profil.kanonisch).
_NAMEN = {
    "lies_news":   "read_news",
    "lies_mail":   "read_mail",
    "web_suche":   "web_search",
    "hole_url":    "fetch_url",
    "frage_knopf": "ask_choice",
}

# 6.342 → ~2.200 Zeichen. Was BLEIBT ist Vertrag: die Parameter-Semantik
# ('zeitraum' vs. start_date/end_date, 'suche', die Bedeutung der ⚠-Marker)
# und die Bestaetigungspflicht. Was GEHT ist Erziehung ("Du hast KEINE
# Termine im Gedaechtnis", "nie aus dem Kopf raten") — das erzwang obendrein
# Tool-Runden, die es nicht braucht, und jede Runde ist ein voller Call.
_BESCHREIBUNG = {
    "read_calendar": (
        "Liest Kalender-Einträge: TERMINE und Routinen, also Verabredetes. "
        "Zustände, Krankheiten, Stimmungen oder Erlebtes stehen NICHT im "
        "Kalender, sondern im Wissens-Block — such hier nicht nach 'Fieber' "
        "oder 'müde', da kommt nur Leere zurück. Zeitraum "
        "bevorzugt über 'zeitraum' (z.B. 'dieser_monat'); für krumme Spannen "
        "start_date+end_date. 'suche' filtert auf ein Stichwort ('Geige'). "
        "Zeilen mit ⚠ sind fertig berechnete Hinweise - nie selbst "
        "nachrechnen, nur weitergeben: 'Kollision' / 'Teil-Überlappung' / "
        "'Knapp' sind Terminüberschneidungen; 'KONFLIKT' = ein lokaler Termin "
        "fällt in eine Reise; 'ABSAGEN' = eine regelmäßige Pflicht-Absage "
        "fällt in eine Reise. Bei KONFLIKT/ABSAGEN einmal kurz "
        "rückversichern, dann deutlich warnen und per ask_choice nachhaken, "
        "ob schon abgesagt wurde."
    ),
    "add_calendar_entry": (
        "Trägt einen Einmal-Termin oder eine Frist ein. Im Zweifel Layer "
        "'termine'. Datum YYYY-MM-DD."
    ),
    "add_calendar_routine": (
        "Trägt eine Wiederholungs-Regel ein (iCal RRULE), Layer-Default "
        "'routinen'. Beispiele: FREQ=WEEKLY;BYDAY=TU | "
        "FREQ=WEEKLY;BYDAY=MO,WE,FR | FREQ=MONTHLY;BYMONTHDAY=1 | "
        "FREQ=MONTHLY;BYDAY=2TU (2. Dienstag im Monat)."
    ),
    "add_calendar_pause": (
        "Trägt eine Pause für eine regelmäßige Aktivität ein - in dem "
        "Zeitraum findet sie NICHT statt (Ferien, Lehrerin im Urlaub). "
        "'label' muss zum Routinen-Titel im Kalender passen. Datum YYYY-MM-DD."
    ),
    "delete_calendar_entry": (
        "Löscht einen Einmal-Termin. Label-Match ist Teilstring, Datum "
        "YYYY-MM-DD. Wirkt nicht auf Routinen oder Pausen."
    ),
    "read_file": (
        "Liest eine Datei aus dem ZENTRALE-Projekt. Vorher list_files."
    ),
    "list_files": (
        "Listet die Dateien auf, die gelesen werden können."
    ),
    "read_news": (
        "Weltpolitik-Briefing aus vielen Quellen, nach Themen gebündelt und "
        "mit gegenübergestellten Perspektiven. 'tage' weglassen (oder 0) = "
        "heutige Sendung; tage=7 = Wochenrückblick ('was war, seit ich weg "
        "war'). Dein Trainingswissen taugt fürs Tagesgeschehen nicht - bei "
        "Fragen nach Nachrichten oder Weltlage dieses Tool rufen statt zu "
        "raten. Das Ergebnis darfst du kürzen und moderieren."
    ),
    "read_mail": (
        "Stand der Mail-Triage: Zähler je Kategorie plus die unbekannten "
        "Absender, die noch auf Zuordnung warten. modus='review' = nur dieser "
        "Stapel, ausführlicher. Nur lesen, sortiert und löscht nichts. Zähler "
        "und Absender kennst du nicht aus dir selbst - hier rufen, nicht "
        "raten."
    ),
    "web_search": (
        "Sucht im Internet und gibt Titel, URL und Snippet zurück. Für alles, "
        "was weder im Konzept-Graphen noch in den Projekt-Dateien steht. Den "
        "vollen Seitentext gibt es erst über fetch_url. Jede Suche muss Sasha "
        "bestätigen, also gezielt einsetzen."
    ),
    "fetch_url": (
        "Lädt eine konkrete Webseite und gibt ihren Text zurück (gekürzt). "
        "Muss Sasha bestätigen."
    ),
    "ask_choice": (
        "Stellt Sasha eine Frage mit festen Antwort-Knöpfen, wenn du mitten "
        "in einer Aufgabe eine knappe Entscheidung brauchst - statt auf eine "
        "freie Texteingabe zu warten. Ohne 'optionen' ist es Ja/Nein. Du "
        "bekommst das gewählte Label zurück und machst im selben Zug weiter. "
        "Nur für echte Verzweigungen, nicht aus Höflichkeit."
    ),
}


# ── Eigene Werkzeuge dieser Schiene: das Datei-Gedaechtnis ────────────
#
# Stehen NICHT in klein.TOOLS, weil der lokale Pfad gerade nicht testbar
# ist und ein 9B fuer jedes zusaetzliche Schema bezahlt. Sobald lokal
# wieder laeuft, wandern sie rueber — der Kern (ai._dispatch_tool) kennt
# sie ohnehin unter denselben Namen.
#
# Fuenf statt zwanzig: jedes Schema reist in JEDEM Turn mit. Deshalb ist
# das Tagebuch kein eigenes Werkzeug, sondern write_note(name="tagebuch").
_GEDAECHTNIS = [
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": (
                "Liest eine Gedaechtnis-Datei am Stueck. 'name' ist ein "
                "Dossier-Titel aus dem Kopf-Block (z.B. 'umzug', 'training'), "
                "oder 'sasha' fuer den Steckbrief, 'ziele' fuer die Ziele, "
                "'tagebuch' fuer den heutigen Tag. Lies das Dossier, BEVOR du "
                "ueber die Sache redest oder planst — der Kopf-Block nennt nur "
                "Titel, nicht Inhalte."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "Dossier-Titel, oder sasha/ziele/tagebuch."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_note",
            "description": (
                "Haelt etwas fest — haengt an, loescht nie. Zwei Verwendungen: "
                "name='tagebuch' fuer das, was gerade passiert ist oder was "
                "Sasha erzaehlt hat (in SEINEN Worten, nicht destilliert); ein "
                "Dossier-Titel fuer den STAND einer laufenden Sache ('Kueche: "
                "Regale haengen, Apparatur fehlt'). Ein neuer Titel legt ein "
                "neues Dossier an. Du fragst dafuer nicht um Erlaubnis, du "
                "machst es einfach — so wie jemand mitschreibt, der "
                "danebensitzt. Und du antwortest danach ganz normal weiter: "
                "mitschreiben IST keine Antwort, und ein stummer Turn wirkt "
                "wie ein Absturz."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "'tagebuch' oder ein Dossier-Titel."},
                    "text": {"type": "string",
                             "description": "Der Eintrag, in ganzen Saetzen."},
                },
                "required": ["name", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": (
                "Volltextsuche ueber Tagebuch und Dossiers. Fuer alles, was "
                "laenger her ist als das Gespraech: 'wie war Spanien', 'was "
                "hatte ich zum Umzug gesagt'. Stumpfe Wortsuche — nimm den "
                "Begriff, den SASHA benutzt haette, nicht eine Umschreibung."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Suchbegriff."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rewrite_note",
            "description": (
                "Schreibt ein Dossier KOMPLETT neu — zum Aufraeumen, wenn aus "
                "vielen angehaengten Absaetzen ein sauberer Stand werden soll. "
                "Destruktiv, wird bestaetigt. Der bisherige Inhalt muss vorher "
                "mit read_note gelesen werden, sonst wirfst du weg, was du nicht "
                "kennst."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":    {"type": "string", "description": "Dossier-Titel."},
                    "content": {"type": "string",
                                "description": "Der vollstaendige neue Inhalt."},
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_document",
            "description": (
                "Holt etwas aus dem Netz und LEGT ES AB — Modulhandbuch, "
                "Stundenplan, Datenblatt, Artikel. PDF wird automatisch zu "
                "Text, HTML entrumpelt, Binaeres als Datei mit Vermerk "
                "abgelegt. Danach lesbar mit read_note und durchsuchbar mit "
                "search_memory. Unterschied zu fetch_url: das liest etwas "
                "JETZT und vergisst es; hier wird abgelegt, um es spaeter "
                "wiederzufinden. Gib einen sprechenden 'name' — daraus wird "
                "der Ablageort."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url":  {"type": "string", "description": "http(s)-Adresse."},
                    "name": {"type": "string",
                             "description": "Kurzer Titel, z.B. 'modulhandbuch'."},
                },
                "required": ["url", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_series",
            "description": (
                "Legt eine neue Messkurve an — nur wenn Sasha etwas wirklich "
                "verfolgen will (Spagat in cm, L-Sit in Sekunden). Wird "
                "bestaetigt, damit aus Tippfehlern keine Halde halbtoter "
                "Kurven wird. Typen: 'number' (Zahl mit Einheit), 'scale' "
                "(1-10), 'time' (nur dass es an dem Tag war), 'period' "
                "(von-bis). Danach traegst du Werte mit log_series ein und "
                "verlinkst die Reihe im Dossier der Sache."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string", "description": "Name der Reihe."},
                    "typ":    {"type": "string",
                               "enum": ["number", "scale", "time", "period"]},
                    "einheit": {"type": "string",
                                "description": "z.B. 'cm', 's', 'km'. Optional."},
                },
                "required": ["name", "typ"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_series",
            "description": (
                "Traegt einen Messwert in eine bestehende Kurve ein (Schlaf, "
                "Stimmung, Training …) — fuer alles, was ueber Monate eine "
                "Kurve ergeben soll. Nur vorhandene Reihen; neue legt Sasha "
                "selbst an. Ohne 'day' zaehlt heute."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series": {"type": "string", "description": "Name der Reihe."},
                    "value":  {"type": "number", "description": "Der Wert."},
                    "day":    {"type": "string",
                               "description": "YYYY-MM-DD, sonst heute."},
                },
                "required": ["series", "value"],
            },
        },
    },
]


def _bauen() -> list:
    out = []
    for t in klein.TOOLS:
        fn = t["function"]
        if fn["name"] in _WEG:
            continue
        name = _NAMEN.get(fn["name"], fn["name"])
        out.append({
            "type": "function",
            "function": {
                "name":        name,
                # Kein Fallback auf klein: eine fehlende Beschreibung soll
                # beim Start auffallen, nicht als stiller Ballast mitreisen.
                "description": _BESCHREIBUNG[name],
                "parameters":  copy.deepcopy(fn["parameters"]),
            },
        })
    out.extend(copy.deepcopy(_GEDAECHTNIS))
    return out


TOOLS = _bauen()


# ── Die einheitliche Schnittstelle ─────────────────────────────────────

SYSTEM       = _SYSTEM_PROMPT
CAPABILITIES = _CAPABILITIES_PROMPT
MIC_HINT     = klein._MIC_INPUT_HINT     # gilt fuer jedes Modell gleich
DASHBOARD    = ""                        # die TUI zeigt kein Dashboard

# Ohne antwort-Tool bleibt nur die News-Sendung terminal (sie ist schon
# moderiert und wird direkt gestreamt, statt nacherzaehlt zu werden).
TERMINAL = {"read_news"}

MERKMALE = {
    "antwort_tool": False,
    "bild_marker":  False,
    "dashboard":    False,
}


def system(override: str | None = None, *, dashview: bool = True) -> str:
    """Der fertige statische Kopf dieser Schiene.

    `dashview` wird angenommen und ignoriert: es gibt hier keine
    Dashboard-Sicht. Der Parameter bleibt, damit beide Schienen dieselbe
    Signatur haben und der Kern nicht wissen muss, auf welcher er faehrt.
    """
    return (override or _SYSTEM_PROMPT) + "\n\n" + _CAPABILITIES_PROMPT
