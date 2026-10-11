"""Die Ablage als Ordner für Sasha (2026-10-11, core/ablage_sichtbar.py).

Sasha: „der user soll nich im code fischen gehen müssen" und „den ordner wo
ich sachen direkt reinschmeißen kann direkt nachrüsten". Geprüft wird das
Verhalten am Ordner: was er sieht, was er hineinlegt, was er ändert,
umbenennt oder löscht — und dass dabei nie etwas verloren geht.
"""
import json
import os
import subprocess
import sys
import time

import ablage
import ablage_sichtbar
import abgleich_auswahl
import dateien

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _w():
    return ablage.wurzel()


def _sichtbar():
    return sorted(n for n in os.listdir(_w()) if not n.startswith("."))


def _einwerfen(name, daten):
    p = os.path.join(_w(), name)
    os.makedirs(_w(), exist_ok=True)
    with open(p, "wb") as f:
        f.write(daten)
    return p


# ── Was die KI ablegt, sieht Sasha als Datei ──────────────────────────

def test_neues_dokument_liegt_lesbar_im_ordner():
    k = ablage.anlegen("Packliste", "- Zelt", "markdown")
    assert _sichtbar() == ["Packliste.md"]
    assert open(os.path.join(_w(), "Packliste.md"), encoding="utf-8").read() == "- Zelt"
    assert ablage_sichtbar.pfad(k["id"]) == os.path.join(_w(), "Packliste.md")


def test_gleicher_titel_bekommt_eine_nummer_und_neue_fassung_ersetzt_die_datei():
    a = ablage.anlegen("Plan", "eins", "text")
    ablage.anlegen("Plan", "anders", "text")
    assert _sichtbar() == ["Plan (2).txt", "Plan.txt"]
    ablage.neue_fassung(a["id"], "zwei")
    assert open(os.path.join(_w(), "Plan.txt")).read() == "zwei"
    assert ablage.lesen(a["id"], 1)["inhalt"] == "eins"          # alte Fassung bleibt


def test_anhang_mit_endung_im_titel_bekommt_sie_nicht_doppelt():
    ablage.anlegen("rechnung.pdf", b"%PDF-1.4 x", "pdf", herkunft="anhang")
    assert _sichtbar() == ["rechnung.pdf"]


# ── Einwurf ────────────────────────────────────────────────────────────

def test_eingeworfene_datei_wird_nach_zwei_blicken_ein_dokument_von_sasha():
    _einwerfen("Preise Fahrschule.txt", b"Fahrstunde 60 Euro")
    assert ablage_sichtbar.abgleichen()["neu"] == []          # erster Blick: abwarten
    b = ablage_sichtbar.abgleichen()
    assert len(b["neu"]) == 1
    k = ablage.kopf(b["neu"][0])
    assert k["titel"] == "Preise Fahrschule.txt" and k["herkunft"] == "einwurf"
    assert ablage.von_sasha(k) and k["abgelegt_von"] == "sasha"
    assert ablage.lesen(k["id"])["inhalt"] == "Fahrstunde 60 Euro"
    # Die Datei bleibt, wo Sasha sie hingelegt hat — keine Kopie daneben.
    assert _sichtbar() == ["Preise Fahrschule.txt"]
    assert ablage_sichtbar.abgleichen() == {"neu": [], "entfernt": [], "umbenannt": []}
    assert [n["titel"] for n in ablage_sichtbar.neu_seit(time.time() - 60)] == \
        ["Preise Fahrschule.txt"]


def test_halb_geschriebene_datei_wartet():
    p = _einwerfen("gross.txt", b"a" * 10)
    ablage_sichtbar.abgleichen()
    with open(p, "ab") as f:                               # wächst noch
        f.write(b"b" * 10)
    assert ablage_sichtbar.abgleichen()["neu"] == []
    assert len(ablage_sichtbar.abgleichen()["neu"]) == 1


def test_versteckte_schluessel_halbfertige_und_zu_grosse_dateien_bleiben_draussen(monkeypatch):
    import anhang
    monkeypatch.setattr(anhang, "DATEI_MAX_BYTES", 50)
    _einwerfen(".geheim", b"x")
    _einwerfen("id_rsa", b"-----BEGIN")
    _einwerfen("film.mp4.part", b"x")
    _einwerfen("riesig.txt", b"x" * 100)
    _einwerfen("binär.bin", b"\x00\x01\x02")
    for _ in range(3):
        assert ablage_sichtbar.abgleichen()["neu"] == []
    assert ablage.alle_ids() == []
    assert os.path.exists(os.path.join(_w(), "riesig.txt"))     # nichts angefasst


# ── Sasha ändert, benennt um, löscht ───────────────────────────────────

def test_sasha_aendert_die_datei_das_wird_eine_neue_fassung():
    k = ablage.anlegen("Notiz", "alt", "text")
    p = os.path.join(_w(), "Notiz.txt")
    with open(p, "w") as f:
        f.write("von Hand geändert")
    ablage_sichtbar.abgleichen()
    assert ablage.kopf(k["id"])["fassung"] == 2
    assert ablage.lesen(k["id"])["inhalt"] == "von Hand geändert"
    assert ablage.lesen(k["id"], 1)["inhalt"] == "alt"


def test_umbenennen_zieht_den_titel_nach():
    k = ablage.anlegen("Einkauf", "- Milch", "markdown")
    os.rename(os.path.join(_w(), "Einkauf.md"), os.path.join(_w(), "Wocheneinkauf.md"))
    b = ablage_sichtbar.abgleichen()
    assert b["umbenannt"] == [k["id"]] and b["neu"] == []
    assert ablage.kopf(k["id"])["titel"] == "Wocheneinkauf"
    assert ablage_sichtbar.abgleichen() == {"neu": [], "entfernt": [], "umbenannt": []}


def test_von_hand_geloescht_heisst_papierkorb_nichts_neu_und_nichts_verloren():
    k = ablage.anlegen("Weg", "inhalt", "text")
    os.remove(os.path.join(_w(), "Weg.txt"))
    assert ablage_sichtbar.abgleichen()["entfernt"] == [k["id"]]
    kk = ablage.kopf(k["id"])
    assert ablage.im_papierkorb(kk) and kk["papierkorb_grund"] == "von Sasha entfernt"
    assert ablage.lesen(k["id"])["inhalt"] == "inhalt"
    for _ in range(2):
        ablage_sichtbar.abgleichen()
    assert _sichtbar() == []
    # Zurückgeholt liegt die Datei wieder da.
    ablage.papierkorb(k["id"], False)
    assert _sichtbar() == ["Weg.txt"]


def test_papierkorb_raeumt_die_datei_in_den_versteckten_ordner():
    k = ablage.anlegen("Alt", "x", "text")
    ablage.papierkorb(k["id"])
    assert _sichtbar() == []
    korb = os.path.join(_w(), ".ablage", "papierkorb")
    assert os.listdir(korb) == [f"{k['id']}--Alt.txt"]


def test_neues_vom_anderen_rechner_erscheint_ohne_als_geloescht_zu_gelten():
    # Kopf + Fassung kommen per Abgleich; hier lag es noch nie.
    doc = os.path.join(ablage.ordner(), "20261011-vom-pc-abcd")
    os.makedirs(doc)
    dateien.json_schreiben(os.path.join(doc, "kopf.json"),
                           {"id": "20261011-vom-pc-abcd", "titel": "Vom PC", "art": "text",
                            "herkunft": "ki", "archiviert": False})
    dateien.atomar_schreiben(os.path.join(doc, "v1-pc.txt"), "hallo")
    b = ablage_sichtbar.abgleichen()
    assert b == {"neu": [], "entfernt": [], "umbenannt": []}
    assert _sichtbar() == ["Vom PC.txt"]
    # Stand gehört diesem Rechner allein.
    assert os.path.exists(os.path.join(_w(), ".ablage", f"sichtbar-{dateien.knoten()}.json"))


# ── Abgleich und Sicherung: dieselben Namen wie vorher ─────────────────

def test_abgleich_kennt_die_ablage_unter_ihrem_alten_namen(monkeypatch):
    monkeypatch.setattr(abgleich_auswahl, "_PROJEKT", os.path.realpath(ROOT))
    k = ablage.anlegen("Plan", "eins", "text")
    rel = f"data/ablage/{k['id']}/kopf.json"
    alle = abgleich_auswahl.auswahl(ROOT, abgleich_auswahl.ABGLEICH)
    assert rel in alle
    assert not any(r.startswith("data/ablage/") and "sichtbar-" in r for r in alle)
    assert abgleich_auswahl.pfad(ROOT, rel) == os.path.join(ablage.ordner(), k["id"],
                                                            "kopf.json")
    # Ein fremder Ordner (Test, --quelle) bleibt bei seinem eigenen data/ablage.
    assert abgleich_auswahl.pfad("/tmp/anders", rel) == "/tmp/anders/" + rel


# ── Umzug ──────────────────────────────────────────────────────────────

def test_umzug_trocken_zeigt_nur_und_wirklich_kopiert(tmp_path):
    alt = tmp_path / "alt"
    (alt / "20261007-liste-93ed").mkdir(parents=True)
    (alt / "20261007-liste-93ed" / "kopf.json").write_text(json.dumps(
        {"id": "20261007-liste-93ed", "titel": "Liste", "art": "markdown", "herkunft": "ki"}))
    (alt / "20261007-liste-93ed" / "v1-pc.md").write_text("- a")
    env = dict(os.environ)
    lauf = [sys.executable, os.path.join(ROOT, "scripts", "ablage_umzug.py"), "--alt", str(alt)]
    r = subprocess.run(lauf, capture_output=True, text=True, env=env)
    assert r.returncode == 0 and "Trocken" in r.stdout and "Liste.md" in r.stdout
    assert ablage.alle_ids() == []
    r = subprocess.run(lauf + ["--wirklich"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    assert ablage.alle_ids() == ["20261007-liste-93ed"]
    assert _sichtbar() == ["Liste.md"]
    assert (alt / "20261007-liste-93ed" / "v1-pc.md").exists()       # alt bleibt


# ── Papierkorb, ersetzen, wem es gehört (core/ablage.py) ───────────────

def test_wem_es_gehoert_im_zweifel_sasha():
    assert not ablage.von_sasha(ablage.anlegen("KI", "x", "text"))
    assert ablage.von_sasha(ablage.anlegen("a.txt", "x", "text", herkunft="anhang"))
    # Alte Köpfe ohne Feld: nur Herkunft ki gehört der KI.
    assert not ablage.von_sasha({"herkunft": "ki"})
    for h in ("anhang", "sandbox", "morgenblick", "ablauf", None):
        assert ablage.von_sasha({"herkunft": h})


def test_papierkorb_blendet_aus_und_ist_umkehrbar():
    k = ablage.anlegen("Weg", "x", "text")
    ablage.papierkorb(k["id"])
    assert ablage.liste() == [] and ablage.liste(archivierte=True) == []
    assert [d["id"] for d in ablage.liste(papierkorb=True)] == [k["id"]]
    assert ablage.lesen(k["id"])["inhalt"] == "x"
    ablage.papierkorb(k["id"], False)
    assert [d["id"] for d in ablage.liste()] == [k["id"]]
    assert "papierkorb" not in ablage.kopf(k["id"])


def test_ersetzen_legt_neu_an_und_das_alte_in_den_papierkorb():
    alt = ablage.anlegen("Tracking", "v1", "markdown", herkunft="anhang")
    neu, alt2 = ablage.ersetzen(alt["id"], "v2")
    assert neu["titel"] == "Tracking" and neu["ersetzt"] == alt["id"]
    assert neu["abgelegt_von"] == "ki"
    assert ablage.im_papierkorb(alt2) and alt2["ersetzt_durch"] == neu["id"]
    assert [d["id"] for d in ablage.liste()] == [neu["id"]]
    assert _sichtbar() == ["Tracking.md"]
    assert open(os.path.join(_w(), "Tracking.md")).read() == "v2"


def test_ersetzen_ganz_oder_gar_nicht(monkeypatch):
    alt = ablage.anlegen("Tracking", "v1", "markdown")
    vorher = ablage.kopf(alt["id"])
    import pytest
    with pytest.raises(ablage.Fehler):
        ablage.ersetzen(alt["id"], "")                       # Anlegen scheitert
    assert ablage.kopf(alt["id"]) == vorher and len(ablage.alle_ids()) == 1

    def kaputt(*a, **k):
        raise OSError("platte voll")
    monkeypatch.setattr(ablage, "papierkorb", kaputt)
    with pytest.raises(OSError):
        ablage.ersetzen(alt["id"], "v2")                     # Papierkorb scheitert
    assert ablage.alle_ids() == [alt["id"]] and not ablage.im_papierkorb(ablage.kopf(alt["id"]))


def test_route_papierkorb_und_filter():
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    k = ablage.anlegen("Weg", "x", "text")
    assert c.post(f"/api/ablage/{k['id']}/papierkorb", json={"an": True}).status_code == 200
    assert c.get("/api/ablage").get_json()["dokumente"] == []
    d = c.get("/api/ablage?papierkorb=1").get_json()
    assert [e["id"] for e in d["dokumente"]] == [k["id"]] and d["ordner"] == _w()
    assert c.post("/api/ablage/gibts-nicht-1234/papierkorb", json={}).status_code == 404
    c.post(f"/api/ablage/{k['id']}/papierkorb", json={"an": False})
    assert [e["id"] for e in c.get("/api/ablage").get_json()["dokumente"]] == [k["id"]]
    assert c.get(f"/api/ablage/{k['id']}").get_json()["pfad"] == os.path.join(_w(), "Weg.txt")
