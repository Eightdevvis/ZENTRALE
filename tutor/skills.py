"""Skills: Situationen erkennen, in denen die Persona sich anders verhalten muss.

Ein Skill ist hier zweierlei: ein DETERMINISTISCHER Auslöser (dieses Modul) und
ein kurzes Verhaltens-Dokument in der Zielsprache, das nur dann in den
System-Prompt kommt (später, `tutor/langs/<code>/skills/<name>.md`). Kein
zweiter LLM-Aufruf, keine Kappung — abgeschnittene Sätze wären Müll.

Erster Skill: `no_entiendo` — Sasha versteht nicht. Der Punkt, an dem die KI
merken muss, dass sie anders reden soll (einzelne Wörter, langsam, zeigen).
Sasha 2026-09-17: erst nur CATCHEN und im Devtool anzeigen, ob es passend
greift; das Verhalten kommt danach.

Regeln (bewusst hart kodiert, Sprache für Sprache erweiterbar):
  1. explizite Unverständnis-Phrasen (siehe _PHRASEN) oder ein nacktes „?"
  2. Äußerung endet mit „?" und hat höchstens zwei Wörter („¿qué?", „cómo?")
  3. ZWEIMAL hintereinander eine Äußerung ohne bekannte Vokabel UND ohne ein
     Wort aus ihrer letzten Antwort — er redet an ihr vorbei.
Aus ist der Zustand, sobald er ein Wort aus ihrer letzten Antwort selbst benutzt
oder eine bekannte Vokabel trifft (ohne dabei wieder eine Phrase zu sagen).

Siehe memory/tutor/naturalisierung.md.
"""

import re

# Phrasen pro Sprache + sprachunabhängig. Kleinschreibung, ohne Satzzeichen
# verglichen (siehe _norm). Ein Eintrag trifft, wenn er als Ganzes in der
# normalisierten Äußerung vorkommt.
_PHRASEN = {
    '*': ["?", "i don't understand", "i dont understand", "what", "sorry what",
          "hä", "häh"],
    'es': ["no entiendo", "no comprendo", "no lo entiendo", "no te entiendo",
           "que", "qué", "como", "cómo", "perdón", "perdon", "otra vez",
           "más despacio", "mas despacio", "repite", "no sé", "no se"],
    'de': ["ich verstehe nicht", "ich versteh nicht", "versteh ich nicht",
           "nicht verstanden", "was", "wie bitte", "wie", "nochmal", "langsamer",
           "keine ahnung", "weiß nicht", "weiss nicht"],
    'zh': ["听不懂", "不明白", "不懂", "什么", "什麼", "再说一遍", "慢一点", "不知道"],
}

# Kurze Rückfrage: höchstens so viele Wörter + Fragezeichen am Ende.
_KURZE_FRAGE_MAX = 2
# Kurze Fragen, die KEIN Unverständnis sind (Gruß/Rückfrage) — sonst träfe
# Regel 2 jedes „¿qué tal?".
_KEIN_UNVERSTAENDNIS = {
    'es': ["qué tal", "que tal", "cómo estás", "como estas", "y tú", "y tu",
           "todo bien", "qué haces", "que haces"],
    'de': ["und du", "wie geht's", "wie gehts", "alles gut", "was machst du"],
    'zh': ["你好吗", "你呢", "怎么样"],
    '*': ["ok", "okay", "hola", "hi", "hello", "hallo", "你好"],
}


def _unverfaenglich(n: str, lang: str = None) -> bool:
    """Kurze Frage, die kein Unverständnis ist (Gruß, Rückfrage)?"""
    kern = n.rstrip('?').strip()
    for p in list(_KEIN_UNVERSTAENDNIS.get(lang or '', [])) + _KEIN_UNVERSTAENDNIS['*']:
        if kern == p:
            return True
    return False
# Regel 3: so viele Äußerungen in Folge ohne Anschluss → erkannt.
_VORBEI_SCHWELLE = 2


def _norm(text: str) -> str:
    t = (text or '').strip().lower()
    t = re.sub(r'[¿¡!.,;:…"\'«»()\[\]]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _woerter(text: str) -> set:
    """Wörter einer Äußerung (lateinisch: per Leerzeichen; CJK: einzelne Zeichen
    zählen als Wörter, weil dort kein Leerzeichen trennt)."""
    n = _norm(text)
    out = set()
    for w in n.split():
        if re.search(r'[一-鿿]', w):
            out.update(ch for ch in w if '一' <= ch <= '鿿')
        else:
            out.add(w.rstrip('?'))
    out.discard('')
    return out


def phrase_treffer(user_text: str, lang: str = None):
    """Welche explizite Phrase trifft? → Phrase oder None."""
    n = _norm(user_text)
    if not n:
        return None
    roh = (user_text or '').strip()
    if roh in ('?', '？'):
        return '?'
    kandidaten = list(_PHRASEN.get(lang or '', [])) + _PHRASEN['*']
    n_pad = ' ' + n + ' '
    if _unverfaenglich(n, lang):
        return None
    for p in kandidaten:
        if p == '?':
            continue
        if re.search(r'[一-鿿]', p):
            if p in n:
                return p
        elif (' ' + p + ' ') in n_pad:
            # Einzelwörter wie „que"/„was" nur, wenn die Äußerung GENAU das
            # ist („¿qué?", „was?") — sonst trifft jedes „was machst du" mit.
            if ' ' not in p and n.rstrip('?').strip() != p:
                continue
            return p
    return None


class Verstaendnis:
    """Zustand pro Session: ist Sasha gerade ›raus‹ (versteht nicht)?

    `pruefen()` wird nach jeder User-Äußerung aufgerufen und liefert ein Dict
    fürs Log/Devtool: erkannt (diese Äußerung), aktiv (Zustand), grund,
    uebergang ('an'/'aus'/None). Handeln tut (noch) niemand damit."""

    def __init__(self):
        self.aktiv = False
        self.vorbei = 0            # Äußerungen in Folge ohne Anschluss
        self.letzte_antwort = ''   # ihr letzter Text (für Regel 3 / Aus)

    def antwort_merken(self, text: str):
        self.letzte_antwort = text or ''

    def pruefen(self, user_text: str, lang: str = None, hits=None) -> dict:
        hits = list(hits or [])
        n = _norm(user_text)
        woerter = _woerter(user_text)
        ihre = _woerter(self.letzte_antwort)
        anschluss = bool(woerter & ihre)

        erkannt = False
        grund = None
        phrase = phrase_treffer(user_text, lang)
        if phrase is not None:
            erkannt, grund = True, f"phrase '{phrase}'"
        elif (user_text or '').strip().endswith(('?', '？')):
            if (len(n.rstrip('?').split()) <= _KURZE_FRAGE_MAX
                    and not _unverfaenglich(n, lang)):
                erkannt, grund = True, 'kurze rückfrage mit ?'

        # Regel 3: an ihr vorbei geredet?
        if not erkannt:
            if not hits and not anschluss and woerter:
                self.vorbei += 1
                if self.vorbei >= _VORBEI_SCHWELLE:
                    erkannt, grund = True, f'{self.vorbei}× ohne bekanntes wort und ohne anschluss'
            else:
                self.vorbei = 0
        else:
            self.vorbei = 0

        uebergang = None
        if erkannt and not self.aktiv:
            self.aktiv = True; uebergang = 'an'
        elif not erkannt and self.aktiv and (anschluss or hits):
            self.aktiv = False; uebergang = 'aus'
            grund = 'anschluss: ' + ', '.join(sorted(woerter & ihre)) if anschluss \
                else 'bekannte vokabel: ' + ', '.join(hits)

        return {'erkannt': erkannt, 'aktiv': self.aktiv, 'grund': grund,
                'uebergang': uebergang, 'hits': hits,
                'anschluss': sorted(woerter & ihre), 'vorbei': self.vorbei}
