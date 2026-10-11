# core/ki_ablage_adapter.py
#
# Der Adapter der Ablage für den Werkzeug-Erzeuger (core/werkzeug_erzeuger/;
# Schemas: core/werkzeug_ablage.py): ersetzen, in den Papierkorb, zurück.
# Nachlesen, Zurücknehmen und die feste Satzform macht der Erzeuger — hier
# steht nur, was die ABLAGE weiß.
#
# 2026-10-11, Führerschein-Gespräch 20261011-081303: die KI legte für jede
# Änderung eines PDFs eine neue Kopie an („die alte bleibt daneben, einfach
# ignorieren"). Sasha: „sie muss alte sachen in der ablage rauslöschen und
# ersetzen können." Gelöscht wird trotzdem nie — der Papierkorb ist ein Feld
# im Kopf, jederzeit zurück.
#
# Sauber im Sinn des Erzeugers: jedes Dokument über seine feste id, nachlesen
# per id (ablage.kopf), Ablehnung mit Code (A-…), nie still.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import os
import shutil

import ablage
import ablage_text
import pdf_schreiben
import word_datei
import zug
from werkzeug_erzeuger import Ablehnung, Ergebnis

# Woraus replace_document eine neue Fassung baut: Text-Arten wörtlich, PDF
# und Word aus Markdown (dieselben Bausteine wie create_pdf/create_docx).
TEXT_ARTEN = ("markdown", "text", "code", "csv")


def _text(args: dict, feld: str) -> str:
    return str(args.get(feld) or "").strip()


def _kopf(doc_id: str) -> dict:
    if not doc_id or not ablage.gibt_es(doc_id):
        raise Ablehnung("A-DOK-UNBEKANNT", "kein Dokument mit dieser id in der Ablage")
    return ablage.kopf(doc_id)


def titel_von(doc_id: str) -> str:
    try:
        return ablage.kopf(doc_id).get("titel") or doc_id
    except (ablage.Unbekannt, OSError):
        return doc_id or "?"


def gehoert_sasha(args: dict) -> bool:
    """Für das Gate: ein Dokument von Sasha wird erst nach seinem Ja ersetzt
    oder weggeräumt (Sasha, 2026-10-11: „ihre eigenen dokumente soll sie
    einfach so wegräumen können. meine sachen soll sie mit nachfrage
    wegräumen können"). Unbekannte id: keine Frage — das Werkzeug bricht
    ohnehin mit A-DOK-UNBEKANNT ab, ohne etwas anzufassen."""
    doc_id = _text(args, "id")
    try:
        return ablage.gibt_es(doc_id) and ablage.von_sasha(ablage.kopf(doc_id))
    except (ablage.Unbekannt, OSError):
        return False


# ── Die drei Aktionen ──────────────────────────────────────────────────

def _neuer_inhalt(k: dict, inhalt: str, titel: str):
    art = k.get("art")
    if art in TEXT_ARTEN:
        return inhalt
    if art == "pdf":
        try:
            roh, info = pdf_schreiben.erzeugen(titel, inhalt)
        except ValueError as e:
            raise Ablehnung("P-DATEI-KAPUTT", str(e))
        if info["ersetzt"]:
            raise Ablehnung("P-ZEICHEN", f"{info['ersetzt']} Zeichen kann die PDF-Schrift "
                            f"nicht darstellen (z. B. {' '.join(info['beispiele'])})")
        return roh
    if art == "docx":
        try:
            return word_datei.erzeugen(titel, inhalt)
        except word_datei.Fehler as e:
            raise Ablehnung("P-DATEI-KAPUTT", str(e))
    if art == "xlsx":
        raise Ablehnung("A-ERSETZEN-ART", "eine Excel-Tabelle ändert edit_xlsx (Zellen, Zeilen)")
    raise Ablehnung("A-ERSETZEN-ART", f"ein Dokument der Art {art} lässt sich nicht aus "
                    f"Text neu bauen")


def _lesbar(neu: dict, inhalt) -> bool:
    try:
        if neu.get("art") in TEXT_ARTEN:
            return ablage.lesen(neu["id"])["inhalt"] == inhalt
        erg = ablage_text.text(neu["id"])
        return not erg.get("fehler")
    except (ablage.Unbekannt, OSError):
        return False


def ersetzen(args: dict) -> Ergebnis:
    alt_id = _text(args, "id")
    k = _kopf(alt_id)
    if ablage.im_papierkorb(k):
        raise Ablehnung("A-IM-PAPIERKORB", "das Dokument liegt im Papierkorb — erst "
                        "restore_document")
    titel = _text(args, "titel") or k.get("titel") or "Dokument"
    inhalt = _neuer_inhalt(k, str(args.get("inhalt") or ""), titel)
    try:
        neu, _alt = ablage.ersetzen(alt_id, inhalt, titel=titel, gespraech=zug.gespraech(),
                                    quelle=f"neue Fassung von {k.get('titel')}")
    except ablage.Fehler as e:
        raise Ablehnung("A-ABGELEHNT", str(e))

    def pruefe(e: dict) -> list:
        falsch = []
        try:
            alt = ablage.kopf(alt_id)
        except ablage.Unbekannt:
            alt = {}
        if e.get("ersetzt") != alt_id:
            falsch.append("die neue Fassung kennt ihr Original nicht")
        if not ablage.im_papierkorb(alt) or alt.get("ersetzt_durch") != neu["id"]:
            falsch.append("das Original liegt nicht im Papierkorb")
        if not _lesbar(neu, inhalt):
            falsch.append("die neue Fassung liest sich nicht so zurück")
        if not falsch:
            zug.melden({"ablage": ablage.kurz(e)})
        return falsch

    return Ergebnis(kennung=neu["id"], pruefe=pruefe, verb="ERSETZT",
                    nachsatz=f": alt {alt_id} liegt im Papierkorb (zurück mit restore_document)",
                    zusatz="Sasha sieht die neue Fassung im Chat und in seinem Ablage-Ordner "
                           "unter dem alten Namen; wiederhole den Inhalt nicht.")


def wegraeumen(args: dict) -> Ergebnis:
    doc_id = _text(args, "id")
    k = _kopf(doc_id)
    if ablage.im_papierkorb(k):
        raise Ablehnung("A-IM-PAPIERKORB", "liegt schon im Papierkorb")
    ablage.papierkorb(doc_id, True)
    return Ergebnis(kennung=doc_id, vorher=k, verb="IN DEN PAPIERKORB GELEGT",
                    pruefe=lambda e: [] if ablage.im_papierkorb(e) else
                    ["liegt nicht im Papierkorb"],
                    nachsatz=" — nichts gelöscht, zurück mit restore_document")


def zurueckholen(args: dict) -> Ergebnis:
    doc_id = _text(args, "id")
    k = _kopf(doc_id)
    if not ablage.im_papierkorb(k):
        raise Ablehnung("A-NICHT-IM-PAPIERKORB", "das Dokument liegt nicht im Papierkorb")
    ablage.papierkorb(doc_id, False)
    return Ergebnis(kennung=doc_id, vorher=k, verb="AUS DEM PAPIERKORB GEHOLT",
                    pruefe=lambda e: ["liegt noch im Papierkorb"] if ablage.im_papierkorb(e)
                    else [])


_AKTIONEN = {"replace_document": ersetzen, "trash_document": wegraeumen,
             "restore_document": zurueckholen}


# ── Fragen und Sätze ───────────────────────────────────────────────────

def ersetzen_hinweis(art: str, doc_id: str) -> str:
    """Für update_document auf PDF/Word/Excel: welcher Weg statt einer Kopie."""
    if art == "zip":
        return "eine Zip bekommt keine neue Fassung — unzip packt sie aus"
    weg = "edit_xlsx" if art == "xlsx" else "replace_document"
    return (f"eine {str(art).upper()}-Datei bekommt keine neue Fassung — {weg}"
            f"(id=\"{doc_id}\", …) legt die neue an und das alte in den Papierkorb")


def _frage(name: str, args: dict):
    titel = titel_von(_text(args, "id"))
    if name == "trash_document":
        return f"„{titel}“ hast du abgelegt — in den Papierkorb legen?"
    if name == "replace_document":
        return (f"„{titel}“ hast du abgelegt — durch eine neue Fassung ersetzen? "
                f"Das Original kommt in den Papierkorb.")
    return None


def _was(name: str, args: dict) -> str:
    titel = titel_von(_text(args, "id"))
    return {"replace_document": f"„{titel}“ ersetzen",
            "trash_document": f"„{titel}“ in den Papierkorb legen",
            "restore_document": f"„{titel}“ aus dem Papierkorb holen"}.get(name, name)


class AblageAdapter:
    """Grundaktionen der Ablage (Schnittstelle: werkzeug_erzeuger/__init__.py)."""

    def ausfuehren(self, name: str, args: dict) -> Ergebnis:
        return _AKTIONEN[name](args)

    def nachlesen(self, kennung: str):
        try:
            return ablage.kopf(kennung) if ablage.gibt_es(kennung) else None
        except ablage.Unbekannt:
            return None

    def loeschen(self, kennung: str) -> None:
        """Rücknahme von replace_document: das Original zurück, das neue weg
        (es gab es vorher nicht)."""
        k = ablage.kopf(kennung)
        if k.get("ersetzt") and ablage.gibt_es(k["ersetzt"]):
            ablage.papierkorb(k["ersetzt"], False)
        shutil.rmtree(os.path.join(ablage.ordner(), kennung))

    def wiederherstellen(self, kennung: str, vorher: dict) -> None:
        ablage.papierkorb_zuruecksetzen(kennung, vorher or {})

    def beschreiben(self, e: dict) -> str:
        return f"„{e.get('titel') or e.get('id')}“"

    def kurz(self, kennung: str) -> str:
        return kennung

    def ziel(self, kennung: str) -> str:
        return f"„{titel_von(kennung)}“"

    def frage(self, name: str, args: dict):
        return _frage(name, args)

    def was(self, name: str, args: dict) -> str:
        return _was(name, args)
