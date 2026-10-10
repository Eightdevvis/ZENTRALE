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
    """-> [(antwort, protokoll, bekannt_text, frueher, nutzer)] je Antwort der KI
    (nutzer: Sashas Nachricht davor — für „frag nicht, tu" und „Aufschub")."""
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
        bisher, frueher, nutzer = [], [], ""
        for e in zeilen:
            if e.get("art") != "nachricht":
                continue
            if e.get("rolle") == "assistant":
                prot = [_schritt(w) for w in e.get("werkzeuge") or []]
                yield e.get("text") or "", prot, "\n".join(bisher), list(frueher), nutzer
                frueher.extend(prot)
            else:
                nutzer = e.get("text") or ""
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
                           list(frueher), z.get("sagt") or "")
                frueher.extend(prot)
                bisher.append(antwort)


def messen(zuege, zeigen=False, name=""):
    n = taten = taten_offen = zusagen = kenn = kenn_offen = nicht_da = nicht_da_offen = 0
    fragen = fragen_befund = aufschub = aufschub_befund = 0
    for antwort, prot, bekannt, frueher, nutzer in zuege:
        n += 1
        # „Sicheres sofort" (2026-10-10): Aufschub-Sätze, und wie viele der
        # Prüfer korrigieren würde (Sasha hat beauftragt, nichts Passendes lief).
        for a in erkennen.aufschuebe(antwort):
            aufschub += 1
            if zeigen:
                print(f"  AUFSCHUB {a.aktion} | {a.satz} || Sasha: "
                      f"{' '.join(nutzer.split())[:120]}")
        b_auf = ehrlichkeit.aufschub_befund(antwort, prot, nutzer)
        aufschub_befund += b_auf is not None
        if zeigen and b_auf:
            print(f"  AUFSCHUB → KORREKTUR | {b_auf['satz']}")
        # „Frag nicht, tu" (2026-10-10): jede Erlaubnis-Frage am Ende, und
        # wie viele davon der Prüfer korrigieren würde (Sasha wollte es,
        # kein passendes Werkzeug lief).
        frage = erkennen.erlaubnis_frage(antwort)
        if frage:
            fragen += 1
            befund = ehrlichkeit.erlaubnis_befund(antwort, prot, nutzer)
            fragen_befund += befund is not None
            if zeigen:
                print(f"  FRAGE {'KORREKTUR' if befund else 'ruhig    '} {frage.aktion} | "
                      f"{frage.satz} || Sasha: {' '.join(nutzer.split())[:120]}")
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
        # „nicht da" (2026-10-09): Sätze über fehlende Dateien, und wie viele
        # davon ohne vollständige Suche im selben Zug stehen.
        for satz in erkennen.nicht_da(antwort):
            nicht_da += 1
            ok = ehrlichkeit.suche_belegt(prot)
            nicht_da_offen += not ok
            if zeigen:
                print(f"  NICHT-DA {'belegt  ' if ok else 'UNBELEGT'} | {satz}")
        b = ehrlichkeit.befunde(antwort, prot, bekannt_text=bekannt, frueher=frueher)
        kenn += len(erkennen.kennungen(antwort))
        kenn_offen += sum(1 for x in b if x["art"] == "kennung")
        if zeigen:
            for x in b:
                if x["art"] == "kennung":
                    print(f"  KENNUNG unbekannt {x['kennung']}")
    print(f"{name}: {n} Antworten · Erledigt-Sätze {taten} (davon ohne Beleg {taten_offen}) · "
          f"Zusagen {zusagen} · Kennungen {kenn} (unbekannt {kenn_offen}) · "
          f"Nicht-da-Sätze {nicht_da} (ohne vollständige Suche {nicht_da_offen}) · "
          f"Erlaubnis-Fragen {fragen} (Korrektur {fragen_befund}) · "
          f"Aufschübe {aufschub} (Korrektur {aufschub_befund})")


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
