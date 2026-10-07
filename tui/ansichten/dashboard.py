# tui/ansichten/dashboard.py
#
# Die rechte Spalte des alten 3-Spalten-Dashboards (/dashboard an):
# lifestyle (Überlagerung aller Graphen), focus (der fokussierte Projekt-
# Teilbaum) und outbound. Die Inhalte zeichnen Graphen und Fokus selbst;
# hier steht nur, wie die Spalte aufgeteilt wird. Bis 06.10.2026 Teil der
# Hauptschleife in run_ui, siehe memory/system/tui_bauplan.md.

import curses


class Dashboard:
    """Das alte Dashboard (Backup der Galaxie): die rechte Spalte. Die linke
    (external, telemetrie, stdout) sind die Technik-Bausteine."""

    def __init__(self, z, graphen, fokus):
        self.z = z
        self.graphen, self.fokus = graphen, fokus

    def zeichne_rechts(self, top, rx, body_h, rightw, gs_cache, gv_cache, cyc_cache,
                       proj_cache, nets):
        """lifestyle / focus / outbound übereinander, Höhen nach Inhalt."""
        C, addclip, draw_box = self.z.C, self.z.addclip, self.z.draw_box
        safe_addstr = self.z.safe_addstr
        draw_overlay, proj_render = self.graphen.draw_overlay, self.fokus.proj_render
        # ── RECHTS: lifestyle / outbound ──────────────────────────────────
        # lifestyle = ÜBERLAGERUNG aller Graphen in EINEM Gitter. X = Datum
        # (Zeitstrahl), Y bewusst MEHRDEUTIG — jeder Graph nutzt seine eigene
        # Achse + Darstellung, alles übereinandergelegt zum Vergleich:
        #   period → zusammenhängende Bande (Zellen-Hintergrund) über die Spanne
        #   time   → Symbol auf der 24h-Skala (Zeitpunkt, keine Linie); je
        #            Graph EIN eigenes aus TIME_SYMBOLS (★ als Default/erstes)
        #   scale  → wachsende Kreise ◦○◉●⬤ auf eigener Zeile (Größe = 1–5)
        #   number → Punkt auf der eigenen min/max-Spanne (sichtbare Werte)
        # Eigener Marker + Farbe je Graph (+ Legende). Quelle:
        # store.graphs_snapshot (langsames Hintergrund-Polling).
        if gs_cache:
            # bewusst kompakt: höchstens ~11 Zeilen, Rest geht an outbound.
            life_h = max(7, min(11, body_h - 4))
        else:
            life_h = 4
        out_h = body_h - life_h
        # PROJECTS schiebt sich zwischen lifestyle und outbound — aber nur wenn
        # es überhaupt geflaggte Projekte gibt UND outbound danach mind. 5 Zeilen
        # behält (sonst lieber ganz weglassen, Tripwire hat Vorrang). Höhe ist
        # VARIABEL (verschachtelt): ein Knoten ohne Unterprojekte braucht 2 Zeilen
        # (Titel+Leiste), einer MIT Unterprojekten einen Rahmen (oben+unten) um
        # seine rekursiv gemessenen Kinder.
        def proj_measure(node, w):
            kids = node.get("children") or []
            if not kids:
                return 2
            return 2 + sum(proj_measure(c, w - 2) for c in kids)
        proj_h = 0
        if proj_cache and out_h >= 9:
            need = 2 + sum(proj_measure(p, rightw - 4) for p in proj_cache
                           if isinstance(p, dict))
            proj_h = min(need, out_h - 5)
        out_h -= proj_h
        draw_box(top, rx, life_h, rightw, "lifestyle")
        # Inhalt der lifestyle-Box: kompakte Überlagerung aller Graphen
        # (geteilte Routine, auch groß im Graph-Werkzeug — siehe draw_overlay).
        draw_overlay(top, rx, life_h, rightw, gs_cache, gv_cache, labeled=False,
                     cyc=cyc_cache)

        # ── PROJECTS (zwischen lifestyle und outbound) ────────────────────
        # VERSCHACHTELT (Quelle: store.projects_snapshot ← /api/projects, Baum).
        # Knoten OHNE Unterprojekte: Titel + Erfüllungsleiste (2 Zeilen). Knoten
        # MIT Unterprojekten: dünner Rahmen (Titel im oberen Rand) um die rekursiv
        # gezeichneten Kinder, KEINE eigene Leiste. Reine Anzeige; markiert wird im
        # Listen-Werkzeug ('p' auf Liste bzw. Eintrag). Bei Platzmangel wird
        # einfach ab dem Punkt aufgehört (kein Überlauf, kein Crash).
        if proj_h:
            draw_box(top + life_h, rx, proj_h, rightw, "focus")
            y_max = top + life_h + proj_h - 2          # letzte innere Zeile
            x0, w0 = rx + 2, max(4, rightw - 4)

            # Dieselbe Routine wie die Projektansicht (Mitte) → BYTE-GLEICHE
            # Darstellung. Ohne Cursor/Fokus-Marke; proj_cache ist ohnehin nur
            # der eine fokussierte Knoten (oder leer → Box wird gar nicht erst
            # gezeichnet, da proj_h dann 0 ist).
            y, rendered = top + life_h + 1, 0
            for p in proj_cache:
                if y > y_max or not isinstance(p, dict):
                    break
                y = proj_render(p, x0, y, w0, y_max)
                rendered += 1
            if rendered < len(proj_cache):         # Rest passt nicht → ehrlich anzeigen
                safe_addstr(top + life_h + proj_h - 1, rx + rightw - 6,
                            "+%d" % (len(proj_cache) - rendered), C["faint"])

        oy = top + life_h + proj_h
        draw_box(oy, rx, out_h, rightw, "outbound", C["warn"])
        if nets:
            inner = out_h - 2
            for i, e in enumerate(nets[-inner:]):
                if not isinstance(e, dict):
                    continue
                yy = oy + 1 + i
                t = (e.get("time") or "")[:8]
                safe_addstr(yy, rx + 2, t, C["faint"])
                px = rx + 2 + len(t) + 1
                avail = (rx + rightw - 1) - px
                addclip(yy, px, e.get("text") or "", avail, C["warn"])
        else:
            safe_addstr(oy + 1, rx + 2, "// offline ✓", C["acc"] | curses.A_DIM)
