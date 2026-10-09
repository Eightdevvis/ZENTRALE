# core/input_dateien.py
#
# Was mit einer Datei aus Sashas Input/ (core/nutzer_ordner.py) passiert,
# außer lesen: eine Zip ansehen oder nach Output/ auspacken (Werkzeug unzip)
# und Erledigtes in den Papierkorb räumen (remove_input).
#
# 2026-10-09. unzip: Sasha legt Zips in Input/, die KEIN Skill sind — bisher
# kam die KI nicht hinein. Das Handwerk (prüfen, Grenzen) teilt es mit
# import_skill (core/zip_sicher.py). Ganz oder gar nicht: ausgepackt wird in
# einen versteckten Ordner IN Output/ (dieselbe Platte → os.rename ist
# atomar), erst danach umbenannt. Ein Ziel, das es schon gibt, bricht ab —
# überschrieben wird nie.
#
# remove_input — Sasha: „ob sie das file aus dem ordner dann removed
# afterwards damit der ordner nich zur halde wird". Gelöscht wird nie: die
# Datei wandert nach <nutzer_ordner>/.Papierkorb/<YYYY-MM-DD>/ (versteckt,
# also für Suchen und read_file unsichtbar). Der Abgleich zwischen Rechnern
# ist additiv; ein Papierkorb passt dazu, ein Löschen nicht.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import shutil
import tempfile
import zipfile
from datetime import date

import context
import nutzer_ordner
import zip_sicher

MAX_BYTES = 20 * 1024 * 1024      # entpackt, alle Dateien zusammen (wie import_skill)
MAX_DATEIEN = 500
PAPIERKORB = ".Papierkorb"
LISTE_MAX = 100                   # so viele Zeilen zeigt ansehen

# Die Arten von zip_sicher als Codes dieses Werkzeugs (core/fehlercodes.py).
_CODE = {zip_sicher.UNSICHER: "Z-UNSICHER", zip_sicher.ZU_GROSS: "Z-ZU-GROSS",
         zip_sicher.KAPUTT: "Z-ZIP-KAPUTT"}


class Fehler(Exception):
    """Abbruch mit Code aus core/fehlercodes.py."""

    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code = code
        self.grund = grund


def groesse(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 2**20:.1f} MB".replace(".", ",")
    return f"{max(1, round(n / 1024))} KB" if n else "0 KB"


# ── Was in Input/ liegt ────────────────────────────────────────────────

def _in_input(pfad, nur_direkt: bool = False) -> str:
    """Der echte Pfad zu dem, was Sasha/die KI nennt — nur in Input/.
    nur_direkt: nur ein Eintrag DIREKT in Input/ (kein Unterordner)."""
    roh = str(pfad or "").strip()
    if not roh:
        raise Fehler("Z-QUELLE-FEHLT", "keine Datei angegeben")
    echt = nutzer_ordner.aufloesen(roh, erlaubt=(nutzer_ordner.INPUT,))
    ein = os.path.realpath(nutzer_ordner.unterordner(nutzer_ordner.INPUT))
    if echt is None or echt == ein:
        raise Fehler("Z-QUELLE-AUSSERHALB", f"„{roh}“ liegt nicht in Input/")
    if not os.path.lexists(echt):
        raise Fehler("Z-QUELLE-FEHLT", f"„{roh}“ gibt es nicht in Input/ — mit find_files suchen")
    rel = os.path.relpath(echt, ein)
    if any(t.startswith(".") for t in rel.split(os.sep)) or context._is_secret(rel):
        raise Fehler("Z-QUELLE-GESPERRT", "versteckt oder nach Schlüssel aussehend")
    if nur_direkt and os.path.dirname(echt) != ein:
        raise Fehler("Z-NICHT-DIREKT", f"„{rel}“ liegt in einem Unterordner von Input/ — "
                                       f"weggeräumt wird nur, was direkt in Input/ liegt")
    return echt


def zip_quelle(pfad) -> str:
    echt = _in_input(pfad)
    if not os.path.isfile(echt) or not zipfile.is_zipfile(echt):
        raise Fehler("Z-KEINE-ZIP", f"„{os.path.basename(echt)}“ ist keine Zip-Datei")
    return echt


def zielname(echt: str) -> str:
    """„Fotos.zip" → „Fotos" (Endung egal wie geschrieben)."""
    name = os.path.basename(echt)
    return name[:-4] if name.lower().endswith(".zip") else name


def ziel_anzeige(echt: str) -> str:
    return f"{nutzer_ordner.OUTPUT}/{zielname(echt)}/"


# ── unzip ──────────────────────────────────────────────────────────────

def ansehen(pfad) -> dict:
    """Was in der Zip steckt, ohne etwas auszupacken.
    → {datei, ziel, dateien: [(pfad, bytes)], bytes, ausgelassen: [pfad],
       zu_gross: "" | grund, ziel_da: bool}. Wirft Fehler (unsicher/kaputt)."""
    echt = zip_quelle(pfad)
    try:
        with zip_sicher.oeffnen(echt) as zf:
            liste = zip_sicher.eintraege(zf)
    except zip_sicher.Fehler as e:
        raise Fehler(_CODE[e.art], e.grund)
    zu_gross = ""
    try:
        zip_sicher.grenzen(liste, MAX_DATEIEN, MAX_BYTES)
    except zip_sicher.Fehler as e:
        zu_gross = e.grund
    dateien, ausgelassen = [], []
    for info, teile in liste:
        if zip_sicher.auslassen_standard(teile):
            ausgelassen.append("/".join(teile))
        else:
            dateien.append(("/".join(teile), info.file_size))
    ziel = os.path.join(nutzer_ordner.unterordner(nutzer_ordner.OUTPUT), zielname(echt))
    return {"datei": os.path.basename(echt), "ziel": ziel_anzeige(echt), "dateien": dateien,
            "bytes": sum(n for _, n in dateien), "ausgelassen": ausgelassen,
            "zu_gross": zu_gross, "ziel_da": os.path.lexists(ziel)}


def _nachzaehlen(ordner: str) -> tuple:
    n = summe = 0
    for ort, _, namen in os.walk(ordner):
        for name in namen:
            n += 1
            summe += os.path.getsize(os.path.join(ort, name))
    return n, summe


def auspacken(pfad) -> dict:
    """Die Zip nach Output/<name>/ — ganz oder gar nicht.
    → {datei, ziel, dateien (Zahl), bytes, ausgelassen: [pfad], oben: [Namen
       in der obersten Ebene], echt}. Wirft Fehler (mit Code)."""
    echt = zip_quelle(pfad)
    aus = nutzer_ordner.unterordner(nutzer_ordner.OUTPUT)
    ziel = os.path.join(aus, zielname(echt))
    if not zielname(echt).strip() or zielname(echt).startswith("."):
        raise Fehler("Z-QUELLE-GESPERRT", "aus diesem Namen entstünde ein versteckter Ordner")
    if os.path.lexists(ziel):
        raise Fehler("Z-ZIEL-GIBT-ES", f"{ziel_anzeige(echt)} gibt es schon")
    arbeit = tempfile.mkdtemp(prefix=".unzip.", dir=aus)
    try:
        try:
            ausgelassen = zip_sicher.auspacken(echt, arbeit, max_dateien=MAX_DATEIEN,
                                               max_bytes=MAX_BYTES)
        except zip_sicher.Fehler as e:
            raise Fehler(_CODE[e.art], e.grund)
        except OSError as e:
            raise Fehler("Z-ZIP-KAPUTT", f"Auspacken ging nicht ({e})")
        n, summe = _nachzaehlen(arbeit)
        if not n:
            raise Fehler("Z-LEER", "darin liegt nichts, was ausgepackt würde"
                         + (f" (ausgelassen: {', '.join(ausgelassen[:5])})" if ausgelassen else ""))
        if os.path.lexists(ziel):       # in der Zwischenzeit entstanden
            raise Fehler("Z-ZIEL-GIBT-ES", f"{ziel_anzeige(echt)} gibt es schon")
        os.chmod(arbeit, 0o755)         # mkdtemp legt 0700 an
        os.rename(arbeit, ziel)
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
    return {"datei": os.path.basename(echt), "ziel": ziel_anzeige(echt), "dateien": n,
            "bytes": summe, "ausgelassen": ausgelassen, "oben": sorted(os.listdir(ziel)),
            "echt": echt, "ziel_echt": ziel}


def nachgezaehlt(ziel_echt: str) -> tuple:
    """(Dateien, Bytes) im ausgepackten Ordner — der Beleg."""
    return _nachzaehlen(ziel_echt) if os.path.isdir(ziel_echt) else (0, 0)


# ── remove_input ───────────────────────────────────────────────────────

def papierkorb_ordner(tag: str | None = None) -> str:
    return os.path.join(nutzer_ordner.wurzel(), PAPIERKORB, tag or date.today().isoformat())


def _freier_name(ordner: str, name: str) -> str:
    """„x.pdf", sonst „x (2).pdf", „x (3).pdf" … — nie überschreiben."""
    if not os.path.lexists(os.path.join(ordner, name)):
        return name
    stamm, endung = os.path.splitext(name)
    if stamm.startswith(".") or not stamm:
        stamm, endung = name, ""
    i = 2
    while os.path.lexists(os.path.join(ordner, f"{stamm} ({i}){endung}")):
        i += 1
    return f"{stamm} ({i}){endung}"


def liegt(neu: str, alt: str) -> bool:
    """Der Beleg nach dem Verschieben: am neuen Ort da, am alten weg."""
    return os.path.lexists(neu) and not os.path.lexists(alt)


def in_papierkorb(pfad) -> dict:
    """Eine Datei/einen Ordner DIREKT aus Input/ in den Papierkorb
    verschieben. → {name, alt, neu (Anzeige), neu_echt}. Wirft Fehler."""
    echt = _in_input(pfad, nur_direkt=True)
    korb = papierkorb_ordner()
    os.makedirs(korb, exist_ok=True)
    neu = os.path.join(korb, _freier_name(korb, os.path.basename(echt)))
    try:
        os.rename(echt, neu)
    except OSError as e:
        raise Fehler("Z-VERSCHIEBEN", f"Verschieben ging nicht ({e})")
    if not liegt(neu, echt):
        try:                            # zurück an den alten Platz
            os.rename(neu, echt)
        except OSError:
            pass
        raise Fehler("W-NICHT-GESPEICHERT", "nachgesehen liegt es nicht im Papierkorb "
                                            "bzw. noch in Input/; zurückgelegt")
    return {"name": os.path.basename(echt), "alt": nutzer_ordner.anzeige(echt),
            "neu": nutzer_ordner.anzeige(neu), "neu_echt": neu, "alt_echt": echt}
