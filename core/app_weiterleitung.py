# core/app_weiterleitung.py
#
# Routen-Weiterleitung des Hubs (Hub-Grundlagen, 2026-10-22,
# memory/hub/hub_bauplan.md „Routen weiterreichen"): eine Prozess-App sagt in
# ihrem app.toml, welche Pfade ihr gehören —
#
#   routen = ["/api/map"]          # /api/map und alles darunter
#
# — und der Hub reicht jede Anfrage darauf UNVERÄNDERT an ihre `adresse`
# weiter: Methode, Pfad, Abfrage (als rohe Bytes), Körper und die
# Inhalts-Köpfe; zurück kommen Status, Inhalts-Köpfe und Körper ebenso
# unverändert. Darum bleiben die alten Pfade für jede Oberfläche gleich (TUI,
# Browser, Pi), wenn ein Modul als App auszieht.
#
# Was NICHT mitgeht: der Zugangsschlüssel des Hubs (Authorization), Kekse,
# Host und die Verbindungs-Köpfe (hop-by-hop, RFC 9110 §7.6.1). Die App
# lauscht nur auf 127.0.0.1; wer an sie will, geht durch die Tür des Hubs
# (ui/routen/zugang.py läuft vorher).
#
# App aus oder nicht erreichbar, oder antwortet nicht in WARTEZEIT →
# 503 {"fehler": "aus"} — dieselbe Form wie bei Kacheln. Umleitungen der App
# folgt der Hub nicht (http.client statt urllib): sie gehen so an den Aufrufer.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import http.client
import json
import threading
import time
from urllib.parse import urlsplit

import apps

WARTEZEIT = 30.0             # Sekunden je Verbindungsschritt (Karte rechnet ~1 s)
TABELLE_TTL = 2.0            # so lange gilt die gelesene Routen-Tabelle

# Köpfe, die zwischen Aufrufer und App durchgehen (klein geschrieben).
KOEPFE_HIN = ("content-type", "accept", "accept-language", "if-none-match",
              "if-modified-since", "user-agent")
KOEPFE_ZURUECK = ("content-type", "cache-control", "etag", "last-modified",
                  "content-disposition", "location", "retry-after", "expires")

_lock = threading.Lock()
_tabelle = {"bis": 0.0, "eintraege": []}


def _eintraege():
    """[(präfix, manifest)], längstes Präfix zuerst; kurz gepuffert, damit
    nicht jede Anfrage alle app.toml liest."""
    jetzt = time.monotonic()
    with _lock:
        if jetzt < _tabelle["bis"]:
            return _tabelle["eintraege"]
    eintraege = []
    for m in apps.installiert():
        for r in apps.routen(m):
            eintraege.append((r, m))
    eintraege.sort(key=lambda e: -len(e[0]))
    with _lock:
        _tabelle.update(bis=jetzt + TABELLE_TTL, eintraege=eintraege)
    return eintraege


def vergessen():
    """Routen-Tabelle neu lesen lassen (nach Änderung eines Manifests, Tests)."""
    with _lock:
        _tabelle["bis"] = 0.0


def besitzer(pfad: str):
    """Manifest der App, der dieser Pfad gehört — oder None (gehört dem Hub).
    Präfix nur an Abschnittsgrenzen: /api/map gehört /api/map/base, nicht
    /api/mapx."""
    for praefix, m in _eintraege():
        if pfad == praefix or pfad.startswith(praefix + "/"):
            return m
    return None


def routen_tabelle() -> dict:
    """präfix → App-Name (für Doku und Wächter)."""
    return {p: str(m.get("name")) for p, m in _eintraege()}


def _aus(m, grund):
    text = "„%s\" ist aus oder antwortet nicht (%s)" % (m.get("name"), grund)
    return 503, [("Content-Type", "application/json")], \
        json.dumps({"fehler": "aus", "text": text}, ensure_ascii=False).encode("utf-8")


def weiterleiten(m: dict, methode: str, pfad: str, abfrage: bytes, koerper: bytes,
                 koepfe) -> tuple:
    """Eine Anfrage an die App reichen. koepfe: Paare (name, wert) des
    Aufrufers. → (status, [(name, wert)], körper-bytes)."""
    ziel = urlsplit(str(m.get("adresse") or ""))
    if ziel.scheme != "http" or not ziel.hostname:
        return _aus(m, "adresse im app.toml taugt nicht")
    basis = ziel.path.rstrip("/")
    url = basis + pfad + (("?" + abfrage.decode("latin-1")) if abfrage else "")
    hin = {k: v for k, v in koepfe if k.lower() in KOEPFE_HIN}
    verbindung = http.client.HTTPConnection(ziel.hostname, ziel.port or 80, timeout=WARTEZEIT)
    try:
        verbindung.request(methode, url, body=koerper or None, headers=hin)
        antwort = verbindung.getresponse()
        daten = antwort.read()
        zurueck = [(k, v) for k, v in antwort.getheaders() if k.lower() in KOEPFE_ZURUECK]
        return antwort.status, zurueck, daten
    except (OSError, http.client.HTTPException) as e:
        return _aus(m, type(e).__name__ if not str(e) else str(e))
    finally:
        verbindung.close()
