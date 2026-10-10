# tui/bausteine/stylebox.py
#
# Stylebox: ein Modal, in dem man das Aussehen eines Objekts einstellt
# (2026-10-10). Der Aufrufer reicht (a) den jetzigen Stil und (b) WELCHE
# Eigenschaften dieses Objekt anbietet — die Box zeigt genau die. Ein Termin
# bekommt Rahmen, Farben und Muster, eine Überschrift später vielleicht nur
# die Schrift­farbe.
#
# Kein eigenes Format: ein Stil ist ein dict CSS-Eigenschaft → CSS-Wert
# ({"border-style": "dashed", "border-color": "#ff8800", …}); Wörter und
# Prüfung stehen in core/stil.py, damit andere Oberflächen dieselbe Liste
# haben. Das Angebot ist eine Liste von CSS-Namen oder ein JSON Schema wie
# aus stil.schema() (dort darf der Aufrufer z. B. die Rahmen-Auswahl
# einschränken: oneOf/enum).
#
# Tasten: ↑↓ (Tab, Shift+Tab) Eigenschaft; ←→ oder Leertaste ändern eine
# Auswahl; bei einer Farbe öffnen Leertaste/→ den Farbwähler (# öffnet ihn
# gleich mit Hex-Feld); ⌫/Entf entfernt die Eigenschaft („—", nicht
# gesetzt; ändern setzt sie wieder), r setzt sie auf den Anfang zurück;
# Enter nimmt, Esc bricht ab. Icon hochladen steht da, ist aber gesperrt
# (readOnly) — es lässt sich nicht öffnen.
#
# `taste(ch)` → None | ("fertig", {geänderte css, entfernte = None}) |
# ("abbruch",); der Aufrufer wendet das mit stil.anwenden(alt, …) an; danach
# steht dasselbe in `ergebnis` (None bei Abbruch). Rein gerechnet:
# `zeilen()` (die Liste), `vorschau(b, h)` (das gestylte Kästchen als
# Zellen); gezeichnet über den Kontext: `zeichne(z, y, x, h, w)`.
# Doku: memory/system/bausteine_farbe_stil.md.

import curses

try:
    from tui import pixel
    from tui.bausteine.farbwaehler import Farbwaehler, ENTER, ESC, ZURUECK, leeren
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel
    from bausteine.farbwaehler import Farbwaehler, ENTER, ESC, ZURUECK, leeren

import stil as stil_kern                # core/stil.py (Pfad: bausteine/__init__.py)

# CSS border-style → Kastenzeichen (oben-links, waagrecht, oben-rechts,
# senkrecht, unten-links, unten-rechts).
RAHMEN_ZEICHEN = {
    "solid": "┌─┐│└┘", "dashed": "┌╌┐╎└┘", "dotted": "┌┈┐┊└┘",
    "double": "╔═╗║╚╝", "none": "      ",
}


def muster_zeichen(name, zeile, spalte):
    """Zeichen des Innenmusters (`--zentrale-muster`) an einer Stelle."""
    if name == "punkte":
        return "·" if (zeile + spalte) % 2 == 0 else " "
    if name == "streifen":
        return "─" if zeile % 2 == 0 else " "
    return {"raster": "░", "dicht": "▒", "schraeg": "╱", "karo": "┼"}.get(name, " ")


def _feld(name, eigen):
    """Schema-Stück einer Eigenschaft → Feld für die Liste. Das Stück des
    Aufrufers liegt über dem aus core/stil.py (Titel, eingeschränkte Wahl)."""
    s = dict(stil_kern.EIGENSCHAFTEN[name])
    s.update(eigen if isinstance(eigen, dict) else {})
    f = {"name": name, "titel": str(s.get("title") or name), "hilfe": s.get("description")}
    wahl = [(w["const"], str(w.get("title") or w["const"]))
            for w in s.get("oneOf") or [] if isinstance(w, dict) and "const" in w]
    wahl = wahl or [(w, str(w)) for w in s.get("enum") or []]
    if s.get("readOnly"):
        f["art"] = "gesperrt"
    elif name in stil_kern.FARBEN:
        f["art"] = "farbe"
    elif wahl:
        f.update(art="wahl", wahl=wahl, vorgabe=s.get("default", wahl[0][0]))
    else:
        f["art"] = "gesperrt"           # Text-Eigenschaften gibt es (noch) nicht
    return f


def felder_aus(optionen):
    """Angebot (Liste von CSS-Namen oder JSON Schema) → Felder; unbekannte
    Namen → ValueError (stil.schema prüft)."""
    if isinstance(optionen, dict):
        props = optionen.get("properties") or {}
        stil_kern.schema(list(props))
        return [_feld(n, s) for n, s in props.items()]
    namen = list(optionen or [])
    stil_kern.schema(namen)
    return [_feld(n, None) for n in namen]


class Stylebox:
    """Modal: einen CSS-Stil einstellen. Siehe Kopf der Datei."""
    titel = "stil"

    def __init__(self, stil, optionen, titel="stil", text="Beispiel"):
        self.felder = felder_aus(optionen)
        self.namen = [f["name"] for f in self.felder]
        self.titel, self.text = titel, text
        anfang = {}
        for name, wert in (stil or {}).items():         # Fremdes/Kaputtes still weglassen
            if name in self.namen:
                sauber, grund = stil_kern.wert_pruefen(name, wert)
                if not grund:
                    anfang[name] = sauber
        self.anfang = anfang
        self.eingang = set(stil or {}) & set(self.namen)   # angeboten und mitgebracht (auch kaputt)
        self.werte = dict(anfang)       # fehlt ein Name: nicht gesetzt („—")
        self.beruehrt = set()           # in dieser Sitzung geändert/entfernt
        self.feld = 0
        self.waehler = None             # offener Farbwähler
        self.hinweis = ""
        self.ergebnis = None

    @property
    def aktuell(self):
        return self.felder[self.feld] if self.felder else None

    # ── Tasten ──────────────────────────────────────────────────────────
    def taste(self, ch):
        """→ None | ("fertig", {geänderte css}) | ("abbruch",)."""
        if self.waehler is not None:
            erg = self.waehler.taste(ch)
            if erg and erg[0] == "fertig":
                self.werte[self.aktuell["name"]] = erg[1]
                self.beruehrt.add(self.aktuell["name"])
            if erg:
                self.waehler = None
            return None
        self.hinweis = ""
        if ch == ESC:
            self.ergebnis = None
            return ("abbruch",)
        if ch in ENTER:
            neu = stil_kern.pruefen(self.werte, self.namen)
            erg = stil_kern.unterschied(self.anfang, neu)   # Entferntes aus dem Anfang = None
            for name in self.beruehrt - set(neu):           # auch Kaputtes/neu Gesetztes, das weg ist
                erg[name] = None
            self.ergebnis = erg
            return ("fertig", self.ergebnis)
        f = self.aktuell
        if f is None:
            return None
        n = len(self.felder)
        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            self.feld = (self.feld - 1) % n
        elif ch in (curses.KEY_DOWN, 9):
            self.feld = (self.feld + 1) % n
        elif f["art"] == "gesperrt" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" "), ord("#")):
            self.hinweis = "%s: noch gesperrt" % f["titel"]
        elif f["art"] == "wahl" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
            werte = [w for w, _t in f["wahl"]]
            jetzt = self.werte.get(f["name"], f["vorgabe"])
            i = werte.index(jetzt) if jetzt in werte else 0
            self.werte[f["name"]] = werte[(i + (-1 if ch == curses.KEY_LEFT else 1)) % len(werte)]
            self.beruehrt.add(f["name"])
        elif f["art"] == "farbe" and ch in (curses.KEY_RIGHT, ord(" "), ord("#")):
            self.waehler = Farbwaehler(self.werte.get(f["name"]))
            if ch == ord("#"):
                self.waehler.taste(ch)
        elif f["art"] == "gesperrt" and ch in ZURUECK + (curses.KEY_DC, ord("r")):
            self.hinweis = "%s: noch gesperrt" % f["titel"]
        elif ch in ZURUECK or ch == curses.KEY_DC:      # entfernen: nicht gesetzt
            if self.werte.pop(f["name"], None) is not None or f["name"] in self.eingang:
                self.beruehrt.add(f["name"])            # nie Gesetztes kommt nicht zurück
        elif ch == ord("r"):                            # zurück auf den Anfang
            if f["name"] in self.anfang:
                self.werte[f["name"]] = self.anfang[f["name"]]
            else:
                self.werte.pop(f["name"], None)
            self.beruehrt.discard(f["name"])
        return None

    def tasten(self):
        if self.waehler is not None:
            return self.waehler.tasten()
        return [("↑↓", "wählen"), ("←→", "ändern"), ("space", "farbe"),
                ("⌫", "entfernen"), ("r", "anfang"), ("enter", "nehmen"), ("esc", "zurück")]

    # ── Inhalt (rein) ───────────────────────────────────────────────────
    def zeilen(self):
        """Je angebotener Eigenschaft: dict(name, titel, text, art, farbe, aktiv);
        nicht gesetzt → text „—"."""
        raus = []
        for i, f in enumerate(self.felder):
            wert = self.werte.get(f["name"])
            farbe = None
            if f["art"] == "gesperrt":
                text = "noch gesperrt"
            elif f["art"] == "farbe":
                text = wert or "—"
                farbe = stil_kern.hex_zu_rgb(wert) if wert else None
            elif wert is None:
                text = "—"
            else:
                text = "‹ %s ›" % next((t for c, t in f["wahl"] if c == wert), wert)
            raus.append({"name": f["name"], "titel": f["titel"], "text": text,
                         "art": f["art"], "farbe": farbe, "aktiv": i == self.feld})
        return raus

    def _rahmen_stil(self):
        if "border-style" in self.werte:
            return self.werte["border-style"]
        return "solid" if {"border-style", "border-color"} & set(self.namen) else "none"

    def vorschau(self, breite, hoehe, grund=None, schrift=None):
        """Das gestylte Kästchen als Zeilen von (zeichen, fg, bg) — Farben als
        RGB; None = Farbe des Themes (grund/schrift, wenn gegeben)."""
        breite, hoehe = max(2, breite), max(2, hoehe)
        werte = self.werte
        hg = stil_kern.hex_zu_rgb(werte["background-color"]) if "background-color" in werte else grund
        vg = stil_kern.hex_zu_rgb(werte["color"]) if "color" in werte else schrift
        rand = stil_kern.hex_zu_rgb(werte["border-color"]) if "border-color" in werte else vg
        muster = werte.get(stil_kern.MUSTER_EIGENSCHAFT, "none")
        leise = pixel.mix(vg, hg, .6) if vg and hg else vg
        z = RAHMEN_ZEICHEN.get(self._rahmen_stil(), RAHMEN_ZEICHEN["solid"])
        zeilen = []
        for r in range(hoehe):
            zeile = []
            for c in range(breite):
                oben, unten, links, rechts = r == 0, r == hoehe - 1, c == 0, c == breite - 1
                if (oben or unten) and (links or rechts):
                    ch = z[0 if oben and links else 2 if oben else 4 if links else 5]
                    zeile.append((ch, rand, hg))
                elif oben or unten:
                    zeile.append((z[1], rand, hg))
                elif links or rechts:
                    zeile.append((z[3], rand, hg))
                else:
                    zeile.append((muster_zeichen(muster, r, c), leise, hg))
            zeilen.append(zeile)
        if hoehe >= 3 and breite >= 4:                          # der Text mittig
            text = self.text[:breite - 2]
            r, c0 = hoehe // 2, (breite - len(text)) // 2
            for i, ch in enumerate(text):
                zeilen[r][c0 + i] = (ch, vg, hg)
        return zeilen

    # ── Zeichnen ────────────────────────────────────────────────────────
    mittig = staticmethod(Farbwaehler.mittig)

    def zeichne(self, z, y, x, h, w):
        """Rahmen + Liste + Vorschau in y, x, h, w über den Kontext z; ist
        der Farbwähler offen, zeichnet er sich an derselben Stelle."""
        if self.waehler is not None:
            self.waehler.zeichne(z, y, x, h, w)
            return
        C = z.C
        leeren(z, y, x, h, w)
        z.draw_box(y, x, h, w, self.titel, C.get("acc", 0))
        iy, ix, iw = y + 1, x + 2, w - 4
        farbig = getattr(z, "has_color", False) and C.get("pix_bg") is not None
        rand = max([len(f["titel"]) for f in self.felder] + [4]) + 2
        listen_breite = rand + 16
        for i, zl in enumerate(self.zeilen()):
            attr = C.get("bright", 0) | curses.A_REVERSE if zl["aktiv"] else C.get("ink", 0)
            z.safe_addstr(iy + i, ix, zl["titel"].ljust(rand)[:iw], attr)
            sx = ix + rand
            if zl["art"] == "farbe" and zl["farbe"] and farbig:
                z.safe_addstr(iy + i, sx, "██", z.pix_attr(zl["farbe"], C["pix_bg"]))
                sx += 3
            art_attr = C.get("faint", 0) if zl["art"] == "gesperrt" else C.get("dim", 0)
            z.safe_addstr(iy + i, sx, zl["text"][:max(0, ix + iw - sx)], art_attr)
        # Vorschau rechts, sonst darunter
        vx, vy = ix + listen_breite + 2, iy
        vb, vh = ix + iw - vx, h - 4
        if vb < 10:
            vx, vy = ix, iy + len(self.felder) + 1
            vb, vh = min(iw, 30), h - 4 - len(self.felder) - 1
        if vb >= 4 and vh >= 3:
            self._zeichne_vorschau(z, vy, vx, min(vh, 7), vb, farbig)
        unten = self.hinweis or " · ".join("%s %s" % t for t in self.tasten())
        z.safe_addstr(y + h - 2, ix, unten[:iw],
                      C.get("warn", 0) if self.hinweis else C.get("faint", 0))

    def _zeichne_vorschau(self, z, y, x, h, w, farbig):
        C = z.C
        grund = C.get("pix_bg")
        schrift = pixel.mix(grund, (255, 255, 255) if sum(grund or (0, 0, 0)) < 384
                            else (0, 0, 0), .85) if grund else None
        for r, zeile in enumerate(self.vorschau(w, h, grund, schrift)):
            for c, (ch, fg, hg) in enumerate(zeile):
                attr = z.pix_attr(fg, hg) if farbig and fg and hg else C.get("ink", 0)
                z.safe_addstr(y + r, x + c, ch, attr)
