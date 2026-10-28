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


# ── Die Quelle der Kalender-App (kalender_einstellung, 28.10.2026) ──────

import abgleich_mitte
import kalender_einstellung as ke


def _mitte_spiel(monkeypatch, tmp_path, knoten="laptop", hat=False):
    """Angemeldet, Abgleich gespielt (zählt nur), eigener Abgleich-Ordner;
    die Mitte antwortet auf „hast du schon einen Kalender?" mit `hat`."""
    import abgleich
    import adapter_ablauf
    monkeypatch.setenv("ZENTRALE_ABGLEICH_DIR", str(tmp_path / "abgleich"))
    monkeypatch.setenv("ZENTRALE_ADAPTER_ORDNER", str(tmp_path / "data" / "adapter"))
    monkeypatch.setattr(adapter_ablauf, "nur_lokal", lambda: False)
    laeufe = []
    monkeypatch.setattr(abgleich, "abgleichen", lambda w, **k: laeufe.append(w))
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", lambda ordner="data/kalender": hat,
                        raising=False)
    monkeypatch.setattr(dateien, "knoten", lambda: knoten)
    return laeufe


def _kalender_da(wurzel):
    d = wurzel / "data" / "kalender" / "termine"
    d.mkdir(parents=True, exist_ok=True)
    (d / "a.ics").write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    return d / "a.ics"


def _skript():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kalender_sync_quelle", os.path.join(os.path.dirname(__file__), "..", "scripts", "kalender_sync.py"))
    skript = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skript)
    return skript


def _basis(abgleich_ordner, dateien_):
    os.makedirs(abgleich_ordner, exist_ok=True)
    with open(os.path.join(abgleich_ordner, "basis.json"), "w") as f:
        json.dump({"stand": "1", "dateien": dateien_}, f)


def test_quelle_ohne_einstellung_wie_bisher(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    assert ke.quelle() == "google" and not ke.eingestellt()
    assert not adapter.kalender_ueber_cloud() and adapter.kalender_google_an()
    assert "data/kalender/**" not in abgleich_apps.muster()
    assert not os.path.exists(ke._pfad(ke.HAUPT))          # nichts legt sie von selbst an
    _kalender_anschluss()                                    # der alte Weg: Brücke per Vertrag
    assert adapter.kalender_ueber_cloud() and adapter.kalender_mit_vertrag()
    assert not os.path.exists(ke._pfad(ke.HAUPT))


def test_quelle_google_jedes_geraet_faehrt_selbst(monkeypatch, tmp_path):
    import adapter_ablauf
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    _mitte_spiel(monkeypatch, tmp_path)
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "google", tmp_path)["ergebnis"] == "gesetzt"
    assert adapter.kalender_google_an() and not adapter.kalender_ueber_cloud()
    assert "data/kalender/**" not in abgleich_apps.muster()
    # Ohne Anschluss: jedes Gerät fährt seine eigene Konfiguration.
    skript = _skript()
    gefahren = []
    monkeypatch.setattr(skript, "_ein_lauf", lambda argv=None: gefahren.append(dateien.knoten()) or 0)
    for wer in ("laptop", "minipc"):
        monkeypatch.setattr(dateien, "knoten", lambda wer=wer: wer)
        assert skript.main(["zentrale"]) == 0
    assert gefahren == ["laptop", "minipc"]
    # Mit Anschluss: auch ohne Mietvertrag, auf jedem Gerät.
    a = _kalender_anschluss()
    assert not adapter.kalender_mit_vertrag()
    monkeypatch.setattr(adapter_ablauf.shutil, "which", lambda n: "/bin/" + n)
    wie = []
    monkeypatch.setattr(adapter_ablauf, "_fahren", lambda *x, lokal=False: wie.append(lokal) or
                        adapter_ablauf.Lauf("gefahren"))
    for wer in ("laptop", "minipc"):
        monkeypatch.setattr(dateien, "knoten", lambda wer=wer: wer)
        assert adapter_ablauf.bruecke_lauf(a, tmp_path, tmp_path / "data/kalender", None).art == "gefahren"
    assert wie == [True, True] and bruecke.lesen("google-kalender") is None


def test_quelle_zencloud_kein_google_kalender_gleicht_ab(monkeypatch, tmp_path):
    import adapter_ablauf
    import kalender_sync_zustand
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    laeufe = _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "fuellt" and r["beiseite"] is None and r["von"] == "google"
    assert ics.exists() and len(laeufe) == 1                # gleich hinaus, füllt die Cloud
    assert adapter.kalender_ueber_cloud() and not adapter.kalender_google_an()
    assert "data/kalender/**" in abgleich_apps.muster()
    # Kein Google: weder der Timer noch das Skript, auch nicht mit eigener Konfiguration.
    cfg = tmp_path / "vdirsyncer-config"
    cfg.write_text("[general]\n")
    monkeypatch.setenv("ZENTRALE_VDIRSYNCER_CONFIG", str(cfg))
    term = Spiel()
    assert befehle.adapter_lauf(term) == 0 and "not google" in term.text
    skript = _skript()
    monkeypatch.setattr(skript, "_ein_lauf", lambda argv=None: pytest.fail("Google-Lauf"))
    assert skript.main(["zentrale"]) == 0
    _kalender_anschluss()                                    # auch mit Anschluss nicht
    assert skript.main(["zentrale"]) == 0
    monkeypatch.setattr(kalender_sync_zustand, "lesen", lambda: {"letzter_versuch": "2026-01-01T00:00:00"})
    assert kalender_sync_zustand.bewerten()["problem"] is False
    # Noch einmal: nichts Neues.
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "gleich"


def test_quelle_zencloud_volle_cloud_legt_beiseite_auch_beim_umstoepseln(monkeypatch, tmp_path):
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, hat=True)
    _kalender_da(tmp_path)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "uebernimmt" and r["beiseite"]
    assert r["beiseite"].startswith(os.path.join(abgleich.ordner(), "kalender-vor-cloud"))
    assert os.path.exists(os.path.join(r["beiseite"], "termine", "a.ics"))   # nie gelöscht
    assert not (tmp_path / "data" / "kalender").exists()


def test_quelle_zencloud_unbekannt_bricht_ab_aendert_nichts(monkeypatch, tmp_path):
    import adapter_ablauf
    import abgleich
    laeufe = _mitte_spiel(monkeypatch, tmp_path, hat=None)
    ics = _kalender_da(tmp_path)
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "unbekannt"
    assert not ke.eingestellt() and ics.exists() and laeufe == []
    monkeypatch.delattr(abgleich, "mitte_hat_kalender")    # Vertrag noch nicht gebaut → None
    assert adapter_ablauf.mitte_hat_kalender() is None
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "unbekannt"
    monkeypatch.setattr(adapter_ablauf, "nur_lokal", lambda: True)
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "ohne_mitte"
    assert not ke.eingestellt()


def test_mitte_hat_kalender_vertrag(monkeypatch):
    import adapter_ablauf
    import abgleich
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", lambda ordner="data/kalender": ordner == "data/kalender")
    assert adapter_ablauf.mitte_hat_kalender() is True
    assert adapter_ablauf.mitte_hat_kalender("data/kalender_arbeit") is False

    def kaputt(ordner="data/kalender"):
        raise OSError("weg")
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", kaputt)
    assert adapter_ablauf.mitte_hat_kalender() is None
    monkeypatch.setattr(abgleich, "mitte_hat_kalender", lambda ordner="data/kalender": "ja")
    assert adapter_ablauf.mitte_hat_kalender() is None


def test_fuellen_geht_nicht_hinaus_nimmt_den_wert_zurueck(monkeypatch, tmp_path):
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)

    def offline(w, **k):
        raise OSError("keine Verbindung")
    monkeypatch.setattr(abgleich, "abgleichen", offline)
    r = adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert r["ergebnis"] == "offline" and not ke.eingestellt() and ics.exists()
    ke.schreiben(ke.HAUPT, "lokal")
    adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)
    assert ke.quelle() == "lokal"


def test_der_fuellende_abgleich_legt_nicht_beiseite(monkeypatch, tmp_path):
    """Im Abgleich, den kalender_quelle_setzen nach „Cloud leer" fährt, bleibt
    der Kalender liegen — vor_abgleich sieht den Block kalender_fuellt."""
    import adapter_ablauf
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)
    gesehen = []
    monkeypatch.setattr(abgleich, "abgleichen", lambda w, **k: gesehen.append(
        adapter.vor_abgleich(tmp_path, abgleich.ordner(), [adapter.KALENDER_MUSTER],
                             abgleich.mitte_hat_kalender, abgleich.basis_kennt)))
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "fuellt"
    assert gesehen == [None] and ics.exists()


def test_spaeteres_geraet_legt_beim_ersten_abgleich_beiseite(monkeypatch, tmp_path):
    """Die Einstellung kam mit dem Abgleich: jedes Gerät folgt derselben
    Regel — Cloud voll → beiseite, Cloud leer → füllt, Basis kennt den
    Kalender → normaler Abgleich, unbekannt → kein Abgleich."""
    import abgleich
    _mitte_spiel(monkeypatch, tmp_path, knoten="minipc")
    ke.schreiben(ke.HAUPT, "zencloud")
    m = abgleich_apps.jetzt_erlaubt([adapter.KALENDER_MUSTER])
    assert m == [adapter.KALENDER_MUSTER]
    o = abgleich.ordner()

    def frage(antwort):
        return lambda ordner="data/kalender": antwort
    kennt = abgleich.basis_kennt
    assert adapter.vor_abgleich(tmp_path, o, m, frage(True), kennt) is None      # nichts da
    _kalender_da(tmp_path)
    _basis(o, ["data/kalender/termine/a.ics"])
    assert adapter.vor_abgleich(tmp_path, o, m, frage(True), kennt) is None      # war schon dabei
    _basis(o, ["data/lists.json"])
    assert adapter.vor_abgleich(tmp_path, o, m, frage(False), kennt) is None     # füllt die Cloud
    with pytest.raises(abgleich_mitte.MitteFehler):
        adapter.vor_abgleich(tmp_path, o, m, frage(None), kennt)
    with pytest.raises(abgleich_mitte.MitteFehler):                   # ohne Frage: unbekannt
        adapter.vor_abgleich(tmp_path, o, m, None, kennt)
    with pytest.raises(abgleich_mitte.MitteFehler):                   # ohne Basis: unbekannt
        adapter.vor_abgleich(tmp_path, o, m, frage(True))
    ziel = adapter.vor_abgleich(tmp_path, o, m, frage(True), kennt)
    assert ziel and os.path.exists(os.path.join(ziel, "termine", "a.ics"))
    assert not (tmp_path / "data" / "kalender").exists()
    # Im Block kalender_fuellt wird nicht gefragt.
    _kalender_da(tmp_path)
    with adapter.kalender_fuellt():
        assert adapter.vor_abgleich(tmp_path, o, m, frage(True), kennt) is None
    assert adapter.vor_abgleich(tmp_path, o, m, frage(True), kennt)


def test_quelle_lokal_weder_cloud_noch_google(monkeypatch, tmp_path):
    import adapter_ablauf
    monkeypatch.setattr(ai_config, "_overrides", {"abgleich_apps": {"kalender": True}})
    _mitte_spiel(monkeypatch, tmp_path)
    _kalender_anschluss()
    adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "lokal", tmp_path)
    assert not adapter.kalender_ueber_cloud() and not adapter.kalender_google_an()
    assert "data/kalender/**" not in abgleich_apps.muster()
    skript = _skript()
    monkeypatch.setattr(skript, "_ein_lauf", lambda argv=None: pytest.fail("Google-Lauf"))
    assert skript.main(["zentrale"]) == 0


def test_umstoepseln_loescht_nichts(monkeypatch, tmp_path):
    import adapter_ablauf
    _mitte_spiel(monkeypatch, tmp_path, hat=False)
    ics = _kalender_da(tmp_path)
    for q in ("zencloud", "lokal", "google", "zencloud", "google"):
        adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, q, tmp_path)
        assert ke.quelle() == q and ics.exists()
    assert ke.instanz()["geaendert"]["von"] == "zencloud"
    with pytest.raises(adapter.AdapterFehler):
        adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "icloud", tmp_path)


def test_alter_schalter_kalender_mitte_wird_zencloud(monkeypatch, tmp_path, capsys):
    import adapter_ablauf
    _mitte_spiel(monkeypatch, tmp_path, hat=True)
    d = tmp_path / "data/adapter/anschluesse"
    d.mkdir(parents=True)
    (d / "kalender-mitte.json").write_text(json.dumps(
        {"format": adapter.FORMAT, "id": "kalender-mitte", "art": "kalender-mitte", "speist": "kalender"}))
    assert adapter.alle() == {} and "ungültig" not in capsys.readouterr().out
    assert ke.quelle() == "zencloud" and adapter.kalender_ueber_cloud()
    # Umstöpseln schreibt die neue Datei und nimmt den alten Schalter weg.
    assert adapter_ablauf.kalender_quelle_setzen(ke.HAUPT, "zencloud", tmp_path)["ergebnis"] == "uebernimmt"
    assert sorted(os.listdir(d)) == ["kalender-haupt.json"]
    assert ke.quelle() == "zencloud"


def test_zwei_kalender_apps_je_eine_quelle(monkeypatch, tmp_path):
    _mitte_spiel(monkeypatch, tmp_path)
    ke.schreiben(ke.HAUPT, "google")
    ke.schreiben("kalender-arbeit", "zencloud", ordner_rel="data/kalender_arbeit")
    assert sorted(ke.instanzen()) == ["kalender-arbeit", "kalender-haupt"]
    assert [e["id"] for e in ke.mit_quelle("zencloud")] == ["kalender-arbeit"]
    assert not adapter.kalender_ueber_cloud()                        # data/kalender: google
    assert adapter.kalender_ueber_cloud(ordner="data/kalender_arbeit")
    assert ke.pruefen(ke.neu("kalender-x", "lokal", "data/kalender_x")) == []
    assert ke.pruefen(dict(ke.neu("kalender-x", "dropbox"))) != []
    assert adapter.alle() == {}                                       # keine Anschlüsse


def test_cli_kalender_quelle(monkeypatch, tmp_path):
    from zentrale_cli import haupt
    _mitte_spiel(monkeypatch, tmp_path)
    monkeypatch.setattr(befehle, "WURZEL", str(tmp_path))
    term = Spiel()
    assert haupt.main(["adapter", "calendar"], term) == 0
    assert "Calendar source: google (not set" in term.text
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "lokal"], term) == 0
    assert "google → lokal" in term.text and ke.quelle() == "lokal"
    term = Spiel()
    assert haupt.main(["adapter", "calendar", "icloud"], term) == 2
    term = Spiel()
    befehle.adapter_liste(term)
    assert "Calendar source: lokal" in term.text
