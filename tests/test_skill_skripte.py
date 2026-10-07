"""Skill-Skripte in der Sandbox (2026-10-07): run_code(skill=…) hängt den
Ordner eines AKTIVEN Skills nur lesend unter /skills/<name> ein — sonst
bleibt alles wie in tests/test_sandbox.py abgeschottet. Geprobt mit dem
echten quick_validate.py des skill-creator von Anthropic (läuft ohne
claude und ohne Netz)."""
import json
import os

import pytest

import gedaechtnis
import ki_werkzeuge
import sandbox
import skills
import state
import zug

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREATOR = os.path.join(ROOT, "core", "skill_vorlagen", "anthropic", "skill-creator")

braucht_bwrap = pytest.mark.skipif(not sandbox.verfuegbar(),
                                   reason="bubblewrap fehlt oder startet nicht")


@pytest.fixture(autouse=True)
def eigener_ordner(tmp_path, monkeypatch):
    monkeypatch.setattr(gedaechtnis, "_DIR", str(tmp_path / "gedaechtnis"))
    monkeypatch.setattr(state, "push_log", lambda *a, **k: None)
    leer = tmp_path / "keine_vorlagen"
    leer.mkdir()
    monkeypatch.setattr(skills, "VORLAGEN_DIR", str(leer))
    monkeypatch.setattr(skills, "ANTHROPIC_STATUS", str(leer / "x.json"))


def _skill(name, status="aktiv", beschreibung="wenn es passt"):
    pfad = os.path.join(gedaechtnis.bereich_ordner(gedaechtnis.SKILLS), name)
    os.makedirs(os.path.join(pfad, "scripts"), exist_ok=True)
    with open(os.path.join(pfad, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nname: {name}\ndescription: {beschreibung}\n---\n\nText\n")
    with open(os.path.join(pfad, "_zentrale.json"), "w") as f:
        json.dump({"status": status}, f)
    with open(os.path.join(pfad, "scripts", "hallo.py"), "w") as f:
        f.write("print('hallo aus dem skill')\n")
    return pfad


@braucht_bwrap
def test_quick_validate_laeuft_in_der_sandbox():
    """Der echte Prüfer von Anthropic, nur lesend eingehängt, prüft sich
    selbst (gültig) und einen kaputten Skill im Arbeitsordner (ungültig)."""
    code = ("python3 /skills/skill-creator/scripts/quick_validate.py "
            "/skills/skill-creator; echo rc=$?\n"
            "mkdir -p kaputt && printf -- '---\\nname: Kaputt_Name\\n"
            "description: x\\n---\\n' > kaputt/SKILL.md\n"
            "python3 /skills/skill-creator/scripts/quick_validate.py kaputt; echo rc=$?")
    erg = sandbox.ausfuehren(code, sprache="shell", skill_ordner=CREATOR)
    assert erg["rc"] == 0, erg
    assert "Skill is valid!\nrc=0" in erg["ausgabe"]
    assert "kebab-case" in erg["ausgabe"] and "rc=1" in erg["ausgabe"]


@braucht_bwrap
def test_quick_validate_auf_einem_zentrale_skill(tmp_path):
    """Was propose_skill schreibt, besteht Claudes Prüfung."""
    skills.vorschlagen("einkauf", "Wenn Sasha einkaufen geht: Liste sortieren",
                       "1. Liste lesen\n2. sortieren")
    pfad = os.path.join(gedaechtnis.bereich_ordner(gedaechtnis.SKILLS), "einkauf")
    with open(os.path.join(pfad, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    erg = sandbox.ausfuehren(
        "python3 /skills/skill-creator/scripts/quick_validate.py einkauf",
        sprache="shell", skill_ordner=CREATOR, dateien={"einkauf/SKILL.md": text})
    assert erg["ausgabe"].strip() == "Skill is valid!", erg


@braucht_bwrap
def test_skill_ordner_ist_nur_lesend_und_sonst_nichts_sichtbar():
    pfad = _skill("probe")
    nachbar = os.path.join(os.path.dirname(pfad), "nachbar")
    os.makedirs(nachbar)
    erg = sandbox.ausfuehren(
        "python3 /skills/probe/scripts/hallo.py\n"
        "touch /skills/probe/neu 2>/dev/null && echo SCHREIBT || echo NURLESEN\n"
        f"ls {nachbar} 2>/dev/null && echo NACHBAR || echo WEG\n"
        "ls /skills", sprache="shell", skill_ordner=pfad)
    aus = erg["ausgabe"]
    assert "hallo aus dem skill" in aus and "NURLESEN" in aus and "WEG" in aus
    assert aus.strip().endswith("probe")
    assert not os.path.exists(os.path.join(pfad, "neu"))


def test_unbekannter_skill_ordner_laeuft_nicht(tmp_path):
    erg = sandbox.ausfuehren("print(1)", skill_ordner=str(tmp_path / "fehlt"))
    assert erg["rc"] is None and "Skill-Ordner" in erg["fehler"]


def test_run_code_mit_ausgeschaltetem_skill_laeuft_nicht(monkeypatch):
    _skill("aus", status="aus")
    gerufen = []
    monkeypatch.setattr(sandbox, "ausfuehren", lambda *a, **k: gerufen.append(k))
    text = ki_werkzeuge.ausfuehren("run_code", {"code": "print(1)", "skill": "aus"})
    assert "nicht aktiv" in text and gerufen == []
    text = ki_werkzeuge.ausfuehren("run_code", {"code": "print(1)", "skill": "../x"})
    assert "Keinen Skill" in text and gerufen == []


def test_run_code_reicht_den_skill_ordner_durch(monkeypatch):
    pfad = _skill("an")
    gerufen = []

    def attrappe(code, **k):
        gerufen.append(k)
        return sandbox._ergebnis(rc=0, ausgabe="ok")
    monkeypatch.setattr(sandbox, "ausfuehren", attrappe)
    monkeypatch.setattr(zug, "gespraech", lambda: None)
    ki_werkzeuge.ausfuehren("run_code", {"code": "print(1)", "skill": "an"})
    assert gerufen[0]["skill_ordner"] == os.path.realpath(pfad)
    ki_werkzeuge.ausfuehren("run_code", {"code": "print(1)"})
    assert gerufen[1].get("skill_ordner") is None
