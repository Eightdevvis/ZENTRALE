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
import io
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
        check("mem_path lang-spezifisch (data/<lang>/persona_mem.json)",
              memory.mem_path("zh").endswith(os.path.join("zh", "persona_mem.json"))
              and memory.mem_path("fr").endswith(os.path.join("fr", "persona_mem.json")))
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
              os.path.exists(os.path.join(tmp, "zh", "persona_mem.json")))
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
        # siehe memory/tutor/tutor_persona_tuning.md). Darum keine Literal-Regel
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

        # Vokabel-Modell: nur spoken/listened → word_status; die KI zählt nicht mehr
        # (keine get_confirmed_vocab/increment_correct_use/mark_known-Tools).
        check("vokabel-status-modell", hasattr(tools, "word_status")
              and tools.word_status({"spoken": 4}) == "learned"
              and tools.word_status({"listened": 4}) == "understood")
        tool_names = {t["function"]["name"] for t in tools.tools_for("zh")}
        check("show_thought/introduce_new erhalten",
              "introduce_new" in tool_names and "show_thought" in tool_names)
        check("keine Zähl-Tools mehr für die KI",
              not ({"get_confirmed_vocab", "increment_correct_use", "mark_known"} & tool_names))

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

        # ── Sprach-Isolation (das war der eigentliche Bug) ──────────────
        # Vorher: tools.py hatte MODUL-Konstanten auf vocab_mandarin.json →
        # /lang fr liess Jacqueline Franzoesisch reden, aber franzoesische
        # Woerter mit einem 'pinyin'-Feld in Ling Lings Mandarin-Liste schreiben,
        # mit chinesischen Tool-Beschreibungen und China-News.
        vtmp = tempfile.mkdtemp(prefix='tutor_vocab_test_')
        orig_root = tools._DATA_ROOT
        tools._DATA_ROOT = vtmp
        try:
            zh_v, fr_v = tools._file('vocab.json', 'zh'), tools._file('vocab.json', 'fr')
            check("vokabel-datei ist pro sprache getrennt", zh_v != fr_v
                  and zh_v.endswith(os.path.join('zh', 'vocab.json'))
                  and fr_v.endswith(os.path.join('fr', 'vocab.json')))

            tools.introduce_new("你好", "nǐ hǎo", lang="zh")
            tools.introduce_new("bonjour", "", lang="fr")
            check("kein leak zh->fr", "你好" not in tools.term_list("fr"))
            check("kein leak fr->zh", "bonjour" not in tools.term_list("zh"))

            # Datenmodell: generisches 'reading', kein mandarin-festes 'pinyin'
            raw = json.load(io.open(zh_v, encoding="utf-8"))
            check("vokabel-schema nutzt 'reading', nicht 'pinyin'",
                  "reading" in raw[0] and "pinyin" not in raw[0])
            check("reading traegt den wert", raw[0]["reading"] == "nǐ hǎo")

            # Tool-Schema: Parameter generisch, Text pro Sprache
            def schema(lang):
                return {t["function"]["name"]: t["function"]
                        for t in tools.tools_for(lang)}
            zs, fs = schema("zh"), schema("fr")
            check("introduce_new hat 'reading', kein 'pinyin'",
                  "reading" in zs["introduce_new"]["parameters"]["properties"]
                  and "pinyin" not in zs["introduce_new"]["parameters"]["properties"])
            check("zh-tooltext ist der getunte (chinesisch bei show_thought)",
                  any('\u4e00' <= c <= '\u9fff'
                      for c in zs["show_thought"]["description"]))
            check("fr bekommt KEINEN chinesischen tooltext",
                  not any('\u4e00' <= c <= '\u9fff'
                          for c in fs["show_thought"]["description"]))

            # Seeds: Landes-Themen kommen aus dem Sprach-Paket
            check("zh hat landes-seeds", len(tools._news_items("zh")) > 0)
            check("fr bekommt KEINE china-seeds", tools._news_items("fr") == [])
            check("fr-news faellt sauber auf 'kein thema' zurueck",
                  "quatsch" in tools.get_local_news("fr").lower())
        finally:
            tools._DATA_ROOT = orig_root
            shutil.rmtree(vtmp, ignore_errors=True)

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
