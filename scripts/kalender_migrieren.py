#!/usr/bin/env python3
"""Kalender-Umzug: data/ai_calendar.json -> .ics (data/kalender/).

Drei Modi (Bedeutung und Reihenfolge: memory/werkzeuge/kalender_ics_bauplan.md):

  --pruefen      (Standard) ändert NICHTS an den echten Daten. Schreibt die
                 alte JSON in einen Wegwerf-Ordner als .ics, liest sie durch
                 den neuen Speicher zurück und vergleicht alles: das ganze
                 Daten-Dict, alle öffentlichen Lesefunktionen über ±2 Jahre,
                 das Feld-Inventar. Gibt Zahlen und jede Abweichung aus.
  --ausfuehren   der echte Umzug, nur nach bestandener Prüfung. Das Backend
                 vorher anhalten (es liest die Einstellung nur beim Start).
  --zurueck      der Rückweg: aus dem .ics-Ordner wieder eine JSON.

Exit-Code: 0 = alles gleich / erledigt, 1 = Abweichung oder Abbruch.
"""

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CORE = os.path.join(_ROOT, "core")
for _p in (_CORE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kalender_migration as mig  # noqa: E402


def _bericht_drucken(b: dict) -> None:
    z = b["zahlen"]
    print("Kalender-Umzug — Prüfung")
    print(f"  Ebenen {z['ebenen']}, Einmal-Termine {z['termine']}, Spannen "
          f"{z['spannen']} (davon mit Zeiten pro Tag {z['spannen_mit_zeiten']}), "
          f"Routinen {z['routinen']}, Pausen {z['pausen']}, erlebt {z['erlebt']} "
          f"(-> Archiv)")
    print(f"  .ics-Dateien geschrieben: {b['dateien']}, nicht als .ics "
          f"abbildbar (roh in Nebendaten): {b['nicht_abbildbar']}")
    print(f"  Routinen-Anker für Google: {b['anker']}")
    print(f"  Verglichene Aufrufe der öffentlichen Funktionen: {b['aufrufe']}")
    print("  Feld-Inventar (Feld -> wohin, Anzahl):")
    for feld, ziele in sorted(b["inventar"]["wohin"].items()):
        z = ", ".join(f"{ziel} {n}" for ziel, n in sorted(ziele.items()))
        print(f"    {feld:32s} {z}")
    print(f"  erlebt exakt im Archiv: {'ja' if b['inventar']['erlebt_im_archiv'] else 'NEIN'}")
    if b["gleich"]:
        print("ERGEBNIS: alles gleich — nichts geht verloren.")
    else:
        print(f"ERGEBNIS: {len(b['abweichungen'])} Abweichung(en) — KEIN Umzug:")
        for a in b["abweichungen"][:50]:
            print(f"  - {a}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    modus = ap.add_mutually_exclusive_group()
    modus.add_argument("--pruefen", action="store_true", help="nur prüfen (Standard)")
    modus.add_argument("--ausfuehren", action="store_true", help="wirklich umziehen")
    modus.add_argument("--zurueck", action="store_true", help="Rückweg in die JSON")
    ap.add_argument("--json", default=os.path.join(_ROOT, "data", "ai_calendar.json"),
                    help="Pfad der alten Kalender-JSON (Standard: data/ai_calendar.json)")
    ap.add_argument("--arbeitsordner", default=None,
                    help="Prüfung in diesen Ordner schreiben und liegen lassen "
                         "(Standard: Wegwerf-Ordner, danach gelöscht)")
    ap.add_argument("--jahre", type=int, default=2, help="Vergleichsfenster ± Jahre")
    ap.add_argument("--json-bericht", action="store_true",
                    help="Bericht zusätzlich als JSON ausgeben")
    a = ap.parse_args(argv)

    try:
        if a.zurueck:
            r = mig.zurueck(a.json)
            print(f"Rückweg erledigt: {r['geschrieben']} geschrieben, Einstellung "
                  f"kalender_speicher=json. Backend neu starten.")
            return 0
        if a.ausfuehren:
            b = mig.ausfuehren(a.json)
            _bericht_drucken(b)
            print(f"UMZUG erledigt. Alte Datei umbenannt: {b['umbenannt']}")
            print("Einstellung kalender_speicher=ics gesetzt. Backend neu starten.")
            return 0
        b = mig.pruefen(a.json, arbeits_dir=a.arbeitsordner, jahre=a.jahre)
        _bericht_drucken(b)
        if a.json_bericht:
            print(json.dumps(b, ensure_ascii=False, indent=1, default=str))
        return 0 if b["gleich"] else 1
    except mig.MigrationAbgebrochen as ex:
        print(f"ABGEBROCHEN: {ex}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
