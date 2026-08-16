#!/usr/bin/env python3
"""Zeigt den System-Prompt, den eine Schiene wirklich rausschickt.

Warum das ein Skript ist und keine Doku-Datei: der Cloud-Prompt (`gross`)
wird zum Teil ABGELEITET — die Persona kommt aus `klein`, minus zwei
Abschnitte. Eine abgeschriebene Fassung waere eine dritte Version, die
still wegdriftet. Was hier rauskommt, ist aus dem Live-Code gebaut, also
per Konstruktion aktuell.

    scripts/prompt_zeigen.py                 # die Cloud-Schiene (gross)
    scripts/prompt_zeigen.py --schiene klein # die lokale (qwen)
    scripts/prompt_zeigen.py --tools         # dazu das Tool-Schema
    scripts/prompt_zeigen.py --diff          # was gross gegenueber klein weglaesst
    scripts/prompt_zeigen.py --woher         # nur die Landkarte: was editiere ich wo?
"""
import argparse
import difflib
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(WURZEL, "core"))
os.environ.setdefault("ZENTRALE_MAIL", "off")

import profil  # noqa: E402


# Wo welcher Teil des Cloud-Prompts herkommt. Der einzige Grund, warum das
# hier steht statt in einer .md: wer den Prompt aendern will, braucht GENAU
# diese Zuordnung, und zwar in dem Moment, in dem er ihn liest.
WOHER = [
    ("Persona / Stimme / Laenge",
     "core/profil/klein.py  ->  _SYSTEM_PROMPT",
     "!! aendert BEIDE Schienen — gross leitet die Persona ab, statt sie zu kopieren"),
    ("Was gross aus der Persona herausschneidet",
     "core/profil/gross.py  ->  die _ohne(...)-Aufrufe",
     "aktuell: '## Text-Effekte' und '## So endet ein Turn'"),
    ("Meta-Regeln der Cloud",
     "core/profil/gross.py  ->  _CAPABILITIES_PROMPT",
     "eigener Text, trifft NUR die Cloud"),
    ("Tool-Auswahl und -Beschreibungen der Cloud",
     "core/profil/gross.py  ->  _WEG, _NAMEN, _BESCHREIBUNG",
     "Parameter-Schemata bleiben geteilt — die sind Vertrag mit Python"),
    ("Spracheingabe-Hinweis",
     "core/profil/klein.py  ->  _MIC_INPUT_HINT",
     "gilt fuer jedes Modell gleich"),
    ("Graph-Kontext, Uhrzeit, Alarme (das Wechselnde)",
     "core/cloud.py  ->  _volatile_text()",
     "steht NICHT im System-Prompt, sondern hinten an der letzten User-Nachricht"),
]


def landkarte():
    print("WAS WILLST DU ANFASSEN?\n")
    for was, wo, hinweis in WOHER:
        print(f"  {was}")
        print(f"      {wo}")
        print(f"      {hinweis}\n")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schiene", default="gross", choices=sorted(profil.PROFILE))
    p.add_argument("--tools", action="store_true", help="Tool-Schema mit ausgeben")
    p.add_argument("--diff", action="store_true", help="gross gegen klein stellen")
    p.add_argument("--woher", action="store_true", help="nur die Landkarte")
    p.add_argument("--roh", action="store_true", help="nur der Prompt, ohne Rahmen")
    a = p.parse_args()

    if a.woher:
        landkarte()
        return

    prof = profil.hol(a.schiene)
    text = prof.system()

    if a.roh:
        print(text)
        return

    if a.diff:
        g, k = profil.hol("gross").system(), profil.hol("klein").system()
        print(f"klein: {len(k):>6} zeichen     gross: {len(g):>6} zeichen"
              f"     gespart: {len(k) - len(g)} ({100 * (len(k) - len(g)) // len(k)} %)\n")
        for z in difflib.unified_diff(k.splitlines(), g.splitlines(),
                                      "klein", "gross", lineterm="", n=1):
            print(z)
        return

    print("=" * 72)
    print(f"SYSTEM-PROMPT DER SCHIENE '{prof.NAME}'"
          f"   {len(text)} zeichen, grob {len(text) // 4} tokens")
    print("=" * 72)
    print(text)

    if a.tools:
        print("\n" + "=" * 72)
        print(f"TOOLS  ({len(prof.TOOLS)} stueck)")
        print("=" * 72)
        for t in prof.TOOLS:
            f = t["function"]
            print(f"\n── {f['name']}")
            print("   " + (f.get("description") or "").replace("\n", "\n   "))
        schema = json.dumps(prof.TOOLS, ensure_ascii=False)
        print(f"\n(schema gesamt: {len(schema)} zeichen, grob {len(schema) // 4} tokens)")

    print("\n" + "-" * 72)
    print("Zum Aendern:  scripts/prompt_zeigen.py --woher")


if __name__ == "__main__":
    main()
