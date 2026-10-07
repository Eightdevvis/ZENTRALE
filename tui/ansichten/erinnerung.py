# tui/ansichten/erinnerung.py
#
# Der Graph-Reminder („bitte eintragen"): poppt EINMAL pro Sitzung ein
# Kästchen auf, wenn ein Graph mit Tages-Reminder heute noch nicht geloggt
# ist (store.reminders ← /api/graphs/reminders). Eine Taste klickt es weg →
# bis Sitzungsende Ruhe für die gezeigten Graphen; neu fällige nagen weiter.
# Bis 06.10.2026 drei lose Variablen (nag_*) und drei Stellen in der
# Hauptschleife von run_ui, siehe memory/system/tui_bauplan.md.


class Erinnerung:
    """Zustand, Taste und Kästchen des Graph-Reminders."""

    def __init__(self, z, graphen):
        self.z = z
        self.graphen = graphen               # 'g' springt gleich ins Graph-Werkzeug
        self.nag_active = False       # Kästchen steht gerade offen?
        self.nag_items = []           # was es listet (ids für die Dismiss-Markierung)
        self.nag_dismissed = set()    # in dieser Sitzung weggeklickte graph-ids

    def taste(self, ch):
        """Bei offenem Kästchen: jede Taste klickt es weg (für diese Sitzung)."""
        if ch != -1:                       # jede Taste klickt den Reminder weg (Sitzung)
            for r in self.nag_items:
                self.nag_dismissed.add(r.get("id"))
            self.nag_active = False
            if ch in (ord("g"), ord("G")):  # g = gleich ins Graph-Werkzeug
                G = self.graphen.G
                G["active"] = True; G["view"] = "list"; G["msg"] = ""
                G["gscroll"] = 0; self.graphen.g_load()

    def pruefen(self, store):
        """Ist heute was fällig (und noch nicht weggeklickt)? Dann aufmachen.
        Die Hauptschleife ruft das nur, wenn niemand gerade tippt."""
        due = [r for r in store.reminders_snapshot()
               if isinstance(r, dict) and r.get("id") not in self.nag_dismissed]
        if due:
            self.nag_active = True
            self.nag_items = due

    def zeichnen(self, H, W):
        """Das Kästchen — zuletzt gezeichnet, liegt also über allem."""
        if not (self.nag_active and self.nag_items):
            return
        C, addclip, draw_box = self.z.C, self.z.addclip, self.z.draw_box
        lines = ["heute noch nicht geloggt:"]
        for r in self.nag_items:
            at = r.get("remind_at") or ""
            lines.append("  • " + str(r.get("name") or r.get("id") or "")
                         + (("  @" + at) if at else ""))
        lines.append("")
        lines.append("g = eintragen · sonst wegklicken")
        nw = min(W - 4, max(26, max(len(s) for s in lines) + 4))
        nh = len(lines) + 2
        nx = max(0, (W - nw) // 2)
        ny = max(0, (H - nh) // 2)
        draw_box(ny, nx, nh, nw, "bitte eintragen", C["warn"])
        for i, s in enumerate(lines):
            addclip(ny + 1 + i, nx + 2, s, nw - 4,
                    C["bright"] if i == 0 else C["faint"])
