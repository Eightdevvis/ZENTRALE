# Zyklus-/PMS-Rechner

Rechnet aus dem Lifestyle-Graphen **»periode«** aus, wann die nächste Periode
fällig ist, und markiert die Woche davor als PMS-Fenster. Modul:
`core/cycle.py`, Endpoint `/api/cycle` (+ Anhang an `/api/calendar`).

## Grundsatz: keine eigene Datenhaltung

Es gibt **keine** neue Datei, **keinen** neuen Kalender-Layer und **kein**
neues Eingabe-Werkzeug. Quelle ist genau der Graph, der ohnehin schon gepflegt
wird: ein Graph namens »periode« (Typ `scale`, jeden Blutungstag die Stärke
1–5). Gefunden wird er über den **Namens-Slug** (`graphs._slug` → `periode`),
nicht über eine harte id — Groß-/Kleinschreibung und Umlaute sind egal.
Gibt es ihn nicht oder hat er noch keine Werte, liefert alles sauber »nichts«
(`/api/cycle` → `{}`) und die Fronten zeichnen einfach nicht.

## Die Rechnung

| Größe          | Wie                                                        |
|----------------|------------------------------------------------------------|
| letzter Start  | erster Tag des **jüngsten zusammenhängenden Log-Blocks**     |
| Zykluslänge    | **Schnitt der echten Abstände** zwischen den Block-Starts    |
| nächste Periode| letzter Start + Zykluslänge                                  |
| PMS-Fenster    | die **7 Tage davor** (`next-7` … `next-1`)                   |

- **Blockbildung (`BLOCK_GAP = 3`):** mehrere Tage hintereinander sind EINE
  Periode, nicht mehrere — sonst wäre jeder Blutungstag ein Zyklus. Eine Lücke
  von bis zu 3 Tagen (vergessener Eintrag) zerreißt den Block nicht; echte
  Zyklen liegen bei ~4 Wochen, da gibt es keine Verwechslungsgefahr.
- **Länge (`len_source`):** `avg` = aus den letzten bis zu 6 echten Abständen
  gemittelt (unplausible 15–60-Tage-Ausreißer fliegen raus, Ergebnis auf 18–45
  geklemmt), `default` = noch kein Abstand messbar → **28** als Fallback. Die
  Fronten zeigen das mit an, damit eine Schätzung nicht wie eine Messung aussieht.
- **`spread`** = max−min der genutzten Abstände: wie fest der Rhythmus ist.
  Wird als »±N t« mitgezeigt statt Scheingenauigkeit zu behaupten.
- **`phase`**: `periode` (läuft gerade) · `pms` (im Fenster) · `ueberfaellig`
  (Vorhersage verstrichen, nichts geloggt — wird als solches gemeldet, die Zahl
  dreht sich NICHT stillschweigend weiter) · `ruhig`.

Grobe Schätzung auf Mittelwert-Basis, **kein medizinisches Werkzeug** — steht
auch so im `title` der Browser-Zeile.

## Wo es auftaucht (alle Kassetten)

**Graph-Werkzeug** — eine leise Zeile, kein Kasten. Der Text kommt fertig aus
`cycle.summary()` und sagt je nach Phase das Wichtigste zuerst (und wiederholt
sich nicht — läuft PMS schon, steht da kein »pms ab …« mehr):

```
ruhig       nächste periode 02.08. (in 13 t) · pms ab 26.07. · ø 26 t
pms         pms läuft seit 26.07. · periode ab 02.08. (6 t) · ø 26 t
periode     periode läuft seit 07.07. · nächste ~02.08. · ø 26 t
überfällig  periode überfällig seit 02.08. (4 t) · ø 26 t
```

Alle Varianten bleiben ≤60 Zeichen (durch `tests/test_cycle.py` festgenagelt),
damit sie in die schmale TUI-Mittelbox passen.

- *Browser* (monolith/laptop, `#graph-panel`): bei ausgewähltem »periode«-
  Graphen die `.gcyc`-Zeile in `--cyc`, `title` sagt »kein medizinisches
  Werkzeug«.
- *TUI* (Taste `g`): in der Liste hängt am periode-Graphen `◆ dd.mm.`; im Solo
  (Enter) steht die volle Zeile direkt über der Eingabe, Farbrolle `cyc`.

**In der Kurve selbst (TUI)** — die Zeitachse der Überlagerung (`draw_overlay`,
dieselbe Routine für die kleine lifestyle-Box UND die große Ansicht im
Graph-Werkzeug) trägt das Fenster mit:

- **PMS-Woche**: je Tag eine gepunktete Senkrechte `┊` in Altrosa über die
  volle Plot-Höhe → liest sich als getönter Block.
- **erwarteter Start**: durchgezogene `│` + `◆` obendrauf; sein Datum steht
  (große Ansicht) in Altrosa in der Datumszeile und **verdrängt** dort ein zu
  dicht danebenstehendes Nachbar-Label.
- Gemalt wird **zuerst**, also überzeichnen Banden/Kurven/Marker die Tönung.
  Sie steht nie vor den echten Werten.
- Nur, wenn der »periode«-Graph in der Überlagerung gerade **sichtbar** ist
  (im Werkzeug abwählbar) — die Tönung gehört sichtbar zu seiner Kurve.

**Die Achse wächst dafür in die Zukunft** (`cycle_axis`, rein rechnend und
ohne Terminal testbar → `tests/test_tui_cycle_axis.py`), sonst läge alles
rechts außerhalb: sie endet ja normal HEUTE. Regel: bis zum erwarteten Start,
aber **ganz oder gar nicht** — passt er nicht in ein Drittel der verfügbaren
Breite, bleibt die Achse wie sie war. Ein halbes PMS-Fenster ohne seinen
Startpunkt wäre nur ein rätselhafter Streifen, und die Historie ist die
Hauptsache. Praktisch heißt das: in der schmalen lifestyle-Box taucht die
Tönung erst auf, wenn es tatsächlich soweit ist; in der großen Ansicht steht
sie fast immer.

> **Nebenwirkung, bewusst abgefangen:** Graphen mit `predict` füllen Lücken im
> Fenster mit Schätzwerten. Seit die Achse in die Zukunft reicht, ist das auf
> Tage **bis heute** begrenzt — sonst stünden plötzlich Schätzungen für Tage
> im Plot, die noch gar nicht waren.

> **Browser:** dort bleibt es bei Textzeile + Kalender. Die Kurve im
> Graph-Werkzeug (`plotSvg`) und die Sparkline der lifestyle-Box haben **keine
> Zeitachse** — x ist die laufende Nummer des Werts, nicht das Datum. »Die
> Woche vor dem Start« lässt sich da nicht ehrlich platzieren; das ginge erst,
> wenn der Plot auf eine echte Datumsachse umgebaut wird.

**Kalender** — Tages-Tönung aus `/api/calendar` → `cycle`:
- *Browser*: `.cday.cyc-pms` / `.cday.cyc-next` (Woche) und `.ccell.cyc-*`
  (Monat) — flächige, sehr leise Tönung (`--cyc-bg`), der vorhergesagte Tag
  zusätzlich mit gestricheltem Rand. Liegt UNTER den Terminen; `today` behält
  seine Hervorhebung.
- *TUI*: Wochen-Kopfzeile bekommt `◆ periode (erwartet)` bzw. `· pms`; im
  Monatsgitter ein `◆`/`·` an der Tageszahl. Die Farbe nimmt sich der Tag nur,
  wenn er sonst nichts zu sagen hat — **ein Termin bleibt wichtiger als eine
  Schätzung**.

## Farbe

Eigene Rolle, bewusst abgesetzt von `--acc` (grün), `--span` (orange) und
`--warn`: gedämpftes **Altrosa**, nie fett.
- Browser: `--cyc` / `--cyc-bg` je Theme (`#9c5f7a` hell, `#c98fae` dunkel).
- TUI: Farbrolle `cyc` (256: 175 night / 132 day, 8-Farben-Fallback Magenta).

## Tests

`tests/test_cycle.py` (Blockbildung, Mittelung, Fallback, PMS-Fenster, Phasen,
Ausreißer, Tages-Marker), `tests/test_tui_cycle_axis.py` (wie weit die Achse
in die Zukunft darf, welche Tage markiert werden) und zwei Endpoint-Tests in
`tests/test_backend_api.py`.

> **Falle beim Erweitern der Endpoint-Tests:** `/api/log` schreibt nach
> `ui.app._DATA_DIR`, der Rechner liest über `graphs._DATA_DIR`. Wer nur eins
> davon auf `tmp_path` patcht, schreibt in die **echten** `data/<graph>.json`.
