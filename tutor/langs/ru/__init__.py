# tutor/langs/ru/ — Russisch, Persona: Ludmila.
#
# SKIZZE (enabled=False): Persona/Land/Provider stehen, der Prompt kommt noch aus
# der generischen build_prompt (deutsch). BEIM AKTIVIEREN: einen eigenen prompt.md
# IN DER ZIELSPRACHE hand-tunen (wie tutor/langs/zh/prompt.md) — ein deutscher
# Prompt lässt das Modell auf Deutsch antworten (memory/tutor/tutor_persona_tuning.md).
# Dann prompt.de.md als Referenz daneben, tool_texts.json + phrases + expect.json
# in der Zielsprache, seeds/ füllen, und enabled=True.

from ..base import profile, build_prompt

PROFILE = profile(
    "ru",
    name         = 'Russisch',
    persona_name = 'Ludmila',
    country      = 'Russland',
    enabled      = False,

    reading  = 'stress',
    script   = 'ltr',
    stt_lang = 'ru',
    tts_lang = 'ru',

    provider = 'qwen',
    model    = 'qwen-plus',

    # ACHTUNG: die Argumente hier sind bewusst NICHT name/country von oben —
    # der Prompt spricht 'Russisch' an, das Profil heisst 'Russisch' (UI).
    system_prompt = build_prompt(
        'Ludmila',
        'Russisch',
        'Russland',
        'Neue Wörter mit Betonungszeichen markieren, z.B. хорошо́.',
    ),
)
