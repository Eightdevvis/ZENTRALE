# tui/ansichten/kontext.py
#
# Der Kontext: das eine Objekt, das jede Ansicht bekommt. Bis 06.10.2026
# lagen diese Dinge als lokale Variablen und Closures in run_ui
# (tui/zentrale_tui.py), und jede Closure konnte alles lesen. Jetzt steht an
# EINER Stelle, was wirklich geteilt ist: stdscr, store, die Farben C, die
# Pixel-Farbpaare PIX, der Theme-Zugriff und die Zeichen-Primitive
# (safe_addstr, addclip, draw_box). Siehe memory/system/tui_bauplan.md.

import curses
import os

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from .farben import DECKKRAFT, KAL, MOTIV_FARBEN, ROLES, THEMES


class Kontext:
    """Was alle Ansichten teilen: Bildschirm, Daten-Store, Farben, Theme,
    Zeichen-Primitive. run_ui baut ihn einmal pro Lauf; jede Ansicht bekommt
    ihn als `z` und liest von hier statt aus Closure-Variablen.

    Die Ansichten hängen ihre Zustands-Dicts zusätzlich hier an (z.AI, z.K …),
    damit run_ui (welches Fenster hat den Fokus?) sie lesen kann, ohne jede
    Ansicht einzeln zu kennen."""

    def __init__(self, stdscr, store, has_color, theme_state):
        self.stdscr = stdscr
        self.store = store
        self.has_color = has_color
        # Tag/Nacht: core/theme.ThemeState, gebaut von zentrale_tui (dort
        # liegt der Pfad zu core/). Die Datei ist die einzige Wahrheit.
        self._theme = theme_state
        self.C = {}
        # Farbpaare des Pixel-Baustein: (fg, bg) → curses-Attribut, vergeben von
        # PIX["base"] bis PIX["top"]; läuft das Budget voll, wird es zu Beginn des
        # nächsten Bildes geleert (nie mitten im Bild — Paare sind Referenzen).
        self.PIX = {"pairs": {}, "base": 0, "top": 0, "voll": False}
        self.PIX_MODUS = (os.environ.get("ZENTRALE_PIXEL") or "mix").strip().lower()

    def pix_farbe(self, rgb):
        """RGB → curses-Farbnummer: 24 Bit, wenn das Terminal es kann (auf
        16er-Stufen gerundet, damit die Paare reichen), sonst die nächste der 256."""
        C = self.C
        if C.get("pix_true"):
            r, g, b = (min(255, round(v / 16) * 16) for v in rgb)
            n = (r << 16) | (g << 8) | b
            return n if n >= 8 else 8          # 0–7 wären Palettenfarben
        return pixel.rgb_256(rgb)

    def pix_attr(self, fg, bg):
        C, PIX, pix_farbe = self.C, self.PIX, self.pix_farbe
        key = (pix_farbe(fg), pix_farbe(bg))
        attr = PIX["pairs"].get(key)
        if attr is None:
            n = PIX["top"] - len(PIX["pairs"])
            if n <= PIX["base"]:
                PIX["voll"] = True
                return C.get("amber", 0)
            try:
                curses.init_pair(n, key[0], key[1])
                attr = curses.color_pair(n)
            except curses.error:
                return C.get("amber", 0)
            PIX["pairs"][key] = attr
        return attr

    def apply_theme(self, tname):
        C, PIX, has_color, stdscr = self.C, self.PIX, self.has_color, self.stdscr
        if not has_color:
            for r in ROLES:
                C[r] = 0
            C["bright"] = curses.A_BOLD
            C["dim"] = curses.A_BOLD       # heller Text im Mono-Fallback
            C["faint"] = curses.A_DIM
            C["acc"] = curses.A_BOLD
            # Ombre ohne Farbe: nur zwei Stufen (normal → gedimmt)
            C["ombre"] = [0, 0, curses.A_DIM, curses.A_DIM, curses.A_DIM]
            # Klaviertasten ohne Farbe: invertiert ist alles, was bleibt.
            C["key_black"] = curses.A_REVERSE
            C["key_press"] = curses.A_REVERSE | curses.A_BOLD
            C["keyframe"], C["keyglow"] = [], []   # Beleuchtung braucht Farben
            # Zyklus-Fenster ohne Farbe: keine Fläche, nur die Rückfall-Linie.
            C["cycbg"] = curses.A_DIM
            C["cyc_is_bg"] = False
            C["kal_glas"] = None               # Glas braucht Farben
            for motiv in MOTIV_FARBEN["night"]:   # Tagesphasen: leise
                C["k_m_" + motiv] = curses.A_DIM
            return
        c256 = curses.COLORS >= 256
        th = THEMES[tname]
        bg = th["bg256"] if c256 else th["bg8"]
        for i, r in enumerate(ROLES, start=1):
            if r == "band":
                continue                       # eigener Hintergrund, siehe unten
            c8, c2, extra = th[r]
            fg = c2 if c256 else c8
            # 8-Farben: reinweißer Text geht nur via A_BOLD (bright white)
            if not c256 and fg == curses.COLOR_WHITE and r in ("dim", "ink", "bright"):
                extra |= curses.A_BOLD
            curses.init_pair(i, fg, bg)
            C[r] = curses.color_pair(i) | extra
        # Schlaf-Bande: GEFÄRBTER HINTERGRUND, kein Vordergrund. curses kennt
        # keine Schichten — "hinter den Kurven" heißt: die Zelle bekommt eine
        # bg-Farbe, Punkt/Kurve wird als Glyph DAVOR in dieselbe Zelle gesetzt.
        # Echtes bg-Färben geht nur mit 256 Farben; sonst Schattenblock ▒.
        bi = ROLES.index("band") + 1
        pp = len(ROLES) + 1                # nächstes freies Farbpaar
        if c256:
            curses.init_pair(bi, th["band_fg"], th["band_bg"])
            C["band"] = curses.color_pair(bi)
            C["band_is_bg"] = True
            # "Auf-Band"-Varianten: gleiche fg jeder Rolle, aber band-bg. Eine
            # Kurve, die DURCH die Bande läuft, wird damit gezeichnet → ihr Glyph
            # liegt sichtbar VOR dem Band, statt ein Loch (Theme-bg) zu stanzen.
            for r in ROLES:
                if r in ("band", "ink"):
                    continue
                _c8, c2, extra = th[r]
                curses.init_pair(pp, c2, th["band_bg"])
                C[r + "@band"] = curses.color_pair(pp) | extra
                pp += 1
            # Banden-KANTE als Vordergrund: band-bg-Farbe als fg auf Theme-bg.
            # Damit lassen sich Halbblöcke ▀/▄ am oberen/unteren Rand der Schlaf-
            # Bande in Bandfarbe zeichnen → sub-zellen-feine Ränder (sonst schnappt
            # der Balken auf ganze Zeilen ≈ 2–3 h und wirkt grob/hackig).
            curses.init_pair(pp, th["band_bg"], bg)
            C["band_edge"] = curses.color_pair(pp)
            pp += 1
        else:
            C["band"] = C["faint"]
            C["band_is_bg"] = False
        # Zyklus-Fenster (PMS-Woche + erwarteter Start) im Graphen: nach genau
        # demselben Muster wie die Schlaf-Bande eine ZELLEN-HINTERGRUNDfarbe,
        # damit es HINTER den Werten liegt statt als Linie davor. Dazu wieder
        # "Auf-Fläche"-Varianten jeder Rolle, sonst stanzt jeder Punkt, der
        # durchs Fenster läuft, ein Loch in die Tönung.
        # Die Schlaf-Bande hat Vorrang: sie wird SPÄTER gemalt und überschreibt
        # die Zyklus-Fläche (siehe draw_overlay).
        if c256 and curses.COLOR_PAIRS >= pp + len(ROLES) + 10:
            curses.init_pair(pp, th["cyc"][1], th["cyc_bg"])
            C["cycbg"] = curses.color_pair(pp)
            C["cyc_is_bg"] = True
            pp += 1
            for r in ROLES:
                if r in ("band", "ink"):
                    continue
                _c8, c2, extra = th[r]
                curses.init_pair(pp, c2, th["cyc_bg"])
                C[r + "@cyc"] = curses.color_pair(pp) | extra
                pp += 1
            # Halbblock-Kante der Schlaf-Bande, wenn sie IN der Zyklus-Fläche
            # liegt: Bandfarbe als fg auf Zyklus-bg — sonst risse die Kante
            # ein Loch (Theme-bg) in die Tönung.
            curses.init_pair(pp, th["band_bg"], th["cyc_bg"])
            C["band_edge@cyc"] = curses.color_pair(pp)
            pp += 1
        else:
            # 8 Farben (oder zu wenig Farbpaare): keine Fläche möglich →
            # gepunktete Senkrechte im Vordergrund als Rückfallebene.
            C["cycbg"] = C["cyc"]
            C["cyc_is_bg"] = False
        # Ombre-Rampe der Sidebar-Liste: eigene Grau-Paare (nur 256-Farben),
        # sonst zweistufiger A_DIM-Fallback.
        if c256:
            C["ombre"] = []
            for g in th.get("ombre", [245]):
                curses.init_pair(pp, g, bg)
                C["ombre"].append(curses.color_pair(pp))
                pp += 1
        else:
            C["ombre"] = [C["dim"], C["dim"], C["faint"],
                          C["faint"], C["faint"] | curses.A_DIM]
        # Klaviertasten (Klavier-Werkzeug): die schwarze Taste kriegt einen
        # eigenen HINTERGRUND statt A_REVERSE. Invertiert wäre ihr Buchstabe in
        # Theme-Hintergrundfarbe gezeichnet und stanzte ein Loch in die Taste;
        # so bleibt die Taste eine geschlossene Fläche mit heller Schrift darauf.
        # Gedrückt wird die Fläche zur Akzentfarbe (Schrift dann dunkel).
        if c256:
            curses.init_pair(pp, 231, th.get("key_bg", 16))
            C["key_black"] = curses.color_pair(pp)
            pp += 1
            curses.init_pair(pp, th.get("key_bg", 16), th["acc"][1])
            C["key_press"] = curses.color_pair(pp)
        else:
            # 8 Farben: schwarze Fläche, weiße Schrift nur via A_BOLD.
            curses.init_pair(pp, curses.COLOR_WHITE, curses.COLOR_BLACK)
            C["key_black"] = curses.color_pair(pp) | curses.A_BOLD
            pp += 1
            curses.init_pair(pp, curses.COLOR_BLACK, th["acc"][0])
            C["key_press"] = curses.color_pair(pp)
        pp += 1
        # Kalender: eine Tabelle für alle Ansichten (farben.KAL).
        echt = curses.COLORS >= (1 << 24)

        def durchscheinend(farbe, deckkraft):
            """`farbe` zu `deckkraft` Anteil über den Theme-Grund gelegt."""
            a, g = pixel.xterm_rgb(farbe), pixel.xterm_rgb(th["bg256"])
            rgb = tuple(round(x * deckkraft + y * (1 - deckkraft)) for x, y in zip(a, g))
            if echt:
                return max(8, (rgb[0] << 16) | (rgb[1] << 8) | rgb[2])
            n = pixel.rgb_256(pixel.bunt(rgb))
            # Tags sind die Pastelle schon die hellsten der 256: landet die
            # Mischung wieder auf der Ausgangsfarbe, den nächsten helleren Ton
            # nehmen (notfalls fast Weiß — dann trägt nur die Schrift die Farbe).
            return pixel.rgb_256(rgb) if n == farbe else n
        def rgb(farbe):
            """Farbnummer (256er oder 24 Bit aus durchscheinend) → RGB."""
            if farbe > 255:
                return (farbe >> 16 & 255, farbe >> 8 & 255, farbe & 255)
            return pixel.xterm_rgb(farbe)
        # Glas (Ebene „uncommitted", kalender.py _glas_attr): zu jeder Rolle,
        # die unter einer Glasscheibe liegen kann, ihre Schrift- und Grundfarbe
        # als RGB — dort wird der Grund mit der Kursfarbe gemischt.
        paare, flaeche = {}, {}
        if c256:
            for r in ROLES:
                if r != "band":
                    paare[r] = (rgb(th[r][1]), rgb(bg), th[r][2])
        for name, (schrift, f_grund, f_schrift, rueck) in KAL[tname].items():
            if c256:
                dk = DECKKRAFT[tname]
                k = "k_" + name
                paare[k] = (rgb(schrift), rgb(bg), 0)
                paare[k + "_inv"] = (rgb(f_schrift), rgb(f_grund), 0)
                paare[k + "_blass"] = (rgb(durchscheinend(schrift, dk["schrift"])), rgb(bg), 0)
                flaeche[k] = rgb(f_grund)
                curses.init_pair(pp, schrift, bg)
                C["k_" + name] = curses.color_pair(pp)
                curses.init_pair(pp + 1, f_schrift, f_grund)
                C["k_" + name + "_inv"] = curses.color_pair(pp + 1)
                # „uncommitted": dieselbe Farbe, durchscheinend auf dem Grund
                # (Rückfall, wo kein Glas geht — siehe kalender.py _glas_attr)
                curses.init_pair(pp + 2, durchscheinend(schrift, dk["schrift"]), bg)
                C["k_" + name + "_blass"] = curses.color_pair(pp + 2)
                curses.init_pair(pp + 3, schrift if tname == "night"
                                 else durchscheinend(schrift, dk["schrift"]),
                                 durchscheinend(f_grund, dk["flaeche"]))
                C["k_" + name + "_blass_inv"] = curses.color_pair(pp + 3)
                pp += 4
            else:
                C["k_" + name] = C[rueck]
                C["k_" + name + "_inv"] = C[rueck] | curses.A_REVERSE
                C["k_" + name + "_blass"] = C[rueck] | curses.A_DIM
                C["k_" + name + "_blass_inv"] = C[rueck] | curses.A_DIM | curses.A_REVERSE
        # Tagesphasen (farben.MOTIV_FARBEN, Hintergrund der Woche): je Motiv
        # nur eine gedämpfte Schrift auf dem Grund — ein Paar pro Motiv. Auch
        # in `paare`, damit Glas (uncommitted) über einem Muster mischen kann.
        for motiv, farbe in MOTIV_FARBEN[tname].items():
            k = "k_m_" + motiv
            if c256:
                curses.init_pair(pp, farbe, bg)
                C[k] = curses.color_pair(pp)
                paare[k] = (rgb(farbe), rgb(bg), 0)
                pp += 1
            else:
                C[k] = C["faint"]
        C["kal_glas"] = ({"thema": tname, "paare": paare, "flaeche": flaeche}
                         if c256 else None)
        # Tastenbeleuchtung: je eine Farbe für den RAND der schwarzen Keycap
        # (Neon auf der schwarzen Fläche) und dieselbe Farbe als Glühen für die
        # Buchstaben der weißen Tasten (auf Theme-Grund). Ohne 256 Farben gibt
        # es das nicht — dann bleiben die Listen leer und alles sieht aus wie
        # vorher, statt in acht Farben zu raten.
        C["keyframe"], C["keyglow"] = [], []
        if c256:
            for col in th.get("key_neon", []):
                curses.init_pair(pp, col, th.get("key_bg", 16))
                C["keyframe"].append(curses.color_pair(pp) | curses.A_BOLD)
                pp += 1
                curses.init_pair(pp, col, bg)
                C["keyglow"].append(curses.color_pair(pp) | curses.A_BOLD)
                pp += 1
        # Pixel-Baustein: Theme-Hintergrund als RGB + freie Farbpaare ab pp.
        # Paare über 255 passen nicht ins curses-Attribut → Budget bis 255.
        C["pix_bg"] = pixel.xterm_rgb(th["bg256"]) if c256 else None
        C["pix_true"] = curses.COLORS >= (1 << 24)
        PIX["base"] = pp
        PIX["top"] = min(255, curses.COLOR_PAIRS - 1)
        PIX["pairs"].clear()
        # leere Zellen (erase) bekommen den Theme-Hintergrund
        stdscr.bkgd(" ", C["ink"])

    # ── Theme-Modus: auto (nach Uhrzeit) | day | night. Taste 't' zykliert. ──
    #
    # EINE QUELLE DER WAHRHEIT: die Datei ~/.config/zentrale/theme. Die TUI hält
    # KEINE eigene Modus-Variable mehr.
    #
    # Warum das wichtig ist (und warum es vorher glitchte): der Modus lag früher
    # doppelt vor — als lokale Variable `theme_mode` UND als Datei —, abgeglichen
    # über drei Hilfspuffer (zuletzt geschriebener Modus, zuletzt gesehene mtime,
    # zuletzt gemeldete Farbe). Dieser Abgleich ist nicht atomar: zwischen „Taste
    # ändert die Variable" und „Schleife schreibt die Datei" liegt ein Fenster, in
    # dem ein Lesevorgang die Variable wieder überschrieb. Ergebnis war genau das
    # beobachtete Bild — das Theme sprang kurz um und wieder zurück, und im
    # Protokoll standen Fremd-Einträge mit exakt den Werten, die die TUI selbst
    # eine Zeile vorher geschrieben hatte: sie las ihr eigenes Echo.
    #
    # Jetzt gibt es nichts mehr abzugleichen. Lesen heißt Datei lesen (per mtime
    # gecacht, damit es billig bleibt), Umschalten heißt Datei schreiben. Der
    # Cache ist keine zweite Wahrheit: er wird bei jeder fremden mtime verworfen
    # und nie gegen die Datei behauptet. Damit ist eine Rückkopplung strukturell
    # unmöglich, statt nur unwahrscheinlich gemacht.
    # Die Logik selbst liegt in core/theme.py — dort ist sie testbar, statt in
    # einer 8000-Zeilen-Funktion vergraben zu sein (und sie kennt
    # ZENTRALE_THEME_FILE, sodass Tests nie die echte Konfiguration anfassen).

    def theme_mode_now(self):
        """Aktueller Modus — kommt immer aus der Datei."""
        _theme = self._theme
        return _theme.mode()

    def set_theme_mode(self, neu, quelle="tui"):
        """Modus setzen = WUNSCH-Datei schreiben. Mehr ist hier nicht zu tun.

        Das Auflösen und das Anstoßen der Applier macht `zentrale-themed`: der
        Dienst hängt per inotify an der Datei und ist schneller da, als die
        TUI ihren nächsten Bildaufbau schafft.
        """
        _theme = self._theme
        _theme.set(neu, quelle)

    def cycle_theme(self):
        """Taste 't' bzw. '/theme' ohne Argument: auto → day → night → auto."""
        _theme = self._theme
        _theme.cycle()

    def resolved_theme(self):
        """Die geltende Farbe — kommt aus theme.now, also vom Dienst."""
        _theme = self._theme
        return _theme.resolved()

    def safe_addstr(self, y, x, text, attr=0):
        stdscr = self.stdscr
        h, w = stdscr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        # Zentrale Zeichen-Primitive → hier hart machen, dann ist der GANZE
        # Render-Pfad immun: alles zu str zwingen und Null-Bytes ersetzen
        # (curses.addstr wirft an \x00 ein ValueError, nicht curses.error).
        if not isinstance(text, str):
            text = str(text)
        if "\x00" in text:
            text = text.replace("\x00", " ")
        if x < 0:
            text = text[-x:]
            x = 0
        text = text[: max(0, w - x)]
        try:
            stdscr.addstr(y, x, text, attr)
        except (curses.error, ValueError):
            pass  # untere rechte Zelle wirft immer; ValueError = exotischer String

    def addclip(self, y, x, text, maxw, attr=0, strike=False):
        """Wie safe_addstr, aber kürzt vorher auf maxw — verhindert, dass
        z.B. lange stdout-Zeilen aus ihrer Box in die Nachbarspalte laufen.
        strike=True legt über jedes (schon gekürzte) Zeichen ein Combining-
        Overlay U+0336 → durchgestrichen (für abgehakte Einträge)."""
        safe_addstr, stdscr = self.safe_addstr, self.stdscr
        if maxw <= 0:
            return
        if not isinstance(text, str):
            text = str(text)
        s = text[:maxw]
        if strike and s:
            # Combining-Zeichen sind Null-Breite (hängen am Vorzeichen) → die
            # sichtbare Breite bleibt maxw. safe_addstr würde aber nach Codepoints
            # kürzen und die Hälfte abschneiden; darum hier direkt setzen.
            s = "".join(c + "̶" for c in s)
            h, w = stdscr.getmaxyx()
            if 0 <= y < h and 0 <= x < w:
                try:
                    stdscr.addstr(y, x, s, attr)
                except (curses.error, ValueError):
                    pass
            return
        safe_addstr(y, x, s, attr)

    def draw_box(self, y, x, h, w, title, title_attr=0):
        C, safe_addstr = self.C, self.safe_addstr
        if h < 2 or w < 2:
            return
        safe_addstr(y, x, "┌" + "─" * (w - 2) + "┐", C["faint"])
        for i in range(1, h - 1):
            safe_addstr(y + i, x, "│", C["faint"])
            safe_addstr(y + i, x + w - 1, "│", C["faint"])
        safe_addstr(y + h - 1, x, "└" + "─" * (w - 2) + "┘", C["faint"])
        if title:
            safe_addstr(y, x + 2, " " + title.upper() + " ", title_attr or C["acc"])
