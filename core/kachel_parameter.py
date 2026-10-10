# core/kachel_parameter.py
#
# Was man beim Anlegen einer Kachel angeben kann — als JSON Schema (Entwurf
# 2020-12, derselbe Dialekt wie OpenAPI 3.1). Sasha 2026-10-10: keine
# eigenen Daten- oder Schnittstellen-Formate, immer verbreitete Standards.
# Bis 2026-10-10 stand hier eine selbst erfundene `felder`-Liste (typ
# datum|zahl|wahl|…, vorgabe, grenzen, wenn, dynamisch); sie ist ganz weg.
#
# Jeder Katalog-Eintrag (`GET /api/kacheln`, memory/system/hub_bauplan.md
# „Katalog") trägt `parameter` = ein Schema `type: object`. Jede Oberfläche
# baut daraus ihren Dialog SELBST (TUI: tui/bausteine/feld_dialog.py, nur
# die Teilmenge unten), der Hub prüft hier, bevor eine Quelle gefragt wird.
#
# Benutzte Teilmenge (alles Standard-Schlüsselwörter):
#   properties   je Name: type string|integer|number|boolean, title (Name
#                vor dem Feld), description (Hilfe), default, minimum/
#                maximum, minLength/maxLength, format: date, Auswahl als
#                oneOf [{const, title}] (oder enum ohne eigene Titel)
#   required     was gesetzt sein muss
#   allOf [{if: {properties: {x: {const: w}}}, then: {required, properties:
#                {y: false}}}]  — Felder, die nur bei einem Wert gelten
#   additionalProperties: false — unbekannte Namen sind ein Fehler
# Reihenfolge der Felder = Reihenfolge in `properties` (der Hub liefert den
# Katalog unsortiert).
#
# Was JSON Schema NICHT ausdrücken kann (Abstand zweier Daten ≤ 31 Tage,
# „bis" nicht vor „von"), prüft die Quelle selbst in `pruefen(art, ref)`;
# der Hub ruft das gleich nach dem Schema und antwortet mit 400 und ihrem
# Text — eine Oberfläche zeigt ihn nur.
#
# Prüfer: das Paket `jsonschema` (requirements.txt, nur das Backend). Fehlt
# es, gibt es OhnePruefer — der Hub sagt dann „aus", statt ungeprüft eine
# Quelle zu fragen.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).

import copy
import re

from kachel_form import KachelFehler

ENTWURF = "https://json-schema.org/draft/2020-12/schema"
LEER = {"$schema": ENTWURF, "type": "object", "properties": {}}


class OhnePruefer(RuntimeError):
    """Das Paket jsonschema fehlt auf diesem Rechner."""


def _validator():
    try:
        from jsonschema import Draft202012Validator
    except ImportError as e:
        raise OhnePruefer("jsonschema fehlt (pip install -r requirements.txt)") from e
    return Draft202012Validator


def schema_pruefen(schema):
    """Ein Schema taugt (gegen das Meta-Schema 2020-12) → schema, sonst
    ValueError. Für den Katalog und Tests."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("parameter muss ein schema mit type: object sein")
    v = _validator()
    try:
        v.check_schema(schema)
    except Exception as e:                       # jsonschema.SchemaError
        raise ValueError("parameter ist kein gültiges schema: %s" % getattr(e, "message", e))
    return schema


# ── Für den Katalog: Werte von jetzt eintragen ────────────────────────

def mit_auswahl(schema, name, wahl):
    """Kopie, in der `name` zur Wahl aus [(wert, titel)] wird (oneOf mit
    const + title) — für Werte, die erst beim Fragen feststehen (welche
    Liste, welcher Graph). Das Schema der Quelle bleibt unverändert."""
    s = copy.deepcopy(schema)
    s["properties"][name]["oneOf"] = [{"const": str(w), "title": str(t)} for w, t in wahl]
    return s


def mit_vorgaben(schema, vorgaben):
    """Kopie mit `default` je Name (z. B. das Datum von heute)."""
    s = copy.deepcopy(schema)
    for name, wert in vorgaben.items():
        s["properties"][name]["default"] = wert
    return s


# ── Aus der Adresse: Text → Typ ───────────────────────────────────────

def _typ(prop):
    t = prop.get("type") if isinstance(prop, dict) else None
    return t if isinstance(t, str) else None


def aus_abfrage(schema, roh):
    """Abfrage einer Adresse (Werte als Text) → getypte Werte, nach dem
    `type` des Schemas — wie OpenAPI Query-Parameter liest. Schon getypte
    Werte bleiben; ein leerer Text bei Zahl/Wahrheit/Datum zählt als nicht
    gesetzt (dann sagt `required`, was fehlt). Was nicht passt, bleibt Text
    und fällt beim Prüfen auf."""
    props = schema.get("properties") or {}
    raus = {}
    for name, wert in roh.items():
        p = props.get(name)
        typ = _typ(p)
        if isinstance(wert, str):
            s = wert.strip()
            if s == "" and (typ in ("integer", "number", "boolean")
                            or (isinstance(p, dict) and p.get("format") == "date")):
                continue
            if typ == "integer" and re.fullmatch(r"-?[0-9]{1,9}", s):
                wert = int(s)
            elif typ == "number" and re.fullmatch(r"-?[0-9]{1,9}(\.[0-9]{1,9})?", s):
                wert = float(s) if "." in s else int(s)
            elif typ == "boolean" and s in ("true", "false"):
                wert = s == "true"
        raus[name] = wert
    return raus


# ── Prüfen ────────────────────────────────────────────────────────────

def _titel(schema, name):
    p = (schema.get("properties") or {}).get(name)
    return str((p or {}).get("title") or name) if isinstance(p, dict) else str(name)


def _teil(schema, pfad):
    """Das Stück Schema an einem schema_path."""
    for schritt in pfad:
        schema = schema[schritt]
    return schema


TYP_TEXT = {"integer": "eine ganze zahl", "number": "eine zahl",
            "boolean": "ja oder nein", "string": "ein text"}
RANG = {"additionalProperties": 0, "required": 1, None: 4}


def _text(schema, werte, e):
    """Ein Fehler des Prüfers → ein Satz in Alltagswörtern."""
    name = e.path[0] if e.path else None
    titel = _titel(schema, name) if name is not None else ""
    v, wert = e.validator, e.validator_value
    if v == "additionalProperties":
        fremd = sorted(set(werte) - set(schema.get("properties") or {}))
        return "unbekannt: %s" % ", ".join(fremd)
    if v == "required":
        fehlt = [n for n in wert if n not in werte]
        return "%s fehlt" % _titel(schema, fehlt[0] if fehlt else wert[0])
    if v is None:                                   # properties: {x: false}
        props = _teil(schema, list(e.schema_path))
        verboten = sorted(n for n, s in props.items() if s is False and n in werte)
        return "gilt hier nicht: %s" % ", ".join(verboten)
    if v == "type":
        return "%s: %s" % (titel, TYP_TEXT.get(wert, wert))
    if v == "format" and wert == "date":
        return "%s: datum als JJJJ-MM-TT" % titel
    if v in ("oneOf", "enum", "const"):
        p = (schema.get("properties") or {}).get(name) or {}
        erlaubt = [str(w.get("const")) for w in p.get("oneOf") or []] or list(map(str, p.get("enum") or []))
        return "%s: eins von %s" % (titel, ", ".join(erlaubt)) if erlaubt else "%s: gibt es nicht" % titel
    if v == "maximum":
        return "höchstens %s %s" % (wert, titel)
    if v == "minimum":
        return "%s: mindestens %s" % (titel, wert)
    if v == "minLength":
        return "%s fehlt" % titel if wert == 1 else "%s: mindestens %d zeichen" % (titel, wert)
    if v == "maxLength":
        return "%s: höchstens %d zeichen" % (titel, wert)
    return "%s: %s" % (titel, e.message) if titel else e.message


def pruefen(schema, roh):
    """{name: wert} (aus der Adresse oder schon getypt) gegen das Schema →
    getypte Werte, sonst KachelFehler mit EINEM Satz (der wichtigste
    zuerst: Unbekanntes, Fehlendes, falscher Typ, Grenzen, gilt hier nicht)."""
    if not isinstance(roh, dict):
        raise KachelFehler("bezug fehlt")
    schema = schema or LEER
    werte = aus_abfrage(schema, roh)
    v = _validator()
    fehler = list(v(schema, format_checker=v.FORMAT_CHECKER).iter_errors(werte))
    if fehler:
        reihe = list(schema.get("properties") or {})

        def wichtig(e):
            n = e.path[0] if e.path else None
            return (RANG.get(e.validator, 2 if e.validator in ("type", "format") else 3),
                    reihe.index(n) if n in reihe else -1)
        raise KachelFehler(_text(schema, werte, min(fehler, key=wichtig)))
    return werte
