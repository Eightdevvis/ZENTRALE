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
#     "modelle": {"claude-sonnet-5": {"euro": 2.80, "calls": 240}},
#     "herkunft": {"pruefstand": {"tage": {…}, "monate": {…}, "modelle": {…}}}
#   }
#
# Alte Tage werden gekappt (KEEP_TAGE), sonst wächst die Datei ewig.
#
# ── Herkunft (2026-10-09) ──────────────────────────────────────────────
# Oben stehen Sashas Chat-Kosten — so wie seit jeher, alte Einträge sind
# damit von selbst „chat". Was nicht aus seinem Chat kommt (der Prüfstand),
# bucht in einen eigenen Topf unter "herkunft". Warum: Prüfstand-Läufe
# fraßen seinen Monatsdeckel, sein Chat fiel auf qwen-plus zurück, und er
# will die Test-Kosten nicht gemischt mit seinen sehen („ich will NICH
# sehen was du zum testen nutzt"). Deckel, Rückfall und Anzeige lesen nur
# oben. Gesetzt wird die Herkunft über einen Kontext, nicht über Parameter
# quer durch alle Wege: herkunft_setzen() für einen ganzen Prozess (der
# Prüfstand), herkunft_block() für einen Block.

import contextlib
import contextvars
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

CHAT = "chat"
PRUEFSTAND = "pruefstand"

# Prozessweit, weil der Chat-Weg Threads startet, die einen ContextVar nicht
# erben — ein Prüfstand-Aufruf darf nie aus Versehen in Sashas Topf landen.
_herkunft_prozess = CHAT
_herkunft_var = contextvars.ContextVar("usage_herkunft", default=None)


def herkunft_setzen(name: str) -> str:
    """Herkunft aller folgenden Buchungen dieses Prozesses. -> die alte
    (zum Zurückstellen)."""
    global _herkunft_prozess
    alt, _herkunft_prozess = _herkunft_prozess, (name or CHAT)
    return alt


@contextlib.contextmanager
def herkunft_block(name: str):
    """Buchungen in diesem Block (dieser Thread/Task) unter `name`."""
    marke = _herkunft_var.set(name or CHAT)
    try:
        yield
    finally:
        _herkunft_var.reset(marke)


def aktuelle_herkunft() -> str:
    return _herkunft_var.get() or _herkunft_prozess


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


def topf(d: dict, name: str = CHAT) -> dict:
    """Der Topf einer Herkunft in der geladenen Datei (chat = oben, die
    anderen unter "herkunft"); legt ihn an, wenn er fehlt."""
    if (name or CHAT) == CHAT:
        return d
    t = d.setdefault("herkunft", {}).setdefault(name, {})
    for k in ("tage", "monate", "modelle"):
        t.setdefault(k, {})
    return t


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


# Zeichen je Token, wenn der Anbieter nichts gezählt hat (gestoppte
# Antworten). 3,5 liegt für deutschen Text und JSON eher zu niedrig (= mehr
# Token, teurer) — gewollt vorsichtig. Eine Regel für beide Wege
# (cloud_openai, cloud), seit 2026-10-08 hier.
ZEICHEN_JE_TOKEN = 3.5


def tokens_geschaetzt(zeichen: int) -> int:
    """Token aus der Zahl der Zeichen (ZEICHEN_JE_TOKEN)."""
    return int(max(0, zeichen or 0) / ZEICHEN_JE_TOKEN)


def buchen(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
           cache_read: int = 0, cache_write: int = 0,
           geschaetzt: bool = False, output_geschaetzt: int = 0,
           faktor: float = 1.0) -> float:
    """
    Einen Call verbuchen. Gibt die geschätzten Kosten dieses Calls in Euro
    zurück (damit der Aufrufer sie gleich loggen kann).

    geschaetzt=True: die Token-Zahlen hat nicht der Anbieter gemeldet,
    sondern wir aus der Textlänge geschätzt (gestoppte Antwort bei einem
    OpenAI-kompatiblen Anbieter, 2026-10-07). Zählt ganz normal mit — der
    Budget-Deckel soll sie sehen — und zusätzlich im Topf „geschaetzt" pro
    Monat, damit erkennbar bleibt, wie viel davon Schätzung ist.

    output_geschaetzt=N (2026-10-08): nur N der output_tokens sind geschätzt
    (gestoppte Claude-Antwort: Eingabe und Cache hat Anthropic gemeldet, die
    Ausgabe bis zum Stopp nicht). In den Topf „geschaetzt" geht dann nur der
    Preis dieser N Token.

    faktor (2026-10-09): Preis-Faktor des Wegs — 0.5 für die Message Batches
    API von Anthropic (halber Preis; der Prüfstand-Richter mit --richter-batch).

    Schluckt Fehler: eine kaputte Buchhaltung darf niemals ein Gespräch
    abbrechen. Im schlimmsten Fall stimmt die Statistik nicht.
    """
    _unbekannten_preis_melden(model)
    try:
        eur = prices.euro(model, input_tokens=input_tokens,
                          output_tokens=output_tokens,
                          cache_read=cache_read, cache_write=cache_write)
        teil_eur = (prices.euro(model, output_tokens=output_geschaetzt)
                    if output_geschaetzt > 0 and not geschaetzt else 0.0)
        eur, teil_eur = eur * float(faktor), teil_eur * float(faktor)
    except Exception:
        return 0.0

    heute = date.today().isoformat()
    monat = heute[:7]
    try:
        with _lock:
            d = _laden()
            t = topf(d, aktuelle_herkunft())
            _bump(t["tage"], heute, eur)
            _bump(t["monate"], monat, eur)
            _bump(t["modelle"], model or "unbekannt", eur)
            if geschaetzt or output_geschaetzt > 0:
                _bump(t.setdefault("geschaetzt", {}), monat,
                      eur if geschaetzt else min(eur, teil_eur))
            # Tagesdetails kappen; Monate bleiben (die sind winzig).
            tage = t["tage"]
            if len(tage) > KEEP_TAGE:
                for alt in sorted(tage)[:-KEEP_TAGE]:
                    del tage[alt]
            _schreiben(d)
    except Exception:
        pass
    return eur


def _summe(feld: str, schluessel: str, herkunft: str = CHAT) -> float:
    t = topf(_laden(), herkunft)
    return float((t.get(feld, {}).get(schluessel) or {}).get("euro", 0.0))


def heute_euro(herkunft: str = CHAT) -> float:
    return _summe("tage", date.today().isoformat(), herkunft)


def monat_euro(herkunft: str = CHAT) -> float:
    """Die Summe des Monats — Standard: nur Sashas Chat (der Deckel rechnet
    damit, ai_backends.budget_lage)."""
    return _summe("monate", date.today().isoformat()[:7], herkunft)


def uebersicht(herkunft: str = CHAT) -> dict:
    """Kompakt für Anzeige: heute, dieser Monat, und was welches Modell kostet.
    Standard nur Chat — der Prüfstand zeigt seinen Topf im eigenen Bericht."""
    d = topf(_laden(), herkunft)
    heute = date.today().isoformat()
    return {
        "heute":  round(float((d["tage"].get(heute) or {}).get("euro", 0.0)), 4),
        "monat":  round(float((d["monate"].get(heute[:7]) or {}).get("euro", 0.0)), 4),
        "calls_heute": int((d["tage"].get(heute) or {}).get("calls", 0)),
        # Davon geschätzt (gestoppte Antworten ohne Zählung des Anbieters) —
        # für die Kosten-Seite der TUI, 2026-10-07.
        "geschaetzt_monat": round(float(((d.get("geschaetzt") or {}).get(heute[:7]) or {})
                                        .get("euro", 0.0)), 4),
        "modelle": {m: round(v.get("euro", 0.0), 4)
                    for m, v in sorted(d["modelle"].items(),
                                       key=lambda kv: -kv[1].get("euro", 0.0))},
    }


def zuruecksetzen():
    """Nur für Tests und bewusstes Aufräumen."""
    with _lock:
        _schreiben(_leer())
