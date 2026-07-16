# tutor/langs/ar/ — Arabisch, Persona: Amira.
#
# SKIZZE (enabled=False): Persona/Land/Provider stehen, der Prompt kommt noch aus
# der generischen build_prompt (deutsch). BEIM AKTIVIEREN: einen eigenen prompt.md
# IN DER ZIELSPRACHE hand-tunen (wie tutor/langs/zh/prompt.md) — ein deutscher
# Prompt lässt das Modell auf Deutsch antworten (memory/tutor_persona_tuning.md).
# Dann prompt.de.md als Referenz daneben, tool_texts.json + phrases + expect.json
# in der Zielsprache, seeds/ füllen, und enabled=True.

from ..base import profile, build_prompt

PROFILE = profile(
    "ar",
    name         = 'Arabisch',
    persona_name = 'Amira',
    country      = 'die arabische Welt',
    enabled      = False,

    reading  = 'translit',
    script   = 'rtl',
    stt_lang = 'ar',
    tts_lang = 'ar',

    provider = 'openai',
    model    = 'gpt-4o-mini',

    # ACHTUNG: die Argumente hier sind bewusst NICHT name/country von oben —
    # der Prompt spricht 'Hocharabisch (MSA)' an, das Profil heisst 'Arabisch' (UI).
    system_prompt = build_prompt(
        'Amira',
        'Hocharabisch (MSA)',
        'die arabische Welt',
        'Neue Wörter mit lateinischer Umschrift in Klammern, z.B. شكراً (shukran). Arabisch wird von rechts nach links geschrieben.',
    ),
)
