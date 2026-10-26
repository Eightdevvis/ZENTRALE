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
# Anthropic-Zeilen geprüft gegen
# https://platform.claude.com/docs/en/about-claude/pricing (26.10.2026).
STAND = "2026-10-26"

# Dollar pro EINE MILLION Token: (input, output).
#
# cache_read / cache_write_5m / cache_write_1h sind MULTIPLIKATOREN auf den
# Input-Preis:
#   Anthropic  – Schreiben 1,25× (5 min) bzw. 2,0× (1 h);
#                Lesen 0,1×, bei Opus 5.5 und Sonnet 5.5 nur 0,05×.
#   OpenAI-kompatible – meist impliziter Cache ohne steuerbaren Aufpreis;
#     wir rechnen dort konservativ mit 1,0× (also: kein Rabatt angenommen).
#
# Bis 26.10.2026 gab es nur EIN cache_write = 2,0× für alles. Das stimmte für
# core/cloud.py (Breakpoints mit ttl "1h"), war aber für 5-min-Breakpoints
# 60 % zu hoch. Jetzt sagt der Aufrufer die Dauer (euro(..., cache_ttl=)).
#
# staffel: Preis hängt an der Länge des Prompts (Haiku 5.5). Prompt =
# input + cache_read + cache_write EINES Aufrufs; liegt er ÜBER "ab", gilt
# die ganze Zeile aus der Staffel (auch für die Ausgabe).
_A   = {"cache_read": 0.10, "cache_write_5m": 1.25, "cache_write_1h": 2.00}
_A05 = {"cache_read": 0.05, "cache_write_5m": 1.25, "cache_write_1h": 2.00}

PREISE = {
    # ── Anthropic ────────────────────────────────────────────────────
    "claude-opus-5-5":   {"in": 4.00, "out": 20.00, **_A05},
    "claude-opus-5":     {"in": 5.00, "out": 25.00, **_A},
    "claude-opus-4-8":   {"in": 5.00, "out": 25.00, **_A},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, **_A05},
    # Sonnet 5: $2/$10 war als Einführungspreis bis 31.08.2026 angekündigt,
    # ist laut Preisseite aber DAUERHAFT der Preis — die Erhöhung auf $3/$15
    # zum 01.09. findet nicht statt. Bis 26.10. stand hier $3/$15 → alle
    # Sonnet-5-Kosten waren 1,5-fach zu hoch verbucht.
    "claude-sonnet-5":   {"in": 2.00, "out": 10.00, **_A},
    "claude-sonnet-4-6": {"in": 3.00, "out": 15.00, **_A},
    # Haiku 5.5: $0,10/$0,50 für Prompts bis 100.000 Token, darüber
    # $0,50/$2,50 (Cache entsprechend). Gilt je Aufruf, nicht kumuliert.
    "claude-haiku-5-5":  {"in": 0.10, "out":  0.50, **_A,
                          "staffel": {"ab": 100_000, "in": 0.50, "out": 2.50}},
    "claude-haiku-4-5":  {"in": 1.00, "out":  5.00, **_A},
    "claude-fable-5":    {"in": 10.00, "out": 50.00, **_A},

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
UNBEKANNT = {"in": 3.00, "out": 15.00, **_A}

USD_EUR = 0.92   # grobe Umrechnung; für Größenordnungen völlig ausreichend


# Seit 2026-10-07 zeigt /modell ALLE Modelle, die ein Anbieter meldet
# (core/modell_liste.py) — also auch solche, die hier fehlen. Damit die nicht
# 0 € kosten, bevor jemand die Zeile nachträgt:
#   1. Datums-Fassungen auf den Grundnamen („claude-sonnet-4-5-20250929",
#      „gpt-4o-2024-08-06") und „models/…" (Gemini) abschneiden.
#   2. Gehört der Name sichtbar zu einer teuren Familie (opus, fable), deren
#      teuerste Zeile — UNBEKANNT läge dort zu niedrig.
#   3. Sonst UNBEKANNT (Sonnet-Preis: über fast allem anderen auf der Liste).
_TEUERE_FAMILIEN = ("fable", "opus")


def _grundname(model: str) -> str:
    import re
    m = (model or "").strip()
    if m.startswith("models/"):
        m = m[len("models/"):]
    m = re.sub(r"-(\d{8}|\d{4}-\d{2}-\d{2})$", "", m)   # -20250929 / -2024-08-06
    return re.sub(r"-latest$", "", m) if m not in PREISE else m


def _zeile(model: str):
    """Die echte Preiszeile oder None (ohne Schätzung)."""
    if (model or "") in PREISE:
        return PREISE[model]
    return PREISE.get(_grundname(model))


def fuer(model: str) -> dict:
    """Preiszeile für ein Modell. Unbekannt → konservative Schätzung."""
    zeile = _zeile(model)
    if zeile is not None:
        return zeile
    name = (model or "").lower()
    for familie in _TEUERE_FAMILIEN:
        if familie in name:
            return max((p for m, p in PREISE.items() if familie in m),
                       key=lambda p: p["out"])
    return UNBEKANNT


def bekannt(model: str) -> bool:
    """Steht das Modell wirklich in der Tabelle? (Für ehrliche Anzeige: eine
    geschätzte Zahl soll als geschätzt erkennbar sein.)"""
    return _zeile(model) is not None


def euro(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
         cache_read: int = 0, cache_write: int = 0,
         cache_ttl: str = "1h") -> float:
    """
    Was dieser eine Call ungefähr gekostet hat, in Euro.

    input_tokens  – ungecachter Input (voller Preis)
    cache_read    – aus dem Cache gelesen (bei Anthropic 10 %, teils 5 %)
    cache_write   – frisch in den Cache geschrieben
    cache_ttl     – Dauer des Cache, in den geschrieben wurde: "5m" (1,25×)
                    oder "1h" (2,0×). Unbekannt → "1h", die teurere Annahme;
                    core/cloud.py schreibt standardmäßig mit 1 h.
    output_tokens – Ausgabe, inklusive Denken. Der teuerste Posten.
    """
    p = fuer(model)
    staffel = p.get("staffel")
    if staffel and input_tokens + cache_read + cache_write > staffel["ab"]:
        p = {**p, "in": staffel["in"], "out": staffel["out"]}
    schreib = p.get("cache_write_5m" if cache_ttl == "5m" else "cache_write_1h", 1.0)
    pro_token_in = p["in"] / 1_000_000
    usd = (
        input_tokens  * pro_token_in
        + cache_read  * pro_token_in * p.get("cache_read", 1.0)
        + cache_write * pro_token_in * schreib
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
