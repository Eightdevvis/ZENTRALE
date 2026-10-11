"""Excel und CSV über die Ablage (2026-10-11, Skill excel).

Anlass: Führerschein-Gespräch 20261011-081303 — Sasha wollte Kosten und
Stunden tracken; die KI hatte nur PDFs und erklärte ihm SUMMEWENN zum
Abtippen. Geprüft: anlegen → lesen (Formeln sichtbar) → ändern (alt im
Papierkorb), deutsche Formeln, CSV, kaputte/zu große Dateien, Gate.
KEINE Modellaufrufe.
"""
import io
import zipfile

import pytest

import ablage
import ablage_text
import erlaubnis
import ki_werkzeuge
import tabelle_datei
import tabelle_formel
from werkzeug_befund import Befund


def _rufen(name, **args):
    r = ki_werkzeuge._verteilen(name, args)
    assert isinstance(r, Befund), r
    return r


KOSTEN = [["Posten", "Betrag", "Status"],
          ["Grundbetrag", 380, "bezahlt"],
          ["Fahrstunde", 60, "offen"],
          ["Bezahlt", "=SUMMEWENN(C:C;\"bezahlt\";B:B)", None]]


def _anlegen(**extra):
    r = _rufen("create_xlsx", titel="Führerschein-Tracking",
               blaetter=[{"name": "Kosten", "zeilen": KOSTEN, "spaltenbreiten": [20, 10, 10]}],
               **extra)
    assert r.status == "ok", r
    return r, r.split("(id ", 1)[1].split(")", 1)[0]


# ── Formeln ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ein, aus", [
    ('=SUMMEWENN(C:C;"bezahlt";B:B)', '=SUMIF(C:C,"bezahlt",B:B)'),
    ('=SUMIF(C:C,"paid",B:B)', '=SUMIF(C:C,"paid",B:B)'),
    ("=B1-SUMME(B3:B20)", "=B1-SUM(B3:B20)"),
    ("=WENN(A1>0;2,5;WAHR)", "=IF(A1>0,2.5,TRUE)"),
    ('="a;b"&LINKS(A1;2)', '="a;b"&LEFT(A1,2)'),        # Text in "…" bleibt
    ("=XVERWEIS(A1;B:B;C:C)", "=_xlfn.XLOOKUP(A1,B:B,C:C)"),
    ("='Mein Blatt'!A1*2", "='Mein Blatt'!A1*2"),
])
def test_deutsche_formeln_werden_sicher_uebersetzt(ein, aus):
    assert tabelle_formel.uebersetzen(ein)[0] == aus


@pytest.mark.parametrize("boese", ["=FOO(1)", '=SUM("a)', "=SUM(1)\n+1", "SUM(1)"])
def test_unsichere_formeln_brechen_ab(boese):
    with pytest.raises(tabelle_formel.FormelFehler):
        tabelle_formel.uebersetzen(boese)


# ── Anlegen → lesen → ändern ───────────────────────────────────────────

def test_anlegen_nennt_formeln_als_formeln_und_was_uebersetzt_wurde():
    r, doc_id = _anlegen()
    assert "Excel-Tabelle „Führerschein-Tracking“ ANGELEGT" in r
    assert 'Kosten!B4 =SUMIF(C:C,"bezahlt",B:B)' in r
    assert "KEIN Wert berechnet" in r and "SUMMEWENN→SUMIF" in r
    assert "440" not in r                               # nichts vorgetäuscht
    assert r.beleg and "11 gefüllte Zellen" in r.beleg
    k = ablage.kopf(doc_id)
    assert k["art"] == "xlsx" and not ablage.von_sasha(k)
    assert not erlaubnis.braucht_erlaubnis("create_xlsx", {"titel": "x", "blaetter": []})


def test_lesen_zeigt_adressen_text_zahlen_und_formeln():
    _r, doc_id = _anlegen()
    r = _rufen("read_xlsx", id=doc_id)
    assert r.status == "ok"
    assert 'A2 "Grundbetrag" | B2 380 | C2 "bezahlt"' in r
    assert 'B4 =SUMIF(C:C,"bezahlt",B:B) → (kein gespeicherter Wert)' in r
    assert "Blätter: Kosten (A1:C4)" in r
    r = _rufen("read_xlsx", id=doc_id, bereich="B2:B3")
    assert "B2 380" in r and "A2" not in r
    assert _rufen("read_xlsx", id=doc_id, blatt="Gibts").code == "T-BLATT-UNBEKANNT"
    assert _rufen("read_xlsx", id=doc_id, bereich="X").code == "T-BEREICH"


def test_gespeicherter_wert_aus_excel_wird_gezeigt():
    """Eine von Excel gespeicherte Datei bringt den Wert der Formel mit."""
    _r, doc_id = _anlegen()
    roh = ablage.roh(doc_id)
    z = zipfile.ZipFile(io.BytesIO(roh))
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w") as neu:
        for info in z.infolist():
            daten = z.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                daten = daten.replace(b"</f><v /></c>", b"</f><v>380</v></c>")
            neu.writestr(info, daten)
    k = ablage.anlegen("Aus Excel", aus.getvalue(), "xlsx", herkunft="anhang")
    r = _rufen("read_xlsx", id=k["id"])
    assert '=SUMIF(C:C,"bezahlt",B:B) → 380' in r


def test_aendern_eigene_tabelle_ersetzt_alt_im_papierkorb():
    _r, alt = _anlegen()
    assert not erlaubnis.braucht_erlaubnis("edit_xlsx", {"id": alt})
    r = _rufen("edit_xlsx", id=alt, aenderungen=[{"zelle": "C3", "wert": "bezahlt"}],
               anhaengen=[["Sonderfahrt", 70, "offen"]])
    assert r.status == "ok", r
    assert "GEÄNDERT als neue Fassung" in r and f"die alte ({alt}) liegt im Papierkorb" in r
    assert 'C3 = "bezahlt"' in r and "1 Zeile angehängt (Kosten, Zeile 5)" in r
    assert ablage.im_papierkorb(ablage.kopf(alt))
    neu = ablage.kopf(alt)["ersetzt_durch"]
    t = _rufen("read_xlsx", id=neu)
    assert 'C3 "bezahlt"' in t and 'A5 "Sonderfahrt" | B5 70' in t
    assert [d["id"] for d in ablage.liste()] == [neu]


def test_sashas_tabelle_fragt_jedes_mal_und_daneben_nicht():
    _r, ki = _anlegen()
    k = ablage.anlegen("Preise.xlsx", ablage.roh(ki), "xlsx", herkunft="anhang")
    args = {"id": k["id"], "aenderungen": [{"zelle": "B2", "wert": 400}]}
    assert erlaubnis.braucht_erlaubnis("edit_xlsx", args)
    assert erlaubnis.optionen("edit_xlsx", args) == ["ja, nur dieses mal", "nein"]
    assert erlaubnis.frage("edit_xlsx", args).startswith("„Preise.xlsx“ hast du abgelegt")
    assert not erlaubnis.braucht_erlaubnis("edit_xlsx", dict(args, daneben=True))
    r = _rufen("edit_xlsx", daneben=True, **args)
    assert r.status == "ok" and "als NEUE Tabelle daneben" in r
    assert not ablage.im_papierkorb(ablage.kopf(k["id"]))
    assert "B2 380" in _rufen("read_xlsx", id=k["id"])          # Original unverändert


def test_aendern_bricht_kontrolliert_ab():
    _r, doc_id = _anlegen()
    vorher = ablage.alle_ids()
    assert _rufen("edit_xlsx", id=doc_id).code == "T-NICHTS-ZU-AENDERN"
    assert _rufen("edit_xlsx", id=doc_id, aenderungen=[{"zelle": "Z0", "wert": 1}]).code == "T-ZELLE"
    assert _rufen("edit_xlsx", id=doc_id,
                  aenderungen=[{"zelle": "A1", "wert": "=GIBTSNICHT(1)"}]).code == "T-FORMEL"
    assert _rufen("edit_xlsx", id=doc_id,
                  aenderungen=[{"blatt": "Nix", "zelle": "A1", "wert": 1}]).code == "T-BLATT-UNBEKANNT"
    assert _rufen("edit_xlsx", id="gibts-nicht-0000", anhaengen=[[1]]).code == "A-DOK-UNBEKANNT"
    text = ablage.anlegen("Notiz", "x", "text")["id"]
    assert _rufen("edit_xlsx", id=text, anhaengen=[[1]]).code == "T-FALSCHE-ART"
    assert set(ablage.alle_ids()) == set(vorher) | {text}
    assert not ablage.im_papierkorb(ablage.kopf(doc_id))


def test_nachgelesen_falsch_laesst_alles_wie_es_war(monkeypatch):
    import ki_tabelle
    _r, doc_id = _anlegen()
    vorher = ablage.alle_ids()
    monkeypatch.setattr(ki_tabelle, "_nachlesen", lambda *a: None)
    r = _rufen("edit_xlsx", id=doc_id, anhaengen=[["x", 1]])
    assert r.code == "W-NICHT-GESPEICHERT"
    assert ablage.alle_ids() == vorher and not ablage.im_papierkorb(ablage.kopf(doc_id))
    r = _rufen("create_xlsx", titel="Weg", blaetter=[{"zeilen": [[1]]}])
    assert r.code == "W-NICHT-GESPEICHERT" and ablage.alle_ids() == vorher


def test_tabelle_mit_diagramm_wird_nicht_veraendert():
    _r, doc_id = _anlegen()
    roh = ablage.roh(doc_id)
    aus = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(roh)) as z, zipfile.ZipFile(aus, "w") as neu:
        for info in z.infolist():
            neu.writestr(info, z.read(info.filename))
        neu.writestr("xl/drawings/drawing1.xml", "<x/>")
    k = ablage.anlegen("Mit Diagramm", aus.getvalue(), "xlsx")
    r = _rufen("edit_xlsx", id=k["id"], anhaengen=[[1]])
    assert r.code == "T-VERLUST" and "Diagramme" in r
    assert not ablage.im_papierkorb(ablage.kopf(k["id"]))


# ── Werte ──────────────────────────────────────────────────────────────

def test_zahlen_als_text_werden_zahlen_aber_nicht_zweideutige():
    r = _rufen("create_xlsx", titel="Z", blaetter=[{"zeilen": [["60", "60,5", "1.000", "0815",
                                                                 "60 €", True, None, 2.25]]}])
    assert r.status == "ok", r
    t = _rufen("read_xlsx", id=r.split("(id ", 1)[1].split(")", 1)[0])
    assert 'A1 60 | B1 60.5 | C1 "1.000" | D1 "0815" | E1 "60 €" | F1 WAHR | H1 2.25' in t


@pytest.mark.parametrize("blaetter, code", [
    ([], "T-BLAETTER-FEHLEN"),
    ([{"zeilen": [[None, ""]]}], "T-BLAETTER-FEHLEN"),
    ([{"name": "x" * 32, "zeilen": [[1]]}], "T-BLATTNAME"),
    ([{"name": "a/b", "zeilen": [[1]]}], "T-BLATTNAME"),
    ([{"name": "A", "zeilen": [[1]]}, {"name": "a", "zeilen": [[1]]}], "T-BLATTNAME"),
    ([{"zeilen": [[{"x": 1}]]}], "T-WERT-UNGUELTIG"),
    ([{"zeilen": [["x" * 40_000]]}], "T-WERT-UNGUELTIG"),
])
def test_anlegen_lehnt_ab_und_legt_nichts_an(blaetter, code):
    r = _rufen("create_xlsx", titel="T", blaetter=blaetter)
    assert r.code == code, r
    assert ablage.alle_ids() == []


# ── CSV ────────────────────────────────────────────────────────────────

def test_csv_anlegen_lesen_aendern_neue_fassung():
    r = _rufen("create_xlsx", titel="Stunden", format="csv",
               blaetter=[{"zeilen": [["Datum", "Art", "Minuten"], ["2026-10-11", "Übung", 45]]}])
    assert r.status == "ok", r
    doc_id = r.split("(id ", 1)[1].split(")", 1)[0]
    k = ablage.kopf(doc_id)
    assert k["art"] == "csv"
    assert ablage.lesen(doc_id)["inhalt"] == "Datum;Art;Minuten\n2026-10-11;Übung;45\n"
    t = _rufen("read_xlsx", id=doc_id)
    assert "Trenner „;“" in t and 'B2 "Übung"' in t
    r = _rufen("edit_xlsx", id=doc_id, anhaengen=[["2026-10-12", "Sonderfahrt", 90]])
    assert r.status == "ok" and "als Fassung 2" in r, r
    assert ablage.lesen(doc_id, 1)["inhalt"].count("\n") == 2       # alte Fassung bleibt
    assert _rufen("create_xlsx", titel="F", format="csv",
                  blaetter=[{"zeilen": [["=SUM(1)"]]}]).code == "T-CSV-FORMEL"


@pytest.mark.parametrize("text, trenner", [
    ("a,b,c\n1,2,3\n", ","),
    ("a;b;c\n1,5;2;3\n", ";"),               # deutsche Dezimalzahl, Semikolon
    ("a\tb\n1\t2\n", "\t"),
])
def test_csv_trenner_wird_erkannt(text, trenner):
    zeilen, t = tabelle_datei.csv_lesen(text)
    assert t == trenner and zeilen[0][:2] == ["a", "b"]


# ── Kaputt, groß, Zip-Bombe ────────────────────────────────────────────

def test_kaputt_zu_gross_und_zip_bombe():
    with pytest.raises(tabelle_datei.Fehler) as e:
        tabelle_datei.lesen(b"PK\x03\x04 kaputt")
    assert e.value.art == "kaputt"
    with pytest.raises(tabelle_datei.Fehler) as e:
        tabelle_datei.lesen(b"\xd0\xcf\x11\xe0" + b"0" * 100)
    assert e.value.art == "gesperrt"
    bombe = io.BytesIO()
    with zipfile.ZipFile(bombe, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", "<x/>")
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (tabelle_datei.MAX_ENTPACKT + 1))
    with pytest.raises(tabelle_datei.Fehler) as e:
        tabelle_datei.lesen(bombe.getvalue())
    assert e.value.art == "zu_gross"


def test_zeitgrenze_im_kindprozess(monkeypatch):
    import subprocess

    def zu_langsam(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)
    _r, doc_id = _anlegen()
    monkeypatch.setattr(subprocess, "run", zu_langsam)
    r = _rufen("read_xlsx", id=doc_id)
    assert r.code == "T-ZEIT"


# ── Ablage-Vorschau und Anhang ─────────────────────────────────────────

def test_vorschau_und_anhang_kennen_xlsx():
    import anhang
    roh = tabelle_datei.erzeugen([{"name": "A", "zeilen": [["x", 1]]}])
    assert ablage_text.art_von(roh) == "xlsx"
    erg = anhang.annehmen("/tmp/kosten.xlsx", roh)
    assert erg["art"] == "xlsx"
    t = ablage_text.text(erg["id"])
    assert 'A1 "x" | B1 1' in t["text"]
    assert "read_xlsx" in ablage_text.kopfzeile(t, erg["id"])
