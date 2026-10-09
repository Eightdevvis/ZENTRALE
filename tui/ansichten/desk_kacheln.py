# tui/ansichten/desk_kacheln.py
#
# Kacheln im Desk holen und puffern (2026-10-10). Eine Kachel ist ein
# Verweis auf ein Objekt einer anderen App (memory/system/hub_bauplan.md
# „Kacheln"); ihren Inhalt fragt die Ansicht über den Hub an
# (`POST /api/kachel`), nie direkt bei der App.
#
# Regel (Sasha, 2026-10-10): gezeichnet wird IMMER aus dem Puffer, geholt im
# Hintergrund — beim Öffnen, wenn die Frist (ttl) um ist, nach Blättern oder
# wenn sich die Größe ändert. Die Oberfläche wartet nie auf eine Antwort.
# Der Puffer liegt am Element unter „_inhalt" (die Art „kachel" im Baustein
# zeichnet ihn); Felder mit „_" gehen nie in die Datei.

import json
import time
import urllib.error

from .farben import ROLES

ROLLEN = set(ROLES)
NOCHMAL_S = 15                 # nach einem Fehler: so lange bis zum nächsten Versuch


def ist_kachel(el):
    return el.get("art") == "kachel" and isinstance(el.get("kachel"), dict)


def innen(el):
    """Innenmaß (ohne Rahmen) — das bekommt die App."""
    return max(0, el["w"] - 2), max(0, el["h"] - 2)


def schluessel(el):
    """Was den Inhalt bestimmt: Verweis, Größe, Blätter-Lage."""
    k = el["kachel"]
    w, h = innen(el)
    return json.dumps([k.get("app"), k.get("art"), k.get("ref"), w, h, el.get("_oben", 0)],
                      sort_keys=True)


def anfrage(el, stand=None):
    k = el["kachel"]
    w, h = innen(el)
    a = {"app": k.get("app"), "art": k.get("art"), "ref": k.get("ref"),
         "w": w, "h": h, "oben": el.get("_oben", 0)}
    if stand:
        a["stand"] = stand
    return a


def faellig(el, jetzt):
    if el.get("_holt"):
        return False
    inhalt = el.get("_inhalt")
    if not inhalt or inhalt.get("schluessel") != schluessel(el):
        return True
    return jetzt >= inhalt.get("bis", 0)


def _zeilen(roh):
    """Zeilen der App → [(text, rolle)]; unbekannte Rollen werden „dim"
    (hub_bauplan.md), Kaputtes fällt weg."""
    raus = []
    for zeile in roh if isinstance(roh, list) else []:
        stuecke = []
        for s in zeile if isinstance(zeile, list) else []:
            if isinstance(s, list) and len(s) == 2:
                stuecke.append((str(s[0]), s[1] if s[1] in ROLLEN else "dim"))
        raus.append(stuecke)
    return raus


def antwort_lesen(alt, a, key, jetzt):
    """Antwort des Hubs → neuer Puffer. `key` = Schlüssel zur Zeit der
    ANFRAGE: wurde inzwischen weitergeblättert, passt er nicht mehr, und
    der nächste Durchgang holt gleich nach."""
    ttl = a.get("ttl") if isinstance(a.get("ttl"), int) else 60
    if a.get("unveraendert") and alt.get("schluessel") == key:
        return dict(alt, bis=jetzt + ttl)
    if isinstance(a.get("zu_klein"), dict):
        k = a["zu_klein"]
        aussen = {n: k[n] + 2 if isinstance(k.get(n), int) else "?" for n in ("w", "h")}
        return {"zustand": "zu_klein", "zu_klein": aussen, "schluessel": key, "bis": jetzt + ttl}
    return {"zustand": "ok", "zeilen": _zeilen(a.get("zeilen")), "text": str(a.get("text") or ""),
            "stand": a.get("stand"), "oben_max": a.get("oben_max", 0) or 0,
            "schluessel": key, "bis": jetzt + ttl}


def fehler_lesen(alt, e, key, jetzt):
    """Fehler → Puffer: weg (404), ungültig (400, mit Grund), sonst „aus" mit
    dem letzten Stand (die Art zeichnet ihn leise)."""
    neu = {"schluessel": key, "bis": jetzt + NOCHMAL_S, "zeilen": alt.get("zeilen") or [],
           "text": alt.get("text", ""), "oben_max": alt.get("oben_max", 0)}
    code = getattr(e, "code", None)
    body = {}
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = json.loads(e.read().decode("utf-8")) or {}
        except Exception:
            body = {}
    if code == 404:
        neu.update(zustand="weg", zeilen=[])
    elif code == 400:
        neu.update(zustand="fehler", zeilen=[], text=str(body.get("text") or "geht nicht"))
    else:
        neu["zustand"] = "aus"
    return neu


def holen(el, api, uhr=time.monotonic):
    """Eine Kachel holen (läuft im Hintergrund). Schreibt am Ende EINMAL
    el["_inhalt"] — ein ganzes neues dict, nie halb."""
    alt = el.get("_inhalt") or {}
    key = schluessel(el)
    stand = alt.get("stand") if alt.get("schluessel") == key else None
    try:
        a = api("/api/kachel", "POST", anfrage(el, stand))
        neu = antwort_lesen(alt, a if isinstance(a, dict) else {}, key, uhr())
    except Exception as e:
        neu = fehler_lesen(alt, e, key, uhr())
    el["_inhalt"] = neu
    el["_holt"] = None


def pflegen(elemente, api, starten, uhr=time.monotonic):
    """Jede Kachel, deren Puffer fehlt, veraltet ist oder nicht mehr passt,
    im Hintergrund holen (`starten(f)` führt f aus — Thread oder, in Tests,
    gleich). Kehrt sofort zurück."""
    jetzt = uhr()
    for el in list(elemente):
        if ist_kachel(el) and faellig(el, jetzt):
            el["_holt"] = schluessel(el)
            starten(lambda el=el: holen(el, api, uhr))


def fuer_datei(el):
    """Element → was zum Backend geht: ohne Puffer („_…"); eine Kachel nimmt
    ihren Klartext als Rückfall für Obsidian mit."""
    raus = {k: v for k, v in el.items() if not k.startswith("_")}
    inhalt = el.get("_inhalt") or {}
    if ist_kachel(el) and inhalt.get("zustand") == "ok" and inhalt.get("text"):
        raus["rueckfall"] = inhalt["text"]
    return raus
