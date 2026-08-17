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
echte Modell steht in `scripts/gedaechtnis_probe.py`.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import ai
import graph
import kalender

HEUTE = date.today()
MORGEN = HEUTE + timedelta(days=1)
DIESER_MONAT = HEUTE.strftime("%Y-%m")


@pytest.fixture
def ohne_embeddings(monkeypatch):
    """Kein Embedder erreichbar — der Normalfall unterwegs."""
    monkeypatch.setattr(graph.embeddings, "_embed_raw", lambda t: None)
    monkeypatch.setattr(graph.embeddings, "_cloud_embed", lambda t: None)
    graph.embeddings._query_cache.clear()


@pytest.fixture
def leerer_kalender(tmp_path, monkeypatch):
    monkeypatch.setattr(kalender, "CAL_PATH", Path(tmp_path) / "cal.json")
    return kalender.CAL_PATH


def _graph_bauen(tmp_path, knoten, kanten, name="g.json"):
    """Graph-Datei direkt schreiben — kein Auto-Zeitanker, keine Extraktion.

    Bewusst von Hand: `add_turn_extraction` hängt an jeden Turn
    `erwähnt-am`-Kanten aufs heutige Datum. Für eine saubere Falle wollen
    wir genau die Kanten im Graphen haben, die wir hinschreiben.
    """
    p = str(tmp_path / name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"nodes": knoten, "edges": kanten}, f)
    return p


def _tag_daten(text):
    """Alle YYYY-MM-DD im Text."""
    return set(re.findall(r"\d{4}-\d{2}-\d{2}", text))


# ── Falle 1: gröber datiert ist nicht undatiert ────────────────────────

def test_monatsdatierung_erlaubt_die_richtige_antwort(tmp_path, ohne_embeddings):
    """„Wann hatte ich Fieber?" → „im August" muss sagbar sein.

    Die Zeit-Regel verhindert erfundene Tage. Sie darf die Auskunft aber
    nicht mit-verhindern: steht der Monat im Graphen, muss er auch im
    Kontext ankommen — sonst hätten wir Falschheit gegen Nutzlosigkeit
    getauscht.
    """
    p = _graph_bauen(tmp_path,
        {"Sasha": {"type": "person"}, "Fieber": {"type": "state"},
         DIESER_MONAT: {"type": "time-month"}},
        [{"from": "Sasha", "to": "Fieber", "rel": "zustand"},
         {"from": "Fieber", "to": DIESER_MONAT, "rel": "geschah-am"}])

    text = graph.context_for_query("wann hatte ich fieber", store=p)
    assert "Fieber" in text
    assert DIESER_MONAT in text                     # die Antwort ist möglich
    assert not _tag_daten(text)                     # kein erfundener Tag
    assert "kein Zeitraum" in text                  # und keine Spanne draus


def test_erwaehnt_am_ist_kein_erlebnis(tmp_path, ohne_embeddings):
    """Über etwas geredet zu haben, darf nicht wie „passiert" aussehen.

    Genau daraus wurde „du hattest bis gestern Fieber": Schüttelfrost war
    nur am Erzähltag verankert, und das las sich wie ein Erlebnis an
    diesem Tag.
    """
    heute = HEUTE.isoformat()
    p = _graph_bauen(tmp_path,
        {"Sasha": {"type": "person"}, "Schüttelfrost": {"type": "state"},
         heute: {"type": "time-day"}},
        [{"from": "Sasha", "to": "Schüttelfrost", "rel": "zustand"},
         {"from": "Schüttelfrost", "to": heute, "rel": "erwähnt-am"}])

    text = graph.context_for_query("wie gehts mir mit dem schüttelfrost", store=p)
    # Nur die KANTEN prüfen: in der Legende steht "geschah-am" natürlich auch.
    kanten = [z for z in text.splitlines() if "─[" in z]
    assert any("erwähnt-am" in z for z in kanten)
    assert not any("geschah-am" in z for z in kanten)
    assert "GEREDET" in text          # die Legende sagt, was das heißt


# ── Falle 2: der gefragte Fakt muss das Budget überleben ───────────────

def test_gefragter_fakt_ueberlebt_die_kuerzung(tmp_path, ohne_embeddings):
    """Unter Zeichenbudget darf nicht der Kern rausfliegen und das
    Beiwerk bleiben.

    Vorher entschied die Datei-Reihenfolge, was den Schnitt überlebt —
    also der Zufall der Entstehung. Der älteste Kram hätte die Antwort
    verdrängt.
    """
    knoten = {"Sasha": {"type": "person"}, "Fieber": {"type": "state"},
              DIESER_MONAT: {"type": "time-month"}}
    kanten = [{"from": "Sasha", "to": "Fieber", "rel": "zustand"},
              {"from": "Fieber", "to": DIESER_MONAT, "rel": "geschah-am"}]
    # 20 alte, unbeteiligte Fakten VOR den relevanten in der Datei
    for i in range(20):
        knoten[f"Altkram {i}"] = {"type": "concept"}
        kanten.insert(0, {"from": "Sasha", "to": f"Altkram {i}", "rel": "macht"})
    p = _graph_bauen(tmp_path, knoten, kanten)

    text = graph.context_for_query("wann hatte ich fieber", store=p, max_chars=700)
    assert len(text) <= 700
    assert "Fieber" in text
    assert DIESER_MONAT in text


# ── Falle 3: nichts wissen ≠ nichts geplant ────────────────────────────

def test_leerer_kalender_sagt_leer_statt_zu_schweigen(leerer_kalender):
    """„Nichts geplant" und „weiß ich nicht" sind verschiedene Antworten.

    Fehlt der Block ganz, muss sie raten oder ein Tool rufen; steht
    „keine Einträge" da, kann sie es einfach sagen.
    """
    text = kalender.imprint_for_prompt()
    assert "Keine Einträge" in text
    assert HEUTE.strftime("%d.%m.%Y") in text     # und WORÜBER sie nichts weiß


def test_leerer_graph_erfindet_nichts(tmp_path, ohne_embeddings):
    """Ohne Wissen kein Kontext-Block — nicht ein Block mit Platzhaltern."""
    p = _graph_bauen(tmp_path, {"Sasha": {"type": "person"}}, [])
    assert graph.context_for_query("was weißt du über meinen hund", store=p) \
        .count("Hund") == 0


# ── Falle 4: heute und morgen dürfen nicht verschwimmen ────────────────

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


def test_imprint_nennt_seine_spanne(leerer_kalender):
    """Ein leerer Block muss sagen, WORÜBER er leer ist.

    „Keine Einträge" ohne Zeitraum wäre die gefährlichste Zeile im ganzen
    Prompt — sie liest sich wie „du hast nie was vor"."""
    text = kalender.imprint_for_prompt()
    assert HEUTE.strftime("%d.%m.%Y") in text
    assert MORGEN.strftime("%d.%m.%Y") in text
    assert "read_calendar" in text


# ── Falle 5: der Cache darf nicht veralten ─────────────────────────────

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


def test_gecachter_kopf_traegt_keine_uhrzeit(leerer_kalender):
    """Und die andere Kehrseite: eine Uhrzeit im gecachten Teil würde ihn
    bei JEDEM Turn neu schreiben — der Cache wäre dann reine
    Kostensteigerung."""
    import cloud
    kalender.add_entry("termine", HEUTE.isoformat(), "Zahnarzt", time="09:00")
    kopf = cloud._static_system(None, tutor_mode=False)
    assert "Aktuelle Uhrzeit" not in kopf
    assert "09:00" in kopf            # Termin-Uhrzeiten sind stabil, die dürfen


# ── Falle 6: Widerspruch muss sichtbar bleiben ─────────────────────────

def test_widerspruch_zwischen_graph_und_kalender_bleibt_erkennbar(
        tmp_path, leerer_kalender, ohne_embeddings, monkeypatch):
    """Wenn eine Altlast im Graphen etwas behauptet, das der Kalender nicht
    hergibt, muss BEIDES im Prompt stehen.

    Ein Gerüst, das eine der beiden Quellen unterschlägt, zwingt sie zur
    falschen Antwort — egal wie schlau sie ist. Nebeneinander kann sie den
    Widerspruch sehen und nachfragen.
    """
    import cloud
    heute = HEUTE.isoformat()
    p = _graph_bauen(tmp_path,
        {"Sasha": {"type": "person"}, "Sport": {"type": "concept"},
         heute: {"type": "time-day"}},
        [{"from": "Sport", "to": heute, "rel": "geschah-am"}])

    kopf = cloud._static_system(None, tutor_mode=False)      # Imprint: leer
    ctx  = graph.context_for_query("war ich heute sport machen", store=p)

    assert "Keine Einträge" in kopf          # Kalender sagt: nichts
    assert "Sport" in ctx and heute in ctx   # Graph sagt: doch
    assert "kein Zeitraum" in ctx            # und die Legende ordnet es ein


# ── Falle 7: fremde Gefühle bleiben fremd ──────────────────────────────

def test_sashas_zustand_steht_unter_sashas_ueberschrift(tmp_path, ohne_embeddings):
    """Der Unterschied zwischen „du fühlst dich einsam" und „ich bin
    einsam seit dem 19. Mai"."""
    p = _graph_bauen(tmp_path,
        {"Sasha": {"type": "person"}, "einsam": {"type": "state"},
         "Bilder generieren": {"type": "limit"}},
        [{"from": "Sasha", "to": "einsam", "rel": "fühlt"}])

    text = graph.context_for_query("wie gehts mir", store=p)
    welt, rest = text.split("### Über SASHA", 1)
    assert "einsam" in rest.split("### Das kannst DU")[0]
    assert "NICHT dir" in text


def test_limit_landet_nicht_bei_den_faehigkeiten(tmp_path, ohne_embeddings):
    """Ein „kann-nicht"-Knoten in der Fähigkeiten-Liste wäre eine
    eingebaute Lüge."""
    p = _graph_bauen(tmp_path,
        {"KI": {"type": "self"}, "Bilder generieren": {"type": "limit"},
         "Kalender lesen": {"type": "capability"}}, [])

    text = graph.context_for_query("kannst du bilder malen", store=p)
    if "Bilder generieren" in text:
        kann = text.split("### Das kannst DU wirklich")[1] \
                   .split("### Das kannst DU NICHT")[0]
        assert "Bilder generieren" not in kann


# ── Falle 8: der Imprint darf nicht wie Allwissen aussehen ─────────────

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


def test_grober_zeitpunkt_wird_nicht_zur_gegenwart(tmp_path, ohne_embeddings):
    """Ein Monats-Datum heißt „irgendwann im August", nicht „jetzt".

    Auf dem Billigmodell kam „du hast momentan Fieber", obwohl im Graphen
    nur `Fieber ─[geschah-am]─► 2026-08` stand. Die Legende sagte damals
    nur etwas über TAGE — für die gröberen Stufen las sie sich wie eine
    Erlaubnis, den Zustand in die Gegenwart zu verlängern.
    """
    p = _graph_bauen(tmp_path,
        {"Sasha": {"type": "person"}, "Fieber": {"type": "state"},
         DIESER_MONAT: {"type": "time-month"}},
        [{"from": "Sasha", "to": "Fieber", "rel": "zustand"},
         {"from": "Fieber", "to": DIESER_MONAT, "rel": "geschah-am"}])

    text = graph.context_for_query("kann ich heute sport machen", store=p)
    assert "und sonst nicht" in text
    assert "schon gar nicht bis heute" in text
    assert "Tag unbekannt" in text
