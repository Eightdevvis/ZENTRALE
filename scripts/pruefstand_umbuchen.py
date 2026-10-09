#!/usr/bin/env python3
"""
Prüfstand-Kosten aus Sashas Chat-Topf in den Prüfstand-Topf umbuchen.

Bis 2026-10-09 buchte der Prüfstand in data/ai_usage.json wie Sashas Chat —
seine Läufe rissen Sashas Monatsdeckel (8 €), sein Chat fiel auf qwen-plus
zurück. Seitdem bucht er in einen eigenen Topf (core/usage.py, Herkunft
„pruefstand"). Dieses Skript holt die ALTEN Prüfstand-Kosten nach.

Belege sind die Protokolle der Läufe (<ordner>/protokolle/*.log): jede
bezahlte Modell-Runde steht dort als Zeile „CLOUD ← <modell> … ≈0.0971€"
bzw. „PRÜFSTAND-RICHTER ← …". Gezählt wird jede Zeile einmal, auch wenn ein
Ordner kopiert wurde (vorher_haiku, *_neu_geprueft enthalten Kopien). Logs,
die schon in den eigenen Topf gebucht haben, tragen eine Marke
(pruefstand_teile.kind.TOPF_MARKE) und bleiben aus. Der Tag der Buchung ist
der Tag, an dem das Log zuletzt geschrieben wurde. Bereits umgebuchte
Zeilen merkt sich die Datei (Topf pruefstand, „umgebucht") — zweimal
ausführen bucht nichts doppelt.

    venv/bin/python scripts/pruefstand_umbuchen.py              # zeigt nur, was es täte
    venv/bin/python scripts/pruefstand_umbuchen.py --wirklich   # bucht um (Sicherung daneben)
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "core"))

from pruefstand_teile import umgebung  # noqa: E402
from pruefstand_teile.kind import TOPF_MARKE  # noqa: E402

BELEGE_STANDARD = [os.path.expanduser("~/.claude/jobs/938c900a/tmp/pruefstand"),
                   os.path.expanduser("~/.cache/zentrale/pruefstand")]

# Die Buchungs-Zeilen aus core/cloud.py (_log_usage, _gestoppt_buchen),
# core/cloud_openai.py und dem Richter (log="PRÜFSTAND-RICHTER").
ZEILE = re.compile(r"\b(CLOUD|PRÜFSTAND-RICHTER)\b[^\n]*? ← (\S+) [^\n]*?≈(\d+\.\d+)€")

TOPF = "pruefstand"


def belege_sammeln(wurzeln: list) -> list:
    """-> [{schluessel, tag, modell, euro, lauf}] — jede bezahlte Runde einmal."""
    gesehen = {}
    for wurzel in wurzeln:
        for ordner, _, dateien_ in os.walk(wurzel):
            if os.path.basename(ordner) != "protokolle":
                continue
            for name in sorted(dateien_):
                if not name.endswith(".log"):
                    continue
                pfad = os.path.join(ordner, name)
                try:
                    with open(pfad, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                    mtime = os.stat(pfad).st_mtime
                except OSError:
                    continue
                if TOPF_MARKE in text:
                    continue                      # schon im eigenen Topf gebucht
                je_text = Counter()
                for zeile in text.splitlines():
                    m = ZEILE.search(zeile)
                    if not m:
                        continue
                    zeile = zeile.strip()
                    je_text[zeile] += 1
                    # Dateiname + wievielte gleiche Zeile + Zeile: dieselbe
                    # Runde in einer Kopie des Ordners hat denselben Schlüssel.
                    roh = f"{name}\0{je_text[zeile]}\0{zeile}"
                    schluessel = hashlib.sha1(roh.encode("utf-8")).hexdigest()[:16]
                    alt = gesehen.get(schluessel)
                    if alt and alt["_mtime"] <= mtime:
                        continue
                    gesehen[schluessel] = {
                        "schluessel": schluessel, "_mtime": mtime,
                        "tag": date.fromtimestamp(mtime).isoformat(),
                        "modell": m.group(2), "euro": float(m.group(3)),
                        "lauf": os.path.relpath(os.path.dirname(ordner), wurzel)}
    return sorted(gesehen.values(), key=lambda b: (b["_mtime"], b["schluessel"]))


def _abziehen(topf: dict, schluessel: str, euro: float, calls: int, warnungen: list, wo: str):
    e = topf.get(schluessel)
    if not e:
        warnungen.append(f"{wo} {schluessel}: im Chat-Topf nicht vorhanden — dort nichts abgezogen")
        return
    # Die Log-Zeilen sind auf 4 Stellen gerundet; ein Rest unter einem
    # Zehntel-Cent ist Rundung, keine Warnung wert.
    if e.get("euro", 0.0) < euro - 0.001:
        warnungen.append(f"{wo} {schluessel}: nur {e.get('euro', 0.0):.4f} € statt "
                         f"{euro:.4f} € — auf 0 gesetzt")
    e["euro"] = round(max(0.0, e.get("euro", 0.0) - euro), 6)
    e["calls"] = max(0, int(e.get("calls", 0)) - calls)


def _dazu(topf: dict, schluessel: str, euro: float, calls: int):
    e = topf.setdefault(schluessel, {"euro": 0.0, "calls": 0})
    e["euro"] = round(e.get("euro", 0.0) + euro, 6)
    e["calls"] = int(e.get("calls", 0)) + calls


def umbuchen(d: dict, belege: list) -> tuple:
    """Bucht in der geladenen ai_usage.json (d, wird verändert) die Belege
    vom Chat-Topf in den Prüfstand-Topf. -> (neu umgebuchte Belege, Warnungen)."""
    import usage
    ziel = usage.topf(d, TOPF)
    schon = set(ziel.get("umgebucht") or [])
    neu = [b for b in belege if b["schluessel"] not in schon]
    warnungen = []
    gruppen = defaultdict(lambda: [0.0, 0])
    for b in neu:
        g = gruppen[(b["tag"], b["modell"])]
        g[0] += b["euro"]
        g[1] += 1
    for (tag, modell), (euro, calls) in sorted(gruppen.items()):
        for feld, schluessel in (("tage", tag), ("monate", tag[:7]), ("modelle", modell)):
            _abziehen(d.setdefault(feld, {}), schluessel, euro, calls, warnungen, feld)
            _dazu(ziel[feld], schluessel, euro, calls)
    ziel["umgebucht"] = sorted(schon | {b["schluessel"] for b in neu})
    return neu, warnungen


def _bericht(belege_neu: list, vorher: dict, nachher: dict) -> str:
    z = []
    je_lauf = defaultdict(lambda: [0.0, 0, set()])
    for b in belege_neu:
        g = je_lauf[b["lauf"]]
        g[0] += b["euro"]
        g[1] += 1
        g[2].add(b["tag"])
    z.append("Umzubuchen (je Lauf-Ordner, Kopien nur einmal gezählt):")
    for lauf, (euro, n, tage) in sorted(je_lauf.items()):
        z.append(f"  {lauf:<36} {euro:7.3f} €  {n:4d} Runden  am {', '.join(sorted(tage))}")
    summe = sum(b["euro"] for b in belege_neu)
    z.append(f"  {'zusammen':<36} {summe:7.3f} €  {len(belege_neu):4d} Runden")
    je_modell = Counter()
    for b in belege_neu:
        je_modell[b["modell"]] += b["euro"]
    z.append("Je Modell: " + ", ".join(f"{m} {e:.3f} €" for m, e in je_modell.most_common()))
    monate = sorted({b["tag"][:7] for b in belege_neu})
    for monat in monate:
        v = ((vorher.get("monate") or {}).get(monat) or {}).get("euro", 0.0)
        n = ((nachher.get("monate") or {}).get(monat) or {}).get("euro", 0.0)
        p = (((nachher.get("herkunft") or {}).get(TOPF) or {}).get("monate", {})
             .get(monat) or {}).get("euro", 0.0)
        z.append(f"Sashas Chat {monat}: {v:.2f} € → {n:.2f} €; Prüfstand-Topf {monat}: {p:.2f} €")
    return "\n".join(z)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wirklich", action="store_true",
                   help="wirklich umbuchen (sonst nur zeigen); legt vorher eine Sicherung an")
    p.add_argument("--datei", help="die Buchhaltung (Standard: data/ai_usage.json im Haupt-Checkout)")
    p.add_argument("--belege", action="append", default=[],
                   help="Ordner mit Prüfstand-Läufen (mehrfach; Standard: "
                        + ", ".join(BELEGE_STANDARD) + ")")
    a = p.parse_args()

    datei = a.datei or os.path.join(umgebung.daten_wurzel(ROOT), "data", "ai_usage.json")
    wurzeln = [w for w in (a.belege or BELEGE_STANDARD) if os.path.isdir(w)]
    if not os.path.exists(datei):
        sys.exit(f"Keine Buchhaltung unter {datei}")
    import copy
    import json
    import dateien
    with open(datei, encoding="utf-8") as f:
        vorher = json.load(f)
    d = copy.deepcopy(vorher)
    belege = belege_sammeln(wurzeln)
    neu, warnungen = umbuchen(d, belege)
    print(f"Buchhaltung: {datei}")
    print(f"Belege aus: {', '.join(wurzeln) or '—'}")
    if not neu:
        print("Nichts umzubuchen" + (" (alles schon erledigt)." if belege else "."))
        return 0
    print(_bericht(neu, vorher, d))
    for w in warnungen:
        print("  ⚠ " + w)
    if not a.wirklich:
        print("\nNur gezeigt, nichts geändert. Umbuchen mit --wirklich.")
        return 0
    sicherung = f"{datei}.vor-umbuchung-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(datei, sicherung)
    # Erst unmittelbar vor dem Schreiben neu laden: was die laufende ZENTRALE
    # seit dem Lesen oben gebucht hat, soll nicht verloren gehen.
    with open(datei, encoding="utf-8") as f:
        d = json.load(f)
    neu, _ = umbuchen(d, belege)
    dateien.json_schreiben(datei, d)
    print(f"\nUmgebucht: {sum(b['euro'] for b in neu):.3f} € in {len(neu)} Runden. "
          f"Sicherung: {sicherung}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
