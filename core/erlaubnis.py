# core/erlaubnis.py
#
# Das Erlaubnis-Gate: welche Werkzeuge vor der Ausführung bestätigt werden
# müssen, und die Ja/Nein-Frage, die Sasha dazu sieht.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 stand das
# in core/ai.py, und die Werkzeug-Schleife musste dafür den ganzen lokalen
# Weg importieren — einer der Knoten im Import-Kreis. Aufbau des KI-Kerns:
# memory/ki/kern_aufbau.md.

import gedaechtnis
import kalender
import profil


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


def braucht_erlaubnis(name: str, args: dict | None = None) -> bool:
    """Muss dieser Tool-Call vor der Ausführung bestätigt werden?

    Ueber diese Funktion gehen, nicht direkt gegen die Menge pruefen: der Name
    kommt vom Modell und traegt die Schreibweise seiner Schiene.

    write_note ist im Normalfall frei (mitschreiben ohne Rückfrage), aber
    NICHT, wenn es eine Kernakte trifft — Hausregeln, Steckbrief, Ziele
    (Sasha, 2026-10-06; gedaechtnis.schreibt_kernakte). Dafür braucht es die
    Argumente.
    """
    kanon = profil.kanonisch(name)
    if kanon in PERMISSION_REQUIRED_TOOLS:
        return True
    if kanon == "write_note" and args:
        return gedaechtnis.schreibt_kernakte(args.get("name")) is not None
    return False


def frage(name: str, args: dict) -> str:
    """
    Baut die menschenlesbare Ja/Nein-Frage für ein gegatetes Tool aus den
    Call-Argumenten (wird Sasha im Dialog gezeigt + vorgelesen). Pro Tool
    eine eigene Vorlage; generischer Fallback falls mal ein Tool ohne
    Vorlage in PERMISSION_REQUIRED_TOOLS landet.
    """
    name = profil.kanonisch(name)
    label = (args.get("label") or "").strip() or "diesen Eintrag"
    if name == "write_note":
        akte = gedaechtnis.schreibt_kernakte(args.get("name")) or "die Notiz"
        text = " ".join(str(args.get("text") or "").split())
        if len(text) > 200:
            text = text[:199] + "…"
        return f'Soll ich in {akte} schreiben: "{text}"?'
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
