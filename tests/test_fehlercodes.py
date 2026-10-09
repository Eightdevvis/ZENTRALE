"""Zwei Ausgänge, feste Codes (2026-10-09, core/fehlercodes.py).

Sasha: „das programm macht etwas richtig ODER bricht KONTROLLIERT KOMPLETT
AB mit genauem fehlercode!" Geprüft wird:
  - jeder Code, der im Kern vorkommt, steht in der Tabelle (und wird erklärt);
  - kein Befund „fehlgeschlagen" ohne Code;
  - es gibt keinen Status „teilweise" mehr;
  - bricht ein schreibendes Werkzeug NACH dem Schreiben ab (nachgelesen
    stand es nicht da), sind die Daten Byte für Byte wie vorher.
"""
import ast
import os
import re

import pytest

import ablage
import browser_sitzung
import fehlercodes
import gedaechtnis
import input_dateien
import ki_pdf_word
import ki_werkzeuge
import skills
import werkzeug_befund
import werkzeug_register
from test_werkzeug_belege import umgebung  # noqa: F401  — Wegwerf-Umgebung

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")
_CODE = re.compile(r"^[KWNADMSPIBZ]-[A-Z0-9]+(?:-[A-Z0-9]+)*$")


def _baeume():
    for name in sorted(os.listdir(CORE)):
        if name.endswith(".py") and name != "fehlercodes.py":
            pfad = os.path.join(CORE, name)
            with open(pfad, encoding="utf-8") as f:
                yield name, ast.parse(f.read())


def test_jeder_verwendete_code_steht_in_der_tabelle():
    benutzt = set()
    for name, baum in _baeume():
        for k in ast.walk(baum):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and _CODE.match(k.value):
                benutzt.add((name, k.value))
    assert benutzt, "keine Codes gefunden — Muster kaputt?"
    fehlt = sorted(f"{n}: {c}" for n, c in benutzt if c not in fehlercodes.CODES)
    assert not fehlt, fehlt


def test_kein_fehlgeschlagen_ohne_code():
    """Befund(…, FEHLGESCHLAGEN) direkt zu bauen heißt: ohne Code. Dafür
    gibt es werkzeug_befund.abgebrochen."""
    roh = []
    for name, baum in _baeume():
        if name == "werkzeug_befund.py":
            continue
        for k in ast.walk(baum):
            if not (isinstance(k, ast.Call) and getattr(k.func, "id", getattr(k.func, "attr", "")) == "Befund"):
                continue
            werte = list(k.args) + [kw.value for kw in k.keywords]
            schlecht = any(getattr(w, "id", getattr(w, "attr", None)) == "FEHLGESCHLAGEN"
                           or (isinstance(w, ast.Constant) and w.value == "fehlgeschlagen")
                           for w in werte)
            if schlecht and not any(kw.arg == "code" for kw in k.keywords):
                roh.append(f"{name}:{k.lineno}")
    assert not roh, roh


def test_teilweise_gibt_es_nicht_mehr():
    assert "teilweise" not in werkzeug_befund.STATUS
    assert not hasattr(werkzeug_befund, "TEILWEISE")
    with pytest.raises(ValueError):
        werkzeug_befund.Befund("x", "teilweise")


def test_jeder_code_ist_erklaert():
    for code, (ursache, tun) in fehlercodes.CODES.items():
        assert _CODE.match(code), code
        assert len(ursache) > 15 and len(tun) > 5, code
        text = fehlercodes.erklaeren(code.lower())
        assert text.startswith(code) and "Ursache:" in text and "Was tun:" in text


def test_kalender_kern_codes_sind_mit_k_davor_erklaert():
    try:
        import kalender_kennung
    except ImportError:
        pytest.skip("core/kalender_kennung.py noch nicht da")
    for code in kalender_kennung.CODES:
        assert "K-" + code in fehlercodes.CODES, code


def test_explain_error_werkzeug():
    w = werkzeug_register.eintrag("explain_error")
    assert w.gross and w.klein is None and w.erlaubnis is False and not w.schreibt
    r = ki_werkzeuge._verteilen("explain_error", {"code": "Fehler K-ENDE-VOR-BEGINN"})
    assert "Ursache:" in r and "Beginn" in r
    assert "Unbekannter Fehlercode" in ki_werkzeuge._verteilen("explain_error", {"code": "X-1"})


def test_abgebrochen_hat_die_feste_form():
    b = werkzeug_befund.abgebrochen("Notiz in 'x'", "N-TEXT-LEER", "[kein Text]",
                                    "nichts geschrieben")
    assert b == "Notiz in 'x' ABGEBROCHEN – nichts geschrieben. Fehler N-TEXT-LEER: kein Text."
    assert b.status == "fehlgeschlagen" and b.code == "N-TEXT-LEER"


# ── Abbruch nach dem Schreiben: alles wie vorher ───────────────────────

def _stand(wurzeln):
    raus = {}
    for w in wurzeln:
        for wurzel, _u, namen in os.walk(w):
            for n in namen:
                p = os.path.join(wurzel, n)
                with open(p, "rb") as f:
                    raus[p] = f.read()
    return raus


@pytest.fixture
def wurzeln(umgebung):  # noqa: F811
    import graphs
    import nutzer_ordner
    return [gedaechtnis._DIR, ablage.ordner(), skills.ordner(), graphs._DATA_DIR,
            nutzer_ordner.wurzel()]


def _vorbereiten():
    """Was die Ändern-Werkzeuge vorfinden müssen."""
    ki_werkzeuge._verteilen("write_note", {"name": "wege", "text": "Zur Schule 20 min."})
    ki_werkzeuge._verteilen("create_series", {"name": "Spagat"})
    ki_werkzeuge._verteilen("propose_skill", {"name": "probe-sicher", "beschreibung": "Wenn x.",
                                              "inhalt": "1. Erst lesen."})
    doc = ki_werkzeuge._verteilen("create_document", {"titel": "Plan", "inhalt": "eins"})
    pdf = ki_werkzeuge._verteilen("create_pdf", {"titel": "P", "inhalt": "# P\n\nText."})
    docx = ki_werkzeuge._verteilen("create_docx", {"titel": "B", "inhalt": "# B\n\nLiebe Frau Meier,"})
    ids = [r.split("(id ", 1)[1].split(",", 1)[0].split(")", 1)[0] for r in (doc, pdf, docx)]
    return dict(zip(("doc", "pdf", "docx"), ids))


def _faelle(ids):
    import graphs
    leer = lambda *a, **k: ""  # noqa: E731
    return [
        ("write_note", {"name": "tagebuch", "text": "Heute Geige."},
         [(gedaechtnis, "tagebuch_lesen", leer)]),
        ("write_note", {"name": "wege", "text": "Zum Bahnhof 5 min."},
         [(gedaechtnis, "dossier_lesen", leer)]),
        ("rewrite_note", {"name": "wege", "content": "Alles neu."},
         [(gedaechtnis, "dossier_lesen", leer)]),
        ("fetch_document", {"url": "https://example.org/a", "name": "handbuch"},
         [(gedaechtnis, "dossier_lesen", leer)]),
        ("log_series", {"series": "Spagat", "value": 12, "day": "2026-10-08"},
         [(graphs, "read_values", lambda gid: [])]),
        ("edit_skill", {"name": "probe-sicher", "inhalt": "1. Neu."},
         [(skills, "laden", leer)]),
        ("propose_skill", {"name": "probe-zwei", "beschreibung": "Wenn y.", "inhalt": "1. A."},
         [(skills, "laden", leer)]),
        ("create_document", {"titel": "Neu", "inhalt": "x"},
         [(ablage, "lesen", lambda *a, **k: None)]),
        ("update_document", {"id": ids["doc"], "inhalt": "zwei"},
         [(ablage, "lesen", lambda *a, **k: None)]),
        ("save_from_sandbox", {"lauf": "x", "datei": "n.txt"},
         [(ablage, "lesen", lambda *a, **k: None)]),
        ("create_pdf", {"titel": "Q", "inhalt": "Text."},
         [(ki_pdf_word, "_pdf_beleg", lambda *a: None)]),
        ("combine_pdf", {"titel": "M", "teile": [{"quelle": ids["pdf"]}]},
         [(ki_pdf_word, "_pdf_beleg", lambda *a: None)]),
        ("create_docx", {"titel": "C", "inhalt": "Hallo."},
         [(ki_pdf_word, "_docx_beleg", lambda *a, **k: None)]),
        ("edit_docx", {"quelle": ids["docx"], "ersetzen": [{"alt": "Frau Meier", "neu": "Herr K"}]},
         [(ki_pdf_word, "_docx_beleg", lambda *a, **k: None)]),
        # Browser-Bild (2026-10-09): eine offene Seite als Attrappe.
        ("browser_screenshot", {},
         [(browser_sitzung, "offen", lambda gid: True),
          (browser_sitzung, "bildschirmfoto",
           lambda gid, n: (b"\x89PNG\r\n\x1a\n" + b"0" * 50, "https://example.org/")),
          (ablage, "lesen", lambda *a, **k: None)]),
    ]


def _skill_ordner_bauen(name):
    """Ein gültiger Skill-Ordner in Input/ für import_skill (2026-10-09)."""
    import nutzer_ordner
    from pathlib import Path
    wo = Path(nutzer_ordner.unterordner()) / name
    wo.mkdir()
    (wo / "SKILL.md").write_text(f"---\nname: {wo.name}\ndescription: Wenn z.\n---\n\n1. B.\n",
                                 encoding="utf-8")
    return name


def _zip_bauen(name):
    """Eine Zip in Input/ für unzip/remove_input (2026-10-09)."""
    import zipfile
    import nutzer_ordner
    with zipfile.ZipFile(os.path.join(nutzer_ordner.unterordner(), name), "w") as z:
        z.writestr("a.txt", "eins")
    return name


def test_abbruch_nach_dem_schreiben_laesst_alles_wie_es_war(wurzeln, umgebung, monkeypatch):  # noqa: F811
    ids = _vorbereiten()
    gesehen = set()
    faelle = _faelle(ids) + [
        # Nachgelesen nicht in der Liste → der neue Ordner ist wieder weg.
        ("import_skill", {"pfad": _skill_ordner_bauen("probe-import")},
         [(skills, "aktive", lambda: [])]),
        # unzip/remove_input (2026-10-09): nachgezählt falsch → Output/ wie vorher;
        # nachgesehen nicht im Papierkorb → zurück in Input/.
        ("unzip", {"datei": _zip_bauen("probe.zip")},
         [(input_dateien, "nachgezaehlt", lambda ziel: (0, 0))]),
        ("remove_input", {"datei": _zip_bauen("weg.zip")},
         [(input_dateien, "liegt", lambda neu, alt: False)]),
    ]
    for name, args, attrappen in faelle:
        vorher = _stand(wurzeln)
        with monkeypatch.context() as m:
            for modul, attr, ersatz in attrappen:
                m.setattr(modul, attr, ersatz)
            r = ki_werkzeuge._verteilen(name, args)
        assert r.status == "fehlgeschlagen" and r.code == "W-NICHT-GESPEICHERT", (name, r)
        assert "ABGEBROCHEN" in r, (name, r)
        assert _stand(wurzeln) == vorher, name
        gesehen.add(name)
    schreibend = {w.name for w in werkzeug_register.WERKZEUGE if w.schreibt}
    kalender = {n for n in schreibend if "calendar" in n}
    # create_series: eine neue Reihe, die nachgelesen fehlt — eigener Test unten.
    assert schreibend - kalender - gesehen == {"create_series"}


def test_create_series_abbruch_laesst_alles_wie_es_war(wurzeln, monkeypatch):
    import graphs
    vorher = _stand(wurzeln)
    echt = graphs.list_graphs
    zaehler = {"n": 0}

    def blind():
        zaehler["n"] += 1
        return echt() if zaehler["n"] <= 2 else []
    monkeypatch.setattr(graphs, "list_graphs", blind)
    r = ki_werkzeuge._verteilen("create_series", {"name": "Schlaf"})
    assert r.code == "W-NICHT-GESPEICHERT"
    assert _stand(wurzeln) == vorher


@pytest.mark.parametrize("name, args, code", [
    ("write_note", {"name": "x", "text": "  "}, "N-TEXT-LEER"),
    ("rewrite_note", {"name": "", "content": "x"}, "N-NAME-LEER"),
    ("create_series", {"name": ""}, "M-NAME-LEER"),
    ("log_series", {"series": "gibtsnicht", "value": 1}, "M-UNBEKANNT"),
    ("update_document", {"id": "x-1", "inhalt": "y"}, "A-DOK-UNBEKANNT"),
    ("combine_pdf", {"teile": []}, "P-TEILE-FEHLEN"),
    ("edit_docx", {"quelle": ""}, "P-QUELLE-FEHLT"),
])
def test_abbruch_vor_dem_schreiben_mit_code(wurzeln, name, args, code):
    vorher = _stand(wurzeln)
    r = ki_werkzeuge._verteilen(name, args)
    assert r.status == "fehlgeschlagen" and r.code == code and f"Fehler {code}:" in r
    assert _stand(wurzeln) == vorher
