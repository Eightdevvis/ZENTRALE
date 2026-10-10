# core/kacheln.py
#
# Der Hub für Kacheln (memory/system/hub_bauplan.md „Kacheln", entschieden
# 2026-10-09, gebaut 2026-10-10). Eine Kachel ist ein VERWEIS auf ein Objekt
# einer anderen App, nie eine Kopie — seit 2026-10-10 die neutrale Adresse
# des Objekts (core/adressen.py, „ein Objekt, eine Adresse"), z. B.
# zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7. Jede Oberfläche
# fragt hier über `POST /api/kachel` — nie direkt bei der App — und erfährt
# über `GET /api/kacheln` (Katalog), was es überhaupt gibt.
#
# Quellen: Listen (`fokus`), Graphen (`graph`) und der Kalender sind noch
# Kern-Module. Darum wohnen ihre Kachel-Quellen im Prozess (ein Modul je
# Quelle, eingetragen in QUELLEN) — hinter derselben Schnittstelle, die
# später eine ausgezogene App über HTTP bedient: Anfrage und Antwort gehen
# hier durch json.dumps/loads, als lägen sie auf der Leitung. Beim Auszug
# wird nur der Eintrag in QUELLEN gegen einen HTTP-Adapter getauscht, und
# der Katalog kommt aus dem Manifest (`app.toml`, `[kachel.<art>]` mit
# denselben Schlüsseln wie ARTEN unten) statt aus dem Modul.
#
# Eine Quelle (Modul) hat:
#   APP                       Name der App („kalender")
#   ARTEN                     {art: {titel, min: (w, h), bevorzugt?: (w, h),
#                              max?: (w, h), ttl, felder: [...]}} — der
#                              Katalog-Eintrag (Felder: core/kachel_felder.py)
#   RECHTE                    was die eingebaute App kann, z. B. ("lesen",)
#   kachel(art, ref, w, h, oben) -> {zeilen, text, oben?, oben_max?}
#   bevorzugt(art, ref)       -> (w, h) für genau diesen Bezug (optional)
#   aktion(art, ref, was)     -> {"zeige": {"adresse"}} (optional)
# und wirft kachel_form.KachelFehler / KachelWeg / KachelZuKlein. `ref` ist
# die Abfrage der Adresse, schon nach den Feldern geprüft und getypt.
#
# Maße: w/h sind abstrakte Zellen (Spalten × Zeilen), immer das Innere ohne
# Rahmen — jede Oberfläche rechnet sie in ihr eigenes Raster um.
#
# Zeitbudget (ZEITBUDGET_S): eine Antwort soll in 0,5 s da sein. Für Apps
# hinter HTTP bricht der Hub dort ab („aus"). Eine Quelle im Prozess lässt
# sich nicht abbrechen — sie wird gemessen und, wenn zu langsam, im Log
# gemeldet. Für JEDE Oberfläche gilt darum: nie auf eine Antwort warten,
# sondern aus dem eigenen Puffer zeichnen und im Hintergrund holen.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import time

import adressen
import kachel_felder
import kachel_kalender
import state
from kachel_form import (KachelFehler, KachelWeg, KachelZuKlein, stand_von,
                         zeilen_kuerzen)

QUELLEN = {}
TTL_VORGABE = 60
ZEITBUDGET_S = 0.5
# Obergrenze je Richtung (Zellen). Kein Bild einer Oberfläche, sondern ein
# Schutz: die Arbeit einer Quelle wächst mit w×h, und eine kaputte oder
# böswillige Anfrage soll sie nicht beliebig rechnen lassen. 400×400 ist weit
# mehr, als eine Kachel sinnvoll zeigt.
GROESSE_GRENZE = 400
FORMEN = ("zeilen",)              # „roh" (Rohdaten für Fenster/Handy) ist reserviert
AKTIONEN = ("oeffnen",)


def registrieren(quelle):
    QUELLEN[quelle.APP] = quelle
    return quelle


registrieren(kachel_kalender)


def _recht(app, recht="lesen"):
    """Prüfpunkt `<app>:lesen` (hub_bauplan.md „Rechte"). Eingebaute Quellen
    bringen ihre Rechte selbst mit; ausgezogene Apps später aus dem
    Manifest. Hier bleibt die Stelle, an der geprüft wird."""
    q = QUELLEN.get(app)
    return q is not None and recht in getattr(q, "RECHTE", ())


def _leitung(x):
    """So, als ginge es über HTTP: was nicht durch JSON passt, fällt hier auf."""
    return json.loads(json.dumps(x, ensure_ascii=False))


def _zahl(x, unten, oben):
    if isinstance(x, bool) or not isinstance(x, int) or not unten <= x <= oben:
        raise KachelFehler("größe muss eine ganze zahl sein")
    return x


def _wh(paar):
    return {"w": int(paar[0]), "h": int(paar[1])}


# ── Katalog ───────────────────────────────────────────────────────────

def _eintrag(q, art, info):
    e = {"app": q.APP, "art": art, "titel": str(info.get("titel") or art),
         "min": _wh(info.get("min", (1, 1))),
         "bevorzugt": _wh(info.get("bevorzugt") or info.get("min", (1, 1))),
         "ttl": int(info.get("ttl", TTL_VORGABE)),
         "felder": kachel_felder.form_pruefen(list(info.get("felder") or [])),
         "aktionen": list(AKTIONEN) if getattr(q, "aktion", None) else [],
         "formen": list(FORMEN)}
    # max immer (2026-10-10, Größe ändern im Desk): sagt die Quelle keins,
    # gilt die neutrale Grenze des Hubs — eine Oberfläche braucht so keine
    # eigene Zahl dafür.
    e["max"] = _wh(info["max"]) if info.get("max") else _wh((GROESSE_GRENZE, GROESSE_GRENZE))
    return e


def katalog():
    """`GET /api/kacheln` → [eintrag]: was jede App als Kachel liefern kann,
    nur Apps mit `<app>:lesen`. Heute aus ARTEN der Quellen im Prozess,
    später aus dem Manifest der App."""
    raus = []
    for app in sorted(QUELLEN):
        if not _recht(app, "lesen"):
            continue
        q = QUELLEN[app]
        for art, info in getattr(q, "ARTEN", {}).items():
            raus.append(_eintrag(q, art, info))
    return _leitung(raus)


# ── Anfrage lesen ─────────────────────────────────────────────────────

class _Abgelehnt(Exception):
    def __init__(self, status, antwort):
        super().__init__(status)
        self.status, self.antwort = status, antwort


def _verweis(anfrage):
    """Anfrage → (app, art, roh-bezug). Neu: `adresse`; alt (bis 2026-10-10,
    ältere Oberflächen auf anderen Rechnern): `app`, `art`, `ref`."""
    if isinstance(anfrage.get("adresse"), str):
        try:
            a = adressen.lesen(anfrage["adresse"])
        except adressen.AdresseFehler as e:
            raise _Abgelehnt(400, {"fehler": "ungueltig", "text": str(e)})
        if len(a.pfad) != 1:
            raise _Abgelehnt(400, {"fehler": "ungueltig",
                                   "text": "kachel-adresse: zentrale://<app>/<art>?…"})
        return a.app, a.pfad[0], a.abfrage
    app, art, ref = anfrage.get("app"), anfrage.get("art"), anfrage.get("ref")
    if not isinstance(app, str) or not isinstance(art, str) or not isinstance(ref, dict):
        raise _Abgelehnt(400, {"fehler": "ungueltig", "text": "adresse fehlt"})
    return app, art, ref


def _anfrage_lesen(anfrage):
    """→ (quelle, app, art, ref) mit geprüftem, getyptem ref; sonst
    _Abgelehnt mit Status und Antwort."""
    if not isinstance(anfrage, dict):
        raise _Abgelehnt(400, {"fehler": "ungueltig", "text": "anfrage fehlt"})
    app, art, roh = _verweis(anfrage)
    q = QUELLEN.get(app)
    if q is None:
        raise _Abgelehnt(503, {"fehler": "aus", "text": "app „%s\" ist nicht da" % app})
    if not _recht(app, "lesen"):
        raise _Abgelehnt(403, {"fehler": "recht", "text": "%s:lesen fehlt" % app})
    if art not in getattr(q, "ARTEN", {}):
        raise _Abgelehnt(400, {"fehler": "ungueltig",
                               "text": "%s kennt keine art „%s\"" % (app, art)})
    felder = q.ARTEN[art].get("felder")
    try:
        ref = kachel_felder.pruefen(felder, roh) if felder is not None else roh
    except KachelFehler as e:
        raise _Abgelehnt(400, {"fehler": "ungueltig", "text": str(e)})
    return q, app, art, ref


def _fehler(e, app):
    if isinstance(e, KachelWeg):
        return 404, {"fehler": "weg"}
    if isinstance(e, KachelFehler):
        return 400, {"fehler": "ungueltig", "text": str(e)}
    state.push_log("KACHEL ✗  %s: %s" % (app, e))
    return 503, {"fehler": "aus", "text": "%s antwortet nicht" % app}


def _gemessen(app, f, *args):
    """Quelle im Prozess fragen und die Zeit gegen ZEITBUDGET_S halten."""
    t0 = time.monotonic()
    try:
        return f(*args)
    finally:
        dauer = time.monotonic() - t0
        if dauer > ZEITBUDGET_S:
            state.push_log("KACHEL ⏱  %s brauchte %.1f s (budget %.1f s)"
                           % (app, dauer, ZEITBUDGET_S))


# ── Inhalt ────────────────────────────────────────────────────────────

def _bevorzugt(q, art, ref):
    f = getattr(q, "bevorzugt", None)
    if f is None:
        return None
    try:
        return _wh(f(art, _leitung(ref)))
    except Exception:
        return None                       # nur ein Wunsch — fehlt er, gilt der Katalog


def holen(anfrage):
    """`POST /api/kachel`. Anfrage {adresse, w, h, oben?, stand?, form?}
    (w/h auch als groesse: {w, h}; alt statt adresse: app, art, ref) →
    (status, antwort). Antwort: {form, zeilen, text, stand, ttl, oben,
    oben_max, bevorzugt?} | {unveraendert, stand, ttl} | {zu_klein: {w, h},
    ttl, bevorzugt?} | {fehler: weg|aus|recht|ungueltig, text?}."""
    anfrage = _leitung(anfrage)
    try:
        q, app, art, ref = _anfrage_lesen(anfrage)
    except _Abgelehnt as e:
        return e.status, e.antwort
    groesse = anfrage.get("groesse") if isinstance(anfrage.get("groesse"), dict) else anfrage
    form = anfrage.get("form", "zeilen")
    if form not in FORMEN:
        return 400, {"fehler": "ungueltig", "text": "form „%s\" gibt es (noch) nicht" % form}
    try:
        w = _zahl(groesse.get("w"), 0, GROESSE_GRENZE)
        h = _zahl(groesse.get("h"), 0, GROESSE_GRENZE)
        oben = _zahl(anfrage.get("oben", 0), 0, 10000)
    except KachelFehler as e:
        return 400, {"fehler": "ungueltig", "text": str(e)}
    art_info = q.ARTEN[art]
    ttl = int(art_info.get("ttl", TTL_VORGABE))
    wunsch = _bevorzugt(q, art, ref)
    extra = {"bevorzugt": wunsch} if wunsch else {}
    mw, mh = art_info.get("min", (1, 1))
    if w < mw or h < mh:
        return 200, dict({"zu_klein": {"w": mw, "h": mh}, "ttl": ttl}, **extra)
    try:
        inhalt = _leitung(_gemessen(app, q.kachel, art, _leitung(ref), w, h, oben))
        zeilen = zeilen_kuerzen(inhalt.get("zeilen") or [], w, h)
    except KachelZuKlein as e:
        return 200, dict({"zu_klein": {"w": e.w, "h": e.h}, "ttl": ttl}, **extra)
    except Exception as e:                  # eine Quelle darf den Hub nie reißen
        return _fehler(e, app)
    text = str(inhalt.get("text") or "")
    oben = int(inhalt.get("oben", oben) or 0)
    stand = stand_von(zeilen, text, oben)
    if anfrage.get("stand") == stand:
        return 200, {"unveraendert": True, "stand": stand, "ttl": ttl}
    return 200, _leitung(dict({"form": form, "zeilen": zeilen, "text": text, "stand": stand,
                               "ttl": ttl, "oben": oben,
                               "oben_max": int(inhalt.get("oben_max", 0) or 0)}, **extra))


def aktion(anfrage):
    """`POST /api/kachel/aktion`. Anfrage {adresse, aktion} (alt: app, art,
    ref, aktion) → (status, antwort). Heute nur „oeffnen": die App sagt mit
    einer Adresse, WAS aufgehen soll — {"zeige": {"adresse"}}; wie, weiß
    jede Oberfläche selbst."""
    anfrage = _leitung(anfrage)
    try:
        q, app, art, ref = _anfrage_lesen(anfrage)
    except _Abgelehnt as e:
        return e.status, e.antwort
    was = anfrage.get("aktion")
    machen = getattr(q, "aktion", None)
    if was not in AKTIONEN or machen is None:
        return 400, {"fehler": "ungueltig", "text": "aktion fehlt oder geht hier nicht"}
    try:
        antwort = _leitung(_gemessen(app, machen, art, _leitung(ref), was))
    except Exception as e:
        return _fehler(e, app)
    zeige = antwort.get("zeige") if isinstance(antwort, dict) else None
    try:
        ziel = adressen.kanonisch((zeige or {}).get("adresse"))
    except adressen.AdresseFehler:
        return 503, {"fehler": "aus", "text": "%s sagt nicht, wohin" % app}
    return 200, {"zeige": {"adresse": ziel}}
