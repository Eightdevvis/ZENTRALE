#!/usr/bin/env python3
"""Holt auf einem AUSSENPOSTEN das zugeschnittene Paket vom Backend-Host.

Laeuft per Cron (deploy/aussenposten-update.cron) auf dem Knoten selbst —
Pi an der Wand, spaeter einer pro Raum. Reine Standardbibliothek, damit es
unter dem System-Python arbeitet: der venv des Knotens haelt nur pygame &
Co, und ein Updater, der seinen eigenen venv braucht, kann ihn nicht
reparieren.

Ablauf:
  1. Manifest vom PC holen (Version = Hash ueber den Paket-Inhalt).
  2. Mit der lokal installierten Version vergleichen. Gleich -> fertig,
     nichts angefasst. Das ist der Normalfall bei jedem Lauf.
  3. Sonst das tar.gz ziehen, in einen Nebenordner auspacken, pruefen.
  4. Datei fuer Datei atomar an ihren Platz schieben (schreiben + rename),
     Reste des Vorgaengerpakets aufraeumen.
  5. Wenn sich die Requirements-Liste geaendert hat: pip nachziehen.

Warum PULL und nicht PUSH: der Knoten fragt beim PC nach, nicht umgekehrt.
Das ist dieselbe Richtung wie alles andere zwischen PC und Pi (siehe
memory/system/topologie.md). Ein Knoten, der aus war, holt beim naechsten
Lauf von selbst auf; der PC braucht keine Schluessel nach draussen und keine
Liste, welche Knoten es ueberhaupt gibt. Beim zehnten Bildschirm ist das der
Unterschied zwischen "geht einfach" und "Inventar pflegen".

Aufruf:
  aussenposten_update.py [--url http://192.168.50.1:5000] [--ziel /opt/zentrale]
  aussenposten_update.py --pruefen    # nur schauen, nichts installieren
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

# Merkzettel des Knotens: welche Version liegt hier, und aus welchen Dateien
# bestand sie. Die Dateiliste brauchen wir, um beim naechsten Mal Reste
# aufzuraeumen — sonst sammelt ein Knoten ueber Jahre Karteileichen an.
STAND_DATEI = ".aussenposten_stand.json"
REQ = "deploy/requirements-aussenposten.txt"


def log(text, logdatei=None):
    zeile = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
    print(zeile, flush=True)
    if logdatei:
        try:
            with open(logdatei, "a", encoding="utf-8") as f:
                f.write(zeile + "\n")
        except OSError:
            pass


def hole(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read(), dict(r.headers)


def stand_lesen(ziel):
    try:
        with open(os.path.join(ziel, STAND_DATEI), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"version": None, "dateien": []}


def stand_schreiben(ziel, version, dateien):
    pfad = os.path.join(ziel, STAND_DATEI)
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": version, "dateien": sorted(dateien),
                   "installiert": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  f, indent=2)
    os.replace(tmp, pfad)


def sicher(name):
    """Darf dieser Archiv-Eintrag ausgepackt werden?

    Ein tar darf theoretisch '../../etc/passwd' oder '/etc/passwd' enthalten
    und beim Auspacken aus dem Zielordner ausbrechen. Wir packen nur, was
    relativ ist und nirgends '..' benutzt.
    """
    if name.startswith("/") or os.path.isabs(name):
        return False
    teile = name.replace("\\", "/").split("/")
    return ".." not in teile and "" not in teile[:-1]


def installieren(daten, ziel, logdatei):
    """Paket auspacken und an Ort und Stelle schieben. Gibt die Dateiliste."""
    tmpdir = tempfile.mkdtemp(prefix=".aussenposten-", dir=ziel)
    try:
        with tarfile.open(fileobj=io.BytesIO(daten), mode="r:gz") as tar:
            mitglieder = []
            for m in tar.getmembers():
                if not m.isfile():
                    continue           # Verzeichnisse legen wir selbst an
                if not sicher(m.name):
                    log("ABGELEHNT (unsicherer Pfad): %s" % m.name, logdatei)
                    continue
                mitglieder.append(m)
            # filter='data' ist ab Python 3.12 der empfohlene und ab 3.14 der
            # Default-Modus: er lehnt absolute Pfade, '..', Links und
            # Sonderrechte ab. Wir pruefen die Namen oben schon selbst; das
            # hier ist der Guertel zum Hosentraeger — und nimmt die
            # DeprecationWarning weg, die auf dem Pi im Log stand.
            try:
                tar.extractall(tmpdir, members=mitglieder, filter="data")
            except TypeError:
                tar.extractall(tmpdir, members=mitglieder)   # Python < 3.12

        geschrieben = []
        for m in mitglieder:
            quelle = os.path.join(tmpdir, m.name)
            zielpfad = os.path.join(ziel, m.name)
            os.makedirs(os.path.dirname(zielpfad), exist_ok=True)
            # Atomar: erst danebenlegen, dann umbenennen. Ein Abbruch
            # mittendrin hinterlaesst so nie eine halb geschriebene Datei,
            # die der Knoten beim naechsten Start ausfuehren wuerde.
            tmpziel = zielpfad + ".neu"
            shutil.copy2(quelle, tmpziel)
            os.replace(tmpziel, zielpfad)
            geschrieben.append(m.name)
        return geschrieben
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def aufraeumen(ziel, alt, neu, logdatei):
    """Dateien entfernen, die im Vorgaengerpaket waren und jetzt nicht mehr."""
    for rel in sorted(set(alt) - set(neu)):
        if not sicher(rel):
            continue
        pfad = os.path.join(ziel, rel)
        try:
            if os.path.isfile(pfad):
                os.remove(pfad)
                log("entfernt (nicht mehr im Paket): %s" % rel, logdatei)
        except OSError as exc:
            log("konnte %s nicht entfernen: %s" % (rel, exc), logdatei)


def _datei_inhalt(pfad):
    try:
        with open(pfad, "rb") as f:
            return f.read()
    except OSError:
        return None


def _venv(ziel):
    """(python, pip) des Knoten-venv, oder (None, None).

    Der Ordner heisst nicht ueberall gleich: PC/Laptop 'venv', der Pi '.venv'.
    """
    for name in (".venv", "venv"):
        py = os.path.join(ziel, name, "bin", "python")
        pip = os.path.join(ziel, name, "bin", "pip")
        if os.path.exists(py) and os.path.exists(pip):
            return py, pip
    return None, None


def _normal(name):
    """Paketnamen vergleichbar machen (PEP 503: Gross/Klein und -_. egal)."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _gefordert(req_pfad):
    """Paketnamen aus der Requirements-Datei. Kommentare und Versions-
    Angaben fliegen raus — wir wollen nur wissen, WAS da sein muss."""
    namen = []
    try:
        with open(req_pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.split("#")[0].strip()
                if not zeile or zeile.startswith("-"):
                    continue
                namen.append(_normal(re.split(r"[<>=!~;\[]", zeile)[0]))
    except OSError:
        pass
    return [n for n in namen if n]


def _fehlende(py, req_pfad):
    """Welche geforderten Pakete fehlen im venv? Rein lokal, ohne Netz."""
    gefordert = _gefordert(req_pfad)
    if not gefordert:
        return []
    code = ("import importlib.metadata as m, re, json;"
            "print(json.dumps([re.sub(r'[-_.]+','-',d.metadata['Name'] or '')"
            ".lower() for d in m.distributions()]))")
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                           timeout=60)
        da = set(json.loads(r.stdout or "[]"))
    except Exception:
        return gefordert          # nicht feststellbar -> lieber installieren
    return [n for n in gefordert if n not in da]


def pip_nachziehen(ziel, logdatei, grund):
    """Requirements installieren — nur wenn ein venv existiert."""
    py, pip = _venv(ziel)
    if not pip:
        log("kein venv gefunden — pip-Schritt uebersprungen (%s)" % grund, logdatei)
        return
    req = os.path.join(ziel, REQ)
    log("%s -> pip install -r %s" % (grund, REQ), logdatei)
    r = subprocess.run([pip, "install", "-q", "-r", req],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log("pip FEHLGESCHLAGEN: %s" % (r.stderr or "").strip()[:500], logdatei)
    else:
        log("pip fertig", logdatei)


def abhaengigkeiten_angleichen(ziel, logdatei, req_vorher):
    """Dafuer sorgen, dass die Pakete des Knotens zur Liste passen.

    Ein Paket ist erst nutzbar, wenn auch seine Pakete da sind. Zwei Gruende
    zu installieren: die Liste hat sich geaendert (req_vorher != jetzt), oder
    es fehlt schlicht etwas. Der zweite Fall ist der wichtige — auf einem
    frisch bespielten Knoten aendert sich die Liste NIE, sie kommt ja fertig
    im Paket mit.

    req_vorher=None heisst: kein Vergleich moeglich/noetig, nur nachsehen was
    fehlt. Der Fehlt-Check laeuft lokal ueber importlib.metadata im venv des
    Knotens — kein Netz, keine Sekunde.
    """
    req_pfad = os.path.join(ziel, REQ)
    if req_vorher is not None and _datei_inhalt(req_pfad) != req_vorher:
        pip_nachziehen(ziel, logdatei, "Requirements-Liste geaendert")
        return
    py, _ = _venv(ziel)
    if not py:
        return
    fehlt = _fehlende(py, req_pfad)
    if fehlt:
        pip_nachziehen(ziel, logdatei,
                       "fehlende Pakete: %s" % ", ".join(sorted(fehlt)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("ZENTRALE_URL",
                                                    "http://192.168.50.1:5000"))
    ap.add_argument("--ziel", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--log", default=os.path.expanduser(
        "~/.aussenposten_update.log"))
    ap.add_argument("--pruefen", action="store_true",
                    help="nur vergleichen, nichts installieren")
    ap.add_argument("--neu", action="store_true",
                    help="neu installieren, auch wenn die Version stimmt "
                         "(repariert lokal veraenderte Dateien — der normale "
                         "Lauf merkt davon nichts, er vergleicht nur Versionen)")
    a = ap.parse_args()

    basis = a.url.rstrip("/")
    ziel = os.path.abspath(a.ziel)
    logdatei = a.log

    try:
        roh, _ = hole(basis + "/api/aussenposten/manifest", timeout=10)
        fern = json.loads(roh.decode("utf-8"))
    except Exception as exc:
        # Backend aus oder Netz weg ist der Normalfall, nicht der Notfall:
        # leise scheitern, beim naechsten Lauf nochmal. Nur nicht so leise,
        # dass man es im Log nicht findet.
        log("Backend nicht erreichbar (%s): %s" % (basis, exc), logdatei)
        return 0

    hier = stand_lesen(ziel)
    if hier.get("version") == fern.get("version") and not a.neu:
        if a.pruefen:
            log("aktuell (%s)" % fern.get("version"), logdatei)
            return 0
        # Paket ist aktuell — die PAKETE trotzdem pruefen. Sonst konvergiert
        # ein Knoten nie: genau das ist beim Pi passiert. Der erste Lauf lief
        # noch mit dem alten Updater (ohne Abhaengigkeits-Pruefung) und
        # installierte das Paket; ab dem zweiten Lauf stimmte die Version, es
        # wurde frueh ausgestiegen — und der venv blieb fuer immer leer.
        # Ein Abgleich muss den SOLL-Zustand herstellen, nicht nur Diffs
        # nachfahren. Der Check ist rein lokal und kostet nichts.
        abhaengigkeiten_angleichen(ziel, logdatei, None)
        return 0

    log("neue Version: %s -> %s (%s Dateien, %s KB)"
        % (hier.get("version") or "keine", fern.get("version"),
           fern.get("dateien"), round(fern.get("bytes", 0) / 1024)), logdatei)
    if a.pruefen:
        return 0

    req_vorher = _datei_inhalt(os.path.join(ziel, REQ))

    try:
        daten, kopf = hole(basis + "/api/aussenposten/paket", timeout=120)
    except Exception as exc:
        log("Download fehlgeschlagen: %s" % exc, logdatei)
        return 1

    geliefert = kopf.get("X-Paket-Version")
    if geliefert and geliefert != fern.get("version"):
        # Zwischen Manifest und Download hat sich der Stand geaendert.
        # Nicht schlimm — wir nehmen, was wirklich kam, und schreiben DIESE
        # Version in den Merkzettel, sonst laeuft der Knoten ewig im Kreis.
        log("Stand hat sich waehrend des Downloads geaendert: %s"
            % geliefert, logdatei)

    try:
        dateien = installieren(daten, ziel, logdatei)
    except Exception as exc:
        log("Installation fehlgeschlagen: %s" % exc, logdatei)
        return 1

    aufraeumen(ziel, hier.get("dateien") or [], dateien, logdatei)
    stand_schreiben(ziel, geliefert or fern.get("version"), dateien)
    log("installiert: %d Dateien" % len(dateien), logdatei)

    abhaengigkeiten_angleichen(ziel, logdatei, req_vorher)
    return 0


if __name__ == "__main__":
    sys.exit(main())
