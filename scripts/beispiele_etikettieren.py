#!/usr/bin/env python3
# scripts/beispiele_etikettieren.py
#
# Aus den gesammelten Beispielen (core/klassifikator_beispiele.py) Etiketten
# für einen eigenen kleinen Klassifikator machen — Format für SetFit: eine
# Zeile je Satz, {"text", "label", "quelle"}.
#
#   venv/bin/python scripts/beispiele_etikettieren.py --aus etiketten.jsonl
#       Etiketten aus Wortliste und Selbstauskunft, kostet nichts.
#   venv/bin/python scripts/beispiele_etikettieren.py --aus e.jsonl --modell claude-haiku-4-5
#       zeigt nur, was ein Vor-Etikettieren per Cloud-Modell kosten würde.
#   … --modell claude-haiku-4-5 --wirklich
#       fragt das Modell je Satz (Kosten gebucht wie jeder Aufruf).
#
# Skizze (2026-10-10, memory/ki/ehrlichkeit_live.md, „Beispiele sammeln"):
# das Etikett ist eine VORLAGE — Sasha bzw. Claude prüfen Stichproben, bevor
# damit trainiert wird. Die Sätze sind privat: die Ausgabedatei nicht ins
# Repo, nicht in die Doku.
#
# Woher ein Etikett kommt (quelle):
#   wortliste   die Satzmuster haben die Art sicher erkannt
#   auskunft    die KI hat es selbst gesagt (Feld fragt_erlaubnis /
#               schiebt_auf → der letzte Satz). `erledigt` nennt Bereiche,
#               keinen Satz — daraus wird kein Etikett geraten.
#   modell      das Cloud-Modell (--modell … --wirklich)
#   (ohne)      sonst — Sätze ohne sicheres Etikett bleiben weg

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import klassifikator             # noqa: E402
import klassifikator_beispiele   # noqa: E402

# Token je Frage ans Modell, grob: Auftrag + Satz rein, ein Wort raus.
TOKEN_REIN, TOKEN_RAUS = 90, 3


def etiketten(beispiele: list) -> list:
    """Beispiele → [{text, label, quelle}] ohne Modell. Ein Satz einmal."""
    raus, gesehen = [], set()
    for b in beispiele:
        saetze = b.get("saetze") or []
        auskunft = b.get("auskunft") or {}
        for i, s in enumerate(saetze):
            text = str(s.get("satz") or "").strip()
            if not text or text in gesehen:
                continue
            label, quelle = None, None
            if s.get("sicher"):
                label, quelle = s.get("art"), "wortliste"
            elif i == len(saetze) - 1 and auskunft.get("fragt_erlaubnis"):
                label, quelle = "erlaubnisfrage", "auskunft"
            elif i == len(saetze) - 1 and auskunft.get("schiebt_auf"):
                label, quelle = "aufschub", "auskunft"
            if label:
                gesehen.add(text)
                raus.append({"text": text, "label": label, "quelle": quelle})
    return raus


def offene_saetze(beispiele: list, fertig: list) -> list:
    """Sätze ohne Etikett (für das Modell)."""
    schon = {e["text"] for e in fertig}
    raus = []
    for b in beispiele:
        for s in b.get("saetze") or []:
            t = str(s.get("satz") or "").strip()
            if t and t not in schon and t not in raus:
                raus.append(t)
    return raus


def kosten_schaetzen(modell: str, n_fragen: int) -> float:
    import prices
    return prices.euro(modell, input_tokens=TOKEN_REIN * n_fragen,
                       output_tokens=TOKEN_RAUS * n_fragen)


def vor_etikettieren(saetze: list, modell: str, fragen=None) -> list:
    """Je Satz die Arten nacheinander (Ja/Nein), erste Zusage gewinnt."""
    cloud = klassifikator.Cloud(modell=modell, fragen=fragen)
    raus = []
    for t in saetze:
        art = next((a for a in klassifikator.ARTEN[:-1] if cloud.entscheiden(t, a)), "sonst")
        raus.append({"text": t, "label": art, "quelle": "modell"})
    return raus


def schreiben(pfad: str, zeilen: list):
    with open(pfad, "w", encoding="utf-8") as f:
        for z in zeilen:
            f.write(json.dumps(z, ensure_ascii=False) + "\n")
    os.chmod(pfad, 0o600)


def main(argv=None, fragen=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ordner", help="Beispiele lesen von hier (Standard: Einstellung)")
    p.add_argument("--aus", required=True, help="Etiketten hierhin (jsonl)")
    p.add_argument("--modell", help="offene Sätze von diesem Modell vor-etikettieren lassen")
    p.add_argument("--wirklich", action="store_true", help="Modell wirklich fragen (kostet)")
    a = p.parse_args(argv)

    beispiele = klassifikator_beispiele.lesen(a.ordner)
    fertig = etiketten(beispiele)
    offen = offene_saetze(beispiele, fertig)
    print(f"{len(beispiele)} Beispiele · {len(fertig)} Sätze mit Etikett · {len(offen)} ohne")
    if a.modell and offen:
        # Höchstens eine Frage je Art (ohne „sonst") und Satz.
        n = len(offen) * (len(klassifikator.ARTEN) - 1)
        eur = kosten_schaetzen(a.modell, n)
        print(f"Vor-Etikettieren mit {a.modell}: bis zu {n} Fragen ≈ {eur:.3f} €")
        if not a.wirklich:
            print("Nichts gefragt — mit --wirklich ausführen.")
        else:
            fertig += vor_etikettieren(offen, a.modell, fragen=fragen)
    schreiben(a.aus, fertig)
    print(f"geschrieben: {a.aus} ({len(fertig)} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
