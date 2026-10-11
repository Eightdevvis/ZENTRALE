"""Zwei Ehrlichkeits-Fehler (2026-10-11):

1. Die Websuche sagte „Keine Treffer", obwohl sie gar nicht lief
   (SearXNG aus, DuckDuckGo leer/geblockt).
2. Ein Zeitablauf der Erlaubnis-Frage zählte als „von dir abgelehnt".
"""
import pytest

import ehrlichkeit
import erlaubnis
import fehlercodes
import state
import web
import werkzeug_befund
import werkzeug_schleife
import zug_ablauf

TREFFER = [{"title": "Ferien", "url": "https://x.de", "snippet": "Kalender"}]


# ── 1. Websuche ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def suche_frisch():
    web.suche_aus_zuruecksetzen()
    yield
    web.suche_aus_zuruecksetzen()


def _netz(monkeypatch, searx, ddg):
    """searx/ddg: Trefferliste oder Exception-Instanz; zählt die Aufrufe."""
    aufrufe = {"searx": 0, "ddg": 0}

    def fake(art, wert):
        def f(q, n):
            aufrufe[art] += 1
            if isinstance(wert, Exception):
                raise wert
            return wert
        return f
    monkeypatch.setattr(web, "_searxng_search", fake("searx", searx))
    monkeypatch.setattr(web, "_ddg_search", fake("ddg", ddg))
    return aufrufe


def test_searxng_ok_und_leer_heisst_keine_treffer(monkeypatch):
    a = _netz(monkeypatch, [], [])
    r = web.suche("nichts da")
    assert r == "Keine Treffer für 'nichts da'."
    assert werkzeug_befund.status_von(r) == "ok"
    assert a["ddg"] == 0


def test_searxng_aus_ddg_hat_treffer(monkeypatch):
    _netz(monkeypatch, ConnectionRefusedError("Connection refused"), TREFFER)
    r = web.suche("ferien")
    assert "1 Treffer" in r and "https://x.de" in r


def test_searxng_aus_ddg_leer_bricht_ab(monkeypatch):
    _netz(monkeypatch, ConnectionRefusedError("Connection refused"), [])
    r = web.suche("ferien")
    assert "Keine Treffer" not in r
    assert "ABGEBROCHEN" in r and "Fehler I-SUCHE-AUS" in r
    assert "nicht verfügbar" in r
    assert werkzeug_befund.status_von(r) == "fehlgeschlagen"


def test_beide_fehler_brechen_ab(monkeypatch):
    _netz(monkeypatch, ConnectionRefusedError("aus"), OSError("geblockt"))
    r = web.suche("ferien")
    assert "Fehler I-SUCHE-AUS" in r
    assert werkzeug_befund.status_von(r) == "fehlgeschlagen"


def test_wiederholungsbremse_versucht_nicht_erneut(monkeypatch):
    a = _netz(monkeypatch, ConnectionRefusedError("aus"), [])
    web.suche("eins")
    zweite = web.suche("ganz anderes wort")
    assert "I-SUCHE-AUS" in zweite
    assert werkzeug_befund.status_von(zweite) == "fehlgeschlagen"
    assert a == {"searx": 1, "ddg": 1}              # beim zweiten Mal kein Netz


def test_nach_der_bremse_darf_es_wieder_klappen(monkeypatch):
    _netz(monkeypatch, ConnectionRefusedError("aus"), [])
    web.suche("eins")
    web.suche_aus_zuruecksetzen()
    _netz(monkeypatch, TREFFER, [])
    assert "1 Treffer" in web.suche("zwei")


def test_der_code_ist_erklaert():
    assert fehlercodes.bekannt("I-SUCHE-AUS")
    assert "Nicht weiter umformulieren" in fehlercodes.erklaeren("I-SUCHE-AUS")


# ── 2. Zeitablauf der Erlaubnis-Frage ──────────────────────────────────

def _fahren(monkeypatch, wait):
    """run_tool mit dem Gate; wait ersetzt state.wait_permission.
    -> (ergebnis, ausgeführt)"""
    ausgefuehrt = []
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda n, a: True)
    monkeypatch.setattr(erlaubnis, "vorab", lambda n, a: None)
    monkeypatch.setattr(state, "wait_permission", wait)
    gen = werkzeug_schleife.run_tool(
        "add_calendar_entry", {"label": "x"}, tutor_mode=False,
        active_exec=lambda n, a: ausgefuehrt.append(n) or "ok",
        user_query="x", store=None)
    try:
        while True:
            next(gen)
    except StopIteration as ende:
        return ende.value, ausgefuehrt


def test_zeitablauf_ist_keine_antwort_und_nichts_laeuft(monkeypatch):
    orig = state.wait_permission                    # die echte, mit kurzer Frist
    erg, ausgefuehrt = _fahren(monkeypatch, lambda: orig(0.01))
    assert ausgefuehrt == []
    text = erg[1]
    assert text.startswith("[ergebnis: keine_antwort]\n")
    assert "nicht geantwortet" in text and "frag im Text nach" in text
    assert "[ergebnis: abgelehnt]" not in text


def test_echtes_nein_bleibt_abgelehnt(monkeypatch):
    erg, ausgefuehrt = _fahren(monkeypatch, lambda: "nein")
    assert ausgefuehrt == []
    assert erg[1].startswith("[ergebnis: abgelehnt]\n")
    assert "nicht geantwortet" not in erg[1]


def test_ja_fuehrt_aus(monkeypatch):
    erg, ausgefuehrt = _fahren(monkeypatch, lambda: "ja, nur dieses mal")
    assert ausgefuehrt == ["add_calendar_entry"]
    assert erg[1].startswith("[ergebnis: ok]")


def test_das_gate_fragt_mit_timeout_none(monkeypatch):
    gesehen = {}
    monkeypatch.setattr(state, "request_permission", lambda **k: gesehen.update(k))
    _fahren(monkeypatch, lambda: "nein")
    assert gesehen["timeout_default"] is None


def test_zug_ablauf_bekommt_keine_antwort(monkeypatch):
    erfasst = []
    monkeypatch.setattr(zug_ablauf, "frage",
                        lambda f, o, a, art="knopf": erfasst.append((a, art)))
    _fahren(monkeypatch, lambda: None)
    assert erfasst == [(None, "erlaubnis")]
    zeile = zug_ablauf.kopfzeile({"art": "frage", "antwort": None})
    assert "keine Antwort, Zeit abgelaufen" in zeile


def test_erledigt_zeile_sagt_keine_antwort():
    liste = [{"werkzeug": "add_calendar_entry", "wen": "Zahnarzt", "status": "keine_antwort"}]
    zeile = ehrlichkeit.erledigt_zeile(liste)
    assert "keine Antwort (Zeit abgelaufen)" in zeile
    assert "abgelehnt" not in zeile
    liste[0]["status"] = "abgelehnt"
    assert "von dir abgelehnt" in ehrlichkeit.erledigt_zeile(liste)


def test_nachfrage_im_text_nach_zeitablauf_zaehlt_als_gefragt():
    s = ehrlichkeit.Schritt("add_calendar_entry", {"label": "x"}, "keine_antwort", "")
    assert ehrlichkeit.tat_lief("eintragen", True, [s]) is True
