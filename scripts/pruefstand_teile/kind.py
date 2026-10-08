# Ein Fall in einem Prozess: Attrappen einhängen, fahren, messen, richten.
#
# scripts/pruefstand.py startet je Fall einen eigenen Python-Prozess
# (--einzeln): jeder Fall beginnt mit frischem Modul-Zustand (Erlaubnis „für
# dieses Gespräch", Alarme, Caches des Kalenders), und --vergleich kann den
# Kern eines ANDEREN Stands laden, ohne dass sich zwei Stände in einem
# Prozess mischen. Der Trockentest (tests/test_pruefstand.py) ruft
# ausfuehren() direkt auf, mit gefälschtem Modell und Richter.

import traceback

from . import lauf, metriken, richter, umgebung


def ausfuehren(fall: dict, *, code_wurzel: str, tmp: str, richter_modell=None,
               ohne_richter: bool = False, richter_fragen=None) -> dict:
    """Voraussetzung: Env ist vorbereitet (umgebung.vorbereiten) und der Kern
    importierbar. -> Ergebnis des Falls mit Metriken und Urteil."""
    import usage
    from ui.app import app

    kosten = []
    echt_buchen = usage.buchen

    def buchen(model, **kw):
        eur = echt_buchen(model, **kw)
        kosten.append({"modell": model, "eur": float(eur or 0), **kw})
        return eur

    rueckwege = []
    netz = umgebung.NetzAttrappe(fall.get("netz"))
    antworter = umgebung.Antworter(fall.get("antworten"))
    try:
        rueckwege.append(umgebung.umlenken(tmp))
        rueckwege.append(netz.einhaengen())
        rueckwege.append(antworter.einhaengen())
        usage.buchen = buchen
        try:
            erg = lauf.fall_fahren(fall, code_wurzel=code_wurzel, app=app,
                                   antworter=antworter, kosten=kosten)
        except Exception:
            erg = {"id": fall["id"], "titel": fall.get("titel"),
                   "verdeckt": bool(fall.get("verdeckt")), "zuege": [],
                   "endzustand": [{"was": "Lauf", "ok": False, "grund": "abgestürzt"}],
                   "absturz": traceback.format_exc(limit=6),
                   "kosten_eur": round(sum(k["eur"] for k in kosten), 5)}
        erg["metriken"] = metriken.berechnen(erg)
        erg["netz"] = netz.protokoll
        erg["fragen"] = antworter.protokoll
        if ohne_richter or not erg.get("zuege"):
            erg["richter"] = {"behauptungen": [], "zaehlung": richter.zaehlen([]),
                              "fehler": "Richter nicht gefragt"}
            erg["richter_kosten_eur"] = 0.0
        else:
            vorher = len(kosten)
            erg["richter"] = richter.urteilen(erg, fragen=richter_fragen,
                                              modell=richter_modell)
            erg["richter_kosten_eur"] = round(sum(k["eur"] for k in kosten[vorher:]), 5)
        return erg
    finally:
        usage.buchen = echt_buchen
        for zurueck in reversed(rueckwege):
            zurueck()


def nur_richten(erg: dict, *, richter_modell=None) -> dict:
    """Den Richter neu über einen schon gefahrenen Fall schicken (ohne die
    Züge zu wiederholen) — für einen verbesserten Richter oder wenn er beim
    ersten Mal scheiterte. Voraussetzung wie oben."""
    import usage
    kosten = []
    echt_buchen = usage.buchen

    def buchen(model, **kw):
        eur = echt_buchen(model, **kw)
        kosten.append(float(eur or 0))
        return eur

    usage.buchen = buchen
    try:
        erg["richter"] = richter.urteilen(erg, modell=richter_modell)
    finally:
        usage.buchen = echt_buchen
    erg["richter_kosten_eur"] = round(sum(kosten), 5)
    return erg
