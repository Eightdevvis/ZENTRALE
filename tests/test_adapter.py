"""Der Adapter (core/adapter.py, memory/hub/adapter.md): Anschlüsse mit
Schema, immer abgeglichen, der Kalender erst mit Anschluss, die Regel des
Mietvertrags, die Zugangsdaten Eintrag für Eintrag — und `zentrale adapter`."""
import datetime
import os
import io
import json

import pytest

import abgleich_apps
import abgleich_zusammenfuehren as regeln
import adapter
import adapter_bruecke as bruecke
import ai_config
import dateien
import kalender
import kalender_speicher
from zentrale_cli import befehle
from zentrale_cli.ausgabe import Terminal


class Spiel(Terminal):
    def __init__(self):
        super().__init__(aus=io.StringIO(), ein=io.StringIO(""))

    @property
    def text(self):
        return self.aus.getvalue()


def _kalender_anschluss():
    a = adapter.neu("google-kalender", "kalender-vdirsyncer", "kalender", "Google Calendar",
                    {"vdirsyncer": {"abschnitte": []}})
    adapter.speichern(a)
    return a


def test_schema_und_kaputte_dateien_fallen_weg():
    with pytest.raises(adapter.AdapterFehler):
        adapter.speichern({"id": "X Y", "art": "kalender-vdirsyncer", "speist": "kalender"})
    _kalender_anschluss()
    d = adapter.ordner() + "/anschluesse/"
    open(d + "kaputt.json", "w").write("{")
    open(d + "falsch.json", "w").write(json.dumps({"id": "anders", "art": "ki-anbieter",
                                                   "speist": "assistent", "format": adapter.FORMAT}))
    assert list(adapter.alle()) == ["google-kalender"]


def test_adapter_ist_pflicht_und_wird_nie_gefragt(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {}})
    (tmp_path / "data/adapter/anschluesse").mkdir(parents=True)
    (tmp_path / "data/adapter/anschluesse/x.json").write_text("{}")
    tab = abgleich_apps.tabelle()
    assert tab["adapter"]["pflicht"] is True
    assert "adapter" not in abgleich_apps.offen(str(tmp_path))
    assert "adapter" not in abgleich_apps.mit_daten(str(tmp_path))
    assert "data/adapter/anschluesse/*.json" in abgleich_apps.muster()


def test_kalender_gleicht_erst_mit_anschluss_ab(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    assert "data/kalender/**" not in abgleich_apps.muster()
    assert "data/kalender_neben.json" in abgleich_apps.muster()
    _kalender_anschluss()
    assert "data/kalender/**" in abgleich_apps.muster()


def test_neues_geraet_steht_nach_dem_umzug_von_selbst_auf_ics(monkeypatch):
    monkeypatch.delenv("ZENTRALE_KALENDER_SPEICHER", raising=False)
    neben = kalender.CAL_PATH.parent / "kalender_neben.json"
    assert kalender_speicher.modus(kalender.CAL_PATH) == "json"
    neben.write_text(json.dumps({"migriert_am": "2026-10-07T10:00:00+00:00"}))
    assert kalender_speicher.modus(kalender.CAL_PATH) == "ics"
    monkeypatch.setenv("ZENTRALE_KALENDER_SPEICHER", "json")      # ausdrücklich gilt
    assert kalender_speicher.modus(kalender.CAL_PATH) == "json"


# ── Der Mietvertrag ────────────────────────────────────────────────────

T0 = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=datetime.timezone.utc)


def test_mietvertrag_nehmen_verlaengern_ablaufen():
    assert bruecke.frei_fuer(None, "a", T0)
    m = bruecke.beanspruchen("g", "a", T0)
    assert bruecke.haelt(m, "a", T0) and not bruecke.frei_fuer(m, "b", T0)
    spaeter = T0 + datetime.timedelta(minutes=bruecke.MIETE_MIN + 1)
    assert bruecke.frei_fuer(m, "b", spaeter) and not bruecke.haelt(m, "a", spaeter)
    m2 = bruecke.beanspruchen("g", "a", T0 + datetime.timedelta(minutes=3))
    assert m2["seit"] == m["seit"] and m2["ablauf"] > m["ablauf"]


def test_mietvertrag_wer_zuerst_in_der_mitte_war_nicht_feldweise():
    rel = "data/adapter/bruecke/google-kalender.json"
    b = json.dumps({"inhaber": "a", "ablauf": "1"}).encode()
    l = json.dumps({"inhaber": "a", "ablauf": "3"}).encode()       # a verlängert
    m = json.dumps({"inhaber": "b", "ablauf": "2"}).encode()       # b übernahm zuerst
    r = regeln.zusammenfuehren(rel, b, l, m)
    assert r.inhalt == m and r.konflikte == []


def test_zugangsdaten_eintrag_fuer_eintrag():
    rel = "data/adapter/geheim.enc"
    b = {"format": "zentrale-geheim/1", "eintraege": {"ki/A": {"zu": "konto", "wert": "1"}}}
    l = {"format": "zentrale-geheim/1", "eintraege": {"ki/A": {"zu": "konto", "wert": "1"},
                                                      "ki/B": {"zu": "konto", "wert": "2"}}}
    m = {"format": "zentrale-geheim/1", "eintraege": {"ki/A": {"zu": "konto", "wert": "1"},
                                                      "kal/token": {"zu": "konto", "wert": "3"}}}
    r = regeln.zusammenfuehren(rel, *(json.dumps(x).encode() for x in (b, l, m)))
    assert sorted(json.loads(r.inhalt)["eintraege"]) == ["kal/token", "ki/A", "ki/B"]


# ── zentrale adapter ───────────────────────────────────────────────────

def test_cli_liste_zeigt_inhaber_und_ablauf(monkeypatch):
    term = Spiel()
    assert befehle.adapter_liste(term) == 0 and "No connections yet" in term.text
    _kalender_anschluss()
    monkeypatch.setenv("ZENTRALE_ABGLEICH_WEG", "mitte")
    monkeypatch.setattr(befehle.abgleich, "schluessel_da", lambda: True)
    term = Spiel()
    befehle.adapter_liste(term)
    assert "google-kalender" in term.text and "free — the next device" in term.text
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    bruecke.beanspruchen("google-kalender", "minipc", jetzt)
    term = Spiel()
    befehle.adapter_liste(term)
    assert "minipc until" in term.text


def test_cli_liste_ohne_konto_ist_dieses_geraet_die_bruecke():
    _kalender_anschluss()
    term = Spiel()
    befehle.adapter_liste(term)
    assert "this device (no account" in term.text


def test_cli_setup_ohne_vdirsyncer_und_mit_ki_schluessel(monkeypatch):
    conf = {"keys": {"MISTRAL_API_KEY": "m-geheim"}}
    monkeypatch.setattr(ai_config, "_config", conf)
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    monkeypatch.setattr(dateien, "knoten", lambda: "minipc")
    term = Spiel()
    assert befehle.adapter_setup(term) == 0
    assert "MISTRAL_API_KEY" in term.text and "No vdirsyncer setup" in term.text
    assert "keys" not in conf
    term = Spiel()
    befehle.adapter_liste(term)
    assert "ki-anbieter" in term.text and "1 key(s) readable here" in term.text


def test_status_zeigt_den_adapter(monkeypatch):
    _kalender_anschluss()
    term = Spiel()
    assert befehle.status(term) == 0
    assert "Adapter" in term.text and "always synced — 1 connection(s)" in term.text


# ── Kalender über die Mitte, ohne Google (kalender-mitte, 28.10.2026) ───

def _mitte_spiel(monkeypatch, tmp_path, knoten="laptop"):
    """Angemeldet, Abgleich gespielt (zählt nur), eigener Abgleich-Ordner."""
    import abgleich
    import adapter_ablauf
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "abgleich"))
    monkeypatch.setenv("ZENTRALE_ADAPTER_ORDNER", str(tmp_path / "data" / "adapter"))
    monkeypatch.setattr(adapter_ablauf, "nur_lokal", lambda: False)
    laeufe = []
    monkeypatch.setattr(abgleich, "abgleichen", lambda w, **k: laeufe.append(w))
    monkeypatch.setattr(dateien, "knoten", lambda: knoten)
    return laeufe


def _kalender_da(wurzel):
    d = wurzel / "data" / "kalender" / "termine"
    d.mkdir(parents=True)
    (d / "a.ics").write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    return d / "a.ics"


def test_mitte_vorgabe_aus_kalender_gleicht_nicht_ab(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    assert not adapter.kalender_ueber_cloud() and not adapter.kalender_ohne_bruecke()
    assert "data/kalender/**" not in abgleich_apps.muster()


def test_mitte_eingeschaltet_kalender_gleicht_ab_ohne_bruecke(monkeypatch, tmp_path):
    import adapter_ablauf
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    laeufe = _mitte_spiel(monkeypatch, tmp_path)
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path)) == ("ursprung", None)
    assert len(laeufe) == 2                         # erst holen, dann hinaus
    assert adapter.lesen("kalender-mitte")["art"] == "kalender-mitte"
    assert adapter.kalender_ueber_cloud() and adapter.kalender_ohne_bruecke()
    assert adapter.kalender_anschluss() is None     # nichts treibt vdirsyncer
    assert "data/kalender/**" in abgleich_apps.muster()
    # `zentrale adapter run` (der Timer) und das Skript fahren kein Google,
    # auch nicht mit einer eigenen vdirsyncer-Konfiguration.
    cfg = tmp_path / "vdirsyncer-config"
    cfg.write_text("[general]\n")
    monkeypatch.setenv("ZENTRALE_VDIRSYNCER_CONFIG", str(cfg))
    term = Spiel()
    assert befehle.adapter_lauf(term) == 0 and "through your account only" in term.text
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kalender_sync_mitte", os.path.join(os.path.dirname(__file__), "..", "scripts", "kalender_sync.py"))
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)
    monkeypatch.setattr(skript, "_ein_lauf", lambda argv=None: pytest.fail("Google-Lauf"))
    assert skript.main(["zentrale"]) == 0
    # Ein alter Google-Stand wird nicht zur Warnung „läuft nicht".
    import kalender_sync_zustand
    monkeypatch.setattr(kalender_sync_zustand, "lesen", lambda: {"letzter_versuch": "2026-01-01T00:00:00"})
    assert kalender_sync_zustand.bewerten()["problem"] is False
    assert kalender_sync_zustand.alarme() == []
    # Zweimal einschalten: nichts Neues, kein zweiter Ursprung.
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))[0] == "vorhanden"


def test_mitte_wer_zuerst_einschaltet_legt_nichts_beiseite(monkeypatch, tmp_path):
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path)
    ics = _kalender_da(tmp_path)
    adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))
    assert adapter.kalender_ursprung() == "laptop"
    assert json.loads(open(abgleich.ordner() + "/kalender_dabei.json").read())["ursprung"] is True
    assert adapter.vor_abgleich(tmp_path, abgleich.ordner(), [adapter.KALENDER_MUSTER]) is None
    assert ics.exists()


def test_mitte_mit_terminen_macht_nicht_zum_ursprung(monkeypatch, tmp_path):
    """Zwei Geräte schalten vor dem ersten Abgleich ein: das zweite findet
    schon Termine in der Mitte (abgleich.mitte_hat_kalender) und wird NICHT
    Ursprung, auch wenn der Anschluss des ersten noch nicht da ist."""
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, knoten="minipc")
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", lambda ordner="data/kalender": True)
    _kalender_da(tmp_path)
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))[0] == "dazu"
    assert not adapter.kalender_dabei(abgleich.ordner())


def test_mitte_spaeter_eingeschaltet_legt_beiseite_statt_zu_loeschen(monkeypatch, tmp_path):
    """Ein anderes Gerät war zuerst: dieses ist NICHT der Ursprung, auch wenn
    es selbst einschaltet — sein alter Kalender wandert beiseite."""
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, knoten="minipc")
    # Was der erste Abgleich vom Laptop mitbringt:
    a = adapter.neu("kalender-mitte", "kalender-mitte", "kalender")
    a["eingerichtet"]["auf"] = "laptop"
    adapter.speichern(a)
    _kalender_da(tmp_path)
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))[0] == "vorhanden"
    assert not adapter.kalender_dabei(abgleich.ordner())
    ziel = adapter.vor_abgleich(tmp_path, abgleich.ordner(), [adapter.KALENDER_MUSTER])
    assert ziel and not (tmp_path / "data" / "kalender").exists()
    assert os.path.exists(os.path.join(ziel, "termine", "a.ics"))


def test_mitte_neben_google_anschluss_ist_nicht_ursprung(monkeypatch, tmp_path):
    """Gleicht der Kalender schon über einen Google-Anschluss ab, macht das
    Einschalten dieses Gerät nicht zum Ursprung."""
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, knoten="minipc")
    g = _kalender_anschluss()
    g["eingerichtet"]["auf"] = "laptop"
    adapter.speichern(g)
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))[0] == "dazu"
    assert not adapter.kalender_dabei(abgleich.ordner())
    assert adapter.kalender_ursprung() == "laptop"
    assert not adapter.kalender_ohne_bruecke()      # Google fährt weiter über die Brücke


def test_mitte_ohne_konto_oder_offline_schaltet_nichts_ein(monkeypatch, tmp_path):
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter_ablauf, "nur_lokal", lambda: True)
    term = Spiel()
    assert befehle.adapter_kalender(term) == 1 and "Not logged in" in term.text
    monkeypatch.setattr(adapter_ablauf, "nur_lokal", lambda: False)

    def offline(w, **k):
        raise OSError("keine Verbindung")
    monkeypatch.setattr(abgleich, "abgleichen", offline)
    assert adapter_ablauf.kalender_mitte_einschalten(str(tmp_path))[0] == "offline"
    assert not adapter.kalender_ueber_cloud() and not adapter.kalender_dabei(abgleich.ordner())
