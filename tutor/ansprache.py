# tutor/ansprache.py
#
# WANN die Persona von sich aus spricht, WOZU, und WIE SCHWER — als Code,
# nicht als Hoffnung im Prompt (2026-10-08, memory/tutor/diagnose_2026-10-08.md).
#
# Sasha: „die idee ist ja dass man an ihr vorbeiläuft, sie einen intelligent und
# mit intention anquatscht, perfekt passend zum schwierigkeitslevel … aber
# momentan quatschen die literally RANDOM ZEUG teilweise ununterbrochen".
#
# Was vorher fehlte und hier steht:
#   Ruhe     — der Server entscheidet, ob ein Anstoß überhaupt reden darf. Bis
#              dahin entschied nur das Zimmer-Fenster (Zeitgeber in room.py);
#              zwei offene Fenster (Pi + Laptop) oder eine verrutschte Uhr
#              hießen: zweimal so viel Gerede. Jetzt höchstens zwei Äußerungen
#              von ihr, bis Sasha etwas sagt; Ankunft erst nach langer Ruhe.
#   Absicht  — jeder Anstoß bekommt einen Anlass mit Ziel: Ankunft = grüßen +
#              EINE leichte Frage; Nachhaken = das Letzte EINFACHER sagen, kein
#              neues Thema; Stille = EIN Wort (fällige Wiederholung oder das
#              nächste Grundwort). Vorher bekam sie nur „es ist still" und
#              erfand irgendwas.
#   Niveau   — die Register-Leiter (expect.json) zählt wieder die Wörter, die
#              Sasha WIRKLICH kennt, nicht die 75 freigegebenen Grundwörter
#              (n war vorher nie kleiner als 75 → die Leiter griff nie).
#   Nachfrage — „que?/qué?/was?/hä?" → das eine Schlüsselwort ihrer letzten
#              Äußerung, langsamer, mit Übersetzung im Gedanken.
#   Nachkontrolle — zählt in ihrer Antwort die Wörter, die Sasha nicht kennt;
#              zu viele → beim nächsten Zug ein kurzer Hinweis in der
#              Zielsprache. Kein zweiter Modell-Aufruf.
#
# Texte in der ZIELSPRACHE aus dem Paket (langs/<code>/absichten.json) — ein
# deutscher Block kippt qwen ins Deutsche (tutor_persona_tuning.md). Fehlt die
# Datei (Skizzen), gibt es keine Absicht, nur die Ruhe-Regeln.

import re
import time

from . import tools

# ── Ruhe ───────────────────────────────────────────────────────────────
MAX_UNBEANTWORTET = 2      # so oft spricht sie höchstens, bis Sasha etwas sagt
                           # (Antwort + EIN Nachhaken). Vorher: Antwort, Nachhaken
                           # nach 15 s, Anstoß nach 90 s, dann alle 15 min — ewig.
MIN_ABSTAND_S     = 60     # zwischen zwei Anstößen von sich aus
ANKUNFT_RUHE_S    = 600    # Ankunft darf reden, wenn sie so lange still war
NACHHAKEN_FRISCH_S = 180   # Nachhaken bezieht sich nur auf frisch Gesagtes


class Ruhe:
    """Wer darf wann? Ein Zustand pro Session (session.activate setzt neu)."""

    def __init__(self, uhr=time.time):
        self.uhr = uhr
        self.unbeantwortet = 0       # ihre Äußerungen seit Sashas letztem Satz
        self.zuletzt_sie = 0.0       # wann sie zuletzt etwas gesagt hat
        self.zuletzt_anstoss = 0.0   # wann sie zuletzt VON SICH AUS gesprochen hat

    def sasha_sagte(self):
        self.unbeantwortet = 0

    def art(self, ankunft: bool) -> str:
        """Welcher Anlass ist dieser Anstoß? ankunft / nachhaken / stille."""
        if ankunft:
            return 'ankunft'
        if (self.unbeantwortet >= 1
                and self.uhr() - self.zuletzt_sie < NACHHAKEN_FRISCH_S):
            return 'nachhaken'
        return 'stille'

    def darf(self, art: str):
        """(darf, grund). Nur für Anstöße — eine Antwort auf Sasha darf immer."""
        jetzt = self.uhr()
        if art == 'ankunft':
            if self.zuletzt_sie and jetzt - self.zuletzt_sie < ANKUNFT_RUHE_S:
                return False, 'ankunft, aber sie hat eben erst geredet'
            return True, ''
        if self.unbeantwortet >= MAX_UNBEANTWORTET:
            return False, f'{self.unbeantwortet}× ohne Antwort von Sasha — sie wartet'
        if self.zuletzt_anstoss and jetzt - self.zuletzt_anstoss < MIN_ABSTAND_S:
            return False, 'eben erst angestoßen'
        return True, ''

    def gesprochen(self, von_sich_aus: bool):
        jetzt = self.uhr()
        self.zuletzt_sie = jetzt
        self.unbeantwortet += 1
        if von_sich_aus:
            self.zuletzt_anstoss = jetzt


# ── Wörter ─────────────────────────────────────────────────────────────

def woerter(text: str) -> list:
    """Wörter einer Äußerung, klein, ohne Satzzeichen, Reihenfolge erhalten.
    CJK: jedes Zeichen zählt (kein Leerzeichen dort)."""
    t = (text or '').lower()
    t = re.sub(r'\([^)]*\)|（[^）]*）|\*[^*]*\*', ' ', t)     # Regie fliegt raus
    raus = []
    for w in re.findall(r"[\w'’]+", t):
        if re.search(r'[一-鿿]', w):
            raus += [ch for ch in w if '一' <= ch <= '鿿']
        elif not w.isdigit():
            raus.append(w)
    return raus


def _eintraege(lang):
    try:
        return tools._load_raw(lang)
    except Exception:
        return []


def bekannte(lang) -> set:
    """Was Sasha wirklich kennt: getrackte Wörter mit Status ≠ new (klein)."""
    raus = set()
    for e in _eintraege(lang):
        if e.get('word') and tools.word_status(e) != 'new':
            raus.update(woerter(e['word']))
    return raus


def bedeutung(wort: str, lang) -> str:
    """Bedeutung in Sashas Muttersprache, wenn wir sie haben (Vokabel-Eintrag
    oder Glosse des Grundworts) — sonst ''."""
    w = (wort or '').strip().lower()
    for e in _eintraege(lang):
        if str(e.get('word', '')).lower() == w and e.get('meaning'):
            return e['meaning']
    for c in tools._core_list(lang):
        if str(c.get('word', '')).lower() == w:
            return tools.glosse(c)
    return ''


def schluesselwort(letzte: str, lang) -> str:
    """Das EINE Wort ihrer letzten Äußerung, das Sasha am wenigsten kennt —
    darum geht es bei „que?". Vorrang: Wörter, zu denen wir eine Bedeutung
    haben (sonst gibt es nichts zu zeigen); darunter das längste."""
    ws = woerter(letzte)
    if not ws:
        return ''
    kennt = bekannte(lang)
    fremd = [w for w in ws if w not in kennt and len(w) >= 2] or ws
    mit = [w for w in fremd if bedeutung(w, lang)]
    return max(mit or fremd, key=len)


def lernziel(lang):
    """(wort, bedeutung) für einen Anstoß in der Stille: zuerst eine fällige
    Wiederholung (SRS), sonst das nächste Grundwort. None → kein Ziel."""
    wort = ''
    try:
        from . import srs
        faellig = srs.due_words(lang, limit=1)
        wort = faellig[0] if faellig else ''
    except Exception:
        wort = ''
    if not wort:
        todo = tools.core_todo(lang, 1)
        wort = todo[0]['word'] if todo else ''
    return (wort, bedeutung(wort, lang)) if wort else None


def fremde(text: str, lang, erlaubt=()) -> list:
    """Wörter ihrer Antwort, die Sasha nicht kennt (ohne die erlaubten, z. B.
    das Lernziel). Für die Nachkontrolle."""
    kennt = bekannte(lang) | {w.lower() for w in erlaubt}
    gesehen, raus = set(), []
    for w in woerter(text):
        if w not in kennt and w not in gesehen:
            gesehen.add(w); raus.append(w)
    return raus


# Wie viele unbekannte Wörter pro Antwort noch in Ordnung sind — nach dem,
# was Sasha kennt. Absichtlich grob; die Leiter im Paket sagt es dem Modell,
# das hier misst nur nach.
def erlaubt_fremd(n_bekannt: int) -> int:
    if n_bekannt < 15:
        return 2
    if n_bekannt < 60:
        return 3
    if n_bekannt < 200:
        return 5
    return 999


# ── Texte aus dem Paket ────────────────────────────────────────────────

def text(prof: dict, schluessel: str, **werte) -> str:
    """Absichts-Text der Sprache (absichten.json), gefüllt. '' wenn das Paket
    ihn nicht hat."""
    vorlage = (prof.get('absichten') or {}).get(schluessel) or ''
    if not vorlage:
        return ''
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError):
        return ''


def anstoss_text(prof: dict, art: str, lang, letzte: str = '') -> str:
    """Der Anlass eines Anstoßes in der Zielsprache — hängt an die Lage-Meldung."""
    if art == 'nachhaken' and letzte:
        wort = schluesselwort(letzte, lang)
        return text(prof, 'nachhaken', letzte=letzte.strip()[:160], wort=wort,
                    bedeutung=bedeutung(wort, lang) or '?')
    if art == 'stille':
        ziel = lernziel(lang)
        if ziel:
            return text(prof, 'stille', wort=ziel[0], bedeutung=ziel[1] or '?')
        return text(prof, 'stille_ohne_ziel')
    if art == 'ankunft':
        return text(prof, 'ankunft')
    return ''
