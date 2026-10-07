"""Projekte (Phase 6 des Claude-Web-Plans, 2026-10-07): ein Rahmen für ein
Thema mit Anweisungen und Wissensdateien; Gespräche gehören optional dazu.

Geprüft wird Verhalten:
  - anlegen, Liste, finden, archivieren (nie löschen), Anweisungen mit .bak,
  - Wissen hinzufügen: Text, Datei, Sperrliste (Zugangsdaten, learning/),
    keine Binärdatei, kein Pfad-Ausbruch über den Namen,
  - Gespräch → Projekt: zuordnen, lösen, /neu bleibt im Projekt,
  - Prompt-Block nur bei einem Projekt-Gespräch, deterministisch, gekappt,
    nur auf gross,
  - read_project_file nur im Projekt des laufenden Gesprächs, kein Ausbruch,
  - search_chats mit Filter projekt.
(Routen: tests/test_projekte_routen.py; Wächter gegen das echte data/:
tests/test_keine_seiteneffekte.py)
"""
import os

import pytest

import chat_suche
import cloud
import gedaechtnis
import gespraeche
import ki_werkzeuge
import projekte
import state
import werkzeug_register
from profil import gross, klein


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)


# ── Speicher ───────────────────────────────────────────────────────────

def test_anlegen_legt_ordner_unter_dem_gedaechtnis_an():
    p = projekte.anlegen("Umzug Berlin", "Immer mit Kostenliste.")
    assert p["id"] == "umzug-berlin" and p["name"] == "Umzug Berlin"
    ordner = os.path.join(gedaechtnis._DIR, "projekte", "umzug-berlin")
    assert os.path.isfile(os.path.join(ordner, "projekt.json"))
    assert os.path.isdir(os.path.join(ordner, "wissen"))
    assert p["anweisungen"].strip() == "Immer mit Kostenliste."
    assert p["stand"] == projekte.stand(p["anweisungen"])


@pytest.mark.parametrize("name", ["", "   ", "neu", "Aus", "kein", "zuordnen", "!!!"])
def test_anlegen_lehnt_leere_und_reservierte_namen_ab(name):
    with pytest.raises(projekte.Ungueltig):
        projekte.anlegen(name)


def test_anlegen_zweimal_derselbe_name_geht_nicht():
    projekte.anlegen("Geige")
    with pytest.raises(projekte.Ungueltig):
        projekte.anlegen("geige")


def test_projekte_stehen_nicht_in_den_gedaechtnis_bereichen():
    """Sonst stünden sie als Titel in jedem Kopf und write_note erreichte sie."""
    projekte.anlegen("Geige", "Anweisung")
    assert "projekte" not in gedaechtnis.BEREICHE
    assert "geige" not in gedaechtnis.kopf_block()


def test_liste_finden_und_archivieren_ohne_loeschen():
    projekte.anlegen("Zebra")
    projekte.anlegen("Apfel")
    assert [p["name"] for p in projekte.liste()] == ["Apfel", "Zebra"]
    assert projekte.finden("apfel") == "apfel"
    assert projekte.finden("ZEBRA") == "zebra"
    assert projekte.finden("gibt es nicht") is None
    projekte.archivieren("zebra")
    assert [p["id"] for p in projekte.liste()] == ["apfel"]
    assert [p["id"] for p in projekte.liste(archivierte=True)] == ["zebra"]
    assert projekte.gibt_es("zebra")          # archiviert, nicht gelöscht
    assert projekte.finden("Zebra") == "zebra"
    projekte.archivieren("zebra", an=False)
    assert len(projekte.liste()) == 2


def test_unbekanntes_projekt_wirft():
    for f in (projekte.laden, projekte.anweisungen_lesen, projekte.archivieren):
        with pytest.raises(projekte.Unbekannt):
            f("nichts")
    assert not projekte.gibt_es("../skills")


def test_anweisungen_schreiben_atomar_mit_bak():
    projekte.anlegen("Geige", "alt")
    neu = projekte.anweisungen_schreiben("geige", "neu\r\nzweite Zeile")
    assert projekte.anweisungen_lesen("geige") == "neu\nzweite Zeile\n"
    assert neu == projekte.stand("neu\nzweite Zeile\n")
    bak = os.path.join(gedaechtnis._DIR, "projekte", "geige", "anweisungen.md.bak")
    assert open(bak, encoding="utf-8").read().strip() == "alt"
    with pytest.raises(projekte.Ungueltig):
        projekte.anweisungen_schreiben("geige", "x" * (projekte.MAX_ANWEISUNGEN + 1))


# ── Wissen ─────────────────────────────────────────────────────────────

def test_wissen_als_text_und_ersetzen_mit_bak():
    projekte.anlegen("Geige")
    w = projekte.wissen_hinzufuegen("geige", "Noten Liste.md", "Bach, Telemann")
    assert w["name"] == "noten-liste.md"
    projekte.wissen_hinzufuegen("geige", "noten liste.md", "Vivaldi")
    assert projekte.wissen_liste("geige") == [{"name": "noten-liste.md", "groesse": 7}]
    assert "Vivaldi" in projekte.wissen_lesen("geige", "noten-liste.md")


@pytest.mark.parametrize("name,erwartet", [
    ("../../ai_config.json", "ai-config.json"),
    ("/etc/passwd", "passwd.md"),
    ("bericht.pdf", "bericht-pdf.md"),
    ("README", "readme.md"),
])
def test_wissen_dateiname_bleibt_im_ordner(name, erwartet):
    projekte.anlegen("Geige")
    assert projekte.wissen_hinzufuegen("geige", name, "x")["name"] == erwartet
    ordner = os.path.join(gedaechtnis._DIR, "projekte", "geige", "wissen")
    assert os.path.isfile(os.path.join(ordner, erwartet))


def test_wissen_leer_oder_zu_lang_geht_nicht():
    projekte.anlegen("Geige")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_hinzufuegen("geige", "a.md", "   ")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_hinzufuegen("geige", "a.md", "x" * (projekte.MAX_WISSEN + 1))
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_hinzufuegen("geige", "", "text")


def test_wissen_aus_datei(tmp_path):
    projekte.anlegen("Geige")
    datei = tmp_path / "Übungsplan.txt"
    datei.write_text("Tonleitern jeden Tag", encoding="utf-8")
    w = projekte.wissen_aus_datei("geige", str(datei))
    assert w["name"] == "uebungsplan.txt"
    assert "Tonleitern" in projekte.wissen_lesen("geige", "uebungsplan")


@pytest.mark.parametrize("name", [".env", "ai_config.json", "id_rsa", "server.key",
                                  "mein_token.txt", "passwort.txt"])
def test_wissen_aus_datei_sperrt_zugangsdaten(tmp_path, name):
    projekte.anlegen("Geige")
    datei = tmp_path / name
    datei.write_text("GEHEIM=1", encoding="utf-8")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_aus_datei("geige", str(datei))
    assert projekte.wissen_liste("geige") == []


def test_wissen_aus_datei_sperrt_den_lernordner(tmp_path):
    """learning/ ist für die KI zu — auch über ein Projekt."""
    projekte.anlegen("Geige")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_aus_datei("geige", str(tmp_path / "learning" / "a.md"))
    # Auch mit schon gelesenem Text (TUI auf einem anderen Rechner): die
    # Sperre prüft den Pfad.
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_aus_datei("geige", "/x/.env", text="KEY=1")


def test_wissen_aus_datei_nur_text(tmp_path):
    projekte.anlegen("Geige")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_aus_datei("geige", str(pdf))
    binaer = tmp_path / "a.txt"
    binaer.write_bytes(b"ab\x00cd")
    with pytest.raises(projekte.Ungueltig):
        projekte.wissen_aus_datei("geige", str(binaer))
    with pytest.raises(FileNotFoundError):
        projekte.wissen_aus_datei("geige", str(tmp_path / "fehlt.md"))


def test_wissen_lesen_in_stuecken():
    projekte.anlegen("Geige")
    text = "a" * projekte.MAX_LESEN + "ENDE"
    projekte.wissen_hinzufuegen("geige", "lang.md", text)
    erst = projekte.wissen_lesen("geige", "lang.md")
    assert "ENDE" not in erst and f"ab={projekte.MAX_LESEN}" in erst
    assert "ENDE" in projekte.wissen_lesen("geige", "lang.md", ab=projekte.MAX_LESEN)


# ── Gespräch → Projekt ─────────────────────────────────────────────────

def test_gespraech_zuordnen_und_loesen():
    projekte.anlegen("Geige")
    gid = gespraeche.neu()
    gespraeche.anhaengen(gid, "user", "hallo")
    assert gespraeche.projekt_von(gid) is None
    gespraeche.projekt_setzen(gid, "geige")
    assert gespraeche.projekt_von(gid) == "geige"
    assert gespraeche.liste()[0]["projekt"] == "geige"
    assert [g["id"] for g in gespraeche.liste(projekt="geige")] == [gid]
    gespraeche.projekt_setzen(gid, None)
    assert gespraeche.projekt_von(gid) is None
    assert gespraeche.liste(projekt="geige") == []


def test_erinnerungen_gehoeren_zu_keinem_projekt():
    gid = gespraeche.erinnerungen()
    with pytest.raises(ValueError):
        gespraeche.projekt_setzen(gid, "geige")


def test_neues_gespraech_merkt_sich_das_projekt_bis_zum_senden():
    gespraeche.aktiv_setzen(None, projekt="geige")
    assert gespraeche.neu_projekt() == "geige"
    gid = gespraeche.neu(projekt=gespraeche.neu_projekt())
    gespraeche.aktiv_setzen(gid)
    assert gespraeche.projekt_von(gid) == "geige"
    assert gespraeche.neu_projekt() is None       # gilt nur bis zum Anlegen


# ── Prompt ─────────────────────────────────────────────────────────────

def _projekt_mit_wissen():
    projekte.anlegen("Geige", "Antworte mit Fingersätzen.")
    projekte.wissen_hinzufuegen("geige", "noten.md", "Bach Partita, Satz 3")
    return "geige"


def test_block_steht_nur_bei_einem_projekt_gespraech(monkeypatch):
    pid = _projekt_mit_wissen()
    monkeypatch.setattr(cloud, "_profil", lambda: gross)
    ohne = cloud._static_system(None, tutor_mode=False)
    mit = cloud._static_system(None, tutor_mode=False, projekt=pid)
    assert "Projekt: Geige" not in ohne
    assert "## Projekt: Geige" in mit
    assert "Antworte mit Fingersätzen." in mit
    assert "- noten.md (" in mit
    # Der INHALT der Wissensdatei steht nicht im Kopf.
    assert "Partita" not in mit
    # Hinter Gedächtnis-Kopf und Skills, vor dem Imprint: alles davor gleich.
    assert mit.startswith(ohne.split("\n\n## Heute")[0][:200])


def test_block_ist_deterministisch_und_aendert_sich_nur_mit_dem_projekt(monkeypatch):
    pid = _projekt_mit_wissen()
    monkeypatch.setattr(cloud, "_profil", lambda: gross)
    a = cloud._static_system(None, tutor_mode=False, projekt=pid)
    assert a == cloud._static_system(None, tutor_mode=False, projekt=pid)
    projekte.wissen_hinzufuegen(pid, "zweites.md", "x")
    assert cloud._static_system(None, tutor_mode=False, projekt=pid) != a


def test_block_kappt_lange_anweisungen():
    projekte.anlegen("Geige", "A" * (projekte.MAX_PROMPT_ANWEISUNGEN + 500))
    block = projekte.prompt_block("geige")
    assert block.count("A") <= projekte.MAX_PROMPT_ANWEISUNGEN + 5
    assert "read_project_file(\"anweisungen\")" in block
    # … und die KI kann sie ganz lesen.
    assert projekte.wissen_lesen("geige", "anweisungen").count("A") > projekte.MAX_PROMPT_ANWEISUNGEN


def test_unbekanntes_projekt_gibt_keinen_block(monkeypatch):
    monkeypatch.setattr(cloud, "_profil", lambda: gross)
    assert projekte.prompt_block("gibts-nicht") == ""
    assert cloud._static_system(None, False, projekt="gibts-nicht") == \
        cloud._static_system(None, False)


def test_klein_bekommt_keinen_projekt_block(monkeypatch):
    pid = _projekt_mit_wissen()
    monkeypatch.setattr(cloud, "_profil", lambda: klein)
    assert "Projekt: Geige" not in cloud._static_system(None, False, projekt=pid)
    assert "read_project_file" not in {t["function"]["name"] for t in klein.TOOLS}


def test_cloud_weg_gibt_das_projekt_an_den_kopf_und_den_ausfuehrer(monkeypatch):
    """kern.chat → cloud.chat_stream(projekt=) → fester Kopf + Ausführer."""
    import kern
    import ai_backends
    gesehen = {}

    class Modul:
        @staticmethod
        def chat_stream(h, **k):
            gesehen.update(k)
            return iter(["ok"])
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    list(kern.chat([], backend=ai_backends.CLOUD, projekt="geige"))
    assert gesehen.get("projekt") == "geige"
    gesehen.clear()
    list(kern.chat([], backend=ai_backends.CLOUD))
    assert "projekt" not in gesehen


# ── read_project_file ──────────────────────────────────────────────────

def test_read_project_file_liest_im_aktiven_projekt():
    pid = _projekt_mit_wissen()
    exe = ki_werkzeuge.mit_projekt(pid)
    assert "Partita" in exe("read_project_file", {"name": "noten.md"})
    assert "Partita" in exe("read_project_file", {"name": "noten"})


def test_read_project_file_ohne_projekt_liest_nichts():
    _projekt_mit_wissen()
    text = ki_werkzeuge.ausfuehren("read_project_file", {"name": "noten.md"})
    assert "keinem Projekt" in text and "Partita" not in text
    # Das Modell kann das Projekt nicht per Argument setzen.
    text = ki_werkzeuge.ausfuehren("read_project_file",
                                   {"name": "noten.md", "projekt": "geige"})
    assert "Partita" not in text


def test_read_project_file_kommt_nicht_in_ein_anderes_projekt():
    _projekt_mit_wissen()
    projekte.anlegen("Umzug")
    exe = ki_werkzeuge.mit_projekt("umzug")
    for name in ("noten.md", "../geige/wissen/noten.md", "../../geige/wissen/noten.md",
                 "/etc/passwd", "../anweisungen.md"):
        text = exe("read_project_file", {"name": name})
        assert "Partita" not in text and "root:" not in text, name
        assert "Keine Wissensdatei" in text, name


def test_read_project_file_ist_frei_und_nur_auf_gross():
    assert not werkzeug_register.braucht_erlaubnis("read_project_file", {"name": "x"})
    assert "read_project_file" in {t["function"]["name"] for t in gross.TOOLS}


# ── search_chats im Projekt ────────────────────────────────────────────

def test_search_chats_filtert_nach_projekt():
    projekte.anlegen("Geige")
    a = gespraeche.neu(projekt="geige")
    gespraeche.anhaengen(a, "user", "die Partita übe ich")
    b = gespraeche.neu()
    gespraeche.anhaengen(b, "user", "die Partita im Radio")
    alle = chat_suche.suchen("partita")
    assert {t["id"] for t in alle} == {a, b}
    nur = ki_werkzeuge.ausfuehren("search_chats", {"query": "partita", "projekt": "Geige"})
    assert a in nur and b not in nur
    falsch = ki_werkzeuge.ausfuehren("search_chats", {"query": "partita", "projekt": "Zebra"})
    assert "Kein Projekt" in falsch and "Geige" in falsch
