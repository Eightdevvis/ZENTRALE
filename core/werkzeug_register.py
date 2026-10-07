# core/werkzeug_register.py
#
# Das Werkzeug-Register: EIN Eintrag pro KI-Werkzeug. Name, Parameter-Schema,
# die Beschreibung je Schiene (klein/gross), die Erlaubnis-Regel samt Frage an
# Sasha, und ob es terminal ist. Ausgeführt wird in core/ki_werkzeuge.py.
#
# 2026-10-07, Phase 0 des Claude-Web-Plans (memory/ki/claude_web_plan.md).
# Vorher lag ein Werkzeug an drei Stellen: Schema in profil/klein.py (und
# abgeleitet in gross.py), Ausführung in ki_werkzeuge._verteilen, Erlaubnis in
# erlaubnis.py. Jedes neue Werkzeug wuchs an allen dreien, und nichts merkte,
# wenn eine davon fehlte. Jetzt beziehen profil, erlaubnis und ki_werkzeuge
# ihre Listen von hier. Wie man ein Werkzeug anlegt: memory/ki/ki_system.md.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).
#
# ── Warum sich die Ausführer hier ANMELDEN, statt importiert zu werden ──
# (2026-10-07) ki_werkzeuge.ausfuehren muss im Register nachschlagen, welche
# Funktion zu einem Namen gehört. Importierte das Register umgekehrt die
# Funktionen aus ki_werkzeuge, wäre das ein Kreis. Also importiert hier
# niemand den Kern darüber: das Register braucht nur Dienste (kalender für das
# Schema und die Konflikt-Zeile, gedaechtnis für die Kernakten, skills für
# die Fragen zu Skills), und
# ki_werkzeuge meldet jede Funktion mit @werkzeug_register.ausfuehrer("name")
# an. Kein Waisenkind bleibt unbemerkt: der Test (tests/test_werkzeug_register.py)
# prüft beide Richtungen.
#
# ── Die Byte-Bedingung ──────────────────────────────────────────────────
# Was schema() baut, geht wörtlich an die Modelle. Reihenfolge, Texte und
# Schemas sind gegen einen Schnappschuss von vor dem Umbau festgenagelt
# (tests/test_werkzeug_schnappschuss.py): ein verschobenes Komma bricht den
# Anthropic-Prompt-Cache (die Werkzeuge stehen ganz vorn im gecachten Teil),
# und das lokale qwen ist auf genau diese Texte gemessen. Die klein-Texte sind
# ein wörtlicher Umzug aus profil/klein.py — dort aufräumen erst, wenn es
# gegen ein echtes qwen nachgemessen werden kann.
#
# Neue Werkzeuge nur auf der gross-Schiene (klein=None): das 9B bezahlt jedes
# Schema in jedem Zug, und was es bekommt, wird vorher gemessen
# (memory/ki/bench_history.md).

import copy
from dataclasses import dataclass
from typing import Callable

import gedaechtnis
import kalender
import skills


SCHIENEN = ("klein", "gross")


@dataclass
class Werkzeug:
    """Ein Werkzeug. Die Reihenfolge der Einträge unten IST die Reihenfolge,
    in der die Schienen sie ans Modell geben.

    name            Der Name, den der Kern spricht (englisch, kanonisch).
    parameter       JSON-Schema der Argumente — der Vertrag mit Python, für
                    beide Schienen gleich.
    klein, gross    Beschreibung auf dieser Schiene; None = dort nicht
                    angeboten. Die Beschreibung ist ANREDE und gehört der
                    Schiene, deshalb zwei Texte.
    klein_name      Alter deutscher Name auf der klein-Schiene (lies_news …);
                    der Kern übersetzt ihn mit kanonisch().
    erlaubnis       False = nie fragen, True = immer, oder eine Funktion
                    f(args) -> bool (nur mit Argumenten gefragt).
    frage           f(args) -> str: die Ja/Nein-Frage, die Sasha sieht.
                    Fehlt sie, kommt eine allgemeine.
    terminal        Das Ergebnis IST die Antwort, danach keine Runde mehr
                    (Behandlung in werkzeug_schleife.run_tool).
    in_der_schleife Hat keinen Ausführer, die Schleife erledigt es selbst
                    (antwort, ask_choice).
    ausfuehrer      f(args) -> str, angemeldet von ki_werkzeuge.
    """
    name: str
    parameter: dict
    klein: str | None = None
    gross: str | None = None
    klein_name: str | None = None
    erlaubnis: bool | Callable[[dict], bool] = False
    frage: Callable[[dict], str] | None = None
    terminal: bool = False
    in_der_schleife: bool = False
    ausfuehrer: Callable[[dict], str] | None = None

    def beschreibung(self, schiene: str) -> str | None:
        return getattr(self, schiene)

    def name_auf(self, schiene: str) -> str:
        if schiene == "klein" and self.klein_name:
            return self.klein_name
        return self.name


# ── Erlaubnis: Regeln und Fragen ───────────────────────────────────────
#
# Was vor der Ausführung bestätigt werden muss: alles, was schreibt, löscht,
# ins Netz geht oder Geld kostet. Das Gate kommt automatisch, das Modell
# weiß davon nichts und muss nicht selbst nachfragen (ein 9b ruft sowas nicht
# zuverlässig von selbst). Lesen und Auskunft bleibt frei. Abgefangen wird in
# werkzeug_schleife.run_tool, gefragt über erlaubnis.frage.
#
# Die Frage zeigt Sasha im Dialog (und liest sie vor). Sie muss sagen, WAS
# passiert: Sasha drückt einen Knopf, ohne den Werkzeug-Aufruf zu sehen.

def _label(args: dict) -> str:
    return (args.get("label") or "").strip() or "diesen Eintrag"


def _trifft_kernakte(args: dict) -> bool:
    """write_note ist im Normalfall frei (mitschreiben ohne Rückfrage — eine
    KI, die vor jeder Notiz fragt, ist kein Sekretär, sondern eine Zumutung),
    aber NICHT, wenn es eine Kernakte trifft: Hausregeln, Steckbrief, Ziele
    (Sasha, 2026-10-06; gedaechtnis.schreibt_kernakte)."""
    return gedaechtnis.schreibt_kernakte(args.get("name")) is not None


def _frage_notiz(args: dict) -> str:
    akte = gedaechtnis.schreibt_kernakte(args.get("name")) or "die Notiz"
    text = " ".join(str(args.get("text") or "").split())
    if len(text) > 200:
        text = text[:199] + "…"
    return f'Soll ich in {akte} schreiben: "{text}"?'


def _frage_dokument(args: dict) -> str:
    return (f'Soll ich {args.get("url", "das")} holen und als '
            f'"{args.get("name", "Dokument")}" ablegen?')


def _frage_messkurve(args: dict) -> str:
    return f'Soll ich eine neue Messkurve "{args.get("name", "?")}" anlegen?'


def _frage_dossier_neu(args: dict) -> str:
    wie = (args.get("name") or "das Dossier").strip()
    return (f'Soll ich das Dossier "{wie}" komplett neu schreiben? '
            f'(Die bisherige Fassung bleibt als .bak liegen.)')


def _frage_termin(args: dict) -> str:
    label = _label(args)
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


def _frage_routine(args: dict) -> str:
    rrule = (args.get("rrule") or "").strip()
    rrule_txt = f' ({rrule})' if rrule else ''
    return f'Soll ich die Routine "{_label(args)}"{rrule_txt} eintragen?'


def _frage_pause(args: dict) -> str:
    von = (args.get("von") or "").strip()
    bis = (args.get("bis") or "").strip()
    spanne = f' von {von} bis {bis}' if von and bis else ''
    return f'Soll ich "{_label(args)}"{spanne} pausieren?'


def _frage_routine_aendern(args: dict) -> str:
    label = _label(args)
    if (args.get("aktion") or "").strip() == "loeschen":
        return f'Soll ich die Routine "{label}" wirklich dauerhaft löschen?'
    # Die Frage nennt, WAS sich aendert. "Soll ich die Routine aendern?"
    # waere nicht zustimmungsfaehig.
    teile = []
    for feld, wort in (("time", "Beginn"), ("ende", "Ende"),
                       ("ort", "Ort"), ("rrule", "Wiederholung"),
                       ("neuer_titel", "Titel")):
        wert = (args.get(feld) or "").strip()
        if wert:
            teile.append(f"{wort} {wert}")
    was = ", ".join(teile) if teile else "etwas"
    return f'Soll ich die Routine "{label}" ändern auf {was}?'


def _frage_termin_loeschen(args: dict) -> str:
    day = (args.get("day") or "").strip()
    wann_txt = f' am {day}' if day else ''
    return f'Soll ich "{_label(args)}"{wann_txt} wirklich löschen?'


def _frage_suche(args: dict) -> str:
    q = (args.get("query") or "").strip()
    return f'Soll ich im Internet nach "{q}" suchen?' if q else "Soll ich im Internet suchen?"


def _frage_seite(args: dict) -> str:
    u = (args.get("url") or "").strip()
    return f'Soll ich die Seite {u} aus dem Internet laden?' if u else "Soll ich eine Webseite laden?"


def _frage_code(args: dict) -> str:
    """Sasha sieht die Sprache und den Anfang des Programms. Die TUI zeigt
    die Frage einzeilig, deshalb stehen die Zeilen mit ⏎ hintereinander."""
    sprache = "Shell" if args.get("sprache") == "shell" else "Python"
    zeilen = [z.rstrip() for z in str(args.get("code") or "").splitlines()
              if z.strip()]
    anfang = " ⏎ ".join(z.strip()[:80] for z in zeilen[:4])
    if len(anfang) > 300:
        anfang = anfang[:299] + "…"
    mehr = f" (+{len(zeilen) - 4} Zeilen)" if len(zeilen) > 4 else ""
    return (f"Soll ich dieses {sprache}-Programm abgeschottet ausführen "
            f"(ohne Internet, ohne Zugriff auf deine Dateien)? "
            f"„{anfang}“{mehr}")


def _frage_skill_neu(args: dict) -> str:
    """Sasha sieht Name, wofür der Skill ist und den Anfang der Anleitung —
    er soll entscheiden können, ohne den Werkzeug-Aufruf zu lesen."""
    name = gedaechtnis.slug(args.get("name")) or "?"
    wofuer = " ".join(str(args.get("beschreibung") or "").split())[:160]
    return (f'Soll ich mir die Anleitung „{name}“ merken? Wofür: {wofuer or "-"}. '
            f'„{skills.anfang(args.get("inhalt"))}“')


def _frage_skill_aendern(args: dict) -> str:
    name = gedaechtnis.slug(args.get("name")) or "?"
    return (f'Soll ich die Anleitung „{name}“ neu schreiben? (Die bisherige '
            f'Fassung bleibt als .bak liegen.) „{skills.anfang(args.get("inhalt"))}“')


# ── Die Werkzeuge ──────────────────────────────────────────────────────
#
# Reihenfolge = Reihenfolge im Prompt. Nicht umsortieren: das bricht den
# Anthropic-Cache und ändert, was das qwen sieht. Neue Werkzeuge hinten an.
#
# Die gross-Beschreibungen sind kürzer (6.342 → ~2.200 Zeichen beim Schnitt
# 2026-08). Was BLEIBT ist Vertrag: die Parameter-Semantik ('zeitraum' vs.
# start_date/end_date, 'suche', die Bedeutung der ⚠-Marker) und die
# Bestaetigungspflicht. Was GEHT ist Erziehung ("Du hast KEINE Termine im
# Gedaechtnis", "nie aus dem Kopf raten") — das erzwang obendrein
# Tool-Runden, die es nicht braucht, und jede Runde ist ein voller Call.

WERKZEUGE = [
    # ── Kalender ──
    # Schreiben, Ändern, Löschen wird bestätigt: es verändert dauerhafte Daten.
    Werkzeug(
        name="read_calendar",
        klein=(
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
        gross=(
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
        parameter={
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
    ),
    Werkzeug(
        name="read_time",
        klein=(
            "Sagt dir, wie spät es JETZT ist - und was als nächstes ansteht, "
            "samt Abstand in Minuten. Du weißt die Uhrzeit nicht von selbst; "
            "rate sie nie und rechne sie nie aus dem Kopf aus. Ruf dies, wenn "
            "Sasha nach der Zeit fragt, wenn er wissen will wie lange er noch "
            "hat, oder wenn die Tageszeit für eine Entscheidung zählt."
        ),
        gross=(
            "Wie spät es jetzt ist, plus der nächste Termin mit Abstand in "
            "Minuten. Du weißt die Uhrzeit nicht von selbst - rate sie nie."
        ),
        parameter={"type": "object", "properties": {}},
    ),
    Werkzeug(
        name="add_calendar_entry",
        erlaubnis=True,
        frage=_frage_termin,
        klein=(
            "Trägt einen Einmal-Eintrag in einen Kalender-Layer ein. "
            "Nutze dies wenn der User einen Termin nennt, eine Frist, ein "
            "Ereignis: 'Arzt am 10. Juni um 14:30', 'TÜV-Frist 3. Juni'. "
            "Im Zweifel Layer 'termine'. Datum-Format: YYYY-MM-DD."
        ),
        gross=(
            "Trägt einen Einmal-Termin oder eine Frist ein. Im Zweifel Layer "
            "'termine'. Datum YYYY-MM-DD."
        ),
        parameter={
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
    ),
    Werkzeug(
        name="add_calendar_routine",
        erlaubnis=True,
        frage=_frage_routine,
        klein=(
            "Trägt eine Wiederholungs-Regel in einen Kalender-Layer ein (iCal RRULE). "
            "Nutze dies bei regelmäßigen Aktivitäten: 'jeden Dienstag Geige', "
            "'jeden 1. im Monat Miete', 'Mo/Mi/Fr Sport'. Layer-Default: 'routinen'. "
            "RRULE-Beispiele: FREQ=WEEKLY;BYDAY=TU | FREQ=WEEKLY;BYDAY=MO,WE,FR | "
            "FREQ=MONTHLY;BYMONTHDAY=1 | FREQ=MONTHLY;BYDAY=2TU (2. Dienstag/Monat)."
        ),
        gross=(
            "Trägt eine Wiederholungs-Regel ein (iCal RRULE), Layer-Default "
            "'routinen'. Beispiele: FREQ=WEEKLY;BYDAY=TU | "
            "FREQ=WEEKLY;BYDAY=MO,WE,FR | FREQ=MONTHLY;BYMONTHDAY=1 | "
            "FREQ=MONTHLY;BYDAY=2TU (2. Dienstag im Monat)."
        ),
        parameter={
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
    ),
    Werkzeug(
        name="edit_calendar_routine",
        erlaubnis=True,
        frage=_frage_routine_aendern,
        klein=(
            "Ändert oder löscht eine BESTEHENDE Wiederholungs-Regel. Nimm dies, "
            "wenn sich an etwas Regelmäßigem etwas ändert - 'Geige ist jetzt um "
            "18:00 statt 17:45', 'Sport fällt weg'. NICHT add_calendar_routine "
            "dafür nehmen: das legt eine zweite Regel an und die alte bleibt "
            "stehen. Der Titel muss nur ein Stück des Eintrags treffen "
            "('geige' findet 'Geigenstunde'). Weggelassene Felder bleiben, wie "
            "sie sind."
        ),
        gross=(
            "Ändert oder löscht eine BESTEHENDE Routine. Bei 'Geige ist jetzt "
            "um 18:00' DIESES Tool, nicht add_calendar_routine - sonst steht "
            "die Stunde zweimal im Kalender. Titel als Teilstring, "
            "aktion='aendern' oder 'loeschen'."
        ),
        parameter={
            "type": "object",
            "properties": {
                "label": {
                    "type":        "string",
                    "description": "Titel der bestehenden Routine (Teilstring genügt)",
                },
                "aktion": {
                    "type":        "string",
                    "enum":        ["aendern", "loeschen"],
                    "description": "'aendern' oder 'loeschen'",
                },
                "time": {
                    "type":        "string",
                    "description": "Neue Uhrzeit HH:MM (24h)",
                },
                "ende": {
                    "type":        "string",
                    "description": "Neues Ende HH:MM (24h)",
                },
                "rrule": {
                    "type":        "string",
                    "description": "Neue Wiederholung, z.B. 'FREQ=WEEKLY;BYDAY=MO'",
                },
                "ort": {
                    "type":        "string",
                    "description": "Neuer Ort",
                },
                "neuer_titel": {
                    "type":        "string",
                    "description": "Neuer Titel, falls die Aktivität anders heißt",
                },
            },
            "required": ["label", "aktion"],
        },
    ),
    Werkzeug(
        name="add_calendar_pause",
        erlaubnis=True,
        frage=_frage_pause,
        klein=(
            "Trägt eine Pause/einen Ausfall für eine regelmäßige Aktivität "
            "ein - in dem Zeitraum findet sie NICHT statt (Ferien, Feiertag, "
            "Lehrerin im Urlaub). Nutze dies, wenn der User sowas sagt: "
            "'Geige fällt in den Sommerferien aus, 1.-15. August', 'nächste "
            "Woche keine Fahrschule'. 'label' muss zum Routinen-Titel im "
            "Kalender passen (z.B. 'Geigenstunde'). Datum: YYYY-MM-DD."
        ),
        gross=(
            "Trägt eine Pause für eine regelmäßige Aktivität ein - in dem "
            "Zeitraum findet sie NICHT statt (Ferien, Lehrerin im Urlaub). "
            "'label' muss zum Routinen-Titel im Kalender passen. Datum YYYY-MM-DD."
        ),
        parameter={
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
    ),
    Werkzeug(
        name="delete_calendar_entry",
        erlaubnis=True,
        frage=_frage_termin_loeschen,
        klein=(
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
        gross=(
            "Löscht einen Einmal-Termin. Label-Match ist Teilstring, Datum "
            "YYYY-MM-DD. Wirkt nicht auf Routinen oder Pausen."
        ),
        parameter={
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
    ),
    Werkzeug(
        name="read_file",
        klein=(
            "Liest den Inhalt einer Datei aus dem ZENTRALE-Projekt. "
            "Nutze list_files zuerst um zu sehen was verfügbar ist. "
            "Nützlich wenn der User nach Daten, Code oder Notizen fragt."
        ),
        gross=(
            "Liest eine Datei aus dem ZENTRALE-Projekt. Vorher list_files."
        ),
        parameter={
            "type": "object",
            "properties": {
                "path": {
                    "type":        "string",
                    "description": "Relativer Pfad zur Datei, z.B. 'data/sleep_quality.json'",
                },
            },
            "required": ["path"],
        },
    ),
    Werkzeug(
        name="list_files",
        klein=(
            "Listet alle Dateien auf die gelesen werden können. Aufrufen bevor read_file."
        ),
        gross=(
            "Listet die Dateien auf, die gelesen werden können."
        ),
        parameter={
            "type":       "object",
            "properties": {},
        },
    ),
    # ── Persönliche Tagesschau ──
    # Liest das im Hintergrund (core/news.py) gebaute Weltpolitik-Briefing.
    # Read-only + lokal -> kein Gate. Der Fetch selbst telefoniert nach
    # draußen, ist aber vom Chat entkoppelt (eigener periodischer Thread,
    # leuchtet im Internet-Panel). Terminal: das Briefing ist schon moderiert
    # und wird direkt gestreamt, statt nacherzählt zu werden.
    Werkzeug(
        name="read_news",
        klein_name="lies_news",
        terminal=True,
        klein=(
            "Liefert ein Weltpolitik-Briefing - aus vielen Nachrichtenquellen "
            "weltweit zusammengetragen, nach Themen gebündelt und mit "
            "gegenübergestellten Perspektiven. Zwei Modi über 'tage': "
            "ohne tage (oder 0) = die aktuelle Tagessendung ('was ist heute/grad "
            "los'). Mit tage=7 = ein Wochenrückblick ('was ist die Woche/seit ich "
            "weg war passiert'). Lies das Ergebnis locker und moderierend vor; "
            "du darfst kürzen oder auf einen Aspekt eingehen."
        ),
        gross=(
            "Weltpolitik-Briefing aus vielen Quellen, nach Themen gebündelt und "
            "mit gegenübergestellten Perspektiven. 'tage' weglassen (oder 0) = "
            "heutige Sendung; tage=7 = Wochenrückblick ('was war, seit ich weg "
            "war'). Dein Trainingswissen taugt fürs Tagesgeschehen nicht - bei "
            "Fragen nach Nachrichten oder Weltlage dieses Tool rufen statt zu "
            "raten. Das Ergebnis darfst du kürzen und moderieren."
        ),
        parameter={
            "type": "object",
            "properties": {
                "tage": {
                    "type":        "integer",
                    "description": "Rückblick-Fenster in Tagen. 0/weglassen = aktuelle Sendung, 7 = Wochenrückblick.",
                },
            },
        },
    ),
    # Liest NUR den lokalen Triage-Stand (core/mail.py) — kein IMAP, kein Netz,
    # nichts wird verschoben. Read-only + lokal -> kein Gate.
    Werkzeug(
        name="read_mail",
        klein_name="lies_mail",
        klein=(
            "Liefert den Stand der Mail-Triage: wie viele Mails je Kategorie "
            "einsortiert wurden und welche unbekannten Absender noch auf eine "
            "Zuordnung warten (der 'sasha muss gucken'-Stapel). Zwei Modi über "
            "'modus': ohne modus (oder '') = Überblick mit Zählern + Review-"
            "Stapel; modus='review' = nur der Review-Stapel, ausführlicher. "
            "Nur lesen — sortiert oder löscht nichts."
        ),
        gross=(
            "Stand der Mail-Triage: Zähler je Kategorie plus die unbekannten "
            "Absender, die noch auf Zuordnung warten. modus='review' = nur dieser "
            "Stapel, ausführlicher. Nur lesen, sortiert und löscht nichts. Zähler "
            "und Absender kennst du nicht aus dir selbst - hier rufen, nicht "
            "raten."
        ),
        parameter={
            "type": "object",
            "properties": {
                "modus": {
                    "type":        "string",
                    "description": "'' = Überblick (Default), 'review' = nur der Stapel unbekannter Absender.",
                },
            },
        },
    ),
    # ── Internet-Pipe (gegatet) ──
    # Zwei Werkzeuge, die bewusst nach draußen telefonieren (core/web.py). Vor
    # JEDEM Aufruf kommt ein JA/NEIN-Dialog: ZENTRALE ist sonst offline, was
    # das LAN verlässt, gibt Sasha bewusst frei. Der Traffic leuchtet
    # zusätzlich im orangen Internet-Panel auf (net.py). Such-Quelle heute:
    # DuckDuckGo keyless, in web._ddg_search gekapselt und später tauschbar.
    Werkzeug(
        name="web_search",
        klein_name="web_suche",
        erlaubnis=True,
        frage=_frage_suche,
        klein=(
            "Sucht im Internet und gibt die Top-Treffer als Liste zurück "
            "(Titel, URL, kurzer Snippet). Nutze dies für aktuelles Wissen, "
            "Fakten, Nachrichten, Wetter oder alles, was NICHT in deinem "
            "Konzept-Graph (Gedächtnis) oder den Projekt-Dateien steht. Du "
            "bekommst nur Vorschau-Snippets - brauchst du den vollen Text "
            "einer Seite, ruf danach hole_url mit der passenden URL auf. "
            "Jede Suche muss Sasha bestätigen (Knopf-Dialog), also sparsam "
            "und gezielt einsetzen."
        ),
        gross=(
            "Sucht im Internet und gibt Titel, URL und Snippet zurück. Für alles, "
            "was weder in Sashas Notizen noch in den Projekt-Dateien steht. Den "
            "vollen Seitentext gibt es erst über fetch_url. Jede Suche muss Sasha "
            "bestätigen, also gezielt einsetzen."
        ),
        parameter={
            "type": "object",
            "properties": {
                "query": {
                    "type":        "string",
                    "description": "Die Suchanfrage in Worten, z.B. 'Wetter Berlin morgen'.",
                },
            },
            "required": ["query"],
        },
    ),
    Werkzeug(
        name="fetch_url",
        klein_name="hole_url",
        erlaubnis=True,
        frage=_frage_seite,
        klein=(
            "Lädt eine konkrete Webseite und gibt ihren Textinhalt zurück "
            "(gekürzt). Nutze dies, wenn du eine URL hast - aus einer "
            "web_suche oder vom User genannt - und den echten Inhalt brauchst, "
            "nicht nur den Suchschnipsel. Jeder Abruf muss Sasha bestätigen."
        ),
        gross=(
            "Lädt eine konkrete Webseite und gibt ihren Text zurück (gekürzt). "
            "Muss Sasha bestätigen."
        ),
        parameter={
            "type": "object",
            "properties": {
                "url": {
                    "type":        "string",
                    "description": "Die vollständige URL, z.B. https://de.wikipedia.org/wiki/...",
                },
            },
            "required": ["url"],
        },
    ),
    # antwort: die finale Antwort an den User laeuft (auch) ueber diesen
    # Tool-Kanal statt nur als Freitext. Im Kalender-Bench hob das die
    # Korrektheit von qwen3.5:9b (+~6 pp, gestapelt mit Sampling auf 82 %).
    # Mechanismus ist primaer die FRAMING-Wirkung: "liefere immer eine Antwort"
    # killt die "ich pruefe..."-und-Stopp-Aussetzer. werkzeug_schleife.run_tool
    # behandelt einen antwort-Call terminal (Text = finale Antwort). Das Modell
    # darf weiterhin frei antworten - dann greift der Suffix-Effekt, nicht der
    # Tool-Pfad. Nur klein: ein starkes Modell antwortet einfach.
    Werkzeug(
        name="antwort",
        terminal=True,
        in_der_schleife=True,
        klein=(
            "Gib deine finale Antwort an den User über dieses Tool aus - "
            "der vollständige Antworttext ins Feld 'text'. Reihenfolge: "
            "erst Daten-Tools (z.B. read_calendar) nutzen, dann mit 'antwort' "
            "die fertige, formulierte Antwort liefern. Nie nur ankündigen "
            "('ich schaue nach…'), immer die echte Antwort."
        ),
        gross=None,
        parameter={
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "Die fertige Antwort für den User."},
            },
            "required": ["text"],
        },
    ),
    # ask_choice: die KI löst SELBST einen Knopf-Dialog aus, wenn sie mitten
    # in einer Aufgabe eine knappe, diskrete Entscheidung von Sasha braucht
    # (statt auf eine freie Texteingabe zu warten). Teilt sich die
    # Button-Leiste + den blockierenden state.wait_permission-Mechanismus mit
    # dem Erlaubnis-Gate - nur der Auslöser ist hier das Modell selbst. Ohne
    # 'optionen' = Ja/Nein. werkzeug_schleife.run_tool behandelt den Call.
    Werkzeug(
        name="ask_choice",
        klein_name="frage_knopf",
        in_der_schleife=True,
        klein=(
            "Stellt Sasha eine Frage mit festen Antwort-Knöpfen, wenn du "
            "mitten in einer Aufgabe eine knappe, diskrete Entscheidung von "
            "ihr brauchst - statt eine freie Texteingabe abzuwarten. Im "
            "Dashboard erscheinen statt der Tastatur die Knöpfe, die Sasha "
            "mit Pfeiltasten und Enter wählt; du bekommst das gewählte Label "
            "zurück und machst dann im selben Zug weiter. Ohne 'optionen' "
            "sind es Ja/Nein. Sparsam einsetzen und nur für echte "
            "Verzweigungen - nicht aus Höflichkeit rückfragen."
        ),
        gross=(
            "Stellt Sasha eine Frage mit festen Antwort-Knöpfen, wenn du mitten "
            "in einer Aufgabe eine knappe Entscheidung brauchst - statt auf eine "
            "freie Texteingabe zu warten. Ohne 'optionen' ist es Ja/Nein. Du "
            "bekommst das gewählte Label zurück und machst im selben Zug weiter. "
            "Nur für echte Verzweigungen, nicht aus Höflichkeit."
        ),
        parameter={
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
    ),
    # ── Das Datei-Gedächtnis (nur gross) ──
    # Nicht auf klein, weil der lokale Pfad gerade nicht testbar ist und ein
    # 9B fuer jedes zusaetzliche Schema bezahlt. Sobald lokal wieder laeuft,
    # bekommen sie dort eine Beschreibung.
    #
    # Fuenf statt zwanzig: jedes Schema reist in JEDEM Turn mit. Deshalb ist
    # das Tagebuch kein eigenes Werkzeug, sondern write_note(name="tagebuch").
    Werkzeug(
        name="read_note",
        klein=None,
        gross=(
            "Liest eine Gedaechtnis-Datei am Stueck. 'name' ist ein "
            "Dossier-Titel aus dem Kopf-Block (z.B. 'umzug', 'training'), "
            "oder 'sasha' fuer den Steckbrief, 'ziele' fuer die Ziele, "
            "'tagebuch' fuer den heutigen Tag. Lies das Dossier, BEVOR du "
            "ueber die Sache redest oder planst — der Kopf-Block nennt nur "
            "Titel, nicht Inhalte."
        ),
        parameter={
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "Dossier-Titel, oder sasha/ziele/tagebuch."},
            },
            "required": ["name"],
        },
    ),
    Werkzeug(
        name="write_note",
        erlaubnis=_trifft_kernakte,
        frage=_frage_notiz,
        klein=None,
        gross=(
            "Haelt etwas fest — haengt an, loescht nie. Verwendungen: "
            "name='tagebuch' fuer das, was gerade passiert ist oder was "
            "Sasha erzaehlt hat (in SEINEN Worten, nicht destilliert); ein "
            "Dossier-Titel fuer den STAND einer laufenden Sache ('Kueche: "
            "Regale haengen, Apparatur fehlt'); ein NEUER Titel fuer "
            "alles Uebrige — das landet formlos in notizen/, ohne "
            "Vorlage, und ist der Ort fuer einzelne Fakten und kurze "
            "Listen (Wegzeiten, Gewohnheiten). Schwankst du: koennte es "
            "einen STATUS haben, also etwas sein, das er TUN "
            "koennte? Dann Katalog-Eintrag, sonst Notiz. Beides "
            "zur selben Sache ist falsch. "
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
        parameter={
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
    ),
    Werkzeug(
        name="search_memory",
        klein=None,
        gross=(
            "Volltextsuche ueber das ganze Gedaechtnis. Fuer alles, was "
            "laenger her ist als das Gespraech: 'wie war Spanien', 'was "
            "hatte ich zum Umzug gesagt'. Stumpfe Wortsuche — nimm den "
            "Begriff, den SASHA benutzt haette, nicht eine Umschreibung."
        ),
        parameter={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchbegriff."},
            },
            "required": ["query"],
        },
    ),
    # Dossier komplett neu schreiben ist destruktiv -> bestätigen. ANHÄNGEN
    # (write_note) ist es nicht und bleibt ungegatet, ausser auf Kernakten.
    Werkzeug(
        name="rewrite_note",
        erlaubnis=True,
        frage=_frage_dossier_neu,
        klein=None,
        gross=(
            "Schreibt ein Dossier KOMPLETT neu — zum Aufraeumen, wenn aus "
            "vielen angehaengten Absaetzen ein sauberer Stand werden soll. "
            "Destruktiv, wird bestaetigt. Der bisherige Inhalt muss vorher "
            "mit read_note gelesen werden, sonst wirfst du weg, was du nicht "
            "kennst."
        ),
        parameter={
            "type": "object",
            "properties": {
                "name":    {"type": "string", "description": "Dossier-Titel."},
                "content": {"type": "string",
                            "description": "Der vollstaendige neue Inhalt."},
            },
            "required": ["name", "content"],
        },
    ),
    # Holt etwas aus dem Netz UND legt es ab — beide Haelften wollen
    # bestaetigt sein: die Internet-Pipe wie bei fetch_url, und das
    # Schreiben, weil sonst ungefragt Dateien im Gedaechtnis landen.
    Werkzeug(
        name="fetch_document",
        erlaubnis=True,
        frage=_frage_dokument,
        klein=None,
        gross=(
            "Holt etwas aus dem Netz ODER von der Platte und LEGT ES AB — Modulhandbuch, "
            "Stundenplan, Datenblatt, Artikel. PDF wird automatisch zu "
            "Text, HTML entrumpelt, Binaeres als Datei mit Vermerk "
            "abgelegt. Danach lesbar mit read_note und durchsuchbar mit "
            "search_memory. Unterschied zu fetch_url: das liest etwas "
            "JETZT und vergisst es; hier wird abgelegt, um es spaeter "
            "wiederzufinden. Gib einen sprechenden 'name' — daraus wird "
            "der Ablageort."
        ),
        parameter={
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
    ),
    # ── Messreihen ──
    # Neue Messkurve: ohne Gate wuerde aus jedem Tippfehler eine weitere
    # halbtote Reihe in Sashas Uebersicht.
    Werkzeug(
        name="create_series",
        erlaubnis=True,
        frage=_frage_messkurve,
        klein=None,
        gross=(
            "Legt eine neue Messkurve an — nur wenn Sasha etwas wirklich "
            "verfolgen will (Spagat in cm, L-Sit in Sekunden). Wird "
            "bestaetigt, damit aus Tippfehlern keine Halde halbtoter "
            "Kurven wird. Typen: 'number' (Zahl mit Einheit), 'scale' "
            "(1-10), 'time' (nur dass es an dem Tag war), 'period' "
            "(von-bis). Danach traegst du Werte mit log_series ein und "
            "verlinkst die Reihe im Dossier der Sache."
        ),
        parameter={
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
    ),
    Werkzeug(
        name="log_series",
        klein=None,
        gross=(
            "Traegt einen Messwert in eine bestehende Kurve ein (Schlaf, "
            "Stimmung, Training …) — fuer alles, was ueber Monate eine "
            "Kurve ergeben soll. Nur vorhandene Reihen; neue legt Sasha "
            "selbst an. Ohne 'day' zaehlt heute."
        ),
        parameter={
            "type": "object",
            "properties": {
                "series": {"type": "string", "description": "Name der Reihe."},
                "value":  {"type": "number", "description": "Der Wert."},
                "day":    {"type": "string",
                           "description": "YYYY-MM-DD, sonst heute."},
            },
            "required": ["series", "value"],
        },
    ),
    # ── Code ausführen ──
    # Phase 7 (2026-10-07): Grundlage für „die KI als Coder". Jeder Lauf wird
    # bestätigt — auch abgeschottet startet hier ein Programm auf Sashas
    # Rechner, das er nicht geschrieben hat. Abschottung: core/sandbox.py.
    Werkzeug(
        name="run_code",
        erlaubnis=True,
        frage=_frage_code,
        klein=None,
        gross=(
            "Fuehrt ein kleines Python- oder Shell-Programm abgeschottet "
            "aus; zurueck kommen Rueckgabewert, Ausgabe, Fehler und neue "
            "Dateien. Fuer genaues Rechnen, Daten umformen, Skripte "
            "ausprobieren. KEIN Internet, KEIN Zugriff auf Sashas Dateien "
            "(nur ein leerer Arbeitsordner, jeder Lauf neu), Python nur mit "
            "Standardbibliothek, Zeitlimit 30 s (max 120), 512 MB, Ausgabe "
            "gekuerzt. Wird bestaetigt. Ergebnis mit print ausgeben."
        ),
        parameter={
            "type": "object",
            "properties": {
                "code":     {"type": "string",
                             "description": "Das Programm."},
                "sprache":  {"type": "string", "enum": ["python", "shell"],
                             "description": "Standard: python."},
                "zeitlimit": {"type": "integer",
                              "description": "Sekunden, 1-120. Standard 30."},
            },
            "required": ["code"],
        },
    ),
    # ── Skills ──
    # Phase 4 (2026-10-07): Anleitungen für eine Art Aufgabe (core/skills.py).
    # Lesen ist frei; Anlegen und Umschreiben werden bestätigt — ein Skill ist
    # eine Anweisung der KI an sich selbst, wie die Hausregeln.
    Werkzeug(
        name="load_skill",
        klein=None,
        gross=(
            "Holt die Anleitung eines Skills aus der Skill-Liste im Kopf. "
            "Passt die Aufgabe zu seiner Beschreibung: zuerst laden, dann "
            "danach arbeiten."
        ),
        parameter={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name aus der Liste."},
            },
            "required": ["name"],
        },
    ),
    Werkzeug(
        name="propose_skill",
        erlaubnis=True,
        frage=_frage_skill_neu,
        klein=None,
        gross=(
            "Schlaegt einen NEUEN Skill vor: eine Anleitung fuer eine Art "
            "Aufgabe, die sich mit Sasha bewaehrt hat. Wird bestaetigt; "
            "lehnt er ab, entsteht nichts. 'beschreibung' ist EINE Zeile: "
            "wann er passt. Inhalt knapp, in Schritten."
        ),
        parameter={
            "type": "object",
            "properties": {
                "name":         {"type": "string",
                                 "description": "Kurz, z.B. 'wochenplan'."},
                "beschreibung": {"type": "string",
                                 "description": "Eine Zeile: wann benutzen."},
                "inhalt":       {"type": "string",
                                 "description": "Die Anleitung."},
            },
            "required": ["name", "beschreibung", "inhalt"],
        },
    ),
    Werkzeug(
        name="edit_skill",
        erlaubnis=True,
        frage=_frage_skill_aendern,
        klein=None,
        gross=(
            "Schreibt die Anleitung eines bestehenden Skills neu; der Kopf "
            "bleibt, die alte Fassung als .bak. Wird bestaetigt. Vorher mit "
            "load_skill lesen."
        ),
        parameter={
            "type": "object",
            "properties": {
                "name":   {"type": "string", "description": "Name aus der Liste."},
                "inhalt": {"type": "string",
                           "description": "Die vollstaendige neue Anleitung."},
            },
            "required": ["name", "inhalt"],
        },
    ),
    # ── Frühere Gespräche ──
    # Phase 3 (2026-10-07): Sasha orientiert sich nach Thema, nicht nach
    # Datum — die Suche quer durch die Gespräche ist dafür die Bedingung
    # (core/chat_suche.py). Nur lesen, deshalb frei. Zwei Werkzeuge statt
    # eines mit Modus: jedes hat ein kleines, eindeutiges Schema.
    Werkzeug(
        name="search_chats",
        klein=None,
        gross=(
            "Sucht in allen frueheren Gespraechen mit Sasha (auch "
            "archivierten und dem alten Verlauf): was er oder du gesagt "
            "habt. Alle Woerter muessen vorkommen; nimm seine Begriffe. "
            "Treffer: Titel, id, Datum, Ausschnitt. Notizen: search_memory."
        ),
        parameter={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Suchwoerter."},
            },
            "required": ["query"],
        },
    ),
    Werkzeug(
        name="read_chat",
        klein=None,
        gross=(
            "Liest ein frueheres Gespraech nach (id aus search_chats): die "
            "letzten Nachrichten, mit query die um die Fundstelle."
        ),
        parameter={
            "type": "object",
            "properties": {
                "id":     {"type": "string", "description": "Gespraechs-id."},
                "query":  {"type": "string", "description": "Optional: Suchwoerter."},
                "anzahl": {"type": "integer",
                           "description": "Nachrichten, Standard 20, max 40."},
            },
            "required": ["id"],
        },
    ),
    # ── Ablage ──
    # Phase 5 (2026-10-07): Dokumente für Sasha (core/ablage.py), Claude-
    # Webs Artefakte. UNGEGATET, Entscheidung 2026-10-07: es wird nur in den
    # eigenen Ordner data/ablage/ geschrieben, nie überschrieben und nie
    # gelöscht (jede Änderung eine neue Fassung), nichts geht nach draußen.
    # Ein Ja/Nein vor jedem Dokument wäre wie bei write_note eine Zumutung —
    # und das Dokument erscheint ohnehin sofort als Zeile im Chat.
    Werkzeug(
        name="create_document",
        klein=None,
        gross=(
            "Legt ein Dokument in Sashas Ablage: Plan, Liste, Text, Code, "
            "Tabelle — was er behalten, lesen oder weiterverwenden will. Er "
            "sieht es sofort als Eintrag im Chat. Fuer Laengeres (ab ~15 "
            "Zeilen) oder zum Mitnehmen; Kurzes gehoert in die Antwort."
        ),
        parameter={
            "type": "object",
            "properties": {
                "titel":   {"type": "string", "description": "Kurzer Titel."},
                "inhalt":  {"type": "string", "description": "Der ganze Inhalt."},
                "art":     {"type": "string",
                            "enum": ["markdown", "text", "code", "csv"],
                            "description": "Standard: markdown."},
                "sprache": {"type": "string",
                            "description": "Nur bei code, z.B. 'python'."},
            },
            "required": ["titel", "inhalt"],
        },
    ),
    Werkzeug(
        name="read_document",
        klein=None,
        gross="Liest ein Dokument aus der Ablage (id steht im Verlauf).",
        parameter={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Dokument-id."},
            },
            "required": ["id"],
        },
    ),
    Werkzeug(
        name="update_document",
        klein=None,
        gross=(
            "Neue Fassung eines Dokuments der Ablage; die alte bleibt. Vorher "
            "mit read_document lesen, 'inhalt' ist der vollstaendige neue Text."
        ),
        parameter={
            "type": "object",
            "properties": {
                "id":     {"type": "string", "description": "Dokument-id."},
                "inhalt": {"type": "string", "description": "Der ganze neue Inhalt."},
            },
            "required": ["id", "inhalt"],
        },
    ),
    Werkzeug(
        name="save_from_sandbox",
        klein=None,
        gross=(
            "Legt eine Datei aus einem run_code-Lauf in Sashas Ablage (Text "
            "oder Bild). 'lauf' und 'datei' stehen im Ergebnis von run_code."
        ),
        parameter={
            "type": "object",
            "properties": {
                "lauf":  {"type": "string", "description": "Lauf-Kennung."},
                "datei": {"type": "string", "description": "Name in /arbeit."},
                "titel": {"type": "string", "description": "Titel in der Ablage."},
            },
            "required": ["lauf", "datei"],
        },
    ),
    # Hinweis: ASCII-Bilder laufen NICHT über ein Werkzeug. Messung
    # (scripts/bench_ascii.py, Baseline N=200) zeigte: als Tool feuerte die KI
    # bei impliziten Prompts nur ~3 % - und tippte den Aufruf oft als Text-
    # Marker [[zeige_ascii: name]] statt einen echten Tool-Call zu machen.
    # Stattdessen ein Inline-Marker im Antworttext (profil/klein.py,
    # _ASCII_MARKER_PROMPT; ki_antwort zieht ihn heraus).
]


# ── Nachschlagen ───────────────────────────────────────────────────────

_NACH_NAME = {w.name: w for w in WERKZEUGE}

# Deutsche Alt-Namen der klein-Schiene → kanonische. Abgeleitet, nicht
# getippt: welche Schiene ihr Werkzeug wie nennt, steht oben im Eintrag.
ALIASE = {w.klein_name: w.name for w in WERKZEUGE
          if w.klein_name and w.klein_name != w.name}


def kanonisch(name: str) -> str:
    """Einen Werkzeug-Namen auf das Vokabular des Kerns bringen.

    Idempotent und tolerant: ein kanonischer oder unbekannter Name kommt
    unverändert zurück (ein unbekannter fällt später als „Unbekanntes Tool"
    auf, nicht hier als KeyError)."""
    return ALIASE.get(name, name)


def eintrag(name: str) -> Werkzeug | None:
    """Der Eintrag zu einem Namen, egal in welcher Schreibweise."""
    return _NACH_NAME.get(kanonisch(name))


def auf_schiene(schiene: str) -> list:
    """Die Einträge, die diese Schiene anbietet, in Prompt-Reihenfolge."""
    if schiene not in SCHIENEN:
        raise ValueError(f"unbekannte Schiene: {schiene!r}")
    return [w for w in WERKZEUGE if w.beschreibung(schiene) is not None]


def schema(schiene: str) -> list:
    """Die Werkzeug-Liste dieser Schiene im OpenAI/Ollama-Schema — genau so,
    wie sie ans Modell geht (cloud._to_anthropic_tools übersetzt sie für
    Anthropic). Jede Liste bekommt eigene Kopien der Parameter, damit ein
    Weg, der darin herumschreibt, nicht die andere Schiene verändert."""
    return [{
        "type": "function",
        "function": {
            "name":        w.name_auf(schiene),
            "description": w.beschreibung(schiene),
            "parameters":  copy.deepcopy(w.parameter),
        },
    } for w in auf_schiene(schiene)]


def terminal(schiene: str) -> set:
    """Namen (wie die Schiene sie nennt) der terminalen Werkzeuge."""
    return {w.name_auf(schiene) for w in auf_schiene(schiene) if w.terminal}


def ausfuehrer(name: str):
    """Dekorator: meldet eine Funktion als Ausführer eines Werkzeugs an.

    Wirft bei einem Namen ohne Eintrag — ein Ausführer, den kein Modell je
    angeboten bekommt, wäre toter Code, der so tut, als gäbe es ein
    Werkzeug."""
    w = _NACH_NAME.get(name)
    if w is None:
        raise KeyError(f"Werkzeug {name!r} steht nicht im Register")
    if w.in_der_schleife:
        raise ValueError(f"{name!r} erledigt die Werkzeug-Schleife selbst")

    def anmelden(fn):
        w.ausfuehrer = fn
        return fn
    return anmelden


# ── Erlaubnis ──────────────────────────────────────────────────────────

def immer_bestaetigen() -> set:
    """Kanonische Namen der Werkzeuge, die IMMER bestätigt werden."""
    return {w.name for w in WERKZEUGE if w.erlaubnis is True}


def braucht_erlaubnis(name: str, args: dict | None = None) -> bool:
    """Muss dieser Aufruf vor der Ausführung bestätigt werden?

    Der Name kommt vom Modell und trägt die Schreibweise seiner Schiene —
    nachgeschlagen wird über den kanonischen, sonst rutschte ein Werkzeug
    unter seinem Alias am Gate vorbei. Eine Regel, die von den Argumenten
    abhängt, greift nur, wenn welche da sind."""
    w = eintrag(name)
    if w is None or w.erlaubnis is False:
        return False
    if w.erlaubnis is True:
        return True
    return bool(args) and bool(w.erlaubnis(args))


def frage(name: str, args: dict) -> str:
    """Die Ja/Nein-Frage an Sasha für diesen Aufruf."""
    w = eintrag(name)
    if w is not None and w.frage is not None:
        return w.frage(args)
    # Für ein Werkzeug ohne eigene Vorlage
    return f'Soll ich die Aktion "{kanonisch(name)}" wirklich ausführen?'
