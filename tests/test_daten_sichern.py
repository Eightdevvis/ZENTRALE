"""scripts/daten_sichern.py — die Sicherung ins private Daten-Repo.

Geprüft wird vor allem, was NICHT passieren darf: ein Schlüssel verlässt
den Rechner, eine nicht freigegebene Datei rutscht mit, ein Rechner
überschreibt den Stand des anderen. Der Push läuft gegen ein lokales
Wegwerf-Repo, nie gegen GitHub.
"""
import importlib.util
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def ds(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "daten_sichern", os.path.join(ROOT, "scripts", "daten_sichern.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fern = tmp_path / "fern.git"
    subprocess.run(["git", "init", "-q", "--bare", str(fern)], check=True)
    monkeypatch.setattr(mod, "REMOTE", str(fern))
    monkeypatch.setattr(mod, "KLON", str(tmp_path / "klon"))
    return mod


def _datei(wurzel, rel, inhalt="{}"):
    pfad = os.path.join(wurzel, rel)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(inhalt)


@pytest.fixture
def quelle(tmp_path):
    q = tmp_path / "zentrale"
    for rel in ("data/lists.json", "data/g_sleep.json", "data/gedaechtnis/sasha.md",
                "data/gedaechtnis/dossiers/umzug.md", "data/ai_transcripts/2026-10.jsonl",
                "tutor/data/staende/a/stand.json",
                # dürfen NICHT mit:
                "data/ai_config.json", "data/mail_secrets.enc", "data/news_stories.json",
                "data/_beiseite/ai_stm.json", "data/unter/g_x.json"):
        _datei(str(q), rel)
    return str(q)


def test_nur_was_auf_der_positivliste_steht(ds, quelle):
    gewaehlt = ds.auswahl(quelle)
    assert "data/lists.json" in gewaehlt and "data/g_sleep.json" in gewaehlt
    assert "data/gedaechtnis/dossiers/umzug.md" in gewaehlt
    assert "tutor/data/staende/a/stand.json" in gewaehlt
    for nie in ("data/ai_config.json", "data/mail_secrets.enc",
                "data/news_stories.json", "data/_beiseite/ai_stm.json",
                "data/unter/g_x.json"):
        assert nie not in gewaehlt, nie


@pytest.mark.parametrize("inhalt", [
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
    '{"ANTHROPIC_API_KEY": "irgendwas-geheimes"}',
    '{"refresh_token": "x"}',
    "-----BEGIN OPENSSH PRIVATE KEY-----",
])
def test_schluessel_verdacht_bricht_alles_ab(ds, quelle, inhalt):
    _datei(quelle, "data/notes.json", inhalt)
    assert ds.main(["--quelle", quelle]) == 2
    # Nichts gepusht: der ferne Branch existiert nicht.
    r = subprocess.run(["git", "ls-remote", "--heads", ds.REMOTE], capture_output=True, text=True)
    assert r.stdout.strip() == ""


def test_saubere_dateien_haben_keinen_verdacht(ds, quelle):
    assert ds.schluessel_funde(ds.auswahl(quelle), quelle) == []


def test_sichern_pusht_in_den_eigenen_branch_und_spiegelt(ds, quelle):
    assert ds.main(["--quelle", quelle]) == 0
    import socket
    branch = f"knoten/{socket.gethostname()}"
    r = subprocess.run(["git", "ls-remote", "--heads", ds.REMOTE, branch],
                       capture_output=True, text=True)
    assert branch in r.stdout
    # Zweiter Lauf ohne Änderung: kein neuer Commit.
    assert ds.main(["--quelle", quelle]) == 0
    log = subprocess.run(["git", "log", "--oneline"], cwd=ds.KLON,
                         capture_output=True, text=True).stdout.strip().splitlines()
    assert len(log) == 1
    # Gelöscht in ZENTRALE → im nächsten Stand weg, in der Historie noch da.
    os.remove(os.path.join(quelle, "data", "lists.json"))
    assert ds.main(["--quelle", quelle]) == 0
    assert not os.path.exists(os.path.join(ds.KLON, "data", "lists.json"))
    alt = subprocess.run(["git", "show", "HEAD~1:data/lists.json"], cwd=ds.KLON,
                         capture_output=True, text=True)
    assert alt.returncode == 0
