"""
Desk View mit Kacheln (2026-10-10, memory/system/desk_view.md): die
+-Auswahl (eigene Arten + Katalog des Hubs), der Dialog aus den Feldern des
Katalogs, Holen im Hintergrund aus dem Puffer, blättern, `o` →
/api/kachel/aktion → Adresse → zeigen, enter greift auch Kacheln, und die
Datei (core/desk.py) mit neuer Kachel (Adresse) und Rückfall-Text.
Die Ansicht spricht über den Flask-Test-Client mit dem echten Backend.
"""
import io
import json
import os
import urllib.error
from datetime import date

import pytest

import desk
import kalender
from tui.ansichten import desk_kacheln

WOCHE = {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"}
WOCHE_ADR = "zentrale://kalender/ausschnitt?bis=2026-10-18&modus=fest&von=2026-10-12"


class Schirm:
    def __init__(self):
        self.folge = []

    def getch(self):
        return self.folge.pop(0) if self.folge else -1

    def getmaxyx(self):
        return (40, 140)

    def __getattr__(self, name):
        return lambda *a, **k: None


@pytest.fixture
def client():
    from ui.app import app
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def termine():
    kalender.ensure_init()
    kalender.add_entry("termine", "2026-10-12", "Arzt", "09:00")
    for i in range(9):
        kalender.add_entry("termine", "2026-10-14", "Probe %d" % i, "1%d:00" % i)


@pytest.fixture
def ansicht(monkeypatch, client):
    import curses
    from tui.ansichten import desk as desk_ansicht
    from tui.ansichten import kontext
    monkeypatch.setattr(curses, "keyname", lambda c: b"")
    aufrufe = []

    def api(pfad, method="GET", body=None, timeout=3.0):
        aufrufe.append((method, pfad, body))
        r = client.open(pfad, method=method, json=body)
        if r.status_code >= 400:
            raise urllib.error.HTTPError(pfad, r.status_code, "x", {}, io.BytesIO(r.data))
        return r.get_json()
    monkeypatch.setattr(desk_ansicht, "api_call", api)
    z = kontext.Kontext(Schirm(), None, False, None)
    z.apply_theme("night")
    d = desk_ansicht.Desk(z)
    d.starten = lambda f: f()                    # Hintergrund gleich ausführen
    d.aufrufe = aufrufe
    d.gesprungen = []
    d.zeigen = lambda adresse: d.gesprungen.append(adresse) or True
    return d


def lies(name):
    with open(os.path.join(desk.ordner(), name + ".canvas"), encoding="utf-8") as f:
        return json.load(f)


def tippe(d, text):
    for b in text.encode("utf-8"):
        d.taste(b)


def zeichne(d):
    d.draw_desk(2, 0, 38, 140)


def sichtbar(d):
    c = d.DESK["canvas"]
    return "\n".join("".join(t for _x, t, _r in z) for z in c.bild(c.vh, c.vw))


def fest_tippen(m, von, bis):
    """Im Dialog auf „fest" stellen und von/bis tippen."""
    import curses
    m.taste(curses.KEY_RIGHT)                     # art: → fest
    for wert in (von, bis):
        m.taste(curses.KEY_DOWN)
        for _ in range(10):
            m.taste(127)
        for c in wert:
            m.taste(ord(c))


def kachel_anlegen(d, name="k"):
    """Desk anlegen, öffnen, + → „kalender" (aus dem Katalog) → Dialog."""
    desk.anlegen(name)
    d.oeffnen()
    d.taste(10)
    zeichne(d)
    d.taste(ord("+"))
    labels = [a.neu_label for a in d.DESK["art_wahl"]["arten"]]
    d.DESK["art_wahl"]["sel"] = labels.index("kalender")
    d.taste(10)
    return d.DESK["modal"]


# ── Wähler hinter + (die Registrierung der Arten) ────────────────────

def test_waehler_eigene_arten_dann_der_katalog(ansicht):
    d, D = ansicht, ansicht.DESK
    desk.anlegen("w")
    d.oeffnen(); d.taste(10); zeichne(d)
    d.taste(ord("+"))
    assert [a.neu_label for a in D["art_wahl"]["arten"]] == ["zettel", "bild", "kalender"]
    assert ("GET", "/api/kacheln", None) in d.aufrufe


def test_neue_app_im_katalog_steht_von_selbst_im_waehler(ansicht, monkeypatch):
    import types
    import kacheln
    probe = types.SimpleNamespace(APP="probe", RECHTE=("lesen",), kachel=lambda *a: {},
                                  ARTEN={"x": {"titel": "probe", "min": (4, 2)}})
    monkeypatch.setitem(kacheln.QUELLEN, "probe", probe)
    d, D = ansicht, ansicht.DESK
    desk.anlegen("p")
    d.oeffnen(); d.taste(10); zeichne(d)
    d.taste(ord("+"))
    labels = [a.neu_label for a in D["art_wahl"]["arten"]]
    assert labels == ["zettel", "bild", "kalender", "probe"]
    D["art_wahl"]["sel"] = 3
    d.taste(10)                                   # ohne Felder: gleich in die Hand
    el = D["canvas"].element(D["canvas"].fokus)
    assert el["kachel"] == {"v": 2, "adresse": "zentrale://probe/x"} and (el["w"], el["h"]) == (6, 4)


def test_ohne_backend_bleiben_zettel_und_bild(ansicht, monkeypatch):
    from tui.ansichten import desk as desk_ansicht
    d, D = ansicht, ansicht.DESK
    desk.anlegen("o")
    d.oeffnen(); d.taste(10); zeichne(d)
    echt = desk_ansicht.api_call

    def ohne_katalog(pfad, *a, **k):
        if pfad == "/api/kacheln":
            raise OSError("aus")
        return echt(pfad, *a, **k)
    monkeypatch.setattr(desk_ansicht, "api_call", ohne_katalog)
    d.taste(ord("+"))
    assert [a.neu_label for a in D["art_wahl"]["arten"]] == ["zettel", "bild"]
    assert "kacheln nicht lesbar" in D["msg"]


def test_plus_enter_macht_weiter_schnell_einen_zettel(ansicht):
    d, D = ansicht, ansicht.DESK
    desk.anlegen("z")
    d.oeffnen(); d.taste(10); zeichne(d)
    d.taste(ord("+"))
    assert D["art_wahl"]["sel"] == 0
    d.taste(10)
    assert D["art_wahl"] is None and D["canvas"].modus == "greifen"
    d.taste(10)
    assert desk.laden("z")["elemente"][0]["art"] == "notiz"


def test_dialog_esc_legt_nichts_hin(ansicht):
    d, D = ansicht, ansicht.DESK
    kachel_anlegen(d, "e")
    d.taste(27)
    assert D["modal"] is None and D["modal_neu"] is None and D["canvas"].elemente == []


# ── Dialog aus dem Katalog ────────────────────────────────────────────

def test_dialog_kommt_aus_den_feldern_des_katalogs(ansicht):
    from tui.bausteine.feld_dialog import FeldDialog
    m = kachel_anlegen(ansicht, "f")
    assert isinstance(m, FeldDialog) and m.kopf == "kalender auf den desk"
    zeilen, _c = m.anzeige(44, 10)
    assert zeilen[0] == "art   ‹ mitlaufend ›" and zeilen[1] == "tage  7"


def test_hub_sagt_nein_dialog_bleibt_offen(ansicht, monkeypatch):
    """Was der Dialog durchlässt, prüft der Hub noch einmal; sagt er nein,
    bleibt der Dialog mit seinem Grund offen."""
    import kacheln
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "h")
    monkeypatch.setitem(kacheln.kachel_kalender.ARTEN["ausschnitt"]["felder"][1],
                        "grenzen", {"min": 1, "max": 5})
    d.taste(10)
    assert D["modal"] is m and "höchstens 5 tage" in m.fehler and D["canvas"].elemente == []


# ── Ganzer Weg in der Ansicht ─────────────────────────────────────────

def test_kalender_kachel_anlegen_holen_speichern(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d)
    assert D["modal_neu"] is not None
    fest_tippen(m, "2026-10-12", "2026-10-18")
    d.taste(10)
    c = D["canvas"]
    assert D["modal"] is None and c.modus == "greifen"
    el = c.element(c.fokus)
    assert el["art"] == "kachel" and el["kachel"] == {"v": 2, "adresse": WOCHE_ADR}
    assert (el["w"], el["h"]) == (92, 9)          # bevorzugt vom Hub + Rahmen
    d.taste(10)                                   # ablegen → gespeichert
    knoten = lies("k")["nodes"][0]
    assert knoten["zentrale_kachel"] == {"v": 2, "adresse": WOCHE_ADR}
    assert knoten["type"] == "text" and (knoten["width"], knoten["height"]) == (920, 180)
    zeichne(d)                                    # holt (gleich, im Test)
    assert ("POST", "/api/kachel", {"adresse": WOCHE_ADR, "w": 90, "h": 7, "oben": 0}) in d.aufrufe
    assert el["_inhalt"]["zustand"] == "ok"
    bild = sichtbar(d)
    assert "Mo 12.10." in bild and "09:00 Arzt" in bild and "+4" in bild
    # beim nächsten Speichern wandert der Klartext als Rückfall in die Datei,
    # der Puffer nie
    d.speichern()
    knoten = lies("k")["nodes"][0]
    assert knoten["text"].startswith("Kalender 12.10.") and "09:00 Arzt" in knoten["text"]
    assert not any(k.startswith("_") for k in knoten)
    # wieder geladen: der Verweis ist derselbe, nicht kopiert
    el2 = desk.laden("k")["elemente"][0]
    assert el2["kachel"]["adresse"] == WOCHE_ADR


def test_monat_kachel_bekommt_die_monatsgroesse_vom_hub(ansicht, termine):
    """Die Startgröße hängt am Bereich — die App weiß sie, nicht die TUI."""
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "m")
    fest_tippen(m, "2026-10-01", "2026-10-31")
    d.taste(10)
    el = D["canvas"].element(D["canvas"].fokus)
    assert (el["w"], el["h"]) == (7 * 11 + 6 + 2, 1 + 5 * 3 + 2)


def test_blaettern_holt_neu_und_zeigt_den_rest(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "b")
    fest_tippen(m, "2026-10-12", "2026-10-18")
    d.taste(10); d.taste(10)
    zeichne(d)
    assert "16:00 Probe" not in sichtbar(d)
    d.taste(curses.KEY_NPAGE)
    zeichne(d)
    holungen = [a for a in d.aufrufe if a[1] == "/api/kachel"]
    assert holungen[-1][2]["oben"] == 1
    d.taste(curses.KEY_NPAGE); d.taste(curses.KEY_NPAGE); d.taste(curses.KEY_NPAGE)
    zeichne(d)
    assert [a for a in d.aufrufe if a[1] == "/api/kachel"][-1][2]["oben"] == 3   # nicht weiter
    assert "18:00 Probe" in sichtbar(d)
    d.taste(curses.KEY_PPAGE)
    zeichne(d)
    assert [a for a in d.aufrufe if a[1] == "/api/kachel"][-1][2]["oben"] == 2


def test_o_oeffnet_den_kalender_enter_greift(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    kachel_anlegen(d, "o")
    d.taste(10)                                   # Dialog: mitlaufend 7 Tage
    d.taste(10)                                   # ablegen
    zeichne(d)
    d.taste(ord("o"))
    assert ("POST", "/api/kachel/aktion") in [(a[0], a[1]) for a in d.aufrufe]
    assert d.gesprungen == ["zentrale://kalender/" + date.today().isoformat()]
    vorher = lies("o")["nodes"][0]["x"]
    d.taste(10)                                   # enter greift auch die Kachel
    assert D["canvas"].modus == "greifen"
    d.taste(curses.KEY_RIGHT); d.taste(10)
    assert lies("o")["nodes"][0]["x"] == vorher + 10


def test_o_auf_zettel_tut_nichts(ansicht):
    d, D = ansicht, ansicht.DESK
    desk.speichern(desk.anlegen("n")["name"],
                   [{"id": "a", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4}], [])
    d.oeffnen(); d.taste(10)
    D["canvas"].fokus = "a"
    d.taste(ord("o"))
    assert d.gesprungen == [] and not any(a[1].startswith("/api/kachel") for a in d.aufrufe)


def test_unbekanntes_ziel_wird_gesagt(ansicht, termine):
    d, D = ansicht, ansicht.DESK
    kachel_anlegen(d, "u")
    d.taste(10); d.taste(10)
    d.zeigen = lambda adresse: False
    d.taste(ord("o"))
    assert "zentrale://kalender/" in D["msg"] and "nicht öffnen" in D["msg"]


# ── Puffer: nie warten, Fehler, Rückfall ──────────────────────────────

def kachel_el(**mehr):
    return dict({"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 40, "h": 6,
                 "kachel": {"v": 2, "adresse": WOCHE_ADR}}, **mehr)


def test_pflegen_startet_nur_was_faellig_ist():
    el = kachel_el()
    gestartet = []
    desk_kacheln.pflegen([el, {"id": "z", "art": "notiz"}], None, gestartet.append, uhr=lambda: 0)
    assert len(gestartet) == 1 and el["_holt"]
    desk_kacheln.pflegen([el], None, gestartet.append, uhr=lambda: 0)
    assert len(gestartet) == 1                    # läuft schon: nicht nochmal


def test_ttl_und_unveraendert():
    el = kachel_el()
    antworten = [{"zeilen": [[["a", "kopf"], ["b", "erfunden"]]], "text": "a", "stand": "s1",
                  "ttl": 60, "oben": 0, "oben_max": 0},
                 {"unveraendert": True, "stand": "s1", "ttl": 60}]
    gesendet = []

    def api(pfad, method, body):
        gesendet.append(body)
        return antworten.pop(0)
    desk_kacheln.holen(el, api, uhr=lambda: 100)
    # Rolle der App → Rolle der TUI-Palette; Unbekanntes wie „text"
    assert el["_inhalt"]["zeilen"] == [[("a", "dim"), ("b", "ink")]]
    assert gesendet[0] == {"adresse": WOCHE_ADR, "w": 38, "h": 4, "oben": 0}
    assert not desk_kacheln.faellig(el, 159) and desk_kacheln.faellig(el, 160)
    desk_kacheln.holen(el, api, uhr=lambda: 160)
    assert gesendet[1]["stand"] == "s1" and el["_inhalt"]["zeilen"][0][0] == ("a", "dim")
    assert el["_inhalt"]["bis"] == 220
    el["w"] = 50                                  # Größe anders → gleich neu
    assert desk_kacheln.faellig(el, 161)


@pytest.mark.parametrize("code,zustand", [(404, "weg"), (400, "fehler"), (503, "aus")])
def test_fehler_werden_zustaende(code, zustand):
    el = kachel_el(_inhalt={"zustand": "ok", "zeilen": [[("alt", "dim")]], "text": "alt",
                            "schluessel": None})

    def api(*a):
        raise urllib.error.HTTPError("/api/kachel", code, "x", {},
                                     io.BytesIO(b'{"fehler": "x", "text": "h\\u00f6chstens 31 tage"}'))
    desk_kacheln.holen(el, api, uhr=lambda: 0)
    assert el["_inhalt"]["zustand"] == zustand and el["_holt"] is None
    if zustand == "aus":
        assert el["_inhalt"]["zeilen"] == [[("alt", "dim")]]   # letzter Stand bleibt
    if zustand == "fehler":
        assert el["_inhalt"]["text"] == "höchstens 31 tage"


def test_zu_klein_kommt_als_aussenmass():
    el = kachel_el()
    desk_kacheln.holen(el, lambda *a: {"zu_klein": {"w": 48, "h": 2}, "ttl": 60}, uhr=lambda: 0)
    assert el["_inhalt"]["zu_klein"] == {"w": 50, "h": 4}


def test_fuer_datei_ohne_puffer_mit_rueckfall():
    el = kachel_el(_oben=2, _holt=None, _inhalt={"zustand": "ok", "text": "Kalender …", "zeilen": []})
    raus = desk_kacheln.fuer_datei(el)
    assert raus["rueckfall"] == "Kalender …" and not any(k.startswith("_") for k in raus)


# ── Datei ─────────────────────────────────────────────────────────────

def test_datei_neue_kachel_nur_mit_gueltigem_verweis():
    desk.anlegen("d")
    with pytest.raises(desk.DeskFehler):
        desk.speichern("d", [{"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 10, "h": 4,
                              "kachel": {"app": "kalender"}}])
    with pytest.raises(desk.DeskFehler):
        desk.speichern("d", [{"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 10, "h": 4,
                              "kachel": {"adresse": "https://kalender/ausschnitt"}}])
    d = desk.speichern("d", [{"id": "k", "art": "kachel", "x": 1, "y": 2, "w": 10, "h": 4,
                              "kachel": {"v": 2, "adresse": WOCHE_ADR}, "rueckfall": "Kalender"}])
    assert d["elemente"][0]["art"] == "kachel" and d["elemente"][0]["titel"] == "Kalender"
    # später: der Verweis ändert sich nie, auch wenn die TUI etwas anderes schickt
    desk.speichern("d", [{"id": "k", "art": "kachel", "x": 1, "y": 2, "w": 10, "h": 4,
                          "kachel": {"v": 2, "adresse": "zentrale://anders/x"}}])
    assert lies("d")["nodes"][0]["zentrale_kachel"] == {"v": 2, "adresse": WOCHE_ADR}
    assert lies("d")["nodes"][0]["text"] == "Kalender"


def test_weitergeblaettert_waehrend_des_holens_holt_gleich_nach():
    """Die Antwort gehört zur Lage der ANFRAGE — wurde inzwischen
    weitergeblättert, ist die Kachel sofort wieder fällig."""
    el = kachel_el()

    def api(pfad, method, body):
        el["_oben"] = 3                           # Sasha blättert, während es lädt
        return {"zeilen": [], "text": "", "stand": "s", "ttl": 60, "oben": body["oben"], "oben_max": 5}
    desk_kacheln.holen(el, api, uhr=lambda: 0)
    assert desk_kacheln.faellig(el, 1)


def test_alte_datei_mit_altem_verweis_laedt_holt_und_wird_neu_geschrieben(ansicht, termine):
    """Desks von vor 2026-10-10 tragen {v: 1, app, art, ref}: sie laden, die
    Kachel zeigt ihren Inhalt, und beim Speichern steht die Adresse drin."""
    d, D = ansicht, ansicht.DESK
    desk.anlegen("alt")
    pfad = os.path.join(desk.ordner(), "alt.canvas")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump({"nodes": [{"id": "k", "type": "text", "text": "Kalender alt",
                              "x": 0, "y": 0, "width": 920, "height": 180,
                              "zentrale_kachel": {"v": 1, "app": "kalender",
                                                  "art": "ausschnitt", "ref": WOCHE}}],
                   "edges": []}, f)
    d.oeffnen()
    d.DESK["sel"] = [x["name"] for x in D["desks"]].index("alt")
    d.taste(10)
    zeichne(d)
    el = D["canvas"].element("k")
    assert el["kachel"] == {"v": 2, "adresse": WOCHE_ADR}
    assert el["_inhalt"]["zustand"] == "ok" and "09:00 Arzt" in sichtbar(d)
    d.speichern()
    assert lies("alt")["nodes"][0]["zentrale_kachel"] == {"v": 2, "adresse": WOCHE_ADR}


# ── Größe ändern (r, 2026-10-10) ──────────────────────────────────────

def test_grenzen_aus_dem_katalog_als_aussenmass():
    el = kachel_el()
    kat = [{"app": "kalender", "art": "ausschnitt", "min": {"w": 6, "h": 2},
            "max": {"w": 50, "h": 20}}]
    assert desk_kacheln.grenzen(el, kat) == {"min": (8, 4), "max": (52, 22)}
    ohne_max = [dict(kat[0], max=None)]
    assert desk_kacheln.grenzen(el, ohne_max)["max"] == (402, 402)
    assert desk_kacheln.grenzen(el, [dict(kat[0], app="post")]) is None
    assert desk_kacheln.app_art(el) == ("kalender", "ausschnitt")


def test_kachel_groesse_aendern_holt_in_neuer_groesse(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "r")
    fest_tippen(m, "2026-10-12", "2026-10-18")
    d.taste(10); d.taste(10)
    zeichne(d)
    c = D["canvas"]
    el = c.element(c.fokus)
    w0, h0 = el["w"], el["h"]
    d.taste(ord("r"))
    assert c.modus == "groesse" and el["_grenzen"]["min"] == (8, 4)
    d.taste(curses.KEY_DOWN); d.taste(curses.KEY_DOWN); d.taste(curses.KEY_LEFT)
    zeichne(d)                                    # holt im Hintergrund (hier: gleich)
    letzte = [a for a in d.aufrufe if a[1] == "/api/kachel"][-1][2]
    assert (letzte["w"], letzte["h"]) == (w0 - 3, h0)
    d.taste(10)
    k = lies("r")["nodes"][0]
    assert (k["width"], k["height"]) == ((w0 - 1) * 10, (h0 + 2) * 20)
    assert not any(n.startswith("_") for n in k)
    # Unter das Minimum der App geht es nicht
    d.taste(ord("r"))
    for _ in range(200):
        d.taste(curses.KEY_LEFT)
    for _ in range(30):
        d.taste(curses.KEY_UP)
    assert (el["w"], el["h"]) == (8, 4) and "kleiner geht nicht" in d.tasten_text()
    d.taste(27)
    assert (el["w"], el["h"]) == (w0 - 1, h0 + 2)


def test_kachel_groesse_ohne_katalog_sagt_es(ansicht, termine, monkeypatch):
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "o")
    fest_tippen(m, "2026-10-12", "2026-10-18")
    d.taste(10); d.taste(10)
    echt = d.aufrufe
    from tui.ansichten import desk as desk_ansicht

    def kaputt(pfad, *a, **k):
        raise OSError("weg")
    monkeypatch.setattr(desk_ansicht, "api_call", kaputt)
    d.taste(ord("r"))
    assert D["canvas"].modus == "ruhe" and "größe geht gerade nicht" in d.tasten_text()
    assert echt is d.aufrufe


# ── Listen- und Graph-Kacheln (2026-10-10) ───────────────────────────

def _aus_dem_katalog(d, name, label):
    desk.anlegen(name)
    d.oeffnen()
    d.taste(10)
    zeichne(d)
    d.taste(ord("+"))
    labels = [a.neu_label for a in d.DESK["art_wahl"]["arten"]]
    d.DESK["art_wahl"]["sel"] = labels.index(label)
    d.taste(10)
    return d.DESK["modal"]


def test_liste_und_graph_aus_dem_katalog_anlegen_und_oeffnen(ansicht):
    import curses
    import graphs
    import lists
    d = ansicht
    lists.create_list("Einkauf")
    zweite = lists.create_list("Ideen")["id"]
    lists.add_item(zweite, "Kacheln bauen")
    gid = graphs.create_graph("Gewicht", "number", unit="kg")["id"]
    graphs.log_value(gid, date.today().isoformat(), 80)
    m = _aus_dem_katalog(d, "lg", "liste")
    assert [f["name"] for f in m.sichtbar()] == ["liste", "erledigte", "tiefe"]
    m.taste(curses.KEY_RIGHT)                     # liste: → Ideen (Werte von jetzt)
    d.taste(10)                                   # erledigte nein, 3 Ebenen
    d.taste(10)                                   # ablegen
    zeichne(d)
    (el,) = lies("lg")["nodes"]
    assert el["zentrale_kachel"]["adresse"] == \
        "zentrale://fokus/liste?erledigte=false&liste=%s&tiefe=3" % zweite
    assert "Kacheln bauen" in sichtbar(d)
    d.taste(ord("o"))
    assert d.gesprungen == ["zentrale://fokus/" + zweite]
    m = _aus_dem_katalog(d, "gr", "graph")
    assert [f["name"] for f in m.sichtbar()] == ["graph", "tage"]
    d.taste(10)
    d.taste(10)
    zeichne(d)
    assert "Gewicht kg" in sichtbar(d) and "80 kg" in sichtbar(d)
    d.taste(ord("o"))
    assert d.gesprungen[-1] == "zentrale://graph/" + gid
    assert len(lies("gr")["nodes"]) == 1
