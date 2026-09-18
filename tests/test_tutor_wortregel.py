"""Wortregel: nur Wörter der Zielsprache kommen in die Vokabelliste.

2026-09-18: qwen rief als Ling Ling show_thought(word="maybe", meaning=
"vielleicht", reading="měi bān"). Das englische Wort lag danach als Vokabel im
chinesischen Stand und stand in jedem Prompt-Vokabelblock. Die Tools hatten
dem Modell blind vertraut — jetzt prüft die Grenze.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "core"))

from tutor import staende, tools, memory, srs, session   # noqa: E402


@pytest.fixture
def welt(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    session.deactivate()
    return root


@pytest.mark.parametrize("lang,wort,ok", [
    ("zh", "也许", True), ("zh", "maybe", False), ("zh", "vielleicht", False), ("zh", "měi bān", False),
    ("es", "agua", True), ("es", "water", False), ("es", "Wasser", False), ("es", "也许", False),
    ("es", "quizás", True), ("es", "no", True),
    ("de", "Wasser", True), ("de", "water", False), ("de", "ja", True), ("de", "也许", False),
])
def test_wortregel(lang, wort, ok):
    assert tools.wort_gueltig(wort, lang)[0] is ok, (lang, wort, tools.wort_gueltig(wort, lang))


def test_show_thought_lehnt_fremdwort_ab_und_legt_nichts_an(welt):
    sid = staende.anlegen(welt, "LL", lang="zh"); staende.waehlen(welt, sid)
    session.activate()
    antwort = tools.show_thought("maybe", "vielleicht", "měi bān", lang="zh")
    assert "maybe" in antwort and "中文" in antwort, antwort      # Rückmeldung auf Chinesisch
    assert tools._load_raw("zh") == []
    assert session.room_state()["thought_word"] == ""            # kein Gedanke gezeigt
    assert tools.show_thought("也许", "vielleicht", "yě xǔ", lang="zh") == "ok"
    assert [e["word"] for e in tools._load_raw("zh")] == ["也许"]
    session.deactivate()


def test_altlast_faellt_beim_laden_raus(welt):
    """Ein Stand, in dem 'maybe' schon liegt (vor der Regel): beim Laden weg,
    beim nächsten Schreiben endgültig — ohne dass jemand aufräumen muss."""
    sid = staende.anlegen(welt, "alt", lang="zh"); staende.waehlen(welt, sid)
    p = os.path.join(welt, "staende", sid, "zh", "vocab.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump([{"word": "maybe", "reading": "měi bān", "spoken": 0, "listened": 0},
                   {"word": "还是", "reading": "hái shì", "spoken": 1, "listened": 0}], f, ensure_ascii=False)
    assert [e["word"] for e in tools._load_raw("zh")] == ["还是"]
    assert "maybe" not in {w for w, _ in tools.prompt_vocab("zh")}
    tools.introduce_new("面", "miàn", lang="zh")
    with open(p, encoding="utf-8") as f:
        assert [e["word"] for e in json.load(f)] == ["还是", "面"]


def test_kernwort_nimmt_glosse_aus_den_daten_nicht_vom_modell(welt, monkeypatch):
    """也许 ist Kernwort: die Blase zeigt die Glosse in der Muttersprache, egal
    was das Modell als meaning schickt."""
    from tutor import config
    monkeypatch.setattr(config, "_overrides", {"native": "de"})
    sid = staende.anlegen(welt, "LL", lang="zh"); staende.waehlen(welt, sid)
    session.activate()
    tools.show_thought("也许", "maybe", "", lang="zh")
    rs = session.room_state()
    assert rs["thought_word"] == "也许" and rs["thought_meaning"] == "vielleicht"
    tools.show_thought("面", "Nudeln", "miàn", lang="zh")      # emergent → Modell-Bedeutung
    assert session.room_state()["thought_meaning"] == "Nudeln"
    session.deactivate()


def test_tooltext_nennt_die_muttersprache_konkret(monkeypatch):
    """Das Modell muss wissen, in WELCHER Sprache es die Bedeutung schreibt —
    »Muttersprache« allein liest qwen als Englisch."""
    from tutor import config
    monkeypatch.setattr(config, "_overrides", {"native": "de"})
    for lang, erwartet in (("es", "alemán"), ("zh", "德语"), ("de", "Deutsch")):
        st = next(t for t in tools.tools_for(lang) if t["function"]["name"] == "show_thought")
        beschr = st["function"]["parameters"]["properties"]["meaning"]["description"]
        assert erwartet in beschr and "{native}" not in beschr, (lang, beschr)
    monkeypatch.setattr(config, "_overrides", {"native": "en"})
    st = next(t for t in tools.tools_for("es") if t["function"]["name"] == "show_thought")
    assert "inglés" in st["function"]["parameters"]["properties"]["meaning"]["description"]


def test_emergentes_wort_speichert_bedeutung_einmal(welt):
    """Nichts doppelt erfinden lassen: die Bedeutung eines emergenten Worts wird
    beim Einführen gespeichert und bleibt."""
    sid = staende.anlegen(welt, "LL", lang="zh"); staende.waehlen(welt, sid)
    session.activate()
    tools.show_thought("面", "Nudeln", "miàn", lang="zh")
    e = {x["word"]: x for x in tools._load_raw("zh")}["面"]
    assert e.get("meaning") == "Nudeln" and e.get("reading") == "miàn"
    tools.show_thought("面", "Pasta", "", lang="zh")          # nochmal, anders → bleibt bei der ersten
    assert {x["word"]: x for x in tools._load_raw("zh")}["面"]["meaning"] == "Nudeln"
    assert session.room_state()["thought_meaning"] == "Nudeln"
    session.deactivate()
