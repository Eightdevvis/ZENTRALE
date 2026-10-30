# tui/ansichten/shop.py
#
# Das Schaufenster (Sasha, 2026-10-10): Stücke aus ZENTRALE ansehen und
# holen — heute alles kostenlos. Oben die Kategorien (←→), darunter der
# Themen-Filter (tab), links die Stücke (↑↓), rechts das Stück im Einzelnen;
# bei Icons das Pixel-Motiv selbst aus tui/pixel.py. Enter holt, Esc zurück.
# Alles kommt per HTTP (/api/shop*, core/shop.py); die Ansicht kennt nur
# Adressen `zentrale://shop/<kategorie>/<id>`. Doku: memory/hub/shop.md.
#
# Apps (2026-10-25, memory/hub/shop.md „Apps installieren"): Enter auf einer
# App lädt sie (POST /api/apps/laden, im Hintergrund), dann zeigt die Ansicht
# ihre Ansichten zur Wahl (Leertaste an/aus, mindestens eine); Enter richtet
# ein (POST /api/apps/installieren) und meldet es dem App-Rad
# (`nach_installieren`, run_ui hängt eigene_apps.laden ein).
#
# Built-in apps (building kit step 10): Cloud and Cloud folder are in the
# catalog with `built_in` — Enter switches them on at once (no download, no
# views), x switches them off on this node (POST /api/apps/remove; ownership
# and data stay). "installed ✓" comes from GET /api/apps/installed.
#
# Geöffnet wird sie von außen über `oeffnen()` (der Rad-Platz `shop` kommt
# mit der Werkstatt, 2026-10-10) — hier steht kein Rad-Wissen.

import curses
import json
import textwrap
import threading
import urllib.error
import urllib.parse

from .basis import api_call
from .tasten import Tasten
from .translate import _

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


def built_in(stueck):
    """additionalProperty `built_in` true: inside the core package (step 10)."""
    return any(isinstance(p, dict) and p.get("name") == "built_in" and p.get("value") is True
               for p in stueck.get("additionalProperty") or [])


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
            "installed": set(),         # addresses installed on this node (apps)
            "geholt": None,             # eben geholt → „geholt ✓"
            "msg": "",
            "laedt": False,             # eine App wird gerade heruntergeladen
            "wahl": None,               # Ansichten-Wahl vor dem Installieren
        }
        # Nach dem Installieren (run_ui: das App-Rad neu holen).
        self.nach_installieren = None
        # Wie im Hintergrund geladen wird; Tests setzen „gleich ausführen".
        self.starten = lambda f: threading.Thread(target=f, daemon=True).start()

    # ── Daten ─────────────────────────────────────────────────────────
    def oeffnen(self):
        S = self.SHOP
        S.update(active=True, msg="", geholt=None, wahl=None)
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

    def _installed_laden(self):
        try:
            r = api_call("/api/apps/installed") or {}
        except Exception:
            return                      # stays as it was; the catalog works anyway
        self.SHOP["installed"] = set(r.get("adressen") or [])

    def _besitz_laden(self):
        S = self.SHOP
        self._installed_laden()
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

    def ist_app(self):
        k = self.kategorie()
        return bool(k and k["id"] == "apps")

    def app_laden(self):
        """Enter auf einer App: herunterladen (Hintergrund), dann die Wahl."""
        S = self.SHOP
        if not S["stuecke"] or S["laedt"]:
            return
        s = S["stuecke"][S["sel"]]
        if built_in(s):
            self.builtin_installieren(s)
            return
        S.update(laedt=True, geholt=None, msg="lade „%s\" …" % (s.get("name") or "app"))

        def laden():
            try:
                r = api_call("/api/apps/laden", "POST", {"adresse": s.get("@id")}, timeout=320) or {}
            except Exception as e:
                S.update(laedt=False, msg="nicht geladen: " + self._fehlertext(e))
                return
            angebot = [a for a in r.get("ansichten") or [] if isinstance(a, dict) and a.get("id")]
            S.update(laedt=False, msg="", wahl={
                "adresse": s.get("@id"), "titel": r.get("titel") or s.get("name") or "app",
                "ansichten": angebot, "sel": 0,
                "an": [a["id"] for a in angebot if a["id"] in (r.get("gewaehlt") or [])],
                "installiert": bool(r.get("installiert"))})
        self.starten(laden)

    def installieren(self):
        S, w = self.SHOP, self.SHOP["wahl"]
        if not w:
            return
        if not w["an"]:
            S["msg"] = "mindestens eine ansicht wählen"
            return
        try:
            r = api_call("/api/apps/installieren", "POST",
                         {"adresse": w["adresse"], "ansichten": w["an"]}, timeout=60) or {}
        except Exception as e:
            S["msg"] = "nicht installiert: " + self._fehlertext(e)
            return
        S["besitz"].add(w["adresse"])
        S.update(wahl=None, geholt=w["adresse"],
                 msg="installiert ✓ — steht im app-rad" if r.get("neu", True)
                 else "ansichten geändert ✓")
        if self.nach_installieren:
            self.nach_installieren()

    def builtin_installieren(self, s):
        """A built-in app: on at once (POST /api/apps/installieren, no views)."""
        S = self.SHOP
        try:
            r = api_call("/api/apps/installieren", "POST", {"adresse": s.get("@id")}, timeout=60) or {}
        except Exception as e:
            S["msg"] = _("not installed: ") + self._fehlertext(e)
            return
        S["besitz"].add(s.get("@id"))
        S["installed"].add(s.get("@id"))
        S.update(geholt=s.get("@id"),
                 msg=_("installed ✓") if r.get("neu", True) else _("already installed ✓"))
        if self.nach_installieren:
            self.nach_installieren()

    def entfernen(self):
        """x on an installed built-in app: off on this node, nothing deleted."""
        S = self.SHOP
        if not S["stuecke"]:
            return
        s = S["stuecke"][S["sel"]]
        if not built_in(s):
            S["msg"] = _("removing downloaded apps is not built yet")
            return
        try:
            api_call("/api/apps/remove", "POST", {"adresse": s.get("@id")}, timeout=60)
        except Exception as e:
            S["msg"] = _("not removed: ") + self._fehlertext(e)
            return
        S["installed"].discard(s.get("@id"))
        S.update(geholt=None, msg=_("removed from this device ✓ — nothing was deleted"))
        if self.nach_installieren:
            self.nach_installieren()

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
    _APP = [("↑↓", "waehlen", "select"), ("enter", "holen", "install"), ("x", "entfernen", "remove")]
    _ZU = [("esc", "zu", "back")]
    _WAHL = [("↑↓", "wahl_waehlen", "select"), ("space", "wahl_umschalten", "toggle"),
             ("enter", "installieren", "install"), ("esc", "wahl_zu", "cancel")]
    TASTEN = Tasten({
        "regal": _KAT + _STUECKE[:1] + _THEMA + _STUECKE[1:] + _ZU,
        "regal:ohne_thema": _KAT + _STUECKE + _ZU,
        "apps": _KAT + _APP[:1] + _THEMA + _APP[1:] + _ZU,
        "apps:ohne_thema": _KAT + _APP + _ZU,
        "laedt": _ZU,                               # eine App kommt gerade
        "wahl": _WAHL,                              # Ansichten vor dem Installieren
        "leer": _KAT + _ZU,
        "leer:thema": _KAT + _THEMA + _ZU,          # nichts zu diesem Thema
        "fehler": _ZU,
    })

    def ansicht(self):
        S = self.SHOP
        if not S["kategorien"]:
            return "fehler"
        if S["wahl"]:
            return "wahl"
        if S["laedt"]:
            return "laedt"
        if S["stuecke"]:
            art = "apps" if self.ist_app() else "regal"
            return art if S["themen"] else art + ":ohne_thema"
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
        if self.ist_app():
            self.app_laden()
        else:
            self.holen()

    def aktion_entfernen(self, _taste):
        self.entfernen()

    def aktion_wahl_waehlen(self, taste):
        w = self.SHOP["wahl"]
        if w and w["ansichten"]:
            w["sel"] = (w["sel"] + (-1 if taste == "up" else 1)) % len(w["ansichten"])

    def aktion_wahl_umschalten(self, _taste):
        w = self.SHOP["wahl"]
        if w and w["ansichten"]:
            a = w["ansichten"][w["sel"]]["id"]
            if a in w["an"]:
                w["an"].remove(a)
            else:
                w["an"] = [x["id"] for x in w["ansichten"] if x["id"] in w["an"] or x["id"] == a]
            self.SHOP["msg"] = ""

    def aktion_installieren(self, _taste):
        self.installieren()

    def aktion_wahl_zu(self, _taste):
        self.SHOP.update(wahl=None, msg="")

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
        if S["wahl"]:
            self._draw_wahl(oben, x0, unten - oben, innen)
            if S["msg"]:
                z.addclip(unten, x0, S["msg"], innen, C["warn"])
            return
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

    def _draw_wahl(self, y0, x, hoehe, breite):
        """Vor dem Installieren: welche Ansichten der App eingerichtet werden."""
        w, C, z = self.SHOP["wahl"], self.z.C, self.z
        frage = ("„%s\" — welche ansichten willst du?" if not w["installiert"]
                 else "„%s\" — welche ansichten sollen eingerichtet sein?") % w["titel"]
        z.addclip(y0, x, frage, breite, C["bright"] | curses.A_BOLD)
        for i, a in enumerate(w["ansichten"][:max(0, hoehe - 3)]):
            zeile = "[%s] %s" % ("x" if a["id"] in w["an"] else " ", a.get("titel") or a["id"])
            if i == w["sel"]:
                z.addclip(y0 + 2 + i, x, zeile.ljust(min(breite, 30)), breite,
                          C["bright"] | curses.A_REVERSE)
            else:
                z.addclip(y0 + 2 + i, x, zeile, breite, C["acc"] if a["id"] in w["an"] else C["dim"])

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
        if self.ist_app() and s.get("@id") in S["installed"]:
            z.addclip(y, x, _("installed ✓"), breite, C["acc"] | curses.A_BOLD)
        elif s.get("@id") in S["besitz"]:
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
