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
try:                                    # 24-Bit-Flächen nach refresh (2026-10-11)
    from tui import echtfarbe
except ImportError:
    import echtfarbe

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
        # Farbpaare des Pixel-Baustein: (fg, bg) → curses-Attribut, Nummern
        # PIX["base"] bis PIX["top"]. Seit 2026-10-21 nach Bildern verwaltet
        # (pix_attr): ist der Vorrat voll, wird das am längsten unbenutzte Paar
        # neu belegt — aber nur eins, das im laufenden Bild nicht vorkommt
        # (Paare sind Referenzen: umdefiniert färbt curses jede Zelle mit).
        # "platz": key → [Nummer, Bild der letzten Nutzung]; "bild" zählt
        # pix_neues_bild() hoch; "fest": Theme-Paare, die ein Pixel mitnutzt.
        self.PIX = {"pairs": {}, "base": 0, "top": 0, "voll": False,
                    "platz": {}, "bild": 0, "fest": {}}
        self.PIX_MODUS = (os.environ.get("ZENTRALE_PIXEL") or "mix").strip().lower()
        # 24-Bit-Flächen (2026-10-11, tui/echtfarbe.py): None = aus, dann
        # zeichnen alle über die 256er-Paare wie bisher. Wer echt malt, ruft
        # echt_malen(); die Hauptschleife ruft nach refresh nachmalen().
        self.echt = (echtfarbe.Uebermalung()
                     if has_color and echtfarbe.truecolor_an() else None)

    def pix_farbe(self, rgb):
        """RGB → curses-Farbnummer: 24 Bit, wenn das Terminal es kann (auf
        16er-Stufen gerundet, damit die Paare reichen), sonst die nächste der 256."""
        C = self.C
        if C.get("pix_true"):
            r, g, b = (min(255, round(v / 16) * 16) for v in rgb)
            n = (r << 16) | (g << 8) | b
            return n if n >= 8 else 8          # 0–7 wären Palettenfarben
        return pixel.rgb_256(rgb)

    def pix_neues_bild(self):
        """Zu Beginn jedes Bildes (nach erase): ab jetzt ist frei, was das
        neue Bild nicht wieder anfordert."""
        PIX = self.PIX
        PIX["bild"] = PIX.get("bild", 0) + 1
        PIX["voll"] = False

    def pix_frei(self):
        """Wie viele Pixel-Paare das laufende Bild noch neu anlegen kann."""
        PIX = self.PIX
        jetzt = PIX.get("bild", 0)
        im_bild = sum(1 for k, (_n, b) in PIX.get("platz", {}).items()
                      if b == jetzt and k in PIX["pairs"])
        return max(0, PIX["top"] - PIX["base"] + 1 - im_bild)

    def pix_attr(self, fg, bg):
        PIX, pix_farbe = self.PIX, self.pix_farbe
        key = (pix_farbe(fg), pix_farbe(bg))
        fest = PIX.get("fest")
        if fest and not self.C.get("pix_true"):
            attr = fest.get(key)             # dieselben Farben hat das Theme schon
            if attr is not None:
                return attr
        pairs = PIX["pairs"]
        platz = PIX.setdefault("platz", {})
        jetzt = PIX.setdefault("bild", 0)
        attr = pairs.get(key)
        if attr is not None:
            pairs[key] = pairs.pop(key)       # ans Ende: zuletzt benutzt
            if key in platz:
                platz[key][1] = jetzt
            return attr
        n = self._pix_platz(jetzt)
        if n is None:                         # ein Bild braucht mehr Paare als es gibt
            PIX["voll"] = True
            return self._pix_naechstes(key)
        try:
            curses.init_pair(n, key[0], key[1])
            attr = curses.color_pair(n)
        except curses.error:
            return self._pix_naechstes(key)
        pairs[key] = attr
        platz[key] = [n, jetzt]
        return attr

    def pix_genau(self, fg, bg):
        """Wie pix_attr, aber None statt einer Ersatzfarbe, wenn es für
        genau diese Farben kein Paar gibt (Vorrat voll) — für Ansichten mit
        eigenem Rückfall (Kalender-Glas)."""
        attr = self.pix_attr(fg, bg)
        PIX = self.PIX
        key = (self.pix_farbe(fg), self.pix_farbe(bg))
        if key in PIX["pairs"]:
            return attr
        if not self.C.get("pix_true") and key in (PIX.get("fest") or {}):
            return attr
        return None

    def _pix_platz(self, jetzt):
        """Eine freie Paarnummer: erst nie vergebene, sonst die des am
        längsten unbenutzten Paars, das im laufenden Bild nicht vorkommt.
        None, wenn alle im laufenden Bild gebraucht werden."""
        PIX = self.PIX
        pairs, platz = PIX["pairs"], PIX["platz"]
        if len(platz) != len(pairs) or any(k not in pairs for k in platz):
            # von außen geleert/geändert (Theme, Tests): Buch neu abgleichen
            for k in [k for k in platz if k not in pairs]:
                del platz[k]
        belegt = {n for n, _b in platz.values()}
        if len(belegt) < PIX["top"] - PIX["base"] + 1:
            for n in range(PIX["top"], PIX["base"] - 1, -1):
                if n not in belegt:
                    return n
        for k in pairs:                       # vorne = am längsten unbenutzt
            if k in platz:
                n, b = platz[k]
                if b == jetzt:
                    return None               # alles davor/dahinter ist jünger
                del pairs[k], platz[k]
                return n
        return None

    def _pix_farbe_rgb(self, n):
        if self.C.get("pix_true"):
            return (n >> 16 & 255, n >> 8 & 255, n & 255)
        return pixel.xterm_rgb(n)

    def _pix_naechstes(self, key):
        """Letzter Ausweg: das vorhandene Pixel-Paar, dessen Farben dem
        gewünschten am nächsten liegen (statt Bernstein)."""
        PIX, rgb = self.PIX, self._pix_farbe_rgb
        kandidaten = list(PIX["pairs"].items())
        if not kandidaten and not self.C.get("pix_true"):
            kandidaten = list(PIX.get("fest", {}).items())   # Theme-Paare erst ganz zuletzt
        if not kandidaten:
            return self.C.get("amber", 0)
        f, h = rgb(key[0]), rgb(key[1])

        def abstand(k):
            a, b = rgb(k[0]), rgb(k[1])
            return sum((x - y) ** 2 for x, y in zip(f + h, a + b))
        return min(kandidaten, key=lambda kv: abstand(kv[0]))[1]

    def apply_theme(self, tname):
        C, PIX, has_color, stdscr = self.C, self.PIX, self.has_color, self.stdscr
        if not has_color:
            for r in ROLES:
                C[r] = 0
            C["bright"] = curses.A_BOLD
            C["sel"] = curses.A_BOLD | curses.A_REVERSE   # Farbrolle „auswahl"
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
        # Feste Paare über paar(): gleiche (Schrift, Grund) teilen sich EIN
        # Paar (2026-10-21). Vorher bekam jede Rolle/Kalenderfarbe ihr eigenes,
        # auch wenn es dasselbe Farbenpaar war — 65 Doppelte im Nachtthema,
        # die dem Pixel-Vorrat fehlten (Auge im leeren Chat lief über).
        # Sichtbar ändert sich nichts: gleiche Farben, gleiches Paar.
        fest = {}
        pp = 1                             # nächstes freies Farbpaar

        def paar(fg, hg):
            nonlocal pp
            n = fest.get((fg, hg))
            if n is None:
                n = fest[(fg, hg)] = pp
                curses.init_pair(n, fg, hg)
                pp += 1
            return curses.color_pair(n)
        for r in ROLES:
            if r == "band":
                continue                       # eigener Hintergrund, siehe unten
            c8, c2, extra = th[r]
            fg = c2 if c256 else c8
            # 8-Farben: reinweißer Text geht nur via A_BOLD (bright white)
            if not c256 and fg == curses.COLOR_WHITE and r in ("dim", "ink", "bright"):
                extra |= curses.A_BOLD
            C[r] = paar(fg, bg) | extra
        # Schlaf-Bande: GEFÄRBTER HINTERGRUND, kein Vordergrund. curses kennt
        # keine Schichten — "hinter den Kurven" heißt: die Zelle bekommt eine
        # bg-Farbe, Punkt/Kurve wird als Glyph DAVOR in dieselbe Zelle gesetzt.
        # Echtes bg-Färben geht nur mit 256 Farben; sonst Schattenblock ▒.
        if c256:
            C["band"] = paar(th["band_fg"], th["band_bg"])
            C["band_is_bg"] = True
            # "Auf-Band"-Varianten: gleiche fg jeder Rolle, aber band-bg. Eine
            # Kurve, die DURCH die Bande läuft, wird damit gezeichnet → ihr Glyph
            # liegt sichtbar VOR dem Band, statt ein Loch (Theme-bg) zu stanzen.
            for r in ROLES:
                if r in ("band", "ink"):
                    continue
                _c8, c2, extra = th[r]
                C[r + "@band"] = paar(c2, th["band_bg"]) | extra
            # Banden-KANTE als Vordergrund: band-bg-Farbe als fg auf Theme-bg.
            # Damit lassen sich Halbblöcke ▀/▄ am oberen/unteren Rand der Schlaf-
            # Bande in Bandfarbe zeichnen → sub-zellen-feine Ränder (sonst schnappt
            # der Balken auf ganze Zeilen ≈ 2–3 h und wirkt grob/hackig).
            C["band_edge"] = paar(th["band_bg"], bg)
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
            C["cycbg"] = paar(th["cyc"][1], th["cyc_bg"])
            C["cyc_is_bg"] = True
            for r in ROLES:
                if r in ("band", "ink"):
                    continue
                _c8, c2, extra = th[r]
                C[r + "@cyc"] = paar(c2, th["cyc_bg"]) | extra
            # Halbblock-Kante der Schlaf-Bande, wenn sie IN der Zyklus-Fläche
            # liegt: Bandfarbe als fg auf Zyklus-bg — sonst risse die Kante
            # ein Loch (Theme-bg) in die Tönung.
            C["band_edge@cyc"] = paar(th["band_bg"], th["cyc_bg"])
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
                C["ombre"].append(paar(g, bg))
        else:
            C["ombre"] = [C["dim"], C["dim"], C["faint"],
                          C["faint"], C["faint"] | curses.A_DIM]
        # Klaviertasten (Klavier-Werkzeug): die schwarze Taste kriegt einen
        # eigenen HINTERGRUND statt A_REVERSE. Invertiert wäre ihr Buchstabe in
        # Theme-Hintergrundfarbe gezeichnet und stanzte ein Loch in die Taste;
        # so bleibt die Taste eine geschlossene Fläche mit heller Schrift darauf.
        # Gedrückt wird die Fläche zur Akzentfarbe (Schrift dann dunkel).
        if c256:
            C["key_black"] = paar(231, th.get("key_bg", 16))
            C["key_press"] = paar(th.get("key_bg", 16), th["acc"][1])
        else:
            # 8 Farben: schwarze Fläche, weiße Schrift nur via A_BOLD.
            C["key_black"] = paar(curses.COLOR_WHITE, curses.COLOR_BLACK) | curses.A_BOLD
            C["key_press"] = paar(curses.COLOR_BLACK, th["acc"][0])
        # Kalender: eine Tabelle für alle Ansichten (farben.KAL).
        echt = curses.COLORS >= (1 << 24)

        def durchscheinend(farbe, deckkraft, grau=False):
            """`farbe` zu `deckkraft` Anteil über den Theme-Grund gelegt.
            256 Farben: die nächste BUNTE (Schrift behält den Farbton) —
            mit `grau` die nächste überhaupt, Graurampe erlaubt (Flächen:
            ein grauer Hauch ist leiser als jeder bunte Ton)."""
            a, g = pixel.xterm_rgb(farbe), pixel.xterm_rgb(th["bg256"])
            rgb = pixel.mix(g, a, deckkraft)
            if echt:
                return max(8, (rgb[0] << 16) | (rgb[1] << 8) | rgb[2])
            n = pixel.rgb_256(rgb if grau else pixel.bunt(rgb))
            # Tags sind die Pastelle schon die hellsten der 256: landet die
            # Mischung wieder auf der Ausgangsfarbe, den nächsten helleren Ton
            # nehmen (notfalls fast Weiß — dann trägt nur die Schrift die Farbe).
            return pixel.rgb_256(rgb) if n == farbe else n

        def leise(farbe, deckkraft, grund):
            """Schrift so durchscheinend wie `deckkraft`, aber lesbar: so
            lange kräftiger, bis sie ≥ 3:1 gegen `grund` hat."""
            for d in [round(deckkraft + i / 20, 2) for i in range(int((1 - deckkraft) * 20) + 1)]:
                n = durchscheinend(farbe, d)
                if pixel.kontrast(rgb(n), rgb(grund)) >= 3:
                    return n
            return farbe

        def glas_flaeche(farbe, deckkraft):
            """Fläche als grauer/bunter Hauch, aber nie genau der Grund."""
            for d in (deckkraft, deckkraft + 0.1, deckkraft + 0.2, deckkraft + 0.3):
                n = durchscheinend(farbe, d, grau=True)
                if n != bg:
                    return n
            return n
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
                blass = leise(schrift, dk["schrift"], bg)
                paare[k + "_blass"] = (rgb(blass), rgb(bg), 0)
                flaeche[k] = rgb(f_grund)
                C["k_" + name] = paar(schrift, bg)
                C["k_" + name + "_inv"] = paar(f_schrift, f_grund)
                # „uncommitted": dieselbe Farbe, durchscheinend auf dem Grund
                # (Rückfall, wo kein Glas geht — siehe kalender.py _glas_attr)
                C["k_" + name + "_blass"] = paar(blass, bg)
                hauch = glas_flaeche(f_grund, dk["flaeche"])
                C["k_" + name + "_blass_inv"] = paar(leise(schrift, dk["schrift"], hauch), hauch)
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
                C[k] = paar(farbe, bg)
                paare[k] = (rgb(farbe), rgb(bg), 0)
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
                C["keyframe"].append(paar(col, th.get("key_bg", 16)) | curses.A_BOLD)
                C["keyglow"].append(paar(col, bg) | curses.A_BOLD)
        # Pixel-Baustein: Theme-Hintergrund als RGB + freie Farbpaare ab pp.
        # Paare über 255 passen nicht ins curses-Attribut → Budget bis 255.
        C["pix_bg"] = pixel.xterm_rgb(th["bg256"]) if c256 else None
        C["pix_true"] = curses.COLORS >= (1 << 24)
        PIX["base"] = pp
        PIX["top"] = min(255, curses.COLOR_PAIRS - 1)
        PIX["pairs"].clear()
        PIX["platz"] = {}
        # feste Paare, die ein Pixel mitbenutzen darf: nur 256er-Nummern
        # (mit 24 Bit sind Pixel-Farben RGB-Zahlen, Theme-Farben nicht)
        PIX["fest"] = ({k: curses.color_pair(n) for k, n in fest.items()}
                       if c256 else {})
        # leere Zellen (erase) bekommen den Theme-Hintergrund
        stdscr.bkgd(" ", C["ink"])
        if self.echt is not None:        # neue Paare/Grund: echte Flächen neu schreiben
            self.echt.ungueltig()

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

    # ── 24-Bit-Flächen (2026-10-11, tui/echtfarbe.py) ───────────────────
    def echt_malen(self, y, x, zeilen):
        """Zellen (zeichen, fg_rgb, bg_rgb) ab y, x nach dem refresh in 24 Bit
        schreiben. curses bekommt dort einen gleichbleibenden Platzhalter
        (Leerzeichen im Theme-Grund), damit es die Zellen nicht anfasst.
        → False, wenn 24 Bit aus ist (dann selbst über pix_attr zeichnen)."""
        if self.echt is None:
            return False
        platz = self.C.get("ink", 0)
        for r, zeile in enumerate(zeilen):
            self.safe_addstr(y + r, x, " " * len(zeile), platz)
        H, W = self.stdscr.getmaxyx()
        if 0 <= y and y + len(zeilen) <= H and 0 <= x and x + max(
                (len(z) for z in zeilen), default=0) <= W - 1:
            self.echt.malen(y, x, zeilen, self.stdscr.inch(y, x) if zeilen else None)
        return True

    def nachmalen(self):
        """Nach stdscr.refresh(): die 24-Bit-Flächen dieses Bildes schreiben."""
        if self.echt is not None:
            self.echt.nachmalen(self.stdscr)

    def groesse_neu(self):
        """Nach KEY_RESIZE: Zellform neu messen, Flächen neu schreiben."""
        pixel.zellmass_vergessen()
        if self.echt is not None:
            self.echt.ungueltig()
