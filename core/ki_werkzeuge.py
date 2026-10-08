# core/ki_werkzeuge.py
#
# Was ein KI-Werkzeug TUT: der Aufruf `ausfuehren(name, args)` und die
# Verteilung auf Kalender, Notizen, Netz, Mail, News, Messreihen. Die
# Werkzeuge laufen IMMER lokal, egal welches Modell denkt — jeder Weg (lokal,
# Anthropic, OpenAI) ruft dieselbe Funktion.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Bis 2026-10-06 in
# core/ai.py; die Cloud-Wege importierten dafür den lokalen Weg — Knoten im
# Import-Kreis. Welche Werkzeuge es gibt, wie sie beschrieben sind und ob sie
# bestätigt werden, steht im Werkzeug-Register (core/werkzeug_register.py);
# jede Funktion hier meldet sich dort mit @ausfuehrer("name") an. Wie die
# Schleife mit terminalen Werkzeugen umgeht: werkzeug_schleife.run_tool.
# Aufbau: memory/ki/kern_aufbau.md.
#
# Wer in einem Test oder Skript die Ausführung abklemmen will, ersetzt
# ki_werkzeuge.ausfuehren — nicht die Durchreiche ai._execute_tool, die nur
# noch zum Aufrufen da ist.

import json as _json
import datetime as _dt
import os as _os

import ablage
import chat_suche
import context
import gedaechtnis
import gespraeche
import kalender
import ki_kalender
import ki_kalender_aendern
import ki_prompt
import mail
import news
import projekte
import sandbox
import skills
import web
import werkzeug_register
import zug
from werkzeug_befund import Befund, OK, FEHLGESCHLAGEN, status_von


def ausfuehren(name: str, args: dict, *, projekt=None) -> str:
    """
    Führt ein Tool aus und gibt das Ergebnis als String zurück.
    Der String wird als 'tool'-Nachricht zurück an das Modell geschickt.

    Jeder Tool-Call wird streng ans Dashboard-Terminal geloggt - sowohl
    die Anfrage (mit Args) als auch das Ergebnis. Damit kann man im UI
    live mitlesen wann die KI WIRKLICH ein Tool ruft. Wichtig weil
    LLMs sonst gerne behaupten "ich speichere das ab", ohne den Tool-
    Call tatsächlich abzusetzen - dieses Log macht den Unterschied
    sichtbar zwischen "AI hat es getan" und "AI hat es behauptet".

    projekt: id des Projekts, zu dem das laufende Gespräch gehört (Phase 6,
    2026-10-07). Nur Ausführer mit @braucht_projekt bekommen es — als
    Argument von hier, nie aus den Argumenten des Modells.
    """
    import state  # state.push_log feuert ins UI-Terminal
    try:
        args_str = _json.dumps(args, ensure_ascii=False)
    except Exception:
        args_str = str(args)
    # Args kürzen damit das Terminal nicht zugemüllt wird
    state.push_log(f"AI →  TOOL {name}({args_str[:200]})")

    try:
        result = _verteilen(name, args, projekt=projekt)
    except Exception as e:
        state.push_log(f"AI ✗  TOOL {name} FEHLER: {e}")
        raise

    # Ergebnis auch loggen (gekürzt, sonst Spam bei großen read_file-Treffern)
    result_str = result if isinstance(result, str) else str(result)
    state.push_log(f"AI ←  TOOL {name} → {result_str[:160]}")
    return result_str


def _verteilen(name: str, args: dict, projekt=None) -> str:
    """
    Reine Tool-Logik ohne Logging - wird von ausfuehren umschlossen.

    Welche Funktion zu einem Namen gehört, steht im Werkzeug-Register (seit
    2026-10-07; vorher eine if-Kette hier). Der Name darf in jeder
    Schreibweise kommen: welche Schiene ihr Tool wie nennt, ist ihre Sache,
    deshalb laufen auch die Bench-Skripte mit den alten deutschen Namen
    unveraendert weiter.
    """
    w = werkzeug_register.eintrag(name)
    if w is None or w.ausfuehrer is None:
        return f"[Unbekanntes Tool: {werkzeug_register.kanonisch(name)}]"
    if getattr(w.ausfuehrer, "braucht_projekt", False):
        return w.ausfuehrer(args, projekt=projekt)
    return w.ausfuehrer(args)


def braucht_projekt(fn):
    """Markiert einen Ausführer, der das Projekt des laufenden Gesprächs
    bekommt (Phase 6, 2026-10-07). Das Projekt kommt als Parameter von der
    Chat-Route über kern.chat und den Cloud-Weg (mit_projekt) — kein
    globaler Zustand, und das Modell kann es nicht per Argument auf ein
    anderes Projekt biegen."""
    fn.braucht_projekt = True
    return fn


def mit_projekt(projekt=None):
    """Der Ausführer für einen Zug: ohne Projekt `ausfuehren` selbst (so
    greift ein monkeypatch in Tests wie bisher), mit Projekt eine Hülle, die
    es mitgibt."""
    if not projekt:
        return ausfuehren

    def mit(name, args):
        return ausfuehren(name, args, projekt=projekt)
    return mit


# ── Die Ausführer ───────────────────────────────────────────────────────
#
# Jede Funktion meldet sich mit @ausfuehrer("name") im Register an. Ein neues
# Werkzeug: Eintrag in core/werkzeug_register.py, Funktion hier.

ausfuehrer = werkzeug_register.ausfuehrer


@ausfuehrer("read_file")
def _read_file(args: dict) -> str:
    return context.read_file(args.get("path", ""))


@ausfuehrer("list_files")
def _list_files(args: dict) -> str:
    files = context.list_available_files()
    return "Verfügbare Dateien:\n" + "\n".join(f"  {f}" for f in files)


# ── Kalender ──
# Seit 2026-10-08 in core/ki_kalender.py (Lesen, Kennungen, Belege) und
# core/ki_kalender_aendern.py (Schreiben): nach Sashas Testlauf lesen alle
# Schreib-Werkzeuge nach, was dasteht, und treffen nur noch EINEN Eintrag.

@ausfuehrer("read_calendar")
def _read_calendar(args: dict) -> str:
    return ki_kalender.lesen(args)


@ausfuehrer("read_calendar_warnings")
def _read_calendar_warnings(args: dict) -> str:
    return ki_kalender.warnungen_lesen(args)


@ausfuehrer("add_calendar_entry")
def _add_calendar_entry(args: dict) -> str:
    # Konflikt-Warnung passiert VOR dem Schreiben im Erlaubnis-Dialog
    # (Frage im Register → conflicts_for_proposed), damit Sasha informiert
    # JA/NEIN klickt. Hier der Beleg: was danach wirklich dasteht.
    return ki_kalender_aendern.termin_eintragen(args)


@ausfuehrer("read_time")
def _read_time(args: dict) -> str:
    from datetime import datetime as _datetime
    jetzt = _datetime.now()
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


@ausfuehrer("add_calendar_routine")
def _add_calendar_routine(args: dict) -> str:
    return ki_kalender_aendern.routine_eintragen(args)


@ausfuehrer("add_calendar_pause")
def _add_calendar_pause(args: dict) -> str:
    return ki_kalender_aendern.pause_eintragen(args)


@ausfuehrer("edit_calendar_routine")
def _edit_calendar_routine(args: dict) -> str:
    return ki_kalender_aendern.routine_aendern(args)


@ausfuehrer("delete_calendar_entry")
def _delete_calendar_entry(args: dict) -> str:
    return ki_kalender_aendern.termin_loeschen(args)


@ausfuehrer("edit_calendar_entry")
def _edit_calendar_entry(args: dict) -> str:
    return ki_kalender_aendern.termin_aendern(args)


@ausfuehrer("web_search")
def _web_search(args: dict) -> str:
    return web.suche(args.get("query", ""))


@ausfuehrer("fetch_url")
def _fetch_url(args: dict) -> str:
    return web.hole(args.get("url", ""))


@ausfuehrer("read_news")
def _read_news(args: dict) -> str:
    return news.lies(args.get("tage", 0))


@ausfuehrer("read_mail")
def _read_mail(args: dict) -> str:
    return mail.lies(args.get("modus", ""))


# ── Belege (2026-10-08) ──
# Jedes schreibende Werkzeug liest nach dem Schreiben nach, was dasteht
# (Feld `beweis` im Register; tests/test_werkzeug_belege.py prüft jedes).
# Steht es NICHT da, sagt das Ergebnis das — mit Status „fehlgeschlagen",
# statt dass die KI einen Erfolg meldet, den es nicht gab.

def _belegt(roh, beleg, fehlt: str = "es steht NICHT da") -> Befund:
    """roh: was der Dienst gemeldet hat. beleg: was nachgelesen wurde
    (None = nicht gefunden)."""
    if status_von(roh) == FEHLGESCHLAGEN:
        return Befund(str(roh), FEHLGESCHLAGEN)
    if beleg is None:
        return Befund(f"{roh}\nNachgelesen: {fehlt} — melde keinen Erfolg.",
                      FEHLGESCHLAGEN)
    return Befund(f"{roh}\nNachgelesen: {beleg}", OK, beleg=beleg)


def _eine_zeile(text: str, n: int = 60) -> str:
    """Die erste Zeile mit Inhalt, Leerraum zusammengefaltet, gekürzt."""
    for z in str(text or "").splitlines():
        z = " ".join(z.strip().lstrip("-").split())
        if z:
            return z[:n]
    return ""


def _steht_drin(text: str, inhalt: str, ort: str):
    """Beleg-Satz, wenn der Anfang von `text` in `inhalt` steht, sonst None."""
    probe = _eine_zeile(text)
    if probe and probe in " ".join(str(inhalt or "").split()):
        return f'steht {ort} („{probe}…“).'
    return None


# ── Gedächtnis: Notizen statt Tripel (siehe core/gedaechtnis.py) ──

@ausfuehrer("read_note")
def _read_note(args: dict) -> str:
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


@ausfuehrer("write_note")
def _write_note(args: dict) -> str:
    wie  = (args.get("name") or "").strip()
    text = args.get("text") or ""
    # 2026-10-08: mit herkunft ist es ein Import (Skill import-memory) —
    # zeilenweise, nur Neues, nie ins Tagebuch oder in Kataloge.
    if str(args.get("herkunft") or "").strip():
        roh = gedaechtnis.import_ergaenzen(wie, text, str(args["herkunft"]))
        lesen, ort = (lambda: gedaechtnis.dossier_lesen(wie)), f"in '{wie}'"
    elif wie.lower() in ("tagebuch", "diary", ""):
        roh = gedaechtnis.tagebuch_notieren(text)
        lesen, ort = gedaechtnis.tagebuch_lesen, "im Tagebuch von heute"
    elif wie.lower() in ("hausregeln", "regeln"):
        roh = gedaechtnis.regel_notieren(text)
        lesen, ort = gedaechtnis.hausregeln, "in den Hausregeln"
    else:
        roh = gedaechtnis.dossier_notieren(wie, text)
        lesen, ort = (lambda: gedaechtnis.dossier_lesen(wie)), f"in '{wie}'"
    return _belegt(roh, _steht_drin(text, lesen(), ort), f"der Text steht NICHT {ort}")


@ausfuehrer("rewrite_note")
def _rewrite_note(args: dict) -> str:
    wie, inhalt = args.get("name") or "", args.get("content") or ""
    roh = gedaechtnis.dossier_ersetzen(wie, inhalt)
    jetzt = gedaechtnis.dossier_lesen(wie)
    beleg = _steht_drin(inhalt, jetzt, f"in '{wie}'")
    if beleg:
        beleg += f" Das Dossier hat jetzt {len(jetzt)} Zeichen."
    return _belegt(roh, beleg, f"'{wie}' hat NICHT den neuen Inhalt")


@ausfuehrer("search_memory")
def _search_memory(args: dict) -> str:
    return gedaechtnis.suchen(args.get("query") or "")


@ausfuehrer("fetch_document")
def _fetch_document(args: dict) -> str:
    name = args.get("name") or ""
    roh = gedaechtnis.dokument_holen(args.get("url") or "", name)
    ort = "quellen/" + gedaechtnis.slug(name)
    jetzt = gedaechtnis.dossier_lesen(ort) if gedaechtnis.slug(name) else ""
    return _belegt(roh, f"{ort} hat {len(jetzt)} Zeichen." if jetzt else None,
                   f"in {ort} steht nichts")


# ── Messreihen ──

@ausfuehrer("create_series")
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
        return Befund(f"[Die Reihe {wie!r} gibt es schon — nichts angelegt.]",
                      FEHLGESCHLAGEN)
    try:
        graphs.create_graph(wie, gtype=(args.get("typ") or "number"),
                            unit=(args.get("einheit") or ""))
    except Exception as e:
        return f"[Anlegen fehlgeschlagen: {e}]"
    da = [g for g in graphs.list_graphs() if g.get("name", "").casefold() == wie.casefold()]
    beleg = (f"Messkurve {da[0].get('name')!r} steht in der Liste "
             f"(Typ {da[0].get('type')}).") if da else None
    return _belegt(f"Messreihe {wie!r} angelegt. Trag Werte mit log_series ein und "
                   f"verlink sie im Dossier der Sache.", beleg,
                   f"die Messkurve {wie!r} steht NICHT in der Liste")


@ausfuehrer("log_series")
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
    da = [e for e in graphs.read_values(g["id"])
          if isinstance(e, dict) and e.get("date") == tag]
    return _belegt(f"{g.get('name')} fuer {tag}: {wert} eingetragen.",
                   f"{g.get('name')} am {tag} = {da[-1].get('value')}." if da else None,
                   f"für {tag} steht kein Wert")


@ausfuehrer("run_code")
def _run_code(args: dict) -> str:
    """Ein Programm abgeschottet ausführen (core/sandbox.py). Das Ergebnis
    geht als Text ans Modell: Rückgabewert, Ausgabe, Fehler, neue Dateien.
    Der Pfad des Arbeitsordners auf Sashas Rechner geht NICHT mit — das
    Modell sieht ihn als /arbeit, mehr braucht es nicht."""
    code = str(args.get("code") or "")
    if not code.strip():
        return "[Fehler: kein Code angegeben]"
    sprache = (args.get("sprache") or "python").strip().lower()
    try:
        zeit = int(args.get("zeitlimit") or sandbox.ZEITLIMIT_STANDARD_S)
    except (TypeError, ValueError):
        zeit = sandbox.ZEITLIMIT_STANDARD_S
    # Arbeitsordner nach dem Gespräch benannt (Phase 5, 2026-10-07).
    lauf = sandbox.lauf_kennung(zug.gespraech())
    # Das Stopp-Signal des Zugs (2026-10-07): Stoppen in der TUI tötet den
    # laufenden Prozess sofort, nicht erst nach dem Zeitlimit. Über 2
    # Minuten hat das Gate schon mit der Dauer gefragt (Register:
    # nur_einmal); hier nur noch die harte Obergrenze.
    # Skill-Skripte (2026-10-07): der Ordner eines AKTIVEN Skills nur lesend
    # unter /skills/<name> — sonst nichts von Sasha.
    extra = {}
    if str(args.get("skill") or "").strip():
        skill_ordner, fehler = skills.skript_ordner(str(args["skill"]))
        if fehler:
            return fehler
        extra["skill_ordner"] = skill_ordner
    erg = sandbox.ausfuehren(code, sprache=sprache, lauf_id=lauf,
                             zeitlimit_s=max(1, min(zeit, sandbox.ZEITLIMIT_MAX_S)),
                             abbruch=zug.abbruch(), **extra)
    text = sandbox.als_text(erg)
    if erg.get("dateien_neu"):
        # Behalten nur auf Sashas Wunsch (2026-10-07), nicht als Einladung.
        text += (f"\nLauf: {lauf} — will Sasha eine Datei behalten: "
                 f"save_from_sandbox.")
    return text


# ── Skills (core/skills.py, Phase 4 2026-10-07) ──
# propose_skill und edit_skill sind im Register gegatet: diese Funktionen
# laufen erst nach Sashas Ja. Sagt er nein, meldet die Schleife das selbst.

@ausfuehrer("load_skill")
def _load_skill(args: dict) -> str:
    return skills.laden(args.get("name") or "", str(args.get("datei") or ""),
                        args.get("ab"))


@ausfuehrer("propose_skill")
def _propose_skill(args: dict) -> str:
    inhalt = str(args.get("inhalt") or "")
    roh = skills.vorschlagen(args.get("name") or "",
                             args.get("beschreibung") or "", inhalt)
    return _belegt(roh, _skill_beleg(args.get("name"), inhalt),
                   "die Anleitung lässt sich NICHT laden")


@ausfuehrer("edit_skill")
def _edit_skill(args: dict) -> str:
    inhalt = str(args.get("inhalt") or "")
    roh = skills.aendern(args.get("name") or "", inhalt)
    return _belegt(roh, _skill_beleg(args.get("name"), inhalt),
                   "die Anleitung hat NICHT den neuen Inhalt")


def _skill_beleg(name, inhalt: str):
    text = skills.laden(name or "")
    if not text or text.lstrip().startswith("[") or \
            _eine_zeile(inhalt) not in " ".join(text.split()):
        return None
    return f"die Anleitung '{gedaechtnis.slug(name)}' lässt sich laden ({len(text)} Zeichen)."


# ── Frühere Gespräche (core/chat_suche.py, Phase 3 2026-10-07) ──
# „Das laufende Gespräch" ist das aktive dieses Rechners: die Chat-Route
# setzt es vor jedem Zug (gespraeche.aktiv_setzen). Dessen Fenster hat die
# KI schon im Verlauf; die Suche liefert es nicht doppelt.

@ausfuehrer("search_chats")
def _search_chats(args: dict) -> str:
    # Optional nur in einem Projekt (Phase 6): Name oder id, wie Sasha es
    # nennt. Ein unbekanntes Projekt sagt das, statt still alles zu suchen.
    pid = None
    if str(args.get("projekt") or "").strip():
        pid = projekte.finden(args["projekt"])
        if pid is None:
            da = ", ".join(p["name"] for p in projekte.liste()) or "keine"
            return f"[Kein Projekt {args['projekt']!r}. Es gibt: {da}]"
    return chat_suche.suchen_text(str(args.get("query") or ""),
                                  aktiv=gespraeche.aktiv(), projekt=pid)


@ausfuehrer("read_chat")
def _read_chat(args: dict) -> str:
    return chat_suche.lesen_text(args.get("id") or "", str(args.get("query") or ""),
                                 args.get("anzahl") or chat_suche.LESEN_STANDARD)


# ── Ablage (core/ablage.py, Phase 5 2026-10-07) ──
# Ungegatet (Begründung im Register). Jedes neue Dokument und jede neue
# Fassung meldet sich über zug.melden bei der TUI: die Chat-Route schickt das
# als SSE-Event 'ablage', die TUI zeigt eine Zeile „▤ Titel".

def _ablage_melden(k: dict) -> None:
    zug.melden({"ablage": ablage.kurz(k)})


def _ablage_text(k: dict, was: str) -> Befund:
    text = (f'{was}: "{k.get("titel")}" (id {k["id"]}, Fassung {k.get("fassung")}). '
            f"Sasha sieht es als Eintrag im Chat; wiederhole den Inhalt nicht.")
    try:
        d = ablage.lesen(k["id"])
    except Exception:
        d = None
    beleg = None
    if d is not None and d["fassung"] == k.get("fassung"):
        groesse = (f"{len(d['inhalt'])} Zeichen" if d["inhalt"] is not None
                   else f"Bild, {d['bytes']} Bytes")
        beleg = f"liegt in der Ablage, Fassung {d['fassung']}, {groesse}."
    return _belegt(text, beleg, "das Dokument liegt NICHT in der Ablage")


@ausfuehrer("create_document")
def _create_document(args: dict) -> str:
    art = (args.get("art") or "markdown").strip().lower()
    if art not in ("markdown", "text", "code", "csv"):
        art = "markdown"
    try:
        k = ablage.anlegen(args.get("titel") or "", str(args.get("inhalt") or ""), art,
                           herkunft="ki", gespraech=zug.gespraech(),
                           sprache=args.get("sprache"))
    except ablage.Fehler as e:
        return f"[Nicht abgelegt: {e}]"
    _ablage_melden(k)
    return _ablage_text(k, "Abgelegt")


@ausfuehrer("read_document")
def _read_document(args: dict) -> str:
    try:
        d = ablage.lesen(str(args.get("id") or "").strip())
    except ablage.Unbekannt:
        return "[Kein Dokument mit dieser id in der Ablage.]"
    k = d["kopf"]
    if d["inhalt"] is None:
        return f'"{k.get("titel")}" ist ein Bild ({d["bytes"]} Bytes) — lesen geht nur bei Text.'
    return f'"{k.get("titel")}" ({k.get("art")}, Fassung {d["fassung"]}):\n' + d["inhalt"]


@ausfuehrer("update_document")
def _update_document(args: dict) -> str:
    try:
        k = ablage.neue_fassung(str(args.get("id") or "").strip(),
                                str(args.get("inhalt") or ""))
    except ablage.Unbekannt:
        return "[Kein Dokument mit dieser id in der Ablage.]"
    except ablage.Fehler as e:
        return f"[Nicht geändert: {e}]"
    _ablage_melden(k)
    return _ablage_text(k, "Neue Fassung abgelegt")


# Was aus einem Lauf höchstens in die Ablage darf (Text: 4 Bytes je Zeichen).
_SANDBOX_MAX_BYTES = max(ablage.BILD_MAX_BYTES, ablage.TEXT_MAX_ZEICHEN * 4)


@ausfuehrer("save_from_sandbox")
def _save_from_sandbox(args: dict) -> str:
    """Eine Datei aus einem run_code-Lauf in die Ablage. Nur aus Läufen
    DIESES Gesprächs (die Kennung beginnt mit seiner id), nur aus dem
    Arbeitsordner (sandbox.datei_lesen: kein Ausbruch, keine Verweise),
    Text oder Bild, mit Größengrenze."""
    lauf = str(args.get("lauf") or "").strip()
    datei = str(args.get("datei") or "").strip()
    gid = zug.gespraech()
    if gid and not lauf.startswith(sandbox.lauf_vorsatz(gid)):
        return "[Nicht abgelegt: dieser Lauf gehört nicht zu diesem Gespräch.]"
    try:
        roh = sandbox.datei_lesen(lauf, datei, _SANDBOX_MAX_BYTES)
    except ValueError as e:
        return f"[Nicht abgelegt: {e}]"
    name = _os.path.basename(datei)
    endung = _os.path.splitext(name)[1].lower()
    titel = str(args.get("titel") or "").strip() or name
    quelle = f"Sandbox-Lauf {lauf}: {datei}"
    try:
        if endung in ablage.BILD_ENDUNGEN:
            k = ablage.anlegen(titel, roh, "bild", herkunft="sandbox", gespraech=gid,
                               endung=endung, quelle=quelle)
        elif b"\x00" in roh[:8192]:
            return "[Nicht abgelegt: das ist weder Text noch ein Bild.]"
        else:
            art = {".md": "markdown", ".csv": "csv", ".txt": "text"}.get(endung, "code")
            k = ablage.anlegen(titel, roh, art, herkunft="sandbox", gespraech=gid,
                               endung=endung or ".txt", quelle=quelle)
    except ablage.Fehler as e:
        return f"[Nicht abgelegt: {e}]"
    _ablage_melden(k)
    return _ablage_text(k, "Abgelegt")
# ── Projekte (core/projekte.py, Phase 6 2026-10-07) ──
# Nur das Projekt des laufenden Gesprächs: `projekt` kommt von
# _verteilen (siehe braucht_projekt), nicht vom Modell. Ein Pfad im Namen
# führt nirgendwo hin — projekte.wissen_lesen sucht nur in der Liste.

@ausfuehrer("read_project_file")
@braucht_projekt
def _read_project_file(args: dict, projekt=None) -> str:
    if not projekt or not projekte.gibt_es(projekt):
        return ("[Dieses Gespräch gehört zu keinem Projekt — es gibt keine "
                "Projektdateien zu lesen.]")
    return projekte.wissen_lesen(projekt, str(args.get("name") or ""),
                                 args.get("ab") or 0)
