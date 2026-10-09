# core/werkzeug_pdf_word.py
#
# Die Einträge der Werkzeuge für PDF und Word (Skills pdf und word) und ihre
# Fragen an Sasha. werkzeug_register hängt EINTRAEGE hinten an seine Liste;
# ausgeführt wird in core/ki_pdf_word.py.
#
# 2026-10-08 (memory/ki/pdf_word.md). Warum Werkzeuge im Register und nicht
# Skripte in der Sandbox (run_code), wie Claude es mit seinen pdf/docx-Skills
# macht: die Sandbox hat weder pypdf noch Zugriff auf die Ablage oder auf
# Sashas Dateien (absichtlich, Phase 7), jeder Lauf wird gefragt, und
# Ergebnisse kämen nur über das gefragte save_from_sandbox in die Ablage.
# Hier liest die KI frei und fragt nur, bevor eine neue Datei entsteht. Der
# Skill sagt ihr, WIE sie die Werkzeuge gut benutzt; die Beschreibungen hier
# bleiben kurz (sie reisen in jedem Zug im gecachten Kopf mit).
#
# Nur gross (klein=None): das lokale qwen ist darauf nicht gemessen.
#
# Gefragt wird vor allem, was eine Datei anlegt (Auftrag 2026-10-08:
# „schreibende Aktionen durchs Erlaubnis-Gate"). „Immer" ist erlaubt: es wird
# nie etwas überschrieben oder gelöscht, nur eine neue Datei in die Ablage
# gelegt — anders als create_document (frei) bleibt Sasha so die Wahl.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import os

import ablage
from werkzeug_eintrag import Werkzeug


# ── Fragen an Sasha ─────────────────────────────────────────────────────

def _kurz(text, n: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _titel(args: dict) -> str:
    return _kurz(args.get("titel"), 80) or "ohne Titel"


def quelle_name(quelle) -> str:
    """Wie Sasha eine Quelle kennt: Titel aus der Ablage oder Dateiname."""
    q = str(quelle or "").strip()
    if not q:
        return "?"
    try:
        if ablage.gibt_es(q):
            return _kurz(ablage.kopf(q).get("titel") or q, 60)
    except Exception:
        pass
    return _kurz(os.path.basename(q.rstrip("/")) or q, 60)


def _frage_pdf_neu(args: dict) -> str:
    return f'Soll ich das PDF „{_titel(args)}“ erstellen und in deine Ablage legen?'


def _frage_docx_neu(args: dict) -> str:
    return (f'Soll ich die Word-Datei „{_titel(args)}“ erstellen und in deine '
            f'Ablage legen?')


def _frage_zusammen(args: dict) -> str:
    teile = args.get("teile") if isinstance(args.get("teile"), list) else []
    namen = []
    for t in teile[:4]:
        t = t if isinstance(t, dict) else {}
        seiten = _kurz(t.get("seiten"), 20)
        namen.append(quelle_name(t.get("quelle")) + (f" (Seiten {seiten})" if seiten else ""))
    if len(teile) > 4:
        namen.append(f"{len(teile) - 4} weiteren")
    woraus = ", ".join(namen) if namen else "mehreren PDFs"
    return (f'Soll ich aus {woraus} ein neues PDF „{_titel(args)}“ machen und in '
            f'deine Ablage legen? Die Originale bleiben, wie sie sind.')


def _frage_docx_aendern(args: dict) -> str:
    ersetzen = args.get("ersetzen") if isinstance(args.get("ersetzen"), list) else []
    was = []
    for e in ersetzen[:3]:
        e = e if isinstance(e, dict) else {}
        was.append(f'„{_kurz(e.get("alt"), 30)}“ → „{_kurz(e.get("neu"), 30)}“')
    if len(ersetzen) > 3:
        was.append(f"und {len(ersetzen) - 3} weitere Ersetzungen")
    if str(args.get("anhaengen") or "").strip():
        was.append("einen Abschnitt hinten anhängen")
    was_text = "; ".join(was) if was else "nichts angegeben"
    return (f'Soll ich eine geänderte Kopie von „{quelle_name(args.get("quelle"))}“ '
            f'anlegen ({was_text})? Das Original bleibt.')


# ── Einträge ────────────────────────────────────────────────────────────

_QUELLE = {"type": "string",
           "description": "Ablage-id (auch Anhang) oder Dateipfad unter ~/codicus."}
_MARKDOWN = {"type": "string",
             "description": "Markdown: # Überschriften, Absätze, **fett**, Listen, "
                            "| Tabellen |, ``` Code."}

EINTRAEGE = [
    Werkzeug(
        name="read_pdf",
        klein=None,
        gross=(
            "Liest ein PDF: Text je Seite mit Seitenzahlen; was='tabellen' "
            "hält Spalten und erkennt Tabellen, was='formular' liest die "
            "Formularfelder. Wie und wo die Grenzen sind: Skill pdf."
        ),
        parameter={
            "type": "object",
            "properties": {
                "quelle": _QUELLE,
                "seiten": {"type": "string",
                           "description": "z.B. '1-3,7'; leer = von vorn."},
                "was": {"type": "string", "enum": ["text", "tabellen", "formular"],
                        "description": "Standard: text."},
            },
            "required": ["quelle"],
        },
    ),
    Werkzeug(
        name="create_pdf",
        erlaubnis=True,
        frage=_frage_pdf_neu,
        alltag="pdf-dateien anlegen",
        schreibt=True,
        beweis="liest das PDF aus der Ablage nach: Seitenzahl und Text der ersten Seite",
        klein=None,
        gross="Erstellt ein neues PDF aus Markdown und legt es in Sashas Ablage. Wird bestätigt.",
        parameter={
            "type": "object",
            "properties": {
                "titel":  {"type": "string", "description": "Titel (auch Dateiname)."},
                "inhalt": _MARKDOWN,
            },
            "required": ["titel", "inhalt"],
        },
    ),
    Werkzeug(
        name="combine_pdf",
        erlaubnis=True,
        frage=_frage_zusammen,
        alltag="pdfs zusammenfügen oder seiten herausnehmen",
        schreibt=True,
        beweis="liest das neue PDF aus der Ablage nach und zählt die Seiten",
        klein=None,
        gross=(
            "Neues PDF aus Teilen anderer PDFs, in dieser Reihenfolge: "
            "zusammenfügen oder Seiten herausnehmen. Originale bleiben. Wird "
            "bestätigt."
        ),
        parameter={
            "type": "object",
            "properties": {
                "titel": {"type": "string", "description": "Titel des neuen PDFs."},
                "teile": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quelle": _QUELLE,
                            "seiten": {"type": "string",
                                       "description": "z.B. '2-4'; leer = alle."},
                        },
                        "required": ["quelle"],
                    },
                },
            },
            "required": ["titel", "teile"],
        },
    ),
    Werkzeug(
        name="read_docx",
        klein=None,
        gross=(
            "Liest eine Word-Datei (.docx): Text mit # Überschriften, Listen "
            "und Tabellen. Skill word."
        ),
        parameter={
            "type": "object",
            "properties": {
                "quelle": _QUELLE,
                "ab": {"type": "integer",
                       "description": "Optional: ab diesem Zeichen weiterlesen."},
            },
            "required": ["quelle"],
        },
    ),
    Werkzeug(
        name="create_docx",
        erlaubnis=True,
        frage=_frage_docx_neu,
        alltag="word-dateien anlegen",
        schreibt=True,
        beweis="liest die Word-Datei aus der Ablage nach: Überschriften, Tabellen, Anfang",
        klein=None,
        gross="Erstellt eine neue Word-Datei (.docx) aus Markdown in Sashas Ablage. Wird bestätigt.",
        parameter={
            "type": "object",
            "properties": {
                "titel":  {"type": "string", "description": "Titel (auch Dateiname)."},
                "inhalt": _MARKDOWN,
            },
            "required": ["titel", "inhalt"],
        },
    ),
    Werkzeug(
        name="edit_docx",
        erlaubnis=True,
        frage=_frage_docx_aendern,
        alltag="geänderte kopien von word-dateien anlegen",
        schreibt=True,
        beweis="liest die Kopie nach: neuer Text da, alter weg, Angehängtes am Ende",
        klein=None,
        gross=(
            "Legt eine geänderte KOPIE einer Word-Datei in die Ablage: Text "
            "wörtlich ersetzen und/oder Markdown hinten anhängen. Das "
            "Original bleibt. Wird bestätigt."
        ),
        parameter={
            "type": "object",
            "properties": {
                "quelle": _QUELLE,
                "ersetzen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "alt": {"type": "string", "description": "Genau so im Text."},
                            "neu": {"type": "string"},
                        },
                        "required": ["alt", "neu"],
                    },
                },
                "anhaengen": _MARKDOWN,
                "titel": {"type": "string",
                          "description": "Titel der Kopie; leer = alter + „(geändert)“."},
            },
            "required": ["quelle"],
        },
    ),
]
