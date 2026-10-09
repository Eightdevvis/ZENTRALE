"""
Desk View mit Kacheln (2026-10-10, memory/system/desk_view.md): die
+-Auswahl (Registrierung), der Kalender-Dialog, Holen im Hintergrund aus dem
Puffer, blättern, `o` → /api/kachel/aktion → zeigen, enter greift auch
Kacheln, und die Datei (core/desk.py) mit neuer Kachel und Rückfall-Text.
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
from tui.ansichten import desk_kacheln, desk_neu

WOCHE = {"modus": "fest", "von": "2026-10-12", "bis": "2026-10-18"}


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
    d.zeigen = lambda ansicht, ziel: d.gesprungen.append((ansicht, ziel)) or True
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


def kachel_anlegen(d, name="k"):
    """Desk anlegen, öffnen, + → „kalender" → Dialog."""
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

def test_kalender_steht_im_waehler_nach_zettel_und_bild(ansicht):
    assert [a.neu_label for a in ansicht.arten.anlegbar()] == ["zettel", "bild", "kalender"]


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


# ── Kalender-Dialog ───────────────────────────────────────────────────

def test_dialog_standard_mitlaufend_7_tage_und_grenze_31():
    import curses
    m = desk_neu.KalenderDialog(date(2026, 10, 14))
    zeilen, _cur = m.anzeige(40, 10)
    assert "mitlaufend" in zeilen[0] and zeilen[1] == "tage  7" and "7 tage · woche" in zeilen
    m.taste(curses.KEY_DOWN)
    m.taste(127); m.taste(127)
    for c in "40":
        m.taste(ord(c))
    assert m.taste(10) is None and "höchstens 31 tage" in m.anzeige(40, 10)[0][-1]
    m.taste(127); m.taste(127); m.taste(ord("9"))
    assert m.taste(10) == "speichern"
    assert m.aenderungen() == {"ref": {"modus": "mitlaufend", "tage": 9}}


def test_dialog_fest_von_bis():
    import curses
    m = desk_neu.KalenderDialog(date(2026, 10, 14))
    m.taste(curses.KEY_RIGHT)                     # → fest
    assert m.felder() == ["modus", "von", "bis"]
    m.taste(curses.KEY_DOWN); m.taste(curses.KEY_DOWN)   # bis
    for _ in range(10):
        m.taste(127)
    for c in "2026-11-30":
        m.taste(ord(c))
    assert m.taste(10) is None and "höchstens 31" in m.fehler
    for _ in range(2):
        m.taste(127)
    for c in "02":
        m.taste(ord(c))
    assert m.taste(10) == "speichern"
    assert m.aenderungen()["ref"] == {"modus": "fest", "von": "2026-10-14", "bis": "2026-11-02"}
    assert m.taste(27) == "abbrechen"


def test_startgroesse_woche_und_monat():
    assert desk_neu.kalender_groesse({"modus": "mitlaufend", "tage": 7}) == (92, 9)
    w, h = desk_neu.kalender_groesse(WOCHE)
    assert (w, h) == (92, 9)
    w, h = desk_neu.kalender_groesse({"modus": "fest", "von": "2026-10-01", "bis": "2026-10-31"})
    assert w == 7 * 11 + 6 + 2 and h == 1 + 5 * 3 + 2
    # mitlaufend 31 Tage: bis zu 6 Wochen, je nach Wochentag
    assert desk_neu.kalender_groesse({"modus": "mitlaufend", "tage": 31})[1] == 1 + 6 * 3 + 2


# ── Ganzer Weg in der Ansicht ─────────────────────────────────────────

def test_kalender_kachel_anlegen_holen_speichern(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d)
    assert isinstance(m, desk_neu.KalenderDialog) and D["modal_neu"] is not None
    m.taste(curses.KEY_RIGHT)                     # fest, von/bis tippen
    m.werte.update(von="2026-10-12", bis="2026-10-18")
    d.taste(10)
    c = D["canvas"]
    assert D["modal"] is None and c.modus == "greifen"
    el = c.element(c.fokus)
    assert el["art"] == "kachel" and el["kachel"]["ref"] == WOCHE and (el["w"], el["h"]) == (92, 9)
    d.taste(10)                                   # ablegen → gespeichert
    knoten = lies("k")["nodes"][0]
    assert knoten["zentrale_kachel"] == {"v": 1, "app": "kalender", "art": "ausschnitt", "ref": WOCHE}
    assert knoten["type"] == "text" and (knoten["width"], knoten["height"]) == (920, 180)
    zeichne(d)                                    # holt (gleich, im Test)
    assert ("POST", "/api/kachel", {"app": "kalender", "art": "ausschnitt", "ref": WOCHE,
                                    "w": 90, "h": 7, "oben": 0}) in d.aufrufe
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
    assert el2["kachel"]["ref"] == WOCHE


def test_blaettern_holt_neu_und_zeigt_den_rest(ansicht, termine):
    import curses
    d, D = ansicht, ansicht.DESK
    m = kachel_anlegen(d, "b")
    m.taste(curses.KEY_RIGHT)
    m.werte.update(von="2026-10-12", bis="2026-10-18")
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
    assert d.gesprungen == [("kalender", date.today().isoformat())]
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
    d.zeigen = lambda ansicht, ziel: False
    d.taste(ord("o"))
    assert "kalender" in D["msg"] and "nicht öffnen" in D["msg"]


# ── Puffer: nie warten, Fehler, Rückfall ──────────────────────────────

def kachel_el(**mehr):
    return dict({"id": "k", "art": "kachel", "x": 0, "y": 0, "w": 40, "h": 6,
                 "kachel": {"v": 1, "app": "kalender", "art": "ausschnitt", "ref": WOCHE}}, **mehr)


def test_pflegen_startet_nur_was_faellig_ist():
    el = kachel_el()
    gestartet = []
    desk_kacheln.pflegen([el, {"id": "z", "art": "notiz"}], None, gestartet.append, uhr=lambda: 0)
    assert len(gestartet) == 1 and el["_holt"]
    desk_kacheln.pflegen([el], None, gestartet.append, uhr=lambda: 0)
    assert len(gestartet) == 1                    # läuft schon: nicht nochmal


def test_ttl_und_unveraendert():
    el = kachel_el()
    antworten = [{"zeilen": [[["a", "dim"], ["b", "erfunden"]]], "text": "a", "stand": "s1",
                  "ttl": 60, "oben": 0, "oben_max": 0},
                 {"unveraendert": True, "stand": "s1", "ttl": 60}]
    gesendet = []

    def api(pfad, method, body):
        gesendet.append(body)
        return antworten.pop(0)
    desk_kacheln.holen(el, api, uhr=lambda: 100)
    assert el["_inhalt"]["zeilen"] == [[("a", "dim"), ("b", "dim")]]   # unbekannte Rolle → dim
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
    d = desk.speichern("d", [{"id": "k", "art": "kachel", "x": 1, "y": 2, "w": 10, "h": 4,
                              "kachel": {"v": 1, "app": "kalender", "art": "ausschnitt",
                                         "ref": WOCHE}, "rueckfall": "Kalender"}])
    assert d["elemente"][0]["art"] == "kachel" and d["elemente"][0]["titel"] == "Kalender"
    # später: der Verweis ändert sich nie, auch wenn die TUI etwas anderes schickt
    desk.speichern("d", [{"id": "k", "art": "kachel", "x": 1, "y": 2, "w": 10, "h": 4,
                          "kachel": {"v": 1, "app": "anders", "art": "x", "ref": {}}}])
    assert lies("d")["nodes"][0]["zentrale_kachel"]["app"] == "kalender"
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
