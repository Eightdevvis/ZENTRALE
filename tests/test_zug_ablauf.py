"""Das Ablauf-Protokoll eines Chat-Zugs (core/zug_ablauf.py, 2026-10-09):
was mitgeschrieben wird, in welcher Reihenfolge, wo es landet (Gespräch,
Route, /trace in die Ablage) — mit gefälschtem Modell, ohne echten Aufruf.
Alle Inhalte sind erfunden."""
import json

import pytest

import ablage
import ai_backends
import ai_config
import cloud
import consolidation
import erlaubnis
import gespraeche
import graph
import kern
import ki_prompt
import ki_werkzeuge
import state
import werkzeug_schleife
import zug_ablauf
from test_cloud_loop import FakeBlock, FakeClient


# ── Bausteine ───────────────────────────────────────────────────────────

def test_ohne_protokoll_tut_melden_nichts():
    assert not zug_ablauf.offen()
    zug_ablauf.text("x")
    zug_ablauf.werkzeug_fertig(zug_ablauf.werkzeug_beginnt("a", {}), "y")
    assert zug_ablauf.abschliessen("z") is None


def test_nicht_scharf_ohne_system_meldung():
    """Lokal/klein meldet niemand system() — dann wird nichts gespeichert,
    auch wenn die Schleife Werkzeuge mitgeschrieben hat."""
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.text("Vorgeplänkel")
        assert zug_ablauf.abschliessen("Antwort") is None
    finally:
        zug_ablauf.beenden(m)


def test_riesen_werden_gekuerzt_mit_hinweis_sonst_nichts():
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.system("fest")
        e = zug_ablauf.werkzeug_beginnt("fetch_url", {"url": "https://example.org"})
        zug_ablauf.werkzeug_fertig(e, "[ergebnis: ok]\n" + "x" * 80_000)
        klein = zug_ablauf.werkzeug_beginnt("read_note", {"name": "n"})
        zug_ablauf.werkzeug_fertig(klein, "[ergebnis: ok]\n" + "y" * 40_000)
        liste = zug_ablauf.abschliessen("fertig")
    finally:
        zug_ablauf.beenden(m)
    gross, normal = liste[1], liste[2]
    assert len(json.dumps(gross, ensure_ascii=False)) <= zug_ablauf.EINTRAG_MAX
    assert gross["gekuerzt"] > 30_000 and "Zeichen gekürzt" in gross["ergebnis"]
    assert gross["ergebnis"].startswith("[ergebnis: ok]") and gross["status"] == "ok"
    assert normal["ergebnis"] == "[ergebnis: ok]\n" + "y" * 40_000 and "gekuerzt" not in normal


def test_system_nur_fingerabdruck():
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.system("Du bist ZENTRALE. " * 500)
        liste = zug_ablauf.abschliessen(None)
    finally:
        zug_ablauf.beenden(m)
    assert liste == [{"art": "system", "zeit": liste[0]["zeit"], "t": liste[0]["t"],
                      "fingerabdruck": zug_ablauf.fingerabdruck("Du bist ZENTRALE. " * 500),
                      "laenge": 18 * 500}]


# ── Ein ganzer Zug: Anthropic-Weg, gefälschtes Modell, über die Route ──

@pytest.fixture
def welt(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "an"})
    monkeypatch.setattr(kern, "cloud_modul", lambda: cloud)
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    monkeypatch.setattr(cloud.graph, "context_for_query", lambda *a, **k: "")
    monkeypatch.setattr(graph, "einmal_seeden", lambda *a, **k: None)
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(ki_prompt, "_imprint_prompt", lambda: "")
    monkeypatch.setattr(ki_prompt, "_alarm_prompt", lambda: "")
    monkeypatch.setattr(ki_prompt, "_now_prompt", lambda: "## Jetzt\nMontag, 10:00")
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    ausgefuehrt = []

    def ausfuehren(name, args):
        ausgefuehrt.append(name)
        return {"read_calendar": "Di 10:30 Zahnarzt #t1234",
                "read_note": "Zahnarzt: Dr. Beispiel, Hauptstraße 1"}[name]
    monkeypatch.setattr(ki_werkzeuge, "mit_projekt", lambda p=None: ausfuehren)
    return app.test_client()


def _runden():
    """Zwei Werkzeuge, dann eine unbelegte Erledigt-Behauptung (Korrektur-
    runde), dann die richtige Antwort."""
    return [
        {"text": ["Ich schau in Kalender und Notizen."], "stop_reason": "tool_use",
         "content": [FakeBlock("text", text="Ich schau in Kalender und Notizen."),
                     FakeBlock("tool_use", name="read_calendar", input={"tag": "dienstag"},
                               id="t1"),
                     FakeBlock("tool_use", name="read_note", input={"name": "zahnarzt"},
                               id="t2")]},
        {"text": ["Hab den Termin eingetragen."],
         "content": [FakeBlock("text", text="Hab den Termin eingetragen.")]},
        {"text": ["Dienstag 10:30 steht schon: Zahnarzt bei Dr. Beispiel."],
         "content": [FakeBlock("text", text="Dienstag 10:30 steht schon: Zahnarzt bei Dr. Beispiel.")]},
    ]


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


def test_zug_mit_zwei_werkzeugen_und_korrektur_vollstaendig_in_reihenfolge(welt, monkeypatch):
    c = FakeClient(_runden())
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    ev = _events(welt.post("/api/chat", json={"message": "hab ich dienstag zahnarzt?"}))
    gid = gespraeche.aktiv()
    antwort = gespraeche.nachrichten(gid)[-1]
    a = antwort["ablauf"]
    assert [e["art"] for e in a] == ["system", "kontext", "text", "werkzeug", "werkzeug",
                                     "pruefung", "antwort", "kosten"]
    sys_, kontext, text, w1, w2, pruefung, fertig, kosten = a
    assert sys_["laenge"] > 1000 and len(sys_["fingerabdruck"]) == 16 and "text" not in sys_
    assert "<kontext_automatisch>" in kontext["text"] and "Montag, 10:00" in kontext["text"]
    assert text["text"] == "Ich schau in Kalender und Notizen."
    assert (w1["name"], w1["args"], w1["status"]) == ("read_calendar", {"tag": "dienstag"}, "ok")
    assert w1["ergebnis"].startswith("[ergebnis: ok]") and "#t1234" in w1["ergebnis"]
    assert w2["name"] == "read_note" and "Dr. Beispiel" in w2["ergebnis"]
    assert w1["dauer"] >= 0
    assert pruefung["erste_antwort"] == "Hab den Termin eingetragen."
    assert pruefung["befunde"][0]["art"] == "tat"
    assert "<pruefung_automatisch>" in pruefung["hinweis"]
    assert fertig["text"] == antwort["text"] == "Dienstag 10:30 steht schon: Zahnarzt bei Dr. Beispiel."
    assert kosten["runden"] == 3 and kosten["eingabe"] == 300 and kosten["euro"] >= 0
    zeiten = [e["t"] for e in a]
    assert zeiten == sorted(zeiten)
    # Die TUI erfährt die id der gespeicherten Antwort.
    assert {"antwort": antwort["id"], "ablauf": 8} in ev
    # „denken" bleibt ein eigenes Feld, nicht im Ablauf.
    assert all(e["art"] != "denken" for e in a)


def test_nichts_aendert_sich_an_dem_was_ans_modell_geht(welt, monkeypatch):
    """Prompt-Cache unberührt: derselbe Zug mit und ohne Protokoll schickt
    byte-gleich dasselbe."""
    gesendet = []
    for mit in (True, False):
        c = FakeClient(_runden())
        monkeypatch.setattr(cloud, "_get_client", lambda: c)
        m = zug_ablauf.beginnen() if mit else None
        try:
            list(cloud.chat_stream([{"role": "user", "content": "hab ich dienstag zahnarzt?"}]))
        finally:
            if m is not None:
                zug_ablauf.beenden(m)
        gesendet.append(json.dumps({"system": c.calls[0]["system"],
                                    "messages": c.calls[0]["messages"],
                                    "tools": c.calls[0]["tools"]}, sort_keys=True,
                                   default=vars))
        assert len(c.calls) == 3
    assert gesendet[0] == gesendet[1]


def test_frage_mit_antwort_steht_im_ablauf(monkeypatch):
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: True)
    monkeypatch.setattr(erlaubnis, "vorab", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "merken", lambda *a, **k: None)
    monkeypatch.setattr(state, "request_permission", lambda **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda: "nein")
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)

    class Skript:
        modell = "test"
        runden = [werkzeug_schleife.Runde("", [("c1", "write_note", {"name": "x", "text": "y"})]),
                  werkzeug_schleife.Runde("Gut, ich lass es.")]

        def runde(self):
            if False:
                yield
            return self.runden.pop(0)

        def assistent_anhaengen(self, r):
            pass

        def ergebnisse_anhaengen(self, e):
            pass
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.system("fest")
        list(werkzeug_schleife.laufen(Skript(), tutor_mode=False, active_exec=lambda n, a: "ok",
                                      user_query="x", schiene="gross"))
        a = zug_ablauf.abschliessen("Gut, ich lass es.")
    finally:
        zug_ablauf.beenden(m)
    arten = [e["art"] for e in a]
    assert arten == ["system", "werkzeug", "frage", "antwort"]
    frage = a[2]
    assert frage["wie"] == "erlaubnis" and frage["antwort"] == "nein" and frage["optionen"]
    assert a[1]["status"] == "abgelehnt"


def test_lokal_speichert_keinen_ablauf(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.LOCAL)

    def lokal(verlauf, **k):
        yield "Hallo."
    import ai
    monkeypatch.setattr(ai, "chat_stream", lokal)
    ev = _events(app.test_client().post("/api/chat", json={"message": "hi"}))
    n = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert n["text"] == "Hallo." and "ablauf" not in n
    assert not any("antwort" in e for e in ev)


# ── Lesen und Export ────────────────────────────────────────────────────

def test_route_liefert_json_history_nur_die_zahl(welt, monkeypatch):
    c = FakeClient(_runden())
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    welt.post("/api/chat", json={"message": "hab ich dienstag zahnarzt?"}).get_data()
    gid = gespraeche.aktiv()
    frage, antwort = gespraeche.nachrichten(gid)
    r = welt.get(f"/api/gespraeche/{gid}/ablauf/{antwort['id']}")
    assert r.status_code == 200
    d = r.get_json()
    assert d["nachricht"] == antwort["id"] and len(d["ablauf"]) == 8
    assert d["ablauf"][3]["ergebnis"].startswith("[ergebnis: ok]")
    assert welt.get(f"/api/gespraeche/{gid}/ablauf/letzte").get_json()["nachricht"] == antwort["id"]
    # Fehlerfälle: fremde Nachricht, Frage ohne Ablauf, fremdes Gespräch.
    assert welt.get(f"/api/gespraeche/{gid}/ablauf/gibtsnicht").status_code == 404
    assert welt.get(f"/api/gespraeche/{gid}/ablauf/{frage['id']}").status_code == 404
    assert welt.get("/api/gespraeche/gibtsnicht/ablauf/letzte").status_code == 404
    h = welt.get(f"/api/chat/history?gespraech={gid}").get_json()
    assert h[-1]["ablauf_n"] == 8 and "ablauf" not in h[-1]
    laden = welt.get(f"/api/gespraeche/{gid}").get_json()
    assert laden["nachrichten"][-1]["ablauf_n"] == 8 and "ablauf" not in laden["nachrichten"][-1]


def test_trace_legt_textdatei_in_die_ablage(welt, monkeypatch):
    c = FakeClient(_runden())
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    welt.post("/api/chat", json={"message": "hab ich dienstag zahnarzt?"}).get_data()
    gid = gespraeche.aktiv()
    r = welt.post(f"/api/gespraeche/{gid}/ablauf/letzte/ablage", json={})
    assert r.status_code == 201
    dok = r.get_json()["dokument"]
    gelesen = ablage.lesen(dok["id"])
    assert gelesen["kopf"]["herkunft"] == "ablauf" and gelesen["kopf"]["gespraech"] == gid
    text = gelesen["inhalt"]
    for stueck in ("Werkzeug read_calendar", "[ergebnis: ok]", "#t1234",
                   "Hab den Termin eingetragen.", "<kontext_automatisch>", "Kosten"):
        assert stueck in text
    assert text.index("read_calendar") < text.index("read_note") < text.index("Prüfung")


def test_trace_ohne_ablauf_sagt_es(welt):
    gid = gespraeche.neu("leer")
    r = welt.post(f"/api/gespraeche/{gid}/ablauf/letzte/ablage", json={})
    assert r.status_code == 404 and "keinen" in r.get_json()["error"]
