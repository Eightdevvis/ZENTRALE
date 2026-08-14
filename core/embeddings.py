# core/embeddings.py
#
# Embedding-Schicht für das KI-Memory-System (siehe memory/ki_memory_plan.md).
#
# Embeddings sind numerische Vektoren, die die *Bedeutung* eines Textes
# in einem hochdimensionalen Raum kodieren - zwei semantisch verwandte
# Texte landen nah beieinander, auch wenn sie keine Worte teilen
# ("Geschwindigkeit war schlecht" liegt nahe an "Latenz war hoch").
#
# Wir nutzen das lokale Ollama-Modell `bge-m3` (1024 Dimensionen, ~570 MB
# Disk, mehrsprachig) - siehe EMBED_MODEL unten. Damit bleibt das gesamte
# Memory-System offline - kein Cloud-Embedding-Provider. `nomic-embed-text`
# (768 Dim, nur Englisch) war die frühere Wahl und ist über
# OLLAMA_EMBED_MODEL weiter nutzbar, inkl. seiner Prefix-Eigenheit unten.
#
# Verantwortlichkeiten dieses Moduls:
#   - embed(text)                 → Vektor erzeugen
#   - cosine_similarity(a, b)     → Vektorähnlichkeit messen (für Phase C)
#   - top_k(query_vec, entries, k) → Convenience für Retrieval (Phase C)
#
# Fehlerverhalten: Wenn Ollama gerade nicht erreichbar ist (Service down,
# Modell nicht installiert), liefert embed() None statt zu crashen. Das
# bricht zwar die semantische Suche für betroffene Einträge, aber lässt
# das restliche System weiterlaufen - Memory ohne Embedding ist immer
# noch persistent gespeicherter Text.

import os
from collections import OrderedDict
from threading import Lock

import net  # HTTP-Wrapper mit Terminal-Logging (NET → / NET ← Zeilen)

# ── Konfiguration ──────────────────────────────────────────────────────
# Endpoint + Modell sind über Env-Vars überschreibbar, damit der gleiche
# Code auch mit anderen Embedding-Providern arbeiten könnte (z.B. ein
# zweiter Pi als Embedding-Server). Default ist lokales Ollama.
OLLAMA_URL    = os.environ.get("OLLAMA_URL",          "http://localhost:11434")
EMBED_MODEL   = os.environ.get("OLLAMA_EMBED_MODEL",  "bge-m3")

# Embed-Modell warmhalten - bge-m3 ist zwar nur ~570 MB, aber wenn es
# zwischendurch unloadet, kostet der erste Call beim nächsten Chat-Turn
# einen unnötigen Reload. Gleicher Mechanismus wie beim Chat-Modell.
EMBED_KEEP_ALIVE = os.environ.get("OLLAMA_EMBED_KEEP_ALIVE", "30m")

# ── Query-Embedding-Cache ─────────────────────────────────────────────
# Vor jedem Chat-Turn wird die User-Frage in einen Vektor übersetzt -
# das ist ein synchroner Ollama-Round-Trip *bevor* das Hauptmodell auch
# nur anfängt zu generieren. Bei Folge-Fragen mit identischem Wortlaut
# (z.B. wenn der User "was meinst du?" mehrfach hintereinander schickt
# nachdem die KI nichts gerafft hat, oder bei Test-Sessions) sparen
# wir den kompletten Round-Trip aus dem Cache.
#
# Cache-Politik:
#   - LRU mit 64 Einträgen. Klein, weil der Hit-Effekt mit Variations-
#     reichtum sowieso sinkt.
#   - Nur Query-Seite cachen, nicht Document-Seite: Dokumente werden
#     einmal beim Speichern embedded und dann persistiert, ein Cache
#     hätte da keinen Hit-Wert. Queries sind das wo wir wiederholten
#     Traffic sehen.
#   - Key ist (model, prefix+text), damit ein Modell-/Prefix-Wechsel
#     den Cache nicht silently falsch beantwortet.
_QUERY_CACHE_MAX = 64
_query_cache: OrderedDict[tuple, list[float]] = OrderedDict()
_query_cache_lock = Lock()

# Vektor-Dimensionen je nach Modell:
#   bge-m3          → 1024 (multilingual, default seit Phase C-Quality-Fix)
#   nomic-embed-text→ 768  (primär Englisch, frühere Default-Wahl)
# Wir hardcoden die Dimension nicht - der Code passt sich an alles an,
# was Ollama zurückgibt.

# ── Task-Prefixes (modell-spezifisch) ─────────────────────────────────
# Manche Embedding-Modelle wurden mit asymmetrischen Task-Prefixes
# trainiert: Dokumente und Suchanfragen leben dann in unterschiedlichen
# Regionen des Vektorraums, was Retrieval-Qualität deutlich verbessert.
#
#   nomic-embed-text: braucht "search_document:" / "search_query:" -
#                     ohne Prefix matcht es zu sehr auf Lexikalisches
#                     (Eigennamen wie "Sasha") statt aufs Thema.
#
#   bge-m3 (BAAI):    funktioniert ohne Prefix - die Trainings-
#                     Objective ist symmetrisch genug, dass der gleiche
#                     Encoder beide Seiten gut darstellt.
#
# Wenn jemand ein anderes Modell setzt: hier ergänzen, sonst kriegt es
# leere Prefixe (was für die meisten modernen Modelle OK ist).
_PREFIXES_BY_MODEL = {
    'nomic-embed-text': ('search_document: ', 'search_query: '),
    'bge-m3':           ('', ''),
}
_PREFIX_DOC, _PREFIX_QUERY = _PREFIXES_BY_MODEL.get(EMBED_MODEL, ('', ''))


def _embed_raw(text: str) -> list[float] | None:
    """
    Erzeugt ein Embedding für den exakten Text via Ollama (kein Prefix).

    Returns:
        list[float]: der Embedding-Vektor (1024 dim bei bge-m3).
        None: wenn Ollama nicht erreichbar war oder das Modell fehlt.

    Der Ollama-Endpoint /api/embed nimmt ein 'input'-Feld (String oder
    Liste) und liefert 'embeddings' als Liste von Vektor-Listen zurück.
    Bei Einzeleingabe nehmen wir [0].

    Nicht direkt aufrufen - die Caller sollten embed_document() oder
    embed_query() benutzen, damit die Prefixe konsistent gesetzt sind.
    """
    if not text or not text.strip():
        return None

    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/embed",
            {
                "model":      EMBED_MODEL,
                "input":      text,
                "keep_alive": EMBED_KEEP_ALIVE,
                # num_gpu=0 zwingt bge-m3 auf die CPU. Grund: das Embed-
                # Modell (~560M) + das 14B-Chat-Modell passen NICHT beide in
                # die 12 GB der 4070 (qwen @ num_ctx=8192 fuellt die Karte
                # allein bis zum Rand). Lag bge-m3 auf der GPU, warf Ollama
                # bei jedem Embed-Call qwen raus und lud es danach 9 GB neu
                # von der Platte -> 30-50 s bis zum ersten Wort. Auf der CPU
                # frisst bge-m3 0 VRAM, qwen bleibt dauerhaft geladen. Der
                # eine Embed-Durchlauf pro Frage kostet auf der CPU nur
                # Bruchteile einer Sekunde (laeuft eh VOR der Generierung,
                # klaut qwen also keine Zyklen).
                "options":    {"num_gpu": 0},
            },
            timeout=30,
        )
        # Response: { "model": ..., "embeddings": [[0.12, -0.45, ...]], ... }
        out = resp.get("embeddings")
        if not out or not isinstance(out, list) or not out[0]:
            return None
        return out[0]
    except Exception:
        # net.post hat den Fehler bereits über state.push_log geloggt.
        # Hier nur None zurückgeben, damit Caller weiterlaufen kann.
        return None


def embed_document(text: str) -> list[float] | None:
    """
    Embedding für etwas, das ins LTM eingelagert wird (Dokument-Seite
    der asymmetrischen Suche).

    Wird in memory.save() und backfill_missing_embeddings() genutzt.
    """
    if not text or not text.strip():
        return None
    return _embed_raw(_PREFIX_DOC + text)


def embed_query(text: str) -> list[float] | None:
    """
    Embedding für eine Suchanfrage (Query-Seite der asymmetrischen Suche).

    Wird in memory._select_relevant_entries(), graph._find_entry_points()
    und überall sonst genutzt, wo die KI semantisch sucht.

    LRU-gecacht: identische Folge-Queries (gleicher Wortlaut, gleicher
    Whitespace nach strip()) sparen einen kompletten Ollama-Round-Trip.
    """
    if not text or not text.strip():
        return None
    full_input = _PREFIX_QUERY + text.strip()
    cache_key  = (EMBED_MODEL, full_input)

    # Cache-Lookup
    with _query_cache_lock:
        cached = _query_cache.get(cache_key)
        if cached is not None:
            # LRU-Touch: ans Ende der OrderedDict verschieben
            _query_cache.move_to_end(cache_key)
            return cached

    # Cache-Miss → frisches Embedding holen
    vec = _embed_raw(full_input)
    if vec is None:
        return None

    # Speichern + Eviction wenn voll
    with _query_cache_lock:
        _query_cache[cache_key] = vec
        _query_cache.move_to_end(cache_key)
        while len(_query_cache) > _QUERY_CACHE_MAX:
            _query_cache.popitem(last=False)  # oldest raus
    return vec


# Backward-compatibility: alter Name embed() bleibt verfügbar, aber wir
# behandeln es als Document-Embedding (das war der häufigere Use Case
# vor der Prefix-Trennung). Phase B-Saves davor brauchen ggf. ein
# Re-Backfill, damit Doc und Query in derselben Raum-Hälfte sitzen.
def embed(text: str) -> list[float] | None:
    """Alias für embed_document. Existiert nur für Backward-Compatibility."""
    return embed_document(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Berechnet die Cosinus-Ähnlichkeit zwischen zwei Vektoren.

    Bereich: -1.0 (gegensätzlich) ... 0.0 (orthogonal) ... 1.0 (identisch).
    In der Praxis bei Embeddings: meistens zwischen 0.3 und 0.95.

    Wir schreiben das händisch statt numpy zu pullen - die Memory-Suche
    operiert auf max. ein paar hundert Einträgen, da macht eine Python-
    Schleife keinen spürbaren Unterschied, und wir sparen uns die
    Numpy-Abhängigkeit.
    """
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot    += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    # math.sqrt würde reichen, aber ** 0.5 spart einen Import.
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def top_k(query_vec: list[float],
          entries: list[dict],
          k: int = 5,
          embedding_key: str = "embedding") -> list[tuple[dict, float]]:
    """
    Findet die k Einträge, deren Embedding dem query_vec am ähnlichsten ist.

    Wird in Phase C vom Retrieval-Code aufgerufen.

    Args:
        query_vec:     der Vektor, gegen den verglichen wird (z.B. die
                       embeddete User-Frage).
        entries:       Liste von dicts mit Embedding-Feld (LTM-Einträge).
        k:             wie viele Treffer maximal.
        embedding_key: welches Feld im Eintrag den Vektor enthält.
                       Default 'embedding' (passt zum LTM-Schema).

    Returns:
        Liste von (entry, similarity_score) absteigend nach Score.
        Einträge ohne Embedding (None) werden ausgefiltert.
        Wenn weniger als k Einträge mit Embedding existieren, sind's
        entsprechend weniger Treffer.
    """
    if not query_vec or k <= 0 or not entries:
        return []

    scored = []
    for e in entries:
        vec = e.get(embedding_key)
        if not vec:
            continue
        score = cosine_similarity(query_vec, vec)
        scored.append((e, score))

    # Absteigend sortieren - höchste Ähnlichkeit zuerst
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]
