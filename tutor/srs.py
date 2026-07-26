# tutor/srs.py
#
# Echte, TAGE-skalige Spaced Repetition fürs KI-GESPRÄCH (nicht das Session-Drill).
# Nutzt die Open-Source-Engine FSRS (py-fsrs, MIT) — Ankis aktueller Algorithmus,
# akademisch validiert — statt selbstgebauter Intervalle.
#
# ── Arbeitsteilung (siehe memory/tutor_system.md) ───────────────────────
#   • room.py-Drill  = WORKING MEMORY: schnelle Basis, Abstände in KARTEN
#     (expanding-retrieval-Ladder 3/7/14/25). Baut den Grundwortschatz auf.
#   • srs.py (hier)   = LANGZEIT-RETENTION: Abstände in TAGEN. Gelernte Wörter
#     werden geseedet; redest du mit der Persona, zieht sie FÄLLIGE Wörter ran,
#     und dein Recall bewertet sie (Good/Again → neues Fälligkeitsdatum).
#
# Speicher pro Sprache (Laufzeit, gitignored — wie vocab.json/game.json):
#     data/<lang>/fsrs.json   {wort: Card.to_dict()}  (state/stability/difficulty/
#                             due/last_review …)
#
# Soft-Import: fehlt `fsrs` auf einem Knoten, sind ALLE Funktionen No-ops — der
# Tutor läuft normal weiter, nur ohne Langzeit-SR (available() sagt es an).

import json
import os
from threading import Lock
from datetime import datetime, timezone

try:
    from fsrs import Scheduler, Card, Rating
    _OK = True
except Exception:                       # Lib nicht installiert → Feature still aus
    _OK = False

_lock = Lock()
_DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
_sched = None

_RATINGS = {}
if _OK:
    _RATINGS = {'again': Rating.Again, 'hard': Rating.Hard,
                'good': Rating.Good, 'easy': Rating.Easy}


def available() -> bool:
    """Ist die FSRS-Engine da? (Sonst sind alle Funktionen No-ops.)"""
    return _OK


def _scheduler():
    global _sched
    if _sched is None:
        _sched = Scheduler()            # Default-Parameter (bewährte FSRS-Gewichte)
    return _sched


def _lang(lang: str = None) -> str:
    if lang:
        return lang
    try:
        from . import session
        return session.active_lang()
    except Exception:
        return 'zh'


def _file(lang: str = None) -> str:
    d = os.path.join(_DATA_ROOT, _lang(lang))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'fsrs.json')


def _load(lang: str = None) -> dict:
    p = _file(lang)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict, lang: str = None):
    try:
        with open(_file(lang), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _due_dt(raw: dict):
    """Fälligkeitsdatum aus einem gespeicherten Card-Dict (ISO-String → aware dt)."""
    due = raw.get('due')
    if isinstance(due, str):
        dt = datetime.fromisoformat(due)
    elif isinstance(due, datetime):
        dt = due
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ensure(word: str, lang: str = None) -> bool:
    """Wort ins Langzeit-SR aufnehmen (falls noch nicht drin). True = neu angelegt.
    No-op ohne fsrs / ohne Wort. Ein frisches Wort ist sofort fällig (Learning)."""
    word = (word or '').strip()
    if not (_OK and word):
        return False
    with _lock:
        d = _load(lang)
        if word in d:
            return False
        # Frisch gedrillt = ein erster erfolgreicher Kontakt → GLEICH einmal „Good"
        # verbuchen, damit die Karte NICHT sofort fällig ist. Sonst wären nach dem
        # Assessment alle Kern-Wörter auf einmal fällig und get_due_reviews flutet
        # die erste Konversation (qwen paukt sie in einer Schleife durch).
        try:
            card, _ = _scheduler().review_card(Card(), Rating.Good, review_datetime=_now())
        except Exception:
            card = Card()
        d[word] = card.to_dict()
        _save(d, lang)
    return True


def review(word: str, rating: str = 'good', lang: str = None) -> dict:
    """Recall eines Worts verbuchen (rating: again|hard|good|easy) → FSRS terminiert
    neu. Legt die Karte an, falls neu. No-op ohne fsrs. Gibt den neuen Stand zurück."""
    word = (word or '').strip()
    if not (_OK and word):
        return {}
    r = _RATINGS.get(str(rating).lower(), Rating.Good)
    with _lock:
        d = _load(lang)
        raw = d.get(word)
        try:
            card = Card.from_dict(raw) if raw else Card()
            card, _ = _scheduler().review_card(card, r, review_datetime=_now())
            d[word] = card.to_dict()
            _save(d, lang)
            due = _due_dt(d[word])
        except Exception:
            return {}
    return {'word': word,
            'due': due.isoformat() if due else None,
            'due_in_days': round((due - _now()).total_seconds() / 86400, 2) if due else None,
            'state': int(getattr(card.state, 'value', card.state))}


def due_words(lang: str = None, limit: int = None) -> list:
    """Aktuell fällige Wörter (due ≤ jetzt), am längsten überfällig zuerst.
    Für die Persona: WAS sie im Gespräch auffrischen sollte. No-op ohne fsrs."""
    if not _OK:
        return []
    now = _now()
    with _lock:
        d = _load(lang)
    due = []
    for w, raw in d.items():
        dt = _due_dt(raw) if isinstance(raw, dict) else None
        if dt is not None and dt <= now:
            due.append((dt, w))
    due.sort(key=lambda t: t[0])
    words = [w for _, w in due]
    return words[:limit] if limit else words


def stats(lang: str = None) -> dict:
    """Kurzstatistik (für UI/Log). KEIN AI-Tool."""
    if not _OK:
        return {'available': False, 'tracked': 0, 'due': 0}
    due = len(due_words(lang))
    with _lock:
        d = _load(lang)
    return {'available': True, 'tracked': len(d), 'due': due}
