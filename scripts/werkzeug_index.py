#!/usr/bin/env python3
"""
Der Index der Werkzeug-Suche als MCP-Antwort auf tools/list (JSON).

Was die Suche kennt (gross-Schiene, ohne antwort/ask_choice/search_tools):
Name, Beschreibung, inputSchema, dazu unter _meta laden (immer|bedarf),
gruppe und die Schlagworte der Gruppe. core/werkzeug_suche.py, Doku
memory/ki/werkzeug_suche.md.

Aufruf (aus dem Projekt-Root):
    venv/bin/python scripts/werkzeug_index.py            # JSON auf stdout
    venv/bin/python scripts/werkzeug_index.py --suche "LSF Stundenplan"
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suche", help="statt der Liste: was diese Anfrage findet")
    a = ap.parse_args()
    import werkzeug_suche
    if a.suche:
        t = werkzeug_suche.suchen(a.suche)
        print(json.dumps({"anfrage": t.anfrage, "werkzeuge": list(t.werkzeuge),
                          "skills": list(t.skills)}, ensure_ascii=False, indent=1))
        return
    print(json.dumps(werkzeug_suche.mcp_liste(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
