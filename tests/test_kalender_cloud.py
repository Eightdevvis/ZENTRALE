"""Der Kalender über die Cloud mit dem Adapter (memory/hub/adapter.md):
zwei gespielte Geräte gegen eine gespielte Cloud (tests/_falsche_cloud.py)
und ein gespieltes „Google" — ein Ordner, mit dem das ECHTE vdirsyncer
abgleicht (filesystem-Speicher; Google selbst wird nie gefragt).

Geprüft: nur die Brücke fährt Google; ein zweites Gerät sieht die Termine
nach dem Abgleich; nach Runden Brücke + Cloud keine Doppelten; Löschen kommt
überall an; die Brücke ist ein Mietvertrag — fällt der Inhaber aus, übernimmt
ein anderes Gerät nahtlos (Stand von vdirsyncer und erneuerter Token reisen
mit), und es fahren nie zwei zugleich."""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess

import pytest

import abgleich
import adapter
import adapter_ablauf
import adapter_bruecke as bruecke
import adapter_geheim
import ai_config
import dateien
import kalender
import kalender_ics
import konto
import konto_schluessel as ks
from _falsche_cloud import FalscheCloud

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PW = "ein-langes-passwort"

pytestmark = pytest.mark.skipif(not shutil.which("vdirsyncer"),
                                reason="vdirsyncer ist auf diesem Rechner nicht installiert")


def _skript():
    spec = importlib.util.spec_from_file_location(
        "kalender_sync_test", os.path.join(ROOT, "scripts", "kalender_sync.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ics(uid, titel, tag="20261102"):
    return (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//DE\r\nBEGIN:VEVENT\r\n"
            f"UID:{uid}\r\nDTSTAMP:20261024T100000Z\r\nDTSTART;VALUE=DATE:{tag}\r\n"
            f"SUMMARY:{titel}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


class Uhr:
    def __init__(self):
        self.t = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=datetime.timezone.utc)

    def weiter(self, minuten):
        self.t += datetime.timedelta(minutes=minuten)


class Geraet:
    def __init__(self, welt, name):
        self.welt, self.name = welt, name
        self.ordner = welt.tmp / name
        self.wurzel = self.ordner / "zentrale"
        (self.wurzel / "data").mkdir(parents=True)
        self.home = self.ordner / "home"
        self.home.mkdir()
        self._einst, self._conf = {}, {}
        self.laeufe = 0

    def ich(self):
        mp = self.welt.mp
        mp.setenv("HOME", str(self.home))
        mp.setenv("ZENTRALE_ABGLEICH_DIR", str(self.ordner / "abgleich"))
        mp.setenv("ZENTRALE_KONTO_DATEI", str(self.ordner / "konto.json"))
        mp.setenv("ZENTRALE_ADAPTER_ORDNER", str(self.wurzel / "data" / "adapter"))
        mp.setenv("ZENTRALE_ADAPTER_LAUF", str(self.ordner / "adapter_lauf"))
        mp.setenv("ZENTRALE_ADAPTER_SCHLUESSEL", str(self.ordner / "adapter.schluessel"))
        mp.setenv("ZENTRALE_VDIRSYNCER_CONFIG", str(self.home / ".config/vdirsyncer/config"))
        mp.setenv("ZENTRALE_KALENDER_SYNC_STAND", str(self.ordner / "sync_stand.json"))
        mp.setenv("ZENTRALE_KALENDER_SYNC_ZUSTAND", str(self.ordner / "sync_zustand.json"))
        mp.setattr(self.welt.skript, "STAND", str(self.ordner / "sync_stand.json"))
        mp.setattr(dateien, "knoten", lambda: self.name)
        mp.setattr(kalender, "CAL_PATH", self.wurzel / "data" / "ai_calendar.json")
        mp.setattr(ai_config, "_overrides", self._einst)
        mp.setattr(ai_config, "_config", self._conf)
        kalender_ics.cache_leeren()
        return self

    @property
    def vdir(self):
        return self.wurzel / "data" / "kalender"

    def abgleichen(self):
        self.ich()
        return abgleich.abgleichen(str(self.wurzel))

    def google_lauf(self):
        """Ein Lauf des Kalender-Timers auf diesem Gerät (das echte Skript)."""
        self.ich()
        return self.welt.skript.main([])

    def termine(self):
        """{dateiname: inhalt} im Kalender-Ordner (nur .ics)."""
        return {p.relative_to(self.vdir).as_posix(): p.read_text()
                for p in self.vdir.rglob("*.ics")} if self.vdir.exists() else {}


def _uids(dateien_):
    raus = []
    for text in dateien_.values():
        raus += [z[4:].strip() for z in text.splitlines() if z.startswith("UID:")]
    return raus


@pytest.fixture
def welt(monkeypatch, tmp_path):
    """Laptop mit eingerichtetem vdirsyncer (wie Sashas), Mini-PC frisch
    beigetreten, beide im selben Konto, eine Cloud, ein „Google"."""
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "ics")
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    monkeypatch.delenv("VDIRSYNCER_CONFIG", raising=False)
    uhr = Uhr()
    monkeypatch.setattr(bruecke, "_utc", lambda jetzt=None: jetzt or uhr.t)

    class Welt:
        pass
    w = Welt()
    w.mp, w.tmp, w.cloud, w.uhr = monkeypatch, tmp_path, c, uhr
    w.skript = _skript()
    w.google = tmp_path / "google"
    (w.google / "termine").mkdir(parents=True)
    w.laptop, w.minipc = Geraet(w, "laptop"), Geraet(w, "minipc")

    # Gezählt wird jeder echte Google-Lauf, je Gerät.
    echt = w.skript._ein_lauf

    def gezaehlt(argv=None):
        {"laptop": w.laptop, "minipc": w.minipc}[dateien.knoten()].laeufe += 1
        return echt(argv)
    monkeypatch.setattr(w.skript, "_ein_lauf", gezaehlt)

    # Der Laptop: Kalender mit Google schon im Gleichen (vdirsyncer lief dort).
    lap = w.laptop.ich()
    entwurf = konto.Entwurf(PW)
    konto.anlegen(entwurf, "sasha", "ZB-AAAA-BBBB-CCCC-DDDD", PW)
    (lap.vdir / "termine").mkdir(parents=True)
    for uid, titel in (("g1", "Geige"), ("g2", "Zahnarzt")):
        (w.google / "termine" / f"{uid}.ics").write_text(_ics(uid, titel))
    cfg = lap.home / ".config/vdirsyncer/config"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f"""[general]
status_path = "~/.local/share/vdirsyncer/status/"

[pair zentrale]
a = "zentrale_lokal"
b = "zentrale_google"
collections = ["termine"]
conflict_resolution = null

[storage zentrale_lokal]
type = "filesystem"
path = "{lap.vdir}/"
fileext = ".ics"

[storage zentrale_google]
type = "filesystem"
path = "{w.google}/"
fileext = ".ics"

[pair google_probe]
a = "google_nur_lesen"
b = "google_kopie"
collections = ["termine"]
conflict_resolution = "a wins"

[storage google_nur_lesen]
type = "filesystem"
path = "{w.google}/"
fileext = ".ics"
read_only = true

[storage google_kopie]
type = "filesystem"
path = "~/.local/share/vdirsyncer/google_kopie/"
fileext = ".ics"

[storage google_zugang]
type = "google_calendar"
token_file = "~/.local/share/vdirsyncer/google_token"
client_id = "die-client-id"
client_secret = "das-client-geheimnis"
""")
    tok = lap.home / ".local/share/vdirsyncer/google_token"
    tok.parent.mkdir(parents=True)
    tok.write_text('{"access_token": "alt", "refresh_token": "r1"}')
    env = dict(os.environ, VDIRSYNCER_CONFIG=str(cfg))
    (lap.home / ".local/share/vdirsyncer/google_kopie/termine").mkdir(parents=True)
    for paar in ("zentrale", "google_probe"):
        subprocess.run(["vdirsyncer", "discover", paar], env=env, input="", check=True,
                       capture_output=True, text=True)
    subprocess.run(["vdirsyncer", "sync"], env=env, check=True, capture_output=True)
    assert sorted(lap.termine()) == ["termine/g1.ics", "termine/g2.ics"]

    mini = w.minipc.ich()
    konto.anmelden("sasha", PW)
    yield w
    c.stopp()


def _einrichten_und_verteilen(w):
    lap = w.laptop.ich()
    r = adapter_ablauf.einrichten(vdir=lap.vdir, wurzel=lap.wurzel)
    assert r["kalender"] == "angelegt"
    w.laptop.abgleichen()
    w.minipc.abgleichen()        # bringt den Adapter (Anschluss, Vertrag, Zugang)
    w.minipc.abgleichen()        # jetzt mit dem Kalender


# ── Einrichten ─────────────────────────────────────────────────────────

def test_einrichten_legt_anschluss_ohne_geheimnis_an(welt):
    lap = welt.laptop.ich()
    adapter_ablauf.einrichten(vdir=lap.vdir, wurzel=lap.wurzel)
    a = adapter.lesen("google-kalender", lap.wurzel)
    text = json.dumps(a)
    assert a["art"] == "kalender-vdirsyncer" and a["speist"] == "kalender"
    assert "das-client-geheimnis" not in text and "die-client-id" not in text
    assert str(lap.vdir) not in text and '"$ort": "kalender"' in text
    assert adapter_geheim.lesen("google-kalender/google_zugang/client_secret", lap.wurzel) \
        == "das-client-geheimnis"
    assert adapter.kalender_ueber_cloud(lap.wurzel)
    # Zweimal einrichten ändert nichts.
    assert adapter_ablauf.einrichten(vdir=lap.vdir, wurzel=lap.wurzel)["kalender"] == "vorhanden"


def test_zweites_geraet_sieht_die_termine_nach_dem_abgleich(welt):
    _einrichten_und_verteilen(welt)
    assert welt.minipc.termine() == welt.laptop.termine()
    mini = welt.minipc.ich()
    tage = kalender.entries_in_range(datetime.date(2026, 11, 2), datetime.date(2026, 11, 2))
    assert {e["label"] for d in tage.values() for e in d} >= {"Geige", "Zahnarzt"}


# ── Nur die Brücke fährt ───────────────────────────────────────────────

def test_nur_die_bruecke_faehrt_google(welt):
    _einrichten_und_verteilen(welt)
    assert welt.laptop.google_lauf() == 0
    welt.minipc.abgleichen()
    assert welt.minipc.google_lauf() == 0
    welt.uhr.weiter(3)
    assert welt.laptop.google_lauf() == 0
    assert (welt.laptop.laeufe, welt.minipc.laeufe) == (2, 0)
    m = bruecke.lesen("google-kalender", welt.minipc.wurzel)
    assert m["inhaber"] == "laptop"
    # Der Mini-PC zeigt den Stand der Brücke, nicht „läuft nicht".
    welt.minipc.ich()
    import kalender_sync_zustand
    assert kalender_sync_zustand.lesen()["bruecke"] == "laptop"


def test_beide_greifen_gleichzeitig_zu_nur_einer_haelt(welt):
    _einrichten_und_verteilen(welt)
    lap, mini = welt.laptop, welt.minipc
    lap.ich()
    bruecke.beanspruchen("google-kalender", "laptop", wurzel=lap.wurzel)
    mini.ich()
    bruecke.beanspruchen("google-kalender", "minipc", wurzel=mini.wurzel)
    lap.abgleichen()
    mini.abgleichen()                  # die Mitte ist weiter: „wer zuerst kam"
    lap.abgleichen()
    halter = [g.name for g in (lap, mini)
              if bruecke.haelt(bruecke.lesen("google-kalender", g.wurzel), g.name)]
    assert halter == ["laptop"]


def test_faellt_die_bruecke_aus_uebernimmt_ein_anderes_geraet_nahtlos(welt):
    _einrichten_und_verteilen(welt)
    lap, mini = welt.laptop, welt.minipc
    assert lap.google_lauf() == 0
    welt.uhr.weiter(5)
    assert mini.google_lauf() == 0 and mini.laeufe == 0     # Laptop hält noch
    # Der Laptop ist weg (zugeklappt). Nach Ablauf des Vertrags:
    welt.uhr.weiter(bruecke.MIETE_MIN + 1)
    google_vorher = sorted(p.name for p in (welt.google / "termine").iterdir())
    # Google hat inzwischen den Token erneuert — das erlebt erst der Mini-PC.
    echt = welt.skript._ein_lauf

    def mit_erneuertem_token(argv=None):
        (mini.home / ".local/share/vdirsyncer/google_token").write_text(
            '{"access_token": "neu", "refresh_token": "r1"}')
        return echt(argv)
    welt.mp.setattr(welt.skript, "_ein_lauf", mit_erneuertem_token)
    assert mini.google_lauf() == 0
    assert bruecke.lesen("google-kalender", mini.wurzel)["inhaber"] == "minipc"
    # Sein Zugang kam aus der Cloud, sein Stand von vdirsyncer auch: nichts
    # wurde neu hochgeladen, nichts doppelt.
    assert sorted(p.name for p in (welt.google / "termine").iterdir()) == google_vorher
    cfg = (mini.ordner / "adapter_lauf/google-kalender/vdirsyncer.config").read_text()
    assert "das-client-geheimnis" in cfg and str(mini.vdir) in cfg
    # Die Nur-Lese-Kopie von Google liegt jetzt auch beim Mini-PC.
    assert sorted(p.name for p in (mini.home / ".local/share/vdirsyncer/google_kopie/termine").iterdir()) \
        == google_vorher
    assert oct(os.stat(mini.ordner / "adapter_lauf/google-kalender/vdirsyncer.config").st_mode)[-3:] == "600"
    # Der Laptop wacht auf: sein alter Vertrag ist abgelaufen, der Mini-PC hat ihn.
    welt.mp.setattr(welt.skript, "_ein_lauf", echt)
    lap.laeufe = 0
    assert lap.google_lauf() == 0 and lap.laeufe == 0
    assert bruecke.lesen("google-kalender", lap.wurzel)["inhaber"] == "minipc"
    # Der erneuerte Token ist beim Laptop angekommen — fällt der Mini-PC aus,
    # fährt der Laptop mit ihm weiter.
    lap.ich()
    assert b'"neu"' in adapter_geheim.lesen_bytes("google-kalender/datei/google_zugang", lap.wurzel)
    welt.uhr.weiter(bruecke.MIETE_MIN + 1)
    assert lap.google_lauf() == 0 and lap.laeufe == 1
    assert '"neu"' in (lap.home / ".local/share/vdirsyncer/google_token").read_text()


# ── Runden ohne Doppelte, Löschen kommt an ─────────────────────────────

def _runde(w):
    w.laptop.google_lauf()
    w.minipc.abgleichen()
    w.laptop.abgleichen()
    w.minipc.abgleichen()


def test_runden_ohne_doppelte_und_loeschen_kommt_an(welt):
    _einrichten_und_verteilen(welt)
    lap, mini = welt.laptop, welt.minipc
    lap.google_lauf()
    # Auf dem Mini-PC angelegt (über ZENTRALE, nicht über Google).
    mini.ich()
    assert kalender.add_entry("termine", "2026-11-05", "Klavierstunde")
    mini.abgleichen()
    for _ in range(3):
        _runde(welt)
        welt.uhr.weiter(3)
    google = {p.name: p.read_text() for p in (welt.google / "termine").iterdir()}
    for g in (lap, mini):
        uids = _uids(g.termine())
        assert len(uids) == len(set(uids)) == 3, g.name
    assert sorted(_uids(google)) == sorted(_uids(lap.termine())) == sorted(_uids(mini.termine()))
    assert lap.termine() == mini.termine()
    # Bei Google neu angelegt → kommt über die Brücke und die Cloud an.
    (welt.google / "termine" / "g3.ics").write_text(_ics("g3", "Konzert", "20261107"))
    _runde(welt)
    assert "g3" in _uids(mini.termine())
    # Auf dem Mini-PC gelöscht → bei Google und auf dem Laptop weg.
    mini.ich()
    assert kalender.delete_entry("2026-11-02", "Zahnarzt") == 1
    mini.abgleichen()
    _runde(welt)
    assert "g2" not in _uids(lap.termine()) and "g2" not in _uids(mini.termine())
    assert not (welt.google / "termine" / "g2.ics").exists()
    # Bei Google gelöscht → überall weg.
    (welt.google / "termine" / "g1.ics").unlink()
    _runde(welt)
    assert "g1" not in _uids(mini.termine())
    uids = _uids(mini.termine())
    assert len(uids) == len(set(uids))
    assert (lap.laeufe, mini.laeufe) == (lap.laeufe, 0)


def test_beide_aendern_denselben_termin_eine_gueltige_datei(welt):
    _einrichten_und_verteilen(welt)
    lap, mini = welt.laptop, welt.minipc
    datei = "termine/g1.ics"
    alt = lap.termine()[datei]
    (lap.vdir / datei).write_text(alt.replace("SUMMARY:Geige", "SUMMARY:Geige (Probe)")
                                  .replace("DTSTAMP:20261024T100000Z", "DTSTAMP:20261024T110000Z"))
    (mini.vdir / datei).write_text(alt.replace("SUMMARY:Geige", "SUMMARY:Geige verschoben")
                                   .replace("DTSTAMP:20261024T100000Z", "DTSTAMP:20261024T120000Z"))
    lap.abgleichen()
    mini.abgleichen()
    lap.abgleichen()
    for g in (lap, mini):
        text = g.termine()[datei]
        assert "Geige verschoben" in text and "⟪" not in text and text.count("BEGIN:VEVENT") == 1


# ── Ein Gerät mit altem eigenen Kalender kommt dazu ───────────────────

def test_alter_eigener_kalender_wandert_beiseite_statt_geister_zu_bringen(welt):
    mini = welt.minipc.ich()
    (mini.vdir / "termine").mkdir(parents=True)
    (mini.vdir / "termine" / "geist.ics").write_text(_ics("geist", "Längst gelöscht"))
    # Ein alter Grabstein für einen Termin, den es in der Cloud gibt.
    steine = mini.wurzel / "data" / "kalender_verlauf" / "grabsteine"
    steine.mkdir(parents=True)
    (steine / "g1.json").write_text(json.dumps({"uid": "g1", "ebene": "termine", "knoten": "minipc",
                                                "geloescht_um": "2099-01-01T00:00:00+00:00"}))
    _einrichten_und_verteilen(welt)
    assert "geist" not in _uids(mini.termine())
    assert "g1" in _uids(mini.termine()) and not steine.exists()
    mini.ich()
    tage = kalender.entries_in_range(datetime.date(2026, 11, 2), datetime.date(2026, 11, 2))
    assert "Geige" in {e["label"] for d in tage.values() for e in d}     # kein Geist
    beiseite = list((mini.ordner / "abgleich" / "kalender-vor-cloud").rglob("geist.ics"))
    assert len(beiseite) == 1
    welt.laptop.google_lauf()
    assert not (welt.google / "termine" / "geist.ics").exists()
    assert "geist" not in _uids(welt.laptop.termine())


def test_ohne_konto_ist_jedes_geraet_seine_eigene_bruecke(welt, monkeypatch):
    lap = welt.laptop.ich()
    konto.abmelden()
    adapter_ablauf.einrichten(vdir=lap.vdir, wurzel=lap.wurzel)
    assert lap.google_lauf() == 0 and lap.laeufe == 1
    assert bruecke.lesen("google-kalender", lap.wurzel) is None
