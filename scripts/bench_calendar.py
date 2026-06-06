#!/usr/bin/env python3
"""
Kalender-End-to-End-Benchmark fuer ZENTRALE
===========================================

Warum DIESES Skript zusaetzlich zu bench_models.py:
  bench_models.py misst nur die ERSTE Runde - feuert der erwartete Tool-Call?
  Das reicht nicht. Der echte Schmerz sitzt in der ZWEITEN Runde: Modell ruft
  read_calendar, kriegt das Ergebnis zurueck - und muss daraus eine KORREKTE
  Antwort bauen. Genau da scheitern schwache Modelle (sagen "keine gefunden"
  trotz Daten, lassen content leer, vergessen Treffer). Dieses Skript faehrt
  den VOLLEN Tool-Loop (Tools werden echt ausgefuehrt) und bewertet die
  FINALE Antwort gegen vorher festgenagelte Ground-Truth.

Bias-Schutz (der Punkt, auf den Sasha bestanden hat):
  - Die richtigen Antworten stehen als Fakten-Checks IM SKRIPT, vor dem Lauf.
  - Gescort wird automatisch per Substring/Synonym-Abgleich, nicht per Urteil.
  - Drei getrennte Metriken, damit sichtbar ist WO es bricht:
      tool_fire   - hat read_calendar ueberhaupt gefeuert? (wenn erwartet)
      answered    - kam ueberhaupt nicht-leerer content zurueck?
      correct     - stimmen die Fakten (richtige Tage/Zeiten, keine Erfindung)?
  - "correct" zaehlt nur als bestanden wenn tool_fire UND answered UND alle
    Fakten passen UND kein Forbid-Begriff auftaucht.

Faithfulness zum Produktiv-Pfad (core/ai.py:chat_stream):
  - gleiche TOOLS, gleicher System-Prompt INKL. _now_prompt (Zeit-Anker +
    Pflicht-Regel zum Tool) - der ist fuer Kalenderfragen essenziell.
  - Tools werden mit ai._dispatch_tool ECHT ausgefuehrt (gegen die LIVE-
    Kalenderdaten in data/).
  - KEINE temperature-Fixierung: der echte chat_stream setzt keine, also
    laeuft das Modell auf seinem Default-Temp. Genau das erzeugt die Varianz,
    die der User spuert - mit temp=0 wuerde man sie wegmessen. Deshalb messen
    wir mit Repeats die ECHTE Treffer-Quote, nicht eine determinische Single-
    Shot-Antwort.
  - Graph-Kontext bleibt weg (privat + fuer Tool-Calling irrelevant), wie in
    bench_models.py begruendet.

ACHTUNG Datumsabhaengigkeit: die Ground-Truth-Checks gehen von HEUTE = Sa,
06.06.2026 aus (passend zu den eingetragenen Juni-Daten). An einem anderen
Tag verschieben sich "naechste Woche" etc. - dann Fixture/Checks anpassen.

Aufruf:
  venv/bin/python scripts/bench_calendar.py
  venv/bin/python scripts/bench_calendar.py --models qwen3.5:9b qwen2.5:14b --repeats 5
  venv/bin/python scripts/bench_calendar.py --configs all   # alle think-Varianten
"""

import argparse
import json
import os
import sys
import time
import types
import urllib.request

# ── core/ai.py importieren ohne den Memory-Stack (wie bench_models.py) ─────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CORE = os.path.join(_ROOT, "core")
sys.path.insert(0, _CORE)
# kalender NICHT stubben - wird real gebraucht (RANGE_BUCKETS in TOOLS, und
# _dispatch_tool fuehrt echte Kalender-Reads aus). context wird gestubbt:
# read_file/list_files rufen wir in den Kalender-Szenarien nicht.
for _m in ("net", "graph", "consolidation", "state", "context"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import ai          # noqa: E402
import kalender     # noqa: E402

# System-Prompt EXAKT wie im Chat-Pfad - inkl. Jetzt-Block (Datum + Tool-Regel).
SYSTEM = (ai._now_prompt() + "\n\n" + ai._SYSTEM_PROMPT
          + "\n\n" + ai._CAPABILITIES_PROMPT)
TOOLS = ai.TOOLS
NUM_CTX = ai.OLLAMA_NUM_CTX
OLLAMA_URL = ai.OLLAMA_URL


# ── Ground-Truth-Szenarien ─────────────────────────────────────────────────
# Fakten (Stand data/, heute = Sa 06.06.2026):
#   Geigenstunde  Di 17:45        | Fahrschule Di+Do 19:00
#   Parkour       Mi 18:00, Fr 20:00
#   Flixbus->Ungarn Mo 08.06 (Nachtfahrt) | Rueckflug Fr 12.06
#   Mutter helfen Sa 13., Sa 20., Fr 26.06 | Hoehlenschlucht So 14.06
#
# include: Liste von Gruppen. Jede Gruppe gilt als erfuellt wenn IRGENDEINER
#          ihrer Synonyme (case-insensitiv) im Antworttext steht. ALLE Gruppen
#          muessen erfuellt sein.
# forbid : faellt durch wenn IRGENDEINER dieser Strings auftaucht.
# expect_tool: muss read_calendar feuern (True) bzw. darf NICHT (False).
REFUSAL = ["keine einträge", "keine termine", "nichts gefunden",
           "nicht gefunden", "kein eintrag", "keine fahrschul",
           "nichts eingetragen", "kann ich nicht", "nichts geplant"]

SCENARIOS = [
    # ── Filter-Fragen ("wann hab ich X") - hier brach qwen3 ──
    dict(key="fahrschule", prompt="wann hab ich fahrschule?",
         expect_tool=True,
         include=[["dienstag"], ["donnerstag"], ["19"]],
         forbid=REFUSAL + ["montag", "mittwoch", "sonntag"]),
    dict(key="geige", prompt="wann ist geige?",
         expect_tool=True,
         include=[["dienstag"], ["17:45", "17.45", "17 uhr 45"]],
         forbid=REFUSAL),
    dict(key="parkour", prompt="wann ist parkour?",
         expect_tool=True,
         include=[["mittwoch"], ["freitag"]],
         forbid=REFUSAL),
    dict(key="ungarn", prompt="wann fahre ich nach ungarn?",
         expect_tool=True,
         include=[["8.", "achten", "montag", "flixbus"]],
         forbid=REFUSAL),
    # ── Range-Fragen ──
    dict(key="monat", prompt="was steht diesen monat noch an?",
         expect_tool=True,
         include=[["ungarn"], ["höhle", "hoehle", "schlucht"],
                  ["mutter", "mutti"]],
         forbid=REFUSAL),
    dict(key="woche_o_naechste",
         prompt="steht diese oder nächste woche sonst etwas an?",
         expect_tool=True,
         include=[["ungarn"], ["geige", "fahrschule", "höhle", "hoehle"]],
         # 26. ist Spaet-Monat (Mutter), darf bei "naechste Woche" NICHT kommen.
         forbid=REFUSAL + ["26."]),
    dict(key="dienstag", prompt="was mache ich nächsten dienstag?",
         expect_tool=True,
         include=[["geige", "17:45", "geigenstunde"],
                  ["fahrschule", "19"]],
         forbid=REFUSAL + ["leer"]),
    dict(key="hoehle", prompt="wann ist die höhlentour?",
         expect_tool=True,
         include=[["14.", "vierzehnten", "sonntag"]],
         forbid=REFUSAL),
    # ── Vergangenheit: nur Tool+Antwort pruefen, KEINE Fakten (erlebt-Layer
    #    ist privat - wir scoren hier nicht auf Inhalte). ──
    dict(key="vergangenheit", prompt="was hatte ich letzte woche?",
         expect_tool=True, include=[], forbid=[]),
    # ── Falsch-Positiv: reiner Chat, KEIN Kalender-Tool darf feuern ──
    dict(key="chat", prompt="was hältst du von regenwetter? halt dich kurz.",
         expect_tool=False, include=[], forbid=[]),
]


def http_post(url, payload, timeout=300):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Antwort-Tool-Variante (Sashas Idee) ────────────────────────────────────
# Hypothese: qwen3 feuert Tool-Calls zuverlaessig, verliert aber mit think=ON
# die finale Antwort (landet im Denkblock, content leer). Wenn "antworten"
# selbst ein Tool ist, reitet die Antwort auf dem zuverlaessigen Tool-Kanal.
ANTWORT_TOOL = {
    "type": "function",
    "function": {
        "name": "antwort",
        "description": (
            "Gib deine finale Antwort an den User AUSSCHLIESSLICH ueber dieses "
            "Tool aus - schreibe den vollstaendigen Antworttext ins Feld 'text'. "
            "Reihenfolge: erst Daten-Tools (z.B. read_calendar) nutzen, dann mit "
            "'antwort' die fertige, formulierte Antwort liefern. Niemals als "
            "freien Text antworten."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string",
                         "description": "Die fertige Antwort fuer den User."},
            },
            "required": ["text"],
        },
    },
}
ANTWORT_SUFFIX = ("\n\nWICHTIG: Deine finale Antwort gibst du IMMER ueber das "
                  "'antwort'-Tool aus (Feld 'text'), nie als freien Text.")


def run_loop(model, prompt, think, max_rounds=5, antwort_mode=False,
             suffix_only=False, sampling=None):
    """
    Faehrt den vollen Tool-Loop fuer EINE Frage. Tools werden echt ausgefuehrt.
    antwort_mode=True: 'antwort'-Tool mitgeben + System-Suffix; ein antwort-Call
    gilt als finale Antwort (text-Feld) und beendet die Schleife.
    suffix_only=True: NUR den System-Suffix anhaengen, OHNE das antwort-Tool -
    zum Isolieren, ob der Gewinn vom Tool oder vom Prompt-Satz kommt.
    Gibt zurueck: fired, args, content (finale Antwort), rounds, latency, error.
    """
    system = SYSTEM + (ANTWORT_SUFFIX if (antwort_mode or suffix_only) else "")
    tools = TOOLS + ([ANTWORT_TOOL] if antwort_mode else [])
    msgs = [{"role": "system", "content": system},
            {"role": "user", "content": prompt}]
    fired, args_seen = [], []
    t0 = time.time()
    for rnd in range(max_rounds):
        payload = {
            "model": model,
            "messages": msgs,
            "tools": tools,
            "stream": False,
            "keep_alive": "5m",
            # Default: nur num_ctx (= Produktiv-Pfad). sampling=dict ueberschreibt,
            # um Qwen-empfohlene Werte zu testen (temp/top_p/top_k/min_p/...).
            "options": {"num_ctx": NUM_CTX, **(sampling or {})},
        }
        if model.startswith("qwen3"):
            payload["think"] = think
        try:
            msg = http_post(OLLAMA_URL + "/api/chat", payload)["message"]
        except Exception as exc:
            return dict(fired=fired, args=args_seen, content="",
                        rounds=rnd, latency=time.time() - t0, error=str(exc))
        tcs = msg.get("tool_calls") or []
        if not tcs:
            # Kein Tool-Call -> Modell hat als Freitext geantwortet. Im
            # antwort_mode ist das Regelbruch, aber wir nehmen den content
            # trotzdem als Antwort (fair: Antwort ist Antwort).
            return dict(fired=fired, args=args_seen,
                        content=(msg.get("content") or "").strip(),
                        rounds=rnd + 1, latency=time.time() - t0, error=None)
        msgs.append({"role": "assistant", "content": msg.get("content", ""),
                     "tool_calls": tcs})
        for tc in tcs:
            name = tc["function"]["name"]
            a = tc["function"].get("arguments", {})
            if isinstance(a, str):
                try:
                    a = json.loads(a)
                except Exception:
                    a = {"_raw": a}
            fired.append(name)
            args_seen.append(a)
            if antwort_mode and name == "antwort":
                # Terminal: die finale Antwort steht im text-Feld.
                return dict(fired=fired, args=args_seen,
                            content=str(a.get("text", "")).strip(),
                            rounds=rnd + 1, latency=time.time() - t0, error=None)
            msgs.append({"role": "tool", "content": ai._dispatch_tool(name, a)})
    return dict(fired=fired, args=args_seen, content="[max_rounds]",
                rounds=max_rounds, latency=time.time() - t0, error=None)


def _has_all(text, groups):
    t = text.casefold()
    return all(any(s.casefold() in t for s in group) for group in groups)


def _has_any(text, subs):
    t = text.casefold()
    return any(s.casefold() in t for s in subs)


def score(scn, r):
    """Bewertet einen Lauf gegen die Ground-Truth. Liefert die Einzel-Checks
    plus 'correct' (alles zusammen). Bias-frei: nur Abgleich, kein Urteil."""
    cal_fired = "read_calendar" in r["fired"]
    answered = bool(r["content"]) and r["content"] != "[max_rounds]"
    if scn["expect_tool"]:
        tool_ok = cal_fired
    else:
        tool_ok = not cal_fired      # Falsch-Positiv-Fall: darf NICHT feuern
    facts_ok = _has_all(r["content"], scn["include"]) if scn["include"] else True
    forbid_hit = _has_any(r["content"], scn["forbid"]) if scn["forbid"] else False
    correct = tool_ok and answered and facts_ok and not forbid_hit
    return dict(tool_ok=tool_ok, answered=answered, facts_ok=facts_ok,
                forbid_hit=forbid_hit, correct=correct)


def bench(model, think, repeats, antwort_mode=False):
    label = f"{model} (think={think})" if model.startswith("qwen3") else model
    if antwort_mode:
        label += " +antwort-tool"
    print(f"\n{'='*70}\nKONFIG: {label}\n{'='*70}")
    # Warmup (laedt Modell, Ergebnis verworfen)
    print("  warmup ...", flush=True)
    w = run_loop(model, "sag kurz hallo", think, antwort_mode=antwort_mode)
    if w["error"]:
        print(f"  FEHLER beim Warmup: {w['error']}  (gepullt? ollama pull {model})")
        return None

    agg = dict(tool_ok=0, answered=0, correct=0, n=0)
    lat = []
    per_scn = []
    for scn in SCENARIOS:
        c = dict(tool_ok=0, answered=0, correct=0)
        for _ in range(repeats):
            r = run_loop(model, scn["prompt"], think, antwort_mode=antwort_mode)
            lat.append(r["latency"])
            s = score(scn, r)
            for k in ("tool_ok", "answered", "correct"):
                c[k] += s[k]
                agg[k] += s[k]
            agg["n"] += 1
        per_scn.append(dict(key=scn["key"], **c))
        print(f"  [{scn['key']:16}] tool {c['tool_ok']}/{repeats}  "
              f"antwort {c['answered']}/{repeats}  KORREKT {c['correct']}/{repeats}")
    summary = dict(
        config=label, model=model, think=(think if model.startswith("qwen3") else None),
        repeats=repeats,
        tool_rate=agg["tool_ok"] / agg["n"],
        answer_rate=agg["answered"] / agg["n"],
        correct_rate=agg["correct"] / agg["n"],
        avg_latency=sum(lat) / len(lat) if lat else 0,
        per_scenario=per_scn,
    )
    print(f"  --> tool {summary['tool_rate']*100:.0f}%  "
          f"antwort {summary['answer_rate']*100:.0f}%  "
          f"KORREKT {summary['correct_rate']*100:.0f}%  "
          f"({summary['avg_latency']:.1f}s/Frage)")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--antwort", action="store_true",
                    help="Testet die antwort-Tool-Variante (Sashas Idee): finale "
                         "Antwort kommt ueber ein 'antwort'-Tool statt als content. "
                         "Fokus-Configs (qwen3* think on/off + qwen2.5 Referenz).")
    args = ap.parse_args()

    if args.antwort:
        # (model, think, antwort_mode) - Fokus auf die Frage: rettet das Antwort-
        # Tool das 9b mit Thinking? qwen2.5:14b als Referenz mitlaufen lassen.
        configs = [
            ("qwen3.5:9b", True, True),
            ("qwen3.5:9b", False, True),
            ("qwen2.5:14b", False, True),
        ]
    else:
        # (model, think, antwort_mode) - Baseline ohne Antwort-Tool.
        configs = [
            ("qwen3.5:9b", False, False),
            ("qwen3.5:9b", True, False),
            ("qwen2.5:14b", False, False),
            ("qwen3:14b", False, False),
            ("qwen3:14b", True, False),
        ]

    print(f"Ollama:  {OLLAMA_URL}   num_ctx={NUM_CTX}   repeats={args.repeats}")
    print(f"Antwort-Tool: {args.antwort}")
    print(f"Szenarien: {[s['key'] for s in SCENARIOS]}")

    results = []
    for model, think, antwort_mode in configs:
        s = bench(model, think, args.repeats, antwort_mode=antwort_mode)
        if s:
            results.append(s)

    print(f"\n\n{'#'*78}\n# GESAMTERGEBNIS (KORREKT = Tool gefeuert + geantwortet + Fakten stimmen)\n{'#'*78}")
    print(f"{'Konfig':24} {'Tool':>7} {'Antwort':>8} {'KORREKT':>8} {'s/Frage':>8}")
    print("-" * 60)
    for s in sorted(results, key=lambda x: -x["correct_rate"]):
        print(f"{s['config']:24} {s['tool_rate']*100:6.0f}% "
              f"{s['answer_rate']*100:7.0f}% {s['correct_rate']*100:7.0f}% "
              f"{s['avg_latency']:7.1f}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = os.path.join(_HERE, f"bench_calendar_{stamp}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nVollergebnis: {out}")


if __name__ == "__main__":
    main()
