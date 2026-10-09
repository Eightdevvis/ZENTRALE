# core/ablage_text.py
#
# Der Text einer PDF- oder Word-Datei — für alle, die ihn brauchen: der
# Verlauf an die KI (angehängte Dateien), die Vorschau in der Ablage (TUI)
# und die Annahme eines Anhangs. Gemerkt nach Inhalt, damit nicht jeder Zug
# das PDF neu zerlegt (Anhänge gehen in jedem Zug wieder mit).
#
# 2026-10-08, Skills pdf und word (memory/ki/pdf_word.md). Seitdem liegt ein
# angehängtes PDF/Word als ORIGINAL in der Ablage (vorher nur sein Text) —
# sonst könnte die KI kein Formular lesen, nichts zusammenfügen und keine
# geänderte Kopie anlegen.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import hashlib
import threading
from collections import OrderedDict

import ablage
import pdf_datei
import word_datei

_MERKEN = 32
_gemerkt: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


def art_von(daten: bytes) -> str | None:
    """"pdf" | "docx" | None — an den ersten Bytes, nicht am Namen."""
    if pdf_datei.ist_pdf(daten):
        return "pdf"
    if word_datei.ist_docx(daten):
        return "docx"
    return None


def _zerlegen(art: str, daten: bytes) -> dict:
    if art == "pdf":
        try:
            r = pdf_datei.lesen(daten)
        except pdf_datei.Fehler as e:
            return {"art": art, "text": "", "fehler": str(e), "seiten": 0}
        teile = [f"--- Seite {s['nr']} ---\n{s['text'].strip()}" for s in r["seiten"]
                 if (s.get("text") or "").strip()]
        return {"art": art, "text": "\n\n".join(teile), "fehler": "",
                "seiten": r.get("seiten_gesamt") or 0, "felder": r.get("felder") or 0,
                "leer": not teile}
    try:
        r = word_datei.lesen(daten)
    except word_datei.Fehler as e:
        return {"art": art, "text": "", "fehler": str(e)}
    return {"art": art, "text": r["text"], "fehler": "", "leer": not r["text"].strip(),
            "hinweise": r.get("hinweise") or []}


def aus_bytes(art: str, daten: bytes) -> dict:
    """{art, text, fehler, leer, seiten?, felder?, hinweise?} — gemerkt nach
    Inhalt (sha256)."""
    schluessel = art + ":" + hashlib.sha256(daten).hexdigest()
    with _lock:
        if schluessel in _gemerkt:
            _gemerkt.move_to_end(schluessel)
            return dict(_gemerkt[schluessel])
    erg = _zerlegen(art, daten)
    with _lock:
        _gemerkt[schluessel] = erg
        while len(_gemerkt) > _MERKEN:
            _gemerkt.popitem(last=False)
    return dict(erg)


def text(doc_id, fassung=None) -> dict:
    """Der Text eines pdf/docx-Dokuments der Ablage. Wirft ablage.Unbekannt;
    andere Arten → fehler."""
    k = ablage.kopf(doc_id)
    if k.get("art") not in ("pdf", "docx"):
        return {"art": k.get("art"), "text": "", "fehler": "keine PDF- oder Word-Datei"}
    return aus_bytes(k["art"], ablage.roh(doc_id, fassung))


def kopfzeile(erg: dict, doc_id: str) -> str:
    """Eine Zeile vor dem Text an die KI: was es ist und womit mehr geht."""
    if erg.get("art") == "pdf":
        felder = f", Formular mit {erg['felder']} Feldern" if erg.get("felder") else ""
        return (f"(PDF, {erg.get('seiten') or '?'} Seiten{felder} — Original in der "
                f"Ablage, id {doc_id}; Seiten/Tabellen/Formular: read_pdf)")
    return (f"(Word-Datei — Original in der Ablage, id {doc_id}; ändern: edit_docx)")
