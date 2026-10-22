"""
Werkzeug-Texte nach der KI-Bibel (memory/ki/bibel/werkzeuge.md), 2026-10-22:

- Schritt 9 der Werkzeug-Suche (W-08): mit Schalter an nennt der Prompt
  search_tools, die Kategorien und an jeder Stelle, die ein zurückgestelltes
  Werkzeug beim Namen nennt, „über search_tools“. Aus bleibt alles
  byte-gleich (dafür sorgen zusätzlich die Schnappschüsse).
- Großbuchstaben-Befehle raus aus den gross-Texten (W-11, P-02), klein bleibt.
- input_examples (W-05): nur gross, nur Anthropic, nur gegen das Schema gültige.
- read_document in Stücken (W-06).
"""
import re

import pytest

import cloud
import gedaechtnis
import ki_prompt
import ki_werkzeuge
import projekte
import werkzeug_beispiele
import werkzeug_register
from profil import gross, klein


@pytest.fixture
def suche_an(monkeypatch):
    monkeypatch.setenv("ZENTRALE_WERKZEUG_SUCHE", "an")


def _gross_text(name: str, tools=None) -> str:
    tools = tools if tools is not None else werkzeug_register.schema("gross")
    return next(t["function"]["description"] for t in tools
                if t["function"]["name"] == name)


# ── Schritt 9 ──────────────────────────────────────────────────────────

def test_ohne_schalter_kein_wort_von_der_suche():
    kopf = cloud._static_system(None, tutor_mode=False)
    assert "search_tools" not in kopf
    assert "search_tools" not in ki_prompt._now_prompt()
    assert "search_tools" not in _gross_text("read_calendar")


def test_mit_schalter_steht_die_suche_im_kopf(suche_an):
    kopf = cloud._static_system(None, tutor_mode=False)
    assert gross.SUCHE in kopf
    # direkt hinter den Meta-Regeln
    assert kopf.index(gross.SUCHE) > kopf.index("## Meta-Regeln")
    for name in ("antwort", "search_tools", "web_search", "fetch_url", "read_calendar"):
        assert name in gross.SUCHE


def test_mit_schalter_nennen_die_stellen_search_tools(suche_an):
    assert "read_time (über search_tools)" in ki_prompt._now_prompt(suche=True)
    assert "read_calendar_warnings holst du vorher mit search_tools" in \
        _gross_text("read_calendar")
    assert "search_tools" in gedaechtnis._REGELN_SUCHE


def test_projekt_block_mit_suche(tmp_path, monkeypatch):
    monkeypatch.setattr(projekte, "gibt_es", lambda pid: True)
    monkeypatch.setattr(projekte, "_kopf_lesen", lambda pid: {"name": "P"})
    monkeypatch.setattr(projekte, "anweisungen_lesen", lambda pid: "")
    monkeypatch.setattr(projekte, "wissen_liste",
                        lambda pid: [{"name": "a.md", "groesse": 10}])
    assert "search_tools" not in projekte.prompt_block("p")
    assert "read_project_file(name) (über search_tools)" in \
        projekte.prompt_block("p", suche=True)


def test_klein_kennt_die_suche_nicht(suche_an):
    assert not cloud._suche_im_prompt(klein)
    assert cloud._suche_im_prompt(gross)
    assert all("search_tools" not in t["function"]["description"]
               for t in werkzeug_register.schema("klein"))


# ── Großbuchstaben (W-11) ──────────────────────────────────────────────

# Eigennamen und Formate, die groß bleiben dürfen.
_ERLAUBT = {"PDF", "HTML", "URL", "CSV", "RRULE", "YYYY", "MM", "DD", "HH", "JJJJ",
            "DTSTART", "UNTIL", "COUNT", "FREQ", "WEEKLY", "BYDAY", "MONTHLY",
            "BYMONTHDAY", "DAILY", "PIL", "MB", "ZENTRALE", "LSF", "SKILL",
            "SUMIF", "SUMMEWENN", "ENDE", "VOR", "BEGINN"}


def test_keine_grossbuchstaben_befehle_in_den_gross_texten(suche_an):
    wort = re.compile(r"\b[A-ZÄÖÜ]{3,}\b")
    funde = []
    for t in werkzeug_register.schema("gross"):
        f = t["function"]
        texte = [f["description"]] + [p.get("description", "") for p in
                                      f["parameters"].get("properties", {}).values()]
        for text in texte:
            funde += [(f["name"], w) for w in wort.findall(text) if w not in _ERLAUBT]
    assert not funde, funde


def test_alarm_block_gross_ohne_dashboard(monkeypatch):
    import state
    monkeypatch.setattr(state, "get_alarms", lambda: [{"text": "⚠ KONFLIKT: x"}])
    g = ki_prompt._alarm_prompt(gross=True)
    assert "[[bild: alarm]]" not in g and "Dashboard" not in g
    assert "EINMAL" not in g and "⚠ KONFLIKT: x" in g
    # klein unverändert (Schnappschuss in test_prompt_nutzer.py)
    assert "[[bild: alarm]]" in ki_prompt._alarm_prompt()


# ── input_examples (W-05) ──────────────────────────────────────────────

def test_beispiele_nur_gross_und_gueltig():
    g = cloud._to_anthropic_tools(gross.TOOLS, beispiele=True)
    mit = {t["name"] for t in g if "input_examples" in t}
    assert mit == set(werkzeug_beispiele.BEISPIELE)
    k = cloud._to_anthropic_tools(klein.TOOLS)
    assert not any("input_examples" in t for t in k)


def test_ungueltiges_beispiel_faellt_weg():
    schema = {"type": "object", "properties": {"a": {"type": "string"}},
              "required": ["a"]}
    assert werkzeug_beispiele.fuer("read_calendar", schema) == []


def test_zurueckgestellte_bekommen_keine_beispiele():
    g = cloud._to_anthropic_tools(gross.TOOLS, {"add_calendar_routine"}, beispiele=True)
    t = next(t for t in g if t["name"] == "add_calendar_routine")
    assert t.get("defer_loading") and "input_examples" not in t


# ── read_document in Stücken (W-06) ────────────────────────────────────

def test_read_document_in_stuecken():
    import ablage
    k = ablage.anlegen("Lang", "x" * (ki_werkzeuge.LESEN_STUECK + 10), "text",
                       herkunft="ki")
    erst = ki_werkzeuge._verteilen("read_document", {"id": k["id"]})
    assert f"ab={ki_werkzeuge.LESEN_STUECK}" in str(erst)
    rest = ki_werkzeuge._verteilen("read_document",
                                   {"id": k["id"], "ab": ki_werkzeuge.LESEN_STUECK})
    assert str(rest).endswith("x" * 10)
    kurz = ablage.anlegen("Kurz", "hallo", "text", herkunft="ki")
    assert str(ki_werkzeuge._verteilen("read_document", {"id": kurz["id"]})).endswith(":\nhallo")
