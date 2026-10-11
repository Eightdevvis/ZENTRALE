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
import io
import threading
import zipfile
from collections import OrderedDict

import ablage
import pdf_datei
import tabelle_datei
import word_datei

_MERKEN = 32
_gemerkt: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()


def art_von(daten: bytes) -> str | None:
    """"pdf" | "docx" | "xlsx" | None — an den ersten Bytes, nicht am Namen."""
    if pdf_datei.ist_pdf(daten):
        return "pdf"
    if word_datei.ist_docx(daten):
        return "docx"
    if tabelle_datei.ist_xlsx(daten):        # Excel (2026-10-11, Skill excel)
        return "xlsx"
    if daten[:4] in (b"PK\x03\x04", b"PK\x05\x06"):   # sonst eine Zip (2026-10-11)
        return "zip"
    return None


ZIP_LISTE = 300           # so viele Einträge zeigt die Vorschau einer Zip


def _zip_liste(daten: bytes) -> dict:
    """Was in einer Zip steckt — Namen und Größen, nichts ausgepackt."""
    try:
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            infos = [i for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        return {"art": "zip", "text": "", "fehler": "Die Zip ist kaputt."}
    zeilen = [f"Zip mit {len(infos)} Dateien (unzip packt aus, import_skill übernimmt Skills):"]
    zeilen += [f"  {i.filename}  ({max(1, round(i.file_size / 1024))} KB)"
               for i in infos[:ZIP_LISTE]]
    if len(infos) > ZIP_LISTE:
        zeilen.append(f"  … {len(infos) - ZIP_LISTE} weitere")
    return {"art": "zip", "text": "\n".join(zeilen), "fehler": "", "leer": not infos}


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
    if art == "zip":
        return _zip_liste(daten)
    if art == "xlsx":
        try:
            r = tabelle_datei.lesen(daten)
        except tabelle_datei.Fehler as e:
            return {"art": art, "text": "", "fehler": str(e)}
        text = tabelle_datei.kopf_text(r) + f"\nBlatt „{r['blatt']}“:\n" + tabelle_datei.als_text(r)
        if r.get("weiter"):
            text += f"\n[… weiter mit read_xlsx bereich={r['weiter']}]"
        return {"art": art, "text": text, "fehler": "", "leer": not r["zellen"]}
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
    if k.get("art") not in ablage.DATEIEN:
        return {"art": k.get("art"), "text": "", "fehler": "keine PDF-, Word- oder Excel-Datei"}
    return aus_bytes(k["art"], ablage.roh(doc_id, fassung))


def kopfzeile(erg: dict, doc_id: str) -> str:
    """Eine Zeile vor dem Text an die KI: was es ist und womit mehr geht."""
    if erg.get("art") == "pdf":
        felder = f", Formular mit {erg['felder']} Feldern" if erg.get("felder") else ""
        return (f"(PDF, {erg.get('seiten') or '?'} Seiten{felder} — Original in der "
                f"Ablage, id {doc_id}; Seiten/Tabellen/Formular: read_pdf)")
    if erg.get("art") == "xlsx":
        return (f"(Excel-Tabelle — Original in der Ablage, id {doc_id}; mehr: read_xlsx, "
                f"ändern: edit_xlsx)")
    if erg.get("art") == "zip":
        return (f"(Zip — Original in der Ablage, id {doc_id}; auspacken: unzip, "
                f"Skills übernehmen: import_skill)")
    return (f"(Word-Datei — Original in der Ablage, id {doc_id}; ändern: edit_docx)")
