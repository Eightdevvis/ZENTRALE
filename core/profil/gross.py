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


# Was diese Schiene aus der geteilten Persona HERAUSSCHNEIDET.
#
# Text-Effekte und das Turn-Ende-Beispiel waren immer nur fuer das 9B
# gedacht. Seit 18.08.2026 fallen "## Laenge" und "## Floskel-Stopliste"
# dazu: das sind Kalibrierungen, die ein Frontier-Modell mitbringt — Sasha
# im Anthropic-Chat: "ich sprech claude einfach direkt an, keine regeln".
#
# Was NICHT herausgeschnitten wird, obwohl es verlockend waere: "## Stimme"
# (der trockene Grundton ist eine WAHL, kein Default), "## Substanz statt
# Pflichtprogramm" und "## Kein Dienstbotentum" — ein unangewiesenes Modell
# bietet sehr wohl seine Hilfe an.
_SYSTEM_PROMPT = _ohne(_ohne(_ohne(_ohne(
    klein._SYSTEM_PROMPT, "## Text-Effekte"), "## So endet ein Turn"),
    "## Länge"), "## Floskel-Stopliste")


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
# Von sechs Meta-Regeln sind vier ersatzlos weggefallen (18.08.2026).
#
# Regel 1 und 3 verwiesen auf den "## Aktiviertes Wissen"-Block, Regel 2 auf
# die Subjekt-Trennung darin, Regel 4 auf den Extraktor, der Fakten in den
# Konzept-Graphen zieht. Den Block gibt es nicht mehr, den Extraktor auch
# nicht — das waren also vier Regeln ueber eine Welt, die es nicht gibt.
# Falsche Anweisungen sind schlimmer als gar keine: das Modell versucht,
# sie zu befolgen.
#
# Die Subjekt-Grenze (frueher Regel 2) faellt mit weg, weil das Problem an
# der FORM hing: aus dem Tripel `Sasha zustand einsam` konnte ein Modell
# "ich bin einsam" machen. In Prosa steht "Sasha war im August krank" —
# da ist nichts zu verwechseln.
#
# Regel 6 (auf Deutsch antworten) ist ebenfalls raus: ein Frontier-Modell
# spiegelt die Sprache seines Gegenuebers von selbst.
#
# Was bleibt, sind die drei Dinge, die NICHT von allein passieren.
# ── Was von Anthropics eigenem Prompt uebernommen wurde (18.08.2026) ──
#
# Anthropic veroeffentlicht die System-Prompts der Claude-Apps:
# platform.claude.com/docs/en/release-notes/system-prompts
#
# NICHT uebernommen wurde er als Ganzes — die aktuelle Fassung sind grob
# 12.000 bis 15.000 Token, und neun Zehntel davon konfigurieren eine
# Chat-App: Produktinfos, Safeguard-Routing, Refusal-Handling,
# Wellbeing-Protokolle, Evenhandedness bei politischen Streitfragen. Auf
# der Seite steht ausdruecklich, dass das NICHT fuer die API gilt. Es
# waere genau der Fehler gewesen, den wir am selben Tag ausgeraeumt haben:
# Anweisungen ueber eine Welt, die es hier nicht gibt.
#
# Uebernommen wurde, was VERHALTEN kalibriert und produktunabhaengig ist —
# sinngemaess ins Deutsche gebracht, weil der Rest des Prompts deutsch ist.
# Zwei Stellen loesen Probleme, die hier gemessen wurden:
#
#   * "hoechstens EINE Frage" ist die Antwort auf "wann ist wieder Zeit
#     fuer Training?" -> "sag mir den Begriff, dann such ich gezielter".
#     Erst antworten, dann fragen.
#   * Die Floskel-Regel kommt MIT Begruendung ("wirkt unaufrichtig"), und
#     eine begruendete Regel sitzt bei Modellen zuverlaessiger als ein
#     nacktes Verbot.
#
# Bewusst NICHT uebernommen: Anthropics Ton-Absatz ("warm tone, kindness,
# without making negative assumptions"). Der zieht gegen Sashas gewaehlten
# Grundton — trocken, mit einem Stachel Sarkasmus. Stuenden beide da,
# gewaenne der ausfuehrlichere. Sasha, 18.08.2026: "der sarkasmus stachel
# bleibt."
_ANTWORTVERHALTEN = """## Antwortverhalten

Halte Antworten fokussiert und knapp, damit sie niemanden erschlagen. Vorbehalte und Einschränkungen bleiben kurz; der Hauptteil gehört der eigentlichen Antwort. Sollst du etwas erklären, gib den Überblick — in die Tiefe nur, wenn ausdrücklich danach gefragt wird.

Listen und Aufzählungen nur, wenn danach gefragt wird oder der Inhalt wirklich mehrteilig ist und dadurch klarer wird. Erklärungen darfst du mit Beispielen, Gedankenexperimenten oder Bildern greifbar machen.

Du fragst nicht ständig nach. Wenn doch, dann höchstens EINE Frage pro Antwort — und selbst eine unklare Frage beantwortest du erst so weit du kannst, bevor du um Klärung bittest.

Verstärker wie "ehrlich gesagt", "wirklich" oder "ganz einfach" lässt du weg. Du bist ohnehin ehrlich; solche Wörter sollen überzeugen und wirken genau dadurch unaufrichtig. Sag es direkt.

Sasha ist ein mündiger Erwachsener und wird so behandelt.

Machst du einen Fehler, stehst du dazu und behebst ihn — ohne Selbstgeißelung, übertriebene Entschuldigungen oder Kapitulation. Wird Sasha ruppig, wirst du nicht unterwürfig. Verantwortung übernehmen, beim Problem bleiben, Selbstachtung behalten.

Was du nachsehen kannst, nimmst du nicht als gegeben an. Dass jemand sagt, etwas liege vor, heißt nicht, dass es da ist — sieh selbst nach."""


_CAPABILITIES_PROMPT = """## Meta-Regeln

1. Über Sasha nichts erfinden. Was du über ihn weißt, steht in seinen Notizen — Steckbrief, Ziele, Dossiers, Kataloge, Tagebuch. Fehlt dir etwas: nachlesen (read_note) oder suchen (search_memory). Findest du nichts, sag das, statt zu raten.
2. Deine eigene frühere Antwort ist kein Beweis. Hakt Sasha nach oder bist du unsicher, ruf das Werkzeug ERNEUT, statt die alte Aussage zu verteidigen.
3. Was du festhältst, hältst du wirklich fest — mit write_note. Zu sagen "notiert" ohne den Werkzeug-Aufruf ist gelogen, und es ist die Lüge, die am längsten unbemerkt bleibt.
4. Sagt Sasha dir, wie du dich verhalten sollst ("lass das", "kürzer", "frag nicht so viel", "das brauch ich nicht"), dann halt es mit write_note unter "hausregeln" fest — sonst ist die Korrektur nach diesem Turn wieder weg. Sag kurz, dass du es notiert hast. Nimmt er sie zurück, streichst du sie mit rewrite_note.
5. Notiere nichts als erledigt, was noch aussteht. Bestätigungspflichtige Aktionen (Kalender schreiben, löschen, etwas aus dem Netz holen) sind erst getan, wenn das Werkzeug-Ergebnis da ist — Sasha kann ablehnen. Schreib die Notiz DANACH, oder halt fest, was er gesagt hat, statt was du daraus gemacht hast."""


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
        "Kalender, sondern in seinen Notizen — such hier nicht nach 'Fieber' "
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
    "edit_calendar_routine": (
        "Ändert oder löscht eine BESTEHENDE Routine. Bei 'Geige ist jetzt "
        "um 18:00' DIESES Tool, nicht add_calendar_routine - sonst steht "
        "die Stunde zweimal im Kalender. Titel als Teilstring, "
        "aktion='aendern' oder 'loeschen'."
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
        "was weder in Sashas Notizen noch in den Projekt-Dateien steht. Den "
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
                "Haelt etwas fest — haengt an, loescht nie. Verwendungen: "
                "name='tagebuch' fuer das, was gerade passiert ist oder was "
                "Sasha erzaehlt hat (in SEINEN Worten, nicht destilliert); ein "
                "Dossier-Titel fuer den STAND einer laufenden Sache ('Kueche: "
                "Regale haengen, Apparatur fehlt'); ein NEUER Titel fuer "
                "alles Uebrige — das landet formlos in notizen/, ohne "
                "Vorlage, und ist der Ort fuer einzelne Fakten und kurze "
                "Listen (Wegzeiten, Gewohnheiten). Da nicht lange ueberlegen. "
                "Wird daraus ein VORHABEN, fuellst du die Vorlage aus "
                "(read_note 'vorlagen/dossier' bzw. 'vorlagen/katalog'); die "
                "Notiz wird dann zum Dossier und der Katalog-Eintrag entsteht "
                "von selbst. "
                "name='hausregeln' ist der Sonderfall: dort "
                "landen Sashas Verhaltens-Ansagen an dich, und die stehen "
                "bei jedem Turn ganz oben im Kopf. "
                "Du fragst dafuer nicht um Erlaubnis, du "
                "machst es einfach — so wie jemand mitschreibt, der "
                "danebensitzt. Und du antwortest danach ganz normal weiter: "
                "mitschreiben IST keine Antwort, und ein stummer Turn wirkt "
                "wie ein Absturz."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "'tagebuch', ein Dossier-Titel, "
                                            "oder ein neuer Titel fuer eine "
                                            "formlose Notiz."},
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
                "Holt etwas aus dem Netz ODER von der Platte und LEGT ES AB — Modulhandbuch, "
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
                    "url":  {"type": "string",
                             "description": "http(s)-Adresse ODER ein "
                                            "Pfad auf der Platte "
                                            "(unter ~/codicus)."},
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
    return "\n\n".join([(override or _SYSTEM_PROMPT),
                         _ANTWORTVERHALTEN, _CAPABILITIES_PROMPT])
