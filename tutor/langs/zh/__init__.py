# tutor/langs/zh/ — Chinesisch (Mandarin), Persona: Ling Ling.
#
# Die EINZIGE LIVE-Sprache. Alles, was diese Sprache ausmacht, liegt in diesem
# Ordner — Code muss dafür nirgends angefasst werden.
#
#   prompt.md        System-Prompt, AUF CHINESISCH hand-getunt gegen echtes
#                    qwen-plus (Log: memory/tutor_persona_tuning.md). Das ist der
#                    Hebel, der das Modell in der Zielsprache hält.
#   prompt.de.md     Deutsche Referenz-Fassung desselben Prompts (nur Review;
#                    NICHT das, was das Modell sieht).
#   vocab_hint.md    {words}-Template, das session ans Prompt-Ende hängt.
#   expect.json      Register-Leiter [[grenze, text], …] — die Sprechweise
#                    skaliert mit dem Wortschatz (war eine if-Kaskade in Code).
#   tool_texts.json  Tool-Beschriftung, die das Modell sieht.
#   seeds/news.json  leichte China-Themen (Content-Lücke: kein echter Feed)
#   seeds/tv.json    Mediathek-Katalog (nur Titel/Meta, kein Video)
#
# ── Ehrliche Grenze (vorbestehend, NICHT beim Umzug entstanden) ─────────
# In tool_texts.json sind vier Tools noch DEUTSCH beschriftet
# (get_confirmed_vocab, get_testing_vocab, increment_correct_use, introduce_new)
# — die stammen aus der Zeit vor dem Tuning. Nach der Tuning-Lehre müssten sie
# chinesisch sein wie der Rest. Beim Umzug 2026-07-16 bewusst WORTGLEICH
# übernommen statt nebenbei übersetzt: eine Prompt-Änderung ohne Gegentest an
# echtem qwen ist Glückssache. Offener Punkt im Tracker.

from ..base import profile, load_text, load_json

PROFILE = profile(
    "zh",
    name         = "Chinesisch",     # Sprach-Anzeigename (UI/lang_name)
    persona_name = "Ling Ling",      # die Figur
    country      = "China",
    enabled      = True,

    # Lesehilfe: das 'reading'-Feld in tutor/data/zh/vocab.json IST Pinyin.
    reading        = "pinyin",
    reading_label  = "拼音",
    script         = "ltr",
    stt_lang       = "zh",
    tts_lang       = "zh",

    provider = "qwen",          # nativ stark, billig, no-train (Singapur)
    model    = "qwen-plus",     # qwen-turbo = noch billiger (Verteil-Variante)

    system_prompt = load_text(__file__, "prompt.md"),
    vocab_hint    = load_text(__file__, "vocab_hint.md").strip(),
    expect_ladder = load_json(__file__, "expect.json"),
    tool_texts    = load_json(__file__, "tool_texts.json", {}),

    # Situations-Meldungen (Öffnen/Stille) — standen vorher als chinesische
    # Literale hart in session.py. Wortgleich hierher gezogen, damit Ling Ling
    # sich exakt gleich verhält und andere Sprachen kein Chinesisch mehr erben.
    situation = {
        "prefix":          "（背景，不是 Sasha 说的话，别重复里面的字：",
        "suffix":          "。）",
        "join":            "，",
        "open":            "Sasha 刚过来了",
        "open_focus":      "，在看着你",
        "nudge_idle":      "一会儿没动静了",
        "nudge_focus_yes": "有人在看着你，可就是不出声",
        "nudge_focus_no":  "也没人看你",
        "nudge_sound":     "好像有点响动，说不好有没有人",
    },

    # Beschriftung des Vokabel-Blocks, den session ans Prompt-Ende hängt
    # (stand vorher als chinesische Literale in session.py — eine fr-Session
    # hätte damit einen chinesischen Block bekommen).
    vocab_labels = {
        "solid":   "已掌握（放心多用）：",
        "learn":   "在学（多带带，用对了帮她记）：",
        "structs": "在教的句型：",
        "plain":   "她在学：",
        "join":    "、",
        "sep":     "；",
    },

    # Regie-Sätze + Rückgaben der Tools — in der Zielsprache, sonst kippt das
    # Modell ins Deutsche (dieselbe Logik wie beim Prompt). Wortgleich aus der
    # alten tools.py übernommen.
    phrases = {
        "news_none":           "（现在没有话题，随便聊聊就好）",
        "news_wrap":           "（可以随口提一句，别像播新闻）中国最近常聊的：{topic}",
        "tv_wrap":             "（打开了电视，随口说一句就好）在看：{title}（{level}，{note}）",
        "struct_none":         "还没有句型。她熟了可以用 introduce_structure 加一个新说法。",
        "struct_header":       "在学的句型/说法:",
        "struct_line":         "{pattern} — {note}（{uses}次{tag}）",
        "struct_mastered_tag": "，已掌握",
        "struct_dup":          "['{pattern}' 已有]",
        "struct_new":          "✓ 新句型: {pattern}",
        "struct_mastered":     "✓ 句型 '{pattern}' 已掌握",
        "struct_progress":     "✓ '{pattern}' {uses}/{threshold}",
        "struct_notfound":     "['{pattern}' 未找到]",
    },

    seeds = {
        "news": load_json(__file__, "seeds/news.json", []),
        "tv":   load_json(__file__, "seeds/tv.json", []),
    },
)
