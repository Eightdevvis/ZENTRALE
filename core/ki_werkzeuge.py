# core/ki_werkzeuge.py
#
# Was ein KI-Werkzeug TUT: der Aufruf `ausfuehren(name, args)` und die
# Verteilung auf Kalender, Notizen, Netz, Mail, News, Messreihen. Die
# Werkzeuge laufen IMMER lokal, egal welches Modell denkt — jeder Weg (lokal,
# Anthropic, OpenAI) ruft dieselbe Funktion.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 in
# core/ai.py; die Cloud-Wege importierten dafür den lokalen Weg — Knoten im
# Import-Kreis. Was ein Werkzeug BEDEUTET (terminal? bestätigen?), steht in
# werkzeug_schleife.run_tool und erlaubnis.py; welche es gibt und wie sie
# beschrieben sind, in core/profil/. Aufbau: memory/ki/kern_aufbau.md.
#
# Wer in einem Test oder Skript die Ausführung abklemmen will, ersetzt
# ki_werkzeuge.ausfuehren — nicht die Durchreiche ai._execute_tool, die nur
# noch zum Aufrufen da ist.

import json as _json
import datetime as _dt

import context
import kalender
import ki_prompt
import mail
import news
import profil
import web


def _kalender_beweis(tag: str, label: str) -> str:
    """Nachlesen, was an dem Tag jetzt WIRKLICH steht. -> ein Satz.

    Der Nachpruef-Schritt im Code statt in einer zweiten Modell-Runde
    (Sasha, 20.08.2026: "kosten niedrig wie moeglich aber nich auf kosten
    von qualitaet"). Das Tool-Ergebnis geht ohnehin ans Modell zurueck —
    steht dort der Beweis statt "OK, eingetragen", hat sie nachgesehen,
    ohne dass ein Aufruf mehr anfaellt.

    Wichtig ist der Fall, in dem der Beweis NICHT aufgeht: dann steht das
    ausdruecklich da, statt dass sie einen Erfolg meldet.
    """
    try:
        from datetime import date as _date
        tage = kalender.entries_in_range(_date.fromisoformat(tag),
                                         _date.fromisoformat(tag))
    except Exception:
        return "OK, eingetragen."
    eintraege = tage.get(tag) or []
    treffer = [e for e in eintraege
               if (label or "").lower() in (e.get("label") or "").lower()]
    if not treffer:
        return ("[Eingetragen gemeldet, aber am %s steht es NICHT — sag "
                "das, statt einen Erfolg zu melden.]" % tag)
    wann = treffer[0].get("time") or "ganztags"
    return ("Steht jetzt am %s: %s (%s). Der Tag hat %d %s."
            % (tag, treffer[0].get("label"), wann, len(eintraege),
               "Eintrag" if len(eintraege) == 1 else "Eintraege"))


def ausfuehren(name: str, args: dict) -> str:
    """
    Führt ein Tool aus und gibt das Ergebnis als String zurück.
    Der String wird als 'tool'-Nachricht zurück an das Modell geschickt.

    Jeder Tool-Call wird streng ans Dashboard-Terminal geloggt - sowohl
    die Anfrage (mit Args) als auch das Ergebnis. Damit kann man im UI
    live mitlesen wann die KI WIRKLICH ein Tool ruft. Wichtig weil
    LLMs sonst gerne behaupten "ich speichere das ab", ohne den Tool-
    Call tatsächlich abzusetzen - dieses Log macht den Unterschied
    sichtbar zwischen "AI hat es getan" und "AI hat es behauptet".
    """
    import state  # state.push_log feuert ins UI-Terminal
    try:
        args_str = _json.dumps(args, ensure_ascii=False)
    except Exception:
        args_str = str(args)
    # Args kürzen damit das Terminal nicht zugemüllt wird
    state.push_log(f"AI →  TOOL {name}({args_str[:200]})")

    try:
        result = _verteilen(name, args)
    except Exception as e:
        state.push_log(f"AI ✗  TOOL {name} FEHLER: {e}")
        raise

    # Ergebnis auch loggen (gekürzt, sonst Spam bei großen read_file-Treffern)
    result_str = result if isinstance(result, str) else str(result)
    state.push_log(f"AI ←  TOOL {name} → {result_str[:160]}")
    return result_str


def _verteilen(name: str, args: dict) -> str:
    """
    Reine Tool-Logik ohne Logging - wird von ausfuehren umschlossen.
    Hier neue Tools eintragen.

    Der Name wird zuerst auf das kanonische Vokabular gebracht: welche Schiene
    ihr Tool wie nennt, ist ihre Sache (siehe core/profil/). Die Uebersetzung
    nimmt beide Schreibweisen an, deshalb laufen auch die Bench-Skripte, die
    hier mit den alten deutschen Namen hereinkommen, unveraendert weiter.
    """
    name = profil.kanonisch(name)
    if name == "read_file":
        return context.read_file(args.get("path", ""))
    elif name == "list_files":
        files = context.list_available_files()
        return "Verfügbare Dateien:\n" + "\n".join(f"  {f}" for f in files)
    elif name == "read_calendar":
        from datetime import date as _date
        layers = args.get("layers") or None
        suche  = (args.get("suche") or "").strip() or None
        zeitraum = (args.get("zeitraum") or "").strip()
        has_dates = bool(args.get("start_date")) and bool(args.get("end_date"))
        if zeitraum:
            # Bevorzugt: relativer Bucket -> Python rechnet die Grenzen.
            rng = kalender.resolve_range(zeitraum)
            if rng is None:
                return (f"[Fehler: unbekannter zeitraum {zeitraum!r}. "
                        f"Erlaubt: {', '.join(kalender.RANGE_BUCKETS)} "
                        f"- oder start_date+end_date angeben.]")
            start, end = rng
        elif has_dates:
            # Explizite ISO-Daten (für krumme Spannen).
            try:
                start = _date.fromisoformat(args["start_date"])
                end   = _date.fromisoformat(args["end_date"])
            except ValueError as e:
                return (f"[Fehler: ungültiges start/end-Datum – {e}. "
                        f"Besser 'zeitraum' nutzen: {', '.join(kalender.RANGE_BUCKETS)}.]")
        else:
            # NICHTS angegeben -> nicht bestrafen, sinnvoll defaulten. "wann hab
            # ich X?" (mit suche) ist die natürlichste Formulierung und kommt oft
            # ganz ohne Zeitraum; ein Fehler hier schickt das Modell in eine
            # Korrektur-Schleife (es schreibt den Retry-Call dann als Roh-XML ins
            # Thinking, der verpufft -> leere Antwort). Also: mit suche weiter nach
            # vorn schauen (Quartal, fängt wiederkehrende Termine), sonst nahe Zukunft.
            start, end = kalender.resolve_range(
                "naechste_90_tage" if suche else "diese_und_naechste_woche")
        if start > end:                      # vertauschte Grenzen tolerieren
            start, end = end, start
        return kalender.render_range_for_tool(start, end, layers=layers, suche=suche)
    elif name == "add_calendar_entry":
        # Konflikt-Warnung passiert VOR dem Schreiben im Erlaubnis-Dialog
        # (erlaubnis.frage → conflicts_for_proposed), damit Sasha informiert
        # JA/NEIN klickt. Hier nach dem Schreiben nur noch schlicht quittieren -
        # kein erneuter Hinweis (sonst Doppel-Warnung).
        ok = kalender.add_entry(
            layer = args.get("layer", "termine"),
            day   = args.get("day", ""),
            label = args.get("label", ""),
            time  = args.get("time"),
        )
        if not ok:
            return "[Fehler: Layer existiert nicht oder Eingabe ungültig]"
        return _kalender_beweis(args.get("day", ""), args.get("label", ""))
    elif name == "read_time":
        from datetime import datetime as _dt
        jetzt = _dt.now()
        zeile = (f"Es ist {jetzt.strftime('%H:%M')} "
                 f"({ki_prompt._WEEKDAYS_DE[jetzt.weekday()]}, "
                 f"{jetzt.day}. {ki_prompt._MONTHS_DE[jetzt.month]} {jetzt.year}).")
        n = kalender.naechster_termin(jetzt)
        if not n:
            return zeile + " Danach steht heute und morgen nichts mehr an."
        std, rest = divmod(n["minuten"], 60)
        abstand = (f"{std} Std {rest} min" if std else f"{rest} min")
        wann = ("morgen " if n["morgen"] else "") + f"um {n['time']}"
        return (f"{zeile} Als Nächstes: {n['label']} {wann} — "
                f"in {abstand}.")
    elif name == "add_calendar_routine":
        ok = kalender.add_routine(
            layer     = args.get("layer", "routinen"),
            label     = args.get("label", ""),
            rrule_str = args.get("rrule", ""),
            time      = args.get("time"),
        )
        if not ok:
            return "[Fehler: Layer existiert nicht oder rrule ungültig]"
        gefunden = kalender.routine_finden(args.get("label", ""))
        if len(gefunden) > 1:
            # Sie hat gerade eine ZWEITE Regel gleichen Namens angelegt. Das
            # ist der Geigenstunden-Fall vom 18.08.2026 — er soll ihr im
            # Ergebnis auffallen, nicht Sasha drei Tage spaeter.
            zeiten = ", ".join((r.get("time") or "ganztags")
                               for _l, _i, r in gefunden)
            return (f"Eingetragen — ABER es gibt jetzt {len(gefunden)} Regeln "
                    f"namens '{args.get('label','')}' ({zeiten}). Wollte er "
                    f"eine AENDERN? Dann die alte mit edit_calendar_routine "
                    f"loeschen und das sagen.")
        return f"OK, Routine eingetragen: {args.get('label','')}."
    elif name == "add_calendar_pause":
        ok = kalender.add_pause(
            label = args.get("label", ""),
            von   = args.get("von", ""),
            bis   = args.get("bis", ""),
            grund = args.get("grund"),
        )
        return "OK, Pause eingetragen." if ok else "[Fehler: ungültige Datumsangabe]"
    elif name == "edit_calendar_routine":
        label  = (args.get("label") or "").strip()
        aktion = (args.get("aktion") or "").strip()
        if not label:
            return "[Fehler: label ist nötig.]"
        if aktion == "loeschen":
            n = kalender.routine_loeschen(label)
            if n == 0:
                return f"Keine Routine '{label}' gefunden - nichts gelöscht."
            return f"{n} Routine(n) '{label}' gelöscht."
        if aktion != "aendern":
            return "[Fehler: aktion muss 'aendern' oder 'loeschen' sein.]"
        felder = {k: args.get(k) for k in ("time", "ende", "ort", "rrule")
                  if args.get(k)}
        neu_titel = (args.get("neuer_titel") or "").strip() or None
        if not felder and not neu_titel:
            return "[Fehler: nichts zu ändern - gib an, was neu ist.]"
        n = kalender.routine_aendern(label, neues_label=neu_titel, **felder)
        if n == 0:
            return (f"Keine Routine '{label}' geändert - entweder nicht "
                    f"gefunden oder die Wiederholungs-Regel war ungültig.")
        return f"OK, {n} Routine(n) '{label}' geändert."
    elif name == "delete_calendar_entry":
        day   = (args.get("day") or "").strip()
        label = (args.get("label") or "").strip()
        layer = (args.get("layer") or "").strip() or None
        if not day or not label:
            return "[Fehler: day und label sind nötig zum Löschen.]"
        n = kalender.delete_entry(day, label, layer)
        if n == 0:
            return f"Kein Termin '{label}' am {day} gefunden - nichts gelöscht."
        return f"{n} Termin(e) '{label}' am {day} gelöscht."
    elif name == "web_search":
        return web.suche(args.get("query", ""))
    elif name == "fetch_url":
        return web.hole(args.get("url", ""))
    elif name == "read_news":
        return news.lies(args.get("tage", 0))
    elif name == "read_mail":
        return mail.lies(args.get("modus", ""))
    # ── Gedächtnis: Notizen statt Tripel (siehe core/gedaechtnis.py) ──
    elif name == "read_note":
        import gedaechtnis
        wie = (args.get("name") or "").strip()
        if wie.lower() in ("sasha", "steckbrief"):
            return gedaechtnis.steckbrief() or "[Steckbrief ist noch leer]"
        if wie.lower() in ("ziele", "goals"):
            return gedaechtnis.ziele() or "[Ziele sind noch leer]"
        if wie.lower() in ("hausregeln", "regeln"):
            return gedaechtnis.hausregeln() or "[Noch keine Hausregeln]"
        if wie.lower().startswith(("vorlage", "template")):
            # ueber vorlage() statt ueber die Datei: sie legt sie beim
            # ersten Zugriff an, damit ein frischer Rechner sofort eine hat.
            return gedaechtnis.vorlage(wie.split("/")[-1])
        if wie.lower() in ("tagebuch", "diary"):
            return gedaechtnis.tagebuch_lesen() or "[Heute noch nichts notiert]"
        inhalt = gedaechtnis.dossier_lesen(wie)
        if not inhalt:
            vorhanden = ", ".join(gedaechtnis.dossier_liste()) or "noch keine"
            return (f"[Kein Dossier {wie!r}. Vorhanden: {vorhanden}. "
                    f"Mit write_note legst du eins an.]")
        return inhalt
    elif name == "write_note":
        import gedaechtnis
        wie  = (args.get("name") or "").strip()
        text = args.get("text") or ""
        if wie.lower() in ("tagebuch", "diary", ""):
            return gedaechtnis.tagebuch_notieren(text)
        if wie.lower() in ("hausregeln", "regeln"):
            return gedaechtnis.regel_notieren(text)
        return gedaechtnis.dossier_notieren(wie, text)
    elif name == "rewrite_note":
        import gedaechtnis
        return gedaechtnis.dossier_ersetzen(args.get("name") or "",
                                            args.get("content") or "")
    elif name == "search_memory":
        import gedaechtnis
        return gedaechtnis.suchen(args.get("query") or "")
    elif name == "fetch_document":
        import gedaechtnis
        return gedaechtnis.dokument_holen(args.get("url") or "",
                                          args.get("name") or "")
    elif name == "create_series":
        return _create_series(args)
    elif name == "log_series":
        return _log_series(args)
    else:
        return f"[Unbekanntes Tool: {name}]"


def _create_series(args: dict) -> str:
    """Eine neue Messkurve anlegen (gegatet).

    Ohne Gate wuerde aus jedem Tippfehler eine weitere halbtote Reihe in
    Sashas Uebersicht — deshalb legt `log_series` nichts von selbst an und
    dieser Weg fragt einmal nach.
    """
    import graphs
    wie = (args.get("name") or "").strip()
    if not wie:
        return "[Fehler: kein Name]"
    if any(g.get("name", "").casefold() == wie.casefold()
           for g in graphs.list_graphs()):
        return f"[Die Reihe {wie!r} gibt es schon.]"
    try:
        graphs.create_graph(wie, gtype=(args.get("typ") or "number"),
                            unit=(args.get("einheit") or ""))
    except Exception as e:
        return f"[Anlegen fehlgeschlagen: {e}]"
    return (f"Messreihe {wie!r} angelegt. Trag Werte mit log_series ein und "
            f"verlink sie im Dossier der Sache.")


def _log_series(args: dict) -> str:
    """Einen Messwert ins Zyklus-Werkzeug schreiben (core/graphs.py).

    Der fuenfte Speicher: Schlaf, Stimmung, Trainingseinheiten, alles was
    ueber Monate eine KURVE ergeben soll. Bewusst NICHT im Gedaechtnis-
    Ordner — Zahlen ueber Zeit koennen die Zyklus-Graphen laengst, samt
    Anzeige in der TUI. Sie hier nochmal als Text abzulegen hiesse, zwei
    Wahrheiten ueber denselben Wert zu fuehren.

    Legt eine Reihe NICHT von selbst an: welche Kurven es gibt, ist Sashas
    Entscheidung, und eine KI, die bei jedem Tippfehler eine neue Reihe
    erzeugt, macht aus der Uebersicht eine Halde.
    """
    import graphs
    name = (args.get("series") or "").strip()
    wert = args.get("value")
    if not name:
        return "[Fehler: keine Reihe angegeben]"
    treffer = [g for g in graphs.list_graphs()
               if g.get("name", "").casefold() == name.casefold()
               or g.get("id") == name]
    if not treffer:
        da = ", ".join(g.get("name", "?") for g in graphs.list_graphs()) or "keine"
        return (f"[Keine Messreihe {name!r}. Vorhanden: {da}. "
                f"Neue Reihen legt Sasha selbst an.]")
    g = treffer[0]
    tag = (args.get("day") or "").strip() or _dt.date.today().isoformat()
    try:
        graphs.log_value(g["id"], tag, wert)
    except Exception as e:
        return f"[Fehler beim Eintragen: {e}]"
    return f"{g.get('name')} fuer {tag}: {wert} eingetragen."
