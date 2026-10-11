# Farbwähler und Stylebox — zwei Bausteine für jede Ansicht

Stand 2026-10-11 (Farbkreis repariert: Cursor, Zoom, 24 Bit, rund). Sasha wollte einen Farbwähler als Regenbogen-Kreis mit
einem kleinen Kreis darin, den man mit den Pfeilen verschiebt und mit + / −
heranzoomt, und eine „Stylebox", in der man das Aussehen eines Objekts
einstellt — für alle Apps, nicht nur den Kalender. Beide sind Bausteine
(`tui/bausteine/`, Regeln in [tui_bauplan.md](tui_bauplan.md) „Bausteine"):
sie kennen keinen Aufrufer, speichern nichts und fragen kein Backend.
Eingehängt seit 10.10.2026 im Kalender, seit 11.10. im Fenster „advanced" des Terminformulars
([kalender_ansichten_vorschau.md](../werkzeuge/kalender_ansichten_vorschau.md)); das
Angebot für einen Kasten steht als `stil.KASTEN` in `core/stil.py` (dort auch
`als_css`/`aus_css`, `anwenden` und die CSS3-Farbnamen für iCalendar COLOR).

| Was | Wo |
|---|---|
| Farbwähler | `tui/bausteine/farbwaehler.py` |
| 24-Bit-Flächen nach curses' refresh (Farbwähler) | `tui/echtfarbe.py`, eingehängt über `Kontext.echt_malen`/`nachmalen` |
| Zellform (Höhe/Breite) aus dem Terminal | `pixel.zell_seiten()`, `pixel.zell_ay()` |
| Stylebox | `tui/bausteine/stylebox.py` |
| CSS-Wörter, Schema, Prüfung, Hex | `core/stil.py` (Schicht 1, Tür `tui/` in [bauplan_kern.md](bauplan_kern.md)) |
| Ausprobieren ohne Backend | `venv/bin/python scripts/stil_probe.py` (`--tag` für Tag-Theme): f = Farbwähler, s = Stylebox, q = Ende |
| Tests | `tests/test_farbe_stil.py` |

## Aus einer Ansicht aufrufen

Beide sind Modale mit demselben Muster: Objekt bauen, Tasten durchreichen,
solange es offen ist, jedes Bild zeichnen.

```python
from tui.bausteine.farbwaehler import Farbwaehler   # als Skript: from bausteine.farbwaehler …
from tui.bausteine.stylebox import Stylebox
import stil                                          # core/stil.py

self.modal = Stylebox(termin_stil,                  # dict CSS-Name → Wert
                      ["border-style", "border-color", "background-color",
                       "color", "--zentrale-muster", "background-image"],
                      titel="termin", text="Uni 08:30")
# in taste(ch):
erg = self.modal.taste(ch)          # None | ("fertig", änderung) | ("abbruch",)
if erg and erg[0] == "fertig":
    termin_stil = stil.anwenden(termin_stil, erg[1])   # None = entfernen; speichern tut die Ansicht
if erg:
    self.modal = None
# in draw_*:
y, x, h, w = self.modal.mittig(H, W, 22, 70)        # oder eigene Stelle
self.modal.zeichne(self.z, y, x, h, w)
```

- `Farbwaehler(start="#rrggbb" | None)`; `taste(ch)` → None |
  `("fertig", "#rrggbb")` | `("abbruch",)`; `hex`, `rgb`, `zeichne(z, y, x, h, w)`,
  `mittig(H, W, h, w)`, `tasten()` (für eine Fußzeile).
- `Stylebox(stil, optionen, titel="stil", text="Beispiel")`; `taste(ch)` →
  None | `("fertig", änderung)` | `("abbruch",)`; danach `ergebnis` (dict, bei
  Abbruch None). Die Änderung anwenden mit **`stil.anwenden(alt, änderung)`**,
  nicht mit `dict.update` (das schriebe None hinein). `zeilen()` und `vorschau(b, h)` sind rein (Tests, andere
  Zeichner). Ist der Farbwähler offen, zeichnet `zeichne` ihn an derselben
  Stelle, und `tasten()` liefert seine Tasten.
- `z` ist der Kontext der TUI (`tui/ansichten/kontext.py`): gebraucht werden
  `C`, `PIX`, `pix_attr`, `pix_farbe`, `safe_addstr`, `draw_box`, `has_color`.
- Das Modal deckt sein Rechteck ab (wischt es leer) und zeichnet Rahmen und
  Titel selbst.

## Farbwähler

- **Farbraum HSV**: Winkel = Farbton (0° Rot rechts, gegen den
  Uhrzeigersinn: 90° Gelbgrün oben, 180° Cyan links, 270° Blau-Violett unten),
  Abstand zur Mitte = Sättigung (Mitte weiß), Helligkeit als Regler rechts.
  HSV statt HSL, weil der HSL-Kreis bei voller Helligkeit nur weiß wäre.
- **Cursor** (seit 11.10.2026): Zustand ist HSV (Farbton, Sättigung,
  Helligkeit), jeder Pfeil schiebt um **genau ein Feld** des gerade
  gezeigten Bildes (auf die Mitte des Nachbarfeldes), bei jedem Zoom. Vorher
  war der Schritt 1/12 Radius = 1,4 Spalten bzw. 0,7 Zeilen — senkrecht
  bewegte jeder dritte Druck nichts. Kreis-Felder sind immer ungerade
  breit/hoch, damit die Kreismitte (weiß) genau ein Feld ist.
- **Zoom** 1×, 2×, 4×, 8×, 16× (`ZOOM`): `+` legt den Ausschnitt mit dem
  Cursor in die Mitte (eigener Zustand `blick`), danach **steht** der
  Ausschnitt; erst wenn der Cursor `RAND` = 2 Felder an den Rand kommt,
  rückt er um ganze Felder nach (vorher war er stets um den Cursor
  zentriert, jeder Druck schob das ganze Bild). Helligkeits-Schritt 5 % bei
  1×, geteilt durch den Zoom.
- **Zwei Farbwege** — welcher gilt, entscheidet der Kontext:
  - **24 Bit** (`tui/echtfarbe.py`): curses zeichnet an Kreis, Regler und
    Farbfeld nur einen gleichbleibenden Platzhalter (Leerzeichen im
    Theme-Grund); nach `stdscr.refresh()` schreibt `Kontext.nachmalen()` die
    Flächen selbst mit `38;2`/`48;2`-SGR. Je Feld ein Halbblock `▀` mit zwei
    exakten Farben (`rad_echt`, Halbpixel ≈ quadratisch, Rand weich in den
    Grund), keine Rasterung, keine Farbpaare. Weil der Platzhalter gleich
    bleibt, fasst curses die Zellen nicht an (kein Flackern); verschwindet
    die Fläche oder wandert sie, malt `redrawln` die Zeilen neu (keine
    Geisterbilder). Unverändert wird nur alle 2 s neu geschrieben. Die TUI
    selbst bleibt bei 256 Farben (`TERM=xterm-direct` würde die Theme-Farben
    als RGB lesen — alles blau).
    **Einstellung `farbe_truecolor`**: `auto` | `an` | `aus` aus
    `ZENTRALE_FARBE_TRUECOLOR` oder der Datei `~/.config/zentrale/farbe_truecolor`
    (ein Wort, wie `theme`). `auto` = an, wenn `COLORTERM` `truecolor`/`24bit`
    sagt (VTE setzt das; tmux reicht 24 Bit mit `terminal-features *:RGB` durch).
  - **256 Farben** (Ersatz): wie bisher über curses-Paare — EINE Farbe je
    Feld, am Rand ein Sextant (`ZENTRALE_PIXEL=half`: Halbblock), gerastert
    **relativ zum Ausschnitt** (`STUFEN`), die Rasterstufe wird je Zoom
    einmal gewählt und danach höchstens gröber (`rad_fuer_budget`, Paar-
    Budget wie gehabt; reicht nicht einmal die gröbste: „zu wenig farben
    frei"). **Zoom endet**, wo benachbarte Felder nicht mehr verschiedene
    Terminal-Farben zeigen (`unterscheidbar` < `GRENZE_256` = 25 %); dann
    steht leise „feiner geht hier nicht". Gemessen 11.10.: der xterm-Würfel
    hat 6 Stufen je Kanal, bei Zoom 16 zeigte der Kreis nur noch 4 Farben.
    Unter dem Farbfeld steht „≈ 256: n". Mit `TERM=xterm-direct` (curses
    selbst 24 Bit) rundet `Kontext.pix_farbe` auf 16er-Stufen; dort gilt
    derselbe Deckel.
  Der Hex-Wert ist immer genau; feiner als das Terminal zeigt, kann man
  trotzdem wählen (Hex tippen).
- **Rund** (seit 11.10.2026): die Zellform kommt aus dem Terminal
  (`pixel.zell_seiten()`: `TIOCGWINSZ` ws_xpixel/ws_ypixel mit Zeilen/Spalten;
  fehlt sie: 1:2; überstimmbar `ZENTRALE_ZELL_SEITEN=2.125`), nach
  `KEY_RESIZE` neu gemessen (`Kontext.groesse_neu`). Vorher galt fest 9×18
  (1:2); Sashas VTE mit „Monospace 10" hat ~8×17 (1:2,125) → der Kreis war
  6 % höher als breit. Die Kreisbreite folgt der Zellform (`masse`).
- **Ohne Farben** (8-Farben-Terminal): kein Kreis, Hex tippen geht.

| Taste | was |
|---|---|
| ← → ↑ ↓ | Cursor genau ein Feld weiter (bleibt im Kreis); am Rand rückt der Ausschnitt nach |
| `+` (auch `=`) / `-` (auch `_`) | Zoom hinein (Ausschnitt um den Cursor) / hinaus; bei 256 Farben endet es mit „feiner geht hier nicht" |
| Bild↑ / Bild↓ (auch `]` / `[`) | heller / dunkler |
| `#` | Hex-Feld: `0–9 a–f` tippen, bei 6 Ziffern sofort gesetzt; ⌫ löscht; Enter nimmt (3 Ziffern = Kurzform); Esc schließt nur das Feld; ein Pfeil schließt es und bewegt |
| Enter | nehmen → `("fertig", "#rrggbb")` |
| Esc | abbrechen → `("abbruch",)` |

## Stylebox

Ein Stil ist ein **dict aus CSS-Eigenschaften**, kein eigenes Format:
`{"border-style": "dashed", "border-color": "#ff8800", "background-color":
"#202030", "color": "#ffffff", "--zentrale-muster": "punkte"}`.

**Angebot** (`optionen`): eine Liste von CSS-Namen oder ein JSON Schema
(`stil.schema(namen)`, Entwurf 2020-12, dieselbe Teilmenge wie die
Kachel-Parameter in `core/kachel_parameter.py`). Im Schema darf der
Aufrufer Titel ändern oder die Auswahl einschränken (`oneOf`/`enum`). Die
Box zeigt **genau** diese Eigenschaften; was der Stil sonst noch hat, bleibt
unberührt und kommt nicht zurück. Unbekannte Namen → `ValueError`.

| CSS-Eigenschaft | Titel | Werte | Terminal |
|---|---|---|---|
| `border-style` | Rahmen | `solid`, `dashed`, `dotted`, `double` (kein `none`; altes fällt beim Lesen weg) | `┌─┐│` · `┌╌┐╎` · `┌┈┐┊` · `╔═╗║` |
| `border-color` | Rahmenfarbe | `#rrggbb` | Farbe der Rahmenzeichen |
| `background-color` | Fläche | `#rrggbb` | Hintergrund des Kästchens |
| `color` | Schrift | `#rrggbb` | Schrift (Muster in Schrift/Fläche gemischt) |
| `--zentrale-muster` | Muster | `punkte`, `raster`, `dicht`, `streifen`, `schraeg`, `karo` (kein `none`; altes fällt beim Lesen weg) | `· ·` versetzt · `░` · `▒` · `─` jede 2. Zeile · `╱` · `┼` |
| `background-image` | Icon | `none`, `url(…)` | **gesperrt** (`readOnly`), zeigt „noch gesperrt" |

- **Farben** nur als `#rrggbb` (CSS-Hex), klein geschrieben; `stil.hex_lesen`
  nimmt auch `#rgb` und Großbuchstaben an.
- **Muster**: CSS hat kein Muster-Wort, deshalb die eigene Eigenschaft
  `--zentrale-muster` (Custom Properties mit `--` sind Standard-CSS). Ein
  Browser kann sie z. B. so abbilden: `punkte` → `radial-gradient(currentColor
  1px, transparent 1px)` mit `background-size: 8px 8px`; `streifen` →
  `repeating-linear-gradient(0deg, …)`; `schraeg` → dasselbe mit 45deg;
  `karo` → zwei gekreuzte; `raster`/`dicht` → Punkte enger bzw. halbdeckend.
- **Rahmen ohne Angebot**: bietet der Aufrufer weder `border-style` noch
  `border-color` an (z. B. eine Überschrift nur mit Schrift), zeigt die
  Vorschau keinen Rahmen.
- **Icon**: das Hochladen gibt es noch nicht. Bietet der Aufrufer
  `background-image` an, steht die Zeile da, lässt sich aber nicht öffnen
  (Hinweis „Icon: noch gesperrt"); ein vorhandener Wert bleibt unverändert.
  Ohne Wert steht da „‹ keine › · noch gesperrt".
- **‹ keine ›** (seit 11.10.2026, vorher „—"): eine Eigenschaft ohne Wert
  steht in der Liste als ausgewählte Wahl „‹ keine ›" — bei jeder Art
  (Rahmen, Farben, Muster, Icon). Bei einer Auswahl ist sie der erste
  Eintrag im Kreis von ←→/Leertaste: `keine → durchgezogen → gestrichelt →
  gepunktet → doppelt → keine` (Muster: `keine → Punkte → … → Karo →
  keine`). ‹ keine › heißt **nicht gesetzt**, nicht CSS `none`, und ist das
  **einzige „nichts"** (11.10.2026, Sasha): „keiner"/„keins" (CSS `none`)
  gibt es nicht mehr — weder in `stil.RAHMEN`/`stil.MUSTER` noch im Schema
  (`stil.schema`), in der Stylebox, im Kalender-Formular oder im
  KI-Werkzeug `set_calendar_style` (Sasha: „ich dachte eigentlich dass wir
  auch mit ausdrücklich nicht gesetzt arbeiten"). Wer nichts will, lässt die
  Eigenschaft weg (in einer Änderung: `None`). Alte Stile mit
  `border-style: none` oder `--zentrale-muster: none` (gespeicherte
  Einträge, `.ics`-Zeile `X-ZENTRALE-STIL`) werden beim Lesen auf **nicht
  gesetzt** gebracht: `stil.pruefen` und `stil.anwenden` lassen sie still
  weg (in einer Änderung mit `entfernen=True` werden sie `None`),
  `stil.wert_pruefen` lehnt `none` als Wert ab, `stil.alt_nichts(name, wert)`
  erkennt sie. Der `.ics`-Schreiber schreibt für sie also nichts. Die
  Stylebox zeigt sie als ‹ keine ›, Enter gibt für sie `None` zurück.
  Eine Farbe zeigt „‹ keine ›", bis
  Leertaste/→/`#` den Farbwähler öffnen (er startet weiß). ⌫/Entf setzt
  jede Eigenschaft zurück auf ‹ keine ›. Die Vorschau zeichnet ohne sie
  (Farbe des Themes, ohne Rahmenstil durchgezogen). `r` holt den Wert vom
  Anfang zurück. Enter nimmt immer die ganze Box.
- **Rückgabe** (Vertrag): Enter prüft mit `stil.pruefen` und gibt eine
  **Änderung** zurück — nur, was sich gegenüber dem Anfang geändert hat
  (`stil.unterschied`): neuer Wert als `#rrggbb`/Wort, **entfernt als
  `None`**, z. B. `{"border-style": None, "color": "#ff8800"}`. None kommt nur
  für Eigenschaften, die der Start-Stil mitbrachte (auch kaputte) oder die in
  dieser Sitzung geändert wurden; nie Gesetztes, das nur ⌫ bekam, fehlt.
  `stil.anwenden(alt, änderung)` → neues dict ohne die None-Namen (`alt`
  bleibt); `stil.pruefen(änderung, namen, entfernen=True)` lässt None durch.
  Kaputte Werte im Start-Stil werden still weggelassen statt das Modal zu
  sprengen; Abbruch lässt den Stil des Aufrufers, wie er war.

| Taste | was |
|---|---|
| ↑ ↓ (Tab, Shift+Tab) | Eigenschaft wählen |
| ← → / Leertaste | Auswahl ändern (‹ keine › gehört zum Kreis); bei einer Farbe: Leertaste oder → öffnet den Farbwähler (`#` öffnet ihn gleich mit Hex-Feld) |
| ⌫ / Entf | diese Eigenschaft auf ‹ keine › (nicht gesetzt, Rückgabe None) |
| `r` | diese Eigenschaft zurück auf den Anfang |
| Enter | nehmen → `("fertig", {geänderte css, entfernte: None})` |
| Esc | abbrechen → `("abbruch",)`, `ergebnis` = None |

Im offenen Farbwähler gelten seine Tasten; sein Enter schreibt die Farbe in
die Box (die Box bleibt offen), sein Esc lässt den alten Wert stehen.

## Offen

- Icon hochladen (Datei aus `~/Zentrale/Input` wie die Desk-Bilder).
- Andere Oberflächen (Fenster, Handy) bauen ihren Dialog aus `stil.schema()`.
- Mit 256 Farben (ohne `COLORTERM=truecolor`/`farbe_truecolor an`) bleibt der
  Kreis grob und der Zoom kurz — das ist die Grenze des Terminals; der
  Hex-Wert stimmt trotzdem.
- Bei Zoom 16 liegen Nachbarn im 24-Bit-Kreis oft nur noch 1 Stufe (von
  255) auseinander — feiner kann keine Bildschirmfarbe.
