# Maps — Quellen-Charta (Layer → offizielle Quelle → Lizenz)

> **Grundsatz (Sasha): seriöses Tool = Primärquelle + tagesaktuell + sauber
> lizenziert.** Keine „random GitHub-Repos" und kein selbstkuratierter Ersatz,
> wo eine ausstellende Institution existiert. Jeder thematische Sub-Layer (Achse
> 2) zieht aus GENAU EINER offiziellen Quelle; das Komposit `trade` morpht sich
> aus den Sub-Layern. Quellen bleiben getrennt → man kann sie gegeneinander
> abgleichen.

## Provenienz ist Pflicht (first-class)

Jedes Overlay-Feature trägt seine Herkunft mit und die Front zeigt sie an:
`source.name`, `source.url`, `source.license`, `vintage` (Datenstand),
`retrieved_at` (wann geholt). Antwort-Format siehe `/api/map/layer/<id>`.

## Struktur vs. Dynamik (warum „tagesaktuell" nur halb gilt)

- **Struktur** (Geometrie: Engstellen-Orte, Häfen, Kabel-/Pipeline-Verläufe) ist
  **quasi-statisch** — ändert sich über Monate. Selten syncen.
- **Dynamik** (Verkehr/Tag, Kanal-Status, Flüsse) ist **echt täglich**.
- IMF PortWatch trennt das selbst: Geometrie-Layer + Tagestabelle, gejoint per
  `portid`. Das ist exakt unsere A/B-Trennung (siehe maps_system.md).

## Lizenz-Regel: committen vs. nur cachen

| Quelle | gemeinfrei? | ins Git-Repo? | Wie genutzt |
|--------|-------------|---------------|-------------|
| Natural Earth (Basiskarte) | ja (Public Domain) | **ja**, `core/map/data/*.geojson` | committet |
| IMF PortWatch (Overlay)    | nein (IMF-Terms)  | **nein** | live geholt, nur LOKAL gecacht (`core/map/data/cache/`, .gitignore't) |
| World Bank Global Shipping Traffic Density | **ja (CC BY 4.0)** | **ja** (mit Namensnennung; Raster ggf. verkleinert/quantisiert wegen Größe) | gemessenes AIS-Dichteraster, committbar |
| EMODnet Human Activities Vessel Density | teils (frei mit Namensnennung **EMODnet + CLS**) | ja, **mit Namensnennung** (Größe prüfen) | gemessenes AIS-Raster, EU-Gewässer |
| Marine Cadastre AIS Vessel Transit Counts | **ja (CC0)** | **ja** | gemessen, US-Gewässer; hat sogar Vektor-Track-Lines |

**Begründung:** IMF-Terms erlauben *Anzeige mit Namensnennung*, aber keine
*Weiterverteilung*. Ein lokaler Cache ≠ Weiterverteilung (wie ein Browser-Cache).
Indem PortWatch-Daten nie ins Repo wandern, greift die heikle Klausel gar nicht.
**Vorbehalt:** würde ZENTRALE je öffentlich/kommerziell, braucht das einen echten
Lizenz-Check.

## Kombinieren: STAPELN statt verschmelzen (+ Konsens-Layer)

Mehrere Routen-Quellen geben mehr Info — aber nur, wenn man sie **nicht zu einer
Zahl/Geometrie einkocht**. Die Quellen sind verschiedene Objekte (Vektor-Linien
vs. Dichte-Raster), verschiedene Einheiten (idealer Weg vs. Stunden/km² vs.
Positions-/Transit-Zählung), verschiedene Abdeckung (global vs. EU vs. US),
verschiedene Stände. Stumpf übereinanderrechnen = Einheiten mischen, Nahtkanten,
keine ehrliche „von-wann/woher"-Antwort mehr → das wäre „devious".

**Stattdessen zwei Ebenen:**

1. **Einzel-Layer (souverän).** Jede Quelle ist ein eigener Sub-Layer mit eigener
   Provenienz, eigener Legenden-Zeile, eigenem Stand, einzeln togglebar. So
   bleiben sie **vergleichbar** (Sashas Kern-Wunsch: Quellen gegeneinander sehen).

2. **`consensus` — der Multimix (abgeleitet).** Zeigt ALLE gleichzeitig und hebt
   ihre **Überschneidung** hervor — also wo sich *unabhängige* Quellen einig sind,
   dass dort Verkehr ist (das vertrauenswürdigste Signal). Damit das sauber bleibt,
   drei Pflicht-Regeln:
   - **Vergleichbar machen, nicht gleichsetzen:** jede Quelle aufs selbe Anzeige-
     raster legen und **rang-/quantil-normalisieren** auf relative Intensität 0–1.
     „Viel Verkehr *relativ zur eigenen Quelle*" wird vergleichbar — ohne zu
     behaupten EMODnet-Stunden = WB-Positionen.
   - **Abdeckung ehrlich kodieren:** pro Zelle zählt nur, was dort *verfügbar* ist
     (Pazifik: WB + PortWatch; EU: + EMODnet; US-Küste: + Marine Cadastre). Anzeige
     ist **„N von M hier verfügbaren Quellen stimmen überein"** — nie Phantom-
     Abdeckung vortäuschen, keine künstlichen Nahtkanten.
   - **Überschneidung = das Laute:** Sättigung trägt die **Konsens-Konfidenz**
     (wie viele unabhängige *gemessene* Quellen konkurrieren), Helligkeit die
     kombinierte Intensität. Einzelquelle/Widerspruch wird gedämpft.
   - **Abgeleitet, also gestempelt:** `source: derived`, Rezeptur dokumentiert —
     nie als Rohmessung ausgegeben. (Spezialfall: `routes_validated` = PortWatch-
     Linien × gemessene Dichte → „von Messung bestätigte" Linien statt Deko.)

## Sub-Layer-Register (Stand 2026-06)

### `trade/chokepoints` — LIVE ✅
- **Institution:** IMF PortWatch (https://portwatch.imf.org), mit UN Global
  Platform / Univ. Oxford. Lizenz: IMF-Terms (Anzeige + Namensnennung, keine
  Weiterverteilung) — `commit_ok = False`.
- **Struktur:** ArcGIS `PortWatch_chokepoints_database/FeatureServer/0` — 28
  Punkte (Suez, Panama, Hormuz, Malakka, Bab-el-Mandeb, Taiwan/Korea/Dover/
  Gibraltar Strait …) mit lat/lon, Jahressumme, Top-Industrien.
- **Dynamik:** ArcGIS `Daily_Chokepoints_Data/FeatureServer/0` — Tageszeile je
  Engstelle (`n_total`/`n_tanker`/… + `capacity`). **täglich**, wir ziehen das
  jüngste Datum, Join per `portid`.
- **Code:** `core/map/layers/portwatch.py` (Fetch+Cache+Provenienz),
  `core/map/layers/trade.py` (Projektion). Refresh: `python -m
  map.layers.portwatch` (Cron-fähig) → schreibt
  `core/map/data/cache/portwatch_chokepoints.json`.
- **Org-Root (alle PortWatch-Services):**
  `https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services`

### `trade/routes` — LIVE ✅
- **Geometrie:** PortWatch `Global_Shipping_Routes/FeatureServer/**15**` (Polyline!
  Layer 0 ist leer). EIN Feature = eine MultiLineString mit ~402 Segmenten / 6336
  Punkten (CAD/DXF-Import der Welt-Schifffahrtslinien). **Statisch** (DocUpdate
  2023-02-28), rein geometrisch — keine Namen/Verkehr. Selbe Quelle/Lizenz wie
  oben → Cache `core/map/data/cache/portwatch_routes.json` (gitignore't).
- **Komposit:** `/api/map/layer/trade` ohne `sub` liefert Routen (Linien) +
  Chokepoints (Punkte) zusammen — so wird das „Handelsrouten"-Dach ehrlich.
  `?sub=routes` / `?sub=chokepoints` adressieren die Sub-Layer einzeln.
- **Code:** `portwatch.routes()` + `trade.py` (Komposit), `render.project_polyline`.

### `trade/density` — Render GEBAUT (Fenster), Ingest ausstehend ⭐
- **Institution:** World Bank Data Catalog, „Global Shipping Traffic Density"
  (Dataset 0037580) — entstanden aus **IMFs eigener AIS-Analyse** (Cerdeiro,
  Komaromi, Liu, Saeed 2020). Also dieselbe institutionelle Linie wie unsere
  Chokepoints, nur das *gemessene* Produkt → die Layer sind kohärent.
- **Was:** stündliche AIS-Positionen **Jan 2015 – Feb 2021**, aggregiert zu einem
  Dichte-**Raster**, 0,005° (~500 m), 6 Layer. Original: Zenodo-Zip
  `shipdensity_global.zip` (**534 MB**, ~10 GB entpackt), CC BY 4.0.
  (Auch als Esri-ImageServer gespiegelt, aber `TilesOnly` = nur vorgefärbte
  Kacheln, keine Rohwerte → unbrauchbar für eigene Farben + Konsens.)
- **Lizenz: CC BY 4.0 → `commit_ok = True`.** Anders als PortWatch: das
  ABGELEITETE Mini-Raster darf (mit Namensnennung) ins Repo.
- **Pipeline (A/B):** `scripts/ingest_shipdensity.py` (läuft EINMAL auf dem PC,
  braucht Netz + `pip install tifffile`) lädt/liest den GeoTIFF, rechnet auf
  **0,05°** runter, log-skaliert auf `uint8`, schreibt
  `core/map/data/shipdensity_density_0p05.npz` (wenige MB, **committen**).
  `core/map/layers/density.py` lädt das offline (nur numpy), trägt Provenienz.
- **Render:** **nur natives Fenster** (Taste `d`) — weiche Heatmap übers Meer
  (Welt→lon/lat samplen, Farb-LUT, smoothscale → nie harte Pixel; Welt-Wrap
  gratis). TUI bewusst NICHT (Sashas Vorgabe: Density vorerst nur Fenster).
- **Stand:** statischer Einmal-Aggregat (kein Update) — A/B-Logik: Tages­aktualität
  sitzt in den Chokepoints, nicht hier. Caption trägt „Stand 2015–2021".
- **OFFEN:** der einmalige Ingest muss auf Sashas PC laufen (Sandbox kommt nicht
  an Zenodo/World Bank — 403). Danach ist der Layer live.
- **URL:** https://datacatalog.worldbank.org/search/dataset/0037580

### `trade/eu` — GEPLANT (gemessen, EU, monatlich)
- **Institution:** EMODnet Human Activities, Vessel Density Map. AIS von CLS +
  ORBCOMM. 1×1 km GeoTIFF, **Stunden/km²/Monat**, monatlich + Jahresmittel,
  jährlich aktualisiert. **Nur EU-Gewässer + Nachbarschaft.**
- **Lizenz:** frei (kommerziell + nicht-kommerziell) mit Namensnennung EMODnet
  **+ CLS** → committbar mit Attribution (Größe prüfen).
- **Rolle:** regionale Schärfung im Konsens-Layer (mehr/aktuellere Auflösung in EU).

### `trade/us` — GEPLANT (gemessen, US, hat Vektor-Linien)
- **Institution:** Marine Cadastre (NOAA/BOEM), „AIS Vessel Transit Counts". 100-m-
  Raster, **jährlich** (2015–2024), plus **Track-Lines (Vektor!)**. **Nur US-EEZ.**
- **Lizenz: CC0 / Public Domain → `commit_ok = True`.**
- **Rolle:** regionale Schärfung + einzige gemessene *Linien*-Quelle.
- **URL:** https://hub.marinecadastre.gov/pages/vesseltraffic

### `trade/consensus` — GEPLANT (abgeleiteter Multimix)
- **Was:** der Konsens-Layer aus dem Abschnitt „Kombinieren" oben — alle
  verfügbaren Quellen rang-normalisiert aufs selbe Raster, Überschneidung
  hervorgehoben, Abdeckung ehrlich kodiert. `source: derived`, Rezeptur dokumentiert.
- **Hängt an:** `density` (+ optional `eu`/`us`) + `routes` — baut erst, wenn
  mindestens zwei gemessene Quellen live sind.

### Geprüfte, noch NICHT eingeplante Quellen
- **`trade/ports` (Hafen-Aktivität):** PortWatch `PortWatch_ports_database` +
  `Daily_Ports_Data` (5,6 Mio Zeilen, Join per `portid`), täglich.
- **`trade/disruptions`:** PortWatch `portwatch_disruptions_database` (Rotes
  Meer, Kanalsperren) — eher Richtung News/Politik-Layer.
- **Fischerei-Verkehr (täglich, API):** Global Fishing Watch API (AIS, CC-BY-SA) —
  aber primär *Fischerei*-Schiffe, nicht Fracht → kein „Handelsrouten"-Fit.
- **Häfen-Stammdaten:** NGA World Port Index (US-Behörde, Public Domain →
  `commit_ok = True`).
- **Seekabel:** TeleGeography Submarine Cable Map API (`www.submarinecablemap.com/
  api/v3/cable/cable-geo.json`) — Branchenstandard, Namensnennung, nicht PD.
- **Öl/Gas-Pipelines:** Global Energy Monitor (GGIT, CC BY 4.0) — Download nur
  Excel/Portal, kein direktes GeoJSON; oder OSM `man_made=pipeline` (ODbL, groß).
  **Offen — Sasha sucht Download-Pfad/Lizenz, bevor gebaut wird.**
- **Live-AIS (Schiffe in Echtzeit):** kein freier globaler, permissiver Anbieter;
  regional staatlich frei (Kystverket/Norwegen, DMA/Dänemark), global nur
  kommerziell (Spire/MarineTraffic). **Offen.**

## Verworfen (zu schwach für ein seriöses Tool)
- `newzealandpaul/shipping-lanes` (GitHub-Repo) — ist nur eine Kopie einer
  ~12 Jahre alten LOC/CIA-Karte. Nicht aktuell, nicht primär → raus.
