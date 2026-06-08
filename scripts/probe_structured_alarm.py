#!/usr/bin/env python3
"""
Fokus-Probe: hebt ERZWUNGENE STRUKTUR (Ollama `format`/JSON-Schema) die
Alarm-Zuordnung des 9b gegenüber Freitext?
================================================================================

Hintergrund (memory/grounding_recherche.md): Maker-Lead, dass strukturierte
Outputs (Ollama `format`) Halluzination dämpfen, weil das Modell SCHEMA-FELDER
füllen muss statt frei zu fabulieren. Lead ① (Modell ist nicht das Problem,
Hebel = Architektur) macht genau das zum richtigen Versuch - im Gegensatz zum
Modellwechsel.

Diese Probe testet NUR den kritischen T2-Moment der Alarm-Episode (post-delete,
offener Alarm = nur noch Geige-ABSAGE) und vergleicht bei identischem Kontext:
  A) FREITEXT  - normaler Chat-Call, Antwort als content.
  B) STRUKTUR  - `format`=JSON-Schema zwingt {art_der_warnung, welche_aktivitaet,
                 warum, was_du_tun_musst}; gescort wird das Feld welche_aktivitaet.

Score (bias-frei, Substring): nennt es die Geige UND nicht den (gelöschten)
10-Uhr-/lokalen Termin? Beide Varianten N-fach, echte Default-Varianz (keine
temp-Fixierung, wie im Prod-Pfad). Isolierte Fixture (Live-Daten unberührt) -
erbt die ganze Setup-Maschinerie aus bench_calendar_delete.py.

Aufruf: venv/bin/python scripts/probe_structured_alarm.py [--repeats 15] [--model qwen3.5:9b]
"""

import argparse
import importlib.util
import json
import os
import time
import urllib.request
from datetime import date, timedelta

# bench_calendar_delete als Modul laden (bringt Stubs, isolierte Fixture,
# write_fixture, build_system, GEIGE/ABSAGE/MISATTRIB, ai/kalender/state mit).
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "bcd", os.path.join(_HERE, "bench_calendar_delete.py"))
bcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcd)
ai, kalender, state = bcd.ai, bcd.kalender, bcd.state

# Anmerkung: Ollama 0.17.7 erzwingt KEIN Schema-Objekt (getestet - es erfindet
# eigene Felder), nur `format:"json"` greift. Darum hier kein JSON-Schema, sondern
# JSON-Mode + Feldnamen im Prompt (siehe run_struktur).

Q_T1 = "lösch bitte den termin um 10 uhr morgen."
Q_T2 = "und was ist diese warnung da im dashboard?"


def post(payload, timeout=300):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ai.OLLAMA_URL + "/api/chat", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def base_payload(model, today, history, extra_user=""):
    system = bcd.build_system(today)
    msgs = [{"role": "system", "content": system}, *history,
            {"role": "user", "content": Q_T2 + extra_user}]
    p = {"model": model, "messages": msgs, "stream": False,
         "options": {"num_ctx": ai.OLLAMA_NUM_CTX}}
    if model.startswith("qwen3"):
        p["think"] = False
    return p


def attribution_ok(text: str) -> bool:
    """Geige genannt UND nicht der gelöschte 10-Uhr-/lokale Termin."""
    return (bcd._has_all(text, [bcd.GEIGE, bcd.ABSAGE])
            and not bcd._has_any(text, bcd.MISATTRIB))


def run_freitext(model, today, history):
    p = base_payload(model, today, history)
    msg = post(p)["message"]
    content = (msg.get("content") or "").strip()
    return content, attribution_ok(content)


def run_think(model, today, history):
    # think=ON: das Modell darf vor der Antwort reflektieren ("ergibt das Sinn?").
    # Auf 0.17.7 kommen thinking + content getrennt zurück (content-loss-Bug weg).
    # Gescort wird der CONTENT (nur der erreicht im Prod-Pfad den User), das
    # thinking-Feld geben wir zum Anschauen mit zurück.
    p = base_payload(model, today, history)
    p["think"] = True
    msg = post(p)["message"]
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()
    return content, attribution_ok(content), thinking


def run_struktur(model, today, history):
    # 0.17.7 erzwingt KEIN Schema-Objekt (getestet - es erfindet eigene Felder),
    # aber `format:"json"` (generischer JSON-Mode) greift. Also: JSON-Mode + die
    # Feldnamen im Prompt benennen → das Modell füllt sie. Kernfeld welche_aktivitaet
    # zwingt es, die betroffene Aktivität EXPLIZIT zu benennen statt frei zu driften.
    p = base_payload(
        model, today, history,
        extra_user=(" Antworte AUSSCHLIESSLICH als JSON mit den Feldern "
                    '"welche_aktivitaet" (die betroffene Aktivität), "warum" '
                    '(der Grund) und "was_du_tun_musst" (die Handlung).'))
    p["format"] = "json"
    raw = (post(p)["message"].get("content") or "").strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return raw, False  # kein gültiges JSON -> Fehlschlag
    akt = str(obj.get("welche_aktivitaet", ""))
    combined = " ".join(str(v) for v in obj.values())
    ok = (bcd._has_any(akt, bcd.GEIGE)
          and not bcd._has_any(akt, bcd.MISATTRIB)
          and bcd._has_any(combined, bcd.ABSAGE))
    return raw, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=15)
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--show", action="store_true", help="Antworten mitprinten")
    args = ap.parse_args()

    today = date.today()
    tomorrow = today + timedelta(days=1)
    print(f"Modell: {args.model}   N={args.repeats}")
    print("Pro Iteration: echte T1-Löschantwort erzeugen (realistische "
          "Vergiftung wie im Bench), dann T2 frei vs. JSON-Struktur.\n")

    # Warmup
    bcd.write_fixture(today)
    bcd.run_turn(args.model, today, [], "warmup hallo")

    res = {"frei": 0, "struktur": 0, "think": 0}
    for i in range(args.repeats):
        # 1) Frische Vor-Lösch-Welt (beide Alarme), echte T1-Löschantwort holen -
        #    so entsteht dieselbe ramblige Modell-Vorantwort wie im echten Bench.
        bcd.write_fixture(today)
        r1 = bcd.run_turn(args.model, today, [], Q_T1)
        history = [{"role": "user", "content": Q_T1},
                   {"role": "assistant", "content": r1["content"]}]
        # 2) Welt auf post-delete normalisieren (10-Uhr weg, Alarm = nur Geige).
        kalender.delete_entry(tomorrow.isoformat(), "Termin um 10 Uhr")
        state.set_alarms(kalender.open_alarms())
        # 3) T2 mit DERSELBEN realistischen History: frei vs. struktur vs. think.
        ft, ft_ok = run_freitext(args.model, today, history)
        st, st_ok = run_struktur(args.model, today, history)
        th, th_ok, th_block = run_think(args.model, today, history)
        res["frei"] += ft_ok
        res["struktur"] += st_ok
        res["think"] += th_ok
        print(f"  [{i+1}/{args.repeats}] frei={int(ft_ok)}  "
              f"struktur={int(st_ok)}  think={int(th_ok)}")
        if args.show:
            print(f"      T1-Vorantwort: {r1['content'][:120]}")
            print(f"      FREI: {ft[:140]}")
            print(f"      THINK-Block: {th_block[:200]}")
            print(f"      THINK-Antwort: {th[:140]}")

    n = args.repeats
    print(f"\n{'='*50}")
    print(f"FREITEXT  Zuordnung korrekt: {res['frei']}/{n} "
          f"({res['frei']/n*100:.0f}%)")
    print(f"STRUKTUR  Zuordnung korrekt: {res['struktur']}/{n} "
          f"({res['struktur']/n*100:.0f}%)")
    print(f"THINK=ON  Zuordnung korrekt: {res['think']}/{n} "
          f"({res['think']/n*100:.0f}%)")
    print(f"{'='*50}")
    print(f"(Fixture-Tempdir: {bcd._TMP} - Live-Daten unberührt.)")


if __name__ == "__main__":
    main()
