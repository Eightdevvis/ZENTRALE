#!/usr/bin/env python3
"""
Live-Rauchtest für den Cloud-Kern (core/cloud.py).

Der erste ECHTE API-Call. Bewusst gestaffelt und billig: jede Stufe prüft eine
Sache, und man sieht nach jeder, ob es Sinn hat weiterzumachen.

  1  Erreichbarkeit  - Key gültig, Modell-ID existiert, Parameter akzeptiert
  2  Prompt-Cache    - zweiter identischer Turn muss cache_read > 0 zeigen
  3  Tool-Loop       - ein lesendes Tool (read_calendar) einmal komplett durch

Stufe 2 ist die wichtigste: ohne Cache-Treffer kostet der Systemblock bei
JEDEM Turn und JEDER Tool-Runde den vollen Preis - das ist der Unterschied
zwischen ~18 und ~45 Euro im Monat.

Aufruf (aus dem Projekt-Root):
    venv/bin/python scripts/cloud_smoke.py
    venv/bin/python scripts/cloud_smoke.py --stufe 1     # nur die erste

Kosten: drei kurze Turns, im Bereich weniger Cent.

Schreibt nichts in den Kalender und hakt nichts ab. Das Erlaubnis-Gate wird
hart auf "nein" verdrahtet - sollte das Modell wider Erwarten ein
schreibendes Tool rufen, blockiert der Test nicht und führt nichts aus.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _abbruch(text):
    print(f"\n  ABBRUCH: {text}\n")
    sys.exit(1)


def _sammle(stream):
    """Generator leerlaufen lassen, Events nach Typ sortiert zurückgeben."""
    text, reflect, sonst = [], [], []
    for ev in stream:
        if isinstance(ev, str):
            text.append(ev)
        elif isinstance(ev, dict) and "reflect" in ev:
            reflect.append(ev["reflect"])
        else:
            sonst.append(ev)
    return "".join(text), "".join(reflect), sonst


def _usage_zeile(protokoll):
    """Letzte CLOUD-Zeile aus dem Terminal-Log fischen."""
    for zeile in reversed(protokoll):
        if "CLOUD ←" in zeile:
            return zeile
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stufe", type=int, default=0,
                    help="nur diese Stufe fahren (1-3), 0 = alle")
    args = ap.parse_args()

    os.environ.setdefault("ZENTRALE_MAIL", "off")

    import ai_config  # noqa: F401  - Import-Effekt: Keys aus data/ai_config.json
    import cloud
    import state

    # ── Vorbedingungen ────────────────────────────────────────────────
    print("\n=== Cloud-Rauchtest ===\n")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _abbruch("Kein ANTHROPIC_API_KEY. Der Key gehört in "
                 "data/ai_config.json, NICHT in die Shell-Umgebung - "
                 "sonst rechnet auch Claude Code über die API ab statt "
                 "über das Abo.")
    if not cloud.is_available():
        _abbruch("anthropic-SDK fehlt im venv.")

    print(f"  Modell      {cloud._MODEL}")
    print(f"  effort      {cloud._EFFORT}")
    print(f"  max_tokens  {cloud._MAX_TOKENS}")
    print(f"  Graph       {cloud.CLOUD_GRAPH}")

    # Erlaubnis-Gate stilllegen: der Test hat keine Oberfläche zum Klicken.
    state.wait_permission = lambda: "nein"
    state.request_permission = lambda **k: None

    protokoll = []
    _echtes_log = state.push_log
    def mitschreiben(zeile):
        protokoll.append(str(zeile))
        _echtes_log(zeile)
    state.push_log = mitschreiben

    stufen = [args.stufe] if args.stufe else [1, 2, 3]
    frage = "Sag in genau einem kurzen Satz Hallo."

    # ── Stufe 1: kommt überhaupt etwas zurück ─────────────────────────
    if 1 in stufen:
        print("\n[1] Erreichbarkeit …")
        text, reflect, sonst = _sammle(
            cloud.chat_stream([{"role": "user", "content": frage}]))
        if text.startswith("[Cloud-Fehler"):
            _abbruch(text)
        if not text.strip():
            _abbruch("Leere Antwort - vermutlich hat das Denken das "
                     "max_tokens-Budget aufgebraucht. ZENTRALE_CLOUD_MAX_TOKENS "
                     "hochsetzen oder ZENTRALE_CLOUD_EFFORT senken.")
        print(f"  Antwort:  {text.strip()[:200]}")
        if reflect:
            print(f"  Denken:   {reflect.strip()[:120]}…  (reflect-Events kommen an)")
        else:
            print("  Denken:   — keine reflect-Events. Erwartbar bei effort=low, "
                  "sonst prüfen ob display='summarized' gesetzt ist.")
        print(f"  {_usage_zeile(protokoll) or 'kein usage-Log'}")

    # ── Stufe 2: greift der Prompt-Cache ──────────────────────────────
    if 2 in stufen:
        print("\n[2] Prompt-Cache (identischer Turn, zweiter Anlauf) …")
        _sammle(cloud.chat_stream([{"role": "user", "content": frage}]))
        zeile = _usage_zeile(protokoll)
        print(f"  {zeile or 'kein usage-Log'}")
        if zeile and "cache_read=0 " in zeile + " ":
            print("\n  ⚠ cache_read=0 - der Cache greift NICHT.")
            print("    Heißt: der Systemblock kostet bei jedem Turn und jeder")
            print("    Tool-Runde den vollen Preis. Ursache ist immer, dass sich")
            print("    im statischen Block etwas pro Turn ändert (_system_blocks).")
            print("    Zweitursache: der Block liegt unter der Mindestgröße.")
        elif zeile:
            print("  ✓ Cache greift - der statische Block wird wiederverwendet.")

    # ── Stufe 3: Tool-Loop ────────────────────────────────────────────
    if 3 in stufen:
        print("\n[3] Tool-Loop (lesend: read_calendar) …")
        text, _, sonst = _sammle(cloud.chat_stream(
            [{"role": "user", "content": "Was steht diese Woche an?"}]))
        if text.startswith("[Cloud-Fehler"):
            _abbruch(text)
        tool_zeilen = [z for z in protokoll if "TOOL" in z]
        print(f"  Antwort:  {text.strip()[:200]}")
        if tool_zeilen:
            print(f"  ✓ Tools gelaufen ({len(tool_zeilen)} Log-Zeilen), z.B.:")
            print(f"    {tool_zeilen[0][:140]}")
        else:
            print("  ⚠ Kein Tool gerufen. Entweder reichte dem Modell der")
            print("    Kontext - oder das Tool-Schema kommt nicht an.")
        if any(isinstance(e, dict) and "permission" in e for e in sonst):
            print("  ⚠ Das Gate hat gefeuert (und wurde auf 'nein' verdrahtet).")
        print(f"  {_usage_zeile(protokoll) or 'kein usage-Log'}")

    print("\n=== fertig ===")
    print("Hinweis: der Turn wird erst nach ~45 s Gesprächspause in den")
    print("Cloud-Graphen konsolidiert - dieses Skript endet vorher, der")
    print("Graph bleibt also leer. Das ist kein Fehler.\n")


if __name__ == "__main__":
    main()
