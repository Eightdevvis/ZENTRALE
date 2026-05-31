#!/usr/bin/env python3
"""
graph_cleanup.py – One-shot Cleanup für data/ai_graph.json.

Hintergrund: Phase G hat den Graph-Extraktor live laufen lassen ohne
ausreichende Sanity. Resultat: halluzinierte Verben ("wohlbehalten",
"kennet", "aktuelles-Datum"), Subjekt-Vertauschung ("KI arbeitet-an
Sasha"), Datum-als-Subjekt ("2026-05-31 zustand Sasha") und Tippfehler-
Duplikate ("kennt"/"kennet"/"kennengelernt" parallel). Der laufende
Code wurde mit einer Whitelist + Sanity-Filter nachgezogen
(consolidation._sanitize_extracted) - dieses Script bringt den
*bestehenden* Datenbestand auf denselben Stand.

Was das Script tut:
  1. Lädt data/ai_graph.json.
  2. Wendet die produktive Sanity-Funktion auf alle Edges an
     (importiert direkt aus consolidation.py - DRY).
  3. Dedup-Pass: Edges mit gleichem (from, rel, to) werden zusammen-
     geführt, Weights summiert.
  4. Verwaiste Nodes (keine Edges nach Cleanup): bleiben drin, weil
     sie Embeddings tragen die als Entry-Points wieder relevant
     werden können. Lieber zu viel als Sasha-Erinnerungen löschen.
  5. Dry-Run by default. Mit --apply: Backup nach
     ai_graph.json.bak.<timestamp> + Overwrite der Live-Datei.

Aufruf:
  python3 scripts/graph_cleanup.py             # nur Analyse
  python3 scripts/graph_cleanup.py --apply     # tatsächlich aufräumen
  python3 scripts/graph_cleanup.py --verbose   # alle Drops einzeln
"""

import argparse
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

# Wir importieren die LIVE-Sanity-Funktion, statt sie zu kopieren -
# damit driften Cleanup-Script und Produktiv-Code nie auseinander.
import consolidation  # noqa: E402

GRAPH_PATH = ROOT / "data" / "ai_graph.json"


def main():
    ap = argparse.ArgumentParser(description="ZENTRALE Graph Cleanup")
    ap.add_argument("--apply", action="store_true",
                    help="Tatsächlich schreiben (default: dry-run)")
    ap.add_argument("--verbose", action="store_true",
                    help="Jeden gedroppten Edge einzeln zeigen")
    args = ap.parse_args()

    if not GRAPH_PATH.exists():
        print(f"[fehler] Graph-Datei nicht gefunden: {GRAPH_PATH}")
        sys.exit(1)

    with GRAPH_PATH.open() as f:
        data = json.load(f)

    nodes = data.get("nodes", {})
    edges = data.get("edges", [])

    print(f"== Eingangs-Zustand ==")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(edges)}")
    print()

    # ── Phase 1: Sanity-Filter (live-Funktion) ────────────────────────
    survivors, drops = consolidation._sanitize_extracted(
        list(nodes.values()), edges
    )
    dropped_edges = [e for e in edges if e not in survivors]

    print(f"== Phase 1: Sanity-Filter ==")
    print(f"  Verb nicht in Whitelist : {drops['verb']}")
    print(f"  Datum als Subjekt       : {drops['date_subject']}")
    print(f"  KI ↔ Sasha Subjekt-Tausch: {drops['subject_swap']}")
    print(f"  → behalten: {len(survivors)}, gedroppt: {len(dropped_edges)}")
    print()

    if args.verbose and dropped_edges:
        print("  Gedroppte Edges:")
        for e in dropped_edges:
            w = e.get("weight", 1.0)
            print(f"    {e.get('from','?')!r:30s} ─[{e.get('rel','?')}]─► "
                  f"{e.get('to','?')!r:30s}  w={w}")
        print()

    # ── Phase 2: Dedup nach (from, rel, to) ───────────────────────────
    # Wenn der Extraktor in mehreren Turns denselben Edge wiederholt,
    # haben wir physisch mehrere Einträge mit aufaddiertem Weight. Wir
    # konsolidieren: ein Edge pro Tripel, Weight = Summe.
    bucket = defaultdict(lambda: {"weight": 0.0, "extras": {}})
    for e in survivors:
        key = (e["from"], e["rel"], e["to"])
        bucket[key]["weight"] += float(e.get("weight", 1.0))
        for k, v in e.items():
            if k not in ("from", "rel", "to", "weight"):
                bucket[key]["extras"][k] = v

    deduped = []
    for (frm, rel, to), val in bucket.items():
        edge = {"from": frm, "rel": rel, "to": to, "weight": val["weight"]}
        edge.update(val["extras"])
        deduped.append(edge)

    dup_killed = len(survivors) - len(deduped)
    print(f"== Phase 2: Dedup nach (from, rel, to) ==")
    print(f"  Duplikate zusammengefasst: {dup_killed}")
    print(f"  Edges final: {len(deduped)}")
    print()

    # ── Optional: orphan-Node Bericht (nur informativ, kein Löschen) ──
    used = set()
    for e in deduped:
        used.add(e["from"])
        used.add(e["to"])
    orphans = [n for n in nodes if n not in used]
    print(f"== Verwaiste Nodes (nicht in Edges) ==")
    print(f"  Anzahl: {len(orphans)}  (bleiben drin - Embeddings sind nützlich)")
    print()

    total_drops = len(edges) - len(deduped)
    print(f"== Zusammenfassung ==")
    print(f"  Vorher: {len(edges)} Edges")
    print(f"  Nachher: {len(deduped)} Edges")
    print(f"  Differenz: -{total_drops} ({100*total_drops/max(1,len(edges)):.1f}%)")
    print()

    if not args.apply:
        print("(dry-run – nichts geschrieben. Mit --apply tatsächlich aufräumen.)")
        return

    # ── Backup + Apply ────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = GRAPH_PATH.with_suffix(f".json.bak.{ts}")
    shutil.copy2(GRAPH_PATH, backup)
    print(f"[backup] {backup}")

    data["edges"] = deduped
    with GRAPH_PATH.open("w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[apply]  {GRAPH_PATH} aktualisiert")


if __name__ == "__main__":
    main()
