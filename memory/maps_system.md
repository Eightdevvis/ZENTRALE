# Maps-System (interaktive Karte, Layer-Architektur)

> **STATUS (2026-06): Schritt 1 (Basiskarte) + erster Achse-2-Overlay live — TUI + natives Fenster.** Die
> Architektur steht (drei Achsen, gemeinsames Substrat + Overlays); gebaut wird
> Schritt für Schritt (Roadmap unten), Sasha gibt pro Layer die Details vor.
> Erledigt: `core/map/`-Engine + `/api/map/base` + TUI-Renderer (Taste `m`) +
> **natives pygame-Fenster** (`scripts/map_window.py`, aus der TUI mit `w`
> aufklappbar — der „Wow"-Front mit echter antialiased Vektorgrafik). Der
> ASCII-Look der TUI bleibt nur die reduzierte Notnagel-Variante.
> **NEU: erster thematischer Overlay (Achse 2) = `trade/chokepoints`** (IMF
> PortWatch, täglicher Schiffsverkehr an den maritimen Engstellen) — über
> `/api/map/layer/trade`, in der TUI Taste `o`, im Fenster Taste `t`. Quellen
> + Lizenzregeln stehen in **`memory/maps_quellen.md`** (Provenienz-Charta).

## Vision

Eine eigene, interaktive Karte in ZENTRALE — auf Dauer in *allen* Fronten
(TUI, Laptop, Monolith), gebaut und getestet aber **zuerst nur in der TUI**.
Zwei Endziele, die sich überlagern lassen sollen:

1. **Thematische Karte** (zuerst): aktive Konflikte, Grenzen, Truppen-
   bewegungen, später wirtschaftliche und klimatische Lagen. Vorbild grob:
   liveuamap. Von weit weg nur die groben Marker, beim Reinzoomen mehr Detail.
2. **Funktionale Karte** (später): Google-Maps-artig — Orientierung,
   Routenplanung. Soll mit den thematischen Layern *überlagerbar* sein
   ("was geht in der Gegend ab, wo ich gerade unterwegs bin").

## Die drei Achsen von „Layer" (WICHTIG, nicht verwechseln)

Im Gespräch wurden mehrere Dinge „Layer" genannt, die architektonisch getrennt
gehören. Drei unabhängige Achsen existieren parallel:

- **Achse 1 — Detailtiefe** (Zoom/LOD): wie scharf die Grundkarte ist.
- **Achse 2 — thematische Overlays**: was du oben drauf stapelst (Politik/…).
- **Achse 3 — Zeit**: an welchem Zeitpunkt du den Layer ansiehst (zurück/vor).

Achse 3 ist **nicht für jeden Layer verfügbar** (s.u.) — Achse 1 und 2 sind es
immer.

### Achse 1 — Detailtiefe (Level-of-Detail, LOD / Zoom)

*Eine* Grundkarte, die je nach Zoom **unterschiedlich viel Geometrie** lädt.
Das ist das „von weit weg grob, beim Reinzoomen detaillierter". Es wird
bewusst **nie alles auf einmal** gerendert — pro Viewport+Zoom liefert das
Backend nur die passende Detailstufe. Das ist der Kern-Mechanismus, nicht ein
Verzicht.

Datenquellen entlang dieser Achse (dieselbe Karte, verschiedene Schärfe):

| Zoom        | Quelle                | Was                                          | Größe        |
|-------------|-----------------------|----------------------------------------------|--------------|
| weit (z0–6) | **Natural Earth**     | Ländergrenzen, Küsten, große Flüsse, Hauptstädte | wenige MB (gemeinfrei) |
| nah (z10+)  | **OpenStreetMap (OSM)** | Straßen, Orte, Gebäude — *das* Open-Source-Kartenmaterial | riesig, erst später |

- **Natural Earth** kommt fertig in drei Maßstäben (1:110M / 1:50M / 1:10M),
  die fast 1:1 auf Zoomstufen passen. Klein, offline, public domain → ideal
  für den Start und für ZENTRALEs „local-first, offline by default"-Ethos.
  - **GEBAUT (2026-06): alle drei Stufen liegen unter `core/map/data/`** (110m
    Küste+Länder ~1 MB, 50m ~4,5 MB, 10m ~22 MB). `basemap.coastline(level)` /
    `basemap.countries(level)` laden pro Stufe lazy + gecacht; `basemap.
    lod_for_zoom(zoom)` wählt die Stufe (zoom<2 →110m, <4.5 →50m, sonst 10m).
  - **Performance-Lektion (natives Fenster):** feine Stufen sind erst nutzbar
    mit (a) **Viewport-Clipping** (Sutherland-Hodgman) VOR dem Füllen — sonst
    rastert ein teils off-screen liegendes Riesen-Polygon zehntausende Scanlines
    (10m war ohne ~5–11 s/Frame), und (b) **numpy-vektorisierter Projektion**
    (>500k Punkte/Frame in reinem Python = Sekunden). Mit beidem: Welt ~25–38 fps,
    tiefer 10m-Zoom ~6–11 fps (nutzbar, beim schnellen Pannen leicht zäh).
    Die Vereinfachung (aufeinanderfolgende Punkte auf gleicher Pixel-Zelle weg)
    kappt die Zeichenlast zusätzlich auf ~Bildschirmauflösung.
- **OSM** ist genau das quelloffene Material, auf dem viele Google-Maps-
  Alternativen beruhen. Wird **nicht** sofort gebaut, aber das LOD-System wird
  so entworfen, dass OSM-Detail bei tiefem Zoom **einsteckbar** ist — ohne die
  Architektur umzubauen.

### Achse 2 — Thematische Overlays

Liegen *über* der Grundkarte, sprechen dasselbe Koordinatensystem, sind
beliebig **stapelbar** (das „übereinanderlegen"). Unabhängig von Achse 1.

- `trade` — **erster gebauter Overlay (2026-06)**, Komposit aus Sub-Layern, je
  EINE offizielle Quelle (siehe `memory/maps_quellen.md`). Live: `chokepoints`
  (IMF PortWatch, maritime Engstellen + täglicher Schiffsverkehr). Geometrie
  (Engstellen-Punkte, quasi-statisch) + Tagesdaten (Verkehr) joint die Engine
  per `portid` — exakt die A/B-Trennung. Geplant: `routes` (PortWatch
  `Global_Shipping_Routes` L15), `ports`, Seekabel (TeleGeography), Pipelines.
  Wichtig: PortWatch ist lizenziert → Daten nur lokal gecacht, NICHT committet.
- `political` — Konflikte, Grenzen, Truppenbewegungen.
- `economic` — danach.
- `climate` — danach.
- `terrain` — **Höhe/Relief**: Berge, Höhenlinien, Geländeschattierung
  (Hillshade), Pässe/Gipfel. Datenquelle ist ein **DEM** (Digital Elevation
  Model, z.B. SRTM/ETOPO, gemeinfrei). Grenzfall zur Achse 1: Relief ist
  physische Geographie wie die Küstenlinie — wir führen es aber als
  **zuschaltbaren** Overlay, damit man die Karte auch „flach" haben kann.
  In der TUI: Höhe über Farbverlauf/Schattierung (Truecolor) statt Konturlinien.
- `subsurface` — **Unterirdisches**: Höhlen, Tunnel, Minen, Bunker, U-Bahn,
  evtl. Grundwasser. Liegt konzeptionell **unter** der Oberfläche → bringt eine
  **Tiefen-Dimension** mit (s.u.). Datenquelle: OSM (`tunnel`, `man_made=mine`,
  `natural=cave_entrance`, `level=…`) plus ggf. spezialisierte Höhlen-Datensätze.
- `navigation` — später (Routing/Orientierung), liegt auf derselben Engine.

> **Tiefen-Dimension (vom `subsurface`-Layer eingeführt).** „Unter der
> Oberfläche" ist nicht nur ein weiterer Overlay — es ist eine eigene
> **vertikale Ebene** (negative Höhe / „Level", analog zu Stockwerken in
> Indoor-Karten, OSM `level`). Praktisch heißt das: man will zwischen
> **Oberflächensicht** und **Untergrundsicht** umschalten *oder* sie
> halbtransparent überlagern („was liegt unter mir?"). Wir behandeln das
> vorerst als **Eigenschaft des `subsurface`-Layers** (ein optionaler
> Tiefen-/Level-Wähler, der nur erscheint, wenn der Layer aktiv ist) — analog
> dazu, wie die Zeitachse (Achse 3) nur bei zeitfähigen Layern auftaucht. Falls
> später mehrere Layer Tiefen brauchen (Indoor-Stockwerke, Geologie-Schichten),
> kann daraus eine eigene **Achse 4 (vertikale Ebene/Tiefe)** werden — bewusst
> noch nicht festgezurrt, nur als Haken vermerkt.

### Achse 3 — Zeit (Zeitreise pro Layer)

Die Layer lassen sich **in der Zeit nach hinten und nach vorne** bewegen — man
sieht denselben Layer zu einem anderen Zeitpunkt. So wird sichtbar, **wie sich
etwas entwickelt hat** (Vergangenheit) und **wohin es sich entwickelt**
(Zukunft/Prognose).

**Nicht jeder Layer hat eine Zeitachse** — vor allem am Anfang nicht. Sie ist
eine *Eigenschaft des Layers*, nicht der Engine:

| Layer        | Zeitachse? | Vergangenheit            | Zukunft (Prognose)                          |
|--------------|-----------|--------------------------|---------------------------------------------|
| `navigation` | nein      | —                        | — (für Routing irrelevant)                  |
| `political`  | ja        | historische Frontverläufe/Grenzen | **vorerst geparkt** (Politik-Vorhersage ist hart) |
| `climate`    | ja        | Klima-Historie           | echte **Vorhersagemodelle** existieren bereits → spannender Teil |
| `economic`   | (offen)   | je nach Datenlage        | je nach Datenlage                           |
| `terrain`    | nein      | — (geologisch ~statisch) | — (auf Menschen-Zeitskala konstant)         |
| `subsurface` | nein      | — (im Wesentlichen statisch) | — (Höhlen/Tunnel ändern sich kaum)      |

- **Vergangenheit** = derselbe Layer, andere Datenscheibe (Zeitstempel der
  Features). Mechanisch „nur" eine weitere Query-Dimension.
- **Zukunft** = Prognose-Daten. Bei **Klima** gibt es dafür fertige
  Vorhersagemodelle — das ist der interessante Ausbau. Bei **Politik** wird die
  Zukunfts-Projektion **vorerst weggelassen** (Vergangenheit/Gegenwart ja,
  Prognose später/nie).

**Architektur-Konsequenz:** der `/api/map/layer/<id>`-Kontrakt bekommt einen
optionalen **Zeit-Parameter** (`?at=<timestamp>` o.ä.). Layer ohne Zeitachse
ignorieren ihn (liefern immer „jetzt"); Layer mit Zeitachse melden in der
Registry ihren verfügbaren Zeitbereich (min/max, ob Zukunft vorhanden). Die
Front zeigt einen Zeit-Regler nur, wenn der aktive Layer eine Zeitachse hat.

> Merksatz: **Achse 1 = wie scharf die Grundkarte ist. Achse 2 = was du oben
> drauf stapelst. Achse 3 = zu welchem Zeitpunkt.** Getrennt lösen sich die
> Fragen sauber auf; Achse 3 ist optional pro Layer.

## Grundsatzentscheidung: gemeinsames Substrat + Overlays

Politik/Wirtschaft/Klima **und** die spätere Navi-Map liegen auf **EINEM
gemeinsamen Geo-Substrat** als unabhängige, stapelbare Overlay-Layer. Die
Base-Map-Engine (Koordinaten, Projektion, Viewport, Zoom/LOD) wird **einmal**
gebaut; alle Layer sind nur Daten-Provider auf demselben Koordinatensystem.

Bewusst **nicht** gewählt: die politische Map als standalone Ding bauen und
später zur Navi-Map zusammenführen (Migrationsrisiko). Und auch **nicht**:
alles von Anfang an in einen Mega-Merge zwingen. Der Mittelweg — ein Substrat,
viele Overlays — ist genau das, was das Endziel ("übereinanderliegen") braucht.

## Architektur (folgt dem Kassetten-Prinzip)

Die Map ist ein Lehrbuchfall für das Haus-Prinzip „geteilte Logik, pro Front
gerendert" (siehe `claude_hinweise.md` → „Kassetten-Prinzip"). Vorbild im
Kleinen ist das **Graph-Werkzeug**: Logik in `core/graphs.py` + Registry +
`/api/graphs`, dreifach gerendert (Monolith-SVG, TUI-curses, Laptop offen).

```
core/map/                 ← ALLE Geo-Logik, front-agnostisch
  ├─ projection.py        WGS84 lon/lat ↔ Pixel, Web-Mercator, slippy z/x/y
  ├─ viewport.py          center(lon,lat)+zoom → sichtbare bbox + LOD-Stufe
  ├─ geometry.py          Vektor laden, pro Zoom clippen/vereinfachen
  ├─ basemap.py           Natural-Earth-Substrat (später OSM-Quelle steckbar)
  └─ layers/              Overlay-Registry (analog core/graphs.py)
        political.py      jeder Layer = reiner Provider:
        economic.py         "gib Features für diese bbox + diesen Zoom
        climate.py           (+ optional: zu diesem Zeitpunkt / dieser Tiefe)"
        terrain.py        Höhe/Relief (DEM → Hillshade/Höhenfarbe)
        subsurface.py     Untergrund (Höhlen/Tunnel; optional Tiefen-Level)

/api/map/...              ← EIN HTTP-Kontrakt, den ALLE Fronten pollen
  GET /api/map/base   ?bbox&zoom            → Grundkarten-Features (schon vereinfacht)
  GET /api/map/layers                       → Registry: welche Overlays, je mit
                                              Meta (hat Zeitachse? min/max-Zeit?
                                              Zukunft vorhanden?)
  GET /api/map/layer/<id> ?bbox&zoom&at     → Features eines Overlays; `at`=Zeit-
                                              punkt (Achse 3), ohne `at` = „jetzt".
                                              Layer ohne Zeitachse ignorieren `at`.
  (später ggf. slippy /api/map/tile/<layer>/<z>/<x>/<y>)

Renderer (pro Front, BEWUSST DUMM):
  ├─ tui/      curses-ASCII-Grid       ← Schritt 1 gebaut & getestet (Notnagel-Look)
  ├─ native    pygame-Fenster          ← scripts/map_window.py, der „Wow"-Front:
  │                                       antialiased Vektor, Meer-Verlauf, Pan/Zoom.
  │                                       Klappt aus der TUI auf (`w`), wie /slide→zathura.
  ├─ laptop    SVG/Canvas              ← später nachgezogen
  └─ monolith  SVG/Canvas (ggf. ins bestehende #core-Exhibit „welt")
```

Das **native Fenster** liest derzeit `core/map/` direkt (eigenständig laufbar,
Sandkasten-Stil wie der Prototyp) statt über `/api/map` — bewusst, fürs schnelle
Look-Iterieren. Wenn der Look steht, kann es genauso auf den `/api/map`-Kontrakt
umgestellt werden wie die anderen Fronten (dann echter dummer Renderer).

**Renderer bleiben dumm:** sie bekommen bereits-projizierte Features für den
aktuellen Viewport und *zeichnen nur*. Alles Harte (Projektion, LOD,
Layer-Logik) liegt **einmal** in `core/map/`. Eine neue Front = nur ein neuer
Zeichner gegen denselben `/api/map`-Kontrakt.

**Backend bleibt zustandslos** (wie der Rest von ZENTRALE): der Viewport-State
(center + zoom + aktive Layer + gewählter Zeitpunkt auf Achse 3) lebt pro Front
im Client; das Backend beantwortet nur „Features für diesen Viewport (zu diesem
Zeitpunkt)". Passt zum Polling-Modell.

### Koordinaten / Projektion

- Speicherung in **WGS84 lon/lat** (Standard für GeoJSON, was Natural Earth
  und OSM liefern).
- Darstellung in **Web-Mercator (EPSG:3857)** mit **slippy-map z/x/y**-Schema
  — dasselbe, was Google/OSM nutzen. Damit ist die spätere Navi-Semantik
  (Kacheln, Zoomstufen) schon richtig verankert.
- **Bekannter Mercator-Trade-off (Flächenverzerrung):** Mercator ist winkeltreu,
  aber NICHT flächentreu — es bläht polnahe Flächen auf (Grönland/Sibirien/Kanada
  wirken riesig), Äquator-Landmassen wie **Afrika wirken relativ zu klein**
  (real ~30 Mio km², ~14× Grönland). Für eine **zoombare Navi-Karte** ist das
  korrekt und gewollt (deshalb nutzt es jeder). Für eine **thematische
  Welt-Übersicht** (Politik/Wirtschaft, wo echte Flächen zählen) ist eine
  **flächentreue Projektion** besser. → **Geplant:** umschaltbarer
  **„True-Size"-Weltmodus** (z.B. *Equal Earth*) als alternative Projektion.
  Mercator bleibt Default; Equal Earth ist eine reine Projektions-Variante in
  `core/map/projection.py` (kein Daten-Eingriff). Greift bei Zoom 0–2 / Welt-
  Übersicht, nicht beim Reinzoomen. Noch nicht gebaut — Notiz für Achse 1/2.
- **Vektor, nicht Raster.** Erzwungen durch die TUI: ASCII rastert man zur
  Laufzeit aus Vektorgeometrie auf ein Zeichen-Grid. Raster-Kacheln (fertige
  Bilder) gingen in curses gar nicht und wären riesig. Vektor skaliert sauber
  zu ASCII *und* SVG aus derselben Quelle.

## Bau-Reihenfolge (Roadmap)

Sasha begleitet jeden Schritt und gibt die Details vor.

1. **Grobe Base-Map in der TUI** — ✅ **erledigt** (Details unten). Nur
   Grundkarte (Küsten), noch keine Overlays.
2. **Politischer Layer** (erster Overlay) — Konflikte, Grenzen,
   Truppenbewegungen. Datenquelle/Details kommen von Sasha.
3. **Wirtschaftlicher Layer**.
4. **Klima-Layer**.
5. **Höhen-/Relief-Layer (`terrain`)** — DEM (SRTM/ETOPO) → Hillshade/Höhenfarbe.
6. **Untergrund-Layer (`subsurface`)** — Höhlen/Tunnel; bringt den optionalen
   Tiefen-/Level-Wähler mit (s. „Tiefen-Dimension" oben).
7. **Nachziehen in Laptop + Monolith** (SVG/Canvas-Renderer gegen denselben
   `/api/map`-Kontrakt).
8. **Später:** OSM-Detail bei tiefem Zoom + Navigations-/Routing-Layer.

> Reihenfolge 3–6 ist nicht in Stein — Sasha gibt pro Layer die Details vor und
> kann die Folge umstellen. `terrain`/`subsurface` sind hier als Plan vermerkt,
> noch nicht terminiert.

## Schritt 1 — Implementierung (was real existiert)

**Engine (`core/map/`, pure stdlib — nur `json` + `math`):**
- `projection.py` — Web-Mercator normalisiert auf [0,1]² (`lonlat_to_world`,
  `world_to_lonlat`, `MAX_LAT=85.05°`). Die Mercator-Mathematik liegt damit
  EINMAL hier; die Fronten machen nur noch eine lineare Welt→Zelle-Abbildung.
- `basemap.py` — lädt die Vektordaten und cacht sie **vorprojiziert** (jeder
  Punkt einmal nach Welt-Koord., plus Bounding-Box pro Linie fürs Clipping).
- `render.py` — `base_features(cx, cy, zoom, cols, rows, aspect)`: rechnet den
  Sicht-Ausschnitt, clippt Linien per Bounding-Box, projiziert die Punkte aufs
  Zellraster und vereinfacht (aufeinanderfolgende Punkte derselben Zelle
  zusammenfassen). Gibt `{center, zoom, bounds:[w,s,e,n], cols, rows, lines}`.
- `data/ne_110m_coastline.geojson` — Küstenlinien 1:110m (Natural Earth,
  gemeinfrei, 137 KB, 134 Linien / ~5k Punkte). Liegt unter `core/map/data/`,
  also **außerhalb** des `data/*.json`-gitignore → wird committet (statische
  Offline-Referenz, kein generierter Inhalt). `ne_110m_admin_0_countries.geojson`
  liegt schon bereit als Grenzen-Quelle für den **politischen** Layer (Schritt 2).

**API (`ui/app.py`):** `GET /api/map/base?cx&cy&zoom&cols&rows&aspect` →
`map_base_features(...)`. **Nicht** KI-gegatet (Karte gibt es in allen
Kassetten). `aspect` = Zellbreite/Höhe: TUI schickt `0.5` (Zeichen ~doppelt so
hoch wie breit), ein Browser-Front später `1.0`.

**TUI-Renderer (`tui/zentrale_tui.py`, Taste `m`):** füllt die MITTE-Box mit
der Karte (analog zum Graph-Werkzeug `g`). Die TUI ist **reiner Zeichner** —
sie hält nur den Viewport (`M = {cx, cy, zoom, data, grid}`), holt die Linien
synchron über `/api/map/base` (bei Öffnen/Pan/Zoom/Resize) und rastert sie per
Bresenham (Glyph `▓`, Farbe `acc`, Fadenkreuz `+` in der Mitte). **Keine
Projektion in der TUI** — Pan-Schrittweite kommt aus den `bounds` der letzten
Antwort. Bei totem Backend: Fehler-Marker statt Dauer-Refetch (kein UI-Freeze).
Steuerung: `↑↓←→`/`hjkl` pan, `+`/`−` zoom, `0` reset, `esc`/`m` zu. Modal wie
das Graph-Werkzeug (`q` beendet erst nach `esc`).

> Verifiziert end-to-end via tmux (Welt + Reinzoomen rendern korrekt, sauberer
> Quit, keine Fehler) — nicht nur Unit-getestet.

## Geparkte / offene Entscheidungen

- **Konflikt-/Overlay-Datenquelle offline:** woher kommen die politischen
  Daten (Konflikte, Frontverläufe) im offline-Betrieb? Pro Layer mit Sasha
  klären (Schritt 2+). Liveuamap selbst ist online — eigene Quelle/Format
  nötig.
- **OSM-Integration:** Format (PBF/GeoJSON), wie viel Region vorhalten, wie
  bei tiefem Zoom einspeisen. Erst relevant ab dem OSM-/Navi-Schritt.
- **Slippy-Tile-Endpoint** (`/api/map/tile/...`) vs. bbox-Query: bbox reicht
  für den Start; Tiles erst wenn Caching/OSM es verlangt.
- **Zeit-Daten (Achse 3):** woher die historischen Scheiben kommen (Politik:
  historische Grenzen/Frontverläufe; Klima: Historie) und welches
  **Klima-Vorhersagemodell** wir für die Zukunft anzapfen — pro Layer mit Sasha
  klären. Politik-Zukunft ist bewusst geparkt.
- **Höhen-Daten (`terrain`):** welches **DEM** (SRTM 90m/30m, ETOPO, GMTED) und
  in welcher Auflösung offline vorhalten — DEMs sind groß; evtl. grobe Stufe
  global + feine Stufe nur für Regionen. Darstellung in der TUI: Höhe →
  Truecolor-Verlauf/Hillshade (kein Konturlinien-Gewirr).
- **Untergrund-Daten + Tiefen-Dimension (`subsurface`):** OSM deckt Tunnel/
  Höhleneingänge/`level` ab, aber selten den *Verlauf* unter Tage; ob
  spezialisierte Höhlen-/Bergwerks-Datensätze rein sollen — offen. Plus die
  Grundsatzfrage, ob die Tiefen-Ebene Layer-Eigenschaft bleibt oder zur
  **Achse 4** wird (s. „Tiefen-Dimension" oben).
