# core/tutor_langs.py
#
# Sprach-Profile für den Sprach-Tutor-Framework.
#
# Der Tutor ist KEIN Chinesisch-Tutor, sondern ein Framework, auf das Sprachen
# als Profile "draufgelegt" werden. Jedes Profil bündelt die sprach-spezifische
# Prägung; der Provider/das Modell ist entkoppelt (siehe tutor_providers.py).
#
# ── enabled ─────────────────────────────────────────────────────────────
#   True  = fertig verdrahtet. False = SKIZZE (stückweise reinziehen).
#
# ── reading ─────────────────────────────────────────────────────────────
#   Transliterations-/Lesehilfe-Schema: zh=Pinyin, ru=Betonung, ar=Translit, es=—

import os


def _prompt(target: str, extra: str = "") -> str:
    """Generischer Tutor-System-Prompt-Bauer (Lernende = Deutsche)."""
    return (
        f"Du bist {target}-Sprachtutor für Sasha, eine Deutsche die {target} lernt. "
        "Deine Aufgabe: lockeres, natürliches Smalltalk – wie ein echter Gesprächs"
        "partner im Alltag, nicht wie ein Lehrer vor einer Klasse. "
        "\n\n"
        "ABLAUF ZU SESSION-BEGINN: "
        "Ruf get_confirmed_vocab() und get_testing_vocab() auf um zu wissen welche "
        "Wörter Sasha kennt. Falls testing_vocab weniger als 10 Einträge hat: "
        "introduce_new() aufrufen. "
        "\n\n"
        "VOKABEL-REGELN: "
        "80% der Zeit nur bestätigte Vokabeln (confirmed=True) verwenden. "
        "20% der Zeit Wörter aus dem Testing-Pool einstreuen. "
        "Wenn Sasha ein Wort korrekt und sinnvoll in einem Satz nutzt: "
        "increment_correct_use() aufrufen. "
        "\n\n"
        f"SPRACH-REGELN: Hauptsächlich auf {target} schreiben. {extra} "
        "Sätze kurz halten – Sasha ist Anfängerin. Wenn Sasha auf Deutsch fragt "
        "oder etwas nicht versteht: kurz auf Deutsch erklären, dann weiter. "
        "\n\n"
        "CHARAKTER: Entspannt, geduldig, kein übertriebenes Lob. Keine Bewertungen "
        "wie 'Super gemacht!' – einfach normal weiterreden. Die erste Nachricht: "
        f"kurze, einfache Begrüßung auf {target}."
    )


PROFILES = {

    # ── LIVE ──────────────────────────────────────────────────────────
    "zh": {
        "name":       "Chinesisch",
        "enabled":    True,
        "vocab_file": "vocab_mandarin.json",
        "reading":    "pinyin",
        "script":     "ltr",
        "stt_lang":   "zh",
        "tts_lang":   "zh",
        "provider":   "qwen",         # nativ stark, billig, no-train (Singapur)
        "model":      "qwen-plus",    # qwen-turbo = noch billiger (Verteil-Variante)
        "system_prompt": _prompt(
            "Mandarin",
            "Neue Wörter immer mit Pinyin in Klammern: 谢谢 (xiè xie).",
        ),
    },

    # ── SKIZZEN: Daten/Default stehen, stückweise reinziehen ──────────
    "ru": {
        "name":       "Russisch",
        "enabled":    False,
        "vocab_file": "vocab_russian.json",   # TODO: anlegen
        "reading":    "stress",               # Betonungszeichen
        "script":     "ltr",
        "stt_lang":   "ru",
        "tts_lang":   "ru",
        "provider":   "qwen",                 # Qwen-Basis stark bei Russisch (T-pro/Vikhr-Basis)
        "model":      "qwen-plus",            # Alternativ: Qwen3 via DeepInfra (EU/US-Host)
        "system_prompt": _prompt(
            "Russisch",
            "Neue Wörter mit Betonungszeichen markieren, z.B. хорошо́.",
        ),
    },
    "ar": {
        "name":       "Arabisch",
        "enabled":    False,
        "vocab_file": "vocab_arabic.json",    # TODO: anlegen
        "reading":    "translit",             # lateinische Umschrift
        "script":     "rtl",                  # Arabisch ist rechts-nach-links!
        "stt_lang":   "ar",
        "tts_lang":   "ar",
        "provider":   "openai",               # gpt-4o-mini: sauber + gut MSA.
        "model":      "gpt-4o-mini",          # Alt: ALLaM-2-7B via Groq (gratis, Policy prüfen)
        "system_prompt": _prompt(
            "Hocharabisch (MSA)",
            "Neue Wörter mit lateinischer Umschrift in Klammern, z.B. شكراً (shukran). "
            "Beachte: Arabisch wird von rechts nach links geschrieben.",
        ),
    },
    "es": {
        "name":       "Spanisch",
        "enabled":    False,
        "vocab_file": "vocab_spanish.json",   # TODO: anlegen
        "reading":    "none",
        "script":     "ltr",
        "stt_lang":   "es",
        "tts_lang":   "es",
        "provider":   "mistral",              # EU/GDPR, billigst, Spanisch trivial-stark
        "model":      "ministral-3b-latest",  # ACHTUNG: nur PAID-Tier (Free trainiert)
        "system_prompt": _prompt(
            "Spanisch",
            "Bei Substantiven das Genus mitnennen, z.B. la casa.",
        ),
    },
}


def get(lang: str = None) -> dict:
    """Liefert das aktive Sprach-Profil. lang=None → TUTOR_LANG-Env, Default 'zh'."""
    code = (lang or os.getenv("TUTOR_LANG", "zh")).lower()
    return PROFILES.get(code) or PROFILES["zh"]
