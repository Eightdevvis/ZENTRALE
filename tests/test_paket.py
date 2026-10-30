"""Das Paket des installierbaren Hubs (scripts/paket_bauen.py, deploy/paket.txt),
`zentrale update` und der Schutz in deploy/install.sh.

Was nie im Paket landen darf: data/, *.enc, ai_config.json, *.schluessel,
memory/, tests/, venv — Sashas Daten und Schlüssel."""
import fnmatch
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest

import dateien
import konto
import konto_schluessel as ks
from devkit.fake_cloud import FalscheCloud

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Hinten anhängen: scripts/abgleich.py darf core/abgleich.py nicht verdecken.
sys.path.append(os.path.join(ROOT, "scripts"))
import paket_bauen  # noqa: E402


@pytest.fixture(scope="module")
def echtes_paket(tmp_path_factory):
    ziel = tmp_path_factory.mktemp("paket")
    pfad, neueste = paket_bauen.bauen("9.9.9", ziel_ordner=str(ziel), stufe=1)
    with tarfile.open(pfad) as tar:
        namen = tar.getnames()
    return pfad, neueste, namen, ziel


def test_paket_enthaelt_keine_daten_keine_schluessel(echtes_paket):
    _pfad, _n, namen, _z = echtes_paket
    innen = [n.split("/", 1)[1] for n in namen if "/" in n]
    for n in innen:
        assert not n.startswith(("data/", "memory/", "tests/", "venv/", "services/")), n
        name = n.rsplit("/", 1)[-1]
        for verboten in ("*.enc", "ai_config.json", "*.schluessel", "*.pyc"):
            assert not fnmatch.fnmatch(name, verboten), n
        assert "/" in n or not name.endswith((".png", ".jpg", ".zip")), n


def test_paket_hat_was_ein_knoten_braucht(echtes_paket):
    _pfad, _n, namen, _z = echtes_paket
    innen = {n.split("/", 1)[1] for n in namen if "/" in n}
    assert all(n.startswith("zentrale-9.9.9") for n in namen)
    for muss in ("VERSION", "bin/zentrale", "zentrale_cli/haupt.py", "core/konto.py",
                 "core/main.py", "ui/app.py", "tui/zentrale_tui.py", "scripts/start_tui.sh",
                 "requirements-basis.txt", "deploy/install.sh"):
        assert muss in innen, muss
    assert any(n.startswith("mitgeliefert/ascii/") for n in innen)


def test_neueste_json_passt_zum_paket(echtes_paket):
    pfad, neueste, _namen, ziel = echtes_paket
    with open(pfad, "rb") as f:
        daten = f.read()
    assert neueste == {"version": "9.9.9", "sha256": hashlib.sha256(daten).hexdigest(),
                       "groesse": len(daten)}
    with open(ziel / "neueste.json", encoding="utf-8") as f:
        assert json.load(f) == neueste


def test_verbotenes_in_der_liste_wird_verweigert(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "lists.json").write_text("[]")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "mail.enc").write_text("x")
    for liste in ([("data/", "data/")], [("core/", "core/")]):
        with pytest.raises(paket_bauen.PaketFehler, match="nie ins Paket"):
            paket_bauen.bauen("1", root=str(tmp_path), ziel_ordner=str(tmp_path / "dist"),
                              liste=liste)


# ── zentrale update ────────────────────────────────────────────────────

def _kleines_paket(tmp_path, fassung):
    quelle = tmp_path / "quelle"
    (quelle / "bin").mkdir(parents=True)
    (quelle / "bin" / "zentrale").write_text("#!/bin/sh\n")
    (quelle / "requirements-basis.txt").write_text("")
    (quelle / "ascii").mkdir()
    (quelle / "ascii" / "katze.txt").write_text("=^.^=")
    pfad, _n = paket_bauen.bauen(fassung, root=str(quelle), ziel_ordner=str(tmp_path / "dist"),
                                 liste=[("bin/zentrale", "bin/zentrale"),
                                        ("requirements-basis.txt", "requirements-basis.txt"),
                                        ("ascii/", "mitgeliefert/ascii/")])
    with open(pfad, "rb") as f:
        return f.read()


def test_update_daneben_installieren_und_umschalten(tmp_path, monkeypatch):
    from zentrale_cli import aktualisieren
    from zentrale_cli.ausgabe import Terminal
    heim = tmp_path / "heim"
    alt = heim / "hub" / "1"
    alt.mkdir(parents=True)
    (alt / "VERSION").write_text("1\n")
    os.symlink("1", heim / "hub" / "aktuell")
    monkeypatch.setenv("ZENTRALE_HEIM", str(heim))
    c = FalscheCloud()
    try:
        monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
        monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
        monkeypatch.setattr(dateien, "knoten", lambda: "minipc")
        konto.anlegen(konto.Entwurf("ein-langes-passwort"), "sasha", "ZB-AAAA-BBBB-CCCC-DDDD",
                      "ein-langes-passwort")
        c.zustand.paket = ("2", _kleines_paket(tmp_path, "2"))
        venvs = []
        term = Terminal(aus=io.StringIO())
        assert aktualisieren.update(term, venv=venvs.append, wurzel=str(alt)) == 0, term.aus.getvalue()
        neu = heim / "hub" / "2"
        assert os.readlink(heim / "hub" / "aktuell") == "2"
        assert (neu / "VERSION").read_text().strip() == "2"
        assert os.path.realpath(neu / "data") == str((heim / "data").resolve())
        assert (heim / "data" / "ascii" / "katze.txt").read_text() == "=^.^="
        assert venvs == [str(neu)]
        assert alt.exists()                                  # Rückweg bleibt
        # The keeper of the new release ran; this one's bin/zentrale is a stub
        # that cannot run, so the update stands and one line says how to repair.
        assert "Run 'zentrale timers install' to repair them." in term.aus.getvalue()
        # Nochmal: schon aktuell.
        term = Terminal(aus=io.StringIO())
        assert aktualisieren.update(term, venv=venvs.append, wurzel=str(neu)) == 0
        assert "newest version" in term.aus.getvalue()
    finally:
        c.stopp()


def test_update_im_entwickler_checkout_tut_nichts(tmp_path, monkeypatch):
    from zentrale_cli import aktualisieren
    from zentrale_cli.ausgabe import Terminal
    monkeypatch.setenv("ZENTRALE_HEIM", str(tmp_path / "heim"))
    term = Terminal(aus=io.StringIO())
    assert aktualisieren.update(term, venv=lambda o: None, wurzel=ROOT) == 1
    assert "developer checkout" in term.aus.getvalue()


# ── install.sh schützt fremde Befehle ──────────────────────────────────

def _install(tmp_path, *args):
    umgebung = dict(os.environ, HOME=str(tmp_path), ZENTRALE_HEIM=str(tmp_path / "heim"),
                    ZENTRALE_BIN_DIR=str(tmp_path / "bin"), ZENTRALE_CLOUD="http://127.0.0.1:9",
                    NO_COLOR="1")
    return subprocess.run(["bash", os.path.join(ROOT, "deploy", "install.sh"), *args],
                          capture_output=True, text=True, env=umgebung, timeout=60,
                          stdin=subprocess.DEVNULL)


def test_install_ueberschreibt_keinen_fremden_befehl(tmp_path):
    (tmp_path / "bin").mkdir()
    eigener = tmp_path / "bin" / "zentrale"
    eigener.write_text("#!/bin/sh\necho Sashas eigener\n")
    r = _install(tmp_path, "CODE")
    assert r.returncode != 0 and "left untouched" in r.stderr
    assert eigener.read_text() == "#!/bin/sh\necho Sashas eigener\n"
    eigener.unlink()
    os.symlink("/usr/bin/true", eigener)
    r = _install(tmp_path, "CODE")
    assert r.returncode != 0 and "left untouched" in r.stderr
    assert os.readlink(eigener) == "/usr/bin/true"
    assert not (tmp_path / "heim").exists()


def test_install_ohne_cloud_klarer_fehler_und_nichts_installiert(tmp_path):
    r = _install(tmp_path, "CODE")
    assert r.returncode != 0 and "invite code" in r.stderr.lower()
    assert not (tmp_path / "bin" / "zentrale").exists()
