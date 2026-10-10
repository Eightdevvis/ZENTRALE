# tui/bausteine/canvas.py
#
# Eine unendliche Fläche mit Kästen darauf und Schnüren dazwischen — der
# Baustein hinter Desk View (2026-10-09), gebaut, damit auch andere Apps ihn
# benutzen können. Er weiß nichts vom Desk, speichert nichts und fragt kein
# Backend: die Ansicht reicht Elemente und Verbindungen herein, gibt ihm
# Tasten und bekommt ein `Ergebnis` zurück, wenn etwas gespeichert oder
# bearbeitet werden will. Gezeichnet wird über `bild()` — Zeilen aus
# (spalte, text, rolle); die Ansicht macht daraus curses-Farben.
#
# Welt: ganze Zellen, x nach rechts, y nach unten, auch negativ. Der
# Ausschnitt (vx, vy, vw, vh) ist das Stück Welt, das man gerade sieht.
#
# Element: dict mit id, x, y, w, h, art (+ was die Art braucht, z. B. text).
# Verbindung: dict mit id, von, nach (Element-ids), optional label.
#
# Arten (Registrierung `Arten`): jede Art sagt, wie ein Element aussieht
# (`zeichne(element, w, h)` → Zeilen innen), ob es ein Bearbeiten-Modal hat
# (`modal(element)` → Objekt mit taste/anzeige/tasten/aenderungen oder
# None) und wie ein neues aussieht (`neu(id, x, y)`). Der Canvas fragt nur
# die Registrierung — eine neue Art braucht keinen Umbau hier
# (Beispiele: tui/bausteine/canvas_arten.py). Optional:
#   rolle                      Farbrolle des Rahmens, solange nicht gewählt
#   oeffnen(element)           -> None oder eine Aktion: Taste `o` auf dem
#                              Kasten meldet sie als Ergebnis „aktion" an die
#                              Ansicht (Bild im Betrachter, Kachel in ihrer
#                              App). Enter greift IMMER — jedes Element ist
#                              gleich zu verschieben (2026-10-10).
#   taste(element, zeichen)    -> True, wenn die Art mit einer eigenen Taste
#                              (z. B. `f` beim Bild: mono/farbe) das Element
#                              geändert hat; der Canvas meldet „geaendert"
#   neu_label                  Name im Wähler von `+` (siehe unten)
#   neu_dialog()               -> Modal: die Ansicht fragt erst (z. B. die
#                              Felder einer Kachel aus dem Katalog) und legt
#                              dann neu(eid, x, y, werte) hin (2026-10-10)
#   blaettern(element, schritt) Bild↑/Bild↓ auf dem gewählten Kasten: im
#                              Inneren blättern (eigene Lage am Element unter
#                              „_oben", wird nie gespeichert). Hier docken
#                              später Kacheln mit langem Inhalt an (Kalender).
#
# Bedienung (Zustände, Sasha 2026-10-09, Belegung siehe
# memory/system/desk_view.md):
#   ruhe       ↑↓←→ Fokus springt zum nächsten Kasten in der Richtung,
#              enter greift, + legt einen neuen an (gleich gegriffen),
#              e bearbeiten, v verbinden, d löschen (Rückfrage), o öffnen
#              (wenn die Art es kann), esc zurück
#
# `+`: hat die Ansicht eine Fabrik `neu` hereingegeben, legt der Canvas
# selbst an. Ohne Fabrik meldet er „neu_waehlen" — die Ansicht zeigt einen
# Wähler der Arten mit `neu_label` (Arten.anlegbar()) und legt das Gewählte
# mit `neu_ablegen(element)` hin (2026-10-10: Zettel ODER Bild).
#   greifen    ↑↓←→ schiebt um eine Zelle, enter legt ab, esc setzt zurück
#              (ein neuer verschwindet wieder)
#   verbinden  ↑↓←→ springt mit dem Ziel, die Schnur wird vorgezeigt,
#              enter/v verbindet (schon verbunden → Rückfrage „lösen?"),
#              esc bricht ab
#   frage      j ja, n/esc nein
#   überall    W A S D (Großbuchstaben) schiebt den Ausschnitt, ebenso
#              shift+↑↓←→ und alt+↑↓←→; beim Greifen reist der Kasten mit
#              (er liegt ja in der Hand)
#
# Weich (2026-10-10, Sasha: „ich möchte dass die bewegung über das canvas
# weicher ist"): (vx, vy) bleibt die Lage, mit der alles rechnet. Gezeichnet
# wird eine Anzeige-Lage (ax, ay), die jedes Bild ein Stück auf (vx, vy)
# zugleitet (`gleiten()`, die Ansicht ruft es je Bild). Aus, solange die
# Ansicht `weich` nicht einschaltet — dann zeichnet bild() genau (vx, vy).
# Was man in der Hand hat, liegt beim Gleiten fest auf dem Schirm (am Ziel
# des Ausschnitts gerechnet, `_in_der_hand`): es gleitet mit der Ansicht,
# statt vorzuspringen und zurückzurutschen (2026-10-10).

import curses
import math
import secrets
from collections import namedtuple

try:
    from tui.bausteine import schnur
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine import schnur

# Was der Canvas der Ansicht meldet. art:
#   "geaendert"   Elemente/Verbindungen sind anders → speichern (grund sagt was)
#   "bearbeiten"  das Modal der Art für `element` öffnen
#   "zu"          esc in Ruhe: der Canvas will geschlossen werden
#   "aktion"      o auf einem Kasten, dessen Art etwas öffnen kann
#                 (`oeffnen` der Art, z. B. ein Bild: ("bild_oeffnen", datei)
#                 → die Ansicht führt es aus); grund = was die Art meldet
#   "neu_waehlen" + ohne Fabrik: die Ansicht soll die Arten zur Wahl stellen
Ergebnis = namedtuple("Ergebnis", "art element grund")

PAN_X, PAN_Y = 6, 3                     # so weit schiebt shift+Pfeil den Ausschnitt
RASTER_X, RASTER_Y = 10, 5              # leise Punkte zur Orientierung beim Schieben

# Gleiten (2026-10-10): je Bild dieser Anteil der Reststrecke (wie das Rad
# auf der Startseite), unter einer halben Zelle rastet es ein. Spätestens
# nach GLEIT_BILDER Bildern steht der Ausschnitt — bei ~33 ms je Bild gut
# 0,2 s; mehr Bilder kosten auf dem Pi nur Rechenzeit.
GLEIT_ANTEIL = 0.38
GLEIT_BILDER = 6
# Gedrückt halten (Tastenwiederholung, 2026-10-10): kommt dieselbe
# Schiebe-Richtung schneller als WIEDERHOLUNG_S wieder, wächst der Schritt
# ×BESCHLEUNIGUNG bis höchstens ×BESCHLEUNIGUNG_MAX; nach einer Pause oder
# in eine andere Richtung wieder der Grundschritt.
WIEDERHOLUNG_S = 0.08
BESCHLEUNIGUNG, BESCHLEUNIGUNG_MAX = 1.5, 4.0


def gleit_schritt(pos, ziel, anteil=GLEIT_ANTEIL):
    """Ein Bild Gleiten: pos rückt um `anteil` der Reststrecke auf ziel zu
    und rastet unter einer halben Zelle ein. PURE."""
    d = ziel - pos
    return float(ziel) if abs(d) < 0.5 else pos + d * anteil


def _runden(x):
    return int(math.floor(x + 0.5))      # nicht round(): 2.5 → 3, nicht 2


# ── Tasten → Ereignisse ───────────────────────────────────────────────
# Shift+Pfeil kommt je nach Terminal (und tmux) verschieden an: als
# KEY_SLEFT/KEY_SRIGHT/KEY_SR/KEY_SF oder als erweiterte Taste mit dem
# terminfo-Namen kLFT2/kRIT2/kUP2/kDN2 (Modifier 2 = Shift), deren Nummer
# von Terminal zu Terminal wechselt. Darum zählt der NAME (curses.keyname),
# nicht die Zahl; die curses-Konstanten nur als Rückfall, wenn kein Name
# zu haben ist (Tests ohne initscr).
# Primär schieben die Großbuchstaben W A S D (2026-10-10, Sasha: „ZENTRALE
# soll überall gleich gut funktionieren") — die kommen in jedem Terminal,
# tmux, macOS und Handy gleich an. Shift+Pfeile und Alt+Pfeile bleiben
# dazu; xfce4-terminal schluckt Shift+↑↓ von Haus aus.
WASD = {ord("W"): "hoch", ord("A"): "links", ord("S"): "runter", ord("D"): "rechts"}
# Alt+Pfeil: Modifier 3 im terminfo-Namen (wie in ansichten/karte.py).
ALT_NAMEN = {b"kLFT3": "links", b"kRIT3": "rechts", b"kUP3": "hoch", b"kDN3": "runter"}
SHIFT_NAMEN = {b"KEY_SLEFT": "links", b"kLFT2": "links",
               b"KEY_SRIGHT": "rechts", b"kRIT2": "rechts",
               b"KEY_SR": "hoch", b"kUP2": "hoch",
               b"KEY_SF": "runter", b"kDN2": "runter"}
_SHIFT_CODES = {curses.KEY_SLEFT: "links", curses.KEY_SRIGHT: "rechts",
                curses.KEY_SR: "hoch", curses.KEY_SF: "runter"}
_PFEILE = {curses.KEY_UP: "hoch", curses.KEY_DOWN: "runter",
           curses.KEY_LEFT: "links", curses.KEY_RIGHT: "rechts"}
# Roh durchgereichte Folgen nach ESC, wenn das Terminal sie nicht übersetzt:
# ESC [ 1 ; 2 A … (xterm-Stil, Modifier 2 = Shift).
# ESC [ 1 ; 3 A … ist dasselbe mit Alt.
_SHIFT_FOLGE = {"[1;2A": "hoch", "[1;2B": "runter", "[1;2C": "rechts", "[1;2D": "links",
                "[1;3A": "hoch", "[1;3B": "runter", "[1;3C": "rechts", "[1;3D": "links"}
# Alt als ESC-Vorsilbe vor einem rohen Pfeil (ESC ESC [ A, ESC ESC O A).
_ALT_ROH = {"\x1b[A": "hoch", "\x1b[B": "runter", "\x1b[C": "rechts", "\x1b[D": "links",
            "\x1bOA": "hoch", "\x1bOB": "runter", "\x1bOC": "rechts", "\x1bOD": "links"}
_BUCHSTABEN = {ord("+"): "neu", ord("e"): "bearbeiten", ord("v"): "verbinden",
               ord("d"): "loeschen", curses.KEY_DC: "loeschen", ord("o"): "oeffnen",
               curses.KEY_PPAGE: "blaettern_hoch", curses.KEY_NPAGE: "blaettern_runter",
               ord("j"): "ja", ord("y"): "ja", ord("n"): "nein",
               10: "enter", 13: "enter", curses.KEY_ENTER: "enter", 27: "esc"}


def tastenname(ch):
    """curses.keyname, ohne zu werfen (vor initscr oder bei -1)."""
    try:
        return curses.keyname(ch) if ch >= 0 else b""
    except (ValueError, OverflowError, curses.error):
        return b""


def shift_pfeil(ch, name=None):
    """Ist ch ein Shift+Pfeil? -> "hoch"/"runter"/"links"/"rechts" oder None."""
    name = tastenname(ch) if name is None else name
    if name in SHIFT_NAMEN:
        return SHIFT_NAMEN[name]
    return _SHIFT_CODES.get(ch)


def alt_pfeil(ch, name=None):
    """Ist ch ein Alt+Pfeil (eine Taste, kLFT3 …)? -> Richtung oder None."""
    return ALT_NAMEN.get(tastenname(ch) if name is None else name)


def esc_folge(folge):
    """Bytes nach einem ESC (ohne das ESC) -> "pan_<richtung>", "esc" (nichts
    folgte) oder None (eine Folge, die der Canvas nicht kennt, z. B. Alt+x)."""
    if not folge:
        return "esc"
    if folge[0] in _PFEILE:              # Alt = ESC + (schon übersetzter) Pfeil
        return "pan_" + _PFEILE[folge[0]]
    roh = "".join(chr(c) for c in folge if 0 <= c < 128)
    r = _SHIFT_FOLGE.get(roh) or _ALT_ROH.get(roh)
    return "pan_" + r if r else None


def taste_deuten(ch, name=None):
    """Taste -> Ereignis des Canvas oder None."""
    name = tastenname(ch) if name is None else name
    p = WASD.get(ch) or shift_pfeil(ch, name) or alt_pfeil(ch, name)
    if p:
        return "pan_" + p
    if ch in _PFEILE:
        return _PFEILE[ch]
    if ch in _BUCHSTABEN:
        return _BUCHSTABEN[ch]
    # Andere druckbare Zeichen gehen als „zeichen:x" an die Art (eigene
    # Tasten wie `f` beim Bild); der Canvas selbst kennt sie nicht.
    if 33 <= ch < 127:
        return "zeichen:" + chr(ch)
    return None


def neue_id():
    """16 Hex-Zeichen wie Obsidian — eindeutig genug über Rechner hinweg."""
    return secrets.token_hex(8)


# ── Arten ─────────────────────────────────────────────────────────────

class _Unbekannt:
    name = "?"

    def zeichne(self, element, w, h):
        return [[("? " + str(element.get("art")), "leise")]]

    def modal(self, element):
        return None


class Arten:
    """Registrierung der Elementarten. Unbekannte Arten zeichnen sich als
    „? art" — ein Element einer Art, die diese TUI (noch) nicht kennt, geht
    nicht verloren und lässt sich weiter verschieben."""

    def __init__(self):
        self._arten = {}

    def registrieren(self, art):
        self._arten[art.name] = art
        return art

    def holen(self, name):
        # Unbekannte Art: wie „fremd" zeichnen, wenn es die gibt (zeigt typ +
        # titel, z. B. eine Kachel, solange keine Kachel-Art registriert ist).
        return self._arten.get(name) or self._arten.get("fremd") or _Unbekannt()

    def gibt_es(self, name):
        return name in self._arten

    def anlegbar(self):
        """Arten, die `+` zur Wahl stellt (mit `neu_label`), in der
        Reihenfolge des Registrierens."""
        return [a for a in self._arten.values() if getattr(a, "neu_label", None)]


# ── Der Canvas ────────────────────────────────────────────────────────

class Canvas:
    def __init__(self, arten, elemente=None, verbindungen=None, neu=None):
        self.arten = arten
        self.elemente = elemente if elemente is not None else []
        self.verbindungen = verbindungen if verbindungen is not None else []
        self.neu_fabrik = neu            # (x, y) -> Element oder None
        self.vx = self.vy = 0
        self.vw, self.vh = 60, 20
        self.fokus = None                # id
        self.modus = "ruhe"              # ruhe | greifen | verbinden | frage
        self.griff = None                # {"id", "x", "y", "neu"}
        self.ziel = None                 # verbinden: id des Ziels
        self.frage = None                # {"was": "loeschen"|"loesen", "id", "text"}
        # Weich (2026-10-10): die Ansicht schaltet es ein; Tests und andere
        # Apps bekommen ohne das den Ausschnitt sofort wie bisher.
        self.weich = False
        self.ax = self.ay = None         # Anzeige-Lage (float), None = noch keine
        self._gleit_ziel, self._gleit_bilder = None, 0
        # Uhr für die Beschleunigung beim Gedrückthalten (time.monotonic);
        # None = immer der Grundschritt.
        self.uhr = None
        self._pan_letzt = None           # (zeit, richtung) des letzten Schiebens
        self._pan_faktor = 1.0

    def __repr__(self):                  # Zustand sichtbar machen (Tests vergleichen repr)
        return "Canvas(%r)" % ((self.vx, self.vy, self.fokus, self.modus, self.griff,
                                self.ziel, self.frage, self.elemente, self.verbindungen),)

    # ── Nachschlagen ──────────────────────────────────────────────────
    def element(self, eid):
        return next((e for e in self.elemente if e.get("id") == eid), None)

    def verbindung_zwischen(self, a, b):
        return next((v for v in self.verbindungen
                     if {v.get("von"), v.get("nach")} == {a, b}), None)

    def mitte_des_ausschnitts(self):
        return self.vx + self.vw // 2, self.vy + self.vh // 2

    # ── Fokus räumlich springen ───────────────────────────────────────
    def _naechster(self, von, richtung, ohne=()):
        """Der nächste Kasten in `richtung` von Kasten `von`. Abstand in
        „Bild-Einheiten" (Zeilen zählen doppelt); wer seitlich weit weg ist,
        zahlt doppelt — so springt ← zum Nachbarn links, nicht zum Kasten
        schräg unten, der zufällig ein Stück weiter links beginnt."""
        cx, cy = schnur.mitte(von)
        bester, wert = None, None
        for e in self.elemente:
            if e is von or e.get("id") in ohne:
                continue
            ex, ey = schnur.mitte(e)
            dx, dy = ex - cx, (ey - cy) * 2
            vor, quer = {"rechts": (dx, dy), "links": (-dx, dy),
                         "runter": (dy, dx), "hoch": (-dy, dx)}[richtung]
            if vor <= 0:
                continue
            w = vor + 2 * abs(quer)
            if wert is None or w < wert:
                bester, wert = e, w
        return bester

    def _naechster_zur_mitte(self, ohne=()):
        mx, my = self.mitte_des_ausschnitts()
        kand = [e for e in self.elemente if e.get("id") not in ohne]
        if not kand:
            return None
        return min(kand, key=lambda e: abs(schnur.mitte(e)[0] - mx)
                   + 2 * abs(schnur.mitte(e)[1] - my))

    def folgen(self, e, rand=1):
        """Ausschnitt so wenig wie möglich verschieben, dass e sichtbar ist."""
        if e["x"] < self.vx:
            self.vx = e["x"] - rand
        elif e["x"] + e["w"] > self.vx + self.vw:
            self.vx = min(e["x"] - rand, e["x"] + e["w"] - self.vw + rand)
        if e["y"] < self.vy:
            self.vy = e["y"] - rand
        elif e["y"] + e["h"] > self.vy + self.vh:
            self.vy = min(e["y"] - rand, e["y"] + e["h"] - self.vh + rand)

    # ── Tasten ────────────────────────────────────────────────────────
    def taste(self, ereignis):
        """Ein Ereignis (taste_deuten) verarbeiten -> Ergebnis oder None."""
        if ereignis is None:
            return None
        if ereignis.startswith("pan_") and self.modus != "frage":
            self._pan(ereignis[4:])
            return None
        return {"ruhe": self._ruhe, "greifen": self._greifen,
                "verbinden": self._verbinden, "frage": self._frage}[self.modus](ereignis)

    def _pan_faktor_neu(self, richtung):
        """Schritt-Faktor für dieses Schieben: wächst bei schneller
        Wiederholung derselben Richtung, sonst 1."""
        if self.uhr is None:
            return 1.0
        jetzt = self.uhr()
        letzt, self._pan_letzt = self._pan_letzt, (jetzt, richtung)
        if letzt and letzt[1] == richtung and jetzt - letzt[0] < WIEDERHOLUNG_S:
            self._pan_faktor = min(BESCHLEUNIGUNG_MAX, self._pan_faktor * BESCHLEUNIGUNG)
        else:
            self._pan_faktor = 1.0
        return self._pan_faktor

    def _pan(self, richtung):
        f = self._pan_faktor_neu(richtung)
        px, py = _runden(PAN_X * f), _runden(PAN_Y * f)
        dx, dy = {"links": (-px, 0), "rechts": (px, 0),
                  "hoch": (0, -py), "runter": (0, py)}[richtung]
        self.vx += dx
        self.vy += dy
        if self.modus == "greifen":
            e = self.element(self.griff["id"])
            e["x"] += dx
            e["y"] += dy

    def _ruhe(self, ev):
        fokus = self.element(self.fokus)
        if ev in ("hoch", "runter", "links", "rechts"):
            neu = self._naechster(fokus, ev) if fokus else self._naechster_zur_mitte()
            if neu:
                self.fokus = neu["id"]
                self.folgen(neu)
            return None
        if ev == "neu":
            if self.neu_fabrik is None:
                return Ergebnis("neu_waehlen", None, "")
            mx, my = self.mitte_des_ausschnitts()
            e = self.neu_fabrik(mx, my)
            if e:
                self.neu_ablegen(e)
            return None
        if ev == "esc":
            return Ergebnis("zu", None, "")
        if fokus is None:
            return None
        if ev in ("blaettern_hoch", "blaettern_runter"):
            blaettern = getattr(self.arten.holen(fokus.get("art")), "blaettern", None)
            if blaettern:
                blaettern(fokus, -1 if ev == "blaettern_hoch" else 1)
            return None
        art = self.arten.holen(fokus.get("art"))
        if ev == "oeffnen":
            oeffnen = getattr(art, "oeffnen", None)
            aktion = oeffnen(fokus) if oeffnen else None
            return Ergebnis("aktion", fokus, aktion) if aktion is not None else None
        if ev.startswith("zeichen:"):
            eigene = getattr(art, "taste", None)
            if eigene and eigene(fokus, ev[len("zeichen:"):]):
                return Ergebnis("geaendert", fokus, "art")
            return None
        if ev == "enter":
            self.griff = {"id": fokus["id"], "x": fokus["x"], "y": fokus["y"], "neu": False}
            self.modus = "greifen"
            # Oben liegen lassen, was man in der Hand hat (Reihenfolge = Stapel).
            self.elemente.remove(fokus)
            self.elemente.append(fokus)
        elif ev == "bearbeiten":
            if self.arten.holen(fokus.get("art")).modal(fokus) is not None:
                return Ergebnis("bearbeiten", fokus, "")
        elif ev == "verbinden":
            ziel = self._naechster_zur_mitte(ohne=(fokus["id"],))
            if ziel:
                self.ziel = ziel["id"]
                self.modus = "verbinden"
        elif ev == "loeschen":
            self.frage = {"was": "loeschen", "id": fokus["id"], "text": "löschen?"}
            self.modus = "frage"
        return None

    def neu_ablegen(self, e):
        """Ein frisches Element mitten in den Ausschnitt legen und gleich
        greifen (enter legt ab = gespeichert, esc nimmt es wieder weg)."""
        mx, my = self.mitte_des_ausschnitts()
        e["x"], e["y"] = mx - e["w"] // 2, my - e["h"] // 2
        self.elemente.append(e)
        self.fokus = e["id"]
        self.griff = {"id": e["id"], "x": e["x"], "y": e["y"], "neu": True}
        self.modus = "greifen"

    def _greifen(self, ev):
        e = self.element(self.griff["id"])
        schritte = {"hoch": (0, -1), "runter": (0, 1), "links": (-1, 0), "rechts": (1, 0)}
        if ev in schritte:
            e["x"] += schritte[ev][0]
            e["y"] += schritte[ev][1]
            self.folgen(e, rand=0)
            return None
        if ev == "enter":
            griff, self.griff, self.modus = self.griff, None, "ruhe"
            if griff["neu"]:
                return Ergebnis("geaendert", e, "neu")
            if (e["x"], e["y"]) != (griff["x"], griff["y"]):
                return Ergebnis("geaendert", e, "verschoben")
            return None
        if ev == "esc":
            if self.griff["neu"]:
                self.elemente.remove(e)
                self.fokus = None
            else:
                e["x"], e["y"] = self.griff["x"], self.griff["y"]
            self.griff, self.modus = None, "ruhe"
        return None

    def _verbinden(self, ev):
        quelle, ziel = self.element(self.fokus), self.element(self.ziel)
        if ev in ("hoch", "runter", "links", "rechts"):
            neu = self._naechster(ziel, ev, ohne=(quelle["id"],))
            if neu:
                self.ziel = neu["id"]
                self.folgen(neu)
            return None
        if ev == "esc":
            self.ziel, self.modus = None, "ruhe"
            return None
        if ev in ("enter", "verbinden"):
            schon = self.verbindung_zwischen(quelle["id"], ziel["id"])
            if schon:
                self.frage = {"was": "loesen", "id": schon["id"],
                              "text": "schon verbunden — schnur lösen?"}
                self.ziel, self.modus = None, "frage"
                return None
            v = {"id": neue_id(), "von": quelle["id"], "nach": ziel["id"]}
            self.verbindungen.append(v)
            self.ziel, self.modus = None, "ruhe"
            return Ergebnis("geaendert", quelle, "verbunden")
        return None

    def _frage(self, ev):
        frage = self.frage
        if ev in ("nein", "esc"):
            self.frage, self.modus = None, "ruhe"
            return None
        if ev != "ja":
            return None
        self.frage, self.modus = None, "ruhe"
        if frage["was"] == "loeschen":
            return self.loeschen(frage["id"])
        self.verbindungen[:] = [v for v in self.verbindungen if v.get("id") != frage["id"]]
        return Ergebnis("geaendert", self.element(self.fokus), "geloest")

    def loeschen(self, eid):
        """Element weg — und jede Schnur, die an ihm hing."""
        e = self.element(eid)
        if e is None:
            return None
        self.elemente.remove(e)
        self.verbindungen[:] = [v for v in self.verbindungen
                                if eid not in (v.get("von"), v.get("nach"))]
        if self.fokus == eid:
            self.fokus = None
        return Ergebnis("geaendert", e, "geloescht")

    def verbindungen_mit_seiten(self):
        """Die Verbindungen mit den Andockseiten, wie sie gerade liegen (für
        die Datei: Obsidian zeichnet die Schnur dann genauso)."""
        raus = []
        for v in self.verbindungen:
            a, b = self.element(v.get("von")), self.element(v.get("nach"))
            if a is None or b is None:
                continue
            sa, sb = schnur.seiten(a, b)
            raus.append(dict(v, von_seite=sa, nach_seite=sb))
        return raus

    # ── Gleiten ───────────────────────────────────────────────────────
    def gleiten(self):
        """Ein Bild weiter: die Anzeige-Lage rückt auf (vx, vy) zu.
        -> True, solange sie noch nicht angekommen ist (dann will die Ansicht
        schnell neu zeichnen). Ändert sich das Ziel, zählen die Bilder neu."""
        if not self.weich or self.ax is None:
            self.springen()
            return False
        ziel = (self.vx, self.vy)
        if ziel != self._gleit_ziel:
            self._gleit_ziel, self._gleit_bilder = ziel, 0
        self._gleit_bilder += 1
        if self._gleit_bilder >= GLEIT_BILDER:
            self.springen()
        else:
            self.ax = gleit_schritt(self.ax, self.vx)
            self.ay = gleit_schritt(self.ay, self.vy)
        return self.bewegt_sich()

    def springen(self):
        """Anzeige sofort aufs Ziel (Öffnen, Zentrieren)."""
        self.ax, self.ay = float(self.vx), float(self.vy)

    def bewegt_sich(self):
        """Gleitet der Ausschnitt gerade noch?"""
        return (self.weich and self.ax is not None
                and (self.ax, self.ay) != (float(self.vx), float(self.vy)))

    def anzeige_lage(self):
        """Welche Weltzelle oben links gezeichnet wird."""
        if not self.weich or self.ax is None:
            return self.vx, self.vy
        return _runden(self.ax), _runden(self.ay)

    # ── Bild ──────────────────────────────────────────────────────────
    def bild(self, hoehe, breite):
        """Das sichtbare Stück als Zeilen: [[(spalte, text, rolle), …], …].
        Rollen: raster, schnur, schnur_vor, rahmen, fokus, griff, ziel, text,
        leise (+ was eine Art selbst liefert). Merkt sich die Größe — von ihr
        hängen Folgen, Mitte und `+` ab. Gezeichnet wird an der
        Anzeige-Lage (beim Gleiten zwischen alter und neuer Lage)."""
        self.vw, self.vh = max(1, breite), max(1, hoehe)
        ox, oy = self.anzeige_lage()
        netz = [[(" ", None)] * self.vw for _ in range(self.vh)]

        def setze(wx, wy, ch, rolle):
            x, y = wx - ox, wy - oy
            if 0 <= x < self.vw and 0 <= y < self.vh:
                netz[y][x] = (ch, rolle)

        for y in range(self.vh):                        # Raster
            wy = oy + y
            if wy % RASTER_Y:
                continue
            for x in range(self.vw):
                if (ox + x) % RASTER_X == 0:
                    netz[y][x] = ("·", "raster")
        sicht = self._in_der_hand(ox, oy)
        self._schnuere(setze, sicht)
        oben = [self.griff and self.griff["id"], self.ziel, self.fokus]
        for e in sorted(self.elemente, key=lambda e: e.get("id") in oben):
            self._kasten(sicht.get(e.get("id"), e), setze, ox, oy)
        return self._zeilen(netz)

    def _in_der_hand(self, ox, oy):
        """{id: Kopie} für das gegriffene Element, um so viel verschoben, wie
        die Anzeige dem Ziel (vx, vy) noch hinterherläuft — so bleibt es auf
        dem Schirm, wo es nach dem Gleiten liegt, und reist mit der Ansicht.
        Die Lage im Element selbst bleibt die Wahrheit."""
        if not self.griff or (ox, oy) == (self.vx, self.vy):
            return {}
        e = self.element(self.griff["id"])
        if e is None:
            return {}
        return {e["id"]: dict(e, x=e["x"] - self.vx + ox, y=e["y"] - self.vy + oy)}

    def _schnuere(self, setze, sicht=None):
        sicht = sicht or {}
        paare = [(v, "schnur") for v in self.verbindungen]
        if self.modus == "verbinden" and self.ziel:
            paare.append(({"von": self.fokus, "nach": self.ziel}, "schnur_vor"))
        for v, rolle in paare:
            a, b = self.element(v.get("von")), self.element(v.get("nach"))
            a, b = sicht.get(v.get("von"), a), sicht.get(v.get("nach"), b)
            if a is None or b is None or a is b:
                continue
            punkte = schnur.weg(a, b)
            netz, ende = schnur.richtungen(punkte)
            for (x, y), r in netz.items():
                setze(x, y, schnur.zeichen(r), rolle)
            if ende:
                setze(ende[0], ende[1], schnur.spitze(ende[2]), rolle)
            if v.get("label"):
                m = schnur.halbe(punkte)
                for i, ch in enumerate(v["label"][:24]):
                    setze(m[0] + i, m[1], ch, "leise")

    def _kasten(self, e, setze, ox, oy):
        x, y, w, h = e["x"], e["y"], max(3, e["w"]), max(3, e["h"])
        if self.griff and self.griff["id"] == e["id"]:
            rand, rolle = "╔═╗║╚╝", "griff"
        elif e["id"] == self.ziel:
            rand, rolle = "┏━┓┃┗┛", "ziel"
        elif e["id"] == self.fokus:
            rand, rolle = "┏━┓┃┗┛", "fokus"
        else:
            rand = "┌─┐│└┘"
            rolle = getattr(self.arten.holen(e.get("art")), "rolle", "rahmen")
        # Schnell raus, wenn der Kasten ganz außerhalb liegt.
        if x + w <= ox or x >= ox + self.vw or y + h <= oy or y >= oy + self.vh:
            return
        for i in range(w):
            setze(x + i, y, rand[1], rolle)
            setze(x + i, y + h - 1, rand[1], rolle)
        for j in range(1, h - 1):
            setze(x, y + j, rand[3], rolle)
            setze(x + w - 1, y + j, rand[3], rolle)
            for i in range(1, w - 1):
                setze(x + i, y + j, " ", "text")         # deckt, was darunter liegt
        setze(x, y, rand[0], rolle)
        setze(x + w - 1, y, rand[2], rolle)
        setze(x, y + h - 1, rand[4], rolle)
        setze(x + w - 1, y + h - 1, rand[5], rolle)
        innen = self.arten.holen(e.get("art")).zeichne(e, w - 2, h - 2) or []
        for j, zeile in enumerate(innen[:h - 2]):
            stuecke = [(zeile, "text")] if isinstance(zeile, str) else zeile
            sp = 0
            for text, r in stuecke:
                for ch in str(text):
                    if sp >= w - 2:
                        break
                    setze(x + 1 + sp, y + 1 + j, ch, r)
                    sp += 1

    @staticmethod
    def _zeilen(netz):
        """Gleiche Rolle hintereinander zu einem Stück zusammenfassen."""
        raus = []
        for reihe in netz:
            stuecke, start, text, rolle = [], 0, "", None
            for x, (ch, r) in enumerate(reihe):
                if r != rolle:
                    if text and rolle is not None:
                        stuecke.append((start, text, rolle))
                    start, text, rolle = x, "", r
                text += ch
            if text and rolle is not None:
                stuecke.append((start, text, rolle))
            raus.append(stuecke)
        return raus
