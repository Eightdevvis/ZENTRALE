"""Leerer Erststart: der Prompt nennt den Nutzer aus den Einstellungen.

2026-10-09 (memory/system/produkt_inventur.md, Punkt 1). Persona, Meta-Regeln
und die Prompt-Bausteine nannten Sasha fest beim Namen. Jetzt stehen dort
Platzhalter, gefüllt aus `nutzer_name` und `nutzer_pronomen`
(core/nutzer_angaben.py). Festgehalten wird:

  1. Mit den Standardwerten ist der gesendete Prompt BYTE-gleich wie vorher.
     Der Schnappschuss unter tests/fixtures/prompt_schnappschuss.json wurde
     mit dem Code VOR dem Umbau gezogen. Ein verschobenes Zeichen bricht den
     Anthropic-Cache, und das lokale qwen ist auf genau diese Texte gemessen.
  2. Mit einem anderen Namen steht nirgends mehr „Sasha" im Prompt.

Neu schreiben (nur wenn sich ein Prompt-Text ABSICHTLICH ändert):
    venv/bin/python tests/test_prompt_nutzer.py --neu
"""
import json
import os
import sys
from datetime import datetime as _echt_datetime

import pytest

HIER = os.path.dirname(os.path.abspath(__file__))
SCHNAPPSCHUSS = os.path.join(HIER, "fixtures", "prompt_schnappschuss.json")

_ALARME = [{"text": "⚠ ABSAGEN: Geige am 12.10. fällt in die Reise"}]


class _FesteZeit(_echt_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 9, 14, 30)


def aktuell():
    """Alles, was als fester Text ans Modell geht — über die Namen, die vor
    UND nach dem Umbau dieselben sind."""
    import ki_prompt
    import state
    from profil import gross, klein

    aus = {}
    for dv in (True, False):
        for gr in (True, False):
            aus[f"klein_dashview{int(dv)}_graph{int(gr)}"] = klein.system(dashview=dv, graph=gr)
    aus["gross"] = gross.system()
    aus["mic"] = ki_prompt._MIC_INPUT_HINT
    alt_zeit, alt_alarme, alt_dv = ki_prompt.datetime, state.get_alarms, ki_prompt._DASHVIEW
    ki_prompt.datetime = _FesteZeit
    state.get_alarms = lambda: list(_ALARME)
    try:
        aus["jetzt"] = ki_prompt._now_prompt()
        for dv in (True, False):
            ki_prompt._DASHVIEW = dv
            aus[f"alarm_dashview{int(dv)}"] = ki_prompt._alarm_prompt()
    finally:
        ki_prompt.datetime, state.get_alarms, ki_prompt._DASHVIEW = alt_zeit, alt_alarme, alt_dv
    return aus


@pytest.fixture
def standard(monkeypatch):
    """Standardwerte: weder Env noch Config setzt Name oder Pronomen."""
    import ai_config
    for n in ("nutzer_name", "nutzer_pronomen"):
        monkeypatch.delenv("ZENTRALE_" + n.upper(), raising=False)
        monkeypatch.delitem(ai_config._overrides, n, raising=False)
    monkeypatch.setattr(ai_config, "_config", {})
    monkeypatch.setattr(ai_config, "_legacy", {})


def _gespeichert():
    with open(SCHNAPPSCHUSS, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("teil", sorted(_gespeichert()) if os.path.exists(SCHNAPPSCHUSS) else [])
def test_standardwerte_sind_byte_gleich(standard, teil):
    assert aktuell()[teil] == _gespeichert()[teil]


@pytest.fixture
def alex(standard, monkeypatch):
    monkeypatch.setenv("ZENTRALE_NUTZER_NAME", "Alex")


def test_anderer_name_kein_sasha_im_prompt(alex):
    for teil, text in aktuell().items():
        assert "sasha" not in text.lower(), teil
    assert "Alex" in aktuell()["gross"]
    assert "ALEX' Gefühl" in aktuell()["klein_dashview1_graph1"]


def test_pronomen_sie(alex, monkeypatch):
    monkeypatch.setenv("ZENTRALE_NUTZER_PRONOMEN", "sie")
    g = aktuell()["gross"]
    assert "Alex ist eine mündige Erwachsene und wird so behandelt. Sie kennt ihre Prioritäten" in g
    assert "in ihrem Leben" in g and "Was du über sie weißt, steht in ihren Notizen" in g
    k = aktuell()["klein_dashview0_graph0"]
    assert "Fragt Alex nach ihren Mails" in k and "wenn sie gezielt" in k


def test_unbekanntes_pronomen_faellt_auf_standard(standard, monkeypatch):
    monkeypatch.setenv("ZENTRALE_NUTZER_PRONOMEN", "xyz")
    assert aktuell()["gross"] == _gespeichert()["gross"]


def test_genitiv_bei_s_am_ende(standard, monkeypatch):
    import nutzer_angaben
    monkeypatch.setenv("ZENTRALE_NUTZER_NAME", "Jonas")
    assert nutzer_angaben.einsetzen("{nutzers} Plan, {NUTZERS} Plan") == "Jonas' Plan, JONAS' Plan"


def test_fremde_klammern_bleiben(standard):
    import nutzer_angaben
    assert nutzer_angaben.einsetzen('{"a": 1} {unbekannt} {nutzer}') == '{"a": 1} {unbekannt} Sasha'


def test_kopf_ist_pro_einstellung_stabil(alex):
    """Prompt-Cache: zwei Züge mit derselben Einstellung, derselbe Kopf."""
    from profil import gross, klein
    assert gross.system() == gross.system()
    assert klein.system() == klein.system()


if __name__ == "__main__":
    if "--neu" not in sys.argv:
        sys.exit("Nur mit --neu: überschreibt den Schnappschuss.")
    sys.path[:0] = [os.path.join(os.path.dirname(HIER), "core"),
                    os.path.dirname(HIER)]
    os.environ.setdefault("ZENTRALE_LOKALE_KI", "aus")
    with open(SCHNAPPSCHUSS, "w", encoding="utf-8") as f:
        json.dump(aktuell(), f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("geschrieben:", SCHNAPPSCHUSS)
