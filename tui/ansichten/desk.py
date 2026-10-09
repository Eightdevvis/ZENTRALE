# tui/ansichten/desk.py
#
# Desk View (Taste `d` im Rad, 2026-10-09). Sasha: „ich klappe z.B.
# ‚Elektronik' auf und habe einen infinity canvas vor mir." Erst eine
# Auswahl der Desks (+ neuer Desk), dann die Fläche. Die Fläche selbst ist
# der Baustein tui/bausteine/canvas.py — er weiß nichts vom Desk. Diese
# Ansicht ist die App drumherum: Desks laden und speichern (HTTP
# /api/desk, core/desk.py), das Bearbeiten-Modal mittig zeigen, Tasten und
# Hinweise. So kann Desk View später als eigene Hub-App ausziehen, ohne den
# Canvas mitzunehmen, und andere Apps nehmen den Canvas ohne den Desk.
# Doku: memory/system/desk_view.md.

import curses
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import basis, bild_betrachter
from .basis import api_call

try:
    from tui.bausteine import canvas as cv
    from tui.bausteine import canvas_bild
    from tui.bausteine.canvas_arten import standard_arten
    from tui.bausteine.textfeld import Textfeld
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine import canvas as cv
    from bausteine import canvas_bild
    from bausteine.canvas_arten import standard_arten
    from bausteine.textfeld import Textfeld

# Rolle des Canvas → Farbrolle der TUI (ansichten/farben.py).
FARBEN = {"raster": "faint", "schnur": "dim", "schnur_vor": "acc", "rahmen": "dim",
          "fokus": "acc", "griff": "warn", "ziel": "acc", "text": "ink", "leise": "faint",
          "notiz_titel": "amberhi", "bild": "ink", "bild_titel": "bright"}
FETT = {"fokus", "griff", "ziel", "notiz_titel", "bild_titel"}

# Was die Hinweiszeile im Kasten je Zustand zeigt. Die Fußleiste ganz unten
# kommt aus befehle.CTX_KEYS — „shift+↑↓←→" kann fussleiste.codes() (noch)
# nicht lesen, darum steht das Schieben nur hier.
HINWEIS = {"ruhe": "shift+↑↓←→ move view · pgup/pgdn scroll note · o open image · f colour",
           "greifen": "shift+↑↓←→ move view (note comes along)",
           "verbinden": "↑↓←→ pick target · enter/v connect · esc cancel"}


def _pfad(name):
    return "/api/desk/" + urllib.parse.quote(name, safe="")


class Desk:
    """Desk View: Auswahl der Desks, dann die Fläche. Zustand in self.DESK
    (auch z.DESK, damit fenster.py den Fokus sieht)."""

    def __init__(self, z):
        self.z = z
        self.arten = standard_arten(cv.Arten())
        self.DESK = z.DESK = {
            "active": False,
            "ebene": "wahl",            # wahl | canvas
            "desks": [], "sel": 0,
            "name": None,               # Textfeld, solange ein neuer Name getippt wird
            "desk": None, "stand": None,
            "canvas": None,             # cv.Canvas des offenen Desks
            "modal": None, "modal_id": None,
            "zentrieren": False,
            "msg": "",
            # Wähler hinter `+` (2026-10-10): erst die Art, beim Bild dann
            # die Datei (Input/ oder Pfad tippen).
            "art_wahl": None,           # {"arten": [...], "sel": i}
            "bild_wahl": None,          # {"quellen": [...], "sel": i, "pfad": Textfeld|None}
        }

    # ── Daten ─────────────────────────────────────────────────────────
    def oeffnen(self):
        D = self.DESK
        D.update(active=True, ebene="wahl", name=None, modal=None, canvas=None, msg="",
                 art_wahl=None, bild_wahl=None)
        self._liste_laden()

    def _liste_laden(self):
        D = self.DESK
        try:
            D["desks"] = (api_call("/api/desk") or {}).get("desks") or []
        except Exception:
            D["desks"] = []
            D["msg"] = "backend nicht erreichbar"
        D["sel"] = max(0, min(D["sel"], len(D["desks"])))   # letzte Zeile: „neuer desk"

    def _fehlertext(self, e):
        if isinstance(e, urllib.error.HTTPError):
            try:
                return json.loads(e.read().decode("utf-8")).get("error") or str(e.code)
            except Exception:
                return "fehler %s" % e.code
        return "backend nicht erreichbar"

    def desk_oeffnen(self, name):
        D = self.DESK
        try:
            d = api_call(_pfad(name))
        except Exception as e:
            D["msg"] = "„%s\" geht nicht auf: %s" % (name, self._fehlertext(e))
            return
        if not isinstance(d, dict):
            D["msg"] = "„%s\" geht nicht auf" % name
            return
        # Ohne Fabrik meldet der Canvas bei + „neu_waehlen": Zettel oder Bild.
        D.update(ebene="canvas", desk=d.get("name", name), stand=d.get("stand"), msg="",
                 zentrieren=True, art_wahl=None, bild_wahl=None,
                 canvas=cv.Canvas(self.arten, list(d.get("elemente") or []),
                                  list(d.get("verbindungen") or [])))

    def _anlegen(self, name):
        D = self.DESK
        try:
            d = api_call("/api/desk", "POST", {"name": name})
        except Exception as e:
            D["msg"] = "desk nicht angelegt: " + self._fehlertext(e)
            return
        self.desk_oeffnen((d or {}).get("name") or name)

    def speichern(self):
        """Den ganzen Desk schicken. Wurde er woanders geändert (409), wird
        neu geladen und das gesagt; geht das Backend nicht, bleibt alles hier
        liegen und das nächste Speichern schickt es mit."""
        D = self.DESK
        c = D["canvas"]
        # Felder mit „_" legt nur die Ansicht zwischen (Vorschau, Blätterlage).
        elemente = [{k: v for k, v in e.items() if not k.startswith("_")} for e in c.elemente]
        body = {"elemente": elemente, "verbindungen": c.verbindungen_mit_seiten(),
                "stand": D["stand"]}
        try:
            d = api_call(_pfad(D["desk"]), "PUT", body)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                self.desk_oeffnen(D["desk"])
                D["msg"] = "desk wurde woanders geändert — neu geladen, letzte änderung fehlt"
            else:
                D["msg"] = "nicht gespeichert: " + self._fehlertext(e)
            return
        except Exception:
            D["msg"] = "nicht gespeichert — backend nicht erreichbar"
            return
        if isinstance(d, dict) and d.get("stand"):
            D["stand"] = d["stand"]
        D["msg"] = ""

    # ── Tasten ────────────────────────────────────────────────────────
    def _esc_folge(self):
        """Nach ESC kurz auf Folgebytes warten (Alt+x, rohe Shift+Pfeile)."""
        s = self.z.stdscr
        folge = []
        s.timeout(50)
        c = s.getch()
        while c != -1 and len(folge) < 8:
            folge.append(c)
            s.timeout(0)
            c = s.getch()
        s.timeout(250)
        return folge

    def taste(self, ch):
        D = self.DESK
        if ch == -1:
            return None
        folge = self._esc_folge() if ch == 27 else None
        if folge:                        # Alt+… / Escape-Folge: nie „abbrechen"
            if D["canvas"] is not None and D["ebene"] == "canvas" and D["modal"] is None \
                    and D["name"] is None and D["art_wahl"] is None and D["bild_wahl"] is None:
                self._canvas_ereignis(cv.esc_folge(folge))
            return None
        if D["modal"] is not None:
            return self._taste_modal(ch)
        if D["bild_wahl"] is not None:
            return self._taste_bild_wahl(ch)
        if D["art_wahl"] is not None:
            return self._taste_art_wahl(ch)
        if D["name"] is not None:
            return self._taste_name(ch)
        if D["ebene"] == "wahl":
            return self._taste_wahl(ch)
        self._canvas_ereignis(cv.taste_deuten(ch, cv.tastenname(ch)))
        return None

    def _taste_wahl(self, ch):
        D = self.DESK
        n = len(D["desks"])
        if ch == curses.KEY_UP:
            D["sel"] = max(0, D["sel"] - 1)
        elif ch == curses.KEY_DOWN:
            D["sel"] = min(n, D["sel"] + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            if D["sel"] < n:
                self.desk_oeffnen(D["desks"][D["sel"]]["name"])
            else:
                D["name"] = Textfeld("")
        elif ch == ord("n"):
            D["name"] = Textfeld("")
        elif ch == 27:
            D["active"] = False
        return None

    def _taste_name(self, ch):
        D = self.DESK
        if ch in (10, 13, curses.KEY_ENTER):
            name = D["name"].text.strip()
            D["name"] = None
            if name:
                self._anlegen(name)
            return None
        if D["name"].taste(ch) == "abbrechen":
            D["name"] = None
        return None

    def _canvas_ereignis(self, ev):
        D = self.DESK
        erg = D["canvas"].taste(ev)
        if erg is None:
            return
        if erg.art == "zu":
            D.update(ebene="wahl", canvas=None, desk=None, msg="")
            self._liste_laden()
        elif erg.art == "bearbeiten":
            D["modal"] = self.arten.holen(erg.element.get("art")).modal(erg.element)
            D["modal_id"] = erg.element["id"]
        elif erg.art == "geaendert":
            self.speichern()
        elif erg.art == "neu_waehlen":
            D["art_wahl"] = {"arten": self.arten.anlegbar(), "sel": 0}
        elif erg.art == "aktion":
            was = erg.grund[0] if isinstance(erg.grund, tuple) and erg.grund else None
            if was == "bild_oeffnen":
                self.bild_oeffnen(erg.grund[1])
            # Kacheln („oeffnen", ref) gehen später an POST /api/kachel/aktion
            # (hub_bauplan.md „Kacheln").

    # ── + : Art wählen, Bild wählen (2026-10-10) ──────────────────────
    def _taste_art_wahl(self, ch):
        D = self.DESK
        w = D["art_wahl"]
        if ch == curses.KEY_UP:
            w["sel"] = max(0, w["sel"] - 1)
        elif ch == curses.KEY_DOWN:
            w["sel"] = min(len(w["arten"]) - 1, w["sel"] + 1)
        elif ch in (10, 13, curses.KEY_ENTER, ord("+")):
            art = w["arten"][w["sel"]] if w["arten"] else None
            D["art_wahl"] = None
            if art is None:
                return None
            if art.name == "bild":
                self._bild_wahl_oeffnen()
            else:
                D["canvas"].neu_ablegen(art.neu(cv.neue_id(), 0, 0))
        elif ch == 27:
            D["art_wahl"] = None
        return None

    def _bild_wahl_oeffnen(self):
        D = self.DESK
        try:
            quellen = (api_call("/api/desk-bild/quellen") or {}).get("quellen") or []
        except Exception as e:
            quellen = []
            D["msg"] = "bilder nicht lesbar: " + self._fehlertext(e)
        D["bild_wahl"] = {"quellen": quellen, "sel": 0, "pfad": None}

    def _taste_bild_wahl(self, ch):
        D = self.DESK
        w = D["bild_wahl"]
        if w["pfad"] is not None:                   # Pfad wird getippt
            if ch in (10, 13, curses.KEY_ENTER):
                text = w["pfad"].text.strip()
                if text:
                    self._bild_hinlegen(text)
                else:
                    w["pfad"] = None
            elif w["pfad"].taste(ch) == "abbrechen":
                w["pfad"] = None
            return None
        n = len(w["quellen"])                       # letzte Zeile: Pfad tippen
        if ch == curses.KEY_UP:
            w["sel"] = max(0, w["sel"] - 1)
        elif ch == curses.KEY_DOWN:
            w["sel"] = min(n, w["sel"] + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            if w["sel"] < n:
                self._bild_hinlegen(w["quellen"][w["sel"]]["name"])
            else:
                w["pfad"] = Textfeld("")
        elif ch == 27:
            D["bild_wahl"] = None
        return None

    def _bild_hinlegen(self, quelle):
        """Bild in den Desk-Ordner kopieren lassen, dann als neues Element
        in die Hand (enter legt ab und speichert)."""
        D = self.DESK
        try:
            info = api_call("/api/desk-bild", "POST", {"quelle": quelle}, timeout=15) or {}
        except Exception as e:
            D["msg"] = "bild nicht übernommen: " + self._fehlertext(e)
            D["bild_wahl"] = None
            return
        D["bild_wahl"] = None
        bild = self.arten.holen("bild")
        D["canvas"].neu_ablegen(bild.neu(cv.neue_id(), 0, 0, info.get("datei", ""),
                                         int(info.get("w") or 34), int(info.get("h") or 12)))
        D["msg"] = ""

    # ── Bilder: Vorschau holen, öffnen ────────────────────────────────
    def _invert(self):
        """Auf hellem Grund (Tag) ist dicht = dunkel: Rampe umdrehen."""
        bg = self.z.C.get("pix_bg")
        return bool(bg) and sum(bg) / 3 > 128

    def vorschauen_holen(self, c):
        """Für jedes sichtbare Bild ohne passende Vorschau eine holen und am
        Element zwischenlegen (der Baustein fragt nie das Backend). Das
        Backend merkt sich fertige Vorschauen; gezeichnet wird von hier."""
        invert = self._invert()
        for e in c.elemente:
            if e.get("art") != "bild":
                continue
            if e["x"] + e["w"] <= c.vx or e["x"] >= c.vx + c.vw \
                    or e["y"] + e["h"] <= c.vy or e["y"] >= c.vy + c.vh:
                continue
            sp, ze = canvas_bild.vorschau_groesse(e)
            fuer = (e.get("datei"), sp, ze, e.get("modus") or "mono", invert)
            if e.get("_vorschau_fuer") == fuer:
                continue
            e["_vorschau_fuer"] = fuer
            try:
                e["_vorschau"] = api_call("/api/desk-bild/vorschau", "POST",
                                          {"datei": fuer[0], "w": sp, "h": ze,
                                           "modus": fuer[3], "invert": invert}, timeout=10)
            except Exception as ex:
                e["_vorschau"] = {"status": "fehler", "text": "keine vorschau: " + self._fehlertext(ex)}

    def bild_oeffnen(self, datei):
        """Im Bildbetrachter DIESES Rechners öffnen. Liegt das Bild hier nicht
        (TUI auf einem anderen Rechner als das Backend), erst holen."""
        D = self.DESK
        try:
            info = api_call("/api/desk-bild/oeffnen", "POST", {"datei": datei}) or {}
        except Exception as e:
            D["msg"] = "bild geht nicht auf: " + self._fehlertext(e)
            return
        pfad = info.get("pfad") or ""
        if not (info.get("da") and os.path.isfile(pfad)):
            if not info.get("da"):
                D["msg"] = "bild fehlt: " + str(datei)
                return
            try:
                pfad = self._bild_holen(datei)
            except Exception as e:
                D["msg"] = "bild nicht geholt: " + self._fehlertext(e)
                return
        try:
            prog = bild_betrachter.oeffnen([pfad], info.get("betrachter") or "system")
        except OSError as e:
            D["msg"] = str(e)
            return
        D["msg"] = "geöffnet mit " + prog

    @staticmethod
    def _bild_holen(datei):
        url = basis.BASE_URL + "/api/desk-bild/datei?datei=" + urllib.parse.quote(datei)
        ziel = os.path.join(bild_betrachter.zwischenordner(), os.path.basename(datei))
        with urllib.request.urlopen(url, timeout=30) as r, open(ziel, "wb") as f:
            f.write(r.read())
        return ziel

    def _taste_modal(self, ch):
        D = self.DESK
        was = D["modal"].taste(ch)
        if was == "speichern":
            el = D["canvas"].element(D["modal_id"])
            if el is not None:
                el.update(D["modal"].aenderungen())
                D["modal"] = None
                self.speichern()
            else:
                D["modal"] = None
        elif was == "abbrechen":
            D["modal"] = None
        return None

    def tasten_text(self):
        """Hinweiszeile im Kasten (Frage, Meldung oder was gerade geht)."""
        D = self.DESK
        c = D["canvas"]
        if c and c.modus == "frage":
            return c.frage["text"] + "  j yes · n no"
        if D["msg"]:
            return D["msg"]
        return HINWEIS.get(c.modus if c else "ruhe", "")

    # ── Zeichnen ──────────────────────────────────────────────────────
    def titel(self):
        D = self.DESK
        return "desk · " + D["desk"] if D["ebene"] == "canvas" and D["desk"] else "desk"

    def draw_desk(self, top, mx, h, w):
        if self.DESK["ebene"] == "wahl":
            self._draw_wahl(top, mx, h, w)
        else:
            self._draw_canvas(top, mx, h, w)

    def _draw_wahl(self, top, mx, h, w):
        D, C, z = self.DESK, self.z.C, self.z
        y = top + 2
        z.addclip(y, mx + 3, "deine desks", w - 6, C["dim"])
        y += 2
        zeilen = [d["name"] + ("" if d.get("elemente") is None else "  · %d" % d["elemente"])
                  for d in D["desks"]] + ["+ neuer desk"]
        for i, text in enumerate(zeilen):
            if y >= top + h - 3:
                break
            gewaehlt = i == D["sel"]
            z.addclip(y, mx + 3, ("› " if gewaehlt else "  ") + text, w - 6,
                      (C["acc"] | curses.A_BOLD) if gewaehlt else C["ink"])
            y += 1
        if D["name"] is not None:
            sicht, (_r, s) = D["name"].anzeige(max(1, w - 20), 1)
            text = sicht[0] if sicht else ""
            z.addclip(top + h - 3, mx + 3, "name: ", 6, C["dim"])
            z.addclip(top + h - 3, mx + 9, text, w - 12, C["bright"])
            z.addclip(top + h - 3, mx + 9 + s, (text[s:s + 1] or " "), 1, C["bright"] | curses.A_REVERSE)
            z.addclip(top + h - 2, mx + 3, "enter create · esc cancel", w - 6, C["faint"])
        elif D["msg"]:
            z.addclip(top + h - 2, mx + 3, D["msg"], w - 6, C["warn"])

    def _draw_canvas(self, top, mx, h, w):
        D, C, z = self.DESK, self.z.C, self.z
        c = D["canvas"]
        ch_, cw = max(1, h - 3), max(1, w - 2)
        c.vw, c.vh = cw, ch_
        if D["zentrieren"]:
            self._zentrieren(c)
            D["zentrieren"] = False
        self.vorschauen_holen(c)
        for j, stuecke in enumerate(c.bild(ch_, cw)):
            for x, text, rolle in stuecke:
                attr = self._farbe(rolle)
                if rolle in FETT:
                    attr |= curses.A_BOLD
                z.safe_addstr(top + 1 + j, mx + 1 + x, text, attr)
        lage = "%d,%d" % (c.vx + cw // 2, c.vy + ch_ // 2)
        hinweis = self.tasten_text()
        farbe = C["warn"] if (D["msg"] or c.modus == "frage") else C["faint"]
        z.addclip(top + h - 2, mx + 2, hinweis, max(0, w - 6 - len(lage)), farbe)
        z.addclip(top + h - 2, mx + w - 2 - len(lage), lage, len(lage), C["faint"])
        if D["modal"] is not None:
            self._draw_modal(top, mx, h, w)
        elif D["bild_wahl"] is not None:
            self._draw_bild_wahl(top, mx, h, w)
        elif D["art_wahl"] is not None:
            self._draw_art_wahl(top, mx, h, w)

    def _farbe(self, rolle):
        """Rolle → curses-Attribut. „#rrggbb" (Bild in Farbe) wird ein
        Pixel-Farbpaar auf dem Theme-Grund; ohne 256 Farben normale Schrift."""
        C = self.z.C
        if rolle and rolle[0] == "#" and len(rolle) == 7:
            if not C.get("pix_bg"):
                return C.get("ink", 0)
            rgb = (int(rolle[1:3], 16), int(rolle[3:5], 16), int(rolle[5:7], 16))
            return self.z.pix_attr(rgb, C["pix_bg"])
        return C.get(FARBEN.get(rolle, rolle), 0)

    def _kasten(self, top, mx, h, w, titel, zeilen, sel, fuss, mh=None):
        """Kleiner Wähler mittig über der Fläche."""
        C, z = self.z.C, self.z
        mw = max(24, min(56, w - 6))
        mh = mh or max(5, min(len(zeilen) + 4, h - 4))
        y0 = top + (h - mh) // 2
        x0 = mx + (w - mw) // 2
        for j in range(mh):
            z.safe_addstr(y0 + j, x0, " " * mw, C["ink"])
        z.draw_box(y0, x0, mh, mw, titel, C["acc"])
        platz = mh - 4
        oben = max(0, min(sel - platz + 1, len(zeilen) - platz)) if sel >= platz else 0
        for j, text in enumerate(zeilen[oben:oben + platz]):
            gewaehlt = oben + j == sel
            z.addclip(y0 + 1 + j, x0 + 2, ("› " if gewaehlt else "  ") + text, mw - 4,
                      (C["acc"] | curses.A_BOLD) if gewaehlt else C["ink"])
        z.addclip(y0 + mh - 2, x0 + 2, fuss, mw - 4, C["faint"])
        return y0, x0, mw, mh

    def _draw_art_wahl(self, top, mx, h, w):
        wahl = self.DESK["art_wahl"]
        self._kasten(top, mx, h, w, "neu", [a.neu_label for a in wahl["arten"]],
                     wahl["sel"], "enter take · esc cancel")

    def _draw_bild_wahl(self, top, mx, h, w):
        C, z = self.z.C, self.z
        wahl = self.DESK["bild_wahl"]
        zeilen = [q["name"] for q in wahl["quellen"]] + ["pfad tippen …"]
        leer = [] if wahl["quellen"] else ["(keine bilder in ~/Zentrale/Input)"]
        if wahl["pfad"] is None:
            self._kasten(top, mx, h, w, "bild aus Input", leer + zeilen,
                         wahl["sel"] + len(leer), "enter take · esc cancel")
            return
        y0, x0, mw, mh = self._kasten(top, mx, h, w, "bild: pfad", leer + zeilen,
                                      len(leer) + len(zeilen) - 1, "enter take · esc back")
        sicht, (_r, s) = wahl["pfad"].anzeige(max(1, mw - 12), 1)
        text = sicht[0] if sicht else ""
        z.addclip(y0 + mh - 3, x0 + 2, "pfad: ", 6, C["dim"])
        z.addclip(y0 + mh - 3, x0 + 8, text, mw - 10, C["bright"])
        z.addclip(y0 + mh - 3, x0 + 8 + s, (text[s:s + 1] or " "), 1, C["bright"] | curses.A_REVERSE)

    @staticmethod
    def _zentrieren(c):
        """Beim Öffnen: Mitte aller Elemente in die Mitte des Ausschnitts."""
        if not c.elemente:
            c.vx, c.vy = -(c.vw // 2), -(c.vh // 2)
            return
        x0 = min(e["x"] for e in c.elemente)
        y0 = min(e["y"] for e in c.elemente)
        x1 = max(e["x"] + e["w"] for e in c.elemente)
        y1 = max(e["y"] + e["h"] for e in c.elemente)
        c.vx = (x0 + x1) // 2 - c.vw // 2
        c.vy = (y0 + y1) // 2 - c.vh // 2
        if x1 - x0 > c.vw or y1 - y0 > c.vh:        # passt nicht: oben links anfangen
            c.vx, c.vy = x0 - 1, y0 - 1

    def _draw_modal(self, top, mx, h, w):
        """Das Bearbeiten-Modal mittig über der Fläche."""
        D, C, z = self.DESK, self.z.C, self.z
        m = D["modal"]
        mw = max(20, min(64, w - 6))
        mh = max(7, min(18, h - 4))
        y0 = top + (h - mh) // 2
        x0 = mx + (w - mw) // 2
        for j in range(mh):
            z.safe_addstr(y0 + j, x0, " " * mw, C["ink"])
        z.draw_box(y0, x0, mh, mw, m.titel + " bearbeiten", C["acc"])
        sicht, (cr, cs) = m.anzeige(mw - 4, mh - 4)
        for j, zeile in enumerate(sicht):
            z.addclip(y0 + 1 + j, x0 + 2, zeile, mw - 4, C["bright"])
        if 0 <= cr < len(sicht) or not sicht:
            zeile = sicht[cr] if sicht else ""
            z.addclip(y0 + 1 + cr, x0 + 2 + cs, zeile[cs:cs + 1] or " ", 1,
                      C["bright"] | curses.A_REVERSE)
        fuss = " · ".join("%s %s" % t for t in m.tasten())
        z.addclip(y0 + mh - 2, x0 + 2, fuss, mw - 4, C["faint"])
