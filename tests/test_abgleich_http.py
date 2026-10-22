"""Abgleich über die Cloud: HttpMitte (core/abgleich_mitte.py) gegen eine
gespielte Cloud (tests/_falsche_cloud.py), und ein ganzer Abgleich mit zwei
gespielten Geräten, Schlüssel = konto_schluessel aus konto.json.
Dazu die Bereichs-Wahl je Gerät (core/abgleich_bereiche.py)."""
import json

import pytest

import abgleich
import abgleich_auswahl as auswahl
import abgleich_bereiche as bereiche
import abgleich_mitte
import abgleich_schluessel as schluessel
import ai_config
import cloud_api
import dateien
import konto
import konto_schluessel as ks
from _falsche_cloud import FalscheCloud

PW = "ein-langes-passwort"
LISTE = [{"id": "einkauf", "name": "Einkauf", "next_item": 2,
          "items": [{"id": 1, "text": "Milch", "done": False}]}]


@pytest.fixture
def cloud(monkeypatch):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 64, "p": 1})
    yield c
    c.stopp()


def _mitte(cloud, token=None):
    return abgleich_mitte.HttpMitte(cloud_api.Client(cloud.adresse, token=token))


def _token(cloud):
    konto.anlegen(konto.Entwurf(PW), "s@x.org", "EINLADUNG-1", PW)
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


@pytest.fixture
def zwei(cloud, monkeypatch, tmp_path):
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    laptop = Geraet(cloud, monkeypatch, tmp_path, "laptop").ich()
    entwurf = konto.Entwurf(PW)
    konto.anlegen(entwurf, "s@x.org", "EINLADUNG-1", PW)
    pc = Geraet(cloud, monkeypatch, tmp_path, "pc").ich()
    konto.anmelden("s@x.org", PW)
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
        == cloud.zustand.kopf["s@x.org"]


def test_cloud_sieht_nur_verschluesseltes_mit_dem_konto_schluessel(zwei, cloud):
    laptop, _ = zwei
    laptop.schreiben("gedaechtnis/geheim.md", "Tagebuch: streng geheim\n")
    laptop.abgleichen()
    stand = cloud.zustand.staende[cloud.zustand.kopf["s@x.org"]]
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


# ── Bereiche je Gerät ──────────────────────────────────────────────────

def test_abgewaehlter_bereich_wird_weder_geholt_noch_gesendet(zwei, cloud):
    laptop, pc = zwei
    laptop.schreiben("lists.json", LISTE)
    laptop.schreiben("gedaechtnis/sasha.md", "mag Tee\n")
    laptop.abgleichen()
    pc.ich()
    bereiche.setzen(["lists"])
    pc.schreiben("gedaechtnis/nur_pc.md", "bleibt hier\n")
    pc.abgleichen()
    assert pc.lesen("lists.json") is not None
    assert pc.lesen("gedaechtnis/sasha.md") is None                 # nicht geholt
    laptop.abgleichen()
    assert laptop.lesen("gedaechtnis/nur_pc.md") is None            # nicht gesendet
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Tee\n"      # in der Mitte unberührt
    inhalt = json.loads(schluessel.Tresor(laptop.konto_schluessel).auf(
        cloud.zustand.staende[cloud.zustand.kopf["s@x.org"]]["inhalt.enc"]))
    assert "data/gedaechtnis/sasha.md" in inhalt["dateien"]
    assert "data/gedaechtnis/nur_pc.md" not in inhalt["dateien"]


def test_bereich_spaeter_abwaehlen_loescht_nirgends(zwei):
    laptop, pc = zwei
    laptop.schreiben("gedaechtnis/sasha.md", "mag Tee\n")
    laptop.abgleichen()
    pc.abgleichen()
    pc.ich()
    bereiche.setzen([])                                             # clean slate
    pc.abgleichen()
    laptop.abgleichen()
    assert pc.lesen("gedaechtnis/sasha.md") == "mag Tee\n"
    assert laptop.lesen("gedaechtnis/sasha.md") == "mag Tee\n"


def test_jedes_muster_der_positivliste_hat_genau_einen_bereich():
    for m in auswahl.ABGLEICH:
        treffer = [i for i, _a, ms in bereiche.BEREICHE if m in ms]
        assert len(treffer) == 1, f"{m}: {treffer} — in core/abgleich_bereiche.py eintragen"
    alle = [m for _i, _a, ms in bereiche.BEREICHE for m in ms]
    assert set(alle) == set(auswahl.ABGLEICH)
    assert bereiche.gewaehlt() is None and set(bereiche.muster()) == set(auswahl.ABGLEICH)


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
    kopf = cloud.zustand.kopf["s@x.org"]
    laptop.abgleichen()                         # erkennt die vorläufige Kennung wieder
    assert cloud.zustand.kopf["s@x.org"] == kopf  # nichts doppelt gesendet
    assert json.loads((laptop.ordner / "abgleich" / "basis.json").read_text())["stand"] == kopf
    pc.abgleichen()
    assert pc.lesen("gedaechtnis/neu.md") == "nach dem Absturz da\n"
