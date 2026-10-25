"""
Konfliktlöser für vdirsyncer (scripts/kalender_konflikt.py) und sein Eintrag
in die vom Adapter erzeugte Konfiguration (core/adapter_vdirsyncer.bauen).

Anlass 24.10.2026: „One item changed on both sides“ an einem ZENTRALE-Termin,
der kurz nach dem Hochladen lokal noch einmal geändert wurde. Lokal gewinnt
nur, wenn es ein ZENTRALE-Termin ist UND die lokale Fassung echt neuer ist —
sonst bleibt der Konflikt ein Fehler wie bisher. Kein Google-Zugriff.
"""
import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "kalender_konflikt", os.path.join(os.path.dirname(__file__), "..", "scripts", "kalender_konflikt.py"))
kk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(kk)


def _ics(uid, geaendert, titel="x"):
    return ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTAMP:20261024T190000Z\r\n"
            "LAST-MODIFIED:%s\r\nSUMMARY:%s\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
            % (uid, geaendert, titel))


def test_lokal_neuer_gewinnt():
    assert kk.entscheiden(_ics("a@zentrale", "20261024T190130Z"),
                          _ics("a@zentrale", "20261024T190036Z")) is None


def test_google_neuer_oder_gleich_bleibt_konflikt():
    assert kk.entscheiden(_ics("a@zentrale", "20261024T190000Z"),
                          _ics("a@zentrale", "20261024T190036Z"))
    assert kk.entscheiden(_ics("a@zentrale", "20261024T190036Z"),
                          _ics("a@zentrale", "20261024T190036Z"))


def test_fremde_termine_bleiben_konflikt():
    assert kk.entscheiden(_ics("abc@google.com", "20261025T000000Z"),
                          _ics("abc@google.com", "20261024T000000Z")) == "kein ZENTRALE-Termin"


def test_unklare_zeit_oder_uid_bleibt_konflikt():
    assert kk.entscheiden(_ics("a@zentrale", "20261025T000000"),          # ohne Z
                          _ics("a@zentrale", "20261024T000000Z"))
    assert kk.entscheiden(_ics("a@zentrale", "20261025T000000Z"),
                          _ics("b@zentrale", "20261024T000000Z"))


def test_main_schreibt_beide_gleich(tmp_path):
    a, b = tmp_path / "zentrale_lokal", tmp_path / "google"
    a.write_text(_ics("a@zentrale", "20261024T190130Z", "neu"))
    b.write_text(_ics("a@zentrale", "20261024T190036Z", "alt"))
    assert kk.main(["--lokal", "a", str(a), str(b)]) == 0
    assert a.read_text() == b.read_text() and "neu" in b.read_text()


def test_main_lokale_seite_b(tmp_path):
    a, b = tmp_path / "google", tmp_path / "zentrale_lokal"
    a.write_text(_ics("a@zentrale", "20261024T190036Z", "alt"))
    b.write_text(_ics("a@zentrale", "20261024T190130Z", "neu"))
    assert kk.main(["--lokal", "b", str(a), str(b)]) == 0
    assert "neu" in a.read_text()


def test_main_laesst_alles_wie_es_war(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_text(_ics("a@zentrale", "20261024T180000Z", "lokal"))
    b.write_text(_ics("a@zentrale", "20261024T190036Z", "handy"))
    assert kk.main(["--lokal", "a", str(a), str(b)]) == 1
    assert "handy" in b.read_text() and "lokal" in a.read_text()


# ── Eintrag in die erzeugte Konfiguration ───────────────────────────────

def _anschluss(regel="fehlt"):
    paar = [["a", "zentrale_lokal"], ["b", "google"],
            ["collections", [["termine", "termine", "ich@x"]]]]
    if regel != "fehlt":
        paar.append(["conflict_resolution", regel])
    return {"id": "google-kalender", "einstellungen": {"vdirsyncer": {"abschnitte": [
        {"kopf": "general", "werte": [["status_path", "~/.local/share/vdirsyncer/status/"]]},
        {"kopf": "pair zentrale", "werte": paar},
        {"kopf": "pair google_probe", "werte": [["a", "kopie"], ["b", "google"],
                                                ["conflict_resolution", "b wins"]]},
        {"kopf": "storage zentrale_lokal", "werte": [
            ["type", "filesystem"], ["path", {"$ort": "kalender", "rest": "."}],
            ["fileext", ".ics"]]},
        {"kopf": "storage kopie", "werte": [["type", "filesystem"], ["path", "~/kopie/"]]},
        {"kopf": "storage google", "werte": [["type", "google_calendar"]]},
    ]}}}


def _paar_regel(cfg_text, paar):
    import adapter_vdirsyncer as vc
    return dict(dict(vc.lesen_config(cfg_text))["pair " + paar]).get("conflict_resolution")


def test_bauen_traegt_den_loeser_ein(tmp_path):
    import adapter_vdirsyncer as vc
    for regel in ("fehlt", None):
        cfg = vc.bauen(_anschluss(regel), tmp_path / "kalender")
        text = open(cfg, encoding="utf-8").read()
        r = _paar_regel(text, "zentrale")
        assert r[0] == "command" and r[-3:] == [vc.KONFLIKT_SKRIPT, "--lokal", "a"]
        assert os.path.isfile(r[-3])
        assert _paar_regel(text, "google_probe") == "b wins"     # fremdes Paar unberührt


def test_bauen_laesst_eine_eigene_regel_stehen(tmp_path):
    import adapter_vdirsyncer as vc
    cfg = vc.bauen(_anschluss("b wins"), tmp_path / "kalender")
    assert _paar_regel(open(cfg, encoding="utf-8").read(), "zentrale") == "b wins"


def test_kalender_paare_unveraendert():
    import adapter_vdirsyncer as vc
    assert vc.kalender_paare(_anschluss()) == ["zentrale"]
