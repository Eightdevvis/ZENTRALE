# Der Richter über die Message Batches API von Anthropic (--richter-batch,
# 2026-10-09, Sasha: Kosten senken).
#
# Halber Preis, dafür kommt das Ergebnis später (meist Minuten, höchstens
# 24 h). Der Richter braucht keine Antwort in Sekunden: die Fälle laufen
# ohne Richter, danach gehen ALLE Richter-Anfragen des Durchgangs in einen
# Batch, der Prüfstand wartet (mit Zeitgrenze) und ordnet die Ergebnisse
# über custom_id wieder den Fällen und Zügen zu (die Reihenfolge der
# Ergebnisse ist beliebig). Geht etwas schief — kein Claude-Modell, Fehler
# beim Anbieter, Zeitgrenze — wirft richten(); scripts/pruefstand.py fällt
# dann auf den normalen Richter zurück.
#
# Was der Richter fragt und wie die Antwort geprüft wird, ist dasselbe wie
# in richter.py (SYSTEM, auftrag, _zeilen_aus, nachpruefen).

import time

from . import richter

MAX_TOKENS = 8000


class KeinBatch(RuntimeError):
    pass


def _id(i: int, zug: int) -> str:
    # custom_id: nur Buchstaben, Ziffern, _ und -, höchstens 64 Zeichen.
    return f"f{i}-z{zug}"


def anfragen(ergebnisse: list, modell: str | None) -> tuple:
    """-> ([{custom_id, params}], {custom_id: (i, zug)}, modell)."""
    mdl = modell or next((m for e in ergebnisse for m in e.get("modelle") or []), None)
    if not mdl or not str(mdl).startswith("claude"):
        raise KeinBatch(f"Batch gibt es nur für Claude-Modelle, nicht {mdl!r}")
    reqs, zuordnung = [], {}
    for i, erg in enumerate(ergebnisse):
        for zi, z in enumerate(erg.get("zuege") or [], 1):
            if not (z.get("antwort") or "").strip():
                continue
            cid = _id(i, zi)
            zuordnung[cid] = (i, zi)
            reqs.append({"custom_id": cid, "params": {
                "model": mdl, "max_tokens": MAX_TOKENS, "system": richter.SYSTEM,
                "messages": [{"role": "user", "content": richter.auftrag(erg, zi)}]}})
    return reqs, zuordnung, mdl


def _buchen(mdl: str, u) -> float:
    """Halber Preis (faktor 0.5), im Prüfstand-Topf."""
    import state
    import usage
    rein = int(getattr(u, "input_tokens", 0) or 0)
    raus = int(getattr(u, "output_tokens", 0) or 0)
    alt = usage.herkunft_setzen(usage.PRUEFSTAND)
    try:
        eur = usage.buchen(mdl, input_tokens=rein, output_tokens=raus, faktor=0.5)
    finally:
        usage.herkunft_setzen(alt)
    state.push_log(f"PRÜFSTAND-RICHTER (Batch) ← {mdl} in={rein} out={raus} ≈{eur:.4f}€")
    return eur


def richten(ergebnisse: list, *, modell: str | None = None, client=None,
            warten_s: float = 1800, takt_s: float = 20, schlafen=time.sleep,
            uhr=time.monotonic) -> list:
    """Richtet alle Fälle in einem Batch. Verändert und liefert `ergebnisse`
    (richter, richter_kosten_eur). Wirft bei jedem Fehler (Aufrufer fällt
    auf den normalen Richter zurück)."""
    reqs, zuordnung, mdl = anfragen(ergebnisse, modell)
    if not reqs:
        return ergebnisse
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=reqs)
    print(f"Richter-Batch {batch.id}: {len(reqs)} Anfragen, warte (höchstens "
          f"{warten_s / 60:.0f} min) …", flush=True)
    start = uhr()
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        if uhr() - start > warten_s:
            try:
                client.messages.batches.cancel(batch.id)
            except Exception:
                pass
            raise KeinBatch(f"Batch {batch.id} nach {warten_s / 60:.0f} min nicht fertig — abgebrochen")
        schlafen(takt_s)

    antworten, fehler, kosten = {}, {}, {}
    for r in client.messages.batches.results(batch.id):
        ziel = zuordnung.get(r.custom_id)
        if ziel is None:
            continue
        if r.result.type == "succeeded":
            msg = r.result.message
            antworten[ziel] = "".join(b.text for b in msg.content
                                      if getattr(b, "type", None) == "text")
            kosten[ziel[0]] = kosten.get(ziel[0], 0.0) + _buchen(mdl, msg.usage)
        else:
            fehler[ziel] = r.result.type
    if not antworten:
        raise KeinBatch(f"Batch {batch.id}: keine einzige Antwort ({sorted(set(fehler.values()))})")

    for i, erg in enumerate(ergebnisse):
        behauptungen, probleme = [], []
        for zi, _ in enumerate(erg.get("zuege") or [], 1):
            if (i, zi) in fehler:
                probleme.append(f"Zug {zi}: {fehler[(i, zi)]}")
            if (i, zi) not in antworten:
                continue
            roh = richter._zeilen_aus(antworten[(i, zi)])
            for b in roh.get("behauptungen") or []:
                b["zug"] = zi
            behauptungen += richter.nachpruefen(roh, erg)
        r = {"behauptungen": behauptungen, "zaehlung": richter.zaehlen(behauptungen),
             "modell": f"{mdl} (Batch)"}
        if probleme:
            r["fehler"] = "Richter ging schief: " + "; ".join(probleme)
        erg["richter"] = r
        erg["richter_kosten_eur"] = round(kosten.get(i, 0.0), 5)
    return ergebnisse
