# core/ablage_zip.py
#
# Eine Zip aus der Ablage ansehen oder auspacken — ihre Dateien werden
# eigene Dokumente der Ablage (Werkzeug unzip).
#
# 2026-10-11: Input/ und Output/ sind für die KI abgebaut, die Ablage ist der
# eine Ort für Dateien (Sasha: „ja einfach nur die ablage dann"). Vorher
# packte unzip eine Zip aus Input/ nach Output/<name>/ (core/input_dateien.py).
# Die Ablage kennt keine Ordner — darum wird jede Datei ein Dokument mit
# Titel „<zipname>/<pfad>" (lesbar im Ordner als „<zipname>_<pfad>"); was
# keine Art hat, die die Ablage kennt (Binäres), wird ausgelassen und
# genannt. Ganz oder gar nicht: geht ein Dokument nicht, ist keins da.
#
# Die Dateien gehören Sasha (abgelegt_von sasha): es ist sein Inhalt, auch
# wenn die KI ausgepackt hat — weggeräumt wird davon nur nach seinem Ja.
#
# Prüfung der Zip (kein .., kein Verweis, Grenzen): core/zip_sicher.py, wie
# bei import_skill.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import shutil
import tempfile

import ablage
import anhang
import zip_sicher

MAX_DATEIEN = 50                  # jede wird ein Dokument und eine Datei im Ordner
MAX_BYTES = 20 * 1024 * 1024      # entpackt, alle zusammen
LISTE_MAX = 100

_CODE = {zip_sicher.UNSICHER: "Z-UNSICHER", zip_sicher.ZU_GROSS: "Z-ZU-GROSS",
         zip_sicher.KAPUTT: "Z-ZIP-KAPUTT"}


class Fehler(Exception):
    """Abbruch mit Code aus core/fehlercodes.py."""

    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code, self.grund = code, grund


def groesse(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 2**20:.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB" if n else "0 KB"


def _zip(doc_id) -> tuple:
    """→ (kopf, roh). Wirft Fehler."""
    q = str(doc_id or "").strip()
    if not q or not ablage.gibt_es(q):
        raise Fehler("A-DOK-UNBEKANNT", "kein Dokument mit dieser id in der Ablage")
    k = ablage.kopf(q)
    if k.get("art") != "zip":
        raise Fehler("Z-KEINE-ZIP", f"„{k.get('titel')}“ ist keine Zip (Art {k.get('art')})")
    return k, ablage.roh(q)


def _stamm(titel: str) -> str:
    t = str(titel or "zip")
    return t[:-4] if t.lower().endswith(".zip") else t


def ansehen(doc_id) -> dict:
    """Was in der Zip steckt, ohne etwas anzulegen. → {titel, dateien:
    [(pfad, bytes)], bytes, ausgelassen, zu_viel: "" | grund}."""
    k, roh = _zip(doc_id)
    with tempfile.TemporaryDirectory(prefix="zentrale_unzip_") as tmp:
        p = os.path.join(tmp, "a.zip")
        with open(p, "wb") as f:
            f.write(roh)
        try:
            with zip_sicher.oeffnen(p) as zf:
                liste = zip_sicher.eintraege(zf)
        except zip_sicher.Fehler as e:
            raise Fehler(_CODE[e.art], e.grund)
    dateien, ausgelassen = [], []
    for info, teile in liste:
        (ausgelassen.append("/".join(teile)) if zip_sicher.auslassen_standard(teile)
         else dateien.append(("/".join(teile), info.file_size)))
    zu_viel = ""
    try:
        zip_sicher.grenzen([(i, t) for i, t in liste if not zip_sicher.auslassen_standard(t)],
                           MAX_DATEIEN, MAX_BYTES)
    except zip_sicher.Fehler as e:
        zu_viel = e.grund
    return {"titel": k.get("titel"), "dateien": dateien, "bytes": sum(n for _, n in dateien),
            "ausgelassen": ausgelassen, "zu_viel": zu_viel}


def auspacken(doc_id, gespraech=None) -> dict:
    """Jede Datei der Zip als eigenes Dokument (Sashas). → {titel, angelegt:
    [kopf], ausgelassen: [pfad], ohne_art: [pfad]}. Wirft Fehler — dann ist
    kein Dokument angelegt."""
    k, roh = _zip(doc_id)
    stamm = _stamm(k.get("titel"))
    angelegt, ohne_art = [], []
    tmp = tempfile.mkdtemp(prefix="zentrale_unzip_")
    try:
        p = os.path.join(tmp, "a.zip")
        with open(p, "wb") as f:
            f.write(roh)
        ziel = os.path.join(tmp, "aus")
        try:
            ausgelassen = zip_sicher.auspacken(p, ziel, max_dateien=MAX_DATEIEN,
                                               max_bytes=MAX_BYTES)
        except zip_sicher.Fehler as e:
            raise Fehler(_CODE[e.art], e.grund)
        for ort, ordner, namen in os.walk(ziel):
            ordner.sort()
            for name in sorted(namen):
                rel = os.path.relpath(os.path.join(ort, name), ziel).replace(os.sep, "/")
                with open(os.path.join(ort, name), "rb") as f:
                    daten = f.read()
                try:
                    art, endung, text = anhang.art_fuer(name, daten)
                except anhang.Abgelehnt:
                    ohne_art.append(rel)
                    continue
                if not daten:
                    ohne_art.append(rel)
                    continue
                try:
                    angelegt.append(ablage.anlegen(
                        f"{stamm}/{rel}", daten if art in ablage.BINAER else text, art,
                        herkunft="ausgepackt", gespraech=gespraech, endung=endung,
                        quelle=f"aus {k.get('titel')}", von="sasha"))
                except ablage.Fehler as e:
                    raise Fehler("Z-ABGELEHNT", f"{rel}: {e}")
        if not angelegt:
            raise Fehler("Z-LEER", "darin liegt nichts, was die Ablage aufnimmt"
                         + (f" (ohne bekannte Art: {', '.join(ohne_art[:5])})" if ohne_art else ""))
    except BaseException:
        for a in angelegt:          # gab es vorher nicht
            shutil.rmtree(os.path.join(ablage.ordner(), a["id"]), ignore_errors=True)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"titel": k.get("titel"), "angelegt": angelegt, "ausgelassen": ausgelassen,
            "ohne_art": ohne_art}
