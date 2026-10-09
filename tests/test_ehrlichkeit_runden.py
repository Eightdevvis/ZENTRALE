"""
Prüfen bis bestanden (2026-10-09, memory/ki/ehrlichkeit_live.md): bis zu
`pruefer_runden` Korrekturrunden, danach raus mit Warnungen; der
Modellwechsel beim Budget-Rückfall als eigenes Ereignis; ältere Browser-
Seiten im laufenden Zug eingedampft. Gefälschte Modelle, kein echter Aufruf.

Anlass: Gespräch 20261009-150713 — qwen (Budget-Rückfall) schrieb „Alles
korrigiert …" ohne Werkzeug, erfand #r7d2c & Co., strich nach EINER Runde
nur die Kennungen, und die zweite Antwort ging ungeprüft raus.
"""
import json

import pytest

import ai_backends
import ai_config
import browser_sitzung
import cloud
import cloud_openai
import consolidation
import ehrlichkeit
import ehrlichkeit_erkennen as erkennen
import erlaubnis
import gespraeche
import graph
import kern
import ki_browser
import ki_prompt
import ki_werkzeuge
import werkzeug_schleife
import zug_ablauf
from test_cloud_loop import FakeBlock, FakeClient

R = werkzeug_schleife.Runde

# Der Fall vom 09.10., gekürzt: kein Werkzeug, Tat behauptet, Kennungen erfunden.
ERFUNDEN = ("Alles korrigiert: alle Vorlesungen laufen jetzt **exakt vom 12.10. bis "
            "18.12.2026**.\nDie Übungsgruppen sind jetzt als Routinen eingetragen — "
            "#r7d2c, #r1a2b, #r3c4d, #r5e6f.")
OHNE_KENNUNG = ("Alles korrigiert: alle Vorlesungen laufen jetzt exakt vom 12.10. bis "
                "18.12.2026.\nDie Übungsgruppen sind jetzt als Routinen eingetragen.")


class _Skript:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)
        self.hinweise = []

    def runde(self):
        if False:
            yield
        return self.runden.pop(0)

    def assistent_anhaengen(self, r):
        pass

    def ergebnisse_anhaengen(self, e):
        pass

    def hinweis_anhaengen(self, r, text):
        self.hinweise.append(text)


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})


def _laufen(adapter, exec_=lambda n, a: "ok", runden=None):
    p = ehrlichkeit.Pruefer("an", runden=runden)
    return list(werkzeug_schleife.laufen(adapter, tutor_mode=False, active_exec=exec_,
                                         user_query="x", schiene="gross", pruefer=p))


def _texte(ev):
    return [e for e in ev if isinstance(e, str)]


# ── Erkennung ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("satz", ["Alles korrigiert: alle laufen jetzt ab dem 12.10.",
                                  "Beides erledigt.", "Alle angelegt!"])
def test_alles_korrigiert_ist_eine_tat(satz):
    assert len(erkennen.taten(satz)) == 1


@pytest.mark.parametrize("satz", ["Alles korrigiert?", "Alles korrigiert wäre schön.",
                                  "Nicht alles korrigiert.", "Alles gut so."])
def test_alles_ohne_behauptung(satz):
    assert erkennen.taten(satz) == []


def test_jeder_bereich_hat_ein_wort_fuer_sasha():
    bereiche = set(ehrlichkeit.BEREICH.values()) | set(erkennen.BEREICH_WOERTER)
    assert bereiche <= set(ehrlichkeit.BEREICH_NAMEN)


# ── Der heutige Fall ────────────────────────────────────────────────────

def test_heutiger_fall_fuenf_korrekturen_dann_raus_mit_warnungen():
    a = _Skript([R(ERFUNDEN)] + [R(OHNE_KENNUNG)] * 5)
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.system("fest")
        ev = _laufen(a)
        ablauf = zug_ablauf.abschliessen("x")
    finally:
        zug_ablauf.beenden(m)
    assert _texte(ev) == [OHNE_KENNUNG]           # erst nach 5 Runden, mit Warnung
    assert len(a.hinweise) == 5
    # Runde 1 nennt ALLE Befunde, auch die Kennungen.
    assert "#r7d2c" in a.hinweise[0] and "Alles korrigiert" in a.hinweise[0]
    # Ab Runde 2 deutlicher: kein Werkzeug lief.
    assert ehrlichkeit.KEIN_WERKZEUG not in a.hinweise[0]
    assert ehrlichkeit.KEIN_WERKZEUG in a.hinweise[1]
    assert "Prüfrunde 2 von 5" in a.hinweise[1]
    assert "Letzte Prüfrunde" in a.hinweise[4]
    fortschritt = [e["pruefung_runde"] for e in ev if isinstance(e, dict) and "pruefung_runde" in e]
    assert [f["runde"] for f in fortschritt] == [1, 2, 3, 4, 5]

    p = ev[-1]["ehrlichkeit"]
    assert p["zeile"] == ehrlichkeit.KEINE_AENDERUNG
    assert p["korrekturen"] == 5
    w = p["warnungen"]
    assert w and all(x.startswith("⚠") for x in w)
    assert any("Ohne Beleg: „Alles korrigiert" in x and "es wurde nichts geändert" in x
               for x in w)
    assert any("(Kalender)" in x for x in w)
    # Nie im Text der KI.
    assert not any("⚠" in t for t in _texte(ev))
    # Im Ablauf: 5 Prüfungen mit Rundennummer, dann die Warnungen.
    pr = [e for e in ablauf if e["art"] == "pruefung"]
    assert [e["runde"] for e in pr] == [1, 2, 3, 4, 5]
    assert [e["text"] for e in ablauf if e["art"] == "warnung"] == w
    assert "Korrekturrunde 5" in zug_ablauf.kopfzeile(pr[-1])


def test_bessert_sich_in_runde_2_keine_warnung():
    a = _Skript([R(ERFUNDEN), R(OHNE_KENNUNG),
                 R("Ich habe noch nichts geändert — soll ich die Routinen jetzt anpassen?")])
    ev = _laufen(a)
    assert len(a.hinweise) == 2
    p = ev[-1]["ehrlichkeit"]
    assert "warnungen" not in p and "befunde" not in p
    assert p["zeile"] == "" and p["korrekturen"] == 2


def test_kennung_plural_und_nicht_da_warnung():
    w = ehrlichkeit.warnungen([{"art": "kennung", "kennung": "#r7d2c"},
                               {"art": "kennung", "kennung": "#r1a2b"},
                               {"art": "nicht_da", "satz": "Die Datei gibt es nicht."}])
    assert w == ["⚠ ‚Nicht da' ohne vollständige Suche: „Die Datei gibt es nicht.“ — "
                 "es kann trotzdem da sein.",
                 "⚠ Erfundene Kennungen #r7d2c, #r1a2b — stehen in keinem Werkzeug-Ergebnis."]
    assert ehrlichkeit.warnungen([{"art": "kennung", "kennung": "#r7d2c"}]) == [
        "⚠ Erfundene Kennung #r7d2c — steht in keinem Werkzeug-Ergebnis."]


def test_warnung_wenn_anderes_geschrieben_wurde():
    prot = [ehrlichkeit.Schritt("write_note", {}, "ok", "")]
    (w,) = ehrlichkeit.warnungen([{"art": "tat", "satz": "Termin verschoben.",
                                   "bereiche": ["kalender"]}], prot)
    assert "dafür wurde nichts geändert" in w and "(Kalender)" in w


def test_einstellung_pruefer_runden(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"pruefer_runden": "2"})
    assert ehrlichkeit.pruefer_runden() == 2
    monkeypatch.setattr(ai_config, "_overrides", {"pruefer_runden": "quatsch"})
    assert ehrlichkeit.pruefer_runden() == ehrlichkeit.RUNDEN_STANDARD == 5
    monkeypatch.setattr(ai_config, "_overrides", {"pruefer_runden": "0"})
    a = _Skript([R(ERFUNDEN)])
    ev = list(werkzeug_schleife.laufen(a, tutor_mode=False, active_exec=lambda n, x: "ok",
                                       user_query="x", schiene="gross",
                                       pruefer=ehrlichkeit.Pruefer("an")))
    assert a.hinweise == [] and ev[-1]["ehrlichkeit"]["warnungen"]


def test_rundengrenze_und_pruefer_zusammen(monkeypatch):
    """Eine Korrekturrunde ist EIN Durchlauf der Schleife; in der letzten
    erlaubten Runde wird nicht mehr korrigiert — die Antwort geht mit
    Warnungen raus, nicht als „Maximale Tool-Tiefe"."""
    monkeypatch.setattr(ai_backends, "runden_grenze", lambda m: 3)
    a = _Skript([R(ERFUNDEN)] * 3)
    ev = _laufen(a)
    assert len(a.hinweise) == 2
    assert not any(isinstance(e, dict) and "fehler" in e for e in ev)
    assert ev[-1]["ehrlichkeit"]["warnungen"]


def test_werkzeug_in_der_korrektur_belegt_dann_kein_befund():
    a = _Skript([R(OHNE_KENNUNG),
                 R("", [("c1", "edit_calendar_routine", {"label": "Übung A"})]),
                 R("Hab die Routine Übung A angepasst.")])
    ev = _laufen(a, lambda n, x: "[ergebnis: ok]\nRoutine geändert: #r1234 Übung A")
    p = ev[-1]["ehrlichkeit"]
    assert len(a.hinweise) == 1 and "warnungen" not in p
    assert p["zeile"] == "✓ Routine geändert: Übung A"


# ── Route: gespeichert, SSE, Verlauf ────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "an"})
    return app.test_client()


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


def _zug(client, monkeypatch, runden, wechsel=None):
    monkeypatch.setattr(ai_backends, "modell_wechsel", lambda: wechsel)

    def gen(history, **k):
        p = ehrlichkeit.pruefer_fuer(history, schiene="gross", tutor_mode=False)
        yield from werkzeug_schleife.laufen(
            _Skript(runden), tutor_mode=False, user_query="x", schiene="gross",
            active_exec=lambda n, a: "ok", pruefer=p)

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    monkeypatch.setattr(ki_prompt, "_alarm_prompt", lambda: "")
    return _events(client.post("/api/chat", json={"message": "ok"}))


WECHSEL = {"von": "claude-x", "zu": "qwen-plus", "von_anbieter": "claude",
           "zu_anbieter": "qwen", "grund": "Monatsbudget 8,50 € von 8,00 € überschritten",
           "satz": "⚠ Budget voll — antwortet jetzt qwen-plus statt claude-x "
                   "(Monatsbudget 8,50 € von 8,00 € überschritten)"}


def test_route_speichert_warnungen_und_wechsel(client, monkeypatch):
    ev = _zug(client, monkeypatch, [R(ERFUNDEN)] + [R(OHNE_KENNUNG)] * 5, wechsel=WECHSEL)
    arten = [next(iter(e)) for e in ev]
    # Der Wechsel kommt vor dem ersten Text, die Warnungen als eigenes Event.
    assert arten.index("modell_wechsel") < arten.index("token")
    warn = next(e["warnungen"] for e in ev if "warnungen" in e)
    assert sum(1 for e in ev if "pruefung_runde" in e) == 5
    gid = gespraeche.aktiv()
    antwort = gespraeche.nachrichten(gid)[-1]
    assert antwort["warnungen"] == warn
    assert antwort["modell_wechsel"]["zu"] == "qwen-plus"
    assert antwort["erledigt"] == {"zeile": ehrlichkeit.KEINE_AENDERUNG, "schritte": []}
    assert antwort["pruefung"]["korrekturen"] == 5
    assert "⚠" not in antwort["text"]
    h = client.get("/api/chat/history").get_json()[-1]
    assert h["warnungen"] == warn and h["modell_wechsel"]["satz"] == WECHSEL["satz"]

    # TUI: Warnzeilen ÜBER der Antwort, in Warnfarbe.
    from tui.ansichten.chat_gespraeche import verlauf_aus
    from tui.ansichten import verlauf
    log = verlauf_aus([h])
    i_ai = max(i for i, (r, _t) in enumerate(log) if r == "ai")
    assert [r for r, _t in log[:i_ai]][-len(warn) - 1:] == ["warnung"] * (len(warn) + 1)
    assert log[i_ai - len(warn) - 1] == ("warnung", WECHSEL["satz"])
    assert ("erledigt", ehrlichkeit.KEINE_AENDERUNG) in log[i_ai:]
    stile = {s for z in verlauf.verlauf_zeilen(log, 60) for t, s, _z in z if t.startswith("⚠")}
    assert stile == {"warnung"}


def test_route_ohne_befund_ohne_warnung(client, monkeypatch):
    ev = _zug(client, monkeypatch, [R("Gern.")])
    assert not any("warnungen" in e or "modell_wechsel" in e for e in ev)
    antwort = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert "warnungen" not in antwort and "modell_wechsel" not in antwort


# ── Modellwechsel ───────────────────────────────────────────────────────

def test_modell_wechsel_beim_budget_rueckfall(monkeypatch):
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "qwen")
    monkeypatch.setattr(ai_backends, "gewollter_provider", lambda: "claude")
    monkeypatch.setattr(ai_backends, "budget_lage",
                        lambda: {"status": "over", "ausgegeben": 8.5, "limit": 8.0})
    monkeypatch.setattr(ai_backends, "chat_model",
                        lambda p=None: {"qwen": "qwen-plus", "claude": "claude-opus-5"}[p])
    w = ai_backends.modell_wechsel()
    assert w["von"] == "claude-opus-5" and w["zu"] == "qwen-plus"
    assert w["grund"] == "Monatsbudget 8,50 € von 8,00 € überschritten"
    assert w["satz"].startswith("⚠ Budget voll — antwortet jetzt qwen-plus statt claude-opus-5")
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "claude")
    assert ai_backends.modell_wechsel() is None


def test_kern_meldet_wechsel_am_anfang(monkeypatch):
    monkeypatch.setattr(ai_backends, "modell_wechsel", lambda: WECHSEL)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "qwen")

    class Modul:
        @staticmethod
        def chat_stream(v, **k):
            yield "hallo"
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    ev = list(kern.chat([], backend=ai_backends.CLOUD))
    assert ev == [{"modell_wechsel": WECHSEL}, "hallo"]


def test_status_nennt_den_wechsel_und_tui_titel(client, monkeypatch):
    monkeypatch.setattr(ai_backends, "modell_wechsel", lambda: WECHSEL)
    monkeypatch.setattr(ai_backends, "status", lambda fresh=False: {"cloud_provider": "qwen"})
    st = client.get("/api/ai/status").get_json()
    assert st["modell_wechsel"]["zu"] == "qwen-plus"


# ── Browser eindampfen ──────────────────────────────────────────────────

def _seite_text(n, laenge=4000):
    return ki_browser.seite_als_text(
        {"url": f"https://lsf.example/{n}", "host": "lsf.example", "titel": f"LSF {n}",
         "text": "Vorlesung " * (laenge // 10), "elemente": [], "rahmen_fremd": 0})


def test_eindampfen_zeile():
    t = "[ergebnis: ok]\n" + _seite_text(1)
    z = ki_browser.eindampfen("browser_open", t)
    assert z == ("[ergebnis: ok]\n[Seite „LSF 1“ https://lsf.example/1 — gelesen, "
                 "ersetzt durch spätere Seite]")
    assert ki_browser.eindampfen("read_calendar", t) is None
    assert ki_browser.eindampfen("browser_open", "[ergebnis: fehlgeschlagen]\nkurz") is None
    assert ki_browser.seite_geladen("browser_click", t)
    assert not ki_browser.seite_geladen("browser_read", t)


@pytest.fixture
def anthropic(monkeypatch):
    monkeypatch.setattr(cloud.graph, "context_for_query", lambda *a, **k: "")
    monkeypatch.setattr(graph, "einmal_seeden", lambda *a, **k: None)
    monkeypatch.setattr(ki_prompt, "_imprint_prompt", lambda: "")
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    seiten = iter(range(1, 100))
    monkeypatch.setattr(ki_werkzeuge, "mit_projekt",
                        lambda p: (lambda n, a: _seite_text(next(seiten))))
    monkeypatch.setattr(browser_sitzung, "verfuegbar", lambda: (True, ""), raising=False)


def _klick_runden(n):
    runden = [{"stop_reason": "tool_use",
               "content": [FakeBlock("tool_use", name="browser_click", input={"nr": k},
                                     id=f"t{k}")]} for k in range(n)]
    return runden + [{"text": ["Gefunden."], "content": [FakeBlock("text", text="Gefunden.")]}]


def _gesendet(c):
    """Zeichen, die je Runde an die API gingen (System + Nachrichten)."""
    return [len(json.dumps(k["system"], ensure_ascii=False))
            + len(json.dumps(k["messages"], ensure_ascii=False, default=str))
            for k in c.calls]


def test_anthropic_dampft_alte_seiten_ein_cache_anfang_bleibt(monkeypatch, anthropic):
    c = FakeClient(_klick_runden(3))
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    ev = list(cloud.chat_stream([{"role": "user", "content": "lsf durchklicken"}]))
    assert "Gefunden." in ev
    letzte = c.calls[-1]["messages"]
    ergebnisse = [b for m in letzte if isinstance(m["content"], list)
                  for b in m["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]
    assert len(ergebnisse) == 3
    assert "ersetzt durch spätere Seite" in ergebnisse[0]["content"]
    assert "ersetzt durch spätere Seite" in ergebnisse[1]["content"]
    assert "Vorlesung" in ergebnisse[2]["content"]                 # die neueste bleibt
    # Cache-Anfang: System und Sashas Nachricht (mit Breakpoint) unverändert.
    assert c.calls[-1]["system"] == c.calls[0]["system"]
    assert letzte[0]["content"][0] == c.calls[0]["messages"][0]["content"][0]
    assert letzte[0]["content"][0].get("cache_control")


def test_kostenvergleich_zehn_seiten(monkeypatch, anthropic):
    """Grob: 10 Seiten in einem Zug. Ohne Eindampfen wächst jede Runde um
    eine ganze Seite, mit Eindampfen nur um eine Zeile."""
    c = FakeClient(_klick_runden(10))
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    list(cloud.chat_stream([{"role": "user", "content": "x"}]))
    mit = sum(_gesendet(c))

    monkeypatch.setattr(ki_browser, "eindampfen", lambda n, t: None)
    c2 = FakeClient(_klick_runden(10))
    monkeypatch.setattr(cloud, "_get_client", lambda: c2)
    list(cloud.chat_stream([{"role": "user", "content": "x"}]))
    ohne = sum(_gesendet(c2))
    print(f"\nBrowser 10 Seiten: ohne {ohne:,} Zeichen, mit {mit:,} Zeichen "
          f"({100 * mit / ohne:.0f} %)")
    assert mit < 0.7 * ohne


def test_tui_strom_setzt_warnungen_ueber_die_antwort(monkeypatch):
    """Live in der TUI: Wechsel und Warnungen ÜBER der eben gestreamten Antwort."""
    from types import SimpleNamespace
    from test_chat_strom import _laufen as strom_laufen, _Schirm
    from tui.ansichten import chat, chat_gespraeche, chat_strom
    ch = chat.Chat(SimpleNamespace(stdscr=_Schirm(), C={}))
    ch.AI.update(active=True, gid="a", titel="t", loaded=True, log=[("user", "alt")])
    ch.verlauf_laden = lambda gid=None: None
    monkeypatch.setattr(chat_gespraeche, "api_call", lambda *a, **k: {})
    monkeypatch.setattr(chat_strom, "api_call", lambda *a, **k: {})
    warn = ["⚠ Erfundene Kennung #r7d2c — steht in keinem Werkzeug-Ergebnis."]
    strom_laufen(ch, monkeypatch, [
        {"strom": "z1"}, {"gespraech": "a", "nachricht": "n1"},
        {"modell_wechsel": WECHSEL}, {"pruefung_runde": {"runde": 1, "von": 5}},
        {"token": "Alles korrigiert."}, {"warnungen": warn},
        {"ehrlichkeit": {"erledigt": [], "zeile": ehrlichkeit.KEINE_AENDERUNG,
                         "warnungen": warn}},
        {"done": True}])
    log = ch.AI["log"]
    i = log.index(("ai", "Alles korrigiert."))
    assert log[i - 2:i] == [("warnung", WECHSEL["satz"]), ("warnung", warn[0])]
    assert ("erledigt", ehrlichkeit.KEINE_AENDERUNG) in log[i:]


def test_openai_adapter_dampft_ein():
    a = cloud_openai._OpenAIAdapter(None, "m", [{"role": "system", "content": "s"}], [])
    a.ergebnisse_anhaengen([("c1", "alt", False), ("c2", "neu", False)])
    assert a.ergebnis_eindampfen("c1", "[kurz]")
    assert [m["content"] for m in a.msgs[1:]] == ["[kurz]", "neu"]
    assert not a.ergebnis_eindampfen("weg", "x")
