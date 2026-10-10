# tui/ansichten/werkstatt.py
#
# Die Werkstatt (2026-10-10, Sasha: „so simpel wie's geht"). Ein Raum im
# Erschaffen-Rad, in dem der Schmied mit kurzen Sätzen Schritt für Schritt
# fragt und aus einer Vorlage eine eigene App baut:
#   Name → Symbol (Bild aus ~/Zentrale/Input oder ein zufälliges Motiv) →
#   Vorlage (heute nur „Desk View") → Agent (kommt später) → bauen.
# Danach steht die App im App-Rad. Außerdem: Vorlagen ansehen, die eigenen
# Apps (öffnen, umbenennen, Symbol ändern, löschen) und die Desks (öffnen,
# umbenennen, löschen) — der Desk ist seit diesem Tag keine App im Rad mehr,
# sondern ein Baustein, den man hier verwaltet.
#
# Bedienung nur mit ↑↓ Enter Esc und Tippen (Sasha: Mainstream, nichts, was
# ein Terminal abfängt). Esc geht einen Schritt zurück, am Anfang zu.
# Alles über HTTP (core/werkstatt.py, ui/routen/werkstatt.py); was im Rad
# steht, pflegt ansichten/eigene_apps.py. Doku: memory/system/werkstatt.md.

import curses
import json
import random
import urllib.error
import urllib.parse

from .basis import api_call

try:
    from tui import pixel
    from tui.bausteine.textfeld import Textfeld
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel
    from bausteine.textfeld import Textfeld

ENTER = (10, 13, curses.KEY_ENTER)
# Besitz aus dem Shop (core/shop.py, eigene Sitzung, 2026-10-10). Gibt es den
# Weg nicht (Backend alt), fehlt die Wahl einfach.
SHOP_BESITZ = "/api/shop/besitz?kategorie=icons"
TEXT_SCHRITTE = ("name", "umbenennen")

# Was der Schmied je Schritt sagt. {name} usw. aus dem Entwurf.
SAETZE = {
    "start": "Moin. Ich bin der Schmied. Was bauen wir?",
    "name": "Wie soll die neue App heißen?",
    "icon": "Welches Symbol soll sie im Rad tragen?",
    "bild": "Such dir ein Bild aus deinem Input-Ordner aus.",
    "bild_leer": "In ~/Zentrale/Input liegt kein Bild. Leg eins hinein oder nimm ein zufälliges Symbol.",
    "vorlage": "Woraus soll ich sie bauen?",
    "agent": "Einen eigenen Agenten bekommt sie später — das lerne ich noch.",
    "fertig": "Also: „{name}\", {symbol}, aus „{vorlage}\". Soll ich?",
    "gebaut": "Fertig. „{name}\" steht jetzt im App-Rad.",
    "vorlagen": "Das sind meine Vorlagen. Enter baut gleich damit.",
    "apps": "Deine Apps.",
    "apps_leer": "Du hast noch keine eigene App gebaut.",
    "app": "Was soll ich mit „{name}\" tun?",
    "umbenennen": "Wie soll „{name}\" jetzt heißen?",
    "loeschen": "Soll „{name}\" wirklich weg?",
    "loeschen_desk": "Und ihren Desk „{desk}\" auch?",
    "desks": "Deine Desks — Flächen ohne eigenes Symbol im Rad.",
    "desks_leer": "Noch kein Desk da.",
    "desk": "Desk „{name}\" — was soll ich tun?",
    "desk_loeschen": "Desk „{name}\" wirklich wegwerfen?",
}
# Esc: ein Schritt zurück. None = Werkstatt zu.
ZURUECK = {"start": None, "name": "start", "icon": "name", "bild": "icon",
           "vorlage": "icon", "agent": "vorlage", "fertig": "agent", "gebaut": "start",
           "vorlagen": "start", "apps": "start", "app": "apps", "loeschen": "app",
           "loeschen_desk": "app", "desks": "start", "desk": "desks",
           "desk_loeschen": "desk"}


def fehlertext(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            return json.loads(e.read().decode("utf-8")).get("error") or "fehler %s" % e.code
        except Exception:
            return "fehler %s" % e.code
    return "backend nicht erreichbar"


def _q(text):
    return urllib.parse.quote(str(text), safe="")


class Werkstatt:
    """Zustand in self.W (auch z.WERK, damit fenster.py den Fokus sieht)."""

    def __init__(self, z, eigene=None, desk=None, router=None):
        self.z, self.eigene, self.desk, self.router = z, eigene, desk, router
        self.zufall = random.Random()
        self.W = z.WERK = {
            "active": False, "schritt": "start", "sel": 0,
            "feld": None,                # Textfeld beim Tippen (Name)
            "neu": {},                   # Entwurf: name, slug, icon, symbol, vorlage, fuer
            "apps": [], "desks": [], "bilder": [], "vorlagen": [], "shop": [],
            "ziel": None,                # App oder Desk, um die es gerade geht
            "msg": "",
        }

    # ── Öffnen, Schritte ──────────────────────────────────────────────
    def oeffnen(self):
        self.W.update(active=True, msg="", neu={}, ziel=None)
        self._gehe("start")

    def _gehe(self, schritt):
        W = self.W
        W.update(schritt=schritt, sel=0, feld=None)
        if schritt == "start":                    # am Anfang ist alles Halbe vergessen
            W["neu"], W["ziel"] = {}, None
        elif schritt == "name":
            W["feld"] = Textfeld(W["neu"].get("name", ""))
        elif schritt == "umbenennen":
            W["feld"] = Textfeld(W["ziel"]["name"])
        elif schritt == "icon":
            W["shop"] = self._shop_symbole()
        elif schritt == "bild":
            W["bilder"] = self._holen("/api/werkstatt/bilder", "bilder")
        elif schritt in ("vorlage", "vorlagen"):
            W["vorlagen"] = self._holen("/api/werkstatt/vorlagen", "vorlagen") or [
                {"id": "desk", "titel": "Desk View", "text": ""}]
        elif schritt == "apps":
            W["apps"] = self._holen("/api/werkstatt/apps", "apps")
        elif schritt == "desks":
            W["desks"] = self._holen("/api/desk", "desks")

    def _holen(self, pfad, feld):
        try:
            d = api_call(pfad) or {}
        except Exception as e:
            self.W["msg"] = fehlertext(e)
            return []
        liste = d.get(feld) if isinstance(d, dict) else None
        return liste if isinstance(liste, list) else []

    def _shop_symbole(self):
        """Symbole, die Sasha im Shop geholt hat — wenn es den Weg gibt.
        Antwort ist schema.org-JSON-LD (core/shop.py): ItemList aus
        OwnershipInfo, das Stück in `typeOfGood`, sein Motiv als
        additionalProperty `pixel_motiv`. -> [{"name", "motiv"}]"""
        try:
            d = api_call(SHOP_BESITZ, timeout=1.0)
        except Exception:
            return []
        raus = []
        for eintrag in (d or {}).get("itemListElement") or [] if isinstance(d, dict) else []:
            gut = ((eintrag or {}).get("item") or {}).get("typeOfGood") or {}
            for e in gut.get("additionalProperty") or []:
                if isinstance(e, dict) and e.get("name") == "pixel_motiv" and e.get("value"):
                    raus.append({"name": gut.get("name") or e["value"], "motiv": str(e["value"])})
        return raus

    def satz(self):
        W = self.W
        s = W["schritt"]
        leer = {"bild": "bilder", "apps": "apps", "desks": "desks"}
        if s in leer and not W[leer[s]]:
            s += "_leer"
        n = W["neu"]
        werte = {"name": n.get("name", ""), "symbol": n.get("symbol", ""),
                 "vorlage": n.get("vorlage_titel", ""), "desk": ""}
        if W["ziel"]:
            werte.update(name=W["ziel"].get("name", ""), desk=W["ziel"].get("desk", ""))
        return SAETZE.get(s, "").format(**werte)

    def punkte(self):
        """Die Wahl im aktuellen Schritt: [(text, aktion)]."""
        W = self.W
        s = W["schritt"]
        if s == "start":
            return [("neue app bauen", "bauen"), ("vorlagen ansehen", "vorlagen"),
                    ("deine apps", "apps"), ("deine desks", "desks")]
        if s == "icon":
            return ([("ein bild aus dem input-ordner", "bilder_zeigen"),
                     ("ein zufälliges symbol", "zufall")]
                    + [("aus dem shop: " + str(e.get("name") or e.get("motiv") or "symbol"), ("shop", e))
                       for e in W["shop"]])
        if s == "bild":
            return [(b["name"], ("bild", b["name"])) for b in W["bilder"]] or [("zurück", "zurueck")]
        if s in ("vorlage", "vorlagen"):
            return [(v["titel"] + (" — " + v["text"] if v.get("text") and s == "vorlagen" else ""),
                     ("vorlage", v)) for v in W["vorlagen"]]
        if s == "agent":
            return [("weiter", "weiter")]
        if s == "fertig":
            return [("ja, bauen", "bauen_jetzt"), ("abbrechen", "start")]
        if s == "gebaut":
            return [("öffnen", "app_oeffnen"), ("zurück in die werkstatt", "start")]
        if s == "apps":
            return [(a["name"] + "  (zentrale://%s/)" % a["slug"], ("ziel", a)) for a in W["apps"]] \
                or [("eine bauen", "bauen")]
        if s == "app":
            return [("öffnen", "app_oeffnen"), ("umbenennen", "umbenennen"),
                    ("symbol ändern", "symbol"), ("wegwerfen", "loeschen")]
        if s == "loeschen":
            return [("nein, behalten", "app"), ("ja, wegwerfen", "loeschen_desk")]
        if s == "loeschen_desk":
            return [("desk behalten", ("weg", False)), ("desk auch wegwerfen", ("weg", True))]
        if s == "desks":
            return [(d["name"], ("ziel", d)) for d in W["desks"]] or [("zurück", "zurueck")]
        if s == "desk":
            return [("öffnen", "desk_oeffnen"), ("umbenennen", "umbenennen"),
                    ("wegwerfen", "desk_loeschen")]
        if s == "desk_loeschen":
            return [("nein, behalten", "desk"), ("ja, wegwerfen", "desk_weg")]
        return []

    # ── Tasten ────────────────────────────────────────────────────────
    def taste(self, ch):
        W = self.W
        if ch == -1:
            return None
        if W["feld"] is not None:
            return self._taste_text(ch)
        n = len(self.punkte())
        if ch == curses.KEY_UP and n:
            W["sel"] = (W["sel"] - 1) % n          # rundherum: ↑ tut immer etwas
        elif ch == curses.KEY_DOWN and n:
            W["sel"] = (W["sel"] + 1) % n
        elif ch in ENTER and n:
            W["msg"] = ""
            self.waehlen(self.punkte()[min(W["sel"], n - 1)][1])
        elif ch == 27:
            self.zurueck()
        return None

    def zurueck(self):
        W = self.W
        W["msg"] = ""
        s = W["schritt"]
        if s == "umbenennen":
            ziel = "app" if W["ziel"] and "slug" in W["ziel"] else "desk"
        elif s == "icon" and W["neu"].get("fuer"):
            ziel = "app"                          # Symbol einer fertigen App ändern
        else:
            ziel = ZURUECK.get(s)
        if ziel is None:
            W["active"] = False
        else:
            self._gehe(ziel)

    def _taste_text(self, ch):
        W = self.W
        if ch in ENTER:
            text = W["feld"].text.strip()
            if W["schritt"] == "name":
                self._name_fertig(text)
            else:
                self._umbenennen(text)
            return None
        if W["feld"].taste(ch) == "abbrechen":
            self.zurueck()
        return None

    def waehlen(self, aktion):
        W = self.W
        art, wert = aktion if isinstance(aktion, tuple) else (aktion, None)
        if art == "bauen":
            W["neu"] = {}
            self._gehe("name")
        elif art in ("vorlagen", "apps", "desks", "desk", "app", "loeschen_desk",
                     "umbenennen", "start"):
            self._gehe(art)
        elif art == "zurueck":
            self.zurueck()
        elif art == "bilder_zeigen":
            self._gehe("bild")
        elif art == "zufall":
            motiv = self.zufall.choice(pixel.FESTE_MOTIVE)
            self._symbol_fertig({"motiv": motiv}, "symbol „%s\"" % motiv)
        elif art == "bild":
            self._symbol_fertig({"bild": wert}, "bild „%s\"" % wert)
        elif art == "shop":
            self._symbol_fertig({"motiv": wert.get("motiv")}, "shop-symbol")
        elif art == "vorlage":
            W["neu"].update(vorlage=wert["id"], vorlage_titel=wert["titel"])
            self._gehe("agent" if W["neu"].get("name") else "name")
        elif art == "weiter":
            self._gehe("fertig")
        elif art == "bauen_jetzt":
            self._bauen()
        elif art == "ziel":
            W["ziel"] = wert
            self._gehe("app" if "slug" in wert else "desk")
        elif art == "app_oeffnen":
            self.app_oeffnen(W["ziel"])
        elif art == "desk_oeffnen" and self.desk is not None:
            self.desk.direkt(W["ziel"]["name"])
        elif art == "symbol":
            W["neu"] = {"fuer": W["ziel"]["slug"]}
            self._gehe("icon")
        elif art == "loeschen":
            self._gehe("loeschen")
        elif art == "weg":
            self._app_weg(wert)
        elif art == "desk_loeschen":
            self._gehe("desk_loeschen")
        elif art == "desk_weg":
            self._desk_weg()

    # ── Die Schritte, die etwas tun ───────────────────────────────────
    def _name_fertig(self, text):
        W = self.W
        if not text:
            W["msg"] = "der name fehlt noch"
            return
        try:
            d = api_call("/api/werkstatt/name", "POST", {"name": text}) or {}
        except Exception as e:
            W["msg"] = fehlertext(e)
            return
        W["neu"].update(name=d.get("name", text), slug=d.get("slug", ""))
        self._gehe("icon")

    def _symbol_fertig(self, icon, beschreibung):
        W = self.W
        n = W["neu"]
        if n.get("fuer"):                          # Symbol einer fertigen App ändern
            try:
                a = api_call("/api/werkstatt/apps/" + _q(n["fuer"]), "PATCH", {"icon": icon})
            except Exception as e:
                W["msg"] = fehlertext(e)
                return
            W["ziel"], W["neu"] = a, {}
            self._neu_im_rad()
            self._gehe("app")
            W["msg"] = "neues symbol sitzt"
            return
        n.update(icon=icon, symbol=beschreibung)
        self._gehe("agent" if n.get("vorlage") else "vorlage")

    def _bauen(self):
        W = self.W
        n = W["neu"]
        body = {"name": n.get("name"), "icon": n.get("icon"), "vorlage": n.get("vorlage", "desk")}
        try:
            a = api_call("/api/werkstatt/apps", "POST", body)
        except Exception as e:
            W["msg"] = "nicht gebaut: " + fehlertext(e)
            return
        W["ziel"] = a
        self._neu_im_rad()
        self._gehe("gebaut")

    def _umbenennen(self, text):
        W = self.W
        ziel = W["ziel"]
        if not text:
            W["msg"] = "der name fehlt noch"
            return
        app = "slug" in ziel
        pfad = ("/api/werkstatt/apps/" + _q(ziel["slug"])) if app else ("/api/desk/" + _q(ziel["name"]))
        try:
            neu = api_call(pfad, "PATCH", {"name": text}) or {}
        except Exception as e:
            W["msg"] = fehlertext(e)
            return
        W["ziel"] = neu if app else dict(ziel, name=neu.get("name", text))
        self._neu_im_rad()
        self._gehe("app" if app else "desk")

    def _app_weg(self, desk_mit):
        W = self.W
        ziel = W["ziel"]
        try:
            api_call("/api/werkstatt/apps/%s?desk=%d" % (_q(ziel["slug"]), 1 if desk_mit else 0), "DELETE")
        except Exception as e:
            W["msg"] = fehlertext(e)
            return
        W["ziel"] = None
        self._neu_im_rad()
        self._gehe("apps")
        W["msg"] = "„%s\" ist weg" % ziel["name"]

    def _desk_weg(self):
        W = self.W
        ziel = W["ziel"]
        try:
            api_call("/api/desk/" + _q(ziel["name"]), "DELETE")
        except Exception as e:
            W["msg"] = fehlertext(e)
            self._gehe("desk")
            return
        W["ziel"] = None
        self._gehe("desks")
        W["msg"] = "desk „%s\" ist weg" % ziel["name"]

    def _neu_im_rad(self):
        if self.eigene is not None:
            self.eigene.laden()

    def app_oeffnen(self, app):
        """Die App wie aus dem Rad öffnen (über ihre Adresse). Die Werkstatt
        bleibt darunter offen: Esc auf dem Desk führt hierher zurück."""
        if not app:
            return
        if self.router is not None and self.router.zeigen("zentrale://%s/" % app["slug"]):
            return
        if self.desk is not None and app.get("desk"):
            self.desk.direkt(app["desk"])

    # ── Zeichnen ──────────────────────────────────────────────────────
    def titel(self):
        return "werkstatt"

    def draw(self, top, mx, h, w):
        z, W = self.z, self.W
        C, addclip = z.C, z.addclip
        x0, breite = mx + 3, max(10, w - 6)
        y = top + 2
        addclip(y, x0, "⚒  der schmied", breite, C["acc"] | curses.A_BOLD)
        y += 2
        addclip(y, x0, "„" + self.satz() + "\"", breite, C["bright"])
        y += 2
        if W["feld"] is not None:
            text = W["feld"].text
            addclip(y, x0, "› " + text + "▏", breite, C["bright"])
            y += 2
        else:
            punkte = self.punkte()
            platz = max(1, top + h - 4 - y)
            erst = max(0, min(W["sel"] - platz // 2, len(punkte) - platz))
            for i, (text, _a) in enumerate(punkte[erst:erst + platz], start=erst):
                gewaehlt = i == W["sel"]
                addclip(y, x0, ("▸ " if gewaehlt else "  ") + text, breite,
                        C["bright"] | curses.A_BOLD if gewaehlt else C["dim"])
                y += 1
        if W["msg"]:
            addclip(top + h - 3, x0, W["msg"], breite, C["warn"])
        self._draw_symbol(top, mx, h, w)

    def _symbol_name(self):
        """Wessen Symbol rechts steht: die gewählte eigene App, der Entwurf."""
        W = self.W
        if W["schritt"] == "apps" and W["apps"]:
            return W["apps"][min(W["sel"], len(W["apps"]) - 1)]["slug"]
        if W["ziel"] and "slug" in W["ziel"]:
            return W["ziel"]["slug"]
        motiv = (W["neu"].get("icon") or {}).get("motiv")
        return motiv if motiv in pixel.FESTE_MOTIVE else None

    def _draw_symbol(self, top, mx, h, w):
        z = self.z
        name = self._symbol_name()
        pix_bg = z.C.get("pix_bg")
        if (not name or not pixel.hat_symbol(name) or pix_bg is None
                or z.PIX_MODUS == "off" or w < 70 or h < pixel.EL_H + 4):
            return
        farben = "nacht" if sum(pix_bg) < 384 else "tag"
        zeilen, schrift = pixel.symbol_zellen(name, 1.0, 0, farben,
                                              "half" if z.PIX_MODUS == "half" else "mix")
        y0, x0 = top + 2, mx + w - pixel.EL_W - 4
        for r, zeile in enumerate(zeilen):
            for c, zelle in enumerate(zeile):
                if zelle:
                    z.safe_addstr(y0 + r, x0 + c, zelle[0], z.pix_attr(zelle[1], zelle[2]))
        for c, ch, fg, bg in schrift:
            z.safe_addstr(y0 + pixel.EL_LABEL_ZEILE, x0 + c, ch, z.pix_attr(fg, bg) | curses.A_BOLD)
