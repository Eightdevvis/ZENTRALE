#!/usr/bin/env python3
"""
Reasoning-Benchmark fuer ZENTRALE: qwen3:14b vs qwen3.5:9b
==========================================================

Frage die das beantwortet: "Ist das kleine 9B beim ECHTEN Denken (Logik,
Mehrschritt-Mathe, Schlussfolgern, Sprachverstaendnis) genauso stark wie das
14B – oder nur schneller?" Der Tool-Bench (bench_models.py) hat nur die
Mechanik gemessen (feuert ein Tool-Call), nicht die Intelligenz.

Methodik:
- Deutsche Aufgaben, gemischt aus:
    * objektiv pruefbar (Mathe, Logik-Deduktion, Constraint, Trick-Fragen) –
      es gibt EINE richtige Antwort, die im Report als `erwartet` steht.
    * offen/qualitativ (Spracherklaerung, Kausal-Reasoning) – wird beim
      Lesen beurteilt, nicht maschinell.
- **Thinking-Modus AN** (Default): qwen3/qwen3.5 koennen vor der Antwort
  "nachdenken". Genau da zeigt sich Reasoning-Faehigkeit. `--no-think`
  schaltet's ab (testet den schnellen Modus den der Voice-Use-Case nutzen
  wuerde). Mit `--both` laufen beide Modi.
- **Neutraler System-Prompt**, NICHT die knappe ZENTRALE-Persona: die
  verbietet Schritt-fuer-Schritt ("so kurz wie moeglich") und wuerde
  Reasoning kuenstlich verschlechtern. Hier testen wir die Faehigkeit, nicht
  den App-Stil.
- temperature=0 (deterministisch), num_ctx=8192 wie in Produktion.

Output: ein lesbarer Markdown-Report mit pro Aufgabe der erwarteten Loesung
und den Antworten BEIDER Modelle untereinander – zum Selber-Vergleichen und
zum Beurteilen. Plus eine Timing-Zeile (Thinking kostet Tokens/Zeit).

Aufruf:
  venv/bin/python scripts/bench_reasoning.py              # think=True
  venv/bin/python scripts/bench_reasoning.py --no-think
  venv/bin/python scripts/bench_reasoning.py --both
  venv/bin/python scripts/bench_reasoning.py --models qwen3:14b qwen3.5:9b
"""

import argparse
import json
import os
import time
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))

# Neutraler Prompt: erlaubt Nachdenken/Begruenden, gibt nur Sprache + Format
# vor. KEINE "fasse dich kurz"-Regel (die wuerde Reasoning sabotieren).
SYSTEM = (
    "Du bist ein praeziser, sorgfaeltiger Assistent. Antworte auf Deutsch. "
    "Denke das Problem gruendlich durch und nenne am Ende klar das Ergebnis."
)

# ── Aufgaben ───────────────────────────────────────────────────────────────
# (id, kategorie, prompt, erwartet)
#   erwartet = die korrekte Loesung (fuer objektive Faelle), oder eine kurze
#   Beurteilungs-Notiz (fuer offene Faelle, Praefix "BEURTEILEN:").
CASES = [
    ("zwei_zuege", "Mathe/mehrschritt",
     "Ein Zug faehrt um 14:00 Uhr mit 90 km/h los. Ein zweiter Zug startet um "
     "14:30 Uhr vom selben Ort mit 120 km/h in dieselbe Richtung. Um wie viel "
     "Uhr holt der zweite Zug den ersten ein?",
     "16:00 Uhr (45 km Vorsprung / 30 km/h Differenz = 1,5 h ab 14:30)."),

    ("alters_reihenfolge", "Logik/Deduktion",
     "Anna ist aelter als Ben. Carla ist juenger als Ben, aber aelter als Dora. "
     "Wer ist am zweitaeltesten?",
     "Ben (Reihenfolge: Anna > Ben > Carla > Dora)."),

    ("getraenke_puzzle", "Logik/Constraint",
     "Tim, Udo und Vera trinken je ein anderes Getraenk: Tee, Kaffee oder "
     "Wasser. Tim trinkt keinen Kaffee. Vera trinkt Wasser. Wer trinkt Kaffee?",
     "Udo (Vera=Wasser, Tim=Tee, also Udo=Kaffee)."),

    ("schlaeger_ball", "Trick/CRT",
     "Ein Schlaeger und ein Ball kosten zusammen 1,10 Euro. Der Schlaeger "
     "kostet 1,00 Euro mehr als der Ball. Was kostet der Ball?",
     "0,05 Euro (NICHT 0,10 - haeufiger Intuitionsfehler)."),

    ("maschinen", "Trick/Rate",
     "Wenn 3 Maschinen in 3 Minuten 3 Teile herstellen, wie lange brauchen "
     "100 Maschinen fuer 100 Teile?",
     "3 Minuten (jede Maschine macht 1 Teil in 3 Min - NICHT 100)."),

    ("wasserkrug", "Planung/Mehrschritt",
     "Du hast einen 3-Liter-Krug und einen 5-Liter-Krug und unbegrenzt Wasser, "
     "aber keine weiteren Messmarken. Wie misst du genau 4 Liter ab? "
     "Beschreibe die Schritte.",
     "Korrekte Schrittfolge, z.B.: 5L fuellen -> in 3L giessen (2L bleiben im "
     "5L) -> 3L leeren -> 2L in 3L giessen -> 5L fuellen -> aus 5L den 3L "
     "auffuellen (nur 1L passt) -> im 5L bleiben 4L."),

    ("blumen_logik", "Logik/Syllogismus",
     "Alle Blumen im Garten sind entweder rot oder gelb. Keine gelbe Blume "
     "duftet. Manche rote Blumen duften, manche nicht. Eine bestimmte Blume im "
     "Garten duftet nicht. Welche Farbe kann sie haben - kann man es sicher "
     "sagen?",
     "Nein, nicht sicher: nicht-duftend kann rot ODER gelb sein (gelbe duften "
     "nie, manche rote auch nicht). Wer 'gelb' oder 'rot' als sicher behauptet, "
     "liegt falsch."),

    ("schrauben", "Mathe/mehrschritt",
     "Sasha kauft 3 Packungen Schrauben mit je 24 Stueck. Fuer ein Regal "
     "verbraucht sie 17 Schrauben, fuer zwei Stuehle je 8. Wie viele Schrauben "
     "bleiben uebrig?",
     "39 (72 - 17 - 16 = 39)."),

    ("staedte_constraint", "Instruction-Following",
     "Nenne genau drei deutsche Staedte, deren Name mit einem Vokal beginnt und "
     "die NICHT Landeshauptstadt sind. Gib nur die drei Namen als Liste aus, "
     "sonst nichts.",
     "BEURTEILEN: 3 Staedte, jede beginnt mit a/e/i/o/u, keine ist "
     "Landeshauptstadt (z.B. Augsburg, Essen, Ulm). Format: nur die Liste. "
     "Auf Constraint-Treue + Format achten."),

    ("umfahren", "Sprache/Semantik",
     "Das deutsche Wort 'umfahren' hat zwei gegensaetzliche Bedeutungen je nach "
     "Betonung. Erklaere beide und gib fuer jede einen Beispielsatz.",
     "BEURTEILEN: 'UMfahren' (trennbar) = ueber den Haufen fahren / "
     "niederfahren; 'umFAHREN' (untrennbar) = darum herumfahren / ausweichen. "
     "Beide Bedeutungen + passende Beispielsaetze."),

    ("kausal_glas", "Kausal/Common-Sense",
     "Ein volles Wasserglas steht direkt an der Tischkante. Eine Katze springt "
     "auf den Tisch und laeuft zielstrebig darauf zu. Was passiert "
     "wahrscheinlich, und nenne zwei Gruende warum.",
     "BEURTEILEN: Glas faellt/kippt -> Wasser + evtl. Scherben; plausible "
     "Gruende (Randlage = wenig Halt, Katzen stossen Dinge, Gewicht/Schwung). "
     "Auf Sinnhaftigkeit + zwei echte Gruende achten."),
]


def supports_thinking(model):
    return model.startswith("qwen3")


def http_post(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(model, prompt, think):
    """Eine Reasoning-Anfrage. Gibt (content, thinking_text, gen_tps, wall_s)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_ctx": NUM_CTX, "temperature": 0},
    }
    if supports_thinking(model):
        payload["think"] = think

    t0 = time.perf_counter()
    try:
        resp = http_post(OLLAMA_URL + "/api/chat", payload, timeout=600)
    except Exception as exc:
        return (f"(FEHLER: {exc})", "", 0.0, time.perf_counter() - t0)
    wall = time.perf_counter() - t0

    msg = resp.get("message", {})
    content = (msg.get("content") or "").strip()
    thinking = (msg.get("thinking") or "").strip()   # Ollama legt Denken hier ab

    eval_count = resp.get("eval_count", 0)
    eval_dur = resp.get("eval_duration", 0) or 1
    gen_tps = eval_count / (eval_dur / 1e9)
    return (content, thinking, gen_tps, wall)


def run(models, think_modes):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"reasoning_results_{stamp}.md")
    lines = [f"# Reasoning-Benchmark {stamp}",
             f"Modelle: {', '.join(models)}  |  num_ctx={NUM_CTX}  |  temp=0",
             ""]

    for think in think_modes:
        mode = "THINKING AN" if think else "THINKING AUS"
        print(f"\n########## MODUS: {mode} ##########")
        lines.append(f"\n## Modus: {mode}\n")

        # Phase 1 - Antworten sammeln, MODELL-AUSSEN: jedes Modell wird nur
        # EINMAL geladen und beantwortet alle Fragen, bevor das naechste dran
        # ist. Sonst muesste Ollama bei jedem Aufruf zwischen 14b und 9b
        # hin- und herladen (passen nicht beide gleichzeitig in 12 GB) -> ein
        # ~9-GB-Reload pro Call = Eviction-Thrash. So: ein Reload pro Modell.
        answers = {}  # (cid, model) -> (content, thinking, tps, wall)
        for model in models:
            print(f"\n--- Modell {model} ({mode}) ---")
            for cid, cat, prompt, erwartet in CASES:
                content, thinking, tps, wall = ask(model, prompt, think)
                answers[(cid, model)] = (content, thinking, tps, wall)
                print(f"  [{cid:18}] {wall:5.1f}s  {tps:4.0f} tok/s  "
                      f"think={len(thinking)}z")

        # Phase 2 - Report nach Frage gruppiert (beide Modelle untereinander
        # = direkter Vergleich), aus den gesammelten Antworten.
        for cid, cat, prompt, erwartet in CASES:
            lines.append(f"### [{cat}] {cid}")
            lines.append(f"**Frage:** {prompt}\n")
            lines.append(f"**Erwartet/Beurteilung:** {erwartet}\n")
            for model in models:
                content, thinking, tps, wall = answers[(cid, model)]
                think_note = (f" _(Thinking: {len(thinking)} Zeichen)_"
                              if thinking else "")
                lines.append(f"**{model}** ({wall:.1f}s, {tps:.0f} tok/s)"
                             f"{think_note}:\n\n{content}\n")
            lines.append("")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"\n\nReport: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="ZENTRALE Reasoning-Benchmark")
    ap.add_argument("--models", nargs="+",
                    default=["qwen3:14b", "qwen3.5:9b"])
    ap.add_argument("--no-think", action="store_true",
                    help="Thinking AUS (schneller Modus)")
    ap.add_argument("--both", action="store_true",
                    help="Beide Modi (think an UND aus) nacheinander")
    args = ap.parse_args()

    if args.both:
        modes = [True, False]
    elif args.no_think:
        modes = [False]
    else:
        modes = [True]

    print(f"Ollama:  {OLLAMA_URL}   num_ctx: {NUM_CTX}")
    print(f"Modelle: {args.models}   Modi: "
          f"{['think' if m else 'no-think' for m in modes]}")
    run(args.models, modes)


if __name__ == "__main__":
    main()
