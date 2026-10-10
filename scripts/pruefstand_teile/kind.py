# Ein Fall in einem Prozess: Attrappen einhängen, fahren, messen, richten.
#
# scripts/pruefstand.py startet je Fall einen eigenen Python-Prozess
# (--einzeln): jeder Fall beginnt mit frischem Modul-Zustand (Erlaubnis „für
# dieses Gespräch", Alarme, Caches des Kalenders), und --vergleich kann den
# Kern eines ANDEREN Stands laden, ohne dass sich zwei Stände in einem
# Prozess mischen. Der Trockentest (tests/test_pruefstand.py) ruft
# ausfuehren() direkt auf, mit gefälschtem Modell und Richter.

import traceback

from . import aufnahme as aufnahme_
from . import lauf, metriken, richter, umgebung

# Steht im Log jedes Prozesses, der in den Prüfstand-Topf bucht. Das
# Umbuch-Skript (scripts/pruefstand_umbuchen.py) lässt solche Logs aus: ihre
# Kosten liegen schon richtig.
TOPF_MARKE = "PRÜFSTAND-KOSTEN → eigener Topf (pruefstand)"


def topf_setzen():
    """Alle Buchungen dieses Prozesses in den Prüfstand-Topf (2026-10-09:
    Sashas Monatsdeckel zählt nur noch seinen Chat). -> Rückweg.

    Ein älterer Kern (--vergleich gegen einen Stand vor der Trennung) kennt
    keine Herkunft und bucht weiter in den Chat — dann ohne Marke im Log,
    damit das Umbuch-Skript diese Kosten findet."""
    import usage
    setzen = getattr(usage, "herkunft_setzen", None)
    if setzen is None:
        print("PRÜFSTAND-KOSTEN → Chat-Topf (dieser Stand kennt keine Trennung)",
              flush=True)
        return lambda: None
    alt = setzen(getattr(usage, "PRUEFSTAND", "pruefstand"))
    print(TOPF_MARKE, flush=True)
    return lambda: setzen(alt)


def ausfuehren(fall: dict, *, code_wurzel: str, tmp: str, richter_modell=None,
               ohne_richter: bool = False, richter_fragen=None, frueh: bool = False,
               aufnahme: str | None = None, abspielen: str | None = None) -> dict:
    """Voraussetzung: Env ist vorbereitet (umgebung.vorbereiten) und der Kern
    importierbar. -> Ergebnis des Falls mit Metriken und Urteil.

    frueh: --abbruch-frueh (frueh.py). aufnahme: Pfad, unter dem die
    Modell-Antworten mitgeschrieben werden. abspielen: Pfad einer Aufnahme —
    dann kein Modell, kein Richter, keine Kosten (aufnahme.py)."""
    import usage
    from ui.app import app

    kosten = []
    echt_buchen = usage.buchen

    def buchen(model, **kw):
        # Abspielen kostet nichts — auch keine 0-€-Aufrufe in der Buchhaltung.
        eur = 0.0 if abspielen else echt_buchen(model, **kw)
        kosten.append({"modell": model, "eur": float(eur or 0), **kw})
        return eur

    rueckwege = [topf_setzen()]
    try:
        # Seiten für den Browser auf 127.0.0.1 (Abschnitt `browser`); ihre
        # Adresse steht im Fall als {server}.
        server = umgebung.SeitenServer((fall.get("browser") or {}).get("seiten"))
        rueckwege.append(server.starten())
        fall = umgebung.platzhalter(fall, {"{server}": server.adresse or ""})
        # Der Browser darf nur an diesen Server, sonst nirgends hin.
        rueckwege.append(umgebung.browser_einsperren(server.adresse))
    except Exception:
        for zurueck in reversed(rueckwege):
            zurueck()
        raise
    netz = umgebung.NetzAttrappe(fall.get("netz"))
    antworter = umgebung.Antworter(fall.get("antworten"))
    beobachter = None
    if abspielen:
        beobachter = aufnahme_.Abspielen.laden(abspielen)
        ohne_richter = True
    elif aufnahme:
        beobachter = aufnahme_.Aufnahme(fall["id"])
    try:
        rueckwege.append(umgebung.umlenken(tmp))
        rueckwege.append(netz.einhaengen())
        rueckwege.append(antworter.einhaengen())
        if beobachter:
            rueckwege.append(beobachter.einhaengen())
        usage.buchen = buchen
        try:
            erg = lauf.fall_fahren(fall, code_wurzel=code_wurzel, app=app,
                                   antworter=antworter, kosten=kosten,
                                   frueh=frueh, beobachter=beobachter)
        except Exception:
            erg = {"id": fall["id"], "titel": fall.get("titel"),
                   "verdeckt": bool(fall.get("verdeckt")), "zuege": [],
                   "endzustand": [{"was": "Lauf", "ok": False, "grund": "abgestürzt"}],
                   "absturz": traceback.format_exc(limit=6),
                   "kosten_eur": round(sum(k["eur"] for k in kosten), 5)}
        if abspielen:
            erg["abspielen"] = beobachter.bericht()
        elif aufnahme:
            try:
                beobachter.speichern(aufnahme)
            except OSError as e:
                print(f"Aufnahme nicht gespeichert: {e}")
        erg["metriken"] = metriken.berechnen(erg)
        erg["netz"] = netz.protokoll
        erg["fragen"] = antworter.protokoll
        if server.adresse:
            erg["seiten_server"] = {"adresse": server.adresse, "aufrufe": server.protokoll}
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
    zurueck = topf_setzen()
    try:
        erg["richter"] = richter.urteilen(erg, modell=richter_modell)
    finally:
        zurueck()
        usage.buchen = echt_buchen
    erg["richter_kosten_eur"] = round(sum(kosten), 5)
    return erg
