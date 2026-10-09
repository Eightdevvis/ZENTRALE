# core/input_aufraeumen.py
#
# Damit Sashas Input/ nicht zur Halde wird: nach jedem Werkzeug, das eine
# Datei aus Input/ fertig verarbeitet hat (import_skill, unzip, read_pdf/
# read_docx/read_file, fetch_document), hängt eine feste Zeile am Ergebnis —
# „Frag Sasha jetzt, ob <datei> aus Input weg soll (remove_input)." — und im
# Gespräch steht eine offene Zusage „input_aufraeumen: <datei>"
# (core/zusagen.py). Die steht in jedem folgenden Zug im Kontext-Umschlag
# (ehrlichkeit.umschlag_block), bis
#   - remove_input für diese Datei lief (oder sie sonst weg ist), oder
#   - Sasha in einer Knopf-Frage nein sagte (am Gate von remove_input oder
#     in einem ask_choice, das die Datei nennt).
#
# 2026-10-09, Sasha: „ob sie das file aus dem ordner dann removed afterwards
# damit der ordner nich zur halde wird". Eine Bitte im Prompt vergisst die
# KI; die Zeile im Ergebnis plus die Zusage im Umschlag nicht.
#
# Nur für Einträge DIREKT in Input/ (remove_input räumt nur die) und nur
# nach einem Erfolg (ein Lesefehler ist kein „fertig").
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import re

import nutzer_ordner
import werkzeug_befund
import zug
import zusagen

ART = "input_aufraeumen: "
WERKZEUG = "remove_input"


def zeile(name: str) -> str:
    return f"Frag Sasha jetzt, ob {name} aus Input weg soll ({WERKZEUG})."


def eintrag(abs_pfad) -> str | None:
    """Der Name, wenn der Pfad (Verweise aufgelöst) DIREKT in Input/ liegt."""
    if not abs_pfad:
        return None
    echt = os.path.realpath(str(abs_pfad))
    ein = os.path.realpath(nutzer_ordner.unterordner(nutzer_ordner.INPUT))
    if os.path.dirname(echt) != ein or not os.path.lexists(echt):
        return None
    return os.path.basename(echt)


def _anhaengen(ergebnis, text: str):
    if isinstance(ergebnis, werkzeug_befund.Befund):
        return werkzeug_befund.Befund(f"{ergebnis}\n{text}", ergebnis.status,
                                      beleg=ergebnis.beleg, code=ergebnis.code,
                                      vollstaendig=ergebnis.vollstaendig)
    return f"{ergebnis}\n{text}"


def nach_verarbeitung(ergebnis, abs_pfad):
    """Das Ergebnis eines Werkzeugs, das `abs_pfad` fertig verarbeitet hat —
    mit der Aufräum-Zeile und der offenen Zusage, wenn die Datei direkt in
    Input/ liegt und das Werkzeug erfolgreich war. Sonst unverändert."""
    # Nur gross: remove_input gibt es nur dort (klein ist nicht gemessen).
    if werkzeug_befund.schiene() != "gross":
        return ergebnis
    name = eintrag(abs_pfad)
    if not name or werkzeug_befund.status_von(ergebnis) != werkzeug_befund.OK:
        return ergebnis
    gid = zug.gespraech()
    if gid:
        try:
            zusagen.merken(gid, ART + name, f"Sasha fragen, ob {name} aus Input weg soll "
                           f"({WERKZEUG})", zusagen.zug_nummer(gid))
        except Exception:
            pass            # die Zeile im Ergebnis bleibt; der Zug geht nie daran kaputt
    return _anhaengen(ergebnis, zeile(name))


def _offen(gid) -> list:
    try:
        return [z for z in zusagen.offen(gid) if str(z.get("art") or "").startswith(ART)]
    except Exception:
        return []


def erledigen(name: str, grund: str) -> None:
    """Die Zusage zu `name` im laufenden Gespräch abhaken."""
    gid = zug.gespraech()
    if not gid:
        return
    for z in _offen(gid):
        if z["art"] == ART + name:
            zusagen.erledigen(gid, z["id"], grund, zusagen.zug_nummer(gid))


def _gleich(datei, name: str) -> bool:
    roh = str(datei or "").strip().replace("\\", "/").strip("/")
    if roh.lower().startswith(nutzer_ordner.INPUT.lower() + "/"):
        roh = roh[len(nutzer_ordner.INPUT) + 1:]
    return os.path.basename(roh) == name


_GEWAEHLT = re.compile(r"Sasha hat gewählt: (.+?)\.?\s*$", re.S)
_NEIN = ("nein", "behalten", "nicht", "lassen", "drin lassen", "da lassen")


def _nein(text: str) -> bool:
    m = _GEWAEHLT.search(str(text or ""))
    if not m:
        return False
    wahl = m.group(1).strip().strip("„“\"'").casefold()
    return wahl.startswith(_NEIN) or "behalten" in wahl


def nachfuehren(gid, protokoll) -> None:
    """Nach einem Zug (ehrlichkeit.Pruefer): Zusagen abhaken, deren Datei
    weg ist oder zu der Sasha nein gesagt hat. protokoll: Schritte mit
    name, args, status, text."""
    if not gid:
        return
    ein = nutzer_ordner.unterordner(nutzer_ordner.INPUT)
    for z in _offen(gid):
        name = z["art"][len(ART):]
        grund = ""
        if not os.path.lexists(os.path.join(ein, name)):
            grund = "weg"
        for s in protokoll or ():
            if grund:
                break
            args = getattr(s, "args", None) or {}
            if s.name == WERKZEUG and s.status == werkzeug_befund.ABGELEHNT \
                    and _gleich(args.get("datei"), name):
                grund = "abgelehnt"
            elif s.name == "ask_choice" and s.status == werkzeug_befund.OK \
                    and name.casefold() in str(args.get("frage") or "").casefold() \
                    and _nein(s.text):
                grund = "abgelehnt"
        if grund:
            zusagen.erledigen(gid, z["id"], grund, zusagen.zug_nummer(gid))
