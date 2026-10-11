"""gross liest Dateien nur noch aus der Ablage (2026-10-11; vorher
Input/ und Output/ des Nutzerordners, 2026-10-09).

Sasha: „ja einfach nur die ablage dann" — wie Claude Web EIN Ort für Dateien.
Geprüft wird an den Werkzeugen, wie die KI sie ruft:
  - gross: read_file, read_pdf/read_docx, fetch_document erreichen keinen
    Dateipfad mehr — weder ZENTRALE/core noch data/ noch ~/codicus noch
    Input/ — mit festem Fehlercode;
  - read_file liest Ablage-Dokumente per id oder genauem Titel;
  - klein liest wie bisher (ZENTRALE-Whitelist, ~/codicus);
  - read_series ersetzt das Lesen von data/<reihe>.json.
"""
import datetime as dt
import os

import pytest

import ablage
import context
import gedaechtnis
import ki_werkzeuge
import nutzer_ordner
import state
import werkzeug_befund

from test_werkzeug_belege import umgebung  # noqa: F401  — Wegwerf-Umgebung

ROOT = context._ROOT


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


@pytest.fixture
def gross():
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


@pytest.fixture
def input_ordner(umgebung):  # noqa: F811
    ein = nutzer_ordner.unterordner(nutzer_ordner.INPUT)
    with open(os.path.join(ein, "notiz.md"), "w", encoding="utf-8") as f:
        f.write("Eisen und Zink")
    return ein


def lauf(name, args):
    return ki_werkzeuge._verteilen(name, args)


# ── gross: kein Dateipfad ───────────────────────────────────────────────

@pytest.mark.parametrize("pfad", [
    os.path.join(ROOT, "core", "context.py"),
    os.path.join(ROOT, "data", "sleep_quality.json"),
    "../../core/context.py", "/etc/hostname", "Input/notiz.md", "notiz.md",
])
def test_gross_read_file_kennt_keine_pfade(gross, input_ordner, pfad):
    r = lauf("read_file", {"path": pfad})
    assert r.startswith("[Nicht in der Ablage"), r
    assert "Eisen" not in r and "Whitelist" not in r


def test_gross_pdf_und_word_nur_aus_der_ablage(gross, input_ordner):
    for name in ("read_pdf", "read_docx"):
        r = lauf(name, {"quelle": os.path.join(ROOT, "core", "context.py")})
        assert r.status == werkzeug_befund.FEHLGESCHLAGEN and "P-QUELLE-FEHLT" in r


@pytest.mark.parametrize("url", [os.path.join(ROOT, "core", "context.py"), "Input/notiz.md"])
def test_gross_fetch_document_mit_pfad_legt_nichts_ab(gross, input_ordner, url):
    r = lauf("fetch_document", {"url": url, "name": "code"})
    assert r.status == werkzeug_befund.FEHLGESCHLAGEN and "Z-AUSSERHALB" in r
    assert not gedaechtnis.dossier_lesen("quellen/code")


# ── gross: die Ablage ──────────────────────────────────────────────────

def test_gross_read_file_liest_die_ablage(gross, input_ordner):
    k = ablage.anlegen("Metalle", "Eisen und Zink", "markdown")
    assert "Eisen und Zink" in lauf("read_file", {"path": k["id"]})
    assert "Eisen und Zink" in lauf("read_file", {"path": "metalle"})       # genauer Titel
    assert "Eisen und Zink" in lauf("read_file", {"path": "Metalle.md"})    # wie im Ordner
    ablage.anlegen("Metalle", "anders", "markdown")
    r = lauf("read_file", {"path": "Metalle"})
    assert r.startswith("[Mehrere Dokumente") and k["id"] in r


def test_gross_list_files_ist_die_ablage(gross, input_ordner):
    k = ablage.anlegen("Metalle", "Eisen", "markdown")
    r = lauf("list_files", {})
    assert r.startswith("Ablage — 1 Dokumente, vollständig") and k["id"] in r
    assert "notiz.md" not in r
    ablage.papierkorb(k["id"])
    assert lauf("list_files", {}).startswith("Ablage — leer")
    assert k["id"] in lauf("list_files", {"papierkorb": True})


# ── klein: unverändert ──────────────────────────────────────────────────

def test_klein_liest_wie_bisher(input_ordner):
    assert werkzeug_befund.schiene() == "klein"
    assert "Whitelist-basierter" in lauf("read_file", {"path": "core/context.py"})
    assert lauf("read_file", {"path": "Input/notiz.md"}) == "Eisen und Zink"
    assert "Verfügbare Dateien" in lauf("list_files", {})


# ── read_series ─────────────────────────────────────────────────────────

def test_read_series_liste_und_werte(umgebung):  # noqa: F811
    import graphs
    graphs.create_graph("Schlaf", gtype="period")
    graphs.create_graph("Spagat", gtype="number", unit="cm")
    heute = dt.date.today()
    gestern = (heute - dt.timedelta(days=1)).isoformat()
    gid = {g["name"]: g["id"] for g in graphs.list_graphs()}
    graphs.log_value(gid["Schlaf"], gestern, 23 * 60 + 30, end=7 * 60)
    graphs.log_value(gid["Spagat"], heute.isoformat(), 12)
    graphs.log_value(gid["Spagat"], (heute - dt.timedelta(days=60)).isoformat(), 30)

    liste = lauf("read_series", {})
    assert f"Schlaf (period): 1 Werte, zuletzt {gestern}: 23:30–07:00" in liste
    assert "Spagat (number): 2 Werte" in liste

    r = lauf("read_series", {"series": "spagat"})
    assert "1 Werte" in r and "12 cm" in r and "30 cm" not in r
    alles = lauf("read_series", {"series": "Spagat", "von": "2000-01-01"})
    assert "30 cm" in alles and "12 cm" in alles


def test_read_series_unbekannt_mit_code(umgebung):  # noqa: F811
    r = lauf("read_series", {"series": "Gibtsnicht"})
    assert r.status == werkzeug_befund.FEHLGESCHLAGEN and "M-UNBEKANNT" in r
    assert lauf("read_series", {}) == "Es gibt noch keine Messreihen."
