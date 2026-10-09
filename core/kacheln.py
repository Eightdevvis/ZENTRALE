# core/kacheln.py
#
# Der Hub für Kacheln (memory/system/hub_bauplan.md „Kacheln", entschieden
# 2026-10-09, gebaut 2026-10-10). Eine Kachel ist ein VERWEIS auf ein Objekt
# einer anderen App (app + art + ref), nie eine Kopie. Jede Front fragt hier
# über `POST /api/kachel` — nie direkt bei der App.
#
# Quellen: Listen (`fokus`), Graphen (`graph`) und der Kalender sind noch
# Kern-Module. Darum wohnen ihre Kachel-Quellen im Prozess (ein Modul je
# Quelle, eingetragen in QUELLEN) — hinter derselben Schnittstelle, die
# später eine ausgezogene App über HTTP bedient: Anfrage und Antwort gehen
# hier durch json.dumps/loads, als lägen sie auf der Leitung. Beim Auszug
# wird nur der Eintrag in QUELLEN gegen einen HTTP-Adapter getauscht.
#
# Eine Quelle (Modul) hat:
#   APP                       Name der App („kalender")
#   ARTEN                     {art: {"min": (w, h), "ttl": s}}
#   RECHTE                    was die eingebaute App kann, z. B. ("lesen",)
#   kachel(art, ref, w, h, oben) -> {zeilen, text, oben?, oben_max?}
#   aktion(art, ref, was)     -> {"zeige": {ansicht, ziel}} (optional)
# und wirft kachel_form.KachelFehler / KachelWeg / KachelZuKlein.
#
# Zeitgrenze 0,5 s (hub_bauplan.md): gilt für Apps hinter HTTP. Eine Quelle
# im Prozess wird nicht abgebrochen — die TUI holt ohnehin im Hintergrund
# und zeichnet aus ihrem Puffer.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json

import state
import kachel_kalender
from kachel_form import (KachelFehler, KachelWeg, KachelZuKlein, stand_von,
                         zeilen_kuerzen)

QUELLEN = {}
TTL_VORGABE = 60
GROESSE_GRENZE = 400              # Zellen je Richtung — mehr zeigt kein Terminal


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


class _Abgelehnt(Exception):
    def __init__(self, status, antwort):
        super().__init__(status)
        self.status, self.antwort = status, antwort


def _anfrage_lesen(anfrage):
    """→ (quelle, app, art, ref); sonst _Abgelehnt mit Status und Antwort."""
    if not isinstance(anfrage, dict):
        raise _Abgelehnt(400, {"fehler": "ungueltig", "text": "anfrage fehlt"})
    app, art, ref = anfrage.get("app"), anfrage.get("art"), anfrage.get("ref")
    if not isinstance(app, str) or not isinstance(art, str) or not isinstance(ref, dict):
        raise _Abgelehnt(400, {"fehler": "ungueltig", "text": "app, art und ref fehlen"})
    q = QUELLEN.get(app)
    if q is None:
        raise _Abgelehnt(503, {"fehler": "aus", "text": "app „%s\" ist nicht da" % app})
    if not _recht(app, "lesen"):
        raise _Abgelehnt(403, {"fehler": "recht", "text": "%s:lesen fehlt" % app})
    if art not in getattr(q, "ARTEN", {}):
        raise _Abgelehnt(400, {"fehler": "ungueltig",
                               "text": "%s kennt keine art „%s\"" % (app, art)})
    return q, app, art, ref


def _fehler(e, app):
    if isinstance(e, KachelWeg):
        return 404, {"fehler": "weg"}
    if isinstance(e, KachelFehler):
        return 400, {"fehler": "ungueltig", "text": str(e)}
    state.push_log("KACHEL ✗  %s: %s" % (app, e))
    return 503, {"fehler": "aus", "text": "%s antwortet nicht" % app}


def holen(anfrage):
    """`POST /api/kachel`. Anfrage {app, art, ref, w, h, oben?, stand?}
    (w/h auch als groesse: {w, h}) → (status, antwort). Antwort: {zeilen,
    text, stand, ttl, oben, oben_max} | {unveraendert, stand, ttl} |
    {zu_klein: {w, h}, ttl} | {fehler: weg|aus|recht|ungueltig, text?}.
    Das Feld `roh` (Rohdaten für Fenster/Handy) ist reserviert."""
    anfrage = _leitung(anfrage)
    try:
        q, app, art, ref = _anfrage_lesen(anfrage)
    except _Abgelehnt as e:
        return e.status, e.antwort
    groesse = anfrage.get("groesse") if isinstance(anfrage.get("groesse"), dict) else anfrage
    try:
        w = _zahl(groesse.get("w"), 0, GROESSE_GRENZE)
        h = _zahl(groesse.get("h"), 0, GROESSE_GRENZE)
        oben = _zahl(anfrage.get("oben", 0), 0, 10000)
    except KachelFehler as e:
        return 400, {"fehler": "ungueltig", "text": str(e)}
    art_info = q.ARTEN[art]
    ttl = int(art_info.get("ttl", TTL_VORGABE))
    mw, mh = art_info.get("min", (1, 1))
    if w < mw or h < mh:
        return 200, {"zu_klein": {"w": mw, "h": mh}, "ttl": ttl}
    try:
        inhalt = _leitung(q.kachel(art, _leitung(ref), w, h, oben))
    except KachelZuKlein as e:
        return 200, {"zu_klein": {"w": e.w, "h": e.h}, "ttl": ttl}
    except Exception as e:                  # eine Quelle darf den Hub nie reißen
        return _fehler(e, app)
    zeilen = zeilen_kuerzen(inhalt.get("zeilen") or [], w, h)
    text = str(inhalt.get("text") or "")
    oben = int(inhalt.get("oben", oben) or 0)
    stand = stand_von(zeilen, text, oben)
    if anfrage.get("stand") == stand:
        return 200, {"unveraendert": True, "stand": stand, "ttl": ttl}
    return 200, _leitung({"zeilen": zeilen, "text": text, "stand": stand, "ttl": ttl,
                          "oben": oben, "oben_max": int(inhalt.get("oben_max", 0) or 0)})


def aktion(anfrage):
    """`POST /api/kachel/aktion`. Anfrage {app, art, ref, aktion} → (status,
    antwort). Heute nur „oeffnen": die App sagt, wohin die Front springt —
    {"zeige": {"ansicht", "ziel"}}."""
    anfrage = _leitung(anfrage)
    try:
        q, app, art, ref = _anfrage_lesen(anfrage)
    except _Abgelehnt as e:
        return e.status, e.antwort
    was = anfrage.get("aktion")
    machen = getattr(q, "aktion", None)
    if not isinstance(was, str) or machen is None:
        return 400, {"fehler": "ungueltig", "text": "aktion fehlt oder geht hier nicht"}
    try:
        antwort = _leitung(machen(art, _leitung(ref), was))
    except Exception as e:
        return _fehler(e, app)
    zeige = antwort.get("zeige") if isinstance(antwort, dict) else None
    if not isinstance(zeige, dict) or not isinstance(zeige.get("ansicht"), str):
        return 503, {"fehler": "aus", "text": "%s sagt nicht, wohin" % app}
    return 200, {"zeige": {"ansicht": zeige["ansicht"], "ziel": zeige.get("ziel")}}
