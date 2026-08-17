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
"""
import json

import pytest

import consolidation
import graph


@pytest.fixture
def ohne_embeddings(monkeypatch):
    """Kein Ollama, keine Vektoren — der Normalfall unterwegs.

    Genau dieser Zustand hat den Schaden ausgelöst: ohne Embeddings fand
    die Einstiegspunkt-Suche gar nichts, und der Spread startete nur an
    den Naben.
    """
    monkeypatch.setattr(graph.embeddings, "_embed_raw", lambda t: None)
    monkeypatch.setattr(graph.embeddings, "_cloud_embed", lambda t: None)
    graph.embeddings._query_cache.clear()


@pytest.fixture
def welt(tmp_path, ohne_embeddings):
    """Ein Graph im Kleinen wie Sashas echter: eine Nabe, viel Beifang.

    Sasha hängt an allem, das heutige Datum an jeder Nennung. Nur „Sport"
    hat mit der Testfrage zu tun.
    """
    p = str(tmp_path / "g.json")
    heute = graph._today_str()
    graph.add_turn_extraction(
        [{"name": n, "type": t} for n, t in [
            ("Sasha", "person"), ("Sport", "concept"), ("Geige", "object"),
            ("Spanien", "place"), ("brain organoids", "project"),
            ("Fieber", "state"), (heute, "event"), ("2026-08-09", "event"),
        ]],
        [{"from": "Sasha", "to": "Sport",           "rel": "kann"},
         {"from": "Sasha", "to": "Geige",           "rel": "macht"},
         {"from": "Sasha", "to": "Spanien",         "rel": "war-am"},
         {"from": "Sasha", "to": "brain organoids", "rel": "arbeitet-an"},
         {"from": "Sasha", "to": "Fieber",          "rel": "zustand"},
         {"from": "Fieber", "to": "2026-08-09",     "rel": "geschah-am"},
         {"from": "Geige",  "to": heute,            "rel": "erwähnt-am"},
         {"from": "Spanien", "to": heute,           "rel": "erwähnt-am"}],
        store=p)
    return p


FRAGE = "kann ich heute wieder sport machen"


def _aktivierung(pfad, frage):
    """{name: score} so wie der Kontext-Renderer es sieht."""
    st = graph._get_store(pfad)
    _, sortiert, _ = graph._activated_view(frage, st, graph.DEFAULT_HOPS, 25)
    return dict(sortiert)


# ── Die Frage steuert den Kontext ──────────────────────────────────────

def test_gefragtes_thema_wird_einstiegspunkt(welt):
    """„Sport" muss ganz oben stehen, nicht als Beifang mitschwimmen.

    Ohne Embeddings ist der wörtliche Treffer die einzige Chance, das
    Thema überhaupt zu finden.
    """
    a = _aktivierung(welt, FRAGE)
    assert a["Sport"] == 1.0
    assert a["Sport"] > a["Geige"]
    assert a["Sport"] > a["Spanien"]


def test_nabe_uebertoent_das_thema_nicht(welt):
    """Sasha bleibt Anker, wird aber nicht zum Themen-Geber.

    Mit voller Aktivierung landete alles, was einen Hop von Sasha weg
    liegt, gleichauf im Kontext — unabhängig von der Frage.
    """
    a = _aktivierung(welt, FRAGE)
    assert a["Sasha"] == pytest.approx(graph.ANKER_START)
    assert a["Sasha"] < a["Sport"]
    # und was nur über Sasha erreichbar ist, fällt deutlich zurück
    assert a["Spanien"] < a["Sasha"]


def test_ohne_treffer_tragen_die_anker_den_kontext(welt):
    """Findet die Frage nichts, darf der Kontext nicht leer werden.

    Die Dämpfung ist eine Rangfolge-Korrektur, kein Abschalten: ohne
    eigene Einstiegspunkte sind Sasha und Heute alles, was wir haben.
    """
    a = _aktivierung(welt, "erzähl mir irgendwas")
    assert a["Sasha"] == 1.0
    assert a["Spanien"] > 0


def test_praefix_findet_komposita(welt):
    """„krank" muss den Knoten „Krankheit" finden.

    Deutsche Komposita treffen sonst nie: gefragt wird nach dem
    Wortstamm, gespeichert ist das Substantiv.
    """
    st = graph._get_store(welt)
    with st.lock:
        data = graph._load_raw(st)
    data["nodes"]["Krankheit"] = {"type": "state"}
    assert "Krankheit" in graph._lexical_entry_points("bin ich noch krank?", data)


def test_teilwort_reicht_nicht(welt):
    """Ein einzelnes Wort aus einem mehrwortigen Knoten reicht nicht.

    Sonst zöge „work" den ganzen „work badhausen"-Komplex in jede Frage
    über Arbeit.
    """
    st = graph._get_store(welt)
    with st.lock:
        data = graph._load_raw(st)
    data["nodes"]["work badhausen"] = {"type": "event"}
    assert "work badhausen" not in graph._lexical_entry_points("wie war die work", data)
    assert "work badhausen" in graph._lexical_entry_points("wie war work badhausen", data)


# ── Kanten nach Relevanz, nicht nach Entstehungs-Zufall ────────────────

def test_kanten_zum_thema_stehen_vorn(welt):
    """Der 40er-Schnitt und das Zeichenbudget dürfen nicht die alten
    Kanten bevorzugen, nur weil sie zuerst in der Datei stehen."""
    st = graph._get_store(welt)
    _, _, kanten = graph._activated_view(FRAGE, st, graph.DEFAULT_HOPS, 25)
    paare = [(e["from"], e["to"]) for e in kanten]
    assert paare.index(("Sasha", "Sport")) < paare.index(("Sasha", "Spanien"))


def test_erwaehnt_am_steht_hinten(welt):
    """Buchhaltung über das Reden rangiert hinter Inhalt.

    `erwähnt-am` machte die halbe Kantenliste aus und ist zugleich der
    Grund, warum das heutige Datum eine Nabe ist.
    """
    st = graph._get_store(welt)
    _, _, kanten = graph._activated_view(FRAGE, st, graph.DEFAULT_HOPS, 25)
    rels = [e["rel"] for e in kanten]
    assert rels.index("kann") < rels.index("erwähnt-am")


# ── Ein Datum ist ein Tag, kein Zeitraum ───────────────────────────────

def test_zeit_legende_bei_datums_kanten(welt):
    """Der Block muss sagen, was geschah-am und erwähnt-am bedeuten —
    sonst wird aus zwei Nennungen ein Zeitraum."""
    text = graph.context_for_query(FRAGE, store=welt)
    assert "kein Zeitraum" in text
    assert "GEREDET" in text


def test_keine_legende_ohne_datums_kanten(tmp_path, ohne_embeddings):
    """Kein Erklärtext auf Vorrat: der Block geht bei jedem Turn
    ungecacht mit raus.

    Der Graph wird hier von Hand geschrieben, nicht über
    add_turn_extraction: die hängt an jeden Turn `erwähnt-am`-Anker, also
    hat ein gewachsener Graph praktisch immer Datums-Kanten. Ohne
    Zeitanker (frisch geseedet, importiert) soll die Legende schweigen.
    """
    p = str(tmp_path / "g.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"nodes": {"Sasha": {"type": "person"},
                             "Geige": {"type": "object"}},
                   "edges": [{"from": "Sasha", "to": "Geige", "rel": "macht"}]}, f)
    text = graph.context_for_query("was ist mit der geige", store=p)
    assert "Geige" in text
    assert "kein Zeitraum" not in text


# ── Der Kalender-Spiegel bleibt aus ────────────────────────────────────

@pytest.fixture
def extraktor(monkeypatch, tmp_path):
    """Extraktor, der genau den Fehler von damals produziert: aus einer
    Frage nach Sport wird ein Ereignis am heutigen Tag."""
    heute = graph._today_str()
    monkeypatch.setattr(consolidation, "_call_graph_extractor",
                        lambda *a, **k: (
                            [{"name": "Sport", "type": "concept"}],
                            [{"from": "Sport", "to": heute, "rel": "geschah-am"}]))
    monkeypatch.setattr(consolidation.transkript, "schreiben", lambda *a, **k: [])
    return str(tmp_path / "g.json")


def test_spiegel_ist_per_default_aus(extraktor, monkeypatch):
    """Kein geschah-am darf ungefragt zur Kalender-Tatsache werden.

    Der Graph ist korrigierbar, ein Kalender-Eintrag ist die Quelle, der
    die KI am meisten glaubt — und liest ihn im nächsten Turn als Beleg
    zurück.
    """
    gespiegelt = []
    monkeypatch.setattr(consolidation.kalender, "auto_capture",
                        lambda c, d: gespiegelt.append((c, d)))
    consolidation.extract_turn_into_graph(
        "kann ich heute wieder sport machen", "kalendarisch nichts im Weg",
        store=extraktor)
    assert gespiegelt == []


def test_spiegel_laesst_sich_einschalten(extraktor, monkeypatch):
    """Der Pfad bleibt am Leben — nur eben bewusst zu schalten."""
    gespiegelt = []
    monkeypatch.setattr(consolidation.kalender, "auto_capture",
                        lambda c, d: gespiegelt.append((c, d)))
    consolidation.extract_turn_into_graph(
        "kann ich heute wieder sport machen", "kalendarisch nichts im Weg",
        store=extraktor, mirror_calendar=True)
    assert gespiegelt == [("Sport", graph._today_str())]


# ── Die Zeit-Regel im Extraktor-Prompt ─────────────────────────────────

def test_extraktor_prompt_verbietet_datum_auf_verdacht():
    """Regel 5 kannte nur das Beispiel „ich war heute müde" und stempelte
    darum auf alles das heutige Datum. Die Unterscheidung Erzähltag ↔
    Ereignistag muss drinstehen bleiben."""
    p = consolidation._GRAPH_EXTRACTOR_PROMPT
    assert "vor ein paar Tagen" in p          # ungefähre Vergangenheit
    assert "NICHT-EREIGNISSE" in p            # Fragen und Vorhaben
    assert "nicht der des Geschehens" in p    # der Kern der Verwechslung
