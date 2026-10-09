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
        "kal":   (curses.COLOR_RED,     204, 0),    # Kalender-Akzent = KAL["akzent"] (Neon-Koralle)
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
        "kal":   (curses.COLOR_RED,     161, 0),    # Kalender-Akzent = KAL["akzent"] (Beere)
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
#   termin   Einmal-Termin (Schrift in A/B, Block in C)
#   routine  Wiederkehrendes — bewusst neutral, damit das Besondere leuchtet
#   sp1..sp4 Spannen und Ganztägiges, reihum (nebeneinander unterscheidbar)
#   wochenende  Sa/So-Köpfe
# Pro Rolle: (Schrift, Fläche-Grund, Fläche-Schrift, Rückfall-Rolle für 8 Farben).
# Die TUI legt daraus C["k_<rolle>"] (Schrift auf Theme-Grund) und
# C["k_<rolle>_inv"] (die Fläche) an — kontext.Kontext.apply_theme.
KAL = {
    "night": {
        "akzent":     (204, 204, 16, "kal"),     # Neon-Koralle (Farbe der Kalender-Pille)
        "heute":      (227, 227, 16, "warn"),    # Neon-Gelb
        "termin":     (51,  51,  16, "net"),     # Neon-Cyan
        "routine":    (231, 238, 252, "dim"),    # Weiß / dunkles Grau
        "sp1":        (141, 141, 16, "graph"),   # Violett (Pink ist schon der Akzent)
        "sp2":        (48,  48,  16, "acc"),     # Spring-Grün
        "sp3":        (215, 215, 16, "span"),    # Orange
        "sp4":        (219, 219, 16, "graph"),   # Flieder-Pink
        "wochenende": (117, 117, 16, "net"),     # helles Cyan
    },
    "day": {
        "akzent":     (161, 218, 89,  "kal"),    # Beere / Rosé-Fläche
        "heute":      (130, 229, 94,  "warn"),   # Ocker / Butter-Fläche
        "termin":     (25,  153, 17,  "net"),    # Wasserblau / Himmel-Fläche
        "routine":    (16,  254, 235, "dim"),    # Schwarz / Papiergrau
        "sp1":        (54,  189, 54,  "graph"),  # Pflaume / Lavendel
        "sp2":        (22,  158, 22,  "acc"),    # Tanne / Minze
        "sp3":        (94,  223, 94,  "span"),   # Rinde / Pfirsich
        "sp4":        (125, 225, 125, "graph"),  # Beere / Blütenrosa
        "wochenende": (24,  153, 17,  "net"),    # Tiefwasser
    },
}
