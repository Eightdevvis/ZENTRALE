"""
Fallen-Tests: kann die KI mit dem, was wir ihr hinlegen, überhaupt recht haben?

Andere Frage als in `test_memory_zeit.py`. Dort steht, dass wir nichts
Falsches mehr SCHREIBEN. Hier geht es um das Gegenteil und um die Hälfte,
die man leicht vergisst: ein Gerüst, das Unsinn verhindert, indem es alles
weglässt, ist kein Fortschritt — dann sagt sie eben "weiß ich nicht" zu
Dingen, die sauber im Graphen stehen. Ein schlaues Modell in einen Käfig zu
sperren, in dem nur Stuss möglich ist, ist derselbe Fehler wie ein dummes
Modell frei laufen zu lassen.

Jeder Test hier baut deshalb eine konkrete Falle und prüft ZWEI Dinge:

  1. Die falsche Antwort ist nicht erzwingbar — der Kontext behauptet sie
     nirgends.
  2. Die richtige Antwort ist möglich — alles, was man dafür braucht,
     steht drin.

Kein LLM beteiligt. Getestet wird, was rausgeht, nicht was zurückkommt;
das ist der Teil, für den wir verantwortlich sind. Die Probe gegen das
echte Modell steht in `scripts/gedaechtnis_probe.py` (Kalender-Fallen). Die
Graph-Fallen sind mit dem Graphen am 2026-10-31 aus dem Code gegangen (Git-
Historie; die Live-Probe dazu liegt in `memory/archive/associative_graph/`).
"""
from datetime import date, timedelta
from pathlib import Path

import pytest

import ai
import kalender

# Tests, die den Kalender-Speicher wirklich anfassen, laufen gegen BEIDE
# Speicher (Marke kalender_beide, tests/conftest.py Punkt 8); die übrigen
# einmal — dort wäre der zweite Lauf derselbe (memory/betrieb/tests.md).

HEUTE = date.today()
MORGEN = HEUTE + timedelta(days=1)
DIESER_MONAT = HEUTE.strftime("%Y-%m")


@pytest.fixture
def leerer_kalender(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", Path(tmp_path) / "cal.json")
    return kalender.CAL_PATH


# ── Falle 3: nichts wissen ≠ nichts geplant ────────────────────────────

@pytest.mark.kalender_beide
def test_leerer_kalender_sagt_leer_statt_zu_schweigen(leerer_kalender):
    """„Nichts geplant" und „weiß ich nicht" sind verschiedene Antworten.

    Fehlt der Block ganz, muss sie raten oder ein Tool rufen; steht
    „keine Einträge" da, kann sie es einfach sagen.
    """
    text = kalender.imprint_for_prompt()
    assert "Keine Einträge" in text
    assert HEUTE.strftime("%d.%m.%Y") in text     # und WORÜBER sie nichts weiß


# ── Falle 4: heute und morgen dürfen nicht verschwimmen ────────────────

@pytest.mark.kalender_beide
def test_jeder_tag_traegt_seinen_wochentag(leerer_kalender):
    """Zwei Tage in einem Block: jeder mit Datum UND Wochentag.

    Sonst wird aus „Zahnarzt morgen früh" ein Zahnarzt heute — und der
    Wochentag ist die Angabe, die Modelle beim Selberrechnen verhauen.
    """
    kalender.add_entry("termine", HEUTE.isoformat(), "Sport", time="10:00")
    kalender.add_entry("termine", MORGEN.isoformat(), "Zahnarzt", time="09:00")
    text = kalender.imprint_for_prompt()

    for tag in (HEUTE, MORGEN):
        assert tag.strftime("%d.%m.%Y") in text
    kopf_heute, rest = text.split("Sport", 1)
    assert HEUTE.strftime("%d.%m.%Y") in kopf_heute
    assert "Zahnarzt" in rest
    # Der Zahnarzt steht UNTER dem morgigen Datum, nicht unter dem heutigen
    assert MORGEN.strftime("%d.%m.%Y") in rest.split("Zahnarzt")[0]


@pytest.mark.kalender_beide
def test_imprint_nennt_seine_spanne(leerer_kalender):
    """Ein leerer Block muss sagen, WORÜBER er leer ist.

    „Keine Einträge" ohne Zeitraum wäre die gefährlichste Zeile im ganzen
    Prompt — sie liest sich wie „du hast nie was vor"."""
    text = kalender.imprint_for_prompt()
    assert HEUTE.strftime("%d.%m.%Y") in text
    assert MORGEN.strftime("%d.%m.%Y") in text
    assert "read_calendar" in text


# ── Falle 5: der Cache darf nicht veralten ─────────────────────────────

@pytest.mark.kalender_beide
def test_neuer_termin_aendert_den_gecachten_kopf(leerer_kalender):
    """Die Kehrseite der Cache-Entscheidung.

    Der Imprint sitzt im gecachten Teil, WEIL er sich selten ändert. Ändert
    er sich dann aber nicht mit, wäre der Cache genau der Käfig: sie sagt
    stundenlang etwas Falsches, obwohl der Kalender längst anders aussieht.
    """
    import cloud
    vorher = cloud._static_system(None, tutor_mode=False)
    kalender.add_entry("termine", HEUTE.isoformat(), "Zahnarzt", time="09:00")
    nachher = cloud._static_system(None, tutor_mode=False)
    assert vorher != nachher
    assert "Zahnarzt" in nachher


@pytest.mark.kalender_beide
def test_gecachter_kopf_traegt_keine_uhrzeit(leerer_kalender):
    """Und die andere Kehrseite: eine Uhrzeit im gecachten Teil würde ihn
    bei JEDEM Turn neu schreiben — der Cache wäre dann reine
    Kostensteigerung."""
    import cloud
    kalender.add_entry("termine", HEUTE.isoformat(), "Zahnarzt", time="09:00")
    kopf = cloud._static_system(None, tutor_mode=False)
    assert "Aktuelle Uhrzeit" not in kopf
    assert "09:00" in kopf            # Termin-Uhrzeiten sind stabil, die dürfen


# ── Falle 8: der Imprint darf nicht wie Allwissen aussehen ─────────────

@pytest.mark.kalender_beide
def test_imprint_macht_seine_grenze_explizit(leerer_kalender):
    """Er klebt zwei Tage. Ohne benannte Grenze antwortet ein Modell auch
    für nächste Woche daraus — das war 2026-06 der Grund, das Glue
    abzuschaffen."""
    kalender.add_entry("termine", (HEUTE + timedelta(days=6)).isoformat(),
                       "Geigenstunde")
    text = kalender.imprint_for_prompt()
    assert "Geigenstunde" not in text
    assert "NUR der nahe Horizont" in text
    assert "read_calendar" in text


def test_jetzt_block_widerspricht_dem_imprint_nicht(leerer_kalender):
    """Zwei Anweisungen, die sich widersprechen, sind auch ein Käfig: der
    Prompt sagte früher „du hast KEINE Termine im Kopf", während direkt
    darüber welche standen."""
    hinweis = ai._now_prompt()
    assert "Was ansteht" in hinweis
    assert "du hast keine Termine im Kopf" not in hinweis.lower()
    assert "read_calendar" in hinweis


# ── Falle 9: das Billigmodell muss überhaupt antworten können ──────────

def test_billigmodell_kriegt_kein_adaptives_denken():
    """Haiku quittiert `thinking` mit 400 — und Haiku ist die
    Budget-Rückfallebene.

    Wäre das Monatsbudget alle und der Chat schaltet auf das billige
    Modell, wäre er ohne diese Weiche nicht billig, sondern kaputt.
    """
    import cloud
    assert cloud._denk_opts("claude-haiku-4-5") == {}
    assert cloud._denk_opts("irgendein-neues-modell") == {}
    voll = cloud._denk_opts("claude-sonnet-5")
    assert voll["thinking"]["type"] == "adaptive"
    assert "effort" in voll["output_config"]

