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

PROVIDERS = {
    "qwen": {
        "base_url":     "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env":      "DASHSCOPE_API_KEY",
        "jurisdiction": "SG",
        "note":         "Alibaba Qwen (intl/Singapur). Sashas aktiver Cloud-Key.",
    },
    "claude": {
        "base_url":     "https://api.anthropic.com",
        "key_env":      "ANTHROPIC_API_KEY",
        "jurisdiction": "US",
        "note":         "Anthropic — Verifikations-Pfad.",
    },
    "openai": {
        "base_url":     "https://api.openai.com/v1",
        "key_env":      "OPENAI_API_KEY",
        "jurisdiction": "US",
    },
    "mistral": {
        "base_url":     "https://api.mistral.ai/v1",
        "key_env":      "MISTRAL_API_KEY",
        "jurisdiction": "EU",
    },
}


def get(name: str) -> dict:
    """Provider-Eintrag oder {} — anders als beim Tutor gibt es hier KEINEN
    local-Fallback: wer hier fragt, fragt nach einem Cloud-Endpunkt."""
    return PROVIDERS.get(name) or {}


def configured() -> str | None:
    """Name des ersten Cloud-Providers, dessen Key in der Env liegt — oder None.
    Keys kommen über ai_config aus data/ai_config.json (bzw. dem Legacy-Fallback)."""
    import os
    for name, p in PROVIDERS.items():
        env = p.get("key_env")
        if env and os.environ.get(env):
            return name
    return None
