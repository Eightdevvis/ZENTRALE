"""Das Werkzeug-Register darf nichts ändern, was ein Modell oder Sasha sieht.

2026-10-07, Phase 0 des Claude-Web-Plans (memory/ki/claude_web_plan.md): die
Werkzeuge zogen aus drei Stellen (profil/klein.py + gross.py, ki_werkzeuge,
erlaubnis) in EIN Register (core/werkzeug_register.py). Der Schnappschuss
unter tests/fixtures/werkzeug_schnappschuss.json wurde mit dem Code VOR dem
Umbau gezogen (Commit davor) und hält fest:

  1. Die Werkzeug-Listen beider Schienen, in beiden Dialekten (OpenAI-Schema
     und Anthropic), BYTE-gleich. Ein verschobenes Komma bricht den
     Anthropic-Prompt-Cache (die Werkzeuge stehen vor allem anderen im
     gecachten Anfang) — und das lokale qwen ist auf genau diese Texte
     gemessen.
  2. Erlaubnis-Gate und Frage-Text für jedes Werkzeug (beide Schreibweisen)
     mit typischen Argumenten: wer gefragt wird und was er liest.

Neu schreiben (nur wenn sich die Liste ABSICHTLICH ändert, z. B. ein neues
Werkzeug auf der gross-Schiene):
    venv/bin/python tests/test_werkzeug_schnappschuss.py --neu
"""
import json
import os
import sys

import pytest

HIER = os.path.dirname(os.path.abspath(__file__))
SCHNAPPSCHUSS = os.path.join(HIER, "fixtures", "werkzeug_schnappschuss.json")

# Typische Argumente: deckt jedes Feld ab, das eine Frage-Vorlage liest,
# dazu leere und kaputte Fälle.
ARGUMENTE = [
    {},
    {"label": "Zahnarzt", "day": "2026-10-08", "time": "10:00"},
    {"label": "Geige", "day": "2026-10-08"},
    {"label": "  ", "day": " ", "time": ""},
    {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU"},
    {"label": "Geige", "von": "2026-10-01", "bis": "2026-10-10"},
    {"label": "Geige", "aktion": "loeschen"},
    {"label": "Geige", "aktion": "aendern", "time": "18:00", "ende": "19:00",
     "ort": "Schule", "rrule": "FREQ=WEEKLY", "neuer_titel": "Geige neu"},
    {"label": "Geige", "aktion": "aendern"},
    {"name": "hausregeln", "text": "Nicht duzen."},
    {"name": "regeln", "text": "x " * 150},
    {"name": "sasha", "text": "mag Tee"},
    {"name": "ziele", "text": "Marathon"},
    {"name": "umzug", "text": "Kisten packen"},
    {"name": "tagebuch", "text": "heute"},
    {"name": "umzug", "content": "# neu"},
    {"url": "https://example.org/a.pdf", "name": "Mietvertrag"},
    {"url": "  https://example.org  "},
    {"query": "Wetter Berlin"},
    {"query": "   "},
    {"name": "Schlaf", "typ": "number", "einheit": "h"},
]


def _konflikt_attrappe(layer, day, label, time=None):
    """Die Frage zu add_calendar_entry fragt den echten Kalender nach
    Konflikten. Für einen festen Schnappschuss eine feste Antwort."""
    if label == "Zahnarzt":
        return [f"⚠ Kollision: {label} am {day} ({layer}, {time})."]
    return []


def aktuell():
    """Was das Modell und Sasha heute sehen — über die öffentlichen Namen,
    die vor UND nach dem Umbau dieselben sind."""
    import cloud
    import erlaubnis
    import kalender
    import profil
    from profil import gross, klein

    alt = kalender.conflicts_for_proposed
    kalender.conflicts_for_proposed = _konflikt_attrappe
    try:
        listen = {}
        for name, schiene in (("klein", klein), ("gross", gross)):
            listen[name + "_openai"] = json.dumps(schiene.TOOLS, ensure_ascii=False)
            listen[name + "_anthropic"] = json.dumps(
                cloud._to_anthropic_tools(schiene.TOOLS), ensure_ascii=False)

        namen = []
        for schiene in (klein, gross):
            for t in schiene.TOOLS:
                n = t["function"]["name"]
                for k in (n, profil.kanonisch(n)):
                    if k not in namen:
                        namen.append(k)
        namen.append("gibt_es_nicht")

        gate = {}
        for n in namen:
            zeilen = [[None, erlaubnis.braucht_erlaubnis(n), None]]
            for a in ARGUMENTE:
                zeilen.append([a, erlaubnis.braucht_erlaubnis(n, a),
                               erlaubnis.frage(n, dict(a))])
            gate[n] = zeilen
        return {"listen": listen, "gate": gate}
    finally:
        kalender.conflicts_for_proposed = alt


def _gespeichert():
    with open(SCHNAPPSCHUSS, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("liste", ["klein_openai", "klein_anthropic",
                                   "gross_openai", "gross_anthropic"])
def test_werkzeug_liste_ist_byte_gleich(liste):
    """Reihenfolge, Texte, Schemas — Zeichen für Zeichen wie vor dem Umbau."""
    assert aktuell()["listen"][liste] == _gespeichert()["listen"][liste]


def test_gate_und_frage_wie_vorher():
    jetzt, vorher = aktuell()["gate"], _gespeichert()["gate"]
    assert sorted(jetzt) == sorted(vorher)
    for name in vorher:
        assert jetzt[name] == vorher[name], name


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
