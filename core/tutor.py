# core/tutor.py
#
# Vokabel-Tools für den Mandarin-Sprachtutor.
#
# Diese Funktionen werden als AI-Tools (über ai.py TOOLS-Liste) der KI bereitgestellt.
# Mistral kann sie während einer Tutor-Session aufrufen um die Vokabelliste zu lesen
# und zu schreiben.
#
# ── Konzept: confirmed vs. testing ───────────────────────────────────
#   confirmed = False  → Wort wird gerade gelernt (20%-Pool)
#   confirmed = True   → Wort ist gefestigt (80%-Pool)
#
# ── Auto-Confirm-Schwelle ─────────────────────────────────────────────
#   correct_use >= CONFIRM_THRESHOLD → confirmed wird automatisch auf True gesetzt
#
# ── Wer ruft was auf ─────────────────────────────────────────────────
#   KI zu Session-Beginn:  get_confirmed_vocab() + get_testing_vocab()
#   KI nach korrekter Nutzung: increment_correct_use(word)
#   KI wenn testing_vocab < 10 neue Wörter hat: introduce_new(word, pinyin)

import json
import os
from threading import Lock

_VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'vocab_mandarin.json')
_lock       = Lock()  # Mehrere Threads (Flask + Event-Loop) könnten gleichzeitig lesen/schreiben

# Ab dieser Anzahl korrekter Verwendungen gilt ein Wort als bestätigt.
CONFIRM_THRESHOLD = 5


def _load_raw() -> list:
    """Lädt die Vokabelliste von Disk (ohne Lock – nur intern nutzen)."""
    if not os.path.exists(_VOCAB_FILE):
        return []
    with open(_VOCAB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_raw(entries: list):
    """Schreibt die Vokabelliste auf Disk (ohne Lock – nur intern nutzen)."""
    with open(_VOCAB_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent='\t', ensure_ascii=False)


def get_confirmed_vocab() -> str:
    """
    Gibt alle bestätigten Vokabeln zurück (confirmed=True).
    KI soll diese ~80% der Zeit im Gespräch verwenden.
    Rückgabe: formatierter String für den AI-Prompt.
    """
    with _lock:
        entries = _load_raw()
    confirmed = [e for e in entries if e.get('confirmed')]
    if not confirmed:
        return "Noch keine bestätigten Vokabeln vorhanden."
    lines = [f"{e['word']} ({e['pinyin']})" for e in confirmed]
    return "Bestätigte Vokabeln (80%-Pool):\n" + "\n".join(lines)


def get_testing_vocab() -> str:
    """
    Gibt alle Vokabeln zurück die noch nicht bestätigt sind (confirmed=False).
    KI soll diese ~20% der Zeit einstreuen.
    Rückgabe: formatierter String + Anzahl (wichtig für introduce_new-Entscheidung).
    """
    with _lock:
        entries = _load_raw()
    testing = [e for e in entries if not e.get('confirmed')]
    count   = len(testing)
    if count == 0:
        return "testing_vocab leer (count=0) – introduce_new aufrufen!"
    lines = [f"{e['word']} ({e['pinyin']}) – {e['correct_use']}x korrekt genutzt" for e in testing]
    return f"Testing-Vokabeln (20%-Pool, count={count}):\n" + "\n".join(lines)


def increment_correct_use(word: str) -> str:
    """
    Erhöht den correct_use-Zähler für ein Wort um 1.
    Wenn correct_use >= CONFIRM_THRESHOLD: Wort wird automatisch als confirmed markiert.

    KI soll dies aufrufen wenn die Lernende das Wort korrekt und sinnvoll verwendet hat.
    Rückgabe: Bestätigungsstring (den die KI sieht, aber nicht vorlesen muss).
    """
    with _lock:
        entries = _load_raw()
        for entry in entries:
            if entry['word'] == word:
                entry['correct_use'] += 1
                # Auto-confirm wenn Schwelle erreicht
                if entry['correct_use'] >= CONFIRM_THRESHOLD and not entry['confirmed']:
                    entry['confirmed'] = True
                    _write_raw(entries)
                    return f"✓ '{word}' jetzt BESTÄTIGT (nach {entry['correct_use']}x korrekter Nutzung)"
                _write_raw(entries)
                return f"✓ correct_use für '{word}' → {entry['correct_use']}/{CONFIRM_THRESHOLD}"
        return f"[Wort '{word}' nicht in der Vokabelliste gefunden]"


def introduce_new(word: str, pinyin: str) -> str:
    """
    Fügt ein neues Wort zur Vokabelliste hinzu (als testing, correct_use=0).
    KI soll dies aufrufen wenn get_testing_vocab() weniger als 10 Wörter zurückgibt.

    word:   chinesische Zeichen, z.B. "你好"
    pinyin: Lautschrift mit Tönen, z.B. "nǐ hǎo"
    Rückgabe: Bestätigungsstring.
    """
    with _lock:
        entries = _load_raw()
        # Duplikate verhindern
        if any(e['word'] == word for e in entries):
            return f"['{word}' bereits in der Vokabelliste vorhanden]"
        entries.append({
            'word':        word,
            'pinyin':      pinyin,
            'correct_use': 0,
            'confirmed':   False,
        })
        _write_raw(entries)
    return f"✓ Neues Wort hinzugefügt: '{word}' ({pinyin})"


def get_vocab_stats() -> str:
    """
    Gibt eine kurze Statistik über den Lernfortschritt zurück.
    Für das Dashboard und für die KI bei Session-Beginn nützlich.
    """
    with _lock:
        entries = _load_raw()
    total     = len(entries)
    confirmed = sum(1 for e in entries if e.get('confirmed'))
    testing   = total - confirmed
    return f"Vokabeln gesamt: {total} | bestätigt: {confirmed} | im Testing: {testing}"


# ── Tool-Definitionen für ai.py ───────────────────────────────────────
# Diese Liste wird in ai.py in die TOOLS-Liste eingehängt wenn der Tutor-Modus aktiv ist.
# Im normalen Chat-Modus sind die Tutor-Tools NICHT verfügbar (KI nicht verwirren).

TUTOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name":        "get_confirmed_vocab",
            "description": "Gibt alle bestätigten Mandarin-Vokabeln zurück. Zu Session-Beginn aufrufen um den 80%-Pool zu kennen.",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "get_testing_vocab",
            "description": "Gibt alle Vokabeln im Testing-Pool zurück (noch nicht bestätigt). Zu Session-Beginn aufrufen. Falls count < 10: introduce_new aufrufen.",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "increment_correct_use",
            "description": "Erhöht den Zähler für ein korrekt verwendetes Wort. Aufrufen wenn die Lernende das Wort korrekt und sinnvoll in einem Satz genutzt hat.",
            "parameters":  {
                "type":       "object",
                "properties": {
                    "word": {
                        "type":        "string",
                        "description": "Das chinesische Wort (Zeichen), z.B. '你好'",
                    }
                },
                "required": ["word"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "introduce_new",
            "description": "Fügt ein neues Wort zum Testing-Pool hinzu. Nur aufrufen wenn get_testing_vocab weniger als 10 Wörter zurückgibt.",
            "parameters":  {
                "type":       "object",
                "properties": {
                    "word": {
                        "type":        "string",
                        "description": "Chinesisches Zeichen, z.B. '谢谢'",
                    },
                    "pinyin": {
                        "type":        "string",
                        "description": "Pinyin mit Tönen, z.B. 'xiè xie'",
                    },
                },
                "required": ["word", "pinyin"],
            },
        },
    },
]


# ── Tool-Dispatcher für ai.py ─────────────────────────────────────────
# ai.py ruft dies auf wenn Mistral ein Tutor-Tool aufruft.

def execute_tool(name: str, args: dict) -> str:
    """Führt ein Tutor-Tool aus und gibt das Ergebnis zurück."""
    if name == "get_confirmed_vocab":
        return get_confirmed_vocab()
    elif name == "get_testing_vocab":
        return get_testing_vocab()
    elif name == "increment_correct_use":
        return increment_correct_use(args.get("word", ""))
    elif name == "introduce_new":
        return introduce_new(args.get("word", ""), args.get("pinyin", ""))
    else:
        return f"[Unbekanntes Tutor-Tool: {name}]"
