# core/werkstatt.py
#
# Die Werkstatt (2026-10-10, Sasha): „so simpel wie's geht" — der Schmied
# baut aus einer Vorlage eine eigene App. Heute gibt es genau eine Vorlage,
# „Desk View": die App IST dann ein Desk mit Namen und Symbol, der als
# eigene App im App-Rad steht. Doku: memory/hub/werkstatt.md.
#
# Ablage — Standards, kein eigenes Format (hub_bauplan.md „Leitlinie"):
#   <apps_ordner>/<slug>/app.toml   dasselbe Manifest wie bei Prozess-Apps
#                                   (language-tutor/app.toml), aber ohne
#                                   `start`, dafür `vorlage = "desk"` und
#                                   `desk = "<Desk-Name>"` (Verweis, keine Kopie)
#   <apps_ordner>/<slug>/icon.png   das Symbol als kleines PNG (wenn aus Bild)
# `apps_ordner` ist Standard data/apps/ und steht auf der Abgleich-Liste
# (core/abgleich_auswahl.py) wie data/desk/. Gefunden werden die Apps über
# core/apps.py (eigene()).
#
# Der Desk selbst bleibt, wo Desks wohnen (core/desk.py): so geht er in
# Obsidian auf wie jeder andere und die Desk-Ansicht muss nichts von Apps
# wissen. Die App zeigt nur auf ihn.
#
# Kurzname (slug): aus dem Namen, klein, a–z 0–9 und „-" — er ist Ordnername
# und Adresse zentrale://<slug>/ (core/adressen.py: Autorität a–z 0–9 _ -).
# Er bleibt beim Umbenennen gleich: eine Adresse soll nicht wandern.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import re
import shutil
import time
import tomllib

import app_installation
import apps
import bild_vorschau
import datasync
import dateien
import desk
import desk_bild
import nutzer_ordner

VERSION = "0.1.0"
SLUG_LAENGE = 16          # passt als Schriftzug auf das Symbol (16 Zellen breit)
_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,%d}$" % (SLUG_LAENGE - 1))
_MOTIV = re.compile(r"^[a-z]{1,20}$")
# Namen, die schon etwas anderes meinen: feste Apps im Rad, die Räder, Hub.
# Ein Kurzname davon würde eine Adresse oder ein Symbol doppelt belegen.
RESERVIERT = {"klavier", "post", "kalender", "fokus", "notizen", "graph", "karte",
              "tutor", "desk", "elektronik", "werkstatt", "shop", "ki", "apps",
              "technik", "erschaffen", "system", "stdout", "netz", "zentrale", "hub"}
# Die Vorlagen. Erst eine (Sasha); eine neue kommt als Eintrag hier und
# als Weg in anlegen() dazu.
VORLAGEN = [{"id": "desk", "titel": "Desk View",
             "text": "eine unendliche fläche mit zetteln, bildern und kacheln"}]
_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


class WerkstattFehler(ValueError):
    """Eingabe taugt nicht. `code` sagt der Route den HTTP-Status."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


def ordner() -> str:
    return apps.eigene_ordner()


def slug_aus(name) -> str:
    """„Geige & Bogen" → „geige-bogen". Leer, wenn nichts übrig bleibt."""
    s = "".join(_UMLAUTE.get(c, c) for c in str(name or "").strip().lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"^[0-9-]+", "", s)               # vorn ein Buchstabe
    return s[:SLUG_LAENGE].rstrip("-")


def _app_ordner(slug) -> str:
    if not _SLUG.match(str(slug or "")):
        raise WerkstattFehler("diese app gibt es nicht", 404)
    return os.path.join(ordner(), slug)


def name_pruefen(name) -> str:
    """Name → getrimmt; er wird auch der Name des Desks, darum dieselben
    Regeln wie dort."""
    try:
        return desk.name_pruefen(name)
    except desk.DeskFehler:
        raise WerkstattFehler("name ungültig (buchstaben, ziffern, leerzeichen, - _ . bis 60 zeichen)")


def namen_pruefen(name, ausser=None) -> tuple:
    """Name für eine neue (oder umbenannte) App → (name, slug). Fehler,
    wenn der Kurzname leer, vergeben oder reserviert ist."""
    name = name_pruefen(name)
    slug = slug_aus(name)
    if not slug:
        raise WerkstattFehler("der name braucht mindestens einen buchstaben")
    if slug in RESERVIERT or slug in apps.BEKANNT or slug in app_installation.namen():
        raise WerkstattFehler("„%s\" heißt schon eine feste app — anderer name?" % slug, 409)
    for m in apps.eigene():
        if m["_slug"] == ausser:
            continue
        if m["_slug"] == slug or str(m.get("name", "")).strip().lower() == name.lower():
            raise WerkstattFehler("eine app „%s\" gibt es schon" % m.get("name", slug), 409)
    return name, slug


# ── Manifest (app.toml) ───────────────────────────────────────────────

def _toml_text(wert) -> str:
    """Ein TOML-Basis-String. json.dumps erzeugt nur Escapes, die TOML auch
    kennt (\\" \\\\ \\n \\t \\uXXXX …) — kein eigener Escaper."""
    return json.dumps(str(wert), ensure_ascii=False)


def manifest_text(m: dict) -> str:
    """dict → app.toml. Nur flache Text-Werte in fester Reihenfolge; mehr
    braucht eine Vorlagen-App nicht. Gelesen wird mit tomllib."""
    zeilen = ["# Selbst gebaute App aus der Werkstatt (memory/hub/werkstatt.md).",
              "# Kein Prozess: vorlage sagt, was beim Öffnen aufgeht."]
    for k in ("name", "version", "vorlage", "icon", "icon_motiv", "desk", "erstellt"):
        if m.get(k) not in (None, ""):
            zeilen.append("%s = %s" % (k, _toml_text(m[k])))
    return "\n".join(zeilen) + "\n"


def _manifest_schreiben(slug, m):
    pfad = os.path.join(_app_ordner(slug), "app.toml")
    dateien.atomar_schreiben(pfad, manifest_text(m))
    datasync.notify_change(pfad)


def _manifest_lesen(slug) -> dict:
    pfad = os.path.join(_app_ordner(slug), "app.toml")
    try:
        with open(pfad, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise WerkstattFehler("diese app gibt es nicht", 404)
    except (OSError, tomllib.TOMLDecodeError):
        raise WerkstattFehler("app.toml ist kaputt — bitte von hand ansehen", 422)


# ── Symbol ────────────────────────────────────────────────────────────

def bilder() -> list:
    """Bilder in ~/Zentrale/Input, die ein Symbol werden können."""
    return desk_bild.quellen()


def _icon_aus_bild(slug, quelle):
    """Bild aus Input/ → icon.png im App-Ordner. Nur Input/ (kein freier
    Pfad): was im abgeglichenen Ordner landet, hat Sasha dort hingelegt."""
    p = nutzer_ordner.aufloesen(quelle, erlaubt=(nutzer_ordner.INPUT,))
    if p is None or not os.path.isfile(p):
        raise WerkstattFehler("bild nicht gefunden: %s" % quelle, 404)
    if not desk.ist_bild(p):
        raise WerkstattFehler("das ist keine bild-datei (png, jpg, gif, webp, bmp)")
    if os.path.getsize(p) > desk_bild.GROESSE_GRENZE:
        raise WerkstattFehler("das bild ist zu groß (über 50 MB)")
    try:
        png = bild_vorschau.icon_machen(p)
    except bild_vorschau.OhnePillow as e:
        raise WerkstattFehler(str(e), 503)
    except bild_vorschau.KeinBild as e:
        raise WerkstattFehler(str(e))
    ziel = os.path.join(_app_ordner(slug), "icon.png")
    dateien.atomar_schreiben(ziel, png)
    datasync.notify_change(ziel)


def _icon_setzen(slug, m, icon):
    """icon = {"bild": "foto.png"} | {"motiv": "post"} → Manifest-Felder."""
    icon = icon if isinstance(icon, dict) else {}
    if icon.get("bild"):
        _icon_aus_bild(slug, icon["bild"])
        m["icon"], m["icon_motiv"] = "icon.png", None
    elif icon.get("motiv"):
        if not _MOTIV.match(str(icon["motiv"])):
            raise WerkstattFehler("unbekanntes symbol")
        m["icon_motiv"], m["icon"] = str(icon["motiv"]), None
        try:
            os.remove(os.path.join(_app_ordner(slug), "icon.png"))
        except FileNotFoundError:
            pass
    else:
        raise WerkstattFehler("welches symbol? (bild oder motiv)")


def _icon_fuer_liste(slug, m):
    return apps.icon(_app_ordner(slug), m)      # eine Stelle für alle Apps


# ── Öffentlich ────────────────────────────────────────────────────────

def _als_eintrag(slug, m) -> dict:
    return {"slug": slug, "name": str(m.get("name") or slug),
            "version": str(m.get("version") or ""), "vorlage": str(m.get("vorlage") or ""),
            "desk": str(m.get("desk") or ""), "adresse": "zentrale://%s/" % slug,
            "icon": _icon_fuer_liste(slug, m)}


def liste() -> list:
    """Alle selbst gebauten Apps, nach Kurzname — die Reihenfolge im Rad."""
    return [_als_eintrag(m["_slug"], m) for m in apps.eigene() if m.get("vorlage")]


def laden(slug) -> dict:
    return _als_eintrag(slug, _manifest_lesen(slug))


def vorlagen() -> list:
    return [dict(v) for v in VORLAGEN]


def anlegen(name, icon, vorlage="desk") -> dict:
    """Neue App aus einer Vorlage. Bei „desk" entsteht (oder gibt es schon)
    ein Desk gleichen Namens — ein vorhandener wird übernommen, nicht
    überschrieben."""
    if vorlage not in {v["id"] for v in VORLAGEN}:
        raise WerkstattFehler("diese vorlage gibt es (noch) nicht")
    name, slug = namen_pruefen(name)
    o = _app_ordner(slug)
    if os.path.exists(o):
        raise WerkstattFehler("der ordner %s gibt es schon — anderer name?" % slug, 409)
    os.makedirs(o)
    m = {"name": name, "version": VERSION, "vorlage": vorlage, "desk": name,
         "erstellt": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        _icon_setzen(slug, m, icon)
        try:
            desk.anlegen(name)
        except desk.DeskFehler as e:
            if e.code != 409:            # gibt es schon: die App nimmt ihn
                raise WerkstattFehler(str(e), e.code)
        _manifest_schreiben(slug, m)
    except Exception:
        shutil.rmtree(o, ignore_errors=True)     # halbe App nie liegen lassen
        raise
    return laden(slug)


def aendern(slug, name=None, icon=None) -> dict:
    """Name und/oder Symbol ändern. Der Kurzname (Ordner, Adresse) bleibt."""
    m = _manifest_lesen(slug)
    if name is not None:
        m["name"] = namen_pruefen(name, ausser=slug)[0]
    if icon is not None:
        _icon_setzen(slug, m, icon)
    _manifest_schreiben(slug, m)
    return laden(slug)


def loeschen(slug, desk_mit=False) -> None:
    """App weg (Ordner). Ihr Desk nur, wenn `desk_mit` — Sasha wird gefragt."""
    m = _manifest_lesen(slug)
    if desk_mit and m.get("desk"):
        try:
            desk.loeschen(m["desk"])
        except desk.DeskFehler as e:
            if e.code != 404:
                raise WerkstattFehler(str(e), e.code)
    o = _app_ordner(slug)
    shutil.rmtree(o)
    datasync.notify_change(o)


def apps_mit_desk(name) -> list:
    """Kurznamen der Apps, die auf diesen Desk zeigen."""
    return [m["_slug"] for m in apps.eigene() if str(m.get("desk") or "") == str(name)]


def desk_umbenennen(alt, neu) -> dict:
    """Desk umbenennen und Apps, die auf ihn zeigen, mitziehen."""
    try:
        d = desk.umbenennen(alt, neu)
    except desk.DeskFehler as e:
        raise WerkstattFehler(str(e), e.code)
    for slug in apps_mit_desk(alt):
        m = _manifest_lesen(slug)
        m["desk"] = d["name"]
        _manifest_schreiben(slug, m)
    return {"name": d["name"]}


def desk_loeschen(name) -> None:
    """Einen Desk löschen — nicht, solange eine App auf ihm steht."""
    belegt = apps_mit_desk(name)
    if belegt:
        raise WerkstattFehler("der desk gehört zur app „%s\" — erst die app löschen" % belegt[0], 409)
    try:
        desk.loeschen(name)
    except desk.DeskFehler as e:
        raise WerkstattFehler(str(e), e.code)
