"""The read rule for versioned formats (core/formats.py,
memory/hub/building_kit_plan.md 2.2 rules 2 and 3, build step 5).

For every entry of formats.FORMATS two tests:
  test_newer_<key>     a file in a newer major → nothing written, one note
                       for `zentrale status`
  test_preserve_<key>  a file with fields this version does not know →
                       written by this version, the fields are still there

and a guard: a core module that defines a `…FORMAT… =` constant is either
mapped to its FORMATS keys here or exempt with a reason.
"""
import base64
import json
import os
import re

import pytest

import abgleich
import abgleich_mitte
import abgleich_schluessel as schluessel
import adapter
import adapter_geheim as geheim
import app_register
import calendar_colours as cc
import formats
import kalender_einstellung as ke
import kalender_ics
import kalender_sicherung as sich
import konto
import plug_store
import schematix_store
import schematix_versions
import wires
from test_abgleich import LISTE, Welt  # noqa: F401  (fixture building blocks)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# core module → the FORMATS keys it reads and writes.
MODULES = {
    "abgleich": ("cloud-index", "cloud-envelope"),
    "konto": ("account-file",),
    "adapter_geheim": ("adapter-secrets",),
    "adapter": ("adapter-connection",),
    "kalender_einstellung": ("calendar-app-setting",),
    "kalender_ics": ("calendar-side-file",),
    "calendar_colours": ("calendar-colours",),
    "account_ownership": ("account-ownership",),
    "plug_store": ("plug-wires",),
    "wires": ("node-wires",),
    "schematix_versions": ("node-versions",),
    "schematix_store": ("schematix-palette", "schematix-thing"),
    "app_register": ("app-register",),
}
EXEMPT = {
    "formats": "the registry itself",
    "werkzeug_erzeuger/anbindung": "hand-written descriptions, only read — no writer in core",
}


def _noted(what):
    return [n for n in formats.notes() if n["what"] == what]


# ── The registry and its guard ────────────────────────────────────────

def test_every_format_constant_in_core_is_registered():
    found = set()
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "core")):
        if "skill_vorlagen" in dirpath or "__pycache__" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            with open(p, encoding="utf-8") as fh:
                if re.search(r"^[A-Z_]*FORMAT[A-Z_]* = ", fh.read(), re.M):
                    found.add(os.path.relpath(p, os.path.join(ROOT, "core"))[:-3])
    assert found == set(MODULES) | set(EXEMPT), (
        "A core module writes a versioned format: add it to formats.FORMATS, to MODULES "
        "here and give it test_newer_/test_preserve_ (or EXEMPT with a reason).")
    assert {k for keys in MODULES.values() for k in keys} == set(formats.FORMATS)


def test_every_format_has_a_newer_and_a_preserve_test():
    for key in formats.FORMATS:
        name = key.replace("-", "_")
        assert "test_newer_" + name in globals(), key
        assert "test_preserve_" + name in globals(), key


def test_major_and_keep_unknown():
    assert formats.major(1) == 1 and formats.major("zentrale-geheim/2") == 2
    assert formats.major(None) is None and formats.major(True) is None
    assert formats.major("kaputt") is None
    assert formats.is_newer(2, "cloud-index") and not formats.is_newer(1, "cloud-index")
    assert not formats.is_newer(None, "cloud-index")
    assert formats.keep_unknown({"a": 1, "x": 2, "o": 3}, {"a": 9}, owned=("o",)) == {"x": 2, "a": 9}
    assert formats.keep_unknown(None, {"a": 1}) == {"a": 1}


def test_note_once_and_gone_after_a_good_read():
    with pytest.raises(formats.NewerFormat):
        formats.check({"format": 7}, "cloud-index")
    before = os.stat(os.environ["ZENTRALE_FORMAT_NOTES"]).st_mtime_ns
    with pytest.raises(formats.NewerFormat):
        formats.check({"format": 7}, "cloud-index")
    assert os.stat(os.environ["ZENTRALE_FORMAT_NOTES"]).st_mtime_ns == before   # no rewrite
    [n] = _noted("cloud-index")
    assert n["found"] == 7 and n["text"] == formats.newer_text("cloud-index")
    formats.check({"format": 1}, "cloud-index")
    assert not _noted("cloud-index")


def test_status_shows_the_note():
    import io
    from zentrale_cli import befehle
    from zentrale_cli.ausgabe import Terminal
    term = Terminal(aus=io.StringIO())
    befehle.format_lines(term)
    assert term.aus.getvalue() == ""
    formats.note_newer("calendar-colours", 2)
    befehle.format_lines(term)
    assert formats.newer_text("calendar-colours") in term.aus.getvalue()


# ── cloud-index: inhalt.enc in the Mitte ─────────────────────────────

def _mitte_umschreiben(welt, aendern):
    """A newer node rewrites inhalt.enc (straight into the throwaway Mitte)."""
    r = welt.rechner("neuer")
    r._als_ich()
    m = abgleich.mitte_oeffnen()
    _stand, lesen, _namen = m.holen()
    tresor = schluessel.Tresor(schluessel.laden())
    d = json.loads(tresor.auf(lesen(abgleich.INHALT)))
    aendern(d)
    assert m.senden(m.vorbereiten(
        {abgleich.INHALT: tresor.zu(json.dumps(d).encode("utf-8"))}, [], "newer node"))


def _zwei(welt):
    laptop, pc = welt.rechner("laptop"), welt.rechner("pc")
    laptop.schreiben("lists.json", LISTE)
    laptop.abgleichen()
    pc.abgleichen()
    return laptop, pc


@pytest.fixture
def welt(tmp_path, monkeypatch):
    return Welt(tmp_path, monkeypatch)


def test_newer_cloud_index(welt):
    _laptop, pc = _zwei(welt)
    _mitte_umschreiben(welt, lambda d: d.update(format=2))
    pc.schreiben("lists.json", LISTE + [{"id": "neu", "name": "Neu", "items": []}])
    with pytest.raises(abgleich_mitte.MitteFehler, match=re.escape(formats.newer_text("cloud-index"))):
        pc.abgleichen()
    assert welt.inhalt()["format"] == 2                     # nothing written
    assert pc.json("lists.json")[-1]["id"] == "neu"         # nothing local lost
    assert _noted("cloud-index")
    pc._als_ich()
    assert abgleich.mitte_pfade() is None                   # never misread as "empty"


def test_preserve_cloud_index(welt):
    _laptop, pc = _zwei(welt)

    def mehr(d):
        d["future"] = {"x": 1}
        d["dateien"]["data/lists.json"]["future"] = "keep"
    _mitte_umschreiben(welt, mehr)
    pc.schreiben("lists.json", LISTE + [{"id": "neu", "name": "Neu", "items": []}])
    pc.abgleichen()
    inhalt = welt.inhalt()
    assert inhalt["future"] == {"x": 1}
    assert inhalt["dateien"]["data/lists.json"]["future"] == "keep"
    assert not _noted("cloud-index")


def test_newer_cloud_data_stops_a_key_change():
    """The account key change (core/key_rotation.py) rewrites the whole Mitte:
    never over a newer table of contents, vault or inbox file."""
    from cryptography.fernet import Fernet
    import key_rotation
    alt_key, neu_key = Fernet.generate_key(), Fernet.generate_key()
    t = schluessel.Tresor(alt_key)
    for files, names in (
            ({abgleich.INHALT: {"format": 2, "dateien": {}}}, []),
            ({abgleich.INHALT: {"format": 1, "dateien": {}},
              "knoten/handy/x.enc": {"format": 2, "pfad": "data/lists.json"}}, ["knoten/handy/x.enc"])):
        blobs = {n: t.zu(json.dumps(d).encode()) for n, d in files.items()}
        with pytest.raises(key_rotation.RotationError, match="Nothing was changed"):
            key_rotation.reencrypt(alt_key, neu_key, blobs.get, [abgleich.INHALT, *names])
    vault = json.dumps({"format": "zentrale-geheim/2", "eintraege": {}}).encode()
    with pytest.raises(geheim.GeheimFehler):
        geheim.rekey(vault, alt_key, neu_key)


# ── cloud-envelope: knoten/<node>/*.enc ──────────────────────────────

def _umschlag(tresor, fmt):
    return tresor.zu(json.dumps({"format": fmt, "pfad": "data/lists.json",
                                 "inhalt": base64.b64encode(b"[]").decode()}).encode())


def test_newer_cloud_envelope(welt):
    tresor = schluessel.Tresor(schluessel.laden())
    name = f"knoten/handy/{tresor.name('data/lists.json')}.enc"
    bericht = abgleich.Bericht()
    fremd, vorschlaege = abgleich._eingang_lesen(
        tresor, [name], lambda n: _umschlag(tresor, 2), "laptop", bericht)
    assert fremd == {} and vorschlaege == {}
    assert len(bericht.hinweise) == 1 and "handy" in bericht.hinweise[0]
    assert _noted("cloud-envelope")


def test_preserve_cloud_envelope(welt):
    """Envelopes are written once by their node and never rewritten by a
    reader — preserving means: unknown fields do not make it unreadable."""
    tresor = schluessel.Tresor(schluessel.laden())
    blob = tresor.zu(json.dumps({"format": 1, "pfad": "data/lists.json", "future": True,
                                 "inhalt": base64.b64encode(b"[]").decode()}).encode())
    name = f"knoten/handy/{tresor.name('data/lists.json')}.enc"
    bericht = abgleich.Bericht()
    abgleich._eingang_lesen(tresor, [name], lambda n: blob, "laptop", bericht)
    assert not any("unlesbar" in h or "newer" in h for h in bericht.hinweise)
    assert not _noted("cloud-envelope")


# ── account-file: konto.json ─────────────────────────────────────────

def _konto(d):
    with open(konto.datei(), "w", encoding="utf-8") as f:
        json.dump(d, f)


KONTO = {"format": 2, "server": "http://x", "name": "sasha", "token": "t",
         "laeuft_ab": "2099", "knoten": "laptop", "konto_schluessel": "k"}


def test_newer_account_file():
    _konto(dict(KONTO, format=3))
    with pytest.raises(konto.KontoFehler, match=re.escape(formats.newer_text("account-file"))):
        konto.lesen()
    assert not konto.angemeldet()
    roh = open(konto.datei(), "rb").read()
    with pytest.raises(konto.KontoFehler):
        konto._speichern("http://x", "sasha", "t2", "2099", b"k", "laptop")
    assert open(konto.datei(), "rb").read() == roh
    assert _noted("account-file")


def test_preserve_account_file():
    _konto(dict(KONTO, future={"a": 1}))
    konto._speichern("http://x", "sasha", "t2", "2099", b"k", "laptop")
    d = konto.lesen()
    assert d["future"] == {"a": 1} and d["token"] == "t2"
    # Another account on this device: nothing of the old one stays.
    konto._speichern("http://x", "other", "t3", "2099", b"k", "laptop")
    assert "future" not in konto.lesen()


# ── adapter-secrets: data/adapter/geheim.enc ─────────────────────────

def test_newer_adapter_secrets():
    os.makedirs(os.path.dirname(geheim.datei()), exist_ok=True)
    with open(geheim.datei(), "w", encoding="utf-8") as f:
        json.dump({"format": "zentrale-geheim/2", "eintraege": {}}, f)
    roh = open(geheim.datei(), "rb").read()
    with pytest.raises(geheim.GeheimFehler, match=re.escape(formats.newer_text("adapter-secrets"))):
        geheim.setzen("ki/X", "wert")
    assert open(geheim.datei(), "rb").read() == roh
    assert _noted("adapter-secrets")


def test_preserve_adapter_secrets():
    geheim.setzen("ki/X", "eins")
    with open(geheim.datei(), encoding="utf-8") as f:
        d = json.load(f)
    d["future"] = [1]
    d["eintraege"]["ki/X"]["future"] = "keep"
    with open(geheim.datei(), "w", encoding="utf-8") as f:
        json.dump(d, f)
    geheim.setzen("ki/X", "zwei")
    geheim.setzen("ki/Y", "drei")
    with open(geheim.datei(), encoding="utf-8") as f:
        d = json.load(f)
    assert d["future"] == [1] and d["eintraege"]["ki/X"]["future"] == "keep"
    assert geheim.lesen("ki/X") == "zwei"


# ── adapter-connection: data/adapter/anschluesse/<id>.json ───────────

def _anschluss(d):
    p = os.path.join(adapter.ordner(), "anschluesse", d["id"] + ".json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return p


def test_newer_adapter_connection():
    a = adapter.neu("ki-schluessel", "ki-anbieter", "assistent")
    p = _anschluss(dict(a, format="zentrale-anschluss/2", art="etwas-neues"))
    assert adapter.alle() == {}
    assert _noted("adapter-connection")
    roh = open(p, "rb").read()
    with pytest.raises(adapter.AdapterFehler):
        adapter.speichern(a)
    assert open(p, "rb").read() == roh


def test_preserve_adapter_connection():
    a = adapter.neu("ki-schluessel", "ki-anbieter", "assistent")
    _anschluss(dict(a, future={"x": 1}))
    gelesen = adapter.lesen("ki-schluessel")          # extra field: still valid
    assert gelesen is not None
    adapter.speichern(dict(a, titel="Neu"))
    d = adapter.lesen("ki-schluessel")
    assert d["future"] == {"x": 1} and d["titel"] == "Neu"
    assert not _noted("adapter-connection")


# ── calendar-app-setting: data/adapter/anschluesse/kalender-*.json ───

def test_newer_calendar_app_setting():
    e = ke.neu(ke.HAUPT, "zencloud")
    p = _anschluss(dict(e, format="zentrale-kalender-app/2", quelle="etwas-neues"))
    assert ke.instanzen() == {}
    assert adapter.alle() == {}                         # never taken for a connection
    assert _noted("calendar-app-setting")
    roh = open(p, "rb").read()
    with pytest.raises(ke.EinstellungFehler):
        ke.schreiben(ke.HAUPT, "lokal")
    assert open(p, "rb").read() == roh


def test_newer_calendar_setting_never_switches_google_on():
    """An old device skipping a newer kalender-haupt must not fall back to the
    default source google: a Google run against the local folder can delete
    Google events (memory/open/calendar_cloud_sync_gaps.md item 1)."""
    e = ke.neu(ke.HAUPT, "zencloud")
    _anschluss(dict(e, format="zentrale-kalender-app/2"))
    assert ke.quelle() == ke.PAUSED and ke.PAUSED not in ke.QUELLEN
    assert not adapter.kalender_google_an() and not adapter.kalender_mit_vertrag()
    assert ke.mit_quelle("google") == []


def test_preserve_calendar_app_setting():
    e = ke.neu(ke.HAUPT, "zencloud")
    e["geaendert"] = {"am": "x", "auf": "y", "von": "google", "future": 1}
    _anschluss(dict(e, future={"x": 1}))
    assert ke.quelle() == "zencloud"                    # extra fields: still valid
    ke.schreiben(ke.HAUPT, "lokal")
    d = ke.instanz()
    assert d["quelle"] == "lokal" and d["future"] == {"x": 1}
    assert d["geaendert"]["future"] == 1 and d["geaendert"]["von"] == "zencloud"
    assert not _noted("calendar-app-setting")


# ── account-ownership: GET/PUT /v1/besitz (core/account_ownership.py) ─

def _ownership_cloud(monkeypatch, blob):
    import account_ownership as ao
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    sent = []

    class C:
        def get(self, pfad):
            return {"besitz": blob(key) if callable(blob) else blob}

        def put(self, pfad, daten):
            sent.append(daten["besitz"])
            return {}
    monkeypatch.setattr(konto, "angemeldet", lambda: True)
    monkeypatch.setattr(konto, "konto_schluessel", lambda: key)
    monkeypatch.setattr(konto, "client", lambda *a: C())
    return ao, key, sent


def test_newer_account_ownership(monkeypatch):
    from cryptography.fernet import Fernet

    def blob(key):
        return Fernet(key).encrypt(json.dumps({"@type": "ItemList", "format": "zentrale-ownership/2",
                                               "itemListElement": []}).encode()).decode()
    ao, _key, sent = _ownership_cloud(monkeypatch, blob)
    with pytest.raises(ao.OwnershipError):
        ao.owned()
    with pytest.raises(ao.OwnershipError):
        ao.mark(["zentrale://shop/apps/cloud"])
    assert sent == [] and _noted("account-ownership")


def test_preserve_account_ownership(monkeypatch):
    import account_ownership as ao
    old = {"zentrale://shop/apps/cloud": "2026-10-30T10:00:00+01:00"}

    def blob(key):
        doc = json.loads(ao.Fernet(key).decrypt(ao.encode(old, key).encode()))
        doc["future"] = {"x": 1}
        return ao.Fernet(key).encrypt(json.dumps(doc).encode()).decode()
    ao, key, sent = _ownership_cloud(monkeypatch, blob)
    have = ao.mark(["zentrale://shop/apps/cloud", "zentrale://shop/apps/cloud_folder"])
    assert have["zentrale://shop/apps/cloud"] == old["zentrale://shop/apps/cloud"]   # first date stays
    doc, owned = ao.decode(sent[-1], key)
    assert doc["future"] == {"x": 1} and set(owned) == set(have)
    assert not _noted("account-ownership")


# ── calendar-side-file: data/kalender_neben.json ─────────────────────

def _sp(tmp_path):
    from datetime import date
    kalender_ics.cache_leeren()
    return kalender_ics.IcsSpeicher(tmp_path / "kalender", tmp_path / "kalender_neben.json",
                                    tmp_path / "kalender_verlauf", tmp_path / "kalender_snapshots",
                                    anker=date(2026, 6, 3))


def _kalender():
    return {"version": 1, "layers": {"termine": {"label": "Termine", "entries": {
        "2026-06-04": [{"time": "10:00", "label": "Zahnarzt"}]}, "routines": []}}}


def _neben_aendern(tmp_path, **felder):
    p = tmp_path / "kalender_neben.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d.update(felder)
    p.write_text(json.dumps(d), encoding="utf-8")
    kalender_ics.cache_leeren()


def test_newer_calendar_side_file(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(_kalender(), erlaube_massenloeschung=True)
    _neben_aendern(tmp_path, format=2)
    data = sp.laden()                                   # still shown
    assert _noted("calendar-side-file")
    roh = (tmp_path / "kalender_neben.json").read_bytes()
    data["neu_oben"] = 1
    with pytest.raises(sich.KalenderGesperrt, match=re.escape(formats.newer_text("calendar-side-file"))):
        sp.speichern(data)
    assert (tmp_path / "kalender_neben.json").read_bytes() == roh


def test_preserve_calendar_side_file(tmp_path):
    sp = _sp(tmp_path)
    sp.speichern(_kalender(), erlaube_massenloeschung=True)
    _neben_aendern(tmp_path, future={"x": 1})
    data = sp.laden()
    data["neu_oben"] = 1                                # the side file is rewritten
    assert sp.speichern(data)["neben"]
    d = json.loads((tmp_path / "kalender_neben.json").read_text(encoding="utf-8"))
    assert d["future"] == {"x": 1} and d["oben"]["neu_oben"] == 1
    assert not _noted("calendar-side-file")


# ── calendar-colours: data/calendar_colours.json ─────────────────────

def test_newer_calendar_colours(tmp_path):
    p = tmp_path / "calendar_colours.json"
    newer = json.dumps({"format": "zentrale-calendar-colours/2", "slots": {"a": 1}}).encode()
    p.write_bytes(newer)
    assert cc.write_table(p, {"a": 2}) is False
    assert p.read_bytes() == newer
    local = cc.table_text({"b": 3}).encode()
    assert cc.merge(None, local, newer) == newer        # the cloud is never overwritten
    assert _noted("calendar-colours")


def test_preserve_calendar_colours(tmp_path):
    p = tmp_path / "calendar_colours.json"
    p.write_text(json.dumps({"format": cc.FORMAT, "slots": {"a": 1}, "future": [1]}))
    assert cc.write_table(p, {"a": 1, "b": 2}) is True
    d = json.loads(p.read_text())
    assert d["future"] == [1] and d["slots"] == {"a": 1, "b": 2}
    m = cc.merge(None, cc.table_text({"c": 4}).encode(), p.read_bytes())
    assert json.loads(m)["future"] == [1]
    # Without extra fields the bytes are what they always were.
    assert cc.table_text({"a": 1}) == json.dumps({"format": cc.FORMAT, "slots": {"a": 1}},
                                                 indent=1, ensure_ascii=False) + "\n"


# ── plug-wires: data/adapter/plugs/<app>.json (core/plug_store.py) ──────

def _plug(state="live", **more):
    return dict({"id": "plug/assistent/model", "from": "zentrale://adapter/port/model",
                 "to": "zentrale://assistent/port/model", "type": "model",
                 "owner": "app:assistent", "state": state}, **more)


def _plug_file(doc):
    p = plug_store.instance_file("assistent")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return p


def test_newer_plug_wires():
    p = _plug_file({"format": "zentrale-plugs/2", "wires": [_plug()]})
    roh = open(p, "rb").read()
    assert plug_store.instance_wires() == []            # never interpreted
    assert _noted("plug-wires")
    assert wires._write_plugs(p, {"plug/assistent/model": _plug("off")})   # a problem, not written
    assert open(p, "rb").read() == roh


def test_preserve_plug_wires():
    other = _plug(id="plug/assistent/files", type="files", seen="x")
    p = _plug_file({"format": plug_store.PLUGS_FORMAT, "wires": [other], "future": {"x": 1}})
    assert wires._write_plugs(p, {"plug/assistent/model": _plug()}) is None
    d = json.loads(open(p, encoding="utf-8").read())
    assert d["future"] == {"x": 1}
    assert [w["id"] for w in d["wires"]] == ["plug/assistent/files", "plug/assistent/model"]
    assert d["wires"][0]["seen"] == "x"                 # an untouched wire keeps its fields
    assert not _noted("plug-wires")


# ── node-wires: `wires` in a node description (core/wires.py) ─────────

def _sync_wire(**more):
    return dict({"id": "sync/minipc/fokus", "from": "zentrale://cloud/port/sync",
                 "to": "zentrale://fokus/port/data", "type": "sync", "owner": "node:minipc",
                 "state": "off"}, **more)


def test_newer_node_wires():
    d = {"name": "minipc", "wires": {"format": "zentrale-node-wires/2", "wires": [_sync_wire()]}}
    assert wires.wires_of_description(d) == []          # read-only: nothing guessed
    assert _noted("node-wires")


def test_preserve_node_wires():
    """The section is written whole by its own node only; a reader keeps the
    fields a newer node put on a wire (Schematix shows what it gets)."""
    d = {"name": "minipc", "wires": {"format": wires.NODE_WIRES_FORMAT, "future": 1,
                                     "wires": [_sync_wire(seen="2026-10-30T09:15:00Z", future={"a": 1})]}}
    got = wires.wires_of_description(d)
    assert got[0]["future"] == {"a": 1} and got[0]["seen"]
    assert not _noted("node-wires")


# ── node-versions: `versions` in a node description (Schematix, step 13) ──

def test_newer_node_versions():
    d = {"name": "minipc", "versions": {"format": "zentrale-node-versions/2", "zentrale": "99"}}
    assert schematix_versions.of_description(d) is None       # read-only: nothing guessed
    assert _noted("node-versions")


def test_preserve_node_versions():
    """Written whole by its own node only; a reader keeps what a newer node added."""
    d = {"name": "minipc", "versions": {"format": schematix_versions.VERSIONS_FORMAT, "zentrale": "44",
                                        "future": {"a": 1}}}
    assert schematix_versions.of_description(d)["future"] == {"a": 1}
    assert not _noted("node-versions")


# ── schematix-palette: data/schematix/palette.json (core/schematix_store.py) ──

def _palette_file(d):
    path = os.path.join(schematix_store.folder(), "palette.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return path


def test_newer_schematix_palette():
    p = _palette_file({"format": "zentrale-schematix-palette/2", "roles": {"ink": "#000000"}})
    before = open(p, "rb").read()
    assert schematix_store.palette()["ink"] == schematix_store.default_palette()["ink"]
    with pytest.raises(formats.NewerFormat):
        schematix_store.set_role("ink", "#111111")
    assert open(p, "rb").read() == before and _noted("schematix-palette")


def test_preserve_schematix_palette():
    p = _palette_file({"format": schematix_store.PALETTE_FORMAT, "roles": {"ink": "#123456"},
                       "future": [1]})
    schematix_store.set_role("dim", "#654321")
    d = json.load(open(p, encoding="utf-8"))
    assert d["future"] == [1] and d["roles"] == {"ink": "#123456", "dim": "#654321"}
    assert not _noted("schematix-palette")


# ── schematix-thing: data/schematix/things/<id>.json (core/schematix_store.py) ──

def _thing_file(d):
    path = os.path.join(schematix_store.folder(), "things", d["id"] + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return path


def test_newer_schematix_thing():
    p = _thing_file({"format": "zentrale-thing/2", "id": "router", "kind": "router"})
    before = open(p, "rb").read()
    assert schematix_store.things() == []                         # not interpreted
    with pytest.raises(formats.NewerFormat):
        schematix_store.write_thing({"id": "router", "kind": "router"})
    assert open(p, "rb").read() == before and _noted("schematix-thing")


def test_preserve_schematix_thing():
    p = _thing_file({"format": schematix_store.THING_FORMAT, "id": "router", "kind": "router",
                     "future": {"a": 1}})
    schematix_store.write_thing({"id": "router", "kind": "router", "title": "Flint 2"})
    d = json.load(open(p, encoding="utf-8"))
    assert d["future"] == {"a": 1} and d["title"] == "Flint 2"
    assert not _noted("schematix-thing")


# ── app-register: data/hub/apps-<node>.json (core/app_register.py) ────

def _register_file(d):
    path = app_register.datei()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f)
    return path


_APP = {"name": "budget", "quelle": "zentrale://shop/apps/budget", "ordner": "/x/budgeter",
        "ansichten": ["browser"]}


def test_newer_app_register():
    p = _register_file({"format": 3, "apps": [_APP]})
    before = open(p, "rb").read()
    assert app_register.alle() == []                              # not interpreted
    with pytest.raises(formats.NewerFormat):
        app_register.schreiben([_APP])
    assert open(p, "rb").read() == before and _noted("app-register")


def test_preserve_app_register():
    p = _register_file({"format": app_register.FORMAT, "future": {"a": 1},
                        "apps": [dict(_APP, later="x", source={"kind": "git", "ref": "", "branch": "main"})]})
    app_register.schreiben(app_register.alle())
    d = json.load(open(p, encoding="utf-8"))
    assert d["future"] == {"a": 1}
    assert d["apps"][0]["later"] == "x" and d["apps"][0]["source"]["branch"] == "main"
    assert not _noted("app-register")
