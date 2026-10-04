# Archiv: draw_time_plot — 24h-Gitter für time/period-Graphen (TUI)

**Stand 2026-10-04:** aus dem Live-Code entfernt.

- **Was es tat:** Zeichnete einen einzelnen `time`- oder `period`-Graphen
  als 24h-Gitter: X = letzte Einträge (ein Datum je Spalte), Y = Uhrzeit
  (00:00 unten, 24:00 oben, Stunden-Marken 00/06/12/18). `time` → Punkt `●`,
  `period` → Balken `█`, über Mitternacht in zwei Segmente gesplittet.
- **Warum archiviert:** Wurde nirgends mehr aufgerufen. Die Graphen zeichnet
  heute `draw_overlay` (alle Graphen überlagert in einem Gitter, `time` und
  `period` inklusive).
- **Wann wieder nützlich:** Wenn ein einzelner Schlaf-/Uhrzeit-Graph wieder
  eine eigene, große Einzelansicht bekommen soll statt der Überlagerung.
- **Abhängigkeiten:** Closure in `main()` der TUI: `safe_addstr`, Palette `C`
  (`faint`, `graph`). `rows` = Einträge aus `/api/graphs/<id>` mit `value`
  (Start-Minute) und bei `period` `end` (End-Minute).

## tui/zentrale_tui.py Z. 4441–4482 (Commit c52f1e1)

```python
    def draw_time_plot(py, bx, bw, ph, rows, is_period):
        """24h-Gitter: X = letzte Einträge (Datum), Y = Uhrzeit (00:00 unten,
        24:00 oben). time → Punkt ●; period → Balken █ (über Mitternacht
        gesplittet, da die Achse an Mitternacht verankert ist)."""
        if ph < 3:
            return
        ix = bx + 2
        plot_x = ix + 3                       # 3 Spalten für die Stunden-Labels
        plot_w = (bx + bw - 2) - plot_x
        if plot_w < 2:
            return

        def row_of(m):                        # 0 → unterste Zeile, 1440 → oberste
            m = max(0, min(1440, m))
            return py + (ph - 1) - int(round(m / 1440.0 * (ph - 1)))

        for r in range(ph):                   # Y-Achse
            safe_addstr(py + r, plot_x - 1, "│", C["faint"])
        for hh in (0, 6, 12, 18, 24):         # Stunden-Marken
            safe_addstr(row_of(hh * 60), ix, "%02d" % (hh % 24), C["faint"])

        def fill(cx, m1, m2):                 # Balken zwischen zwei Minuten (kein Wrap)
            a, b = sorted((row_of(m1), row_of(m2)))
            for r in range(a, b + 1):
                safe_addstr(r, cx, "█", C["graph"])

        for ci, e in enumerate(rows[-plot_w:]):
            cx = plot_x + ci
            s = e.get("value")
            if s is None:
                continue
            if is_period:
                en = e.get("end")
                if en is None:
                    continue
                if en >= s:
                    fill(cx, s, en)
                else:                         # Wrap über Mitternacht
                    fill(cx, s, 1440)
                    fill(cx, 0, en)
            else:
                safe_addstr(row_of(s), cx, "●", C["graph"])
```
