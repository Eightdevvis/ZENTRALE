"""
Die Werkzeug-Suche (core/werkzeug_suche.py, memory/ki/werkzeug_suche.md):
Index und BM25, Register-Felder laden/gruppe, der Schalter (aus = alles wie
vorher), beide Adapter (Anthropic: defer_loading + tool_reference, OpenAI:
Schemas anhängen), über Züge hinweg (byte-gleiches Paar im Verlauf), Skills
mit Kurzfassung, Prüfer und Vorauswahl.

Ohne Netz: die Clients sind Fakes aus tests/test_cloud_loop.py und
tests/test_cloud_openai.py. Was die echte API annimmt, hat
scripts/werkzeug_suche_probe.py geklärt.
"""
import json

import pytest

import anhang
import cloud
import cloud_openai
import consolidation
import graph
import werkzeug_gruppen
import werkzeug_register
import werkzeug_schleife
import werkzeug_suche
from test_cloud_loop import FakeClient as AFake, _tool_block
from test_cloud_openai import FakeClient as OFake, _text as o_text, _tool as o_tool


@pytest.fixture
def suche_an(monkeypatch):
    """Schalter an, und die gross-Liste so, wie sie mit Schalter gebaut
    würde (profil.gross.TOOLS entsteht beim Import)."""
    from profil import gross
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "an")
    monkeypatch.setattr(gross, "TOOLS", werkzeug_register.schema("gross"))
    return gross.TOOLS


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(cloud.graph, "context_for_query", lambda *a, **k: "")
    monkeypatch.setattr(graph, "einmal_seeden", lambda *a, **k: None)
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)


def _namen(tools):
    return [t.get("function", t)["name"] for t in tools]


# ── Suche ──────────────────────────────────────────────────────────────

def test_lsf_bringt_die_browser_gruppe():
    t = werkzeug_suche.suchen("LSF")
    assert set(werkzeug_gruppen.GRUPPEN["browser"]) <= set(t.werkzeuge)


def test_excel_findet_die_tabellen():
    t = werkzeug_suche.suchen("Excel")
    assert {"read_xlsx", "create_xlsx", "edit_xlsx"} <= set(t.werkzeuge)


def test_routine_verschieben_findet_edit_calendar_routine():
    assert "edit_calendar_routine" in werkzeug_suche.suchen("Routine verschieben").werkzeuge


def test_kein_treffer_sagt_es_und_schaltet_nichts_frei():
    t = werkzeug_suche.suchen("qqqxyz")
    assert t.werkzeuge == () and "Kein Werkzeug" in t


def test_suche_findet_nie_antwort_und_sich_selbst():
    namen = {d.name for d in werkzeug_suche.INDEX}
    assert not namen & {"antwort", "search_tools"}
    assert "ask_choice" in namen          # zurückgestellt, also findbar


def test_hoechstens_fuenf_immer_geladen():
    assert len(werkzeug_gruppen.IMMER) <= 5
    assert {"antwort", "search_tools"} <= set(werkzeug_gruppen.IMMER)


def test_kalender_notiz_und_skill_sind_findbar():
    assert "add_calendar_entry" in werkzeug_suche.suchen("Termin eintragen").werkzeuge
    assert "write_note" in werkzeug_suche.suchen("Notiz merken").werkzeuge
    assert "load_skill" in werkzeug_suche.suchen("skill laden").werkzeuge


def test_skills_sind_findbar(monkeypatch):
    monkeypatch.setattr(werkzeug_suche, "_skill_dokumente", lambda: [
        werkzeug_suche.Dokument("skill", "kochen", [("kochen", 3),
                                                    ("Rezepte und Einkaufslisten", 1)])])
    t = werkzeug_suche.suchen("Rezepte")
    assert t.skills == ("kochen",) and "load_skill" in t.werkzeuge


def test_mcp_liste_hat_das_format_von_tools_list():
    d = werkzeug_suche.mcp_liste()
    t = next(x for x in d["tools"] if x["name"] == "read_xlsx")
    assert set(t) == {"name", "description", "inputSchema", "_meta"}
    assert t["_meta"]["zentrale/laden"] == "bedarf"
    assert t["_meta"]["zentrale/gruppe"] == "tabellen"
    json.dumps(d)


# ── Register und Gruppen ───────────────────────────────────────────────

def test_immer_geladen_ist_genau_die_liste():
    gross = {w.name: w for w in werkzeug_register.auf_schiene("gross")}
    assert {n for n, w in gross.items() if w.laden == "immer"} == set(werkzeug_gruppen.IMMER)


def test_jedes_zurueckgestellte_hat_eine_gruppe_aus_der_tabelle():
    """Ein neues gross-Werkzeug fällt hier auf: es gehört in GRUPPEN oder
    IMMER (core/werkzeug_gruppen.py)."""
    erzeugt_oder_angebunden = {w.name for w in werkzeug_register.ANGEBUNDEN}
    for w in werkzeug_register.auf_schiene("gross"):
        if w.laden == "bedarf" and w.name not in erzeugt_oder_angebunden:
            assert w.name in werkzeug_gruppen.GRUPPE_VON, w.name


def test_gruppen_tabelle_nennt_nur_echte_werkzeuge():
    alle = {w.name for w in werkzeug_register.WERKZEUGE}
    for gruppe in (werkzeug_gruppen.GRUPPEN, {k: v[1] for k, v in
                                              werkzeug_gruppen.VORAUSWAHL.items()}):
        for g, namen in gruppe.items():
            assert set(namen) <= alle, g


def test_qwen_liest_dieselbe_tabelle():
    from profil.modelle import qwen
    assert qwen._GRUPPEN is werkzeug_gruppen.VORAUSWAHL


def test_schalter_aus_laesst_die_liste_wie_sie_war(monkeypatch):
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "aus")
    aus = werkzeug_register.schema("gross")
    assert "search_tools" not in _namen(aus)
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "an")
    an = werkzeug_register.schema("gross")
    assert an[:-1] == aus and _namen(an)[-1] == "search_tools"
    assert "search_tools" not in _namen(werkzeug_register.schema("klein"))


def test_search_tools_ohne_gate():
    assert not werkzeug_register.braucht_erlaubnis("search_tools", {"query": "x"})


# ── Anthropic ──────────────────────────────────────────────────────────

def test_defer_loading_nur_auf_den_zurueckgestellten(suche_an):
    tools = cloud._to_anthropic_tools(suche_an, werkzeug_suche.zurueckgestellt())
    zurueck = {t["name"] for t in tools if t.get("defer_loading")}
    assert zurueck == werkzeug_suche.zurueckgestellt()
    assert "search_tools" not in zurueck and "read_calendar" not in zurueck


def test_ohne_zurueckstellen_kein_defer_loading(suche_an):
    assert not any("defer_loading" in t for t in cloud._to_anthropic_tools(suche_an))


def _a_fake(monkeypatch, runden):
    c = AFake(runden)
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    return c


def test_anthropic_suche_liefert_nur_tool_reference(suche_an, monkeypatch):
    c = _a_fake(monkeypatch, [
        {"stop_reason": "tool_use",
         "content": [_tool_block("search_tools", {"query": "Excel"}, id="t1")]},
        {"stop_reason": "end_turn", "text": ["ok"]},
    ])
    events = list(cloud.chat_stream([{"role": "user", "content": "excel bitte"}]))
    erste = c.calls[0]
    assert any(t.get("defer_loading") for t in erste["tools"])
    ergebnis = c.calls[1]["messages"][-1]["content"]
    assert ergebnis[0]["type"] == "tool_result"
    inhalt = ergebnis[0]["content"]
    assert all(b["type"] == "tool_reference" for b in inhalt)
    assert {"read_xlsx", "create_xlsx", "edit_xlsx"} <= {b["tool_name"] for b in inhalt}
    frei = [e["werkzeug"].get("freigeschaltet") for e in events
            if isinstance(e, dict) and "werkzeug" in e and e["werkzeug"].get("freigeschaltet")]
    assert frei and "read_xlsx" in frei[0]["namen"] and frei[0]["anfrage"] == "Excel"


def test_anthropic_ohne_treffer_bleibt_text(suche_an, monkeypatch):
    c = _a_fake(monkeypatch, [
        {"stop_reason": "tool_use",
         "content": [_tool_block("search_tools", {"query": "qqqxyz"}, id="t1")]},
        {"stop_reason": "end_turn", "text": ["ok"]},
    ])
    list(cloud.chat_stream([{"role": "user", "content": "x"}]))
    inhalt = c.calls[1]["messages"][-1]["content"][0]["content"]
    assert isinstance(inhalt, str) and "Kein Werkzeug" in inhalt


def test_zurueckgestelltes_ohne_suche_laeuft_trotzdem(suche_an, monkeypatch):
    c = _a_fake(monkeypatch, [
        {"stop_reason": "tool_use", "content": [_tool_block("read_time", {}, id="t1")]},
        {"stop_reason": "end_turn", "text": ["ok"]},
    ])
    list(cloud.chat_stream([{"role": "user", "content": "wie spät?"}]))
    inhalt = c.calls[1]["messages"][-1]["content"][0]["content"]
    assert inhalt.startswith("[ergebnis: ok]")


def test_zurueckgestelltes_ohne_suche_geht_durchs_gate(suche_an, monkeypatch):
    gefragt = []

    def nein(name, args):
        gefragt.append(name)
        return False
        yield  # noqa: unreachable — Generator wie das Original

    monkeypatch.setattr(werkzeug_schleife, "_ask_permission", nein)
    _a_fake(monkeypatch, [
        {"stop_reason": "tool_use", "content": [_tool_block(
            "add_calendar_routine", {"label": "Geige", "rrule": "FREQ=WEEKLY"}, id="t1")]},
        {"stop_reason": "end_turn", "text": ["ok"]},
    ])
    list(cloud.chat_stream([{"role": "user", "content": "geige jede woche"}]))
    assert gefragt == ["add_calendar_routine"]


def test_tool_result_nimmt_listen():
    r = cloud._tool_result("x", [{"type": "tool_reference", "tool_name": "a"}])
    assert r["content"] == [{"type": "tool_reference", "tool_name": "a"}]
    assert cloud._tool_result("x", 5)["content"] == "5"


def test_skills_kommen_als_text_neben_den_ergebnissen(suche_an):
    a = cloud._AnthropicAdapter(None, "m", [], [], cloud._to_anthropic_tools(suche_an),
                                suche=True)
    t = werkzeug_suche.Treffer("x", ("read_xlsx",), ("excel",), "Excel")
    a.ergebnisse_anhaengen([("t1", t, False)])
    bloecke = a.msgs[-1]["content"]
    assert bloecke[0]["content"] == [{"type": "tool_reference", "tool_name": "read_xlsx"}]
    assert bloecke[1]["type"] == "text" and "excel" in bloecke[1]["text"]
    assert a.freigeschaltet.namen == ["read_xlsx"]


# ── Über Züge hinweg ───────────────────────────────────────────────────

def _spur():
    return [{"name": "search_tools", "args": "query=Excel", "status": "ok",
             "freigeschaltet": {"anfrage": "Excel", "namen": ["read_xlsx", "create_xlsx"]}}]


def _verlauf():
    return [{"role": "user", "content": "mach eine tabelle"},
            {"role": "assistant", "content": "Erledigt.", "werkzeuge": _spur()},
            {"role": "user", "content": "und jetzt?"}]


def test_verlauf_einsetzen_gibt_die_suche_mit(suche_an):
    v = anhang.verlauf_einsetzen(_verlauf(), cloud=True)
    assert v[1]["suche"] == [{"anfrage": "Excel", "namen": ["read_xlsx", "create_xlsx"]}]


def test_verlauf_ohne_schalter_ohne_suche(monkeypatch):
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "aus")
    assert "suche" not in anhang.verlauf_einsetzen(_verlauf(), cloud=True)[1]


def test_paar_wird_byte_gleich_eingesetzt(suche_an):
    v = anhang.verlauf_einsetzen(_verlauf(), cloud=True)
    eins = json.dumps(cloud._prepare_messages(v), ensure_ascii=False, sort_keys=True)
    zwei = json.dumps(cloud._prepare_messages(anhang.verlauf_einsetzen(_verlauf(), cloud=True)),
                      ensure_ascii=False, sort_keys=True)
    assert eins == zwei
    msgs = cloud._prepare_messages(v)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant", "user"]
    aufruf, ergebnis = msgs[1]["content"][0], msgs[2]["content"][0]
    assert aufruf["type"] == "tool_use" and aufruf["name"] == "search_tools"
    assert aufruf["input"] == {"query": "Excel"}
    assert ergebnis["tool_use_id"] == aufruf["id"]
    assert [b["tool_name"] for b in ergebnis["content"]] == ["read_xlsx", "create_xlsx"]


def test_weggefallenes_werkzeug_wird_nicht_referenziert():
    spur = [{"freigeschaltet": {"anfrage": "x", "namen": ["gibt_es_nicht"]}}]
    assert werkzeug_suche.aus_spur(spur) == []


def test_anthropic_adapter_kennt_das_frueher_freigeschaltete(suche_an, monkeypatch):
    c = _a_fake(monkeypatch, [{"stop_reason": "end_turn", "text": ["ok"]}])
    list(cloud.chat_stream(anhang.verlauf_einsetzen(_verlauf(), cloud=True)))
    tools = {t["name"]: t for t in c.calls[0]["tools"]}
    # Die Liste bleibt dieselbe (Cache); freigeschaltet wird über das Paar.
    assert tools["read_xlsx"].get("defer_loading") is True


def test_ui_merkt_die_freischaltung():
    from ui.routen import ki
    werkzeuge = []
    ki._werkzeug_merken(werkzeuge, {"phase": "start", "name": "search_tools",
                                    "args": {"query": "Excel"}})
    ki._werkzeug_merken(werkzeuge, {"phase": "fertig", "name": "search_tools", "text": "x",
                                    "freigeschaltet": {"anfrage": "Excel",
                                                       "namen": ["read_xlsx"]}})
    assert werkzeuge[0]["freigeschaltet"] == {"anfrage": "Excel", "namen": ["read_xlsx"]}


# ── OpenAI ─────────────────────────────────────────────────────────────

@pytest.fixture
def o_fake(monkeypatch):
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", "{}")

    def bauen(runden):
        c = OFake(runden)
        monkeypatch.setattr(cloud_openai, "_get_client", lambda prov: c)
        monkeypatch.setattr(cloud_openai, "_provider",
                            lambda name=None: {"kind": "openai_compat",
                                               "base_url": "http://test",
                                               "key_env": "X",
                                               "default_model": "qwen-plus"})
        return c
    return bauen


def test_openai_beginnt_mit_dem_kern_und_haengt_gefundenes_an(suche_an, o_fake):
    c = o_fake([o_tool("search_tools", '{"query": "Excel"}'), o_text("ok")])
    list(cloud_openai.chat_stream([{"role": "user", "content": "hallo"}]))
    erste, zweite = _namen(c.calls[0]["tools"]), _namen(c.calls[1]["tools"])
    assert set(erste) == set(werkzeug_suche.immer())
    assert zweite[:len(erste)] == erste
    assert {"read_xlsx", "create_xlsx", "edit_xlsx"} <= set(zweite[len(erste):])


def test_openai_nimmt_vorab_und_verlauf_mit(suche_an, o_fake):
    c = o_fake([o_text("ok")])
    verlauf = anhang.verlauf_einsetzen(_verlauf(), cloud=True)
    verlauf[-1]["content"] = "kannst du im lsf nachsehen?"
    list(cloud_openai.chat_stream(verlauf))
    namen = _namen(c.calls[0]["tools"])
    assert "browser_open" in namen and "read_xlsx" in namen
    assert namen.index("read_xlsx") > namen.index("browser_open")


def test_openai_ohne_schalter_wie_bisher(o_fake):
    from profil import gross
    c = o_fake([o_text("ok")])
    list(cloud_openai.chat_stream([{"role": "user", "content": "hallo"}]))
    # Seit 2026-10-22 mit dem Satz zum Freigabestand (erlaubnis.mit_freigabe,
    # KI-Bibel W-03) — sonst dieselbe Liste.
    import erlaubnis
    assert c.calls[0]["tools"] == erlaubnis.mit_freigabe(gross.TOOLS)


# ── Profil: Vorauswahl und Prüfer ──────────────────────────────────────

def test_modell_schiene_vorab_und_pruefer_kennen_zurueckgestellte(monkeypatch):
    from profil import gross
    from profil.modelle import ModellSchiene, qwen
    s = ModellSchiene(gross, qwen)
    assert "browser_open" in s.vorab([{"role": "user", "content": "lsf"}])
    gesehen = {}
    monkeypatch.setattr(qwen, "pruefer",
                        lambda basis, werkzeuge=frozenset(), **_: gesehen.update(w=werkzeuge))
    s.pruefer(object())
    assert werkzeug_suche.zurueckgestellt() <= gesehen["w"]


# ── Skills ─────────────────────────────────────────────────────────────

def test_skill_liste_kurz_und_load_skill_mit_beschreibung(monkeypatch):
    import skills
    lang = ("Erster Satz sagt wann. Zweiter Satz mit vielen Einzelheiten, "
            "die nur beim Laden gebraucht werden.")
    monkeypatch.setattr(skills, "aktive", lambda: [{"name": "probe", "beschreibung": lang}])
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "aus")
    assert "Zweiter Satz" in skills.prompt_block()
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "an")
    block = skills.prompt_block()
    assert "- probe — Erster Satz sagt wann." in block and "Zweiter Satz" not in block
    assert len(skills.kurzzeile("x" * 400)) <= skills.KURZ_ZEILE
