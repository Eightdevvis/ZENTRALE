# core/selbstauskunft.py
#
# Die Selbstauskunft der KI: feste Felder am Werkzeug `antwort` (nur gross),
# in denen das Modell sagt, WAS seine Antwort tut — unabhängig davon, in
# welcher Sprache sie geschrieben ist.
#
#   text             die Antwort selbst
#   erledigt         Bereiche, in denen die Antwort meldet, dass in DIESEM Zug
#                    etwas geändert wurde (Werte aus BEREICHE)
#   fragt_erlaubnis  endet sie mit der Frage, ob ein Werkzeug benutzt werden soll
#   schiebt_auf      verschiebt sie einen Auftrag auf später
#   ungeprueft       Aussagen, die kein Werkzeug belegt hat (optional)
#
# Warum (Sasha, 2026-10-10): „für jeden bereich eine wortliste … skaliert nur
# so mäßig … was passiert wenn zentrale später von anders sprachlern benutzt
# wird" — „langfristig ganz ohne wörter ist irgendwie schlauer". Die Felder
# vergleicht Python mit dem Werkzeug-Protokoll (core/ehrlichkeit.py); die
# Wortlisten bleiben der Rückfall, wenn das Modell frei antwortet, und das
# Netz, wenn Feld und Text sich widersprechen.
#
# Hier steht nur die FORM: das Vokabular der Bereiche und wie die Felder
# gelesen werden. Was ein Feld bedeutet, prüft core/ehrlichkeit.py.
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md): kein Fach, kein Modell.

from dataclasses import dataclass, field

# Die Bereiche, in denen etwas GEÄNDERT werden kann (die Schlüssel von
# ehrlichkeit.BEREICH ohne „netz" — dort wird nur gelesen). Eine Quelle für
# das Schema des Werkzeugs (werkzeug_register) und den Prüfer; der Test
# hält beide deckungsgleich (tests/test_selbstauskunft.py). Reihenfolge fest:
# das Schema steht im gecachten Präfix.
BEREICHE = ("kalender", "notiz", "ablage", "messreihe", "skill")

# Das Schema der Felder, wie es auf der gross-Schiene ans Modell geht
# (werkzeug_register, Eintrag antwort). Die Erklärung steht in den Feldern,
# nicht im Werkzeug-Text: der zählt gegen das Budget der Beschreibungen.
FELDER = {
    "erledigt": {
        "type": "array",
        "items": {"type": "string", "enum": list(BEREICHE)},
        "description": "Bereiche, in denen deine Antwort meldet, dass in DIESEM Zug etwas "
                       "geändert wurde. Leer, wenn nichts geändert wurde.",
    },
    "fragt_erlaubnis": {
        "type": "boolean",
        "description": "true, wenn die Antwort mit der Frage endet, ob du ein Werkzeug "
                       "benutzen sollst.",
    },
    "schiebt_auf": {
        "type": "boolean",
        "description": "true, wenn du einen Auftrag auf später verschiebst, obwohl dir "
                       "keine Angabe fehlt (eine Rückfrage zählt nicht).",
    },
    "ungeprueft": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional: Aussagen der Antwort, die kein Werkzeug belegt hat.",
    },
}
PFLICHT = ["text", "erledigt", "fragt_erlaubnis", "schiebt_auf"]


@dataclass
class Auskunft:
    text: str = ""
    erledigt: list = field(default_factory=list)       # nur bekannte Bereiche, sortiert
    fragt_erlaubnis: bool = False
    schiebt_auf: bool = False
    ungeprueft: list = field(default_factory=list)
    fremd: list = field(default_factory=list)          # unbekannte Bereichs-Werte

    def als_dict(self) -> dict:
        d = {"erledigt": list(self.erledigt), "fragt_erlaubnis": self.fragt_erlaubnis,
             "schiebt_auf": self.schiebt_auf}
        if self.ungeprueft:
            d["ungeprueft"] = list(self.ungeprueft)
        if self.fremd:
            d["fremd"] = list(self.fremd)
        return d


def _bool(wert) -> bool:
    # Manche Modelle schicken "true"/"false" als Text (OpenAI-kompatible
    # Anbieter halten sich nicht immer ans Schema).
    if isinstance(wert, str):
        return wert.strip().casefold() in ("true", "ja", "yes", "1")
    return bool(wert)


def _liste(wert) -> list:
    if wert is None:
        return []
    if isinstance(wert, str):
        wert = [w for w in wert.replace(";", ",").split(",")]
    if not isinstance(wert, (list, tuple)):
        return []
    return [" ".join(str(w).split()) for w in wert if str(w).strip()]


def lesen(args) -> Auskunft:
    """Die Argumente eines antwort-Aufrufs → Auskunft. Tolerant: fehlende
    Felder sind leer/false, unbekannte Bereiche landen in `fremd` (ein
    Bereich, den das Schema nicht kennt, kann nichts belegen und nichts
    behaupten, was Python nachprüfen könnte)."""
    args = args if isinstance(args, dict) else {}
    bekannt, fremd = [], []
    for b in _liste(args.get("erledigt")):
        k = b.casefold()
        (bekannt if k in BEREICHE else fremd).append(k)
    return Auskunft(
        text=str(args.get("text") or "").strip(),
        erledigt=sorted(set(bekannt), key=BEREICHE.index),
        fragt_erlaubnis=_bool(args.get("fragt_erlaubnis")),
        schiebt_auf=_bool(args.get("schiebt_auf")),
        ungeprueft=_liste(args.get("ungeprueft"))[:20],
        fremd=sorted(set(fremd)))
