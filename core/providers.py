# core/providers.py
#
# Cloud-Provider-Registry des KERNS — die Endpunkte, an denen ZENTRALE selbst
# erkennt: „ist von dieser Maschine aus überhaupt eine Cloud-KI erreichbar?"
#
# ── Warum es diese Datei gibt ───────────────────────────────────────────
# ai_backends brauchte dafür bis 2026-07-16 core/tutor_providers.py — der Kern
# griff also in die Tabelle eines Addons, um seine eigene EXTERNAL-Box zu füllen.
# Pfeil verkehrt herum. Diese Registry gehört dem Kern.
#
# ── Verhältnis zu tutor_providers ───────────────────────────────────────
# Der Tutor hat seine EIGENE, größere Liste (inkl. Skizzen + Policy-Notizen),
# weil er am Ende andere Modelle nutzt als der Kern. Bewusste Entscheidung
# (2026-07-16): lieber zwei kleine Tabellen als eine geteilte, an der beide
# zerren — so ist tutor/ später ohne Rückgriff auf core/providers.py rausziehbar.
# Preis: die paar Welt-Fakten unten (base_url/key_env) stehen an zwei Stellen.
# Ändert ein Anbieter seinen Endpunkt, beide prüfen.
#
# Der Kern selbst REDET aktuell mit keiner Cloud (chat/news laufen local-only,
# siehe MODULE_BACKENDS in ai_backends.py). Diese Tabelle beantwortet nur die
# Erreichbarkeits-Frage. Wächst der Kern mal einen echten Cloud-Pfad, kommt der
# Client hierher — nicht in den Tutor zurück.

# kind sagt, WELCHES Kern-Modul den Provider bedienen kann:
#   'anthropic'      → core/cloud.py        (tool_use-Blöcke, cache_control)
#   'openai_compat'  → core/cloud_openai.py (tool_calls, /v1/chat/completions)
# Ohne kind kann der Kern mit dem Provider nicht reden, auch wenn ein Key da
# ist — die Erreichbarkeit allein macht ihn noch nicht nutzbar.
#
# ── Warum hier Anbieter ohne Key stehen ────────────────────────────────
# Fast alle sprechen inzwischen OpenAI-kompatibel. Ein neuer Anbieter ist damit
# HIER EINE ZEILE, kein neues Modul — core/cloud_openai.py bedient sie alle.
# Nur Anthropic hat einen eigenen Dialekt (tool_use-Blöcke, cache_control) und
# deshalb ein eigenes Modul.
#
# Die Einträge stehen bewusst schon da, bevor die Keys existieren: umschalten
# soll später eine Config-Zeile sein und kein Umbau. `configured()` überspringt
# alles ohne Key, `preference()` sortiert nur.
PROVIDERS = {
    "claude": {
        "base_url":      "https://api.anthropic.com",
        "key_env":       "ANTHROPIC_API_KEY",
        "kind":          "anthropic",
        "default_model": "claude-sonnet-5",
        "jurisdiction":  "US",
        "note":          "Anthropic — der Ziel-Pfad des Kerns. Einziger "
                         "Anbieter mit steuerbarem Prompt-Cache "
                         "(cache_control) und effort-Regler.",
    },
    "qwen": {
        "base_url":      "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env":       "DASHSCOPE_API_KEY",
        "kind":          "openai_compat",
        "default_model": "qwen-plus",
        "jurisdiction":  "SG",
        "note":          "Alibaba Qwen (intl/Singapur), no-train verifiziert. "
                         "Billig — die Rückfallebene, wenn das Budget alle ist.",
    },
    "openai": {
        "base_url":      "https://api.openai.com/v1",
        "key_env":       "OPENAI_API_KEY",
        "kind":          "openai_compat",
        "default_model": "gpt-4o",
        "jurisdiction":  "US",
    },
    "grok": {
        "base_url":      "https://api.x.ai/v1",
        "key_env":       "XAI_API_KEY",
        "kind":          "openai_compat",
        "default_model": "grok-4",
        "jurisdiction":  "US",
        "note":          "xAI, OpenAI-kompatibler Endpoint.",
    },
    "gemini": {
        # Google fährt neben seiner eigenen API einen OpenAI-kompatiblen
        # Endpoint — darüber passt Gemini durch dieselbe Naht wie alle anderen.
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env":       "GEMINI_API_KEY",
        "kind":          "openai_compat",
        "default_model": "gemini-2.5-pro",
        "jurisdiction":  "US",
    },
    "deepseek": {
        "base_url":      "https://api.deepseek.com/v1",
        "key_env":       "DEEPSEEK_API_KEY",
        "kind":          "openai_compat",
        "default_model": "deepseek-chat",
        "jurisdiction":  "CN",
        "note":          "⚠ Jurisdiktion CN — bewusst wählen.",
    },
    "groq": {
        "base_url":      "https://api.groq.com/openai/v1",
        "key_env":       "GROQ_API_KEY",
        "kind":          "openai_compat",
        "default_model": "llama-3.3-70b-versatile",
        "jurisdiction":  "US",
        "note":          "Groq — sehr schnell, offene Modelle.",
    },
    "mistral": {
        "base_url":      "https://api.mistral.ai/v1",
        "key_env":       "MISTRAL_API_KEY",
        "kind":          "openai_compat",
        "default_model": "mistral-large-latest",
        "jurisdiction":  "EU",
    },
}


def get(name: str) -> dict:
    """Provider-Eintrag oder {} — anders als beim Tutor gibt es hier KEINEN
    local-Fallback: wer hier fragt, fragt nach einem Cloud-Endpunkt."""
    return PROVIDERS.get(name) or {}


# Welchen Provider der Kern nimmt, wenn MEHRERE Keys gesetzt sind — bewusst als
# eigene Liste, nicht als Reihenfolge der Tabelle oben. Vorher fiel die Wahl über
# die Einfüge-Reihenfolge von PROVIDERS: qwen stand vorne, also gewann bei
# gesetztem DASHSCOPE_API_KEY still Qwen, obwohl der Kern-Cloud-Pfad auf
# Anthropic gebaut wird. Diese Kopplung („Tabellen-Position = Vorrang") ist die
# Art Falle, die man beim nächsten Umsortieren wieder tritt.
# Nicht gelistete Provider hängen hinten dran, in Tabellen-Reihenfolge.
PREFERENCE = ("claude", "qwen", "openai", "grok", "gemini",
              "deepseek", "groq", "mistral")

# Harte Vorwahl per Env, falls mal gezielt ein anderer dran soll (Vergleich,
# Kostenbremse). Unbekannter/keyloser Name → wird ignoriert, normale Reihenfolge.
PREFERENCE_ENV = "ZENTRALE_CLOUD_PROVIDER"


def preference() -> list[str]:
    """Provider-Namen in Vorrang-Reihenfolge, inklusive der in PREFERENCE
    vergessenen (die landen hinten). Reine Namensliste, prüft keine Keys."""
    rest = [n for n in PROVIDERS if n not in PREFERENCE]
    return [n for n in PREFERENCE if n in PROVIDERS] + rest


def configured() -> str | None:
    """Name des bevorzugten Cloud-Providers, dessen Key in der Env liegt — oder
    None. Keys kommen über ai_config aus data/ai_config.json (bzw. dem
    Legacy-Fallback)."""
    import os

    def has_key(name: str) -> bool:
        env = (PROVIDERS.get(name) or {}).get("key_env")
        return bool(env and os.environ.get(env))

    forced = (os.environ.get(PREFERENCE_ENV) or "").strip()
    if forced and has_key(forced):
        return forced

    for name in preference():
        if has_key(name):
            return name
    return None
