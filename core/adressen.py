# core/adressen.py
#
# „Ein Objekt, eine Adresse" (Sasha, 2026-10-10; memory/system/hub_bauplan.md
# „Adressen"): jedes Objekt in ZENTRALE hat genau EINE neutrale Adresse
#
#     zentrale://<app>/<pfad>[?<abfrage>]
#
# z. B. zentrale://kalender/2026-10-12 (ein Tag) oder
# zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7 (ein Stück
# Kalender). Dieselbe Adresse steht im Kachel-Verweis auf der Fläche, kommt
# als Antwort von „oeffnen" und dient später als Link in Notizen und auf dem
# Handy. Jede Oberfläche bildet sie selbst auf ihre Ansicht ab — die App
# kennt keine Ansicht.
#
# Eine gewöhnliche URI (RFC 3986), gebaut und gelesen nur mit urllib.parse:
#   Schema     immer „zentrale"
#   Autorität  der App-Name (klein: a–z, 0–9, _ und -)
#   Pfad       das Objekt in der App, Abschnitte prozent-kodiert; bei einer
#              Kachel ist der erste Abschnitt die Art aus dem Katalog
#   Abfrage    Merkmale des Objekts (bei Kacheln: die `felder` des
#              Katalogs), jeder Name höchstens einmal
#   Fragment   reserviert (Stelle IN einem Objekt), heute abgelehnt
# Kanonisch: Namen der Abfrage sortiert, Werte als Text — dasselbe Objekt
# ergibt dieselbe Zeichenkette, so lässt sich eine Adresse vergleichen.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import re
from collections import namedtuple
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

SCHEMA = "zentrale"
LAENGE_GRENZE = 2000            # eine Adresse ist ein Verweis, kein Inhalt
_APP = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,39}$")

Adresse = namedtuple("Adresse", "app pfad abfrage")      # str, tuple[str], dict[str, str]


class AdresseFehler(ValueError):
    """Keine gültige ZENTRALE-Adresse. Der Text geht so an Sasha."""


def wert_text(wert):
    """Ein Wert als Text für die Abfrage: Zahlen als Ziffern, Wahr/Falsch als
    true/false (wie JSON), alles andere als str."""
    if isinstance(wert, bool):
        return "true" if wert else "false"
    return str(wert)


def bauen(app, pfad=(), abfrage=None):
    """(app, [abschnitt …], {name: wert}) → kanonische Adresse."""
    if not isinstance(app, str) or not _APP.match(app):
        raise AdresseFehler("app-name ungültig: %r" % (app,))
    if isinstance(pfad, str):
        pfad = [pfad]
    teile = [str(t) for t in pfad]
    if any(t == "" for t in teile):
        raise AdresseFehler("leerer abschnitt im pfad")
    weg = "/" + "/".join(quote(t, safe="") for t in teile) if teile else ""
    paare = sorted((str(k), wert_text(v)) for k, v in (abfrage or {}).items()
                   if v is not None)
    text = urlunsplit((SCHEMA, app, weg, urlencode(paare), ""))
    if len(text) > LAENGE_GRENZE:
        raise AdresseFehler("adresse zu lang")
    return text


def lesen(text):
    """Adresse → Adresse(app, pfad, abfrage); sonst AdresseFehler."""
    if not isinstance(text, str) or not text or len(text) > LAENGE_GRENZE:
        raise AdresseFehler("adresse fehlt oder ist zu lang")
    try:
        teile = urlsplit(text)
    except ValueError:
        raise AdresseFehler("keine adresse: %s" % text[:80])
    if teile.scheme != SCHEMA:
        raise AdresseFehler("adresse muss mit %s:// anfangen" % SCHEMA)
    if not _APP.match(teile.netloc or ""):
        raise AdresseFehler("app-name fehlt oder ist ungültig")
    if teile.fragment:
        raise AdresseFehler("„#…\" gibt es in adressen (noch) nicht")
    pfad = tuple(unquote(t) for t in teile.path.split("/")[1:]) if teile.path else ()
    if any(t == "" for t in pfad):
        raise AdresseFehler("leerer abschnitt im pfad")
    abfrage = {}
    for k, v in parse_qsl(teile.query, keep_blank_values=True, strict_parsing=False):
        if k in abfrage:
            raise AdresseFehler("„%s\" steht doppelt in der adresse" % k)
        abfrage[k] = v
    return Adresse(teile.netloc, pfad, abfrage)


def kanonisch(text):
    """Dieselbe Adresse in ihrer einen Schreibweise."""
    a = lesen(text)
    return bauen(a.app, a.pfad, a.abfrage)


def aus_verweis(app, art, ref):
    """Alter Kachel-Verweis {app, art, ref} (bis 2026-10-10) → Adresse. `ref`
    ist flach (Werte Text, Zahl, Wahr/Falsch) — so sahen alle aus."""
    if not isinstance(ref, dict) or any(isinstance(v, (dict, list)) for v in ref.values()):
        raise AdresseFehler("verweis lässt sich nicht als adresse schreiben")
    return bauen(app, [art], ref)
