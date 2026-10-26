#!/usr/bin/env python3
"""
Probelauf: Werkzeug-Suche mit defer_loading und EIGENEM Suchwerkzeug
(Schritt 1 des Bauplans, memory/ki/werkzeug_suche.md).

Klärt gegen die echte API (claude-sonnet-5), bevor der Kern es benutzt:

  A  Ein tool_result mit GEMISCHTEM Inhalt (Text + tool_reference) wird
     angenommen, und das Modell ruft danach das gefundene Werkzeug.
  B  Ein tool_result NUR aus tool_reference-Blöcken.
  C  cache_read: bleibt der Präfix (Werkzeuge + System) über die Runde mit
     dem Suchergebnis gecacht?
  D  Ein Verlauf, in dem ein zurückgestelltes Werkzeug schon aufgerufen
     wurde (Suchaufruf + Ergebnis wieder eingesetzt, Schritt 7), wird in
     einem NEUEN Zug angenommen.

Kosten: wenige kurze Aufrufe, effort low. Die Zahlen druckt das Skript am
Ende (Tokens und € nach core/prices.py). Der Key kommt wie überall aus
data/ai_config.json (ZENTRALE_AI_CONFIG_DIR, falls aus einem Worktree) —
er wird nie ausgegeben.

Aufruf:  venv/bin/python scripts/werkzeug_suche_probe.py [--nur A|B|C|D]
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import ai_config  # noqa: E402,F401 — Import-Effekt: Keys in die Env
import prices     # noqa: E402

MODELL = "claude-sonnet-5"
_SUMME = {"in": 0, "out": 0, "rd": 0, "wr": 0, "eur": 0.0}

# Fester System-Text, lang genug für den Cache (Sonnet: ab 1024 Token).
SYSTEM = ("Du bist ein Assistent mit Werkzeugen. Viele Werkzeuge sind erst "
          "nach einer Suche mit search_tools verfügbar: such zuerst, ruf dann "
          "das gefundene Werkzeug. Antworte kurz auf Deutsch.\n\n"
          + "\n".join(f"Regel {i}: Bleib sachlich, nenne nur, was ein Werkzeug "
                      f"geliefert hat, und erfinde keine Werte (Nr. {i})."
                      for i in range(1, 90)))

SUCHE = {
    "name": "search_tools",
    "description": ("Sucht Werkzeuge, die noch nicht geladen sind, nach "
                    "Stichworten. Danach stehen die gefundenen Werkzeuge zur "
                    "Verfügung."),
    "input_schema": {"type": "object",
                     "properties": {"query": {"type": "string"}},
                     "required": ["query"]},
}
UHR = {"name": "read_time", "description": "Liest die aktuelle Uhrzeit.",
       "input_schema": {"type": "object", "properties": {}}}
WETTER = {"name": "get_weather", "description": "Wetter für eine Stadt.",
          "input_schema": {"type": "object",
                           "properties": {"stadt": {"type": "string"}},
                           "required": ["stadt"]},
          "defer_loading": True}
TABELLE = {"name": "read_xlsx", "description": "Liest eine Excel-Tabelle.",
           "input_schema": {"type": "object",
                            "properties": {"name": {"type": "string"}},
                            "required": ["name"]},
           "defer_loading": True}
TOOLS = [UHR, SUCHE, WETTER, TABELLE]


def _client():
    import anthropic
    return anthropic.Anthropic()


def _rufen(client, msgs, titel):
    import anthropic
    try:
        r = client.messages.create(
            model=MODELL, max_tokens=2000,
            system=[{"type": "text", "text": SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            tools=TOOLS, messages=msgs,
            thinking={"type": "adaptive"}, output_config={"effort": "low"})
    except anthropic.APIStatusError as e:
        print(f"  [{titel}] HTTP {e.status_code}: {e.message}")
        return None
    u = r.usage
    rd = u.cache_read_input_tokens or 0
    wr = u.cache_creation_input_tokens or 0
    eur = prices.euro(MODELL, input_tokens=u.input_tokens,
                      output_tokens=u.output_tokens, cache_read=rd, cache_write=wr,
                      cache_ttl="5m")   # Breakpoint oben ohne ttl = 5 min
    for k, v in (("in", u.input_tokens), ("out", u.output_tokens), ("rd", rd), ("wr", wr)):
        _SUMME[k] += v
    _SUMME["eur"] += eur
    bloecke = [(b.type, getattr(b, "name", None) or (getattr(b, "text", "") or "")[:80])
               for b in r.content]
    print(f"  [{titel}] stop={r.stop_reason} in={u.input_tokens} cache_read={rd} "
          f"cache_write={wr} out={u.output_tokens} ≈{eur:.4f}€")
    print(f"      Blöcke: {bloecke}")
    return r


def _tool_use(r):
    return next((b for b in r.content if b.type == "tool_use"), None)


def lauf(art: str):
    """art 'A' = Text + tool_reference, 'B' = nur tool_reference."""
    client = _client()
    msgs = [{"role": "user", "content": "Wie ist das Wetter gerade in Bremen?"}]
    r1 = _rufen(client, msgs, f"{art}1 Frage")
    if r1 is None:
        return None
    t = _tool_use(r1)
    if not t or t.name != "search_tools":
        print(f"  [{art}] kein search_tools-Aufruf: {t and t.name}")
        return None
    ref = {"type": "tool_reference", "tool_name": "get_weather"}
    inhalt = ([{"type": "text", "text": "1 Treffer: get_weather (Wetter)."}, ref]
              if art == "A" else [ref])
    msgs += [{"role": "assistant", "content": r1.content},
             {"role": "user", "content": [{"type": "tool_result",
                                           "tool_use_id": t.id, "content": inhalt}]}]
    r2 = _rufen(client, msgs, f"{art}2 nach Suche")
    if r2 is None:
        return None
    t2 = _tool_use(r2)
    print(f"  [{art}] ruft danach: {t2 and t2.name} {t2 and json.dumps(t2.input, ensure_ascii=False)}")
    if not t2 or t2.name != "get_weather":
        return msgs
    msgs += [{"role": "assistant", "content": r2.content},
             {"role": "user", "content": [{"type": "tool_result", "tool_use_id": t2.id,
                                           "content": "Bremen: 12 °C, Nieselregen."}]}]
    r3 = _rufen(client, msgs, f"{art}3 Antwort")
    if r3 is not None:
        msgs.append({"role": "assistant", "content": r3.content})
    return msgs


def lauf_d(verlauf):
    """Neuer Zug auf einem Verlauf, der Suche + Aufruf schon enthält."""
    client = _client()
    msgs = list(verlauf) + [{"role": "user", "content": "Und in Hamburg?"}]
    r = _rufen(client, msgs, "D neuer Zug")
    if r is not None:
        t = _tool_use(r)
        print(f"  [D] ruft: {t and t.name} (ohne neue Suche = Freischaltung hält)")


def lauf_e():
    """E: tool_reference auf ein NICHT zurückgestelltes Werkzeug, danach ein
    tool_result mit Text-Block daneben (wie nachricht_anhaengen)."""
    client = _client()
    msgs = [{"role": "user", "content": "Wie spät ist es? Such dafür erst mit "
                                        "search_tools nach 'uhr'."}]
    r = _rufen(client, msgs, "E1")
    t = r and _tool_use(r)
    if not t or t.name != "search_tools":
        print(f"  [E] kein search_tools: {t and t.name}")
        return
    msgs += [{"role": "assistant", "content": r.content},
             {"role": "user", "content": [{"type": "tool_result", "tool_use_id": t.id,
                                           "content": [{"type": "tool_reference",
                                                        "tool_name": "read_time"}]}]}]
    r2 = _rufen(client, msgs, "E2 Referenz auf geladenes Werkzeug")
    t2 = r2 and _tool_use(r2)
    if not t2:
        return
    msgs += [{"role": "assistant", "content": r2.content},
             {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": t2.id, "content": "14:05"},
                 {"type": "text", "text": "(Hinweis: kurz antworten.)"}]}]
    _rufen(client, msgs, "E3 tool_result + Text daneben")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nur", choices=list("ABCDE"))
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Kein ANTHROPIC_API_KEY (ZENTRALE_AI_CONFIG_DIR setzen?).")
    print(f"Modell {MODELL}, System {len(SYSTEM)} Zeichen\n")
    verlauf = None
    if a.nur in (None, "A", "C"):
        print("A: Text + tool_reference gemischt (C: cache_read je Runde)")
        verlauf = lauf("A")
    if a.nur in (None, "B", "D"):
        print("\nB: nur tool_reference")
        verlauf = lauf("B") or verlauf
    if a.nur in (None, "D") and verlauf:
        print("\nD: neuer Zug auf dem Verlauf mit Suche")
        lauf_d(verlauf)
    if a.nur in (None, "E"):
        print("\nE: Referenz auf geladenes Werkzeug")
        lauf_e()
    s = _SUMME
    print(f"\nSumme: in={s['in']} out={s['out']} cache_read={s['rd']} "
          f"cache_write={s['wr']} ≈{s['eur']:.4f}€")


if __name__ == "__main__":
    main()
