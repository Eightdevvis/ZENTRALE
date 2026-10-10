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
#   auftrag          jeder Teil von Sashas Auftrag mit Stand (erledigt | offen |
#                    abgelehnt), Grund und dem sicheren Teil (2026-10-10,
#                    Prüfstand f01k: ein Teil fiel still weg — „Pause" fehlte,
#                    kein Satz war falsch, also schlug kein Prüfer an).
#                    Geprüft in core/auftrag_abrechnung.py.
#   nicht_gefunden   was die Antwort als „nicht da / nicht gefunden" meldet
#                    (optional, 2026-10-10, Prüfstand f10) — sprachfrei für
#                    den Prüfer „nur ein Stichwort gesucht".
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
    # Auftrags-Abrechnung (2026-10-10): jeder Teil, keiner weggelassen. Die
    # Erklärung steht hier in den Feldern (zählt nicht gegen den Kopf).
    "auftrag": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "was": {"type": "string",
                        "description": "Ein Teil des Auftrags, kurz in den Worten des Nutzers."},
                "stand": {"type": "string", "enum": ["erledigt", "offen", "abgelehnt"]},
                "werkzeug": {"type": "string",
                             "description": "Bei erledigt: das Werkzeug, das es in diesem Zug "
                                            "getan hat."},
                "grund": {"type": "string",
                          "description": "Bei offen/abgelehnt: warum, kurz (was fehlt)."},
                "sicherer_teil": {"type": "string",
                                  "description": "Bei offen: was davon sofort ginge, aber noch "
                                                 "nicht getan ist (z. B. „Pause ab heute“). "
                                                 "Leer, wenn nichts davon sicher ist."},
            },
            "required": ["was", "stand"],
        },
        "description": "Jeder Teil des Auftrags in der letzten Nachricht des Nutzers, "
                       "keiner weggelassen — auch der, den du nicht oder noch nicht tust. "
                       "Leer bei reinen Fragen oder Plaudern.",
    },
    "nicht_gefunden": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional: was die Antwort als nicht vorhanden oder nicht gefunden "
                       "meldet.",
    },
}
PFLICHT = ["text", "erledigt", "fragt_erlaubnis", "schiebt_auf", "auftrag"]

# Stand eines Auftrags-Teils. Ein unbekannter Wert gilt als „offen": dann
# sieht Sasha ihn als offen, und kein Prüfer verlangt einen Beleg für etwas,
# das das Modell nicht klar als erledigt gemeldet hat.
STAENDE = ("erledigt", "offen", "abgelehnt")


@dataclass
class Auskunft:
    text: str = ""
    erledigt: list = field(default_factory=list)       # nur bekannte Bereiche, sortiert
    fragt_erlaubnis: bool = False
    schiebt_auf: bool = False
    ungeprueft: list = field(default_factory=list)
    fremd: list = field(default_factory=list)          # unbekannte Bereichs-Werte
    # None: das Feld fehlte ganz; []: ausdrücklich nichts zu tun.
    auftrag: list | None = None                         # [{was, stand, werkzeug?, grund?, sicherer_teil?}]
    nicht_gefunden: list = field(default_factory=list)

    def als_dict(self) -> dict:
        d = {"erledigt": list(self.erledigt), "fragt_erlaubnis": self.fragt_erlaubnis,
             "schiebt_auf": self.schiebt_auf}
        if self.ungeprueft:
            d["ungeprueft"] = list(self.ungeprueft)
        if self.fremd:
            d["fremd"] = list(self.fremd)
        if self.auftrag is not None:
            d["auftrag"] = [dict(p) for p in self.auftrag]
        if self.nicht_gefunden:
            d["nicht_gefunden"] = list(self.nicht_gefunden)
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


def _text(wert, n: int = 200) -> str:
    return " ".join(str(wert or "").split())[:n]


def auftrag_lesen(wert) -> list | None:
    """Das Feld auftrag → [{was, stand, werkzeug?, grund?, sicherer_teil?}],
    oder None, wenn es fehlt. Tolerant: ein Text statt einer Liste wird ein
    offener Punkt, Punkte ohne `was` fallen weg, höchstens 20."""
    if wert is None:
        return None
    if isinstance(wert, str):
        wert = [{"was": wert, "stand": "offen"}] if wert.strip() else []
    if isinstance(wert, dict):
        wert = [wert]
    if not isinstance(wert, (list, tuple)):
        return None
    raus = []
    for p in wert:
        if isinstance(p, str):
            p = {"was": p}
        if not isinstance(p, dict) or not _text(p.get("was")):
            continue
        stand = _text(p.get("stand")).casefold()
        punkt = {"was": _text(p.get("was")),
                 "stand": stand if stand in STAENDE else "offen"}
        for k in ("werkzeug", "grund", "sicherer_teil"):
            if _text(p.get(k)):
                punkt[k] = _text(p.get(k))
        raus.append(punkt)
    return raus[:20]


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
        fremd=sorted(set(fremd)),
        auftrag=auftrag_lesen(args.get("auftrag")),
        nicht_gefunden=_liste(args.get("nicht_gefunden"))[:20])
