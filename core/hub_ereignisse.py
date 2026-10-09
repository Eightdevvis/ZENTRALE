# core/hub_ereignisse.py
#
# Der Hub schickt Ereignisse an Apps, die sie abonniert haben (seit 2026-10-09).
#
# Vorher rief brain.py bei „jemand ist im Raum" direkt den Tutor auf
# (tutor_port.presence_ping) — ZENTRALE hatte dafür den Code des Tutors
# importiert. Jetzt sagt eine App in ihrer app.toml, welche Ereignisse sie will
# (Recht „ereignis:anwesenheit"), und bekommt sie als
#   POST <adresse><ziel>   {"name": "anwesenheit", "daten": {...}}
# (ziel aus [ereignisse], Standard /hub/ereignis).
#
# Im Hintergrund und mit kurzer Wartezeit: ein Sensor darf nie auf eine App
# warten. Ist sie aus oder nicht erreichbar, wird das geloggt und vergessen —
# Ereignisse sind Hinweise, kein Auftrag.

import json
import threading
import urllib.request

import apps

WARTEZEIT = 2.0


def _ziel_url(m: dict) -> str:
    ziel = ((m.get("ereignisse") or {}).get("ziel")) or "/hub/ereignis"
    return str(m.get("adresse") or "").rstrip("/") + ziel


def _zustellen(m: dict, name: str, daten: dict) -> bool:
    url = _ziel_url(m)
    try:
        req = urllib.request.Request(
            url, data=json.dumps({"name": name, "daten": daten}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=WARTEZEIT) as r:
            r.read()
        return True
    except Exception as e:
        print(f"[hub] Ereignis '{name}' an {m.get('name')} nicht zugestellt "
              f"({url}): {e}", flush=True)
        return False


def senden(name: str, daten: dict = None, *, warten: bool = False) -> int:
    """Ereignis an alle Abonnenten. Gibt die Zahl der Abonnenten zurück.
    warten=True (Tests): zustellen, bevor die Funktion zurückkehrt."""
    ziele = apps.abonnenten(name)
    for m in ziele:
        if warten:
            _zustellen(m, name, daten or {})
        else:
            threading.Thread(target=_zustellen, args=(m, name, daten or {}),
                             daemon=True).start()
    return len(ziele)
