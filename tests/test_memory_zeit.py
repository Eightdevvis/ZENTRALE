"""
Zeit und Relevanz im Graph-Gedächtnis.

Der Anlass ist ein realer Schaden vom 17.08.2026. Sasha fragte „kann ich
heute wieder Sport machen?" — und bekam eine Antwort, in der drei Fehler
zusammenliefen, die einander gegenseitig fütterten:

  1. **Der Erzähltag wurde zum Ereignistag.** Aus der FRAGE nach Sport
     wurde `{Sport ─[geschah-am]─► 2026-08-17}`. Genauso war „ich hatte
     vor ein paar Tagen Schüttelfrost" auf den Tag des Erzählens datiert
     worden statt auf den des Geschehens.
  2. **Der Kalender-Spiegel machte daraus eine Tatsache.** Jede
     geschah-am-Kante landete im `erlebt`-Layer. Der nächste Turn las per
     read_calendar „Sport" und behandelte den eigenen Irrtum als Beleg.
     Eine Frage war binnen einer Minute zur Kalender-Wahrheit geworden.
  3. **Der Kontext wurde nicht von der Frage gesteuert.** Einstiegspunkte
     waren Embedding-Treffer plus Sasha plus heutiges Datum — und ohne
     Ollama gibt es keine Embeddings. Blieben die zwei größten Naben: auf
     die Frage nach Sport kamen Geige, Spanien und brain organoids
     zurück, „Sport" selbst schwamm nur über zwei Ecken mit.

Dazu die stille Nachwirkung: aus zwei datierten Nennungen liest ein
Modell einen ZEITRAUM („du hattest bis gestern Fieber"), obwohl der Graph
nur einzelne Tage kennt. Ein Zustand hängt an genau seinem Datum und sagt
nichts über andere Tage.

Seit 2026-10-31 ist der Graph aus dem Code. Geblieben sind die Lehren, die
nicht am Graphen hingen: kein Kalender-Spiegel, und der Imprint liest den
nahen Horizont, statt ihn zu schreiben.
"""
from datetime import date, timedelta
from pathlib import Path

import pytest

import ai
import ki_prompt
import consolidation
import kalender

# Tests, die den Kalender-Speicher wirklich anfassen, laufen gegen BEIDE
# Speicher (Marke kalender_beide, tests/conftest.py Punkt 8); die übrigen
# einmal — dort wäre der zweite Lauf derselbe (memory/betrieb/tests.md).


@pytest.fixture
def tmp_kalender(tmp_path, monkeypatch):
    """Frischer Kalender mit den Default-Layern, in einer Wegwerf-Datei."""
    monkeypatch.setattr(kalender, "CAL_PATH", Path(tmp_path) / "cal.json")
    return kalender.CAL_PATH


# ── Der Kalender-Spiegel bleibt aus ────────────────────────────────────

def test_konsolidierung_schreibt_nicht_in_den_kalender(monkeypatch):
    """Nach dem Turn wird ins Transkript geschrieben — und nirgendwo sonst.

    Der Kalender-Spiegel war ein Schreibweg am Erlaubnis-Gate vorbei: jeder
    Kalender-Schreib-TOOL-Call muss bestätigt werden, dieser Nebeneffekt
    im Hintergrund-Thread nie. Er ist gelöscht; dieser Test hält die Tür
    zu, falls jemand ihn "der Bequemlichkeit halber" wieder aufmacht.
    """
    geschrieben = []
    monkeypatch.setattr(kalender, "_save_raw",
                        lambda *a, **k: geschrieben.append(a))
    monkeypatch.setattr(consolidation.transkript, "schreiben", lambda *a, **k: [])
    consolidation.record_turns(
        "kann ich heute wieder sport machen", "kalendarisch nichts im Weg")
    assert geschrieben == []


def test_auto_capture_gibt_es_nicht_mehr():
    """Ersatzlos gestrichen, nicht nur abgeschaltet."""
    assert not hasattr(kalender, "auto_capture")


# ── Imprint: lesen statt schreiben ─────────────────────────────────────

@pytest.mark.kalender_beide
def test_imprint_zeigt_heute_und_morgen(tmp_kalender):
    """Was der Spiegel durch Schreiben erreichen wollte, holt der Imprint
    durch Lesen: der nahe Horizont steht im Prompt, ohne Tool-Runde."""
    heute = date.today()
    kalender.add_entry("termine", heute.isoformat(), "Zahnarzt", time="09:00")
    kalender.add_entry("termine", (heute + timedelta(days=1)).isoformat(),
                       "Abreise")
    text = kalender.imprint_for_prompt()
    assert "Zahnarzt" in text
    assert "Abreise" in text


@pytest.mark.kalender_beide
def test_imprint_endet_nicht_am_uebermorgen(tmp_kalender):
    """Der Block ist der NAHE Horizont. Was weiter weg liegt, gehört ins
    Tool — sonst antwortet das Modell faul aus dem geklebten Block."""
    heute = date.today()
    kalender.add_entry("termine", (heute + timedelta(days=5)).isoformat(),
                       "Geigenstunde")
    text = kalender.imprint_for_prompt()
    assert "Geigenstunde" not in text
    assert "read_calendar" in text


@pytest.mark.kalender_beide
def test_imprint_zeigt_nur_was_sasha_auch_sieht(tmp_kalender):
    """Die Asymmetrie, die den ganzen Schaden ermöglicht hat: der
    erlebt-Layer ist fuer Sasha ausgeblendet, der Tool-Pfad las ihn
    trotzdem. Der Imprint haelt sich an SEINE Sichtbarkeit."""
    heute = date.today().isoformat()
    kalender.add_entry("erlebt", heute, "Sport")
    assert "Sport" not in kalender.imprint_for_prompt()


@pytest.mark.kalender_beide
def test_leerer_tag_sagt_das_auch(tmp_kalender):
    """'Nichts geplant' und 'weiß ich nicht' sind verschiedene Antworten."""
    text = kalender.imprint_for_prompt()
    assert "Keine Einträge" in text


def test_imprint_steht_im_gecachten_kopf(monkeypatch):
    """In den gecachten Teil, nicht ins Wechselnde.

    Der Imprint ändert sich mit dem TAG und mit echten Kalender-Änderungen,
    nicht mit dem Turn. Im wechselnden Teil müsste derselbe Text bei jedem
    Turn ungecacht bezahlt werden; im Kopf sind es ein, zwei
    Cache-Schreibvorgänge am Tag.
    """
    import cloud
    monkeypatch.setattr(ki_prompt, "_imprint_prompt", lambda **_: "## Was ansteht\nZahnarzt")
    statisch  = cloud._static_system(None, tutor_mode=False)
    fluechtig = cloud._volatile_text(via_mic=False, tutor_mode=False)
    assert "Zahnarzt" in statisch
    assert "Zahnarzt" not in fluechtig


def test_gecachter_kopf_bleibt_ueber_turns_gleich(monkeypatch):
    """Byte-identisch, solange sich am Kalender nichts ändert — sonst wäre
    der Cache-Treffer weg und der Imprint teurer als die Tool-Runde."""
    import cloud
    monkeypatch.setattr(ki_prompt, "_imprint_prompt", lambda **_: "## Was ansteht\nZahnarzt")
    assert (cloud._static_system(None, tutor_mode=False)
            == cloud._static_system(None, tutor_mode=False))


@pytest.mark.kalender_beide
def test_imprint_blickt_nicht_zurueck(tmp_kalender):
    """Vergangenes darf den Cache nicht vollmüllen — der Block fängt heute
    an, nicht gestern."""
    gestern = (date.today() - timedelta(days=1)).isoformat()
    kalender.add_entry("termine", gestern, "Umzug")
    assert "Umzug" not in kalender.imprint_for_prompt()


def test_kalender_faellt_aus_chat_laeuft_weiter(monkeypatch):
    """Ein kaputter Kalender darf den Chat nicht mitreißen."""
    def kaputt():
        raise RuntimeError("kalender weg")
    monkeypatch.setattr(kalender, "imprint_for_prompt", kaputt)
    assert ai._imprint_prompt() == ""
