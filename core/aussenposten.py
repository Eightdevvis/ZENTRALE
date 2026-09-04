"""Aussenposten-Pakete: was ein Knoten ohne Backend bekommt, geschnuert.

Ein Aussenposten (der Pi an der Wand, spaeter je einer pro Raum) hostet kein
Backend. Er ist Anzeige, Ton und Sensorik; gerechnet wird auf dem PC. Frueher
holte er sich seinen Code per `git pull` — das brachte den ganzen getrackten
Baum (~34 MB, davon 29 MB Kartendaten), verlangte einen Git-Clone und einen
GitHub-Zugang auf jedem Knoten und einen manuellen RELEASE-Bump als Ausloeser.

Stattdessen: der Backend-Host schnuert aus der Positivliste
`deploy/aussenposten.txt` ein Paket, der Knoten holt es sich ueber HTTP ab.

  * **Zugeschnitten** — nur was der Knoten wirklich ausfuehrt (~660 KB).
  * **Inhalts-adressiert** — die Version ist ein Hash ueber den Inhalt. Kein
    Mensch muss eine Zahl hochziehen und keiner kann vergessen, es zu tun:
    aendert sich eine Datei, aendert sich die Version, der Knoten merkt es.
  * **Pull, nicht Push** — der Knoten fragt beim PC nach. Das ist dieselbe
    Richtung wie alles andere zwischen PC und Pi (siehe
    memory/system/topologie.md): ein Knoten, der aus war, holt beim naechsten
    Anlauf von selbst auf, und der PC braucht keine Schluessel nach draussen
    und keine Liste, wer alles existiert.

Reine Standardbibliothek — das Gegenstueck auf dem Knoten
(`scripts/aussenposten_update.py`) laeuft unter dem System-Python ohne venv.
"""

import gzip
import hashlib
import io
import json
import os
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTE = os.path.join(ROOT, "deploy", "aussenposten.txt")

# Nichts davon gehoert je in ein Paket: Python-Cache und Editor-Reste blaehen
# nur auf und machen die Version wackelig (Cache aendert sich ohne Quelltext).
IGNORIEREN = ("__pycache__", ".pyc", ".pyo", ".swp", "~")


def _uebergehen(pfad):
    return any(t in pfad if t.startswith("__") else pfad.endswith(t)
               for t in IGNORIEREN)


def liste_lesen(pfad=None):
    """Die Positivliste als Pfade relativ zur Projektwurzel.

    Kommentare ('#') und Leerzeilen fliegen raus — die Datei ist bewusst
    ausfuehrlich kommentiert, sie erklaert ja, WAS ein Aussenposten ist.
    """
    pfad = pfad or LISTE
    eintraege = []
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#"):
                eintraege.append(zeile)
    return eintraege


def dateien(root=None):
    """Die Positivliste zu einer sortierten Liste echter Dateien aufloesen.

    Verzeichnis-Eintraege werden rekursiv expandiert. Sortiert, damit Paket
    und Version bei gleichem Inhalt Byte fuer Byte gleich rauskommen.
    Rueckgabe: [(relpath, abspath), ...]
    """
    root = root or ROOT
    raus = []
    for eintrag in liste_lesen():
        abs_ = os.path.join(root, eintrag)
        if os.path.isdir(abs_):
            for basis, verzeichnisse, namen in os.walk(abs_):
                verzeichnisse[:] = [d for d in verzeichnisse
                                    if not _uebergehen(d)]
                for name in namen:
                    voll = os.path.join(basis, name)
                    if not _uebergehen(voll):
                        raus.append((os.path.relpath(voll, root), voll))
        elif os.path.isfile(abs_) and not _uebergehen(abs_):
            raus.append((eintrag, abs_))
        # Fehlende Eintraege werden still uebergangen: die Liste darf Dinge
        # nennen, die es auf diesem Host (noch) nicht gibt, ohne dass ein
        # Knoten deshalb gar kein Update mehr bekommt.
    raus.sort()
    return raus


def _datei_hash(pfad):
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def manifest(root=None):
    """Was gerade zu holen waere — ohne das Paket zu bauen.

    Der Knoten fragt das alle paar Minuten ab; es darf also billig sein.
    `version` ist ein Hash ueber Pfade UND Inhalte: zwei Hosts mit demselben
    Stand liefern dieselbe Version, und jede Aenderung faellt auf.
    """
    eintraege = dateien(root)
    gesamt = hashlib.sha256()
    bytes_ = 0
    for rel, abs_ in eintraege:
        gesamt.update(rel.encode("utf-8"))
        gesamt.update(b"\0")
        gesamt.update(_datei_hash(abs_).encode("ascii"))
        gesamt.update(b"\n")
        bytes_ += os.path.getsize(abs_)
    return {
        "version": gesamt.hexdigest()[:16],
        "dateien": len(eintraege),
        "bytes": bytes_,
        "gebaut": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def paket(root=None):
    """Das Paket als tar.gz-Bytes.

    Deterministisch: sortierte Reihenfolge, feste mtime/uid/gid und
    `mtime=0` im gzip-Kopf. Gleicher Inhalt -> gleiche Bytes. Ohne das
    stuende in jedem Archiv eine andere Zeit und nichts liesse sich
    vergleichen.
    """
    root = root or ROOT
    puffer = io.BytesIO()
    # gzip schreibt sonst die BAUZEIT in seinen Kopf — dann waeren zwei
    # Archive mit identischem Inhalt verschiedene Bytes. mtime=0 dagegen.
    gz = gzip.GzipFile(fileobj=puffer, mode="wb", compresslevel=6, mtime=0)
    with tarfile.open(fileobj=gz, mode="w",
                      format=tarfile.GNU_FORMAT) as tar:
        for rel, abs_ in dateien(root):
            info = tar.gettarinfo(abs_, arcname=rel)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with open(abs_, "rb") as f:
                tar.addfile(info, f)
    gz.close()
    return puffer.getvalue()
