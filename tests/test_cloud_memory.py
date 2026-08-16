"""
Memory unterwegs: Cloud-Embedder + Cloud-Konsolidierung.

Ollama läuft nur daheim. Damit die Cloud-KI unterwegs nicht gedächtnislos ist,
kann der CLOUD-Graph über einen Cloud-Embedder laufen und sich per
Cloud-Extraktor verdichten.

Zwei Invarianten, die hier scharf geprüft werden, weil ihr Bruch STILL wäre:

  1. Vektorräume nie mischen. bge-m3 und text-embedding-v3 haben beide 1024
     Dimensionen. Verglichen kracht nichts - die Suche liefert Rauschen.
  2. Der lokale Graph verlässt das Haus nicht. Weder als Embedding-Auftrag
     noch als Extraktions-Auftrag.
"""
import pytest

import embeddings
import graph


@pytest.fixture
def kein_echter_embedder(monkeypatch):
    """Beide Embedder durch Marker ersetzen, damit sichtbar wird, WELCHER
    gelaufen ist - und keiner echtes Netz anfasst."""
    gerufen = []

    def lokal(text):
        gerufen.append(("local", text))
        return [1.0, 0.0]

    def wolke(text):
        gerufen.append(("cloud", text))
        return [0.0, 1.0]

    monkeypatch.setattr(embeddings, "_embed_raw", lokal)
    monkeypatch.setattr(embeddings, "_cloud_embed", wolke)
    return gerufen


@pytest.fixture(autouse=True)
def leerer_query_cache():
    embeddings._query_cache.clear()
    yield
    embeddings._query_cache.clear()


# ── Der Embedder folgt dem Graphen ─────────────────────────────────────

def test_neuer_store_bekommt_den_angemeldeten_embedder(tmp_path):
    p = str(tmp_path / "wolke.json")
    graph.register_store(p, "cloud")
    d = graph.dump(p)
    assert d["embedder"] == "cloud"
    assert d["embed_model"] == embeddings.CLOUD_EMBED_MODEL


def test_ohne_anmeldung_bleibt_es_lokal(tmp_path):
    d = graph.dump(str(tmp_path / "unbekannt.json"))
    assert d["embedder"] == "local"


def test_die_datei_gewinnt_gegen_die_konfiguration(tmp_path):
    """DIE zentrale Sicherung: was einmal mit bge-m3 gebaut wurde, bleibt
    bge-m3 - auch wenn die Konfiguration inzwischen 'cloud' sagt. Sonst
    würden alte und neue Vektoren verglichen, ohne dass irgendwo ein Fehler
    auftaucht."""
    import json
    p = tmp_path / "alt.json"
    p.write_text(json.dumps({"schema_version": 1, "nodes": {}, "edges": [],
                             "embedder": "local", "embed_model": "bge-m3"}),
                 encoding="utf-8")
    graph.register_store(str(p), "cloud")     # Konfiguration sagt jetzt cloud
    d = graph.dump(str(p))
    assert d["embedder"] == "local"           # …die Datei sagt weiterhin lokal
    assert d["embed_model"] == "bge-m3"


def test_embedder_landet_wirklich_in_der_datei(tmp_path, kein_echter_embedder):
    import json
    p = str(tmp_path / "neu.json")
    graph.register_store(p, "cloud")
    graph.add_turn_extraction([{"name": "Kaffee", "type": "concept"}], [], store=p)
    roh = json.loads(open(p, encoding="utf-8").read())
    assert roh["embedder"] == "cloud"
    assert roh["embed_model"] == embeddings.CLOUD_EMBED_MODEL


def test_cloud_store_embedded_ueber_die_cloud(tmp_path, kein_echter_embedder):
    p = str(tmp_path / "wolke.json")
    graph.register_store(p, "cloud")
    graph.add_turn_extraction([{"name": "Kaffee", "type": "concept"}], [], store=p)
    assert any(b == "cloud" for b, _ in kein_echter_embedder)
    assert not any(b == "local" for b, _ in kein_echter_embedder)


def test_lokaler_store_embedded_nie_ueber_die_cloud(tmp_path, kein_echter_embedder):
    """Isolations-Invariante: Sashas Konzeptnamen gehen nicht raus."""
    p = str(tmp_path / "lokal.json")
    graph.add_turn_extraction([{"name": "Kaffee", "type": "concept"}], [], store=p)
    assert any(b == "local" for b, _ in kein_echter_embedder)
    assert not any(b == "cloud" for b, _ in kein_echter_embedder)


def test_suche_nutzt_den_embedder_des_graphen(tmp_path, kein_echter_embedder):
    p = str(tmp_path / "wolke.json")
    graph.register_store(p, "cloud")
    graph.add_turn_extraction([{"name": "Kaffee", "type": "concept"}], [], store=p)
    kein_echter_embedder.clear()
    graph.context_for_query("kaffee?", store=p)
    assert all(b == "cloud" for b, _ in kein_echter_embedder)


# ── Zeichenbudget für den Graph-Kontext ────────────────────────────────
#
# Der Block geht bei JEDEM Turn ungecacht raus — er ändert sich ja mit der
# Frage. max_nodes deckelt die Anzahl; über die LÄNGE sagt eine Knotenzahl
# nichts, und Knotennamen können beliebig lang sein.

def _voller_graph(p, extra=()):
    """Graph-Datei direkt schreiben.

    Nicht über add_turn_extraction: der Stub-Embedder gibt für JEDEN Text
    denselben Vektor zurück, damit greift die Alias-Auflösung und alle Knoten
    verschmelzen zu einem. (Genau der Fehlmerge-Mechanismus, den Stufe 3
    abschaltet — hier stört er nur den Aufbau.)
    """
    import json
    # "Sasha" ist der Anker, von dem der Aktivierungs-Spread ausgeht — ohne
    # ihn findet context_for_query() keinen Einstieg und liefert leer.
    nodes = {"Sasha": {"type": "concept"}}
    nodes.update({f"Konzept-Nummer-{i}-mit-einem-recht-langen-Namen":
                  {"type": "concept"} for i in range(40)})
    for name, typ in extra:
        nodes[name] = {"type": typ}
    edges = [{"from": "Sasha", "to": n, "rel": "hat"}
             for n in nodes if n != "Sasha"]
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"schema_version": graph.SCHEMA_VERSION,
                   "nodes": nodes, "edges": edges}, f)
    graph._invalidate(p) if hasattr(graph, "_invalidate") else None


def test_kontext_haelt_das_zeichenbudget(tmp_path, kein_echter_embedder):
    p = str(tmp_path / "voll.json")
    _voller_graph(p)
    ohne = graph.context_for_query(None, store=p, max_nodes=40)
    mit  = graph.context_for_query(None, store=p, max_nodes=40, max_chars=600)
    assert len(ohne) > 600
    assert len(mit) <= 600


def test_ohne_budget_bleibt_alles_wie_bisher(tmp_path, kein_echter_embedder):
    """max_chars=0 ist der Default — der lokale Pfad darf sich nicht ändern."""
    p = str(tmp_path / "voll.json")
    _voller_graph(p)
    assert (graph.context_for_query(None, store=p, max_nodes=40) ==
            graph.context_for_query(None, store=p, max_nodes=40, max_chars=0))


def test_die_leitplanken_ueberleben_das_kuerzen(tmp_path, kein_echter_embedder):
    """Was die KI über SICH weiß (kann / kann nicht) bleibt stehen. Das sind
    die Leitplanken gegen erfundene Fähigkeiten, und sie kosten fast nichts —
    sie wegzukürzen hieße, an der falschen Stelle zu sparen."""
    p = str(tmp_path / "mitgrenzen.json")
    _voller_graph(p, extra=[("Bilder generieren", "limit"),
                            ("Kalender lesen", "capability")])
    kurz = graph.context_for_query(None, store=p, max_nodes=45, max_chars=700)
    assert len(kurz) <= 700
    assert "Bilder generieren" in kurz
    assert "Kalender lesen" in kurz


# ── Der Query-Cache darf die Räume nicht vermischen ────────────────────

def test_query_cache_trennt_die_backends(kein_echter_embedder):
    """Ohne getrennte Schlüssel käme bei gleichem Wortlaut der bge-m3-Vektor
    aus dem Cache zurück, wenn eigentlich ein Cloud-Vektor gebraucht wird -
    der stille Vektorraum-Mix, den niemand bemerkt."""
    lok = embeddings.embed_query("kaffee", backend="local")
    wol = embeddings.embed_query("kaffee", backend="cloud")
    assert lok == [1.0, 0.0]
    assert wol == [0.0, 1.0]
    # beide wirklich gelaufen, keiner aus dem falschen Cache bedient
    assert [b for b, _ in kein_echter_embedder] == ["local", "cloud"]


def test_query_cache_greift_innerhalb_eines_backends(kein_echter_embedder):
    embeddings.embed_query("kaffee", backend="cloud")
    embeddings.embed_query("kaffee", backend="cloud")
    assert len(kein_echter_embedder) == 1


# ── Nachziehen fehlender Vektoren ──────────────────────────────────────

def test_fehlende_embeddings_werden_nachgezogen(tmp_path, kein_echter_embedder):
    """Knoten, die ohne erreichbaren Embedder entstanden sind, haben keinen
    Vektor und wären für die Suche unsichtbar - dauerhaft, weil ensure_seed
    idempotent ist. Genau das ist dem Cloud-Graphen unterwegs passiert."""
    import json
    p = tmp_path / "loecher.json"
    p.write_text(json.dumps({"schema_version": 1, "edges": [], "nodes": {
        "Kaffee": {"type": "concept", "embedding": None},
        "Tee":    {"type": "concept", "embedding": [0.5, 0.5]},
        "2026-08-15": {"type": "time-day", "embedding": None},
    }}), encoding="utf-8")
    n = graph.reembed_missing(str(p))
    assert n == 1                                  # nur Kaffee
    d = graph.dump(str(p))
    assert d["nodes"]["Kaffee"]["embedding"] == [1.0, 0.0]
    assert d["nodes"]["Tee"]["embedding"] == [0.5, 0.5]      # unangetastet
    assert d["nodes"]["2026-08-15"]["embedding"] is None     # Zeit bleibt leer


def test_nachziehen_ist_idempotent(tmp_path, kein_echter_embedder):
    import json
    p = tmp_path / "voll.json"
    p.write_text(json.dumps({"schema_version": 1, "edges": [],
                             "nodes": {"Tee": {"type": "concept",
                                               "embedding": [0.5, 0.5]}}}),
                 encoding="utf-8")
    assert graph.reembed_missing(str(p)) == 0
    assert kein_echter_embedder == []


def test_ohne_erreichbaren_embedder_wird_nichts_geschrieben(tmp_path, monkeypatch):
    """Sonst würde eine halb gefüllte Datei geschrieben, und beim nächsten
    Versuch wäre nicht mehr erkennbar, was fehlt."""
    import json
    monkeypatch.setattr(embeddings, "_embed_raw", lambda t: None)
    p = tmp_path / "tot.json"
    inhalt = {"schema_version": 1, "edges": [],
              "nodes": {"Kaffee": {"type": "concept", "embedding": None}}}
    p.write_text(json.dumps(inhalt), encoding="utf-8")
    vorher = p.stat().st_mtime_ns
    assert graph.reembed_missing(str(p)) == 0
    assert p.stat().st_mtime_ns == vorher


# ── Konsolidierung unterwegs ───────────────────────────────────────────

@pytest.fixture
def extraktoren(monkeypatch):
    import consolidation
    gerufen = []
    monkeypatch.setattr(consolidation, "_call_graph_extractor",
                        lambda u, a, t: gerufen.append("local") or ([], []))
    monkeypatch.setattr(consolidation, "_call_graph_extractor_cloud",
                        lambda u, a, t: gerufen.append("cloud") or ([], []))
    monkeypatch.setattr(consolidation, "_is_substantive", lambda m: True)
    return gerufen


def test_cloud_graph_faellt_ohne_ollama_auf_die_cloud_zurueck(extraktoren,
                                                              monkeypatch):
    import consolidation
    monkeypatch.setattr(consolidation, "_local_da", lambda: False)
    consolidation.extract_turn_into_graph("ich mag kaffee", "ok",
                                          store="/tmp/ai_graph_cloud.json")
    assert extraktoren == ["local", "cloud"]


def test_lokaler_graph_faellt_niemals_auf_die_cloud_zurueck(extraktoren,
                                                            monkeypatch):
    """Ohne Ollama wird der private Graph eben nicht verdichtet. Ihn zum
    Extrahieren rauszuschicken wäre derselbe Bruch wie ihn mitzusenden."""
    import consolidation
    monkeypatch.setattr(consolidation, "_local_da", lambda: False)
    consolidation.extract_turn_into_graph("ich mag kaffee", "ok", store=None)
    assert extraktoren == ["local"]


def test_mit_ollama_bleibt_es_lokal(extraktoren, monkeypatch):
    """Daheim ist der lokale Extraktor gratis und für Fleißarbeit gut genug."""
    import consolidation
    monkeypatch.setattr(consolidation, "_local_da", lambda: True)
    consolidation.extract_turn_into_graph("ich mag kaffee", "ok",
                                          store="/tmp/ai_graph_cloud.json")
    assert extraktoren == ["local"]


# ── Verdrahtung ────────────────────────────────────────────────────────

def test_cloud_meldet_seinen_store_an(monkeypatch):
    import cloud
    monkeypatch.setattr(cloud, "_store_bereit", False)
    monkeypatch.setattr(embeddings, "cloud_available", lambda: True)
    monkeypatch.setattr(graph, "reembed_missing", lambda *a, **k: 0)
    cloud.prepare_store()
    import os
    assert graph._store_embedder[os.path.abspath(cloud.CLOUD_GRAPH)] == "cloud"


def test_ohne_cloud_embedder_bleibt_der_cloud_graph_lokal(monkeypatch):
    """Anthropic hat gar keine Embeddings-API - dann muss der Cloud-Graph auf
    Ollama zurückfallen (und ist unterwegs eben gedächtnislos)."""
    import cloud
    import os
    monkeypatch.setattr(cloud, "_store_bereit", False)
    monkeypatch.setattr(embeddings, "cloud_available", lambda: False)
    monkeypatch.setattr(graph, "reembed_missing", lambda *a, **k: 0)
    cloud.prepare_store()
    assert graph._store_embedder[os.path.abspath(cloud.CLOUD_GRAPH)] == "local"


def test_anthropic_taugt_nicht_als_embedder(monkeypatch):
    """cloud_available() darf für einen Anbieter ohne Embeddings-API nicht
    True sagen - sonst liefe der Cloud-Graph in einen Embedder, den es nicht
    gibt, und stünde ohne Vektoren da."""
    import providers
    monkeypatch.setattr(embeddings, "CLOUD_EMBED_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert providers.get("claude")["kind"] == "anthropic"
    assert embeddings.cloud_available() is False
