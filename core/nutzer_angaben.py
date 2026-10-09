# core/nutzer_angaben.py
#
# Wer der Nutzer ist, soweit der Prompt es braucht: Name und Pronomen aus den
# Einstellungen, eingesetzt in die Prompt-Texte der Schienen (core/profil/)
# und die Bausteine in core/ki_prompt.py.
#
# 2026-10-09, Produkt-Inventur Punkt 1 („leerer Erststart",
# memory/system/produkt_inventur.md): Persona und Meta-Regeln nannten Sasha
# fest beim Namen. Eine andere Installation hätte ihren Nutzer „Sasha"
# genannt. Jetzt stehen Platzhalter im Text; die Standardwerte sind genau,
# was vorher dastand — für Sasha ist der Prompt byte-gleich
# (tests/test_prompt_nutzer.py), der Prompt-Cache bleibt also warm.
#
# Einstellungen (ai_config.setting, Env ZENTRALE_NUTZER_NAME bzw.
# ZENTRALE_NUTZER_PRONOMEN):
#   nutzer_name      Standard „Sasha"
#   nutzer_pronomen  „er" (Standard — so sprechen die Prompts heute von Sasha)
#                    oder „sie"; Unbekanntes fällt auf den Standard zurück.
# Pro Installation fest, nicht pro Zug: der feste Kopf ändert sich nur, wenn
# jemand die Einstellung ändert.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import ai_config

STANDARD_NAME = "Sasha"
STANDARD_PRONOMEN = "er"

# Die Formen je Pronomen. Schlüssel = Platzhalter ohne Klammern; was mit
# Großbuchstaben beginnt, steht am Satzanfang.
FORMEN = {
    "er": {
        "er": "er", "Er": "Er", "ihn": "ihn", "ihm": "ihm",
        "sein": "sein", "seine": "seine", "seinen": "seinen",
        "seinem": "seinem", "seiner": "seiner",
        "ein_muendiger_erwachsener": "ein mündiger Erwachsener",
    },
    "sie": {
        "er": "sie", "Er": "Sie", "ihn": "sie", "ihm": "ihr",
        "sein": "ihr", "seine": "ihre", "seinen": "ihren",
        "seinem": "ihrem", "seiner": "ihrer",
        "ein_muendiger_erwachsener": "eine mündige Erwachsene",
    },
}


def name() -> str:
    return str(ai_config.setting("nutzer_name", STANDARD_NAME) or "").strip() or STANDARD_NAME


def pronomen() -> str:
    p = str(ai_config.setting("nutzer_pronomen", STANDARD_PRONOMEN) or "").strip().lower()
    return p if p in FORMEN else STANDARD_PRONOMEN


def _genitiv(n: str) -> str:
    # „Sashas", aber „Jonas'" — deutsche Regel für Namen auf s, ß, x, z.
    return n + "'" if n[-1:].lower() in ("s", "ß", "x", "z") else n + "s"


def ersetzungen() -> dict:
    """Platzhalter → Text, für die aktuellen Einstellungen."""
    n = name()
    raus = {"{nutzer}": n, "{nutzers}": _genitiv(n),
            "{NUTZER}": n.upper(), "{NUTZERS}": _genitiv(n).upper()}
    raus.update({"{" + k + "}": v for k, v in FORMEN[pronomen()].items()})
    return raus


def einsetzen(vorlage: str) -> str:
    """Die Platzhalter einer Vorlage füllen. Nur die bekannten — andere
    geschweifte Klammern im Text bleiben, wie sie sind (kein str.format)."""
    for platzhalter, text in ersetzungen().items():
        vorlage = vorlage.replace(platzhalter, text)
    return vorlage
