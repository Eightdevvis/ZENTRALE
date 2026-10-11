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
# Nicht gesetzt heißt „‹ keine ›" und ist eine echte Wahl (11.10.2026,
# Sasha: „da sollte Rahmen ‹keine› einfach ausgewählt dann sein"): bei einer
# Auswahl steht sie vorn im Kreis (keine → durchgezogen → … → keine), eine
# Farbe zeigt sie, bis man eine wählt. ‹ keine › ist NICHT CSS „none" —
# die Eigenschaft fehlt dann einfach. Es ist das EINZIGE „nichts" (11.10.2026,
# Sasha): „keiner"/„keins" (CSS none) gibt es nicht mehr zur Wahl. Ein alter
# Stil mit none zeigt ‹ keine ›, und Enter gibt dafür None zurück (fällt weg).
#
# Tasten: ↑↓ (Tab, Shift+Tab) Eigenschaft; ←→ oder Leertaste ändern eine
# Auswahl; bei einer Farbe öffnen Leertaste/→ den Farbwähler (# öffnet ihn
# gleich mit Hex-Feld); ⌫/Entf setzt auf ‹ keine › (nicht gesetzt), r setzt
# auf den Anfang zurück; Enter nimmt, Esc bricht ab. Icon hochladen steht da, ist aber gesperrt
# (readOnly) — es lässt sich nicht öffnen.
#
# Die Box zeigt immer, was gezeichnet wird (11.10.2026, Sasha): nach jeder
# Änderung gilt stil.stimmig — Rahmenfarbe ohne Rahmenstil → durchgezogen,
# Rahmenstil auf ‹ keine › → Rahmenfarbe fällt mit weg.
#
# `taste(ch)` → None | ("fertig", {geänderte css, entfernte = None}) |
# ("abbruch",); der Aufrufer wendet das mit stil.anwenden(alt, …) an; danach
# steht dasselbe in `ergebnis` (None bei Abbruch). Rein gerechnet:
# `zeilen()` (die Liste), `vorschau(b, h)` (das gestylte Kästchen als
# Zellen); gezeichnet über den Kontext: `zeichne(z, y, x, h, w)`.
# Doku: memory/hub/bausteine_farbe_stil.md.

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

KEINE = "‹ keine ›"                     # Anzeige: Eigenschaft nicht gesetzt


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
    wahl = [(w, t) for w, t in wahl if not stil_kern.alt_nichts(name, w)]   # nur ‹ keine ›
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
                if not grund and not stil_kern.alt_nichts(name, sauber):
                    anfang[name] = sauber
        self.anfang = anfang
        # altes CSS „none": zeigt ‹ keine ›, Enter gibt None (fällt weg)
        self.alt_nichts = {n for n, w in (stil or {}).items()
                           if n in self.namen and stil_kern.alt_nichts(n, w)}
        self.eingang = set(stil or {}) & set(self.namen)   # angeboten und mitgebracht (auch kaputt)
        self.werte = dict(anfang)       # fehlt ein Name: nicht gesetzt (‹ keine ›)
        self.beruehrt = set()           # in dieser Sitzung geändert/entfernt
        self.feld = 0
        self._stimmig(None)             # alter Stil: Rahmenfarbe ohne Stil → durchgezogen
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
                name = self.aktuell["name"]
                vorher = dict(self.werte)
                self.werte[name] = erg[1]
                self.beruehrt.add(name)
                self._stimmig(vorher)
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
            for name in (self.beruehrt | self.alt_nichts) - set(neu):   # auch Kaputtes/Altes, das weg ist
                erg[name] = None
            self.ergebnis = erg
            return ("fertig", self.ergebnis)
        f = self.aktuell
        if f is None:
            return None
        vorher = dict(self.werte)
        n = len(self.felder)
        if ch in (curses.KEY_UP, curses.KEY_BTAB):
            self.feld = (self.feld - 1) % n
        elif ch in (curses.KEY_DOWN, 9):
            self.feld = (self.feld + 1) % n
        elif f["art"] == "gesperrt" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" "), ord("#")):
            self.hinweis = "%s: noch gesperrt" % f["titel"]
        elif f["art"] == "wahl" and ch in (curses.KEY_LEFT, curses.KEY_RIGHT, ord(" ")):
            werte = [None] + [w for w, _t in f["wahl"]]     # None = ‹ keine ›
            jetzt = self.werte.get(f["name"])
            i = werte.index(jetzt) if jetzt in werte else 0
            neu = werte[(i + (-1 if ch == curses.KEY_LEFT else 1)) % len(werte)]
            if neu is None:
                self._keine(f["name"])
            else:
                self.werte[f["name"]] = neu
                self.beruehrt.add(f["name"])
        elif f["art"] == "farbe" and ch in (curses.KEY_RIGHT, ord(" "), ord("#")):
            self.waehler = Farbwaehler(self.werte.get(f["name"]))
            if ch == ord("#"):
                self.waehler.taste(ch)
        elif f["art"] == "gesperrt" and ch in ZURUECK + (curses.KEY_DC, ord("r")):
            self.hinweis = "%s: noch gesperrt" % f["titel"]
        elif ch in ZURUECK or ch == curses.KEY_DC:      # ‹ keine ›: nicht gesetzt
            self._keine(f["name"])
        elif ch == ord("r"):                            # zurück auf den Anfang
            if f["name"] in self.anfang:
                self.werte[f["name"]] = self.anfang[f["name"]]
            else:
                self.werte.pop(f["name"], None)
            self.beruehrt.discard(f["name"])
        self._stimmig(vorher)           # Rahmenstil ↔ Rahmenfarbe (stil.stimmig)
        return None

    def _stimmig(self, vorher):
        """stil.stimmig nach jeder Änderung (Rahmenstil ↔ Rahmenfarbe), nur
        wenn beide angeboten sind; was die Regel ändert, gilt als berührt
        (Enter gibt es mit zurück, Entferntes als None)."""
        if not {"border-style", "border-color"} <= set(self.namen):
            return
        neu = stil_kern.stimmig(self.werte, vorher)
        for name in set(neu) | set(self.werte):
            if neu.get(name) != self.werte.get(name):
                self.beruehrt.add(name)
        self.werte = neu

    def _keine(self, name):
        """Auf ‹ keine › (nicht gesetzt); nie Gesetztes kommt nicht zurück."""
        if self.werte.pop(name, None) is not None or name in self.eingang:
            self.beruehrt.add(name)

    def tasten(self):
        if self.waehler is not None:
            return self.waehler.tasten()
        return [("↑↓", "feld"), ("←→", "wert"), ("space", "farbe"),         # passt in 80 Spalten
                ("⌫", "keine"), ("r", "anfang"), ("enter", "ok"), ("esc", "zurück")]

    # ── Inhalt (rein) ───────────────────────────────────────────────────
    def zeilen(self):
        """Je angebotener Eigenschaft: dict(name, titel, text, art, farbe, aktiv);
        nicht gesetzt → text „‹ keine ›" (bei jeder Art)."""
        raus = []
        for i, f in enumerate(self.felder):
            wert = self.werte.get(f["name"])
            farbe = None
            if f["art"] == "gesperrt":
                text = "noch gesperrt" if wert else KEINE + " · noch gesperrt"
            elif wert is None:
                text = KEINE
            elif f["art"] == "farbe":
                text = wert
                farbe = stil_kern.hex_zu_rgb(wert)
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
    VORSCHAU_H = 7                      # Zeilen der Vorschau mit Rahmen/Fläche/Muster

    @property
    def vorschau_h(self):
        """Nur Schrift angeboten: drei Zeilen reichen (Text in der Mitte)."""
        kasten = {"border-style", "border-color", "background-color",
                  stil_kern.MUSTER_EIGENSCHAFT}
        return self.VORSCHAU_H if kasten & set(self.namen) else 3
    WAEHLER_MASS = (22, 72)             # (h, w) mit offenem Farbwähler

    def _listen_breite(self):
        rand = max([len(f["titel"]) for f in self.felder] + [4]) + 2
        return rand, rand + max([16] + [len(zl["text"]) + 3 for zl in self.zeilen()])

    def groesse(self, H, W):
        """(h, w) des Modals aus dem Inhalt (11.10.2026, Sasha: „unten voll
        viel Platz frei" — vorher setzten die Aufrufer fest 22 Zeilen):
        Liste und Vorschau nebeneinander (sonst untereinander), eine
        Leerzeile, die Fußzeile, Rahmen; höchstens H×W. Breit genug für die
        Fußzeile, solange W reicht. Mit offenem Farbwähler dessen Maß."""
        if self.waehler is not None:
            return min(H, self.WAEHLER_MASS[0]), min(W, self.WAEHLER_MASS[1])
        _rand, lb = self._listen_breite()
        fuss = len(" · ".join("%s %s" % t for t in self.tasten()))
        w = min(W, max(lb + 2 + 10, fuss) + 4)
        n = len(self.felder)
        if (w - 4) - lb - 2 >= 10:                       # Vorschau rechts
            innen = max(n, self.vorschau_h)
        else:                                            # Vorschau darunter
            innen = n + 1 + self.vorschau_h
        return min(H, innen + 4), w

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
        rand, listen_breite = self._listen_breite()
        zeilen = self.zeilen()
        for i, zl in enumerate(zeilen):
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
            self._zeichne_vorschau(z, vy, vx, min(vh, self.vorschau_h), vb, farbig)
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
