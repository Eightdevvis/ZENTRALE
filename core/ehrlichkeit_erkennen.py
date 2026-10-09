# core/ehrlichkeit_erkennen.py
#
# Was in einer fertigen Antwort der KI steht, das Python nachprüfen kann:
#
#   taten()        „hab ich eingetragen", „ist jetzt gelöscht", „steht jetzt
#                  drin" — eine Erledigt-Behauptung
#   versprechen()  „trag ich gleich ein", „mach ich, sobald …" — eine Zusage
#   kennungen()    #r3f9c / #t47d2 — Kalender-Kennungen (core/ki_kalender.py)
#
# 2026-10-09, „Ehrlichkeit durch Bauweise" (memory/ki/ehrlichkeit_live.md).
# Reines Python, kein zweites Modell: billig, jeden Zug, und vor allem
# vorhersagbar. Der Preis ist, dass die Erkennung nur Satzmuster kennt. Sie
# ist deshalb auf WENIGE Falschtreffer gebaut, nicht auf Vollständigkeit —
# ein übersehenes „erledigt" ist harmlos, eine Korrekturrunde wegen eines
# Satzes, der keine Behauptung war, kostet Geld und verwirrt die KI.
# Darum fliegt jeder Satz raus, der eine Frage, ein Angebot, eine Bedingung
# oder eine Verneinung ist.
#
# Die Bereiche (kalender, notiz, …) verbinden Satz und Werkzeug: „Termin
# verschoben" ist nur belegt, wenn ein Kalender-Werkzeug lief. Welches
# Werkzeug in welchen Bereich gehört, steht in ehrlichkeit.py (dort ist das
# Werkzeug-Register bekannt); hier steht nur, woran man den Bereich im TEXT
# erkennt.
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md): nur Text, kein Fach.

import re
from dataclasses import dataclass, field

# ── Bereiche im Text ────────────────────────────────────────────────────
# Wörter, an denen ein Satz seinen Bereich verrät. Kein Treffer → der Satz
# gilt für jeden Bereich (dann belegt ihn jedes passende Werkzeug).
_WOCHENTAG = r"montags?|dienstags?|mittwochs?|donnerstags?|freitags?|samstags?|sonntags?"
BEREICH_WOERTER = {
    "kalender": re.compile(
        r"termin|routine|kalender|pause|ferien|\buhr\b|\d{1,2}[:.]\d{2}|"
        r"wöchentlich|täglich|" + _WOCHENTAG),
    "notiz": re.compile(
        r"notiz|hausregel|steckbrief|\bziele?\b|dossier|katalog|tagebuch|"
        r"gedächtnis|notiert|festgehalten|vermerkt|gemerkt|merk\w* (ich )?mir|"
        r"aufgeschrieben"),
    "ablage": re.compile(r"dokument|ablage|\bpdf|datei|\bword\b|docx"),
    "messreihe": re.compile(r"messreihe|messkurve|kurve|messwert"),
    "skill": re.compile(r"\bskills?\b|anleitung"),
    "netz": re.compile(r"internet|im netz|webseite|website|online|recherch|google"),
}


def bereiche(satz: str) -> set:
    s = satz.lower()
    return {b for b, rx in BEREICH_WOERTER.items() if rx.search(s)}


# ── Sätze ───────────────────────────────────────────────────────────────

@dataclass
class Satz:
    text: str          # wie in der Antwort (für die Anzeige, gekürzt)
    klein: str         # kleingeschrieben, Leerraum geglättet
    frage: bool


def saetze(text: str) -> list:
    """Antwort → Sätze. Getrennt an . ! ? und Zeilenumbrüchen; Markdown-
    Zeichen am Anfang (Aufzählung, Fett) weg. Uhrzeiten („18.30") und
    Daten („12.10.") trennen nicht."""
    raus = []
    for zeile in str(text or "").splitlines():
        zeile = re.sub(r"^\s*(?:[-*•>]|\d+[.)])\s+", "", zeile)
        zeile = zeile.replace("**", "").replace("__", "")
        for m in re.finditer(r".+?(?:(?<!\d)[.!?…]+(?!\d)|$)", zeile):
            t = m.group(0).strip()
            if len(t) < 3:
                continue
            raus.append(Satz(t[:200], " ".join(t.lower().split()),
                             t.rstrip().endswith("?")))
    return raus


# Was einen Satz zu etwas anderem als einer Behauptung macht.
_VERNEINT = re.compile(r"\b(nicht|nichts|kein|keine|keinen|keiner|nie|niemals|"
                       r"noch nicht|weder)\b")
_BEDINGT = re.compile(r"\b(würde|würden|würd|wäre|wären|hätte|hätten|könnte|"
                      r"könnten|sollte|sollten|soll ich|sollen wir|kann ich|"
                      r"darf ich|falls|wenn|ob|sonst|vielleicht|eventuell|"
                      r"vermutlich|wahrscheinlich)\b")
# Angebote und Rückfragen — „soll ich …?", „wenn du willst, trag ich …".
_ANGEBOT = re.compile(r"\b(soll ich|sollen wir|willst du|möchtest du|magst du|"
                      r"wenn du (willst|möchtest|magst|magst)|falls du|"
                      r"wenn gewünscht|bei bedarf|kann ich|könnte ich|"
                      r"würde ich|darf ich|sag (mir )?bescheid|entweder|"
                      r"zwei (wege|möglichkeiten|optionen)|oder soll)\b")
# Bezug auf einen früheren Zug: dann reicht ein Beleg aus dem Gespräch.
_FRUEHER = re.compile(r"\b(vorhin|vorher|gestern|letztes mal|letztens|bereits|"
                      r"schon|früher|neulich|damals|eben schon)\b")


# ── Erledigt-Behauptungen ───────────────────────────────────────────────

_PARTIZIP = (r"(eingetragen|ausgetragen|gelöscht|entfernt|verschoben|angelegt|"
             r"gespeichert|geändert|aktualisiert|angepasst|notiert|festgehalten|"
             r"vermerkt|hinzugefügt|ergänzt|umbenannt|erstellt|abgelegt|pausiert|"
             r"korrigiert|gestrichen|aufgeschrieben|reingeschrieben|eingerichtet|"
             r"abgesagt|repariert|zusammengeführt|bereinigt|ersetzt|gemerkt|"
             r"neu geschrieben|umgestellt|verlegt|eingetragen)")
# „hab ich … eingetragen", „ich habe … angelegt", „Hab die Routine angelegt."
_ICH_PERFEKT = re.compile(
    r"(?:\bich (?:hab|habe|hab's|habs)\b|\b(?:hab|habe|hab's|habs) ich\b|"
    r"^(?:so,? |ok,? |okay,? |gut,? |erledigt[:,]? |fertig[:,]? )?(?:hab|habe|hab's|habs)\b)"
    r"(?:\s+\S+){0,8}?\s+" + _PARTIZIP + r"\b")
# „ist jetzt gelöscht", „wurde verschoben", „sind damit eingetragen"
_ZUSTAND = re.compile(
    r"\b(?:ist|sind|wurde|wurden)\b(?:\s+\S+){0,6}?\s+" + _PARTIZIP + r"\b")
_ZUSTAND_JETZT = re.compile(r"\b(jetzt|nun|damit|ab sofort|erfolgreich|soeben)\b")
_STEHT_JETZT = re.compile(r"\bsteh(?:t|en) (?:jetzt|nun|ab sofort)\b(?:\s+\S+){0,6}?"
                          r"\s+(?:drin|im kalender|eingetragen|in de[mnr]|da\b)")
_KNAPP = re.compile(r"^(erledigt|eingetragen|gelöscht|verschoben|angelegt|"
                    r"gespeichert|geändert|notiert|festgehalten)\b[.!:]?")


@dataclass
class Tat:
    satz: str
    bereiche: set = field(default_factory=set)
    frueher: bool = False      # bezieht sich auf einen früheren Zug


def taten(text: str) -> list:
    """Die Erledigt-Behauptungen einer Antwort (je Satz höchstens eine)."""
    raus = []
    for s in saetze(text):
        k = s.klein
        if s.frage or _VERNEINT.search(k) or _BEDINGT.search(k):
            continue
        treffer = (_ICH_PERFEKT.search(k) or _STEHT_JETZT.search(k)
                   or _KNAPP.match(k)
                   or (_ZUSTAND.search(k) and (_ZUSTAND_JETZT.search(k)
                                               or re.search(r"\bwurden?\b", k))))
        if treffer:
            raus.append(Tat(s.text, bereiche(k), bool(_FRUEHER.search(k))))
    return raus


# ── „Nicht da" ──────────────────────────────────────────────────────────
# 2026-10-09, Gespräch 20261009-155510: „Ich seh in der Liste keine
# chefkoch-Datei oder ZIP" — dabei war die Liste nur gekappt. Behauptet die
# KI, eine Datei gebe es nicht, muss eine VOLLSTÄNDIGE Suche das belegen
# (ehrlichkeit.suche_belegt). Erkannt wird nur, was nach Datei klingt —
# „den Termin gibt es nicht" ist Sache des Kalenders, nicht dieses Prüfers.
_DATEI_WORT = re.compile(r"datei|\bzip\b|-zip\b|ordner|verzeichnis|\bpfad|\bpdf\b|"
                         r"dokument|\.(?:zip|md|txt|pdf|json|csv|docx?|png|jpe?g)\b|"
                         r"\binput\b|\boutput\b")
_NICHT_DA = re.compile(
    r"\b(?:find|finde|fand|seh|sehe|sah|entdecke)\b(?:\s+\S+){0,8}?\s+(?:nicht|nichts|kein\w*)\b|"
    r"\b(?:nicht|kein\w*)\b(?:\s+\S+){0,6}?\s+(?:gefunden|vorhanden|auffindbar|"
    r"zu finden|zu sehen|da|dort|drin)\b|"
    r"\b(?:gibt es|gibt's|existiert|existieren)\b(?:\s+\S+){0,4}?\s+(?:nicht|kein\w*)\b|"
    r"\b(?:liegt|liegen)\b(?:\s+\S+){0,6}?\s+(?:nicht|kein\w*)\b")


def nicht_da(text: str) -> list:
    """Sätze, die sagen, eine Datei/ein Ordner sei nicht da („finde ich
    nicht", „gibt es nicht", „liegt nicht in Input/", „keine Zip gefunden").
    Fragen und Bedingtes („falls die Datei nicht da ist") zählen nicht."""
    # Punkte IN Dateinamen („rezepte.md") trennen keinen Satz: vorübergehend
    # durch ein Ersatzzeichen ersetzt, im Ergebnis wieder Punkt.
    text = re.sub(r"(?<=\w)\.(?=\w)", "․", str(text or ""))
    raus = []
    for s in saetze(text):
        k = s.klein.replace("․", ".")
        if s.frage or _BEDINGT.search(k):
            continue
        if _DATEI_WORT.search(k) and _NICHT_DA.search(k):
            raus.append(s.text.replace("․", "."))
    return raus


# ── Zusagen ─────────────────────────────────────────────────────────────

# Erste Person Präsens der Verben, mit denen die KI etwas zusagt. Bewusst
# ohne „seh/sehe" („das sehe ich auch so") und „stell" („stell ich mir vor").
_VERB = (r"(trag|trage|leg|lege|mach|mache|schreib|schreibe|notier|notiere|"
         r"lösch|lösche|verschieb|verschiebe|änder|ändere|ändre|speicher|"
         r"speichere|merk|merke|kümmer|kümmere|kümmre|erledig|erledige|setz|"
         r"setze|füg|füge|hol|hole|prüf|prüfe|schau|schaue|guck|gucke|such|"
         r"suche|ergänz|ergänze|korrigier|korrigiere|richt|richte|buch|buche|"
         r"pausier|pausiere|halt|halte|les|lese)")
# Woran man erkennt, dass etwas NOCH kommt: Zeitwort oder abgetrennte Silbe.
_NOCH = re.compile(r"\b(gleich|sofort|nachher|später|dann|danach|morgen|jetzt|"
                   r"als nächstes|sobald|direkt|noch|gern|gerne|demnächst|"
                   r"im anschluss|umgehend)\b")
_SILBE = re.compile(r"\b(ein|an|um|nach|fest|auf|weg|raus|rein|hinzu|ab|"
                    r"zurück|drum|darum|vor)\s*[.!,;:–-]*$|"
                    r"\b(ein|an|um|nach|fest|auf|weg|raus|rein|hinzu|ab|"
                    r"zurück|drum|darum)\s*,")
_INVERTIERT = re.compile(r"\b" + _VERB + r" ich\b")
_ICH_PRAESENS = re.compile(r"\bich " + _VERB + r"\b")
_ICH_WERDE = re.compile(
    r"\bich (?:werde|werd)\b(?:\s+\S+){0,8}?\s+(eintragen|anlegen|löschen|"
    r"verschieben|ändern|speichern|notieren|festhalten|nachsehen|nachschauen|"
    r"prüfen|schreiben|aufschreiben|merken|kümmern|erledigen|hinzufügen|"
    r"ergänzen|korrigieren|anpassen|suchen|raussuchen|holen|erstellen|"
    r"ablegen|pausieren|lesen|nachlesen)\b")
_LASS_MICH = re.compile(r"\blass mich\b(?:\s+\S+){0,3}?\s+(nachsehen|nachschauen|"
                        r"prüfen|schauen|gucken|suchen|eintragen)\b")
_KUEMMERN = re.compile(r"\b(?:ich kümmere?|kümmere? ich) mich\b|\bmerk\w* ich mir\b|"
                       r"\bich merk\w* mir\b")


# Zusagen, nur nachzusehen — eingelöst schon durch ein LESENDES Werkzeug.
_NUR_SCHAUEN = re.compile(r"\b(schau|schaue|guck|gucke|such|suche|prüf|prüfe|les|"
                          r"lese|nachsehen|nachschauen|prüfen|suchen|raussuchen|"
                          r"lesen|nachlesen|google)\b")


@dataclass
class Zusage:
    satz: str
    bereiche: set = field(default_factory=set)
    stichwoerter: list = field(default_factory=list)
    schreibend: bool = True    # False: „schau ich nach" — Lesen löst sie ein


def versprechen(text: str) -> list:
    """Zusagen in Zukunftsform. Fragen und Angebote („soll ich …?", „wenn du
    willst, trag ich …") sind keine — die Entscheidung liegt dann bei Sasha."""
    raus = []
    for s in saetze(text):
        k = s.klein
        if s.frage or _VERNEINT.search(k) or _ANGEBOT.search(k):
            continue
        if _ICH_PERFEKT.search(k):      # „hab ich eingetragen und …": Tat, keine Zusage
            continue
        zeit = bool(_NOCH.search(k) or _SILBE.search(k))
        treffer = (_ICH_WERDE.search(k) or _LASS_MICH.search(k)
                   or _KUEMMERN.search(k)
                   or ((_INVERTIERT.search(k) or _ICH_PRAESENS.search(k)) and zeit))
        if treffer:
            raus.append(Zusage(s.text, bereiche(k), stichwoerter(s.text),
                               not _NUR_SCHAUEN.search(k)))
    return raus


# Großgeschriebene Wörter mitten im Satz sind im Deutschen meist Namen und
# Dinge („Zahnarzt", „Geige") — daran hängt, ob ein späterer Zug sich noch
# auf die Zusage bezieht.
_KEINE_STICHWOERTER = {"ich", "du", "sasha", "ok", "okay", "das", "die", "der",
                       "sie", "es", "wir", "zentrale", "uhr"}


def stichwoerter(satz: str) -> list:
    woerter = re.findall(r"(?<![.!?]\s)(?<!^)\b([A-ZÄÖÜ][\wäöüß-]{3,})", satz)
    raus = []
    for w in woerter:
        if w.lower() not in _KEINE_STICHWOERTER and w.lower() not in raus:
            raus.append(w.lower())
    return raus[:6]


# ── Kennungen ───────────────────────────────────────────────────────────

# Wie core/ki_kalender.py sie vergibt: t/r + 4 (bei Kollision mehr) Hexzeichen.
_KENNUNG = re.compile(r"(?<![\w#])#([tr][0-9a-f]{4,12})\b")


def kennungen(text: str) -> list:
    """Alle Kalender-Kennungen im Text, ohne #, in Reihenfolge, ohne Doppel."""
    raus = []
    for k in _KENNUNG.findall(str(text or "").lower()):
        if k not in raus:
            raus.append(k)
    return raus


def unbekannte_kennungen(antwort: str, bekannt: set) -> list:
    """Kennungen der Antwort, die in keiner Quelle stehen. Eine abgekürzte
    Kennung (Anfang einer bekannten, ab 5 Zeichen) gilt als bekannt —
    ki_kalender.finden nimmt sie genauso."""
    raus = []
    for k in kennungen(antwort):
        if k in bekannt:
            continue
        if len(k) >= 5 and any(b.startswith(k) for b in bekannt):
            continue
        raus.append(k)
    return raus


# ── Sasha lehnt ab ──────────────────────────────────────────────────────

_ABLEHNUNG = re.compile(r"^\s*(nein|nee|ne|nö|lass (es|das|mal|gut sein)|"
                        r"brauchst du nicht|musst du nicht|nicht nötig|"
                        r"vergiss (es|das)|passt schon|schon gut|egal)\b")


def lehnt_ab(nachricht: str) -> bool:
    """Sagt Sasha am Anfang seiner Nachricht nein / lass es?"""
    return bool(_ABLEHNUNG.search(str(nachricht or "").lower()))
