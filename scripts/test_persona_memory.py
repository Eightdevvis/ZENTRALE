#!/usr/bin/env python3
# scripts/test_persona_memory.py
#
# Regression für das Persona-Gedächtnis (Sprach-Tutor). Prüft die Teile, die
# OHNE Ollama testbar sind: den Multi-Store des Konzept-Graphen (Isolation
# Persona ↔ Core), den Persona-Kontext-Renderer, den History-Roundtrip und das
# Persona-Portal (Ling Ling, kein Lehrer, kein Fake-Mensch).
#
# Embeddings werden gestubbt → kein laufender Ollama/bge-m3 nötig. Der reale
# LLM-Extraktor (consolidation) wird hier NICHT getestet (braucht Ollama); den
# deckt scripts/test_graph_memory.py ab, sobald ein Modell läuft.
#
# Aufruf:  venv/bin/python scripts/test_persona_memory.py
# Exit-Code = Anzahl Fehler.

import os
import sys
import json
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import embeddings
# Anker Sasha/Heute laufen über exakten Namens-Match, nicht über Embedding →
# None-Stub reicht und hält den Test service-frei.
embeddings.embed_document = lambda t: None
embeddings.embed_query    = lambda t: None

import graph
import persona_memory
import tutor_langs

_fails = 0


def check(name, cond):
    global _fails
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        _fails += 1


def main():
    tmp = tempfile.mkdtemp(prefix='persona_mem_test_')
    core_file = os.path.join(tmp, 'ai_graph.json')
    pers_file = os.path.join(tmp, 'persona_mem_zh.json')
    graph._GRAPH_FILE = core_file
    persona_memory._DATA_DIR = tmp

    try:
        # ── Store-Isolation: Persona-Turn landet NUR im Persona-Graphen ──
        graph.add_turn_extraction(
            nodes_in=[{"name": "Sasha", "type": "person"},
                      {"name": "Klausur", "type": "event"}],
            edges_in=[{"from": "Sasha", "to": "Klausur", "rel": "hat"}],
            store=pers_file)
        check("persona-store angelegt", os.path.exists(pers_file))
        check("core-store NICHT angelegt", not os.path.exists(core_file))

        # ── Core-Turn landet NUR im Core-Graphen ──
        graph.add_turn_extraction(
            nodes_in=[{"name": "Sasha", "type": "person"},
                      {"name": "Pi", "type": "object"}],
            edges_in=[{"from": "Sasha", "to": "Pi", "rel": "besitzt"}],
            store=None)
        pdata = json.load(open(pers_file, encoding='utf-8'))
        cdata = json.load(open(core_file, encoding='utf-8'))
        check("kein Leak Core→Persona (kein Pi)", "Pi" not in pdata["nodes"])
        check("kein Leak Persona→Core (keine Klausur)", "Klausur" not in cdata["nodes"])

        # ── Persona-Kontext-Renderer ──
        ctx = graph.context_for_persona("was ist mit sasha",
                                        store=pers_file, persona_name="Ling Ling")
        check("kontext nennt Klausur", "Klausur" in ctx)
        check("kontext framing 'über Sasha'", "über Sasha" in ctx)
        check("kontext ohne KI-Capability-Block", "Das kannst DU" not in ctx)

        # ── persona_memory Fassade + History-Roundtrip ──
        check("mem_path lang-spezifisch",
              persona_memory.mem_path("zh").endswith("persona_mem_zh.json"))
        hist = [{"role": "assistant", "content": "你好"},
                {"role": "user", "content": "hallo"}]
        persona_memory.save_history(hist, lang="zh")
        check("history roundtrip", persona_memory.load_history(lang="zh") == hist)
        check("mem_stats liest persona-store",
              persona_memory.mem_stats("zh")["nodes"] >= 2)

        # ── Persona-Portal: Charakter statt Lehrer ──
        p = tutor_langs.get("zh")
        check("persona Ling Ling", p.get("persona_name") == "Ling Ling")
        sp = p["system_prompt"]
        check("prompt: kein Lehrer", "KEIN Lehrer" in sp)
        check("prompt: kein Fake-Mensch", "KEIN FAKE-MENSCH" in sp)
        check("prompt: Vokabel-Mechanik erhalten", "get_confirmed_vocab" in sp)

        # ── Kapazitätsbasierte Backend-Wahl (Ollama daheim ODER Cloud) ──
        import ai_backends
        captured = {}
        def fake_extract(u, a, store=None, mirror_calendar=True,
                         backend=None, provider=None, model=None):
            captured.clear()
            captured.update(backend=backend, provider=provider, store=store,
                            mirror_calendar=mirror_calendar)
        orig_extract = persona_memory.consolidation.extract_turn_into_graph
        orig_status  = ai_backends.status
        persona_memory.consolidation.extract_turn_into_graph = fake_extract
        try:
            ai_backends.status = lambda *a, **k: {"local": True, "cloud": True, "cloud_provider": "qwen"}
            persona_memory.remember("ich hab morgen klausur", "加油", lang="zh",
                                    provider="qwen", model="qwen-plus")
            check("local da → backend local", captured.get("backend") == "local")
            check("persona-turn spiegelt NICHT in kalender", captured.get("mirror_calendar") is False)

            ai_backends.status = lambda *a, **k: {"local": False, "cloud": True, "cloud_provider": "qwen"}
            persona_memory.remember("ich hab morgen klausur", "加油", lang="zh",
                                    provider="qwen", model="qwen-plus")
            check("kein Ollama, cloud da → backend cloud", captured.get("backend") == "cloud")
            check("cloud → provider gesetzt", captured.get("provider") == "qwen")

            captured.clear()
            ai_backends.status = lambda *a, **k: {"local": False, "cloud": False, "cloud_provider": None}
            persona_memory.remember("ich hab morgen klausur", "加油", lang="zh")
            check("kein backend → verdichtung uebersprungen", captured == {})
        finally:
            persona_memory.consolidation.extract_turn_into_graph = orig_extract
            ai_backends.status = orig_status
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + ("ALLE GRÜN" if _fails == 0 else f"{_fails} FEHLER"))
    return _fails


if __name__ == "__main__":
    sys.exit(main())
