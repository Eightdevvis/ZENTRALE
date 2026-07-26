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
                "Das Overlay (Taste h) zeigt diese Punkte + Schiffe pro Tag — "
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
                "h im Fenster, o in der TUI).",
    },
    {
        "term": "Verkehrsdichte (Heatmap)",
        "keys": ["dichte", "density", "heatmap", "verkehr", "wärmebild", "d",
                 "world bank", "weltbank", "ais", "gemessen", "korridore"],
        "text": "Die gemessene Schiffsdichte als weiche Wärmewolke übers Meer "
                "(Taste d) — hell/warm = viel Verkehr. Quelle: World Bank/IMF aus "
                "AIS-Positionen 2015–2021 (CC BY 4.0), also ein GEMESSENES "
                "Mittel, kein gezeichneter Idealweg wie die Routen-Linien. "
                "Statischer Stand (kein Tagesbezug); Tagesaktualität sitzt in den "
                "Chokepoints. Wird tief reingezoomt nur weicher, nie pixelig.",
    },
    {
        "term": "Achse 2 — Overlays",
        "keys": ["achse 2", "overlay", "layer", "thematisch", "handelsrouten",
                 "trade", "politik", "konflikt"],
        "text": "Thematische Ebenen, die ÜBER der Grundkarte liegen und stapelbar "
                "sind. Gebaut: (1) Handel — Routen + Chokepoints + Verkehrsdichte; "
                "(2) Politik/Konflikt — Gebietskontrolle + Konfliktereignisse + "
                "umstrittene Grenzen. Jeder Sub-Layer zieht aus genau einer "
                "offiziellen Quelle (Provenienz inklusive). Beide laufen sowohl im "
                "nativen Fenster (Handel=h, Dichte=d, Politik=p) als auch in der TUI.",
    },
    {
        "term": "Achse 3 — Zeit",
        "keys": ["achse 3", "zeit", "zeitreise", "vintage", "stand", "datum",
                 "historie", "scrubber", "zeitstrahl"],
        "text": "Denselben Layer zu einem anderen Zeitpunkt ansehen (Vergangenheit/"
                "Prognose). Nicht jeder Layer ist zeitfähig. Bei den Chokepoints "
                "ist 'Stand' das Datum der gezeigten Tagesdaten. Voll zeitreisefähig "
                "ist die Gebietskontrolle (VIINA): der Scrubber (Tasten ,/. einen "
                "Schritt vor/zurück — gedrückt halten geht, ; = jetzt) zeigt die "
                "Frontlage wie an einem beliebigen Tag. Taste t stellt die "
                "Schrittweite: Woche→Monat→Jahr→10/50/100 Jahre.",
    },
    {
        "term": "Politik / Konflikt-Overlay",
        "keys": ["politik", "konflikt", "political", "krieg", "front", "overlay",
                 "gewalt", "ukraine"],
        "text": "Der zweite Achse-2-Overlay: ein Komposit aus Gebietskontrolle "
                "(VIINA, Ukraine), Konfliktereignissen (UCDP) und umstrittenen "
                "Grenzen (Natural Earth). ACLED liefert reichere Ereignisse, ist "
                "aber lizenz-gesperrt und nur lokal/explizit dazuschaltbar. Jeder "
                "Sub-Layer trägt seine Provenienz mit. Im nativen Fenster mit Taste "
                "p, in der TUI über den Overlay-Zyklus (o).",
    },
    {
        "term": "Gebietskontrolle (VIINA)",
        "keys": ["kontrolle", "gebietskontrolle", "viina", "front", "frontlinie",
                 "besetzt", "ukraine", "ua", "ru", "umstritten", "control"],
        "text": "Wer welchen Ort kontrolliert — je Siedlung ein Punkt, eingefärbt "
                "nach Status (UA / RU / umstritten). Quelle: VIINA (Yuri Zhukov, "
                "Yale/U-Michigan), ein tägliches MEHRHEITSVOTUM aus DeepStateMap, "
                "ISW und Wikipedia (ODbL, Namensnennung + Share-alike; kein reiner "
                "Primärdatensatz, sondern Aggregat). Voll zeitreisefähig (Achse 3): "
                "die Statuswechsel sind als Zeitachse gecacht.",
    },
    {
        "term": "Konfliktereignisse (UCDP)",
        "keys": ["ucdp", "ereignis", "ereignisse", "gewalt", "opfer", "ged",
                 "uppsala", "konfliktereignis", "event"],
        "text": "Einzelne bewaffnete Gewaltereignisse als Punkte (Ort + Opferzahl). "
                "Quelle: UCDP GED — Georeferenced Event Dataset der Universität "
                "Uppsala (CC BY 4.0, deckt 1989–heute). Für Tagesaktualität braucht "
                "es einen Zugangstoken (per Mail bei UCDP); der Zeitfilter für "
                "Ereignisse ist noch nicht scharfgestellt.",
    },
    {
        "term": "ACLED",
        "keys": ["acled", "armed conflict", "ereignisse", "lizenz", "eula",
                 "nur lokal", "event"],
        "text": "Armed Conflict Location & Event Data — reichere Konfliktereignisse "
                "als UCDP. Lizenz (ACLED EULA): nicht-kommerziell, KEINE "
                "Weiterverteilung → wird nie ins Repo committet, nur lokal gecacht "
                "und nur explizit zugeschaltet. Braucht API-Key + Registrierung.",
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
