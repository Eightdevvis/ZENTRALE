"""Die Verteilung (memory/betrieb/verteilung.md): .deb, PKGBUILD, der Schalter
in deploy/verteilung.toml und wie `zentrale update` sich bei apt/pacman verhält.

Alles aus EINEM tar.gz (scripts/paket_bauen.py) — was dort nie hinein darf
(data/, memory/, tests/, Schlüssel), darf auch ins .deb nicht."""
import fnmatch
import functools
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))   # hinten: scripts/abgleich.py verdeckt sonst den Kern
import arch_bauen   # noqa: E402
import deb_bauen    # noqa: E402
import paket_bauen  # noqa: E402
import verteilung   # noqa: E402

PRIVAT = paket_bauen.verteilung_lesen()
PY = sys.executable

braucht_dpkg = pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb fehlt")


@pytest.fixture(scope="module")
def gebaut(tmp_path_factory):
    """Ein tar.gz (Fassung 9.9.9) und daraus .deb und PKGBUILD — einmal je Modul."""
    ziel = tmp_path_factory.mktemp("verteilung")
    tar, neueste = paket_bauen.bauen("9.9.9", ziel_ordner=str(ziel), stufe=1, verteilung=PRIVAT)
    deb = deb_bauen.bauen(tar, "9.9.9", str(ziel), PRIVAT) if shutil.which("dpkg-deb") else None
    arch = arch_bauen.bauen(tar, neueste, str(ziel), PRIVAT)
    return {"ziel": ziel, "tar": tar, "neueste": neueste, "deb": deb, "arch": arch}


def _tar_namen(tar):
    with tarfile.open(tar) as t:
        return {n.split("/", 1)[1] for n in t.getnames() if "/" in n}


# ── .deb ───────────────────────────────────────────────────────────────

@braucht_dpkg
def test_deb_inhalt_gleich_dem_tar_ohne_daten_und_schluessel(gebaut):
    r = subprocess.run(["dpkg-deb", "-c", gebaut["deb"]], capture_output=True, text=True, check=True)
    eintraege = {}
    for z in r.stdout.splitlines():
        teile = z.split()
        eintraege[teile[5].lstrip(".")] = teile[0]
    dateien = {p for p, m in eintraege.items() if not m.startswith("d")}
    for p in dateien:
        assert p.startswith(("/usr/lib/zentrale/", "/usr/share/doc/zentrale/")) or p == "/usr/bin/zentrale", p
    innen = {p[len("/usr/lib/zentrale/"):] for p in dateien if p.startswith("/usr/lib/zentrale/")}
    for n in innen:
        assert not n.startswith(("data/", "memory/", "tests/", "venv/", "services/", ".git")), n
        for verboten in ("*.enc", "ai_config.json", "*.schluessel", "*.pyc", "*.key", ".env"):
            assert not fnmatch.fnmatch(n.rsplit("/", 1)[-1], verboten), n
    assert innen == _tar_namen(gebaut["tar"]) | {"KANAL"}
    assert eintraege["/usr/bin/zentrale"] == "-rwxr-xr-x"
    assert {"/usr/share/doc/zentrale/copyright", "/usr/share/doc/zentrale/changelog.gz"} <= dateien
    assert all(m == "drwxr-xr-x" for p, m in eintraege.items() if m.startswith("d"))


@braucht_dpkg
def test_deb_steuerdaten(gebaut):
    assert os.path.basename(gebaut["deb"]) == "zentrale_9.9.9_all.deb"
    feld = lambda k: subprocess.run(["dpkg-deb", "-f", gebaut["deb"], k], capture_output=True,  # noqa: E731
                                    text=True, check=True).stdout.strip()
    assert feld("Package") == "zentrale"
    assert feld("Version") == "9.9.9"
    assert feld("Architecture") == "all"
    assert feld("Depends") == "python3 (>= 3.11), python3-venv, ca-certificates"
    assert "<" in feld("Maintainer") and feld("Description")


@braucht_dpkg
def test_deb_starter_richtet_nutzer_ein_und_update_verweigert(gebaut, tmp_path):
    """/usr/bin/zentrale aus dem .deb: Kopie in ~/.local/share/zentrale/paket/<fassung>,
    Daten daneben, Kanal apt — und `update` ersetzt sich nicht selbst."""
    wurzel = tmp_path / "wurzel"
    subprocess.run(["dpkg-deb", "-x", gebaut["deb"], str(wurzel)], check=True)
    paket = wurzel / "usr" / "lib" / "zentrale"
    heim = tmp_path / "heim"
    # venv vorab, damit der Test kein pip/Netz braucht: Stempel wie im Starter.
    venv = heim / "paket" / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text(f'#!/bin/sh\nexec "{PY}" "$@"\n')
    (venv / "bin" / "python").chmod(0o755)
    ver = subprocess.run([PY, "-c", "import sys; print(sys.version.split()[0])"],
                         capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256((paket / "requirements-basis.txt").read_bytes()).hexdigest()
    (venv / ".stempel").write_text(f"{ver} {sha}\n")
    umgebung = dict(os.environ, HOME=str(tmp_path), ZENTRALE_PAKET=str(paket),
                    ZENTRALE_HEIM=str(heim), ZENTRALE_PYTHON=PY, NO_COLOR="1")
    umgebung.pop("PYTHONPATH", None)
    starter = str(wurzel / "usr" / "bin" / "zentrale")

    r = subprocess.run([starter, "version"], capture_output=True, text=True, env=umgebung, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ZENTRALE 9.9.9 (installed with apt)"
    kopie = heim / "paket" / "9.9.9"
    assert (kopie / ".fertig").exists() and (kopie / "KANAL").read_text() == "apt\n"
    assert os.path.realpath(kopie / "data") == str((heim / "data").resolve())
    assert os.readlink(kopie / "venv") == "../venv"
    assert (heim / "data" / "ascii").is_dir()

    r = subprocess.run([starter, "update"], capture_output=True, text=True, env=umgebung, timeout=60)
    assert r.returncode == 1
    assert "installed with apt" in r.stdout and "apt upgrade" in r.stdout
    assert sorted(os.listdir(heim / "paket")) == [".sperre", "9.9.9", "venv"]


# ── PKGBUILD ───────────────────────────────────────────────────────────

def test_pkgbuild_sha_passt_zum_tar(gebaut):
    pkgbuild, srcinfo, kopie = gebaut["arch"]
    with open(gebaut["tar"], "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    text = open(pkgbuild, encoding="utf-8").read()
    assert f"sha256sums=('{sha}')" in text
    assert "_fassung=9.9.9" in text and "pkgver=9.9.9" in text
    assert "depends=('python>=3.11')" in text
    assert "@" not in text.split("\n", 1)[1].replace("${", "")   # keine Marke übrig
    assert "/releases/download/v9.9.9/zentrale-9.9.9.tar.gz" in text
    assert f"sha256sums = {sha}" in open(srcinfo, encoding="utf-8").read()
    with open(kopie, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == sha
    assert subprocess.run(["bash", "-n", pkgbuild]).returncode == 0


def test_pkgver_ohne_bindestrich():
    assert arch_bauen.pkgver("2026.10.23-rc1") == "2026.10.23_rc1"


# ── Der Schalter: install.sh ───────────────────────────────────────────

def test_eingechecktes_install_sh_passt_zum_schalter():
    with open(os.path.join(ROOT, "deploy", "install.sh"), encoding="utf-8") as f:
        assert f.read() == verteilung.install_sh_rendern(PRIVAT), \
            "deploy/install.sh neu rendern: scripts/verteilung.py install-sh"


def _oeffentlich(quelle="github"):
    cfg = paket_bauen.verteilung_lesen()
    cfg.update(oeffentlich=True, quelle=quelle)
    return cfg


def test_install_sh_privat_und_oeffentlich_gerendert():
    privat = verteilung.install_sh_rendern(PRIVAT)
    assert "OEFFENTLICH=0\n" in privat and "NEUESTE_VORLAGE=__CLOUD__/v1/paket\n" in privat
    offen = verteilung.install_sh_rendern(_oeffentlich())
    assert "OEFFENTLICH=1\n" in offen
    assert "NEUESTE_VORLAGE=https://github.com/" in offen
    assert "PAKET_VORLAGE=https://github.com/" in offen and "__VERSION__.tar.gz" in offen
    for text in (privat, offen):
        assert subprocess.run(["bash", "-n"], input=text, text=True).returncode == 0


def test_install_sh_oeffentlich_fragt_keinen_code(tmp_path):
    skript = tmp_path / "install.sh"
    skript.write_text(verteilung.install_sh_rendern(_oeffentlich("cloud")))
    umgebung = dict(os.environ, HOME=str(tmp_path), ZENTRALE_HEIM=str(tmp_path / "heim"),
                    ZENTRALE_BIN_DIR=str(tmp_path / "bin"), ZENTRALE_CLOUD="http://127.0.0.1:9",
                    NO_COLOR="1")
    r = subprocess.run(["bash", str(skript)], capture_output=True, text=True, env=umgebung,
                       timeout=60, stdin=subprocess.DEVNULL)
    assert r.returncode != 0
    assert "Could not get the package description. Are you online?" in r.stderr
    assert "invite code" not in (r.stdout + r.stderr).lower()


def test_paket_traegt_den_schalter(gebaut):
    import json
    with tarfile.open(gebaut["tar"]) as t:
        d = json.load(t.extractfile("zentrale-9.9.9/VERTEILUNG.json"))
    assert d == {"oeffentlich": False, **paket_bauen.quell_vorlagen(PRIVAT)}


# ── zentrale update / version: der Kanal ───────────────────────────────

def _term():
    from zentrale_cli.ausgabe import Terminal
    return Terminal(aus=io.StringIO())


def test_kanal_erkannt(tmp_path, monkeypatch):
    from zentrale_cli import aktualisieren
    monkeypatch.setenv("ZENTRALE_HEIM", str(tmp_path / "heim"))
    assert aktualisieren.kanal(ROOT) == "dev"
    skript = tmp_path / "heim" / "hub" / "1"
    skript.mkdir(parents=True)
    assert aktualisieren.kanal(str(skript)) == "script"
    for k in ("apt", "pacman"):
        (skript / "KANAL").write_text(k + "\n")
        assert aktualisieren.kanal(str(skript)) == k


def test_update_verweigert_bei_paketverwaltung(tmp_path, monkeypatch):
    from zentrale_cli import aktualisieren
    monkeypatch.setenv("ZENTRALE_HEIM", str(tmp_path / "heim"))
    wurzel = tmp_path / "heim" / "paket" / "3"
    wurzel.mkdir(parents=True)
    for k, wort in (("apt", "apt upgrade"), ("pacman", "pacman -Syu")):
        (wurzel / "KANAL").write_text(k + "\n")
        term = _term()
        geholt = []
        assert aktualisieren.update(term, venv=geholt.append, wurzel=str(wurzel)) == 1
        assert wort in term.aus.getvalue()
        assert geholt == [] and not (tmp_path / "heim" / "hub").exists()


def test_update_oeffentlich_ohne_konto(tmp_path, monkeypatch):
    """oeffentlich = true im Paket → `update` holt ohne Anmeldung aus der Quelle."""
    import json
    from zentrale_cli import aktualisieren
    quelle = tmp_path / "quelle"
    (quelle / "bin").mkdir(parents=True)
    (quelle / "bin" / "zentrale").write_text("#!/bin/sh\n")
    (quelle / "requirements-basis.txt").write_text("")
    netz = tmp_path / "netz"
    tar, neueste = paket_bauen.bauen("2", root=str(quelle), ziel_ordner=str(netz),
                                     liste=[("bin/zentrale", "bin/zentrale"),
                                            ("requirements-basis.txt", "requirements-basis.txt")],
                                     stufe=1, verteilung=PRIVAT)
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(
        SimpleHTTPRequestHandler, directory=str(netz)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        basis = f"http://127.0.0.1:{server.server_address[1]}"
        heim = tmp_path / "heim"
        alt = heim / "hub" / "1"
        alt.mkdir(parents=True)
        (alt / "VERSION").write_text("1\n")
        (alt / "VERTEILUNG.json").write_text(json.dumps({
            "oeffentlich": True, "neueste": basis + "/neueste.json",
            "paket": basis + "/zentrale-__VERSION__.tar.gz"}))
        os.symlink("1", heim / "hub" / "aktuell")
        monkeypatch.setenv("ZENTRALE_HEIM", str(heim))
        monkeypatch.setattr(aktualisieren.konto, "angemeldet", lambda: False)
        term, venvs = _term(), []
        assert aktualisieren.update(term, venv=venvs.append, wurzel=str(alt), check=lambda d: (True, "")) == 0, term.aus.getvalue()
        assert os.readlink(heim / "hub" / "aktuell") == "2"
        assert venvs == [str(heim / "hub" / "2")]
    finally:
        server.shutdown()
