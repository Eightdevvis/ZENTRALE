"""
Der Stand des Google-Kalender-Syncs ist sichtbar (16.10.2026).

Anlass: ab 14.10. 16:33 brach jeder Sync ab („invalid_grant: Token has been
expired or revoked"), davor stand der Timer drei Tage — beides war in
ZENTRALE unsichtbar. Geprüft:
  * die Erkennung typischer Fälle im Klartext (core/kalender_sync_zustand.py),
  * scripts/kalender_sync.py schreibt nach JEDEM Lauf (Exit 0/1/2/3, Absturz),
  * Urteil „alt/Problem", Route, Alarm, und wo die TUI es zeigt.
Alle Pfade liegen in tmp_path — nie der echte Zustand.
"""
import importlib.util
import json
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import kalender_sync_zustand as zs  # noqa: E402

GRANT = ("error: Unknown error occurred: (invalid_grant) Token has been "
         "expired or revoked.\nerror: Use `-vdebug` to see the full traceback.\n")
JETZT = datetime(2026, 10, 16, 12, 0, 0)


@pytest.fixture
def zpfad(tmp_path, monkeypatch):
    p = tmp_path / "zustand.json"
    monkeypatch.setenv("ZENTRALE_KALENDER_SYNC_ZUSTAND", str(p))
    return p


# ── Erkennen ───────────────────────────────────────────────────────────
def test_erkennt_abgelaufenen_zugang_vor_der_stufe():
    assert zs.erkennen(3, GRANT, "sicherung") == (
        "zugang", "Google-Zugang abgelaufen — neu anmelden")


def test_erkennt_die_uebrigen_faelle():
    assert zs.erkennen(0, GRANT) == ("ok", None)
    assert zs.erkennen(1, "Temporary failure in name resolution")[0] == "netz"
    assert zs.erkennen(2, "", "loeschsperre")[0] == "loeschsperre"
    assert zs.erkennen(3, "kaputt", "sicherung")[0] == "sicherung"
    art, text = zs.erkennen(1, "x\nerror: Storage kaputt\n")
    assert art == "sonstig" and "Exit 1" in text and "Storage kaputt" in text


# ── Schreiben, seit, letzter Erfolg ────────────────────────────────────
def test_seit_bleibt_bis_zum_naechsten_erfolg(zpfad):
    t0 = JETZT - timedelta(hours=2)
    zs.schreiben(0, "ok", None, t0)
    zs.schreiben(3, "zugang", "x", t0 + timedelta(minutes=3))
    z = zs.schreiben(3, "zugang", "x", t0 + timedelta(minutes=6))
    assert z["seit"] == (t0 + timedelta(minutes=3)).isoformat()
    assert z["letzter_erfolg"] == t0.isoformat() and z["ok"] is False
    z = zs.schreiben(0, "ok", None, t0 + timedelta(minutes=9))
    assert z["seit"] is None and z["fehler"] is None
    assert json.loads(zpfad.read_text())["letzter_erfolg"] == (t0 + timedelta(minutes=9)).isoformat()


# ── Bewerten ───────────────────────────────────────────────────────────
def _z(**kw):
    z = {"letzter_versuch": (JETZT - timedelta(minutes=1)).isoformat(),
         "letzter_erfolg": (JETZT - timedelta(minutes=1)).isoformat(),
         "ok": True, "art": "ok", "fehler": None, "seit": None, "exit": 0}
    z.update(kw)
    return z


def test_ohne_datei_nichts(zpfad):
    b = zs.bewerten(jetzt=JETZT)
    assert b["bekannt"] is False and not b["problem"] and zs.alarme(JETZT) == []


def test_alles_gut_leise():
    b = zs.bewerten(_z(), JETZT)
    assert not b["problem"] and not b["alt"] and b["kurz"] == "google ✓ 11:59"


def test_zugang_abgelaufen_mit_seit():
    b = zs.bewerten(_z(ok=False, art="zugang", fehler="Google-Zugang abgelaufen — neu anmelden",
                       seit="2026-10-14T16:33:00",
                       letzter_erfolg="2026-10-14T16:30:00"), JETZT)
    assert b["problem"] and b["alt"]
    assert b["hinweis"] == "⚠ google-sync: Zugang abgelaufen — seit 14.10. 16:33"


def test_timer_tot_ist_ein_problem():
    alt = (JETZT - timedelta(minutes=30)).isoformat()
    b = zs.bewerten(_z(letzter_versuch=alt, letzter_erfolg=alt), JETZT)
    assert b["problem"] and b["hinweis"].startswith("⚠ google-sync läuft nicht")


def test_kurz_ohne_netz_ist_noch_kein_problem():
    vor = lambda m: (JETZT - timedelta(minutes=m)).isoformat()  # noqa: E731
    b = zs.bewerten(_z(ok=False, art="netz", letzter_erfolg=vor(20), seit=vor(17)), JETZT)
    assert not b["problem"] and b["alt"]
    b = zs.bewerten(_z(ok=False, art="netz", letzter_erfolg=vor(90), seit=vor(87)), JETZT)
    assert b["problem"] and "kein Netz" in b["hinweis"]


def test_alarm_stabil_und_mit_klartext(zpfad):
    zpfad.write_text(json.dumps(_z(ok=False, art="zugang", seit="2026-10-14T16:33:00",
                                   fehler="Google-Zugang abgelaufen — neu anmelden")))
    a, = zs.alarme(JETZT)
    assert a["kind"] == "Google-Sync" and "neu anmelden" in a["text"]
    assert zs.alarme(JETZT + timedelta(seconds=30))[0]["id"] == a["id"]


# ── scripts/kalender_sync.py schreibt bei jedem Ausgang ────────────────
@pytest.fixture
def ks(tmp_path, monkeypatch, zpfad):
    spec = importlib.util.spec_from_file_location(
        "kalender_sync_test", os.path.join(ROOT, "scripts", "kalender_sync.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    vdir = tmp_path / "kal"
    vdir.mkdir()
    sp = SimpleNamespace(vdir=vdir, loeschsperre=5, aufraeumen=lambda: 0, snapshot=lambda: None)
    monkeypatch.setattr(m, "STAND", str(tmp_path / "stand.json"))
    monkeypatch.setattr(m.kalender_speicher, "modus", lambda *a: "ics")
    monkeypatch.setattr(m.kalender_speicher, "ics_speicher", lambda *a, **k: sp)
    monkeypatch.setattr(m, "_spiegeln", lambda grund: None)
    monkeypatch.setattr(m.shutil, "which", lambda n: "/x/vdirsyncer")
    monkeypatch.setattr(m.kalender_ics, "cache_leeren", lambda: None)
    m.ANTWORT = {"google_probe": (0, ""), "zentrale": (0, "")}

    def run(cmd, **kw):
        code, out = m.ANTWORT[cmd[2]]
        return SimpleNamespace(returncode=code, stdout=out)
    monkeypatch.setattr(m.subprocess, "run", run)
    monkeypatch.setattr(m, "_google_sichern",
                        lambda exe: m._vdirsyncer(exe, "google_probe") == 0)
    m.sp = sp
    return m


def test_lauf_ok(ks):
    assert ks.main(["zentrale"]) == 0
    z = zs.lesen()
    assert z["ok"] and z["art"] == "ok" and z["letzter_erfolg"]


def test_abgelaufener_zugang_bei_der_sicherung(ks):
    ks.ANTWORT["google_probe"] = (1, GRANT)
    assert ks.main(["zentrale"]) == 3
    z = zs.lesen()
    assert (z["ok"], z["art"], z["exit"]) == (False, "zugang", 3)
    assert z["fehler"] == "Google-Zugang abgelaufen — neu anmelden"


def test_abgleich_selbst_scheitert(ks):
    ks.ANTWORT["zentrale"] = (1, "error: kaputt\n")
    assert ks.main(["zentrale"]) == 1
    assert zs.lesen()["art"] == "sonstig"


def test_loeschsperre(ks, monkeypatch):
    monkeypatch.setattr(ks, "_fehlende", lambda vdir, basis=None: ["t%d" % i for i in range(9)])
    assert ks.main(["zentrale"]) == 2
    assert zs.lesen()["art"] == "loeschsperre"


def test_nicht_eingerichtet(ks, monkeypatch):
    monkeypatch.setattr(ks.kalender_speicher, "modus", lambda *a: "json")
    assert ks.main(["zentrale"]) == 1
    assert zs.lesen()["art"] == "einrichtung"


def test_absturz_wird_festgehalten(ks, monkeypatch):
    def kaputt():
        raise RuntimeError("Platte voll")
    monkeypatch.setattr(ks.sp, "aufraeumen", kaputt)
    with pytest.raises(RuntimeError):
        ks.main(["zentrale"])
    z = zs.lesen()
    assert z["art"] == "sonstig" and "Platte voll" in z["fehler"]


# ── Route ──────────────────────────────────────────────────────────────
def test_route_liefert_zustand_und_urteil(zpfad):
    from ui.app import app
    zs.schreiben(3, "zugang", "Google-Zugang abgelaufen — neu anmelden")
    c = app.test_client()
    d = c.get("/api/calendar/sync").get_json()
    assert d["bekannt"] and d["problem"] and d["art"] == "zugang"
    assert "Zugang abgelaufen" in d["hinweis"]
    assert c.get("/api/calendar").get_json()["sync"]["art"] == "zugang"


# ── TUI ────────────────────────────────────────────────────────────────
def _text(zeilen):
    return "\n".join("".join(t for t, _r in z) for z in zeilen)


def test_ansichten_zeigen_die_warnung():
    from tui.ansichten import kalender_ansichten as ka
    from tui.ansichten import kalender_beispiel as kb
    sync = {"problem": True, "hinweis": "⚠ google-sync: Zugang abgelaufen — seit 14.10. 16:33"}
    for ansicht, view in (("A", "week"), ("B", "month"), ("C", "week")):
        d = dict(kb.api_daten(view), sync=sync)
        assert "google-sync: Zugang abgelaufen" in _text(ka.zeichne(ansicht, d, 140, 40)), ansicht


def test_ohne_problem_nur_leise_in_a():
    from tui.ansichten import kalender_ansichten as ka
    from tui.ansichten import kalender_beispiel as kb
    sync = {"problem": False, "kurz": "google ✓ 11:59"}
    assert "google ✓ 11:59" in _text(ka.zeichne("A", dict(kb.api_daten(), sync=sync), 140, 40))
    assert "google" not in _text(ka.zeichne("C", dict(kb.api_daten(), sync=sync), 140, 40))


def test_startseite_liest_den_alarm():
    from tui.ansichten import startseite
    st = {"alarms": [{"kind": "KONFLIKT", "text": "x"},
                     {"kind": "Google-Sync", "text": "google-sync: Zugang abgelaufen — seit "
                      "14.10. 16:33 (Google-Zugang abgelaufen — neu anmelden)"}]}
    assert startseite.sync_warnung(st) == "⚠ google-sync: Zugang abgelaufen — seit 14.10. 16:33"
    assert startseite.sync_warnung({"alarms": []}) is None
