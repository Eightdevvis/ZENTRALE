# core/prices.py
#
# Was ein Cloud-Turn kostet. Reine Datentabelle plus eine Rechnung — keine
# Logik, keine Netz-Zugriffe, keine Abhängigkeiten.
#
# ── Warum das eine eigene Datei ist ────────────────────────────────────
# Preise ändern sich, Modelle kommen dazu, Einführungspreise laufen aus. Wer
# das nachzieht, soll GENAU EINE Datei anfassen müssen und dabei sofort sehen,
# von wann der Stand ist. In providers.py hätte es sich mit Endpunkten und
# Keys vermischt.
#
# ── Warum es das überhaupt gibt ────────────────────────────────────────
# Sasha ist knapp bei Kasse. Eine Schätzung, die er nach jedem Turn im
# Terminal sieht, ist der Unterschied zwischen "ich glaube, das ist teuer" und
# "das waren 0,4 Cent". Ohne diese Zahl ist jede Sparmaßnahme Bauchgefühl —
# und der Budget-Deckel hätte nichts, worauf er sich stützen könnte.
#
# ⚠ Es sind SCHÄTZUNGEN. Die echte Rechnung macht der Anbieter. Für
# Größenordnung, Vergleich zwischen Modellen und den Budget-Deckel reicht das;
# als Buchhaltung taugt es nicht.

# Stand der Preise. Beim Aktualisieren mitziehen — eine Tabelle ohne Datum
# ist eine Tabelle, der man nicht ansieht, dass sie falsch ist.
STAND = "2026-08-15"

# Dollar pro EINE MILLION Token: (input, output).
#
# cache_read / cache_write sind MULTIPLIKATOREN auf den Input-Preis:
#   Anthropic  – Lesen 0,1× / Schreiben 1,25× (5 min) bzw. 2,0× (1 h)
#   OpenAI-kompatible – meist impliziter Cache ohne steuerbaren Aufpreis;
#     wir rechnen dort konservativ mit 1,0× (also: kein Rabatt angenommen).
PREISE = {
    # ── Anthropic ────────────────────────────────────────────────────
    "claude-opus-5":     {"in": 5.00, "out": 25.00, "cache_read": 0.10, "cache_write": 2.00},
    "claude-opus-4-8":   {"in": 5.00, "out": 25.00, "cache_read": 0.10, "cache_write": 2.00},
    "claude-sonnet-5":   {"in": 3.00, "out": 15.00, "cache_read": 0.10, "cache_write": 2.00},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, "cache_read": 0.10, "cache_write": 2.00},
    "claude-haiku-4-5":  {"in": 1.00, "out":  5.00, "cache_read": 0.10, "cache_write": 2.00},
    "claude-fable-5":    {"in": 10.00, "out": 50.00, "cache_read": 0.10, "cache_write": 2.00},

    # ── Alibaba / DashScope ──────────────────────────────────────────
    "qwen-plus":         {"in": 0.40, "out": 1.20},
    "qwen-turbo":        {"in": 0.05, "out": 0.20},
    "qwen-max":          {"in": 1.60, "out": 6.40},
    "text-embedding-v3": {"in": 0.02, "out": 0.00},

    # ── Weitere (Platzhalter bis zum ersten echten Key) ──────────────
    # Bewusst eingetragen, damit ein Providerwechsel nicht an einer fehlenden
    # Zeile hängt. Vor dem produktiven Einsatz gegen die Preisseite prüfen.
    "gpt-4o":                  {"in": 2.50, "out": 10.00},
    "gpt-4o-mini":             {"in": 0.15, "out":  0.60},
    "grok-4":                  {"in": 3.00, "out": 15.00},
    "gemini-2.5-pro":          {"in": 1.25, "out": 10.00},
    "gemini-2.5-flash":        {"in": 0.30, "out":  2.50},
    "deepseek-chat":           {"in": 0.27, "out":  1.10},
    "llama-3.3-70b-versatile": {"in": 0.59, "out":  0.79},
    "mistral-large-latest":    {"in": 2.00, "out":  6.00},
}

# Wenn ein Modell nicht in der Tabelle steht: lieber grob schätzen als gar
# nichts anzeigen. Eine fehlende Zeile darf den Budget-Deckel nicht blind
# machen — sonst schützt er ausgerechnet dann nicht, wenn etwas Neues läuft.
UNBEKANNT = {"in": 3.00, "out": 15.00, "cache_read": 0.10, "cache_write": 2.00}

USD_EUR = 0.92   # grobe Umrechnung; für Größenordnungen völlig ausreichend


def fuer(model: str) -> dict:
    """Preiszeile für ein Modell. Unbekannt → konservative Schätzung."""
    return PREISE.get(model or "", UNBEKANNT)


def bekannt(model: str) -> bool:
    """Steht das Modell wirklich in der Tabelle? (Für ehrliche Anzeige: eine
    geschätzte Zahl soll als geschätzt erkennbar sein.)"""
    return (model or "") in PREISE


def euro(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
         cache_read: int = 0, cache_write: int = 0) -> float:
    """
    Was dieser eine Call ungefähr gekostet hat, in Euro.

    input_tokens  – ungecachter Input (voller Preis)
    cache_read    – aus dem Cache gelesen (bei Anthropic 10 %)
    cache_write   – frisch in den Cache geschrieben (bei Anthropic 2,0× bei 1 h)
    output_tokens – Ausgabe, inklusive Denken. Der teuerste Posten.
    """
    p = fuer(model)
    pro_token_in = p["in"] / 1_000_000
    usd = (
        input_tokens  * pro_token_in
        + cache_read  * pro_token_in * p.get("cache_read", 1.0)
        + cache_write * pro_token_in * p.get("cache_write", 1.0)
        + output_tokens * p["out"] / 1_000_000
    )
    return usd * USD_EUR


def billigstes(kandidaten) -> str | None:
    """
    Das billigste Modell aus einer Auswahl — nach Ausgabepreis, weil der bei
    einem Chat den Ausschlag gibt (Ausgabe kostet das Fünffache der Eingabe).
    Für den Budget-Rückfall: lieber weiterreden auf einem billigen Modell als
    gar nicht mehr reden.
    """
    kandidaten = [m for m in (kandidaten or []) if m]
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda m: (fuer(m)["out"], fuer(m)["in"]))
