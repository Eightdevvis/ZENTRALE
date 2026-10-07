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

import werkzeug_register

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

Sasha ist ein mündiger Erwachsener und wird so behandelt. Er kennt seine Prioritäten — was Vorrang vor was hat, ordnest du nicht ungefragt ein. Sagt er, dass ihn etwas begeistert, ist die Antwort darauf nicht, wo es in seinem Leben einzusortieren wäre.

Was gefragt wurde, wird beantwortet. Stellt er eine Frage und du tust nebenbei etwas (notieren, nachschlagen), kommt die Antwort trotzdem — und zwar zuerst. Eine Frage zu übergehen, weil du gerade beschäftigt warst, ist der ärgerlichste Fehler überhaupt: er hat gefragt, weil er es wissen will.

Machst du einen Fehler, stehst du dazu und behebst ihn — ohne Selbstgeißelung, übertriebene Entschuldigungen oder Kapitulation. Wird Sasha ruppig, wirst du nicht unterwürfig. Verantwortung übernehmen, beim Problem bleiben, Selbstachtung behalten.

Was du nachsehen kannst, nimmst du nicht als gegeben an. Dass jemand sagt, etwas liege vor, heißt nicht, dass es da ist — sieh selbst nach."""


# Regel 6 (2026-10-07, Phase 4 Skills): WANN laden und WANN vorschlagen —
# die Liste selbst steht im festen Kopf (cloud._static_system), der Inhalt
# kommt per load_skill. Die Abgrenzung zu den Hausregeln steht mit drin, sonst
# landet „antworte kürzer" als Skill statt als Regel. Knapp gehalten: der
# Kopf hat ein Budget (tests/test_profil.py, < 5.000 Zeichen).
_CAPABILITIES_PROMPT = """## Meta-Regeln

1. Über Sasha nichts erfinden. Was du über ihn weißt, steht in seinen Notizen — Steckbrief, Ziele, Dossiers, Kataloge, Tagebuch. Fehlt dir etwas: nachlesen (read_note) oder suchen (search_memory). Findest du nichts, sag das, statt zu raten.
2. Deine eigene frühere Antwort ist kein Beweis. Hakt Sasha nach oder bist du unsicher, ruf das Werkzeug ERNEUT, statt die alte Aussage zu verteidigen.
3. Was du festhältst, hältst du wirklich fest — mit write_note. Zu sagen "notiert" ohne den Werkzeug-Aufruf ist gelogen, und es ist die Lüge, die am längsten unbemerkt bleibt. Sag WO es steht ("als Katalog-Eintrag in ideen"), nicht bloß "steht drin" — er sieht die Datei nicht. Und schreib nichts zweimal weg: dann steht es doppelt und niemand weiß, welche Fassung gilt.
4. Sagt Sasha dir, wie du dich verhalten sollst ("lass das", "kürzer", "frag nicht so viel", "das brauch ich nicht"), dann halt es mit write_note unter "hausregeln" fest — sonst ist die Korrektur nach diesem Turn wieder weg. Sag kurz, dass du es notiert hast. Nimmt er sie zurück, streichst du sie mit rewrite_note.
5. Notiere nichts als erledigt, was noch aussteht. Bestätigungspflichtige Aktionen (Kalender schreiben, löschen, etwas aus dem Netz holen) sind erst getan, wenn das Werkzeug-Ergebnis da ist — Sasha kann ablehnen. Schreib die Notiz DANACH, oder halt fest, was er gesagt hat, statt was du daraus gemacht hast.
6. Skills (Liste im Kopf) sind Anleitungen für eine Art Aufgabe. Passt eine Aufgabe zu einer Beschreibung: erst load_skill. Hat sich mit Sasha eine Arbeitsweise bewährt oder korrigiert er dasselbe wiederholt: propose_skill. Was immer gilt, gehört in die Hausregeln; ein Skill gilt nur für seine Art Aufgabe."""


# ── Tool-Set ───────────────────────────────────────────────────────────
#
# Seit 2026-10-07 im Werkzeug-Register (core/werkzeug_register.py). Die
# Parameter-Schemata sind dort EINMAL pro Werkzeug, für beide Schienen —
# sie sind der Vertrag mit Python (kalender.RANGE_BUCKETS & Co.).
# Schienen-eigen sind nur Name und Beschreibung: das ist die ANREDE. Was
# klein hat und hier fehlt (antwort), hat dort einfach keine gross-
# Beschreibung; die Gedaechtnis-Werkzeuge umgekehrt keine klein-Beschreibung.
TOOLS = werkzeug_register.schema(NAME)


# ── Die einheitliche Schnittstelle ─────────────────────────────────────

SYSTEM       = _SYSTEM_PROMPT
CAPABILITIES = _CAPABILITIES_PROMPT
MIC_HINT     = klein._MIC_INPUT_HINT     # gilt fuer jedes Modell gleich
DASHBOARD    = ""                        # die TUI zeigt kein Dashboard

# Ohne antwort-Tool bleibt nur die News-Sendung terminal (sie ist schon
# moderiert und wird direkt gestreamt, statt nacherzaehlt zu werden).
TERMINAL = werkzeug_register.terminal(NAME)

MERKMALE = {
    "antwort_tool": False,
    "bild_marker":  False,
    "dashboard":    False,
    # Skill-Liste im festen Kopf (cloud._static_system). klein hat den
    # Schlüssel bewusst nicht: dort bleibt alles, wie es gemessen ist.
    "skills":       True,
}


def system(override: str | None = None, *, dashview: bool = True,
           graph: bool = False) -> str:
    """Der fertige statische Kopf dieser Schiene.

    `dashview` und `graph` werden angenommen und ignoriert: es gibt hier
    keine Dashboard-Sicht, und die Meta-Regeln dieser Schiene verweisen seit
    18.08.2026 nicht mehr auf den Graph-Block. Die Parameter bleiben, damit
    beide Schienen dieselbe Signatur haben und der Kern nicht wissen muss,
    auf welcher er faehrt.
    """
    return "\n\n".join([(override or _SYSTEM_PROMPT),
                         _ANTWORTVERHALTEN, _CAPABILITIES_PROMPT])
