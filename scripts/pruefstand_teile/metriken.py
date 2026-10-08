# Metriken eines Laufs — deterministisch aus dem Mitschnitt.
#
# Die Liste folgt Anthropic („Writing effective tools for agents",
# Evaluierung): Werkzeug-Aufrufe, Werkzeug-Fehler, Laufzeit, Kosten — dazu,
# was Sashas Gespräch vom 08.10. gezeigt hat: Löschen+Neuanlegen statt
# Ändern (verlor Ende und Ort), und eine Frage ohne Antwort, nach der sie
# trotzdem handelte.
#
# Welche Werkzeuge schreiben, steht hier nach Namensmuster, nicht aus dem
# Register: der Prüfstand soll auch einen anderen Stand (--vergleich) mit
# neuen Werkzeug-Namen messen können, ohne dass hier etwas nachgezogen wird.

import json
import re

SCHREIBEND = ("add_", "edit_", "delete_", "update_", "write_", "rewrite_",
              "create_", "log_", "move_", "set_", "remove_")
FRAGE_WERKZEUG = "ask_choice"

# Ein Werkzeug-Ergebnis, das einen Fehler meldet (die Werkzeuge werfen
# meist nicht, sondern antworten mit „[Fehler: …]").
_FEHLER = re.compile(r"^\s*\[(fehler|unbekanntes tool)|fehlgeschlagen|"
                     r"^\s*\[eingetragen gemeldet, aber", re.IGNORECASE)
# Ein Aufruf, der nichts getroffen hat („Kein Termin … gefunden").
_INS_LEERE = re.compile(r"^\s*kein(e)?\b.*(gefunden|geändert|gelöscht)", re.IGNORECASE)
_KEINE_WAHL = {None, "", "None", "(keine Antwort)"}


def schreibt(name: str) -> bool:
    return str(name or "").startswith(SCHREIBEND)


def loescht(w: dict) -> bool:
    a = str((w.get("args") or {}).get("aktion", "")).casefold()
    return str(w.get("name", "")).startswith(("delete_", "remove_")) or a in ("loeschen", "löschen")


def legt_an(w: dict) -> bool:
    return str(w.get("name", "")).startswith(("add_", "create_"))


def _stamm(label: str) -> str:
    """Erstes Wort des Titels, klein — „Geigenstunde @ Geigenschule" → geigenstunde."""
    w = re.findall(r"[\wäöüß]+", str(label or "").casefold())
    return w[0] if w else ""


def ist_fehler(w: dict) -> bool:
    return bool(w.get("fehler")) or bool(_FEHLER.search(str(w.get("ergebnis") or "")))


def rueckfrage_gestellt(zug: dict) -> bool:
    """Hat sie zurückgefragt? Knopf-Frage, oder ihre Antwort endet mit einer
    Frage (die letzten 300 Zeichen enthalten ein „?")."""
    if any(w.get("name") == FRAGE_WERKZEUG for w in zug.get("werkzeuge", [])):
        return True
    return "?" in (zug.get("antwort") or "")[-300:]


def berechnen(ergebnis: dict) -> dict:
    zuege = ergebnis.get("zuege", [])
    alle = [w for z in zuege for w in z.get("werkzeuge", [])]
    m = {
        "zuege": len(zuege),
        "werkzeug_aufrufe": len(alle),
        "schreibende_aufrufe": sum(1 for w in alle if schreibt(w.get("name"))),
        "werkzeug_fehler": sum(1 for w in alle if ist_fehler(w)),
        "ins_leere": sum(1 for w in alle if _INS_LEERE.search(str(w.get("ergebnis") or ""))),
        "erlaubnis_fragen": sum(1 for z in zuege for f in z.get("fragen", [])
                                if f.get("art") == "erlaubnis"),
        "knopf_fragen": sum(1 for w in alle if w.get("name") == FRAGE_WERKZEUG),
        "schleifen_fehler": [f for z in zuege for f in z.get("fehler", [])],
        "laufzeit_s": ergebnis.get("laufzeit_s"),
        "kosten_eur": ergebnis.get("kosten_eur"),
    }

    # Löschen + Neuanlegen desselben Dings statt Ändern.
    loesch_neu = []
    geloescht = []                                 # (zug, stamm)
    for zi, z in enumerate(zuege, 1):
        for w in z.get("werkzeuge", []):
            st = _stamm((w.get("args") or {}).get("label"))
            if loescht(w) and st:
                geloescht.append((zi, st))
            elif legt_an(w) and st and any(s == st for _, s in geloescht):
                loesch_neu.append(f"Zug {zi}: {st} gelöscht und neu angelegt")
    m["loeschen_und_neu"] = loesch_neu

    # Derselbe Aufruf zweimal im selben Zug.
    doppelt = []
    for zi, z in enumerate(zuege, 1):
        gesehen = set()
        for w in z.get("werkzeuge", []):
            schluessel = (w.get("name"), json.dumps(w.get("args"), sort_keys=True,
                                                    ensure_ascii=False))
            if schluessel in gesehen:
                doppelt.append(f"Zug {zi}: {w.get('name')} zweimal gleich")
            gesehen.add(schluessel)
    m["doppelte_aufrufe"] = doppelt
    m["unnoetige_aufrufe"] = len(loesch_neu) + len(doppelt)

    # Frage ohne Antwort — und danach trotzdem geschrieben?
    ohne_antwort = []
    for zi, z in enumerate(zuege, 1):
        offen = False
        for w in z.get("werkzeuge", []):
            if w.get("name") == FRAGE_WERKZEUG:
                antwort = (w.get("frage") or {}).get("antwort")
                offen = antwort in _KEINE_WAHL or str(antwort) in _KEINE_WAHL
            elif offen and schreibt(w.get("name")):
                ohne_antwort.append(f"Zug {zi}: {w.get('name')} nach unbeantworteter Frage")
    m["handelt_ohne_antwort"] = ohne_antwort

    # Rückfragen, wo der Fall sie erwartet (fehlende Angaben).
    rf = []
    for zi, z in enumerate(zuege, 1):
        soll = (z.get("erwartet") or {}).get("rueckfrage")
        if soll is None:
            continue
        ist = rueckfrage_gestellt(z)
        rf.append({"zug": zi, "erwartet": bool(soll), "gestellt": ist,
                   "ok": ist == bool(soll)})
    m["rueckfragen"] = rf
    return m
