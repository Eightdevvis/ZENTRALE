#!/usr/bin/env python3
# scripts/ehrlichkeit_messen.py
#
# Die Live-Prüfer (core/ehrlichkeit.py) über schon gespeicherte Züge laufen
# lassen — NUR lesend, kostet nichts. Wozu: bevor ein Prüfer Korrekturrunden
# auslöst, zählen, wie oft er anschlägt und wie oft davon zu Unrecht
# (memory/ki/ehrlichkeit_live.md, „Falschtreffer").
#
#   venv/bin/python scripts/ehrlichkeit_messen.py                 # nur Zahlen
#   venv/bin/python scripts/ehrlichkeit_messen.py --zeigen        # Treffer-Sätze
#   venv/bin/python scripts/ehrlichkeit_messen.py --pruefstand ~/.claude/jobs/…/pruefstand
#
# --zeigen druckt die erkannten Sätze ins Terminal, zum selbst Beurteilen.
# Es schreibt nichts weg: Gesprächsinhalte sind privat und gehören in keine
# Doku und keinen Test — dort stehen nur die Zahlen.
#
# Verdeckte Prüfstand-Fälle (verdeckt: true) werden übersprungen: sie sind
# die zurückgehaltene Testmenge (memory/ki/pruefstand.md).

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import ehrlichkeit                       # noqa: E402
import ehrlichkeit_erkennen as erkennen  # noqa: E402
import werkzeug_befund                   # noqa: E402


def _schritt(w):
    text = str(w.get("ergebnis") or w.get("text") or "")
    st = w.get("status")
    if not st:
        st = ehrlichkeit.status_aus(text, bool(w.get("fehler"))) if text.startswith("[ergebnis") \
            else ("fehlgeschlagen" if w.get("fehler") else werkzeug_befund.status_von(text))
    return ehrlichkeit.Schritt(w.get("name") or "", w.get("args") or {}, st, text)


def zuege_gespraeche(ordner):
    """-> [(antwort, protokoll, bekannt_text, frueher)] je Antwort der KI."""
    for kopf in sorted(glob.glob(os.path.join(ordner, "*", "kopf.json"))):
        zeilen = []
        for p in glob.glob(os.path.join(os.path.dirname(kopf), "*.jsonl")):
            with open(p, encoding="utf-8") as f:
                for z in f:
                    try:
                        zeilen.append(json.loads(z))
                    except ValueError:
                        pass
        zeilen.sort(key=lambda e: e.get("ts") or "")
        bisher, frueher = [], []
        for e in zeilen:
            if e.get("art") != "nachricht":
                continue
            if e.get("rolle") == "assistant":
                prot = [_schritt(w) for w in e.get("werkzeuge") or []]
                yield e.get("text") or "", prot, "\n".join(bisher), list(frueher)
                frueher.extend(prot)
            bisher.append(e.get("text") or "")


def zuege_pruefstand(ordner):
    gesehen = set()
    for p in sorted(glob.glob(os.path.join(ordner, "**", "ergebnis.json"), recursive=True)):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for fall in d.get("faelle") or []:
            if fall.get("verdeckt"):
                continue
            bisher, frueher = [], []
            for z in fall.get("zuege") or []:
                bisher.append(z.get("sagt") or "")
                antwort = z.get("antwort") or ""
                prot = [_schritt(w) for w in z.get("werkzeuge") or []]
                schluessel = (fall.get("id"), antwort)
                if antwort and schluessel not in gesehen:
                    gesehen.add(schluessel)
                    yield (antwort, prot, "\n".join(bisher + [z.get("kontext") or ""]),
                           list(frueher))
                frueher.extend(prot)
                bisher.append(antwort)


def messen(zuege, zeigen=False, name=""):
    n = taten = taten_offen = zusagen = kenn = kenn_offen = 0
    for antwort, prot, bekannt, frueher in zuege:
        n += 1
        for t in erkennen.taten(antwort):
            taten += 1
            ok = ehrlichkeit.tat_belegt(t, prot, frueher)
            taten_offen += not ok
            if zeigen:
                print(f"  TAT {'belegt  ' if ok else 'UNBELEGT'} {sorted(t.bereiche)} | {t.satz}")
        for z in erkennen.versprechen(antwort):
            zusagen += 1
            if zeigen:
                eingeloest = ehrlichkeit._zusage_belegt(z.bereiche, prot, z.schreibend)
                print(f"  ZUSAGE {'(gleich eingelöst)' if eingeloest else ''} "
                      f"{sorted(z.bereiche)} | {z.satz}")
        b = ehrlichkeit.befunde(antwort, prot, bekannt_text=bekannt, frueher=frueher)
        kenn += len(erkennen.kennungen(antwort))
        kenn_offen += sum(1 for x in b if x["art"] == "kennung")
        if zeigen:
            for x in b:
                if x["art"] == "kennung":
                    print(f"  KENNUNG unbekannt {x['kennung']}")
    print(f"{name}: {n} Antworten · Erledigt-Sätze {taten} (davon ohne Beleg {taten_offen}) · "
          f"Zusagen {zusagen} · Kennungen {kenn} (unbekannt {kenn_offen})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gespraeche", default=os.path.join(ROOT, "data", "gespraeche"))
    ap.add_argument("--pruefstand", default=None,
                    help="Ordner mit Prüfstand-Durchgängen (ergebnis.json)")
    ap.add_argument("--zeigen", action="store_true",
                    help="erkannte Sätze ins Terminal (nur zum Beurteilen)")
    a = ap.parse_args()
    if os.path.isdir(a.gespraeche):
        messen(zuege_gespraeche(a.gespraeche), a.zeigen, "Gespräche")
    if a.pruefstand and os.path.isdir(a.pruefstand):
        messen(zuege_pruefstand(a.pruefstand), a.zeigen, "Prüfstand")


if __name__ == "__main__":
    main()
