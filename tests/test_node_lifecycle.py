"""Build steps 7 and 8 (memory/hub/building_kit_plan.md) against the fake
cloud (devkit/fake_cloud.py): an insecure release keeps syncing and is
warned in `status`/`devices`; `zentrale devices remove` and `zentrale leave`;
the removed device's next sync says so; "lost or stolen?" → the account key
is changed (core/key_rotation.py) and everything stays readable."""
import base64
import io
import json
import re

import pytest

import abgleich
import abgleich_schluessel as schluessel
import adapter_geheim
import ai_config
import cloud_notices
import dateien
import konto
import konto_schluessel as ks
from devkit.fake_cloud import FalscheCloud
from zentrale_cli import befehle, haupt
from zentrale_cli.ausgabe import Terminal

PW = "ein-langes-passwort"
CODE = "ZB-AAAA-BBBB-CCCC-DDDD"


class Play(Terminal):
    def __init__(self, *answers):
        super().__init__(aus=io.StringIO(), ein=io.StringIO("".join(a + "\n" for a in answers)))

    @property
    def text(self):
        return self.aus.getvalue()


class Device:
    def __init__(self, mp, tmp, name):
        self.mp, self.name = mp, name
        self.folder = tmp / name
        self.root = self.folder / "zentrale"
        (self.root / "data").mkdir(parents=True)
        (self.root / "VERSION").write_text("41\n")

    def me(self):
        self.mp.setenv("ZENTRALE_ABGLEICH_DIR", str(self.folder / "abgleich"))
        self.mp.setenv("ZENTRALE_KONTO_DATEI", str(self.folder / "konto.json"))
        self.mp.setenv("ZENTRALE_NUTZUNG_DIR", str(self.folder / "state"))
        self.mp.setattr(dateien, "knoten", lambda: self.name)
        self.mp.setattr(befehle, "WURZEL", str(self.root))
        return self

    def run(self, *argv_and_answers, answers=()):
        self.me()
        term = Play(*answers)
        rc = haupt.main(list(argv_and_answers), term=term)
        return rc, term.text


@pytest.fixture
def cloud(monkeypatch):
    c = FalscheCloud()
    monkeypatch.setenv("ZENTRALE_CLOUD", c.adresse)
    monkeypatch.setenv("ZENTRALE_LANG", "en")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_MITTE_ART", "http")
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    monkeypatch.setattr(ks, "KDF_VORGABE", {"name": "argon2id", "t": 1, "m": 19456, "p": 1})
    monkeypatch.setattr(cloud_notices, "_release", "41")
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    yield c
    c.stopp()


@pytest.fixture
def two(cloud, monkeypatch, tmp_path):
    """minipc creates the account, laptop logs in. → (minipc, laptop, draft)."""
    mini = Device(monkeypatch, tmp_path, "minipc").me()
    draft = konto.Entwurf(PW)
    konto.anlegen(draft, "sasha", CODE, PW)
    laptop = Device(monkeypatch, tmp_path, "laptop").me()
    konto.anmelden("sasha", PW)
    for d in (mini, laptop):
        d.me()
        befehle.geraet_melden()
    return mini, laptop, draft


# ── Build step 7: insecure release ─────────────────────────────────────

def test_insecure_release_warns_and_keeps_syncing(two, cloud):
    mini, laptop, _ = two
    cloud.zustand.insecure["41"] = {"since": 1793318400000, "link": "https://example.test/adv", "reason": "x"}
    (mini.root / "data" / "lists.json").write_text("[]")
    rc, text = mini.run("sync")
    assert rc == 0, text
    assert cloud.zustand.kopf["sasha"] is not None                    # synced anyway
    rc, text = mini.run("status")
    assert "Security: this version (41) is marked insecure since 2026-10-30" in text
    assert "https://example.test/adv" in text
    rc, text = laptop.run("devices")
    assert rc == 0
    assert text.count("insecure version since 2026-10-30") == 2        # both devices
    assert "Security: this version (41)" in text                      # and the own note
    # Unmarked → the next answer clears the note.
    cloud.zustand.insecure.clear()
    mini.run("sync")
    assert "Security" not in mini.run("status")[1]


def test_deprecation_header_parsing():
    d = cloud_notices.parse_deprecation({"Deprecation": "@1793318400",
                                         "Link": '<https://x.test/a>; rel="deprecation"; type="text/html"'})
    assert d == {"since": "2026-10-30T00:00:00+00:00", "link": "https://x.test/a"}
    assert cloud_notices.parse_deprecation({"Deprecation": "true"}) is None
    assert cloud_notices.parse_deprecation({}) is None


# ── Build step 8: remove and leave ─────────────────────────────────────

def test_remove_from_another_device(two, cloud):
    mini, laptop, _ = two
    rc, text = laptop.run("devices", "remove", "laptop")
    assert rc == 1 and "zentrale leave" in text
    rc, text = laptop.run("devices", "remove", "minipc", answers=("y", "n"))
    assert rc == 0, text
    assert "'minipc' was removed (1 session(s) ended)" in text
    assert "Change the account key" not in text                       # not lost → no offer

    rc, text = mini.run("sync")
    assert rc == 1 and "This device was removed from your account" in text
    assert mini.run("sync", "--automatic") == (0, "")                 # the timer stays quiet
    assert "Removed: this device was removed from your account" in mini.run("status")[1]

    rc, text = laptop.run("devices")
    assert re.search(r"minipc\n.*\n\s+removed .* \(from laptop\)", text), text

    # Logging in again adds it back.
    mini.me()
    konto.abmelden()
    konto.anmelden("sasha", PW)
    assert mini.run("sync")[0] == 0
    assert "Removed" not in mini.run("status")[1]


def test_remove_unknown_device(two):
    _, laptop, _ = two
    rc, text = laptop.run("devices", "remove", "toaster", answers=("y", "n"))
    assert rc == 1 and "There is no device 'toaster'" in text


def test_leave_keeps_data_by_default(two, cloud):
    mini, laptop, _ = two
    (mini.root / "data" / "lists.json").write_text("[]")
    rc, text = mini.run("leave", answers=("y", ""))
    assert rc == 0, text
    assert "'minipc' has left. The data on this device was kept." in text
    assert not konto.angemeldet()
    assert (mini.root / "data" / "lists.json").exists()
    tomb = cloud.zustand.knoten["sasha"]["minipc"]
    assert tomb["removed_by"] == "minipc"
    assert "left " in laptop.run("devices")[1]


def test_leave_deletes_data_when_asked(two):
    mini, _, _ = two
    (mini.root / "data" / "lists.json").write_text("[]")
    rc, text = mini.run("leave", answers=("y", "y"))
    assert rc == 0 and "was deleted" in text
    assert not (mini.root / "data").exists()


def test_leave_cancelled_changes_nothing(two):
    mini, _, _ = two
    rc, _text = mini.run("leave", answers=("",))
    assert rc == 1 and konto.angemeldet()


# ── Lost or stolen: change the account key ─────────────────────────────

def _inbox_file(mini, rel, content: bytes):
    """What the phone puts into its inbox (memory/betrieb/abgleich_fremde_knoten.md)."""
    import abgleich_mitte
    mini.me()
    t = schluessel.Tresor(konto.konto_schluessel())
    m = abgleich_mitte.HttpMitte(konto.client())
    m.holen()
    envelope = json.dumps({"format": 1, "pfad": rel, "inhalt": base64.b64encode(content).decode()}).encode()
    name = f"knoten/handy/{t.name(rel)}.enc"
    assert m.senden(m.vorbereiten({name: t.zu(envelope)}, []))
    return name


def test_lost_device_changes_the_account_key(two, cloud):
    mini, laptop, draft = two
    mini.me()
    (mini.root / "data" / "lists.json").write_text('[{"id": "a"}]')
    adapter_geheim.setzen("ki/TEST_KEY", "geheim-123", str(mini.root))
    assert mini.run("sync")[0] == 0
    old_inbox = _inbox_file(mini, "data/rueckmeldungen/handy.jsonl", b'{"x": 1}\n')
    old_key = konto.konto_schluessel()

    rc, text = mini.run("devices", "remove", "laptop",
                        answers=("y", "y", "y", PW, "", "y"))
    assert rc == 0, text
    assert "ALL your other devices" in text.split("Change the account key now?")[0]
    assert "The account key was changed" in text
    emergency = re.search(r"\n\s+([A-Z2-7]{4}(?:-[A-Z2-7]{4}){12})\n", text).group(1)

    new_key = konto.konto_schluessel()
    assert new_key != old_key
    new, z = schluessel.Tresor(new_key), cloud.zustand
    files = z.staende[z.kopf["sasha"]]
    inhalt = json.loads(new.auf(files["inhalt.enc"]))
    for rel, e in inhalt["dateien"].items():
        assert e["name"] == new.name(rel)
        new.auf(files["d/" + e["name"] + ".enc"])                     # every file opens
    assert old_inbox not in files
    assert f"knoten/handy/{new.name('data/rueckmeldungen/handy.jsonl')}.enc" in files
    with pytest.raises(schluessel.SchluesselFehler):
        schluessel.Tresor(old_key).auf(files["inhalt.enc"])
    # The vault in the cloud and here opens with the new key.
    vault = json.loads(new.auf(files["d/" + inhalt["dateien"]["data/adapter/geheim.enc"]["name"] + ".enc"]))
    from cryptography.fernet import Fernet
    assert Fernet(new_key).decrypt(vault["eintraege"]["ki/TEST_KEY"]["wert"].encode()) == b"geheim-123"
    assert adapter_geheim.lesen("ki/TEST_KEY", str(mini.root)) == "geheim-123"

    # This device syncs on without conflicts.
    b = abgleich.abgleichen(str(mini.root))
    assert not b.beiseite and not b.hinweise, b.hinweise

    # The laptop is out; a new login gets the new key. Old emergency key: dead; new one works.
    laptop.me()
    konto.abmelden()
    assert konto.anmelden("sasha", PW)["konto_schluessel"].encode() == new_key
    with pytest.raises(konto.KontoFehler):
        konto.wiederherstellen("sasha", draft.notfall_text, "noch-ein-passwort")
    assert konto.wiederherstellen("sasha", emergency, "noch-ein-passwort")["konto_schluessel"].encode() == new_key


def test_key_change_wrong_password_changes_nothing(two, cloud):
    mini, _, _ = two
    (mini.root / "data" / "lists.json").write_text("[]")
    assert mini.run("sync")[0] == 0
    head = cloud.zustand.kopf["sasha"]
    key = konto.konto_schluessel()
    rc, text = mini.run("devices", "remove", "laptop", answers=("y", "y", "y", "falsches-passwort", "", "y"))
    assert rc == 1 and "Wrong password. Nothing was changed" in text
    assert cloud.zustand.kopf["sasha"] == head and konto.konto_schluessel() == key


def test_key_change_declined(two, cloud):
    mini, _, _ = two
    key = konto.konto_schluessel()
    rc, text = mini.run("devices", "remove", "laptop", answers=("y", "y", "n"))
    assert rc == 0 and "The account key stays as it is." in text
    assert konto.konto_schluessel() == key
