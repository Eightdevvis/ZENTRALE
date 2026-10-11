# core/ablage_sichtbar.py
#
# Die Ablage als Ordner, den Sasha im Dateimanager sieht: ~/Zentrale/Ablage/
# (Einstellung ablage_dir). Darin liegt von jedem Dokument die neueste
# Fassung als lesbare Datei „<Titel><endung>" — und was Sasha selbst dort
# hineinlegt, wird zu einem Dokument der Ablage.
#
# 2026-10-11, Sasha: „das problem mit der ablage ist ja momentan nur das sie
# wo liegt? der user soll nich im code fischen gehen müssen" und „den ordner
# wo ich sachen direkt reinschmeißen kann direkt nachrüsten". Der Ordner ist
# zugleich der Einwurf: kein zweiter Ordner, keine Input/Output-Trennung.
#
# Wahrheit bleibt, was core/ablage.py versteckt unter .ablage/dokumente/
# hält (Kopf + Fassungen, nie überschrieben). Die lesbaren Dateien sind eine
# Ansicht darauf, die abgleichen() in beide Richtungen nachzieht:
#
#   neues Dokument / neue Fassung   → Datei anlegen bzw. neu schreiben
#   Sasha ändert die Datei          → neue Fassung (auch bei PDF/Excel)
#   Sasha benennt sie um            → neuer Titel (erkannt am Inhalt)
#   Sasha löscht sie                → Papierkorb „von Sasha entfernt", nichts neu
#   Papierkorb (KI oder Sasha)      → Datei nach .ablage/papierkorb/
#   unbekannte Datei im Ordner      → Einwurf: nach zwei Blicken mit gleicher
#                                     Größe (fertig geschrieben) ein Dokument,
#                                     abgelegt_von sasha, Titel = Dateiname
#
# ── Mehrere Rechner ────────────────────────────────────────────────────
# Abgeglichen wird nur .ablage/dokumente/ (Köpfe und Fassungen, wie bisher
# data/ablage/); die lesbaren Dateien baut jeder Rechner selbst daraus. Was
# dieser Rechner zuletzt in den Ordner gelegt hat (Name, Größe, Zeit,
# Prüfsumme je id), steht in .ablage/sichtbar-<rechner>.json — eine Datei
# pro Rechner, die nur er schreibt (Regel „eine Datei pro Knoten"). Nur an
# ihr lässt sich unterscheiden, ob Sasha eine Datei hier gelöscht hat (sie
# stand drin) oder ob sie hier nur noch nie lag (neu vom anderen Rechner).
# Ein gemeinsamer Index, in den beide schreiben, hätte genau das verwischt;
# die Köpfe je Dokument führt der Abgleich ohnehin feldweise zusammen.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Meldet sich beim Import
# bei ablage.NACH_SCHREIBEN an; den Takt gibt core/ablage_wache.py.

import hashlib
import json
import os
import re
import threading
import time
from collections import deque

import ablage
import anhang
import context
import dateien

PAPIERKORB = "papierkorb"
# Zwischenstände von Browsern/Office/Editoren — nie übernehmen.
_HALBFERTIG = (".part", ".crdownload", ".tmp", ".partial", ".download", "~")
NEU_MERKEN = 20

_lock = threading.RLock()
_still = threading.local()        # während abgleichen(): Meldungen nicht einzeln
_gesehen: dict = {}               # name → (größe, mtime_ns) beim letzten Blick
_abgelehnt: dict = {}             # name → (größe, mtime_ns): nicht nochmal versuchen
NEU: deque = deque(maxlen=NEU_MERKEN)   # zuletzt Eingeworfenes (TUI-Hinweis)


# ── Wo ──────────────────────────────────────────────────────────────────

def _versteckt() -> str:
    return os.path.join(ablage.wurzel(), ablage.VERSTECKT)


def _stand_pfad() -> str:
    return os.path.join(_versteckt(), f"sichtbar-{dateien.knoten()}.json")


def _stand_lesen() -> dict:
    try:
        with open(_stand_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _stand_schreiben(stand: dict) -> None:
    os.makedirs(_versteckt(), exist_ok=True)
    dateien.json_schreiben(_stand_pfad(), stand)


def dateiname(k: dict) -> str:
    """„<Titel><endung>" — ohne Schrägstrich, nicht versteckt, und ohne die
    Endung doppelt (ein Anhang heißt schon „plan.pdf")."""
    endung = k.get("endung") or ""
    titel = re.sub(r"[\x00-\x1f/\\]", "_", str(k.get("titel") or "")).strip().lstrip(".")
    titel = titel[:120].strip() or k.get("id") or "dokument"
    if endung and titel.lower().endswith(endung.lower()):
        return titel
    return titel + endung


def _frei(name: str, belegt: set) -> str:
    """name, sonst „name (2)", „name (3)" … — nie über eine andere Datei."""
    w = ablage.wurzel()
    stamm, endung = os.path.splitext(name)
    kandidat, i = name, 2
    while kandidat in belegt or os.path.lexists(os.path.join(w, kandidat)):
        kandidat = f"{stamm} ({i}){endung}"
        i += 1
    return kandidat


def _sha(pfad: str) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for stueck in iter(lambda: f.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


def _merken(pfad: str, name: str, fassung: int) -> dict:
    st = os.stat(pfad)
    return {"name": name, "groesse": st.st_size, "mtime_ns": st.st_mtime_ns,
            "sha": _sha(pfad), "fassung": fassung}


def _unveraendert(pfad: str, e: dict) -> bool:
    try:
        st = os.stat(pfad)
    except OSError:
        return False
    if (st.st_size, st.st_mtime_ns) == (e.get("groesse"), e.get("mtime_ns")):
        return True
    return _sha(pfad) == e.get("sha")


# ── Ein Dokument nachziehen ────────────────────────────────────────────

def _wegraeumen(doc_id: str, e: dict) -> None:
    """Die lesbare Datei eines Dokuments im Papierkorb nach .ablage/papierkorb/."""
    alt = os.path.join(ablage.wurzel(), e["name"])
    if os.path.isfile(alt) and not os.path.islink(alt):
        korb = os.path.join(_versteckt(), PAPIERKORB)
        os.makedirs(korb, exist_ok=True)
        os.replace(alt, os.path.join(korb, f"{doc_id}--{e['name']}"))


def _einen(doc_id: str, stand: dict, belegt: set) -> None:
    """Die lesbare Datei EINES Dokuments auf den Stand der Ablage bringen
    (und Sashas Änderung daran als neue Fassung übernehmen)."""
    e = stand.get(doc_id)
    if not ablage.gibt_es(doc_id):          # gab es nie / wieder entfernt
        if e:
            _wegraeumen(doc_id, e)
            stand.pop(doc_id, None)
        return
    k = ablage.kopf(doc_id)
    if ablage.im_papierkorb(k):
        if e:
            _wegraeumen(doc_id, e)
            stand.pop(doc_id, None)
        return
    w = ablage.wurzel()
    if e is None:
        vorgaenger = stand.get(k.get("ersetzt") or "")
        if vorgaenger:
            # Die neue Fassung übernimmt den Namen der alten (ersetzen()):
            # Sasha findet seine Datei, wo sie war; die alte geht in den
            # versteckten Papierkorb.
            _wegraeumen(k["ersetzt"], vorgaenger)
            stand.pop(k["ersetzt"], None)
            belegt.discard(vorgaenger["name"])
        name = _frei(vorgaenger["name"] if vorgaenger else dateiname(k), belegt)
        pfad = os.path.join(w, name)
        dateien.atomar_schreiben(pfad, ablage.roh(doc_id))
        stand[doc_id] = _merken(pfad, name, k["fassung"])
        belegt.add(name)
        return
    pfad = os.path.join(w, e["name"])
    if not os.path.lexists(pfad):
        return                              # das klärt abgleichen() (umbenannt/gelöscht)
    if not _unveraendert(pfad, e):
        # Sasha hat die Datei geändert: eine neue Fassung, seine.
        with open(pfad, "rb") as f:
            daten = f.read()
        try:
            inhalt = daten if k.get("art") in ablage.BINAER else daten.decode("utf-8")
            k = ablage.fassung_von_sasha(doc_id, inhalt)
        except (ablage.Fehler, UnicodeDecodeError) as err:
            print(f"[ablage] Änderung an {e['name']} nicht übernommen: {err}")
            return
        stand[doc_id] = _merken(pfad, e["name"], k["fassung"])
    elif e.get("fassung") != k["fassung"]:
        # Neue Fassung (KI, anderer Rechner): die Datei neu schreiben.
        dateien.atomar_schreiben(pfad, ablage.roh(doc_id))
        stand[doc_id] = _merken(pfad, e["name"], k["fassung"])


def dokument(doc_id: str) -> None:
    """Nach jedem Schreiben in der Ablage (ablage.NACH_SCHREIBEN)."""
    if getattr(_still, "an", False):
        return
    with _lock:
        stand = _stand_lesen()
        vorher = json.dumps(stand, sort_keys=True)
        _einen(doc_id, stand, {e["name"] for e in stand.values()})
        if json.dumps(stand, sort_keys=True) != vorher:
            _stand_schreiben(stand)


ablage.NACH_SCHREIBEN.append(dokument)


# ── Der ganze Ordner ───────────────────────────────────────────────────

def _fremde_dateien(bekannt: set) -> dict:
    """Dateien im sichtbaren Ordner, die keinem Dokument gehören:
    {name: (größe, mtime_ns)} — ohne Verstecktes, Verweise, Ordner."""
    raus = {}
    try:
        eintraege = list(os.scandir(ablage.wurzel()))
    except OSError:
        return raus
    for d in eintraege:
        if d.name in bekannt or d.name.startswith((".", "~$")):
            continue
        try:
            if d.is_symlink() or not d.is_file():
                continue
            st = d.stat()
        except OSError:
            continue
        raus[d.name] = (st.st_size, st.st_mtime_ns)
    return raus


def _einwerfen(name: str, merkmal: tuple) -> str | None:
    """Eine fremde Datei als Dokument übernehmen. -> id oder None."""
    if name.lower().endswith(_HALBFERTIG) or context._is_secret(name):
        return None
    if merkmal[0] == 0 or merkmal[0] > anhang.DATEI_MAX_BYTES:
        if _abgelehnt.get(name) != merkmal:
            _abgelehnt[name] = merkmal
            print(f"[ablage] {name} nicht übernommen: leer oder größer als "
                  f"{anhang.DATEI_MAX_BYTES // 1024 // 1024} MB")
        return None
    if _abgelehnt.get(name) == merkmal:
        return None
    pfad = os.path.join(ablage.wurzel(), name)
    try:
        with open(pfad, "rb") as f:
            daten = f.read()
        art, endung, text = anhang.art_fuer(name, daten)
        inhalt = daten if art in ablage.BINAER else text
        k = ablage.anlegen(name, inhalt, art, herkunft="einwurf", endung=endung,
                           quelle=name, von="sasha")
    except (OSError, anhang.Abgelehnt, ablage.Fehler) as err:
        _abgelehnt[name] = merkmal
        print(f"[ablage] {name} nicht übernommen: {err}")
        return None
    NEU.append({"id": k["id"], "titel": k["titel"], "zeit": time.time()})
    return k["id"]


def abgleichen() -> dict:
    """Den ganzen Ordner nachziehen (core/ablage_wache.py, alle paar
    Sekunden). → {neu: [id], entfernt: [id], umbenannt: [id]}."""
    bericht = {"neu": [], "entfernt": [], "umbenannt": []}
    with _lock:
        _still.an = True
        try:
            stand = _stand_lesen()
            vorher = json.dumps(stand, sort_keys=True)
            w = ablage.wurzel()
            fremd = _fremde_dateien({e["name"] for e in stand.values()})
            # 1. Verschwundene: umbenannt (gleicher Inhalt liegt unter neuem
            #    Namen) oder gelöscht (→ Papierkorb, nichts neu anlegen).
            for doc_id, e in list(stand.items()):
                if os.path.lexists(os.path.join(w, e["name"])):
                    continue
                neu = next((n for n in fremd if fremd[n][0] == e.get("groesse")
                            and _sha(os.path.join(w, n)) == e.get("sha")), None)
                if neu and ablage.gibt_es(doc_id):
                    fremd.pop(neu)
                    stand[doc_id] = dict(e, name=neu)
                    ablage.umbenennen(doc_id, os.path.splitext(neu)[0] or neu)
                    bericht["umbenannt"].append(doc_id)
                    continue
                stand.pop(doc_id)
                if ablage.gibt_es(doc_id) and not ablage.im_papierkorb(ablage.kopf(doc_id)):
                    ablage.papierkorb(doc_id, True, grund="von Sasha entfernt")
                    bericht["entfernt"].append(doc_id)
            # 2. Eingeworfenes: erst, wenn zwei Blicke dieselbe Größe sehen.
            for name, merkmal in fremd.items():
                if _gesehen.get(name) != merkmal:
                    continue
                doc_id = _einwerfen(name, merkmal)
                if doc_id:
                    k = ablage.kopf(doc_id)
                    stand[doc_id] = _merken(os.path.join(w, name), name, k["fassung"])
                    bericht["neu"].append(doc_id)
            _gesehen.clear()
            _gesehen.update(fremd)
            # 3. Jedes Dokument auf seinen Stand.
            belegt = {e["name"] for e in stand.values()}
            for doc_id in sorted(set(ablage.alle_ids()) | set(stand)):
                _einen(doc_id, stand, belegt)
            if json.dumps(stand, sort_keys=True) != vorher:
                _stand_schreiben(stand)
        finally:
            _still.an = False
    return bericht


def neu_seit(zeitpunkt: float) -> list:
    """Eingeworfenes seit zeitpunkt (Unix-Zeit): [{id, titel, zeit}]."""
    return [dict(n) for n in NEU if n["zeit"] > zeitpunkt]


def pfad(doc_id: str) -> str | None:
    """Wo die lesbare Datei liegt (oder None)."""
    e = _stand_lesen().get(doc_id)
    return os.path.join(ablage.wurzel(), e["name"]) if e else None
