# tui/ansichten/kalender.py
#
# Der Kalender der TUI (Zeichner gegen /api/calendar; die Logik liegt in
# core/kalender.py). Wird in tui/ansichten/ relativ importiert — mit
# core/kalender.py kann es deshalb nie verwechselt werden.
#
# Seit 07.10.2026 nur noch die drei Ansichten aus kalender_ansichten.py:
#   A Tagesliste (wie calcurse) · B Monatsraster · C Woche als Zeitachse,
# alle bedienbar wie calcurse (kalender_bedienung.py, Logik in
# kalender_werkzeuge.py). Der alte selbst gebaute Kalender (Woche/Monat mit
# Formular und Seitenliste, ~1.000 Zeilen) ist raus — Sasha: „die kalender
# ansicht von vorher kannst du dann rausschmeißen". EIN Kalender, mehrere
# Ansichten: Auswahl, Kästen und Backend-Aufrufe gibt es nur einmal.

import curses
import json
import os
from datetime import date

from . import kalender_ansichten
from .basis import BEENDEN
from .kalender_ansichten import (ANSICHT_NAMEN, INV, naechste_ansicht,
                                 tasten_hinweis, text_breite)
from .kalender_ansichten import zeichne as stil_zeichnen
from .kalender_bedienung import Bedienung


class Kalender:
    def __init__(self, z):
        self.z = z
        # active    : der Kalender hat den Fokus
        # ref       : Anker der Ansicht (A: erster der 3 Tage, B: Monat, C: Woche)
        # stil      : "A" | "B" | "C" — gilt pro Sitzung, beim Öffnen bleibt sie
        # sdata     : letzte /api/calendar-Antwort (Bedienung.daten() holt neu)
        # data      : von der Bedienung beim Neuladen mit geleert (Altlast-frei)
        # showhidden: Deaktiviertes/Ausgefallenes zeigen (Taste x)
        # w         : Zustand der Bedienung (Auswahl, Kasten, Meldung)
        self.K = z.K = {"active": False, "ref": date.today().isoformat(),
                        "stil": "A", "sdata": None, "data": None,
                        "showhidden": False, "msg": ""}
        self.bedienung = Bedienung(self)
        self._farben_daten = None
        self._farben_laden()

    # ── feste Kursfarben (kalender_ansichten.farben_vergeben) ─────────
    @staticmethod
    def _farben_pfad():
        return (os.environ.get("ZENTRALE_KALENDER_FARBEN")
                or os.path.expanduser("~/.local/state/zentrale/kalender_farben.json"))

    def _farben_laden(self):
        try:
            with open(self._farben_pfad()) as f:
                t = json.load(f)
            if isinstance(t, dict):
                kalender_ansichten.FARBTABELLE.clear()
                kalender_ansichten.FARBTABELLE.update(t)
        except (OSError, ValueError):
            pass

    def _farben_pflegen(self, d):
        """Neue Kurse aus frisch geladenen Daten fest einfärben und speichern."""
        if d is self._farben_daten:
            return
        self._farben_daten = d
        if kalender_ansichten.farben_vergeben(d, kalender_ansichten.FARBTABELLE):
            pfad = self._farben_pfad()
            try:
                os.makedirs(os.path.dirname(pfad), exist_ok=True)
                with open(pfad + ".neu", "w") as f:
                    json.dump(kalender_ansichten.FARBTABELLE, f, ensure_ascii=False, indent=1)
                os.replace(pfad + ".neu", pfad)
            except OSError:
                pass                    # dann eben nur für diese Sitzung

    def oeffnen(self):
        """Startseite → Kalender: frisch laden, heute gewählt, nichts offen."""
        K, W = self.K, self.bedienung.W
        K["active"] = True
        K["sdata"] = K["data"] = None
        K["msg"] = ""
        W["dialog"] = W["popup"] = None
        W["fokus"] = "termine"
        self.bedienung.setze_tag(date.today())

    def k_stil_weiter(self):
        K = self.K
        K["stil"] = naechste_ansicht(K["stil"])
        K["sdata"] = None
        # Der gewählte Tag bleibt; die neue Ansicht rückt so, dass er drin ist.
        self.bedienung.setze_tag(self.bedienung.tag(), self.bedienung.W["idx"])
        K["msg"] = "ansicht: " + ANSICHT_NAMEN[K["stil"]]

    def taste(self, ch):
        """Eine Taste, während der Kalender den Fokus hat. → BEENDEN (q)."""
        if ch in (ord("v"), ord("V")) and self.bedienung.W["dialog"] is None:
            self.k_stil_weiter()
            return None
        if self.bedienung.taste(ch) is BEENDEN:
            return BEENDEN
        return None

    def draw_calendar(self, by, bx, bh, bw):
        """Die gewählte Ansicht in die MITTE-Box: Zeilen aus
        kalender_ansichten.py, Rollen auf die Palette („_inv" = Fläche),
        darüber Ansehen-Fenster und Kasten der Bedienung."""
        C, K, z, bed = self.z.C, self.K, self.z, self.bedienung
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if iw < 8:
            return
        d = bed.daten()
        if d.get("failed"):
            z.addclip(by + 1, ix, "kalender: backend? (versuche gleich nochmal)", iw, C["faint"])
            return
        hoehe = bottom - (by + 1)
        self._farben_pflegen(d)
        try:
            zeilen = stil_zeichnen(K["stil"], d, iw, hoehe, erledigte=K["showhidden"],
                                   auswahl=bed.auswahl())
        except Exception as e:          # eine kaputte Ansicht darf die TUI nicht reißen
            z.addclip(by + 1, ix, "ansicht %s: %s" % (K["stil"], e), iw, C["warn"])
            return
        for i, zeile in enumerate(zeilen[:hoehe]):
            x = ix
            for text, rolle in zeile:
                if rolle.endswith(INV):
                    # eigene Fläche (Kalender-Tabelle), sonst die Schrift invertiert
                    attr = C.get(rolle) or (C.get(rolle[:-len(INV)], C["dim"]) | curses.A_REVERSE)
                else:
                    attr = C.get(rolle, C["dim"])
                if text.strip() or rolle.endswith(INV):
                    z.addclip(by + 1 + i, x, text, ix + iw - x, attr)
                x += text_breite(text)
        unten = bed.zeile_unten()
        if unten:
            txt, rolle = unten
            z.addclip(bottom, ix, txt, iw, C.get(rolle, C["faint"]))
        else:
            z.addclip(bottom, ix, tasten_hinweis(K["stil"]), iw, C["faint"])
        bed.zeichne_popup(by, bx, bh, bw)
        bed.zeichne_kasten(by, bx, bh, bw)

    def tippt(self) -> bool:
        """Ist gerade ein Kasten offen, in den getippt wird? Dann sind alle
        Tasten Text — auch „/" (sonst ginge die Befehlszeile auf)."""
        return self.K["active"] and self.bedienung.W["dialog"] is not None
