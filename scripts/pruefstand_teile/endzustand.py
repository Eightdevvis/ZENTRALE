# Stimmt der Kalender danach? — deterministisch, ohne Modell.
#
# Geprüft wird der ZUSTAND, nicht die Wortwahl und nicht der Weg: ob die KI
# eine Pause, eine Ausnahme oder eine neue Regel benutzt hat, ist ihre Sache;
# ob die Geigenstunde am 22.10. um 18:10 stattfindet, ist Sashas. Deshalb
# laufen die meisten Prüfungen über die aufgeklappte Tagesansicht
# (kalender.entries_in_range), wie die TUI sie zeigt.
#
# Eine Prüfung im Fall (Liste unter `endzustand`):
#
#   - was: Geige Do 22.10. 18:10–19:00 an der Geigenschule
#     am: 2026-10-22          # ein Tag oder eine Liste
#     label: geige            # Teilwort des Titels, egal ob groß/klein
#     findet_statt: true      # true: genau `anzahl` (Standard 1) aktive Treffer
#                             # false: kein aktiver Treffer (fehlt oder fällt aus)
#     beginn: "18:10"         # nur mit findet_statt: true
#     ende: "19:00"           # fehlt das Ende im Kalender, ist das ein Fehler
#     ort: geigenschule       # Teilwort des ORT-Felds (nicht des Titels)
#     titel_ohne: geigenschule  # darf NICHT im Titel stehen (Ort im Namen versteckt)
#     anzahl: 0               # ohne findet_statt: Treffer überhaupt
#
#   - was: Nur eine Geigen-Regel
#     regeln: {label: geige, anzahl: 1}     # Wiederholungs-Regeln zählen
#
#   - was: Parkour fragt nach ODER behält die Dauer
#     eins_von:               # bestanden, wenn EINE Liste ganz besteht
#       - [ {…}, {…} ]
#       - [ {…} ]

from datetime import date


_WT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _tage(am) -> list:
    werte = am if isinstance(am, list) else [am]
    return [w if isinstance(w, date) else date.fromisoformat(str(w)) for w in werte]


def _uhr(v):
    if v is None:
        return None
    if isinstance(v, int):               # YAML 1.1: 18:30 → 1110
        return f"{v // 60:02d}:{v % 60:02d}"
    return str(v)


def _aktiv(e: dict) -> bool:
    return not e.get("ausfall") and not e.get("deaktiviert")


def _kurz(e: dict) -> str:
    teile = [e.get("label", "?")]
    if e.get("time"):
        teile.append(e["time"] + ("–" + e["ende"] if e.get("ende") else " (ohne Ende)"))
    if e.get("ort"):
        teile.append("@ " + e["ort"])
    if e.get("ausfall"):
        teile.append(f"[fällt aus: {e['ausfall']}]")
    if e.get("deaktiviert"):
        teile.append("[abgesagt]")
    return " ".join(teile)


def _tag_pruefen(p: dict, tag: date) -> str | None:
    """None = bestanden, sonst der Grund."""
    import kalender
    nadel = str(p.get("label", "")).casefold()
    eintraege = kalender.entries_in_range(tag, tag).get(tag.isoformat(), [])
    treffer = [e for e in eintraege if nadel in str(e.get("label", "")).casefold()]
    aktiv = [e for e in treffer if _aktiv(e)]
    gesehen = "; ".join(_kurz(e) for e in treffer) or "nichts"
    wo = f"{_WT[tag.weekday()]} {tag.strftime('%d.%m.')}: {gesehen}"

    if p.get("findet_statt") is False:
        return f"findet doch statt — {wo}" if aktiv else None
    if p.get("findet_statt") is True:
        soll = int(p.get("anzahl", 1))
        if len(aktiv) != soll:
            return f"{len(aktiv)} statt {soll} — {wo}"
        for e in aktiv:
            if p.get("beginn") and e.get("time") != _uhr(p["beginn"]):
                return f"Beginn {e.get('time') or 'ganztags'} statt {_uhr(p['beginn'])} — {wo}"
            if p.get("ende") and e.get("ende") != _uhr(p["ende"]):
                ist = e.get("ende") or "kein Ende eingetragen (zählt als 60 min)"
                return f"Ende {ist} statt {_uhr(p['ende'])} — {wo}"
            if p.get("titel_ohne") and str(p["titel_ohne"]).casefold() in str(e.get("label", "")).casefold():
                return f"{p['titel_ohne']!r} steht im Titel {e.get('label')!r} — {wo}"
            if p.get("ort") and str(p["ort"]).casefold() not in str(e.get("ort") or "").casefold():
                return (f"Ort {e.get('ort')!r} statt …{p['ort']}… "
                        f"(Titel: {e.get('label')!r}) — {wo}")
        return None
    if "anzahl" in p:
        return None if len(treffer) == int(p["anzahl"]) else \
            f"{len(treffer)} statt {p['anzahl']} Treffer — {wo}"
    return "Prüfung sagt nicht, was gelten soll (findet_statt/anzahl)"


def _regeln_pruefen(p: dict) -> str | None:
    import kalender
    r = p["regeln"]
    nadel = str(r.get("label", "")).casefold()
    daten = kalender._load_raw()
    gefunden = [x for lyr in daten.get("layers", {}).values()
                for x in lyr.get("routines") or []
                if nadel in str(x.get("label", "")).casefold()]
    soll = int(r.get("anzahl", 1))
    if len(gefunden) == soll:
        return None
    zeilen = ", ".join(f"{x.get('label')} ({x.get('rrule')}, {x.get('time') or 'ganztags'}"
                       f"{'–' + x['ende'] if x.get('ende') else ''})" for x in gefunden)
    return f"{len(gefunden)} Regeln statt {soll}: {zeilen or '—'}"


def eine(p: dict) -> str | None:
    """Eine Prüfung. -> None (bestanden) oder Grund."""
    if "eins_von" in p:
        gruende = []
        for alternative in p["eins_von"]:
            g = [x for x in (eine(q) for q in alternative) if x]
            if not g:
                return None
            gruende.append(" & ".join(g))
        return "keine Variante passt: " + " | ".join(gruende)
    if "regeln" in p:
        return _regeln_pruefen(p)
    if "am" in p:
        for tag in _tage(p["am"]):
            g = _tag_pruefen(p, tag)
            if g:
                return g
        return None
    return "Prüfung ohne am/regeln/eins_von"


def pruefen(liste: list) -> list:
    """-> [{was, ok, grund}]"""
    raus = []
    for p in liste:
        try:
            grund = eine(p)
        except Exception as e:
            grund = f"Prüfung abgestürzt: {e}"
        raus.append({"was": p.get("was"), "ok": grund is None, "grund": grund})
    return raus
