#!/usr/bin/env python3
"""
Modell-Benchmark fuer ZENTRALE
==============================

Vergleicht Ollama-Modelle auf dem ECHTEN Tool-Calling-Pfad der ZENTRALE,
damit der Modell-Pick auf Messung statt auf Papier-Scores beruht.

Warum dieses Skript ueberhaupt:
  Qwen3.5 hat auf dem Papier (BFCL/TAU2) starkes Tool-Calling, aber es gibt
  GEMELDETE Ollama-spezifische Bugs (ollama/ollama Issue #14745: der Tool-
  Call wird als Text ausgegeben statt ausgefuehrt). Ob der Tool-Call durch
  *deine* Ollama-Version und *deinen* Chat-Template-Pfad sauber feuert, kann
  man nur lokal messen - genau das tut dieses Skript.

Gemessen wird pro Modell:
  1. Tool-Call-Zuverlaessigkeit
     Bei Fragen die ein Tool brauchen: feuert der ERWARTETE Tool-Call
     strukturiert (response message.tool_calls), oder leakt er als Text im
     content-Feld (= der qwen3.5-Ollama-Bug)? Beides wird getrennt gezaehlt.
  2. Falsch-Positive
     Bei reinen Chat-Fragen: feuert das Modell faelschlich ein Tool?
  3. Speed
     - Generierungs-Tempo (tok/s aus eval_count / eval_duration)
     - Time-to-first-token (load_duration + prompt_eval_duration), also wie
       lange bis das erste Wort kommt - der Wert der den Voice-Use-Case
       gefuehlt macht oder bricht.
  4. VRAM / Processor-Split via `ollama ps` (CPU vs GPU - kritisch bei 12 GB).

Faithfulness: repliziert den ai.chat_stream-Call so nah wie sinnvoll:
  - gleiche TOOLS (importiert aus core/ai.py -> kein Schema-Drift)
  - gleicher System-Prompt (Persona + Meta-Regeln, importiert)
  - num_ctx = OLLAMA_NUM_CTX (8192), temperature = 0 (reproduzierbar)
  Der private Graph-Kontext ("## Aktiviertes Wissen") bleibt ABSICHTLICH weg:
  Tool-Calls laufen ueber das tools-Array, nicht ueber den Graphen - und der
  Graph ist tabu (privat). Fuer den Tool-Calling-Test ist er irrelevant.

Aufruf:
  venv/bin/python scripts/bench_models.py
  venv/bin/python scripts/bench_models.py --models qwen2.5:14b qwen3:14b qwen3.5:9b
  venv/bin/python scripts/bench_models.py --repeats 5
  venv/bin/python scripts/bench_models.py --think      # Thinking-Modus an (qwen3*)
"""

import argparse
import json
import os
import subprocess
import sys
import time
import types
import urllib.request


# ── core/ai.py importieren OHNE den Memory-Stack hochzufahren ──────────────
# ai.py macht beim Laden `import net/context/graph/consolidation/kalender`.
# Die wollen wir hier nicht (graph/consolidation laden den privaten Graphen,
# net braucht state, etc.). Trick: leere Platzhalter-Module in sys.modules
# legen, BEVOR wir ai importieren. ai.py benutzt diese Module nur INNERHALB
# von Funktionen, nicht auf Modul-Ebene - der Import klappt also mit Stubs,
# und wir bekommen die echten Konstanten (TOOLS, Prompts) ohne Drift.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_CORE = os.path.join(_ROOT, "core")
sys.path.insert(0, _CORE)
# kalender wird NICHT gestubbt: ai.py liest kalender.RANGE_BUCKETS auf
# Modul-Ebene (in der TOOLS-Definition), ein leerer Stub wuerfe da einen
# AttributeError. Das echte kalender ist harmlos (nur json/datetime/dateutil +
# state-Logging, kein privater Graph) und laedt beim Import keine Daten.
# graph/consolidation/net/context/state bleiben gestubbt - die nutzt ai.py nur
# INNERHALB von Funktionen, nie auf Modul-Ebene.
for _m in ("net", "context", "graph", "consolidation", "state"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)

try:
    import ai  # noqa: E402  (Import nach sys.path/Stub-Setup, das ist Absicht)
except Exception as exc:  # pragma: no cover - Diagnose-Hilfe
    print(f"FEHLER: konnte core/ai.py nicht importieren: {exc}")
    print("(Stub-Import-Trick gebrochen? Dann TOOLS/Prompt von Hand setzen.)")
    sys.exit(1)

TOOLS = ai.TOOLS
# System-Prompt = Persona + Meta-Regeln, exakt wie im echten Chat-Pfad
# zusammengesetzt (siehe core/ai.py: _SYSTEM_PROMPT dann _CAPABILITIES_PROMPT).
SYSTEM = ai._SYSTEM_PROMPT + "\n\n" + ai._CAPABILITIES_PROMPT
NUM_CTX = ai.OLLAMA_NUM_CTX
OLLAMA_URL = ai.OLLAMA_URL


# ── Testfaelle ────────────────────────────────────────────────────────────
# (label, prompt, expected_tool)
#   expected_tool = Name des Tools das feuern SOLL, oder None fuer "reiner
#   Chat, KEIN Tool darf feuern". Deckt alle 5 ZENTRALE-Tools ab plus zwei
#   Nicht-Tool-Faelle fuer die Falsch-Positiv-Rate.
CASES = [
    ("list_files",
     "Welche Dateien kannst du eigentlich alles lesen?",
     "list_files"),
    ("read_file",
     "Lies die Datei memory/setup.md und sag mir in einem Satz worum's geht.",
     "read_file"),
    ("read_calendar",
     "Was hatte ich letzten Monat alles an Terminen im Kalender?",
     "read_calendar"),
    ("add_entry",
     "Trag mir bitte einen Termin ein: Zahnarzt am 12. Juni um 9:00 Uhr.",
     "add_calendar_entry"),
    ("add_routine",
     "Ich hab jeden Dienstag um 18 Uhr Geige - trag das als Routine ein.",
     "add_calendar_routine"),
    ("chat_opinion",
     "Was haeltst du eigentlich von Regenwetter? Kurz.",
     None),
    ("chat_smalltalk",
     "Wie laeuft dein Tag bisher so?",
     None),
]


def http_post(url, payload, timeout):
    """Ein /api/chat-Call gegen Ollama, JSON rein, JSON raus."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def supports_thinking(model):
    """qwen3 und qwen3.5 haben einen Thinking-Modus, qwen2.5 nicht.
    Ollama wirft 400 wenn man `think` an ein Nicht-Thinking-Modell schickt -
    deshalb das Feld nur fuer qwen3* setzen."""
    return model.startswith("qwen3")


def one_call(model, prompt, think):
    """
    Ein Tool-Call-Versuch. Gibt ein Dict mit den Messwerten zurueck:
      fired       : Name des gefeuerten Tools (erster tool_call) oder None
      leaked      : True wenn KEIN tool_call kam, aber der content nach einem
                    durchgerutschten Tool-Call aussieht (qwen3.5-Bug-Signatur)
      gen_tps     : Generierungs-Tempo in tok/s
      ttft_s      : Time-to-first-token in Sekunden (Load + Prompt-Processing)
      content     : die Textantwort (gekuerzt geloggt)
      error       : Fehlertext oder None
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "tools": TOOLS,
        "stream": False,
        "keep_alive": "5m",
        # temperature 0 -> deterministische Tool-Entscheidung, fairer Vergleich.
        # num_ctx identisch zum Produktiv-Pfad, sonst clampt Ollama klein.
        "options": {"num_ctx": NUM_CTX, "temperature": 0},
    }
    if supports_thinking(model):
        payload["think"] = think

    try:
        resp = http_post(OLLAMA_URL + "/api/chat", payload, timeout=300)
    except Exception as exc:
        return {"error": str(exc), "fired": None, "leaked": False,
                "gen_tps": 0.0, "ttft_s": 0.0, "content": ""}

    msg = resp.get("message", {})
    tool_calls = msg.get("tool_calls") or []
    content = msg.get("content", "") or ""

    fired = None
    if tool_calls:
        fired = tool_calls[0].get("function", {}).get("name")

    # Leak-Heuristik: kein strukturierter tool_call, aber der Text riecht nach
    # einem (JSON mit "name"/"arguments" oder dem Wort tool_call). Das ist die
    # Signatur des qwen3.5-Ollama-Bugs - Modell WOLLTE ein Tool, Parser hat's
    # nicht gegriffen, es landet als Text beim User.
    leaked = False
    if not tool_calls:
        low = content.lower()
        if ('"arguments"' in low or "tool_call" in low or
                ('"name"' in low and "{" in low)):
            leaked = True

    # Timings kommen als Nanosekunden zurueck.
    eval_count = resp.get("eval_count", 0)
    eval_dur = resp.get("eval_duration", 0) or 1          # ns, /0 vermeiden
    prompt_dur = resp.get("prompt_eval_duration", 0)      # ns
    load_dur = resp.get("load_duration", 0)               # ns (warm ~ 0)

    gen_tps = eval_count / (eval_dur / 1e9)
    ttft_s = (load_dur + prompt_dur) / 1e9

    return {"error": None, "fired": fired, "leaked": leaked,
            "gen_tps": gen_tps, "ttft_s": ttft_s, "content": content}


def ollama_ps_line(model):
    """Die `ollama ps`-Zeile fuer dieses Modell (zeigt SIZE + CPU/GPU-Split).
    Roh zurueckgegeben - das Format ist spaltig und nicht stabil genug zum
    sauberen Parsen, fuers Auge reicht die Zeile."""
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception as exc:
        return f"(ollama ps fehlgeschlagen: {exc})"
    for line in out.splitlines():
        if line.startswith(model.split(":")[0]):
            return " ".join(line.split())
    return "(Modell nicht in ollama ps gefunden)"


def bench_model(model, repeats, think):
    """Alle Faelle x `repeats` gegen ein Modell, aggregiert."""
    print(f"\n{'='*64}\nMODELL: {model}  (think={think if supports_thinking(model) else 'n/a'})\n{'='*64}")

    # Warmup: ein Call laedt das Modell in den VRAM, damit der erste echte
    # Fall keinen Kaltstart-Ausreisser misst. Ergebnis verworfen.
    print("  Warmup (laedt Modell in VRAM) ...")
    warm = one_call(model, "Sag kurz hallo.", think)
    if warm["error"]:
        print(f"  -> FEHLER beim Warmup: {warm['error']}")
        print(f"     Modell gepullt? `ollama pull {model}`")
        return None

    vram = ollama_ps_line(model)
    print(f"  VRAM/Processor: {vram}")

    tool_runs = 0          # Faelle die ein Tool brauchen (Zaehler-Nenner)
    tool_ok = 0            # davon: richtiges Tool gefeuert
    tool_leak = 0          # davon: als Text geleakt (Bug-Signatur)
    nofunc_runs = 0        # reine Chat-Faelle
    nofunc_false = 0       # davon: faelschlich ein Tool gefeuert
    tps_all = []
    ttft_all = []
    per_case = []

    for label, prompt, expected in CASES:
        ok = leak = false_pos = 0
        for _ in range(repeats):
            r = one_call(model, prompt, think)
            if r["error"]:
                print(f"  [{label}] FEHLER: {r['error']}")
                continue
            tps_all.append(r["gen_tps"])
            ttft_all.append(r["ttft_s"])
            if expected is not None:
                tool_runs += 1
                if r["fired"] == expected:
                    tool_ok += 1
                    ok += 1
                elif r["leaked"]:
                    tool_leak += 1
                    leak += 1
            else:
                nofunc_runs += 1
                if r["fired"] is not None:
                    nofunc_false += 1
                    false_pos += 1

        if expected is not None:
            note = f"ok {ok}/{repeats}"
            if leak:
                note += f"  GELEAKT {leak}"
            print(f"  [{label:14}] erwartet {expected:20} -> {note}")
        else:
            print(f"  [{label:14}] kein Tool erwartet      -> "
                  f"falsch gefeuert {false_pos}/{repeats}")
        per_case.append({"label": label, "expected": expected,
                         "ok": ok, "leak": leak, "false_pos": false_pos})

    avg_tps = sum(tps_all) / len(tps_all) if tps_all else 0
    avg_ttft = sum(ttft_all) / len(ttft_all) if ttft_all else 0

    summary = {
        "model": model,
        "think": think if supports_thinking(model) else None,
        "vram": vram,
        "tool_reliability": tool_ok / tool_runs if tool_runs else 0,
        "tool_leaked": tool_leak,
        "false_positive_rate": nofunc_false / nofunc_runs if nofunc_runs else 0,
        "avg_gen_tps": avg_tps,
        "avg_ttft_s": avg_ttft,
        "per_case": per_case,
    }
    return summary


def main():
    ap = argparse.ArgumentParser(description="ZENTRALE Modell-Benchmark")
    ap.add_argument("--models", nargs="+",
                    default=["qwen2.5:14b", "qwen3:14b", "qwen3.5:9b"],
                    help="Modelle (muessen gepullt sein)")
    ap.add_argument("--repeats", type=int, default=3,
                    help="Wiederholungen pro Fall (Default 3)")
    ap.add_argument("--think", action="store_true",
                    help="Thinking-Modus AN fuer qwen3* (Default: aus = "
                         "schneller, fuer Voice-Use-Case)")
    args = ap.parse_args()

    print(f"Ollama:   {OLLAMA_URL}")
    print(f"num_ctx:  {NUM_CTX}")
    print(f"Tools:    {[t['function']['name'] for t in TOOLS]}")
    print(f"Modelle:  {args.models}")
    print(f"Repeats:  {args.repeats}   Thinking: {args.think}")

    results = []
    for model in args.models:
        s = bench_model(model, args.repeats, args.think)
        if s:
            results.append(s)

    # ── Abschluss-Tabelle ─────────────────────────────────────────────────
    print(f"\n\n{'#'*72}\n# ERGEBNIS\n{'#'*72}")
    print(f"{'Modell':16} {'Tool-OK':>8} {'Leaks':>6} {'Falsch+':>8} "
          f"{'tok/s':>7} {'TTFT s':>7}")
    print("-" * 60)
    for s in results:
        print(f"{s['model']:16} "
              f"{s['tool_reliability']*100:7.0f}% "
              f"{s['tool_leaked']:6} "
              f"{s['false_positive_rate']*100:7.0f}% "
              f"{s['avg_gen_tps']:7.1f} "
              f"{s['avg_ttft_s']:7.2f}")
    print("\nVRAM/Processor:")
    for s in results:
        print(f"  {s['model']:16} {s['vram']}")

    # Vollergebnis als JSON ablegen (Zeitstempel im Namen, kein Ueberschreiben).
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(_HERE, f"bench_results_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)
    print(f"\nVollergebnis: {out_path}")


if __name__ == "__main__":
    main()
