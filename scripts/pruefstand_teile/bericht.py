# Der Bericht eines Durchgangs: eine Markdown-Seite zum Lesen, ein JSON zum
# Vergleichen, und je Fall ein Transkript (was Sasha sagte, was die KI rief,
# was zurückkam, was sie antwortete).
#
# Verdeckte Fälle (Anthropic: „held-out test set"): im Bericht nur ihre
# Zahlen, keine Behauptungen, keine Gründe — die Details liegen getrennt
# unter verdeckt/. Wer an den Werkzeugen baut, schaut dort nicht hinein,
# sonst optimiert er auf genau diese Fälle hin.

import json
import os

ZEICHEN = {"belegt": "✓", "vermutung": "~", "unbelegt": "?", "falsch": "✗"}


def _eur(x) -> str:
    return f"{(x or 0):.3f} €"


def _endzustand_kurz(f: dict) -> str:
    ez = f.get("endzustand") or []
    ok = sum(1 for e in ez if e["ok"])
    return f"{ok}/{len(ez)}" + (" ✓" if ez and ok == len(ez) else "")


def _belege_kurz(f: dict) -> str:
    r = f.get("richter") or {}
    z = r.get("zaehlung") or {}
    if not r.get("behauptungen") and r.get("fehler"):
        return "Richter-Fehler"
    if not z:
        return "—"
    return (f"{z.get('belegt', 0)} / {z.get('vermutung', 0)} / "
            f"{z.get('unbelegt', 0)} / {z.get('falsch', 0)}"
            + (" ⚠" if r.get("fehler") else ""))


def _rueckfragen_kurz(m: dict) -> str:
    rf = m.get("rueckfragen") or []
    if not rf:
        return "—"
    return f"{sum(1 for r in rf if r['ok'])}/{len(rf)}"


def uebersicht_zeile(f: dict) -> str:
    m = f.get("metriken") or {}
    name = f["id"] + (" (verdeckt)" if f.get("verdeckt") else "")
    return (f"| {name} | {_endzustand_kurz(f)} | {_belege_kurz(f)} | "
            f"{m.get('werkzeug_aufrufe', 0)} | {m.get('werkzeug_fehler', 0)} | "
            f"{m.get('unnoetige_aufrufe', 0)} | {len(m.get('handelt_ohne_antwort') or [])} | "
            f"{_rueckfragen_kurz(m)} | {_eur(f.get('kosten_eur'))} | "
            f"{f.get('laufzeit_s', 0):.0f} s |")


def summen(faelle: list) -> dict:
    s = {"faelle": len(faelle), "endzustand_ok": 0, "pruefungen": 0,
         "pruefungen_ok": 0, "belegt": 0, "vermutung": 0, "unbelegt": 0,
         "falsch": 0, "werkzeug_aufrufe": 0, "werkzeug_fehler": 0,
         "unnoetige_aufrufe": 0, "handelt_ohne_antwort": 0,
         "rueckfragen_ok": 0, "rueckfragen": 0, "kosten_ki_eur": 0.0,
         "kosten_richter_eur": 0.0, "laufzeit_s": 0.0}
    for f in faelle:
        ez = f.get("endzustand") or []
        s["pruefungen"] += len(ez)
        s["pruefungen_ok"] += sum(1 for e in ez if e["ok"])
        s["endzustand_ok"] += 1 if ez and all(e["ok"] for e in ez) else 0
        z = (f.get("richter") or {}).get("zaehlung") or {}
        for k in ("belegt", "vermutung", "unbelegt", "falsch"):
            s[k] += z.get(k, 0)
        m = f.get("metriken") or {}
        for k in ("werkzeug_aufrufe", "werkzeug_fehler", "unnoetige_aufrufe"):
            s[k] += m.get(k, 0) or 0
        s["handelt_ohne_antwort"] += len(m.get("handelt_ohne_antwort") or [])
        rf = m.get("rueckfragen") or []
        s["rueckfragen"] += len(rf)
        s["rueckfragen_ok"] += sum(1 for r in rf if r["ok"])
        s["kosten_ki_eur"] += f.get("kosten_eur") or 0
        s["kosten_richter_eur"] += f.get("richter_kosten_eur") or 0
        s["laufzeit_s"] += f.get("laufzeit_s") or 0
    s["kosten_gesamt_eur"] = round(s["kosten_ki_eur"] + s["kosten_richter_eur"], 4)
    s["kosten_ki_eur"] = round(s["kosten_ki_eur"], 4)
    s["kosten_richter_eur"] = round(s["kosten_richter_eur"], 4)
    s["laufzeit_s"] = round(s["laufzeit_s"], 1)
    return s


def _fall_abschnitt(f: dict) -> list:
    m = f.get("metriken") or {}
    z = [f"## {f['id']} — {f.get('titel', '')}", ""]
    if f.get("absturz"):
        z += [f"**Lauf abgestürzt:** `{f['absturz']}`", ""]
    z += ["**Endzustand**", ""]
    for e in f.get("endzustand") or []:
        z.append(f"- {'✓' if e['ok'] else '✗'} {e['was']}"
                 + (f" — {e['grund']}" if e.get("grund") else ""))
    z.append("")
    r = f.get("richter") or {}
    z += [f"**Belege** (Richter: {r.get('modell') or '—'})", ""]
    if r.get("fehler"):
        z += [f"- ⚠ {r['fehler']}", ""]
    if r.get("behauptungen"):
        z += ["| Zug | Urteil | Behauptung | Beleg / Grund |", "|---|---|---|---|"]
        reihenfolge = {"falsch": 0, "unbelegt": 1, "vermutung": 2, "belegt": 3}
        for b in sorted(r["behauptungen"],
                        key=lambda b: (reihenfolge.get(b["urteil"], 9), b.get("zug") or 0)):
            beleg = (f"{b['quelle']}: „{b['zitat']}“" if b.get("zitat") else "")
            grund = " ".join(x for x in (beleg, b.get("begruendung", ""),
                                         f"[{b['vermerk']}]" if b.get("vermerk") else "") if x)
            wort = b.get("wortlaut") or b.get("behauptung")
            z.append(f"| {b.get('zug')} | {ZEICHEN.get(b['urteil'], '')} {b['urteil']} | "
                     f"{_zelle(wort)} | {_zelle(grund)} |")
        z.append("")
    elif not r.get("fehler"):
        z += ["- keine Behauptungen", ""]
    z += ["**Metriken**", "",
          f"- Werkzeug-Aufrufe: {m.get('werkzeug_aufrufe', 0)} "
          f"(schreibend {m.get('schreibende_aufrufe', 0)}), Fehler: {m.get('werkzeug_fehler', 0)}, "
          f"ins Leere: {m.get('ins_leere', 0)}",
          f"- Erlaubnis-Fragen: {m.get('erlaubnis_fragen', 0)}, Knopf-Fragen: {m.get('knopf_fragen', 0)}"]
    for k, text in (("loeschen_und_neu", "Löschen + neu statt ändern"),
                    ("doppelte_aufrufe", "Doppelte Aufrufe"),
                    ("handelt_ohne_antwort", "Handelt nach Frage ohne Antwort"),
                    ("schleifen_fehler", "Fehler der Schleife")):
        if m.get(k):
            z.append(f"- {text}: " + "; ".join(m[k]))
    for rf in m.get("rueckfragen") or []:
        z.append(f"- Zug {rf['zug']}: Rückfrage {'erwartet' if rf['erwartet'] else 'nicht nötig'}, "
                 f"{'gestellt' if rf['gestellt'] else 'nicht gestellt'} {'✓' if rf['ok'] else '✗'}")
    z += [f"- Kosten: KI {_eur(f.get('kosten_eur'))}, Richter {_eur(f.get('richter_kosten_eur'))}; "
          f"Laufzeit {f.get('laufzeit_s', 0):.0f} s; Modell {', '.join(f.get('modelle') or []) or '—'}",
          f"- Transkript: [transkripte/{f['id']}.md](transkripte/{f['id']}.md)", ""]
    return z


def _zelle(s) -> str:
    return " ".join(str(s or "").split()).replace("|", "\\|")[:400]


def markdown(durchgang: dict) -> str:
    s = durchgang["summen"]
    z = [f"# Prüfstand — Durchgang {durchgang['zeit']}", "",
         f"Code: `{durchgang.get('code')}` · Modell: {', '.join(durchgang.get('modelle') or []) or '—'}"
         f" · Richter: {durchgang.get('richter') or '—'}", "",
         f"**Kosten:** KI {_eur(s['kosten_ki_eur'])} + Richter {_eur(s['kosten_richter_eur'])}"
         f" = **{_eur(s['kosten_gesamt_eur'])}** · Laufzeit {s['laufzeit_s']:.0f} s", "",
         f"**Isolation:** {durchgang.get('isolation', '—')}", "",
         "## Übersicht", "",
         f"- Endzustand: **{s['endzustand_ok']}/{s['faelle']} Fälle ganz richtig** "
         f"({s['pruefungen_ok']}/{s['pruefungen']} Einzelprüfungen)",
         f"- Behauptungen: {s['belegt']} belegt, {s['vermutung']} als Vermutung, "
         f"**{s['unbelegt']} unbelegt, {s['falsch']} falsch**",
         f"- Werkzeug-Aufrufe {s['werkzeug_aufrufe']}, Fehler {s['werkzeug_fehler']}, "
         f"unnötig {s['unnoetige_aufrufe']}, handelt ohne Antwort {s['handelt_ohne_antwort']}, "
         f"Rückfragen richtig {s['rueckfragen_ok']}/{s['rueckfragen']}", "",
         "| Fall | Endzustand | Belege ✓/~/?/✗ | Aufrufe | Fehler | unnötig | ohne Antwort "
         "| Rückfrage | Kosten | Zeit |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    offen = [f for f in durchgang["faelle"] if not f.get("verdeckt")]
    verdeckt = [f for f in durchgang["faelle"] if f.get("verdeckt")]
    z += [uebersicht_zeile(f) for f in offen + verdeckt]
    z += ["", "✓ belegt · ~ Vermutung · ? unbelegt · ✗ falsch. Fehler = unbelegt + falsch.", ""]
    for f in offen:
        z += _fall_abschnitt(f)
    if verdeckt:
        z += ["## Verdeckte Fälle", "",
              "Nur die Zahlen oben. Die Einzelheiten liegen unter `verdeckt/` — "
              "nicht ansehen, solange an Werkzeugen und Prompt gebaut wird "
              "(sonst misst der Fall die Anpassung, nicht die Verbesserung).", ""]
    return "\n".join(z)


def transkript(f: dict) -> str:
    z = [f"# Transkript {f['id']} — {f.get('titel', '')}", "",
         f"Zeitpunkt des Falls: {f.get('jetzt') or 'echt'}", "",
         "## Kalender vorher", "", "```", f.get("kalender_vorher", ""), "```", ""]
    for zi, zug in enumerate(f.get("zuege", []), 1):
        z += [f"## Zug {zi}", "", f"**Sasha:** {zug['sagt']}", ""]
        if zug.get("kontext"):
            z += ["<details><summary>Kontext der KI (Datum, heute/morgen, Erinnerungen)</summary>",
                  "", "```", zug["kontext"], "```", "</details>", ""]
        if zug.get("denken"):
            z += ["<details><summary>Denken</summary>", "", zug["denken"], "</details>", ""]
        for wi, w in enumerate(zug.get("werkzeuge", []), 1):
            args = json.dumps(w.get("args") or {}, ensure_ascii=False)
            z.append(f"**T{zi}.{wi}** `{w.get('name')}` {args}")
            if w.get("frage"):
                fr = w["frage"]
                z.append(f"> Frage an Sasha ({fr['art']}): {fr.get('frage')} "
                         f"{fr.get('optionen')} → Skript antwortet: **{fr.get('antwort')!r}**")
            z += ["```", str(w.get("ergebnis")), "```", ""]
        for fe in zug.get("fehler", []):
            z += [f"**Fehler:** {fe}", ""]
        z += [f"**KI:** {zug.get('antwort') or '(keine Antwort)'}", "",
              f"_{zug.get('laufzeit_s', 0)} s, {_eur(zug.get('kosten_eur'))}_", "",
              "<details><summary>Kalender danach (Prüfer-Sicht)</summary>", "", "```",
              zug.get("kalender_danach", ""), "```", "</details>", ""]
    return "\n".join(z)


def schreiben(durchgang: dict, ordner: str) -> str:
    """Bericht, JSON und Transkripte ablegen. -> Pfad des Berichts."""
    os.makedirs(os.path.join(ordner, "transkripte"), exist_ok=True)
    for f in durchgang["faelle"]:
        unter = os.path.join(ordner, "verdeckt") if f.get("verdeckt") else \
            os.path.join(ordner, "transkripte")
        os.makedirs(unter, exist_ok=True)
        with open(os.path.join(unter, f"{f['id']}.md"), "w", encoding="utf-8") as d:
            d.write(transkript(f))
        if f.get("verdeckt"):
            with open(os.path.join(unter, f"{f['id']}_bericht.md"), "w", encoding="utf-8") as d:
                d.write("\n".join(_fall_abschnitt(f)))
    with open(os.path.join(ordner, "ergebnis.json"), "w", encoding="utf-8") as d:
        json.dump(durchgang, d, ensure_ascii=False, indent=1, default=str)
    pfad = os.path.join(ordner, "bericht.md")
    with open(pfad, "w", encoding="utf-8") as d:
        d.write(markdown(durchgang))
    return pfad


def vergleich(a: dict, b: dict, name_a: str, name_b: str) -> str:
    """Zwei Durchgänge nebeneinander (gleiche Fälle)."""
    sa, sb = a["summen"], b["summen"]
    z = [f"# Vergleich: `{name_a}` gegen `{name_b}`", "",
         "| | " + name_a + " | " + name_b + " |", "|---|---|---|"]
    for k, text in (("endzustand_ok", "Fälle ganz richtig"),
                    ("pruefungen_ok", "Einzelprüfungen richtig"),
                    ("unbelegt", "unbelegte Behauptungen"),
                    ("falsch", "falsche Behauptungen"),
                    ("belegt", "belegte Behauptungen"),
                    ("werkzeug_aufrufe", "Werkzeug-Aufrufe"),
                    ("werkzeug_fehler", "Werkzeug-Fehler"),
                    ("unnoetige_aufrufe", "unnötige Aufrufe"),
                    ("handelt_ohne_antwort", "handelt ohne Antwort"),
                    ("rueckfragen_ok", "Rückfragen richtig"),
                    ("kosten_gesamt_eur", "Kosten €"),
                    ("laufzeit_s", "Laufzeit s")):
        z.append(f"| {text} | {sa.get(k)} | {sb.get(k)} |")
    z += ["", "| Fall | Endzustand | Belege ✓/~/?/✗ |", "|---|---|---|"]
    fb = {f["id"]: f for f in b["faelle"]}
    for f in a["faelle"]:
        g = fb.get(f["id"], {})
        z.append(f"| {f['id']} | {_endzustand_kurz(f)} → {_endzustand_kurz(g) if g else '—'} | "
                 f"{_belege_kurz(f)} → {_belege_kurz(g) if g else '—'} |")
    return "\n".join(z) + "\n"
