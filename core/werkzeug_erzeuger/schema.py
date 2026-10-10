# core/werkzeug_erzeuger/schema.py
#
# Das Aktions-Schema einer Quelle lesen: prüfen, ob es vollständig ist, die
# Fassung fürs Modell bauen (ohne unsere Erweiterungen), die Argumente eines
# Aufrufs dagegen prüfen, bevor irgendetwas geschrieben wird.
#
# Form einer Aktion (2026-10-10): eine MCP-Werkzeug-Definition — `name`,
# `description`, `inputSchema` (JSON Schema 2020-12), `annotations`
# (readOnlyHint, destructiveHint) — plus der Erweiterung `x-zentrale`
# (wie die x-…-Erweiterungen in OpenAPI). Standard statt Eigenformat
# (memory/system/hub_bauplan.md): ein fremder MCP-Server liefert genau diese
# Form, nur ohne x-zentrale.
#
#   x-zentrale (Aktion)   art: lesen|anlegen|aendern|loeschen, alltag, worte,
#                         frage (Satzanfang der Ja/Nein-Frage), immer_erlaubbar,
#                         beweis, einfach (Beschreibung für schwache Modelle),
#                         nichts (Wortlaut im Abbruch, Standard je Art)
#   x-zentrale (Feld)     wort (wie Sasha das Feld liest), fehlt / ungueltig
#                         (Code-Endung statt PFLICHTFELD / WERT-UNGUELTIG),
#                         ziel (Wert ist eine Kennung → in der Frage
#                         aufgelöst), schwach: false (Profil „schwach" sieht
#                         das Feld nicht; nur für freiwillige Felder)

import copy
from datetime import date

ARTEN = ("lesen", "anlegen", "aendern", "loeschen")
X = "x-zentrale"


class SchemaFehler(ValueError):
    """Das Aktions-Schema selbst ist kaputt — ein Fehler der Quelle, nicht der
    KI. Fällt beim Erzeugen (Prozess-Start, Tests) auf, nie im Gespräch."""


def art(aktion: dict) -> str:
    """lesen|anlegen|aendern|loeschen. Ohne x-zentrale.art aus den
    MCP-Hinweisen: readOnlyHint → lesen, destructiveHint → loeschen."""
    a = (aktion.get(X) or {}).get("art")
    if a:
        return a
    hinweis = aktion.get("annotations") or {}
    if hinweis.get("readOnlyHint"):
        return "lesen"
    if hinweis.get("destructiveHint"):
        return "loeschen"
    return "aendern"


def felder(aktion: dict) -> dict:
    return (aktion.get("inputSchema") or {}).get("properties") or {}


def pflicht(aktion: dict) -> list:
    return list((aktion.get("inputSchema") or {}).get("required") or [])


def feld_x(aktion: dict, name: str) -> dict:
    return (felder(aktion).get(name) or {}).get(X) or {}


def pruefen(aktion: dict) -> None:
    """Ist die Aktion vollständig beschrieben? Wirft SchemaFehler."""
    name = aktion.get("name")
    if not isinstance(name, str) or not name:
        raise SchemaFehler(f"Aktion ohne Namen: {aktion!r}")
    if not str(aktion.get("description") or "").strip():
        raise SchemaFehler(f"{name}: description fehlt")
    s = aktion.get("inputSchema")
    if not isinstance(s, dict) or s.get("type") != "object":
        raise SchemaFehler(f"{name}: inputSchema muss ein JSON-Schema-Objekt sein")
    if art(aktion) not in ARTEN:
        raise SchemaFehler(f"{name}: art {art(aktion)!r} gibt es nicht ({', '.join(ARTEN)})")
    for p in pflicht(aktion):
        if p not in felder(aktion):
            raise SchemaFehler(f"{name}: Pflichtfeld {p!r} steht nicht in properties")
        if feld_x(aktion, p).get("schwach") is False:
            # Ein ausgeblendetes Pflichtfeld könnte das schwache Modell nie
            # füllen — jeder Aufruf bräche ab.
            raise SchemaFehler(f"{name}: Pflichtfeld {p!r} darf nicht ausgeblendet werden")


def _ohne_x(wert):
    if isinstance(wert, dict):
        return {k: _ohne_x(v) for k, v in wert.items() if k != X}
    if isinstance(wert, list):
        return [_ohne_x(v) for v in wert]
    return wert


def fuer_modell(aktion: dict) -> dict:
    """Das Parameter-Schema, wie es ans Modell geht: reines JSON Schema,
    ohne x-zentrale (das Modell braucht unsere Verwaltung nicht zu lesen)."""
    s = _ohne_x(copy.deepcopy(aktion["inputSchema"]))
    s.setdefault("required", [])
    return s


# ── Argumente prüfen (vor dem Schreiben) ───────────────────────────────

_TYPEN = {"string": str, "boolean": bool, "array": list, "object": dict}


def _leer(wert) -> bool:
    return wert is None or (isinstance(wert, str) and not wert.strip())


def _typ_passt(wert, typ) -> bool:
    if typ == "integer":
        return isinstance(wert, int) and not isinstance(wert, bool)
    if typ == "number":
        return isinstance(wert, (int, float)) and not isinstance(wert, bool)
    py = _TYPEN.get(typ)
    return py is None or isinstance(wert, py)


def args_pruefen(aktion: dict, args: dict, ablehnen) -> dict:
    """Die Argumente gegen das Schema: unbekannte Felder, Pflicht, Typ, enum,
    format: date. `ablehnen(code_endung, grund)` wirft (der Erzeuger setzt
    die Vorsilbe der Quelle davor). -> die Argumente ohne leere Werte.

    Leer ("", nur Leerzeichen, None) zählt als „nicht angegeben": die
    Modelle schicken oft "" für Felder, die sie nicht meinen."""
    if not isinstance(args, dict):
        ablehnen("WERT-UNGUELTIG", "die Argumente sind kein Objekt")
    bekannt = felder(aktion)
    fremd = sorted(set(args) - set(bekannt))
    if fremd:
        ablehnen("UNBEKANNTES-FELD", f"{', '.join(fremd)} gibt es hier nicht; erlaubt: "
                 + ", ".join(bekannt))
    for p in pflicht(aktion):
        if _leer(args.get(p)):
            ablehnen(feld_x(aktion, p).get("fehlt") or "PFLICHTFELD", f"{p} fehlt")
    sauber = {}
    for name, wert in args.items():
        if _leer(wert):
            continue
        f = bekannt[name]
        code = feld_x(aktion, name).get("ungueltig") or "WERT-UNGUELTIG"
        if f.get("type") and not _typ_passt(wert, f["type"]):
            ablehnen(code, f"{name} muss {f['type']} sein, nicht {type(wert).__name__}")
        if "enum" in f and wert not in f["enum"]:
            normal = wert.strip().lower() if isinstance(wert, str) else wert
            if normal not in f["enum"]:
                ablehnen(code, f"{name} {wert!r} gibt es nicht; erlaubt: "
                         + ", ".join(map(str, f["enum"])))
            wert = normal
        if f.get("format") == "date":
            try:
                date.fromisoformat(str(wert).strip())
            except ValueError:
                ablehnen(feld_x(aktion, name).get("ungueltig") or "DATUM-UNGUELTIG",
                         f"{name} {wert!r} ist kein Datum (YYYY-MM-DD)")
        sauber[name] = wert.strip() if isinstance(wert, str) else wert
    return sauber


# ── Zuschnitt je Modellprofil ──────────────────────────────────────────

def zuschnitt(aktion: dict) -> dict | None:
    """{"schwach": {"weg": [...], "beschreibung": ...}} oder None."""
    weg = [n for n in felder(aktion) if feld_x(aktion, n).get("schwach") is False]
    einfach = (aktion.get(X) or {}).get("einfach")
    if not weg and not einfach:
        return None
    raus = {"weg": weg}
    if einfach:
        raus["beschreibung"] = einfach
    return {"schwach": raus}
