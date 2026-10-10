# core/ehrlichkeit.py
#
# Live-Prüfer, die Ehrlichkeit durch Bauweise erzwingen — reines Python,
# kein zweites Modell (2026-10-09, memory/ki/ehrlichkeit_live.md):
#
#   1. Kennungen:  nennt die Antwort eine Kalender-Kennung (#r3f9c), muss sie
#                  in einem Werkzeug-Ergebnis dieses Zugs oder im Gespräch
#                  stehen — sonst ist sie erfunden.
#   2. Tat/Wort:   „hab ich eingetragen" ohne ein Kalender-Werkzeug mit
#                  [ergebnis: ok] in DIESEM Zug ist eine Behauptung ohne Tat.
#   2b. Nicht da: „finde ich nicht / gibt es nicht" über eine Datei nur nach
#                  einer VOLLSTÄNDIGEN Suche ohne Treffer in diesem Zug
#                  (find_files/search_files, „Suche vollständig: 0 Treffer",
#                  oder read_file „nicht gefunden"; seit 2026-10-09).
#                  1, 2, 2b → Korrekturrunden, bis die Antwort die Prüfung
#                  besteht, höchstens `pruefer_runden` (5) je Zug. Besteht sie
#                  dann noch nicht, geht sie raus — mit Warnungen davor, die
#                  Python schreibt (Feld `warnungen`, nie im Text der KI).
#                  Dazu die Erledigt-Zeile, die Python allein aus dem
#                  Werkzeug-Protokoll schreibt (✓ geändert … · ✗ …).
#   2c. Frag nicht: endet die Antwort mit „Soll ich im Netz suchen?" o. ä.,
#                  obwohl Sasha gefragt/beauftragt hat und kein passendes
#                  Werkzeug lief → EINE Korrekturrunde „ruf das Werkzeug, das
#                  Gate fragt per Knopf" (seit 2026-10-10, Prüfstand f09;
#                  vorher nur im qwen-Zusatzprüfer). Keine Warnung danach.
#   2d. Aufschub:  „trag ich erst ein, wenn …", obwohl Sasha es klar
#                  beauftragt hat und kein passendes Werkzeug lief → EINE
#                  Runde „trag den sicheren Teil jetzt ein, frag nur das
#                  Fehlende" (2026-10-10, Prüfstand f01).
#   3. Zusagen:    „trag ich gleich ein" wird als offener Punkt des Gesprächs
#                  gespeichert (core/zusagen.py) und steht in jedem folgenden
#                  Zug unsichtbar im Kontext-Umschlag, bis ein passendes
#                  Werkzeug lief, Sasha ablehnt oder nach N Zügen ohne Bezug.
#
# Warum mehrere Runden statt einer (2026-10-09, Gespräch 20261009-150713):
# qwen im Budget-Rückfall schrieb „Alles korrigiert …" ohne ein Werkzeug und
# erfand vier Kennungen. Nach der EINEN Korrekturrunde strich es nur die
# Kennungen, log weiter — und die zweite Antwort ging ungeprüft raus.
#
# Warum Python statt einer Bitte im Prompt: „Erfolg meldest du erst nach dem
# Beleg" steht seit 08.10. im Prompt (Regel 2) — eine Bitte. Der Prüfstand
# zeigte danach weiter Absicht als Ergebnis. Was das Protokoll belegt, kann
# Python nachzählen; das Modell muss es nicht mehr selbst einhalten wollen.
#
# Einstellung `ehrlichkeit_pruefer` (ai_config.setting):
#   aus     nichts
#   melden  Erledigt-Zeile, Befunde und Warnungen im Gespräch/Log, aber
#           KEINE Korrekturrunde und kein Hinweis an die KI (zum Messen)
#   an      alles
# Nur die gross-Schiene; klein (lokales qwen) bleibt, wie es gemessen ist.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md): kennt das Werkzeug-
# Register; die Satzmuster stehen in ehrlichkeit_erkennen.py (Schicht 2),
# der Speicher der Zusagen in zusagen.py (Schicht 2).

import re

import ai_config
import ehrlichkeit_erkennen as erkennen
import input_aufraeumen
import werkzeug_register
import zusagen
import zug
import zug_ablauf

AUS, MELDEN, AN = "aus", "melden", "an"
MODI = (AUS, MELDEN, AN)
# Standard nach der Messung vom 09.10.2026 (memory/ki/ehrlichkeit_live.md,
# „Falschtreffer"): an, weil die Erkennung über alle gespeicherten Gespräche
# und Prüfstand-Züge unter 5 % Falschtreffer blieb.
STANDARD = AN

# So viele Züge ohne Bezug, dann verfällt eine Zusage still.
VERFALL_STANDARD = 4

# So viele Korrekturrunden höchstens je Zug (Sasha 2026-10-09: „prüfen was
# das zeug hält … wenn sie das nach 5x oder so immernoch nich tut, geht sie
# halt raus mit den warnungen"). Jede Runde ist ein Modell-Aufruf und zählt
# EINMAL gegen die Rundengrenze der Schleife (ai_backends.runden_grenze).
RUNDEN_STANDARD = 5
RUNDEN_HOECHSTENS = 20


def modus() -> str:
    wert = str(ai_config.setting("ehrlichkeit_pruefer", STANDARD) or "").strip().lower()
    return wert if wert in MODI else STANDARD


def pruefer_runden() -> int:
    """Höchstens so viele Korrekturrunden je Zug (Einstellung
    `pruefer_runden`). 0 heißt: prüfen und warnen, aber nie korrigieren."""
    try:
        n = int(ai_config.setting("pruefer_runden", RUNDEN_STANDARD))
    except (TypeError, ValueError):
        return RUNDEN_STANDARD
    return max(0, min(RUNDEN_HOECHSTENS, n))


def verfall_zuege() -> int:
    try:
        return max(1, int(ai_config.setting("zusagen_verfall", VERFALL_STANDARD)))
    except (TypeError, ValueError):
        return VERFALL_STANDARD


# ── Werkzeuge → Bereiche ────────────────────────────────────────────────
# Welcher Bereich (ehrlichkeit_erkennen.BEREICH_WOERTER) ein Werkzeug
# belegt. Ein schreibendes Werkzeug, das hier fehlt, belegt nur Sätze ohne
# erkennbaren Bereich — das ist die vorsichtige Seite (Test hält die Liste
# vollständig: tests/test_ehrlichkeit.py).
BEREICH = {
    "add_calendar_entry": "kalender", "add_calendar_routine": "kalender",
    "edit_calendar_routine": "kalender", "edit_calendar_entry": "kalender",
    "add_calendar_pause": "kalender", "delete_calendar_entry": "kalender",
    "read_calendar": "kalender", "read_calendar_warnings": "kalender",
    "write_note": "notiz", "rewrite_note": "notiz", "read_note": "notiz",
    "search_memory": "notiz",
    "fetch_document": "ablage", "create_document": "ablage",
    "update_document": "ablage", "save_from_sandbox": "ablage",
    "read_document": "ablage", "create_pdf": "ablage", "combine_pdf": "ablage",
    "create_docx": "ablage", "edit_docx": "ablage", "read_pdf": "ablage",
    "read_docx": "ablage", "read_file": "ablage",
    "create_series": "messreihe", "log_series": "messreihe",
    "propose_skill": "skill", "edit_skill": "skill", "load_skill": "skill",
    "import_skill": "skill",
    # Input/ (2026-10-09): Dateien auspacken und wegräumen gehören zur Ablage.
    "unzip": "ablage", "remove_input": "ablage",
    "web_search": "netz", "fetch_url": "netz",
    # Browser (2026-10-09): lesen gehört zum Netz, das Bild zur Ablage.
    "browser_open": "netz", "browser_click": "netz", "browser_type": "netz",
    "browser_find": "netz", "browser_read": "netz", "browser_back": "netz",
    "browser_screenshot": "ablage",
}

# Wie Sasha einen Bereich liest — für die Warnungen (2026-10-09). Eine
# Warn-Form für alles, was die KI kann; der Bereich kommt aus BEREICH bzw.
# den Bereichswörtern des Satzes, nicht aus einem Text je Werkzeug. Ein
# neuer Bereich braucht hier ein Wort (Test: tests/test_ehrlichkeit_runden.py).
BEREICH_NAMEN = {
    "kalender": "Kalender", "notiz": "Notizen/Gedächtnis", "ablage": "Ablage/Dateien",
    "messreihe": "Messreihen", "skill": "Skills", "netz": "Netz/Browser",
}

# Für die Erledigt-Zeile: (geklappt, versucht). Sasha liest das — Alltagswörter.
WORTE = {
    "add_calendar_entry": ("Termin eingetragen", "Termin eintragen"),
    "add_calendar_routine": ("Routine eingetragen", "Routine eintragen"),
    "edit_calendar_routine": ("Routine geändert", "Routine ändern"),
    "edit_calendar_entry": ("Termin geändert", "Termin ändern"),
    "add_calendar_pause": ("Pause eingetragen", "Pause eintragen"),
    "delete_calendar_entry": ("gelöscht", "Löschen"),
    "write_note": ("notiert", "Notieren"),
    "rewrite_note": ("Notiz neu geschrieben", "Notiz neu schreiben"),
    "fetch_document": ("in der Ablage", "Ablegen"),
    "create_document": ("Dokument angelegt", "Dokument anlegen"),
    "update_document": ("Dokument geändert", "Dokument ändern"),
    "save_from_sandbox": ("Datei abgelegt", "Datei ablegen"),
    "create_pdf": ("PDF angelegt", "PDF anlegen"),
    "combine_pdf": ("PDF zusammengefügt", "PDF zusammenfügen"),
    "create_docx": ("Word-Datei angelegt", "Word-Datei anlegen"),
    "edit_docx": ("Word-Kopie angelegt", "Word-Kopie anlegen"),
    "create_series": ("Messreihe angelegt", "Messreihe anlegen"),
    "log_series": ("Messwert eingetragen", "Messwert eintragen"),
    "propose_skill": ("Anleitung vorgeschlagen", "Anleitung vorschlagen"),
    "edit_skill": ("Anleitung geändert", "Anleitung ändern"),
    "browser_screenshot": ("Bild der Seite abgelegt", "Bild der Seite ablegen"),
    "import_skill": ("Skill übernommen", "Skill übernehmen"),
    "unzip": ("ausgepackt", "Auspacken"),
    "remove_input": ("in den Papierkorb gelegt", "In den Papierkorb legen"),
}

_KOPF = re.compile(r"^\[ergebnis: (\w+)\]")


def status_aus(text: str, ist_fehler: bool = False) -> str:
    """Der Status aus der Kopfzeile eines Werkzeug-Ergebnisses
    (werkzeug_befund.mit_kopf)."""
    m = _KOPF.match(str(text or ""))
    if m:
        return m.group(1)
    return "fehlgeschlagen" if ist_fehler else "ok"


def _schreibt(name: str, args: dict | None = None) -> bool:
    w = werkzeug_register.eintrag(name)
    if w and w.erlaubnis and callable(w.erlaubnis) and name in _NUR_MIT_GATE_SCHREIBEND:
        return bool(w.erlaubnis(args or {}))
    return bool(w and w.schreibt)


# Werkzeuge, die je nach Argument nur lesen (2026-10-09: unzip mit
# ansehen=true zeigt nur den Inhalt): schreibend ist ein Aufruf nur, wenn
# das Gate für ihn fragt. Sonst stünde „✓ ausgepackt" in der Erledigt-Zeile.
_NUR_MIT_GATE_SCHREIBEND = {"unzip"}


def _wen(args: dict) -> str:
    """Worum es ging, kurz: Titel, Name, Kennung — was das Werkzeug bekam."""
    for k in ("label", "titel", "title", "name", "datei", "kennung", "id"):
        v = (args or {}).get(k)
        if v:
            return " ".join(str(v).split())[:50]
    return ""


# ── Das Protokoll eines Zugs ────────────────────────────────────────────

class Schritt:
    __slots__ = ("name", "args", "status", "text")

    def __init__(self, name, args, status, text):
        self.name, self.args, self.status, self.text = name, args or {}, status, text

    @property
    def bereich(self):
        return BEREICH.get(self.name)

    @property
    def schreibt(self):
        return _schreibt(self.name, self.args)


def erledigt_liste(protokoll: list) -> list:
    """Die schreibenden Schritte eines Zugs, für die Erledigt-Zeile."""
    raus = []
    for s in protokoll:
        if not s.schreibt:
            continue
        raus.append({"werkzeug": s.name, "wen": _wen(s.args), "status": s.status})
    return raus


def erledigt_zeile(liste: list) -> str:
    """„✓ Termin eingetragen: Zahnarzt · ✗ Routine ändern ging nicht: Parkour".
    Steht als eigenes Feld am Gespräch, nie im Text der KI."""
    teile = []
    for e in liste:
        geklappt, versucht = WORTE.get(e["werkzeug"], (e["werkzeug"], e["werkzeug"]))
        wen = f": {e['wen']}" if e.get("wen") else ""
        st = e.get("status")
        if st == "ok":
            teile.append(f"✓ {geklappt}{wen}")
        elif st == "abgelehnt":
            teile.append(f"– {versucht}: von dir abgelehnt{wen}")
        else:
            teile.append(f"✗ {versucht} ging nicht{wen}")
    return " · ".join(teile)


# ── Prüfen ──────────────────────────────────────────────────────────────

def _passt(bereiche: set, schritt: Schritt) -> bool:
    return not bereiche or schritt.bereich in bereiche or schritt.bereich is None


def tat_belegt(tat, protokoll: list, frueher: list = ()) -> bool:
    """Ist eine Erledigt-Behauptung durch das Protokoll gedeckt?

    Ein schreibendes Werkzeug des passenden Bereichs mit Status ok.
    Bezieht sich der Satz auf früher („hab ich vorhin eingetragen"), reicht
    auch ein Lesen dieses Bereichs jetzt oder ein Schreiben früher im
    Gespräch."""
    for s in protokoll:
        if s.schreibt and s.status == "ok" and _passt(tat.bereiche, s):
            return True
    if tat.frueher:
        for s in protokoll:
            if s.status == "ok" and s.bereich and s.bereich in (tat.bereiche or {s.bereich}):
                return True
        for s in frueher:
            if s.schreibt and s.status == "ok" and _passt(tat.bereiche, s):
                return True
    return False


# Kopfzeile einer vollständigen Suche (core/nutzer_suche.py) und das, was
# read_file bei einem fehlenden Pfad sagt (core/context.py).
_SUCHE_LEER = re.compile(r"^Suche vollständig: 0 Treffer\b", re.M)
_SUCHEN = ("find_files", "search_files")


def suche_belegt(protokoll: list) -> bool:
    """Deckt eine Suche dieses Zugs ein „gibt es nicht"? Nur eine
    VOLLSTÄNDIGE ohne Treffer (find_files/search_files) oder read_file mit
    „nicht gefunden" (2026-10-09, Prüfer „nicht da")."""
    for s in protokoll:
        if s.name in _SUCHEN and _SUCHE_LEER.search(s.text):
            return True
        if s.name == "read_file" and "Datei nicht gefunden" in s.text:
            return True
    return False


# ── Frag nicht, tu (2026-10-10) ─────────────────────────────────────────
# Welche Werkzeuge eine Art Tat (ehrlichkeit_erkennen.aktion) erledigen, und
# wie der Hinweis sie nennt. None: jedes Werkzeug passender Richtung (lesend
# bzw. schreibend). Gilt für alle Modelle der gross-Schiene; vorher stand
# die Erlaubnis-Frage nur im qwen-Zusatzprüfer.
TATEN = {
    "netz": ({"web_search", "fetch_url", "fetch_document", "browser_open", "browser_click"},
             "web_search"),
    "seite": ({"fetch_url", "fetch_document", "browser_open", "browser_click", "browser_read",
               "browser_back", "browser_type"}, "fetch_url oder browser_open"),
    "nachsehen": (None, "das passende Werkzeug (read_calendar, read_note, web_search …)"),
    "pause": ({"add_calendar_pause"}, "add_calendar_pause"),
    "eintragen": ({"add_calendar_entry", "add_calendar_routine", "add_calendar_pause"},
                  "add_calendar_entry bzw. add_calendar_routine"),
    "loeschen": ({"delete_calendar_entry", "edit_calendar_routine"},
                 "delete_calendar_entry bzw. edit_calendar_routine"),
    "aendern": ({"edit_calendar_entry", "edit_calendar_routine"},
                "edit_calendar_entry bzw. edit_calendar_routine"),
    "notieren": ({"write_note", "rewrite_note"}, "write_note"),
    "tun": (None, "das passende Werkzeug"),
}

# Befunde, die höchstens EINE Korrekturrunde je Zug bekommen und nie als
# Warnung bei Sasha landen: die Antwort lügt nicht, sie zögert nur. Bleibt
# die KI nach dem Hinweis dabei, ist es vielleicht doch eine echte Rückfrage.
WEICH = ("erlaubnis_frage", "aufschub")


def tat_lief(art: str, schreibend: bool, protokoll: list) -> bool:
    """Lief in diesem Zug schon ein Werkzeug für diese Art Tat? Lesend: jeder
    Versuch zählt. Schreibend: ok, oder Sasha hat am Knopf abgelehnt."""
    namen = TATEN.get(art, (None, ""))[0]
    for s in protokoll:
        if namen is not None and s.name not in namen:
            continue
        if not schreibend:
            if namen is not None or not s.schreibt:
                return True
        elif s.schreibt and s.status in ("ok", "abgelehnt"):
            return True
    return False


def erlaubnis_befund(antwort: str, protokoll: list, nutzer_text: str) -> dict | None:
    """Bittet die Antwort im Text um Erlaubnis für etwas, das ein Werkzeug
    tun könnte — obwohl Sasha es verlangt oder gefragt hat?"""
    f = erkennen.erlaubnis_frage(antwort)
    if f is None:
        return None
    if f.schreibend:
        if not (erkennen.auftrag(nutzer_text) or erkennen.zustimmung(nutzer_text)):
            return None
    elif not (erkennen.will_wissen(nutzer_text) or erkennen.auftrag(nutzer_text)
              or erkennen.zustimmung(nutzer_text)):
        return None
    if tat_lief(f.aktion, f.schreibend, protokoll):
        return None
    return {"art": "erlaubnis_frage", "satz": f.satz, "werkzeug": TATEN[f.aktion][1]}


def aufschub_befund(antwort: str, protokoll: list, nutzer_text: str) -> dict | None:
    """Schiebt die Antwort eine von Sasha klar beauftragte Tat auf („trag ich
    erst ein, wenn …"), und in diesem Zug lief dafür kein Werkzeug?
    (2026-10-10, Prüfstand f01: Pause statt heute auf „irgendwann")."""
    if not erkennen.auftrag(nutzer_text):
        return None
    for a in erkennen.aufschuebe(antwort):
        if not tat_lief(a.aktion, True, protokoll):
            return {"art": "aufschub", "satz": a.satz, "aktion": a.aktion,
                    "werkzeug": TATEN[a.aktion][1]}
    return None


def befunde(antwort: str, protokoll: list, *, bekannt_text: str = "",
            frueher: list = (), nutzer_text: str = "") -> list:
    """Was an einer Antwort nicht gedeckt ist. -> [{art, satz|kennung}]"""
    raus = []
    for tat in erkennen.taten(antwort):
        if not tat_belegt(tat, protokoll, frueher):
            b = {"art": "tat", "satz": tat.satz}
            if tat.bereiche:
                b["bereiche"] = sorted(tat.bereiche)
            raus.append(b)
    if not suche_belegt(protokoll):
        for satz in erkennen.nicht_da(antwort):
            raus.append({"art": "nicht_da", "satz": satz})
    bekannt = set(erkennen.kennungen(bekannt_text))
    for s in protokoll:
        bekannt.update(erkennen.kennungen(s.text))
    for k in erkennen.unbekannte_kennungen(antwort, bekannt):
        raus.append({"art": "kennung", "kennung": "#" + k})
    for weich in (erlaubnis_befund(antwort, protokoll, nutzer_text),
                  aufschub_befund(antwort, protokoll, nutzer_text)):
        if weich:
            raus.append(weich)
    return raus


_HINWEIS_AUF = ("<pruefung_automatisch>\n(ZENTRALE prüft jede Antwort, bevor Sasha sie "
                "sieht. Diesen Hinweis hat Sasha NICHT geschrieben, und deine Antwort "
                "eben hat er noch nicht gesehen.)")
_HINWEIS_ZU = "</pruefung_automatisch>"


# Was die KI tun soll, wenn dieselbe Art Befund wiederkommt — je ART des
# Befunds, nicht je Bereich (2026-10-09).
_WIEDER = {
    "tat": "In diesem Zug lief kein passendes schreibendes Werkzeug. Ruf das Werkzeug "
           "jetzt auf ODER schreib, dass nichts geändert wurde.",
    "nicht_da": "Du hast in diesem Zug keine vollständige Suche gemacht. Such jetzt mit "
                "find_files/search_files ODER schreib, dass du es nicht weißt.",
    "kennung": "Nenn keine Kennung, die in keinem Werkzeug-Ergebnis steht — lass sie weg "
               "oder lies sie mit dem Werkzeug nach.",
}
KEIN_WERKZEUG = ("Du hast in diesem Zug KEIN Werkzeug aufgerufen. Ruf das Werkzeug jetzt "
                 "auf ODER schreib, dass nichts geändert wurde.")


def _befund_zeile(b: dict) -> str:
    if b["art"] == "tat":
        return (f"- Du schreibst „{b['satz']}“ — in diesem Zug lief dafür kein "
                f"passendes schreibendes Werkzeug mit [ergebnis: ok].")
    if b["art"] == "nicht_da":
        return (f"- Du sagst „{b['satz']}“ — also ‚nicht da', hast aber keine "
                f"vollständige Suche gemacht. Such gezielt mit find_files/"
                f"search_files oder sag, dass du es nicht weißt.")
    if b["art"] == "kennung":
        return (f"- Die Kennung {b['kennung']} steht in keinem Werkzeug-Ergebnis "
                f"und nirgends im Gespräch.")
    if b["art"] == "erlaubnis_frage":
        return (f"- Du fragst „{b['satz']}“ — frag nicht im Text um Erlaubnis: ruf "
                f"{b.get('werkzeug') or 'das Werkzeug'} auf; das Programm fragt Sasha per "
                f"Knopf, wenn nötig. Fehlt wirklich eine Angabe, frag genau danach — ohne "
                f"„soll ich“.")
    if b["art"] == "aufschub":
        beispiel = ("z. B. add_calendar_pause nur mit von = heute" if b.get("aktion") == "pause"
                    else f"z. B. {b.get('werkzeug') or 'das Werkzeug'} mit dem, was feststeht")
        return (f"- Du schreibst „{b['satz']}“ — Sasha hat das klar beauftragt. Trag den "
                f"sicheren Teil JETZT ein ({beispiel}) und frag nur nach dem, was wirklich "
                f"fehlt. Ist nichts davon sicher (Tag oder Uhrzeit fehlen), lass den "
                f"Aufschub weg und frag nur danach.")
    return f"- Nicht belegt: {b.get('satz') or b.get('art')}"


def hinweis(befunde_: list, *, runde: int = 1, runden: int = 1,
            wiederholt: tuple = (), werkzeug_lief: bool = True) -> str:
    """Die Korrektur an die KI. Als eigene Nutzer-Nachricht hinter ihrer
    Antwort — nicht in einem Werkzeug-Ergebnis: Anweisungen dort behandelt
    Claude als fremde Daten (Anthropic, „Mitigate jailbreaks").

    Nennt ALLE offenen Befunde. Ab der zweiten Runde wird er deutlicher:
    welche Runde, und für jede Art Befund, die wiederkommt, was jetzt zu tun
    ist (2026-10-09 — vorher kam nach einer Runde nichts mehr)."""
    zeilen = [_befund_zeile(b) for b in befunde_]
    if runde > 1:
        zeilen.append(f"Das ist Prüfrunde {runde} von {runden}: auch deine letzte Antwort "
                      f"hatte Stellen ohne Beleg.")
        for art in wiederholt:
            if art == "tat" and not werkzeug_lief:
                zeilen.append(KEIN_WERKZEUG)
            elif art in _WIEDER:
                zeilen.append(_WIEDER[art])
    if runde >= runden > 1:
        zeilen.append("Letzte Prüfrunde: hat die neue Antwort wieder Stellen ohne Beleg, "
                      "sieht Sasha sie mit einer Warnung davor.")
    return "\n".join([
        _HINWEIS_AUF, *zeilen,
        "Entweder jetzt das Werkzeug aufrufen, oder die Antwort so neu schreiben, dass "
        "sie nur sagt, was belegt ist (was noch aussteht, als offen). Schreib die GANZE "
        "Antwort neu — Sasha sieht nur die neue. Kein Wort über diese Prüfung.",
        _HINWEIS_ZU])


# ── Warnungen an Sasha ──────────────────────────────────────────────────
# Besteht eine Antwort die Prüfung nach allen Runden nicht, geht sie raus —
# mit diesen Zeilen davor (Feld `warnungen`, SSE, TUI in Warnfarbe). Eine
# Form für alle Bereiche; welcher Bereich, sagt BEREICH_NAMEN.

KEINE_AENDERUNG = "✗ keine Änderung in diesem Zug"


def _kurz(satz, n: int = 90) -> str:
    t = " ".join(str(satz or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def bereich_namen(bereiche) -> str:
    return ", ".join(BEREICH_NAMEN.get(b, b) for b in sorted(bereiche or ()))


def warnungen(befunde_: list, protokoll: list = ()) -> list:
    """Befunde → Sätze für Sasha. -> [str], jeder mit ⚠ vorn."""
    geschrieben = any(s.schreibt and s.status == "ok" for s in protokoll)
    raus, kennungen = [], []
    for b in befunde_ or []:
        art = b.get("art")
        if art in WEICH:           # Zögern ist keine Unwahrheit — keine Warnung
            continue
        if art == "tat":
            wo = bereich_namen(b.get("bereiche"))
            folge = ("dafür wurde nichts geändert" if geschrieben
                     else "es wurde nichts geändert")
            raus.append(f"⚠ Ohne Beleg: „{_kurz(b.get('satz'))}“ — in diesem Zug lief kein "
                        f"passendes Werkzeug{f' ({wo})' if wo else ''}, {folge}.")
        elif art == "nicht_da":
            raus.append(f"⚠ ‚Nicht da' ohne vollständige Suche: „{_kurz(b.get('satz'))}“ — "
                        f"es kann trotzdem da sein.")
        elif art == "kennung":
            kennungen.append(str(b.get("kennung")))
        else:
            raus.append(f"⚠ Ohne Beleg: „{_kurz(b.get('satz') or art)}“.")
    if len(kennungen) == 1:
        raus.append(f"⚠ Erfundene Kennung {kennungen[0]} — steht in keinem Werkzeug-Ergebnis.")
    elif kennungen:
        raus.append(f"⚠ Erfundene Kennungen {', '.join(kennungen)} — stehen in keinem "
                    f"Werkzeug-Ergebnis.")
    return raus


# ── Der Prüfer eines Zugs ───────────────────────────────────────────────

class Pruefer:
    """Begleitet EINEN Zug durch die Werkzeug-Schleife (werkzeug_schleife.
    laufen, Parameter pruefer). Merkt die Werkzeug-Aufrufe, prüft die fertige
    Antwort und liefert am Ende das Ereignis {"ehrlichkeit": …}."""

    def __init__(self, modus_: str, *, gespraech=None, bekannt_text: str = "",
                 frueher: list = (), nutzer_text: str = "", runden: int = None):
        self.modus = modus_
        self.gespraech = gespraech
        self.bekannt_text = bekannt_text
        self.frueher = list(frueher)
        self.nutzer_text = nutzer_text
        self.runden = pruefer_runden() if runden is None else max(0, int(runden))
        self.protokoll = []
        self.korrekturen = 0
        self.befunde = []
        self.gesehen = set()        # Arten von Befunden aus früheren Runden

    @property
    def korrigiert(self) -> bool:
        return self.korrekturen > 0

    def werkzeug(self, name: str, args: dict, text: str, ist_fehler: bool = False):
        self.protokoll.append(Schritt(werkzeug_register.kanonisch(name), args,
                                      status_aus(text, ist_fehler), str(text or "")))

    def nach_antwort(self, text: str, *, letzte_runde: bool) -> str | None:
        """Die fertige Antwort prüfen — nach JEDER Korrekturrunde wieder ganz
        (alle Prüfer). -> Korrektur-Text für eine weitere Runde, oder None:
        die Antwort geht so raus (bestanden, nicht „an", Runden aufgebraucht,
        oder die letzte erlaubte Runde der Schleife)."""
        b = befunde(text, self.protokoll, bekannt_text=self.bekannt_text,
                    frueher=self.frueher, nutzer_text=self.nutzer_text)
        self.befunde = b
        # Weiche Befunde (Erlaubnis-Frage, Aufschub) nur EINE Runde je Zug.
        b = [x for x in b if not (x["art"] in WEICH and x["art"] in self.gesehen)]
        if (not b or self.modus != AN or letzte_runde
                or self.korrekturen >= self.runden):
            return None
        self.korrekturen += 1
        arten = list(dict.fromkeys(x["art"] for x in b))
        wiederholt = tuple(a for a in arten if a in self.gesehen)
        self.gesehen.update(arten)
        self._log(f"PRÜFUNG ↺ Korrekturrunde {self.korrekturen}/{self.runden}: "
                  f"{len(b)} Befund(e)")
        return hinweis(b, runde=self.korrekturen, runden=self.runden,
                       wiederholt=wiederholt, werkzeug_lief=bool(self.protokoll))

    def abschluss(self, text: str | None) -> dict | None:
        """Das Ereignis für die Route: Erledigt-Zeile, Befunde, Warnungen,
        offene Zusagen. text None: der Zug endete ohne Antwort (Fehler,
        Grenze) — dann keine Warnungen, Sasha sieht ja keine Antwort.
        None, wenn es nichts zu sagen gibt (kein Schreiben, kein Befund,
        keine Zusage — der gewöhnliche Plauder-Zug bleibt ohne Zusatz)."""
        liste = erledigt_liste(self.protokoll)
        zeile = erledigt_zeile(liste)
        offen_b = self.befunde if text is not None else []
        if not liste and any(x["art"] == "tat" for x in offen_b):
            # Die Antwort behauptet Taten, aber kein schreibendes Werkzeug
            # lief: das steht jetzt ausdrücklich da (2026-10-09).
            zeile = KEINE_AENDERUNG
        ereignis = {"erledigt": liste, "zeile": zeile}
        if self.befunde:
            ereignis["befunde"] = self.befunde
            wie = (f"nach {self.korrekturen} Korrektur(en)" if self.korrigiert
                   else "(nur gemeldet)")
            self._log(f"PRÜFUNG ✗ {len(self.befunde)} Befund(e) {wie}")
        warn = warnungen(offen_b, self.protokoll)
        if warn:
            ereignis["warnungen"] = warn
            zug_ablauf.warnungen(warn)
        if self.korrigiert:
            ereignis["korrigiert"] = True
            ereignis["korrekturen"] = self.korrekturen
        bewegt = False
        if self.gespraech:
            offen, vorher = self._zusagen(text)
            bewegt = bool(offen or vorher)
            if self.modus == AN and bewegt:
                ereignis["offen"] = offen
        if not (liste or zeile or self.befunde or self.korrigiert or bewegt):
            return None
        return {"ehrlichkeit": ereignis}

    def _zusagen(self, text) -> tuple:
        """Alte Zusagen abhaken/verfallen lassen, neue merken.
        -> (offen danach [sätze], wie viele vorher offen waren)."""
        try:
            vorher = len(zusagen.offen(self.gespraech))
            nr = zusagen.zug_nummer(self.gespraech)
            zusagen.nachfuehren(self.gespraech, nr, self.protokoll,
                                nutzer_text=self.nutzer_text,
                                belegt=_zusage_belegt, verfall=verfall_zuege())
            if text:
                neu = [z for z in erkennen.versprechen(text)
                       if not _zusage_belegt(z.bereiche, self.protokoll, z.schreibend)]
                zusagen.hinzufuegen(self.gespraech, neu, nr)
            # Zusagen, die ein Werkzeug eintrug (Input aufräumen, 2026-10-09).
            input_aufraeumen.nachfuehren(self.gespraech, self.protokoll)
            return [z["satz"] for z in zusagen.offen(self.gespraech)], vorher
        except Exception as e:      # ein Prüfer darf den Zug nie kosten
            self._log(f"PRÜFUNG ✗ Zusagen: {e}")
            return [], 0

    def _log(self, zeile: str):
        try:
            import state
            state.push_log(zeile)
        except Exception:
            pass


def _zusage_belegt(bereiche: set, protokoll: list, schreibend: bool = True) -> bool:
    """Eine Zusage gilt als eingelöst, wenn ein Werkzeug ihres Bereichs ok
    lief — ein schreibendes; bei „schau ich nach" (schreibend False) auch
    ein lesendes."""
    bereiche = set(bereiche or ())
    for s in protokoll:
        if s.status != "ok":
            continue
        if schreibend and not s.schreibt:
            continue
        if not bereiche or (s.bereich and s.bereich in bereiche) or s.bereich is None:
            return True
    return False


def pruefer_fuer(verlauf: list, *, schiene: str, tutor_mode: bool,
                 kontext: str = "") -> Pruefer | None:
    """Den Prüfer für einen Zug — oder None (aus, klein, Tutor)."""
    if tutor_mode or schiene != "gross":
        return None
    m = modus()
    if m == AUS:
        return None
    gid = zug.gespraech()
    texte = [str(n.get("content") or "") for n in (verlauf or [])
             if isinstance(n.get("content"), str)]
    nutzer = next((str(n.get("content") or "") for n in reversed(verlauf or [])
                   if n.get("role") == "user"), "")
    return Pruefer(m, gespraech=gid, bekannt_text="\n".join(texte + [kontext]),
                   frueher=_frueher(gid), nutzer_text=nutzer)


def _frueher(gid) -> list:
    """Schreibende Schritte aus früheren Zügen des Gesprächs (gespeichert
    von der Route: name, args, ergebnis, status)."""
    if not gid:
        return []
    try:
        import gespraeche
        raus = []
        for n in gespraeche.nachrichten(gid, versteckte=True):
            for w in n.get("werkzeuge") or []:
                st = w.get("status") or ("fehlgeschlagen" if w.get("fehler") else "ok")
                raus.append(Schritt(werkzeug_register.kanonisch(w.get("name") or ""),
                                    {}, st, str(w.get("ergebnis") or "")))
        return raus
    except Exception:
        return []


def umschlag_block() -> str:
    """„Noch offen von dir zugesagt: …" für den Kontext-Umschlag
    (cloud._volatile_text). Leer, wenn nichts offen ist oder nicht an."""
    gid = zug.gespraech()
    if not gid or modus() != AN:
        return ""
    try:
        offen = zusagen.offen(gid)
    except Exception:
        return ""
    if not offen:
        return ""
    zeilen = [f"- „{z['satz']}“ (Zug {z['zug']})" for z in offen]
    return ("## Noch offen von dir zugesagt\n" + "\n".join(zeilen)
            + "\nEinlösen, oder Sasha sagen, dass es (noch) nicht geht.")
