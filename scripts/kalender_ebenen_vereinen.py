#!/usr/bin/env python3
"""Ein Kalender: alles aus der Ebene „routinen" nach „termine".

Sasha, 07.10.2026: „wieso führt zentrale zwei kalender? ich brauche einen
einheitlichen". Termine und Routinen können längst in derselben Ebene
stehen; getrennt waren sie nur aus Gewohnheit. Mit EINER Ebene gibt es auch
nur EINEN Kalender, den vdirsyncer mit dem Google-Hauptkalender abgleicht.

  (ohne Schalter)  Probe: kopiert die Kalenderdaten in einen Wegwerf-Ordner,
                   zieht dort um und vergleicht. Ändert NICHTS Echtes.
  --ausfuehren     der echte Umzug — nur, wenn die Probe vorher bestand
                   (läuft sie hier nochmal mit). Vorher macht der Speicher
                   seinen Tages-Snapshot; die Dateien behalten ihre ID (UID),
                   ein Ebenenwechsel zählt nicht als Löschung.

Verglichen wird alles, was man sieht: jeder Tag von −400 bis +800 Tagen
(ohne das Feld „layer"), die Alarme, der Tages-Abdruck für die KI.
Exit 0 = gleich / erledigt, 1 = Abweichung oder Abbruch.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT / "core"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _sicht(kalender) -> dict:
    """Alles Sichtbare, ohne die Ebene — die soll sich ja ändern."""
    heute = date.today()
    tage = kalender.entries_in_range(heute - timedelta(days=400), heute + timedelta(days=800))
    ohne = {iso: sorted(json.dumps({k: v for k, v in e.items() if k != "layer"},
                                   sort_keys=True, ensure_ascii=False) for e in es)
            for iso, es in tage.items()}
    import re
    return {"tage": ohne,
            "alarme": sorted(a.get("text", "") for a in kalender.open_alarms()),
            # Das Ebenen-Etikett („[routinen] 18:00 Parkour") darf sich ändern —
            # genau das ist der Umzug. Alles andere im Abdruck muss gleich sein.
            "abdruck": re.sub(r"\[(routinen|termine)\] ", "[] ", kalender.imprint_for_prompt())}


def _vereinen(kalender) -> dict:
    """Unter dem Kalender-Lock umziehen. -> Zahlen."""
    with kalender._lock:
        data = kalender._load_raw()
        ebenen = data.get("layers", {})
        quelle = ebenen.get("routinen")
        if quelle is None:
            return {"routinen": 0, "termine": 0, "schon_einer": True}
        ziel = ebenen.setdefault("termine", {"label": "Termine", "entries": {}, "routines": []})
        r = list(quelle.get("routines") or [])
        e = quelle.get("entries") or {}
        ziel.setdefault("routines", []).extend(r)
        n_e = 0
        for iso, liste in e.items():
            ziel.setdefault("entries", {}).setdefault(iso, []).extend(liste)
            n_e += len(liste)
        del ebenen["routinen"]
        kalender._save_raw(data)
    # Der leere Ordner trüge die Ebene sonst wieder herein (Farbe/Name liegen
    # als Dateien darin). Nur weg, wenn wirklich keine Termin-Datei mehr drin ist.
    ordner = kalender.CAL_PATH.parent / "kalender" / "routinen"
    if ordner.is_dir() and not any(p.suffix == ".ics" for p in ordner.iterdir()):
        shutil.rmtree(ordner)
    return {"routinen": len(r), "termine": n_e, "schon_einer": False}


def _durchlauf(kalender) -> tuple:
    vorher = _sicht(kalender)
    zahlen = _vereinen(kalender)
    import kalender_ics
    kalender_ics.cache_leeren()
    nachher = _sicht(kalender)
    rest = list(kalender._load_raw().get("layers", {}).keys())
    return zahlen, vorher, nachher, rest


def _unterschiede(vorher, nachher) -> list:
    aus = []
    for teil in ("alarme", "abdruck"):
        if vorher[teil] != nachher[teil]:
            aus.append(teil)
    for iso in sorted(set(vorher["tage"]) | set(nachher["tage"])):
        if vorher["tage"].get(iso) != nachher["tage"].get(iso):
            aus.append("tag " + iso)
    return aus


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ausfuehren", action="store_true")
    ap.add_argument("--daten", help="data/-Ordner (Standard: der des Repos)")
    a = ap.parse_args(argv)

    import kalender
    import kalender_speicher
    if a.daten:
        kalender.CAL_PATH = Path(a.daten).expanduser().resolve() / "ai_calendar.json"
    if kalender_speicher.modus() != "ics":
        print("Abbruch: der Kalender läuft nicht auf .ics.")
        return 1
    echt_basis = kalender.CAL_PATH.parent

    # ── Probe an einer Kopie ────────────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="kalender-probe-") as tmp:
        tmp = Path(tmp)
        for name in ("kalender", "kalender_neben.json"):
            q = echt_basis / name
            if q.is_dir():
                shutil.copytree(q, tmp / name)
            elif q.exists():
                shutil.copy2(q, tmp / name)
        echt_pfad = kalender.CAL_PATH
        os.environ["ZENTRALE_KALENDER_GIT_SPIEGEL"] = "aus"
        kalender.CAL_PATH = tmp / "ai_calendar.json"
        try:
            zahlen, vorher, nachher, rest = _durchlauf(kalender)
        finally:
            kalender.CAL_PATH = echt_pfad
            os.environ.pop("ZENTRALE_KALENDER_GIT_SPIEGEL", None)
            import kalender_ics
            kalender_ics.cache_leeren()
        uebrig = sorted(p.name for p in (tmp / "kalender" / "routinen").glob("*.ics")) \
            if (tmp / "kalender" / "routinen").exists() else []
    diff = _unterschiede(vorher, nachher)
    print("Probe: %d Routinen, %d Einträge aus „routinen“ → „termine“; Ebenen danach: %s"
          % (zahlen["routinen"], zahlen["termine"], ", ".join(rest)))
    print("  Tage verglichen: %d, Abweichungen: %d, übrige .ics in routinen/: %d"
          % (len(vorher["tage"]), len(diff), len(uebrig)))
    for d in diff[:20]:
        print("   ≠", d)
    if zahlen["schon_einer"]:
        print("Nichts zu tun: es gibt nur noch eine Ebene.")
        return 0
    if diff or uebrig or "routinen" in rest:
        print("Probe NICHT bestanden — nichts Echtes angefasst.")
        return 1
    print("Probe bestanden.")
    if not a.ausfuehren:
        print("Echter Umzug: nochmal mit --ausfuehren.")
        return 0

    # ── Echt ───────────────────────────────────────────────────────────
    zahlen, vorher, nachher, rest = _durchlauf(kalender)
    diff = _unterschiede(vorher, nachher)
    print("Echt: %d Routinen, %d Einträge umgezogen; Ebenen jetzt: %s; Abweichungen: %d"
          % (zahlen["routinen"], zahlen["termine"], ", ".join(rest), len(diff)))
    for d in diff[:20]:
        print("   ≠", d)
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
