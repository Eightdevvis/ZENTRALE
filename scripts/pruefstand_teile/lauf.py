# Einen Fall fahren: Ausgangszustand anlegen, jede Nutzer-Nachricht über den
# ECHTEN Weg schicken (POST /api/chat → kern.chat → Werkzeug-Schleife →
# echte Werkzeuge gegen die Probe-Daten), alles mitschreiben.
#
# Warum über die Route und nicht direkt kern.chat (2026-10-08): die Route
# speichert das Gespräch (Werkzeug-Zusammenfassungen im Verlauf, wie die KI
# sie im nächsten Zug sieht), öffnet den Zug (Gesprächs-Erlaubnis, Ablage)
# und baut den Verlauf. Ein Prüfstand, der daneben eine eigene Kopie davon
# fährt, prüfte die Kopie.

import json
import time
from datetime import timedelta

from . import faelle, uhr


def _text(v) -> str:
    return "" if v is None else str(v)


def _uhrzeit(v):
    """YAML 1.1 liest 18:30 ohne Anführungszeichen als Zahl (1110)."""
    if v is None or v == "":
        return None
    if isinstance(v, int):
        return f"{v // 60:02d}:{v % 60:02d}"
    return str(v)


# ── Ausgangszustand ────────────────────────────────────────────────────

def ausgangszustand(fall: dict) -> None:
    """Kalender und Gedächtnis des Falls anlegen (über die öffentlichen
    Funktionen — so steht es genauso da, wie Sasha es angelegt hätte)."""
    import gedaechtnis
    import kalender
    kalender.ensure_init()
    kal = fall.get("kalender") or {}
    for t in kal.get("termine") or []:
        extras = {k: _uhrzeit(t[k]) if k == "ende" else _text(t[k])
                  for k in ("ende", "ort") if t.get(k)}
        layer = t.get("layer", "termine")
        if t.get("bis"):
            ok = kalender.add_span(layer, _text(t["tag"]), _text(t["bis"]),
                                   _text(t["label"]), **extras)
        else:
            ok = kalender.add_entry(layer, _text(t["tag"]), _text(t["label"]),
                                    time=_uhrzeit(t.get("zeit")), **extras)
        if not ok:
            raise faelle.FallFehler(f"Termin nicht anlegbar: {t}")
    for r in kal.get("routinen") or []:
        extras = {k: _uhrzeit(r[k]) if k == "ende" else _text(r[k])
                  for k in ("ende", "ort") if r.get(k)}
        if not kalender.add_routine(r.get("layer", "termine"), _text(r["label"]),
                                    _text(r["rrule"]), time=_uhrzeit(r.get("zeit")),
                                    **extras):
            raise faelle.FallFehler(f"Routine nicht anlegbar: {r}")
    for p in kal.get("pausen") or []:
        if not kalender.add_pause(_text(p["label"]), _text(p["von"]),
                                  _text(p["bis"]), p.get("grund")):
            raise faelle.FallFehler(f"Pause nicht anlegbar: {p}")
    for name, inhalt in (fall.get("gedaechtnis") or {}).items():
        bereich, _, datei = str(name).rpartition("/")
        with open(gedaechtnis._pfad(bereich, datei), "w", encoding="utf-8") as f:
            f.write(str(inhalt))


def kalender_ansicht(tage_vor: int = 1, tage_nach: int = 35) -> str:
    """Was WIRKLICH im Kalender steht (für den Richter, die KI sieht es nicht)."""
    import kalender
    from datetime import date
    heute = date.today()
    try:
        return kalender.render_range_for_tool(heute - timedelta(days=tage_vor),
                                              heute + timedelta(days=tage_nach))
    except Exception as e:
        return f"(Kalender nicht lesbar: {e})"


def kontext_der_ki() -> str:
    """Die wechselnden Teile, die die KI zu Beginn des Zugs im Prompt hat und
    die Tatsachen tragen: Datum, „Was ansteht" (heute/morgen), offene
    Erinnerungen. Nur die — Persona und Werkzeug-Texte belegen nichts."""
    import ki_prompt
    teile = []
    for fn in ("_now_prompt", "_imprint_prompt", "_alarm_prompt"):
        f = getattr(ki_prompt, fn, None)
        if f is None:
            continue
        try:
            t = f() or ""
        except Exception as e:
            t = f"({fn} fehlgeschlagen: {e})"
        if fn == "_now_prompt":
            t = t.split("\n\n")[0]          # nur die Datumszeile, nicht die Regeln
        if t:
            teile.append(t)
    return "\n\n".join(teile)


# ── Ein Zug ────────────────────────────────────────────────────────────

def _sse_ereignisse(antwort):
    """Die SSE-Zeilen einer gestreamten Flask-Antwort als dicts, der Reihe nach."""
    puffer = ""
    for stueck in antwort.response:
        puffer += stueck.decode("utf-8") if isinstance(stueck, bytes) else stueck
        while "\n\n" in puffer:
            block, puffer = puffer.split("\n\n", 1)
            for zeile in block.splitlines():
                if zeile.startswith("data: "):
                    try:
                        yield json.loads(zeile[6:])
                    except ValueError:
                        pass


def zug_fahren(client, gid: str, nachricht: str, antworter, kosten: list) -> dict:
    """Eine Nutzer-Nachricht schicken und alles mitschreiben."""
    zug = {"sagt": nachricht, "antwort": "", "denken": "", "werkzeuge": [],
           "fragen": [], "fehler": [], "gestoppt": False, "quellen": []}
    start, k0 = time.monotonic(), len(kosten)
    antwort = client.post("/api/chat", json={"message": nachricht, "gespraech": gid},
                          buffered=False)
    if antwort.status_code != 200:
        zug["fehler"].append(f"HTTP {antwort.status_code}: "
                             f"{antwort.get_data(as_text=True)[:300]}")
    else:
        text, denken = [], []
        for ev in _sse_ereignisse(antwort):
            if "token" in ev:
                text.append(ev["token"])
            elif "reflect" in ev:
                denken.append(_text(ev["reflect"]))
            elif "werkzeug" in ev:
                w = ev["werkzeug"]
                if w.get("phase") == "start":
                    zug["werkzeuge"].append({"name": w.get("name"),
                                             "args": w.get("args") or {},
                                             "ergebnis": None, "fehler": False})
                elif zug["werkzeuge"]:
                    zug["werkzeuge"][-1]["ergebnis"] = _text(w.get("text"))
                    zug["werkzeuge"][-1]["fehler"] = w.get("phase") == "fehler"
            elif "permission" in ev:
                p = ev["permission"]
                gewaehlt = antworter.entscheiden(p)
                eintrag = {"art": "erlaubnis" if p.get("erlaubnis") else "knopf",
                           "frage": p.get("frage"), "optionen": p.get("optionen"),
                           "antwort": gewaehlt}
                zug["fragen"].append(eintrag)
                if zug["werkzeuge"]:
                    zug["werkzeuge"][-1]["frage"] = eintrag
                    if eintrag["art"] == "knopf":
                        # ask_choice hat kein Ergebnis-Event: die Schleife gibt
                        # das Ergebnis direkt ans Modell (werkzeug_schleife.
                        # _knopf_werkzeug). Mitschreiben, was dort steht.
                        zug["werkzeuge"][-1]["ergebnis"] = f"Sasha hat gewählt: {gewaehlt}."
            elif "quellen" in ev:
                # Die Quellen-Zeile, die Python unter die Antwort setzt
                # (core/quellen.py, 2026-10-10) — prüfbar mit `quellen:`.
                zug["quellen"] = list(ev["quellen"] or [])
            elif "fehler" in ev:
                zug["fehler"].append(_text(ev["fehler"]))
            elif "gestoppt" in ev:
                zug["gestoppt"] = True
        zug["antwort"] = "".join(text)
        zug["denken"] = "".join(denken)
    zug["laufzeit_s"] = round(time.monotonic() - start, 1)
    zug["kosten_eur"] = round(sum(k["eur"] for k in kosten[k0:]), 5)
    return zug


# ── Der ganze Fall ─────────────────────────────────────────────────────

def fall_fahren(fall: dict, *, code_wurzel: str, app, antworter, kosten: list,
                frueh: bool = False, beobachter=None) -> dict:
    """-> Rohergebnis des Falls (ohne Richter): Züge, Endzustand, Ansichten.

    frueh=True (--abbruch-frueh): nach jedem Zug aufhören, sobald der Fall
    sicher verloren ist (frueh.py) — die restlichen Züge kosten nur noch.
    beobachter (aufnahme.py): vor_zug(n) vor, nach_zug(n) nach jedem Zug;
    gibt nach_zug einen Text zurück (Abspielen nicht mehr gültig), endet
    der Fall dort."""
    from . import frueh as frueh_
    import gespraeche
    import kalender
    import state
    from . import endzustand

    ergebnis = {"id": fall["id"], "titel": fall.get("titel"),
                "verdeckt": bool(fall.get("verdeckt")), "zuege": [],
                "jetzt": _text(fall.get("jetzt"))}
    start = time.monotonic()
    with uhr.verstellt(faelle.jetzt_von(fall), code_wurzel):
        ausgangszustand(fall)
        ergebnis["kalender_vorher"] = kalender_ansicht()
        gid = gespraeche.neu(titel=f"Prüfstand {fall['id']}")
        client = app.test_client()
        for z in fall["zuege"]:
            # Der Event-Loop (core/main.py) rechnet die Erinnerungen
            # regelmäßig nach; hier läuft er nicht, also vor jedem Zug.
            state.set_alarms(kalender.open_alarms())
            kontext = kontext_der_ki()
            antworter.zug_vorgaben = z.get("antworten") or {}
            if beobachter:
                beobachter.vor_zug(len(ergebnis["zuege"]) + 1)
            zug = zug_fahren(client, gid, str(z["sagt"]), antworter, kosten)
            zug["kontext"] = kontext
            zug["erwartet"] = z.get("erwartet") or {}
            zug["kalender_danach"] = kalender_ansicht()
            ergebnis["zuege"].append(zug)
            if any(f.startswith("HTTP ") for f in zug["fehler"]):
                break
            if beobachter and beobachter.nach_zug(len(ergebnis["zuege"])):
                break
            if frueh and len(ergebnis["zuege"]) < len(fall["zuege"]):
                grund = frueh_.verloren(fall, ergebnis)
                if grund:
                    ergebnis["frueh_abgebrochen"] = {
                        "nach_zug": len(ergebnis["zuege"]), "von": len(fall["zuege"]),
                        "grund": grund}
                    break
        ergebnis["endzustand"] = endzustand.pruefen(fall["endzustand"], ergebnis)
    ergebnis["laufzeit_s"] = round(time.monotonic() - start, 1)
    ergebnis["kosten_eur"] = round(sum(k["eur"] for k in kosten), 5)
    ergebnis["modelle"] = sorted({k["modell"] for k in kosten})
    return ergebnis
