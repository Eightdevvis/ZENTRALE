# core/state.py
#
# Gemeinsamer In-Memory-State zwischen Event-Loop und Flask-UI.
#
# ZENTRALE läuft als ein Python-Prozess mit zwei gleichzeitigen Threads:
#   Thread 1 – Event-Loop (main.py): liest Sensoren, feuert Events
#   Thread 2 – Flask (app.py):       beantwortet HTTP-Anfragen des Browsers
#
# Beide Threads müssen auf dieselben Daten zugreifen (Logs, Events, etc.).
# Ohne Synchronisierung könnte Thread 1 gerade schreiben während Thread 2
# liest → inkonsistente Daten, schwer reproduzierbare Bugs (race conditions).
#
# Lösung: threading.Lock() als "Türsteher".
# Nur ein Thread darf gleichzeitig in den mit _lock geschützten Block –
# der andere wartet, bis der erste fertig ist.

import threading
from datetime import datetime
from collections import deque

# Der Lock ist ein Mutex (mutual exclusion).
# Er wird einmal erstellt und von allen Funktionen dieses Moduls geteilt.
_lock = threading.Lock()

# deque (double-ended queue) aus collections ist wie eine Liste,
# aber mit maxlen: wenn das Limit erreicht ist, fliegt automatisch
# das älteste Element raus. Kein manuelles Aufräumen nötig.
#
# maxlen=20 → wir merken uns die letzten 20 Events (für das Terminal-Log)
_events = deque(maxlen=20)

# Sensor-Status als einfaches Dict.
# Werte sind immer bool: True = aktiv, False = inaktiv.
_sensors = {"button": False, "light": False}

# Aktuelle Vokabel des Tages (None = noch nicht geladen).
# Wird beim Start aus vocab_mandarin.json befüllt.
_vocab = None

# Letzte 100 Log-Zeilen (stdout-Ausgaben, sichtbar im Dashboard-Terminal)
_logs = deque(maxlen=100)

# Chat-History für die AI-Konversation.
# maxlen=50 Nachrichten → älteste fliegen raus wenn voll.
# Diese History wird 1:1 an Ollama geschickt – das Modell sieht
# immer den gesamten (hier: max 50 Nachrichten langen) Verlauf.
# WICHTIG: Wird NICHT auf Disk gespeichert – beim Neustart weg.
_chat_history = deque(maxlen=50)


def push_event(name: str):
    """Fügt ein neues Event an den Anfang der Event-Liste."""
    with _lock:
        _events.appendleft({          # appendleft = neuestes Event zuerst
            "name": name,
            "time": datetime.now().strftime("%H:%M:%S"),
        })


def set_sensor(name: str, value: bool):
    """Setzt den aktuellen Status eines Sensors (True/False)."""
    with _lock:
        _sensors[name] = value


def set_vocab(word):
    """
    Setzt die aktuelle Vokabel.
    word: {"word": "你好", "pinyin": "nǐ hǎo"} oder None
    """
    global _vocab
    with _lock:
        _vocab = word


def push_log(line: str):
    """Fügt eine neue Log-Zeile an (erscheint im Dashboard-Terminal)."""
    with _lock:
        _logs.append({
            "text": line,
            "time": datetime.now().strftime("%H:%M:%S"),
        })


def push_chat_message(role: str, content: str):
    """
    Fügt eine Nachricht zur Chat-History hinzu.

    role:    "user" (Mensch) oder "assistant" (AI)
    content: der Nachrichtentext

    Die History wächst chronologisch (älteste zuerst) – genau so
    wie Ollama sie erwartet: erst alle alten Nachrichten, dann die neue.
    """
    with _lock:
        _chat_history.append({"role": role, "content": content})


def get_chat_history() -> list:
    """
    Gibt eine Kopie der gesamten Chat-History zurück.

    Wir geben eine Kopie (list()) zurück, nicht die deque selbst.
    So kann der Aufrufer die Liste gefahrlos weiterverarbeiten,
    auch wenn ein anderer Thread gleichzeitig etwas in die deque schreibt.
    """
    with _lock:
        return list(_chat_history)


def clear_chat_history():
    """Löscht die gesamte Chat-History (z.B. bei /clear im Chat)."""
    with _lock:
        _chat_history.clear()


def get_snapshot() -> dict:
    """
    Gibt einen aktuellen Schnappschuss des gesamten States zurück.

    Wird von Flask alle 1s an den Browser geliefert (/api/state).
    Auch hier: alles kopieren (list/dict) damit der Lock
    nur kurz gehalten werden muss und niemand auf einem
    "lebenden" Objekt weiterarbeitet.
    """
    with _lock:
        return {
            "events":  list(_events),
            "sensors": dict(_sensors),
            "vocab":   _vocab,
            "logs":    list(_logs),
        }
