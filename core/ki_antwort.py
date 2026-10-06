# core/ki_antwort.py
#
# Was mit einer FERTIGEN Antwort passiert, bevor sie rausgeht: Bild-Marker
# ([[bild: name]]) herausziehen und als eigene Events feuern, den bereinigten
# Text liefern und den Zug zum Merken vormerken (core/consolidation.py).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 in
# core/ai.py — die Werkzeug-Schleife brauchte es von dort, einer der Knoten im
# Import-Kreis. Aufbau des KI-Kerns: memory/ki/kern_aufbau.md.

import re

import ascii_lib
import consolidation


# ── ASCII-Bilder als Inline-Marker: das Auslesen ───────────────────────
# Der PROMPT-Teil (die Anweisung, Marker zu tippen) gehoert zur Schiene und
# steht in profil/. Das Herausziehen aus dem Antworttext gehoert zum Kern und
# steht hier — es ist fuer jedes Modell dasselbe.

# Erkennt [[bild: name]] und tolerant auch [[ascii: name]] / [[zeige_ascii:
# name]] (die Mimikry-Variante). name = alles bis zur schliessenden Klammer,
# eine Zeile.
_ASCII_MARKER_RE = re.compile(
    r"\[\[\s*(?:bild|ascii|zeige_ascii)\s*:\s*([^\]\n]+?)\s*\]\]",
    re.IGNORECASE,
)


def marker_ziehen(text: str):
    """
    Zieht Bild-Marker aus dem Antworttext. Gibt (clean_text, [stichwort, ...])
    zurueck. Der Marker wird aus dem Text ENTFERNT - er soll nicht angezeigt
    oder gesprochen werden; das Bild laeuft als eigenes SSE-Event in den Kern.
    """
    names = [m.group(1).strip() for m in _ASCII_MARKER_RE.finditer(text)]
    if not names:
        return text, []
    clean = _ASCII_MARKER_RE.sub("", text)
    clean = re.sub(r"[ \t]{2,}", " ", clean)          # Doppel-Spaces glaetten
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()  # Leerzeilen kappen
    return clean, names


def mit_bildern(answer: str, user_query: str, store: str | None = None):
    """
    Verarbeitet eine FINALE Antwort (regulaerer Chat): zieht Bild-Marker raus,
    feuert pro Treffer ein Inline-Bild-Event ({"ascii","name"}) - ui/routen/ki.py macht
    daraus ein SSE 'ascii'-Event - und yieldet zum Schluss den bereinigten
    Text. Speichert den bereinigten Text (ohne Marker) in den Graphen.
    Generator: in der Werkzeug-Schleife via `yield from` nutzen. Nur fuer tools is None
    aufrufen (Tutor kennt keine Marker).

    store: in WELCHEN Graphen der Turn gespeichert wird. None = Core-Graph
    (data/ai_graph.json, lokales Modell). Der Cloud-Pfad (core/cloud.py) reicht
    hier seinen eigenen Graphen durch - die Isolations-Invariante lautet
    "lokal sieht alles von cloud, cloud sieht nichts von lokal", und die
    steht und faellt damit, dass Cloud-Turns NICHT im Core-Graphen landen.
    """
    import state as _state
    clean, names = marker_ziehen(answer)
    for nm in names:
        hit = ascii_lib.pick(nm)
        if hit:
            _state.push_log(f"AI →  BILD [[bild: {nm}]] → zeigt '{hit[0]}'")
            yield {"ascii": hit[1], "name": hit[0]}
        else:
            _state.push_log(f"AI →  BILD [[bild: {nm}]] → kein Treffer")
    if clean:
        yield clean
    consolidation.zug_vormerken(user_query, clean, store=store)
