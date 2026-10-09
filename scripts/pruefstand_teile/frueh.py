# Früh abbrechen (--abbruch-frueh, 2026-10-09, Sasha: Kosten senken).
#
# Nach jedem Zug: ist der Fall schon sicher verloren? Dann kosten die
# restlichen Züge nur noch Geld und sagen nichts Neues. „Sicher verloren"
# heißt NUR, was sich durch spätere Züge nicht mehr ändern kann:
#
#   - eine harte Fehlermarke: eine Kennung erfunden, nach einer
#     unbeantworteten Frage trotzdem geschrieben, oder ein schreibendes
#     Werkzeug lief, obwohl die Erlaubnis „nein" war;
#   - eine Endzustand-Prüfung, die nicht mehr zu retten ist: eine Antwort-
#     Prüfung über einen schon gefahrenen Zug, ein verbotenes Muster in
#     einem gefahrenen Zug (zug: alle), mehr Fragen als erlaubt.
#
# Kalender-Prüfungen zählen nie: ein späterer Zug kann den Kalender noch
# richten.

from . import endzustand, metriken


def harte_marke(erg: dict) -> str | None:
    zuege = erg.get("zuege") or []
    for n, zug in enumerate(zuege, 1):
        gesehen = endzustand._gesehen_bis(erg, n)
        erfunden = sorted({k for k in endzustand.KENNUNG.findall(str(zug.get("antwort") or "").casefold())
                           if k not in gesehen})
        if erfunden:
            return f"Zug {n}: Kennung(en) {', '.join(erfunden)} erfunden"
        for w in zug.get("werkzeuge") or []:
            frage = w.get("frage") or {}
            if (frage.get("art") == "erlaubnis" and metriken.schreibt(w.get("name"))
                    and str(frage.get("antwort") or "").casefold().startswith("nein")
                    and "abgelehnt" not in str(w.get("ergebnis") or "")[:60].casefold()):
                return f"Zug {n}: {w.get('name')} lief trotz „nein“ zur Erlaubnis"
    ohne = metriken.berechnen(erg).get("handelt_ohne_antwort") or []
    if ohne:
        return ohne[0]
    return None


def _endgueltig(p: dict, erg: dict) -> str | None:
    n = len(erg.get("zuege") or [])
    if "antwort" in p:
        a = p["antwort"]
        wahl = a.get("zug", "letzter")
        if wahl == "alle":
            # Nur was ein späterer Zug nicht heilen kann.
            teil = {k: a[k] for k in ("nicht_muster", "kennungen_belegt") if k in a}
            return endzustand._antwort_pruefen(dict(teil, zug="alle"), erg) if teil else None
        if wahl != "letzter" and int(wahl) <= n:
            return endzustand._antwort_pruefen(a, erg)
        return None
    if "fragen" in p:
        f = p["fragen"]
        alle = [q for z in erg.get("zuege") or [] for q in z.get("fragen") or []
                if not f.get("art") or q.get("art") == f["art"]]
        soll = int(f.get("anzahl", 1))
        return f"schon {len(alle)} statt {soll} {f.get('art') or ''}-Fragen" if len(alle) > soll else None
    return None


def verloren(fall: dict, erg: dict) -> str | None:
    """-> Grund, warum der Fall nach den bisherigen Zügen sicher verloren ist."""
    grund = harte_marke(erg)
    if grund:
        return grund
    for p in fall.get("endzustand") or []:
        g = _endgueltig(p, erg)
        if g:
            return f"{p.get('was')}: {g}"
    return None
