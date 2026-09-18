# tutor/langs/zh/ — Chinesisch (Mandarin), Persona: Ling Ling.
#
# Eine der LIVE-Sprachen (mit es, de). Alles, was diese Sprache ausmacht, liegt
# in diesem Ordner — Code muss dafür nirgends angefasst werden. Seit 2026-09-18
# auf Lucías vollem Bauplan (memory/tutor/bauplan.md): core_vocab (76 Kern-
# wörter mit Pinyin + Glosse), core_hint, status_labels, alle 28 phrases,
# tool_texts komplett chinesisch, expect.json leer (Register trägt der Prompt).
#
#   prompt.md        System-Prompt, AUF CHINESISCH hand-getunt gegen echtes
#                    qwen-plus (Log: memory/tutor/tutor_persona_tuning.md). Das ist der
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
# ── Offen ───────────────────────────────────────────────────────────────
# Die 2026-09-18 ergänzten chinesischen Texte (introduce_new, get_due_reviews,
# status_labels, die 16 nachgetragenen phrases, der Haken-Absatz im Prompt)
# sind noch nicht gegen echtes qwen-plus gegengetestet — beim nächsten
# Live-Test mit Ling Ling anschauen (memory/tutor/tutor_persona_tuning.md).

from ..base import profile, load_text, load_json

PROFILE = profile(
    "zh",
    name         = "Chinesisch",     # Sprach-Anzeigename (UI/lang_name)
    persona_name = "Ling Ling",      # die Figur
    country      = "China",
    enabled      = True,

    # Lesehilfe: das 'reading'-Feld in tutor/data/zh/vocab.json IST Pinyin.
    reading        = "pinyin",
    word_pattern   = r"[\u4e00-\u9fff]",    # ein chinesisches Wort hat Han-Zeichen
    reading_label  = "拼音",
    script         = "ltr",
    stt_lang       = "zh",
    tts_lang       = "zh",

    native_names = {"en": "英语", "de": "德语", "es": "西班牙语", "zh": "中文",
                    "fr": "法语", "ru": "俄语", "ar": "阿拉伯语"},
    provider = "qwen",          # nativ stark, billig, no-train (Singapur)
    model    = "qwen-plus",     # qwen-turbo = noch billiger (Verteil-Variante)

    system_prompt = load_text(__file__, "prompt.md"),
    vocab_hint    = load_text(__file__, "vocab_hint.md").strip(),
    expect_ladder = load_json(__file__, "expect.json"),
    tool_texts    = load_json(__file__, "tool_texts.json", {}),

    # Kern-Syllabus (76 Wörter, dieselben Bedeutungen wie bei Lucía) + Hinweis.
    core_vocab = load_json(__file__, "core_vocab.json", []),
    core_hint  = ("（基础词汇：{got}/{total} 已扎实。还没教、按顺序：{words}。合适的时候优先带这些，"
                  "别硬塞，别一下子全倒出来。）"),

    # Status-Beschriftung fürs Modell ({词: 状态}) — beschreibend, keine Drill-Verben.
    status_labels = {
        "new":        "新词",
        "understood": "听得懂",
        "learning":   "开始会用",
        "learned":    "用得不错",
        "intuitive":  "脱口而出",
    },

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
        "vocab_none":            "还没有已确认的词。",
        "vocab_confirmed_header": "已确认的词（80% 池）：",
        "vocab_testing_empty":   "testing_vocab 为空（count=0）——调用 introduce_new！",
        "vocab_testing_header":  "在测的词（20% 池，count={count}）：",
        "vocab_confirmed_now":   "✓「{word}」现在已确认（正确使用 {uses} 次）",
        "vocab_progress":        "✓「{word}」correct_use → {uses}/{threshold}",
        "vocab_notfound":        "[词表里没有「{word}」]",
        "vocab_dup":             "[「{word}」已在词表里]",
        "vocab_added":           "✓ 新词已加入：「{word}」（{reading}）",
        "vocab_invalid":         "[「{word}」不是中文词——只展示中文词，翻译放在 meaning 里]",
        "known_noword":          "[没有词]",
        "known_marked":          "✓「{word}」已标为会了",
        "known_added":           "✓「{word}」已作为会了加入",
        "stats":                 "词汇总数：{total} | 已确认：{confirmed} | 在测：{testing}",
        "struct_nopattern":      "[没有句型]",
        "srs_none":              "（现在没有该复习的——正常聊就好）",
        "srs_due":               "（要是自然接得上，就悄悄带一个进去——别有压力，别提问，别全说）该复习：{words}",
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
