# core/fehlercodes.py
#
# Die eine Tabelle aller Fehlercodes der KI-Werkzeuge: Code → (Ursache, was
# zu tun ist). Ein schreibendes Werkzeug kennt nur zwei Ausgänge — ERLEDIGT
# oder ABGEBROCHEN (nichts geändert) —, und jeder Abbruch trägt einen Code
# von hier. Die KI kann ihn mit explain_error nachschlagen.
#
# 2026-10-09, Sasha: „unsere tools sollen auch nich ‚teilweise' oder so nen
# bs erlauben weil das heißt dass DAS TOOL das problem ist, nicht die ki,
# das programm macht etwas richtig ODER bricht KONTROLLIERT KOMPLETT AB mit
# genauem fehlercode!" Vorher gab es den Status „teilweise" und Fehlertexte
# in freier Form; was davon ein Tippfehler der KI war und was eine Lücke im
# Werkzeug, stand nirgends.
#
# Vorsilben: W allgemein, K Kalender (K-<CODE> des Kalender-Kerns kommen
# gleichnamig dazu), N Notizen/Gedächtnis, A Ablage, D Download, M
# Messreihen, S Skills, P PDF/Word, I Internet (lesend), B Browser, Z Sashas
# Nutzerordner (~/Zentrale: unzip, remove_input; read_file und fetch_document auf gross).
# tests/test_fehlercodes.py hält die
# Tabelle und den Code deckungsgleich.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): reine Tabelle.

CODES = {
    # ── allgemein ──
    "W-AUSNAHME": (
        "Das Werkzeug ist an einem Programmfehler gescheitert, bevor es fertig war.",
        "Nicht in derselben Form wiederholen. Sasha sagen, dass es an ZENTRALE lag, nicht an ihm."),
    "W-NICHT-GESPEICHERT": (
        "Nach dem Schreiben nachgelesen: es stand nicht (oder nicht so) da wie verlangt. "
        "Der alte Stand ist wiederhergestellt.",
        "Neu lesen, was jetzt dasteht. Nicht blind wiederholen; Sasha sagen, dass es nicht ging."),
    # ── Kalender (Werkzeug) ──
    "K-PFLICHTFELD": (
        "Eine nötige Angabe fehlt (Titel, Tag, Regel oder Kennung).",
        "Die fehlende Angabe von Sasha holen oder aus read_calendar nehmen."),
    "K-MEHRDEUTIG": (
        "Der Name trifft mehrere Einträge; geändert wird nur genau einer.",
        "Sasha fragen, welcher gemeint ist, dann mit dessen Kennung aufrufen."),
    "K-NICHT-GEFUNDEN": (
        "Kein Eintrag mit diesem Namen (an diesem Tag).",
        "read_calendar mit suche aufrufen und die Kennung nehmen."),
    "K-PAUSE-KEINE-ROUTINE": (
        "Eine Pause wirkt nur auf eine Routine mit GENAU diesem Titel — es gibt keine.",
        "Die Routine per read_calendar suchen und die Pause mit ihrer Kennung eintragen."),
    "K-NICHTS-ZU-AENDERN": (
        "Der Aufruf nennt kein Feld, das sich ändern soll.",
        "Angeben, was neu ist (time, ende, ort, neuer_titel, …)."),
    "K-AKTION-UNGUELTIG": (
        "aktion muss 'aendern' oder 'loeschen' sein.",
        "Mit einer gültigen aktion erneut aufrufen."),
    "K-EBENE-UNBEKANNT": (
        "Diese Kalender-Ebene gibt es nicht.",
        "Ohne layer aufrufen (Standard: termine)."),
    "K-SPANNE-UHRZEIT": (
        "Uhrzeiten einzelner Tage eines mehrtägigen Termins ändert das Werkzeug nicht.",
        "Sasha sagen, dass das in der Kalender-Ansicht geht."),
    # ── Kalender-Kern (core/kalender_kennung.py, gleichnamig mit K- davor) ──
    "K-KENNUNG-UNBEKANNT": (
        "Diese Kennung gibt es nicht (mehr) — der Eintrag wurde vielleicht geändert oder gelöscht.",
        "read_calendar neu aufrufen und die aktuelle Kennung nehmen."),
    "K-FALSCHE-ART": (
        "Die Kennung gehört zu einer anderen Art Eintrag (Routine statt Termin oder umgekehrt).",
        "Das passende Werkzeug nehmen: edit_calendar_routine für Routinen, "
        "edit_calendar_entry/delete_calendar_entry für Termine."),
    "K-ZEIT-UNGUELTIG": (
        "Eine Uhrzeit ist nicht im Format HH:MM (24 h).",
        "Als HH:MM angeben, z. B. 18:10."),
    "K-DATUM-UNGUELTIG": (
        "Ein Datum ist nicht im Format YYYY-MM-DD.",
        "Als YYYY-MM-DD angeben, z. B. 2026-10-12."),
    "K-ENDE-VOR-BEGINN": (
        "Das Ende liegt nicht nach dem Beginn.",
        "Beginn und Ende zusammen angeben; bei Unklarheit Sasha fragen."),
    "K-ENDE-OHNE-BEGINN": (
        "Ein Ende ohne Beginn geht nicht.",
        "time mit angeben."),
    "K-RRULE-UNGUELTIG": (
        "Die Wiederholungsregel (rrule) ist ungültig.",
        "Eine RFC-5545-Regel angeben, z. B. FREQ=WEEKLY;BYDAY=MO."),
    # 2026-10-09: Serien nur mit Zeitraum (Sashas Uni-Fächer liefen „für immer").
    "K-ZEITRAUM-FEHLT": (
        "Eine Routine braucht ihren Zeitraum: von (erster Tag) und bis (letzter Tag).",
        "Sasha fragen, von wann bis wann es läuft (z. B. Semesteranfang und -ende). "
        "Nie ‚für immer' annehmen und kein Datum erfinden."),
    "K-RRULE-MIT-ENDE": (
        "Die Regel (rrule) enthält UNTIL oder COUNT; das Ende der Serie geht nur über 'bis'.",
        "UNTIL/COUNT aus der rrule nehmen und den letzten Tag als bis angeben."),
    "K-KEIN-VORKOMMEN": (
        "Die Routine findet an diesem Tag gar nicht statt.",
        "Einen Tag nehmen, an dem sie stattfindet (read_calendar)."),
    "K-TITEL-LEER": (
        "Der Titel ist leer.",
        "Einen Titel angeben."),
    "K-SPANNE-VERDREHT": (
        "Das Ende einer Spanne (bis) liegt vor ihrem Anfang.",
        "von/bis in der richtigen Reihenfolge angeben."),
    "K-TAG-AUSSERHALB": (
        "Der Tag liegt außerhalb des mehrtägigen Termins.",
        "Einen Tag innerhalb der Spanne nehmen."),
    "K-UNBEKANNTES-FELD": (
        "Ein Feld, das der Kalender nicht kennt.",
        "Nur die Felder des Werkzeugs benutzen."),
    # ── Notizen / Gedächtnis ──
    "N-NAME-LEER": (
        "Kein Name: wohin soll es geschrieben werden?",
        "name angeben (Dossier, hausregeln, tagebuch …)."),
    "N-TEXT-LEER": (
        "Kein Text zum Schreiben.",
        "text bzw. content angeben."),
    "N-ABGELEHNT": (
        "Das Gedächtnis hat den Schreibwunsch abgelehnt (Grund im Ergebnis, z. B. Kernakte).",
        "Den Grund lesen; bei Kernakten Sasha fragen, statt es anders zu versuchen."),
    # ── Ablage ──
    "A-ABGELEHNT": (
        "Die Ablage hat das Dokument abgelehnt (Grund im Ergebnis: leer, zu groß, falsche Art).",
        "Den Grund beheben (kürzer, anderer Titel, andere Art)."),
    "A-DOK-UNBEKANNT": (
        "Kein Dokument mit dieser id in der Ablage.",
        "Die id aus dem Chat oder der Ablage-Liste nehmen."),
    "A-LAUF-FREMD": (
        "Dieser Programm-Lauf gehört nicht zu diesem Gespräch.",
        "Nur Läufe aus diesem Gespräch ablegen (run_code hier)."),
    "A-DATEI-NICHT-LESBAR": (
        "Die Datei aus dem Programm-Lauf fehlt, ist zu groß oder liegt außerhalb des Arbeitsordners.",
        "Den Dateinamen aus dem Lauf-Ergebnis nehmen."),
    "A-KEIN-TEXT-ODER-BILD": (
        "Die Datei ist weder Text noch ein Bild.",
        "Als Text (csv, md, txt) oder Bild (png, jpg) schreiben lassen."),
    # ── Download ──
    "D-ABGELEHNT": (
        "Das Dokument ließ sich nicht holen oder nicht ablegen (Grund im Ergebnis).",
        "Den Grund lesen; eine andere Adresse oder Sasha fragen."),
    # ── Messreihen ──
    "M-NAME-LEER": ("Kein Name der Messreihe.", "name bzw. series angeben."),
    "M-GIBT-ES-SCHON": (
        "Eine Messreihe mit diesem Namen gibt es schon.",
        "Werte mit log_series in die bestehende eintragen."),
    "M-UNBEKANNT": (
        "Keine Messreihe mit diesem Namen. Neue legt Sasha (oder create_series nach seinem Ja) an.",
        "Einen vorhandenen Namen nehmen (Liste im Ergebnis)."),
    "M-ABGELEHNT": (
        "Die Messreihe hat den Wert oder das Anlegen abgelehnt (Grund im Ergebnis).",
        "Wert im passenden Format angeben (Zahl, Uhrzeit …)."),
    # ── Skills ──
    "S-ABGELEHNT": (
        "Die Anleitung wurde nicht gespeichert (Grund im Ergebnis: Name, Format, schreibgeschützt).",
        "Den Grund beheben; eine mitgelieferte Anleitung nicht überschreiben."),
    # Skills übernehmen (import_skill, 2026-10-09, core/skill_import.py)
    "S-QUELLE-FEHLT": (
        "Die genannte Zip-Datei bzw. der Ordner existiert nicht in Input/ (oder kein Pfad angegeben).",
        "Mit find_files nach dem Namen suchen und den gefundenen Pfad nehmen."),
    "S-QUELLE-AUSSERHALB": (
        "Der Pfad liegt nicht in Sashas Input/-Ordner; übernommen wird nur von dort.",
        "Sasha bitten, die Zip bzw. den Ordner in seinen Input/-Ordner zu legen."),
    "S-QUELLE-GESPERRT": (
        "Die Datei ist versteckt oder sieht nach einem Schlüssel aus.",
        "Nicht umgehen. Sasha fragen."),
    "S-ZIP-KAPUTT": (
        "Die Datei ist keine lesbare Zip (kaputt, verschlüsselt, oder gar keine Zip).",
        "Sasha sagen; er soll die Zip neu herunterladen oder den ausgepackten Ordner nennen."),
    "S-UNSICHER": (
        "Die Zip oder der Ordner enthält einen Pfad nach draußen (absolut oder mit ..) "
        "oder einen Verweis (Symlink). Es wurde nichts ausgepackt.",
        "Nicht umgehen. Sasha sagen, dass die Datei so nicht übernommen wird."),
    "S-ZU-GROSS": (
        "Zu groß: entpackt über 20 MB oder über 500 Dateien.",
        "Sasha sagen; ein Skill ist eine Anleitung, kein Archiv."),
    "S-KEIN-SKILL": (
        "Darin liegt keine SKILL.md — weder in der Wurzel, noch in skills/<name>/, noch in <name>/.",
        "Sasha fragen, ob es die richtige Datei ist (mit find_files nach Alternativen suchen)."),
    "S-SKILL-UNGUELTIG": (
        "Eine SKILL.md erfüllt Claudes Format nicht (Name oder description im Kopf fehlt/"
        "ungültig, Anleitung leer, Name doppelt, plugin.json kaputt).",
        "Den Grund im Ergebnis Sasha nennen; selbst nichts umschreiben."),
    "S-SKILL-GIBT-ES": (
        "Einen Skill mit diesem Namen gibt es schon; überschrieben wird nie. Nichts übernommen.",
        "Sasha fragen, was er will (den alten mit load_skill zeigen). Nicht selbst umbenennen."),
    # ── Nutzerordner: unzip, remove_input (2026-10-09, core/input_dateien.py) ──
    "Z-QUELLE-FEHLT": (
        "Die genannte Datei gibt es nicht in Input/ (oder kein Name angegeben).",
        "Mit find_files nach dem Namen suchen und den gefundenen Namen nehmen."),
    "Z-QUELLE-AUSSERHALB": (
        "Der Pfad liegt nicht in Sashas Input/-Ordner; nur von dort wird ausgepackt "
        "bzw. weggeräumt.",
        "Sasha bitten, die Datei in seinen Input/-Ordner zu legen."),
    # read_file und fetch_document auf gross (2026-10-09, core/context.py):
    # gelesen wird nur noch in Input/ und Output/, nicht mehr im Projektbaum.
    "Z-AUSSERHALB": (
        "Der Pfad liegt nicht in Input/ oder Output/ des Nutzerordners; Dateien "
        "liest du nur dort (und Anhänge/Dokumente aus der Ablage per id).",
        "Nicht umgehen. Darum bitten, die Datei in Input/ zu legen oder im Chat anzuhängen."),
    "Z-QUELLE-GESPERRT": (
        "Die Datei ist versteckt oder sieht nach einem Schlüssel aus.",
        "Nicht umgehen. Sasha fragen."),
    "Z-KEINE-ZIP": (
        "Die Datei ist keine Zip (oder ein Ordner).",
        "Den Namen prüfen (find_files); andere Dateien mit read_file/read_pdf lesen."),
    "Z-ZIP-KAPUTT": (
        "Die Zip ist kaputt oder verschlüsselt. Es wurde nichts ausgepackt.",
        "Sasha sagen; er soll sie neu herunterladen."),
    "Z-UNSICHER": (
        "Die Zip enthält einen Pfad nach draußen (absolut oder mit ..) oder einen "
        "Verweis (Symlink). Es wurde nichts ausgepackt.",
        "Nicht umgehen. Sasha sagen, dass die Zip so nicht ausgepackt wird."),
    "Z-ZU-GROSS": (
        "Zu groß: entpackt über 20 MB oder über 500 Dateien. Nichts ausgepackt.",
        "Sasha sagen; mit unzip ansehen=true lässt sich der Inhalt trotzdem zeigen."),
    "Z-LEER": (
        "In der Zip liegt nichts, was ausgepackt würde (leer, oder nur Verstecktes/"
        "Ballast/Schlüssel).",
        "Sasha sagen, was drin ist (unzip ansehen=true)."),
    "Z-ZIEL-GIBT-ES": (
        "Den Ordner Output/<name>/ gibt es schon; überschrieben wird nie. Nichts ausgepackt.",
        "Sasha fragen: den vorhandenen Ordner ansehen oder erst wegräumen lassen."),
    "Z-NICHT-DIREKT": (
        "Die Datei liegt in einem Unterordner von Input/; weggeräumt wird nur, was "
        "direkt in Input/ liegt.",
        "Den obersten Ordner in Input/ nennen — nach Sashas Ja."),
    "Z-VERSCHIEBEN": (
        "Das Verschieben in den Papierkorb ging nicht (Grund im Ergebnis). Nichts verschoben.",
        "Sasha sagen; nicht wiederholen."),
    # ── Internet (lesend) ──
    "I-KEIN-TEXT": (
        "Die Seite war erreichbar, aber ohne lesbaren Text (Skript-Seite, Bild, leer).",
        "Eine andere Quelle suchen; nicht so tun, als stünde dort etwas."),
    # ── Browser (core/ki_browser.py, 2026-10-09) ──
    "B-NICHT-EINGERICHTET": (
        "Der Browser ist auf diesem Rechner nicht eingerichtet (Paket oder Chromium fehlt, "
        "oder Chromium startet nicht — Grund im Ergebnis).",
        "Sasha sagen, dass der Browser hier fehlt. Solange fetch_url nehmen."),
    "B-ADRESSE": (
        "Die Adresse taugt nicht: leer, kaputt oder nicht http/https.",
        "Eine vollständige http(s)-Adresse angeben."),
    "B-ADRESSE-GESPERRT": (
        "Die Adresse liegt im eigenen Rechner oder Netz (localhost, 192.168.…) — der Browser "
        "darf dort nicht hin.",
        "Nicht umgehen. Sasha sagen, falls er es so wollte."),
    "B-ANDERE-SEITE": (
        "Klick oder Weiterleitung führt zu einem anderen Host, für den Sasha in diesem "
        "Gespräch noch nicht Ja gesagt hat. Nichts geladen.",
        "browser_open mit der genannten Adresse aufrufen — Sasha wird gefragt."),
    "B-KEINE-SEITE": (
        "In diesem Gespräch ist keine Seite offen (nie geöffnet, geschlossen, oder nach "
        "10 Minuten ohne Benutzung zu).",
        "Erst browser_open."),
    "B-NR-UNBEKANNT": (
        "Diese Nummer steht nicht in der Liste der zuletzt gelesenen Seite, oder die Seite "
        "hat sich seitdem verändert.",
        "Die Nummer aus dem letzten Ergebnis nehmen, oder browser_find."),
    "B-KEIN-FELD": (
        "Das Element ist kein Eingabefeld (oder nimmt diesen Text nicht an).",
        "Ein Feld oder eine Auswahl aus der Liste nehmen; Knöpfe und Links mit browser_click."),
    "B-PASSWORT": (
        "In Passwortfelder tippt die KI nicht — das Passwort stünde sonst in Verlauf und Log.",
        "Sasha sagen, dass Anmelden über den Browser der KI nicht geht."),
    "B-ZEIT": (
        "Der Schritt hat länger als 20 Sekunden gedauert.",
        "Einmal neu versuchen; sonst Sasha sagen, dass die Seite nicht antwortet."),
    "B-LADEN": (
        "Die Seite ließ sich nicht laden (Grund im Ergebnis: Netz, Name unbekannt, …).",
        "Adresse prüfen; nicht so tun, als stünde dort etwas."),
    "B-DOWNLOAD": (
        "Der Link lädt eine Datei herunter — Downloads sind im Browser aus.",
        "Für PDFs und Dokumente fetch_document mit der Adresse nehmen."),
    "B-KEIN-ZURUECK": ("Es gibt keine vorige Seite.", "browser_open mit einer Adresse."),
    # ── PDF / Word ──
    "P-QUELLE-FEHLT": (
        "Keine Quelle angegeben, oder es ist weder eine Ablage-id noch eine Datei.",
        "Ablage-id oder Dateipfad angeben."),
    "P-QUELLE-AUSSERHALB": (
        "Der Dateipfad liegt nicht in Input/ oder Output/ des Nutzerordners; nur dort "
        "(oder per Ablage-id) wird gelesen.",
        "Darum bitten, die Datei in Input/ zu legen oder im Chat anzuhängen."),
    "P-QUELLE-GESPERRT": (
        "Diese Datei darf die KI nicht lesen.",
        "Sasha bitten, die Datei anzuhängen."),
    "P-FALSCHE-ART": (
        "Die Quelle ist keine Datei dieser Art (z. B. kein PDF).",
        "Das passende Werkzeug nehmen (read_document, read_docx, read_pdf)."),
    "P-ORIGINAL-FEHLT": (
        "Der Anhang liegt nur als Text vor, das Original fehlt.",
        "Sasha bitten, die Datei neu anzuhängen."),
    "P-ZU-GROSS": ("Die Datei ist zu groß (höchstens 30 MB).", "Sasha sagen."),
    "P-DATEI-KAPUTT": (
        "Die Datei ließ sich nicht lesen oder erzeugen (Grund im Ergebnis).",
        "Sasha sagen; bei einer erzeugten Datei den Inhalt vereinfachen."),
    "P-KEIN-TEXT": (
        "Auf diesen Seiten ist kein Text — vermutlich gescannt (nur Bilder).",
        "Sasha sagen, dass Texterkennung fehlt."),
    "P-ZEICHEN": (
        "Einige Zeichen kann die PDF-Schrift nicht darstellen; es wurde nichts angelegt.",
        "Die Zeichen ersetzen oder weglassen (Liste im Ergebnis), oder create_docx nehmen."),
    "P-TEILE-FEHLEN": ("Keine Teile zum Zusammenfügen angegeben.", "teile angeben."),
    "P-ZU-VIELE-TEILE": ("Zu viele Teile (höchstens 30).", "In mehreren Schritten zusammenfügen."),
    "P-ERSETZEN-FEHLT": (
        "Ein zu ersetzender Text kommt in der Datei nicht vor; es wurde keine Kopie angelegt.",
        "Mit read_docx nachsehen, wie es genau geschrieben ist."),
    "P-ERSETZEN-GETEILT": (
        "Ein Treffer geht über einen Tab oder Zeilenumbruch und ließe sich nicht ersetzen; "
        "es wurde keine Kopie angelegt.",
        "Kürzeren Text ohne Umbruch ersetzen."),
    "P-NICHTS-ZU-AENDERN": (
        "Weder ersetzen noch anhängen angegeben.",
        "Angeben, was sich ändern soll."),
    "P-ABGELEHNT": (
        "Die Ablage hat die neue Datei abgelehnt (Grund im Ergebnis).",
        "Den Grund beheben."),
}


def bekannt(code: str) -> bool:
    return str(code or "").strip().upper() in CODES


def erklaeren(code: str) -> str:
    """Text für explain_error."""
    c = str(code or "").strip().upper()
    if c.startswith("FEHLER "):
        c = c[7:].strip()
    if c not in CODES:
        aehnlich = [k for k in CODES if c and (c in k or k in c)]
        da = ", ".join(aehnlich[:6]) if aehnlich else "keiner"
        return f"Unbekannter Fehlercode {c!r}. Ähnliche: {da}."
    ursache, tun = CODES[c]
    return f"{c}\nUrsache: {ursache}\nWas tun: {tun}"
