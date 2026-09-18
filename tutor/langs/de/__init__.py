# tutor/langs/de/ — Deutsch, Persona: Lena (Berlin).
#
# Lucías Konstrukt (tutor/langs/es/) 1:1 übersetzt — Sasha 2026-09-17: »kopier
# unsere Lucía in ihrem vollen Konstrukt und übersetz alles auf Deutsch, that's
# it.« Zweite LIVE-Sprache neben es und zh, vor allem zum Testen und Debuggen
# des Tutors in einer Sprache, die Sasha selbst kann (Glosse = Muttersprache,
# Einstellung 'native'; Deutsch-mit-Glosse-Deutsch ist erlaubt).
#
#   prompt.md        System-Prompt AUF DEUTSCH (Übersetzung von
#                    PROMPT_TEMPLATE.en.md über es/prompt.md, inkl. Haken-Absatz).
#                    {native} bleibt Platzhalter (session füllt die Muttersprache).
#   vocab_hint.md    {words}-Template ans Prompt-Ende.
#   expect.json      leer — Register trägt der Prompt (wie es).
#   core_vocab.json  76 Kernwörter, dieselben Bedeutungen wie bei Lucía, mit
#                    gloss {en, de}.
#   tool_texts.json  Tool-Beschriftung auf Deutsch (nur lebende Tools).
#   seeds/           leichte Deutschland-Themen + Mediathek-Katalog.
#
# Stimme: services/tts_service.py hat eine de-Engine (Piper, eine Sprecherin;
# der speaker-Parameter wird ignoriert). Figur: Default-Rig 'lucia', bis Lena
# ihre eigene Schablone hat (memory/tutor/tutor_puppe.md).
#
# Offen: die Texte sind noch nicht gegen echtes qwen-plus gegengetestet.

from ..base import profile, load_text, load_json

PROFILE = profile(
    "de",
    name         = "Deutsch",
    persona_name = "Lena",
    country      = "Deutschland",
    enabled      = True,

    reading        = "none",
    reading_label  = "",
    script         = "ltr",
    stt_lang       = "de",
    tts_lang       = "de",

    # Muttersprache (Glosse) in der Zielsprache benannt — {native} im Prompt.
    native_names = {"en": "Englisch", "de": "Deutsch", "es": "Spanisch", "zh": "Chinesisch",
                    "fr": "Französisch", "ru": "Russisch", "ar": "Arabisch"},

    provider = "qwen",
    model    = "qwen-plus",

    system_prompt = load_text(__file__, "prompt.md"),
    vocab_hint    = load_text(__file__, "vocab_hint.md").strip(),
    expect_ladder = load_json(__file__, "expect.json"),
    tool_texts    = load_json(__file__, "tool_texts.json", {}),

    core_vocab = load_json(__file__, "core_vocab.json", []),
    core_hint  = ("(Grundwortschatz: {got}/{total} sitzen. Noch dran, in dieser Reihenfolge: "
                  "{words}. Nimm die bevorzugt, wenn es passt — nicht erzwingen, nicht alle "
                  "auf einmal.)"),

    # Hintergrund-Meldungen (Öffnen/Stille) — in der Zielsprache.
    situation = {
        "prefix":          "(Kontext, nicht das, was Sasha gesagt hat, wiederhol diese Wörter nicht: ",
        "suffix":          ".)",
        "join":            ", ",
        "open":            "Sasha kommt gerade rein",
        "open_focus":      " und schaut dich an",
        "nudge_idle":      "es ist schon eine Weile still",
        "nudge_focus_yes": "jemand schaut dich an, sagt aber nichts",
        "nudge_focus_no":  "niemand schaut dich an",
        "nudge_sound":     "man hört etwas, vielleicht ist jemand da",
    },

    vocab_labels = {
        "structs": "Sagweisen, die er gerade aufschnappt: ",
        "join":    ", ",
        "sep":     "; ",
    },

    # Nur beschreibend — keine Drill-Verben (die ließen qwen abfragen).
    status_labels = {
        "new":        "neu",
        "understood": "erkennt er",
        "learning":   "fängt an, es zu benutzen",
        "learned":    "benutzt er gut",
        "intuitive":  "kommt von allein",
    },

    phrases = {
        "vocab_none":             "Noch keine gefestigten Wörter.",
        "vocab_confirmed_header": "Gefestigte Wörter (die 80 %):",
        "vocab_testing_empty":    "keine Wörter im Lernen (0) — nimm introduce_new",
        "vocab_testing_header":   "Wörter im Lernen (die 20 %, es sind {count}):",
        "vocab_confirmed_now":    "✓ «{word}» jetzt gefestigt (nach {uses}-mal richtig benutzt)",
        "vocab_progress":         "✓ Zähler für «{word}» → {uses}/{threshold}",
        "vocab_notfound":         "[das Wort «{word}» steht nicht in der Liste]",
        "vocab_dup":              "[«{word}» steht schon in der Liste]",
        "vocab_added":            "✓ neues Wort aufgenommen: «{word}»",
        "vocab_invalid":          "[«{word}» ist kein deutsches Wort — zeig nur deutsche Wörter; die Übersetzung gehört in «meaning»]",
        "known_noword":           "[kein Wort]",
        "known_marked":           "✓ «{word}» als bekannt markiert",
        "known_added":            "✓ «{word}» als bekannt aufgenommen",
        "stats":                  "Wörter gesamt: {total} | gefestigt: {confirmed} | im Lernen: {testing}",

        "struct_none":            "Noch keine Muster. Wenn er sicher ist, kannst du mit introduce_structure eins reinbringen.",
        "struct_header":          "Muster / Sagweisen im Lernen:",
        "struct_line":            "{pattern} — {note} ({uses}-mal{tag})",
        "struct_mastered_tag":    ", gefestigt",
        "struct_nopattern":       "[kein Muster]",
        "struct_dup":             "[«{pattern}» gibt es schon]",
        "struct_new":             "✓ neues Muster: {pattern}",
        "struct_mastered":        "✓ Muster «{pattern}» gefestigt",
        "struct_progress":        "✓ «{pattern}» {uses}/{threshold}",
        "struct_notfound":        "[«{pattern}» nicht gefunden]",

        "srs_none":               "(gerade nichts zum Auffrischen, quatsch einfach weiter)",
        "srs_due":                "(vielleicht EINES davon nebenbei einstreuen, wenn es von selbst passt, ohne Druck, nicht abfragen, nicht alle: {words})",
        "news_none":              "(gerade kein Thema, quatsch einfach weiter)",
        "news_wrap":              "(nebenbei fallen lassen, nicht wie die Tagesschau) Aus Deutschland wird oft erzählt: {topic}",
        "tv_wrap":                "(du hast den Fernseher angemacht, sag einfach einen Satz) Es läuft: {title} ({level}, {note})",
    },

    seeds = {
        "news": load_json(__file__, "seeds/news.json", []),
        "tv":   load_json(__file__, "seeds/tv.json", []),
    },
)
