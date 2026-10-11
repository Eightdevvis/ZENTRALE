# core/werkzeug_erzeuger/vorlage.py
#
# Die zwei kleinen Sprachen der Anbindungs-Beschreibung (2026-10-11):
#
#   Platzhalter   "{day}", "{kennung.label}", "{alt.time}", "{e.ort}" in
#                 Texten. Der erste Teil nennt ein Argument des Werkzeugs
#                 oder einen der festen Namen kennung / alt / antwort / e.
#                 Ist der ganze Text genau ein Platzhalter, kommt der Wert
#                 unverändert heraus (Zahl bleibt Zahl, Liste bleibt Liste);
#                 sonst wird eingesetzt. Fehlt ein Wert, fällt das Feld weg
#                 (freiwillige Argumente) — in einem Pfad ist das ein Fehler.
#                 "{alt.ort|}" setzt bei fehlendem Wert den Text hinter dem |
#                 ein (hier: nichts) — so wird ein früher leeres Feld beim
#                 Zurückschreiben wieder geleert statt vergessen.
#
#   Zeiger        JSON-Pointer (RFC 6901): "/days/2026-11-03". Eine einzige
#                 Erweiterung: "*" heißt „alle Werte dieser Ebene“ (Liste
#                 oder Objekt) — damit lässt sich „irgendein Tag des Monats“
#                 sagen. Mehr Sprache gibt es nicht: was die Werkstatt
#                 ausfüllt, muss streng prüfbar bleiben.
#
# Fundament-nah, ohne Fach (Teil des Pakets werkzeug_erzeuger, Schicht 3).

import re
import urllib.parse

PLATZHALTER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)(?:\|([^{}]*))?\}")
FESTE_NAMEN = ("kennung", "alt", "antwort", "e")


class Fehlt(Exception):
    """Ein Platzhalter hat keinen Wert (nicht angegeben)."""


class Kennung(str):
    """Eine Kennung als Text; hat sie Teile („2026-11-03|Zahnarzt“), kann man
    sie als {kennung.day} ansprechen."""

    def __new__(cls, text, teile=None):
        obj = super().__new__(cls, text)
        obj.teile = dict(teile or {})
        return obj


def namen(text) -> list:
    """Alle Platzhalter in einem Text (ganze Pfade, z. B. 'kennung.day')."""
    return [m.group(1) for m in PLATZHALTER.finditer(text)] if isinstance(text, str) else []


def alle_namen(wert) -> list:
    """Platzhalter in einem beliebig verschachtelten JSON-Wert."""
    if isinstance(wert, str):
        return namen(wert)
    if isinstance(wert, dict):
        return [n for v in wert.values() for n in alle_namen(v)]
    if isinstance(wert, list):
        return [n for v in wert for n in alle_namen(v)]
    return []


def holen(ctx: dict, pfad: str):
    """Der Wert hinter 'a.b.c' im Kontext; Fehlt, wenn er nicht da/leer ist."""
    erstes, *rest = pfad.split(".")
    if erstes not in ctx:
        raise Fehlt(pfad)
    cur = ctx[erstes]
    for teil in rest:
        if isinstance(cur, Kennung):
            cur = cur.teile.get(teil)
        elif isinstance(cur, dict):
            cur = cur.get(teil)
        elif isinstance(cur, list) and teil.isdigit() and int(teil) < len(cur):
            cur = cur[int(teil)]
        else:
            cur = None
        if cur is None:
            break
    if cur is None:
        raise Fehlt(pfad)
    return cur


def _kodieren(wert, modus: str) -> str:
    text = wert if isinstance(wert, str) else (
        "true" if wert is True else "false" if wert is False else str(wert))
    if modus == "pfad":
        return urllib.parse.quote(text, safe="")
    if modus == "zeiger":
        return text.replace("~", "~0").replace("/", "~1")
    return text


def text(vorlage: str, ctx: dict, modus: str = "text"):
    """Einen Text ausfüllen (modus: text | pfad | zeiger)."""
    ganz = PLATZHALTER.fullmatch(vorlage)
    if ganz and modus == "text":
        return _wert(ctx, ganz)
    return PLATZHALTER.sub(lambda m: _kodieren(_wert(ctx, m), modus), vorlage)


def _wert(ctx: dict, m):
    try:
        return holen(ctx, m.group(1))
    except Fehlt:
        if m.group(2) is None:
            raise
        return m.group(2)


def fuellen(wert, ctx: dict):
    """Einen JSON-Wert ausfüllen. In Objekten fällt ein Feld weg, dessen
    Platzhalter nichts hat (und ein Objekt, das dadurch leer wird)."""
    if isinstance(wert, str):
        return text(wert, ctx)
    if isinstance(wert, list):
        return [fuellen(v, ctx) for v in wert]
    if isinstance(wert, dict):
        raus = {}
        for k, v in wert.items():
            try:
                r = fuellen(v, ctx)
            except Fehlt:
                continue
            if isinstance(v, dict) and not r:
                continue
            raus[k] = r
        return raus
    return wert


# ── Zeiger ─────────────────────────────────────────────────────────────

_NICHTS = object()


def _schritt(cur, teil: str):
    teil = teil.replace("~1", "/").replace("~0", "~")
    if isinstance(cur, dict):
        return cur.get(teil, _NICHTS)
    if isinstance(cur, list) and teil.isdigit() and int(teil) < len(cur):
        return cur[int(teil)]
    return _NICHTS


def zeiger_alle(daten, zeiger: str) -> list:
    """Alle Treffer eines Zeigers (ohne '*' höchstens einer). Hinter einem '*'
    werden Listen flach zusammengelegt."""
    if zeiger in ("", "/"):
        return [daten]
    if not zeiger.startswith("/"):
        raise ValueError(f"Zeiger muss mit / beginnen: {zeiger!r}")
    front, mit_stern = [daten], False
    for teil in zeiger[1:].split("/"):
        neu = []
        for cur in front:
            if teil == "*":
                mit_stern = True
                neu.extend(cur.values() if isinstance(cur, dict)
                           else cur if isinstance(cur, list) else [])
            else:
                r = _schritt(cur, teil)
                if r is not _NICHTS:
                    neu.append(r)
        front = neu
    if mit_stern:
        flach = []
        for r in front:
            flach.extend(r) if isinstance(r, list) else flach.append(r)
        return flach
    return front


def zeiger_eins(daten, zeiger: str, standard=None):
    treffer = zeiger_alle(daten, zeiger)
    return treffer[0] if treffer else standard


def text_nachsichtig(vorlage: str, ctx: dict) -> str:
    """Wie text(), aber was fehlt wird zu '' — für Zeilen, die die KI liest
    (ein Termin ohne Ort ist trotzdem eine Zeile)."""
    def ein(m):
        try:
            return _kodieren(_wert(ctx, m), "text")
        except Fehlt:
            return ""
    return PLATZHALTER.sub(ein, vorlage)
