#!/usr/bin/env python3
# tutor/test_memory.py
#
# Regression für den Sprach-Tutor. Prüft die Teile, die OHNE Backend testbar
# sind: das GROB-Gedächtnis (Notiz-Modell), die Sandbox (Persona-Store fasst den
# Core-Graphen nie an), das Persona-Portal (Ling Ling) und die kapazitätsbasierte
# Backend-Wahl.
#
# Vorgeschichte: hieß scripts/test_persona_memory.py und war auf den ALTEN
# Graph-Store gemünzt — der ist seit dem Notiz-Umbau (2026-07-10) weg, der Test
# lief seitdem auf KeyError('nodes'). Beim Ordner-Umzug (2026-07-16) auf das
# Notiz-Modell nachgezogen und hierher geholt: ein Tutor-Test gehört in tutor/,
# sonst ist der Ordner nicht allein rausziehbar.
#
# Aufruf:  venv/bin/python tutor/test_memory.py
# Exit-Code = Anzahl Fehler.

import os
import sys
import json
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)                      # tutor/ als Paket
sys.path.insert(0, os.path.join(ROOT, 'core'))  # basic core (ai, ai_backends)

from tutor import memory, langs, tools, config, providers

_fails = 0


def check(name, cond):
    global _fails
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        _fails += 1


def main():
    tmp = tempfile.mkdtemp(prefix='tutor_mem_test_')
    orig_dir = memory._DATA_DIR
    memory._DATA_DIR = tmp

    try:
        # ── Notiz-Modell: grob, gedeckelt, pro Sprache ──────────────────
        check("mem_path lang-spezifisch",
              memory.mem_path("zh").endswith("persona_mem_zh.json"))
        check("mem_path liegt in tutor/data (nicht ZENTRALE/data)",
              orig_dir.rstrip('/').endswith(os.path.join('tutor', 'data')))

        memory._save_notes({"facts": ["她在学中文"], "topics": ["考试"]}, lang="zh")
        back = memory._load_notes("zh")
        check("notiz-roundtrip", back["facts"] == ["她在学中文"]
              and back["topics"] == ["考试"])

        ctx = memory.context("考试", lang="zh")
        check("kontext nennt die notiz", "她在学中文" in ctx)
        check("kontext ist als GROB gerahmt (kein exaktes protokoll)",
              "大概" in ctx or "印象" in ctx)

        # Deckel: mehr als _MEM_MAX_FACTS wird gekappt
        memory._save_notes({"facts": [f"事实{i}" for i in range(50)],
                            "topics": [f"话题{i}" for i in range(50)]}, lang="zh")
        capped = memory._load_notes("zh")
        check("facts gedeckelt", len(capped["facts"]) <= memory._MEM_MAX_FACTS)
        check("topics gedeckelt", len(capped["topics"]) <= memory._MEM_MAX_TOPICS)

        # ── Sandbox: der Persona-Store fasst ai_graph.json NIE an ───────
        check("persona-notizen liegen im tmp-store",
              os.path.exists(os.path.join(tmp, "persona_mem_zh.json")))
        check("kein core-graph angelegt",
              not os.path.exists(os.path.join(tmp, "ai_graph.json")))
        check("memory importiert weder graph noch consolidation",
              not hasattr(memory, "graph") and not hasattr(memory, "consolidation"))

        # ── Persona-Portal: getunter zh-Prompt (chinesisch, schlank) ────
        p = langs.get("zh")
        check("persona Ling Ling", p.get("persona_name") == "Ling Ling")
        sp = p["system_prompt"]
        # Der Prompt ist SELBST auf Chinesisch verfasst — das ist der Hebel, der
        # qwen in der Zielsprache hält (deutscher Prompt → deutsche Monologe,
        # siehe memory/tutor_persona_tuning.md). Darum keine Literal-Regel
        # ("只用中文") mehr, sondern die Eigenschaft direkt prüfen.
        cjk = sum(1 for c in sp if '一' <= c <= '鿿')
        check("zh-prompt ist auf Chinesisch verfasst (>60% CJK)",
              cjk / max(len(sp), 1) > 0.6)
        check("zh-prompt: Deutsch nur als kurze Ausnahme, dann zurück",
              "用德语" in sp and "回中文" in sp)
        check("zh-prompt: kein Fake-Lob", "别夸她" in sp)
        check("zh-prompt: ehrlich KI, kein Fake-Mensch",
              "你是 AI" in sp and "不是真人" in sp)
        check("zh-prompt: KEIN altes Länder-Spam",
              "Nationalgericht" not in sp and "vernarrt" not in sp)
        # Leanness-Wächter gegen Aufblähen (Emergenz-Prompt liegt bei ~900;
        # die alte 800er-Schwelle stammt aus der Zeit davor).
        check("zh-prompt: schlank (< 1200 zeichen)", len(sp) < 1200)

        check("vokabel-tools erhalten", hasattr(tools, "get_confirmed_vocab")
              and any(t["function"]["name"] == "introduce_new"
                      for t in tools.TUTOR_TOOLS))

        fr = langs.get("fr")["system_prompt"]
        check("fr-fallback: nur-Zielsprache-Regel", "NUR auf Französisch" in fr)
        check("fr-fallback: kein Fake-Mensch", "keine Vergangenheit" in fr)

        # ── Kapazitätsbasierte Backend-Wahl (Ollama daheim ODER Cloud) ──
        # remember() verdichtet über _distill (NICHT mehr über consolidation —
        # der Cloud-Graph-Extraktor ist 2026-07-16 als tot gelöscht worden).
        import ai_backends
        captured = {}

        def fake_distill(backend, provider, model, user_msg):
            captured.clear()
            captured.update(backend=backend, provider=provider, model=model)
            return '{"facts": [], "topics": []}'

        orig_distill = memory._distill
        orig_status = ai_backends.status
        memory._distill = fake_distill
        try:
            ai_backends.status = lambda *a, **k: {"local": True, "cloud": True,
                                                  "cloud_provider": "qwen"}
            memory.remember("ich hab morgen klausur", "加油", lang="zh",
                            provider="qwen", model="qwen-plus")
            check("local da → backend local", captured.get("backend") == "local")

            ai_backends.status = lambda *a, **k: {"local": False, "cloud": True,
                                                  "cloud_provider": "qwen"}
            memory.remember("ich hab morgen klausur", "加油", lang="zh",
                            provider="qwen", model="qwen-plus")
            check("kein Ollama, cloud da → backend cloud",
                  captured.get("backend") == "cloud")
            check("cloud → provider gesetzt", captured.get("provider") == "qwen")

            captured.clear()
            ai_backends.status = lambda *a, **k: {"local": False, "cloud": False,
                                                  "cloud_provider": None}
            memory.remember("ich hab morgen klausur", "加油", lang="zh")
            check("kein backend → verdichtung uebersprungen", captured == {})
        finally:
            memory._distill = orig_distill
            ai_backends.status = orig_status

        # ── Secrets: tutor/ hält KEINE Keys mehr (der Core besitzt sie) ──
        cfg_file = os.path.join(ROOT, "tutor", "data", "tutor_config.json")
        if os.path.exists(cfg_file):
            raw = json.load(open(cfg_file, encoding="utf-8"))
            check("tutor/data/tutor_config.json ohne keys-block",
                  "keys" not in raw)
            check("tutor/data/tutor_config.json ohne API-KEY-artige werte",
                  not any("KEY" in str(k).upper() for k in raw))
        check("tutor.config injiziert keine keys mehr",
              not hasattr(config, "_inject_keys"))

    finally:
        memory._DATA_DIR = orig_dir
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + ("ALLE GRÜN" if _fails == 0 else f"{_fails} FEHLER"))
    return _fails


if __name__ == '__main__':
    sys.exit(main())
