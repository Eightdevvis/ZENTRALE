# tutor/langs/ — Persona/Sprach-Portal des Tutors.
#
# Der Tutor ist KEIN Chinesisch-Tutor, sondern ein Framework, auf das Sprachen
# als PERSONAS draufgelegt werden. Jede Sprache = ein Ordner hier drin = eine
# benannte Figur mit eigenem Charakter, eigenem Land und eigenem AI-Anbieter
# (Provider/Modell ist entkoppelt, siehe tutor/providers.py).
#
# ── Eine Sprache dazubauen ──────────────────────────────────────────────
#   1. Ordner tutor/langs/<code>/ anlegen, __init__.py mit PROFILE = profile(…)
#   2. prompt.md IN DER ZIELSPRACHE hand-tunen (siehe base.py, das ist der Hebel,
#      der das Modell in der Sprache hält) + prompt.de.md als Referenz daneben
#   3. tool_texts + phrases in der Zielsprache, expect.json (Register-Leiter),
#      seeds/news.json + seeds/tv.json
#   4. enabled=True setzen
# Diese Datei muss dafür NICHT angefasst werden — sie findet den Ordner selbst.
#
# ── Was NICHT hier reingehört ───────────────────────────────────────────
# Lernstand (Vokabeln, Strukturen, Persona-Notizen). Der ist pro Sprache in
# tutor/data/<code>/ und gitignored. Hier liegt nur, was zur SPRACHE gehört und
# mit dem Repo ausgeliefert wird (Prompt, Beschriftung, Seeds).
#
# ── LIVE: zh (Ling Ling). Skizzen: fr, ru, ar, es ───────────────────────

import os
import pkgutil
import importlib

from .base import (profile, build_prompt, load_text, load_json,   # noqa: F401
                   expect_from_ladder, DEFAULTS)

_DIR = os.path.dirname(os.path.abspath(__file__))

PROFILES = {}


def _discover():
    """Jedes Unterpaket mit einem PROFILE einsammeln. Ein kaputtes Sprach-Paket
    darf die anderen nicht mitreißen — es fällt einzeln aus."""
    for mod in pkgutil.iter_modules([_DIR]):
        if not mod.ispkg or mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module("." + mod.name, __name__)
        except Exception as e:
            print(f"[tutor.langs] Sprach-Paket '{mod.name}' übersprungen: {e}")
            continue
        p = getattr(m, "PROFILE", None)
        if isinstance(p, dict):
            PROFILES[mod.name] = p


_discover()


def get(lang: str = None) -> dict:
    """Profil einer Sprache. Unbekannt/None → zh (die einzige LIVE-Sprache);
    fehlt auch die, das erste Paket, das sich finden ließ."""
    code = (lang or "zh").strip().lower()
    if code in PROFILES:
        return PROFILES[code]
    if "zh" in PROFILES:
        return PROFILES["zh"]
    return next(iter(PROFILES.values()))


def expect(lang: str, n: int) -> str:
    """Erwartungs-Bremse der Sprache für n bekannte Wörter/Strukturen.
    Die Leiter ist Paket-DATEN (expect.json), kein Code — siehe base.py."""
    return expect_from_ladder(get(lang).get("expect_ladder"), n)


def enabled() -> list:
    """Codes der fertig verdrahteten Sprachen (Skizzen raus)."""
    return [c for c, p in PROFILES.items() if p.get("enabled")]
