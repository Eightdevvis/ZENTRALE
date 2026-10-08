"""Bewerten im Chat (tui/ansichten/bewertung.py, 2026-10-08): good/bad unter
jeder Antwort, das kleine Fenster mit Kommentar, Klicks und Tasten, die
Zuordnung Verlauf-Zeile → Nachricht-id, Customize → Feedback."""
import curses

import pytest

from test_chat_web_teile import Schirm, Theme, _klick, _zeichnen   # noqa: F401
from tui.ansichten import bewertung, chat as chatmod, einstellungen, kontext

VERLAUF = [{"id": "n1", "role": "user", "content": "wie flicke ich?"},
           {"id": "n2", "role": "assistant", "content": "Mit Flickzeug."},
           {"id": "n3", "role": "user", "content": "und ohne?"},
           {"id": "n4", "role": "assistant", "content": "Dann schieben."}]
LISTE = {"rueckmeldungen": [
    {"ts": "2026-10-08T09:00:00+00:00", "gespraech": "g2", "nachricht": "m1", "wert": -1,
     "kommentar": "zu lang", "gespraech_titel": "Steuer", "ausschnitt": "Zuerst die Belege …"},
    {"ts": "2026-10-07T09:00:00+00:00", "gespraech": "g1", "nachricht": "n2", "wert": 1,
     "gespraech_titel": "Schlauch", "verworfen": True}]}


@pytest.fixture
def welt(monkeypatch):
    aufrufe = []
    antworten = {"history": list(VERLAUF), "post": None}

    def api(pfad, methode="GET", body=None, timeout=3.0, **_k):
        aufrufe.append((methode, pfad, body))
        if pfad.startswith("/api/chat/history"):
            return antworten["history"]
        if pfad.startswith("/api/rueckmeldungen"):
            return {"rueckmeldungen": []} if "gespraech=" in pfad else LISTE
        if pfad == "/api/rueckmeldung" and antworten["post"]:
            raise antworten["post"].pop(0)
        return {}
    from tui import ansichten as A
    for name in dir(A):
        m = getattr(A, name)
        if hasattr(m, "api_call"):
            monkeypatch.setattr(m, "api_call", api)
    monkeypatch.setattr(bewertung, "api_call", api)

    def bauen(h=30, w=136):
        z = kontext.Kontext(Schirm(h, w), None, False, Theme())
        z.apply_theme("night")
        c = chatmod.Chat(z)
        c.AI["active"] = True
        c.AI["gid"], c.AI["titel"] = "g1", "Schlauch"
        c.AI["log"] = [("user", "wie flicke ich?"), ("ai", "Mit Flickzeug."),
                       ("user", "und ohne?"), ("ai", "Dann schieben.")]
        c.bewertung.geladen("g1", VERLAUF)
        c.aufrufe, c.antworten = aufrufe, antworten
        aufrufe.clear()
        return c
    return bauen


def _posts(c):
    return [b for m, p, b in c.aufrufe if p == "/api/rueckmeldung"]


# ── Reine Helfer ──────────────────────────────────────────────────────

def test_ids_und_marken():
    assert bewertung.antwort_ids(VERLAUF + [{"id": "x", "role": "assistant", "content": " "}]) \
        == ["n2", "n4"]
    log = [("user", "a"), ("denken", "…"), ("ai", "b"), ("hinweis", "h"), ("ai", "c")]
    assert bewertung.antwort_nummer(log, 4) == 1 and bewertung.antwort_nummer(log, 0) is None
    assert bewertung.marken(log, ["n2", "n4"], {"n4": {"wert": -1}}) == {4: -1}


def test_zeichen_sind_einspaltig():
    import unicodedata
    for z in list(bewertung.ZEICHEN.values()) + ["good", "bad"]:
        assert all(unicodedata.east_asian_width(c) in ("N", "Na") for c in z)


# ── Klicks ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("groesse", [(24, 80), (30, 136)])
def test_klick_auf_bad_kommentar_enter_speichert(welt, monkeypatch, groesse):
    c = welt(*groesse)
    _zeichnen(c)
    _klick(c, monkeypatch, "bad")                       # unter der ERSTEN Antwort
    assert c.AI["bewertung"]["wert"] == -1 and c.AI["bewertung"]["i"] == 1
    _zeichnen(c)
    schirm = "\n".join(c.z.stdscr.zeile(y) for y in range(c.z.stdscr.h))
    assert "Was war schlecht? (optional)" in schirm and "[save]" in schirm
    for ch in "zu knapp":
        c.taste(ord(ch))
    c.taste(10)
    assert _posts(c) == [{"gespraech": "g1", "nachricht": "n2", "wert": -1,
                          "kommentar": "zu knapp"}]
    assert c.AI["bewertung"] is None and "gespeichert" in c.AI["msg"]
    _zeichnen(c)
    schirm = "\n".join(c.z.stdscr.zeile(y) for y in range(c.z.stdscr.h))
    assert "bad ✗" in schirm                            # der Zustand steht da


def test_fenster_nimmt_alle_klicks_und_hat_knoepfe(welt, monkeypatch):
    c = welt()
    _zeichnen(c)
    _klick(c, monkeypatch, "good")
    _zeichnen(c)
    # Klick daneben (auf „copy" der anderen Antwort): nichts passiert
    _klick(c, monkeypatch, "Mit Flickzeug.")
    assert c.AI["bewertung"] is not None and not _posts(c)
    _klick(c, monkeypatch, "bad ✗")                    # im Kopf: umschalten
    assert c.AI["bewertung"]["wert"] == -1
    _zeichnen(c)
    _klick(c, monkeypatch, "[cancel]")
    assert c.AI["bewertung"] is None and not _posts(c)
    _zeichnen(c)
    _klick(c, monkeypatch, "good")
    _zeichnen(c)
    _klick(c, monkeypatch, "[save]")
    assert _posts(c)[0]["wert"] == 1 and _posts(c)[0]["kommentar"] == ""


def test_erneut_klicken_aendert_mit_altem_kommentar(welt, monkeypatch):
    c = welt()
    c.AI["bewertungen"] = {"n4": {"wert": 1, "kommentar": "passt"}}
    _zeichnen(c)
    schirm = "\n".join(c.z.stdscr.zeile(y) for y in range(c.z.stdscr.h))
    assert "good ✓" in schirm
    _klick(c, monkeypatch, "good ✓")
    assert c.AI["bewertung"]["text"] == "passt" and c.AI["bewertung"]["wert"] == 1
    c.taste(9)                                          # doch schlecht
    c.taste(10)
    assert _posts(c)[0]["kommentar"] == "passt"
    assert c.AI["bewertungen"]["n4"]["wert"] == -1


# ── Tasten ────────────────────────────────────────────────────────────

def test_plus_minus_im_verlauf_und_esc_bricht_ab(welt, monkeypatch):
    c = welt()
    _zeichnen(c)
    c.AI["fokus"] = "verlauf"
    c.taste(curses.KEY_UP)                              # letztes Ziel: bad der letzten
    assert ("+/-", "rate") in c.tasten()
    c.taste(ord("+"))
    assert c.AI["bewertung"]["wert"] == 1 and c.AI["bewertung"]["i"] == 3
    assert c.tasten()[0] == ("enter", "save")
    c.taste(9)                                          # Tab: gut ↔ schlecht
    assert c.AI["bewertung"]["wert"] == -1
    monkeypatch.setattr(c, "_esc_lesen", lambda: "esc")
    c.taste(27)
    assert c.AI["bewertung"] is None and not _posts(c) and c.AI["msg"] == "nicht bewertet"


def test_mehrzeilig_und_umlaute(welt, monkeypatch):
    c = welt()
    c.bewertung.oeffnen(1, 1)
    for b in "für".encode("utf-8"):
        c.taste(b)
    monkeypatch.setattr(c, "_esc_lesen", lambda: "alt_enter")
    c.taste(27)                                         # Alt+Enter
    c.taste(ord("x"))
    c.taste(curses.KEY_BACKSPACE)
    c.taste(ord("y"))
    assert c.AI["bewertung"]["text"] == "für\ny"
    c.taste(10)
    assert _posts(c)[0]["kommentar"] == "für\ny"


# ── Nachricht-id fehlt oder passt nicht mehr ──────────────────────────

def test_eben_gestreamte_antwort_holt_die_id_nach(welt):
    c = welt()
    c.AI["log"] += [("user", "noch was"), ("ai", "Neu.")]
    c.antworten["history"] = VERLAUF + [
        {"id": "n5", "role": "user", "content": "noch was"},
        {"id": "n6", "role": "assistant", "content": "Neu."}]
    c.bewertung.oeffnen(5, 1)
    c.taste(10)
    assert _posts(c)[0]["nachricht"] == "n6"


def test_404_holt_einmal_frisch(welt):
    import urllib.error
    c = welt()
    c.antworten["history"] = [VERLAUF[0], {"id": "n2b", "role": "assistant", "content": "x"},
                              VERLAUF[2], VERLAUF[3]]
    c.antworten["post"] = [urllib.error.HTTPError("u", 404, "weg", None, None)]
    c.bewertung.oeffnen(1, -1)
    c.taste(10)
    assert c.AI["bewertungen"]["n2b"]["wert"] == -1 and c.AI["bewertung"] is None


def test_ohne_verbindung_bleibt_das_fenster_offen(welt):
    import urllib.error
    c = welt()
    c.antworten["post"] = [urllib.error.URLError("weg")]
    c.bewertung.oeffnen(1, 1)
    c.taste(ord("a"))
    c.taste(10)
    assert c.AI["bewertung"]["text"] == "a" and "nicht gespeichert" in c.AI["msg"]


# ── Customize → Feedback ──────────────────────────────────────────────

def test_feedback_liste_und_enter_springt_ins_gespraech(welt, monkeypatch):
    c = welt()
    c.einstellungen.oeffnen("feedback")
    _zeichnen(c)
    schirm = "\n".join(c.z.stdscr.zeile(y) for y in range(c.z.stdscr.h))
    assert "08.10. ✗  Steuer" in schirm and "zu lang" in schirm
    assert "07.10. ✓  Schlauch" in schirm and "(antwort später ersetzt)" in schirm
    geoeffnet = []
    monkeypatch.setattr(c, "gespraech_oeffnen", geoeffnet.append)
    c.taste(curses.KEY_DOWN)
    c.taste(10)
    assert geoeffnet == ["g1"] and c.AI["einstellungen"] is None
    # Ist der Verlauf geladen, steht die Wahl auf der bewerteten Antwort.
    c.AI["bewertungen"] = {"n2": {"wert": 1}}
    c.bewertung.geladen("g1", VERLAUF)
    assert c.AI["fokus"] == "verlauf" and c.AI["vwahl"] == ("gut", 1)


def test_feedback_zeilen_helfer():
    z = einstellungen.feedback_zeilen(LISTE["rueckmeldungen"][0], 40)
    assert z[0] == ("08.10. ✗  Steuer", "warn")
    assert ("      zu lang", "") in z and z[-1][1] == "leise"
