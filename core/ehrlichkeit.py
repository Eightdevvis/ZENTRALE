# core/ehrlichkeit.py
#
# Drei Live-Prüfer, die Ehrlichkeit durch Bauweise erzwingen — reines Python,
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
#                  1 und 2 → EINE Korrekturrunde, bevor Sasha die Antwort
#                  sieht. Dazu die Erledigt-Zeile, die Python allein aus dem
#                  Werkzeug-Protokoll schreibt (✓ geändert … · ✗ …).
#   3. Zusagen:    „trag ich gleich ein" wird als offener Punkt des Gesprächs
#                  gespeichert (core/zusagen.py) und steht in jedem folgenden
#                  Zug unsichtbar im Kontext-Umschlag, bis ein passendes
#                  Werkzeug lief, Sasha ablehnt oder nach N Zügen ohne Bezug.
#
# Warum Python statt einer Bitte im Prompt: „Erfolg meldest du erst nach dem
# Beleg" steht seit 08.10. im Prompt (Regel 2) — eine Bitte. Der Prüfstand
# zeigte danach weiter Absicht als Ergebnis. Was das Protokoll belegt, kann
# Python nachzählen; das Modell muss es nicht mehr selbst einhalten wollen.
#
# Einstellung `ehrlichkeit_pruefer` (ai_config.setting):
#   aus     nichts
#   melden  Erledigt-Zeile und Befunde im Gespräch/Log, aber KEINE
#           Korrekturrunde und kein Hinweis an die KI (zum Messen)
#   an      alles
# Nur die gross-Schiene; klein (lokales qwen) bleibt, wie es gemessen ist.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md): kennt das Werkzeug-
# Register; die Satzmuster stehen in ehrlichkeit_erkennen.py (Schicht 2),
# der Speicher der Zusagen in zusagen.py (Schicht 2).

import re

import ai_config
import ehrlichkeit_erkennen as erkennen
import werkzeug_register
import zusagen
import zug

AUS, MELDEN, AN = "aus", "melden", "an"
MODI = (AUS, MELDEN, AN)
# Standard nach der Messung vom 09.10.2026 (memory/ki/ehrlichkeit_live.md,
# „Falschtreffer"): an, weil die Erkennung über alle gespeicherten Gespräche
# und Prüfstand-Züge unter 5 % Falschtreffer blieb.
STANDARD = AN

# So viele Züge ohne Bezug, dann verfällt eine Zusage still.
VERFALL_STANDARD = 4


def modus() -> str:
    wert = str(ai_config.setting("ehrlichkeit_pruefer", STANDARD) or "").strip().lower()
    return wert if wert in MODI else STANDARD


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
    "web_search": "netz", "fetch_url": "netz",
    # Browser (2026-10-09): lesen gehört zum Netz, das Bild zur Ablage.
    "browser_open": "netz", "browser_click": "netz", "browser_type": "netz",
    "browser_find": "netz", "browser_read": "netz", "browser_back": "netz",
    "browser_screenshot": "ablage",
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
}

_KOPF = re.compile(r"^\[ergebnis: (\w+)\]")


def status_aus(text: str, ist_fehler: bool = False) -> str:
    """Der Status aus der Kopfzeile eines Werkzeug-Ergebnisses
    (werkzeug_befund.mit_kopf)."""
    m = _KOPF.match(str(text or ""))
    if m:
        return m.group(1)
    return "fehlgeschlagen" if ist_fehler else "ok"


def _schreibt(name: str) -> bool:
    w = werkzeug_register.eintrag(name)
    return bool(w and w.schreibt)


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
        return _schreibt(self.name)


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


def befunde(antwort: str, protokoll: list, *, bekannt_text: str = "",
            frueher: list = ()) -> list:
    """Was an einer Antwort nicht gedeckt ist. -> [{art, satz|kennung}]"""
    raus = []
    for tat in erkennen.taten(antwort):
        if not tat_belegt(tat, protokoll, frueher):
            raus.append({"art": "tat", "satz": tat.satz})
    if not suche_belegt(protokoll):
        for satz in erkennen.nicht_da(antwort):
            raus.append({"art": "nicht_da", "satz": satz})
    bekannt = set(erkennen.kennungen(bekannt_text))
    for s in protokoll:
        bekannt.update(erkennen.kennungen(s.text))
    for k in erkennen.unbekannte_kennungen(antwort, bekannt):
        raus.append({"art": "kennung", "kennung": "#" + k})
    return raus


_HINWEIS_AUF = ("<pruefung_automatisch>\n(ZENTRALE prüft jede Antwort, bevor Sasha sie "
                "sieht. Diesen Hinweis hat Sasha NICHT geschrieben, und deine Antwort "
                "eben hat er noch nicht gesehen.)")
_HINWEIS_ZU = "</pruefung_automatisch>"


def hinweis(befunde_: list) -> str:
    """Die Korrektur an die KI. Als eigene Nutzer-Nachricht hinter ihrer
    Antwort — nicht in einem Werkzeug-Ergebnis: Anweisungen dort behandelt
    Claude als fremde Daten (Anthropic, „Mitigate jailbreaks")."""
    zeilen = []
    for b in befunde_:
        if b["art"] == "tat":
            zeilen.append(f"- Du schreibst „{b['satz']}“ — in diesem Zug lief dafür kein "
                          f"passendes schreibendes Werkzeug mit [ergebnis: ok].")
        elif b["art"] == "nicht_da":
            zeilen.append(f"- Du sagst „{b['satz']}“ — also ‚nicht da', hast aber keine "
                          f"vollständige Suche gemacht. Such gezielt mit find_files/"
                          f"search_files oder sag, dass du es nicht weißt.")
        else:
            zeilen.append(f"- Die Kennung {b['kennung']} steht in keinem Werkzeug-Ergebnis "
                          f"und nirgends im Gespräch.")
    return "\n".join([
        _HINWEIS_AUF, *zeilen,
        "Entweder jetzt das Werkzeug aufrufen, oder die Antwort so neu schreiben, dass "
        "sie nur sagt, was belegt ist (was noch aussteht, als offen). Schreib die GANZE "
        "Antwort neu — Sasha sieht nur die neue. Kein Wort über diese Prüfung.",
        _HINWEIS_ZU])


# ── Der Prüfer eines Zugs ───────────────────────────────────────────────

class Pruefer:
    """Begleitet EINEN Zug durch die Werkzeug-Schleife (werkzeug_schleife.
    laufen, Parameter pruefer). Merkt die Werkzeug-Aufrufe, prüft die fertige
    Antwort und liefert am Ende das Ereignis {"ehrlichkeit": …}."""

    def __init__(self, modus_: str, *, gespraech=None, bekannt_text: str = "",
                 frueher: list = (), nutzer_text: str = ""):
        self.modus = modus_
        self.gespraech = gespraech
        self.bekannt_text = bekannt_text
        self.frueher = list(frueher)
        self.nutzer_text = nutzer_text
        self.protokoll = []
        self.korrigiert = False
        self.befunde = []

    def werkzeug(self, name: str, args: dict, text: str, ist_fehler: bool = False):
        self.protokoll.append(Schritt(werkzeug_register.kanonisch(name), args,
                                      status_aus(text, ist_fehler), str(text or "")))

    def nach_antwort(self, text: str, *, letzte_runde: bool) -> str | None:
        """Die fertige Antwort prüfen. -> Korrektur-Text für EINE weitere
        Runde, oder None (Antwort geht so raus). Nur einmal je Zug, nie in
        der letzten erlaubten Runde."""
        b = befunde(text, self.protokoll, bekannt_text=self.bekannt_text,
                    frueher=self.frueher)
        self.befunde = b
        if not b or self.modus != AN or self.korrigiert or letzte_runde:
            return None
        self.korrigiert = True
        self._log(f"PRÜFUNG ↺ Korrekturrunde: {len(b)} Befund(e)")
        return hinweis(b)

    def abschluss(self, text: str | None) -> dict | None:
        """Das Ereignis für die Route: Erledigt-Zeile, Befunde, offene
        Zusagen. text None: der Zug endete ohne Antwort (Fehler, Grenze).
        None, wenn es nichts zu sagen gibt (kein Schreiben, kein Befund,
        keine Zusage — der gewöhnliche Plauder-Zug bleibt ohne Zusatz)."""
        liste = erledigt_liste(self.protokoll)
        ereignis = {"erledigt": liste, "zeile": erledigt_zeile(liste)}
        if self.befunde:
            ereignis["befunde"] = self.befunde
            self._log(f"PRÜFUNG ✗ {len(self.befunde)} Befund(e) "
                      f"{'nach Korrektur' if self.korrigiert else '(nur gemeldet)'}")
        if self.korrigiert:
            ereignis["korrigiert"] = True
        bewegt = False
        if self.gespraech:
            offen, vorher = self._zusagen(text)
            bewegt = bool(offen or vorher)
            if self.modus == AN and bewegt:
                ereignis["offen"] = offen
        if not (liste or self.befunde or self.korrigiert or bewegt):
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
