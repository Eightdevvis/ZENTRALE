# tui/ansichten/shop.py
#
# Das Schaufenster (Sasha, 2026-10-10): Stücke aus ZENTRALE ansehen und
# holen — heute alles kostenlos. Oben die Kategorien (←→), darunter der
# Themen-Filter (tab), links die Stücke (↑↓), rechts das Stück im Einzelnen;
# bei Icons das Pixel-Motiv selbst aus tui/pixel.py. Enter holt, Esc zurück.
# Alles kommt per HTTP (/api/shop*, core/shop.py); die Ansicht kennt nur
# Adressen `zentrale://shop/<kategorie>/<id>`. Doku: memory/hub/shop.md.
#
# Geöffnet wird sie von außen über `oeffnen()` (der Rad-Platz `shop` kommt
# mit der Werkstatt, 2026-10-10) — hier steht kein Rad-Wissen.

import curses
import json
import textwrap
import urllib.error
import urllib.parse

from .basis import api_call
from .tasten import Tasten

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel



def motiv(stueck):
    """Name des Pixel-Motivs eines Stücks (additionalProperty `pixel_motiv`)
    — nur, wenn tui/pixel.py es zeichnen kann."""
    for p in stueck.get("additionalProperty") or []:
        if isinstance(p, dict) and p.get("name") == "pixel_motiv":
            v = p.get("value")
            if v in pixel.MOTIVE or v == "elektronik":
                return v
    return None


def preis_text(stueck):
    o = stueck.get("offers")
    o = o[0] if isinstance(o, list) and o else o
    try:
        betrag = float((o or {}).get("price", "0"))
    except (TypeError, ValueError):
        return "preis unklar"
    if betrag == 0:
        return "kostenlos"
    return ("%.2f %s" % (betrag, (o or {}).get("priceCurrency", "EUR"))).replace(".", ",")


def themen_von(stuecke):
    """Alle Themen (keywords) der Stücke, sortiert, ohne Doppelte."""
    return sorted({t for s in stuecke for t in (s.get("keywords") or []) if isinstance(t, str)})


def _stuecke(liste):
    return [el["item"] for el in (liste or {}).get("itemListElement") or []
            if isinstance(el, dict) and isinstance(el.get("item"), dict)]


class Shop:
    """Das Schaufenster. Zustand in self.SHOP (auch z.SHOP, damit fenster.py
    den Fokus sieht)."""

    def __init__(self, z):
        self.z = z
        self.SHOP = z.SHOP = {
            "active": False,
            "kategorien": [],           # [{id, name, anzahl}] aus /api/shop/kategorien
            "kat": 0,
            "themen": [],               # Themen der gewählten Kategorie
            "thema": None,              # None = alle
            "stuecke": [], "sel": 0,
            "besitz": set(),            # Adressen, die geholt sind
            "geholt": None,             # eben geholt → „geholt ✓"
            "msg": "",
        }

    # ── Daten ─────────────────────────────────────────────────────────
    def oeffnen(self):
        S = self.SHOP
        S.update(active=True, msg="", geholt=None)
        try:
            S["kategorien"] = (api_call("/api/shop/kategorien") or {}).get("kategorien") or []
        except Exception as e:
            S.update(kategorien=[], stuecke=[], themen=[], msg=self._fehlertext(e))
            return
        S["kat"] = max(0, min(S["kat"], len(S["kategorien"]) - 1))
        self._besitz_laden()
        self._laden()

    def kategorie(self):
        S = self.SHOP
        return S["kategorien"][S["kat"]] if S["kategorien"] else None

    def _laden(self):
        """Stücke der Kategorie holen; die Themen kommen aus ALLEN Stücken der
        Kategorie, gefiltert wird beim Hub (?thema=)."""
        S, k = self.SHOP, self.kategorie()
        if k is None:
            S.update(stuecke=[], themen=[], sel=0)
            return
        pfad = "/api/shop?" + urllib.parse.urlencode({"kategorie": k["id"]})
        try:
            alle = _stuecke(api_call(pfad))
            S["themen"] = themen_von(alle)
            if S["thema"] not in S["themen"]:
                S["thema"] = None
            if S["thema"]:
                alle = _stuecke(api_call(pfad + "&" + urllib.parse.urlencode({"thema": S["thema"]})))
        except Exception as e:
            alle, S["msg"] = [], self._fehlertext(e)
        S["stuecke"] = alle
        S["sel"] = max(0, min(S["sel"], len(alle) - 1))

    def _besitz_laden(self):
        S = self.SHOP
        try:
            liste = _stuecke(api_call("/api/shop/besitz"))
        except Exception:
            return                      # bleibt beim alten; der Katalog geht trotzdem
        S["besitz"] = {(o.get("typeOfGood") or {}).get("@id") for o in liste} - {None}

    @staticmethod
    def _fehlertext(e):
        if isinstance(e, urllib.error.HTTPError):
            try:
                return json.loads(e.read().decode("utf-8")).get("error") or "fehler %s" % e.code
            except Exception:
                return "fehler %s" % e.code
        return "backend nicht erreichbar"

    def holen(self):
        S = self.SHOP
        if not S["stuecke"]:
            return
        s = S["stuecke"][S["sel"]]
        try:
            r = api_call("/api/shop/holen", "POST", {"adresse": s.get("@id")}) or {}
        except Exception as e:
            S["msg"] = "nicht geholt: " + self._fehlertext(e)
            return
        S["besitz"].add(r.get("adresse") or s.get("@id"))
        S["geholt"] = s.get("@id")
        S["msg"] = "geholt ✓" if r.get("neu", True) else "hast du schon ✓"

    # ── Tasten (Tastentabelle, 2026-10-11) ────────────────────────────
    # EINE Tabelle für Verteilung UND Leiste (tasten.py). Je Ansicht nur, was
    # dort geht: ↑↓/enter nur bei Stücken, tab nur, wenn es Themen gibt,
    # ←→ nur, wenn Kategorien da sind (sonst ist das Backend weg).
    _KAT = [("←→", "kategorie", "category")]
    _THEMA = [("tab", "thema", "theme"), ("shift+tab", "thema")]
    _STUECKE = [("↑↓", "waehlen", "select"), ("enter", "holen", "get")]
    _ZU = [("esc", "zu", "back")]
    TASTEN = Tasten({
        "regal": _KAT + _STUECKE[:1] + _THEMA + _STUECKE[1:] + _ZU,
        "regal:ohne_thema": _KAT + _STUECKE + _ZU,
        "leer": _KAT + _ZU,
        "leer:thema": _KAT + _THEMA + _ZU,          # nichts zu diesem Thema
        "fehler": _ZU,
    })

    def ansicht(self):
        S = self.SHOP
        if not S["kategorien"]:
            return "fehler"
        if S["stuecke"]:
            return "regal" if S["themen"] else "regal:ohne_thema"
        return "leer:thema" if S["themen"] else "leer"

    def taste(self, ch):
        self.TASTEN.verteilen(self, self.ansicht(), ch)
        return None

    def aktion_zu(self, _taste):
        self.SHOP["active"] = False

    def aktion_kategorie(self, taste):
        S = self.SHOP
        if S["kategorien"]:
            S["kat"] = (S["kat"] + (-1 if taste == "left" else 1)) % len(S["kategorien"])
            S.update(thema=None, sel=0, msg="", geholt=None)
            self._laden()

    def aktion_waehlen(self, taste):
        S = self.SHOP
        if S["stuecke"]:
            schritt = -1 if taste == "up" else 1
            S["sel"] = max(0, min(len(S["stuecke"]) - 1, S["sel"] + schritt))
            S.update(msg="", geholt=None)

    def aktion_thema(self, taste):
        """Reihe: alle → erstes Thema → … → letztes → alle (shift+tab rückwärts)."""
        S = self.SHOP
        if S["themen"]:
            reihe = [None] + S["themen"]
            i = reihe.index(S["thema"]) if S["thema"] in reihe else 0
            S["thema"] = reihe[(i + (-1 if taste == "shift+tab" else 1)) % len(reihe)]
            S.update(sel=0, msg="", geholt=None)
            self._laden()

    def aktion_holen(self, _taste):
        self.holen()

    # ── Zeichnen ──────────────────────────────────────────────────────
    def titel(self):
        return "schaufenster"

    def draw_shop(self, top, mx, h, w):
        S, C, z = self.SHOP, self.z.C, self.z
        z.draw_box(top, mx, h, w, self.titel())
        if h < 6 or w < 20:
            return
        x0, innen = mx + 2, w - 4
        self._draw_leiste(top + 1, x0, innen)
        thema = S["thema"] or "alle"
        z.addclip(top + 2, x0, "thema: ", innen, C["faint"])
        z.addclip(top + 2, x0 + 7, thema, innen - 7, C["acc"] if S["thema"] else C["dim"])
        z.addclip(top + 3, x0, "─" * innen, innen, C["faint"])
        oben, unten = top + 4, top + h - 2           # unten = Rückmeldung
        if not S["stuecke"]:
            leer = "noch leer" if not S["thema"] else "nichts zu diesem thema"
            if S["msg"]:
                leer = S["msg"]
            z.addclip(oben + max(0, (unten - oben) // 2 - 1), mx + max(2, (w - len(leer)) // 2),
                      leer, innen, C["faint"])
        else:
            lw = max(14, min(28, innen // 3))
            self._draw_liste(oben, x0, unten - oben, lw)
            dx = x0 + lw + 2
            self._draw_detail(oben, dx, unten - oben, x0 + innen - dx)
        # Die Tasten stehen in der Fußleiste (aus TASTEN); hier nur, was eben
        # passiert ist.
        if S["msg"] and S["stuecke"]:
            z.addclip(unten, x0, S["msg"], innen, C["acc"] if S["msg"].endswith("✓") else C["warn"])

    def _draw_leiste(self, y, x, breite):
        """Kategorien nebeneinander; die gewählte hell, leere blass."""
        S, C, z = self.SHOP, self.z.C, self.z
        if not S["kategorien"]:
            z.addclip(y, x, S["msg"] or "keine kategorien", breite, C["faint"])
            return
        pos = 0
        for i, k in enumerate(S["kategorien"]):
            teil = "%s %d" % (k["name"], k["anzahl"]) if k["anzahl"] else k["name"]
            if i == S["kat"]:
                attr = C["bright"] | curses.A_REVERSE
                teil = " %s " % teil
            else:
                attr = C["dim"] if k["anzahl"] else C["faint"]
            if pos + len(teil) > breite:
                z.addclip(y, x + max(0, breite - 1), "›", 1, C["faint"])
                break
            z.addclip(y, x + pos, teil, breite - pos, attr)
            pos += len(teil) + 2

    def _draw_liste(self, y0, x, hoehe, breite):
        S, C, z = self.SHOP, self.z.C, self.z
        n = len(S["stuecke"])
        start = max(0, min(S["sel"] - hoehe // 2, n - hoehe))
        for j, s in enumerate(S["stuecke"][start:start + hoehe]):
            i = start + j
            hat = s.get("@id") in S["besitz"]
            zeichen = "✓ " if hat else "  "
            text = zeichen + (s.get("name") or s.get("identifier") or "?")
            if i == S["sel"]:
                z.addclip(y0 + j, x, text.ljust(breite), breite, C["bright"] | curses.A_REVERSE)
            else:
                z.addclip(y0 + j, x, text, breite, C["acc"] if hat else C["dim"])

    def _draw_detail(self, y0, x, hoehe, breite):
        S, C, z = self.SHOP, self.z.C, self.z
        if breite < 8:
            return
        s = S["stuecke"][S["sel"]]
        y = y0
        m = motiv(s)
        if m and hoehe >= pixel.EL_H + 5 and breite >= pixel.EL_W:
            self._draw_motiv(m, y, x)
            y += pixel.EL_H + 1
        z.addclip(y, x, s.get("name") or "?", breite, C["bright"] | curses.A_BOLD)
        y += 1
        z.addclip(y, x, preis_text(s), breite, C["faint"])
        y += 2
        for zeile in textwrap.wrap(s.get("description") or "", max(8, breite)):
            if y >= y0 + hoehe - 3:
                break
            z.addclip(y, x, zeile, breite, C["ink"])
            y += 1
        y += 1
        if s.get("keywords") and y < y0 + hoehe - 2:
            z.addclip(y, x, "themen: " + " · ".join(s["keywords"]), breite, C["faint"])
            y += 1
        if isinstance(s.get("isBasedOn"), str) and y < y0 + hoehe - 2:
            z.addclip(y, x, "für " + s["isBasedOn"], breite, C["faint"])
            y += 1
        y = min(y + 1, y0 + hoehe - 1)
        if s.get("@id") in S["besitz"]:
            z.addclip(y, x, "geholt ✓", breite, C["acc"] | curses.A_BOLD)

    def _draw_motiv(self, name, y, x):
        """Das Pixel-Motiv wie im Rad (offen, ruhend). Ohne 256 Farben oder mit
        ZENTRALE_PIXEL=off nur der Name in Großbuchstaben."""
        z, C = self.z, self.z.C
        bg = C.get("pix_bg")
        if bg is None or getattr(z, "PIX_MODUS", "mix") == "off":
            z.addclip(y + pixel.EL_LABEL_ZEILE, x, "[%s]" % name.upper(), pixel.EL_W, C["dim"])
            return
        farben = "nacht" if sum(bg) < 384 else "tag"
        modus = "half" if getattr(z, "PIX_MODUS", "mix") == "half" else "mix"
        zeilen, schrift = pixel.symbol_zellen(name, 1.0, 0, farben, modus)
        for r, line in enumerate(zeilen):
            for c, zelle in enumerate(line):
                if zelle:
                    z.safe_addstr(y + r, x + c, zelle[0], z.pix_attr(zelle[1], zelle[2]))
        for c, ch, fg, hg in schrift:
            z.safe_addstr(y + pixel.EL_LABEL_ZEILE, x + c, ch, z.pix_attr(fg, hg) | curses.A_BOLD)
