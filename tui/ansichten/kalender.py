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

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from . import kalender_ansichten, kalender_stil
from . import kalender_werkzeuge as kw
from .basis import BEENDEN
from .farben import DECKKRAFT
from .kalender_advanced import Advanced
from .kalender_ansichten import (ANSICHT_NAMEN, GLAS, INV, LEISE, glas_teile,
                                 naechste_ansicht, text_breite)
from .kalender_ansichten import zeichne as stil_zeichnen
from .kalender_bedienung import Bedienung
from .kalender_phasen import PhasenListe
from .kalender_quellen import QuellenWahl
from .tasten import Tasten

try:
    from tui.bausteine.stylebox import Stylebox
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine.stylebox import Stylebox

# Die Kästen, die über dem Kalender aufgehen, mit ihrer eigenen Tabelle;
# ihre Ansichten heißen in der Tabelle des Kalenders „name:ansicht". Die
# Stylebox ist ein Baustein: ihre Tabelle (dict) trägt den offenen
# Farbwähler schon als „farbe:…" mit — dieselbe, aus der sie verteilt.
KAESTEN = (("frage", kw.Dialog), ("formular", kw.Formular), ("advanced", Advanced),
           ("quellen", QuellenWahl), ("rhythmus", PhasenListe), ("stylebox", Stylebox))


def _tabelle(klasse):
    t = klasse.TASTEN
    return Tasten(t) if isinstance(t, dict) else t


def _offen(klasse):
    """Weg zum offenen Kasten dieser Art (ohne offenen: die Klasse — die
    Tabelle fragt dann nur, ob es die aktion_-Methoden gibt)."""
    def weg(kal):
        return next((o for o in kal.bedienung.kette() if isinstance(o, klasse)), klasse)
    return weg


def _bedienung(kal):
    return kal.bedienung


class Kalender:
    # ── Tasten: EINE Tabelle (tasten.py, 2026-10-11) ───────────────────
    # Die Ansichten A/B/C (kalender_bedienung: a:…, b:monat, c:…), das
    # Ansehen-Fenster und jeder Kasten mit seiner Tabelle. Aus ihr verteilt
    # taste(), und die Leiste ganz unten zeigt die offene Ansicht — im
    # Kasten steht keine Tastenzeile mehr.
    TASTEN = Tasten.zusammen(
        {"ansehen": [("any key", "ansehen_zu", "close")]},     # jede Taste schließt
        dict({"a": (Bedienung.TASTEN_A, _bedienung), "b": (Bedienung.TASTEN_B, _bedienung),
              "c": (Bedienung.TASTEN_C, _bedienung)},
             **{name: (_tabelle(klasse), _offen(klasse)) for name, klasse in KAESTEN}))

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
        # Glas-Farben je (Rolle, Theme, 24 Bit?) — Mischen + bunt kostet
        self._glas_farben = {}

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
        K["staende"], K["sprung"] = {}, None   # frisch geöffnet: alle Ansichten bei heute
        self.bedienung.setze_tag(date.today())

    # ── Ansicht wechseln: jede merkt sich ihren Tag ───────────────────
    # Sasha, 10.10.2026: „wenn ich danach wieder drauf wechsel is es
    # automatisch auf dem tag auf dem ich in der ansicht stehen blieb und nich
    # auf dem tag wo ich hingesprungen bin durch die monatsansicht". Also hat
    # jede Ansicht (A/B/C) ihren eigenen Stand (Tag, Termin, Fenster), und der
    # Sprung aus dem Monat in die Tagesliste ist nur geliehen.
    def _stand_merken(self):
        K, W = self.K, self.bedienung.W
        if not K.get("sprung"):
            K.setdefault("staende", {})[K["stil"]] = (self.bedienung.tag(), W["idx"], K["ref"])

    def _stand_holen(self, stil, sonst_tag):
        K, W = self.K, self.bedienung.W
        K["stil"], K["sdata"] = stil, None
        st = (K.get("staende") or {}).get(stil)
        if st:
            W["tag"], W["idx"], K["ref"] = st
        else:
            self.bedienung.setze_tag(sonst_tag, W["idx"])

    def k_stil_weiter(self):
        K = self.K
        tag = self.bedienung.tag()
        self._stand_merken()
        if K.get("sprung"):                    # geliehene Tagesliste verlassen
            K["sprung"] = None
        self._stand_holen(naechste_ansicht(K["stil"]), tag)
        K["msg"] = "ansicht: " + ANSICHT_NAMEN[K["stil"]]

    def sprung_zum_tag(self, d):
        """Enter im Monat: diesen Tag in der Tagesliste (A) bearbeiten; der
        eigene Stand von A bleibt unangetastet, Esc führt zurück."""
        K, W = self.K, self.bedienung.W
        self._stand_merken()
        K["sprung"] = {"von": K["stil"]}
        K["stil"], K["sdata"] = "A", None
        W["fokus"] = "termine"
        self.bedienung.setze_tag(d, 0)
        K["ref"] = d.isoformat()
        K["msg"] = "tag aus dem monat"

    def sprung_zurueck(self):
        K = self.K
        von = (K.get("sprung") or {}).get("von") or "B"
        K["sprung"] = None
        self._stand_holen(von, self.bedienung.tag())
        K["msg"] = "ansicht: " + ANSICHT_NAMEN[K["stil"]]

    def ansicht(self) -> str:
        """Welche Ansicht der Tabelle offen ist: der innerste Kasten, sonst
        das Ansehen-Fenster, sonst die Ansicht A/B/C."""
        kette = self.bedienung.kette()
        if kette:
            o = kette[-1]
            name = next(n for n, k in KAESTEN if isinstance(o, k))
            return name + ":" + o.ansicht()
        if self.bedienung.W["popup"]:
            return "ansehen"
        return self.bedienung.ansicht()

    def taste(self, ch):
        """Eine Taste, während der Kalender den Fokus hat. → BEENDEN (q).
        Ein offener Kasten verteilt selbst (seine Tabelle ist ein Teil von
        TASTEN) und sagt der Bedienung, was daraus folgt."""
        bed = self.bedienung
        if ch != -1:
            bed.W["msg"] = ""
        if bed.W["dialog"] is not None:
            bed.dialog_taste(ch)
            return None
        return BEENDEN if self.TASTEN.verteilen(self, self.ansicht(), ch) is BEENDEN else None

    def aktion_ansehen_zu(self, _t):
        self.bedienung.W["popup"] = None

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
                stil = rolle.startswith(kalender_stil.MARKE)
                attr = self._stil_attr(rolle) if stil else self._attr(rolle)
                if text.strip() or rolle.endswith((INV, LEISE)) or GLAS in rolle or stil:
                    z.addclip(by + 1 + i, x, text, ix + iw - x, attr)
                x += text_breite(text)
        unten = bed.zeile_unten()              # nur Meldungen; die Tasten: Leiste ganz unten
        if unten:
            txt, rolle = unten
            z.addclip(bottom, ix, txt, iw, C.get(rolle, C["faint"]))
        bed.zeichne_popup(by, bx, bh, bw)
        bed.zeichne_kasten(by, bx, bh, bw)

    def _attr(self, rolle):
        """Rolle der Leinwand (kalender_ansichten) → curses-Attribut."""
        C = self.z.C
        if GLAS in rolle:
            return self._glas_attr(rolle)
        if rolle.endswith(LEISE):
            return self._leise_attr(rolle[:-len(LEISE)])
        if rolle.endswith(INV):
            # eigene Fläche (Kalender-Tabelle), sonst die Schrift invertiert
            return C.get(rolle) or (C.get(rolle[:-len(INV)], C["dim"]) | curses.A_REVERSE)
        return C.get(rolle, C["dim"])

    def _stil_attr(self, rolle):
        """„$schrift$grund$rückfall" (kalender_stil.rolle, Stylebox eines
        Termins) → Farbpaar über Kontext.pix_attr. Was der Stil offen lässt,
        kommt aus dem Paar der Rückfall-Rolle (z. B. die Kursfläche unter einem
        farbigen Rahmen). Im 256er-Modus werden bunte Farben über
        pixel.bunt gerundet (sonst kippten sie auf die Graurampe), graue über
        pix_farbe. Ohne 256 Farben oder wenn die Paare ausgehen: der Rückfall."""
        C, z = self.z.C, self.z
        basis, schrift, grund = kalender_stil.teile(rolle)
        rueckfall = self._attr(basis)
        info = C.get("kal_glas")
        if not info:
            return rueckfall
        schl = ("stil", rolle, info["thema"], bool(C.get("pix_true")))
        farben = self._glas_farben.get(schl)
        if farben is None:
            paare = info["paare"]
            kern = basis[:-len(LEISE)] if basis.endswith(LEISE) else basis
            paar = paare.get(kern)
            if paar is None and kern.endswith(INV) and kern[:-len(INV)] in paare:
                f, b, _e = paare[kern[:-len(INV)]]
                paar = (b, f, 0)
            fg0, bg0, _e = paar or paare.get("dim") or ((200, 200, 200), C.get("pix_bg") or (0, 0, 0), 0)

            def rgb(h, sonst):
                if not h:
                    return sonst
                c = kalender_stil.stil_kern.hex_zu_rgb(h)
                if not C.get("pix_true") and max(c) - min(c) >= 40:
                    c = pixel.bunt(c)
                return c
            farben = self._glas_farben[schl] = (rgb(schrift, fg0), rgb(grund, bg0))
        fg, bg = farben
        attr = z.pix_attr(fg, bg)
        if (z.pix_farbe(fg), z.pix_farbe(bg)) not in z.PIX["pairs"]:
            return rueckfall                    # Paare voll → lieber Kursfarbe als Bernstein
        return attr

    def _glas_attr(self, rolle):
        """„<darunter>~<glas>[~<schrift>]" (Leinwand.glas) → curses-Attribut:
        Schrift und Grund der Rolle darunter, der Grund mit der Fläche der
        Glasrolle gemischt (farben.DECKKRAFT) — so scheinen Punktlinien und
        feste Termine durch die uncommitted-Ebene. Ohne 256 Farben oder wenn
        die Farbpaare ausgehen: die alte blasse Fläche."""
        C, z = self.z.C, self.z
        unter, glas, schrift = glas_teile(rolle)
        info = C.get("kal_glas")
        rueckfall = C.get(glas + "_blass_inv", C["dim"] | curses.A_REVERSE)
        if not info or glas not in info["flaeche"]:
            return rueckfall
        schl = (rolle, info["thema"], bool(C.get("pix_true")))
        farben = self._glas_farben.get(schl)
        if farben is None:
            farben = self._glas_farben[schl] = self._glas_mischen(info, unter, glas, schrift)
        fg, grund, extra = farben
        attr = z.pix_attr(fg, grund)
        if (z.pix_farbe(fg), z.pix_farbe(grund)) not in z.PIX["pairs"]:
            return rueckfall                    # Paare voll → lieber blass als Bernstein
        return attr | extra

    def _leise_attr(self, flaeche):
        """„k_t3_inv" + LEISE → dieselbe Fläche, die Schrift ein Stück zum
        Grund hin gemischt (Liste und Zeit unter dem Titel eines Blocks,
        10.10.2026). Lesbar bleibt sie (≥ 3:1). Ohne 256 Farben oder wenn
        die Paare ausgehen: die Fläche mit A_DIM."""
        C, z = self.z.C, self.z
        basis = C.get(flaeche) or (C.get(flaeche[:-len(INV)], C["dim"]) | curses.A_REVERSE
                                   if flaeche.endswith(INV) else C.get(flaeche, C["dim"]))
        rueckfall = basis | curses.A_DIM
        info = C.get("kal_glas")
        paar = (info or {}).get("paare", {}).get(flaeche)
        if not paar:
            return rueckfall
        schl = ("leise", flaeche, info["thema"], bool(C.get("pix_true")))
        farben = self._glas_farben.get(schl)
        if farben is None:
            fg, grund, _e = paar
            for a in (0.45, 0.3, 0.15, 0.0):     # Anteil Grund in der Schrift
                f = tuple(round(x * (1 - a) + y * a) for x, y in zip(fg, grund))
                if not C.get("pix_true"):
                    f = pixel.bunt(f)
                if _kontrast(f, grund) >= 3 or a == 0.0:
                    break
            farben = self._glas_farben[schl] = (f, grund)
        f, grund = farben
        attr = z.pix_attr(f, grund)
        if (z.pix_farbe(f), z.pix_farbe(grund)) not in z.PIX["pairs"]:
            return rueckfall
        return attr

    def _glas_mischen(self, info, unter, glas, schrift):
        """(Schrift, Grund, Extra) einer Glaszelle als RGB — siehe _glas_attr."""
        C, z = self.z.C, self.z
        paare = info["paare"]
        paar = paare.get(unter)
        if paar is None and unter.endswith(INV) and unter[:-len(INV)] in paare:
            f, b, e = paare[unter[:-len(INV)]]      # „faint_inv" = faint umgedreht
            paar = (b, f, e)
        fg, bg, extra = paar or paare["dim"]
        a0 = DECKKRAFT[info["thema"]]["glas"]
        oben = info["flaeche"][glas]
        for a in (a0, a0 + 0.15, a0 + 0.3, a0 + 0.45, 1.0):
            grund = tuple(round(u * (1 - a) + o * a) for u, o in zip(bg, oben))
            if not C.get("pix_true"):
                # 256 Farben: auf die nächste BUNTE runden, sonst fiele ein dunkles
                # Orange auf die Graurampe (wie kontext.apply_theme durchscheinend).
                grund = pixel.bunt(grund)
            # Landet die Mischung wieder auf dem Grund darunter (Pfirsich unter
            # Rosa, tags fast immer), wäre die Scheibe unsichtbar → kräftiger.
            if z.pix_farbe(grund) != z.pix_farbe(bg) or a >= 1.0:
                break
        if schrift:
            # Eigenes Label auf dem Glas: in der Kursfarbe (so liest es sich
            # als Glas, nicht als Fläche), solange sie lesbar ist (≥ 3:1) —
            # sonst die besser lesbare von Kursfarbe und Flächenschrift.
            kand = [p[0] for p in (paare.get(schrift), paare.get(glas + INV)) if p]
            if kand and _kontrast(kand[0], grund) < 3:
                kand = [max(kand, key=lambda f: _kontrast(f, grund))]
            fg = kand[0] if kand else fg
            extra = 0
        return fg, grund, extra

    def tippt(self) -> bool:
        """Ist gerade ein Kasten offen, in den getippt wird? Dann sind alle
        Tasten Text — auch „/" (sonst ginge die Befehlszeile auf)."""
        return self.K["active"] and self.bedienung.W["dialog"] is not None


def _hell(rgb):
    """Relative Helligkeit (WCAG) einer RGB-Farbe."""
    def k(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (k(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _kontrast(a, b):
    ha, hb = _hell(a), _hell(b)
    return (max(ha, hb) + 0.05) / (min(ha, hb) + 0.05)
