#!/usr/bin/env python3
# scripts/tutor_devtools.py
#
# Devtools-Terminal für den Sprach-Tutor. In einem eigenen Terminal laufen lassen:
#     scripts/tutor_devtools.py                 # localhost:5000
#     scripts/tutor_devtools.py --url http://192.168.50.1:5000
#
# Zeigt LIVE (alles zeitgestempelt), in dieser Reihenfolge:
#   1. Snapshot beim Verbinden — die KOMPLETTE User-Vokabel (mit Level neu/wacklig/
#      fest) + das Assessment-Routing (braucht der User noch das Drill?).
#   2. Danach jede Vokabel-Statusänderung, sobald sie passiert.
#   3. Der KOMPLETTE AI-Stream: was die KI KRIEGT (voller System-Prompt + Messages +
#      Tools + Modell) und was sie AUSGIBT (Roh-Antwort inkl. dem, was das Zimmer
#      sonst versteckt), plus jeder Tool-Call.
#
# Reine Standardbibliothek (urllib, SSE von Hand geparst). Reconnect bei Abbruch.

import argparse
import json
import os
import sys
import time
import urllib.request

C = {  # ANSI-Farben (leer, wenn kein TTY)
    'dim': '\033[2m', 'rst': '\033[0m', 'b': '\033[1m',
    'ts': '\033[90m', 'vocab': '\033[36m', 'req': '\033[35m', 'out': '\033[32m',
    'tool': '\033[33m', 'head': '\033[1;37m', 'warn': '\033[31m', 'ok': '\033[32m',
    # Vokabel-Status
    'new': '\033[90m', 'understood': '\033[36m', 'learning': '\033[33m',
    'learned': '\033[32m', 'intuitive': '\033[1;32m',
}
if not sys.stdout.isatty():
    C = {k: '' for k in C}


def _stat(status):
    return f"{C.get(status, '')}{status}{C['rst']}"


def _indent(text, pad='      │ '):
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return '\n'.join(pad + ln for ln in text.split('\n'))


def render(ev):
    ts = f"{C['ts']}{ev.get('ts', '')}{C['rst']}"
    kind = ev.get('kind')

    if kind == 'snapshot':
        r_need = ev.get('needs_assessment')
        print(f"\n{C['head']}══ SNAPSHOT ({ev.get('lang')}) ══{C['rst']}  {ts}")
        got, tot = ev.get('core_got', 0), ev.get('core_total', 0)
        route = (f"{C['warn']}ASSESSMENT nötig{C['rst']}" if r_need
                 else f"{C['ok']}durch — freie Konversation{C['rst']}")
        print(f"  Routing: {route}   Kern {got}/{tot}"
              f"   graduated={ev.get('graduated')}")
        g = ev.get('game') or {}
        s = ev.get('srs') or {}
        print(f"  Spiel: {g.get('coins', 0)} Münzen · Teile {len(g.get('parts', []))}/{g.get('parts_total', 0)}"
              f"   FSRS: {s.get('tracked', 0)} getrackt, {s.get('due', 0)} fällig")
        vocab = ev.get('vocab') or []
        print(f"  User-Vokabel ({len(vocab)}):")
        if not vocab:
            print(f"    {C['dim']}(leer){C['rst']}")
        for v in vocab:
            print(f"    {_stat(v.get('status', '')):<24} {v['word']:<16} "
                  f"{C['dim']}spoken={v.get('spoken', 0)} listened={v.get('listened', 0)}{C['rst']}")
        print()
        return

    if kind == 'vocab':
        print(f"{ts} {C['vocab']}VOKABEL{C['rst']} {ev.get('action', ''):<8} "
              f"{C['b']}{ev.get('word', '')}{C['rst']} → {_stat(ev.get('status', ''))} "
              f"{C['dim']}(spoken={ev.get('spoken')} listened={ev.get('listened')}){C['rst']}")
        return

    if kind == 'ai.req':
        print(f"\n{ts} {C['req']}{C['b']}AI ← ANFRAGE{C['rst']} "
              f"[{ev.get('phase')}] {ev.get('provider')}/{ev.get('model')} ({ev.get('lang')})")
        print(f"      {C['dim']}Tools: {', '.join(ev.get('tools') or [])}{C['rst']}")
        print(f"      {C['req']}System-Prompt (komplett, inkl. Vokabel-Kontext + Lage):{C['rst']}")
        print(_indent(ev.get('system', '')))
        msgs = ev.get('messages') or []
        print(f"      {C['req']}Messages ({len(msgs)}):{C['rst']}")
        for m in msgs:
            print(_indent(f"[{m.get('role')}] {m.get('content', '')}"))
        return

    if kind == 'ai.out':
        print(f"{ts} {C['out']}{C['b']}AI → AUSGABE{C['rst']} [{ev.get('phase')}] "
              f"{C['dim']}(roh, inkl. versteckter Regie){C['rst']}")
        print(_indent(ev.get('raw', ''), pad='      ▸ '))
        return

    if kind == 'ai.tool':
        print(f"{ts} {C['tool']}AI ⚙ TOOL{C['rst']} {C['b']}{ev.get('name')}{C['rst']}"
              f"({json.dumps(ev.get('args') or {}, ensure_ascii=False)}) "
              f"{C['dim']}→ {str(ev.get('result'))[:200]}{C['rst']}")
        return

    # Unbekannt → roh
    print(f"{ts} {C['dim']}{kind}: {json.dumps({k: v for k, v in ev.items() if k not in ('ts', 'kind')}, ensure_ascii=False)}{C['rst']}")


def stream(url):
    req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
    with urllib.request.urlopen(req, timeout=60) as r:
        for raw in r:
            line = raw.decode('utf-8', 'replace').rstrip('\r\n')
            if not line.startswith('data:'):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except ValueError:
                continue
            render(ev)


def main():
    ap = argparse.ArgumentParser(description="Tutor-Devtools-Terminal")
    ap.add_argument('--url', default=os.environ.get('ZENTRALE_URL', 'http://localhost:5000'))
    a = ap.parse_args()
    endpoint = a.url.rstrip('/') + '/api/tutor/debug/stream'
    print(f"{C['head']}Tutor-Devtools{C['rst']} → {endpoint}   {C['dim']}(Strg+C zum Beenden){C['rst']}")
    while True:
        try:
            stream(endpoint)
        except KeyboardInterrupt:
            print("\nbeendet.")
            return 0
        except Exception as e:
            print(f"{C['warn']}Verbindung weg ({e}) — neu in 2 s …{C['rst']}")
            time.sleep(2)


if __name__ == '__main__':
    sys.exit(main())
