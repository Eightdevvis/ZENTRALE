# core/shop.py
#
# Das Schaufenster (Sasha, 2026-10-10): ein kleiner Laden in ZENTRALE. Heute
# ist alles kostenlos und wird nur „geholt"; bezahlen kommt später über
# Sashas eigenen Server. Doku: memory/hub/shop.md.
#
# ── Katalog: schema.org als JSON-LD, kein eigenes Format ──────────────
# Eine `ItemList`, jedes Stück ein `ListItem` mit `item` vom passenden Typ
# (ImageObject, CreativeWork, SoftwareApplication, Product), mit `offers`
# (`Offer`, `price` "0", `priceCurrency` "EUR"), `category` (eine der
# KATEGORIEN unten), `keywords` (die Themen), `name`, `description`,
# `identifier`. `@id` ist die Adresse des Stücks:
#     zentrale://shop/<kategorie>/<identifier>     (core/adressen.py)
# Der Katalog ist Produkt-Inhalt, keine Nutzerdaten — er liegt im Repo
# (core/shop_katalog.jsonld). Nur echte Dinge aus ZENTRALE, nichts Erfundenes;
# eine Kategorie ohne Stücke zeigt „noch leer".
#
# ── Tauschstelle: woher der Katalog kommt ─────────────────────────────
# `_katalog_roh()` ist die EINE Stelle. Heute liest sie die Datei (Einstellung
# `shop_katalog`, Env ZENTRALE_SHOP_KATALOG, Standard die Datei im Repo).
# Später holt sie dieselbe ItemList von Sashas Server (über net.py) und
# fällt auf die Datei zurück — alles darüber bleibt, wie es ist.
#
# ── Holen: Besitz als JSON-LD, eine Datei pro Rechner ─────────────────
# `<shop_ordner>/besitz-<rechner>.jsonld` (Standard data/shop/, abgeglichen:
# core/abgleich_auswahl.py data/shop/**). Wieder eine `ItemList`, jedes
# Stück ein `OwnershipInfo` mit `ownedFrom` (Zeitpunkt) und `typeOfGood`
# {"@id": adresse} — nur der Verweis, nie eine Kopie des Stücks (Leitlinie
# „dasselbe Objekt, nicht kopiert"). Eine Datei pro Rechner, weil der
# Abgleich „neueste Datei gewinnt" sonst ein Holen auf dem anderen Rechner
# verlöre (2026-10-10); gelesen wird die Vereinigung aller Dateien, das
# früheste `ownedFrom` gilt. Holen ist idempotent: schon Besessenes bleibt
# mit seinem ersten Datum.
#
# Später (Bezahlen): ein Stück mit `price` > 0 lehnt `holen` heute mit 402
# ab; dann prüft hier der Server die Zahlung, bevor der Besitz entsteht.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import threading
from datetime import datetime

import adressen
import ai_config
import app_register
import datasync
import dateien

APP = "shop"
# (id, Anzeigename, schema.org-Typ der Stücke) — Reihenfolge = Reihenfolge der
# Leiste in der Oberfläche (Sasha, 2026-10-10).
KATEGORIEN = (
    ("icons", "Icons", "ImageObject"),
    ("hintergruende", "Hintergründe", "CreativeWork"),
    ("apps", "Apps", "SoftwareApplication"),
    ("bauteile", "Bauteile", "SoftwareApplication"),
    ("agenten", "Agenten", "SoftwareApplication"),
    ("avatare", "Avatare", "ImageObject"),
)
KATEGORIE_IDS = tuple(k[0] for k in KATEGORIEN)
TYPEN = {"ImageObject", "CreativeWork", "SoftwareApplication", "Product"}
KONTEXT = "https://schema.org"
STANDARD_KATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shop_katalog.jsonld")

_LOCK = threading.Lock()
_PUFFER = {"schluessel": None, "katalog": None}


class ShopFehler(ValueError):
    """Eingabe taugt nicht oder Stück fehlt. `code` = HTTP-Status der Route."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


# ── Orte ──────────────────────────────────────────────────────────────

def ordner():
    """Wo der Besitz liegt. Einstellung `shop_ordner` (Env ZENTRALE_SHOP_ORDNER;
    Tests), Standard data/shop/ in ZENTRALE."""
    eigen = ai_config.setting("shop_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "shop"))


def besitz_datei():
    """Die Besitz-Datei DIESES Rechners."""
    return os.path.join(ordner(), "besitz-%s.jsonld" % dateien.knoten())


def adresse(kategorie, kennung):
    return adressen.bauen(APP, [kategorie, kennung])


# ── Katalog ───────────────────────────────────────────────────────────

def _katalog_roh():
    """Die Tauschstelle (siehe Kopf): heute die Datei, später Sashas Server."""
    pfad = str(ai_config.setting("shop_katalog") or STANDARD_KATALOG)
    try:
        stand = os.stat(pfad).st_mtime_ns
    except OSError:
        raise ShopFehler("katalog fehlt", 503)
    if _PUFFER["schluessel"] == (pfad, stand):
        return _PUFFER["katalog"]
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, ValueError):
        raise ShopFehler("katalog ist kein gültiges JSON", 503)
    stuecke = pruefen(daten)
    _PUFFER.update(schluessel=(pfad, stand), katalog=stuecke)
    return stuecke


def pruefen(daten):
    """ItemList → Liste der Stücke (die `item`s), geprüft. Ein kaputtes Stück
    macht den ganzen Katalog ungültig — lieber laut als ein halber Laden."""
    if not isinstance(daten, dict) or daten.get("@type") != "ItemList" \
            or not isinstance(daten.get("itemListElement"), list):
        raise ShopFehler("katalog hat nicht die form einer schema.org ItemList", 503)
    stuecke, gesehen = [], set()
    for el in daten["itemListElement"]:
        it = el.get("item") if isinstance(el, dict) else None
        if not isinstance(it, dict):
            raise ShopFehler("katalog: eintrag ohne item", 503)
        kat, kennung = it.get("category"), it.get("identifier")
        if kat not in KATEGORIE_IDS or not isinstance(kennung, str) or not kennung:
            raise ShopFehler("katalog: kategorie oder identifier fehlt bei %r" % it.get("name"), 503)
        if it.get("@type") not in TYPEN:
            raise ShopFehler("katalog: typ %r unbekannt" % it.get("@type"), 503)
        if it.get("@id") != adresse(kat, kennung):
            raise ShopFehler("katalog: @id passt nicht zu %s/%s" % (kat, kennung), 503)
        fehlt = app_register.quelle_fehler(it) if kat == "apps" else None
        if fehlt:                              # holbar = installierbar (2026-10-25)
            raise ShopFehler("katalog: %s bei %s" % (fehlt, it["@id"]), 503)
        if it["@id"] in gesehen:
            raise ShopFehler("katalog: %s doppelt" % it["@id"], 503)
        gesehen.add(it["@id"])
        stuecke.append(it)
    return stuecke


def _liste(stuecke, name, **mehr):
    """Stücke → schema.org ItemList (Positionen neu gezählt)."""
    d = {"@context": KONTEXT, "@type": "ItemList", "name": name,
         "numberOfItems": len(stuecke),
         "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": s}
                             for i, s in enumerate(stuecke)]}
    d.update(mehr)
    return d


def _kategorie_pruefen(kategorie):
    if kategorie is not None and kategorie not in KATEGORIE_IDS:
        raise ShopFehler("kategorie gibt es nicht: %s" % kategorie, 400)


def katalog(kategorie=None, thema=None):
    """Der Katalog als ItemList, auf Wunsch nur eine Kategorie / ein Thema."""
    _kategorie_pruefen(kategorie)
    stuecke = [s for s in _katalog_roh()
               if (kategorie is None or s["category"] == kategorie)
               and (not thema or thema in (s.get("keywords") or []))]
    return _liste(stuecke, "ZENTRALE Schaufenster", **{"@id": adresse_katalog()})


def adresse_katalog():
    return adressen.bauen(APP, ["katalog"])


def stueck(kategorie, kennung):
    """Ein Stück aus dem Katalog; sonst ShopFehler 404."""
    _kategorie_pruefen(kategorie)
    for s in _katalog_roh():
        if s["category"] == kategorie and s["identifier"] == kennung:
            return s
    raise ShopFehler("gibt es nicht im schaufenster", 404)


def uebersicht():
    """Kategorien (mit Anzahl, auch leere) und Themen (mit Anzahl) — für die
    Leiste der Oberfläche."""
    stuecke = _katalog_roh()
    kats = [{"id": k, "name": n, "anzahl": sum(1 for s in stuecke if s["category"] == k)}
            for k, n, _t in KATEGORIEN]
    zaehler = {}
    for s in stuecke:
        for t in s.get("keywords") or []:
            zaehler[t] = zaehler.get(t, 0) + 1
    themen = [{"thema": t, "anzahl": n} for t, n in sorted(zaehler.items())]
    return {"kategorien": kats, "themen": themen}


# ── Besitz ────────────────────────────────────────────────────────────

def _aus_adresse(text):
    """Adresse eines Stücks → (kategorie, kennung); sonst ShopFehler 400."""
    try:
        a = adressen.lesen(text)
    except adressen.AdresseFehler as e:
        raise ShopFehler(str(e), 400)
    if a.app != APP or len(a.pfad) != 2 or a.abfrage:
        raise ShopFehler("keine adresse eines stücks im schaufenster", 400)
    return a.pfad


def _datei_lesen(pfad):
    """Eine Besitz-Datei → {adresse: ownedFrom}. Kaputtes zählt nicht mit
    (es bleibt liegen; geschrieben wird nur die eigene Datei)."""
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return {}
    raus = {}
    for el in (daten.get("itemListElement") if isinstance(daten, dict) else None) or []:
        it = el.get("item") if isinstance(el, dict) else None
        if not isinstance(it, dict):
            continue
        ziel = (it.get("typeOfGood") or {}).get("@id") if isinstance(it.get("typeOfGood"), dict) else None
        am = it.get("ownedFrom")
        if isinstance(ziel, str) and isinstance(am, str):
            raus[ziel] = min(am, raus.get(ziel, am))
    return raus


def _alle_besitze():
    """Vereinigung aller Rechner: {adresse: frühestes ownedFrom}."""
    raus = {}
    try:
        namen = sorted(os.listdir(ordner()))
    except OSError:
        return raus
    for n in namen:
        if n.startswith("besitz-") and n.endswith(".jsonld"):
            for ziel, am in _datei_lesen(os.path.join(ordner(), n)).items():
                raus[ziel] = min(am, raus.get(ziel, am))
    return raus


def _datei_schreiben(eigene):
    elemente = [{"@type": "ListItem", "position": i + 1,
                 "item": {"@type": "OwnershipInfo", "ownedFrom": am,
                          "typeOfGood": {"@id": ziel}}}
                for i, (ziel, am) in enumerate(sorted(eigene.items(), key=lambda x: (x[1], x[0])))]
    pfad = besitz_datei()
    dateien.json_schreiben(pfad, {"@context": KONTEXT, "@type": "ItemList",
                                  "name": "Geholt auf %s" % dateien.knoten(),
                                  "itemListElement": elemente})
    datasync.notify_change(pfad)


def _preis_null(s):
    o = s.get("offers")
    for angebot in (o if isinstance(o, list) else [o]):
        if isinstance(angebot, dict):
            try:
                if float(angebot.get("price", "0")) != 0:
                    return False
            except (TypeError, ValueError):
                return False
    return True


def holen(text):
    """Ein Stück holen (heute kostenlos). -> {adresse, geholt, neu, am}.
    Schon besessen → neu=False, das erste Datum bleibt."""
    kategorie, kennung = _aus_adresse(text)
    s = stueck(kategorie, kennung)
    if not _preis_null(s):
        raise ShopFehler("kostet etwas — bezahlen geht noch nicht", 402)
    ziel = s["@id"]
    with _LOCK:
        alle = _alle_besitze()
        if ziel in alle:
            return {"adresse": ziel, "geholt": True, "neu": False, "am": alle[ziel]}
        am = datetime.now().astimezone().isoformat(timespec="seconds")
        eigene = _datei_lesen(besitz_datei())
        eigene[ziel] = am
        _datei_schreiben(eigene)
    return {"adresse": ziel, "geholt": True, "neu": True, "am": am}


def besitz(kategorie=None):
    """Was geholt ist, als ItemList von OwnershipInfo; `typeOfGood` ist das
    Stück aus dem Katalog (gelesen, nicht gespeichert). Ein Stück, das der
    Katalog nicht mehr kennt, kommt nur mit `@id` und `category`."""
    _kategorie_pruefen(kategorie)
    nach_id = {s["@id"]: s for s in _katalog_roh()}
    eintraege = []
    for ziel, am in sorted(_alle_besitze().items(), key=lambda x: (x[1], x[0])):
        try:
            kat, kennung = _aus_adresse(ziel)
        except ShopFehler:
            continue
        if kategorie is not None and kat != kategorie:
            continue
        gut = nach_id.get(ziel) or {"@id": ziel, "category": kat, "identifier": kennung}
        eintraege.append({"@type": "OwnershipInfo", "ownedFrom": am, "typeOfGood": gut})
    return _liste(eintraege, "Geholt")
