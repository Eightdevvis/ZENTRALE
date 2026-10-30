"""Abgleich über die Cloud: HttpMitte (core/abgleich_mitte.py) gegen eine
gespielte Cloud (devkit/fake_cloud.py), und ein ganzer Abgleich mit zwei
gespielten Geräten, Schlüssel = konto_schluessel aus konto.json.
Dazu die Wahl je App und Gerät (core/abgleich_apps.py)."""
import json

import pytest

import abgleich
import abgleich_apps
import abgleich_auswahl as auswahl
import abgleich_mitte
import abgleich_schluessel as schluessel
import ai_config
import cloud_api
import dateien
import konto
import konto_schluessel as ks
from devkit.fake_cloud import FalscheCloud

PW = "ein-langes-passwort"
LISTE = [{"id": "einkauf", "name": "Einkauf", "next_item": 2,
          "items": [{"id": 1, "text": "Milch", "done": False}]}]


@pytest.fixture
def cloud(monkeypatch):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    yield c
    c.stopp()


def _mitte(cloud, token=None):
    return abgleich_mitte.HttpMitte(cloud_api.Client(cloud.adresse, token=token))


def _token(cloud):
    konto.anlegen(konto.Entwurf(PW), "sasha", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    return konto.lesen()["token"]


# ── Die vier Handgriffe ────────────────────────────────────────────────

def test_leere_mitte_dann_senden_dann_holen(cloud):
    m = _mitte(cloud, _token(cloud))
    stand, lesen, namen = m.holen()
    assert (stand, namen, lesen("inhalt.enc")) == (None, [], None)
    k = m.vorbereiten({"inhalt.enc": b"I", "d/a.enc": b"A"}, [], "x")
    assert k.startswith(abgleich_mitte.VORLAEUFIG)
    assert m.senden(k) is True
    echt = m.echte_kennung(k)
    assert echt == "s0001"
    stand, lesen, namen = m.holen()
    assert stand == echt and sorted(namen) == ["d/a.enc", "inhalt.enc"]
    assert lesen("d/a.enc") == b"A" and lesen("d/fehlt.enc") is None
    assert m.enthaelt(echt) and m.enthaelt(k)


def test_jemand_war_schneller_409_ergibt_false(cloud):
    token = _token(cloud)
    a, b = _mitte(cloud, token), _mitte(cloud, token)
    a.holen()
    b.holen()
    assert a.senden(a.vorbereiten({"inhalt.enc": b"A"}, [], "")) is True
    kb = b.vorbereiten({"inhalt.enc": b"B"}, [], "")
    assert b.senden(kb) is False
    assert not b.enthaelt(kb)
    b.holen()
    assert b.senden(b.vorbereiten({"inhalt.enc": b"B"}, [], "")) is True


def test_vorlaeufige_kennung_nach_absturz_noch_erkennbar(cloud):
    """Absturz nach dem Senden: ein neuer Lauf kennt nur die vorläufige
    Kennung aus dem Vorhaben — und erkennt sie am inhalt.enc wieder."""
    token = _token(cloud)
    a = _mitte(cloud, token)
    a.holen()
    k = a.vorbereiten({"inhalt.enc": b"genau-diese-bytes"}, [], "")
    a.senden(k)
    assert _mitte(cloud, token).enthaelt(k) is True
    assert _mitte(cloud, token).enthaelt(abgleich_mitte.VORLAEUFIG + "0" * 32) is False


def test_nur_fehlende_blobs_gehen_hoch_und_stand_ist_nur_verweise(cloud):
    token = _token(cloud)
    m = _mitte(cloud, token)
    m.holen()
    m.senden(m.vorbereiten({"inhalt.enc": b"I1", "d/a.enc": b"A"}, [], ""))
    m.holen()
    m.senden(m.vorbereiten({"inhalt.enc": b"I2", "d/b.enc": b"A"}, ["d/a.enc"], ""))
    blobs = [p for meth, p in cloud.zustand.aufrufe if meth == "PUT" and "/blob/" in p]
    assert len(blobs) == 3                       # I1, A, I2 — A nicht zweimal
    stand, lesen, namen = m.holen()
    assert sorted(namen) == ["d/b.enc", "inhalt.enc"] and lesen("d/b.enc") == b"A"


def test_blob_fehlt_wird_einmal_nachgeladen(cloud, monkeypatch):
    m = _mitte(cloud, _token(cloud))
    m.holen()
    echt, erstes = abgleich_mitte.HttpMitte._hochladen, {"mal": True}

    def vergisst_beim_ersten_mal(self, inhalte):
        if erstes.pop("mal", False):
            return
        echt(self, inhalte)
    monkeypatch.setattr(abgleich_mitte.HttpMitte, "_hochladen", vergisst_beim_ersten_mal)
    assert m.senden(m.vorbereiten({"inhalt.enc": b"I"}, [], "")) is True


def test_ohne_sitzung_klarer_fehler(cloud):
    with pytest.raises(abgleich_mitte.MitteFehler, match="(?i)not logged in"):
        _mitte(cloud).holen()


# ── Ein ganzer Abgleich, zwei Geräte ───────────────────────────────────

class Geraet:
    def __init__(self, cloud, mp, tmp, name):
        self.cloud, self.mp, self.name = cloud, mp, name
        self.wurzel = tmp / name / "zentrale"
        (self.wurzel / "data").mkdir(parents=True)
        self.ordner = tmp / name

    def ich(self):
        self.mp.setenv("ZENTRALE_ABGLEICH_DIR", str(self.ordner / "abgleich"))
        self.mp.setenv("ZENTRALE_KONTO_DATEI", str(self.ordner / "konto.json"))
        self.mp.setattr(dateien, "knoten", lambda: self.name)
        self.mp.setattr(ai_config, "_overrides", getattr(self, "_einst", {}))
        self._einst = ai_config._overrides
        # Einstellungen gelten je Gerät — auch die persistierten.
        self.mp.setattr(ai_config, "_config", getattr(self, "_conf", {}))
        self._conf = ai_config._config
        return self

    def abgleichen(self):
        self.ich()
        return abgleich.abgleichen(str(self.wurzel))

    def schreiben(self, rel, inhalt):
        p = self.wurzel / "data" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(inhalt if isinstance(inhalt, str) else json.dumps(inhalt), encoding="utf-8")

    def lesen(self, rel):
        p = self.wurzel / "data" / rel
        return p.read_text(encoding="utf-8") if p.exists() else None

    def alles(self):
        """{rel: inhalt} von allem, was auf der Positivliste steht."""
        return {rel: (self.wurzel / rel).read_bytes()
                for rel in auswahl.auswahl(str(self.wurzel), auswahl.ABGLEICH)}


@pytest.fixture
def zwei(cloud, monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    laptop = Geraet(cloud, monkeypatch, tmp_path, "laptop").ich()
    entwurf = konto.Entwurf(PW)
    konto.anlegen(entwurf, "sasha", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    pc = Geraet(cloud, monkeypatch, tmp_path, "pc").ich()
    konto.anmelden("sasha", PW)
    laptop.konto_schluessel = entwurf.konto_schluessel
    return laptop, pc


def test_zwei_geraete_ueber_die_cloud(zwei, cloud):
    laptop, pc = zwei
    laptop.schreiben("lists.json", LISTE)
    laptop.schreiben("gedaechtnis/sasha.md", "# Sasha\nmag Tee\n")
    assert laptop.abgleichen().art == "erstbefuellung"
    assert pc.abgleichen().art == "erstabgleich"
    assert json.loads(pc.lesen("lists.json")) == LISTE
    assert pc.lesen("gedaechtnis/sasha.md") == "# Sasha\nmag Tee\n"
    # Beide ändern verschiedene Einträge — beide bleiben.
    pc_liste = json.loads(pc.lesen("lists.json"))
    pc_liste[0]["items"].append({"id": 2, "text": "Brot", "done": False})
    pc_liste[0]["next_item"] = 3
    pc.schreiben("lists.json", pc_liste)
    pc.abgleichen()
    l_liste = json.loads(laptop.lesen("lists.json"))
    l_liste[0]["items"][0]["done"] = True
    laptop.schreiben("lists.json", l_liste)
    laptop.abgleichen()
    pc.abgleichen()
    fertig = json.loads(pc.lesen("lists.json"))[0]["items"]
    assert [(e["text"], e["done"]) for e in fertig] == [("Milch", True), ("Brot", False)]
    # Die Basis merkt sich die ECHTE Kennung des Servers.
    pc.ich()
    assert json.loads((pc.ordner / "abgleich" / "basis.json").read_text())["stand"] \
        == cloud.zustand.kopf["sasha"]


def test_cloud_sieht_nur_verschluesseltes_mit_dem_konto_schluessel(zwei, cloud):
    laptop, _ = zwei
    laptop.schreiben("gedaechtnis/geheim.md", "Tagebuch: streng geheim\n")
    laptop.abgleichen()
    stand = cloud.zustand.staende[cloud.zustand.kopf["sasha"]]
    alles = b"".join(stand.values()) + b"".join(n.encode() for n in stand)
    assert b"streng geheim" not in alles and b"gedaechtnis" not in alles
    inhalt = json.loads(schluessel.Tresor(laptop.konto_schluessel).auf(stand["inhalt.enc"]))
    assert "data/gedaechtnis/geheim.md" in inhalt["dateien"]


def test_jemand_schneller_ueber_die_cloud_beide_bleiben(zwei, cloud, monkeypatch):
    laptop, pc = zwei
    laptop.schreiben("notes.json", {"notes": []})
    laptop.abgleichen()
    pc.abgleichen()
    pc.schreiben("gedaechtnis/pc.md", "vom pc\n")
    laptop.schreiben("gedaechtnis/laptop.md", "vom laptop\n")
    echt_holen = abgleich_mitte.HttpMitte.holen
    zwischendurch = {"einmal": True}

    def holen_und_pc_schiebt_dazwischen(self):
        r = echt_holen(self)
        if zwischendurch.pop("einmal", False):
            pc.abgleichen()
            laptop.ich()
        return r
    laptop.ich()
    monkeypatch.setattr(abgleich_mitte.HttpMitte, "holen", holen_und_pc_schiebt_dazwischen)
    laptop.abgleichen()
    monkeypatch.setattr(abgleich_mitte.HttpMitte, "holen", echt_holen)
    pc.abgleichen()
    assert laptop.lesen("gedaechtnis/pc.md") == "vom pc\n"
    assert pc.lesen("gedaechtnis/laptop.md") == "vom laptop\n"
    assert any(p == "/v1/mitte/stand" for _m, p in cloud.zustand.aufrufe)


def test_abgemeldet_klarer_fehler_statt_abgleich(zwei):
    laptop, _ = zwei
    laptop.ich()
    konto.abmelden()
    with pytest.raises(schluessel.SchluesselFehler, match="Not logged in"):
        laptop.abgleichen()
    assert abgleich.zustand()["schluessel_da"] is False


# ── Apps je Gerät ──────────────────────────────────────────────────

def test_abgewaehlte_app_wird_weder_geholt_noch_gesendet(zwei, cloud):
    laptop, pc = zwei
    laptop.schreiben("lists.json", LISTE)
    laptop.schreiben("gedaechtnis/sasha.md", "mag Tee\n")
    laptop.abgleichen()
    pc.ich()
    abgleich_apps.setzen({"fokus": True, "assistent": False})
    pc.schreiben("gedaechtnis/nur_pc.md", "bleibt hier\n")
    pc.abgleichen()
    assert pc.lesen("lists.json") is not None
    assert pc.lesen("gedaechtnis/sasha.md") is None                 # nicht geholt
    laptop.abgleichen()
    assert laptop.lesen("gedaechtnis/nur_pc.md") is None            # nicht gesendet
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Tee\n"      # in der Mitte unberührt
    inhalt = json.loads(schluessel.Tresor(laptop.konto_schluessel).auf(
        cloud.zustand.staende[cloud.zustand.kopf["sasha"]]["inhalt.enc"]))
    assert "data/gedaechtnis/sasha.md" in inhalt["dateien"]
    assert "data/gedaechtnis/nur_pc.md" not in inhalt["dateien"]


def test_app_spaeter_abwaehlen_loescht_nirgends(zwei):
    laptop, pc = zwei
    laptop.schreiben("gedaechtnis/sasha.md", "mag Tee\n")
    laptop.abgleichen()
    pc.abgleichen()
    pc.ich()
    abgleich_apps.setzen({n: False for n in abgleich_apps.tabelle()})   # clean slate
    pc.abgleichen()
    laptop.abgleichen()
    assert pc.lesen("gedaechtnis/sasha.md") == "mag Tee\n"
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Tee\n"


# Eine Datei je App (und je Muster), auch der Tutor am alten Ort.
JE_APP = {"data/lists.json": "[]", "data/features.json": "[]", "data/notes.json": '{"notes": []}',
          "data/kalender_neben.json": "{}", "data/graphs.json": "[]", "data/g_schlaf.json": "{}",
          "data/sleep_quality.json": "{}", "data/gedaechtnis/sasha.md": "Tee\n",
          "data/gespraeche/g1/laptop.jsonl": "{}\n", "data/ai_transcripts/a.jsonl": "{}\n",
          "data/rueckmeldungen/laptop.jsonl": "{}\n", "data/mobil/kontext.json": "{}",
          "data/ai_usage.json": "{}", "data/ablage/d1/brief.txt": "Hallo\n",
          "data/desk/a.canvas": "{}", "data/apps/meine/app.toml": "name = 'meine'\n",
          "data/shop/besitz-laptop.jsonld": "{}", "data/mail_rules.json": "[]",
          "data/melodies.json": "[]", "tutor/data/tutor_config.json": "{}",
          "tutor/data/aktiver_stand": "es\n", "tutor/data/staende/s1.json": "{}",
          "tutor/data/es/w.json": "{}"}


def test_sashas_alte_wahl_alles_gleicht_genau_dasselbe_ab(zwei, cloud):
    """Sasha am 23.10.: Setup mit „alles" (abgleich_bereiche = alle ids, Weg
    mitte, http). Nach dem Umbau liest das Gerät die alte Wahl und gleicht
    dieselben Dateien ab wie ein Gerät ohne Wahl — nichts fehlt, nichts fragt."""
    laptop, pc = zwei
    for rel, inhalt in JE_APP.items():
        p = laptop.wurzel / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(inhalt, encoding="utf-8")
    assert sorted(laptop.alles()) == sorted(JE_APP)              # jede Datei steht auf der Liste
    pc.ich()
    pc._einst.update(abgleich_bereiche=["lists", "notes", "calendar", "graphs", "memory",
                                        "conversations", "documents", "desk", "apps", "mail",
                                        "music", "tutor"],
                     abgleich_weg="mitte")
    # Only the cloud folder (newer than the old areas) is undecided; it has no
    # data here nor in the cloud → nothing to ask.
    assert abgleich_apps.offen(str(pc.wurzel), lambda: set()) == []
    laptop.abgleichen()
    pc.abgleichen()
    assert pc.alles() == laptop.alles()
    (pc.wurzel / "data" / "notes.json").write_text('{"notes": [{"id": "n1"}]}')
    (pc.wurzel / "tutor" / "data" / "es" / "neu.json").write_text("{}")
    pc.abgleichen()
    laptop.abgleichen()
    assert pc.alles() == laptop.alles() and len(laptop.alles()) == len(JE_APP) + 1


def test_manifest_mit_schluesseldatei_wird_nie_abgeglichen(zwei, cloud, tmp_path, monkeypatch):
    laptop, pc = zwei
    eigen = tmp_path / "eigene_apps" / "boese"
    eigen.mkdir(parents=True)
    (eigen / "app.toml").write_text('name = "boese"\nvorlage = "desk"\n[daten]\n'
                                    'muster = ["data/ai_config.json", "../x", "data/**"]\n'
                                    'abgleichen = true\n')
    monkeypatch.setenv("ZENTRALE_APPS_ORDNER", str(tmp_path / "eigene_apps"))
    laptop.ich()
    abgleich_apps.setzen({"boese": True, "fokus": True})
    laptop.schreiben("ai_config.json", {"ANTHROPIC_API_KEY": "sk-geheim"})
    (laptop.wurzel / "x").write_text("daneben")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    inhalt = json.loads(schluessel.Tresor(laptop.konto_schluessel).auf(
        cloud.zustand.staende[cloud.zustand.kopf["sasha"]]["inhalt.enc"]))
    assert sorted(inhalt["dateien"]) == ["data/lists.json"]


def test_cloud_pfade_nur_aus_dem_inhaltsverzeichnis(zwei, cloud):
    laptop, pc = zwei
    laptop.schreiben("lists.json", LISTE)
    laptop.schreiben("gedaechtnis/sasha.md", "Tee\n")
    laptop.abgleichen()
    pc.ich()
    vorher = len(cloud.zustand.aufrufe)
    assert abgleich.cloud_pfade() == {"data/lists.json", "data/gedaechtnis/sasha.md"}
    dateien_geholt = [p for m, p in cloud.zustand.aufrufe[vorher:] if "/datei/" in p]
    assert dateien_geholt == ["/v1/mitte/datei/inhalt.enc"]
    konto.abmelden()
    assert abgleich.cloud_pfade() is None


def test_cloud_als_app_im_zustand(zwei):
    laptop, _ = zwei
    laptop.ich()
    assert abgleich.cloud_an() is True and abgleich.zustand()["cloud"] is True
    konto.abmelden()
    assert abgleich.cloud_an() is False


def test_daten_als_verweis_werden_gefunden(tmp_path):
    """Installierter Hub: data/ ist ein Verweis auf ~/.local/share/zentrale/data."""
    echt = tmp_path / "daten"
    (echt / "gedaechtnis").mkdir(parents=True)
    (echt / "gedaechtnis" / "a.md").write_text("x")
    (echt / "lists.json").write_text("[]")
    hub = tmp_path / "hub" / "1"
    hub.mkdir(parents=True)
    (hub / "data").symlink_to(echt)
    assert auswahl.auswahl(str(hub), auswahl.ABGLEICH) == ["data/gedaechtnis/a.md", "data/lists.json"]


def test_absturz_nach_dem_senden_ueber_die_cloud_wird_zu_ende_gebracht(zwei, cloud, monkeypatch):
    laptop, pc = zwei
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    laptop.schreiben("gedaechtnis/neu.md", "nach dem Absturz da\n")
    echt = abgleich._vorhaben_abschliessen

    def absturz(wurzel, bericht=None):
        raise RuntimeError("Strom weg")
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", absturz)
    with pytest.raises(RuntimeError):
        laptop.abgleichen()
    monkeypatch.setattr(abgleich, "_vorhaben_abschliessen", echt)
    kopf = cloud.zustand.kopf["sasha"]
    laptop.abgleichen()                         # erkennt die vorläufige Kennung wieder
    assert cloud.zustand.kopf["sasha"] == kopf  # nichts doppelt gesendet
    assert json.loads((laptop.ordner / "abgleich" / "basis.json").read_text())["stand"] == kopf
    pc.abgleichen()
    assert pc.lesen("gedaechtnis/neu.md") == "nach dem Absturz da\n"
