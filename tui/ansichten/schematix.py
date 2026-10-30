# tui/ansichten/schematix.py
#
# Schematix — the wiring map as an app (memory/hub/schematix.md; plan
# memory/hub/building_kit_plan.md 6, steps 13–15; look:
# memory/hub/schematix_style.md). One plan is a **scheme**, making one is
# **scheming**. Opened from the Erschaffen wheel ("schematix").
#
# Built ON the Desk building block: the board is tui/bausteine/canvas.py (the
# same canvas, wires laid fresh from positions every frame); the pieces are
# one canvas art (schematix_arten.py); panels and colours: schematix_bild.py.
# The map itself is never computed here — GET /api/schematix/map lays it from
# the truths (this node's projection, the other nodes' descriptions), so the
# drawing is the wiring: nothing on the board is a copy.
#
# Keys (one table, tasten.py; mainstream and collision-free letters):
#   ↑↓←→ select · W A S D move the view · 1–5 layers on/off (sync, services,
#   hardware, network, power) · i versions panel of a node · c colours ·
#   esc back

import threading
import time

from . import schematix_bild
from .basis import api_call
from .schematix_arten import ART, Piece, node_height
from .tasten import Tasten
from .translate import _

try:
    from tui.bausteine import canvas as cv
    from tui.bausteine.farbwaehler import Farbwaehler
except ImportError:                     # started as a script: tui/ is on the path
    from bausteine import canvas as cv
    from bausteine.farbwaehler import Farbwaehler

LAYERS = ("data", "services", "hardware", "network", "power")
REFRESH_S = 30.0                        # the map is laid fresh this often while open

_PAN = [("W/A/S/D", "schieben", "move view"), ("alt+↑↓←→", "schieben"), ("shift+↑↓←→", "schieben")]
_BOARD = ([("↑↓←→", "waehlen", "select"), _PAN[0], ("1/2/3/4/5", "ebene", "layers"),
           ("c", "farben", "colours"), ("esc", "zu", "back")] + _PAN[1:])


def elements(m, layers, offen=()):
    """Canvas elements for the visible pieces (things hide with the hardware
    layer)."""
    out = []
    for p in m.get("pieces") or []:
        if p.get("kind") == "device" and not layers.get("hardware", True):
            continue
        h = node_height(p, p["id"] in offen) if p.get("kind") == "node" else p.get("h", 4)
        out.append({"id": p["id"], "art": ART, "x": p.get("x", 0), "y": p.get("y", 0),
                    "w": p.get("w", 20), "h": h, "piece": p, "offen": p["id"] in offen})
    return out


def wire_style(w):
    return {"off": "off", "planned": "planned"}.get(w.get("state"), "pcb")


def connections(m, layers, visible):
    out = []
    for w in m.get("wires") or []:
        layer = w.get("layer") or "data"
        if not layers.get(layer, True):
            continue
        if w.get("from_piece") not in visible or w.get("to_piece") not in visible:
            continue
        label = ""
        if w.get("state") == "off":
            label = _("off")
        elif w.get("state") == "planned":
            label = _("not yet")
        elif w.get("type") != "sync":
            label = str(w.get("type"))
        out.append({"id": w["id"], "von": w["from_piece"], "nach": w["to_piece"],
                    "rolle": "layer-" + layer, "stil": wire_style(w), "rolle_ende": "solder",
                    **({"label": label} if label else {})})
    return out


class Schematix:
    """State in self.S (also z.SCHEMATIX, so fenster.py sees the focus)."""

    def __init__(self, z):
        self.z = z
        self.arten = cv.Arten()
        self.arten.registrieren(Piece())
        # Background loading; tests set "run now".
        self.starten = lambda f: threading.Thread(target=f, daemon=True).start()
        self.uhr = time.monotonic
        self.S = z.SCHEMATIX = {
            "active": False, "map": None, "palette": None, "canvas": None,
            "layers": {layer: True for layer in LAYERS}, "offen": set(),
            "ebene": "board",           # board | colours
            "colour_sel": 0, "farbe": None,
            "msg": "", "geladen": 0.0, "laedt": False,
        }

    # ── Data ──────────────────────────────────────────────────────────
    def oeffnen(self):
        S = self.S
        S.update(active=True, ebene="board", farbe=None, msg="")
        self.laden()

    def laden(self):
        """The map and the palette, fresh (on open, then every REFRESH_S)."""
        S = self.S
        try:
            m = api_call("/api/schematix/map", timeout=15)
        except Exception as e:
            S["msg"] = _("the map is not reachable: {e}").format(e=getattr(e, "reason", e))
            m = S["map"]
        try:
            S["palette"] = api_call("/api/schematix/palette") or S["palette"]
        except Exception:
            pass
        S["geladen"] = self.uhr()
        if isinstance(m, dict):
            S["map"] = m
            self.board_neu()

    def pflegen(self):
        """While open: lay the map fresh now and then (in the background)."""
        S = self.S
        if not S["active"] or S["laedt"] or self.uhr() - S["geladen"] < REFRESH_S:
            return

        def los():
            try:
                self.laden()
            finally:
                S["laedt"] = False
        S["laedt"] = True
        self.starten(los)

    def board_neu(self):
        """Build the board from the map; keep focus and view."""
        S = self.S
        m = S["map"] or {}
        els = elements(m, S["layers"], S["offen"])
        vis = {e["id"] for e in els}
        cons = connections(m, S["layers"], vis)
        c = S["canvas"]
        if c is None:
            c = cv.Canvas(self.arten, els, cons)
            c.weich, c.uhr = True, self.uhr
            S["canvas"] = c
            S["zentrieren"] = True
        else:
            c.elemente[:] = els
            c.verbindungen[:] = cons
            if c.fokus not in vis:
                c.fokus = None

    def bewegt_sich(self):
        c = self.S["canvas"]
        return bool(self.S["active"] and c is not None and c.bewegt_sich())

    def fokus_piece(self):
        c = self.S["canvas"]
        el = c.element(c.fokus) if c is not None else None
        return (el or {}).get("piece")

    # ── Keys: ONE table ───────────────────────────────────────────────
    TASTEN = Tasten.zusammen({
        "board": _BOARD,
        "node": _BOARD[:1] + [("i", "versionen", "versions")] + _BOARD[1:],
        "colours": [("↑↓", "farbe_waehlen", "select"), ("enter", "farbe_aendern", "change"),
                    ("x", "farbe_zurueck", "default"), ("esc", "farben_zu", "back")],
    }, {"farbe": (Tasten(Farbwaehler.TASTEN),
                  lambda s: s.S["farbe"] if isinstance(s.S["farbe"], Farbwaehler) else Farbwaehler)})

    def ansicht(self):
        S = self.S
        if S["farbe"] is not None:
            return "farbe:" + S["farbe"].ansicht()
        if S["ebene"] == "colours":
            return "colours"
        p = self.fokus_piece()
        return "node" if p and p.get("kind") == "node" else "board"

    def taste(self, ch):
        if ch == -1:
            return None
        ansicht = self.ansicht()
        if self.S["msg"] and not ansicht.startswith("farbe:"):
            self.S["msg"] = ""
        erg = self.TASTEN.verteilen(self, ansicht, ch)
        if ansicht.startswith("farbe:"):
            self._farbe_ergebnis(erg)
        elif isinstance(erg, cv.Ergebnis) and erg.art == "zu":
            self.S["active"] = False
        return None

    # board
    def aktion_waehlen(self, taste):
        return self.S["canvas"].aktion_waehlen(taste)

    def aktion_schieben(self, taste):
        return self.S["canvas"].aktion_schieben(taste)

    def aktion_zu(self, taste):
        return self.S["canvas"].aktion_zu(taste)

    def aktion_ebene(self, taste):
        S = self.S
        layer = LAYERS[int(taste) - 1]
        S["layers"][layer] = not S["layers"][layer]
        self.board_neu()

    def aktion_versionen(self, _taste):
        p = self.fokus_piece()
        if p:
            self.S["offen"] ^= {p["id"]}
            self.board_neu()

    # colours (the knobs: Sasha tunes, we only measure)
    def aktion_farben(self, _taste):
        self.S.update(ebene="colours", colour_sel=0)

    def _rollen(self):
        return list(((self.S["palette"] or {}).get("roles") or {}).keys())

    def aktion_farbe_waehlen(self, taste):
        n = len(self._rollen()) or 1
        self.S["colour_sel"] = (self.S["colour_sel"] + (-1 if taste == "up" else 1)) % n

    def aktion_farbe_aendern(self, _taste):
        rollen = self._rollen()
        if rollen:
            role = rollen[self.S["colour_sel"] % len(rollen)]
            self.S["farbe"] = Farbwaehler(self.S["palette"]["roles"][role])

    def aktion_farbe_zurueck(self, _taste):
        self._rolle_setzen(None)

    def aktion_farben_zu(self, _taste):
        self.S["ebene"] = "board"

    def _rolle_setzen(self, value):
        S = self.S
        rollen = self._rollen()
        if not rollen:
            return
        role = rollen[S["colour_sel"] % len(rollen)]
        try:
            S["palette"] = api_call("/api/schematix/palette/" + role, "PUT", {"value": value})
        except Exception as e:
            S["msg"] = _("colour not stored: {e}").format(e=getattr(e, "reason", e))

    def _farbe_ergebnis(self, erg):
        if not erg:
            return
        if erg[0] == "fertig":
            self._rolle_setzen(erg[1])
        self.S["farbe"] = None

    # ── Drawing ───────────────────────────────────────────────────────
    def titel(self):
        return "schematix · " + _("account map")

    def draw(self, top, mx, h, w):
        self.pflegen()
        schematix_bild.zeichnen(self, top, mx, h, w)
