# core/ki_dateien.py
#
# Was die Datei-Werkzeuge auf gross TUN — alles in der Ablage: find_files,
# search_files, import_skill, unzip, dazu list_files und read_file auf gross
# (ki_werkzeuge ruft liste()/lesen(); deren Ausführer teilt es mit klein).
# Einträge und Fragen: core/werkzeug_dateien.py; das Handwerk:
# core/ablage_suche.py, core/ablage_zip.py, core/skill_import.py.
#
# 2026-10-11 (Sasha: „ja einfach nur die ablage dann"): vorher arbeiteten sie
# in ~/Zentrale/Input und Output (core/ki_nutzer_ordner.py, 2026-10-09).
# Suchen geben weiter einen Befund mit `vollstaendig` zurück — der Prüfer
# „nicht da" (core/ehrlichkeit.py) liest die Kopfzeile „Suche vollständig:
# N Treffer". Schreibendes kennt nur ERLEDIGT (nachgelesen) oder ABGEBROCHEN
# mit Code.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Meldet sich per
# @ausfuehrer an; ki_werkzeuge importiert dieses Modul.

import os
import shutil

import ablage
import ablage_suche
import ablage_text
import ablage_zip
import skill_import
import werkzeug_dateien
import werkzeug_register
import zug
from werkzeug_befund import Befund, OK, erledigt, abgebrochen

ausfuehrer = werkzeug_register.ausfuehrer


def befund(e: ablage_suche.Ergebnis):
    """Ergebnis einer Suche → was die KI bekommt. Ein Fehler (kein Muster)
    bleibt ein „[Fehler …]"-Text wie bei den anderen lesenden Werkzeugen."""
    if e.fehler:
        return e.text
    return Befund(e.text, vollstaendig=e.vollstaendig)


def _zahl(n: int, eins: str, viele: str) -> str:
    return f"{n} {eins if n == 1 else viele}"


# ── Suchen, auflisten, lesen ───────────────────────────────────────────

@ausfuehrer("find_files")
def _find_files(args: dict):
    return befund(ablage_suche.finden(str(args.get("muster") or ""),
                                      werkzeug_dateien.papierkorb(args)))


@ausfuehrer("search_files")
def _search_files(args: dict):
    return befund(ablage_suche.textsuche(str(args.get("text") or ""),
                                         str(args.get("muster") or ""),
                                         werkzeug_dateien.papierkorb(args)))


def liste(args: dict):
    """list_files auf gross: die Ablage wie ls."""
    return befund(ablage_suche.auflisten(werkzeug_dateien.papierkorb(args)))


LESEN_ZEICHEN = 30_000


def lesen(angabe) -> str:
    """read_file auf gross: ein Dokument per id oder genauem Titel. Ein
    Titel, den es mehrfach gibt, wird nicht geraten (Liste der ids)."""
    q = str(angabe or "").strip()
    if not q:
        return "[Fehler: keine Ablage-id oder Titel angegeben]"
    if ablage.gibt_es(q):
        k = ablage.kopf(q)
    else:
        name = q.casefold()
        treffer = [k for k in ablage.liste() + ablage.liste(archivierte=True)
                   if str(k.get("titel") or "").casefold() in
                   (name, name.rsplit(".", 1)[0] if "." in name else name)]
        if not treffer:
            return (f"[Nicht in der Ablage: „{q}“ ist weder eine id noch ein genauer Titel — "
                    f"mit find_files suchen]")
        if len(treffer) > 1:
            return (f"[Mehrere Dokumente heißen „{q}“ — mit der id lesen:\n"
                    + "\n".join(ablage_suche.zeile(k) for k in treffer) + "]")
        k = treffer[0]
    kopf = f"„{k.get('titel')}“ (id {k['id']}, {k.get('art')}, Fassung {k.get('fassung')})"
    if k.get("art") in ablage.DATEIEN:
        erg = ablage_text.text(k["id"])
        if erg.get("fehler"):
            return f"[Lesefehler: {kopf}: {erg['fehler']}]"
        text = ablage_text.kopfzeile(erg, k["id"]) + "\n" + (erg.get("text") or "(kein Text)")
    elif k.get("art") == "bild":
        return f"{kopf}: ein Bild — lesen geht nur bei Text."
    else:
        text = ablage.lesen(k["id"])["inhalt"] or ""
    if len(text) > LESEN_ZEICHEN:
        text = text[:LESEN_ZEICHEN] + (f"\n[… gekürzt: {LESEN_ZEICHEN} von {len(text)} Zeichen "
                                       f"— PDF/Word/Excel stückweise mit read_pdf/read_docx/"
                                       f"read_xlsx]")
    return f"{kopf}:\n{text}"


# ── import_skill ───────────────────────────────────────────────────────

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
    q = str(args.get("id") or "").strip()
    titel = q
    try:
        titel = ablage.kopf(q).get("titel") or q if ablage.gibt_es(q) else q
    except ablage.Unbekannt:
        pass
    was = f"Skill aus „{titel or '?'}“ übernehmen"
    try:
        e = skill_import.uebernehmen(q)
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


# ── unzip ──────────────────────────────────────────────────────────────

def _unzip_ansehen(q: str):
    try:
        z = ablage_zip.ansehen(q)
    except ablage_zip.Fehler as f:
        return abgebrochen(f"Zip „{q}“ ansehen", f.code, f.grund, "nichts gelesen")
    zeilen = [f"Inhalt von „{z['titel']}“: {_zahl(len(z['dateien']), 'Datei', 'Dateien')}, "
              f"{ablage_zip.groesse(z['bytes'])} entpackt (nichts ausgepackt)."]
    zeilen += [f"  {p}  ({ablage_zip.groesse(n)})" for p, n in z["dateien"][:ablage_zip.LISTE_MAX]]
    if len(z["dateien"]) > ablage_zip.LISTE_MAX:
        zeilen.append(f"  … {len(z['dateien']) - ablage_zip.LISTE_MAX} weitere")
    if z["ausgelassen"]:
        zeilen.append("Beim Auspacken ausgelassen (versteckt, Ballast oder nach Schlüssel "
                      "aussehend): " + ", ".join(z["ausgelassen"][:20])
                      + (" …" if len(z["ausgelassen"]) > 20 else "") + ".")
    if z["zu_viel"]:
        zeilen.append(f"Auspacken geht nicht: zu viel ({z['zu_viel']}).")
    else:
        zeilen.append("Auspacken (unzip ohne ansehen) legt jede Datei als Dokument in die Ablage.")
    return Befund("\n".join(zeilen), OK)


def nachgezaehlt(angelegt: list) -> list:
    """Der Beleg: welche der neuen Dokumente die Ablage wirklich hat."""
    return [k for k in angelegt if ablage.gibt_es(k["id"]) and ablage.roh(k["id"])]


@ausfuehrer("unzip")
def _unzip(args: dict):
    q = str(args.get("id") or "").strip()
    if werkzeug_dateien.ansehen(args):
        return _unzip_ansehen(q)
    was = f"„{q or '?'}“ auspacken"
    try:
        e = ablage_zip.auspacken(q, gespraech=zug.gespraech())
    except ablage_zip.Fehler as f:
        return abgebrochen(was, f.code, f.grund, "nichts ausgepackt")
    da = nachgezaehlt(e["angelegt"])
    if len(da) != len(e["angelegt"]):
        for k in e["angelegt"]:
            shutil.rmtree(os.path.join(ablage.ordner(), k["id"]), ignore_errors=True)
        return abgebrochen(was, "W-NICHT-GESPEICHERT", f"nachgezählt {len(da)} statt "
                           f"{len(e['angelegt'])} Dokumente; wieder entfernt", "nichts ausgepackt")
    for k in da:
        zug.melden({"ablage": ablage.kurz(k)})
    n = len(da)
    satz = (f"„{e['titel']}“ AUSGEPACKT: {_zahl(n, 'Dokument', 'Dokumente')} in der Ablage — "
            + "; ".join(f"„{k['titel']}“ (id {k['id']})" for k in da[:8])
            + (f"; … {n - 8} weitere" if n > 8 else "") + ".")
    zusatz = []
    if e["ohne_art"]:
        zusatz.append("Nicht übernommen (keine Art, die die Ablage kennt): "
                      + ", ".join(e["ohne_art"][:20]) + ".")
    if e["ausgelassen"]:
        zusatz.append("Ausgelassen (versteckt, Ballast oder nach Schlüssel aussehend): "
                      + ", ".join(e["ausgelassen"][:20]) + ".")
    beleg = f"nachgezählt: {_zahl(n, 'neues Dokument', 'neue Dokumente')} in der Ablage."
    return erledigt(satz, beleg, zusatz=" ".join(zusatz))
