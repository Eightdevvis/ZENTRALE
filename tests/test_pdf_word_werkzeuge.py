"""PDF- und Word-Werkzeuge der KI, Anhänge, Routen, Skills (2026-10-08).

Verhalten, das die KI und Sasha sehen: Status und Beleg im Ergebnis, neue
Dateien nur als neues Dokument in der Ablage (Original bleibt), Fragen vor
dem Anlegen, ehrliche Meldungen bei Scan/Passwort/Tippfehler, Quelle aus
Ablage oder ~/codicus (dieselbe Sperre wie read_file).
"""
import os
import re

import pytest

import ablage
import ablage_text
import anhang
import context
import ki_pdf_word
import ki_werkzeuge
import pdf_datei
import pdf_schreiben
import skill_format
import skills
import state
import werkzeug_register
import word_datei
import zug
from werkzeug_befund import Befund

from test_pdf_word_dateien import deutsches_docx, formular_pdf, scan_pdf, text_pdf, _p


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


def _id(ergebnis: str) -> str:
    return re.search(r"\(id ([a-z0-9-]+)", ergebnis).group(1)


def _ablegen(daten: bytes, art: str, titel="probe") -> str:
    return ablage.anlegen(titel, daten, art, herkunft="anhang", quelle=f"{titel}.{art}")["id"]


def lauf(name, args):
    return ki_werkzeuge._verteilen(name, args)


# ── Lesen ───────────────────────────────────────────────────────────────

def test_read_pdf_aus_der_ablage_mit_seiten_und_status():
    doc = _ablegen(text_pdf("Erste", "Zweite"), "pdf", "Skript")
    r = lauf("read_pdf", {"quelle": doc})
    assert isinstance(r, Befund) and r.status == "ok"
    assert r.startswith(f"„Skript“ (Ablage-id {doc}): PDF,") and "--- Seite 1 ---" in r


def test_langes_pdf_kommt_in_stuecken(monkeypatch):
    monkeypatch.setattr(ki_pdf_word, "SEITE_ZEICHEN", 3000)
    doc = _ablegen(text_pdf("A", "B", "C"), "pdf")
    r = lauf("read_pdf", {"quelle": doc})
    # Stückweise ist kein Teil-Ergebnis (2026-10-09): ok, und der Text sagt genau,
    # was gelesen ist und wie es weitergeht.
    assert r.status == "ok" and "Seiten 1 von 6 gelesen, weiter mit seiten=2-" in r
    weiter = re.search(r"seiten=([0-9-]+)", r).group(1)
    r2 = lauf("read_pdf", {"quelle": doc, "seiten": weiter})
    assert "--- Seite 2 ---" in r2


def test_read_pdf_tabellen_und_formular():
    doc = _ablegen(pdf_schreiben.erzeugen("R", "| A | B |\n|---|---|\n| 1 | 2 |")[0], "pdf")
    t = lauf("read_pdf", {"quelle": doc, "was": "tabellen"})
    assert "| A | B |" in t and "gegen den Text prüfen" in t
    f = lauf("read_pdf", {"quelle": _ablegen(formular_pdf(), "pdf"), "was": "formular"})
    assert "Formular mit 2 Feldern" in f and "- Name (text): Sasha" in f


def test_scan_und_passwort_werden_ehrlich_gemeldet():
    r = lauf("read_pdf", {"quelle": _ablegen(scan_pdf(), "pdf")})
    assert r.status == "fehlgeschlagen" and "gescannt" in r and r.code == "P-KEIN-TEXT"
    from test_pdf_word_dateien import verschluesselt
    r = lauf("read_pdf", {"quelle": _ablegen(verschluesselt(text_pdf("x"), "pw"), "pdf")})
    assert r.code == "P-DATEI-KAPUTT" and "Passwort" in r


def test_quelle_als_pfad_nur_mit_derselben_sperre_wie_read_file(tmp_path, monkeypatch):
    datei = tmp_path / "plan.pdf"
    datei.write_bytes(text_pdf("Plan"))
    monkeypatch.setattr(context, "erlaubt", lambda p: "ausserhalb von ZENTRALE und ~/codicus")
    r = lauf("read_pdf", {"quelle": str(datei)})
    assert r.code == "P-QUELLE-GESPERRT" and "anhängen" in r
    monkeypatch.setattr(context, "erlaubt", lambda p: "")
    r = lauf("read_pdf", {"quelle": str(datei)})
    assert r.status == "ok" and "„plan.pdf“ (Datei)" in r
    assert lauf("read_pdf", {"quelle": str(tmp_path / "gibtsnicht.pdf")}).code == "P-QUELLE-FEHLT"


def test_alter_text_anhang_sagt_dass_das_original_fehlt():
    alt = ablage.anlegen("vertrag.pdf", "Seite 1 Text", "text", herkunft="anhang",
                         quelle="vertrag.pdf")["id"]
    r = lauf("read_pdf", {"quelle": alt})
    assert "nur als Text" in r and "neu anhängen" in r
    assert "keine Word-Datei" in lauf("read_docx", {"quelle": _ablegen(text_pdf("x"), "pdf")})


def test_read_document_zeigt_auf_die_richtigen_werkzeuge():
    doc = _ablegen(text_pdf("x"), "pdf")
    assert f'read_pdf(quelle="{doc}")' in lauf("read_document", {"id": doc})


def test_read_docx_mit_hinweisen_und_weiterlesen():
    doc = _ablegen(deutsches_docx(_p("Kapitel", "berschrift1") + _p("Text " * 50),
                                  kopfzeile="Kopf"), "docx")
    r = lauf("read_docx", {"quelle": doc})
    assert r.status == "ok" and "# Kapitel" in r and "Kopf-/Fußzeilen" in r
    lang = _ablegen(deutsches_docx("".join(_p("Wort " * 100) for _ in range(60))), "docx")
    r = lauf("read_docx", {"quelle": lang})
    assert r.status == "ok" and "gelesen, weiter mit ab=20000" in r


# ── Schreiben: neue Datei, Beleg, Ereignis ──────────────────────────────

def _mit_zug(fn):
    marke = zug.beginnen("g-test")
    try:
        r = fn()
        return r, zug.abholen()
    finally:
        zug.beenden(marke)


def test_create_pdf_legt_ab_belegt_und_meldet():
    r, ereignisse = _mit_zug(lambda: lauf("create_pdf", {"titel": "Packliste",
                                                         "inhalt": "# Packen\n\n- Zelt\n- Kocher"}))
    assert r.status == "ok" and "Seite 1 beginnt mit „Packen" in r.beleg
    k = ablage.kopf(_id(r))
    assert k["art"] == "pdf" and k["gespraech"] == "g-test" and k["herkunft"] == "ki"
    assert ereignisse == [{"ablage": ablage.kurz(k)}]


def test_create_pdf_mit_fremden_zeichen_bricht_ab_ohne_datei():
    vorher = ablage.liste()
    r = lauf("create_pdf", {"titel": "Vokabeln", "inhalt": "你好 heißt Hallo"})
    assert r.status == "fehlgeschlagen" and r.code == "P-ZEICHEN" and "你" in r
    assert "nichts angelegt" in r and ablage.liste() == vorher


def test_combine_pdf_neu_aus_teilen_originale_bleiben():
    a = _ablegen(pdf_schreiben.erzeugen("A", "# Deckblatt")[0], "pdf", "Deckblatt")
    b = _ablegen(text_pdf("Haupt", "Anhang"), "pdf", "Hauptteil")
    vorher = ablage.roh(b)
    r = lauf("combine_pdf", {"titel": "Mappe", "teile": [{"quelle": a}, {"quelle": b, "seiten": "1"}]})
    assert r.status == "ok" and "2 Seiten" in r.beleg and "Deckblatt" in r
    assert ablage.roh(b) == vorher
    texte = [s["text"] for s in pdf_datei.lesen(ablage.roh(_id(r)))["seiten"]]
    assert "Deckblatt" in texte[0] and "Haupt" in texte[1]
    falsch = lauf("combine_pdf", {"titel": "x", "teile": [{"quelle": a, "seiten": "5"}]})
    assert falsch.code == "P-DATEI-KAPUTT" and "gibt es nicht" in falsch


def test_create_docx_und_edit_docx_als_kopie():
    r = lauf("create_docx", {"titel": "Brief", "inhalt": "# Brief\n\nLiebe Frau Meier,\n\nGruß"})
    assert r.status == "ok" and "1 Überschriften" in r.beleg
    quelle = _id(r)
    vorher = ablage.roh(quelle)
    e = lauf("edit_docx", {"quelle": quelle, "ersetzen": [{"alt": "Frau Meier", "neu": "Herr Kurz"}],
                           "anhaengen": "## PS\n\nBis bald."})
    assert e.status == "ok" and "1× ersetzt" in e and "unverändert" in e
    assert ablage.roh(quelle) == vorher
    neu = word_datei.lesen(ablage.roh(_id(e)))["text"]
    assert "Herr Kurz" in neu and "Frau Meier" not in neu and "## PS" in neu
    assert ablage.kopf(_id(e))["titel"] == "Brief (geändert)"


def test_edit_docx_tippfehler_bricht_ganz_ab():
    """Ganz oder gar nicht (2026-10-09): ein Treffer fehlt → keine Kopie."""
    quelle = _ablegen(deutsches_docx(_p("Hallo Welt")), "docx")
    vorher = len(ablage.liste())
    r = lauf("edit_docx", {"quelle": quelle, "ersetzen": [{"alt": "Hallo Welt", "neu": "Moin"},
                                                          {"alt": "Hallo welt", "neu": "x"}]})
    assert r.status == "fehlgeschlagen" and r.code == "P-ERSETZEN-FEHLT" and "Hallo welt" in r
    r = lauf("edit_docx", {"quelle": quelle, "ersetzen": [{"alt": "gibt es nicht", "neu": "x"}]})
    assert r.status == "fehlgeschlagen" and "keine Kopie" in r
    assert len(ablage.liste()) == vorher


# ── Erlaubnis ───────────────────────────────────────────────────────────

def test_anlegen_wird_gefragt_lesen_nicht():
    for name in ("create_pdf", "combine_pdf", "create_docx", "edit_docx"):
        assert werkzeug_register.braucht_erlaubnis(name, {"titel": "x"}), name
        assert werkzeug_register.immer_erlaubbar(name), name
        assert werkzeug_register.eintrag(name).klein is None
    for name in ("read_pdf", "read_docx"):
        assert not werkzeug_register.braucht_erlaubnis(name, {"quelle": "x"})
    doc = _ablegen(deutsches_docx(_p("x")), "docx", "Lebenslauf")
    f = werkzeug_register.frage("edit_docx", {"quelle": doc, "ersetzen": [
        {"alt": "2024", "neu": "2025"}], "anhaengen": "x"})
    assert "„Lebenslauf“" in f and "„2024“ → „2025“" in f and "anhängen" in f
    f = werkzeug_register.frage("combine_pdf", {"titel": "Mappe", "teile": [
        {"quelle": doc, "seiten": "1-2"}]})
    assert "Lebenslauf (Seiten 1-2)" in f and "Originale bleiben" in f


# ── Anhänge ─────────────────────────────────────────────────────────────

def test_word_anhang_bleibt_original_und_die_ki_liest_den_text():
    ablage_text._gemerkt.clear()
    daten = deutsches_docx(_p("Kapitel", "berschrift1") + _p("Inhalt"))
    r = anhang.annehmen("/tmp/bericht.docx", daten)
    assert r["art"] == "docx" and ablage.roh(r["id"]) == daten
    t = anhang.verlauf_einsetzen([{"role": "user", "content": "?",
                                   "anhaenge": anhang.verweise([r["id"]])}], True)
    text = t[0]["anhaenge"][0]["text"]
    assert "# Kapitel" in text and "edit_docx" in text and r["id"] in text


def test_gescanntes_pdf_wird_angenommen_mit_hinweis_doc_abgelehnt():
    r = anhang.annehmen("/tmp/scan.pdf", scan_pdf())
    assert r["art"] == "pdf" and "kein Text" in r["hinweis"]
    with pytest.raises(anhang.Abgelehnt, match=".docx"):
        anhang.annehmen("/tmp/alt.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 50)


# ── Routen und TUI ──────────────────────────────────────────────────────

def test_route_zeigt_text_und_liefert_die_datei():
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    doc = _ablegen(text_pdf("Vorschau"), "pdf", "Plan für Köln")
    d = c.get(f"/api/ablage/{doc}").get_json()
    assert d["inhalt"] is None and "Vorschau" in d["text"] and d["pfad"].endswith(".pdf")
    r = c.get(f"/api/ablage/{doc}/roh")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.headers["Content-Disposition"].startswith("attachment;")
    assert r.data == ablage.roh(doc)


def test_tui_liest_pdf_als_ort_und_vorschau():
    from tui.ansichten.ablage import ART_KURZ, lese_zeilen
    assert ART_KURZ["pdf"] == "pdf" and ART_KURZ["docx"] == "word"
    z = lese_zeilen({"kopf": {"art": "pdf"}, "inhalt": None, "bytes": 4096,
                     "pfad": "/x/v1.pdf", "text": "# Titel\n\nText"}, 40)
    texte = [t for t, _ in z]
    assert texte[0].startswith("eine pdf-datei (4 kb)") and "/x/v1.pdf" in texte
    assert any("Titel" in t for t in texte) and all(len(t) <= 40 for t in texte)


# ── Skills ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["pdf", "word"])
def test_skill_ist_gueltig_an_und_nennt_nur_echte_werkzeuge(name):
    ordner = os.path.join(skills.VORLAGEN_DIR, name)
    with open(os.path.join(ordner, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    _, kopf, rumpf = skill_format.zerlegen(text)
    assert kopf["name"] == name and len(kopf["description"]) < 400
    assert "<" not in kopf["description"] and ">" not in kopf["description"]
    genannt = set(re.findall(r"`([a-z]+_[a-z_]+)`", rumpf))
    bekannt = {w.name for w in werkzeug_register.WERKZEUGE}
    assert genannt and genannt <= bekannt, genannt - bekannt
    eintrag = next(s for s in skills.alle() if s["name"] == name)
    assert eintrag["status"] == "aktiv" and eintrag["herkunft"] == "zentrale"
    assert name in skills.prompt_block()
    assert not skills.liste_lage()["zu_lang"]
