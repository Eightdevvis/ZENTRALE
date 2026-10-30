"""
Die Fußleiste der TUI zeigt nur, was wirkt (tui/ansichten/fussleiste.py,
2026-10-07). Sasha: „unten die leiste ist generell weird weil sie halt
einfach nich stimmt meistens".

Der Kern-Test baut die echte TUI ohne Bildschirm (alle Ansichten, gefälschtes
Backend, ein gezeichnetes Bild), bringt sie in jeden Zustand, den die
Fußleiste kennt, und drückt JEDE beworbene Taste über die echte Verteilung
(taste_verteilen). Ändert sich danach nichts — kein Zustand, kein Aufruf ans
Backend, kein Fenster, kein Ende —, war die Beschriftung gelogen.
"""
import copy
import curses
import importlib.util
import os
import subprocess
import tempfile
import urllib.error
import threading
import time
import types

import pytest

from tui import zentrale_tui as zt
from tui import ansichten as A
from tui.ansichten import befehle, chat_befehle, fussleiste
from tui.ansichten import kalender_beispiel as kb

# Die erfundenen Daten des Bildschirm-Werkzeugs (Gespräche, Gedächtnis,
# Ablage, Projekte). Sein Cache zeigt beim Import auf einen Wegwerf-Ort.
os.environ.setdefault("ZTUI_CACHE", os.path.join(tempfile.mkdtemp(prefix="ztui-"), "c.json"))
_spec = importlib.util.spec_from_file_location(
    "tui_schirm_backend", os.path.join(os.path.dirname(__file__), "tui_schirm", "backend.py"))
SCHIRM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SCHIRM)


# ── Reine Helfer ──────────────────────────────────────────────────────

def test_codes_lesen_die_beschriftungen():
    assert fussleiste.codes("↑↓") == [[curses.KEY_UP], [curses.KEY_DOWN]]
    assert fussleiste.codes("a/s") == [[ord("a")], [ord("s")]]
    assert fussleiste.codes("/") == [[ord("/")]]
    assert fussleiste.codes("+/-") == [[ord("+")], [ord("-")]]
    assert fussleiste.codes("alt+←→") == [[27, curses.KEY_LEFT], [27, curses.KEY_RIGHT]]
    assert fussleiste.codes("ctrl+c") == [[3]]
    assert fussleiste.codes("pgup pgdn") == [[curses.KEY_PPAGE], [curses.KEY_NPAGE]]
    assert fussleiste.codes("/help") is None and fussleiste.codes("type") is None
    with pytest.raises(ValueError):
        fussleiste.codes("bild↑↓")


def test_kompakt_zeigt_nur_tasten():
    """25.10.2026: nur die Tasten, Bedeutung über '?' + Taste."""
    assert fussleiste.kompakt(["↑↓", "enter", "S"], ["/", "?"], 80) == " ↑↓ · enter · S · / · ?"
    assert fussleiste.kompakt([], [], 80) == ""


def test_kompakt_wirft_nichts_still_weg():
    """Passt es nicht, steht „…" vor '/' und '?' — die bleiben immer."""
    t = ["↑↓", "t/w/m/y", "g", "S", "R"]
    s = fussleiste.kompakt(t, ["/", "?"], 26)
    assert s.endswith("… · / · ?") and len(s) <= 26 and s.startswith(" ↑↓ · t/w/m/y")
    assert len(fussleiste.kompakt(t, ["/", "?"], 5)) == 5


# ── Die TUI ohne Bildschirm ───────────────────────────────────────────

class Schirm:
    """stdscr-Ersatz: getch liefert, was eine Taste nach sich zieht (Esc-
    Folgen), alles Zeichnen tut nichts."""

    def __init__(self):
        self.folge = []

    def getch(self):
        return self.folge.pop(0) if self.folge else -1

    def getmaxyx(self):
        return (40, 140)

    def __getattr__(self, name):
        return lambda *a, **k: None


class Store:
    def snapshot(self):
        return ({"logs": [], "uptime_s": 10}, {}, True)

    def graphs_snapshot(self):
        return ([], {})

    def cycle_snapshot(self):
        return None

    def reminders_snapshot(self):
        return []

    def projects_snapshot(self):
        return []

    def backends_snapshot(self):
        return {}


class Theme:
    def __getattr__(self, name):
        return lambda *a, **k: "night"


GRAPHEN = [{"id": "g1", "name": "schlaf", "type": "number", "unit": "h"},
           {"id": "g2", "name": "laune", "type": "number"}]
LISTEN = [{"id": "l1", "name": "einkauf", "items": [
    {"id": 1, "text": "milch", "done": False, "children": []},
    {"id": 2, "text": "brot", "done": True, "children": []}]},
    {"id": "l2", "name": "ideen", "items": []},
    {"id": "l3", "name": "reise", "items": []}]
NOTIZEN = [{"id": "n1", "title": "erste", "blocks": [
    {"id": "b1", "type": "text", "text": "hallo"},
    {"id": "b2", "type": "list", "items": [{"id": 1, "text": "a", "done": False}]}]},
    {"id": "n2", "title": "zweite", "blocks": []}]
MAILS = {"mails": [
    {"uid": 11, "from": "Anna <anna@example.org>", "subject": "Treffen", "seen": False,
     "account": "a", "category": "arbeit"},
    {"uid": 12, "from": "Bank", "subject": "Auszug", "seen": True, "account": "a"},
    {"uid": 13, "from": "Verein", "subject": "Fest", "seen": False, "account": "b"}],
    "live": False}


# Ein Desk wie ein Kreuz: Mitte und je ein Zettel oben, unten, links, rechts —
# so führt jeder Pfeil vom gewählten Kasten irgendwohin.
DESK = {"name": "Elektronik", "stand": "s1", "verbindungen": [], "elemente": [
    {"id": "m", "art": "notiz", "x": 0, "y": 0, "w": 10, "h": 4, "text": "mitte"},
    {"id": "o", "art": "notiz", "x": 0, "y": -10, "w": 10, "h": 4, "text": "oben"},
    {"id": "u", "art": "notiz", "x": 0, "y": 10, "w": 10, "h": 4, "text": "unten"},
    {"id": "l", "art": "notiz", "x": -30, "y": 0, "w": 10, "h": 4, "text": "links"},
    {"id": "r", "art": "notiz", "x": 30, "y": 0, "w": 10, "h": 4, "text": "rechts"},
    # Bild (2026-10-10): eigener Zustand desk:bild (o öffnen, f mono/farbe).
    {"id": "b", "art": "bild", "x": 30, "y": 10, "w": 14, "h": 6, "datei": "bilder/b.png",
     "titel": "", "modus": "mono"},
    # Kachel (2026-10-10): eigener Zustand desk:kachel (o öffnen, blättern).
    {"id": "k", "art": "kachel", "x": -30, "y": 10, "w": 24, "h": 6, "titel": "Kalender",
     "kachel": {"v": 2, "adresse": "zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7"}}]}


def antwort(pfad, methode):
    """Das gefälschte Backend: erfundene Daten je Pfad (Chat, Gespräche,
    Gedächtnis, Ablage, Projekte wie im Bildschirm-Werkzeug tests/tui_schirm)."""
    p = pfad.split("?")[0]
    if p.startswith("/api/schematix") or p == "/api/pieces":   # Schematix (2026-10-30)
        import _schematix_fake
        return _schematix_fake.answer(pfad, methode)
    if methode == "GET":
        d = SCHIRM._synth(pfad)
        if d is not None and not p.startswith("/api/graphs/reminders"):
            return copy.deepcopy(d)
    if p == "/api/desk-bild/quellen":             # Bilder auf dem Desk (2026-10-10)
        return {"quellen": [{"name": "foto.png", "pfad": "/x/Input/foto.png"}]}
    if p == "/api/shop/kategorien":               # Schaufenster (2026-10-10)
        return {"kategorien": [{"id": "icons", "name": "Icons", "anzahl": 2},
                               {"id": "apps", "name": "Apps", "anzahl": 0}],
                "themen": [{"thema": "pixel", "anzahl": 2}]}
    if p == "/api/shop/holen":
        return {"adresse": "zentrale://shop/icons/post", "geholt": True, "neu": True,
                "am": "2026-10-10T12:00:00+02:00"}
    if p == "/api/apps/laden":                    # Apps aus dem Laden (2026-10-25)
        return {"adresse": "zentrale://shop/apps/budget", "name": "budget", "titel": "Budget",
                "ansichten": [{"id": "browser", "titel": "im browser"},
                              {"id": "terminal", "titel": "im terminal"}],
                "gewaehlt": ["browser", "terminal"], "installiert": False, "neu": True}
    if p == "/api/apps/installieren":
        return {"name": "budget", "titel": "Budget", "ansichten": ["browser"], "neu": True}
    if p == "/api/shop/besitz":
        return {"@type": "ItemList", "itemListElement": []}
    if p == "/api/shop":
        return {"@type": "ItemList", "itemListElement": [] if "kategorie=apps" in pfad else [
            {"@type": "ListItem", "position": i + 1, "item": {
                "@type": "ImageObject", "@id": "zentrale://shop/icons/" + n, "identifier": n,
                "name": n, "description": "", "category": "icons", "keywords": ["pixel", n],
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR"}}}
            for i, n in enumerate(("post", "karte"))]}
    if p == "/api/kacheln":                       # Katalog (2026-10-10)
        return [{"app": "kalender", "art": "ausschnitt", "titel": "kalender",
                 "min": {"w": 6, "h": 2}, "bevorzugt": {"w": 90, "h": 7}, "ttl": 60,
                 "parameter": {"type": "object", "properties": {
                     "tage": {"title": "tage", "type": "integer", "default": 7}}},
                 "aktionen": ["oeffnen"], "formen": ["zeilen"]}]
    if p == "/api/kachel":                        # Kacheln (2026-10-10)
        return {"zeilen": [[["Mo 12.10.", "heute"]]], "text": "Kalender", "stand": "s",
                "ttl": 60, "oben": 0, "oben_max": 3}
    if p == "/api/kachel/aktion":
        return {"zeige": {"adresse": "zentrale://kalender/2026-10-12"}}
    if p.startswith("/api/desk-bild"):
        if p == "/api/desk-bild/vorschau":
            return {"status": "ok", "zeilen": [[["@", None], ["#", "#ff0000"]]]}
        if p == "/api/desk-bild/oeffnen":
            return {"pfad": "/gibt/es/nicht.png", "da": False, "betrachter": "system"}
        return {"datei": "bilder/foto.png", "titel": "foto", "w": 20, "h": 8}
    if p.startswith("/api/desk"):                # Desk View (2026-10-09)
        if p == "/api/desk" and methode == "GET":
            return {"desks": [{"name": "Elektronik", "elemente": 5, "geaendert": 1.0}]}
        if methode == "GET":
            return copy.deepcopy(DESK)
        return dict(copy.deepcopy(DESK), stand="s2")
    if methode != "GET":
        if p == "/api/lists" or p.endswith("/items"):
            return {"id": "l9", "name": "neu", "items": []}
        return {"ok": True}
    if p == "/api/graphs":
        return copy.deepcopy(GRAPHEN)
    if p.startswith("/api/data/"):
        return [{"date": "2026-10-06", "value": 7}]
    if p == "/api/lists":
        return copy.deepcopy(LISTEN)
    if p == "/api/projects":
        return []
    if p == "/api/calendar":
        q = dict(x.split("=", 1) for x in pfad.split("?", 1)[1].split("&")) if "?" in pfad else {}
        d = kb.api_daten(q.get("view", "week"), q.get("ref", kb.HEUTE), heute=kb.HEUTE)
        d["weekplan"] = {"lid": "l_week", "items": [
            {"id": 1, "text": "Steuer", "done": False},
            {"id": 2, "text": "Rad", "done": False}]}
        return d
    if p == "/api/notes":
        return copy.deepcopy(NOTIZEN)
    if p.startswith("/api/notes/"):
        return copy.deepcopy(NOTIZEN[0])
    if p == "/api/melodies":
        return [{"id": "m1", "name": "lied", "notes": [{"t": 0, "n": 60, "d": 50}]},
                {"id": "m2", "name": "tanz", "notes": [{"t": 0, "n": 62, "d": 50}]}]
    if p == "/api/map/braille":
        return {"bounds": [-180, -60, 180, 80], "braille": ["⠀" * 20] * 6}
    if p == "/api/mail":
        return {"categories": [{"name": "arbeit", "count": 2}, {"name": "privat", "count": 1}],
                "inbox": 3}
    if p.startswith("/api/mail"):
        return copy.deepcopy(MAILS)
    return {}


@pytest.fixture
def welt(monkeypatch, tmp_path):
    """Baut die TUI wie run_ui, nur ohne curses. -> Funktion, die ein frisches
    Bündel u liefert (jede Taste bekommt eine frische TUI)."""
    monkeypatch.setenv("ZENTRALE_NO_AUDIO", "1")
    monkeypatch.delenv("DISPLAY", raising=False)
    aufrufe = []

    def api(pfad, method="GET", body=None, timeout=3.0, **_k):
        aufrufe.append((method, pfad))
        return antwort(pfad, method)

    for name in dir(A):
        modul = getattr(A, name)
        if isinstance(modul, types.ModuleType) and hasattr(modul, "api_call"):
            monkeypatch.setattr(modul, "api_call", api)
    nebenwirkung = []
    monkeypatch.setattr(zt, "fenster_zuklappen", lambda: nebenwirkung.append("zu"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: nebenwirkung.append("popen"))
    # Hintergrund-Arbeit (Laden beim Öffnen/Zeichnen) läuft zu Ende, bevor
    # verglichen wird — sonst sähe der Test ihr Ergebnis als Wirkung der Taste.
    start = threading.Thread.start

    def start_und_warten(self):
        start(self)
        self.join(1.0)
    monkeypatch.setattr(threading.Thread, "start", start_und_warten)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: nebenwirkung.append("run"))
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: nebenwirkung.append("call") or 0)
    monkeypatch.setattr(curses, "keyname", lambda c: b"")              # braucht sonst initscr
    for f in ("def_prog_mode", "reset_prog_mode", "endwin", "curs_set", "ungetch"):
        monkeypatch.setattr(curses, f, lambda *a: None)
    import urllib.request

    def kein_netz(*a, **k):
        raise urllib.error.URLError("kein netz im test")
    monkeypatch.setattr(urllib.request, "urlopen", kein_netz)
    for rad in ("RAD", "META", "TRAD", "ERAD"):  # Räder je Test frisch
        monkeypatch.setattr(zt, rad, copy.deepcopy(getattr(zt, rad)))

    def bauen():
        aufrufe.clear(); nebenwirkung.clear()
        z = A.kontext.Kontext(Schirm(), Store(), False, Theme())
        z.apply_theme("night")
        z.cycle_theme = lambda: nebenwirkung.append("theme")
        z.theme_mode_now = lambda: "auto"
        z.set_theme_mode = lambda m: None
        z.LAUF = {"an": False, "laeuft": False}
        chat = A.chat.Chat(z)
        u = types.SimpleNamespace(z=z, chat=chat, AI=chat.AI, LAUF=z.LAUF,
                                  DASH={"an": False}, C=z.C, PIX=z.PIX,
                                  addclip=z.addclip, safe_addstr=z.safe_addstr,
                                  draw_box=z.draw_box, stdscr=z.stdscr, store=z.store)
        u.post = A.post.Post(z); u.MAIL = u.post.MAIL
        u.kalender = A.kalender.Kalender(z); u.K = u.kalender.K
        u.graphen = A.graphen.Graphen(z); u.G = u.graphen.G
        u.fokus = A.fokus.Fokus(z); u.L = u.fokus.L
        u.notizen = A.notizen.Notizen(z); u.NOTE = u.notizen.NOTE
        u.klavier = A.klavier.Klavier(z); u.PIANO = u.klavier.PIANO
        u.karte = A.karte.Karte(z); u.M = u.karte.M
        u.technik = A.technik.Technik(z); u.TECH = u.technik.TECH
        u.desk = A.desk.Desk(z); u.DESK = u.desk.DESK
        u.shop = A.shop.Shop(z); u.SHOP = u.shop.SHOP
        u.router = A.sprung.router_fuer(u.DESK, u.kalender, u.fokus, u.graphen)
        u.bz = A.befehle.Befehlszeile(z)
        u.app_wahl = A.app_oeffnen.AppOeffnen(z, u.bz); u.APPWAHL = u.app_wahl.W   # 2026-10-25
        u.eigene = A.eigene_apps.EigeneApps(z, u.router, u.desk, u.app_wahl)     # Werkstatt (2026-10-10)
        u.werkstatt = A.werkstatt.Werkstatt(z, u.eigene, u.desk, u.router); u.WERK = u.werkstatt.W
        u.schematix = A.schematix.Schematix(z); u.SCHEMATIX = u.schematix.S   # 2026-10-30
        u.startseite = A.startseite.Startseite(z, zt.RAD, zt.META, zt.TRAD, u.technik, zt.ERAD)
        u.dashboard = A.dashboard.Dashboard(z, u.graphen, u.fokus)
        u.erinnerung = A.erinnerung.Erinnerung(z, u.graphen)
        u.app_start = A.app_start.AppStart(z, u.bz)
        u.aufrufe, u.nebenwirkung = aufrufe, nebenwirkung
        u.zuklappen = lambda: zt.fenster_zuklappen()     # wie run_ui
        A.fenster.verkabeln(z, u)            # wie run_ui: Horcher fragt jedes Programm
        return u
    return bauen


def zeichnen(u):
    try:
        zt.bild_zeichnen(u)
    except curses.error:
        pass


def fingerabdruck(u):
    teile = []
    for name in ("AI", "G", "L", "M", "K", "MAIL", "NOTE", "PIANO", "TECH", "DESK",
                 "SHOP", "WERK", "APPWAHL", "SCHEMATIX"):
        teile.append(repr(getattr(u, name)))
    teile.append(repr((zt.RAD, zt.META, zt.TRAD, zt.ERAD)))
    teile.append(repr(vars(u.bz)))
    teile.append(repr((u.erinnerung.nag_active, u.post.MAIL_Q.qsize())))
    teile.append(repr(list(u.aufrufe)) + repr(list(u.nebenwirkung)))
    return "\n".join(teile)


# Aufbauten: bringen die TUI in einen Zustand (tests/tasten_zustaende/*
# nehmen sie für die Ansichten der Programme).
def _graph(u):
    u.graphen.oeffnen()


def _wald(u):
    u.fokus.oeffnen()


def _ebene(u):
    u.fokus.oeffnen()
    zt.taste_verteilen(u, 10)                # „einkauf" öffnen


def _notiz(u):
    u.notizen.oeffnen()


def _notizen(u):
    u.notizen.oeffnen()
    zt.taste_verteilen(u, ord("n"))


def _kal(u):
    u.kalender.oeffnen()
    zeichnen(u)


def _kal_a(u, kasten=0):               # der Kalender startet in A
    _kal(u)
    for _ in range(kasten):
        zt.taste_verteilen(u, 9); zeichnen(u)


def _kal_b(u):
    _kal(u); zt.taste_verteilen(u, ord("v")); zeichnen(u)
    # Tab wählt den nächsten Termin des Tages — dafür einen Beispieltag mit
    # mehreren Terminen (heute kann leer sein).
    import datetime
    u.kalender.bedienung.setze_tag(datetime.date.fromisoformat(kb.HEUTE)); zeichnen(u)


def _kal_c(u):
    _kal_b(u); zt.taste_verteilen(u, ord("v")); zeichnen(u)


def _post(u):
    u.post.oeffnen()
    u.MAIL["data"] = antwort("/api/mail", "GET")


def _post_liste(u):
    _post(u)
    u.MAIL["level"] = "mails"; u.MAIL["cat"] = "arbeit"; u.MAIL["mode2"] = "list"
    u.MAIL["mails"] = copy.deepcopy(MAILS["mails"])


def _post_lesen(u):
    _post_liste(u)
    u.MAIL["mode2"] = "read"; u.MAIL["msel"] = 1


def _eingang_liste(u):
    _post_liste(u)
    u.MAIL["cat"] = A.post.MAIL_EINGANG


def _eingang_lesen(u):
    _post_lesen(u)
    u.MAIL["cat"] = A.post.MAIL_EINGANG


def _klavier(u):
    u.klavier.oeffnen()


def _karte(u):
    u.karte.oeffnen()
    zeichnen(u)


def _einordnen(u):
    _wald(u)
    zt.taste_verteilen(u, ord(">"))


def _technik(u):
    u.TECH["active"] = True; u.TECH["view"] = "system"


def _werkstatt(u):                          # Werkstatt (2026-10-10)
    u.werkstatt.oeffnen()


def _desk_wahl(u):
    u.desk.oeffnen()


def _desk(u):
    u.desk.oeffnen()
    zt.taste_verteilen(u, 10)                # „Elektronik" öffnen
    zeichnen(u)
    u.DESK["canvas"].fokus = "m"


def _desk_greifen(u):
    _desk(u); zt.taste_verteilen(u, 10)


def _desk_verbinden(u):
    _desk(u); zt.taste_verteilen(u, ord("v"))


def _desk_frage(u):
    _desk(u); zt.taste_verteilen(u, ord("d"))


def _desk_bild(u):
    _desk(u)
    u.DESK["canvas"].fokus = "b"


def _desk_kachel(u):
    _desk(u)
    u.desk.starten = lambda f: f()           # Kachel gleich holen, nicht im Thread
    zeichnen(u)
    u.DESK["canvas"].fokus = "k"
    u.DESK["canvas"].element("k")["_oben"] = 1   # damit auch Bild↑ etwas tut


def _desk_neu(u):
    _desk(u); zt.taste_verteilen(u, ord("+"))


def _desk_groesse(u):                       # r: Größe ändern (2026-10-10)
    _desk(u); zt.taste_verteilen(u, ord("r"))




# ── Chat und Überlagerungen (Kontext = None: dort fragt die Leiste die
# Ansicht selbst, siehe fussleiste.ANSICHTEN) ─────────────────────────

def _chat(u):
    u.chat.oeffnen()


def _chat_text(u):
    _chat(u); u.AI["input"], u.AI["cur"] = "hallo", 5


def _chat_zeilen(u):
    _chat(u); u.AI["input"], u.AI["cur"] = "eins\nzwei", 9


def _chat_antwort(u):
    _chat(u)
    u.AI.update(streaming=True, strom=7, answer="es war einmal")


def _chat_wahl(u):
    _chat(u)
    u.AI["wahl"] = A.chat.auswahl("effort", SCHIRM._EINSTELLUNGEN)


def _chat_modell(u):                  # /model: tippen filtert
    _chat(u)
    u.chat.befehl("modell", "")
    assert u.AI["wahl"] and "filter" in u.AI["wahl"]


def _chat_erlaubnis(u):               # /permissions: Zurücknehmen
    _chat(u)
    u.chat.befehl("erlaubnis", "")
    assert u.AI["wahl"]


def _chat_frage(u):
    _chat_antwort(u)
    u.AI["perm"] = {"frage": "darf ich die datei schreiben?",
                    "optionen": ["ja", "nein"]}


def _chat_bearbeiten(u):
    _chat(u)
    u.AI.update(ersetzt="m1", input="alte frage", cur=10)


def _liste(u):                         # seit 2026-10-07 die Seitenleiste
    _chat(u); u.chat.seite.aufklappen()


def _seite_menue(u):
    _liste(u); u.AI["liste"]["idx"] = 0; zt.taste_verteilen(u, curses.KEY_UP)
    assert u.AI["seite_menu"] is not None


def _verlauf(u):
    _chat(u); zeichnen(u); u.AI["fokus"] = "verlauf"


def _verlauf_antwort(u):              # eine Antwort gewählt: + / − bewerten
    _verlauf(u)
    i = A.verlauf.letzte_antwort(u.AI["log"])
    assert i is not None
    u.AI["vwahl"] = ("kopieren", i)


def _bewertung(u):                    # das kleine Fenster (2026-10-08)
    _chat(u); zeichnen(u)
    u.chat.bewertung.oeffnen(A.verlauf.letzte_antwort(u.AI["log"]), -1)


def _bewertung_text(u):
    _bewertung(u)
    u.AI["bewertung"].update(text="zu knapp", cur=8)


def _dokument(u):
    _chat(u); u.chat.rechts.dokument_zeigen("d1")
    assert u.AI["fokus"] == "rechts"


def _outputs(u):
    _chat(u)
    u.AI["log"].append(("ablage", "d2\tSkizze"))
    u.chat.rechts.outputs_umschalten(); zeichnen(u); u.AI["fokus"] = "rechts"


def _einstellungen(abschnitt=None):
    def aufbau(u):
        _chat(u); u.chat.einstellungen.oeffnen(abschnitt)
    return aufbau


def _liste_suche(u):
    _liste(u); zt.taste_verteilen(u, ord("/"))


def _liste_umbenennen(u):
    _liste(u); zt.taste_verteilen(u, curses.KEY_DOWN); zt.taste_verteilen(u, ord("r"))


def _liste_archiv(u):
    _liste(u); zt.taste_verteilen(u, ord("z"))


def _gedaechtnis(u):
    _chat(u); u.chat.gedaechtnis.oeffnen()


def _skills(u):
    _chat(u); u.chat.gedaechtnis.oeffnen("skills")


def _ablage(u):
    _chat(u); u.chat.ablageliste.oeffnen()


def _ablage_lesen(u):
    _ablage(u); zt.taste_verteilen(u, 10)


def _projekte(u):
    _chat(u); u.chat.projekte.oeffnen()


def _projekt(u):
    _projekte(u); zt.taste_verteilen(u, 10)


def _projekt_name(u):
    _projekte(u); zt.taste_verteilen(u, ord("n"))


def _erinnerung(u):
    u.erinnerung.nag_active = True
    u.erinnerung.nag_items = [{"id": "g1", "name": "schlaf"}]


def _hilfe(u):
    u.bz.help_latched = True


def _befehlszeile(u):
    u.bz.oeffnen()
    u.bz.cmd_buf = "/the"


UEBERLAGERUNGEN = {
    "ai": _chat, "ai:text": _chat_text, "ai:zeilen": _chat_zeilen,
    "ai:antwort": _chat_antwort, "ai:wahl": _chat_wahl, "ai:modell": _chat_modell,
    "ai:erlaubnis": _chat_erlaubnis, "ai:frage": _chat_frage,
    "ai:bearbeiten": _chat_bearbeiten, "ai:liste": _liste, "ai:liste:suche": _liste_suche,
    "ai:liste:umbenennen": _liste_umbenennen, "ai:liste:archiv": _liste_archiv,
    "ai:seite:menue": _seite_menue, "ai:verlauf": _verlauf,
    "ai:verlauf:antwort": _verlauf_antwort, "ai:bewertung": _bewertung,
    "ai:bewertung:text": _bewertung_text, "ai:dokument": _dokument,
    "ai:outputs": _outputs, "ai:einstellungen": _einstellungen(),
    "ai:einstellungen:skills": _einstellungen("skills"),
    "ai:einstellungen:memory": _einstellungen("memory"),
    "ai:einstellungen:usage": _einstellungen("usage"),
    "ai:einstellungen:capabilities": _einstellungen("capabilities"),
    "ai:einstellungen:permissions": _einstellungen("permissions"),
    "ai:einstellungen:model": _einstellungen("model"),
    "ai:einstellungen:feedback": _einstellungen("feedback"),
    "ai:gedaechtnis": _gedaechtnis, "ai:skills": _skills, "ai:ablage": _ablage,
    "ai:ablage:lesen": _ablage_lesen, "ai:projekte": _projekte, "ai:projekt": _projekt,
    "ai:projekt:name": _projekt_name, "erinnerung": _erinnerung, "hilfe": _hilfe,
    "befehlszeile": _befehlszeile,
}

GEGENTEIL = {curses.KEY_UP: curses.KEY_DOWN, curses.KEY_DOWN: curses.KEY_UP,
             curses.KEY_LEFT: curses.KEY_RIGHT, curses.KEY_RIGHT: curses.KEY_LEFT,
             curses.KEY_PPAGE: curses.KEY_NPAGE, curses.KEY_NPAGE: curses.KEY_PPAGE,
             curses.KEY_HOME: curses.KEY_END, curses.KEY_END: curses.KEY_HOME,
             # Kalender 0/$ = Wochenanfang/-ende: am Montag bzw. Sonntag steht
             # man schon dort (fiel am Sonntag, 11.10.2026, als rot auf).
             ord("0"): ord("$"), ord("$"): ord("0"),
             # vim-Zweitbelegung der Pfeile (Tastentabellen, 2026-10-11)
             ord("k"): ord("j"), ord("j"): ord("k")}


def drueck(u, folge):
    u.z.stdscr.folge = list(folge[1:])
    try:
        return zt.taste_verteilen(u, folge[0])
    except KeyboardInterrupt:
        return "ende"


def _aufgebaut(welt, aufbau):
    u = welt()
    aufbau(u)
    zeichnen(u)
    u.aufrufe.clear(); u.nebenwirkung.clear()
    return u


def wirkt(welt, aufbau, folge):
    """Frische TUI im Zustand, Taste drücken: tut sie etwas?"""
    u = _aufgebaut(welt, aufbau)
    vorher = fingerabdruck(u)
    raus = drueck(u, folge)
    if raus is None and fingerabdruck(u) == vorher and folge[-1] in GEGENTEIL:
        # ↑ ganz oben tut nichts — erst einen Schritt weg vom Rand, dann
        # muss die Taste zurückführen.
        drueck(u, folge[:-1] + [GEGENTEIL[folge[-1]]])
        u.aufrufe.clear(); u.nebenwirkung.clear()
        vorher = fingerabdruck(u)
        raus = drueck(u, folge)
    return raus is not None or fingerabdruck(u) != vorher


# Die Programme in jeder Ansicht prüft tests/test_tastentabellen.py; hier
# bleiben die Überlagerungen der Hauptschleife und die Chat-Zustände.
ALLE = UEBERLAGERUNGEN


@pytest.mark.parametrize("name", list(ALLE))
def test_jede_taste_in_der_leiste_tut_etwas(welt, name):
    """Die Einträge kommen aus der ECHTEN Leiste (fussleiste.eintraege) —
    was dort steht, wird gedrückt."""
    aufbau = ALLE[name]
    eintraege = fussleiste.eintraege(_aufgebaut(welt, aufbau))
    assert eintraege, name
    gelogen = []
    for taste, was in eintraege:
        folgen = fussleiste.codes(taste)
        if folgen is None:
            if taste.startswith("/") and name.startswith("ai"):   # Chat-Befehl
                assert chat_befehle.lesen(taste).art == "befehl", taste
            continue
        for folge in folgen:
            if not wirkt(welt, aufbau, folge):
                gelogen.append("%s %s (%s)" % (taste, was, folge))
    assert not gelogen, "%s: steht in der Leiste, tut aber nichts: %s" % (name, gelogen)


def test_leiste_im_chat_zeigt_keine_globale_befehlszeile(welt):
    # Seit der Tastentabelle (2026-10-11): '/' beginnt bei leerer Eingabe
    # einen Chat-Befehl — die Leiste sagt das, statt „/help" als Taste.
    e = fussleiste.eintraege(_aufgebaut(welt, _chat))
    assert ("/", "commands") not in e and ("/", "chat commands") in e


def test_leiste_auf_der_startseite_ohne_fremde_tasten(welt):
    e = dict(fussleiste.eintraege(_aufgebaut(welt, lambda u: None)))
    assert e["space"] == "ai chat" and e["/"] == "commands"
    k = dict(fussleiste.eintraege(_aufgebaut(welt, _kal)))
    assert "space" not in k                      # dort ist Leertaste nicht die KI


def test_strg_c_ausserhalb_des_chats_beendet_wie_frueher(welt):
    u = _aufgebaut(welt, _kal)
    with pytest.raises(KeyboardInterrupt):
        zt.taste_verteilen(u, 3)


def test_strg_c_im_chat_beendet_nie(welt):
    u = _aufgebaut(welt, _chat)
    assert zt.taste_verteilen(u, 3) is None
    assert u.AI["active"] and "keine antwort" in u.AI["msg"]
    u = _aufgebaut(welt, _liste)                 # auch über einer Überlagerung
    assert zt.taste_verteilen(u, 3) is None


def test_hilfe_kommt_aus_den_tastentabellen(welt):
    """/help (2026-10-11): je Programm die Tasten seiner Hauptansicht aus dem
    Horcher — keine zweite Liste von Hand (früher befehle.TUI_KEYS)."""
    u = _aufgebaut(welt, lambda u: None)
    h = dict(fussleiste.hilfe(u))
    assert "start" in h and "space ai chat" in h["start"]
    assert {"notizen", "kalender", "liste", "post", "ki-chat", "desk"} <= set(h)
    _titel, rows = befehle.overlay_rows("/help", True, None, fussleiste.hilfe(u))
    assert ("key", "notizen", h["notizen"]) in rows


def test_hilfe_zeigt_die_hauptansicht_des_kalenders(welt):
    """25.10.2026: /help zeigte beim Kalender nur „any key close" (die erste
    Ansicht der Tabelle ist das Ansehen-Fenster) — S (Muss|Soll), R, x …
    fehlten. Jetzt: die Hauptansicht, mit jeder beschrifteten Taste dort."""
    u = _aufgebaut(welt, lambda u: None)
    h = dict(fussleiste.hilfe(u))["kalender"]
    assert "any key" not in h
    for taste, was in u.z.horcher.eintraege("kalender", u.kalender.HAUPTANSICHT):
        assert "%s %s" % (taste, was) in h
    for stueck in ("S must/should", "R rhythm", "x show done", "g go to", "u (un)commit"):
        assert stueck in h


def test_kalender_s_steht_in_jeder_hauptansicht(welt):
    """Taste S (Muss|Soll, c0b1368) wirkt in A, B und C — und steht dort in
    der Tabelle, aus der Leiste, '/' und /help lesen."""
    u = _aufgebaut(welt, lambda u: None)
    for ansicht in ("a:termine", "a:kalender", "a:todo", "b:monat", "c:woche"):
        e = u.z.horcher.eintraege("kalender", ansicht)
        assert ("S", "must/should") in e, ansicht


def test_keine_handtabelle_mehr():
    """Die Tasten stehen nur noch in den Tastentabellen der Programme."""
    for alt in ("CTX_KEYS", "CTX_TITLES", "TUI_KEYS"):
        assert not hasattr(befehle, alt), alt
    assert not hasattr(A.fenster, "current_ctx")


def test_bewerten_zustaende_bieten_ihre_tasten_an(welt):
    """Die neuen Zustände (2026-10-08) zeigen, was sie können — sonst prüfte
    der Test oben eine leere Leiste."""
    e = fussleiste.eintraege(_aufgebaut(welt, _verlauf_antwort))
    assert ("+/-", "rate") in e
    e = fussleiste.eintraege(_aufgebaut(welt, _bewertung))
    assert ("enter", "save") in e and ("tab", "good/bad") in e and ("esc", "cancel") in e
    e = fussleiste.eintraege(_aufgebaut(welt, _einstellungen("feedback")))
    assert ("enter", "open chat") in e and ("↑↓", "select") in e
