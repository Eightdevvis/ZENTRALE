#!/usr/bin/env python3
# scripts/ai_devtools.py
#
# Devtools-Terminal fuer die KERN-KI. In einem eigenen Terminal laufen lassen:
#     scripts/ai_devtools.py                        # localhost:5000
#     scripts/ai_devtools.py --url http://<pc>:5000
#     scripts/ai_devtools.py --voll                 # auch die Messages ungekuerzt
#
# Der System-Prompt geht IMMER ungekuerzt raus — deswegen macht man das
# Terminal ja auf. --grenze/--voll betreffen nur die Messages.
#
# Zeigt LIVE, alles zeitgestempelt:
#   ai.req    Was die KI KRIEGT — das komplette Paket: System-Prompt Block fuer
#             Block (mit Markierung, wo ein Cache-Breakpoint sitzt), jede
#             Message, jedes Werkzeug MIT Beschreibung und Parametern, Modell
#             und Schiene. Die Werkzeug-Schemata stehen beim ersten Request
#             ausgeschrieben da und danach nur noch als "[Schemata wie oben]" —
#             sie aendern sich nicht, und 500-mal dasselbe wuerde den
#             Ringpuffer leerdruecken. Aendert sich der Satz, steht er wieder
#             vollstaendig da (erkennbar am Fingerabdruck dahinter).
#   ai.out    Was sie AUSGIBT — die ROH-Antwort inklusive Denk-Bloecken und dem
#             Vorgeplaenkel vor einem Tool-Call, das der Chat sonst schluckt.
#   ai.tool   Jeder Tool-Call: Name, Argumente, Ergebnis.
#   ai.graph  Was der Extraktor in den Graphen geschrieben hat. Bleibt seit
#             18.08.2026 STUMM: die Tripel-Extraktion ist aus, das
#             Gedaechtnis sind Dateien (core/gedaechtnis.py). Was sie sich
#             merkt, siehst du jetzt als ai.tool — write_note und Co.
#
# Das Gegenstueck fuer den Sprach-Tutor ist scripts/tutor_devtools.py — anderer
# Bus, andere Events, weil der Tutor ein eigenstaendiges Addon ist.
#
# Reine Standardbibliothek (urllib, SSE von Hand geparst). Reconnect bei Abbruch.

import argparse
import json
import os
import sys
import urllib.request

C = {  # ANSI-Farben (leer, wenn kein TTY)
    'dim': '\033[2m', 'rst': '\033[0m', 'b': '\033[1m',
    'ts': '\033[90m', 'req': '\033[35m', 'out': '\033[32m',
    'tool': '\033[33m', 'graph': '\033[36m', 'head': '\033[1;37m',
    'warn': '\033[31m', 'cache': '\033[1;34m',
}
if not sys.stdout.isatty() or os.environ.get('NO_COLOR'):
    C = {k: '' for k in C}

BREITE = 78


def linie(zeichen='─'):
    print(C['dim'] + zeichen * BREITE + C['rst'])


def kuerzen(text, grenze):
    text = text or ''
    if grenze <= 0 or len(text) <= grenze:
        return text
    return text[:grenze] + f"{C['dim']}… (+{len(text) - grenze} Zeichen){C['rst']}"


def block(text, grenze, einzug='  '):
    for zeile in kuerzen(text, grenze).split('\n'):
        print(einzug + zeile)


def zeig_req(ev, grenze):
    linie('═')
    print(f"{C['ts']}{ev['ts']}{C['rst']} {C['req']}{C['b']}→ REQUEST{C['rst']} "
          f"{ev.get('modell','?')} {C['dim']}| Schiene: {ev.get('schiene','?')}{C['rst']}")

    sysb = ev.get('system') or []
    zeichen = sum(len(b.get('text', '')) for b in sysb)
    print(f"{C['head']}System-Prompt{C['rst']} {C['dim']}({len(sysb)} Block/Bloecke, "
          f"{zeichen} Zeichen ≈ {zeichen // 4} Token){C['rst']}")
    for i, b in enumerate(sysb):
        marke = (f" {C['cache']}◄ CACHE-BREAKPOINT{C['rst']}"
                 if b.get('cache') else '')
        print(f"{C['dim']}  [{i}]{C['rst']}{marke}")
        # Der System-Prompt wird NIE gekuerzt. Er ist der Grund, warum man
        # dieses Terminal aufmacht — "(+6700 Zeichen)" ist genau die
        # Information, die man nicht sehen wollte. Gekuerzt werden nur die
        # Messages, die im Zweifel eine ganze News-Sendung enthalten.
        block(b.get('text', ''), 0, '    ')

    msgs = ev.get('messages') or []
    print(f"{C['head']}Messages{C['rst']} {C['dim']}({len(msgs)}){C['rst']}")
    for m in msgs:
        print(f"{C['dim']}  {m.get('rolle','?')}:{C['rst']}")
        for b in m.get('bloecke') or []:
            marke = (f" {C['cache']}◄ CACHE-BREAKPOINT{C['rst']}"
                     if b.get('cache') else '')
            if marke:
                print(f"   {marke}")
            block(b.get('text', ''), grenze, '    ')

    tools = ev.get('tools') or []
    voll  = ev.get('tools_voll')
    zeichen = sum(len(t.get('beschreibung', ''))
                  + len(json.dumps(t.get('parameter') or {}, ensure_ascii=False))
                  for t in (voll or []))
    kopf = (f"{C['head']}Tools{C['rst']} {C['dim']}({len(tools)}"
            + (f", {zeichen} Zeichen ≈ {zeichen // 4} Token" if voll else "")
            + f"){C['rst']}")
    if voll is None:
        # Unveraendert seit dem letzten Request — der Emitter spart sich die
        # Wiederholung, damit der Ringpuffer nicht nur noch Werkzeuge enthaelt.
        print(kopf + f"  {C['dim']}[Schemata wie oben, "
                     f"{ev.get('tools_fp','?')}]{C['rst']}  " + ', '.join(tools))
        return
    print(kopf + f"  {C['dim']}[{ev.get('tools_fp','?')}]{C['rst']}")
    for t in voll:
        print(f"  {C['tool']}{t.get('name','?')}{C['rst']}")
        block(t.get('beschreibung', ''), 0, '      ')
        props = (t.get('parameter') or {}).get('properties') or {}
        pflicht = set((t.get('parameter') or {}).get('required') or [])
        for pname, pinfo in props.items():
            marke = '*' if pname in pflicht else ' '
            typ = pinfo.get('type', '?')
            enum = pinfo.get('enum')
            if enum:
                typ += ' ' + '|'.join(str(e) for e in enum)
            print(f"      {C['dim']}{marke}{pname} ({typ}){C['rst']} "
                  f"{pinfo.get('description','')}")


def zeig_out(ev, grenze):
    v = ev.get('verbrauch') or {}
    zahlen = ' '.join(f"{k}={v[k]}" for k in v) if v else ''
    print(f"{C['ts']}{ev['ts']}{C['rst']} {C['out']}{C['b']}← ANTWORT{C['rst']} "
          f"{C['dim']}{ev.get('stop_reason','?')} {zahlen}{C['rst']}")
    for b in ev.get('bloecke') or []:
        block(b, grenze, '  ')


def zeig_tool(ev, grenze):
    kopf = f"{C['ts']}{ev['ts']}{C['rst']} {C['tool']}{C['b']}⚙ TOOL{C['rst']} {ev.get('name','?')}"
    print(kopf)
    print(f"{C['dim']}  args:{C['rst']} {kuerzen(json.dumps(ev.get('args'), ensure_ascii=False), grenze)}")
    if ev.get('fehler'):
        print(f"{C['warn']}  FEHLER: {ev['fehler']}{C['rst']}")
    else:
        block(ev.get('ergebnis', ''), grenze, '  ')


def zeig_graph(ev, grenze):
    print(f"{C['ts']}{ev['ts']}{C['rst']} {C['graph']}{C['b']}⊕ GRAPH{C['rst']} "
          f"{C['dim']}({ev.get('store','?')}){C['rst']}")
    knoten = ev.get('knoten') or []
    if knoten:
        print(f"{C['dim']}  knoten:{C['rst']} " + ', '.join(str(k) for k in knoten))
    for k in ev.get('kanten') or []:
        print(f"{C['dim']}  {k}{C['rst']}")
    if ev.get('quellen'):
        print(f"{C['dim']}  quellen: {', '.join(ev['quellen'])}{C['rst']}")


def zeig(ev, grenze):
    art = ev.get('kind')
    if art == 'hallo':
        linie('═')
        print(f"{C['head']}verbunden{C['rst']} {C['dim']}— backend "
              f"{ev.get('backend')}, provider {ev.get('provider')}{C['rst']}")
        print(f"{C['dim']}warte auf den naechsten Turn …{C['rst']}")
    elif art == 'ai.req':
        zeig_req(ev, grenze)
    elif art == 'ai.out':
        zeig_out(ev, grenze)
    elif art == 'ai.tool':
        zeig_tool(ev, grenze)
    elif art == 'ai.graph':
        zeig_graph(ev, grenze)
    else:
        print(f"{C['ts']}{ev.get('ts','')}{C['rst']} {art}: {ev}")
    sys.stdout.flush()


def stream(url, grenze):
    req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
    with urllib.request.urlopen(req, timeout=None) as r:
        for roh in r:
            zeile = roh.decode('utf-8', 'replace').rstrip('\n')
            if not zeile.startswith('data: '):
                continue          # Kommentar-Zeilen (Heartbeat) ueberspringen
            try:
                zeig(json.loads(zeile[6:]), grenze)
            except Exception as e:
                print(f"{C['warn']}[unlesbares Event: {e}]{C['rst']}")


def main():
    p = argparse.ArgumentParser(
        description="Live-Blick auf alles, was an die Kern-KI geht und zurueckkommt.")
    p.add_argument('--url', default='http://localhost:5000',
                   help='Backend-URL (Default: http://localhost:5000)')
    p.add_argument('--grenze', type=int, default=2000,
                   help='Zeichen pro Textblock, 0 = unbegrenzt (Default: 2000)')
    p.add_argument('--voll', action='store_true',
                   help='nichts kuerzen (wie --grenze 0)')
    a = p.parse_args()
    grenze = 0 if a.voll else a.grenze

    endpoint = a.url.rstrip('/') + '/api/ai/debug/stream'
    print(f"{C['dim']}verbinde mit {endpoint} …{C['rst']}")
    import time
    while True:
        try:
            stream(endpoint, grenze)
            print(f"{C['warn']}Verbindung beendet — neuer Versuch in 3 s{C['rst']}")
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"{C['warn']}nicht erreichbar ({e}) — neuer Versuch in 3 s{C['rst']}")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            return 0


if __name__ == '__main__':
    sys.exit(main())
