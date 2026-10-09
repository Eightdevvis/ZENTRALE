"""Zips aus Input/ auspacken (unzip) und Input/ aufräumen (remove_input,
Aufräum-Zeile + offene Zusage) — 2026-10-09.

Sasha: „ob sie das file aus dem ordner dann removed afterwards damit der
ordner nich zur halde wird". Geprüft wird Verhalten: was nach einem Aufruf
in Output/, Input/ und im Papierkorb liegt, was NICHT geschrieben wird
(Zip-Slip, zu groß, Ziel schon da), welche Zeile die KI im Ergebnis liest
und welche Zusage im Gespräch offen steht — und wann sie abgehakt ist.
"""
import os
import stat
import zipfile
from datetime import date
from pathlib import Path

import pytest

import ehrlichkeit
import erlaubnis
import gedaechtnis
import gespraeche
import input_aufraeumen
import input_dateien
import ki_werkzeuge
import nutzer_ordner
import pdf_schreiben
import skills
import state
import werkzeug_befund
import zug
import zusagen

HINWEIS = "Frag Sasha jetzt, ob {} aus Input weg soll (remove_input)."


@pytest.fixture(autouse=True)
def umgebung(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "Zentrale"))
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_DIR", str(leer / "anthropic"))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "anthropic" / "zentrale.json"))
    monkeypatch.setenv("ZENTRALE_EHRLICHKEIT_PRUEFER", "an")


@pytest.fixture
def gespraech():
    """Ein laufender Zug auf der gross-Schiene in einem frischen Gespräch."""
    gid = gespraeche.neu("input")
    z = zug.beginnen(gid)
    s = werkzeug_befund.schiene_setzen("gross")
    yield gid
    werkzeug_befund.schiene_zuruecksetzen(s)
    zug.beenden(z)


@pytest.fixture
def ein():
    return Path(nutzer_ordner.unterordner(nutzer_ordner.INPUT))


@pytest.fixture
def aus():
    return Path(nutzer_ordner.unterordner(nutzer_ordner.OUTPUT))


def _zip(pfad, eintraege: dict, symlinks=()):
    with zipfile.ZipFile(pfad, "w") as z:
        for name, text in eintraege.items():
            z.writestr(name, text)
        for name in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return str(pfad)


def _fotos(ein):
    return _zip(ein / "Fotos.zip", {"Fotos/a.txt": "eins", "Fotos/b/c.md": "zwei",
                                    "Fotos/.env": "KEY=1", ".DS_Store": "x",
                                    "__MACOSX/Fotos/._a.txt": "y"})


def _rufen(werkzeug, **args):
    return ki_werkzeuge._verteilen(werkzeug, args)


def _offen(gid):
    return [z for z in zusagen.offen(gid) if z.get("art")]


def _alles(ordner: Path) -> list:
    return sorted(str(p.relative_to(ordner)) for p in ordner.rglob("*"))


# ── unzip ───────────────────────────────────────────────────────────────

def test_ansehen_zeigt_inhalt_und_packt_nichts_aus(ein, aus, gespraech):
    _fotos(ein)
    r = _rufen("unzip", datei="Fotos.zip", ansehen=True)
    assert r.status == "ok"
    assert "2 Dateien" in r and "Fotos/a.txt" in r and "Fotos/b/c.md" in r
    assert "Fotos/.env" in r and "ausgelassen" in r.lower()
    assert "Output/Fotos/" in r
    assert _alles(aus) == []
    assert HINWEIS.format("Fotos.zip") not in r and _offen(gespraech) == []
    # ansehen ist frei, auspacken wird bestätigt.
    assert not erlaubnis.braucht_erlaubnis("unzip", {"datei": "Fotos.zip", "ansehen": True})
    assert not erlaubnis.braucht_erlaubnis("unzip", {"datei": "Fotos.zip", "ansehen": "true"})
    assert erlaubnis.braucht_erlaubnis("unzip", {"datei": "Fotos.zip"})


def test_frage_nennt_ziel_zahl_und_groesse(ein):
    _fotos(ein)
    f = erlaubnis.frage("unzip", {"datei": "Fotos.zip"})
    assert f.startswith("„Fotos.zip“ nach Output/Fotos/ auspacken? 2 Dateien")
    assert "3 ausgelassen" in f
    assert erlaubnis.frage("remove_input", {"datei": "Fotos.zip"}) == \
        "„Fotos.zip“ aus Input entfernen? (kommt in den Papierkorb)"


def test_auspacken_legt_alles_nach_output_mit_beleg(ein, aus, gespraech):
    _fotos(ein)
    r = _rufen("unzip", datei="Fotos.zip")
    assert r.status == "ok", r
    assert r.startswith("„Fotos.zip“ AUSGEPACKT nach Output/Fotos/: 2 Dateien")
    assert "nachgezählt 2 Dateien" in r.beleg
    assert (aus / "Fotos" / "Fotos" / "a.txt").read_text() == "eins"
    assert (aus / "Fotos" / "Fotos" / "b" / "c.md").read_text() == "zwei"
    assert not (aus / "Fotos" / "Fotos" / ".env").exists()
    assert "Fotos/.env" in r                      # sagt, welche ausgelassen
    assert [p for p in os.listdir(aus) if p.startswith(".")] == []   # kein Rest
    assert (ein / "Fotos.zip").exists()           # die Zip bleibt, bis Sasha ja sagt
    assert r.rstrip().endswith(HINWEIS.format("Fotos.zip"))
    (z,) = _offen(gespraech)
    assert z["art"] == "input_aufraeumen: Fotos.zip"


@pytest.mark.parametrize("eintraege,symlinks,code", [
    ({"../../boese.txt": "x", "gut.txt": "y"}, (), "Z-UNSICHER"),
    ({"/etc/boese": "x"}, (), "Z-UNSICHER"),
    ({"gut.txt": "y"}, ("link",), "Z-UNSICHER"),
])
def test_zip_slip_schreibt_nichts(ein, aus, gespraech, eintraege, symlinks, code):
    _zip(ein / "boese.zip", eintraege, symlinks)
    r = _rufen("unzip", datei="boese.zip")
    assert r.status == "fehlgeschlagen" and r.code == code, r
    assert "ABGEBROCHEN" in r and "nichts ausgepackt" in r
    assert _alles(aus) == []
    assert _offen(gespraech) == [] and "remove_input" not in r


def test_zu_gross_schreibt_nichts(ein, aus, gespraech, monkeypatch):
    monkeypatch.setattr(input_dateien, "MAX_BYTES", 1000)
    _zip(ein / "gross.zip", {"a.bin": "x" * 600, "b.bin": "y" * 600})
    r = _rufen("unzip", datei="gross.zip")
    assert r.code == "Z-ZU-GROSS" and _alles(aus) == []
    # ansehen geht trotzdem und sagt, warum Auspacken nicht geht.
    r = _rufen("unzip", datei="gross.zip", ansehen=True)
    assert r.status == "ok" and "zu groß" in r
    monkeypatch.setattr(input_dateien, "MAX_BYTES", 10 ** 7)
    monkeypatch.setattr(input_dateien, "MAX_DATEIEN", 1)
    r = _rufen("unzip", datei="gross.zip")
    assert r.code == "Z-ZU-GROSS" and _alles(aus) == []
    assert _offen(gespraech) == []


def test_ziel_gibt_es_schon_nichts_ueberschrieben(ein, aus, gespraech):
    _fotos(ein)
    (aus / "Fotos").mkdir()
    (aus / "Fotos" / "mein.txt").write_text("bleibt")
    r = _rufen("unzip", datei="Fotos.zip")
    assert r.code == "Z-ZIEL-GIBT-ES"
    assert _alles(aus) == ["Fotos", "Fotos/mein.txt"]
    assert (aus / "Fotos" / "mein.txt").read_text() == "bleibt"
    assert _offen(gespraech) == []


def test_nur_aus_input_und_nur_zips(ein, aus, tmp_path):
    draussen = _zip(tmp_path / "draussen.zip", {"a.txt": "x"})
    assert _rufen("unzip", datei=draussen).code == "Z-QUELLE-AUSSERHALB"
    assert _rufen("unzip", datei="gibtsnicht.zip").code == "Z-QUELLE-FEHLT"
    (ein / "text.txt").write_text("kein zip")
    assert _rufen("unzip", datei="text.txt").code == "Z-KEINE-ZIP"
    (ein / "kaputt.zip").write_bytes(b"PK\x03\x04 kaputt")
    assert _rufen("unzip", datei="kaputt.zip").code in ("Z-KEINE-ZIP", "Z-ZIP-KAPUTT")
    _zip(ein / "nur_versteckt.zip", {".env": "x"})
    assert _rufen("unzip", datei="nur_versteckt.zip").code == "Z-LEER"
    assert _alles(aus) == []


def test_auspacken_ist_ganz_oder_gar_nicht(ein, aus, monkeypatch):
    """Bricht es mitten im Auspacken ab, bleibt in Output/ nichts liegen."""
    import zip_sicher
    _zip(ein / "halb.zip", {"a.txt": "eins", "b.txt": "zwei"})
    echt = zip_sicher.auspacken

    def halb(datei, ziel, **k):
        Path(ziel, "a.txt").write_text("eins")
        raise zip_sicher.Fehler(zip_sicher.KAPUTT, "b.txt kaputt")
    monkeypatch.setattr(zip_sicher, "auspacken", halb)
    r = _rufen("unzip", datei="halb.zip")
    assert r.code == "Z-ZIP-KAPUTT" and _alles(aus) == []
    monkeypatch.setattr(zip_sicher, "auspacken", echt)


# ── remove_input ────────────────────────────────────────────────────────

def test_remove_input_verschiebt_in_den_papierkorb_mit_datum(ein, gespraech):
    (ein / "rechnung.pdf").write_bytes(b"%PDF-1.4 x")
    r = _rufen("remove_input", datei="Input/rechnung.pdf")
    heute = date.today().isoformat()
    korb = Path(nutzer_ordner.wurzel()) / ".Papierkorb" / heute
    assert r.status == "ok", r
    assert f".Papierkorb/{heute}/rechnung.pdf" in r and "AUS INPUT ENTFERNT" in r
    assert not (ein / "rechnung.pdf").exists()
    assert (korb / "rechnung.pdf").read_bytes() == b"%PDF-1.4 x"
    assert r.beleg


def test_remove_input_namenskonflikt_haengt_zaehler_an(ein):
    for inhalt in ("eins", "zwei", "drei"):
        (ein / "notiz.txt").write_text(inhalt)
        assert _rufen("remove_input", datei="notiz.txt").status == "ok"
    korb = Path(nutzer_ordner.wurzel()) / ".Papierkorb" / date.today().isoformat()
    assert sorted(os.listdir(korb)) == ["notiz (2).txt", "notiz (3).txt", "notiz.txt"]
    assert (korb / "notiz.txt").read_text() == "eins"
    assert (korb / "notiz (3).txt").read_text() == "drei"


def test_remove_input_nimmt_auch_ordner(ein):
    (ein / "Projekt").mkdir()
    (ein / "Projekt" / "a.md").write_text("x")
    assert _rufen("remove_input", datei="Projekt").status == "ok"
    korb = Path(nutzer_ordner.wurzel()) / ".Papierkorb" / date.today().isoformat()
    assert (korb / "Projekt" / "a.md").read_text() == "x"


def test_remove_input_nur_direkt_aus_input(ein, aus, tmp_path):
    (aus / "ergebnis.md").write_text("x")
    (ein / "Ordner").mkdir()
    (ein / "Ordner" / "tief.txt").write_text("x")
    (tmp_path / "draussen.txt").write_text("x")
    assert _rufen("remove_input", datei="Output/ergebnis.md").code == "Z-QUELLE-AUSSERHALB"
    assert _rufen("remove_input", datei=str(tmp_path / "draussen.txt")).code == "Z-QUELLE-AUSSERHALB"
    assert _rufen("remove_input", datei="Input/Ordner/tief.txt").code == "Z-NICHT-DIREKT"
    assert _rufen("remove_input", datei="../draussen.txt").code == "Z-QUELLE-AUSSERHALB"
    assert _rufen("remove_input", datei="").code == "Z-QUELLE-FEHLT"
    assert _rufen("remove_input", datei="Input").code == "Z-QUELLE-AUSSERHALB"
    assert (aus / "ergebnis.md").exists() and (ein / "Ordner" / "tief.txt").exists()
    assert (tmp_path / "draussen.txt").exists()
    assert not (Path(nutzer_ordner.wurzel()) / ".Papierkorb").exists() or \
        _alles(Path(nutzer_ordner.wurzel()) / ".Papierkorb") in ([], [date.today().isoformat()])


# ── Aufräum-Zeile und Zusage nach anderen Werkzeugen ────────────────────

def test_hinweis_nach_import_skill(ein, gespraech):
    _zip(ein / "Chefkoch.zip", {"chefkoch/SKILL.md": (
        "---\nname: chefkoch\ndescription: Wenn Sasha kochen will.\n---\n\n1. Vorrat lesen.\n")})
    r = _rufen("import_skill", pfad="Chefkoch.zip")
    assert r.status == "ok", r
    assert HINWEIS.format("Chefkoch.zip") in r
    assert [z["art"] for z in _offen(gespraech)] == ["input_aufraeumen: Chefkoch.zip"]


def test_kein_hinweis_nach_fehler(ein, gespraech):
    _zip(ein / "keinskill.zip", {"a.txt": "x"})
    r = _rufen("import_skill", pfad="keinskill.zip")
    assert r.status == "fehlgeschlagen" and "remove_input" not in r
    (ein / "kaputt.pdf").write_bytes(b"kein pdf")
    r = _rufen("read_pdf", quelle="Input/kaputt.pdf")
    assert r.status == "fehlgeschlagen" and "remove_input" not in r
    r = _rufen("read_file", path="Input/gibtsnicht.md")
    assert "remove_input" not in r
    assert _offen(gespraech) == []


def test_hinweis_nach_read_pdf_aus_input(ein, gespraech):
    roh, _ = pdf_schreiben.erzeugen("Rechnung", "# Rechnung\n\nBetrag 12 Euro.")
    (ein / "rechnung.pdf").write_bytes(roh)
    r = _rufen("read_pdf", quelle="Input/rechnung.pdf")
    assert r.status == "ok" and "Betrag 12 Euro" in r
    assert r.rstrip().endswith(HINWEIS.format("rechnung.pdf"))
    assert len(_offen(gespraech)) == 1
    # zweimal gelesen → dieselbe Zusage, nicht zwei
    _rufen("read_pdf", quelle="Input/rechnung.pdf")
    assert len(_offen(gespraech)) == 1


def test_hinweis_nach_read_file_und_fetch_document(ein, gespraech):
    (ein / "liste.md").write_text("[ ] Milch\n[ ] Brot\n")     # beginnt mit „["
    r = _rufen("read_file", path="Input/liste.md")
    assert r.startswith("[ ] Milch") and r.rstrip().endswith(HINWEIS.format("liste.md"))
    (ein / "plan.md").write_text("# Plan\n\nMontag Geige, Dienstag Chor. " * 5)
    r = _rufen("fetch_document", url="Input/plan.md", name="plan")
    assert r.status == "ok", r
    assert r.rstrip().endswith(HINWEIS.format("plan.md"))
    assert sorted(z["art"] for z in _offen(gespraech)) == [
        "input_aufraeumen: liste.md", "input_aufraeumen: plan.md"]


def test_kein_hinweis_fuer_unterordner_und_klein(ein, gespraech):
    (ein / "Ordner").mkdir()
    (ein / "Ordner" / "a.md").write_text("tief")
    assert "remove_input" not in _rufen("read_file", path="Input/Ordner/a.md")
    (ein / "b.md").write_text("flach")
    s = werkzeug_befund.schiene_setzen("klein")
    try:
        assert "remove_input" not in _rufen("read_file", path="Input/b.md")
    finally:
        werkzeug_befund.schiene_zuruecksetzen(s)
    assert _offen(gespraech) == []


# ── Zusage abhaken ──────────────────────────────────────────────────────

def _pruefer(gid):
    return ehrlichkeit.Pruefer(ehrlichkeit.AN, gespraech=gid)


def test_zusage_steht_im_umschlag_bis_remove_input_lief(ein, gespraech):
    (ein / "a.md").write_text("x")
    _rufen("read_file", path="Input/a.md")
    assert "Sasha fragen, ob a.md aus Input weg soll" in ehrlichkeit.umschlag_block()
    # Ein anderes schreibendes Werkzeug und Züge ohne Bezug haken sie NICHT ab.
    for _ in range(ehrlichkeit.verfall_zuege() + 2):
        p = _pruefer(gespraech)
        p.werkzeug("write_note", {"name": "tagebuch"}, "[ergebnis: ok]\nnotiert")
        p.abschluss("Gut.")
    assert len(_offen(gespraech)) == 1
    r = _rufen("remove_input", datei="a.md")
    assert r.status == "ok"
    assert _offen(gespraech) == [] and "a.md" not in ehrlichkeit.umschlag_block()


def test_zusage_erledigt_nach_nein_am_gate(ein, gespraech):
    (ein / "a.md").write_text("x")
    _rufen("read_file", path="Input/a.md")
    p = _pruefer(gespraech)
    p.werkzeug("remove_input", {"datei": "Input/a.md"},
               "[ergebnis: abgelehnt]\nSasha hat die Aktion 'remove_input' abgelehnt")
    p.abschluss("Okay, bleibt liegen.")
    assert _offen(gespraech) == [] and (ein / "a.md").exists()


@pytest.mark.parametrize("wahl,erledigt", [("Nein", True), ("behalten", True),
                                           ("Ja", False)])
def test_zusage_und_ask_choice(ein, gespraech, wahl, erledigt):
    (ein / "a.md").write_text("x")
    _rufen("read_file", path="Input/a.md")
    p = _pruefer(gespraech)
    p.werkzeug("ask_choice", {"frage": "Soll a.md aus Input weg?"},
               f"[ergebnis: ok]\nSasha hat gewählt: {wahl}.")
    p.abschluss("Gut.")
    assert (_offen(gespraech) == []) is erledigt


def test_ask_choice_zu_anderer_datei_zaehlt_nicht(ein, gespraech):
    (ein / "a.md").write_text("x")
    _rufen("read_file", path="Input/a.md")
    p = _pruefer(gespraech)
    p.werkzeug("ask_choice", {"frage": "Soll b.md weg?"}, "[ergebnis: ok]\nSasha hat gewählt: Nein.")
    p.abschluss("Gut.")
    assert len(_offen(gespraech)) == 1


def test_zusage_erledigt_wenn_datei_sonst_weg_ist(ein, gespraech):
    (ein / "a.md").write_text("x")
    _rufen("read_file", path="Input/a.md")
    (ein / "a.md").unlink()                     # Sasha hat selbst aufgeräumt
    _pruefer(gespraech).abschluss("Gut.")
    assert _offen(gespraech) == []


def test_ansehen_steht_nicht_in_der_erledigt_zeile():
    p = ehrlichkeit.Pruefer(ehrlichkeit.AN)
    p.werkzeug("unzip", {"datei": "x.zip", "ansehen": True}, "[ergebnis: ok]\nInhalt")
    p.werkzeug("unzip", {"datei": "x.zip"}, "[ergebnis: ok]\nAUSGEPACKT")
    p.werkzeug("remove_input", {"datei": "x.zip"}, "[ergebnis: ok]\nentfernt")
    assert ehrlichkeit.erledigt_zeile(ehrlichkeit.erledigt_liste(p.protokoll)) == \
        "✓ ausgepackt: x.zip · ✓ in den Papierkorb gelegt: x.zip"


def test_input_aufraeumen_ohne_gespraech_bleibt_still(ein):
    """Ohne laufenden Zug (Skripte, Tests): Zeile ja, Zusage nirgends."""
    (ein / "a.md").write_text("x")
    s = werkzeug_befund.schiene_setzen("gross")
    try:
        r = input_aufraeumen.nach_verarbeitung("Inhalt", str(ein / "a.md"))
    finally:
        werkzeug_befund.schiene_zuruecksetzen(s)
    assert r.endswith(HINWEIS.format("a.md"))
