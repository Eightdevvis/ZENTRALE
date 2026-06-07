# core/graph.py
#
# Konzept-Graph Memory (Phase G des Memory-Plans).
#
# WAS: Knoten = Konzepte als Labels (Entitäten, Zustände, Orte, Konzepte,
# Zeit-Punkte). Edges = typisierte/gewichtete Relationen. Speichert
# Sashas konkrete Realität - NICHT generisches Weltwissen (das macht
# das LLM beim Output-Synthesizing).
#
# WARUM: Memory ist assoziativ, nicht kategorial. Flache Listen + Top-K-
# Embedding-Retrieval versagen bei breiten Fragen ("was weißt du über
# mich"), bei zeitbasierten Fragen, und bei der Verbindung zwischen
# Konzepten die linguistisch unähnlich aber konzeptuell verwandt sind
# (Konto → broke). Aktivierungs-Spread durch typed edges modelliert das.
#
# DREI ROLLEN VON EMBEDDINGS hier:
#   1. Alias-Resolution beim Schreiben ("der Pi" == "mein Raspberry"
#      == Pi-Knoten via Cosinus-Schwelle)
#   2. Fuzzy Entry-Point beim Lesen (Query → nächste Knoten finden)
#   3. KEIN Top-K-Retrieval mehr - das macht Aktivierungs-Spread
#
# ZEIT als Knoten: Tage/Monate/Jahre sind eigene Knoten in einer
# Hierarchie. Jedes erwähnte Konzept kriegt automatisch eine
# `erwähnt-am`-Kante zum heutigen Datum-Knoten. "heute"/"gestern"
# werden NIE als Knoten gespeichert - immer zu absoluten ISO-Dates
# aufgelöst, sonst verschiebt sich "heute" jeden Tag.
#
# Detail-Plan: memory/ki_memory_plan.md (Phase-G-Abschnitt kommt nach).

import json
import os
from datetime import datetime, date
from threading import Lock

import embeddings


_DATA_DIR    = os.path.join(os.path.dirname(__file__), '..', 'data')
_GRAPH_FILE  = os.path.join(_DATA_DIR, 'ai_graph.json')

SCHEMA_VERSION = 1

# Cosinus-Schwelle für Alias-Resolution. Bei Werten >= das wird ein
# neu erwähnter Knotenname als bestehender Knoten erkannt und mit
# dem alten gemerged. Zu niedrig → unterschiedliche Konzepte werden
# fusioniert. Zu hoch → Aliasse bleiben getrennt. 0.85 ist
# konservativ - kann später nachjustiert werden wenn wir Praxis-
# Beobachtungen haben.
# Cosinus-Schwelle für Alias-Resolution. Beim reinen Cosinus zwischen
# 0.7-0.85 sind echte Synonyme ("Pi" / "raspberry pi": 0.67) genau in
# der Grauzone wo auch False-Positives lauern ("Pi" / "Pizza": 0.61).
# Wir kompensieren mit Token-Overlap-Bonus: wenn der neue Name einen
# Token mit einem bestehenden Knoten teilt, gibt's +0.15 auf den
# Cosinus. Damit kommen Sub-Phrasen (raspberry pi enthält pi) sicher
# über die Schwelle, ohne Pizza versehentlich mit Pi zu mergen.
ALIAS_THRESHOLD = 0.78
ALIAS_TOKEN_BONUS = 0.15

# Activation-Spread-Parameter
DEFAULT_HOPS  = 2     # wie weit propagieren
DEFAULT_DECAY = 0.5   # pro Hop mit diesem Faktor multiplizieren
NOISE_FLOOR   = 0.05  # Aktivierung unter diesem Wert nicht weiterspreaden

_lock = Lock()


# ── Helpers ────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat()


def _today_str() -> str:
    return date.today().isoformat()


def _is_date(s: str) -> bool:
    """Looks like ISO date YYYY-MM-DD?"""
    try:
        date.fromisoformat(s)
        return True
    except Exception:
        return False


def _log(line: str):
    """Lazy state-import damit Tests ohne live state importieren können."""
    try:
        import state
        state.push_log(line)
    except Exception:
        pass


def _normalize_name(name: str) -> str:
    """
    Knotennamen normalisieren: Whitespace trimmen, deutsche Artikel
    am Anfang entfernen. Lässt Groß/Klein-Schreibung intact (Sasha
    bleibt Sasha, der pi wird Pi).

    Beispiele:
      "der Pi"          → "Pi"
      "  mein Hut "     → "Hut"
      "Sasha"           → "Sasha"
      "eine Wasserkanne" → "Wasserkanne"
    """
    s = (name or '').strip()
    lower = s.lower()
    articles = (
        'der ', 'die ', 'das ', 'den ', 'dem ', 'des ',
        'ein ', 'eine ', 'einen ', 'einer ', 'eines ',
        'mein ', 'meine ', 'meinen ', 'meiner ', 'meines ',
        'dein ', 'deine ', 'deinen ', 'deiner ', 'deines ',
        'sein ', 'seine ', 'seinen ', 'seiner ', 'seines ',
        'ihr ', 'ihre ', 'ihren ', 'ihrer ', 'ihres ',
    )
    for prefix in articles:
        if lower.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.strip()


def _light_stem(s: str) -> str:
    """
    Sehr leichtes deutsches Stemming für Alias-Matching: lowercased,
    typische Plural/Flexions-Endungen abgestrippt. Kein voller Porter-
    Stemmer - nur die häufigsten Fälle damit "Hund" und "Hunde" auf
    den gleichen Stem fallen.

    Beispiele:
      "Hunde"    → "hund"
      "Hund"     → "hund"
      "Wohnungen" → "wohnung"
      "Mails"    → "mail"
    """
    s = (s or '').strip().lower()
    if len(s) <= 3:
        return s  # zu kurz für Stemming-Heuristiken
    for suffix in ('innen', 'enen', 'eren', 'erin', 'ungen', 'chen',
                   'lein', 'ern', 'en', 'er', 'es', 'em', 'e', 's', 'n'):
        if s.endswith(suffix) and len(s) - len(suffix) >= 3:
            return s[:-len(suffix)]
    return s


def _tokens(s: str) -> set[str]:
    """Wort-Tokens aus einem Namen, lowercased, für Substring-Match."""
    return {w for w in (s or '').lower().replace('-', ' ').split() if len(w) >= 2}


# ── Persistence ───────────────────────────────────────────────────────
#
# Wir cachen den geparsten Graph in-memory mit mtime-Invalidierung:
#   - Pro Chat-Turn wurde die ~700 KB große JSON sonst frisch von Disk
#     gelesen und geparst, obwohl sich oft nichts ändert. Das tropft
#     sich auf der wahrgenommenen Latenz bemerkbar.
#   - Cache-Key ist (mtime, size) der Datei. Bei Write via _write_atomic
#     ändert os.replace die mtime → Cache invalidiert automatisch beim
#     nächsten Read.
#   - Read-Pfad gibt eine TIEFE KOPIE zurück. Wir vertrauen den Callern
#     im Read-Pfad zwar dass sie nicht mutieren (sie tun's heute nicht),
#     aber Defensiv-Kopie verhindert Bugs wenn das mal aus Versehen
#     passiert - und der Speed-Gewinn liegt im gesparten JSON-Parse,
#     nicht in der Kopie selbst.

_cache_lock = Lock()
_cache_key  = None   # (mtime_ns, size) der zuletzt geladenen Datei
_cache_data = None   # das geparste dict


def _file_key() -> tuple | None:
    """Schnüre einen Cache-Key aus dem Dateizustand. None wenn Datei fehlt."""
    try:
        st = os.stat(_GRAPH_FILE)
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return None


def _empty_graph() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "nodes":          {},
        "edges":          [],
    }


def _load_raw(for_write: bool = False) -> dict:
    """
    Lädt den Graphen. Im Read-Pfad (for_write=False) kommt's aus dem
    in-memory Cache wenn die Datei seit dem letzten Load unverändert ist;
    sonst frisch von Disk.

    Im Write-Pfad (for_write=True) immer von Disk lesen - der Caller wird
    das dict mutieren und _write_atomic rufen. Wir geben hier nicht das
    Cache-dict zurück, damit der Cache durch Caller-Mutation nicht
    schleichend mit halbfertigem Stand befallen wird.

    Caller muss den _lock halten (Write-Pfade tun das schon). Cache-Lock
    schützt zusätzlich die _cache_*-Globals gegen Race zwischen
    Async-Save-Thread und Request-Thread.
    """
    global _cache_key, _cache_data

    key = _file_key()
    if key is None:
        # Datei existiert nicht → frisches leeres Schema, nichts cachen
        return _empty_graph()

    if for_write:
        # Direkt von Disk, keine Cache-Bedienung
        with open(_GRAPH_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("nodes", {})
        data.setdefault("edges", [])
        return data

    # Read-Pfad mit Cache
    with _cache_lock:
        if _cache_key == key and _cache_data is not None:
            # Defensiv-Kopie der Top-Level-Container; die Werte (Knoten-Dicts,
            # Edge-Dicts) bleiben geteilt - der Read-Pfad mutiert sie eh nicht
            # und das spart ggü. deepcopy einiges. Falls ein Read-Pfad doch
            # mal anfängt zu mutieren: zu copy.deepcopy wechseln.
            return {
                "schema_version": _cache_data["schema_version"],
                "nodes":          dict(_cache_data["nodes"]),
                "edges":          list(_cache_data["edges"]),
            }

        with open(_GRAPH_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("nodes", {})
        data.setdefault("edges", [])

        _cache_key  = key
        _cache_data = data
        # Selbe shallow-Kopier-Strategie wie oben
        return {
            "schema_version": data["schema_version"],
            "nodes":          dict(data["nodes"]),
            "edges":          list(data["edges"]),
        }


def _write_atomic(data: dict):
    """Atomic write: tmp + rename, gegen halbgeschriebene Files."""
    global _cache_key, _cache_data
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _GRAPH_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _GRAPH_FILE)
    # Cache nach Write aktualisieren: wir haben gerade frische Daten in
    # der Hand, also einlagern statt nächsten Read auf Disk zu schicken.
    # Neuer Cache-Key kommt aus der frisch geschriebenen Datei.
    with _cache_lock:
        _cache_data = data
        _cache_key  = _file_key()


# ── Node Operations ───────────────────────────────────────────────────

def _find_alias(name: str, data: dict, threshold: float = ALIAS_THRESHOLD) -> str | None:
    """
    Sucht ob ein bestehender Knoten dem `name` als Alias zugeordnet
    werden kann. Returns kanonischer Knotenname oder None.

    Mehrstufige Strategie, von billig zu teuer:

      1. Exakter Match auf den raw name.
      2. Case-insensitive exakter Match ("Zentrale" == "zentrale").
      3. Stem-Match: leichtes deutsches Stemming für Plural/Flexion
         ("Hund" == "Hunde", "Wohnung" == "Wohnungen").
      4. Embedding-Cosinus mit optionalem Token-Overlap-Bonus.
         Einzelnes Cosinus reicht nicht zuverlässig (zu enges Window
         zwischen False-Positives und echten Synonymen), aber mit
         Token-Overlap-Bonus kommen Sub-Phrasen sicher rüber
         ("raspberry pi" + "Pi" via gemeinsamen "pi"-Token).

    Zeit-Knoten haben kein Embedding und werden nur über exakten
    String-Match gefunden (ISO-Dates haben sowieso keine Aliase).
    """
    if name in data["nodes"]:
        return name

    name_lower = name.lower()

    # 1+2: Exact (mit Case-Insensitiv)
    for existing in data["nodes"]:
        if existing.lower() == name_lower:
            return existing

    # 3: Stem-Match
    name_stem = _light_stem(name)
    if name_stem and len(name_stem) >= 3:
        for existing in data["nodes"]:
            if _light_stem(existing) == name_stem:
                return existing

    # 4: Embedding + Token-Overlap
    new_emb = embeddings.embed_document(name)
    if not new_emb:
        return None
    new_tokens = _tokens(name)

    best_score = 0.0
    best_name  = None
    for existing_name, node in data["nodes"].items():
        ex_emb = node.get("embedding")
        if not ex_emb:
            continue
        sim = embeddings.cosine_similarity(new_emb, ex_emb)
        # Token-Overlap-Bonus nur wenn die geteilten Token nicht zu
        # generisch sind. "der" / "ein" sind durch _normalize_name eh
        # raus; übrig bleiben echte Inhalts-Tokens. Bei Überlapp +0.15.
        ex_tokens = _tokens(existing_name)
        if new_tokens & ex_tokens:
            sim += ALIAS_TOKEN_BONUS
        if sim > best_score:
            best_score = sim
            best_name  = existing_name
    if best_score >= threshold:
        return best_name
    return None


def _add_or_get_node(name: str, node_type: str, data: dict) -> str:
    """
    Fügt einen Knoten hinzu falls noch nicht da (oder findet Alias).
    Returns kanonischer Knotenname. Updated mentions/last_seen bei
    bestehendem Knoten.
    """
    name = _normalize_name(name)
    if not name:
        return ""
    alias = _find_alias(name, data)
    if alias is not None:
        node = data["nodes"][alias]
        node["last_seen"] = _now_iso()
        node["mentions"]  = node.get("mentions", 1) + 1
        return alias

    # Neuer Knoten - Embedding generieren falls kein Zeit-Knoten
    emb = None
    if not _is_date(name) and node_type not in ("time-day", "time-month", "time-year"):
        emb = embeddings.embed_document(name)
    data["nodes"][name] = {
        "type":       node_type or "concept",
        "embedding":  emb,
        "first_seen": _now_iso(),
        "last_seen":  _now_iso(),
        "mentions":   1,
    }
    return name


def _add_edge(from_node: str, to_node: str, rel: str, data: dict, weight_delta: float = 1.0):
    """
    Fügt eine Kante hinzu oder verstärkt eine existierende mit
    gleichem (from, to, rel)-Tripel. Edge-Weight akkumuliert über
    Co-Erwähnungen - häufig zusammen genannt = stark verbunden.
    """
    if not from_node or not to_node or not rel:
        return
    if from_node == to_node:
        return  # Selbst-Schleifen sind nutzlos für Activation-Spread
    for edge in data["edges"]:
        if edge["from"] == from_node and edge["to"] == to_node and edge["rel"] == rel:
            edge["weight"]    = edge.get("weight", 1.0) + weight_delta
            edge["last_seen"] = _now_iso()
            return
    data["edges"].append({
        "from":       from_node,
        "to":         to_node,
        "rel":        rel,
        "weight":     weight_delta,
        "first_seen": _now_iso(),
        "last_seen":  _now_iso(),
    })


# ── Time-Knoten Hierarchie ─────────────────────────────────────────────

def _ensure_time_node(date_str: str, data: dict):
    """
    Stellt sicher dass der Tag-Knoten + Monat + Jahr existieren und
    via `enthält`-Kanten hierarchisch verknüpft sind.

      2026 ─[enthält]─► 2026-05 ─[enthält]─► 2026-05-15
    """
    if not _is_date(date_str):
        return
    if date_str in data["nodes"]:
        # Day existiert schon → Hierarchie auch
        node = data["nodes"][date_str]
        node["last_seen"] = _now_iso()
        return

    year, month, day = date_str.split('-')
    year_str  = year
    month_str = f"{year}-{month}"

    # Year
    if year_str not in data["nodes"]:
        data["nodes"][year_str] = {
            "type": "time-year", "embedding": None,
            "first_seen": _now_iso(), "last_seen": _now_iso(), "mentions": 1,
        }
    # Month
    if month_str not in data["nodes"]:
        data["nodes"][month_str] = {
            "type": "time-month", "embedding": None,
            "first_seen": _now_iso(), "last_seen": _now_iso(), "mentions": 1,
        }
        _add_edge(year_str, month_str, "enthält", data, weight_delta=1.0)
    # Day
    data["nodes"][date_str] = {
        "type": "time-day", "embedding": None,
        "first_seen": _now_iso(), "last_seen": _now_iso(), "mentions": 1,
    }
    _add_edge(month_str, date_str, "enthält", data, weight_delta=1.0)


# ── Public Write API ──────────────────────────────────────────────────

def add_turn_extraction(nodes_in: list[dict], edges_in: list[dict]):
    """
    Hauptweg um den Graphen zu erweitern. Wird vom Extraktor in
    consolidation.py nach jedem Turn (async) aufgerufen.

    Args:
        nodes_in: Liste von {"name": str, "type": str}
        edges_in: Liste von {"from": str, "to": str, "rel": str}

    Macht:
      1. Alle Knoten via Alias-Resolution adden (Mapping orig→canonical).
      2. Heutigen Time-Node garantieren.
      3. Alle Edges adden, dabei from/to durch Alias-Map ersetzen.
      4. Jeden gemenagten Knoten zusätzlich mit dem heutigen Datum
         per `erwähnt-am`-Kante verbinden - das ist die Temporal-
         Anker für Aktivierungs-Spread "was war heute".

    Loggt was extrahiert wurde damit man im Dashboard live mitliest.
    """
    if not nodes_in and not edges_in:
        return

    with _lock:
        data = _load_raw(for_write=True)
        name_map = {}

        # 1. Nodes adden mit Alias-Resolution
        for n in nodes_in:
            orig = (n.get("name") or "").strip()
            if not orig:
                continue
            node_type = (n.get("type") or "concept").strip()
            canonical = _add_or_get_node(orig, node_type, data)
            if canonical:
                name_map[orig] = canonical

        # 2. Heutiger Time-Node
        today = _today_str()
        _ensure_time_node(today, data)

        # 3. Edges
        for e in edges_in:
            from_orig = (e.get("from") or "").strip()
            to_orig   = (e.get("to")   or "").strip()
            rel       = (e.get("rel")  or "").strip()
            if not from_orig or not to_orig or not rel:
                continue

            # Mapping. Wenn nicht im name_map: vielleicht ein Date oder
            # ein impliziter Knoten den der Extraktor nicht in nodes_in
            # aufgeführt hat. Defensiv lazy-anlegen.
            def _resolve(orig: str) -> str:
                if orig in name_map:
                    return name_map[orig]
                if _is_date(orig):
                    _ensure_time_node(orig, data)
                    return orig
                # Fallback: anlegen
                canon = _add_or_get_node(orig, "concept", data)
                if canon:
                    name_map[orig] = canon
                return canon

            from_canon = _resolve(from_orig)
            to_canon   = _resolve(to_orig)
            _add_edge(from_canon, to_canon, rel, data)

        # 4. Erwähnt-am-Kanten zum heutigen Tag für alle Knoten dieses Turns
        for canon in set(name_map.values()):
            if canon and canon != today:
                _add_edge(canon, today, "erwähnt-am", data, weight_delta=0.3)

        _write_atomic(data)

    # Logging außerhalb des Locks
    nlist = list(set(name_map.values()))
    _log(f"GRAPH ⊕ Turn-Extraktion: {len(nlist)} Knoten, {len(edges_in)} Kanten ({', '.join(nlist[:6])}{'...' if len(nlist)>6 else ''})")


# ── Public Read API ───────────────────────────────────────────────────

def _neighbors(node_name: str, data: dict):
    """Generator über (other_node, edge) für alle anliegenden Kanten."""
    for edge in data["edges"]:
        if edge["from"] == node_name:
            yield (edge["to"], edge)
        elif edge["to"] == node_name:
            yield (edge["from"], edge)


def _activate(entry_nodes: list[str], data: dict,
              hops: int = DEFAULT_HOPS, decay: float = DEFAULT_DECAY) -> dict[str, float]:
    """
    Aktivierungs-Spread: ausgehend von entry_nodes, breitet sich
    Aktivierung durch den Graphen aus. Pro Hop wird's um `decay`
    verringert, Edge-Weight moduliert.

    Returns: {node_name: score} mit Werten in (0, 1].
    """
    activation = {n: 1.0 for n in entry_nodes if n in data["nodes"]}
    frontier   = set(activation.keys())

    for _ in range(hops):
        next_frontier = set()
        for node in list(frontier):
            for neighbor, edge in _neighbors(node, data):
                # Edge-Weight normalisieren: 1 mention ≈ 1.0, stärkere
                # Kanten bringen mehr Aktivierung mit. Cap bei 1.5
                # damit eine einzelne überstarke Kante nicht alles
                # dominiert.
                ew = min(1.5, edge.get("weight", 1.0))
                contrib = activation[node] * decay * (ew / 1.5)
                if contrib < NOISE_FLOOR:
                    continue
                if contrib > activation.get(neighbor, 0):
                    activation[neighbor] = contrib
                    next_frontier.add(neighbor)
        frontier = next_frontier

    return activation


def _find_entry_points(query: str, data: dict,
                       top_k: int = 3, threshold: float = 0.45) -> list[str]:
    """
    Findet die top_k Knoten mit höchster Embedding-Ähnlichkeit zum
    Query. Wird genutzt um den Aktivierungs-Spread zu starten.

    threshold: niedriger als bei normalem Retrieval (0.45 statt 0.6),
    weil wir nur Entry-Points brauchen - der Graph-Spread holt dann
    den Rest.
    """
    qvec = embeddings.embed_query(query)
    if not qvec:
        return []
    scored = []
    for name, node in data["nodes"].items():
        emb = node.get("embedding")
        if not emb:
            continue
        sim = embeddings.cosine_similarity(qvec, emb)
        if sim >= threshold:
            scored.append((name, sim))
    scored.sort(key=lambda x: -x[1])
    return [n for n, _ in scored[:top_k]]


def context_for_query(query: str | None,
                      hops: int = DEFAULT_HOPS,
                      max_nodes: int = 25) -> str:
    """
    Hauptweg um Memory-Kontext für einen Chat-Turn zu holen.

    Strategie:
      1. Entry-Points = Query-Embedding-Match (top_k) + "Sasha"-Knoten
         (immer als zentraler Anker) + heutiger Time-Knoten (Recency-
         Bias).
      2. Aktivierungs-Spread von Entry-Points aus, hops mal.
      3. Top-N nach Aktivierungs-Score nehmen.
      4. Relevante Edges zwischen diesen Knoten dazu.
      5. Als strukturierter Text-Block für den System-Prompt formatieren.

    Wenn der Graph leer ist oder kein Entry-Point findbar: leerer String.
    """
    with _lock:
        data = _load_raw()

    if not data["nodes"]:
        _log("GRAPH →  leer, kein Kontext")
        return ""

    # Entry-Points sammeln
    entries: list[str] = []
    if query:
        entries.extend(_find_entry_points(query, data))

    # Sasha + Heute IMMER als Anker (wenn Graph sie kennt)
    if "Sasha" in data["nodes"] and "Sasha" not in entries:
        entries.append("Sasha")
    today = _today_str()
    if today in data["nodes"] and today not in entries:
        entries.append(today)

    if not entries:
        _log(f"GRAPH →  Query '{(query or '')[:40]}': keine Entry-Points")
        return ""

    _log(f"GRAPH →  Entry-Points: {', '.join(entries)}")

    activation = _activate(entries, data, hops=hops)

    # Top-N
    sorted_nodes = sorted(activation.items(), key=lambda x: -x[1])[:max_nodes]
    node_set     = {n for n, _ in sorted_nodes}

    # Relevante Edges - nur zwischen aktivierten Knoten
    relevant_edges = [
        e for e in data["edges"]
        if e["from"] in node_set and e["to"] in node_set
    ]

    _log(f"GRAPH ←  {len(sorted_nodes)} Knoten, {len(relevant_edges)} Kanten aktiv")

    if not sorted_nodes:
        return ""

    # Kontext-Block bauen. WICHTIG gegen Identity-Bleed: Konzepte werden nach
    # SUBJEKT getrennt gerendert - die KI-eigene Identitaet (type self/
    # capability/limit) klar abgegrenzt von Sashas Welt (alles andere). Sonst
    # landet z.B. Sashas Zustand "einsam" in einer flachen Liste, und ein
    # ungeguardtes Modell (qwen3.5 ist weniger zurueckhaltend als qwen2.5)
    # schreibt ihn sich selbst zu -> "ich bin einsam". Der Header sagt jetzt
    # explizit, wem die Gefuehle/Zustaende gehoeren. Die Kanten tragen das
    # Subjekt ohnehin LINKS (Sasha ─[fuehlt]─► einsam).
    # Drei Subjekt-Gruppen statt flacher Liste - gegen ZWEI Fehlerklassen:
    # (a) Identity-Bleed (Sashas Gefuehle als eigene), (b) Limit-als-Faehigkeit
    # (Modell liest den kann-nicht-Knoten "Bilder generieren" als Faehigkeit
    # und behauptet, es koenne Bilder malen). Deshalb klar getrennt:
    # Sashas Welt | was die KI KANN | was die KI NICHT kann. Nutzt nur das
    # type-Feld (capability/limit/self), kein Graph-Inhalt.
    def _typ(n):
        return data["nodes"][n].get("type", "concept")

    def _fmt(name, score):
        if score >= 0.999:                       # Entry-Points sind 1.0
            return f"  - {name} [{_typ(name)}]"
        return f"  - {name} [{_typ(name)}] (a={score:.2f})"

    world_nodes = [(n, s) for n, s in sorted_nodes
                   if _typ(n) not in ("self", "capability", "limit")]
    cap_nodes   = [(n, s) for n, s in sorted_nodes if _typ(n) == "capability"]
    lim_nodes   = [(n, s) for n, s in sorted_nodes if _typ(n) == "limit"]

    lines = ["## Aktiviertes Wissen", ""]
    if world_nodes:
        lines.append("### Über SASHA und seine/ihre Welt "
                     "(Gefühle, Zustände, Erlebnisse, Leben — das gehört SASHA, NICHT dir):")
        for name, score in world_nodes:
            lines.append(_fmt(name, score))
        lines.append("")
    if cap_nodes:
        lines.append("### Das kannst DU wirklich (deine echten Tools/Fähigkeiten):")
        for name, score in cap_nodes:
            lines.append(_fmt(name, score))
        lines.append("")
    if lim_nodes:
        lines.append("### Das kannst DU NICHT — auch wenn es aus dem Pretraining "
                     "vertraut klingt, du hast es NICHT:")
        for name, score in lim_nodes:
            lines.append(_fmt(name, score))
        lines.append("")
    if relevant_edges:
        lines.append("### Verbindungen (das Subjekt steht immer LINKS):")
        for e in relevant_edges[:40]:  # cap
            w = e.get("weight", 1.0)
            w_str = f" w={w:.1f}" if w != 1.0 else ""
            lines.append(f"  {e['from']} ─[{e['rel']}{w_str}]─► {e['to']}")

    return "\n".join(lines)


# ── Identity Seed (KI-Selbstbild als Graph-Knoten statt Prompt-Block) ─
#
# Statt `_CAPABILITIES_PROMPT` als always-injected Text-Block: die
# Fähigkeiten und Grenzen der KI sind Graph-Knoten mit Kanten zur
# zentralen "KI"-Node. Vorteil: nur wenn der Query thematisch passt
# (z.B. "kannst du Mails senden") spreadet die Aktivierung zu den
# relevanten Limit-Knoten - keine konstante Prompt-Last.
#
# Layer-Modell siehe Doku-Hinweis ai.py:_SYSTEM_PROMPT:
#   1. Base-Model qwen2.5 weiß schon "ich bin ein Assistant".
#   2. System-Prompt formt die ZENTRALE-Persona.
#   3. DIESER SEED hier: ZENTRALE-spezifische konkrete Tools + Limits.
#   4. Learned: was im Chat gelernt wird, kommt durch Extraktor dazu.
#
# Wenn die KI im Chat lernt sie kann zusätzliches nicht ("du kannst
# nicht meine Spotify-Playlist ändern"), wird das vom Extraktor als
# weitere `kann-nicht`-Kante hinzugefügt.

_SEED_CAPABILITIES = [
    "save_memory aufrufen",
    "Dateien aus der Projekt-Whitelist lesen",
    "list_files aufrufen",
    "read_file aufrufen",
    "auf Deutsch antworten",
    "auf Englisch antworten",
    "Token-weise streamen",
    "im Chat Werkzeuge nutzen",
    # Internet-Pipe (seit 2026-06-07): die KI darf - jeweils nach Sashas
    # Bestätigung - im Internet suchen und Webseiten laden. Siehe core/web.py
    # und die Tools web_suche/hole_url in ai.py. Wer den laufenden Graphen
    # migriert, nutzt graph.migrate_internet_access().
    "im Internet suchen",
    "Webseiten abrufen",
]

_SEED_LIMITS = [
    "Mails senden",
    "Code ausführen",
    "Dateien schreiben",
    "Dateien löschen",
    "etwas aus dem Gedächtnis löschen",
    "bestehende Memory-Einträge ändern",
    "Hardware-Sensoren aktiv abfragen",
    "Aktoren oder Geräte schalten",
    "Bilder generieren",
    "Audio direkt produzieren ohne TTS-Pipeline",
    "Anrufe machen oder Telefon nutzen",
]
# Entfernt 2026-06-07 (von Limit -> Fähigkeit, Internet-Pipe): "auf das
# Internet zugreifen", "Web-Suche durchführen", "Echtzeit-News oder Wetter
# abrufen". Web-Suche deckt News/Wetter jetzt ab. Für bereits geseedete
# Graphen wird das per migrate_internet_access() nachgezogen.
_OBSOLETE_INTERNET_LIMITS = [
    "auf das Internet zugreifen",
    "Web-Suche durchführen",
    "Echtzeit-News oder Wetter abrufen",
]


def ensure_seed():
    """
    Stellt sicher dass die KI-Identität im Graphen verankert ist.
    Idempotent - läuft nur wenn der "KI"-Knoten noch nicht existiert.

    Wird beim ersten chat_stream-Call lazy aufgerufen (siehe ai.py).
    Kann auch manuell für Debugging gerufen werden.

    Was passiert:
      1. KI-Knoten anlegen (type: "self")
      2. Pro Capability: Knoten + Edge KI ─[kann]─► capability
      3. Pro Limit: Knoten + Edge KI ─[kann-nicht]─► limit
    """
    with _lock:
        data = _load_raw(for_write=True)
        if "KI" in data["nodes"]:
            return  # bereits geseedet

        # KI-Node selbst
        ki_emb = embeddings.embed_document("KI")
        data["nodes"]["KI"] = {
            "type":       "self",
            "embedding":  ki_emb,
            "first_seen": _now_iso(),
            "last_seen":  _now_iso(),
            "mentions":   1,
        }

        for cap in _SEED_CAPABILITIES:
            data["nodes"][cap] = {
                "type":       "capability",
                "embedding":  embeddings.embed_document(cap),
                "first_seen": _now_iso(),
                "last_seen":  _now_iso(),
                "mentions":   1,
            }
            _add_edge("KI", cap, "kann", data, weight_delta=1.0)

        for lim in _SEED_LIMITS:
            data["nodes"][lim] = {
                "type":       "limit",
                "embedding":  embeddings.embed_document(lim),
                "first_seen": _now_iso(),
                "last_seen":  _now_iso(),
                "mentions":   1,
            }
            _add_edge("KI", lim, "kann-nicht", data, weight_delta=1.0)

        _write_atomic(data)

    _log(f"GRAPH ⊕ Seed: KI-Identität mit {len(_SEED_CAPABILITIES)} kann + {len(_SEED_LIMITS)} kann-nicht")


def migrate_internet_access():
    """
    Einmal-Migration für BEREITS geseedete Graphen (2026-06-07, Internet-Pipe).

    ensure_seed() ist idempotent und läuft nur einmal - es zieht spätere
    Änderungen an _SEED_CAPABILITIES/_SEED_LIMITS NICHT nach. Diese Funktion
    holt das gezielt für die Internet-Fähigkeit nach:

      1. Entfernt die obsoleten "kann-nicht"-Knoten + zugehörige Kanten
         (_OBSOLETE_INTERNET_LIMITS) - die KI kann jetzt ins Internet.
      2. Fügt die neuen "kann"-Knoten ("im Internet suchen", "Webseiten
         abrufen") + KI-[kann]-Kanten hinzu, falls noch nicht vorhanden.

    Fasst NUR die KI-Identity-Knoten an - kein Anfassen/Lesen von Sashas
    persönlichen Konzepten. Idempotent: mehrfaches Aufrufen ist harmlos.
    Gibt ein kleines Report-Dict zurück (entfernt/hinzugefügt) für Logging.
    """
    new_caps = ["im Internet suchen", "Webseiten abrufen"]
    removed, added = [], []
    with _lock:
        data = _load_raw(for_write=True)
        obsolete = set(_OBSOLETE_INTERNET_LIMITS)

        # No-op-Guard: nur schreiben, wenn wirklich etwas zu tun ist. Sonst
        # liefe die Funktion bei JEDEM Boot (sie hängt in _ensure_seed_once)
        # und würde unnötig schreiben bzw. Edge-Gewichte hochzählen.
        def _edge_exists(cap):
            return any(e["from"] == "KI" and e["to"] == cap and e["rel"] == "kann"
                       for e in data["edges"])

        has_obsolete = any(l in data["nodes"] for l in _OBSOLETE_INTERNET_LIMITS)
        caps_missing = any(c not in data["nodes"] or not _edge_exists(c)
                           for c in new_caps)
        if not has_obsolete and not caps_missing:
            return {"removed": [], "added": []}   # schon migriert, nichts tun

        # 1. Obsolete Limit-Knoten + alle Kanten zu/von ihnen wegwerfen.
        for label in _OBSOLETE_INTERNET_LIMITS:
            if label in data["nodes"]:
                del data["nodes"][label]
                removed.append(label)
        data["edges"] = [
            e for e in data["edges"]
            if e["from"] not in obsolete and e["to"] not in obsolete
        ]

        # 2. Neue Fähigkeits-Knoten + Kanten (nur falls fehlend, kein
        #    Gewicht-Bump bei schon vorhandenen).
        for cap in new_caps:
            if cap not in data["nodes"]:
                data["nodes"][cap] = {
                    "type":       "capability",
                    "embedding":  embeddings.embed_document(cap),
                    "first_seen": _now_iso(),
                    "last_seen":  _now_iso(),
                    "mentions":   1,
                }
                added.append(cap)
            if "KI" in data["nodes"] and not _edge_exists(cap):
                _add_edge("KI", cap, "kann", data, weight_delta=1.0)

        _write_atomic(data)

    _log(f"GRAPH ⊕ Internet-Migration: -{len(removed)} Limit, +{len(added)} Fähigkeit")
    return {"removed": removed, "added": added}


# ── Debug/Inspection API ──────────────────────────────────────────────

def stats() -> dict:
    """Schnelle Übersicht für Debug/UI."""
    with _lock:
        data = _load_raw()
    return {
        "nodes": len(data["nodes"]),
        "edges": len(data["edges"]),
        "schema_version": data["schema_version"],
    }


def dump() -> dict:
    """Roher Zugriff auf den Graph (Read-Only-Snapshot)."""
    with _lock:
        return _load_raw()
