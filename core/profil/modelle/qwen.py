# core/profil/modelle/qwen.py
#
# Das Profil für qwen über die Cloud (qwen-plus & Co., DashScope, OpenAI-
# kompatibel). Gebaut und gemessen in der Nacht 09./10.10.2026 mit dem
# Prüfstand (memory/ki/modell_profile.md: was half, was nicht, Zahlen).
#
# Jede Strategie steht hier mit ihrem Grund. Was nicht half, steht NICHT
# hier, sondern in der Doku — sonst zahlt qwen für Text, der nichts bringt.

import re as _re

import nutzer_angaben

NAME = "qwen"


# ── Arbeitsweise: zuerst handeln, dann reden (Runde 1) ──────────────────
# Grundmessung 09.10. (ohne Profil): qwen-plus kündigte an statt zu tun
# („ändere ich ihn direkt … Möchtest du die Änderung jetzt durchführen?"),
# antwortete über den Kalender, ohne nachzulesen („nur ein Parkour-Termin"),
# erfand Daten („Ferien 12.–31. Oktober, steht in der amtlichen
# Ferienordnung") und meldete Erledigtes, das nie lief („Du hast nyam
# gelöscht"). Die gross-Regeln stehen weiter unten im langen Kopf; ein
# kleineres Modell folgt dem, was ganz vorn und ganz hinten steht, deutlich
# eher (Anthropic/OpenAI-Leitfäden: Regeln an Anfang und Ende, kurz, im
# Imperativ). Deshalb dieselben Pflichten als knappe Liste VOR die Persona —
# und als Erinnerung ans Ende jeder Nachricht.
# Geschärft in den Runden 3 (breiter suchen), 6/7 (Suche ohne Zeitraum, „Was
# ansteht" ist nicht der Kalender, Ende nicht erfinden, „halb X" als Regel
# mit neutralen Beispielen — ein Beispiel mit Fall-Werten hatte „halb sieben"
# zu 19:30 gemacht) und 10 (nicht mehr als verlangt, Suchtreffer kennzeichnen,
# Quelle nennen). Seit 2026-10-10 schreibt die Quelle Python (core/quellen.py),
# die KI muss keine Adresse mehr abschreiben.
_ARBEITSWEISE_VORLAGE = """## Arbeitsweise (gilt vor allem anderen)

1. Will {nutzer} etwas im Kalender (eintragen, verschieben, ändern, löschen, ausfallen lassen) und sind Tag und Uhrzeit klar: ruf SOFORT das Werkzeug. Nicht ankündigen, nicht fragen „soll ich?" — die Ja/Nein-Frage stellt ZENTRALE selbst, bevor etwas geschrieben wird.
2. Sagt {nutzer} „ok", „ja", „mach", „passt" auf deinen Vorschlag: führ ihn JETZT mit Werkzeugen aus.
3. Bevor du einen bestehenden Termin änderst oder etwas über den Kalender sagst: read_calendar — für einen bestimmten Termin oder eine Serie mit 'suche' (Stichwort) und OHNE 'zeitraum'. Der Block „Was ansteht" zeigt nur heute und morgen, nie den ganzen Kalender. Findet die Stichwort-Suche nichts, lies den Zeitraum ohne 'suche' (Titel heißen oft anders), bevor du sagst, es gibt ihn nicht. Kennungen (#r…, #t…) schreibst du nur aus einem Werkzeug-Ergebnis ab, nie ausgedacht, und nie in den Text an {nutzer}.
4. „Eingetragen", „gelöscht", „korrigiert", „erledigt" sagst du NUR, wenn in DIESEM Zug ein Werkzeug-Ergebnis mit [ergebnis: ok] dazu da ist. Sonst sag, was noch nicht passiert ist.
5. Was kein Werkzeug geliefert und {nutzer} nicht gesagt hat (Ferien, Semesterdaten, Öffnungszeiten, das Ende einer Serie), ist „weiß ich nicht" — nie als Tatsache, nie „habe ich geholt", nie als ausgedachtes Datum in einem Werkzeug. Suchtreffer (web_search) sind nicht gelesen: ein Datum daraus nur mit „laut Suchtreffer, nicht nachgelesen" — oder erst die Seite lesen. Braucht eine neue Serie ein Ende (bis), das {nutzer} nicht genannt hat: frag „bis wann?".
6. Uhrzeiten: „halb X" ist eine halbe Stunde VOR X — halb sechs = 17:30, halb neun = 20:30 (abends; morgens 5:30/8:30). „viertel nach fünf" = 17:15, „dreiviertel sechs" = 17:45. Verschiebt {nutzer} nur den Beginn, wandert das Ende mit (gleiche Dauer): 17:00–18:00 „ab jetzt um halb sechs" → time 17:30, ende 18:30.
7. Du änderst nur, was {nutzer} verlangt. Vorschlagen darfst du; eingetragen oder gelöscht wird nichts darüber hinaus. Sagt {er} „nur nachschauen": schau nach und sag, was du gefunden hast — eintragen nichts.
8. Antwort danach kurz: was jetzt im Kalender steht (Titel, Tag, Uhrzeit). Die Adressen gelesener Seiten zeigt ZENTRALE selbst als Quellen an. Keine Pläne, was du gleich tun wirst — entweder tun oder lassen."""

_ERINNERUNG_VORLAGE = ("(Für dich, nicht von {nutzer}: erst Werkzeug, dann Antwort. Erledigt ist nur, "
              "was in diesem Zug mit [ergebnis: ok] zurückkam.)")


# Platzhalter ({nutzer}, {er} …) wie in gross (core/nutzer_angaben.py,
# Erststart 2026-10-09): eingesetzt bei jedem Bau, wie gross.system().
def system(text: str) -> str:
    return nutzer_angaben.einsetzen(_ARBEITSWEISE_VORLAGE) + "\n\n" + text


def erinnerung(verlauf: list = ()) -> str:
    text = nutzer_angaben.einsetzen(_ERINNERUNG_VORLAGE)
    uhr = uhrzeiten(_letzte_nachricht(verlauf))
    return f"{text}\n{uhr}" if uhr else text


# ── Uhrzeiten vorrechnen (Runde 12) ─────────────────────────────────────
# Regel 6 („halb X = eine halbe Stunde vor X") reichte nicht: im
# Abschlusslauf machte qwen aus „halb sieben" wieder 19:30 (f03), obwohl die
# Regel mit Beispielen dastand. Was Python sicher rechnen kann, rechnet
# Python: steht in der neuesten Nachricht eine Umgangs-Uhrzeit, kommt die
# Übersetzung als Zeile in die Erinnerung am Ende („halb sieben" = 6:30 oder
# 18:30) — welche der beiden, entscheidet qwen aus dem Zusammenhang.
_ZAHL = {"eins": 1, "ein": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
         "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11,
         "zwölf": 12, "zwoelf": 12}
_UHR = _re.compile(r"\b(halb|viertel nach|viertel vor|dreiviertel)\s+(\d{1,2}|"
                   + "|".join(_ZAHL) + r")\b")


def uhrzeiten(text: str) -> str:
    """„halb sieben" → '„halb sieben“ = 6:30 oder 18:30'; mehrere mit ' · '."""
    raus = []
    for art, zahl in _UHR.findall((text or "").casefold()):
        n = int(zahl) if zahl.isdigit() else _ZAHL[zahl]
        if not 1 <= n <= 12:
            continue
        stunde, minute = {"halb": (n - 1, 30), "viertel nach": (n, 15),
                          "viertel vor": (n - 1, 45), "dreiviertel": (n - 1, 45)}[art]
        stunde = stunde or 12
        raus.append(f"„{art} {zahl}“ = {stunde}:{minute:02d} oder "
                    f"{stunde + 12 if stunde < 12 else 0}:{minute:02d}")
    if not raus:
        return ""
    return "Uhrzeiten in dieser Nachricht: " + " · ".join(dict.fromkeys(raus)) + "."


def _letzte_nachricht(verlauf) -> str:
    for m in reversed(list(verlauf or [])):
        if m.get("role") == "user":
            return str(m.get("content") or "")
    return ""


# ── Werkzeuge: weniger Stellschrauben, Dauer mitschieben (Runde 2/3) ────
# Runde 1: qwen filterte read_calendar auf layers=["routinen"] — die
# Routinen lagen aber in „termine", es fand nichts und fragte nach (f03).
# Optionale Felder, die nur selten passen, sind für ein kleineres Modell
# eher Falle als Hilfe (OpenAI-Leitfaden: wenige, klare Parameter); der
# Ausführer kommt ohne sie aus. Und beim Verschieben ließ qwen das Ende
# stehen (Training 19:30–20:00 statt 19:30–20:30, m04): der Satz dazu steht
# jetzt dort, wo es ihn beim Aufruf liest — in der Beschreibung.
_WEG = {"read_calendar": ("layers",)}
_DAUER = (" Verschiebst du nur den Beginn, schieb das Ende um dieselbe Zeit mit "
          "(die Dauer bleibt) — außer {nutzer} nennt ein neues Ende.")
# Runde 3: seit main bc304c9 brauchen neue Routinen von/bis. qwen las das
# auch für edit_calendar_routine als Pflicht und fragte vor einer reinen
# Uhrzeit-Änderung nach einem Enddatum (m04).
_NUR_ZEITRAUM = (" von/bis nur mitgeben, wenn sich der Zeitraum der Serie ändern soll; "
                 "für Uhrzeit, Ende, Ort weglassen.")
_ZUSATZ = {"edit_calendar_routine": _DAUER + _NUR_ZEITRAUM, "edit_calendar_entry": _DAUER}


def werkzeuge(tools: list) -> list:
    """Die Werkzeug-Liste für qwen: Kopien, gross bleibt unberührt."""
    import copy
    raus = []
    for t in tools:
        name = t["function"]["name"]
        if name in _WEG or name in _ZUSATZ:
            t = copy.deepcopy(t)
            f = t["function"]
            for feld in _WEG.get(name, ()):
                f["parameters"]["properties"].pop(feld, None)
                if feld in f["parameters"].get("required", []):
                    f["parameters"]["required"].remove(feld)
            f["description"] += nutzer_angaben.einsetzen(_ZUSATZ.get(name, ""))
        raus.append(t)
    return raus


# ── Werkzeug-Auswahl je Gespräch (Runde 9) ──────────────────────────────
# Die gross-Schiene gibt 54 Werkzeuge mit (~31.000 Zeichen Schema). OpenAI
# rät zu „unter 20 zu Beginn eines Zugs“, „Less is More“ (arXiv 2411.15399)
# misst mit dynamisch verkleinerter Liste deutlich bessere Werkzeug-Wahl bei
# kleineren Modellen. In der Grundmessung griff qwen bei der Ferien-Frage zu
# list_files und search_memory. Also: ein fester Kern (Kalender, Notizen,
# Suche, Netz), der Rest in Gruppen, die erst dazukommen, wenn Sasha im
# Gespräch ein passendes Wort benutzt. Die Liste wächst im Gespräch nur
# (alle Nachrichten Sashas zählen) — so bleibt der Präfix-Cache meist heil.
# Ein Werkzeug, das in keiner Gruppe steht (neu dazugekommen), ist immer
# dabei: lieber ein Werkzeug zu viel als eins, das fehlt.
_GRUPPEN = {
    "browser": (r"lsf|portal|browser|klick|webseite|website|seite|http|www\.|"
                r"vorlesungsverzeichnis|login|online|einloggen",
                ("browser_open", "browser_click", "browser_type", "browser_find",
                 "browser_read", "browser_back", "browser_close", "browser_screenshot")),
    "dateien": (r"datei|ordner|input|output|\bzip|skill|code|python|rechne|sandbox|"
                r"skript|script|csv|tabelle",
                ("read_file", "list_files", "find_files", "search_files", "unzip",
                 "remove_input", "import_skill", "fetch_document", "save_from_sandbox",
                 "run_code")),
    "dokumente": (r"pdf|word|docx|dokument|brief|bewerbung|lebenslauf|schreiben|"
                  r"anschreiben|formular",
                  ("read_pdf", "create_pdf", "combine_pdf", "read_docx", "create_docx",
                   "edit_docx", "create_document", "read_document", "update_document",
                   "fetch_document")),
    "post": (r"mail|post|nachricht|news|neuigkeit|welt|schlagzeil|zeitung",
             ("read_mail", "read_news")),
    "messreihen": (r"mess|reihe|gewicht|kurve|tracke|protokollier|wert",
                   ("create_series", "log_series")),
    "skills": (r"skill|anleitung|arbeitsweise|vorgehen",
               ("propose_skill", "edit_skill")),
}
_IN_GRUPPE = {n for _, namen in _GRUPPEN.values() for n in namen}


def auswahl(tools: list, verlauf: list) -> list:
    text = " ".join(str(m.get("content") or "") for m in verlauf
                    if m.get("role") == "user").casefold()
    an = {n for muster, namen in _GRUPPEN.values()
          if _re.search(muster, text) for n in namen}
    return [t for t in tools
            if t["function"]["name"] not in _IN_GRUPPE or t["function"]["name"] in an]


# ── Zusatz-Prüfer: was Python sehen kann, prüft Python (Runde 4/7) ──────
# Runde 3 zeigte: auch mit Arbeitsweise-Block fragt qwen zufällig um
# Erlaubnis, statt zu ändern; Runde 6: es schrieb einmal den Aufruf als Text
# hin und schloss aus einer leeren Stichwort-Suche „gibt es nicht“. Je eine
# Korrekturrunde, Einzelheiten in zusatzpruefer.py.
from . import zusatzpruefer as _zusatz  # noqa: E402


def pruefer(basis, messages=None, werkzeuge=frozenset(), **_):
    if basis is None:
        return None
    return _zusatz.ZusatzPruefer(basis, _zusatz.letzte_nachricht(messages), werkzeuge)


# ── Erste Runde: erst lesen, wenn Sasha etwas ändern will (Runde 5/7/10)
# Runde 4: f03 „parkour am mittwoch ist ab jetzt um halb sieben" — qwen las
# den Block „Was ansteht" (nur heute/morgen) als ganzen Kalender und
# antwortete „kein Termin für Mittwoch", ohne ein Werkzeug zu rufen.
# Runde 5 erzwang deshalb in der ersten Runde IRGENDEIN Werkzeug
# (tool_choice="required" — DashScope nimmt es an, selbst geprüft
# 09.10.2026, obwohl die Doku nur auto/none/Funktion nennt). Runde 6 zeigte
# die Kehrseite: gezwungen, irgendetwas zu tun, trug qwen eine Serie mit
# ausgedachtem Ende ein, statt nach dem Ende zu fragen (f06). Seit Runde 7
# wird deshalb gezielt read_calendar erzwungen — Lesen schadet nie, und
# danach entscheidet qwen frei (auch: nachfragen).
def tool_choice(*, nr: int, verlauf: list, tools=(), **_):
    if nr != 0 or not _zusatz.will_aendern(verlauf):
        return None
    if any(t["function"]["name"] == "read_calendar" for t in tools or ()):
        return {"type": "function", "function": {"name": "read_calendar"}}
    return None
