"""The cloud folder (core/cloud_folder.py, memory/hub/cloud_folder.md): what
of ~/Zentrale/Cloud syncs, that it rides on the normal sync, that too-large
files and a vanished folder never break or empty anything, that the cloud
wins against a differing local version (kept aside), and the TUI opener."""
import gettext
import json
import os
import re

import pytest

import abgleich
import abgleich_apps
import abgleich_auswahl as auswahl
import abgleich_mitte
import ai_config
import cloud_folder
from test_abgleich_http import PW, cloud, zwei  # noqa: F401 — fixtures

from tui.ansichten import cloud_folder as tui_cloud
from tui.ansichten import translate


def _put(dev, inside, data=b"x"):
    p = dev.wurzel / "data" / "cloud" / inside
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _get(dev, inside):
    p = dev.wurzel / "data" / "cloud" / inside
    return p.read_bytes() if p.exists() else None


def _kept_aside(dev, inside):
    """All versions kept under konflikte/<time>/ for this path."""
    root = dev.ordner / "abgleich" / "konflikte"
    return [p.read_bytes() for p in root.glob("*/data/cloud/" + inside)] if root.exists() else []


# ── What syncs ──────────────────────────────────────────────────────────

def test_pattern_is_sync_only_and_belongs_to_the_cloud_folder_app():
    assert cloud_folder.PATTERN in auswahl.ABGLEICH
    assert cloud_folder.PATTERN not in auswahl.SICHERN          # never the plain-text backup
    assert abgleich_apps.tabelle()["cloud_folder"]["muster"] == [cloud_folder.PATTERN]
    assert abgleich_apps.app_von("data/cloud/a/b.pdf") == "cloud_folder"


def test_what_is_left_out():
    ok = ["data/cloud/a.txt", "data/cloud/Fotos/2026/img.jpg", "data/cloud/.hidden-note",
          "data/cloud/x/notes.json"]
    out = ["data/cloud/proj/.git/config", "data/cloud/web/node_modules/a/i.js",
           "data/cloud/film.mkv.part", "data/cloud/doc.odt~", "data/cloud/.~lock.doc.odt#",
           "data/cloud/.DS_Store", "data/cloud/../ai_config.json", "data/cloud/a//b",
           "data/cloud/p/__pycache__/m.pyc", "data/cloud/dl.crdownload"]
    assert all(auswahl.passt(r, auswahl.ABGLEICH) for r in ok)
    assert not any(auswahl.passt(r, auswahl.ABGLEICH) for r in out)


def test_selection_skips_heavy_dirs_and_symlinks(tmp_path):
    base = tmp_path / "data" / "cloud"
    (base / "web" / "node_modules" / "x").mkdir(parents=True)
    (base / "web" / "node_modules" / "x" / "i.js").write_text("1")
    (base / "web" / "index.html").write_text("<p>")
    (tmp_path / "secret").write_text("no")
    os.symlink(tmp_path / "secret", base / "link")
    assert auswahl.auswahl(str(tmp_path), auswahl.ABGLEICH) == ["data/cloud/web/index.html"]


def test_cloud_folder_files_are_never_merged_inside():
    import abgleich_zusammenfuehren as regeln
    assert regeln.art("data/cloud/notes.json") == "ganz"
    r = regeln.zusammenfuehren("data/cloud/a.md", b"a\n", b"a\nhere\n", b"a\ncloud\n")
    assert r.inhalt == b"a\ncloud\n" and r.konflikte                # no conflict markers


def test_encrypted_size_matches_fernet():
    from cryptography.fernet import Fernet
    f = Fernet(Fernet.generate_key())
    for n in (0, 15, 16, 17, 4097, 100_000):
        assert len(f.encrypt(b"x" * n)) == abgleich_mitte.encrypted_size(n)
    assert abgleich_mitte.fits_blob(18 * 2**20 - 100)
    assert not abgleich_mitte.fits_blob(18 * 2**20 + 1)


# ── Two devices over the cloud ──────────────────────────────────────────

def test_dropped_files_reach_the_other_device(zwei):
    laptop, pc = zwei
    _put(laptop, "Einkauf/rechnung.pdf", b"%PDF-1.7\x00\xff binary")
    _put(laptop, "idee.md", b"# Idee\n")
    laptop.abgleichen()
    pc.abgleichen()
    assert _get(pc, "Einkauf/rechnung.pdf") == b"%PDF-1.7\x00\xff binary"
    assert _get(pc, "idee.md") == b"# Idee\n"


def test_too_large_file_is_held_back_and_the_rest_syncs(zwei):
    laptop, pc = zwei
    _put(laptop, "klein.txt", b"ok")
    big = _put(laptop, "film.mkv", b"")
    os.truncate(big, 30 * 2**20)                 # sparse: never read, never sent
    b = laptop.abgleichen()
    assert [(h["path"], h["reason"]) for h in b.held_back] == [("data/cloud/film.mkv", "too_large")]
    assert any("film.mkv" in h and "MiB" in h for h in b.hinweise)
    laptop.ich()
    assert abgleich.zustand()["held_back"][0]["path"] == "data/cloud/film.mkv"
    assert not any("film.mkv" in h for h in laptop.abgleichen().hinweise)   # noted once
    pc.abgleichen()
    assert _get(pc, "klein.txt") == b"ok" and _get(pc, "film.mkv") is None
    assert big.stat().st_size == 30 * 2**20      # untouched here


def test_file_that_grows_too_large_is_neither_sent_nor_deleted(zwei):
    laptop, pc = zwei
    p = _put(laptop, "log.bin", b"small")
    laptop.abgleichen()
    pc.abgleichen()
    os.truncate(p, 25 * 2**20)
    laptop.abgleichen()
    pc.abgleichen()
    assert _get(pc, "log.bin") == b"small"        # not deleted in the cloud
    assert p.stat().st_size == 25 * 2**20         # and not replaced here
    p.write_bytes(b"small again, changed")
    laptop.abgleichen()
    pc.abgleichen()
    assert _get(pc, "log.bin") == b"small again, changed"


def test_both_changed_cloud_wins_local_kept_aside(zwei):
    laptop, pc = zwei
    _put(laptop, "plan.md", b"v1\n")
    laptop.abgleichen()
    pc.abgleichen()
    _put(pc, "plan.md", b"v2 from pc\n")
    pc.abgleichen()
    _put(laptop, "plan.md", b"v2 from laptop\n")
    b = laptop.abgleichen()
    assert _get(laptop, "plan.md") == b"v2 from pc\n"
    assert _kept_aside(laptop, "plan.md") == [b"v2 from laptop\n"]
    assert any("plan.md" in h for h in b.hinweise)


def test_later_attached_device_cloud_wins_local_kept_aside(zwei):
    laptop, pc = zwei
    _put(laptop, "liste.txt", b"from the cloud\n")
    laptop.abgleichen()
    _put(pc, "liste.txt", b"made here before joining\n")
    _put(pc, "nur-hier.txt", b"new\n")
    assert pc.abgleichen().art == "erstabgleich"
    assert _get(pc, "liste.txt") == b"from the cloud\n"
    assert _kept_aside(pc, "liste.txt") == [b"made here before joining\n"]
    laptop.abgleichen()
    assert _get(laptop, "liste.txt") == b"from the cloud\n"      # cloud never overwritten
    assert _get(laptop, "nur-hier.txt") == b"new\n"


def test_app_chosen_later_cloud_wins_local_kept_aside(zwei):
    laptop, pc = zwei
    _put(laptop, "a.txt", b"cloud\n")
    laptop.abgleichen()
    pc.ich()
    abgleich_apps.setzen({"fokus": True})          # cloud folder: not decided yet
    pc.abgleichen()
    assert _get(pc, "a.txt") is None
    _put(pc, "a.txt", b"local\n")
    pc.abgleichen()
    pc.ich()
    abgleich_apps.setzen({"cloud_folder": True})
    pc.abgleichen()
    assert _get(pc, "a.txt") == b"cloud\n"
    assert _kept_aside(pc, "a.txt") == [b"local\n"]


def test_vanished_folder_deletes_nothing(zwei):
    laptop, pc = zwei
    for n in ("a", "b", "c"):
        _put(laptop, n + ".txt", n.encode())
    laptop.abgleichen()
    pc.abgleichen()
    import shutil
    shutil.rmtree(laptop.wurzel / "data" / "cloud")
    b = laptop.abgleichen()
    assert {h["reason"] for h in b.held_back} == {"folder_missing"} and len(b.held_back) == 3
    assert any("cloud folder" in h.lower() or "cloud-ordner" in h.lower() for h in b.hinweise)
    pc.abgleichen()
    assert [_get(pc, n + ".txt") for n in "abc"] == [b"a", b"b", b"c"]
    # Files back → normal again; then deleting a single file is a real delete.
    for n in "abc":
        _put(laptop, n + ".txt", n.encode())
    assert laptop.abgleichen().held_back == []
    (laptop.wurzel / "data" / "cloud" / "a.txt").unlink()
    laptop.abgleichen()
    pc.abgleichen()
    assert _get(pc, "a.txt") is None                 # moved aside there, via the tombstone
    assert list((pc.ordner / "abgleich" / "beiseite").glob("*/data/cloud/a.txt"))


def test_emptying_a_small_folder_on_purpose_works(zwei):
    laptop, pc = zwei
    _put(laptop, "a.txt", b"a")
    _put(laptop, "b.txt", b"b")
    laptop.abgleichen()
    pc.abgleichen()
    for n in "ab":
        (laptop.wurzel / "data" / "cloud" / (n + ".txt")).unlink()
    assert laptop.abgleichen().held_back == []
    pc.abgleichen()
    assert _get(pc, "a.txt") is None and _get(pc, "b.txt") is None


def test_real_root_maps_to_the_home_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_config, "_overrides", {cloud_folder.SETTING: str(tmp_path / "Cloud")})
    real = auswahl._PROJEKT
    assert auswahl.create_outside(real, cloud_folder.PREFIX) is True
    assert (tmp_path / "Cloud").is_dir()
    assert auswahl.pfad(real, "data/cloud/x/y.txt") == str(tmp_path / "Cloud" / "x" / "y.txt")
    assert auswahl.create_outside(str(tmp_path / "other"), cloud_folder.PREFIX) is False


# ── TUI: the icon opens the folder ──────────────────────────────────────

def test_command_needs_a_graphical_session(monkeypatch):
    with pytest.raises(OSError):
        tui_cloud.command("/x", env={}, platform="linux")
    assert tui_cloud.command("/x", env={}, platform="darwin") == ["open", "/x"]
    monkeypatch.setattr(tui_cloud.shutil, "which", lambda n: "/usr/bin/" + n)
    assert tui_cloud.command("/x", env={"WAYLAND_DISPLAY": "wayland-1"}) == ["/usr/bin/xdg-open", "/x"]
    monkeypatch.setattr(tui_cloud.shutil, "which", lambda n: "/usr/bin/gio" if n == "gio" else None)
    assert tui_cloud.command("/x", env={"DISPLAY": ":0"}) == ["/usr/bin/gio", "open", "/x"]


def test_open_folder_creates_and_opens_detached(monkeypatch, tmp_path):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(tui_cloud.shutil, "which", lambda n: "/usr/bin/" + n)
    calls = []
    target = tmp_path / "Zentrale" / "Cloud"
    msg = tui_cloud.open_folder(api=lambda p: {"cloud_folder": str(target)},
                                popen=lambda cmd, **kw: calls.append((cmd, kw)))
    assert target.is_dir() and calls[0][0] == ["/usr/bin/xdg-open", str(target)]
    assert calls[0][1]["start_new_session"] is True and str(target.name) in msg

    def offline(_p):
        raise OSError("down")
    assert "Backend" in tui_cloud.open_folder(api=offline) or "backend" in tui_cloud.open_folder(api=offline)


def test_tui_table_compiled_and_german_default(monkeypatch):
    po = os.path.join(translate.LOCALE_DIR, "de", "LC_MESSAGES", "zentrale_tui.po")
    mo = po[:-3] + ".mo"
    pairs = dict(re.findall(r'^msgid "(.+)"\nmsgstr "(.*)"$', open(po, encoding="utf-8").read(), re.M))
    with open(mo, "rb") as f:
        table = gettext.GNUTranslations(f)
    for msgid, msgstr in pairs.items():
        assert table.gettext(msgid) == msgstr, "zentrale_tui.mo is stale — run msgfmt"
        assert set(re.findall(r"\{(\w+)\}", msgid)) == set(re.findall(r"\{(\w+)\}", msgstr))
    monkeypatch.delenv("ZENTRALE_LANG", raising=False)
    assert translate._("Cloud folder opened: {path}").startswith("Cloud-Ordner")


def test_wheel_has_the_cloud_icon():
    from tui import pixel
    from tui.ansichten import rad_wahl, startseite
    assert ("cloud", "cloud") in startseite.RAD_APPS and "cloud" in rad_wahl.OEFFNEN
    assert pixel.hat_symbol("cloud")
    _zeilen, schrift = pixel.symbol_zellen("cloud", 1.0, 0)
    assert "".join(c for _x, c, _f, _b in schrift) == "CLOUD"


def test_status_shows_the_folder_path():
    assert abgleich.zustand()["cloud_folder"] == cloud_folder.root()
    assert json.dumps(abgleich.zustand())                       # route stays JSON
