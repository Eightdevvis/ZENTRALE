"""
PC-Status: eine Quelle für „ist der andere Knoten da?" (core/pc_status.py).

Sasha, 02.10.2026: statt dass jeder (Boot-Abgleich, zentrale-pull, Claude)
für sich minutenlang nach dem PC sucht, soll einfach bekannt sein, ob er
verbunden ist. Geprüft wird hier ohne Netz — TCP und Finder sind ersetzt.
"""
import json
import os

import pytest

import pc_status as ps


@pytest.fixture
def umg(tmp_path, monkeypatch):
    cfg = tmp_path / "ssh_config"
    cfg.write_text("Host andere\n    HostName 1.1.1.1\n"
                   "# >>> find-pc >>>\nHost pc\n    HostName 10.0.0.7\n"
                   "    User sasha\n# <<< find-pc <<<\n")
    monkeypatch.setattr(ps, "ip_aus_ssh_config",
                        lambda alias, pfad=None, _o=ps.ip_aus_ssh_config: _o(alias, str(cfg)))
    monkeypatch.setattr(ps, "peer_name", lambda: "pc")
    monkeypatch.setattr(ps, "netz_kennung", lambda: "wlan0:1")
    rufe = {"tcp": [], "finder": 0}
    zustand = {"offen": set()}

    def tcp(ip, port=22, timeout=1.0):
        rufe["tcp"].append(ip)
        return ip in zustand["offen"]

    def finder(peer, timeout=6):
        rufe["finder"] += 1
        return False

    monkeypatch.setattr(ps, "tcp_offen", tcp)
    monkeypatch.setattr(ps, "_finder", finder)
    return {"pfad": str(tmp_path / "peer.json"), "rufe": rufe, "zustand": zustand}


def test_liest_die_adresse_aus_dem_find_pc_block(umg):
    assert ps.ip_aus_ssh_config("pc") == "10.0.0.7"


def test_verbunden_wenn_ssh_port_antwortet(umg):
    umg["zustand"]["offen"].add("10.0.0.7")
    d = ps.pruefen(pfad=umg["pfad"])
    assert d["verbunden"] is True
    assert umg["rufe"]["finder"] == 0, "kein teurer Suchlauf, wenn die Adresse antwortet"
    assert json.load(open(umg["pfad"]))["verbunden"] is True


def test_getrennt_sucht_nur_selten(umg):
    d = ps.pruefen(pfad=umg["pfad"])
    assert d["verbunden"] is False and umg["rufe"]["finder"] == 1
    ps.pruefen(pfad=umg["pfad"])
    ps.pruefen(pfad=umg["pfad"])
    assert umg["rufe"]["finder"] == 1, "der Finder läuft nicht bei jeder Prüfung"


def test_netzwechsel_erlaubt_neue_suche(umg, monkeypatch):
    ps.pruefen(pfad=umg["pfad"])
    monkeypatch.setattr(ps, "netz_kennung", lambda: "wlan0:2")
    ps.pruefen(pfad=umg["pfad"])
    assert umg["rufe"]["finder"] == 2


def test_ohne_netz_sofort_getrennt(umg, monkeypatch):
    monkeypatch.setattr(ps, "netz_kennung", lambda: None)
    d = ps.pruefen(pfad=umg["pfad"])
    assert d["verbunden"] is False and d["grund"] == "kein netz"
    assert umg["rufe"]["tcp"] == [] and umg["rufe"]["finder"] == 0


def test_seit_bleibt_stehen_solange_sich_nichts_aendert(umg):
    a = ps.pruefen(jetzt=1000.0, pfad=umg["pfad"])
    b = ps.pruefen(jetzt=1010.0, pfad=umg["pfad"])
    assert a["seit"] == b["seit"] == 1000.0
    umg["zustand"]["offen"].add("10.0.0.7")
    c = ps.pruefen(jetzt=1020.0, pfad=umg["pfad"])
    assert c["verbunden"] and c["seit"] == 1020.0


def test_aktuell_nimmt_frischen_stand_ohne_pruefung(umg):
    ps.pruefen(pfad=umg["pfad"])
    n = len(umg["rufe"]["tcp"])
    ps.aktuell(pfad=umg["pfad"])
    assert len(umg["rufe"]["tcp"]) == n, "frischer Stand wird nur gelesen"


def test_cli_exit_code(umg, capsys, monkeypatch):
    monkeypatch.setattr(ps, "status_pfad", lambda: umg["pfad"])
    assert ps.main(["--frisch"]) == 1
    assert "PC getrennt" in capsys.readouterr().out
    umg["zustand"]["offen"].add("10.0.0.7")
    assert ps.main(["--frisch"]) == 0


def test_tui_anzeige():
    from tui import zentrale_tui as z
    assert z.peer_anzeige(None) is None
    assert z.peer_anzeige({"peer": "pc", "verbunden": True}) == ("PC ✓", True)
    assert z.peer_anzeige({"peer": "0RAMMachine", "verbunden": False}) == ("LAPTOP ✗", False)
