"""Ablage und Anhänge (core/ablage.py, core/anhang.py, core/zug.py,
ui/routen/ablage.py) — Claude-Web-Plan Phase 5, 2026-10-07.

Verhalten, das zählt: die Ablage schreibt nur in ihren Ordner, jede Änderung
ist eine neue Fassung, nichts wird gelöscht; Werkzeuge melden ein Dokument
als Event an die TUI; aus der Sandbox kommt nur, was im Lauf-Ordner liegt;
Anhänge gehen als Text bzw. Bild an die Cloud, im Gespräch steht nur ein
Verweis; gesperrte Pfade gehen nie raus."""
import base64
import json
import os

import pytest

import ablage
import ai_backends
import anhang
import cloud
import cloud_openai
import context
import dateien
import gedaechtnis
import gespraeche
import kern
import ki_werkzeuge
import sandbox
import state
import werkzeug_register
import werkzeug_schleife
import zug

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Ein echtes PNG (1×1), damit die Art-Erkennung nichts durchwinkt.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    import consolidation
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)


def _alle_dateien(wurzel):
    raus = set()
    for w, _o, ds in os.walk(wurzel):
        for d in ds:
            raus.add(os.path.relpath(os.path.join(w, d), wurzel))
    return raus


# ── Speicher ───────────────────────────────────────────────────────────

def test_anlegen_schreibt_nur_in_den_ablage_ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_ABLAGE_DIR", str(tmp_path / "ablage"))
    k = ablage.anlegen("Einkaufsliste für Samstag", "- Milch\n- Brot", "markdown",
                       gespraech="g1")
    assert k["titel"] == "Einkaufsliste für Samstag" and k["art"] == "markdown"
    assert k["herkunft"] == "ki" and k["gespraech"] == "g1" and k["fassung"] == 1
    assert k["id"].endswith(k["id"][-4:]) and "einkaufsliste-fuer-samstag" in k["id"]
    # Alles liegt unter dem Ordner, sonst nirgends: kopf + eine Fassung.
    assert _alle_dateien(tmp_path) == {
        f"ablage/{k['id']}/kopf.json", f"ablage/{k['id']}/v1-{dateien.knoten()}.md"}
    assert ablage.lesen(k["id"])["inhalt"] == "- Milch\n- Brot"


def test_neue_fassung_ist_eine_neue_datei_die_alte_bleibt():
    k = ablage.anlegen("Plan", "eins", "text")
    k2 = ablage.neue_fassung(k["id"], "zwei")
    assert k2["fassung"] == 2
    assert ablage.lesen(k["id"], 1)["inhalt"] == "eins"
    assert ablage.lesen(k["id"])["inhalt"] == "zwei"
    namen = sorted(os.listdir(os.path.join(ablage.ordner(), k["id"])))
    assert namen == ["kopf.json", f"v1-{dateien.knoten()}.txt", f"v2-{dateien.knoten()}.txt"]


def test_zwei_rechner_mit_derselben_fassungsnummer_verlieren_nichts(monkeypatch):
    k = ablage.anlegen("Plan", "eins", "markdown")
    # Der Laptop hat gleichzeitig auch eine „zweite" angelegt; der Sync brachte sie.
    pfad = os.path.join(ablage.ordner(), k["id"], "v2-laptop.md")
    dateien.atomar_schreiben(pfad, "vom laptop")
    os.utime(pfad, (1, 1))                       # älter
    ablage.neue_fassung(k["id"], "vom pc")
    assert ablage.kopf(k["id"])["fassung"] == 3
    assert ablage.lesen(k["id"], 2)["inhalt"] == "vom laptop"
    assert ablage.lesen(k["id"], 3)["inhalt"] == "vom pc"


def test_archivieren_loescht_nichts_und_ist_umkehrbar():
    k = ablage.anlegen("Alt", "x", "text")
    vorher = _alle_dateien(ablage.ordner())
    ablage.archivieren(k["id"])
    assert [d["id"] for d in ablage.liste()] == []
    assert [d["id"] for d in ablage.liste(archivierte=True)] == [k["id"]]
    assert _alle_dateien(ablage.ordner()) == vorher
    ablage.archivieren(k["id"], False)
    assert [d["id"] for d in ablage.liste()] == [k["id"]]
    assert not any(n for n in dir(ablage) if "loesch" in n.lower())


def test_liste_neueste_zuerst():
    a = ablage.anlegen("A", "a", "text")
    b = ablage.anlegen("B", "b", "text")
    p = ablage.pfad(a["id"])
    os.utime(p, (1, 1))
    assert [d["id"] for d in ablage.liste()] == [b["id"], a["id"]]


@pytest.mark.parametrize("inhalt", ["", "   ", "x" * (ablage.TEXT_MAX_ZEICHEN + 1)])
def test_leer_oder_zu_lang_wird_abgelehnt(inhalt):
    with pytest.raises(ablage.Fehler):
        ablage.anlegen("T", inhalt, "text")
    assert ablage.liste() == []


@pytest.mark.parametrize("boese", ["../x", "/etc", "..", "a/b", "", None, "A" * 3])
def test_ungueltige_ids_fuehren_nirgendwohin(boese):
    with pytest.raises(ablage.Unbekannt):
        ablage.lesen(boese)
    assert not ablage.gibt_es(boese)


def test_code_bekommt_endung_nach_sprache():
    k = ablage.anlegen("Skript", "print(1)", "code", sprache="python")
    assert ablage.pfad(k["id"]).endswith(".py") and k["sprache"] == "python"


def test_bild_nur_mit_bildendung_und_groessengrenze():
    k = ablage.anlegen("Foto", PNG, "bild", endung=".png", herkunft="anhang")
    assert ablage.bild_bytes(k["id"]) == ("image/png", PNG)
    with pytest.raises(ablage.Fehler):
        ablage.anlegen("x", PNG, "bild", endung=".exe")
    with pytest.raises(ablage.Fehler):
        ablage.anlegen("x", b"0" * (ablage.BILD_MAX_BYTES + 1), "bild", endung=".png")
    with pytest.raises(ablage.Fehler):
        ablage.neue_fassung(k["id"], "text")


# ── Werkzeuge ──────────────────────────────────────────────────────────

def test_werkzeuge_nur_auf_der_grossen_schiene_und_ungegatet():
    for name in ("create_document", "read_document", "update_document", "save_from_sandbox"):
        w = werkzeug_register.eintrag(name)
        assert w.klein is None and w.gross and w.ausfuehrer is not None
    for name in ("create_document", "read_document", "update_document"):
        assert not werkzeug_register.braucht_erlaubnis(name, {"titel": "x", "inhalt": "y"})


def test_save_from_sandbox_ist_gegatet_und_nur_auf_wunsch():
    """Sasha 2026-10-07: behalten „nur auf initiative von mir" — gefragt,
    ohne „immer", und die Beschreibung sagt es dem Modell."""
    assert werkzeug_register.braucht_erlaubnis("save_from_sandbox", {"lauf": "x", "datei": "a"})
    assert not werkzeug_register.immer_erlaubbar("save_from_sandbox")
    assert "NUR wenn Sasha" in werkzeug_register.eintrag("save_from_sandbox").gross
    frage = werkzeug_register.frage("save_from_sandbox", {"lauf": "x", "datei": "plot.png",
                                                          "titel": "Kurve"})
    assert "plot.png" in frage and "Kurve" in frage and "Ablage" in frage


def test_create_document_meldet_ein_ablage_ereignis():
    marke = zug.beginnen("g1")
    try:
        text = ki_werkzeuge._verteilen(
            "create_document", {"titel": "Wochenplan", "inhalt": "# Mo\n- Geige", "art": "markdown"})
        ereignisse = zug.abholen()
    finally:
        zug.beenden(marke)
    k = ablage.liste()[0]
    assert k["titel"] == "Wochenplan" and k["gespraech"] == "g1" and k["herkunft"] == "ki"
    assert k["id"] in text and "Fassung 1" in text
    assert ereignisse == [{"ablage": {"id": k["id"], "titel": "Wochenplan",
                                      "art": "markdown", "fassung": 1}}]
    assert zug.abholen() == []                      # außerhalb des Zugs: nichts


def test_read_und_update_document():
    k = ablage.anlegen("Plan", "alt", "markdown")
    assert "alt" in ki_werkzeuge._verteilen("read_document", {"id": k["id"]})
    marke = zug.beginnen(None)
    try:
        text = ki_werkzeuge._verteilen("update_document", {"id": k["id"], "inhalt": "neu"})
        ev = zug.abholen()
    finally:
        zug.beenden(marke)
    assert "Fassung 2" in text and ev[0]["ablage"]["fassung"] == 2
    assert ablage.lesen(k["id"])["inhalt"] == "neu" and ablage.lesen(k["id"], 1)["inhalt"] == "alt"
    assert "Kein Dokument" in ki_werkzeuge._verteilen("update_document", {"id": "x-1", "inhalt": "y"})
    assert "Kein Dokument" in ki_werkzeuge._verteilen("read_document", {"id": "../../etc"})


def test_create_document_fehler_sind_text_kein_absturz():
    assert "Nicht abgelegt" in ki_werkzeuge._verteilen(
        "create_document", {"titel": "x", "inhalt": "x" * (ablage.TEXT_MAX_ZEICHEN + 1)})
    assert ablage.liste() == []


# ── Ende zu Ende: Werkzeug in der Schleife → SSE 'ablage' → Gespräch ──

class _Skript:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)

    def runde(self):
        return self.runden.pop(0)
        yield

    def assistent_anhaengen(self, r):
        pass

    def ergebnisse_anhaengen(self, e):
        pass


@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    return app.test_client()


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


def _modul(monkeypatch, gen):
    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)


def test_dokument_im_zug_kommt_als_event_und_bleibt_im_gespraech(client, monkeypatch):
    gesehen = []

    def gen(history, **k):
        gesehen.append(history)
        adapter = _Skript([
            werkzeug_schleife.Runde("", [("c1", "create_document",
                                          {"titel": "Packliste", "inhalt": "- Zelt"})]),
            werkzeug_schleife.Runde("Liegt in der Ablage.")])
        yield from werkzeug_schleife.laufen(adapter, tutor_mode=False,
                                            active_exec=ki_werkzeuge.ausfuehren,
                                            user_query="x")
    _modul(monkeypatch, gen)
    ev = _events(client.post("/api/chat", json={"message": "mach eine packliste"}))
    gid = gespraeche.aktiv()
    doc = ablage.liste()[0]
    assert doc["gespraech"] == gid
    i_fertig = next(i for i, e in enumerate(ev) if e.get("werkzeug", {}).get("phase") == "fertig")
    assert ev[i_fertig + 1] == {"ablage": {"id": doc["id"], "titel": "Packliste",
                                           "art": "markdown", "fassung": 1}}
    antwort = gespraeche.nachrichten(gid)[-1]
    assert antwort["dokumente"] == [ev[i_fertig + 1]["ablage"]]
    # Die Anzeige bekommt es mit, die KI im nächsten Zug auch (mit id).
    h = client.get("/api/chat/history").get_json()
    assert h[-1]["dokumente"][0]["id"] == doc["id"]
    _events(client.post("/api/chat", json={"message": "danke"}))
    assert f'(id {doc["id"]})' in gesehen[-1][1]["content"]
    # Nach dem Zug ist kein Zug mehr offen.
    assert zug.gespraech() is None


# ── Sandbox → Ablage ───────────────────────────────────────────────────

@pytest.fixture
def lauf(tmp_path, monkeypatch):
    """Ein Lauf-Ordner des Gesprächs g1, wie run_code ihn hinterlässt."""
    basis = tmp_path / "sandbox"
    monkeypatch.setenv("ZENTRALE_SANDBOX_DIR", str(basis))
    kennung = sandbox.lauf_kennung("g1")
    ordner = basis / kennung
    (ordner / "unter").mkdir(parents=True)
    (ordner / "ergebnis.csv").write_text("a,b\n1,2\n")
    (ordner / "unter" / "plot.png").write_bytes(PNG)
    (ordner / "roh.bin").write_bytes(b"\x00\x01\x02")
    geheim = tmp_path / "geheim.txt"
    geheim.write_text("SCHLUESSEL")
    os.symlink(geheim, ordner / "verweis.txt")
    os.symlink(tmp_path, ordner / "ordnerverweis")
    return kennung


def _speichern(args, gid="g1"):
    marke = zug.beginnen(gid)
    try:
        return ki_werkzeuge._verteilen("save_from_sandbox", args), zug.abholen()
    finally:
        zug.beenden(marke)


def test_sandbox_datei_kommt_in_die_ablage(lauf):
    text, ev = _speichern({"lauf": lauf, "datei": "ergebnis.csv", "titel": "Zahlen"})
    k = ablage.liste()[0]
    assert "Abgelegt" in text and k["titel"] == "Zahlen" and k["art"] == "csv"
    assert k["herkunft"] == "sandbox" and k["gespraech"] == "g1"
    assert ablage.lesen(k["id"])["inhalt"] == "a,b\n1,2\n" and ev[0]["ablage"]["id"] == k["id"]
    text, _ = _speichern({"lauf": lauf, "datei": "unter/plot.png"})
    assert ablage.liste()[0]["art"] == "bild"


@pytest.mark.parametrize("datei", ["verweis.txt", "ordnerverweis/geheim.txt", "../geheim.txt",
                                   "/etc/passwd", "../../" + "x", "", "gibtsnicht.txt",
                                   "roh.bin", "unter"])
def test_sandbox_ausbruch_wird_verhindert(lauf, datei):
    text, ev = _speichern({"lauf": lauf, "datei": datei})
    assert text.startswith("[Nicht abgelegt") and ev == []
    assert ablage.liste() == []


@pytest.mark.parametrize("fremd", ["../x", "/tmp", "g2--20261007-000000-abc", "", ".probe"])
def test_nur_laeufe_dieses_gespraechs(lauf, fremd):
    text, _ = _speichern({"lauf": fremd, "datei": "ergebnis.csv"})
    assert text.startswith("[Nicht abgelegt") and ablage.liste() == []


def test_sandbox_groessengrenze(lauf, monkeypatch):
    monkeypatch.setattr(ki_werkzeuge, "_SANDBOX_MAX_BYTES", 4)
    text, _ = _speichern({"lauf": lauf, "datei": "ergebnis.csv"})
    assert "zu groß" in text and ablage.liste() == []


def test_run_code_benennt_den_lauf_nach_dem_gespraech(monkeypatch):
    gesehen = {}

    def falsch(code, sprache, zeitlimit_s, lauf_id=None, abbruch=None):
        gesehen["lauf"] = lauf_id
        return sandbox._ergebnis(rc=0, dateien_neu=[{"name": "a.txt", "bytes": 1}])
    monkeypatch.setattr(sandbox, "ausfuehren", falsch)
    marke = zug.beginnen("20261007-120000-abcdef")
    try:
        text = ki_werkzeuge._verteilen("run_code", {"code": "x"})
    finally:
        zug.beenden(marke)
    assert gesehen["lauf"].startswith("20261007-120000-abcdef--")
    assert "Lauf: " + gesehen["lauf"] in text and "save_from_sandbox" in text
    # Ohne Gespräch (Skript, Erinnerung): ein frischer Lauf wie bisher.
    ki_werkzeuge._verteilen("run_code", {"code": "x"})
    assert "--" not in gesehen["lauf"]


@pytest.mark.skipif(not sandbox.verfuegbar(), reason="bubblewrap fehlt")
def test_echter_lauf_und_dann_in_die_ablage():
    marke = zug.beginnen("g7")
    try:
        text = ki_werkzeuge._verteilen(
            "run_code", {"code": "open('/arbeit/hallo.md','w').write('# Hallo')"})
        kennung = text.split("Lauf: ", 1)[1].split(" ", 1)[0]
        ergebnis = ki_werkzeuge._verteilen(
            "save_from_sandbox", {"lauf": kennung, "datei": "hallo.md"})
    finally:
        zug.beenden(marke)
    assert "Abgelegt" in ergebnis
    assert ablage.lesen(ablage.liste()[0]["id"])["inhalt"] == "# Hallo"


# ── Anhänge: Sperrliste ────────────────────────────────────────────────

@pytest.mark.parametrize("pfad", [
    os.path.join(ROOT, "data", "ai_config.json"),
    os.path.join(ROOT, "data", "lists.json"),
    os.path.join(ROOT, "data", "gedaechtnis", "steckbrief.md"),
    os.path.join(ROOT, "tutor", "data", "x.json"),
    "~/.ssh/id_ed25519", "~/.ssh/config", "~/.gnupg/pubring.kbx",
    "~/.local/share/zentrale/daten-sicherung/data/lists.json",
    "~/.claude/.credentials.json", "~/projekt/.env", "~/projekt/server.key",
    "~/codicus/learning/notiz.txt", "~/projekt/.git/config",
    "/proc/self/environ", "/etc/shadow",
])
def test_gesperrte_pfade(pfad):
    assert context.anhang_gesperrt(pfad), pfad
    with pytest.raises(anhang.Abgelehnt):
        anhang.annehmen(pfad, b"geheim")
    assert ablage.liste() == []


def test_verweis_auf_gesperrte_datei_wird_aufgeloest(tmp_path):
    ziel = tmp_path / ".ssh"
    ziel.mkdir()
    (ziel / "id_rsa").write_text("x")
    link = tmp_path / "harmlos.txt"
    os.symlink(ziel / "id_rsa", link)
    assert context.anhang_gesperrt(str(link))


@pytest.mark.parametrize("pfad", ["~/Downloads/rezept.txt", "/tmp/notiz.md",
                                  "~/codicus/ZENTRALE/core/ablage.py"])
def test_erlaubte_pfade(pfad):
    assert context.anhang_gesperrt(pfad) == ""


# ── Anhänge: Text, PDF, Bild ───────────────────────────────────────────

def test_text_anhang_als_verweis_und_im_verlauf_der_ki():
    r = anhang.annehmen("/tmp/rezept.md", "# Pfannkuchen\n2 Eier".encode())
    assert r["art"] == "markdown" and not r["gekappt"]
    k = ablage.kopf(r["id"])
    assert k["herkunft"] == "anhang" and k["titel"] == "rezept.md"
    verw = anhang.verweise([r["id"]])
    assert verw == [{"id": r["id"], "titel": "rezept.md", "art": "markdown", "fassung": 1}]
    v = [{"role": "user", "content": "was koche ich?", "anhaenge": verw}]
    wolke = anhang.verlauf_einsetzen(v, cloud=True)
    assert wolke[0]["content"] == "was koche ich?"
    assert wolke[0]["anhaenge"] == [{"art": "text", "titel": "rezept.md",
                                    "text": "# Pfannkuchen\n2 Eier"}]
    lokal = anhang.verlauf_einsetzen(v, cloud=False)
    assert "anhaenge" not in lokal[0] and "2 Eier" in lokal[0]["content"]


def test_langer_anhang_wird_mit_hinweis_gekappt():
    r = anhang.annehmen("/tmp/lang.txt", ("x" * (anhang.TEXT_MAX_CLOUD + 50)).encode())
    assert r["gekappt"] and r["hinweis"]
    t = anhang.verlauf_einsetzen([{"role": "user", "content": "?",
                                   "anhaenge": anhang.verweise([r["id"]])}], True)
    text = t[0]["anhaenge"][0]["text"]
    assert text.startswith("x" * anhang.TEXT_MAX_CLOUD) and "gekürzt" in text
    lokal = anhang.verlauf_einsetzen([{"role": "user", "content": "?",
                                       "anhaenge": anhang.verweise([r["id"]])}], False)
    assert len(lokal[0]["content"]) < anhang.TEXT_MAX_LOKAL + 300


def test_pdf_geht_ueber_den_weg_von_fetch_document(monkeypatch):
    gesehen = []
    monkeypatch.setattr(gedaechtnis, "pdf_text", lambda d: (gesehen.append(d), ("Seite 1", ""))[1])
    r = anhang.annehmen("/tmp/vertrag.pdf", b"%PDF-1.4 ...")
    assert gesehen == [b"%PDF-1.4 ..."] and r["art"] == "text"
    assert ablage.lesen(r["id"])["inhalt"] == "Seite 1"
    monkeypatch.setattr(gedaechtnis, "pdf_text", lambda d: ("", "Nichts Lesbares drin"))
    with pytest.raises(anhang.Abgelehnt, match="Nichts Lesbares"):
        anhang.annehmen("/tmp/scan.pdf", b"%PDF-1.4 ...")


def _mini_pdf(text):
    """Ein kleinstes gültiges PDF mit einer Zeile Text."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, x)


@pytest.mark.skipif(not __import__("shutil").which("pdftotext"), reason="poppler fehlt")
def test_echtes_pdf_wird_text():
    r = anhang.annehmen("/tmp/mietvertrag.pdf", _mini_pdf("Mietvertrag Seite eins"))
    assert "Mietvertrag Seite eins" in ablage.lesen(r["id"])["inhalt"]


def test_binaeres_und_falsche_bilder_werden_abgelehnt():
    with pytest.raises(anhang.Abgelehnt):
        anhang.annehmen("/tmp/programm", b"\x7fELF\x00\x00\x00")
    with pytest.raises(anhang.Abgelehnt):
        anhang.annehmen("/tmp/foto.png", b"kein bild")
    with pytest.raises(anhang.Abgelehnt):
        anhang.annehmen("/tmp/leer.txt", b"")
    with pytest.raises(anhang.Abgelehnt):
        anhang.annehmen("/tmp/riesig.txt", b"x" * (anhang.DATEI_MAX_BYTES + 1))


def test_bild_landet_richtig_bei_anthropic_und_openai():
    r = anhang.annehmen("/tmp/skizze.png", PNG)
    assert r["art"] == "bild"
    v = anhang.verlauf_einsetzen([{"role": "user", "content": "was siehst du?",
                                   "anhaenge": anhang.verweise([r["id"]])}], cloud=True)
    b64 = base64.b64encode(PNG).decode()
    anth = cloud._prepare_messages(v)
    bloecke = anth[0]["content"]
    assert {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": b64}} in bloecke
    assert bloecke[-1] == {"type": "text", "text": "was siehst du?"}
    oa = cloud_openai._prepare_messages(v, "SYSTEM", "JETZT")
    teile = oa[-1]["content"]
    assert {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}} in teile
    assert teile[0] == {"type": "text", "text": "was siehst du?"}
    assert teile[-1] == {"type": "text", "text": "JETZT"}       # Wechselndes hinten
    # Ohne Anhang bleibt alles wie vorher (Strings bei OpenAI).
    assert cloud_openai._prepare_messages([{"role": "user", "content": "hi"}], "S", "V")[-1] == \
        {"role": "user", "content": "hi\n\nV"}


def test_lokal_sieht_kein_bild_sondern_einen_hinweis():
    r = anhang.annehmen("/tmp/skizze.png", PNG)
    v = anhang.verlauf_einsetzen([{"role": "user", "content": "?",
                                   "anhaenge": anhang.verweise([r["id"]])}], cloud=False)
    assert "nur die Cloud" in v[0]["content"] and "anhaenge" not in v[0]


def test_fehlende_datei_auf_diesem_rechner():
    v = anhang.verlauf_einsetzen([{"role": "user", "content": "?", "anhaenge": [
        {"id": "20261007-weg-0000", "titel": "weg.txt", "art": "text", "fassung": 1}]}], True)
    assert "nicht vor" in v[0]["anhaenge"][0]["text"]


# ── Anhänge über die Routen ────────────────────────────────────────────

def _anhaengen(client, pfad, daten):
    return client.post("/api/anhang", json={"pfad": pfad,
                                            "daten": base64.b64encode(daten).decode()})


def test_anhang_route_und_chat_bild_nie_als_base64_im_gespraech(client, monkeypatch):
    gesehen = []

    def gen(history, **k):
        gesehen.append(history)
        yield "Ein Punkt."
    _modul(monkeypatch, gen)
    r = _anhaengen(client, "/tmp/skizze.png", PNG).get_json()
    assert r["art"] == "bild" and r["titel"] == "skizze.png"
    _events(client.post("/api/chat", json={"message": "was ist das?", "anhaenge": [r["id"]]}))
    frage = gespraeche.nachrichten(gespraeche.aktiv())[0]
    assert frage["anhaenge"] == [{"id": r["id"], "titel": "skizze.png", "art": "bild",
                                  "fassung": 1}]
    b64 = base64.b64encode(PNG).decode()
    assert gesehen[0][-1]["anhaenge"][0]["daten"] == b64
    # Auf der Platte steht nur der Verweis, nie das Bild.
    ordner = os.path.join(gespraeche._DIR, gespraeche.aktiv())
    for name in os.listdir(ordner):
        with open(os.path.join(ordner, name), encoding="utf-8") as f:
            assert b64 not in f.read()
    # Die Anzeige bekommt den Verweis.
    assert client.get("/api/chat/history").get_json()[0]["anhaenge"][0]["id"] == r["id"]


def test_bild_mit_lokaler_ki_klare_meldung(client, monkeypatch):
    r = _anhaengen(client, "/tmp/skizze.png", PNG).get_json()
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.LOCAL)
    a = client.post("/api/chat", json={"message": "?", "anhaenge": [r["id"]]})
    assert a.status_code == 400 and "nur mit der Cloud" in a.get_json()["error"]
    assert gespraeche.aktiv() is None or not gespraeche.nachrichten(gespraeche.aktiv())
    # Beim Annehmen schon ein Hinweis.
    r2 = _anhaengen(client, "/tmp/zwei.png", PNG).get_json()
    assert "Cloud" in r2["hinweis"]


def test_anhang_route_lehnt_ab(client):
    a = _anhaengen(client, os.path.join(ROOT, "data", "lists.json"), b"{}")
    assert a.status_code == 400 and "data/" in a.get_json()["error"]
    a = client.post("/api/anhang", json={"pfad": "/tmp/x.txt", "daten": "%%%kaputt"})
    assert a.status_code == 400
    a = client.post("/api/chat", json={"message": "?", "anhaenge": ["20261007-gibtsnicht-0000"]})
    assert a.status_code == 400
    assert ablage.liste() == []


def test_wiederholen_und_bearbeiten_behalten_die_anhaenge(client, monkeypatch):
    gesehen = []

    def gen(history, **k):
        gesehen.append(history)
        yield "ok"
    _modul(monkeypatch, gen)
    r = _anhaengen(client, "/tmp/brief.txt", b"Sehr geehrte").get_json()
    _events(client.post("/api/chat", json={"message": "kuerzen", "anhaenge": [r["id"]]}))
    _events(client.post("/api/chat/wiederholen", json={}))
    assert gesehen[-1][-1]["anhaenge"][0]["text"] == "Sehr geehrte"
    frage = gespraeche.letzte_nutzer_nachricht(gespraeche.aktiv())
    _events(client.post("/api/chat", json={"message": "noch kuerzer", "ersetzt": frage["id"]}))
    assert gesehen[-1][-1]["anhaenge"][0]["text"] == "Sehr geehrte"
    assert len(gesehen[-1]) == 1


def test_ablage_routen_liste_lesen_archiv(client):
    k = ablage.anlegen("Plan", "# A", "markdown", gespraech=None)
    ablage.neue_fassung(k["id"], "# B")
    liste = client.get("/api/ablage").get_json()["dokumente"]
    assert [d["id"] for d in liste] == [k["id"]] and liste[0]["fassung"] == 2
    d = client.get(f"/api/ablage/{k['id']}?fassung=1").get_json()
    assert d["inhalt"] == "# A" and d["fassung"] == 1 and d["pfad"].endswith(".md")
    assert client.get("/api/ablage/gibts-nicht").status_code == 404
    assert client.get(f"/api/ablage/{k['id']}?fassung=9").status_code == 404
    client.post(f"/api/ablage/{k['id']}/archiv", json={"an": True})
    assert client.get("/api/ablage").get_json()["dokumente"] == []
    assert client.get("/api/ablage?archiv=1").get_json()["dokumente"][0]["id"] == k["id"]


def test_zug_ist_pro_kontext_und_raeumt_auf():
    assert zug.gespraech() is None and zug.abholen() == []
    zug.melden({"x": 1})                             # ohne Zug: ins Leere
    m = zug.beginnen("a")
    zug.melden({"x": 2})
    assert zug.gespraech() == "a" and zug.abholen() == [{"x": 2}] and zug.abholen() == []
    zug.beenden(m)
    assert zug.gespraech() is None
