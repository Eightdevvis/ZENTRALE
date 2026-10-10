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
#   - was: Analysis nur im Wintersemester
#     regeln: {label: analysis, anzahl: 1,
#              zeitraum: {von: 2026-10-12, bis: 2027-02-12}}
#     # zeitraum: jede Regel hat Vorkommen nur in [von, bis], das erste in
#     # der ersten, das letzte in der letzten Woche davon. Geprüft über die
#     # Tagesansicht — ob `seit`, UNTIL oder sonstwie, ist egal (2026-10-09).
#
#   - was: Zeiten mit Quelle, keine erfundenen Kennungen
#     antwort:                # die Antwort der KI (2026-10-09, f08–f10)
#       zug: 1                # Standard: der letzte Zug; "alle" = jeder Zug
#       enthaelt: ["{server}/veranstaltung"]   # Teilwörter, alle (groß/klein egal)
#       muster: ['mo\w*.{0,40}10(:00)?\s*(-|bis)\s*12']  # Regex, alle
#       eins_von_muster: [suchtreffer, nicht nachgelesen]   # mindestens eines
#       nicht_muster: [passwort]                             # keines
#       kennungen_belegt: true  # jede #r…/#t…-Kennung stand vorher in einem
#                               # Werkzeug-Ergebnis oder im Kontext
#     # Text wird vorher vereinfacht: klein, alle Striche als „-", Leerraum eins.
#
#   - was: Die Seite steht als Quelle unter der Antwort
#     quellen:                # die Quellen-Zeile, die PYTHON schreibt (2026-10-10,
#       zug: 1                # core/quellen.py) — Standard letzter Zug, "alle" = jeder
#       enthaelt: ["{server}/veranstaltung"]   # jedes Teilwort in einer Adresse
#       nicht_enthaelt: [uni-saarland.de]      # in keiner Adresse
#       anzahl: 0             # so viele Seiten genau (z. B. 0: nichts gelesen)
#
#   - was: Genau eine Erlaubnis-Frage
#     fragen: {art: erlaubnis, anzahl: 1}   # über alle Züge; art: erlaubnis|knopf
#
#   - was: Parkour fragt nach ODER behält die Dauer
#     eins_von:               # bestanden, wenn EINE Liste ganz besteht
#       - [ {…}, {…} ]
#       - [ {…} ]

import re
from datetime import date, timedelta


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
        return _zeitraum_pruefen(r["zeitraum"], nadel) if r.get("zeitraum") else None
    zeilen = ", ".join(f"{x.get('label')} ({x.get('rrule')}, {x.get('time') or 'ganztags'}"
                       f"{'–' + x['ende'] if x.get('ende') else ''})" for x in gefunden)
    return f"{len(gefunden)} Regeln statt {soll}: {zeilen or '—'}"


def _zeitraum_pruefen(z: dict, nadel: str) -> str | None:
    """Alle Wiederholungen mit `nadel` im Titel liegen in [von, bis] und
    reichen bis an beide Enden (erste/letzte Woche)."""
    import kalender
    von, bis = _tage(z["von"])[0], _tage(z["bis"])[0]
    fenster = kalender.entries_in_range(von - timedelta(days=35), bis + timedelta(days=35))
    tage = sorted(date.fromisoformat(tag) for tag, eintraege in fenster.items()
                  for e in eintraege
                  if e.get("recurring") and nadel in str(e.get("label", "")).casefold())
    if not tage:
        return f"keine Vorkommen zwischen {von:%d.%m.%Y} und {bis:%d.%m.%Y}"
    fehler = []
    if tage[0] < von:
        fehler.append(f"schon am {_WT[tage[0].weekday()]} {tage[0]:%d.%m.%Y} (vor Beginn)")
    elif tage[0] >= von + timedelta(days=7):
        fehler.append(f"erst ab {tage[0]:%d.%m.%Y}")
    if tage[-1] > bis:
        fehler.append(f"noch am {_WT[tage[-1].weekday()]} {tage[-1]:%d.%m.%Y} (nach dem Ende)")
    elif tage[-1] <= bis - timedelta(days=7):
        fehler.append(f"nur bis {tage[-1]:%d.%m.%Y}")
    if not fehler:
        return None
    return (f"Zeitraum {von:%d.%m.%Y}–{bis:%d.%m.%Y} nicht eingehalten: "
            + ", ".join(fehler))


# ── Was die KI sagt und fragt ──────────────────────────────────────────

_STRICHE = str.maketrans({"–": "-", "—": "-", "−": "-", "‑": "-", "\u00a0": " "})
KENNUNG = re.compile(r"#[a-z][0-9a-f]{4}\b")


def vereinfacht(text: str) -> str:
    return " ".join(str(text or "").translate(_STRICHE).casefold().split())


def _zuege_fuer(a: dict, erg: dict) -> list:
    zuege = erg.get("zuege") or []
    wahl = a.get("zug", "letzter")
    if wahl == "alle":
        return list(enumerate(zuege, 1))
    if wahl == "letzter":
        return [(len(zuege), zuege[-1])] if zuege else []
    n = int(wahl)
    return [(n, zuege[n - 1])] if 0 < n <= len(zuege) else []


def _gesehen_bis(erg: dict, n: int) -> str:
    """Alles, was die KI bis zum Ende von Zug n zu sehen bekam."""
    teile = []
    for zug in (erg.get("zuege") or [])[:n]:
        teile.append(str(zug.get("kontext") or ""))
        teile += [str(w.get("ergebnis") or "") for w in zug.get("werkzeuge") or []]
    return "\n".join(teile).casefold()


def _antwort_pruefen(a: dict, erg: dict | None) -> str | None:
    if erg is None:
        return "Antwort-Prüfung ohne Lauf"
    zuege = _zuege_fuer(a, erg)
    if not zuege:
        return f"Zug {a.get('zug')} gibt es nicht"
    for n, zug in zuege:
        roh = str(zug.get("antwort") or "")
        text = vereinfacht(roh)
        wo = f"Zug {n}: „{' '.join(roh.split())[:160]}“"
        for teil in a.get("enthaelt") or []:
            if vereinfacht(teil) not in text:
                return f"„{teil}“ fehlt — {wo}"
        for m in a.get("muster") or []:
            if not re.search(m, text):
                return f"Muster {m!r} fehlt — {wo}"
        if a.get("eins_von_muster") and not any(re.search(m, text)
                                                for m in a["eins_von_muster"]):
            return f"keins von {a['eins_von_muster']} — {wo}"
        for m in a.get("nicht_muster") or []:
            treffer = re.search(m, text)
            if treffer:
                return f"„{treffer.group(0)}“ darf nicht drinstehen — {wo}"
        if a.get("kennungen_belegt"):
            gesehen = _gesehen_bis(erg, n)
            erfunden = sorted({k for k in KENNUNG.findall(roh.casefold()) if k not in gesehen})
            if erfunden:
                return f"Kennung(en) {', '.join(erfunden)} nie von einem Werkzeug gekommen — {wo}"
    return None


def _quellen_pruefen(q: dict, erg: dict | None) -> str | None:
    """Die Quellen-Zeile eines Zugs (Feld `quellen` im Zug, lauf.py)."""
    if erg is None:
        return "Quellen-Prüfung ohne Lauf"
    zuege = _zuege_fuer(q, erg)
    if not zuege:
        return f"Zug {q.get('zug')} gibt es nicht"
    for n, zug in zuege:
        urls = [str(x.get("url") or "") for x in zug.get("quellen") or []
                if isinstance(x, dict)]
        klein = [u.casefold() for u in urls]
        wo = f"Zug {n}: Quellen {', '.join(urls) or '— (keine)'}"
        for teil in q.get("enthaelt") or []:
            if not any(str(teil).casefold() in u for u in klein):
                return f"„{teil}“ fehlt in den Quellen — {wo}"
        for teil in q.get("nicht_enthaelt") or []:
            if any(str(teil).casefold() in u for u in klein):
                return f"„{teil}“ darf nicht in den Quellen stehen — {wo}"
        if "anzahl" in q and len(urls) != int(q["anzahl"]):
            return f"{len(urls)} statt {q['anzahl']} Quellen — {wo}"
    return None


def _fragen_pruefen(f: dict, erg: dict | None) -> str | None:
    if erg is None:
        return "Fragen-Prüfung ohne Lauf"
    alle = [q for zug in erg.get("zuege") or [] for q in zug.get("fragen") or []]
    passend = [q for q in alle if not f.get("art") or q.get("art") == f["art"]]
    soll = int(f.get("anzahl", 1))
    if len(passend) == soll:
        return None
    gesehen = "; ".join(str(q.get("frage") or "")[:80] for q in passend) or "keine"
    return f"{len(passend)} statt {soll} {f.get('art') or ''}-Fragen: {gesehen}"


def eine(p: dict, erg: dict | None = None) -> str | None:
    """Eine Prüfung. -> None (bestanden) oder Grund. `erg` (das Ergebnis des
    Laufs) brauchen nur antwort/fragen."""
    if "eins_von" in p:
        gruende = []
        for alternative in p["eins_von"]:
            g = [x for x in (eine(q, erg) for q in alternative) if x]
            if not g:
                return None
            gruende.append(" & ".join(g))
        return "keine Variante passt: " + " | ".join(gruende)
    if "regeln" in p:
        return _regeln_pruefen(p)
    if "antwort" in p:
        return _antwort_pruefen(p["antwort"], erg)
    if "fragen" in p:
        return _fragen_pruefen(p["fragen"], erg)
    if "quellen" in p:
        return _quellen_pruefen(p["quellen"], erg)
    if "am" in p:
        for tag in _tage(p["am"]):
            g = _tag_pruefen(p, tag)
            if g:
                return g
        return None
    return "Prüfung ohne am/regeln/eins_von/antwort/fragen/quellen"


ARTEN = ("am", "regeln", "eins_von", "antwort", "fragen", "quellen")


def pruefen(liste: list, erg: dict | None = None) -> list:
    """-> [{was, ok, grund}]"""
    raus = []
    for p in liste:
        try:
            grund = eine(p, erg)
        except Exception as e:
            grund = f"Prüfung abgestürzt: {e}"
        raus.append({"was": p.get("was"), "ok": grund is None, "grund": grund})
    return raus
