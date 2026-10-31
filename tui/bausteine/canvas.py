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
#   grenzen(element)           -> ((min_w, min_h), (max_w, max_h)) Außenmaß
#                              mit Rahmen, für `r` (Größe ändern); ohne gilt
#                              GROESSE_MIN / GROESSE_MAX (2026-10-10)
#   rand_von(element)          -> six frame characters (┌─┐│└┘ order) and
#   rolle_von(element)         -> frame role per element (2026-10-30,
#                              Schematix: states readable without colour)
#   rand_fokus(element)        -> six frame characters for the focused /
#                              target element (2026-10-31; default ┏━┓┃┗┛)
#
# Connections may carry `rolle` (colour role of the line), `stil` ("pcb",
# "planned", "off": rounded traces with solder dots, schnur.py),
# `rolle_ende` (role of the solder dots) and `punkt` (their glyph). The view's `passt(quelle, ziel)`
# refuses unfitting connections: red ✕ at the cursor, Ergebnis "abgelehnt".
#
# Bedienung (Zustände, Sasha 2026-10-09; Belegung: die Tastentabelle
# TASTEN unten, memory/hub/desk_view.md):
#   ruhe       ↑↓←→ / w a s d move a free cursor over the surface
#              (2026-10-31, see "Cursor" below); the piece under it is
#              focused. tab / shift+tab jump to the next / previous piece.
#              enter greift, + legt einen neuen an (gleich gegriffen, at the
#              cursor), e bearbeiten, v verbinden, x/del löschen (Rückfrage),
#              o öffnen (wenn die Art es kann), esc zurück
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
#   groesse    (r, 2026-10-10, Sasha: „die Größe muss man nachträglich ändern
#              können") ←→ schmaler/breiter, ↑↓ niedriger/höher um eine
#              Zelle, oben links bleibt stehen; enter behält (gespeichert),
#              esc setzt die alte Größe zurück. Unter das Minimum der Art geht
#              es nicht (Anschlag mit kurzem Hinweis), über das Maximum auch
#              nicht. Der Ausschnitt folgt der Ecke unten rechts.
#   überall    W A S D (Großbuchstaben) schiebt den Ausschnitt, ebenso
#              shift+↑↓←→ und alt+↑↓←→ and the mouse wheel / two-finger
#              scroll; beim Greifen reist der Kasten mit (er liegt ja in der
#              Hand). Lower-case w a s d are the arrows in every state.
#
# Cursor (2026-10-31, Sasha: arrows only "aimed at the pieces that are
# there instead of moving smoothly over the surface"): (cx, cy) is a world
# cell, None until first used. Arrows move it cell by cell (held: the same
# acceleration and cap as panning), the view follows when it nears the
# edge, and it may go into empty space within the growable area
# (`pan_bounds`). Panning does not move it; an arrow while it is out of
# view starts again from the middle of the view. Mouse (`zeiger`, `rad`):
# a click puts the cursor on the cell, dragging a piece carries it,
# dragging empty space drags the surface, the wheel pans.
#
# Weich (2026-10-10, Sasha: „ich möchte dass die bewegung über das canvas
# weicher ist"): (vx, vy) bleibt die Lage, mit der alles rechnet. Gezeichnet
# wird eine Anzeige-Lage (ax, ay), die jedes Bild ein Stück auf (vx, vy)
# zugleitet (`gleiten()`, die Ansicht ruft es je Bild). Aus, solange die
# Ansicht `weich` nicht einschaltet — dann zeichnet bild() genau (vx, vy).
# Was man in der Hand hat, liegt beim Gleiten fest auf dem Schirm (am Ziel
# des Ausschnitts gerechnet, `_in_der_hand`): es gleitet mit der Ansicht,
# statt vorzuspringen und zurückzurutschen (2026-10-10).

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
#   "abgelehnt"   enter while connecting onto a target `passt` refuses;
#                 element = the target, grund = the short reason
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
# Pan limits (2026-10-31, Schematix "flies too fast, then stuck" — see
# memory/system/gefahrzonen.md). Held W/A/S/D at 20 repeats/s with ×4
# carried the view 480 columns / 240 rows a second, straight past the
# content into empty space where only the raster moves. Two limits, both
# here in the block so every app on it gets them:
#  - one step is at most a quarter of the view in that axis (never below
#    the base step) — the eye can still follow;
#  - growable surface (Sasha, same day: "the surface should stay endless —
#    you can extend it as far as you like"): the reachable area is the
#    content's bounding box plus one full view on every side
#    (Canvas.pan_bounds). You can always go a view past the edge into empty
#    space to put something new there, the area grows with what you build,
#    and you can never get lost far out in the void. Only the step that
#    would go further out is held; the opposite direction always moves at
#    once. While something is in the hand there is no limit (the carried
#    piece is content and pushes the edge out); an empty canvas is free.
PAN_VIEW_DIVISOR = 4
# Cursor (2026-10-31): base step per arrow (columns are half as tall as
# rows, so two columns feel like one row), accelerated like panning.
CURSOR_X, CURSOR_Y = 2, 1
# Mouse wheel / two-finger scroll: cells per notch. However many notches a
# fast swipe piles up into one frame, the view moves at most one capped
# pan step per frame (`rad`) — no fling.
RAD_X, RAD_Y = 4, 2


def pan_step(pos, d, lo, hi):
    """One pan step on one axis: pos + d, but not past lo/hi in the
    direction of travel (a position already beyond stays, never jumps
    back). PURE."""
    neu = pos + d
    if d > 0:
        return min(neu, max(pos, hi))
    if d < 0:
        return max(neu, min(pos, lo))
    return pos


# Größe ändern (2026-10-10): Grenzen (Außenmaß mit Rahmen) für Arten ohne
# eigenes `grenzen`. 3×3 ist der kleinste Kasten, den _kasten zeichnet; das
# Maximum ist nur ein Schutz gegen versehentliches Riesenwachsen.
GROESSE_MIN = (3, 3)
GROESSE_MAX = (400, 200)


def gleit_schritt(pos, ziel, anteil=GLEIT_ANTEIL):
    """Ein Bild Gleiten: pos rückt um `anteil` der Reststrecke auf ziel zu
    und rastet unter einer halben Zelle ein. PURE."""
    d = ziel - pos
    return float(ziel) if abs(d) < 0.5 else pos + d * anteil


def _runden(x):
    return int(math.floor(x + 0.5))      # nicht round(): 2.5 → 3, nicht 2


# ── Tasten (Tastentabelle, 2026-10-11) ──────────────────────────────
# Der Canvas trägt seine Tabelle selbst (tui/bausteine/tastenteil.py); die
# Ansicht bindet sie mit Tasten.zusammen ein und verteilt. Ansichten = die
# Zustände unten, „ruhe" ohne gewählten Kasten, „kasten" mit; eine Art mit
# eigenen Zeilen (`TASTEN` der Art: e, o, pgup/pgdn, f …) bekommt ihre
# eigene Ansicht unter ihrem Namen (tabelle_mit(arten)).
# Schieben: primär die Großbuchstaben W A S D (2026-10-10, Sasha: „ZENTRALE
# soll überall gleich gut funktionieren") — die kommen in jedem Terminal,
# tmux, macOS und Handy gleich an. Shift+Pfeile und Alt+Pfeile gehen dazu
# (ohne Text: verarbeitet, nicht gezeigt); xfce4-terminal schluckt
# Shift+↑↓ von Haus aus.
_SCHIEBEN = [("W/A/S/D", "schieben", "move view"), ("alt+↑↓←→", "schieben"),
             ("shift+↑↓←→", "schieben")]
# Lower-case w a s d are the arrows (2026-10-31, Sasha pressed them and
# nothing happened: only the capitals were bound). They move the cursor at
# rest, the piece while carrying, the target while connecting, the size
# while resizing. Delete moved from d to x/del to free them.
PFEILE = "↑↓←→ w/a/s/d"
CURSOR = (PFEILE, "waehlen", "move cursor")
SPRINGEN = [("tab", "springen", "next piece"), ("shift+tab", "springen")]
_KOPF = [CURSOR] + _SCHIEBEN[:1] + [("enter", "greifen", "grab")] + SPRINGEN
_FUSS = [("r", "groesse", "size"), ("+", "neu", "new"), ("v", "verbinden", "connect"),
         ("x", "loeschen", "delete"), ("del", "loeschen"), ("esc", "zu", "back")] + _SCHIEBEN[1:]
TASTEN = {
    "ruhe": [CURSOR, _SCHIEBEN[0], ("+", "neu", "new"),
             ("esc", "zu", "back")] + SPRINGEN + _SCHIEBEN[1:],
    "kasten": _KOPF + _FUSS,
    "greifen": [(PFEILE, "bewegen", "move"), _SCHIEBEN[0], ("enter", "ablegen", "drop"),
                ("esc", "zurueck", "cancel")] + _SCHIEBEN[1:],
    "verbinden": [(PFEILE, "ziel", "target"), _SCHIEBEN[0], ("enter/v", "verbinden", "connect"),
                  ("esc", "zurueck", "cancel")] + _SCHIEBEN[1:],
    "frage": [("j", "ja", "yes"), ("y", "ja"), ("n/esc", "nein", "no")],
    "groesse": [("←→ a/d", "aendern", "width"), ("↑↓ w/s", "aendern", "height"), _SCHIEBEN[0],
                ("enter", "behalten", "keep"), ("esc", "zurueck", "undo")] + _SCHIEBEN[1:],
}


def tabelle_mit(arten):
    """Die Tabelle des Canvas plus je Art mit eigenen Zeilen (`TASTEN` der
    Art) eine Ansicht unter ihrem Namen: Kopf (wählen, schieben, greifen),
    die Zeilen der Art, dann der Rest. Für Ansichten, die diese Arten
    registrieren (Desk)."""
    tab = {a: list(liste) for a, liste in TASTEN.items()}
    for art in arten.alle():
        zeilen = getattr(art, "TASTEN", None)
        if zeilen and art.name not in tab:
            tab[art.name] = _KOPF + list(zeilen) + _FUSS
    return tab


# Neutraler Tastenname → Richtung (Pfeile, W A S D, alt+/shift+Pfeil)
_PFEIL = {"up": "hoch", "down": "runter", "left": "links", "right": "rechts"}
_RICHTUNG = dict(_PFEIL, W="hoch", A="links", S="runter", D="rechts",
                 w="hoch", a="links", s="runter", d="rechts",
                 **{"alt+" + k: r for k, r in _PFEIL.items()},
                 **{"shift+" + k: r for k, r in _PFEIL.items()})


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

    def alle(self):
        return list(self._arten.values())

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
        self.modus = "ruhe"              # ruhe | greifen | verbinden | frage | groesse
        self.griff = None                # {"id", "x", "y", "neu"}
        self.ziel = None                 # verbinden: id des Ziels
        self.frage = None                # {"was": "loeschen"|"loesen", "id", "text"}
        # Größe ändern: {"id", "w", "h" (die alte Größe), "min", "max",
        # "anschlag" (Hinweis, wenn eine Grenze erreicht ist, sonst "")}
        self.groesse = None
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
        # vor_groesse(element) -> bool: die Ansicht darf vor `r` noch etwas
        # holen (Desk: Grenzen einer Kachel beim Hub); False = es geht nicht.
        self.vor_groesse = None
        # passt(quelle, ziel) -> None | short reason (2026-10-30, Schematix):
        # the fit check while connecting. A reason draws a red ✕ at the
        # cursor; enter does not attach and reports Ergebnis("abgelehnt",
        # ziel, reason) — refused, never greyed out. None = everything fits.
        self.passt = None
        # The free cursor (world cell) — None until an arrow or a click
        # puts it somewhere.
        self.cx = self.cy = None
        # Where the host draws the canvas on the screen (row, column of the
        # view's top left cell) — for the mouse. The host sets it each frame.
        self.ursprung = (0, 0)
        self._zug = None                 # mouse drag: {"id", "x", "y", "bewegt"}

    def __repr__(self):                  # Zustand sichtbar machen (Tests vergleichen repr)
        return "Canvas(%r)" % ((self.vx, self.vy, self.cx, self.cy, self.fokus, self.modus, self.griff,
                                self.ziel, self.frage, self.groesse, self.elemente,
                                self.verbindungen),)

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
    TASTEN = TASTEN

    def ansicht(self):
        """Welche Ansicht der Tabelle gerade offen ist: der Zustand; in Ruhe
        „ruhe" (nichts gewählt), der Name der gewählten Art (hat sie eigene
        Zeilen, tabelle_mit) oder „kasten"."""
        if self.modus != "ruhe":
            return self.modus
        fokus = self.element(self.fokus)
        if fokus is None:
            return "ruhe"
        art = self.arten.holen(fokus.get("art"))
        return art.name if getattr(art, "TASTEN", None) else "kasten"

    # Die Aktionen der Tabelle: neutraler Tastenname → Ereignis für taste().
    def aktion_waehlen(self, taste):
        return self.taste(_RICHTUNG[taste])

    aktion_bewegen = aktion_ziel = aktion_aendern = aktion_waehlen

    def aktion_schieben(self, taste):
        return self.taste("pan_" + _RICHTUNG[taste])

    def aktion_springen(self, taste):
        return self.taste("vorheriger" if taste == "shift+tab" else "naechster")

    def aktion_greifen(self, _taste):
        return self.taste("enter")

    aktion_ablegen = aktion_behalten = aktion_greifen

    def aktion_zu(self, _taste):
        return self.taste("esc")

    aktion_zurueck = aktion_zu

    def aktion_verbinden(self, taste):
        return self.taste("verbinden" if self.modus == "ruhe" else "enter")

    def aktion_neu(self, _taste):
        return self.taste("neu")

    def aktion_bearbeiten(self, _taste):
        return self.taste("bearbeiten")

    def aktion_loeschen(self, _taste):
        return self.taste("loeschen")

    def aktion_oeffnen(self, _taste):
        return self.taste("oeffnen")

    def aktion_groesse(self, _taste):
        fokus = self.element(self.fokus)
        if fokus is not None and self.vor_groesse and not self.vor_groesse(fokus):
            return None
        return self.taste("groesse")

    def aktion_blaettern(self, taste):
        return self.taste("blaettern_hoch" if taste == "pgup" else "blaettern_runter")

    def aktion_art_taste(self, taste):
        return self.taste("zeichen:" + taste)

    def aktion_ja(self, _taste):
        return self.taste("ja")

    def aktion_nein(self, _taste):
        return self.taste("nein")

    def taste(self, ereignis):
        """Ein Ereignis verarbeiten -> Ergebnis oder None. Ereignisse:
        hoch/runter/links/rechts, pan_<richtung>, enter, esc, neu,
        bearbeiten, verbinden, loeschen, oeffnen, groesse,
        blaettern_hoch/_runter, ja, nein, zeichen:<x> (an die Art)."""
        if ereignis is None:
            return None
        if ereignis.startswith("pan_") and self.modus != "frage":
            self._pan(ereignis[4:])
            return None
        return {"ruhe": self._ruhe, "greifen": self._greifen, "verbinden": self._verbinden,
                "frage": self._frage, "groesse": self._groesse}[self.modus](ereignis)

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

    def flaeche(self):
        """The growable area (x0, y0, x1, y1), end exclusive: the content's
        bounding box plus one full view on every side. None = no limit
        (empty canvas, or something in the hand)."""
        if not self.elemente or self.modus == "greifen":
            return None
        els = self.elemente
        return (min(e["x"] for e in els) - self.vw, min(e["y"] for e in els) - self.vh,
                max(e["x"] + e["w"] for e in els) + self.vw,
                max(e["y"] + e["h"] for e in els) + self.vh)

    def pan_bounds(self):
        """(lo_x, hi_x, lo_y, hi_y) for vx/vy while panning: the view stays
        inside the growable area (`flaeche`) — at most one view past the
        content's edge. None = no limit."""
        f = self.flaeche()
        if f is None:
            return None
        return f[0], f[2] - self.vw, f[1], f[3] - self.vh

    def _deckel(self):
        """The largest pan step per axis: a quarter of the view, never below
        the base step."""
        return (max(PAN_X, self.vw // PAN_VIEW_DIVISOR), max(PAN_Y, self.vh // PAN_VIEW_DIVISOR))

    def _pan(self, richtung):
        f = self._pan_faktor_neu(richtung)
        kx, ky = self._deckel()
        px, py = min(_runden(PAN_X * f), kx), min(_runden(PAN_Y * f), ky)
        dx, dy = {"links": (-px, 0), "rechts": (px, 0),
                  "hoch": (0, -py), "runter": (0, py)}[richtung]
        self._pan_um(dx, dy)

    def _pan_um(self, dx, dy):
        """Move the view by (dx, dy) within the growable area; while
        carrying, the piece travels along and there is no limit."""
        if self.modus == "greifen":
            self.vx += dx
            self.vy += dy
            e = self.element(self.griff["id"])
            e["x"] += dx
            e["y"] += dy
            return
        g = self.pan_bounds()
        if g is None:
            self.vx += dx
            self.vy += dy
            return
        self.vx = pan_step(self.vx, dx, g[0], g[1])
        self.vy = pan_step(self.vy, dy, g[2], g[3])

    # ── Cursor (2026-10-31) ───────────────────────────────────────────
    def unter(self, wx, wy):
        """The topmost piece covering world cell (wx, wy), or None."""
        for e in reversed(self.elemente):
            if e["x"] <= wx < e["x"] + max(3, e["w"]) and e["y"] <= wy < e["y"] + max(3, e["h"]):
                return e
        return None

    def _im_ausschnitt(self, wx, wy):
        return self.vx <= wx < self.vx + self.vw and self.vy <= wy < self.vy + self.vh

    def ablage_punkt(self):
        """Where `+` puts a new piece: the cursor if it is in view, else the
        middle of the view."""
        if self.cx is not None and self._im_ausschnitt(self.cx, self.cy):
            return self.cx, self.cy
        return self.mitte_des_ausschnitts()

    def cursor_setzen(self, wx, wy):
        """Cursor onto a world cell; the piece under it gets the focus."""
        self.cx, self.cy = wx, wy
        e = self.unter(wx, wy)
        self.fokus = e["id"] if e else None

    def _cursor_gehen(self, richtung):
        """One arrow at rest: the cursor moves (held: accelerating, capped
        at a quarter view), stays inside the growable area and the view
        follows when it nears the edge."""
        fokus = self.element(self.fokus)
        if fokus is not None and (self.cx is None or self.unter(self.cx, self.cy) is not fokus):
            self.cx, self.cy = schnur.mitte(fokus)       # go on from the focused piece
        elif self.cx is None or not self._im_ausschnitt(self.cx, self.cy):
            self.cx, self.cy = self.mitte_des_ausschnitts()
        f = self._pan_faktor_neu("cursor_" + richtung)
        kx, ky = self._deckel()
        sx, sy = min(_runden(CURSOR_X * f), kx), min(_runden(CURSOR_Y * f), ky)
        dx, dy = {"links": (-sx, 0), "rechts": (sx, 0),
                  "hoch": (0, -sy), "runter": (0, sy)}[richtung]
        g = self.flaeche()
        if g is None:
            x, y = self.cx + dx, self.cy + dy
        else:
            x = pan_step(self.cx, dx, g[0], g[2] - 1)
            y = pan_step(self.cy, dy, g[1], g[3] - 1)
        self.cursor_setzen(x, y)
        rx, ry = min(4, self.vw // 4), min(2, self.vh // 4)
        if x < self.vx + rx:
            self.vx = x - rx
        elif x >= self.vx + self.vw - rx:
            self.vx = x - self.vw + rx + 1
        if y < self.vy + ry:
            self.vy = y - ry
        elif y >= self.vy + self.vh - ry:
            self.vy = y - self.vh + ry + 1

    # ── Mouse (2026-10-31) ────────────────────────────────────────────
    # The host reads the terminal (tui/bausteine/sgr_mouse.py) and hands in
    # screen coordinates; `ursprung` turns them into cells of the drawn view.
    def rad(self, dx, dy):
        """Wheel / two-finger scroll: dx, dy notches piled up in one frame
        (negative = left/up). Pans at most one capped step per axis — a
        fast swipe can't fling. Not while a question is open."""
        if self.modus == "frage" or not (dx or dy):
            return None
        kx, ky = self._deckel()
        px = max(-kx, min(kx, dx * RAD_X))
        py = max(-ky, min(ky, dy * RAD_Y))
        self._pan_um(px, py)
        return None

    def maus(self, ereignisse):
        """Mouse events of one frame (sgr_mouse.Ereignis: art, x, y, dx,
        dy) → the last Ergebnis (a drop) or None."""
        raus = None
        for e in ereignisse:
            if e.art == "wheel":
                self.rad(e.dx, e.dy)
            else:
                raus = self.zeiger(e.art, e.x, e.y) or raus
        return raus

    def _welt(self, sx, sy):
        """Screen cell → world cell of what is drawn there (at the display
        position while gliding) — None outside the view."""
        x, y = sx - self.ursprung[1], sy - self.ursprung[0]
        if not (0 <= x < self.vw and 0 <= y < self.vh):
            return None
        ox, oy = self.anzeige_lage()
        return ox + x, oy + y

    def zeiger(self, art, sx, sy):
        """Left button: art "press" | "drag" | "release" at screen (sx, sy).
        Press puts the cursor there (the piece under it is focused); dragging
        a piece carries it and release drops it (Ergebnis like enter);
        dragging empty space drags the surface along. At rest only — while
        connecting a press picks the target; otherwise ignored."""
        w = self._welt(sx, sy)
        if art == "press":
            self._zug = None
            if w is None:
                return None
            if self.modus == "verbinden":
                e = self.unter(*w)
                if e is not None and e["id"] != self.fokus:
                    self.ziel = e["id"]
                return None
            if self.modus != "ruhe":
                return None
            self.cursor_setzen(*w)
            e = self.unter(*w)
            self._zug = {"id": e["id"] if e else None, "x": w[0], "y": w[1], "bewegt": False}
            return None
        zug = self._zug
        if zug is None:
            return None
        if art == "drag":
            if w is None:
                return None
            dx, dy = w[0] - zug["x"], w[1] - zug["y"]
            if not (dx or dy):
                return None
            zug["bewegt"] = True
            if zug["id"] is None:                  # drag the surface along
                if self.modus == "ruhe":
                    self._pan_um(-dx, -dy)
                    self.springen()                # the cell under the hand stays the same
                return None
            if self.modus == "ruhe" and self.fokus == zug["id"]:
                self._ruhe("enter")                # pick it up, as enter does
            if self.modus == "greifen" and self.griff["id"] == zug["id"]:
                e = self.element(zug["id"])
                e["x"] += dx
                e["y"] += dy
                zug["x"], zug["y"] = w
                self.cursor_setzen(*w)
                self.fokus = zug["id"]
            return None
        # release
        self._zug = None
        if zug["id"] is not None and zug["bewegt"] and self.modus == "greifen":
            return self._greifen("enter")
        return None

    def _springen(self, schritt):
        """tab / shift+tab: the next / previous piece in reading order (top
        to bottom, left to right); the first jump takes the piece nearest
        the middle of the view."""
        reihe = sorted(self.elemente, key=lambda e: (e["y"], e["x"]))
        if not reihe:
            return
        fokus = self.element(self.fokus)
        neu = (reihe[(reihe.index(fokus) + schritt) % len(reihe)] if fokus in reihe
               else self._naechster_zur_mitte())
        self.fokus = neu["id"]
        self.cx, self.cy = schnur.mitte(neu)
        self.folgen(neu)

    def _ruhe(self, ev):
        fokus = self.element(self.fokus)
        if ev in ("hoch", "runter", "links", "rechts"):
            self._cursor_gehen(ev)
            return None
        if ev in ("naechster", "vorheriger"):
            self._springen(1 if ev == "naechster" else -1)
            return None
        if ev == "neu":
            if self.neu_fabrik is None:
                return Ergebnis("neu_waehlen", None, "")
            mx, my = self.ablage_punkt()
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
        elif ev == "groesse":
            self.groesse_beginnen(fokus)
        return None

    # ── Größe ändern (r, 2026-10-10) ──────────────────────────────────
    def grenzen(self, e):
        """(min, max) als (w, h) Außenmaß — von der Art, sonst die Vorgabe."""
        g = getattr(self.arten.holen(e.get("art")), "grenzen", None)
        g = g(e) if g else None
        return tuple(g[0]) if g else GROESSE_MIN, tuple(g[1]) if g else GROESSE_MAX

    def groesse_beginnen(self, e):
        mi, ma = self.grenzen(e)
        self.groesse = {"id": e["id"], "w": e["w"], "h": e["h"], "min": mi, "max": ma,
                        "anschlag": ""}
        self.modus = "groesse"

    def _groesse(self, ev):
        g = self.groesse
        e = self.element(g["id"])
        schritte = {"rechts": (1, 0), "links": (-1, 0), "runter": (0, 1), "hoch": (0, -1)}
        if ev in schritte:
            dw, dh = schritte[ev]
            w, h = e["w"] + dw, e["h"] + dh
            # Ein Schritt darf nie unter das Minimum oder über das Maximum
            # führen; liegt der Kasten schon außerhalb (von Obsidian), geht
            # es nur in Richtung der Grenzen.
            if (dw < 0 and w < g["min"][0]) or (dh < 0 and h < g["min"][1]):
                g["anschlag"] = "kleiner geht nicht (mind. %d×%d)" % g["min"]
                return None
            if (dw > 0 and w > g["max"][0]) or (dh > 0 and h > g["max"][1]):
                g["anschlag"] = "größer geht nicht (höchstens %d×%d)" % g["max"]
                return None
            e["w"], e["h"], g["anschlag"] = w, h, ""
            # Der Ecke unten rechts folgen — sie ist es, die wächst.
            self.folgen({"x": e["x"] + e["w"] - 1, "y": e["y"] + e["h"] - 1, "w": 1, "h": 1})
            return None
        if ev == "enter":
            self.groesse, self.modus = None, "ruhe"
            if (e["w"], e["h"]) != (g["w"], g["h"]):
                return Ergebnis("geaendert", e, "groesse")
            return None
        if ev == "esc":
            e["w"], e["h"] = g["w"], g["h"]
            self.groesse, self.modus = None, "ruhe"
        return None

    def neu_ablegen(self, e):
        """Ein frisches Element mitten in den Ausschnitt (or onto the cursor,
        `ablage_punkt`) legen und gleich greifen (enter legt ab =
        gespeichert, esc nimmt es wieder weg)."""
        mx, my = self.ablage_punkt()
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
            grund = self.passt(quelle, ziel) if self.passt else None
            if grund:
                self.ziel, self.modus = None, "ruhe"
                return Ergebnis("abgelehnt", ziel, grund)
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
        oben = [self.griff and self.griff["id"], self.groesse and self.groesse["id"],
                self.ziel, self.fokus]
        for e in sorted(self.elemente, key=lambda e: e.get("id") in oben):
            self._kasten(sicht.get(e.get("id"), e), setze, ox, oy)
        # The cursor on empty space (on a piece, the piece's focus frame
        # shows where it is).
        if self.modus == "ruhe" and self.cx is not None and self.unter(self.cx, self.cy) is None:
            setze(self.cx, self.cy, "+", "fokus")
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
        paare = [(v, v.get("rolle") or "schnur") for v in self.verbindungen]
        abgelehnt = None
        if self.modus == "verbinden" and self.ziel:
            vor = {"von": self.fokus, "nach": self.ziel}
            if self.passt:
                abgelehnt = self.passt(self.element(self.fokus), self.element(self.ziel))
            paare.append((vor, "abgelehnt" if abgelehnt else "schnur_vor"))
        for v, rolle in paare:
            a, b = self.element(v.get("von")), self.element(v.get("nach"))
            a, b = sicht.get(v.get("von"), a), sicht.get(v.get("nach"), b)
            if a is None or b is None or a is b:
                continue
            punkte = schnur.weg(a, b)
            netz, ende = schnur.richtungen(punkte)
            stil = v.get("stil")
            for (x, y), r in netz.items():
                setze(x, y, schnur.zeichen(r, stil), rolle)
            punkt = v.get("rolle_ende") or rolle   # solder dots may have their own role
            dot = v.get("punkt") or schnur.LOETPUNKT   # … and their own glyph (2026-10-31)
            if stil and punkte:                    # solder dots at both ends (pcb)
                setze(punkte[0][0], punkte[0][1], dot, punkt)
            if ende:
                if rolle == "abgelehnt":           # the red ✕ at the cursor (2026-10-30)
                    setze(ende[0], ende[1], "✕", rolle)
                elif stil:
                    setze(ende[0], ende[1], dot, punkt)
                else:
                    setze(ende[0], ende[1], schnur.spitze(ende[2]), rolle)
            if v.get("label"):
                m = schnur.halbe(punkte)
                for i, ch in enumerate(v["label"][:24]):
                    setze(m[0] + i, m[1], ch, "leise")

    def _kasten(self, e, setze, ox, oy):
        x, y, w, h = e["x"], e["y"], max(3, e["w"]), max(3, e["h"])
        if self.griff and self.griff["id"] == e["id"]:
            rand, rolle = "╔═╗║╚╝", "griff"
        elif self.groesse and self.groesse["id"] == e["id"]:
            # Gestrichelt mit Griff-Ecke unten rechts: die Ecke wächst.
            rand, rolle = "┏╍┓╏┗◢", "groesse"
        elif e["id"] in (self.ziel, self.fokus):
            # An art may draw focus and target in its own frame (2026-10-31,
            # Schematix: a thin glowing outline instead of the heavy box).
            art = self.arten.holen(e.get("art"))
            rand = art.rand_fokus(e) if hasattr(art, "rand_fokus") else "┏━┓┃┗┛"
            rolle = "ziel" if e["id"] == self.ziel else "fokus"
        else:
            # An art may give each element its own frame and role (2026-10-30,
            # Schematix: node ┏━┓, thing ╔═╗, planned ┌╌┐ — readable without
            # colour); otherwise the plain frame in the art's role.
            art = self.arten.holen(e.get("art"))
            rand = art.rand_von(e) if hasattr(art, "rand_von") else "┌─┐│└┘"
            rolle = art.rolle_von(e) if hasattr(art, "rolle_von") else getattr(art, "rolle", "rahmen")
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
