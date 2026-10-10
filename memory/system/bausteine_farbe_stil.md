# Farbwähler und Stylebox — zwei Bausteine für jede Ansicht

Stand 2026-10-10. Sasha wollte einen Farbwähler als Regenbogen-Kreis mit
einem kleinen Kreis darin, den man mit den Pfeilen verschiebt und mit + / −
heranzoomt, und eine „Stylebox", in der man das Aussehen eines Objekts
einstellt — für alle Apps, nicht nur den Kalender. Beide sind Bausteine
(`tui/bausteine/`, Regeln in [tui_bauplan.md](tui_bauplan.md) „Bausteine"):
sie kennen keinen Aufrufer, speichern nichts und fragen kein Backend.
Eingehängt seit 10.10.2026 im Kalender: Feld „Stylebox" im Terminformular
([kalender_ansichten_vorschau.md](../werkzeuge/kalender_ansichten_vorschau.md)); das
Angebot für einen Kasten steht als `stil.KASTEN` in `core/stil.py` (dort auch
`als_css`/`aus_css` und die CSS3-Farbnamen für iCalendar COLOR).

| Was | Wo |
|---|---|
| Farbwähler | `tui/bausteine/farbwaehler.py` |
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

self.modal = Stylebox(termin_stil,                  # dict CSS-Name → Wert
                      ["border-style", "border-color", "background-color",
                       "color", "--zentrale-muster", "background-image"],
                      titel="termin", text="Uni 08:30")
# in taste(ch):
erg = self.modal.taste(ch)          # None | ("fertig", {geänderte css}) | ("abbruch",)
if erg and erg[0] == "fertig":
    termin_stil.update(erg[1])      # nur Geändertes; speichern tut die Ansicht
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
  None | `("fertig", dict)` | `("abbruch",)`; danach `ergebnis` (dict, bei
  Abbruch None). `zeilen()` und `vorschau(b, h)` sind rein (Tests, andere
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
- **Zoom** 1×, 2×, 4×, 8×, 16× (`ZOOM`): ab 2× zeigt der Kreis den
  Ausschnitt um den Cursor (Lupe, der Cursor bleibt in der Mitte). Pfeil-
  und Helligkeits-Schritt teilen sich durch den Zoom (1/12 Radius bzw. 5 %
  bei 1×). Gerastert wird **relativ zum Ausschnitt** (`STUFEN`: Farbtöne ×
  Sättigungen je Ausschnitt), deshalb zeigt das Hineinzoomen feinere Stufen,
  ohne mehr Farben zu brauchen.
- **Pixel**: jedes Feld EINE Farbe auf dem Grund des Themes, am Kreisrand
  ein Sextant (Modus `ZENTRALE_PIXEL=half`: Halbblock) aus `pixel.sextant`.
  So kostet jede Farbe genau ein Farbpaar. Zwei Farben je Feld (wie
  `pixel.zellen`) brauchten bei 30×15 Feldern über 250 Paare — mehr als es
  gibt ([pixelstil.md](pixelstil.md)).
- **Paar-Budget**: vor dem Zeichnen zählt `rad_fuer_budget`, wie viele
  Paare die feinste Rasterung bräuchte, und nimmt die erste aus `STUFEN`,
  die in die freien Paare passt (minus Reserve für Regler, Feld, Marke).
  Reicht nicht einmal die gröbste: nur Text („zu wenig farben frei"), keine
  Farbe — so läuft `PIX` nie mitten im Bild über und färbt nichts anderes um.
- **256 Farben / 24 Bit**: die Farbnummer wählt `Kontext.pix_farbe` (nächste
  der 256, sonst 24 Bit auf 16er-Stufen). Bei 256 steht unter dem Feld
  „≈ 256: n". Der Hex-Wert ist immer genau; feiner als das Terminal zeigt,
  kann man trotzdem wählen (Zoom, Hex tippen).
- **Ohne Farben** (8-Farben-Terminal): kein Kreis, Hex tippen geht.

| Taste | was |
|---|---|
| ← → ↑ ↓ | Cursor im Kreis (bleibt im Kreis) |
| `+` (auch `=`) / `-` (auch `_`) | Zoom hinein / hinaus |
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
| `border-style` | Rahmen | `solid`, `dashed`, `dotted`, `double`, `none` | `┌─┐│` · `┌╌┐╎` · `┌┈┐┊` · `╔═╗║` · leer |
| `border-color` | Rahmenfarbe | `#rrggbb` | Farbe der Rahmenzeichen |
| `background-color` | Fläche | `#rrggbb` | Hintergrund des Kästchens |
| `color` | Schrift | `#rrggbb` | Schrift (Muster in Schrift/Fläche gemischt) |
| `--zentrale-muster` | Muster | `none`, `punkte`, `raster`, `dicht`, `streifen`, `schraeg`, `karo` | leer · `· ·` versetzt · `░` · `▒` · `─` jede 2. Zeile · `╱` · `┼` |
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
- **Rückgabe**: Enter prüft mit `stil.pruefen` und gibt nur zurück, was sich
  gegenüber dem Anfang geändert hat (`stil.unterschied`). Kaputte Werte im
  Start-Stil werden still weggelassen statt das Modal zu sprengen.

| Taste | was |
|---|---|
| ↑ ↓ (Tab, Shift+Tab) | Eigenschaft wählen |
| ← → / Leertaste | Auswahl ändern; bei einer Farbe: Leertaste oder → öffnet den Farbwähler (`#` öffnet ihn gleich mit Hex-Feld) |
| ⌫ / Entf | diese Eigenschaft zurück auf den Anfang |
| Enter | nehmen → `("fertig", {geänderte css})` |
| Esc | abbrechen → `("abbruch",)`, `ergebnis` = None |

Im offenen Farbwähler gelten seine Tasten; sein Enter schreibt die Farbe in
die Box (die Box bleibt offen), sein Esc lässt den alten Wert stehen.

## Offen

- Icon hochladen (Datei aus `~/Zentrale/Input` wie die Desk-Bilder).
- Andere Oberflächen (Fenster, Handy) bauen ihren Dialog aus `stil.schema()`.
- Feiner als 16er-Stufen zeigt die TUI im 24-Bit-Modus nicht
  (`pix_farbe` rundet für das Paar-Budget); der Hex-Wert stimmt trotzdem.
