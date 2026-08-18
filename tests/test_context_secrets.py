# tests/test_context_secrets.py
#
# Regression für die Secret-Sperre in core/context.py.
#
# Vorgeschichte (2026-07-17): die Whitelist der lokalen KI ist bewusst breit
# (`data/*.json` deckt alle Logs ab) — und genau dadurch fiel der API-Key-Store
# data/ai_config.json mit hinein. Die KI konnte per read_file den DASHSCOPE-Key
# im Klartext lesen. Fix: eine Denylist, die VOR der Whitelist greift und nach
# Basename matcht. Dieser Test friert das ein: der Key-Store bleibt für die KI
# tabu, egal wie die Whitelist wächst.

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import context


def _denied(out: str) -> bool:
    return isinstance(out, str) and out.startswith("[Zugriff verweigert")


def test_key_store_is_blocked():
    # data/ai_config.json MATCHT die Whitelist (`data/*.json`) — trotzdem tabu.
    out = context.read_file("data/ai_config.json")
    assert _denied(out), out
    assert "DASHSCOPE" not in out and "cloud_enabled" not in out


def test_legacy_config_blocked():
    out = context.read_file("data/tutor_config.json")
    assert _denied(out), out


def test_traversal_to_secret_blocked():
    # Umweg über .. darf die Sperre nicht aushebeln.
    out = context.read_file("data/../data/ai_config.json")
    assert _denied(out), out


def test_secret_suffixes_blocked():
    for name in ("data/mail.enc", "data/foo.key", "data/cert.pem"):
        out = context.read_file(name)
        assert _denied(out), (name, out)


def test_secret_never_listed():
    # list_files darf die Existenz des Key-Stores nicht mal verraten.
    files = context.list_available_files()
    assert not any(os.path.basename(f) in ("ai_config.json", "tutor_config.json")
                   for f in files), files


def test_normal_data_still_readable():
    # Die Sperre darf legitime Logs nicht mitreißen: eine harmlose data/*.json
    # bleibt lesbar (oder sauber 'nicht gefunden', wenn sie fehlt) — jedenfalls
    # NICHT als Secret abgelehnt.
    out = context.read_file("data/sleep_quality.json")
    assert not out.startswith("[Zugriff verweigert: Secret"), out


def test_source_code_still_readable():
    # Die KI darf ihren eigenen Code weiter lesen (core/*.py), auch ai_config.py
    # (Quellcode, kein Secret — der Key steht in der .json, nicht im .py).
    out = context.read_file("core/context.py")
    assert not out.startswith("[Zugriff verweigert"), out


# ── Reichweite: alles unter ~/codicus ─────────────────────────────────
#
# Sasha, 18.08.2026: "die ai brauch zugriff auf alles unter /codicus/".
# Damit traegt die Secret-Sperre ungleich mehr als vorher — in fremden
# Repos liegen .env-Dateien und Deploy-Keys, an die niemand denkt.
#
# Die Tests bauen sich einen EIGENEN Baum, statt Sashas echte Projekte zu
# lesen. Zwei Gruende: sie sollen ueberall laufen, und der Testlauf biegt
# HOME auf einen Wegwerf-Ordner um (venv-Riegel) — `~/codicus` zeigt darin
# ohnehin ins Leere.

import pytest


@pytest.fixture
def baum(tmp_path, monkeypatch):
    wurzel = tmp_path / "codicus"
    for rel in ("Kunstwolff/notiz.md", "learning/uebung.c",
                "projekt/.git/config", "projekt/node_modules/x.js",
                "projekt/src/main.py", "projekt/.env", "projekt/deploy.key"):
        ziel = wurzel / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text("inhalt", encoding="utf-8")
    monkeypatch.setattr(context, "_CODICUS", str(wurzel))
    monkeypatch.setattr(context, "_WURZELN", [context._ROOT, str(wurzel)])
    return wurzel


def test_fremdes_projekt_ist_lesbar(baum):
    assert context.erlaubt(str(baum / "Kunstwolff" / "notiz.md")) == ""
    assert context.erlaubt(str(baum / "projekt" / "src" / "main.py")) == ""


def test_lernzone_bleibt_zu(baum):
    """Sashas Lernordner ist bewusst ohne KI-Beteiligung. Das ist eine
    Entscheidung, keine Notwendigkeit — sie steht als eine Zeile in
    _GESPERRTE_ORDNER und ist genauso leicht zurueckzunehmen."""
    assert "gesperrt" in context.erlaubt(str(baum / "learning" / "uebung.c"))


def test_versionsverwaltung_und_ballast_bleiben_zu(baum):
    """.git ist Innerei, kein Inhalt; node_modules und Arbeitskopien waeren
    dieselben Dateien noch einmal."""
    assert "gesperrt" in context.erlaubt(str(baum / "projekt/.git/config"))
    assert "gesperrt" in context.erlaubt(str(baum / "projekt/node_modules/x.js"))


def test_secret_muster_greifen_auch_in_fremden_projekten(baum):
    """Diese Sperre wurde durch die neue Reichweite erst wichtig."""
    assert context.erlaubt(str(baum / "projekt" / ".env")) != ""
    assert context.erlaubt(str(baum / "projekt" / "deploy.key")) != ""
    for name in ("id_rsa", "my_secret.txt", "API_KEY.txt", "credentials.json"):
        assert context.erlaubt(str(baum / "projekt" / name)) != "", name


def test_keine_flucht_nach_oben(baum):
    """`..` braucht keine eigene Pruefung: wer hinausklettert, faellt aus
    der Wurzel und damit durch."""
    import os
    for weg in ("/etc/passwd", os.path.expanduser("~/.ssh/id_rsa"),
                str(baum / ".." / ".." / "etc" / "passwd")):
        assert context.erlaubt(weg) != "", weg


def test_auflistung_zeigt_zentrale_zuerst(baum):
    """Sonst frisst ein alphabetisch fruehes Fremdprojekt den Deckel auf
    und ausgerechnet das, was sie taeglich braucht, faellt heraus."""
    dateien = context.list_available_files()
    assert any(f.startswith("core/") for f in dateien)
    assert "learning/uebung.c" not in dateien
    assert not any(".env" in f for f in dateien)


def test_read_file_nimmt_beide_wurzeln(baum):
    assert "def " in context.read_file("core/context.py")
    assert "inhalt" in context.read_file("Kunstwolff/notiz.md")


def test_verzeichnis_ist_keine_datei(baum):
    assert "Verzeichnis" in context.read_file("Kunstwolff")
