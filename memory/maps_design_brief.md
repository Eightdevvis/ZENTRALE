# Maps — Design-Brief (Handoff für eine Look-/Render-Überarbeitung)

> **Zweck:** Alles, was jemand braucht, um den **visuellen Look** der ZENTRALE-
> Karte zu verbessern — ohne sich in falschen Annahmen zu verrennen. Architektur/
> Plan stehen in `maps_system.md`; HIER stehen Ziel, Medium-Grenzen, was schon
> probiert wurde und der Sandkasten zum Iterieren.

## Ziel

Eine interaktive Karte, die **gut aussieht** — aktuell im **Terminal (curses-TUI)**,
später auch in Browser-Fronten. Der erste Wurf (gefüllte Kontinente in Farbe,
Halbblock) wird vom Auftraggeber noch als „sieht kacke aus" bewertet — es braucht
ein echtes Gestalter-Auge (Palette, Kontrast, Anti-Aliasing, Beschriftung,
Rahmung, Balance Küstenlinie vs. Fläche).

## HARTE Medium-Grenzen (zuerst lesen — sonst verrennt man sich)

Zielterminal ist real **xfce4-terminal auf VTE 0.76**, `TERM=xterm-256color`,
`COLORTERM=truecolor`.

- **KEINE Pixel-Bildprotokolle.** Sixel und das Kitty-Graphics-Protokoll werden
  von VTE 0.76 **nicht** unterstützt. Also **keine** inline-PNGs/Bitmaps im
  Terminal. (Genau deshalb öffnet das `/slide`-Feature der TUI PDFs extern in
  zathura statt inline.) Alles muss aus **Zeichen** gebaut werden.
- **Verfügbar im Zeichen-Gitter:**
  - **Truecolor (24-bit)** — ja, voll. Größter Hebel für „sieht gut aus"
    (Land/Meer/Höhen-Verläufe, Anti-Aliasing über Zwischentöne).
  - **256-Farben** als Fallback (curses nutzt color pairs).
  - **Braille** `⠿` (U+2800–28FF): 2×4 = **8 Subpixel/Zelle** — das ist die
    **Auflösungs-Decke** im Zeichen-Gitter. Ideal für feine **Linien** (Küsten,
    Grenzen, Routen). Eine Farbe pro Zelle.
  - **Halbblöcke** `▀▄█`: 2 Subpixel/Zelle, aber **fg+bg getrennt einfärbbar**
    → satte **Farbflächen** UND behebt das 2:1-Verzerrungsproblem (Terminalzelle
    ist ~doppelt so hoch wie breit). Ideal für **gefüllte** Flächen (Land/Meer).
  - Quadranten (2×2), Sextanten (2×3), Box-/Block-Zeichen `░▒▓█` ebenfalls da.
  - **Oktanten** (2×4 solid, Unicode 16/2025) wären für Füllung schöner als
    Braille — aber **Font-Support fehlt** auf dem System. Nicht nutzbar.
- **Mehr Detail = mehr Zellen** (kleinere Schrift / größeres Fenster). Auflösung
  = Zellen × Subpixel. So holt **`mapscii`** seine Schärfe — `mapscii` ist die
  realistische **Qualitäts-Decke** im Terminal (zoombare OSM-Karte in Braille +
  Farbe; lohnt sich als Referenz anzuschauen).
- **Faustregel:** **Braille für Linien, Halbblock für Flächen, Truecolor für
  beides.** Braille-*Füllung* wirkt körnig (Punktlücken) — nicht für Flächen.

## Was schon probiert wurde (alle als „kacke" bewertet)

Im Prototyp als Stile A–D abrufbar:
- **A baseline** — dünner Umriss, 1 Glyph/Zelle (`▓`). Pixelsuppe.
- **B halfblock** — gefüllte Kontinente, Halbblock, + Truecolor (Land grün/Meer
  blau/Küste hell). Der bisher beste, aber noch nicht „schön".
- **C braille** — Küsten-Umriss in Braille. Feine Linien.
- **D braille-fill** — gefülltes Land in Braille. Körnig.

Offene Gestaltungs-Fragen, an denen es vermutlich hängt: Farbpalette (zu
grell/zu matt?), fehlende **Beschriftung** (Ländernamen/Städte), kein
**Hillshade/Tiefe**, harte Kanten (kein Anti-Aliasing über Zwischentöne),
Rahmung/Legende, evtl. zu niedrige Auflösung (Fenster/Schrift).

## Sandkasten zum Iterieren (DAS Arbeits-File)

**`scripts/map_render_proto.py`** — laufbar, pure stdlib, druckt nach stdout
(echte Farbe nur im Terminal). Hier Glyphen/Palette/Füllung/Stile ändern und
sofort sehen. Nutzt die echte Projektion (`core/map/projection.py`), also
1:1 wie die spätere TUI.

```bash
venv/bin/python scripts/map_render_proto.py --style halfblock --color
venv/bin/python scripts/map_render_proto.py --style halfblock --color --cols 120 --rows 50
venv/bin/python scripts/map_render_proto.py --style braille --color --cx 10 --cy 50 --zoom 3
venv/bin/python scripts/map_render_proto.py            # alle vier Stile
```
Flags: `--style {all,baseline,halfblock,braille,braille-fill}`, `--cx/--cy/--zoom`,
`--cols/--rows`, `--color`.

## Daten & Engine (Hintergrund)

- Geometrie: **Natural Earth 1:110m** (gemeinfrei) unter `core/map/data/` —
  `ne_110m_coastline.geojson` (Küstenlinien) + `ne_110m_admin_0_countries.geojson`
  (Land-Polygone, für Füllung).
- Engine `core/map/`: `projection.py` (Web-Mercator → [0,1]²), `basemap.py`
  (lädt + cacht vorprojiziert), `render.py` (Viewport → projizierte Features).
- **Architektur-Regel:** der echte TUI-Renderer bleibt „dumm" (holt fertige
  Daten über `/api/map/...`, zeichnet nur). Für reines **Look-Experimentieren**
  ist aber der Prototyp der Sandkasten — dort ohne Backend frei spielen.

## Wichtig: es gibt DREI Render-Ziele (nicht nur das Terminal)

Dieselbe Karte (gleiche `core/map`-Engine, gleicher `/api/map`-Kontrakt) kann in
verschiedenen Fronten leben — der Renderer ist „dumm", nur das Zeichnen ändert
sich. Drei Ziele mit sehr unterschiedlichem Look-Spielraum:

1. **TUI (curses-Terminal)** — die Grenzen oben. Schlank, charmant-reduziert.
2. **Natives GUI-Fenster** (kein curses, KEIN Browser) — **das ist der
   eigentliche „Wow"-Ort ohne Browser-Bloat.** Ein zweites Fenster über ein
   Python-GUI-Toolkit: echte **antialiased Vektorgrafik**, gefüllte Farbflächen,
   Verläufe/Hillshade, flüssiges Pan/Zoom, Labels — alles, was im Terminal nicht
   geht. RAM: ~20–80 MB (vs. Browser 300–600 MB), passt also zum Lean-Motiv der
   TUI. Precedent im Projekt: `/slide` öffnet schon ein **separates Fenster**
   (zathura) für PDFs — ein Karten-Fenster kann genauso aus der TUI heraus
   gestartet werden (Tastendruck → Fenster auf).
   - **Display ist da** (`DISPLAY=:0.0`, X11), aber **kein Toolkit installiert**.
     Optionen: **pygame** (leicht, glatt, einfaches Pan/Zoom — pragmatischer
     Sweet Spot), **PySide6/Qt** (maximale Politur, GPU, mehr Code/Dep),
     **tkinter** (fast dep-frei, braucht System-Paket `python3-tk`, Look „ok"
     statt „wow"), oder GPU-Wege (pyglet/moderngl/raylib).
3. **Browser-Fronten** (laptop/monolith) — echtes Canvas/SVG/WebGL, volle
   Freiheit, aber eben Browser (RAM-schwer).

→ Ein Gestalter sollte alle drei kennen. Wahrscheinlich beste Aufteilung:
**Wow-Design im nativen Fenster (oder Browser), TUI bleibt die reduzierte
Variante.** Nicht am Terminal-Limit abarbeiten, wenn das Schaufenster woanders
sein kann.

## Was man dem Design-Claude gibt

1. **dieses File** (`memory/maps_design_brief.md`) — Ziel + Grenzen + Stand.
2. **`scripts/map_render_proto.py`** — der Sandkasten zum Iterieren.
3. Optional tiefer Kontext: **`memory/maps_system.md`** (3-Achsen-Architektur).
