"""
Längen-Wächter für den festen System-Prompt der großen Schiene (2026-10-14).

Der feste Kopf (cloud._static_system: Schiene gross + Gedächtnis-Kopf +
Skill-Liste + Imprint) geht bei JEDEM Zug und JEDER Werkzeug-Runde mit.
Wächst er still, merkt man es erst an der Rechnung — und daran, dass die
Regeln im Rauschen untergehen. Dieser Test wird rot, sobald er das Budget
überschreitet.

Gemessen wird in der Test-Umgebung: Gedächtnis und Kalender sind leer
(conftest), die Skill-Liste kommt aus den Vorlagen. Sashas eigene Notizen
(Steckbrief, Ziele, Hausregeln, Index) kommen im echten Betrieb dazu —
am 14.10.2026 mit seinen Daten gemessen: 19.017 Zeichen gesamt.

Die Werkzeug-Beschreibungen zählen bewusst NICHT gegen das Budget: sie
kommen später über einen Index (nur die passenden Werkzeuge im Kopf). Ihr
Umfang wird hier nur ausgegeben (`pytest -s` oder `-rP`).
"""
import json

import cloud
from profil import gross

# Maßstab: Anthropics eigener claude.ai-System-Prompt für Sonnet 5.5 hat
# ~20.300 Zeichen ohne Werkzeuge (Stand 28.09.2026). Mehr als das soll der
# feste Kopf hier nicht tragen — ein Assistent für EINEN Menschen braucht
# keinen längeren Prompt als eine Chat-App für alle.
PROMPT_BUDGET_ZEICHEN = 21_000


def _fester_kopf() -> str:
    return cloud._static_system(None, tutor_mode=False)


def test_fester_prompt_bleibt_im_budget():
    """Rot heißt: erst Ballast suchen (Doppeltes, Veraltetes, was in eine
    Werkzeug-Beschreibung gehört), dann erst über das Budget reden."""
    laenge = len(_fester_kopf())
    assert laenge <= PROMPT_BUDGET_ZEICHEN, (
        f"fester System-Prompt (gross) {laenge} Zeichen > Budget "
        f"{PROMPT_BUDGET_ZEICHEN}")


def test_werkzeuge_nur_als_info():
    """Kein Budget, nur die Zahlen — damit man sieht, wo das Gewicht liegt."""
    beschreibungen = sum(len(t["function"].get("description", ""))
                         for t in gross.TOOLS)
    schema = len(json.dumps(gross.TOOLS, ensure_ascii=False))
    kopf = len(_fester_kopf())
    print(f"\n[prompt-budget] fester Kopf {kopf}/{PROMPT_BUDGET_ZEICHEN} Zeichen "
          f"(Schiene {len(gross.system())}); Werkzeuge: {len(gross.TOOLS)} Stück, "
          f"Beschreibungen {beschreibungen} Zeichen, Schema gesamt {schema} Zeichen")
    assert schema > 0
