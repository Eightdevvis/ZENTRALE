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
# the truths (this node's projection, the other nodes' descriptions, the
# documented things) with the places and planned pieces of the scheme, so
# the drawing is the wiring: nothing on the board is a copy. After every
# change the whole board goes back (PUT /api/schematix/schemes/<name>), like
# the Desk sends the whole desk.
#
# Keys (one table, tasten.py; mainstream and collision-free letters):
#   ↑↓←→ select · W A S D move the view · enter grab / drop · + add a piece
#   · d remove a planned piece · m make a planned thing real (documented)
#   · 1–5 layers on/off · i versions panel of a node · c colours · esc back

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
SCHEME = "home"

_PAN = [("W/A/S/D", "schieben", "move view"), ("alt+↑↓←→", "schieben"), ("shift+↑↓←→", "schieben")]
_SELECT = [("↑↓←→", "waehlen", "select"), _PAN[0]]
_TAIL = [("+", "neu", "add"), ("1/2/3/4/5", "ebene", "layers"), ("c", "farben", "colours"),
         ("esc", "zu", "back")] + _PAN[1:]
_GRAB = [("enter", "greifen", "grab")]
_REMOVE = [("d", "entfernen", "remove"), ("del", "entfernen")]


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


def body_of(m):
    """The whole board for PUT /api/schematix/schemes/<name>: every place,
    the planned pieces (with the address they will have), the planned wires."""
    planned = {p["id"] for p in m.get("pieces") or [] if p.get("state") == "planned"}
    pieces = []
    for p in m.get("pieces") or []:
        d = {k: int(p.get(k, 0)) for k in ("x", "y", "w", "h")}
        d["id"] = p["id"]
        if p["id"] in planned:
            d["planned"] = {k: p.get(k) for k in ("kind", "ref", "title", "node", "thing_kind",
                                                  "address", "store") if p.get(k)}
        pieces.append(d)
    ids = {p["id"] for p in m.get("pieces") or []}
    wires = [{k: w.get(k) for k in ("id", "from_piece", "to_piece", "type", "from", "to", "owner")}
             for w in m.get("wires") or [] if w.get("state") == "planned"
             and w.get("from_piece") in ids and w.get("to_piece") in ids]
    return {"stand": (m.get("scheme") or {}).get("stand"), "pieces": pieces, "wires": wires}


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
            "active": False, "map": None, "palette": None, "canvas": None, "scheme": SCHEME,
            "layers": {layer: True for layer in LAYERS}, "offen": set(),
            "ebene": "board",           # board | colours
            "colour_sel": 0, "farbe": None,
            "picker": None,             # {"pieces": [...], "sel": i} behind +
            "msg": "", "geladen": 0.0, "laedt": False,
        }

    # ── Data ──────────────────────────────────────────────────────────
    def oeffnen(self):
        S = self.S
        S.update(active=True, ebene="board", farbe=None, picker=None, msg="")
        self.laden()

    def laden(self):
        """The map with the scheme and the palette, fresh."""
        S = self.S
        try:
            m = api_call("/api/schematix/map?scheme=" + S["scheme"], timeout=15)
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
        """While open: lay the map fresh now and then (in the background) —
        not while something is in the hand."""
        S = self.S
        c = S["canvas"]
        busy = c is not None and c.modus != "ruhe"
        if not S["active"] or S["laedt"] or busy or self.uhr() - S["geladen"] < REFRESH_S:
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

    def speichern(self):
        """The whole board back into the scheme; the answer is the new map.
        Changed elsewhere (409) → reload and say so."""
        S = self.S
        m = S["map"] or {}
        c = S["canvas"]
        places = {e["id"]: e for e in c.elemente}
        pieces = []
        for p in m.get("pieces") or []:
            e = places.get(p["id"])
            if e is None and p.get("kind") == "device" and not S["layers"].get("hardware", True):
                pieces.append(p)                     # hidden by a layer, not removed
            elif e is not None:
                pieces.append(dict(p, x=e["x"], y=e["y"]))
        known = {p["id"] for p in m.get("pieces") or []}
        pieces += [dict(e["piece"], x=e["x"], y=e["y"]) for e in c.elemente if e["id"] not in known]
        m = dict(m, pieces=pieces)
        try:
            neu = api_call("/api/schematix/schemes/" + S["scheme"], "PUT", body_of(m), timeout=15)
        except Exception as e:
            if getattr(e, "code", None) == 409:
                self.laden()
                S["msg"] = _("the scheme was changed elsewhere — reloaded, the last change is lost")
            else:
                S["msg"] = _("not stored: {e}").format(e=getattr(e, "reason", e))
            return
        if isinstance(neu, dict) and neu.get("pieces") is not None:
            S["map"] = neu
            self.board_neu()

    def bewegt_sich(self):
        c = self.S["canvas"]
        return bool(self.S["active"] and c is not None and c.bewegt_sich())

    def fokus_piece(self):
        c = self.S["canvas"]
        el = c.element(c.fokus) if c is not None else None
        return (el or {}).get("piece")

    # ── Keys: ONE table ───────────────────────────────────────────────
    TASTEN = Tasten.zusammen({
        "board": _SELECT + _TAIL,
        "piece": _SELECT + _GRAB + _TAIL,
        "node": _SELECT + _GRAB + [("i", "versionen", "versions")] + _TAIL,
        "planned": _SELECT + _GRAB + _REMOVE + _TAIL,
        "thing": _SELECT + _GRAB + [("m", "dokumentieren", "make real")] + _REMOVE + _TAIL,
        "grab": [("↑↓←→", "bewegen", "move"), _PAN[0], ("enter", "ablegen", "drop"),
                 ("esc", "zurueck", "cancel")] + _PAN[1:],
        "ask": [("y", "ja", "yes"), ("j", "ja"), ("n/esc", "nein", "no")],
        "picker": [("↑↓", "wahl", "select"), ("enter", "nehmen", "take"), ("esc", "wahl_zu", "cancel")],
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
        if S["picker"] is not None:
            return "picker"
        c = S["canvas"]
        if c is not None and c.modus == "greifen":
            return "grab"
        if c is not None and c.modus == "frage":
            return "ask"
        p = self.fokus_piece()
        if not p:
            return "board"
        if p.get("state") == "planned":
            return "thing" if p.get("kind") == "device" else "planned"
        return "node" if p.get("kind") == "node" else "piece"

    def taste(self, ch):
        if ch == -1:
            return None
        ansicht = self.ansicht()
        if self.S["msg"] and not ansicht.startswith("farbe:"):
            self.S["msg"] = ""
        erg = self.TASTEN.verteilen(self, ansicht, ch)
        if ansicht.startswith("farbe:"):
            self._farbe_ergebnis(erg)
        elif isinstance(erg, cv.Ergebnis):
            self._ergebnis(erg)
        return None

    def _ergebnis(self, erg):
        if erg.art == "zu":
            self.S["active"] = False
        elif erg.art == "geaendert":
            self.speichern()

    # board (the canvas does the moving)
    def aktion_waehlen(self, taste):
        return self.S["canvas"].aktion_waehlen(taste)

    aktion_bewegen = aktion_waehlen

    def aktion_schieben(self, taste):
        return self.S["canvas"].aktion_schieben(taste)

    def aktion_greifen(self, taste):
        return self.S["canvas"].aktion_greifen(taste)

    aktion_ablegen = aktion_greifen

    def aktion_zu(self, taste):
        return self.S["canvas"].aktion_zu(taste)

    aktion_zurueck = aktion_zu

    def aktion_ja(self, taste):
        return self.S["canvas"].aktion_ja(taste)

    def aktion_nein(self, taste):
        return self.S["canvas"].aktion_nein(taste)

    def aktion_entfernen(self, taste):
        """Only planned pieces leave the scheme by hand — live ones leave it
        when they leave reality."""
        return self.S["canvas"].aktion_loeschen(taste)

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

    def aktion_dokumentieren(self, _taste):
        """A planned thing becomes real: its file in the things store, same
        reference (zentrale://schematix/things/<id>/) — the piece stays."""
        S = self.S
        p = self.fokus_piece()
        tid = str(p["ref"]).rstrip("/").rsplit("/", 1)[-1]
        body = {"kind": p.get("thing_kind") or p.get("role"), "title": p.get("title")}
        if p.get("address"):
            body["address"] = p["address"]
        try:
            api_call("/api/schematix/things/" + tid, "PUT", body)
        except Exception as e:
            S["msg"] = _("not documented: {e}").format(e=getattr(e, "reason", e))
            return
        self.laden()
        S["msg"] = _("{title} is real now (documented)").format(title=p.get("title"))

    # + : the picker (GET /api/pieces, fresh every time)
    def aktion_neu(self, _taste):
        S = self.S
        try:
            pieces = (api_call("/api/pieces") or {}).get("pieces") or []
        except Exception as e:
            S["msg"] = _("pieces not readable: {e}").format(e=getattr(e, "reason", e))
            return
        S["picker"] = {"pieces": pieces, "sel": 0}

    def aktion_wahl(self, taste):
        w = self.S["picker"]
        n = len(w["pieces"]) or 1
        w["sel"] = (w["sel"] + (-1 if taste == "up" else 1)) % n

    def aktion_wahl_zu(self, _taste):
        self.S["picker"] = None

    def aktion_nehmen(self, _taste):
        S = self.S
        w, S["picker"] = S["picker"], None
        if not w["pieces"]:
            return
        e = w["pieces"][w["sel"] % len(w["pieces"])]
        p = self._neues_stueck(e)
        if p is None:
            return
        el = {"id": p["id"], "art": ART, "x": 0, "y": 0, "w": p["w"], "h": p["h"], "piece": p,
              "offen": False}
        S["canvas"].neu_ablegen(el)               # in the hand: enter drops (stored), esc takes it back

    def _neues_stueck(self, e):
        """A picker entry → a new planned piece, or None (it is already there:
        the focus jumps to it)."""
        S = self.S
        have = {p["id"] for p in S["map"]["pieces"]}
        node = (self.fokus_piece() or {}).get("node") or S["map"].get("node")
        if e.get("group") == "device":
            n = 1
            while "device:%s-%d" % (e["thing_kind"], n) in have:
                n += 1
            tid = "%s-%d" % (e["thing_kind"], n)
            return {"id": "device:" + tid, "ref": "zentrale://schematix/things/%s/" % tid, "kind": "device",
                    "thing_kind": e["thing_kind"], "role": e.get("role"), "title": e.get("title"),
                    "state": "planned", "band": "things", "needs": e.get("needs") or [],
                    "offers": e.get("offers") or [], "w": 24, "h": 4}
        pid = e["id"] if e.get("kind") == "node" else "%s@%s" % (e["id"], node)
        if pid in have or e["id"] in have:
            S["canvas"].fokus = pid if pid in have else e["id"]
            S["msg"] = _("{title} is already on the scheme").format(title=e.get("title"))
            return None
        if e.get("kind") == "node":
            name = e["id"].split(":", 1)[1]
            return {"id": pid, "ref": e["ref"], "kind": "node", "title": e.get("title"), "state": "planned",
                    "band": "nodes", "node": name, "needs": [], "offers": [], "w": 42, "h": 5}
        return {"id": pid, "ref": e["ref"], "kind": "app", "title": e.get("title"), "state": "planned",
                "band": "software", "node": node, "name": e["id"].split(":", 1)[1],
                "store": e.get("store"), "needs": e.get("needs") or [], "offers": e.get("offers") or [],
                "w": 24, "h": 4}

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
        return "schematix · " + _("scheme") + " " + self.S["scheme"]

    def status_text(self):
        """The question while asking, otherwise the last message."""
        c = self.S["canvas"]
        if c is not None and c.modus == "frage":
            p = self.fokus_piece() or {}
            return _("remove {title} from the scheme? y / n").format(title=p.get("title") or p.get("id"))
        return self.S["msg"]

    def draw(self, top, mx, h, w):
        self.pflegen()
        schematix_bild.zeichnen(self, top, mx, h, w)
