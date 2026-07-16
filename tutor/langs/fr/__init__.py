# tutor/langs/fr/ — Französisch, Persona: Jacqueline.
#
# SKIZZE (enabled=False): Persona/Land/Provider stehen, der Prompt kommt noch aus
# der generischen build_prompt (deutsch). BEIM AKTIVIEREN: einen eigenen prompt.md
# IN DER ZIELSPRACHE hand-tunen (wie tutor/langs/zh/prompt.md) — ein deutscher
# Prompt lässt das Modell auf Deutsch antworten (memory/tutor_persona_tuning.md).
# Dann prompt.de.md als Referenz daneben, tool_texts.json + phrases + expect.json
# in der Zielsprache, seeds/ füllen, und enabled=True.

from ..base import profile, build_prompt

PROFILE = profile(
    "fr",
    name         = 'Französisch',
    persona_name = 'Jacqueline',
    country      = 'Frankreich',
    enabled      = False,

    reading  = 'none',
    script   = 'ltr',
    stt_lang = 'fr',
    tts_lang = 'fr',

    provider = 'mistral',
    model    = 'ministral-3b-latest',

    # ACHTUNG: die Argumente hier sind bewusst NICHT name/country von oben —
    # der Prompt spricht 'Französisch' an, das Profil heisst 'Französisch' (UI).
    system_prompt = build_prompt(
        'Jacqueline',
        'Französisch',
        'Frankreich',
        'Bei Substantiven das Genus mitnennen, z.B. le pain.',
    ),
)
