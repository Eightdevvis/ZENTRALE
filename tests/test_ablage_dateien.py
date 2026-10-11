"""Die Datei-Werkzeuge der KI in der Ablage (2026-10-11): find_files,
search_files, list_files/read_file auf gross, unzip.

Sasha: „ja einfach nur die ablage dann" — Input/ und Output/ sind für die KI
abgebaut. Geblieben ist das Versprechen der Suchen (2026-10-09, „wie machst du
die regel gegen falsche nicht da meldungen?"): jede sagt ganz vorn, wie
vollständig sie war.
"""
import io
import zipfile

import pytest

import ablage
import ablage_suche
import erlaubnis
import ki_werkzeuge
import werkzeug_befund
import werkzeug_register


@pytest.fixture
def gross():
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


def _rufen(name, **args):
    return ki_werkzeuge._verteilen(name, args)


def _zip(titel, eintraege):
    roh = io.BytesIO()
    with zipfile.ZipFile(roh, "w") as z:
        for n, t in eintraege.items():
            z.writestr(n, t)
    return ablage.anlegen(titel, roh.getvalue(), "zip", herkunft="einwurf")["id"]


@pytest.mark.parametrize("name", ["find_files", "search_files"])
def test_suchen_sind_frei_und_nur_gross(name):
    w = werkzeug_register.eintrag(name)
    assert w.klein is None and w.gross and w.erlaubnis is False and not w.schreibt


# ── find_files ─────────────────────────────────────────────────────────

def test_find_files_nach_titel_vollstaendig():
    a = ablage.anlegen("Chefkoch ai-v1.zip", b"PK\x05\x06" + b"\0" * 18, "zip", herkunft="einwurf")
    ablage.anlegen("Chefkoch Notiz", "x", "markdown")
    ablage.anlegen("Einkauf", "x", "markdown")
    r = _rufen("find_files", muster="*chefkoch*")
    assert r.vollstaendig is True
    zeilen = r.splitlines()
    assert zeilen[0] == "Suche vollständig: 2 Treffer — durchsucht: Ablage (3 Dokumente)."
    assert any(a["id"] in z and "von Sasha" in z for z in zeilen)
    assert "Chefkoch ai-v1.zip" in _rufen("find_files", muster="chefkoch-ai")   # Trenner egal
    assert "Chefkoch ai-v1.zip" in _rufen("find_files", muster="*.ZIP")
    leer = _rufen("find_files", muster="*.pdf")
    assert leer.startswith("Suche vollständig: 0 Treffer") and leer.vollstaendig


def test_find_files_papierkorb_getrennt_und_ohne_muster():
    k = ablage.anlegen("Alt", "x", "text")
    ablage.papierkorb(k["id"])
    assert _rufen("find_files", muster="alt").startswith("Suche vollständig: 0 Treffer")
    r = _rufen("find_files", muster="alt", papierkorb=True)
    assert k["id"] in r and "im Papierkorb" in r
    assert _rufen("find_files", muster="").startswith("[Fehler")


def test_find_files_zaehlt_alle_zeigt_50():
    for i in range(55):
        ablage.anlegen(f"bild {i:02}", "x", "text")
    zeilen = _rufen("find_files", muster="bild*").splitlines()
    assert zeilen[0].startswith("Suche vollständig: 55 Treffer")
    assert len(zeilen) == 52 and zeilen[-1].startswith("  … 5 weitere Treffer nicht gezeigt")


# ── search_files ───────────────────────────────────────────────────────

def test_search_files_wie_grep_auch_in_pdf_und_excel():
    import pdf_schreiben
    import tabelle_datei
    t = ablage.anlegen("Notiz", "Zeile eins\nEisen und Zink\n", "markdown")
    p = ablage.anlegen("Preise", pdf_schreiben.erzeugen("P", "Fahrstunde 60 Euro")[0], "pdf")
    x = ablage.anlegen("Kosten", tabelle_datei.erzeugen(
        [{"name": "K", "zeilen": [["Fahrstunde", 60]]}]), "xlsx")
    ablage.anlegen("Skizze", b"\x89PNG\r\n\x1a\n", "bild", endung=".png")
    r = _rufen("search_files", text="eisen")
    assert r.vollstaendig and f"„Notiz“ (id {t['id']}):2: Eisen und Zink" in r
    r = _rufen("search_files", text="fahrstunde")
    assert p["id"] in r and x["id"] in r and r.vollstaendig
    assert "Ohne Text (Bild, Zip): 1" in r


def test_search_files_ehrlich_unvollstaendig(monkeypatch):
    for i in range(3):
        ablage.anlegen(f"N{i}", "treffer", "text")
    monkeypatch.setattr(ablage_suche, "MAX_TEXT_TREFFER", 2)
    r = _rufen("search_files", text="treffer")
    assert r.startswith("Suche NICHT vollständig: abgebrochen nach 2 Treffern")
    assert r.vollstaendig is False


def test_search_files_unlesbares_heisst_nicht_vollstaendig():
    ablage.anlegen("Kaputt", b"%PDF-1.4 kaputt", "pdf")
    r = _rufen("search_files", text="x")
    assert r.startswith("Suche NICHT vollständig: 1 Dokumente nicht lesbar") and not r.vollstaendig


# ── unzip ──────────────────────────────────────────────────────────────

def test_unzip_ansehen_ist_frei_auspacken_fragt():
    z = _zip("Fotos.zip", {"Fotos/a.txt": "eins", "Fotos/b/c.md": "# C", "Fotos/.env": "X=1"})
    assert not erlaubnis.braucht_erlaubnis("unzip", {"id": z, "ansehen": True})
    assert erlaubnis.braucht_erlaubnis("unzip", {"id": z})
    assert erlaubnis.frage("unzip", {"id": z}).startswith("„Fotos.zip“ auspacken? 2 Dateien")
    r = _rufen("unzip", id=z, ansehen=True)
    assert r.status == "ok" and "Fotos/a.txt" in r and "Fotos/.env" in r
    assert ablage.alle_ids() == [z]


def test_unzip_legt_jede_datei_als_dokument_von_sasha_an():
    z = _zip("Fotos.zip", {"Fotos/a.txt": "eins", "Fotos/b/c.md": "# C", "Fotos/x.bin": "\x00\x01",
                           "Fotos/.env": "X=1"})
    r = _rufen("unzip", id=z)
    assert r.status == "ok", r
    assert r.startswith("„Fotos.zip“ AUSGEPACKT: 2 Dokumente in der Ablage")
    assert "Fotos/x.bin" in r and "Fotos/.env" in r
    neu = [ablage.kopf(i) for i in ablage.alle_ids() if i != z]
    assert sorted(k["titel"] for k in neu) == ["Fotos/Fotos/a.txt", "Fotos/Fotos/b/c.md"]
    assert all(ablage.von_sasha(k) and k["herkunft"] == "ausgepackt" for k in neu)


def test_unzip_bricht_ab_und_legt_nichts_an():
    assert _rufen("unzip", id=ablage.anlegen("t", "x", "text")["id"]).code == "Z-KEINE-ZIP"
    leer = _zip("leer.zip", {"nur/.versteckt": "x"})
    assert _rufen("unzip", id=leer).code == "Z-LEER"
    boese = io.BytesIO()
    with zipfile.ZipFile(boese, "w") as zz:
        zz.writestr("../raus.txt", "x")
    b = ablage.anlegen("boese.zip", boese.getvalue(), "zip", herkunft="einwurf")["id"]
    assert _rufen("unzip", id=b).code == "Z-UNSICHER"
    assert set(ablage.alle_ids()) <= {leer, b} | {i for i in ablage.alle_ids()
                                                  if ablage.kopf(i)["art"] == "text"}


# ── list_files / read_file auf gross ───────────────────────────────────

def test_list_files_gross_ist_die_ablage(gross):
    k = ablage.anlegen("Plan", "x", "text")
    r = _rufen("list_files")
    assert r.startswith("Ablage — 1 Dokumente, vollständig") and k["id"] in r
    assert r.vollstaendig is True


def test_zip_als_anhang_und_vorschau():
    import anhang
    import ablage_text
    roh = io.BytesIO()
    with zipfile.ZipFile(roh, "w") as z:
        z.writestr("skills/a/SKILL.md", "x")
    erg = anhang.annehmen("/tmp/paket.zip", roh.getvalue())
    assert erg["art"] == "zip"
    t = ablage_text.text(erg["id"])
    assert "skills/a/SKILL.md" in t["text"] and "import_skill" in ablage_text.kopfzeile(t, erg["id"])
