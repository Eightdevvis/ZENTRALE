# core/werkzeug_gruppen.py
#
# Welche Werkzeuge zusammengehören und an welchen Wörtern man sie erkennt —
# EINE Tabelle für zwei Leser (2026-10-14, Werkzeug-Suche,
# memory/ki/werkzeug_suche.md):
#
#   - das qwen-Profil (core/profil/modelle/qwen.py): seine Vorauswahl je
#     Gespräch (VORAUSWAHL, wörtlich aus qwen._GRUPPEN hierher gezogen —
#     gemessen im Prüfstand, Runde 9; nicht umformulieren, ohne qwen neu zu
#     messen);
#   - die Werkzeug-Suche (core/werkzeug_suche.py): Schlagworte je Gruppe im
#     Index, und „ein Treffer bringt seine ganze Gruppe".
#
# Und die Register-Felder `laden` und `gruppe` (core/werkzeug_eintrag.py):
# welche Werkzeuge auf gross IMMER geladen sind (IMMER) und zu welcher
# Gruppe jedes zurückgestellte gehört (GRUPPE_VON). Das Register setzt beide
# beim Import aus dieser Tabelle (werkzeug_register.laden_setzen) — eine
# Stelle zum Nachlesen statt eines Felds in fünf Dateien.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Importiert nichts aus
# dem Kern: Register, qwen und Suche lesen hier, nicht umgekehrt.

import re as _re


# ── Immer geladen (gross) ──────────────────────────────────────────────
# Höchstens fünf (Sasha, 2026-10-14, nach Anthropics Doku: „keep the 3–5
# tools Claude needs most" nicht zurückgestellt). Pflicht: antwort (die
# Antwort selbst) und search_tools (ohne sie findet die KI nichts). Dazu
# die drei meistgenutzten laut Werkzeug-Spur der gespeicherten Gespräche
# (Stand 14.10.: von 75 Antworten nutzten web_search 13, fetch_url 6,
# read_calendar 5, alles andere ≤ 3). Alles andere ist „bedarf": das
# Modell sieht es erst nach search_tools (Anthropic: defer_loading;
# OpenAI: angehängt) — auch Kalender-Schreiben, Notizen, load_skill.
IMMER = (
    "antwort", "search_tools", "web_search", "fetch_url", "read_calendar",
)


# ── Die Vorauswahl des qwen-Profils (Runde 9) ──────────────────────────
# Wörtlich aus core/profil/modelle/qwen.py (_GRUPPEN), dort der Grund. Ein
# Werkzeug kommt dazu, sobald Sasha im Gespräch ein passendes Wort benutzt.
# Ein Werkzeug in keiner dieser Gruppen ist für qwen immer dabei.
VORAUSWAHL = {
    "browser": (r"lsf|portal|browser|klick|webseite|website|seite|http|www\.|"
                r"vorlesungsverzeichnis|login|online|einloggen",
                ("browser_open", "browser_click", "browser_type", "browser_find",
                 "browser_read", "browser_back", "browser_close", "browser_screenshot")),
    "dateien": (r"datei|ordner|ablage|\bzip|skill|code|python|rechne|sandbox|"
                r"skript|script|csv|tabelle|papierkorb|such",
                ("read_file", "list_files", "find_files", "search_files", "unzip",
                 "import_skill", "fetch_document", "save_from_sandbox", "run_code")),
    "dokumente": (r"pdf|word|docx|dokument|brief|bewerbung|lebenslauf|schreiben|"
                  r"anschreiben|formular",
                  ("read_pdf", "create_pdf", "combine_pdf", "read_docx", "create_docx",
                   "edit_docx", "create_document", "read_document", "update_document",
                   "fetch_document",
                   # 2026-10-11: ersetzen/Papierkorb der Ablage.
                   "replace_document", "trash_document", "restore_document")),
    # 2026-10-11, Skill excel: Tabellen erst auf ein passendes Wort.
    "tabellen": (r"excel|xlsx|csv|tabelle|kosten|budget|summ|formel|tracke|ausgab|"
                 r"rechne|zelle|spalte",
                 ("read_xlsx", "create_xlsx", "edit_xlsx")),
    "post": (r"mail|post|nachricht|news|neuigkeit|welt|schlagzeil|zeitung",
             ("read_mail", "read_news")),
    "messreihen": (r"mess|reihe|gewicht|kurve|tracke|protokollier|wert",
                   ("create_series", "log_series")),
    "skills": (r"skill|anleitung|arbeitsweise|vorgehen",
               ("propose_skill", "edit_skill")),
    # Tagesrhythmus, Gruppe, fest/vielleicht (2026-10-10, erzeugte
    # Kalender-Werkzeuge): selten gebraucht, also erst auf ein passendes Wort.
    # 2026-10-22: „uncommitted" dazu — Sashas Wort (Gespräch 20261022-111358),
    # vorher kam set_calendar_layer darauf nicht mit.
    "rhythmus": (r"schlaf|bett|aufsteh|aufwach|rhythmus|phase|hungrig|essen|"
                 r"mittag|fokus|runterkommen",
                 ("set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase")),
    "gruppe": (r"gruppe|kategorie|block|\buni\b|arbeit|schicht|vielleicht|"
               r"unverbindlich|uncommitted|\bfest\b|zugesagt|monatsansicht",
               ("set_calendar_group", "set_calendar_layer")),
    # 2026-10-11: Aussehen eines Eintrags — selten, also nur auf ein passendes Wort.
    "stil": (r"farb|einfärb|rahmen|muster|aussehen|stil|markier|hervorheb|bunt",
             ("set_calendar_style",)),
    "quelle": (r"liste|todo|to-do|projekt|aufgabe|blocke|block",
               ("read_calendar_sources", "set_calendar_source", "clear_calendar_source")),
}
IN_VORAUSWAHL = {n for _, namen in VORAUSWAHL.values() for n in namen}


def vorab(verlauf, index=None) -> set:
    """Welche Werkzeuge das Gespräch nach seinen Wörtern braucht — die
    Schnittstelle für einen späteren Klassifikator (profil.vorab(verlauf,
    index) -> namen). Erste Umsetzung: die Schlagwort-Logik des qwen-Profils
    (alle Nachrichten Sashas zählen, die Menge wächst im Gespräch nur).
    `index` (core/werkzeug_suche) bleibt bis dahin ungenutzt."""
    text = " ".join(str(m.get("content") or "") for m in verlauf or ()
                    if m.get("role") == "user").casefold()
    return {n for muster, namen in VORAUSWAHL.values()
            if _re.search(muster, text) for n in namen}


# ── Gruppen der Suche ──────────────────────────────────────────────────
# Jedes zurückgestellte Werkzeug gehört zu GENAU einer Gruppe; ein Treffer
# der Suche schaltet die ganze Gruppe frei (wer browser_open braucht,
# braucht gleich auch browser_click). Die Gruppen hier sind feiner als die
# Vorauswahl (pdf und word getrennt, sandbox eigen), damit ein Treffer
# nicht zwölf Werkzeuge auf einmal lädt.
GRUPPEN = {
    "browser": ("browser_open", "browser_click", "browser_type", "browser_find",
                "browser_read", "browser_back", "browser_close", "browser_screenshot"),
    "dateien": ("read_file", "list_files", "find_files", "search_files", "unzip"),
    "sandbox": ("run_code", "save_from_sandbox"),
    "ablage": ("create_document", "read_document", "update_document", "fetch_document",
               "replace_document", "trash_document", "restore_document"),
    "pdf": ("read_pdf", "create_pdf", "combine_pdf"),
    "word": ("read_docx", "create_docx", "edit_docx"),
    "tabellen": ("read_xlsx", "create_xlsx", "edit_xlsx"),
    "post": ("read_mail", "read_news"),
    "messreihen": ("create_series", "log_series", "read_series"),
    "skills": ("load_skill", "propose_skill", "edit_skill", "import_skill"),
    "gedaechtnis": ("read_note", "write_note", "search_memory", "rewrite_note",
                    "archive_note"),
    "gespraeche": ("search_chats", "read_chat"),
    "rueckfrage": ("ask_choice",),
    "fehler": ("explain_error",),
    "projekte": ("read_project_file",),
    "kalender": ("add_calendar_entry", "edit_calendar_entry", "delete_calendar_entry",
                 "read_calendar_warnings", "read_time"),
    "routinen": ("add_calendar_routine", "edit_calendar_routine", "add_calendar_pause"),
    "rhythmus": ("set_calendar_phase", "edit_calendar_phase", "delete_calendar_phase"),
    "gruppe": ("set_calendar_group", "set_calendar_layer"),
    "stil": ("set_calendar_style",),
    "quelle": ("read_calendar_sources", "set_calendar_source", "clear_calendar_source"),
}
GRUPPE_VON = {n: g for g, namen in GRUPPEN.items() for n in namen}

# Schlagworte je Gruppe für den Index — Wörter, die Sasha sagt, nicht die,
# die in den Beschreibungen stehen. Für Gruppen mit gleichem Namen in der
# Vorauswahl kommen deren Muster-Wörter dazu (schlagworte()).
SCHLAGWORTE = {
    "browser": "lsf hochschulportal uni-portal anmelden einloggen klicken formular webseite "
               "seite bedienen screenshot",
    "dateien": "datei dateien ordner suchen finden zip entpacken auspacken lesen",
    "sandbox": "programm python code rechnen ausführen skript sandbox",
    "ablage": "dokument ablage speichern ersetzen papierkorb wiederherstellen notizdokument "
              "herunterladen",
    "pdf": "pdf zusammenfügen seiten formular",
    "word": "word docx brief bewerbung lebenslauf anschreiben",
    "tabellen": "excel xlsx tabelle tabellenkalkulation csv spalte zeile formel summe budget",
    "post": "mail e-mail email post postfach nachrichten news schlagzeilen zeitung",
    "messreihen": "messen messreihe messwert kurve gewicht schlaf protokollieren tracken",
    "skills": "skill skills anleitung laden arbeitsweise vorgehen übernehmen",
    "gedaechtnis": "gedächtnis notiz notizen merken erinnern tagebuch hausregeln steckbrief "
                   "ziele dossier umschreiben archivieren aufräumen",
    "gespraeche": "gespräch gespräche chat früher damals verlauf nachlesen",
    "rueckfrage": "rückfrage frage knopf knöpfe auswahl wählen nachhaken",
    "fehler": "fehler fehlercode code erklären",
    "projekte": "projekt wissen wissensdatei",
    "kalender": "termin termine eintragen ändern verschieben löschen absagen kalender "
                "uhrzeit uhr spät datum heute warnung kollision konflikt",
    "routinen": "routine serie wöchentlich regelmäßig jeden verschieben pause ausfallen "
                "ferien wiederholung",
    "rhythmus": "schlaf aufstehen tagesrhythmus phase essen fokus",
    "gruppe": "kategorie gruppe fest vielleicht unverbindlich uncommitted zugesagt",
    "stil": "farbe einfärben stil markieren aussehen",
    "quelle": "liste todo aufgabe quelle blocken",
}


def schlagworte(gruppe: str) -> str:
    """Die Schlagworte einer Gruppe als Text: eigene plus die Wörter aus dem
    Muster der gleichnamigen Vorauswahl-Gruppe (Regex-Zeichen entfernt)."""
    teile = [SCHLAGWORTE.get(gruppe, "")]
    muster = VORAUSWAHL.get(gruppe, ("", ()))[0]
    if muster:
        teile.append(" ".join(_re.sub(r"\\b|\\\.|\\", " ", muster).split("|")))
    return " ".join(t for t in teile if t)


# ── Felder laden/gruppe im Register ────────────────────────────────────

def laden_setzen(werkzeuge) -> None:
    """laden/gruppe jedes Eintrags aus IMMER und GRUPPE_VON (ohne Gruppe:
    der eigene Name). Das Register ruft es beim Import und nach jedem
    Umschalten der erzeugten Werkzeuge."""
    for w in werkzeuge:
        if w.name in IMMER:
            w.laden, w.gruppe = "immer", None
        else:
            w.laden, w.gruppe = "bedarf", GRUPPE_VON.get(w.name, w.name)


# ── Der Schalter ───────────────────────────────────────────────────────
# Hier unten (Schicht 1), damit auch skills und anhang (Schicht 2) fragen
# können, ohne die Suche (Schicht 3) zu kennen.
SCHALTER = "werkzeug_suche"


def schalter_an(name) -> bool:
    """Ist die Einstellung eines Register-Felds `schalter` an? Kein Name =
    immer; sonst Standard aus."""
    if not name:
        return True
    try:
        import ai_config
        wert = ai_config.setting(name, "aus")
    except Exception:
        return False
    return str(wert or "").strip().lower() in ("an", "1", "true", "ja", "on")


def suche_an() -> bool:
    """Werkzeug-Suche eingeschaltet? (Einstellung werkzeug_suche, Standard aus.)"""
    return schalter_an(SCHALTER)


def suche_aus_spur(spur) -> list:
    """Werkzeug-Spur einer gespeicherten Antwort → [{anfrage, namen}] der
    Suchen darin, roh (welche Namen es noch gibt, prüft core/werkzeug_suche
    beim Einsetzen)."""
    raus = []
    for e in spur or ():
        f = e.get("freigeschaltet") if isinstance(e, dict) else None
        if isinstance(f, dict) and f.get("namen"):
            raus.append({"anfrage": str(f.get("anfrage") or ""),
                         "namen": [str(n) for n in f["namen"]]})
    return raus
