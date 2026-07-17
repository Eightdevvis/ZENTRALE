# tutor/providers.py
#
# Provider-Registry für den Sprach-Tutor.
#
# Entkoppelt "welcher Anbieter/welches Modell" von der Sprache (siehe
# tutor/langs/). Ein LanguageProfile zeigt auf einen Provider-Namen hier.
#
# ── kind ────────────────────────────────────────────────────────────────
#   ollama        → lokal, über core/ai.py (Default, offline)
#   anthropic     → Claude via Anthropic-SDK (tutor/cloud.py)
#   openai_compat → OpenAI-/v1-kompatibel (tutor/openai_compat.py):
#                   Qwen, DeepSeek, Mistral, OpenAI, Groq, Gemini, …
#
# ── trains_on_data (HART, siehe memory/tutor_system.md) ──────────────────
#   True  → Anbieter trainiert/nutzt offiziell die Nutzdaten. NICHT verboten,
#           aber MUSS während der Nutzung laut geflaggt werden (tutor_session
#           setzt eine prominente Warnung; /api/tutor/status liefert sie).
#   False → trainiert laut offizieller Policy NICHT auf API-Daten (verifiziert,
#           Stand 2026-06, Quellen in der Recherche/Memory).
#
# ── enabled ─────────────────────────────────────────────────────────────
#   True  → fertig verdrahtet, nutzbar.
#   False → SKIZZE: Daten stehen, wird stückweise reingezogen.

PROVIDERS = {

    # ── live ──────────────────────────────────────────────────────────
    "local": {
        "kind":           "ollama",
        "base_url":       None,           # ai.py kennt OLLAMA_URL selbst
        "key_env":        None,
        "default_model":  None,           # ai.py nutzt OLLAMA_MODEL
        "trains_on_data": False,
        "jurisdiction":   "local",
        "enabled":        True,
        "note":           "Lokales Ollama – Default, vollständig offline.",
    },
    "claude": {
        "kind":           "anthropic",
        "base_url":       None,           # Anthropic-SDK kennt den Endpoint
        "key_env":        "ANTHROPIC_API_KEY",
        "default_model":  "claude-opus-4-8",   # smart = Verifikation; per TUTOR_MODEL änderbar
        "trains_on_data": False,          # Anthropic trainiert nicht auf API-Daten
        "jurisdiction":   "US",
        "enabled":        True,
        "note":           "Claude – Sashas persönlicher Verifikations-Pfad (teuer).",
    },
    "qwen": {
        "kind":           "openai_compat",
        # Internationaler Endpoint = Daten in Singapur (NICHT China):
        "base_url":       "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env":        "DASHSCOPE_API_KEY",
        "default_model":  "qwen-plus",    # qwen-turbo = noch billiger
        "trains_on_data": False,          # DashScope trainiert explizit NICHT auf API-Daten
        "jurisdiction":   "SG",
        "enabled":        True,
        "note":           "Alibaba Qwen (intl/Singapur). Billig + nativ stark bei "
                          "Chinesisch, solide bei ru/ar/es. no-train (verifiziert).",
    },

    # ── Skizzen: Daten stehen, stückweise reinziehen ──────────────────
    "openai": {
        "kind":           "openai_compat",
        "base_url":       "https://api.openai.com/v1",
        "key_env":        "OPENAI_API_KEY",
        "default_model":  "gpt-4o-mini",
        "trains_on_data": False,          # OpenAI trainiert seit 2023 nicht auf API-Daten
        "jurisdiction":   "US",
        "enabled":        False,
        "note":           "GPT-mini/nano. Sauber, zuverlässig. Guter Arabisch-Default "
                          "(gpt-4o-mini).",
    },
    "mistral": {
        "kind":           "openai_compat",
        "base_url":       "https://api.mistral.ai/v1",
        "key_env":        "MISTRAL_API_KEY",
        "default_model":  "ministral-3b-latest",
        "trains_on_data": False,          # PAID trainiert nicht (FREE-Tier trainiert!)
        "jurisdiction":   "EU",
        "enabled":        False,
        "note":           "Mistral/Ministral. EU/GDPR, sehr billig. Idealer "
                          "Spanisch-Default. ACHTUNG: nur PAID nutzen (Free-Tier trainiert).",
    },
    "groq": {
        "kind":           "openai_compat",
        "base_url":       "https://api.groq.com/openai/v1",
        "key_env":        "GROQ_API_KEY",
        "default_model":  "allam-2-7b",   # Modell-ID auf Groq vor Nutzung verifizieren
        "trains_on_data": None,           # UNVERIFIZIERT → vor Default-Nutzung prüfen!
        "jurisdiction":   "US",
        "enabled":        False,
        "note":           "Gratis-Tier mit ALLaM-2-7B (arabisch-nativ!). Daten-Policy "
                          "noch NICHT verifiziert – erst prüfen, dann ggf. Arabisch-Default.",
    },
    "deepseek": {
        "kind":           "openai_compat",
        "base_url":       "https://api.deepseek.com",
        "key_env":        "DEEPSEEK_API_KEY",
        "default_model":  "deepseek-chat",
        "trains_on_data": True,           # ⚠ trainiert (Opt-out, default an) + Daten in China
        "jurisdiction":   "CN",
        "enabled":        False,
        "note":           "Absolut billigst + SOTA-Arabisch, ABER trainiert auf Daten + "
                          "China-Jurisdiktion + Sicherheitsberichte → MUSS laut geflaggt werden.",
    },
    "gemini": {
        "kind":           "openai_compat",
        "base_url":       "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env":        "GEMINI_API_KEY",
        "default_model":  "gemini-2.5-flash-lite",
        "trains_on_data": True,           # ⚠ FREE-Tier trainiert + menschliche Reviewer (paid nicht)
        "jurisdiction":   "US",
        "enabled":        False,
        "note":           "Nur als Opt-in-Notpfad. Free-Tier trainiert + Reviewer lesen mit "
                          "→ laut flaggen. Paid-Gemini trainiert nicht.",
    },
}


def get(name: str) -> dict:
    """Liefert den Provider-Eintrag (oder den lokalen Default als Fallback)."""
    return PROVIDERS.get(name) or PROVIDERS["local"]


def trains_on_data(name: str) -> bool:
    """True, wenn der Provider laut Policy auf Nutzdaten trainiert (→ laut flaggen).
    None (unverifiziert) wird vorsichtshalber als True behandelt."""
    flag = get(name).get("trains_on_data")
    return flag is not False   # True und None → flaggen
