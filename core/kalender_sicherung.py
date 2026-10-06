# core/kalender_sicherung.py
#
# Absicherung der Kalenderdaten gegen Verlust — alles, was nichts über
# Termine wissen muss, sondern nur über Dateien.
#
# Warum ein eigenes Modul: dieselben Bausteine (atomar schreiben, sperren,
# alte Fassung aufheben, Snapshot) brauchen der ics-Speicher, der JSON-
# Speicher, die Migration und der vdirsyncer-Wrapper. Stünden sie in
# jedem davon, gäbe es vier leicht verschiedene Fassungen derselben
# Sicherung — und die eine, die vergessen wurde, wäre die, die Daten frisst.
#
# Die große Randbedingung (memory/system/topologie.md): `data/` wird
# zwischen PC und Laptop per rsync Datei für Datei abgeglichen, NUR
# HINZUFÜGEND, neueste Datei gewinnt. Daraus folgt alles hier:
#   * Verlaufs-Dateien bekommen EINDEUTIGE Namen (Zeit + Knoten + UID),
#     dann überschreiben sich die beiden Knoten nie gegenseitig.
#   * Gelöschtes käme vom anderen Knoten zurück → Grabsteine.
#   * Kein git-Repo in data/ (refs/index würden dateiweise überschrieben);
#     der git-Spiegel lebt außerhalb (core/kalender_spiegel.py).
#
# Bauplan: memory/werkzeuge/kalender_ics_bauplan.md

import fcntl
import json
import os
import re
import socket
import tarfile
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path


class KalenderGesperrt(Exception):
    """Eine Schreiboperation wurde absichtlich verweigert (Massenlöschung,
    Rückfall-Sperre, Sperre nicht zu bekommen). Wer das fängt, soll es
    MELDEN, nicht verschlucken — die Weigerung ist die Information."""


# ── Atomar schreiben ────────────────────────────────────────────────────

# Zog am 2026-10-07 nach core/dateien.py (Fundament), weil Listen, Notizen,
# Messreihen und der Key-Speicher denselben Schutz brauchen. Der Name bleibt
# hier, damit kalender_json/_ics/_migration unverändert weiterlaufen.
from dateien import atomar_schreiben  # noqa: E402,F401

# ── Sperre zwischen Prozessen ───────────────────────────────────────────

@contextmanager
def dateisperre(pfad: Path, warten_s: float = 15.0):
    """Exklusive Sperre über eine Sperrdatei (flock).

    Der threading.Lock in kalender.py schützt nur innerhalb EINES Prozesses.
    Das Backend, das Migrations-Skript und der vdirsyncer-Wrapper sind aber
    drei Prozesse, die denselben Ordner anfassen. flock wird vom Kernel beim
    Prozessende freigegeben — ein abgestürzter Schreiber hinterlässt also
    keine ewige Sperre.

    Bekommt man die Sperre nicht in `warten_s` Sekunden → KalenderGesperrt,
    statt ewig zu hängen (ein hängender Request ist schlimmer als ein
    gemeldeter Fehler).
    """
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(pfad, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        ende = time.monotonic() + warten_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > ende:
                    raise KalenderGesperrt(
                        f"Kalender-Sperre {pfad} nach {warten_s:.0f} s nicht frei")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


# ── Namen ───────────────────────────────────────────────────────────────

def knoten() -> str:
    """Name dieses Rechners, dateinamen-tauglich. Steht in jedem Verlaufs-
    und Snapshot-Namen, damit PC und Laptop nie denselben Namen erzeugen."""
    return sicherer_name(socket.gethostname() or "knoten")


def sicherer_name(text: str) -> str:
    """Alles außer Buchstaben, Ziffern, '@', '.', '-' wird '_'. Kein '~' —
    das ist unser Trennzeichen in Verlaufs-Namen."""
    s = re.sub(r"[^A-Za-z0-9@.\-]", "_", str(text))
    return s.strip(".") or "_"


def _zeitstempel(jetzt: datetime | None = None) -> str:
    jetzt = jetzt or datetime.now(timezone.utc)
    return jetzt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


# ── Verlauf: jede alte Fassung aufheben ─────────────────────────────────
#
# Name:  <Verlauf>/<JJJJ-MM>/<zeit>~<knoten>~<ebene>~<uid>~<aktion><endung>
# Unterordner pro Monat, damit kein Ordner über die Jahre zehntausende
# Dateien sammelt.

VERLAUF_AKTIONEN = ("geaendert", "geloescht", "geist", "vor-wiederherstellen")


def verlauf_ablegen(verlauf_dir: Path, inhalt, ebene: str, uid: str,
                    aktion: str, endung: str = ".ics",
                    jetzt: datetime | None = None) -> Path:
    """Legt `inhalt` (die ALTE Fassung) unter eindeutigem Namen ab und gibt
    den Pfad zurück. Wird VOR dem Überschreiben/Löschen gerufen — schlägt
    es fehl, fliegt die Ausnahme, und der Aufrufer schreibt gar nicht erst.
    Lieber ein verweigertes Schreiben als eine Änderung ohne Rückweg."""
    jetzt = jetzt or datetime.now(timezone.utc)
    ordner = Path(verlauf_dir) / jetzt.astimezone(timezone.utc).strftime("%Y-%m")
    basis = "~".join([_zeitstempel(jetzt), knoten(), sicherer_name(ebene),
                      sicherer_name(uid), sicherer_name(aktion)])
    ziel = ordner / f"{basis}{endung}"
    n = 1
    while ziel.exists():                 # gleiche Mikrosekunde: Zähler dran
        ziel = ordner / f"{basis}-{n}{endung}"
        n += 1
    atomar_schreiben(ziel, inhalt)
    return ziel


def verlauf_liste(verlauf_dir: Path, uid: str | None = None) -> list[dict]:
    """Alle abgelegten Fassungen, neueste zuerst.
    -> [{pfad, zeit, knoten, ebene, uid, aktion}]. `uid` filtert (über den
    dateinamen-sicheren Namen, wie er beim Ablegen gebildet wurde)."""
    raus = []
    wurzel = Path(verlauf_dir)
    if not wurzel.exists():
        return raus
    want = sicherer_name(uid) if uid else None
    for p in wurzel.glob("*/*"):
        if p.parent.name == "grabsteine" or not p.is_file():
            continue
        teile = p.stem.split("~")
        if len(teile) != 5:
            continue
        zeit, kn, ebene, u, aktion = teile
        if want and u != want:
            continue
        raus.append({"pfad": p, "zeit": zeit, "knoten": kn, "ebene": ebene,
                     "uid": u, "aktion": re.sub(r"-\d+$", "", aktion)})
    raus.sort(key=lambda d: (d["zeit"], d["pfad"].name), reverse=True)
    return raus


# ── Grabsteine: Gelöschtes bleibt gelöscht, auch über den Sync ──────────
#
# Der Sync löscht nie. Löscht der Laptop einen Termin, hat der PC die
# Datei noch, und der nächste Abgleich brächte sie zurück — ein Termin, den
# man gelöscht hat, stünde wieder da. Der Grabstein ist eine NEUE Datei,
# und neue Dateien überträgt der Sync zuverlässig.

def _grab_dir(verlauf_dir: Path) -> Path:
    return Path(verlauf_dir) / "grabsteine"


def grabstein_setzen(verlauf_dir: Path, uid: str, ebene: str,
                     jetzt: datetime | None = None) -> None:
    jetzt = (jetzt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    atomar_schreiben(
        _grab_dir(verlauf_dir) / f"{sicherer_name(uid)}.json",
        json.dumps({"uid": uid, "ebene": ebene, "knoten": knoten(),
                    "geloescht_um": jetzt.isoformat()},
                   ensure_ascii=False, indent=1))


def grabsteine_lesen(verlauf_dir: Path) -> dict:
    """{uid: geloescht_um (aware datetime, UTC)}. Kaputte Grabsteine werden
    übersprungen — ein unlesbarer Grabstein darf nie einen Termin
    verstecken."""
    raus = {}
    d = _grab_dir(verlauf_dir)
    if not d.exists():
        return raus
    for p in d.glob("*.json"):
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
            raus[g["uid"]] = datetime.fromisoformat(g["geloescht_um"])
        except Exception:
            continue
    return raus


def grabstein_entfernen(verlauf_dir: Path, uid: str) -> None:
    p = _grab_dir(verlauf_dir) / f"{sicherer_name(uid)}.json"
    try:
        p.unlink()
    except FileNotFoundError:
        pass


# ── Massenlösch-Sperre ──────────────────────────────────────────────────

def loeschungen_pruefen(anzahl: int, grenze: int, erlaubt: bool = False) -> None:
    """Mehr als `grenze` Löschungen in EINER Operation → verweigern.

    Kein normaler Handgriff löscht viele Termine auf einmal (ein Tag, eine
    Routine, eine Spanne). Viele auf einmal heißt fast immer: ein Fehler —
    ein Teilstring, der zu viel trifft, ein halb gelesener Ordner, ein
    Programmfehler. Dann lieber gar nichts schreiben und laut sein.
    Wiederherstellen und der Migrations-Rückweg dürfen das ausdrücklich
    (`erlaubt=True`)."""
    if not erlaubt and anzahl > grenze:
        raise KalenderGesperrt(
            f"Massenlösch-Sperre: {anzahl} Termine in einem Schritt löschen "
            f"(erlaubt sind höchstens {grenze}) — nichts geschrieben.")


# ── Tägliche Snapshots ──────────────────────────────────────────────────

def snapshot_machen(snap_dir: Path, basis: Path, quellen: list,
                    heute: date | None = None) -> Path | None:
    """Ein tar.gz mit `quellen` (Pfade unter `basis`), höchstens EINES pro
    Tag und Knoten. Gibt den Pfad zurück, wenn heute einer entstand.

    Gerufen VOR der ersten Änderung des Tages: der Snapshot hält also den
    Stand fest, bevor heute irgendetwas passiert ist. Liegen die Quellen
    noch gar nicht vor (frischer Kalender), entsteht nichts."""
    heute = heute or date.today()
    snap_dir = Path(snap_dir)
    ziel = snap_dir / f"kalender_{heute.isoformat()}_{knoten()}.tar.gz"
    if ziel.exists():
        return None
    da = [Path(q) for q in quellen if Path(q).exists()]
    if not da:
        return None
    snap_dir.mkdir(parents=True, exist_ok=True)
    tmp = snap_dir / f".{ziel.name}.{os.getpid()}.tmp"
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for q in da:
                tar.add(q, arcname=str(q.relative_to(basis)),
                        filter=_ohne_sperre)
        os.replace(tmp, ziel)
    finally:
        if tmp.exists():
            tmp.unlink()
    return ziel


def _ohne_sperre(info):
    # Sperr- und Temp-Dateien gehören nicht in ein Backup.
    name = os.path.basename(info.name)
    if name.endswith(".lock") or name.endswith(".tmp"):
        return None
    return info


def snapshots_rotieren(snap_dir: Path, heute: date | None = None,
                       tage: int = 30, monate: int = 24) -> list:
    """Alte Snapshots wegräumen: behalten werden die letzten `tage` Tage und
    jeder Monatserste der letzten `monate` Monate.

    Bewusst für ALLE Knoten, nicht nur den eigenen: der Sync löscht nie,
    also hätte sonst jeder Knoten die alten Snapshots des anderen für immer.
    Beide wenden dieselbe Regel an, also sind sie sich einig."""
    heute = heute or date.today()
    weg = []
    d = Path(snap_dir)
    if not d.exists():
        return weg
    for p in d.glob("kalender_*.tar.gz"):
        m = re.match(r"kalender_(\d{4}-\d{2}-\d{2})_", p.name)
        if not m:
            continue
        try:
            tag = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        alter = (heute - tag).days
        if alter <= tage:
            continue
        if tag.day == 1 and alter <= monate * 31:
            continue
        p.unlink()
        weg.append(p)
    return weg


def snapshot_liste(snap_dir: Path) -> list:
    d = Path(snap_dir)
    return sorted(d.glob("kalender_*.tar.gz"), reverse=True) if d.exists() else []


def snapshot_auspacken(snap: Path, ziel: Path) -> None:
    """Packt einen Snapshot nach `ziel` aus (für Wiederherstellen). Einträge
    mit '..' oder absolutem Pfad werden abgelehnt — ein Backup darf beim
    Auspacken nie aus seinem Zielordner ausbrechen."""
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    with tarfile.open(snap, "r:gz") as tar:
        for m in tar.getmembers():
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                raise KalenderGesperrt(f"unsicherer Pfad im Snapshot: {m.name}")
        tar.extractall(ziel, filter="data")
