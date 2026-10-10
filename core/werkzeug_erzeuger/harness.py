# core/werkzeug_erzeuger/harness.py
#
# Die Schutzschicht um JEDES erzeugte Werkzeug — dieselbe für jede Quelle.
# Was bis 2026-10-10 in jedem Kalender-Werkzeug von Hand stand
# (core/ki_kalender_aendern.py), steht hier einmal:
#
#   1. Argumente gegen das Schema (Pflicht, enum, Typ, Datum, unbekannte
#      Felder) — Abbruch mit Code, BEVOR etwas geschrieben wird;
#   2. der Adapter führt aus (oder lehnt mit Code ab: Ablehnung);
#   3. nachlesen per Kennung: steht es so da, wie verlangt?
#   4. sonst zurücknehmen (ganz oder gar nicht): Neues löschen, Geändertes
#      auf den alten Stand;
#   5. der Satz in fester Form aus dem NACHGELESENEN Stand, mit Kennung:
#      „<was> EINGETRAGEN (#k)…" / „ABGEBROCHEN – nichts geändert. Fehler
#      <PRÄFIX>-<CODE>: …" (core/werkzeug_befund.py).
#
# Die Erlaubnis-Frage (Gate) baut frage() aus den Feldern des Schemas; der
# Adapter darf eine eigene, genauere liefern.

import re
from dataclasses import dataclass, field
from typing import Callable

from werkzeug_befund import abgebrochen, erledigt

from . import schema

VERB = {"anlegen": "EINGETRAGEN", "aendern": "GEÄNDERT", "loeschen": "GELÖSCHT"}
NICHTS = {"anlegen": "nichts eingetragen", "aendern": "nichts geändert",
          "loeschen": "nichts gelöscht", "lesen": "nichts gelesen"}


class Ablehnung(Exception):
    """Kontrollierter Abbruch mit Code — vom Adapter oder vom Schema. Ohne
    Vorsilbe („TITEL-LEER") setzt der Erzeuger die der Quelle davor."""

    def __init__(self, code: str, grund: str = ""):
        super().__init__(grund or code)
        self.code, self.grund = code, grund or code


@dataclass
class Ergebnis:
    """Was der Adapter nach dem Ausführen meldet. Alles, was der Satz an
    Werten nennt, kommt aus dem NACHGELESENEN Eintrag, nicht von hier.

    kennung   betroffener Eintrag (feste Kennung der Quelle)
    verlangt  Feld → Wert, der nachgelesen so dastehen muss
    pruefe    f(eintrag) -> [Abweichung]: was sich nicht als Gleichheit sagt
    vorher    Stand vor Ändern/Löschen (zum Zurücknehmen, Satz beim Löschen)
    art       überschreibt die Art der Aktion für DIESEN Aufruf
              (edit_calendar_routine mit aktion=loeschen)
    verb      statt EINGETRAGEN/GEÄNDERT/GELÖSCHT (z. B. ABGESAGT)
    subjekt   f(eintrag) -> Satzanfang, statt adapter.beschreiben
    nachsatz  hinter Verb und Kennung (Text oder f(eintrag))
    zusatz    Hinweise hinter dem Satz, kein Beleg (Text oder f(eintrag))
    text      nur bei lesen: das fertige Ergebnis"""
    kennung: str | None = None
    verlangt: dict = field(default_factory=dict)
    pruefe: Callable[[dict], list] | None = None
    vorher: dict | None = None
    art: str | None = None
    verb: str | None = None
    subjekt: Callable[[dict], str] | None = None
    nachsatz: str | Callable[[dict], str] = ""
    zusatz: str | Callable[[dict], str] = ""
    text: str | None = None


_MIT_VORSILBE = re.compile(r"^[A-Z]-")


def code(quelle, endung: str) -> str:
    return endung if _MIT_VORSILBE.match(endung) else f"{quelle.praefix}-{endung}"


def _wert(x, eintrag):
    return x(eintrag) if callable(x) else (x or "")


def passt(eintrag: dict, verlangt: dict) -> list:
    """Felder, die nachgelesen anders dastehen als verlangt."""
    return [f"{k} verlangt {v!r}, steht {eintrag.get(k)!r}"
            for k, v in verlangt.items() if (eintrag.get(k) or "") != (v or "")]


def ausfuehren(quelle, aktion: dict, args: dict):
    """Der Ausführer eines erzeugten Werkzeugs (Kopf dieser Datei)."""
    adapter, name = quelle.adapter, aktion["name"]
    art = schema.art(aktion)
    was_fn = getattr(adapter, "was", None)
    was = (was_fn(name, args or {}) if was_fn else None) or f"Aktion {name}"

    def ablehnen(endung, grund):
        raise Ablehnung(endung, grund)

    try:
        sauber = schema.args_pruefen(aktion, args or {}, ablehnen)
        erg = adapter.ausfuehren(name, sauber)
        if art == "lesen":
            return erg.text if isinstance(erg, Ergebnis) else erg
        art = erg.art or art
        return _belegen(quelle, art, erg)
    except Ablehnung as e:
        nichts = (aktion.get(schema.X) or {}).get("nichts") or NICHTS[art]
        return abgebrochen(was, code(quelle, e.code), e.grund, nichts)
    except _NichtZurueck as e:
        return abgebrochen(was, code(quelle, "W-NICHT-GESPEICHERT"), e.grund,
                           "ob etwas geändert ist, ist NICHT belegt — nachlesen")


class _NichtZurueck(Exception):
    def __init__(self, grund):
        super().__init__(grund)
        self.grund = grund


def _belegen(quelle, art: str, erg: Ergebnis):
    """Nachlesen, prüfen, ggf. zurücknehmen, Satz bauen."""
    adapter = quelle.adapter
    jetzt = adapter.nachlesen(erg.kennung) if erg.kennung else None
    if art == "loeschen":
        if jetzt is not None:
            raise Ablehnung("W-NICHT-GESPEICHERT", "nachgelesen steht es noch da")
        eintrag = erg.vorher or {}
    else:
        if jetzt is None:
            raise Ablehnung("W-NICHT-GESPEICHERT", "nachgelesen steht es nicht da")
        falsch = passt(jetzt, erg.verlangt) + (erg.pruefe(jetzt) if erg.pruefe else [])
        if falsch:
            _zuruecknehmen(adapter, art, erg, "; ".join(falsch))
        eintrag = jetzt
    subjekt = erg.subjekt(eintrag) if erg.subjekt else adapter.beschreiben(eintrag)
    kenn = ""
    if art != "loeschen" and erg.kennung:
        kurz = getattr(adapter, "kurz", None)
        kenn = f" (#{kurz(erg.kennung) if kurz else erg.kennung})"
    satz = f"{subjekt} {erg.verb or VERB[art]}{kenn}{_wert(erg.nachsatz, eintrag)}"
    if not satz.endswith((".", "!", "?")):
        satz += "."
    return erledigt(satz, satz, zusatz=_wert(erg.zusatz, eintrag))


def _zuruecknehmen(adapter, art: str, erg: Ergebnis, falsch: str):
    """Ganz oder gar nicht: Neues weg, Geändertes zurück — dann Abbruch."""
    try:
        if art == "anlegen":
            adapter.loeschen(erg.kennung)
            wie = "wieder gelöscht"
        else:
            adapter.wiederherstellen(erg.kennung, erg.vorher)
            wie = "der alte Stand ist wiederhergestellt"
    except Exception as e:      # noqa: BLE001 — jeder Fehler hier heißt: nicht belegt
        raise _NichtZurueck(f"nachgelesen stand es anders da ({falsch}); zurücknehmen "
                            f"ging nicht: {e}")
    raise Ablehnung("W-NICHT-GESPEICHERT", f"nachgelesen stand es anders da ({falsch}); {wie}")


# ── Die Ja/Nein-Frage an Sasha ─────────────────────────────────────────

def frage(quelle, aktion: dict, args: dict) -> str:
    """Aus den Feldern gebaut: „Soll ich <frage> <Ziel>: <Wort> <Wert>, …?"
    Der Adapter darf eine eigene liefern (frage(name, args) -> str|None)."""
    adapter = quelle.adapter
    eigene = getattr(adapter, "frage", None)
    text = eigene(aktion["name"], args or {}) if eigene else None
    if text:
        return text
    x = aktion.get(schema.X) or {}
    ziel, teile = "", []
    for name, f in schema.felder(aktion).items():
        wert = (args or {}).get(name)
        if wert is None or (isinstance(wert, str) and not wert.strip()):
            continue
        fx = f.get(schema.X) or {}
        if fx.get("ziel"):
            zt = getattr(adapter, "ziel", None)
            ziel = " " + (zt(str(wert)) if zt else f"#{str(wert).lstrip('#')}")
            continue
        teile.append(f"{fx.get('wort') or name} {wert}")
    satz = x.get("frage") or f"„{aktion['name']}“ ausführen"
    return f"Soll ich {satz}{ziel}" + (": " + ", ".join(teile) if teile else "") + "?"
