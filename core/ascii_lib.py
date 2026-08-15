# ASCII-Bibliothek für ZENTRALE.
#
# ── Wozu das gut ist ──────────────────────────────────────────────────
# Die KI soll "visuell mitreden" können, während sie mit Worten
# antwortet — ein passendes ASCII-Bild im Kern des Dashboards als Mimik
# zur Antwort. Sie MALT das Bild aber nicht selbst: ein 9b-Modell ist
# mies im freien ASCII-Malen (2D-Layout über einen 1D-Tokenstrom), aber
# gut im Greppen. Also kuratiert es aus einer handgepflegten Bibliothek
# statt zu malen.
#
# ── Datei-Format (data/ascii/<name>.txt) ──────────────────────────────
#   # tags: katze, tier, müde          ← optionale erste Zeile, Komma-Liste
#   <ab hier die reine ASCII-Art, beliebig viele Zeilen>
# Fehlt die tags-Zeile, wird der Dateiname (ohne .txt) als einziger Tag
# genutzt. Neue Bilder einfach als .txt in den Ordner legen.
#
# ── Matching (Hybrid, siehe memory/ki/ki_system.md) ──────────────────────
#   Stufe 1 — Tag/Keyword: exakter Tag-Treffer > Substring in Tag/Name >
#             Token-Überlappung. Schnell, vorhersehbar, debuggbar.
#   Stufe 2 — Embedding-Fallback: greift NUR wenn Stufe 1 nichts findet.
#             Stichwort (query) gegen Bild-Tags (document) via bge-m3,
#             asymmetrisch. Liegt auch der beste Vektor unter dem
#             Schwellwert -> None. Lieber kein Bild als ein falsches.
#
# bge-m3 ist durch den ai.warmup() ohnehin warm; die Bild-Vektoren
# werden beim ersten Bedarf einmal berechnet und im RAM gecacht.

import os

import embeddings  # core/embeddings.py — bge-m3-Client (Doc/Query getrennt)

# Ordner mit den ASCII-Dateien. Per Env überschreibbar (analog _PHOTO_DIR
# in ui/app.py). Default: <repo>/data/ascii/.
ASCII_DIR = os.environ.get(
    "ZENTRALE_ASCII_DIR",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "ascii",
    ),
)

# Cosinus-Schwellwert für den Embedding-Fallback. Darunter gilt: nichts
# passt gut genug -> kein Bild. bge-m3 liefert für "klar verwandt" meist
# > 0.6; 0.55 lässt etwas Spielraum, ohne wahllos zu werden.
_EMBED_THRESHOLD = 0.55

# Geladene Bibliothek (einmalig, lazy). Liste von Dicts:
#   {"name": str, "tags": [str], "art": str, "vec": [float] | None}
# vec wird erst beim ersten Embedding-Fallback berechnet und dann gecacht.
_lib = None


def _load():
    """Liest alle .txt aus ASCII_DIR ein und parst Tags + Art. Idempotent."""
    global _lib
    lib = []
    if os.path.isdir(ASCII_DIR):
        for fn in sorted(os.listdir(ASCII_DIR)):
            if not fn.endswith(".txt"):
                continue
            try:
                with open(os.path.join(ASCII_DIR, fn), encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue
            name  = fn[:-4]
            lines = raw.split("\n")
            # Erste Zeile als "# tags: a, b, c" erkennen (sonst Dateiname).
            if lines and lines[0].strip().lower().startswith("# tags:"):
                tagline = lines[0].split(":", 1)[1]
                tags    = [t.strip().lower() for t in tagline.split(",") if t.strip()]
                art     = "\n".join(lines[1:]).strip("\n")
            else:
                tags = []
                art  = raw.strip("\n")
            if not tags:
                tags = [name.lower()]
            if art:
                lib.append({"name": name, "tags": tags, "art": art, "vec": None})
    _lib = lib
    return lib


def _ensure_loaded():
    """Lazy-Load: lädt die Bibliothek beim ersten Zugriff."""
    if _lib is None:
        _load()
    return _lib


def reload():
    """Bibliothek neu von Platte laden (z.B. nach dem Hinzufügen von Bildern)."""
    return _load()


def concept_list():
    """
    Komma-Liste aller Bild-Namen — wird in die Tool-Beschreibung von
    'zeige_ascii' gespiegelt, damit die KI sieht, was es überhaupt gibt
    (gleiche Idee wie RANGE_BUCKETS beim Kalender-Tool). Statisch ab
    Import-Zeit; nach neuen Bildern Backend neu starten.
    """
    return ", ".join(e["name"] for e in _ensure_loaded())


def _keyword_score(entry, sw):
    """
    Punktet, wie gut ein Stichwort 'sw' (klein, getrimmt) zu einem Eintrag
    passt. 0 = kein Treffer. Höher = besser.
      100  exakter Tag-Treffer oder exakter Name
       60  Substring (Stichwort in Tag/Name oder umgekehrt)
     30+n  n überlappende Einzelwörter
    """
    name = entry["name"].lower()
    cand = entry["tags"] + [name]          # alle Vergleichs-Strings

    if sw in entry["tags"] or sw == name:
        return 100
    for t in cand:
        if sw in t or t in sw:
            return 60
    sw_toks = set(sw.replace(",", " ").split())
    best = 0
    for t in cand:
        overlap = len(sw_toks & set(t.split()))
        if overlap:
            best = max(best, 30 + overlap)
    return best


def pick(stichwort):
    """
    Wählt das beste ASCII-Bild für ein Stichwort.

    Rückgabe: (name, art) oder None, wenn nichts gut genug passt
    (leere Bibliothek, leeres Stichwort, kein Keyword-Treffer UND
    Embedding-Fallback unter Schwellwert / nicht verfügbar).
    """
    lib = _ensure_loaded()
    sw  = (stichwort or "").strip().lower()
    if not lib or not sw:
        return None

    # ── Stufe 1: Keyword/Tag ──────────────────────────────────────────
    best_kw = max(lib, key=lambda e: _keyword_score(e, sw))
    if _keyword_score(best_kw, sw) > 0:
        return (best_kw["name"], best_kw["art"])

    # ── Stufe 2: Embedding-Fallback ───────────────────────────────────
    qvec = embeddings.embed_query(sw)
    if qvec is None:                       # Ollama down o.ä. -> lieber nichts
        return None
    best_sim, best_e = 0.0, None
    for e in lib:
        if e["vec"] is None:               # Tags+Name einmalig als Doc embedden
            e["vec"] = embeddings.embed_document(", ".join(e["tags"] + [e["name"]]))
        if e["vec"] is None:
            continue
        sim = embeddings.cosine_similarity(qvec, e["vec"])
        if sim > best_sim:
            best_sim, best_e = sim, e
    if best_e is not None and best_sim >= _EMBED_THRESHOLD:
        return (best_e["name"], best_e["art"])
    return None
