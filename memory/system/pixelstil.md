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
  Klaviatur, Notizblock, Balken, Zielscheibe, Sprechblase, seit 2026-10-09 Pinnwand mit Schnur für desk) mit eigener
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
| Symbole der Chat-Seitenleiste (Braille, 4×2 Felder = 8×8 Punkte): `BILDER`, `codieren`, `symbol_zellen` | `tui/ansichten/symbole.py` |
| Probe-Bild wie im Terminal (Sextanten als Blöcke, Braille aus der Ersatzschrift): `python3 scripts/icon_probe.py ZIEL` | `scripts/icon_probe.py` |
| Farbpaare anlegen (begrenztes Budget, 24 Bit wenn möglich): `Kontext.pix_attr`, `pix_farbe`; Modus `ZENTRALE_PIXEL=half` für Terminals ohne Sextanten | `tui/ansichten/kontext.py` |

Alle Pixel-Funktionen sind **curses-frei**: sie liefern Zellen
`(zeichen, fg_rgb, bg_rgb)`, die Ansicht setzt sie mit
`safe_addstr(y, x, zeichen, z.pix_attr(fg, bg))`. Testbar ohne Bildschirm
(`tests/test_tui_pixel.py`, `tests/test_denkadern.py`).

## Regeln für neue Symbole

0. **Icons der Seitenleiste: Braille, 4 Felder × 2 Zeilen = 8×8 Punkte**
   (seit 2026-10-08). Erst waren es Sextanten 3×1 („man erkennt gar
   nichts"), dann Sextanten 4×2 — erkennbar, aber grob: **VTE zeichnet
   Sextanten selbst als volle Blöcke**, kleine Formen wirken „dickflüssig".
   **Braille** hat DejaVu Sans Mono nicht; es kommt aus der Ersatzschrift
   DejaVu Sans als feine runde Punkte mit Luft dazwischen — filigran, passt
   zu Sashas „klein und filigran". Sasha hat am 08.10. alle Varianten als
   Bild verglichen und Braille 4×2 gewählt. Wo nur eine Zeile Platz ist
   (Listenzeile), ein klares einspaltiges Unicode-Zeichen (`symbole.DOKU` ▤).
1. **Erst die Größe, dann das Raster.** Flächige Motive (Rad, Auge,
   Bernstein): Sextanten bzw. 2×6 Feinpixel je Feld (`pixel.zellen`) — da
   sind die vollen Blöcke gewollt. Linien-Icons: Braille, 2×4 Punkte je Feld
   (`symbole.codieren`), eine Farbe je Feld — Akzent-Teile deshalb auf
   Feldgrenzen legen (Spalten 0-1, 2-3, …; Zeilen 0-3, 4-7). Die unterste
   Punktreihe meist leer lassen, dann stoßen untereinander stehende Symbole
   nicht aneinander.
2. **Ein Feinpixel ist nicht quadratisch** (Sextant ~4,5×6, Feinpixel 2×6
   ~4,5×3). Kreise vorher strecken (`pixel.AY`, `denkadern.HOCH`).
3. **Zwei Farben je Symbol** reichen meist (Grund + Akzent); große Motive
   bekommen eine Palette aus fünf (`_pal`: core, edge, glow, akzent, dunkel).
4. **Tag und Nacht** immer beide, Tag dunkler statt heller.
5. **Reine Funktion mit Cache** (`lru_cache`), Zeit grob rastern. Ein Bild
   pro Tastendruck neu zu rechnen kostet Akku.
6. **Ansehen, nicht raten — aber mit der richtigen Zeichnung.** Icons nur mit
   einem Bild prüfen, das die Ersatzschriften nachbildet:
   `python3 scripts/icon_probe.py ZIEL` (System-Python mit Pillow) malt die
   echten Raster aus `symbole.py` so, wie xfce4-terminal sie zeigt —
   Sextanten als Rechtecke, Braille aus DejaVu Sans. Ein Bild, das alles mit
   einer Schrift malt, lügt. Am 08.10. so je Symbol mehrere Entwürfe
   verglichen (Zahnrad: vier Fassungen, Sasha nahm „z3"; Leiste auf/zu: eine
   2 Punkte breite Spalte war zu schwer, eine dünne passt zu den Linien).
7. **Einzelne Zeichen** (Listenzeile, `DOKU`): nur Glyphen, die einspaltig
   sind — East-Asian-Width N oder A, nie W/F (kein ＋, keine Emoji). Prüfen
   mit `unicodedata.east_asian_width` und fontconfig. Ohne 256 Farben oder
   mit `ZENTRALE_PIXEL=half` zeichnet die Leiste dieselben Braille-Punkte in
   der Schriftfarbe — Braille kann praktisch jedes Terminal.
