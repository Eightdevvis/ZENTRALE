# core/werkzeug_tabelle.py
#
# Die Einträge der Tabellen-Werkzeuge (Skill excel) und ihre Fragen an
# Sasha: read_xlsx, create_xlsx, edit_xlsx. werkzeug_register hängt
# EINTRAEGE hinten an; ausgeführt wird in core/ki_tabelle.py.
#
# 2026-10-11 (Führerschein-Gespräch 20261011-081303; memory/ki/tabellen.md).
# Warum von Hand wie pdf/word und nicht über den Werkzeug-Erzeuger: der
# Erzeuger prüft flache Felder und belegt über einen Eintrag mit Kennung;
# hier gehen verschachtelte Zeilen/Blätter hinein, der Beleg ist der
# zurückgelesene Inhalt einer Datei (Zelle für Zelle), und lesen liefert
# langen Text in Stücken — genau das, was ki_pdf_word schon so macht.
# Ersetzen und Papierkorb teilen sie mit replace_document (ablage.ersetzen).
#
# Gate (Sasha: „ihre eigenen dokumente soll sie einfach so wegräumen können.
# meine sachen soll sie mit nachfrage wegräumen können"):
#   - read_xlsx frei;
#   - create_xlsx frei wie create_document: nur ein neues Dokument in der
#     Ablage, nichts überschrieben;
#   - edit_xlsx: eigene Tabelle frei (das alte in den Papierkorb), Sashas
#     Tabelle nur nach seinem Ja — jedes Mal, kein „immer"; mit daneben=true
#     entsteht eine neue Tabelle neben seiner, das braucht kein Ja.
#
# Nur gross (klein=None): das lokale qwen ist darauf nicht gemessen.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import ablage
from werkzeug_eintrag import Werkzeug


def _daneben(args: dict) -> bool:
    v = args.get("daneben")
    return v is True or str(v).strip().lower() in ("true", "1", "ja")


def _kopf(args: dict):
    doc_id = str(args.get("id") or "").strip()
    try:
        return ablage.kopf(doc_id) if ablage.gibt_es(doc_id) else None
    except ablage.Unbekannt:
        return None


def sashas_tabelle(args: dict) -> bool:
    """Gate von edit_xlsx: Sashas Tabelle (im Zweifel) ohne daneben."""
    k = _kopf(args)
    return bool(k) and not _daneben(args) and ablage.von_sasha(k)


def _frage_aendern(args: dict) -> str:
    k = _kopf(args) or {}
    titel = k.get("titel") or "?"
    teile = []
    for a in (args.get("aenderungen") if isinstance(args.get("aenderungen"), list) else [])[:3]:
        a = a if isinstance(a, dict) else {}
        teile.append(f"{a.get('zelle')} = {str(a.get('wert'))[:30]}")
    zeilen = args.get("anhaengen") if isinstance(args.get("anhaengen"), list) else []
    if zeilen:
        teile.append(f"{len(zeilen)} Zeile{'n' if len(zeilen) != 1 else ''} anhängen")
    was = f" ({'; '.join(teile)})" if teile else ""
    if k.get("art") == "csv":
        return (f"„{titel}“ hast du abgelegt — geänderte Fassung speichern{was}? "
                f"Die alte Fassung bleibt erhalten.")
    return (f"„{titel}“ hast du abgelegt — geänderte Fassung speichern und das Original "
            f"in den Papierkorb legen{was}?")


_ID = {"type": "string", "description": "Ablage-id einer .xlsx oder .csv."}
_ZEILEN = {"type": "array", "items": {"type": "array"},
           "description": "Zeilen, je eine Liste von Zellen: Zahl, Text, true/false, null; "
                          "Formel als Text mit =, z.B. \"=SUMIF(C:C,\\\"bezahlt\\\",B:B)\" "
                          "(deutsch geht auch: =SUMMEWENN(C:C;\\\"bezahlt\\\";B:B))."}

EINTRAEGE = [
    Werkzeug(
        name="read_xlsx",
        klein=None,
        gross=("Liest eine Tabelle (.xlsx/.csv) der Ablage: Zellen mit Adresse, Formeln "
               "und ihr in der Datei gespeicherter Wert. Skill excel."),
        parameter={
            "type": "object",
            "properties": {
                "id": _ID,
                "blatt": {"type": "string", "description": "Optional; sonst das erste."},
                "bereich": {"type": "string", "description": "Optional, z.B. 'A1:D50'."},
            },
            "required": ["id"],
        },
    ),
    Werkzeug(
        name="create_xlsx",
        schreibt=True,
        beweis="liest die Tabelle aus der Ablage nach: jede gefüllte Zelle wie verlangt",
        alltag="excel-tabellen anlegen",
        klein=None,
        gross=("Legt eine neue Excel-Tabelle (oder format=csv) in Sashas Ablage an — für "
               "Listen, die wachsen und rechnen (Kosten, Stunden). Formeln stehen als "
               "Formeln drin, Werte rechnet Excel."),
        parameter={
            "type": "object",
            "properties": {
                "titel": {"type": "string", "description": "Titel (auch Dateiname)."},
                "blaetter": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Blattname, ≤31 Zeichen."},
                            "zeilen": _ZEILEN,
                            "spaltenbreiten": {"type": "array", "items": {"type": "number"},
                                               "description": "Optional, in Zeichen."},
                        },
                        "required": ["zeilen"],
                    },
                },
                "format": {"type": "string", "enum": ["xlsx", "csv"],
                           "description": "Standard xlsx; csv ohne Formeln, ein Blatt."},
            },
            "required": ["titel", "blaetter"],
        },
    ),
    Werkzeug(
        name="edit_xlsx",
        schreibt=True,
        beweis="liest die neue Fassung nach: geänderte Zellen und angehängte Zeilen stehen da",
        erlaubnis=sashas_tabelle,
        nur_einmal=lambda args: True,
        immer_erlaubbar=False,
        frage=_frage_aendern,
        alltag="sashas tabellen ändern",
        klein=None,
        gross=("Ändert Zellen einer Tabelle der Ablage und/oder hängt Zeilen an; speichert "
               "eine neue Fassung, die alte kommt in den Papierkorb (daneben=true: neue "
               "Tabelle daneben). Sashas Tabellen nur nach seinem Ja."),
        parameter={
            "type": "object",
            "properties": {
                "id": _ID,
                "aenderungen": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "blatt": {"type": "string", "description": "Optional; sonst das erste."},
                            "zelle": {"type": "string", "description": "z.B. 'C3'."},
                            "wert": {"description": "Zahl, Text, true/false, null; Formel mit =."},
                        },
                        "required": ["zelle"],
                    },
                },
                "anhaengen": _ZEILEN,
                "blatt": {"type": "string", "description": "Wohin anhaengen geht; sonst das erste."},
                "daneben": {"type": "boolean",
                            "description": "true: als neue Tabelle daneben, Original bleibt."},
                "titel": {"type": "string", "description": "Optional neuer Titel."},
            },
            "required": ["id"],
        },
    ),
]
