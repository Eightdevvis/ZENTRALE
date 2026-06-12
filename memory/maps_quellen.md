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

**Begründung:** IMF-Terms erlauben *Anzeige mit Namensnennung*, aber keine
*Weiterverteilung*. Ein lokaler Cache ≠ Weiterverteilung (wie ein Browser-Cache).
Indem PortWatch-Daten nie ins Repo wandern, greift die heikle Klausel gar nicht.
**Vorbehalt:** würde ZENTRALE je öffentlich/kommerziell, braucht das einen echten
Lizenz-Check.

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

### Geprüfte, noch NICHT gebaute Quellen (für nächste Sub-Layer)
- **`trade/routes` (Routengeometrie):** PortWatch `Global_Shipping_Routes/
  FeatureServer/**15**` (Polyline! Layer 0 ist leer) — echte Schiffsrouten-Linien,
  selbe Quelle/Lizenz wie oben.
- **`trade/ports` (Hafen-Aktivität):** PortWatch `PortWatch_ports_database` +
  `Daily_Ports_Data` (5,6 Mio Zeilen, Join per `portid`), täglich.
- **`trade/disruptions`:** PortWatch `portwatch_disruptions_database` (Rotes
  Meer, Kanalsperren) — eher Richtung News/Politik-Layer.
- **Routendichte (EU-amtlich):** EMODnet Human Activities, Vessel Density (CC-BY,
  monatlich/jährlich, AIS-abgeleitet).
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
