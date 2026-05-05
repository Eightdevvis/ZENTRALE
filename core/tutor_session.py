# core/tutor_session.py
#
# Verwaltet den State einer aktiven Sprachtutor-Session.
#
# ── Was ist eine Session? ─────────────────────────────────────────────
# Eine Session beginnt wenn Presence erkannt wird (oder manuell per 'T').
# Die KI begrüßt zuerst auf Mandarin. Der User antwortet (per Mikrofon +
# Space-Taste). Das geht hin und her bis die Session manuell beendet wird.
#
# ── Thread-Safety ─────────────────────────────────────────────────────
# _active und _history werden von Flask (Browser-Requests) und dem
# Event-Loop (brain.py) gleichzeitig gelesen/geschrieben → Lock nötig.
#
# ── Tutor-System-Prompt ───────────────────────────────────────────────
# Komplett anderer Prompt als der reguläre Chat – die KI weiß hier dass
# sie Sprachlehrerin ist und nutzt die Tutor-Tools (get_confirmed_vocab etc.)

from threading import Lock
from collections import deque
import ai
import tutor

_lock    = Lock()
_active  = False
_history = deque(maxlen=100)  # Tutor-Gesprächsverlauf (separat vom Chat-History)

# ── Tutor-System-Prompt ───────────────────────────────────────────────
# Wird statt _SYSTEM_PROMPT aus ai.py verwendet wenn Tutor aktiv ist.
_TUTOR_PROMPT = (
    "Du bist Mandarin-Sprachtutor für Sasha, eine Deutsche die Mandarin lernt. "
    "Deine Aufgabe: lockeres, natürliches Smalltalk auf Mandarin – wie ein echter "
    "Gesprächspartner im Alltag, nicht wie ein Lehrer vor einer Klasse. "
    "\n\n"
    "ABLAUF ZU SESSION-BEGINN: "
    "Ruf get_confirmed_vocab() und get_testing_vocab() auf um zu wissen welche Wörter "
    "Sasha kennt. Falls testing_vocab weniger als 10 Einträge hat: introduce_new() aufrufen. "
    "\n\n"
    "VOKABEL-REGELN: "
    "80% der Zeit nur bestätigte Vokabeln (confirmed=True) verwenden. "
    "20% der Zeit Wörter aus dem Testing-Pool einstreuen. "
    "Wenn Sasha ein Wort korrekt und sinnvoll in einem Satz nutzt: increment_correct_use() aufrufen. "
    "\n\n"
    "SPRACH-REGELN: "
    "Hauptsächlich auf Mandarin schreiben. "
    "Neue Wörter immer mit Pinyin in Klammern: 谢谢 (xiè xie). "
    "Sätze kurz halten – Sasha ist Anfängerin. "
    "Wenn Sasha auf Deutsch fragt oder etwas nicht versteht: kurz auf Deutsch erklären, "
    "dann weiter auf Mandarin. "
    "\n\n"
    "CHARAKTER: Entspannt, geduldig, kein übertriebenes Lob. Reagiere natürlich. "
    "Keine Bewertungen wie 'Super gemacht!' – einfach normal weiterreden. "
    "Die erste Nachricht: kurze, einfache Begrüßung auf Mandarin."
)


def is_active() -> bool:
    """Gibt zurück ob gerade eine Tutor-Session läuft."""
    with _lock:
        return _active


def activate():
    """
    Aktiviert den Session-State (wird von brain.py aufgerufen wenn TUTOR_START Event kommt).
    Setzt _active = True und leert die History für eine frische Session.
    Die KI-Begrüßung kommt separat über /api/tutor/start.
    """
    global _active, _history
    with _lock:
        _active  = True
        _history = deque(maxlen=100)


def deactivate():
    """Beendet die Session. History bleibt für eventuelle Nachbetrachtung."""
    global _active
    with _lock:
        _active = False


def get_history() -> list:
    """Gibt die aktuelle Gesprächshistory als Liste zurück (thread-safe)."""
    with _lock:
        return list(_history)


def push_message(role: str, content: str):
    """Fügt eine Nachricht zur Session-History hinzu."""
    with _lock:
        _history.append({"role": role, "content": content})


def respond_stream(user_text: str = None):
    """
    Generator: schickt die aktuelle History (+ optionale neue User-Nachricht)
    an Mistral mit dem Tutor-System-Prompt und Tutor-Tools.
    Yieldet Token für Token für das Browser-Streaming.

    user_text=None bedeutet: KI startet das Gespräch (Session-Beginn).
    """
    if user_text is not None:
        push_message("user", user_text)

    history = get_history()

    # ai.chat_stream mit Tutor-Prompt + Tutor-Tools aufrufen.
    # Wir nutzen die gleiche Infrastruktur wie der reguläre Chat,
    # aber mit anderem System-Prompt und anderen Tools.
    full_response = []

    for token in ai.chat_stream(
        messages=history,
        system=_TUTOR_PROMPT,
        tools=tutor.TUTOR_TOOLS,
        tool_executor=tutor.execute_tool,
    ):
        full_response.append(token)
        yield token

    # Komplette Antwort in History speichern
    push_message("assistant", "".join(full_response))
