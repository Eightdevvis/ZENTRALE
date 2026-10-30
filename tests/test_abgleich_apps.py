"""Was ein Gerät abgleicht, je App (core/abgleich_apps.py, memory/hub/cloud_app.md):
Tabelle aus eingebauten Apps + Manifesten, geschnitten mit der Positivliste;
Übernahme der alten Bereichs-Wahl; wer Daten hat; wer noch fragen muss.
Abgleich über die Cloud mit zwei Geräten: tests/test_abgleich_http.py."""
import pytest

import abgleich_apps
import abgleich_auswahl as auswahl
import ai_config
import app_verwaltung
import apps
import eingebaute_apps

ALLE_BEREICHE = ["lists", "notes", "calendar", "graphs", "memory", "conversations",
                 "documents", "desk", "apps", "mail", "music", "tutor"]


@pytest.fixture
def einst(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    return ai_config._config


def _app(ordner, name, daten_toml):
    d = ordner / name
    d.mkdir(parents=True)
    (d / "app.toml").write_text(f'name = "{name}"\nversion = "1"\nvorlage = "desk"\n{daten_toml}')
    return d


# Der Adapter ist Pflicht (memory/hub/adapter.md); ohne Konto ohne Zugangsdaten.
NUR_ADAPTER = ["data/adapter/anschluesse/*.json", "data/adapter/plugs/*.json", "data/adapter/bruecke/**"]


# ── Die Tabelle ────────────────────────────────────────────────────────

def test_jedes_muster_der_positivliste_gehoert_genau_einer_app():
    alle = {**eingebaute_apps.EINGEBAUT, **eingebaute_apps.ERSATZ}
    for m in auswahl.ABGLEICH:
        treffer = [n for n, e in alle.items() if m in e.get("daten", {}).get("muster", [])]
        assert len(treffer) == 1, f"{m}: {treffer} — in core/eingebaute_apps.py eintragen"
    tab = abgleich_apps.tabelle()
    assert sorted(x for a in tab.values() for x in a["muster"]) == sorted(auswahl.ABGLEICH)


def test_cloud_ist_eingebaute_app_ohne_daten():
    assert eingebaute_apps.EINGEBAUT["cloud"].get("dienst") is True
    assert "cloud" not in abgleich_apps.tabelle()


def test_daten_aus_dem_manifest_lesen():
    m = {"daten": {"muster": ["data/x.json", "../x", "/etc/passwd", "~/.ssh/id", "a\\b",
                              "data/../ai_config.json", "", "data/x.json"],
                   "abgleichen": True}}
    assert apps.daten(m) == {"muster": ["data/x.json"], "abgleichen": True}
    assert apps.daten({"daten": {"muster": ["data/x.json"]}})["abgleichen"] is False   # deny by default
    assert apps.daten({}) is None


def test_manifest_kann_der_positivliste_nicht_entkommen(einst, tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_APPS_ORDNER", str(tmp_path / "apps"))
    _app(tmp_path / "apps", "boese",
         '[daten]\nmuster = ["data/ai_config.json", "../x", "data/**", "data/mail_secrets.enc",\n'
         '          "data/lists.json"]\nabgleichen = true\n')
    tab = abgleich_apps.tabelle()
    assert "boese" not in tab                                  # nichts Erlaubtes übrig
    assert tab["fokus"]["muster"] == ["data/lists.json", "data/features.json"]   # erste gewinnt
    abgleich_apps.setzen({"boese": True, "fokus": False})
    muster = abgleich_apps.muster()
    assert not auswahl.passt("data/ai_config.json", muster)
    assert not auswahl.passt("data/lists.json", muster)


def test_abgleichen_false_bleibt_auf_dem_geraet(einst, tmp_path, monkeypatch):
    monkeypatch.setenv("ZENTRALE_APPS_ORDNER", str(tmp_path / "apps"))
    _app(tmp_path / "apps", "fremd", '[daten]\nmuster = ["data/notes.json"]\nabgleichen = false\n')
    assert "fremd" not in abgleich_apps.tabelle()


def test_tutor_mit_eigenem_daten_ersetzt_den_ersatz(einst, tmp_path, monkeypatch):
    d = tmp_path / "tutor"
    d.mkdir()
    (d / "app.toml").write_text('name = "tutor"\ntitel = "Tutor"\nstart = "x"\nadresse = "http://127.0.0.1:9"\n'
                                '[daten]\nmuster = ["tutor/data/staende/**", "tutor/data/es/**"]\n'
                                'abgleichen = true\n')
    monkeypatch.setenv("ZENTRALE_APP_PFAD_TUTOR", str(d))
    assert abgleich_apps.tabelle()["tutor"]["muster"] == ["tutor/data/staende/**", "tutor/data/es/**"]
    # GET /api/apps zeigt daten
    eintrag = next(e for e in app_verwaltung.liste() if e["name"] == "tutor")
    assert eintrag["daten"] == {"muster": ["tutor/data/staende/**", "tutor/data/es/**"],
                                "abgleichen": True}


def test_api_apps_ohne_daten_ist_null():
    assert all(e["daten"] is None for e in app_verwaltung.liste())


# ── Übernahme von abgleich_bereiche ───────────────────────────────────

def test_nicht_gesetzt_heisst_alles(einst):
    assert abgleich_apps.entscheidungen() is None
    # Ohne Kalender-Anschluss und ohne Konto: keine Termine, keine Zugangsdaten.
    assert abgleich_apps.muster() == [m for m in auswahl.ABGLEICH
                                      if m not in ("data/kalender/**", "data/adapter/geheim.enc")]
    assert abgleich_apps.offen("/gibt/es/nicht") == []


def test_alte_wahl_alles_wird_zu_allen_apps_und_gleicht_dasselbe_ab(einst):
    """Sashas Stand nach dem ersten Setup: alle Bereiche, Weg mitte, http."""
    einst.update(abgleich_bereiche=list(ALLE_BEREICHE), abgleich_weg="mitte",
                 abgleich_mitte_art="http")
    e = abgleich_apps.entscheidungen()
    # Apps that came after the old areas (cloud_folder, 2026-10-29) are not
    # part of the old choice: they ask once, like any new app with data
    # (schematix, 2026-10-30, too).
    later = {"cloud_folder", "schematix"}
    assert e == {n: True for n, a in abgleich_apps.tabelle().items()
                 if not a["pflicht"] and n not in later}
    assert sorted(abgleich_apps.muster()) == sorted(
        m for m in abgleich_apps.jetzt_erlaubt(auswahl.ABGLEICH)
        if m not in ("data/cloud/**", "data/schematix/**"))
    assert abgleich_apps.offen("/gibt/es/nicht", lambda: set()) == []


def test_alte_wahl_teilweise(einst):
    einst["abgleich_bereiche"] = ["lists", "memory", "tutor"]
    e = abgleich_apps.entscheidungen()
    assert e["fokus"] is True and e["tutor"] is True and e["notizen"] is False
    assert "assistent" not in e            # memory ohne conversations: fragt einmal
    m = abgleich_apps.muster()
    assert auswahl.passt("data/lists.json", m) and not auswahl.passt("data/gedaechtnis/a.md", m)


def test_alte_wahl_leer_ist_nichts(einst):
    einst["abgleich_bereiche"] = []
    assert set(abgleich_apps.entscheidungen().values()) == {False}
    assert abgleich_apps.muster() == NUR_ADAPTER      # Pflicht: der Adapter gleicht immer ab


def test_neue_wahl_gilt_vor_der_alten_und_die_alte_bleibt_stehen(einst):
    einst["abgleich_bereiche"] = list(ALLE_BEREICHE)
    abgleich_apps.setzen({"mail": False})
    assert ai_config._overrides["abgleich_apps"]["mail"] is False
    assert ai_config._overrides["abgleich_apps"]["fokus"] is True     # übernommen
    assert einst["abgleich_bereiche"] == ALLE_BEREICHE
    assert not auswahl.passt("data/mail_rules.json", abgleich_apps.muster())


# ── Wer hat Daten, wer fragt ──────────────────────────────────────────

def test_frisch_hat_niemand_daten(einst, tmp_path):
    (tmp_path / "data").mkdir()
    assert abgleich_apps.mit_daten(str(tmp_path), set()) == []


def test_daten_hier_oder_in_der_cloud(einst, tmp_path):
    (tmp_path / "data" / "gedaechtnis" / "t").mkdir(parents=True)
    (tmp_path / "data" / "gedaechtnis" / "t" / "a.md").write_text("x")
    (tmp_path / "data" / "g_schlaf.json").write_text("{}")
    (tmp_path / "data" / ".notes.json.1.2.tmp").write_text("x")      # Zwischendatei zählt nicht
    assert abgleich_apps.mit_daten(str(tmp_path)) == ["graph", "assistent"]
    assert abgleich_apps.mit_daten(str(tmp_path), {"data/notes.json", "tutor/data/es/a.json"}) \
        == ["notizen", "graph", "assistent", "tutor"]


def test_offen_nur_unentschiedene_mit_daten(einst, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "lists.json").write_text("[]")
    abgleich_apps.setzen({})
    assert abgleich_apps.offen(str(tmp_path)) == ["fokus"]
    assert abgleich_apps.offen(str(tmp_path), lambda: {"data/melodies.json"}) == ["fokus", "klavier"]
    abgleich_apps.setzen({"fokus": False})
    assert abgleich_apps.offen(str(tmp_path)) == []
    assert abgleich_apps.muster() == NUR_ADAPTER
