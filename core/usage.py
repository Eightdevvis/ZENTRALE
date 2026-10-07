# core/usage.py
#
# Buchführung über das, was die Cloud-KI kostet. Pro Tag und pro Monat, in
# data/ai_usage.json.
#
# ── Wozu ───────────────────────────────────────────────────────────────
# Zwei Dinge, die ohne diese Datei nicht gehen:
#   1. „Was kostet mich das?" beantworten, ohne beim Anbieter nachzusehen.
#   2. Der Budget-Deckel — er braucht eine Zahl, gegen die er prüft.
#
# ── Warum nicht einfach ins Log ────────────────────────────────────────
# Ein Log ist weg, wenn der Prozess neu startet, und man kann nicht dagegen
# rechnen. Der Deckel muss einen Monat überdauern, also braucht es eine Datei.
#
# ── Form ───────────────────────────────────────────────────────────────
# Absichtlich klein und roh: Tages- und Monatssummen, keine Einzel-Calls. Ein
# Turn-für-Turn-Journal wäre ein zweites Transkript mit anderen Daten drin —
# und die eigentliche Frage ist „wie viel diesen Monat", nicht „welcher Turn".
#
#   {
#     "tage":   {"2026-08-15": {"euro": 0.42, "calls": 37}},
#     "monate": {"2026-08":    {"euro": 3.10, "calls": 291}},
#     "modelle": {"claude-sonnet-5": {"euro": 2.80, "calls": 240}}
#   }
#
# Alte Tage werden gekappt (KEEP_TAGE), sonst wächst die Datei ewig.

import json
import dateien
import os
from datetime import date
from threading import Lock

import prices

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# Ziel-Datei per Env umlenkbar. Das ist keine Bequemlichkeit, sondern eine
# Schutzmassnahme: die Testsuite fährt einen gefälschten API-Client, der ganz
# normal durch buchen() läuft — ein voller Testlauf hat so 345 erfundene
# claude-sonnet-5-Calls für 0,20 € in die echte Buchhaltung geschrieben.
# Damit ist nicht nur die Anzeige wertlos, sondern auch der Budget-Deckel:
# er würde gegen Geld rechnen, das nie jemand ausgegeben hat.
# Gesetzt wird das in tests/conftest.py.
_FILE = os.path.abspath(os.environ.get("ZENTRALE_USAGE_FILE") or
                        os.path.join(_DATA_DIR, 'ai_usage.json'))

KEEP_TAGE = 90     # Tagesdetails so lange behalten, Monatssummen bleiben

_lock = Lock()


def _leer() -> dict:
    return {"tage": {}, "monate": {}, "modelle": {}}


def _laden() -> dict:
    try:
        with open(_FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return _leer()
    for k in ("tage", "monate", "modelle"):
        d.setdefault(k, {})
    return d


def _schreiben(d: dict):
    dateien.json_schreiben(_FILE, d)


def _bump(topf: dict, schluessel: str, euro: float, calls: int = 1):
    e = topf.setdefault(schluessel, {"euro": 0.0, "calls": 0})
    e["euro"] = round(e["euro"] + euro, 6)
    e["calls"] += calls


# Modelle, deren Preis schon als unbekannt gemeldet wurde (einmal je Lauf).
_unbekannt_gemeldet = set()


def _unbekannten_preis_melden(model: str):
    """Ein Modell ohne Preiszeile (2026-10-07: /modell zeigt jetzt alles,
    was der Anbieter hat) wird vorsichtig geschätzt, nicht mit 0 € — und
    das soll man im Log sehen, damit jemand die Zeile in prices.py nachträgt."""
    if not model or prices.bekannt(model) or model in _unbekannt_gemeldet:
        return
    _unbekannt_gemeldet.add(model)
    p = prices.fuer(model)
    zeile = (f"PREIS ? {model}: nicht in der Preistabelle — gerechnet mit "
             f"{p['in']:g} $ / {p['out']:g} $ je Mio. Token (vorsichtig)")
    try:
        import state
        state.push_log(zeile)
    except Exception:
        print(f"[usage] {zeile}")


def buchen(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
           cache_read: int = 0, cache_write: int = 0,
           geschaetzt: bool = False) -> float:
    """
    Einen Call verbuchen. Gibt die geschätzten Kosten dieses Calls in Euro
    zurück (damit der Aufrufer sie gleich loggen kann).

    geschaetzt=True: die Token-Zahlen hat nicht der Anbieter gemeldet,
    sondern wir aus der Textlänge geschätzt (gestoppte Antwort bei einem
    OpenAI-kompatiblen Anbieter, 2026-10-07). Zählt ganz normal mit — der
    Budget-Deckel soll sie sehen — und zusätzlich im Topf „geschaetzt" pro
    Monat, damit erkennbar bleibt, wie viel davon Schätzung ist.

    Schluckt Fehler: eine kaputte Buchhaltung darf niemals ein Gespräch
    abbrechen. Im schlimmsten Fall stimmt die Statistik nicht.
    """
    _unbekannten_preis_melden(model)
    try:
        eur = prices.euro(model, input_tokens=input_tokens,
                          output_tokens=output_tokens,
                          cache_read=cache_read, cache_write=cache_write)
    except Exception:
        return 0.0

    heute = date.today().isoformat()
    monat = heute[:7]
    try:
        with _lock:
            d = _laden()
            _bump(d["tage"], heute, eur)
            _bump(d["monate"], monat, eur)
            _bump(d["modelle"], model or "unbekannt", eur)
            if geschaetzt:
                _bump(d.setdefault("geschaetzt", {}), monat, eur)
            # Tagesdetails kappen; Monate bleiben (die sind winzig).
            tage = d["tage"]
            if len(tage) > KEEP_TAGE:
                for alt in sorted(tage)[:-KEEP_TAGE]:
                    del tage[alt]
            _schreiben(d)
    except Exception:
        pass
    return eur


def _summe(topf: str, schluessel: str) -> float:
    return float((_laden().get(topf, {}).get(schluessel) or {}).get("euro", 0.0))


def heute_euro() -> float:
    return _summe("tage", date.today().isoformat())


def monat_euro() -> float:
    return _summe("monate", date.today().isoformat()[:7])


def uebersicht() -> dict:
    """Kompakt für Anzeige: heute, dieser Monat, und was welches Modell kostet."""
    d = _laden()
    heute = date.today().isoformat()
    return {
        "heute":  round(float((d["tage"].get(heute) or {}).get("euro", 0.0)), 4),
        "monat":  round(float((d["monate"].get(heute[:7]) or {}).get("euro", 0.0)), 4),
        "calls_heute": int((d["tage"].get(heute) or {}).get("calls", 0)),
        "modelle": {m: round(v.get("euro", 0.0), 4)
                    for m, v in sorted(d["modelle"].items(),
                                       key=lambda kv: -kv[1].get("euro", 0.0))},
    }


def zuruecksetzen():
    """Nur für Tests und bewusstes Aufräumen."""
    with _lock:
        _schreiben(_leer())
