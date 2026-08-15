# core/map/ — das Maps-System (Geo-Logik, front-agnostisch)
#
# Architektur & großer Plan: memory/maps/maps_system.md.
#
# Hier liegt ALLE Karten-Logik EINMAL, ohne curses/HTML/SVG — die Fronten
# (TUI, Laptop, Monolith) holen sich fertig aufbereitete Features über den
# /api/map-Kontrakt und zeichnen nur (Kassetten-Prinzip, siehe
# claude_hinweise.md). Bewusst pure Python-stdlib (nur json + math) — keine
# shapely/geopandas/numpy, passt zur Offline-/Lean-Philosophie.
#
# Schritt 1 (jetzt): grobe Basiskarte — Küstenlinien (Natural Earth 1:110m)
# als Vektor, projiziert und auf das vom Client genannte Zellraster skaliert.
# Overlays (politisch/wirtschaftlich/klima) und tiefere LOD-Stufen (OSM)
# kommen schrittweise dazu, ohne diese Engine umzubauen.

from .render import base_features, base_braille, country_outlines  # noqa: F401  (Einstieg für app.py)
from . import layers  # noqa: F401  (Overlay-Registry, Achse 2 — Handelsrouten etc.)
