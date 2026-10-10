# tui/ansichten/farben.py
#
# Die Paletten der TUI: welche Rollen es gibt (acc, warn, dim …) und welche
# Farbe jede Rolle bei Tag und bei Nacht hat. Reine Daten — das Anlegen der
# curses-Farbpaare macht Kontext.apply_theme (kontext.py). Stand bis
# 06.10.2026 als lokale Variablen in run_ui (memory/system/tui_bauplan.md).

import curses


# ── Themes (hell/dunkel) ────────────────────
# Pro Rolle: (8-Farben-fg, 256-Farben-fg, extra-Attribut). bg pro Theme.
# Light-Mode: KEIN Gelb auf Weiß (unlesbar) → warn/num = rot/blau.
# Dark-Mode: ULTRA HIGH CONTRAST — hartes Schwarz, reinweißer Text (231),
# Rahmen ein klar sichtbares Grau (245). Grün NIE bold (= sonst Neon),
# gedämpftes Salbeigrün (108) statt grellem Standard-Grün.
ROLES = ["acc", "warn", "net", "graph", "event", "audio", "hook", "span",
         "num", "amber", "amberhi", "amberdk", "cyc", "dim", "faint", "bright", "ink", "band",
         "kal"]

# Farbrollen der Apps (core/farbrollen.py ROLLEN, 2026-10-10): eine App sagt
# nur, was ein Stück BEDEUTET; hier entscheidet die TUI, welche ihrer Rollen
# oben es zeichnet. Muss JEDE Rolle des Wörterbuchs abdecken (Test:
# tests/test_farbrollen.py); Unbekanntes zeichnet die TUI als „text".
# heute = Kalender-Akzent, wie der heutige Tag im Kalender selbst.
FARBROLLEN = {"text": "ink", "leise": "faint", "kopf": "dim", "betont": "bright",
              "heute": "kal", "spanne": "span", "mehr": "acc", "warnung": "warn",
              "erledigt": "faint"}


THEMES = {
    "night": {
        "bg8": curses.COLOR_BLACK, "bg256": 16,
        #         8-Farbe              256   extra
        "acc":   (curses.COLOR_GREEN,   108, 0),
        "warn":  (curses.COLOR_YELLOW,  226, curses.A_BOLD),
        "net":   (curses.COLOR_CYAN,    51,  curses.A_BOLD),
        "graph": (curses.COLOR_MAGENTA, 213, curses.A_BOLD),
        "event": (curses.COLOR_GREEN,   108, 0),
        "audio": (curses.COLOR_GREEN,   108, 0),
        "hook":  (curses.COLOR_YELLOW,  215, 0),
        "span":  (curses.COLOR_YELLOW,  216, 0),    # Mehrtages-Klammer: weiches Orange
        # Kalender-Akzent. Bis 09.10.2026 calcurse-Rot 196; jetzt dieselbe
        # Farbe wie KAL["akzent"] (unten), damit Kasten und Ansichten eins sind.
        "kal":   (curses.COLOR_GREEN,   47,  0),    # Kalender-Akzent = KAL["akzent"] (Neongrün)
        "num":   (curses.COLOR_YELLOW,  222, 0),
        "amber": (curses.COLOR_YELLOW,  214, curses.A_BOLD),  # Fokus-Leiste: Bernstein
        # Bernsteinleiste (Listen-Werkzeug): Glanzpixel + Schatten/leere Fassung
        "amberhi": (curses.COLOR_YELLOW, 222, curses.A_BOLD),
        "amberdk": (curses.COLOR_YELLOW, 136, 0),
        # Zyklus/PMS (aus dem »periode«-Graphen): weiches Altrosa, bewusst
        # NICHT bold — die Vorhersage soll dastehen, nicht rufen.
        "cyc":   (curses.COLOR_MAGENTA, 175, 0),
        "dim":   (curses.COLOR_WHITE,   231, 0),    # normaler Text: reinweiß = max Kontrast
        "faint": (curses.COLOR_WHITE,   245, 0),    # Rahmen: sichtbares Grau (nicht gedimmt)
        "bright":(curses.COLOR_WHITE,   231, curses.A_BOLD),
        "ink":   (curses.COLOR_WHITE,   231, 0),
        # Schlaf-Bande: gedämpftes Dunkelmagenta als ZELLEN-HINTERGRUND
        "band_fg": 245, "band_bg": 53,
        # Zyklus-Fenster im Graphen: dunkles Rosé als ZELLEN-HINTERGRUND —
        # rötlich gegen das Magenta der Schlaf-Bande, damit die beiden
        # Flächen nicht verwechselbar sind, wo sie sich kreuzen.
        "cyc_bg": 52,
        # Klavier: Fläche der schwarzen Taste. Auf schwarzem Grund NICHT 16
        # (dann verschwände die Taste), sondern ein Hauch heller.
        "key_bg": 236,
        # Leuchtfarben der Keycaps: im Dunkeln echtes Neon (Cyan, Magenta,
        # Grün, Gelb, Orange, Pink, Violett) — jede Taste kriegt eine, im
        # Schimmer-Modus wandern sie durch. Bewusst grell: das ist der
        # einzige Ort in der TUI, wo Neon erwünscht ist.
        "key_neon": [51, 201, 46, 226, 208, 199, 129],
        # Ombre der Sidebar-Liste: 256-Grau-Rampe, die nach unten in den
        # (schwarzen) Hintergrund verblasst → „weiter unten = transparenter".
        "ombre": [252, 246, 241, 237, 235],
    },
    "day": {
        "bg8": curses.COLOR_WHITE, "bg256": 231,
        "acc":   (curses.COLOR_GREEN,   65,  0),
        "warn":  (curses.COLOR_RED,     124, curses.A_BOLD),
        "net":   (curses.COLOR_BLUE,    26,  curses.A_BOLD),
        "graph": (curses.COLOR_MAGENTA, 90,  curses.A_BOLD),
        "event": (curses.COLOR_GREEN,   65,  0),
        "audio": (curses.COLOR_GREEN,   65,  0),
        "hook":  (curses.COLOR_RED,     130, 0),
        "span":  (curses.COLOR_RED,     166, 0),    # Mehrtages-Klammer: kräftiges Orange (auf Weiss lesbar)
        "kal":   (curses.COLOR_GREEN,   29,  0),    # Kalender-Akzent = KAL["akzent"] (Salbei, dunkel genug)
        "num":   (curses.COLOR_BLUE,    26,  0),
        "amber": (curses.COLOR_YELLOW,  172, curses.A_BOLD),  # Fokus-Leiste: Bernstein (auf weiß lesbar)
        # Bernsteinleiste: Glanz heller, Schatten/Fassung dunkler (≥4,5:1 auf weiß)
        "amberhi": (curses.COLOR_YELLOW, 214, curses.A_BOLD),
        "amberdk": (curses.COLOR_YELLOW, 130, 0),
        # Zyklus/PMS: dasselbe Altrosa, auf Weiß dunkler gesetzt (lesbar).
        "cyc":   (curses.COLOR_MAGENTA, 132, 0),
        "dim":   (curses.COLOR_BLACK,   16,  0),    # schwarzer Text auf weiß
        "faint": (curses.COLOR_BLUE,    67,  0),    # Rahmen blau-grau (auf weiß sichtbar)
        "bright":(curses.COLOR_BLACK,   16,  curses.A_BOLD),
        "ink":   (curses.COLOR_BLACK,   16,  0),
        # Schlaf-Bande: hell-magenta angehauchtes Grau als ZELLEN-HINTERGRUND
        "band_fg": 240, "band_bg": 225,
        # Zyklus-Fenster im Graphen: blasses Rosé als ZELLEN-HINTERGRUND —
        # warm/rötlich, die Schlaf-Bande daneben violett: auch dort
        # unterscheidbar, wo beide Flächen aneinanderstoßen.
        "cyc_bg": 224,
        # Klavier: schwarze Taste auf weißem Grund darf echtes Schwarz sein.
        "key_bg": 16,
        # KEIN "key_neon" auf Papier: Leuchttasten sind eine Nacht-Sache.
        # Tagsüber bleibt die Keycap schlicht schwarz-weiß, 'L' hat hier
        # nichts zu färben (die TUI sagt das auch, wenn man es drückt).
        # Ombre der Sidebar-Liste: nach unten in den (weißen) Hintergrund
        # verblassend → Grau wird heller.
        "ombre": [238, 244, 248, 251, 253],
    },
}


# ── Kalender (alle drei Ansichten + Kasten) ─────────────────────────────
# Sasha, 09.10.2026: „das farbtheme in zentrale startansicht ist schön … der
# kalender passt nicht … mach ihn vorallem einheitlich". Also EIN Schema für
# A, B, C und den Eingabe-Kasten, in der Sprache der Startseite: nachts
# Neon auf Schwarz (zentrale-cyber), tagsüber Pastellflächen mit dunkler,
# pflanzlicher Schrift (zentrale-paper; Schrift ≥ 4,5:1 auf Weiß).
#
# Gleiche Art = gleiche Farbe in jeder Ansicht:
#   akzent   Kastentitel, Datumsköpfe, KW, aktiver Rahmen, Auswahl, Statuszeile
#   heute    der heutige Tag
#   t0..t11  Termine und Routinen: Farbe nach TITEL (Sasha, 10.10.2026: „im
#            stundenplan sind die meisten felder einfach grau, manche grell
#            türkis") — Analysis ist immer dieselbe Farbe, Serie oder einzeln
#   sp1..sp4 Spannen, reihum (nebeneinander unterscheidbar)
#   wochenende  Sa/So-Köpfe
# Pro Rolle: (Schrift, Fläche-Grund, Fläche-Schrift, Rückfall-Rolle für 8 Farben).
# Die TUI legt daraus C["k_<rolle>"] (Schrift auf Theme-Grund) und
# C["k_<rolle>_inv"] (die Fläche) an — kontext.Kontext.apply_theme.
KAL = {
    "night": {
        "akzent":     (47,  47,  16, "kal"),     # Neongrün (Sasha, 10.10.2026)
        "heute":      (227, 227, 16, "warn"),    # Neon-Gelb
        "t0":         (51,  51,  16, "net"),     # Cyan
        "t1":         (213, 213, 16, "graph"),   # Pink
        "t2":         (141, 141, 16, "graph"),   # Violett
        "t3":         (215, 215, 16, "span"),    # Orange
        "t4":         (117, 117, 16, "net"),     # Himmel
        "t5":         (210, 210, 16, "hook"),    # Lachs
        "t6":         (183, 183, 16, "cyc"),     # Lavendel
        "t7":         (159, 159, 16, "net"),     # Eis
        "t8":         (222, 222, 16, "num"),     # Gold
        "t9":         (174, 174, 16, "cyc"),     # Altrosa
        "t10":        (147, 147, 16, "graph"),   # Immergrün-Blau
        "t11":        (79,  79,  16, "acc"),     # Meergrün
        "sp1":        (141, 141, 16, "graph"),   # Violett
        "sp2":        (215, 215, 16, "span"),    # Orange
        "sp3":        (213, 213, 16, "graph"),   # Pink
        "sp4":        (117, 117, 16, "net"),     # Himmel
        "wochenende": (117, 117, 16, "net"),     # helles Cyan
    },
    "day": {
        "akzent":     (29,  151, 22,  "kal"),    # Salbei / Salbei-Fläche
        "heute":      (130, 229, 94,  "warn"),   # Ocker / Butter-Fläche
        "t0":         (24,  159, 23,  "net"),    # Petrol / Eis
        "t1":         (125, 225, 89,  "graph"),  # Beere / Blütenrosa
        "t2":         (54,  189, 54,  "graph"),  # Pflaume / Lavendel
        "t3":         (130, 223, 94,  "span"),   # Rinde / Pfirsich
        "t4":         (25,  153, 17,  "net"),    # Wasser / Himmel
        "t5":         (124, 217, 88,  "hook"),   # Ziegel / Lachs
        "t6":         (61,  183, 54,  "cyc"),    # Iris / Flieder
        "t7":         (23,  195, 23,  "net"),    # Tiefsee / Wasserhauch
        "t8":         (94,  230, 94,  "num"),    # Rinde / Creme
        "t9":         (131, 224, 88,  "cyc"),    # Rost / Rosenhauch
        "t10":        (18,  147, 18,  "graph"),  # Tinte / Immergrün
        "t11":        (22,  194, 22,  "acc"),    # Tanne / Blattgrün
        "sp1":        (54,  189, 54,  "graph"),  # Pflaume / Lavendel
        "sp2":        (94,  223, 94,  "span"),   # Rinde / Pfirsich
        "sp3":        (125, 225, 125, "graph"),  # Beere / Blütenrosa
        "sp4":        (25,  153, 17,  "net"),    # Wasser / Himmel
        "wochenende": (24,  153, 17,  "net"),    # Tiefwasser
    },
}


# ── Durchscheinend (Ebene „uncommitted", 10.10.2026) ────────────────────
# Sasha: „mehr transparent … nich schraffiert, so transparent aussehend".
# Terminals kennen keine Deckkraft — also wird die Farbe mit dem Theme-Grund
# gemischt, als läge sie zu einem Teil durchsichtig darüber, und auf die
# nächste der 256 Farben gerundet. DECKKRAFT: wie viel von der Farbe bleibt.
# Seit 10.10.2026 abends ist es Glas (Leinwand.glas, kalender.py _glas_attr):
# „glas" mischt den Grund JEDER Zelle darunter — Punktlinien, feste Termine —
# mit der Kursfarbe; „flaeche"/„schrift" bleiben der Rückfall (blasse Fläche,
# blasse Schrift in A und B). Nachts 0.30: die dunkelsten Töne der 256er, auf
# denen die Neon-Schrift des Labels noch ≥ 3:1 hat. Tags landet jede Mischung
# mit Weiß ohnehin wieder auf dem Pastell — durchscheinend wirkt es dort,
# weil Punkte und Termine darunter sichtbar bleiben.
DECKKRAFT = {"night": {"flaeche": 0.38, "schrift": 0.60, "glas": 0.30},
             "day":   {"flaeche": 0.45, "schrift": 0.70, "glas": 0.45}}
# Das Mischen selbst macht kontext.apply_theme (durchscheinend) bzw. für Glas
# kalender.py — beide runden über pixel.bunt, damit ein dunkles Orange orange
# bleibt statt auf die Graurampe zu fallen.


# ── Tagesphasen (Hintergrund der Woche, 10.10.2026) ─────────────────────
# Sasha: „eine leichte hintergrund ebene". Die Zeichen der Phasen
# (kalender_motive.MUSTER) stehen in einer GEDÄMPFTEN Farbe je Motiv auf dem
# Theme-Grund — leiser als die Punktlinien (nachts Grau 245 ≈ 7:1), aber
# sichtbar: nachts um 3–5:1 auf Schwarz, tags um 2–3:1 auf Weiß. Es ist
# Schmuck, keine Schrift; wer es kräftiger will, dreht hier.
# Pro Motiv: 256er-Farbe; ohne 256 Farben zeichnet alles in „faint".
MOTIV_FARBEN = {
    "night": {
        "nachthimmel": 61,    # Schieferblau
        "schlaf":      60,    # gedämpftes Violettgrau
        "essen":       95,    # Altrosa-Braun
        "sonne":       130,   # warmes Ocker
        "fokus":       30,    # stilles Petrol
        "sport":       29,    # Tannengrün
        "ruhe":        59,    # Grau
        "unterwegs":   24,    # Tiefblau
        "rueckfall":   59,
    },
    "day": {
        "nachthimmel": 104,   # Flieder-Grau
        "schlaf":      139,   # Malve
        "essen":       173,   # Terrakotta, hell
        "sonne":       172,   # Orange-Ocker
        "fokus":       73,    # Wasser
        "sport":       71,    # Blattgrün
        "ruhe":        247,   # Grau
        "unterwegs":   110,   # Taubenblau
        "rueckfall":   247,
    },
}
