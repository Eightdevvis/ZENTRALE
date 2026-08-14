#!/usr/bin/env python3
"""
Live-Rauchtest für den Cloud-Kern — der erste ECHTE API-Call.

Bedient beide Dialekte: Anthropic (core/cloud.py) und OpenAI-kompatibel
(core/cloud_openai.py, also Qwen/DashScope & Co). Welcher gefahren wird,
ergibt sich aus dem konfigurierten Provider; --provider übersteuert.

Gestaffelt und billig - jede Stufe prüft eine Sache, und man sieht nach jeder,
ob es Sinn hat weiterzumachen:

  1  Erreichbarkeit  Key gültig, Modell-ID existiert, Parameter akzeptiert
  2  Prompt-Cache    zweiter identischer Turn (nur bei Anthropic messbar)
  3  Tool-Loop       ein lesendes Tool einmal komplett durch
  4  Erlaubnis-Gate  ein SCHREIBENDES Tool wird abgefangen und abgelehnt

── Was rausgeht ────────────────────────────────────────────────────────
Stufe 1+2 schicken den System-Prompt und einen Gruß. Stufe 3 schickt
zusätzlich das ERGEBNIS des Tools. Default ist deshalb `list_files` (nur
Dateinamen aus der Whitelist). Mit --kalender wird stattdessen read_calendar
gefahren - dann gehen echte Termine an den Anbieter. Bewusst nicht der
Default.

Aufruf (aus dem Projekt-Root):
    venv/bin/python scripts/cloud_smoke.py
    venv/bin/python scripts/cloud_smoke.py --stufe 1
    venv/bin/python scripts/cloud_smoke.py --provider qwen --kalender

Schreibt nichts und hakt nichts ab: das Erlaubnis-Gate ist hart auf "nein"
verdrahtet, damit der Test weder hängt noch etwas verändert.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _abbruch(text):
    print(f"\n  ABBRUCH: {text}\n")
    sys.exit(1)


def _sammle(stream):
    """Generator leerlaufen lassen, Events nach Typ sortiert zurückgeben."""
    text, reflect, sonst = [], [], []
    for ev in stream:
        if isinstance(ev, str):
            text.append(ev)
        elif isinstance(ev, dict) and "reflect" in ev:
            reflect.append(ev["reflect"])
        else:
            sonst.append(ev)
    return "".join(text), "".join(reflect), sonst


def _usage_zeile(protokoll):
    for zeile in reversed(protokoll):
        if "CLOUD ←" in zeile:
            return zeile
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stufe", type=int, default=0,
                    help="nur diese Stufe fahren (1-3), 0 = alle")
    ap.add_argument("--provider", default=None,
                    help="Provider erzwingen (claude, qwen, …)")
    ap.add_argument("--kalender", action="store_true",
                    help="Stufe 3 mit read_calendar statt list_files "
                         "(schickt echte Termine an den Anbieter)")
    args = ap.parse_args()

    os.environ.setdefault("ZENTRALE_MAIL", "off")

    import ai_config  # noqa: F401  - Import-Effekt: Keys aus data/ai_config.json
    import ai_backends
    import providers
    import state

    print("\n=== Cloud-Rauchtest ===\n")

    name = args.provider or providers.configured()
    if not name:
        _abbruch("Kein Cloud-Provider konfiguriert. Ein API-Key gehört in den "
                 "keys-Block von data/ai_config.json, NICHT in die "
                 "Shell-Umgebung.")
    prov = providers.get(name)
    if not prov:
        _abbruch(f"Provider '{name}' steht nicht in core/providers.py.")
    if not os.environ.get(prov.get("key_env") or ""):
        _abbruch(f"Kein Key für '{name}' ({prov.get('key_env')}).")

    kind = ai_backends.cloud_kind_for(name)
    if kind == "anthropic":
        import cloud as modul
        ruf = lambda h: modul.chat_stream(h)
        mdl, extra = modul._MODEL, f"effort {modul._EFFORT}"
    elif kind == "openai_compat":
        import cloud_openai as modul
        ruf = lambda h: modul.chat_stream(h, provider=name)
        mdl = os.environ.get("ZENTRALE_CLOUD_OPENAI_MODEL") or prov.get("default_model")
        extra = f"temp {modul._TEMP}"
    else:
        _abbruch(f"Der Kern kann mit '{name}' nicht reden (kein kind).")

    print(f"  Provider    {name}  ({kind}, {prov.get('jurisdiction')})")
    print(f"  Modell      {mdl}")
    print(f"  {extra}")
    print(f"  Graph       {modul.cloud.CLOUD_GRAPH if kind == 'openai_compat' else modul.CLOUD_GRAPH}")

    # Erlaubnis-Gate stilllegen: der Test hat keine Oberfläche zum Klicken.
    state.wait_permission = lambda: "nein"
    state.request_permission = lambda **k: None

    protokoll = []
    _echtes_log = state.push_log

    def mitschreiben(zeile):
        protokoll.append(str(zeile))
        _echtes_log(zeile)

    state.push_log = mitschreiben

    stufen = [args.stufe] if args.stufe else [1, 2, 3, 4]
    frage = "Sag in genau einem kurzen Satz Hallo."

    # ── Stufe 1 ───────────────────────────────────────────────────────
    if 1 in stufen:
        print("\n[1] Erreichbarkeit …")
        text, reflect, _ = _sammle(ruf([{"role": "user", "content": frage}]))
        if text.startswith("[Cloud-Fehler"):
            _abbruch(text)
        if not text.strip():
            _abbruch("Leere Antwort. Bei Anthropic meist: das Denken hat das "
                     "max_tokens-Budget aufgebraucht.")
        print(f"  Antwort:  {text.strip()[:200]}")
        print(f"  Denken:   {reflect.strip()[:100] + '…' if reflect else '— keine reflect-Events'}")
        if _usage_zeile(protokoll):
            print(f"  {_usage_zeile(protokoll)}")

    # ── Stufe 2 ───────────────────────────────────────────────────────
    if 2 in stufen:
        print("\n[2] Prompt-Cache …")
        if kind != "anthropic":
            print("  übersprungen - cache_control gibt es nur bei Anthropic.")
            print("  DashScope cacht implizit, ohne messbares Signal in der Antwort.")
        else:
            _sammle(ruf([{"role": "user", "content": frage}]))
            zeile = _usage_zeile(protokoll)
            print(f"  {zeile or 'kein usage-Log'}")
            if zeile and "cache_read=0 " in zeile + " ":
                print("\n  ⚠ cache_read=0 - der Cache greift NICHT.")
                print("    Der Systemblock kostet dann bei jedem Turn und jeder")
                print("    Tool-Runde den vollen Preis. Ursache ist immer, dass")
                print("    sich im statischen Block etwas pro Turn ändert.")
            elif zeile:
                print("  ✓ Cache greift.")

    # ── Stufe 3 ───────────────────────────────────────────────────────
    if 3 in stufen:
        wunsch = ("Was steht diese Woche an?" if args.kalender
                  else "Welche Dateien kannst du lesen? Nenn nur zwei.")
        print(f"\n[3] Tool-Loop … ({'read_calendar' if args.kalender else 'list_files'})")
        vorher = len(protokoll)
        text, _, sonst = _sammle(ruf([{"role": "user", "content": wunsch}]))
        if text.startswith("[Cloud-Fehler"):
            _abbruch(text)
        tool_zeilen = [z for z in protokoll[vorher:] if "TOOL" in z]
        print(f"  Antwort:  {text.strip()[:220]}")
        if tool_zeilen:
            print(f"  ✓ Tool-Loop lief ({len(tool_zeilen)} Log-Zeilen):")
            for z in tool_zeilen[:3]:
                print(f"    {z[:150]}")
        else:
            print("  ⚠ Kein Tool gerufen. Entweder reichte dem Modell der")
            print("    Kontext - oder das Tool-Schema kommt nicht an.")
        if any(isinstance(e, dict) and "permission" in e for e in sonst):
            print("  ⚠ Das Gate hat gefeuert (und wurde auf 'nein' verdrahtet).")

    # ── Stufe 4 ───────────────────────────────────────────────────────
    if 4 in stufen:
        print("\n[4] Erlaubnis-Gate (schreibendes Tool) …")
        # Das Gate ist das Stück, bei dem ein Fehler wirklich weh tut: es ist
        # das Einzige, was zwischen einem Modell-Einfall und Sashas echtem
        # Kalender steht. Ein Fake-Test reicht dafür nicht.
        # Das Tool wird HIER hart blockiert, egal was das Gate sagt - falls
        # das Gate versagt, soll trotzdem nichts geschrieben werden.
        import ai
        geschrieben = []
        echt = ai._execute_tool

        def nur_mitschreiben(name, args):
            if name in ai.PERMISSION_REQUIRED_TOOLS:
                geschrieben.append(name)
                return "(vom Rauchtest blockiert)"
            return echt(name, args)

        ai._execute_tool = nur_mitschreiben
        try:
            vorher = len(protokoll)
            text, _, sonst = _sammle(ruf([{
                "role": "user",
                "content": "Trag mir bitte morgen um 15 Uhr 'Rauchtest' in den "
                           "Kalender ein."}]))
        finally:
            ai._execute_tool = echt

        gefragt = [e for e in sonst if isinstance(e, dict) and "permission" in e]
        if gefragt:
            print(f"  ✓ Gate hat gefeuert: \"{gefragt[0]['permission']['frage'][:120]}\"")
            print("    (Antwort war 'nein' - genau wie ein Klick auf NEIN)")
        else:
            tool_zeilen = [z for z in protokoll[vorher:] if "TOOL" in z]
            if any("add_calendar" in z for z in tool_zeilen):
                print("  ⚠⚠ Das Modell hat ein Schreib-Tool gerufen und das Gate")
                print("     hat NICHT gefragt. Das ist ein echter Befund.")
            else:
                print("  — Das Modell hat gar kein Schreib-Tool gerufen; über das")
                print("    Gate sagt dieser Lauf dann nichts. Nochmal versuchen")
                print("    oder direkter formulieren.")
        if geschrieben:
            print(f"  ⚠ Ausführung wurde versucht: {geschrieben} "
                  f"(vom Rauchtest abgefangen, nichts eingetragen)")
        print(f"  Antwort:  {text.strip()[:200]}")

    print("\n=== fertig ===")
    print("Der Turn wird erst nach ~45 s Gesprächspause in den Cloud-Graphen")
    print("konsolidiert - dieses Skript endet vorher, der Graph bleibt leer.")
    print("Das ist kein Fehler.\n")


if __name__ == "__main__":
    main()
