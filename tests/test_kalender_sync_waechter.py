"""
Der Löschwächter vor dem Google-Sync (scripts/kalender_sync.py).

Sasha, 07.10.2026: „bitte bitte lösch nix aus google calendar aus versehen".
Fehlen lokal seit dem letzten Sync mehr Termine als die Löschsperre erlaubt,
darf vdirsyncer gar nicht erst laufen — sonst trüge es die Lücke als
Löschung zu Google.
"""
import importlib.util
import os

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "kalender_sync", os.path.join(os.path.dirname(__file__), "..", "scripts", "kalender_sync.py"))
ks = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ks)


@pytest.fixture
def vdir(tmp_path, monkeypatch):
    monkeypatch.setattr(ks, "STAND", str(tmp_path / "stand.json"))
    v = tmp_path / "kalender" / "termine"
    v.mkdir(parents=True)
    for i in range(10):
        (v / ("t%d.ics" % i)).write_text(_ics("t%d@zentrale" % i))
    return tmp_path / "kalender"


def _ics(uid):
    return ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:%s\r\nSUMMARY:x\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n" % uid)


def test_erster_lauf_kennt_keine_fehlenden(vdir):
    assert ks._fehlende(vdir) == []


def test_nach_dem_merken_fehlt_was_geloescht_wurde(vdir):
    ks._stand_merken(vdir)
    for i in range(3):
        (vdir / "termine" / ("t%d.ics" % i)).unlink()
    assert ks._fehlende(vdir) == ["termine/t0.ics", "termine/t1.ics", "termine/t2.ics"]


def test_neue_termine_zaehlen_nicht_als_fehlend(vdir):
    ks._stand_merken(vdir)
    (vdir / "termine" / "neu.ics").write_text("x")
    assert ks._fehlende(vdir) == []


# ── 25.10.2026: Fehlalarm nach gewolltem Verschieben und bestätigter Löschung ──
# Vorfall 24./25.10.: „6 Termine fehlen“ alle 3 min über 5,5 h. Zwei davon
# lagen nur in uncommitted/ (geht nie zu Google) und waren nach termine/
# gewandert; die übrigen vier waren gewollt gelöscht und mit
# ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1 bestätigt — ein Konflikt an einem
# anderen Termin ließ vdirsyncer mit 1 enden, die eigene Liste blieb alt.


def test_nur_termine_zaehlt(vdir):
    (vdir / "uncommitted").mkdir()
    (vdir / "rhythmus").mkdir()
    (vdir / "uncommitted" / "u.ics").write_text(_ics("u@zentrale"))
    (vdir / "rhythmus" / "r.ics").write_text(_ics("r@zentrale"))
    ks._stand_merken(vdir)
    (vdir / "uncommitted" / "u.ics").unlink()
    (vdir / "rhythmus" / "r.ics").unlink()
    assert ks._fehlende(vdir) == []


def test_alte_liste_mit_uncommitted_zaehlt_nur_termine(vdir):
    import json
    with open(ks.STAND, "w") as f:
        json.dump({"dateien": ["termine/t0.ics", "uncommitted/weg.ics"]}, f)
    assert ks._fehlende(vdir) == []
    (vdir / "termine" / "t0.ics").unlink()
    assert ks._fehlende(vdir) == ["termine/t0.ics"]


def test_verschobene_uid_fehlt_nicht(vdir):
    ks._stand_merken(vdir)
    (vdir / "uncommitted").mkdir()
    (vdir / "termine" / "t0.ics").rename(vdir / "uncommitted" / "t0.ics")
    (vdir / "termine" / "t1.ics").rename(vdir / "termine" / "anders.ics")
    assert ks._fehlende(vdir) == []


def test_liste_ohne_uids_nimmt_den_dateinamen(vdir):
    import json
    with open(ks.STAND, "w") as f:
        json.dump({"dateien": ["termine/t0@zentrale.ics"]}, f)
    (vdir / "uncommitted").mkdir()
    (vdir / "uncommitted" / "x.ics").write_text(_ics("t0@zentrale"))
    assert ks._fehlende(vdir) == []


def test_stand_merkt_nur_termine_mit_uid(vdir):
    import json
    (vdir / "uncommitted").mkdir()
    (vdir / "uncommitted" / "u.ics").write_text(_ics("u@zentrale"))
    ks._stand_merken(vdir)
    d = json.load(open(ks.STAND))
    assert all(n.startswith("termine/") for n in d["dateien"])
    assert d["uids"]["termine/t3.ics"] == "t3@zentrale"


def test_uid_gefaltet_und_mit_parameter(tmp_path):
    p = tmp_path / "x.ics"
    p.write_text("BEGIN:VEVENT\r\nUID;X-A=1:abc\r\n def@zentrale\r\nEND:VEVENT\r\n")
    assert ks._uid_aus(p) == "abcdef@zentrale"


# ── Basis = vdirsyncer-Status (Stand nach dem letzten Abgleich) ─────────

def _status_anlegen(tmp_path, vdir, monkeypatch, zeilen, seite="a"):
    """Konfiguration + Status wie vdirsyncer sie hätte (ohne Zugangsdaten)."""
    import sqlite3
    status = tmp_path / "status"
    (status / "zentrale").mkdir(parents=True)
    lokal, fern = ("zentrale_lokal", "google") if seite == "a" else ("google", "zentrale_lokal")
    samml = '[["termine", "termine", "ich@x"]]' if seite == "a" else '[["termine", "ich@x", "termine"]]'
    cfg = tmp_path / "config"
    cfg.write_text(f"""[general]
status_path = "{status}/"

[pair zentrale]
a = "{lokal}"
b = "{fern}"
collections = {samml}
conflict_resolution = null

[storage zentrale_lokal]
type = "filesystem"
path = "{vdir}/"
fileext = ".ics"

[storage google]
type = "google_calendar"
client_secret = "GEHEIM-NIE-AUSGEBEN"
""")
    monkeypatch.setenv("ZENTRALE_VDIRSYNCER_CONFIG", str(cfg))
    db = sqlite3.connect(status / "zentrale" / "termine.items")
    db.execute('CREATE TABLE status ("ident" TEXT PRIMARY KEY NOT NULL, "href_a" TEXT, '
               '"href_b" TEXT, "hash_a" TEXT NOT NULL, "hash_b" TEXT NOT NULL, '
               '"etag_a" TEXT, "etag_b" TEXT)')
    for ident, href in zeilen:
        a, b = (href, "/caldav/" + href) if seite == "a" else ("/caldav/" + href, href)
        db.execute("INSERT INTO status VALUES (?, ?, ?, 'h', 'h', 'e', 'e')", (ident, a, b))
    db.commit()
    db.close()
    return db


def test_status_ist_die_basis(vdir, tmp_path, monkeypatch, capsys):
    _status_anlegen(tmp_path, vdir, monkeypatch,
                    [("t%d@zentrale" % i, "t%d.ics" % i) for i in range(10)])
    assert ks._basis(vdir)[1] == "vdirsyncer-Status"
    (vdir / "termine" / "t0.ics").unlink()
    assert ks._fehlende(vdir) == ["termine/t0.ics"]
    assert "GEHEIM" not in capsys.readouterr().out


def test_bestaetigte_loeschung_zaehlt_nicht_wieder(vdir, tmp_path, monkeypatch):
    """Die eigene Liste ist noch alt (Lauf endete wegen eines Konflikts mit
    1), der Status kennt die gelöschten Termine nicht mehr → nichts fehlt."""
    ks._stand_merken(vdir)
    for i in range(6):
        (vdir / "termine" / ("t%d.ics" % i)).unlink()
    assert len(ks._fehlende(vdir)) == 6            # ohne Status: eigene Liste
    _status_anlegen(tmp_path, vdir, monkeypatch,
                    [("t%d@zentrale" % i, "t%d.ics" % i) for i in range(6, 10)])
    assert ks._fehlende(vdir) == []


def test_status_mit_lokaler_seite_b(vdir, tmp_path, monkeypatch):
    _status_anlegen(tmp_path, vdir, monkeypatch, [("t1@zentrale", "t1.ics")], seite="b")
    (vdir / "termine" / "t1.ics").unlink()
    assert ks._fehlende(vdir) == ["termine/t1.ics"]


def test_status_unlesbar_faellt_auf_die_liste_zurueck(vdir, tmp_path, monkeypatch, capsys):
    _status_anlegen(tmp_path, vdir, monkeypatch, [])
    (tmp_path / "status" / "zentrale" / "termine.items").write_bytes(b"kein sqlite")
    ks._stand_merken(vdir)
    (vdir / "termine" / "t2.ics").unlink()
    assert ks._fehlende(vdir) == ["termine/t2.ics"]
    assert "eigenen Liste" in capsys.readouterr().out


def test_vorfall_vom_24_10(vdir, tmp_path, monkeypatch):
    """Nachgestellt: 4 gelöscht (bestätigt, aus dem Status), 2 von
    uncommitted nach termine gewandert. Die alte Liste kannte alle 6."""
    import json
    (vdir / "uncommitted").mkdir()
    for n in ("u1", "u2"):
        (vdir / "uncommitted" / (n + ".ics")).write_text(_ics(n + "@zentrale"))
    alt = ["termine/t%d.ics" % i for i in range(10)] + ["uncommitted/u1.ics", "uncommitted/u2.ics"]
    with open(ks.STAND, "w") as f:
        json.dump({"dateien": alt}, f)
    for i in range(4):
        (vdir / "termine" / ("t%d.ics" % i)).unlink()
    for n in ("u1", "u2"):
        (vdir / "uncommitted" / (n + ".ics")).rename(vdir / "termine" / (n + ".ics"))
    _status_anlegen(tmp_path, vdir, monkeypatch,
                    [("t%d@zentrale" % i, "t%d.ics" % i) for i in range(4, 10)])
    assert ks._fehlende(vdir) == []
    # Die Sperre selbst bleibt: verschwinden jetzt 6 unerklärt, zählen sie.
    for i in range(4, 10):
        (vdir / "termine" / ("t%d.ics" % i)).unlink()
    assert len(ks._fehlende(vdir)) == 6
