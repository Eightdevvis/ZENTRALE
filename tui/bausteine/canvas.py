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
#   bei_enter(element)         -> None (enter greift, wie beim Zettel) oder
#                              eine Aktion, die als Ergebnis „aktion" zur
#                              Ansicht geht; die Art entscheidet
#   blaettern(element, schritt) Bild↑/Bild↓ auf dem gewählten Kasten: im
#                              Inneren blättern (eigene Lage am Element unter
#                              „_oben", wird nie gespeichert). Hier docken
#                              später Kacheln mit langem Inhalt an (Kalender).
#
# Bedienung (Zustände, Sasha 2026-10-09, Belegung siehe
# memory/system/desk_view.md):
#   ruhe       ↑↓←→ Fokus springt zum nächsten Kasten in der Richtung,
#              enter greift, + legt einen neuen an (gleich gegriffen),
#              e bearbeiten, v verbinden, d löschen (Rückfrage), esc zurück
#   greifen    ↑↓←→ schiebt um eine Zelle, enter legt ab, esc setzt zurück
#              (ein neuer verschwindet wieder)
#   verbinden  ↑↓←→ springt mit dem Ziel, die Schnur wird vorgezeigt,
#              enter/v verbindet (schon verbunden → Rückfrage „lösen?"),
#              esc bricht ab
#   frage      j ja, n/esc nein
#   überall    shift+↑↓←→ schiebt den Ausschnitt; beim Greifen reist der
#              Kasten mit (er liegt ja in der Hand)

import curses
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
#   "aktion"      enter auf einem Kasten, dessen Art eine eigene Aktion hat
#                 (`bei_enter` der Art, z. B. eine Kachel: („oeffnen", ref)
#                 → die Ansicht reicht es weiter); grund = was die Art meldet
Ergebnis = namedtuple("Ergebnis", "art element grund")

PAN_X, PAN_Y = 6, 3                     # so weit schiebt shift+Pfeil den Ausschnitt
RASTER_X, RASTER_Y = 10, 5              # leise Punkte zur Orientierung beim Schieben


# ── Tasten → Ereignisse ───────────────────────────────────────────────
# Shift+Pfeil kommt je nach Terminal (und tmux) verschieden an: als
# KEY_SLEFT/KEY_SRIGHT/KEY_SR/KEY_SF oder als erweiterte Taste mit dem
# terminfo-Namen kLFT2/kRIT2/kUP2/kDN2 (Modifier 2 = Shift), deren Nummer
# von Terminal zu Terminal wechselt. Darum zählt der NAME (curses.keyname),
# nicht die Zahl; die curses-Konstanten nur als Rückfall, wenn kein Name
# zu haben ist (Tests ohne initscr).
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
_SHIFT_FOLGE = {"[1;2A": "hoch", "[1;2B": "runter", "[1;2C": "rechts", "[1;2D": "links"}
_BUCHSTABEN = {ord("+"): "neu", ord("e"): "bearbeiten", ord("v"): "verbinden",
               ord("d"): "loeschen", curses.KEY_DC: "loeschen",
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


def esc_folge(folge):
    """Bytes nach einem ESC (ohne das ESC) -> "pan_<richtung>", "esc" (nichts
    folgte) oder None (eine Folge, die der Canvas nicht kennt, z. B. Alt+x)."""
    if not folge:
        return "esc"
    r = _SHIFT_FOLGE.get("".join(chr(c) for c in folge if 0 <= c < 128))
    return "pan_" + r if r else None


def taste_deuten(ch, name=None):
    """Taste -> Ereignis des Canvas oder None."""
    p = shift_pfeil(ch, name)
    if p:
        return "pan_" + p
    if ch in _PFEILE:
        return _PFEILE[ch]
    return _BUCHSTABEN.get(ch)


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

    def _pan(self, richtung):
        dx, dy = {"links": (-PAN_X, 0), "rechts": (PAN_X, 0),
                  "hoch": (0, -PAN_Y), "runter": (0, PAN_Y)}[richtung]
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
        if ev == "neu" and self.neu_fabrik:
            mx, my = self.mitte_des_ausschnitts()
            e = self.neu_fabrik(mx, my)
            if e:
                e["x"], e["y"] = mx - e["w"] // 2, my - e["h"] // 2
                self.elemente.append(e)
                self.fokus = e["id"]
                self.griff = {"id": e["id"], "x": e["x"], "y": e["y"], "neu": True}
                self.modus = "greifen"
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
        if ev == "enter":
            bei_enter = getattr(self.arten.holen(fokus.get("art")), "bei_enter", None)
            aktion = bei_enter(fokus) if bei_enter else None
            if aktion is not None:
                return Ergebnis("aktion", fokus, aktion)
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

    # ── Bild ──────────────────────────────────────────────────────────
    def bild(self, hoehe, breite):
        """Das sichtbare Stück als Zeilen: [[(spalte, text, rolle), …], …].
        Rollen: raster, schnur, schnur_vor, rahmen, fokus, griff, ziel, text,
        leise (+ was eine Art selbst liefert). Merkt sich die Größe — von ihr
        hängen Folgen, Mitte und `+` ab."""
        self.vw, self.vh = max(1, breite), max(1, hoehe)
        netz = [[(" ", None)] * self.vw for _ in range(self.vh)]

        def setze(wx, wy, ch, rolle):
            x, y = wx - self.vx, wy - self.vy
            if 0 <= x < self.vw and 0 <= y < self.vh:
                netz[y][x] = (ch, rolle)

        for y in range(self.vh):                        # Raster
            wy = self.vy + y
            if wy % RASTER_Y:
                continue
            for x in range(self.vw):
                if (self.vx + x) % RASTER_X == 0:
                    netz[y][x] = ("·", "raster")
        self._schnuere(setze)
        oben = [self.griff and self.griff["id"], self.ziel, self.fokus]
        for e in sorted(self.elemente, key=lambda e: e.get("id") in oben):
            self._kasten(e, setze)
        return self._zeilen(netz)

    def _schnuere(self, setze):
        paare = [(v, "schnur") for v in self.verbindungen]
        if self.modus == "verbinden" and self.ziel:
            paare.append(({"von": self.fokus, "nach": self.ziel}, "schnur_vor"))
        for v, rolle in paare:
            a, b = self.element(v.get("von")), self.element(v.get("nach"))
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

    def _kasten(self, e, setze):
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
        if x + w <= self.vx or x >= self.vx + self.vw or y + h <= self.vy or y >= self.vy + self.vh:
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
