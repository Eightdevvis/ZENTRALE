# Der Pixelstil der TUI

Stand 2026-10-07. Sasha: „du kannst generell irgendwo nen kleines vermerk über
diesen stil machen den wir haben und bissl auch zusammengebastelt haben."
Was ihn ausmacht, wo der Code liegt und wie ein neues Symbol gebaut wird.

## Was ihn ausmacht

- **Pixel aus Zeichen.** Ein Terminal-Feld kann genau zwei Farben
  (Vorder- und Hintergrund). Gemalt wird in **Feinpixeln** — 2×6 je Feld für
  große Bilder, 2×3 (Sextant) für kleine — und je Feld das Zeichen gewählt,
  das die Pixel am treuesten trifft: Halbblock `▀`, Viertel `▚`, Sextant
  `🬗`. VTE (xfce4-terminal) zeichnet alle drei pixelgenau selbst.
- **Kantig, wenige Farben.** Keine Verläufe über viele Stufen: Farben werden
  gerastert (Bayer-Matrix im Auge, 3–5 Helligkeitsstufen in Leiste und
  Denk-Adern). Lieber eine Stufe weniger als Matsch.
- **Paletten Tag/Nacht.** Jedes Motiv hat eine Nacht- und eine Tag-Fassung
  (Schwarz bzw. Weiß als Grund). Auf Weiß leuchtet nichts: dort wird ein
  Glimmen dunkler statt heller (Auge, Denk-Adern), und nichts wird blasser
  als lesbar (E-Ink-Regel aus Sashas Gedächtnis: nie unter 4,5:1 für Schrift).
- **Motive.** Der **Bernstein** im Treppenschliff (Fokus-Leiste, Vorlage ein
  16×16-PNG), die **App-Symbole** des Rads (Brief, Globus, Kalenderblatt,
  Klaviatur, Notizblock, Balken, Zielscheibe, Sprechblase) mit eigener
  Fünf-Farben-Palette je App, die **Elektronik** (ein Kern mit Zacken), das
  **Auge** der KI (grüne Iris, schweres Lid, durchscheinend), seit 07.10.
  die **Denk-Adern** (Spiralen aus dem Kern, in den Farben des Auges).
- **Glimmen.** Was lebt, glimmt: der zuletzt abgehakte Stein glüht nach
  (`EMBER`), die Iris pulst beim Denken, eine Helligkeitswelle läuft die
  Adern entlang. Ruhig, nie hektisch — Animation in groben Zeitrastern,
  damit Bilder aus dem Zwischenspeicher kommen (Akku).
- **Durchscheinend.** Ränder lösen sich gerastert in den Grund auf (Auge:
  `setze` mit Bayer-Schwelle) statt hart abzubrechen.

## Wo der Code liegt

| Was | Wo |
|---|---|
| Feinpixel → Zeichen: `zelle`, `zellen`, `sextant`, `mix`; 24-Bit/256-Farben: `rgb_256`, `xterm_rgb` | `tui/pixel.py` |
| Bernstein: `gem`, `bernstein_zellen` (Fokus-Leiste) | `tui/pixel.py`, benutzt in `tui/ansichten/fokus.py` |
| App-Symbole: `SYM_FARBEN`, `MOTIVE` (`_m_post` …), `symbol_pixel`, `symbol_zellen`, `symbol_pille` | `tui/pixel.py`, benutzt in `tui/ansichten/startseite.py` |
| Elektronik: `elektronik_pixel`, `elektronik_zellen` | `tui/pixel.py` |
| Auge: `AUGE_FARBEN`, `auge_zustand`, `auge_zellen` | `tui/pixel.py`, benutzt in `tui/ansichten/chat.py` |
| Denk-Adern: `adern_zellen(t, dauer, breite, hoehe, thema, ausklang)` | `tui/ansichten/denkadern.py` |
| Symbole der Chat-Seitenleiste (4×2 Felder = 8×6 Pixel, oder ein Zeichen; Einstellung `tui_symbole`): `BILDER`, `ZEICHEN`, `symbol_zellen`, `art` | `tui/ansichten/symbole.py` |
| Farbpaare anlegen (begrenztes Budget, 24 Bit wenn möglich): `Kontext.pix_attr`, `pix_farbe`; Modus `ZENTRALE_PIXEL=half` für Terminals ohne Sextanten | `tui/ansichten/kontext.py` |

Alle Pixel-Funktionen sind **curses-frei**: sie liefern Zellen
`(zeichen, fg_rgb, bg_rgb)`, die Ansicht setzt sie mit
`safe_addstr(y, x, zeichen, z.pix_attr(fg, bg))`. Testbar ohne Bildschirm
(`tests/test_tui_pixel.py`, `tests/test_denkadern.py`).

## Regeln für neue Symbole

0. **Pixel-Symbole nie kleiner als 2 Zeilen hoch** (seit 2026-10-08).
   Sasha zu den 3×1-Symbolen der Seitenleiste: „man erkennt gar nichts" —
   in 3 Pixel Höhe passt keine Form, Lupe, Ordner und Blatt sahen gleich
   aus. Wo nur eine Zeile Platz ist (eine Listenzeile), nimmt man ein klares
   Unicode-Zeichen statt eines Pixel-Symbols.
1. **Erst die Größe, dann das Raster.** Groß (Rad, Auge): 2×6 Feinpixel je
   Feld, `pixel.zellen`. Klein (2 Zeilen, z. B. 4×2 Felder = 8×6 Pixel):
   2×3 je Feld direkt als Sextant setzen (`symbole.symbol_zellen`), eine
   Farbe je Feld — Akzent-Teile deshalb auf Feldgrenzen legen. Die unterste
   Pixelzeile leer lassen, dann stoßen untereinander stehende Symbole nicht
   aneinander.
2. **Ein Feinpixel ist nicht quadratisch** (Sextant ~4,5×6, Feinpixel 2×6
   ~4,5×3). Kreise vorher strecken (`pixel.AY`, `denkadern.HOCH`).
3. **Zwei Farben je Symbol** reichen meist (Grund + Akzent); große Motive
   bekommen eine Palette aus fünf (`_pal`: core, edge, glow, akzent, dunkel).
4. **Tag und Nacht** immer beide, Tag dunkler statt heller.
5. **Reine Funktion mit Cache** (`lru_cache`), Zeit grob rastern. Ein Bild
   pro Tastendruck neu zu rechnen kostet Akku.
6. **Ansehen, nicht raten:** Zellen als PNG malen (Pillow, je Feld die
   Sextant-Bits als Rechtecke) und anschauen, bevor es in die TUI geht. Ohne
   Pillow geht es auch mit `zlib` + `struct` (eine PNG-Datei ist kurz). Am
   08.10. so je Symbol 3–6 Entwürfe verglichen (Zahnrad: gerade Zähne allein
   sahen aus wie #, in 5 Zeilen wie ein Käfer).
7. **Zeichen statt Pixel** (Art `zeichen`): nur Glyphen, die DejaVu Sans
   Mono (Monospace in xfce4-terminal) hat und die einspaltig sind —
   East-Asian-Width N oder A, nie W/F (kein ＋, keine Emoji). Prüfen mit
   `unicodedata.east_asian_width` und fontconfig.
