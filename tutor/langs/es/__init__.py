# tutor/langs/es/ — Spanisch, Persona: Lucía.
#
# LIVE (enabled=True). Alles, was diese Sprache ausmacht, liegt in diesem Ordner —
# Code muss dafür nirgends angefasst werden.
#
#   prompt.md        System-Prompt, AUF SPANISCH (der Hebel, der das Modell in der
#                    Zielsprache hält; siehe base.py + memory/tutor/tutor_persona_tuning.md).
#   prompt.de.md     Deutsche Referenz-Fassung (nur Review; NICHT was das Modell sieht).
#   vocab_hint.md    {words}-Template, das session ans Prompt-Ende hängt.
#   expect.json      Register-Leiter [[grenze, text], …] — Sprechweise skaliert mit
#                    dem Wortschatz.
#   core_vocab.json  Kern-Syllabus: die ersten ~75 Wörter, die drankommen sollen
#                    (tools.core_coverage/core_todo, session hängt core_hint an).
#   tool_texts.json  Tool-Beschriftung, die das Modell sieht (Spanisch).
#   seeds/news.json  leichte Spanien-Themen (Content-Lücke: kein echter Feed)
#   seeds/tv.json    Mediathek-Katalog (nur Titel/Meta, kein Video)
#
# ── Provider: qwen (statt der früheren Skizzen-Wahl mistral) ─────────────
# Die Skizze zeigte auf mistral/ministral-3b — der „ideale Spanisch-Default" auf
# dem Papier, aber (a) enabled=False, (b) braucht einen MISTRAL_API_KEY (nur PAID,
# sonst trainiert der Free-Tier). Damit die Sprache HEUTE läuft, zeigt sie auf
# qwen-plus: enabled, Key vorhanden (DASHSCOPE), no-train, „solide bei es"
# (providers.py). Umstellen jederzeit über tutor/data/tutor_config.json
# (provider/model) — die Sprache ist an keinen Anbieter gebunden.
#
# ── Noch nicht gegen echtes Modell gegengetestet ────────────────────────
# prompt.md ist 1:1 nach dem zh-Bauplan übersetzt, aber noch nicht in einer echten
# qwen-Session gegengeprüft (siehe prompt.de.md). Beim ersten Live-Lauf: bleibt
# Lucía auf Spanisch, kurz, mit show_thought-Reflex? Sonst am prompt.md feilen.

from ..base import profile, load_text, load_json

PROFILE = profile(
    "es",
    name         = "Spanisch",       # Sprach-Anzeigename (UI/lang_name)
    persona_name = "Lucía",          # die Figur
    country      = "Spanien",
    enabled      = True,

    # Spanisch braucht keine Lesehilfe → das 'reading'-Feld bleibt leer.
    reading        = "none",
    reading_label  = "",
    script         = "ltr",
    stt_lang       = "es",
    tts_lang       = "es",

    provider = "qwen",           # siehe Kopf: läuft heute; über Config umstellbar
    model    = "qwen-plus",

    system_prompt = load_text(__file__, "prompt.md"),
    # Drill-/Prüf-Prompt fürs harte Assessment-Gate (aktiv bis Kern gemeistert).
    assessment_prompt = load_text(__file__, "assessment_prompt.md"),
    vocab_hint    = load_text(__file__, "vocab_hint.md").strip(),
    expect_ladder = load_json(__file__, "expect.json"),
    tool_texts    = load_json(__file__, "tool_texts.json", {}),

    # Kern-Syllabus + der Hinweis, den session ans Prompt-Ende hängt (Zielsprache).
    core_vocab = load_json(__file__, "core_vocab.json", []),
    core_hint  = ("(Vocabulario básico: {got}/{total} afianzadas. Aún por enseñar, "
                  "por orden: {words}. Prioriza estas cuando encaje, sin forzar ni "
                  "soltarlas de golpe.)"),

    # Hintergrund-Meldungen (Öffnen/Stille) — MÜSSEN spanisch sein. Vorher hart
    # chinesisch (für Ling Ling gebaut) → qwen bekam als Lucía eine chinesische
    # Meta-Lage und kippte in Echo-Schleifen ("¿cansada?"-Loop). Jetzt Zielsprache.
    situation = {
        "prefix":          "(contexto, no es lo que dijo Sasha, no repitas estas palabras: ",
        "suffix":          ".)",
        "join":            ", ",
        "open":            "Sasha acaba de entrar",
        "open_focus":      " y te está mirando",
        "nudge_idle":      "lleva un momento en silencio",
        "nudge_focus_yes": "alguien te mira pero no dice nada",
        "nudge_focus_no":  "no te mira nadie",
        "nudge_sound":     "se oye algo, quizá haya alguien",
    },

    # Beschriftung des Vokabel-Blocks (session hängt ihn ans Prompt-Ende) — Spanisch,
    # sonst bekäme eine es-Session einen deutschen Block.
    # WICHTIG: die Labels beschreiben nur, WAS sie schon kennt — sie sind KEINE
    # Drill-Anweisung. „repítelas/afiánzalas/examínala" o.Ä. lassen qwen wieder
    # abfragen und in Fragen-Schleifen kippen (gegen echtes qwen belegt). Nur zwei
    # Eimer fürs Reden (session.vocab_buckets): BEKANNT (solid) + NEU (learn).
    vocab_labels = {
        "structs": "maneras de decir que va cogiendo: ",
        "join":    ", ",
        "sep":     "; ",
    },

    # Status-Beschriftung (die KI kriegt {wort: status} — NUR beschreibend, KEINE
    # Drill-Anweisung; „úsala/examínala/repite" ließen qwen abfragen).
    status_labels = {
        "new":        "nueva",
        "understood": "la reconoce",
        "learning":   "empieza a usarla",
        "learned":    "la usa bien",
        "intuitive":  "le sale sola",
    },

    # Rückgaben + Regie-Sätze der Tools — in der Zielsprache, sonst liest das Modell
    # mitten in der Session Deutsch und kippt zurück.
    phrases = {
        "vocab_none":             "Todavía no hay palabras afianzadas.",
        "vocab_confirmed_header": "Palabras afianzadas (el 80 %):",
        "vocab_testing_empty":    "no hay palabras en aprendizaje (0) — usa introduce_new",
        "vocab_testing_header":   "Palabras en aprendizaje (el 20 %, son {count}):",
        "vocab_confirmed_now":    "✓ «{word}» ya afianzada (tras usarla bien {uses} veces)",
        "vocab_progress":         "✓ contador de «{word}» → {uses}/{threshold}",
        "vocab_notfound":         "[la palabra «{word}» no está en la lista]",
        "vocab_dup":              "[«{word}» ya está en la lista]",
        "vocab_added":            "✓ palabra nueva añadida: «{word}»",
        "known_noword":           "[ninguna palabra]",
        "known_marked":           "✓ «{word}» marcada como que ya la sabe",
        "known_added":            "✓ «{word}» añadida como que ya la sabe",
        "stats":                  "Palabras en total: {total} | afianzadas: {confirmed} | en aprendizaje: {testing}",

        "struct_none":            "Aún no hay patrones. Cuando esté suelta, puedes añadir uno con introduce_structure.",
        "struct_header":          "Patrones / maneras de decir en aprendizaje:",
        "struct_line":            "{pattern} — {note} ({uses} veces{tag})",
        "struct_mastered_tag":    ", afianzado",
        "struct_nopattern":       "[ningún patrón]",
        "struct_dup":             "[«{pattern}» ya existe]",
        "struct_new":             "✓ patrón nuevo: {pattern}",
        "struct_mastered":        "✓ patrón «{pattern}» afianzado",
        "struct_progress":        "✓ «{pattern}» {uses}/{threshold}",
        "struct_notfound":        "[«{pattern}» no encontrado]",

        "srs_none":               "(ahora no hay nada que repasar, tú sigue charlando sin más)",
        "srs_due":                "(quizá cuela UNA de estas de pasada si sale sola, sin forzar, sin examinarla, no todas: {words})",
        "news_none":              "(ahora no hay tema, tú sigue charlando sin más)",
        "news_wrap":              "(suéltalo de pasada, no como un telediario) De España se suele comentar: {topic}",
        "tv_wrap":                "(has encendido la tele, di una frase sin más) Están echando: {title} ({level}, {note})",
    },

    seeds = {
        "news": load_json(__file__, "seeds/news.json", []),
        "tv":   load_json(__file__, "seeds/tv.json", []),
    },
)
