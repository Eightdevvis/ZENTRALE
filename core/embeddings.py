# core/embeddings.py
#
# Embedding-Schicht für das KI-Memory-System (siehe memory/ki_memory_plan.md).
#
# Embeddings sind numerische Vektoren, die die *Bedeutung* eines Textes
# in einem hochdimensionalen Raum kodieren - zwei semantisch verwandte
# Texte landen nah beieinander, auch wenn sie keine Worte teilen
# ("Geschwindigkeit war schlecht" liegt nahe an "Latenz war hoch").
#
# Wir nutzen das lokale Ollama-Modell `nomic-embed-text` (768 Dimensionen,
# ~274 MB Disk, CPU-schnell). Damit bleibt das gesamte Memory-System
# offline - kein Cloud-Embedding-Provider.
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

import net  # HTTP-Wrapper mit Terminal-Logging (NET → / NET ← Zeilen)

# ── Konfiguration ──────────────────────────────────────────────────────
# Endpoint + Modell sind über Env-Vars überschreibbar, damit der gleiche
# Code auch mit anderen Embedding-Providern arbeiten könnte (z.B. ein
# zweiter Pi als Embedding-Server). Default ist lokales Ollama.
OLLAMA_URL    = os.environ.get("OLLAMA_URL",          "http://localhost:11434")
EMBED_MODEL   = os.environ.get("OLLAMA_EMBED_MODEL",  "nomic-embed-text")

# nomic-embed-text liefert 768-dimensionale Vektoren. Wir hardcoden das
# nicht - falls jemand das Modell wechselt, passt sich alles automatisch
# an. Aber als Referenz: 768 ist der erwartete Default.


def embed(text: str) -> list[float] | None:
    """
    Erzeugt ein Embedding für den gegebenen Text via Ollama.

    Returns:
        list[float]: der Embedding-Vektor (768 Dimensionen bei
                     nomic-embed-text).
        None: wenn Ollama nicht erreichbar war oder das Modell fehlt.
              Caller müssen diesen Fall handhaben (kein Crash).

    Der Ollama-Endpoint /api/embed nimmt ein 'input'-Feld (entweder
    String oder Liste von Strings) und liefert 'embeddings' als Liste
    von Vektor-Listen zurück. Bei Einzeleingabe nehmen wir [0].
    """
    if not text or not text.strip():
        return None

    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/embed",
            {
                "model": EMBED_MODEL,
                "input": text,
            },
            timeout=30,  # Embedding ist deutlich schneller als Chat, 30s ist großzügig
        )
        # Response-Form bei nomic-embed-text:
        #   { "model": ..., "embeddings": [[0.12, -0.45, ...]], "total_duration": ..., ... }
        embeddings = resp.get("embeddings")
        if not embeddings or not isinstance(embeddings, list) or not embeddings[0]:
            return None
        return embeddings[0]
    except Exception:
        # Wir loggen das nicht doppelt - net.post hat den Fehler bereits
        # über state.push_log als "NET ✗ FAIL" sichtbar gemacht. Hier
        # nur None zurückgeben, damit der Caller weiterlaufen kann.
        return None


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
