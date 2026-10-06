#!/usr/bin/env python3
"""Testmüll im Transkript finden — und nur auf ausdrücklichen Wunsch entfernen.

Hintergrund (2026-10-06): Die Konsolidierungs-Tests schrieben seit August bei
jedem Lauf ihre Probesätze in das ECHTE Transkript (data/ai_transcripts/),
weil der Pfad fest verdrahtet war. Der Fehler ist behoben (tests/conftest.py
lenkt um, tests/test_keine_seiteneffekte.py wacht darüber). Was schon drin
steht, bleibt, bis Sasha entscheidet.

Woran eine Zeile als Testmüll erkannt wird: Frage UND Antwort stehen beide
wörtlich als Text in den Testdateien (tests/*.py). Ein echter Satz von
Sasha, der zufällig einem Testsatz gleicht UND dieselbe Antwort bekam, ist
damit praktisch ausgeschlossen — und selbst dann bleibt die Sicherung.

Ohne Argument: nur anzeigen, nichts schreiben.
Mit --entfernen: pro Datei erst eine Sicherung <datei>.vor-testputz-<datum>
anlegen, dann die Testzeilen herausnehmen. Die Zeilen-IDs der übrigen
Einträge bleiben, wie sie sind (sie sind Quell-IDs im Graphen).
"""

import argparse
import ast
import datetime
import glob
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_texte():
    texte = set()
    for pfad in glob.glob(os.path.join(ROOT, "tests", "*.py")):
        try:
            baum = ast.parse(open(pfad, encoding="utf-8").read())
        except SyntaxError:
            continue
        for k in ast.walk(baum):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                texte.add(k.value)
    return texte


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--entfernen", action="store_true",
                    help="Testzeilen wirklich herausnehmen (mit Sicherung)")
    ap.add_argument("--ordner", default=os.path.join(ROOT, "data", "ai_transcripts"))
    args = ap.parse_args()

    texte = test_texte()
    gesamt = muell_gesamt = 0
    for pfad in sorted(glob.glob(os.path.join(args.ordner, "*.jsonl"))):
        behalten, muell = [], []
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                try:
                    e = json.loads(zeile)
                except ValueError:
                    behalten.append(zeile)
                    continue
                if e.get("user") in texte and e.get("ai") in texte:
                    muell.append(e)
                else:
                    behalten.append(zeile)
        gesamt += len(behalten) + len(muell)
        muell_gesamt += len(muell)
        print(f"{os.path.basename(pfad)}: {len(behalten) + len(muell)} Zeilen, "
              f"Testmüll {len(muell)}, echt {len(behalten)}")
        for e in muell[:3]:
            print(f"    z.B. {e.get('id')}: {e.get('user')!r} → {e.get('ai')!r}")
        if args.entfernen and muell:
            sicherung = f"{pfad}.vor-testputz-{datetime.date.today().isoformat()}"
            shutil.copy2(pfad, sicherung)
            tmp = pfad + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(behalten)
            os.replace(tmp, pfad)
            print(f"    → entfernt, Sicherung: {os.path.basename(sicherung)}")
    print(f"\nInsgesamt {gesamt} Zeilen, davon Testmüll {muell_gesamt}.")
    if not args.entfernen and muell_gesamt:
        print("Nichts geändert. Mit --entfernen werden die Testzeilen "
              "herausgenommen (vorher Sicherung je Datei).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
