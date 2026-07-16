# tutor/langs/es/ — Spanisch, Persona: Lucía.
#
# SKIZZE (enabled=False): Persona/Land/Provider stehen, der Prompt kommt noch aus
# der generischen build_prompt (deutsch). BEIM AKTIVIEREN: einen eigenen prompt.md
# IN DER ZIELSPRACHE hand-tunen (wie tutor/langs/zh/prompt.md) — ein deutscher
# Prompt lässt das Modell auf Deutsch antworten (memory/tutor_persona_tuning.md).
# Dann prompt.de.md als Referenz daneben, tool_texts.json + phrases + expect.json
# in der Zielsprache, seeds/ füllen, und enabled=True.

from ..base import profile, build_prompt

PROFILE = profile(
    "es",
    name         = 'Spanisch',
    persona_name = 'Lucía',
    country      = 'Spanien',
    enabled      = False,

    reading  = 'none',
    script   = 'ltr',
    stt_lang = 'es',
    tts_lang = 'es',

    provider = 'mistral',
    model    = 'ministral-3b-latest',

    # ACHTUNG: die Argumente hier sind bewusst NICHT name/country von oben —
    # der Prompt spricht 'Spanisch' an, das Profil heisst 'Spanisch' (UI).
    system_prompt = build_prompt(
        'Lucía',
        'Spanisch',
        'Spanien',
        'Bei Substantiven das Genus mitnennen, z.B. la casa.',
    ),
)
