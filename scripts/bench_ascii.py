#!/usr/bin/env python3
"""
ASCII-Bild-Benchmark fuer ZENTRALE (zeige_ascii)
================================================

Frage, die dieses Skript objektiv beantwortet:
  Wie oft greift das Modell VON SELBST zum Tool `zeige_ascii`, wenn ein
  Prompt ein Bild nahelegt? Sashas Beobachtung: nach expliziter Nachfrage
  kommt ein Bild, sonst ist das Modell schwerfaellig. Das hier misst die
  echte Feuer-Quote statt aus 2-3 Stichproben zu raten (siehe Memory
  feedback_messen_nicht_vibes).

Methode (warum so):
  - EINE Runde pro Test reicht: wollte das Modell ein Bild, packt es den
    zeige_ascii-Call in den ERSTEN Assistant-Turn (ggf. neben `antwort`).
    Also kein voller Tool-Loop noetig -> ein Ollama-Call pro Test, schnell
    genug fuer ~1000 Stueck.
  - Produktionstreu: identischer System-Prompt (_now_prompt + _SYSTEM_PROMPT
    + _CAPABILITIES_PROMPT + ANTWORT_SUFFIX) und identische TOOLS wie
    chat_stream, think=false, Qwen-Sampling. NUR der Graph-Kontext bleibt
    weg (privat + fuer Tool-Calling irrelevant, wie in bench_models.py).
  - KEIN chat_stream-Pfad -> kein Auto-Save, der private KI-Graph bleibt
    unberuehrt.

Prompt-Korpus, drei Kategorien:
  implizit  - emotional/gegenstaendlich, legt ein Bild NAHE (das ist die
              eigentliche Metrik: hier soll die Quote hoch sein)
  explizit  - direkte Bitte um ein Bild (Kontrolle: muss ~100 % feuern,
              sonst ist das Tool selbst kaputt)
  neutral   - Faktenfrage/kurz, KEIN Bild erwuenscht (Spam-Check: hier
              soll die Quote niedrig sein)

Metriken:
  fire      - hat zeige_ascii gefeuert?
  matched   - falls gefeuert: liefert ascii_lib.pick(stichwort) ein Bild?
              (Keyword-Pfad; der Embedding-Fallback ist im Bench aus, da
              `net` gestubbt ist - Hinweis steht in der Ausgabe.)

Aufruf:
  venv/bin/python scripts/bench_ascii.py                 # ~1000 Tests (40x25)
  venv/bin/python scripts/bench_ascii.py --repeats 5     # schneller Probelauf
  venv/bin/python scripts/bench_ascii.py --model qwen3.5:9b --repeats 25
"""

import argparse
import json
import os
import sys
import time
import types
import urllib.request
from collections import Counter, defaultdict

# ── core/ai.py importieren ohne den Memory-Stack (wie bench_calendar.py) ────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CORE = os.path.join(_ROOT, "core")
sys.path.insert(0, _CORE)

# net/graph/consolidation/state/context stubben. ascii_lib + kalender bleiben
# echt (ascii_lib.pick fuer die Match-Pruefung; kalender liefert RANGE_BUCKETS
# in TOOLS). Mit gestubbtem `net` faellt embeddings.embed_query auf None ->
# der Embedding-Fallback in ascii_lib ist im Bench inaktiv (Keyword-Pfad only).
for _m in ("net", "graph", "consolidation", "state", "context"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

import ai          # noqa: E402
import ascii_lib   # noqa: E402

# System-Prompt + Tools EXAKT wie der regulaere Chat-Pfad in chat_stream:
# _now_prompt + _SYSTEM_PROMPT + _CAPABILITIES_PROMPT + ANTWORT_SUFFIX +
# _ASCII_MARKER_PROMPT (die "visuelle Stimme" - genau die misst dieser Bench).
SYSTEM = (ai._now_prompt() + "\n\n" + ai._SYSTEM_PROMPT
          + "\n\n" + ai._CAPABILITIES_PROMPT
          + ai.ANTWORT_SUFFIX + ai._ASCII_MARKER_PROMPT)
TOOLS = ai.TOOLS
NUM_CTX = ai.OLLAMA_NUM_CTX
OLLAMA_URL = ai.OLLAMA_URL
SAMPLING = ai.QWEN_SAMPLING


# ── Prompt-Korpus ───────────────────────────────────────────────────────────
# (kategorie, prompt). Casual-Deutsch, so wie Sasha mit der KI redet.
PROMPTS = [
    # ── implizit: legt ein Bild nahe, ohne danach zu fragen ──
    ("implizit", "boah bin ich müde heute, kaum geschlafen"),
    ("implizit", "yes!! endlich hab ich den bug gefixt"),
    ("implizit", "mist, schon wieder alles abgestürzt"),
    ("implizit", "ich freu mich grad so, das wird ein guter tag"),
    ("implizit", "ich glaub ich brauch erstmal nen kaffee"),
    ("implizit", "magst du eigentlich katzen?"),
    ("implizit", "puh, der tag war echt anstrengend"),
    ("implizit", "ich hab mega hunger, weiß gar nicht was ich essen soll"),
    ("implizit", "die sonne scheint, endlich mal schönes wetter"),
    ("implizit", "so ein mistwetter, regnet schon den ganzen tag"),
    ("implizit", "ich bin grad echt sauer ehrlich gesagt"),
    ("implizit", "das macht mich gerade richtig traurig"),
    ("implizit", "wow, das hätt ich echt nicht gedacht"),
    ("implizit", "lass uns feiern, wir habens geschafft!"),
    ("implizit", "hey, schön dass du da bist"),
    ("implizit", "ok ich geh jetzt pennen, gute nacht"),
    ("implizit", "ich hab da ne idee, hör mal"),
    ("implizit", "weiß auch nicht so recht, was meinst du?"),
    ("implizit", "wer bist du eigentlich genau?"),
    ("implizit", "ich versteh grad nur bahnhof ehrlich"),
    ("implizit", "danke dir, das war echt lieb von dir"),
    ("implizit", "ja genau, sehe ich ganz genauso"),
    ("implizit", "nee, das würd ich lieber nicht machen"),
    ("implizit", "ich hör grad voll die geile musik"),
    ("implizit", "der hund von nebenan ist so süß"),
    ("implizit", "ich fühl mich heut richtig cool und entspannt"),
    ("implizit", "alter, das ist ja mal richtig krass"),
    ("implizit", "ich könnt jetzt echt ne ganze pizza essen"),
    ("implizit", "endlich wochenende, zeit zum chillen"),
    ("implizit", "ich bin total verwirrt von dem ganzen kram"),
    # ── explizit: direkte Bitte ums Bild (Kontrolle) ──
    ("explizit", "zeig mir mal ein ascii bild von ner katze"),
    ("explizit", "kannst du was visuelles dazu zeigen?"),
    ("explizit", "mach mal ein bild passend zu meiner stimmung, ich bin müde"),
    ("explizit", "hast du ein ascii bild für freude?"),
    ("explizit", "zeig mir was lustiges als bild"),
    # ── neutral: kein Bild erwuenscht (Spam-Check) ──
    ("neutral", "wie spät ist es gerade?"),
    ("neutral", "was ist die hauptstadt von frankreich?"),
    ("neutral", "rechne mir mal 17 mal 23 aus"),
    ("neutral", "wie funktioniert grob ein dieselmotor, kurz bitte"),
    ("neutral", "buchstabier mal das wort sonne rückwärts"),
]


def http_post(url, payload, timeout=300):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ollama(model, messages, think):
    payload = {
        "model": model, "messages": messages, "tools": TOOLS,
        "stream": False, "keep_alive": "10m",
        "options": {"num_ctx": NUM_CTX, **SAMPLING},
    }
    if model.startswith("qwen3"):
        payload["think"] = think
    return http_post(OLLAMA_URL + "/api/chat", payload)["message"]


def one_call(model, prompt, think, max_rounds=3):
    """
    Faehrt den (kurzen) Tool-Loop wie chat_stream und ermittelt die FINALE
    Antwort - aus dem 'antwort'-Tool oder als Freitext. Darin werden die
    Bild-Marker [[bild: name]] gezaehlt (ai._extract_ascii_markers, exakt der
    Produktions-Parser). Datentools (read_calendar) werden echt ausgefuehrt,
    damit der Loop nicht haengt. Gibt markers (Liste Stichworte) + die finale
    Antwort zurueck.
    """
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt}]
    t0 = time.time()
    answer = ""
    try:
        for _ in range(max_rounds):
            msg = _ollama(model, msgs, think)
            tcs = msg.get("tool_calls") or []
            if not tcs:
                answer = msg.get("content", "") or ""
                break
            msgs.append({"role": "assistant",
                         "content": msg.get("content", "") or "",
                         "tool_calls": tcs})
            done = False
            for tc in tcs:
                name = tc["function"]["name"]
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if name == "antwort":          # terminal: finale Antwort
                    answer = str(args.get("text", "")).strip()
                    done = True
                    break
                # Datentool echt ausfuehren (kalender ist real; read_file etc.
                # kommen bei diesen Prompts nicht vor)
                try:
                    res = ai._dispatch_tool(name, args)
                except Exception as exc:
                    res = f"[bench: tool {name} fehler: {exc}]"
                msgs.append({"role": "tool", "content": str(res)})
            if done:
                break
    except Exception as exc:
        return dict(error=str(exc), latency=time.time() - t0)
    _, markers = ai._extract_ascii_markers(answer)
    return dict(markers=markers, answer=answer,
                latency=time.time() - t0, error=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=ai.OLLAMA_MODEL)
    ap.add_argument("--repeats", type=int, default=25,
                    help="Wiederholungen pro Prompt (40 Prompts x repeats = N)")
    ap.add_argument("--think", action="store_true",
                    help="Thinking AN (Default: aus, = Produktiv-Pfad)")
    args = ap.parse_args()

    total = len(PROMPTS) * args.repeats
    print(f"# bench_ascii  model={args.model}  think={args.think}  "
          f"N={total} ({len(PROMPTS)} prompts x {args.repeats})")
    print(f"# Bibliothek: {len(ascii_lib._ensure_loaded())} Bilder")
    print(f"# Hinweis: Embedding-Fallback im Bench AUS (net gestubbt) - "
          f"matched zeigt nur den Keyword-Pfad.\n")

    # Aggregatoren
    per_cat = defaultdict(lambda: dict(n=0, fire=0, matched=0))
    sw_hist = Counter()        # welche Stichworte werden gewaehlt
    miss_hist = Counter()      # gefeuert, aber pick() findet nichts
    errors = 0
    lat_sum = 0.0
    t_start = time.time()
    done = 0

    for rep in range(args.repeats):
        for cat, prompt in PROMPTS:
            r = one_call(args.model, prompt, args.think)
            done += 1
            if r.get("error"):
                errors += 1
                if errors <= 5:
                    print(f"  ! Fehler: {r['error'][:80]}")
                continue
            lat_sum += r["latency"]
            c = per_cat[cat]
            c["n"] += 1
            markers = r["markers"]
            if markers:
                c["fire"] += 1
                # pro Marker zaehlen; "matched" = mind. ein Marker findet ein Bild
                any_hit = False
                for sw in markers:
                    sw_hist[sw] += 1
                    if ascii_lib.pick(sw):
                        any_hit = True
                    else:
                        miss_hist[sw] += 1
                if any_hit:
                    c["matched"] += 1
            # Fortschritt grob alle 40 Calls
            if done % len(PROMPTS) == 0:
                el = time.time() - t_start
                print(f"  … {done}/{total}  ({el:.0f}s, "
                      f"Ø {lat_sum/max(1,done-errors):.2f}s/Call)")

    # ── Auswertung ──
    print("\n=== ERGEBNIS ===")
    print(f"{'Kategorie':10} {'N':>5} {'fire':>6} {'fire%':>7} {'match%':>7}")
    for cat in ("implizit", "explizit", "neutral"):
        c = per_cat.get(cat)
        if not c or c["n"] == 0:
            continue
        firep = 100 * c["fire"] / c["n"]
        matchp = 100 * c["matched"] / c["fire"] if c["fire"] else 0.0
        print(f"{cat:10} {c['n']:>5} {c['fire']:>6} {firep:>6.1f}% {matchp:>6.1f}%")

    print("\nTop-Stichworte (gewählt):")
    for sw, n in sw_hist.most_common(15):
        print(f"  {n:>4}  {sw!r}")
    if miss_hist:
        print("\nGefeuert, aber KEIN Bild gefunden (Keyword-Pfad):")
        for sw, n in miss_hist.most_common(15):
            print(f"  {n:>4}  {sw!r}")

    print(f"\nFehler: {errors} | Ø Latenz: {lat_sum/max(1,done-errors):.2f}s "
          f"| Gesamt: {time.time()-t_start:.0f}s")

    # JSON-Dump (Mess-Artefakt, via .gitignore ausgeschlossen)
    out = {
        "model": args.model, "think": args.think, "n": total,
        "per_cat": {k: dict(v) for k, v in per_cat.items()},
        "stichworte": dict(sw_hist), "misses": dict(miss_hist),
        "errors": errors,
    }
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(_HERE, f"bench_ascii_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nJSON: {path}")


if __name__ == "__main__":
    main()
