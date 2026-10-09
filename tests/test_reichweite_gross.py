"""gross liest nur noch im Nutzerordner (2026-10-09, core/context.py).

Sasha: der Assistent arbeitet mit ~/Zentrale (Input/, Output/) und seinem
Gedächtnis; ~/codicus und der ZENTRALE-Code gehören später zur Coder-App.
Geprüft wird an den Werkzeugen, wie die KI sie ruft:
  - gross: read_file, read_pdf/read_docx, fetch_document erreichen weder
    ZENTRALE/core noch data/ noch ~/codicus — mit festem Fehlercode;
  - Input/ und Output/ gehen weiter, Verstecktes, Schlüssel und Verweise
    nach draußen nicht;
  - klein liest wie bisher (ZENTRALE-Whitelist, ~/codicus);
  - read_series ersetzt das Lesen von data/<reihe>.json.
"""
import datetime as dt
import os

import pytest

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


# ── gross: draußen ist zu ───────────────────────────────────────────────

@pytest.mark.parametrize("pfad", [
    os.path.join(ROOT, "core", "context.py"),
    os.path.join(ROOT, "notes.md"),
    os.path.join(ROOT, "data", "sleep_quality.json"),
    "../../core/context.py",
    "/etc/hostname",
])
def test_gross_liest_keinen_zentrale_code_und_keine_daten(gross, input_ordner, pfad):
    r = lauf("read_file", {"path": pfad})
    assert r.startswith("[Zugriff verweigert") and "Z-AUSSERHALB" in r, r


@pytest.mark.parametrize("pfad", ["core/context.py", "data/sleep_quality.json", "notes.md"])
def test_gross_relativ_heisst_input(gross, input_ordner, pfad):
    """Ein relativer Pfad meint den Nutzerordner — die alten Projektpfade
    treffen dort nichts, und die Meldung sagt, wo gesucht wurde."""
    assert lauf("read_file", {"path": pfad}) == f"[Datei nicht gefunden: Input/{pfad}]"


def test_gross_liest_nichts_unter_codicus(gross, input_ordner, tmp_path, monkeypatch):
    baum = tmp_path / "codicus"
    (baum / "projekt").mkdir(parents=True)
    (baum / "projekt" / "notiz.md").write_text("geheimes Projekt")
    monkeypatch.setattr(context, "_CODICUS", str(baum))
    monkeypatch.setattr(context, "_WURZELN", [ROOT, str(baum)])
    assert "Z-AUSSERHALB" in lauf("read_file", {"path": str(baum / "projekt" / "notiz.md")})
    assert "geheimes" not in lauf("read_file", {"path": "projekt/notiz.md"})


def test_gross_pdf_und_word_von_draussen_mit_code(gross, input_ordner):
    for name in ("read_pdf", "read_docx"):
        r = lauf(name, {"quelle": os.path.join(ROOT, "core", "context.py")})
        assert r.status == werkzeug_befund.FEHLGESCHLAGEN
        assert "P-QUELLE-AUSSERHALB" in r


def test_gross_fetch_document_von_draussen_legt_nichts_ab(gross, input_ordner):
    r = lauf("fetch_document", {"url": os.path.join(ROOT, "core", "context.py"),
                                "name": "code"})
    assert r.status == werkzeug_befund.FEHLGESCHLAGEN and "Z-AUSSERHALB" in r
    assert not gedaechtnis.dossier_lesen("quellen/code")


def test_gross_kein_verweis_aus_input_hinaus(gross, input_ordner):
    os.symlink(os.path.join(ROOT, "core", "context.py"),
               os.path.join(input_ordner, "weg.py"))
    r = lauf("read_file", {"path": "Input/weg.py"})
    assert "Z-AUSSERHALB" in r


# ── gross: Input/ und Output/ gehen weiter ──────────────────────────────

@pytest.mark.parametrize("pfad", ["notiz.md", "Input/notiz.md", "input/notiz.md"])
def test_gross_liest_input(gross, input_ordner, pfad):
    assert lauf("read_file", {"path": pfad}).startswith("Eisen und Zink")


def test_gross_liest_output_und_absolut(gross, input_ordner):
    aus = nutzer_ordner.unterordner(nutzer_ordner.OUTPUT)
    with open(os.path.join(aus, "plan.md"), "w", encoding="utf-8") as f:
        f.write("Plan A")
    assert lauf("read_file", {"path": "Output/plan.md"}) == "Plan A"
    assert lauf("read_file", {"path": os.path.join(aus, "plan.md")}) == "Plan A"


def test_gross_versteckt_und_schluessel_bleiben_zu(gross, input_ordner):
    for name in (".geheim.md", "api_token.txt"):
        with open(os.path.join(input_ordner, name), "w") as f:
            f.write("x")
        assert lauf("read_file", {"path": "Input/" + name}).startswith("[Zugriff verweigert")


def test_gross_fetch_document_aus_input(gross, input_ordner):
    r = lauf("fetch_document", {"url": "Input/notiz.md", "name": "metalle"})
    assert r.status == werkzeug_befund.OK, r
    assert "Eisen und Zink" in gedaechtnis.dossier_lesen("quellen/metalle")


def test_fehlende_datei_heisst_nicht_gefunden(gross, input_ordner):
    assert lauf("read_file", {"path": "gibtsnicht.md"}).startswith("[Datei nicht gefunden")


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
