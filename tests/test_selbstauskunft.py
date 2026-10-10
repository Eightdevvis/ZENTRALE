"""
Selbstauskunft über das Werkzeug `antwort` (2026-10-10, memory/ki/
ehrlichkeit_live.md, „Selbstauskunft"): auf gross gibt die KI jede Antwort
über antwort(text, erledigt, fragt_erlaubnis, schiebt_auf, ungeprueft) ab,
Python vergleicht die Felder mit dem Werkzeug-Protokoll — sprachfrei. Freier
Text → Wortlisten wie bisher. Widerspruch Feld/Wortliste → „unsicher", der
Klassifikator (wenn an) entscheidet. Jede geprüfte Antwort → ein Beispiel.

Gefälschte Modelle, kein echter Aufruf.
"""
import json

import pytest

import abgleich_auswahl
import ai_config
import billig
import cloud
import cloud_openai
import consolidation
import ehrlichkeit
import erlaubnis
import graph
import klassifikator
import klassifikator_beispiele
import selbstauskunft
import usage
import werkzeug_register
import werkzeug_schleife
from profil import gross, klein
from profil.modelle import qwen
from test_cloud_loop import FakeBlock, FakeClient

R = werkzeug_schleife.Runde


def _antwort(text, erledigt=(), fragt=False, schiebt=False, id="a1", **mehr):
    args = {"text": text, "erledigt": list(erledigt), "fragt_erlaubnis": fragt,
            "schiebt_auf": schiebt, **mehr}
    return R("", [(id, "antwort", args)])


class _Skript:
    """Adapter wie in test_ehrlichkeit_runden, dazu nachricht_anhaengen und
    ein Mitschnitt, was in welcher Reihenfolge angehängt wurde."""
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)
        self.verlauf = []

    def runde(self):
        if False:
            yield
        return self.runden.pop(0)

    def assistent_anhaengen(self, r):
        self.verlauf.append(("assistent", [c[1] for c in r.calls]))

    def ergebnisse_anhaengen(self, e):
        self.verlauf.append(("ergebnisse", [(cid, text) for cid, text, _ in e]))

    def hinweis_anhaengen(self, r, text):
        self.verlauf.append(("hinweis", text))

    def nachricht_anhaengen(self, text):
        self.verlauf.append(("nachricht", text))

    @property
    def hinweise(self):
        return [t for art, t in self.verlauf if art in ("hinweis", "nachricht")]


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})
    monkeypatch.setattr(klassifikator, "_backends", {})


def _laufen(adapter, nutzer="", exec_=lambda n, a: "ok", schiene="gross"):
    p = ehrlichkeit.Pruefer("an", nutzer_text=nutzer)
    ev = list(werkzeug_schleife.laufen(adapter, tutor_mode=False, active_exec=exec_,
                                       user_query=nutzer, schiene=schiene, pruefer=p))
    return ev, p


def _texte(ev):
    return [e for e in ev if isinstance(e, str)]


def _schluss(ev):
    return next((e["ehrlichkeit"] for e in ev if isinstance(e, dict) and "ehrlichkeit" in e),
                None)


# ── Form ────────────────────────────────────────────────────────────────

def test_bereiche_sind_die_schreibenden_bereiche_des_pruefers():
    assert set(selbstauskunft.BEREICHE) == set(ehrlichkeit.BEREICH.values()) - {"netz"}
    assert set(selbstauskunft.BEREICHE) <= set(ehrlichkeit.BEREICH_NAMEN)


def test_lesen_ist_tolerant():
    a = selbstauskunft.lesen({"text": " Hi ", "erledigt": "Kalender, wetter",
                              "fragt_erlaubnis": "true", "schiebt_auf": None})
    assert a.text == "Hi" and a.erledigt == ["kalender"] and a.fremd == ["wetter"]
    assert a.fragt_erlaubnis is True and a.schiebt_auf is False
    assert selbstauskunft.lesen(None).erledigt == []


def test_schema_nur_auf_gross_und_klein_bleibt_wie_es_war():
    g = next(t["function"] for t in gross.TOOLS if t["function"]["name"] == "antwort")
    k = next(t["function"] for t in klein.TOOLS if t["function"]["name"] == "antwort")
    assert g["parameters"]["required"] == selbstauskunft.PFLICHT
    assert g["parameters"]["properties"]["erledigt"]["items"]["enum"] == list(selbstauskunft.BEREICHE)
    assert k["parameters"] == {"type": "object", "properties": {"text": {
        "type": "string", "description": "Die fertige Antwort für den User."}},
        "required": ["text"]}
    assert werkzeug_register.eintrag("antwort").in_der_schleife


# ── Tat gegen Feld ──────────────────────────────────────────────────────

def test_erledigt_ohne_werkzeug_ist_ein_befund_auch_auf_englisch():
    a = _Skript([_antwort("Done, it's in your calendar.", ["kalender"]),
                 _antwort("Nothing changed yet — want me to add it?")])
    ev, p = _laufen(a, nutzer="trag zahnarzt morgen 10 uhr ein")
    assert _texte(ev) == ["Nothing changed yet — want me to add it?"]
    assert len(a.hinweise) == 1
    assert "Feld erledigt" in a.hinweise[0] and "kalender" in a.hinweise[0]
    # Erst Ergebnis für den antwort-Aufruf, DANN der Hinweis als Nachricht.
    arten = [art for art, _ in a.verlauf]
    assert arten == ["assistent", "ergebnisse", "nachricht"]
    assert a.verlauf[1][1][0][1] == werkzeug_schleife.ZURUECKGEHALTEN


def test_erledigt_mit_werkzeug_kein_befund():
    a = _Skript([R("", [("t1", "add_calendar_entry",
                         {"label": "Zahnarzt", "day": "2026-10-09", "time": "10:00"})]),
                 _antwort("Steht drin: Zahnarzt morgen 10:00.", ["kalender"])])
    ev, p = _laufen(a, nutzer="trag zahnarzt morgen 10 uhr ein")
    assert _texte(ev) == ["Steht drin: Zahnarzt morgen 10:00."]
    assert a.hinweise == [] and p.befunde == []
    assert _schluss(ev)["auskunft"]["erledigt"] == ["kalender"]


def test_werkzeug_lief_aber_erledigt_leer_kein_befund():
    a = _Skript([R("", [("t1", "add_calendar_entry", {"label": "Zahnarzt"})]),
                 _antwort("Zahnarzt morgen um zehn.")])
    ev, p = _laufen(a, nutzer="trag zahnarzt morgen 10 uhr ein")
    assert p.befunde == [] and a.hinweise == []
    assert "✓" in _schluss(ev)["zeile"]


def test_falscher_bereich_ist_ein_befund():
    a = _Skript([R("", [("t1", "add_calendar_entry", {"label": "Zahnarzt"})]),
                 _antwort("Done.", ["kalender", "notiz"]),
                 _antwort("Done.", ["kalender"])])
    ev, p = _laufen(a, nutzer="trag ein und notier es")
    assert len(a.hinweise) == 1 and "notiz" in a.hinweise[0]


# ── Erlaubnis-Frage und Aufschub über das Feld ──────────────────────────

def test_fragt_erlaubnis_korrektur_dann_werkzeug():
    a = _Skript([_antwort("Should I add it to your calendar?", fragt=True),
                 R("", [("t1", "add_calendar_entry", {"label": "Zahnarzt"})]),
                 _antwort("Added: dentist tomorrow 10:00.", ["kalender"])])
    ev, p = _laufen(a, nutzer="trag zahnarzt morgen 10 uhr ein")
    assert _texte(ev) == ["Added: dentist tomorrow 10:00."]
    assert len(a.hinweise) == 1 and "frag nicht im Text um Erlaubnis" in a.hinweise[0]
    assert p.befunde == []


def test_fragt_erlaubnis_ohne_auftrag_bleibt_ruhig():
    # Sasha erzählt nur; die Frage ist ein Angebot, kein Zögern.
    a = _Skript([R("", [("t1", "read_time", {})]),
                 _antwort("Should I set a reminder?", fragt=True)])
    ev, p = _laufen(a, nutzer="heute war lang")
    assert a.hinweise == [] and p.befunde == []


def test_schiebt_auf_wird_korrigiert():
    a = _Skript([_antwort("I'll pause it once I know when the holidays end.", schiebt=True),
                 R("", [("t1", "add_calendar_pause", {"label": "Geige", "von": "2026-10-08"})]),
                 _antwort("Paused from today. Until when?", ["kalender"])])
    ev, p = _laufen(a, nutzer="geige fällt wegen der ferien jetzt aus")
    assert len(a.hinweise) == 1 and "klar beauftragt" in a.hinweise[0]
    assert _texte(ev) == ["Paused from today. Until when?"]


# ── Rückfall und Widerspruch ────────────────────────────────────────────

def test_freier_text_faellt_auf_die_wortlisten_zurueck():
    a = _Skript([R("Hab ich eingetragen."), R("Noch nichts eingetragen.")])
    ev, p = _laufen(a, nutzer="trag zahnarzt ein")
    assert len(a.hinweise) == 1
    assert [art for art, _ in a.verlauf] == ["hinweis"]   # alter Weg, unverändert
    assert p.auskunft is None


def test_widerspruch_ohne_klassifikator_gilt_die_wortliste():
    a = _Skript([_antwort("Hab den Termin eingetragen."),
                 _antwort("Noch nichts geändert.")])
    ev, p = _laufen(a, nutzer="trag zahnarzt ein")
    assert len(a.hinweise) == 1
    b = ehrlichkeit.befunde("Hab den Termin eingetragen.", [], nutzer_text="x",
                            auskunft=selbstauskunft.lesen({"erledigt": []}))
    assert b[0]["unsicher"] and b[0]["quelle"] == "wortliste"


@pytest.mark.parametrize("urteil,korrigiert", [("nein", False), ("ja", True)])
def test_widerspruch_klassifikator_entscheidet(monkeypatch, urteil, korrigiert):
    gefragt = []

    def fragen(system, text, modell, anbieter):
        gefragt.append(text)
        return urteil
    monkeypatch.setenv("ZENTRALE_KLASSIFIKATOR", "cloud")
    monkeypatch.setattr(klassifikator, "_backends",
                        {"cloud": klassifikator.Cloud(modell="claude-haiku-4-5", fragen=fragen)})
    a = _Skript([_antwort("Hab den Termin eingetragen."),
                 _antwort("Noch nichts geändert.")])
    ev, p = _laufen(a, nutzer="trag zahnarzt ein")
    assert len(gefragt) == 1 and "Hab den Termin eingetragen." in gefragt[0]
    assert bool(a.hinweise) is korrigiert


def test_feld_ohne_wortliste_ist_kein_widerspruch(monkeypatch):
    # Das Modell sagt selbst „erledigt", die Wortliste kennt die Sprache
    # nicht: kein Klassifikator nötig, geprüft wird das Feld.
    monkeypatch.setenv("ZENTRALE_KLASSIFIKATOR", "cloud")
    monkeypatch.setattr(klassifikator, "_backends", {"cloud": klassifikator.Cloud(
        fragen=lambda *a: pytest.fail("Klassifikator gefragt"))})
    b = ehrlichkeit.befunde("C'est fait.", [], nutzer_text="x",
                            auskunft=selbstauskunft.lesen({"erledigt": ["kalender"]}))
    assert b == [{"art": "tat", "satz": "", "bereiche": ["kalender"], "quelle": "auskunft"}]


def test_warnung_ohne_satz():
    w = ehrlichkeit.warnungen([{"art": "tat", "satz": "", "bereiche": ["kalender"]}])
    assert w == ["⚠ Ohne Beleg: die Antwort meldet eine Änderung — in diesem Zug lief "
                 "kein passendes Werkzeug (Kalender), es wurde nichts geändert."]


# ── antwort zusammen mit anderen Werkzeugen ─────────────────────────────

def test_antwort_mit_anderen_werkzeugen_kommt_zurueck():
    a = _Skript([R("", [("t1", "add_calendar_entry", {"label": "Zahnarzt"}),
                        ("a1", "antwort", {"text": "Erledigt.", "erledigt": ["kalender"]})]),
                 _antwort("Steht drin.", ["kalender"], id="a2")])
    ev, p = _laufen(a, nutzer="trag ein")
    assert _texte(ev) == ["Steht drin."]
    ergebnisse = dict(a.verlauf[1][1])
    assert ergebnisse["a1"] == werkzeug_schleife.NICHT_ALLEIN
    assert [s.name for s in p.protokoll] == ["add_calendar_entry"]


def test_klein_bleibt_beim_alten_antwort_weg():
    a = _Skript([R("", [("a1", "antwort", {"text": "Hallo."})])])
    ev = list(werkzeug_schleife.laufen(a, tutor_mode=False, active_exec=lambda n, x: "",
                                       user_query="x", schiene="klein"))
    assert "Hallo." in _texte(ev)
    assert any(isinstance(e, dict) and e.get("werkzeug", {}).get("name") == "antwort"
               for e in ev)


def test_gross_zeigt_antwort_nicht_als_werkzeug():
    a = _Skript([_antwort("Hallo.")])
    ev, _ = _laufen(a)
    assert _texte(ev) == ["Hallo."]
    assert not any(isinstance(e, dict) and "werkzeug" in e for e in ev)


def test_leeres_textfeld_nimmt_den_freien_text():
    a = _Skript([R("Hallo frei.", [("a1", "antwort", {"erledigt": []})])])
    ev, _ = _laufen(a)
    assert _texte(ev) == ["Hallo frei."]


# ── Echte Adapter: was an die API geht ──────────────────────────────────

@pytest.fixture
def anthropic_fake(monkeypatch):
    monkeypatch.setattr(cloud.graph, "context_for_query", lambda *a, **k: "")
    monkeypatch.setattr(graph, "einmal_seeden", lambda *a, **k: None)

    def bauen(runden):
        c = FakeClient(runden)
        monkeypatch.setattr(cloud, "_get_client", lambda: c)
        return c
    return bauen


def test_anthropic_hinweis_steht_hinter_dem_tool_result(anthropic_fake):
    c = anthropic_fake([
        {"stop_reason": "tool_use", "content": [FakeBlock(
            "tool_use", name="antwort", id="a1",
            input={"text": "Eingetragen.", "erledigt": ["kalender"],
                   "fragt_erlaubnis": False, "schiebt_auf": False})]},
        {"stop_reason": "tool_use", "content": [FakeBlock(
            "tool_use", name="antwort", id="a2",
            input={"text": "Noch nichts geändert.", "erledigt": [],
                   "fragt_erlaubnis": False, "schiebt_auf": False})]},
    ])
    ev = list(cloud.chat_stream([{"role": "user", "content": "trag zahnarzt ein"}]))
    assert [e for e in ev if isinstance(e, str)] == ["Noch nichts geändert."]
    letzte = c.calls[1]["messages"][-1]
    assert letzte["role"] == "user"
    typen = [b["type"] for b in letzte["content"]]
    assert typen == ["tool_result", "text"]
    assert letzte["content"][0]["tool_use_id"] == "a1"
    assert "<pruefung_automatisch>" in letzte["content"][1]["text"]
    # Das Werkzeug geht mit den Feldern an Anthropic.
    werkzeug = next(t for t in c.calls[0]["tools"] if t["name"] == "antwort")
    assert "erledigt" in werkzeug["input_schema"]["properties"]


def test_openai_hinweis_nach_role_tool():
    a = cloud_openai._OpenAIAdapter(None, "qwen-plus", [{"role": "system", "content": "s"}], [])
    runde = R("", [("a1", "antwort", {"text": "x"})],
              roh=[{"id": "a1", "name": "antwort", "args": '{"text": "x"}'}])
    werkzeug_schleife._korrektur_anhaengen(a, runde, runde.calls[0], "HINWEIS")
    assert [m["role"] for m in a.msgs] == ["system", "assistant", "tool", "user"]
    assert a.msgs[2]["tool_call_id"] == "a1" and a.msgs[3]["content"] == "HINWEIS"


# ── qwen ────────────────────────────────────────────────────────────────

def test_qwen_antwort_pflicht(monkeypatch):
    tools = [{"function": {"name": "read_calendar"}}, {"function": {"name": "antwort"}}]
    verlauf = [{"role": "user", "content": "wie war das wetter"}]
    assert qwen.tool_choice(nr=1, verlauf=verlauf, tools=tools) is None
    monkeypatch.setenv("ZENTRALE_ANTWORT_PFLICHT", "an")
    assert qwen.tool_choice(nr=1, verlauf=verlauf, tools=tools) == "required"
    assert qwen.tool_choice(nr=0, verlauf=verlauf, tools=tools[1:]) == "required"
    # Runde 0 mit Änderungswunsch: weiter erst lesen.
    aendern = [{"role": "user", "content": "lösch nyam"}]
    assert qwen.tool_choice(nr=0, verlauf=aendern, tools=tools)["function"]["name"] \
        == "read_calendar"


def test_qwen_zusatzpruefer_reicht_die_auskunft_durch():
    from profil.modelle import zusatzpruefer
    basis = ehrlichkeit.Pruefer("an", nutzer_text="trag ein")
    z = zusatzpruefer.ZusatzPruefer(basis, "trag ein", {"antwort"})
    k = z.nach_antwort("Done.", letzte_runde=False,
                       auskunft=selbstauskunft.lesen({"erledigt": ["kalender"]}))
    assert k and "Feld erledigt" in k


# ── Beispiele ───────────────────────────────────────────────────────────

def test_jede_gepruefte_antwort_schreibt_ein_beispiel():
    a = _Skript([_antwort("Done, it's in your calendar.", ["kalender"]),
                 _antwort("Nothing changed yet.")])
    _laufen(a, nutzer="trag zahnarzt ein")
    alle = klassifikator_beispiele.lesen()
    assert len(alle) == 2                        # beide geprüften Antworten
    erst = alle[0]
    assert erst["auskunft"]["erledigt"] == ["kalender"]
    assert erst["befunde"][0]["quelle"] == "auskunft"
    assert erst["saetze"] and "knoten" in erst
    assert alle[1]["runde"] == 1


def test_beispiele_aus(monkeypatch):
    monkeypatch.setenv("ZENTRALE_BEISPIELE_SAMMELN", "aus")
    _laufen(_Skript([_antwort("Hi.")]))
    assert klassifikator_beispiele.lesen() == []


def test_beispiele_nicht_im_abgleich():
    assert not abgleich_auswahl.passt("data/klassifikator_beispiele/2026-10-pc.jsonl")


# ── Klassifikator ───────────────────────────────────────────────────────

def test_wortlisten_satzarten():
    arten = klassifikator.Wortlisten().satzarten(
        "Hab ich eingetragen. Soll ich im Netz nach den Ferien suchen? Wann genau?")
    assert [a["art"] for a in arten] == ["behauptung_tat", "erlaubnisfrage", "frage"]


def test_standard_ist_aus():
    assert klassifikator.modus() == "aus"


def test_lokal_ohne_modelle_faellt_auf_wortliste(monkeypatch):
    monkeypatch.setenv("ZENTRALE_KLASSIFIKATOR", "lokal")
    monkeypatch.setattr(klassifikator.Lokal, "verfuegbar", staticmethod(lambda: False))
    assert klassifikator.entscheiden("Hab ich eingetragen.", "behauptung_tat") is True


def test_cloud_ist_gecacht_und_bucht_mit_zweck(monkeypatch):
    usage.zuruecksetzen()
    gebucht = []

    class Antwort:
        content = [type("B", (), {"type": "text", "text": "ja"})()]
        usage = type("U", (), {"input_tokens": 80, "output_tokens": 1})()

    class Messages:
        def create(self, **kw):
            gebucht.append(kw["model"])
            return Antwort()

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: type("C", (), {"messages": Messages()})())
    c = klassifikator.Cloud(modell="claude-haiku-4-5")
    assert c.entscheiden("Hab ich eingetragen.", "behauptung_tat") is True
    assert c.entscheiden("Hab ich eingetragen.", "behauptung_tat") is True
    assert gebucht == ["claude-haiku-4-5"]                      # einmal gefragt
    d = json.load(open(usage._FILE, encoding="utf-8"))
    assert any(d.get("zwecke", {}).get("klassifikator", {}).values())
    assert sum(v["calls"] for v in d["monate"].values()) == 1    # im Chat-Topf


def test_anbieter_fuer_modell():
    assert klassifikator.anbieter_fuer("claude-haiku-4-5") == "claude"
    assert klassifikator.anbieter_fuer("qwen-turbo") == "qwen"
    assert klassifikator.anbieter_fuer(None) is None


def test_billig_nimmt_den_anbieter(monkeypatch):
    seen = {}

    def falsch(*a, **k):
        raise AssertionError("aktiver Anbieter gefragt")
    monkeypatch.setattr(billig.ai_backends, "cloud_provider", falsch)
    monkeypatch.setattr(billig.providers, "get", lambda n: seen.setdefault("n", n) and {})
    with pytest.raises(billig.KeinWeg):
        billig.einmal("s", "t", anbieter="claude")
    assert seen["n"] == "claude"
