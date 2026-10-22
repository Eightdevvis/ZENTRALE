"""`zentrale update` — die neueste Fassung holen und daneben installieren.

Aufbau eines installierten Hubs (gleich in deploy/install.sh):

    ~/.local/share/zentrale/            HEIM (Env ZENTRALE_HEIM für Tests)
      data/                            die Daten — überleben jede Fassung
      hub/<fassung>/                   ein entpacktes Paket + eigenes venv
      hub/<fassung>/data -> ../../data
      hub/aktuell -> <fassung>         der Umschalter (atomar ersetzt)
    ~/.local/bin/zentrale -> HEIM/hub/aktuell/bin/zentrale

Die alte Fassung bleibt bis zum nächsten Update liegen (Rückweg: den
Verweis `aktuell` zurückdrehen)."""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile

from zentrale_cli import WURZEL
from zentrale_cli.texte import t

import cloud_api   # noqa: E402
import knoten      # noqa: E402
import konto       # noqa: E402

_FASSUNG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def heim() -> str:
    return os.path.expanduser(os.environ.get("ZENTRALE_HEIM") or "~/.local/share/zentrale")


def installiert(wurzel=WURZEL) -> bool:
    hub = os.path.realpath(os.path.join(heim(), "hub"))
    return os.path.realpath(wurzel).startswith(hub + os.sep)


def _groesse(n):
    return f"{n / 1e6:.1f} MB" if n else "?"


def venv_bauen(ordner):
    """venv + requirements-basis.txt. Eigene Funktion, damit Tests sie ersetzen."""
    subprocess.run([sys.executable, "-m", "venv", os.path.join(ordner, "venv")], check=True)
    subprocess.run([os.path.join(ordner, "venv", "bin", "pip"), "install", "-q", "-r",
                    os.path.join(ordner, "requirements-basis.txt")], check=True)


def entpacken(tar_pfad, ziel):
    """Paket nach `ziel` entpacken. Das Paket hat genau einen obersten Ordner
    (zentrale-<fassung>/); Pfade nach draußen lehnt der Filter 'data' ab."""
    zwischen = ziel + ".teil"
    shutil.rmtree(zwischen, ignore_errors=True)
    os.makedirs(zwischen)
    with tarfile.open(tar_pfad, "r:gz") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(zwischen, filter="data")
        else:                       # Python 3.11.0–3.11.3: selbst prüfen
            for m in tar.getmembers():
                if m.name.startswith("/") or ".." in m.name.split("/") or \
                        not (m.isfile() or m.isdir()):
                    raise ValueError(f"Unsafe entry in the package: {m.name}")
            tar.extractall(zwischen)
    oben = os.listdir(zwischen)
    if len(oben) != 1 or not os.path.isdir(os.path.join(zwischen, oben[0])):
        shutil.rmtree(zwischen, ignore_errors=True)
        raise ValueError("The package has an unexpected layout.")
    shutil.rmtree(ziel, ignore_errors=True)
    os.replace(os.path.join(zwischen, oben[0]), ziel)
    os.rmdir(zwischen)


def umschalten(fassung):
    """hub/aktuell atomar auf <fassung> drehen."""
    hub = os.path.join(heim(), "hub")
    neu = os.path.join(hub, ".aktuell-neu")
    if os.path.lexists(neu):
        os.remove(neu)
    os.symlink(fassung, neu)
    os.replace(neu, os.path.join(hub, "aktuell"))


def aufraeumen(behalten):
    hub = os.path.join(heim(), "hub")
    for name in os.listdir(hub):
        p = os.path.join(hub, name)
        if name in behalten or name.startswith(".") or os.path.islink(p):
            continue
        shutil.rmtree(p, ignore_errors=True)


def update(term, venv=venv_bauen, wurzel=WURZEL):
    if not installiert(wurzel):
        term.sag(t("upd_dev", wurzel=wurzel))
        return 1
    if not konto.angemeldet():
        term.sag(t("upd_need_login"))
        return 1
    term.sag(t("upd_check"), "blass")
    c = konto.client()
    info = c.get("/v1/paket")
    neu, sha, groesse = str(info.get("version", "")), str(info.get("sha256", "")).lower(), info.get("groesse")
    if not _FASSUNG.match(neu) or len(sha) != 64:
        raise cloud_api.CloudFehler("The cloud sent an unreadable package description.")
    alt = knoten.fassung(wurzel)
    if neu == alt:
        term.sag(t("upd_current", fassung=alt), "gut")
        return 0
    term.sag(t("upd_found", neu=neu, alt=alt, groesse=_groesse(groesse)))
    term.sag(t("upd_download"), "blass")
    daten = c.bytes_holen(f"/v1/paket/{neu}.tar.gz")
    if hashlib.sha256(daten).hexdigest() != sha:
        term.sag(t("upd_bad_sha"), "fehler")
        return 1
    hub = os.path.join(heim(), "hub")
    os.makedirs(hub, exist_ok=True)
    tar_pfad = os.path.join(hub, f".lade-{neu}.tar.gz")
    with open(tar_pfad, "wb") as f:
        f.write(daten)
    ziel = os.path.join(hub, neu)
    try:
        entpacken(tar_pfad, ziel)
    finally:
        os.remove(tar_pfad)
    os.makedirs(os.path.join(heim(), "data"), exist_ok=True)
    if not os.path.lexists(os.path.join(ziel, "data")):
        os.symlink(os.path.join("..", "..", "data"), os.path.join(ziel, "data"))
    vorlage, daten_ascii = os.path.join(ziel, "mitgeliefert", "ascii"), os.path.join(heim(), "data", "ascii")
    if os.path.isdir(vorlage) and not os.path.exists(daten_ascii):
        shutil.copytree(vorlage, daten_ascii)
    term.sag(t("upd_venv"), "blass")
    venv(ziel)
    alt_name = os.path.basename(os.path.realpath(wurzel))
    umschalten(neu)
    aufraeumen({neu, alt_name})
    term.sag(t("upd_ok", neu=neu, alt_ordner=os.path.join(hub, alt_name)), "gut")
    return 0
