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
# „Alles korrigiert: …", „Beides erledigt." — Gespräch 20261009-150713 (qwen
# im Budget-Rückfall, kein Werkzeug): der Satz rutschte durch, weil das
# Partizip nicht ganz vorn stand und kein „ist/hab" davor (2026-10-09).
_ALLES = re.compile(r"^(?:so,? |ok,? |okay,? |gut,? )?(?:alles|beides|alle|beide)\s+"
                    r"(?:" + _PARTIZIP[1:-1] + r"|erledigt)\s*(?:[.!:,—–-]|$)")


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
                   or _KNAPP.match(k) or _ALLES.match(k)
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


# ── Was Sasha will (2026-10-10) ─────────────────────────────────────────
# Für „frag nicht, tu" und „Sicheres sofort": nur wenn Sasha etwas
# beauftragt hat, darf der Prüfer Taten verlangen. Bewusst eng — ein
# übersehener Auftrag kostet nichts, ein erfundener ließe die KI etwas tun,
# das niemand wollte.

def _klein(text) -> str:
    return " ".join(str(text or "").lower().split())


# „noch nix eintragen", „nicht löschen", „nur nachschauen" (wie qwen,
# zusatzpruefer._VERNEINT): dann ist es kein Auftrag zu ändern.
_NUR_SCHAUEN = re.compile(
    r"\b(nicht|nix|nichts|kein\w*)\s+(\w+\s+){0,2}(ein)?(trag|lösch|loesch|änder|aender|"
    r"verschieb)\w*|\bnur\s+(nach)?(schau|guck|seh|such|wissen)\w*")
_IMPERATIV = re.compile(
    r"\b(trag|lösch|lösche|loesch|verschieb|verschiebe|änder|ändere|aender|streich|"
    r"notier|pausier|setz)\b|\bleg\b[^.?!]{0,40}\ban\b|\bmerk dir\b|"
    r"\bschreib\b[^.?!]{0,40}\b(auf|ein|rein)\b")
_AENDERUNG = re.compile(r"\bf(?:ä|ae)llt\b[^.?!]{0,60}\baus\b|\bab (jetzt|sofort)\b|"
                        r"\b(ist|sind) jetzt\b|\bverschiebt sich\b")
_BITTE = re.compile(r"\b(kannst|könntest|würdest) du\b[^?]{0,80}\b(eintragen|löschen|"
                    r"ändern|verschieben|anlegen|notieren|streichen|pausieren|rausnehmen)\b")
_JA = re.compile(r"^\W*(ja|jo|jup|jep|ok|okay|passt|genau|mach( das| es| mal)?|gerne?|"
                 r"bitte|los|sure|klar|yes)\b")
_WISSEN = re.compile(r"\?|\b(wann|wie|was|wo|wer|welche\w*|wieso|warum|weshalb|"
                     r"weißt du|gibt es|gibt's|hast du)\b|"
                     r"\b(such|schau|guck|find|check|lies|öffne|recherchier)\w*\b")


def auftrag(nachricht: str) -> bool:
    """Beauftragt Sasha eine Änderung? Imperativ („trag … ein", „lösch …"),
    eine Änderung als Tatsache („fällt … aus", „ist ab jetzt …") oder eine
    Bitte („kannst du … eintragen"). Nicht bei „nur nachschauen" / „noch nix
    eintragen" und nicht, wenn er ablehnt."""
    t = _klein(nachricht)
    if not t or lehnt_ab(t) or _NUR_SCHAUEN.search(t):
        return False
    return bool(_IMPERATIV.search(t) or _AENDERUNG.search(t) or _BITTE.search(t))


def zustimmung(nachricht: str) -> bool:
    """Beginnt Sasha mit ja / ok / mach / sure …?"""
    t = _klein(nachricht)
    return bool(t and _JA.search(t)) and not lehnt_ab(t)


def will_wissen(nachricht: str) -> bool:
    """Fragt Sasha etwas oder schickt die KI nachsehen?"""
    return bool(_WISSEN.search(_klein(nachricht)))


# ── Erlaubnis-Frage statt Tat (2026-10-10, Prüfstand f09) ───────────────
# „Soll ich im Netz nach der Frist suchen?" — statt web_search zu rufen.
# Das Erlaubnis-Gate fragt Sasha ohnehin per Knopf, wo es nötig ist; eine
# Frage im Text kostet ihn einen Zug und die KI vergisst danach oft, was sie
# vorhatte. Vorher nur bei qwen (profil/modelle/zusatzpruefer.py), jetzt für
# alle Modelle der gross-Schiene.
#
# Erkannt wird nur die LETZTE Satz einer Antwort, und nur in Erlaubnis-Form
# („soll ich", „darf ich", „möchtest du, dass ich", „sag Bescheid, dann mach
# ich's"). Keine Erlaubnis-Frage ist eine Wahl („… oder …?") — und bei
# Änderungen eine Frage nach einer Angabe (Zahl, Wochentag, wann, welche).

_ERLAUBNIS = re.compile(r"\b(soll ich|darf ich|sollen wir|"
                        r"(möchtest|willst|magst) du,? dass ich)\b")
_BESCHEID = re.compile(r"\bsag (kurz |einfach |mir |gern |gerne )?bescheid\b[^.?!]{0,40}"
                       r"\b(dann|und) (mach|trag|änder|pass|leg|lösch|such|schau)")
_WAHL = re.compile(r"\boder\b(?!\s*(nicht|lieber nicht)?\s*[?!.…]*\s*$)")
_ANGABE = re.compile(r"\d|\b(wann|welch\w*|wie (viel|lange|spät)|wo|wohin|um wie viel)\b|"
                     r"\b(" + _WOCHENTAG + r"|januar|februar|märz|april|mai|juni|juli|"
                     r"august|september|oktober|november|dezember)\b")

_NETZ_WORT = r"(im netz|im internet|online|im web|bei google|web)"
_SUCHEN = r"(such|googl|recherchier|nachseh|nachschau|schau|guck)\w*"
_SEITE_WORT = r"(seite|link|url|adresse|website|webseite|lsf|portal|browser)"
_LADEN = (r"(öffn|lad|aufruf|aufrufen|abruf|les|lese|nachles|anschau|reinschau|nachseh|"
          r"nachschau|schau|guck)\w*")
# (aktion, muster, schreibend) — die erste passende gewinnt.
_AKTIONEN = (
    ("netz", re.compile(rf"\b{_SUCHEN}\b[^?]*\b{_NETZ_WORT}\b|\b{_NETZ_WORT}\b[^?]*\b{_SUCHEN}"),
     False),
    ("seite", re.compile(rf"\b{_LADEN}\b[^?]*\b{_SEITE_WORT}\b|\b{_SEITE_WORT}\b[^?]*\b{_LADEN}"),
     False),
    ("pause", re.compile(r"\b(pause|pausier\w*|ausfall|ausfallen)\b"), True),
    ("eintragen", re.compile(r"\b(eintrag\w*|einträg\w*|anleg\w*|anlegen|hinzufüg\w*|"
                             r"reinschreib\w*|einplan\w*|eintragen)\b"), True),
    ("loeschen", re.compile(r"\b(lösch\w*|loesch\w*|entfern\w*|streich\w*|rausnehm\w*|"
                            r"rausnimm\w*)\b"), True),
    ("aendern", re.compile(r"\b(änder\w*|aender\w*|verschieb\w*|anpass\w*|korrigier\w*|"
                           r"umstell\w*|verleg\w*|zusammenleg\w*|setzen)\b"), True),
    ("notieren", re.compile(r"\b(notier\w*|festhalt\w*|festhalten|merk\w*|aufschreib\w*|"
                            r"speicher\w*)\b"), True),
    ("nachsehen", re.compile(r"\b(such\w*|nachseh\w*|nachschau\w*|nachguck\w*|schau\w*|"
                             r"guck\w*|check\w*|prüf\w*|nachles\w*|raussuch\w*|"
                             r"herausfind\w*|rausfind\w*)\b"), False),
    ("tun", re.compile(r"\b(durchführ\w*|umsetz\w*|erledig\w*|mach\w*|ausführ\w*)\b"), True),
)


@dataclass
class Frage:
    satz: str
    aktion: str          # netz, seite, nachsehen | pause, eintragen, loeschen, aendern, notieren, tun
    schreibend: bool


def aktion(satz: str) -> tuple:
    """Welche Art Tat ein Satz meint. -> (aktion, schreibend) oder (None, False).
    Ein Satz mit Notiz-Wörtern („in deine Notizen eintragen") ist notieren."""
    k = _klein(satz)
    for name, rx, schreibend in _AKTIONEN:
        if rx.search(k):
            if schreibend and name in ("eintragen", "aendern", "loeschen") \
                    and "notiz" in bereiche(k) and "kalender" not in bereiche(k):
                return "notieren", True
            return name, schreibend
    return None, False


def erlaubnis_frage(antwort: str) -> Frage | None:
    """Endet die Antwort damit, um Erlaubnis für eine Tat zu bitten, die ein
    Werkzeug erledigen könnte? -> Frage oder None."""
    alle = saetze(antwort)
    if not alle:
        return None
    # Der letzte Satz — saetze() trennt nach einer Uhrzeit nicht („auf
    # 16:30. Soll ich …?"), hier zählt aber nur die Frage selbst.
    text = re.split(r"(?<=[.!?…])\s+(?=[A-ZÄÖÜ„\"])", alle[-1].text)[-1]
    s = Satz(text, _klein(text), text.rstrip().endswith("?"))
    k = s.klein
    if not ((s.frage and _ERLAUBNIS.search(k)) or _BESCHEID.search(k)):
        return None
    if _WAHL.search(k):
        return None
    name, schreibend = aktion(k)
    if name is None:
        return None
    if schreibend and _ANGABE.search(k):
        return None
    return Frage(s.text, name, schreibend)
