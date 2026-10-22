"""Recherche nach der KI-Bibel (memory/ki/bibel/recherche.md, 2026-10-22).

Anlass: das Jeans-Gespräch vom 14.10. — vier Suchen, keine Seite gelesen,
dann „gibt es wohl nicht". Geprüft wird, was Python sehen kann:

1. Werkzeug-Texte von web_search/fetch_url (gross): was, wann, was nicht;
   kein festes „muss Sasha bestätigen" mehr (W-03), der Satz zum
   Freigabestand kommt beim Senden mit dem echten Stand dazu.
2. Das Ergebnis von web_search nennt auf gross den nächsten Schritt
   (die besten Treffer lesen), klein behält seinen gemessenen Kopf.
3. Der Prüfer meldet ein „gibt es nicht", wenn nur Suchtreffer da waren.
4. Der Prompt der Schiene gross hat die Recherche-Regel, klein nicht.
"""
import pytest

import ai_config
import ehrlichkeit
import erlaubnis
import web
import werkzeug_register
from profil import gross, klein
from profil.modelle import qwen

NETZ = ("web_search", "fetch_url")


def _text(tools, name):
    return next(t["function"]["description"] for t in tools
                if t["function"]["name"] == name)


# ── 1. Werkzeug-Texte ──────────────────────────────────────────────────

def test_gross_texte_sagen_was_wann_und_was_nicht():
    suche, seite = _text(gross.TOOLS, "web_search"), _text(gross.TOOLS, "fetch_url")
    assert "Vorschautext" in suche and "nicht den Inhalt" in suche
    assert "fetch_url" in suche and "1–6 Wörter" in suche
    assert "Adresse nennt" in seite and "Anmeldung" in seite
    for t in (suche, seite):
        assert "bestätigen" not in t and "sparsam" not in t


def test_klein_texte_bleiben_wie_gemessen():
    # klein ist der gemessene Kanon: dort steht der alte Satz weiter.
    assert "Jede Suche muss Sasha bestätigen" in _text(klein.TOOLS, "web_suche")


@pytest.fixture
def freigabe(monkeypatch):
    monkeypatch.setattr(ai_config, "_save", lambda: None)
    erlaubnis.gespraech_beginnt("__leer__")
    erlaubnis.gespraech_beginnt(None)

    def setzen(namen):
        ai_config.set_override("immer_erlaubt", list(namen))
    yield setzen
    ai_config.set_override("immer_erlaubt", None)
    ai_config._config.pop("immer_erlaubt", None)


def test_freigabe_satz_folgt_dem_echten_stand(freigabe):
    freigabe(["web_search"])
    tools = erlaubnis.mit_freigabe(gross.TOOLS)
    assert _text(tools, "web_search").endswith(erlaubnis.FREIGEGEBEN)
    assert _text(tools, "fetch_url").endswith(erlaubnis.GEFRAGT)
    freigabe([])
    tools = erlaubnis.mit_freigabe(gross.TOOLS)
    assert all(_text(tools, n).endswith(erlaubnis.GEFRAGT) for n in NETZ)


def test_freigabe_aendert_nur_die_netz_werkzeuge_und_nichts_am_original(freigabe):
    freigabe(["web_search", "fetch_url"])
    vorher = [dict(t["function"]) for t in gross.TOOLS]
    tools = erlaubnis.mit_freigabe(gross.TOOLS)
    assert [t["function"] for t in gross.TOOLS] == vorher       # Original unberührt
    assert gross.TOOLS == werkzeug_register.schema("gross")
    anders = [n["function"]["name"] for n, a in zip(tools, gross.TOOLS) if n != a]
    assert anders == list(NETZ)
    # klein-Namen (web_suche, hole_url) bleiben, wie sie sind.
    assert erlaubnis.mit_freigabe(klein.TOOLS) == klein.TOOLS


def test_qwen_zuschnitt_laesst_die_netz_texte_ganz():
    zugeschnitten = qwen.werkzeuge(gross.TOOLS)
    for n in NETZ:
        assert _text(zugeschnitten, n) == _text(gross.TOOLS, n)


# ── 2. Ergebnis von web_search ─────────────────────────────────────────

TREFFER = [{"title": "Jeans W32", "url": "https://laden.de/jeans", "snippet": "Slim"}]


@pytest.fixture
def netz(monkeypatch):
    web.suche_aus_zuruecksetzen()

    def setzen(ergebnis):
        monkeypatch.setattr(web, "_searxng_search", lambda q, n: ergebnis)
    yield setzen
    web.suche_aus_zuruecksetzen()


def test_gross_ergebnis_nennt_den_naechsten_schritt(netz):
    netz(TREFFER)
    r = web.suche("jeans w32", gross=True)
    assert r.startswith(web.SUCHE_HINWEIS_GROSS)
    assert "fetch_url lesen, bevor du antwortest oder etwas verneinst" in r
    assert "laut Suchtreffer" not in r
    assert "Web-Suche 'jeans w32' - 1 Treffer:" in r


def test_klein_ergebnis_bleibt(netz):
    netz(TREFFER)
    assert web.suche("jeans w32").startswith(web.SUCHE_HINWEIS)


def test_keine_treffer_auf_gross_schlaegt_andere_woerter_vor(netz):
    netz([])
    assert web.suche("xyz") == "Keine Treffer für 'xyz'."
    assert web.suche("xyz", gross=True).endswith(web.KEINE_TREFFER_GROSS)


# ── 3. Prüfer: „gibt es nicht" ohne gelesene Seite ─────────────────────

def _schritt(name, text="", status="ok"):
    return ehrlichkeit.Schritt(name, {}, status, text)


SUCHE = _schritt("web_search", web.SUCHE_HINWEIS_GROSS
                 + "\nWeb-Suche 'jeans w32' - 1 Treffer:\n1. Jeans\n   https://laden.de")
LEER = _schritt("web_search", "Keine Treffer für 'jeans w32'.")
GELESEN = _schritt("fetch_url", "Inhalt von https://laden.de:\nJeans W32, vorrätig.")
NEIN = "Eine schwarze Jeans in W32 gibt es wohl nicht."


def _arten(antwort, protokoll, **kw):
    return [b["art"] for b in ehrlichkeit.befunde(antwort, protokoll, **kw)]


def test_verneinung_nach_nur_suchtreffern_ist_ein_befund():
    b = ehrlichkeit.befunde(NEIN, [SUCHE])
    assert [x["art"] for x in b] == ["ungelesen"] and b[0]["satz"] == NEIN
    zeile = ehrlichkeit.hinweis(b)
    assert "keine Seite gelesen" in zeile and "fetch_url" in zeile
    assert ehrlichkeit.warnungen(b)[0].startswith("⚠ ‚Gibt es nicht' ohne gelesene Seite")


@pytest.mark.parametrize("satz", [
    "Ich habe nichts gefunden.",
    "Die Jeans ist nirgends zu bekommen.",
    "So eine Jeans scheint es nicht zu geben.",
    "Keinen Laden mit W32 gefunden."])
def test_verneinungen_werden_erkannt(satz):
    assert _arten(satz, [SUCHE]) == ["ungelesen"]


def test_kein_befund_wenn_gelesen_ohne_treffer_oder_ohne_verneinung():
    assert "ungelesen" not in _arten(NEIN, [SUCHE, GELESEN])
    assert "ungelesen" not in _arten(NEIN, [LEER])
    assert "ungelesen" not in _arten(NEIN, [])
    assert "ungelesen" not in _arten("Bei laden.de gibt es sie für 59 €.", [SUCHE])
    assert "ungelesen" not in _arten("Gibt es die Jeans nicht auch in W33?", [SUCHE])


def test_feld_nicht_gefunden_zaehlt_auch_ohne_satzmuster():
    class Auskunft:
        nicht_gefunden = ["Jeans W32"]
        erledigt = ()
        fragt_erlaubnis = False
        schiebt_auf = False
        auftrag = None
    b = ehrlichkeit.befunde("Leider Fehlanzeige.", [SUCHE], auskunft=Auskunft())
    assert [(x["art"], x["quelle"]) for x in b] == [("ungelesen", "auskunft")]


def test_wiederholter_befund_sagt_was_jetzt_zu_tun_ist():
    b = ehrlichkeit.befunde(NEIN, [SUCHE])
    text = ehrlichkeit.hinweis(b, runde=2, runden=3, wiederholt=("ungelesen",))
    assert ehrlichkeit._WIEDER["ungelesen"] in text


# ── 4. Prompt ──────────────────────────────────────────────────────────

def test_recherche_regel_nur_auf_gross():
    text = gross.system()
    assert "## Recherche" in text
    assert "statt aus deinem Trainingswissen zu schreiben" in text
    assert "8–20" in text
    assert "## Recherche" not in klein.system()
