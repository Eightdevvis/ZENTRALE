"""Das Skill-Format von Claude (core/skill_format.py, 2026-10-07): SKILL.md
mit YAML-Kopf lesen — robust, auch fremde Felder, auch ohne PyYAML — und
Claude-taugliche SKILL.md schreiben."""
import os
import sys

import pytest

import skill_format

ANTHROPIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "core", "skill_vorlagen", "anthropic")


@pytest.fixture(params=["yaml", "ohne_yaml"])
def leser(request, monkeypatch):
    """Jeder Test zweimal: mit PyYAML und mit dem eigenen Leser (ein Rechner
    ohne PyYAML muss name und description genauso lesen)."""
    if request.param == "ohne_yaml":
        monkeypatch.setitem(sys.modules, "yaml", None)
    return request.param


def test_einfacher_kopf(leser):
    roh, felder, rest = skill_format.zerlegen(
        "---\nname: plan\ndescription: Wenn er plant\n---\n\n# Plan\nSchritt")
    assert roh == "name: plan\ndescription: Wenn er plant"
    assert felder["name"] == "plan" and felder["description"] == "Wenn er plant"
    assert rest == "# Plan\nSchritt"


@pytest.mark.parametrize("kopf, erwartet", [
    ("description: >\n  eins\n  zwei\n\n  drei\n", "eins zwei\ndrei"),
    ("description: |-\n  eins\n  zwei\n", "eins\nzwei"),
    ("description: \"mit: Doppelpunkt # und Raute\"\n", "mit: Doppelpunkt # und Raute"),
    ("description: 'it''s'\n", "it's"),
    ("description: eins\n  weiter\n", "eins weiter"),
])
def test_beschreibungs_schreibweisen(leser, kopf, erwartet):
    _, felder, _ = skill_format.zerlegen(f"---\nname: x\n{kopf}---\nText")
    assert felder["description"].strip() == erwartet


def test_fremde_felder_stoeren_nicht(leser):
    text = ("---\nname: fremd\ndescription: d\nlicense: Apache-2.0\n"
            "compatibility: braucht Netz\nallowed-tools: Read Bash\n"
            "metadata:\n  version: \"1.2\"\n  author: x\n---\nText")
    _, felder, rest = skill_format.zerlegen(text)
    assert felder["name"] == "fremd" and felder["description"] == "d"
    assert felder["compatibility"] == "braucht Netz"
    assert "metadata" in felder and rest == "Text"


@pytest.mark.parametrize("text", [
    "", "nur Text", "---\nname: x\nohne Ende", "\n---\nname: x\n---\n",
    "---\n: kaputt [\n---\nText", "---\n- liste\n- statt dict\n---\nText",
])
def test_kaputtes_wirft_nie(leser, text):
    roh, felder, rest = skill_format.zerlegen(text)
    assert isinstance(felder, dict)
    assert skill_format.text_feld(felder, "description") in ("", felder.get("description"))


def test_crlf_und_bom(leser):
    _, felder, rest = skill_format.zerlegen("﻿---\r\nname: x\r\ndescription: d\r\n---\r\nT")
    assert felder["description"] == "d" and rest == "T"


def test_text_feld_einzeilig_und_nur_text():
    assert skill_format.text_feld({"d": "a\n  b"}, "d") == "a b"
    assert skill_format.text_feld({"d": 3}, "d") == ""
    assert skill_format.text_feld({}, "d") == ""


def test_alle_anthropic_skills_gleich_gelesen_mit_und_ohne_yaml(monkeypatch):
    """Der eigene Leser liest die echten Claude-Skills genau wie PyYAML."""
    for name in sorted(os.listdir(ANTHROPIC)):
        pfad = os.path.join(ANTHROPIC, name, "SKILL.md")
        if not os.path.isfile(pfad):
            continue
        with open(pfad, encoding="utf-8") as f:
            text = f.read()
        roh, mit, _ = skill_format.zerlegen(text)
        ohne = skill_format._kopf_einfach(roh)
        for feld in ("name", "description"):
            assert skill_format.text_feld(mit, feld) == skill_format.text_feld(ohne, feld), name


@pytest.mark.parametrize("name, gut", [
    ("plan", True), ("skill-creator", True), ("a1", True), ("x" * 64, True),
    ("x" * 65, False), ("Plan", False), ("-plan", False), ("plan-", False),
    ("pl--an", False), ("pl_an", False), ("../x", False), ("", False), (None, False),
])
def test_gueltiger_name(name, gut):
    assert skill_format.gueltiger_name(name) is gut


def test_rendern_ist_gueltiges_yaml_und_claude_tauglich(leser):
    beschreibung = 'Wenn: "Zitat" # keine Raute-Falle, Umlaute äöü'
    text = skill_format.rendern("plan", beschreibung, "\nSchritt eins\n")
    assert text.startswith("---\nname: plan\n")
    _, felder, rest = skill_format.zerlegen(text)
    assert felder == {"name": "plan", "description": beschreibung}
    assert rest == "Schritt eins"


def test_mit_neuer_anleitung_behaelt_kopf_woertlich():
    alt = "---\nname: x\n# Kommentar\nmetadata:\n  a: 1\n---\n\nALT\n"
    neu = skill_format.mit_neuer_anleitung(alt, "NEU")
    assert neu == "---\nname: x\n# Kommentar\nmetadata:\n  a: 1\n---\n\nNEU\n"
    assert skill_format.mit_neuer_anleitung("ohne Kopf", "NEU") == "NEU\n"
