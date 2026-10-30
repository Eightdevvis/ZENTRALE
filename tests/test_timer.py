"""Die Timer eines Geräts (zentrale_cli/timer.py): gerendert mit dem Befehl
`zentrale` des Kanals statt Sashas Checkout-Pfad, idempotent installiert mit
einem falschen systemctl, ohne systemd ein Satz. Nie das echte systemd
(conftest: ZENTRALE_SYSTEMCTL=aus, eigener Einheiten-Ordner; der falsche
systemctl ist devkit/fake_systemd.py)."""
import io
import os
import pathlib

import pytest

from devkit import fake_systemd
from zentrale_cli import befehle, haupt, timer
from zentrale_cli.ausgabe import Terminal


class Spiel(Terminal):
    def __init__(self):
        super().__init__(aus=io.StringIO(), ein=io.StringIO())

    @property
    def text(self):
        return self.aus.getvalue()


@pytest.fixture
def systemd(tmp_path, monkeypatch):
    """The shared fake (devkit/fake_systemd.py) — the same one `zentrale dev` uses."""
    fake = fake_systemd.make(tmp_path / "systemd")
    for k, v in fake.env().items():
        monkeypatch.setenv(k, v)

    class S:
        pass
    s = S()
    s.fake = fake
    s.ordner = pathlib.Path(fake.units)
    s.aufrufe = fake.calls
    s.leeren = fake.clear_log
    return s


def _checkout(tmp_path, name="checkout"):
    w = tmp_path / name
    (w / "bin").mkdir(parents=True, exist_ok=True)
    return str(w)


# ── Rendern ────────────────────────────────────────────────────────────

def test_entwickler_checkout_ruft_den_eigenen_befehl(tmp_path):
    w = _checkout(tmp_path)
    e = timer.einheiten(w)
    assert set(e) == {"zentrale-abgleich.service", "zentrale-abgleich.timer",
                      "zentrale-kalender-sync.service", "zentrale-kalender-sync.timer"}
    assert f"ExecStart={w}/bin/zentrale sync --automatic\n" in e["zentrale-abgleich.service"]
    assert f"ExecStart={w}/bin/zentrale adapter run\n" in e["zentrale-kalender-sync.service"]
    assert "OnCalendar=*:0/5" in e["zentrale-abgleich.timer"]
    assert "OnCalendar=*:0/3" in e["zentrale-kalender-sync.timer"]
    assert "PATH=%h/.local/bin" in e["zentrale-kalender-sync.service"]     # vdirsyncer per pipx
    assert all("codicus" not in v for v in e.values())


def test_installierter_hub_ruft_aktuell_nicht_die_fassung(tmp_path, monkeypatch):
    heim = tmp_path / "heim"
    monkeypatch.setenv("ZENTRALE_HEIM", str(heim))
    fassung = heim / "hub" / "41"
    (fassung / "bin").mkdir(parents=True)
    e = timer.einheiten(str(fassung))
    assert f"ExecStart={heim}/hub/aktuell/bin/zentrale sync --automatic\n" in e["zentrale-abgleich.service"]
    assert "/hub/41/" not in "".join(e.values())          # ein Update dreht nur `aktuell`


def test_paketverwaltung_ruft_den_starter(tmp_path):
    w = _checkout(tmp_path)
    with open(os.path.join(w, "KANAL"), "w") as f:
        f.write("pacman\n")
    assert "ExecStart=/usr/bin/zentrale adapter run\n" in timer.einheiten(w)["zentrale-kalender-sync.service"]


def test_pfad_mit_leerzeichen_in_anfuehrungszeichen(tmp_path):
    w = _checkout(tmp_path, "mein hub")
    assert f'ExecStart="{w}/bin/zentrale" sync --automatic' in timer.einheiten(w)["zentrale-abgleich.service"]


# ── Installieren ───────────────────────────────────────────────────────

def test_installieren_idempotent(tmp_path, systemd):
    w = _checkout(tmp_path)
    r = timer.installieren(w)
    assert r["da"] and len(r["geschrieben"]) == 4 and not r["ersetzt"] and not r["fehler"]
    a = systemd.aufrufe()
    assert "--user daemon-reload" in a
    assert "--user enable --now zentrale-abgleich.timer zentrale-kalender-sync.timer" in a
    inhalt = (systemd.ordner / "zentrale-abgleich.service").read_text()
    systemd.leeren()
    r = timer.installieren(w)
    assert r["geschrieben"] == [] and "--user daemon-reload" not in systemd.aufrufe()
    assert (systemd.ordner / "zentrale-abgleich.service").read_text() == inhalt
    z = timer.zustand(w)
    assert {d["service"] for d in z["timer"].values()} == {"eigen"}
    assert z["timer"]["zentrale-abgleich"]["an"] == "enabled"


def test_alter_verweis_nach_deploy_wird_ersetzt_nicht_beschrieben(tmp_path, systemd):
    """Sashas Laptop: die alten Einheiten sind Verweise in den Checkout."""
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    alt = deploy / "zentrale-abgleich.service"
    alt.write_text("ALT\n")
    systemd.ordner.mkdir(parents=True)
    os.symlink(alt, systemd.ordner / "zentrale-abgleich.service")
    os.symlink(deploy / "zentrale-abgleich.timer", systemd.ordner / "zentrale-abgleich.timer")
    assert timer.zustand(_checkout(tmp_path))["timer"]["zentrale-abgleich"]["service"] == "verweis"
    r = timer.installieren(_checkout(tmp_path))
    assert sorted(r["ersetzt"]) == ["zentrale-abgleich.service", "zentrale-abgleich.timer"]
    assert alt.read_text() == "ALT\n"                                   # Checkout unberührt
    neu = systemd.ordner / "zentrale-abgleich.service"
    assert not neu.is_symlink() and neu.read_text().startswith(timer.MARKE)
    assert "--user reenable zentrale-abgleich.timer" in systemd.aufrufe()


def test_entfernen_nur_eigene_dateien(tmp_path, systemd):
    timer.installieren(_checkout(tmp_path))
    fremd = systemd.ordner / "zentrale-kalender-sync.timer"
    fremd.write_text("[Timer]\n")                                       # von Hand
    r = timer.entfernen()
    assert "--user disable --now zentrale-abgleich.timer zentrale-kalender-sync.timer" in systemd.aufrufe()
    assert r["liegen"] == ["zentrale-kalender-sync.timer"] and len(r["entfernt"]) == 3
    assert fremd.exists() and not (systemd.ordner / "zentrale-abgleich.timer").exists()


def test_ohne_systemd_ein_satz_nichts_geschrieben(tmp_path):
    w = _checkout(tmp_path)
    assert timer.installieren(w) == {"da": False, "geschrieben": [], "ersetzt": [], "fehler": ""}
    term = Spiel()
    assert haupt.main(["timers", "install"], term=term) == 0
    assert "systemd for your user is not available" in term.text
    assert not os.path.exists(timer.ordner())
    term = Spiel()
    assert haupt.main(["timers"], term=term) == 0 and "not available" in term.text


def test_unter_pytest_ohne_umlenkung_nie_das_echte(monkeypatch):
    monkeypatch.delenv("ZENTRALE_SYSTEMCTL")
    assert timer._programm() is None and not timer.verfuegbar()


def test_cli_install_status_remove(tmp_path, systemd, monkeypatch):
    monkeypatch.setattr(befehle, "WURZEL", _checkout(tmp_path))
    term = Spiel()
    assert haupt.main(["timers", "install"], term=term) == 0, term.text
    assert "Timers on" in term.text
    term = Spiel()
    assert haupt.main(["timers"], term=term) == 0
    assert "zentrale-kalender-sync" in term.text and "enabled" in term.text
    assert "timers install" not in term.text                            # alles gut, kein Rat
    term = Spiel()
    assert haupt.main(["timers", "remove"], term=term) == 0 and "removed" in term.text
    assert haupt.main(["timers", "tanzen"], term=Spiel()) == 2


# ── vdirsyncer, Brücke, Kern ───────────────────────────────────────────

def test_vdirsyncer_fehlt_nennt_das_paket(monkeypatch):
    monkeypatch.setattr(timer.shutil, "which",
                        lambda p, path=None: "/usr/bin/pacman" if p == "pacman" else None)
    term = Spiel()
    befehle.vdirsyncer_hinweis(term)
    assert "install the package 'vdirsyncer' with pacman" in term.text
    monkeypatch.setattr(timer.shutil, "which",
                        lambda p, path=None: "/usr/bin/apt-get" if p == "apt-get" else None)
    term = Spiel()
    befehle.vdirsyncer_hinweis(term)
    assert "with apt" in term.text


def test_adapter_run_ohne_anschluss_still_nichts(monkeypatch, tmp_path):
    monkeypatch.setenv("VDIRSYNCER_CONFIG", str(tmp_path / "gibt-es-nicht"))
    term = Spiel()
    assert haupt.main(["adapter", "run"], term=term) == 0
    assert "nothing to do" in term.text


def test_neue_ki_schluessel_starten_den_kern_neu(systemd, monkeypatch):
    monkeypatch.setattr(befehle, "_ki_werte", lambda: {"ANTHROPIC_API_KEY": "neu"})
    term = Spiel()
    befehle._ki_neu_melden(term, {}, automatisch=True)
    assert "ANTHROPIC_API_KEY" in term.text and "quit and start" not in term.text  # Timer: kein Rat
    assert "--user try-restart" not in " ".join(systemd.aufrufe())     # Kern läuft nicht
    systemd.fake.set_active("zentrale-kern.service")
    term = Spiel()
    befehle._ki_neu_melden(term, {}, automatisch=False)
    assert "--user try-restart zentrale-kern.service" in systemd.aufrufe()
    assert "restarted zentrale-kern.service" in term.text
    term = Spiel()
    befehle._ki_neu_melden(term, {"ANTHROPIC_API_KEY": "neu"}, automatisch=False)
    assert term.text == ""                                               # nichts Neues


def test_sync_automatic_ohne_cloud_still(monkeypatch):
    term = Spiel()
    assert haupt.main(["sync", "--automatic"], term=term) == 0 and term.text == ""
    assert haupt.main(["sync", "--laut"], term=Spiel()) == 2
    assert haupt.main(["status", "extra"], term=Spiel()) == 2


def test_nie_aus_einem_worktree(tmp_path, systemd):
    w = _checkout(tmp_path / ".claude" / "worktrees", "zweig")
    r = timer.installieren(w)
    assert "worktree" in r["fehler"] and r["geschrieben"] == [] and systemd.aufrufe() == ["--user show-environment"]
