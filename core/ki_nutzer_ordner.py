# core/ki_nutzer_ordner.py
#
# Was find_files, search_files und import_skill TUN (list_files auf gross:
# ki_werkzeuge, der Ausführer ist mit klein geteilt). Einträge und Frage:
# core/werkzeug_nutzer_ordner.py; das Handwerk: core/nutzer_suche.py und
# core/skill_import.py. Alles nur im Nutzerordner (Input/, Output/,
# core/nutzer_ordner.py).
#
# 2026-10-09 (Gespräch 20261009-155510, „Chefkoch ai-v1.zip"). Suchen geben
# einen Befund mit `vollstaendig` zurück — der Prüfer „nicht da"
# (core/ehrlichkeit.py) liest die Kopfzeile „Suche vollständig: N Treffer".
# import_skill kennt nur zwei Ausgänge (core/fehlercodes.py): ÜBERNOMMEN —
# nachgelesen aus der Skill-Liste — oder ABGEBROCHEN mit Code.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Meldet sich per
# @ausfuehrer an; ki_werkzeuge importiert dieses Modul.

import os

import nutzer_suche
import skill_import
import werkzeug_register
from werkzeug_befund import Befund, erledigt, abgebrochen

ausfuehrer = werkzeug_register.ausfuehrer


def befund(e: nutzer_suche.Ergebnis):
    """Ergebnis einer Suche → was die KI bekommt. Ein Fehler (kein Muster,
    Ordner draußen) bleibt ein „[Fehler …]"-Text wie bei den anderen
    lesenden Werkzeugen."""
    if e.fehler:
        return e.text
    return Befund(e.text, vollstaendig=e.vollstaendig)


@ausfuehrer("find_files")
def _find_files(args: dict):
    return befund(nutzer_suche.finden(str(args.get("muster") or ""),
                                      str(args.get("ordner") or "")))


@ausfuehrer("search_files")
def _search_files(args: dict):
    return befund(nutzer_suche.textsuche(str(args.get("text") or ""),
                                         str(args.get("ordner") or ""),
                                         str(args.get("muster") or "")))


def _zahl(n: int, eins: str, viele: str) -> str:
    return f"{n} {eins if n == 1 else viele}"


def _inhalt(z: dict) -> str:
    teile = ["SKILL.md"]
    if z["referenzen"]:
        teile.append(_zahl(z["referenzen"], "Referenz", "Referenzen"))
    if z["skripte"]:
        teile.append(_zahl(z["skripte"], "Skript", "Skripte"))
    if z["weitere"]:
        teile.append(_zahl(z["weitere"], "weitere Datei", "weitere Dateien"))
    return " + ".join(teile)


@ausfuehrer("import_skill")
def _import_skill(args: dict):
    pfad = str(args.get("pfad") or "").strip()
    was = f"Skill aus „{os.path.basename(pfad.rstrip('/')) or '?'}“ übernehmen"
    try:
        e = skill_import.uebernehmen(pfad)
    except skill_import.Fehler as f:
        return abgebrochen(was, f.code, f.grund, "nichts übernommen")
    namen = e["namen"]
    if len(namen) == 1:
        satz = f"Skill „{namen[0]}“ ÜBERNOMMEN (aktiv): {_inhalt(e['inhalt'][namen[0]])}."
    else:
        satz = ("Skills ÜBERNOMMEN (aktiv): "
                + "; ".join(f"„{n}“: {_inhalt(e['inhalt'][n])}" for n in namen) + ".")
    beleg = f"steht aktiv in der Skill-Liste: {', '.join(namen)} (Quelle {e['quelle']})."
    zusatz = [f"Quelle: {e['quelle']}.",
              "In der Skill-Liste ab Sashas nächster Nachricht; jetzt schon mit load_skill lesbar."]
    mit_skripten = [n for n in namen if e["inhalt"][n]["skripte"]]
    if mit_skripten:
        zusatz.append("Skripte laufen nur in der Sandbox: run_code mit skill="
                      + " bzw. ".join(f"„{n}“" for n in mit_skripten) + ".")
    if e["ausgelassen"]:
        zusatz.append(f"{_zahl(e['ausgelassen'], 'Datei', 'Dateien')} ausgelassen "
                      f"(versteckt, Ballast oder nach Schlüssel aussehend).")
    return erledigt(satz, beleg, zusatz=" ".join(zusatz))
