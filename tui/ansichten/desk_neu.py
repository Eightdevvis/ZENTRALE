# tui/ansichten/desk_neu.py
#
# Was `+` auf dem Desk außer den Arten des Bausteins anbietet: alles, was
# der Katalog des Hubs als Kachel kennt (`GET /api/kacheln`, 2026-10-10,
# memory/system/hub_bauplan.md „Katalog"). Der Wähler hinter `+` = die
# eigenen Arten des Canvas mit `neu_label` (Zettel, Bild) + je Katalog-
# Eintrag eine KatalogWahl. Eine neue App erscheint so von selbst, ohne
# dass hier etwas über sie steht.
#
# Eine KatalogWahl ist keine eigene Element-Art: sie legt Elemente der
# allgemeinen Art „kachel" an (canvas_arten.Kachel), deren Verweis die
# Adresse des Objekts ist (zentrale://<app>/<art>?<felder>). Den Dialog
# baut tui/bausteine/feld_dialog.py aus den `felder` des Eintrags; die
# Startgröße kommt vom Hub (`bevorzugt`, für genau diese Werte — siehe
# desk.py), sonst aus dem Katalog. Vorher (bis 2026-10-10) stand hier ein
# eigener Kalender-Dialog mit Kalender-Regeln.

from urllib.parse import quote, urlencode, urlunsplit

try:
    from tui.bausteine.feld_dialog import FeldDialog
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine.feld_dialog import FeldDialog

SCHEMA = "zentrale"


def wert_text(wert):
    """Wie core/adressen.wert_text: Wahr/Falsch als true/false, sonst str."""
    if isinstance(wert, bool):
        return "true" if wert else "false"
    return str(wert)


def adresse(app, art, werte):
    """Kanonische Adresse (Namen sortiert) — dieselbe Schreibweise wie der
    Hub (core/adressen.bauen), gebaut nur mit urllib.parse."""
    abfrage = urlencode(sorted((k, wert_text(v)) for k, v in (werte or {}).items()
                               if v is not None))
    return urlunsplit((SCHEMA, app, "/" + quote(str(art), safe=""), abfrage, ""))


class KatalogWahl:
    """Ein Eintrag des Katalogs im Wähler hinter `+`."""

    def __init__(self, eintrag):
        self.eintrag = eintrag
        self.app, self.art = str(eintrag.get("app")), str(eintrag.get("art"))
        self.name = "kachel:%s/%s" % (self.app, self.art)     # kein Element heißt so
        self.neu_label = str(eintrag.get("titel") or self.art)

    def neu_dialog(self):
        return FeldDialog(self.eintrag.get("felder") or [], titel=self.neu_label,
                          kopf="%s auf den desk" % self.neu_label)

    def adresse(self, werte):
        return adresse(self.app, self.art, werte)

    def groesse(self, innen=None):
        """Außenmaß (mit Rahmen) aus einem Innenmaß {w, h}; ohne: bevorzugt
        aus dem Katalog, nie kleiner als min."""
        b = innen or self.eintrag.get("bevorzugt") or self.eintrag.get("min") or {}
        m = self.eintrag.get("min") or {}
        w = max(int(b.get("w") or 1), int(m.get("w") or 1))
        h = max(int(b.get("h") or 1), int(m.get("h") or 1))
        return w + 2, h + 2

    def neu(self, eid, x, y, werte=None, innen=None):
        w, h = self.groesse(innen)
        return {"id": eid, "art": "kachel", "x": x, "y": y, "w": w, "h": h,
                "kachel": {"v": 2, "adresse": self.adresse((werte or {}).get("werte") or {})},
                "typ": "kachel · %s/%s" % (self.app, self.art), "titel": ""}

    def zeichne(self, element, w, h):        # nie gebraucht: kein Element heißt so
        return []

    def modal(self, element):
        return None


def wahlen(katalog):
    """Katalog (Antwort von GET /api/kacheln) → KatalogWahl je Eintrag."""
    return [KatalogWahl(e) for e in katalog or []
            if isinstance(e, dict) and e.get("app") and e.get("art")]
