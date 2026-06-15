# core/glossary.py
#
# Kuratiertes Mini-Glossar für ZENTRALE: kurze Erklärungen zu Begriffen/Features,
# die es WIRKLICH schon gibt — nichts Erfundenes, nichts Geplantes. Gedacht zum
# Nachschlagen direkt in der UI (aktuell: `?`-Such-Modal im nativen Karten-
# fenster, scripts/map_window.py). Bewusst front-agnostisch hier in core/, damit
# später auch TUI/Laptop dasselbe Glossar + dieselbe Suche nutzen können
# (Kassetten-Prinzip: Inhalt/Logik einmal, jede Front rendert nur).
#
# Pflege: bei neuen Features hier einen Eintrag ergänzen (term, keys, text).
# `keys` sind zusätzliche Suchbegriffe/Synonyme; `text` bleibt kurz (1–3 Sätze).

GLOSSARY = [
    {
        "term": "Chokepoint",
        "keys": ["chokepoint", "engstelle", "meerenge", "strait", "suez",
                 "panama", "hormuz", "malakka", "malacca", "bab-el-mandeb",
                 "gibraltar", "nadelöhr"],
        "text": "Maritime Engstelle — eine schmale, strategisch kritische "
                "Durchfahrt, durch die sich ein Großteil des Seehandels zwängen "
                "muss (Suez, Panama, Hormuz, Malakka …). Staut oder blockiert es "
                "dort, hat das überproportionale Folgen für globale Lieferketten. "
                "Das Overlay (Taste t) zeigt diese Punkte + Schiffe pro Tag — "
                "keine Routen/Wege.",
    },
    {
        "term": "IMF PortWatch",
        "keys": ["portwatch", "imf", "quelle", "daten", "source"],
        "text": "Die Quelle des Chokepoints-Overlays: ein offizieller, TÄGLICH "
                "aktualisierter Datensatz des Internationalen Währungsfonds (mit "
                "UN Global Platform / Univ. Oxford), der Schiffsverkehr an Häfen "
                "und Engstellen aus AIS-Daten schätzt. Lizenziert (nicht "
                "gemeinfrei) → wird nur lokal gecacht, nicht weiterverteilt.",
    },
    {
        "term": "Schiffe/Tag (am Marker)",
        "keys": ["schiffe", "verkehr", "traffic", "wert", "zahl", "heute",
                 "n_total", "marker"],
        "text": "Die Zahl an einem Chokepoint-Marker ist die geschätzte Anzahl "
                "Schiffspassagen am jüngsten verfügbaren Tag (Datenstand steht "
                "oben links). Die Markergröße wächst mit ~√(Schiffe).",
    },
    {
        "term": "Achse 1 — Detail/LOD",
        "keys": ["achse 1", "lod", "level of detail", "auflösung", "detail",
                 "zoom", "grob", "fein"],
        "text": "Wie scharf die Grundkarte ist. Je nach Zoom lädt das Backend "
                "unterschiedlich viel Geometrie (Natural Earth 1:110m → 1:50m → "
                "1:10m). Von weit weg grob, beim Reinzoomen detaillierter.",
    },
    {
        "term": "Schifffahrtsrouten",
        "keys": ["route", "routen", "schifffahrtsrouten", "linien", "wege",
                 "shipping", "handelsrouten", "seewege"],
        "text": "Die Linien des Welt-Seehandels (woauf Schiffe fahren) — als "
                "dezente Pfade unter den Chokepoint-Markern. Reine Geometrie aus "
                "IMF PortWatch (statisch), ohne Namen/Verkehr. Zusammen mit den "
                "Engstellen-Punkten ergeben sie das Handelsrouten-Overlay (Taste "
                "t im Fenster, o in der TUI).",
    },
    {
        "term": "Achse 2 — Overlays",
        "keys": ["achse 2", "overlay", "layer", "thematisch", "handelsrouten",
                 "trade"],
        "text": "Thematische Ebenen, die ÜBER der Grundkarte liegen und stapelbar "
                "sind. Erster gebauter Overlay: trade/chokepoints. Jeder Sub-Layer "
                "zieht aus genau einer offiziellen Quelle (Provenienz inklusive).",
    },
    {
        "term": "Achse 3 — Zeit",
        "keys": ["achse 3", "zeit", "zeitreise", "vintage", "stand", "datum",
                 "historie"],
        "text": "Denselben Layer zu einem anderen Zeitpunkt ansehen (Vergangenheit/"
                "Prognose). Nicht jeder Layer ist zeitfähig. Bei den Chokepoints "
                "ist 'Stand' das Datum der gezeigten Tagesdaten.",
    },
    {
        "term": "Web-Mercator",
        "keys": ["mercator", "projektion", "verzerrung", "afrika", "grönland",
                 "fläche"],
        "text": "Die Karten-Projektion (wie Google/OSM). Winkeltreu, aber NICHT "
                "flächentreu: polnahe Gebiete (Grönland) wirken riesig, "
                "äquatornahe (Afrika) relativ zu klein. Für zoombare Karten "
                "korrekt; eine flächentreue Variante ist geplant.",
    },
    {
        "term": "Natural Earth",
        "keys": ["natural earth", "basiskarte", "küste", "grenzen", "land",
                 "gemeinfrei", "public domain"],
        "text": "Die gemeinfreie Vektor-Datenquelle der Grundkarte (Küsten, "
                "Ländergrenzen) in drei Maßstäben (110m/50m/10m). Klein, offline, "
                "public domain — wird mit ins Repo committet.",
    },
    {
        "term": "Provenienz",
        "keys": ["provenienz", "quelle", "lizenz", "stand", "vintage",
                 "herkunft", "cache", "license"],
        "text": "Jedes Overlay-Feature trägt seine Herkunft mit: Quelle, Lizenz, "
                "Datenstand und wann geholt. Steht oben links, wenn das "
                "Chokepoints-Overlay an ist — damit klar ist, wer was wann sagt.",
    },
    {
        "term": "Gradnetz",
        "keys": ["gradnetz", "graticule", "längengrad", "breitengrad", "raster",
                 "linien", "g"],
        "text": "Die dünnen Längen-/Breitengrad-Linien (alle 30°). Äquator und "
                "Nullmeridian sind etwas heller. Taste g blendet sie um.",
    },
    {
        "term": "Länder-Labels",
        "keys": ["label", "labels", "name", "länder", "beschriftung", "hover",
                 "l"],
        "text": "Der Ländername unter dem Mauszeiger (Hover). Taste l blendet die "
                "Beschriftung um.",
    },
    {
        "term": "Natives Fenster",
        "keys": ["fenster", "pygame", "window", "wow", "vektor"],
        "text": "Dieses Karten-Fenster (pygame) — der 'Wow'-Front mit echter "
                "antialiased Vektorgrafik, Meer-Verlauf und weichem Pan/Zoom. "
                "Klappt aus der Terminal-TUI mit Taste w auf.",
    },
    {
        "term": "Pan / Zoom",
        "keys": ["pan", "zoom", "navigation", "ziehen", "rad", "pfeiltasten",
                 "schwenken", "band", "wrap", "datumsgrenze", "endlos"],
        "text": "Pan: Maus ziehen oder Pfeiltasten. Zoom: Mausrad (auf den "
                "Cursor) oder + / −. Taste 0 springt weich zurück zur Weltansicht. "
                "Die Bewegung easet (weich statt sprunghaft). Horizontal läuft die "
                "Karte als ENDLOS-BAND: über die Datumsgrenze hinaus pannen geht "
                "nahtlos weiter (links Verschwundenes kommt rechts wieder), damit "
                "Routen z.B. Asien→Amerika am Stück sichtbar bleiben.",
    },
]


def search(query, limit=20):
    """Glossar nach `query` durchsuchen (case-insensitiv, über Begriff + Synonyme
    + Text). Leerer Query → alle Einträge. Rückgabe: Liste von Einträgen,
    bestplatzierte zuerst."""
    q = (query or "").strip().lower()
    if not q:
        return list(GLOSSARY)
    scored = []
    for e in GLOSSARY:
        term = e["term"].lower()
        score = 0
        if q == term:
            score = 100
        elif term.startswith(q):
            score = 80
        elif q in term:
            score = 60
        if any(q in k for k in e["keys"]):
            score = max(score, 50)
        if q in e["text"].lower():
            score = max(score, 20)
        if score:
            scored.append((score, e))
    scored.sort(key=lambda t: -t[0])
    return [e for _, e in scored[:limit]]
