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

# Letzte 100 Log-Zeilen, die NUR Internet-Traffic betreffen (Public-IPs /
# Public-Hostnames). Wird von core/net.py gespiegelt, wenn _is_internet(url)
# True ist. Sinn: ein dediziertes Panel im Dashboard, das ausschließlich
# zeigt was die ZENTRALE wirklich raus ins Internet schickt - alles Lokale
# und LAN bleibt im normalen stdout-Panel, läuft aber NICHT hier rein.
# Wenn dieses Panel leer bleibt, ist die "vollständig offline"-Garantie
# der ZENTRALE gerade tatsächlich eingehalten.
_internet_logs = deque(maxlen=100)

# Chat-History für die AI-Konversation.
# maxlen=50 Nachrichten → älteste fliegen raus wenn voll.
# Diese History wird 1:1 an Ollama geschickt – das Modell sieht
# immer den gesamten (hier: max 50 Nachrichten langen) Verlauf.
# WICHTIG: Wird NICHT auf Disk gespeichert – beim Neustart weg.
_chat_history = deque(maxlen=50)

# ── Externe Sensor-Trigger (über Webhook) ─────────────────────────────
# Seit der PC↔Pi-Topologie-Migration kommen Sensor-Signale nicht mehr
# nur lokal aus der Tastatur-Simulation (sensors.py), sondern auch via
# HTTP-POST von externen Quellen (Pi-Bridge → POST /api/sensor/<name>).
#
# Der Flask-Handler legt den Sensor-Namen hier rein, der Event-Loop in
# main.py drainet die Queue pro Tick und mapped sie auf Events.
#
# Bewusst eine Liste, nicht ein "letztes Pending"-Flag: schnelle
# Doppel-Trigger gehen sonst verloren. maxlen=100 als Sicherheitsnetz
# falls der Loop mal hängt – ältester Trigger fliegt dann raus.
_sensor_queue = deque(maxlen=100)


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
    """
    Fügt eine neue Log-Zeile an. Sichtbar an zwei Stellen:

      1. Dashboard-Terminal (cyberpunk-Panel in der Browser-UI),
         pollt /api/state und rendert _logs.
      2. stdout des start_local-Terminals - praktisch wenn man in der
         Shell live mitlesen will und das Browser-Fenster nicht offen
         hat oder wenn man einen bestimmten Logflow debugged. flush=True
         damit Zeilen nicht durch start_local.sh-Buffering verschluckt
         werden.
    """
    stamp = datetime.now().strftime("%H:%M:%S")
    with _lock:
        _logs.append({"text": line, "time": stamp})
    print(f"{stamp}  {line}", flush=True)


def push_internet_log(line: str):
    """
    Hängt eine Log-Zeile an den Internet-Traffic-Channel.

    Aufrufer: core/net.py, sobald eine Request-URL als Public-Ziel
    klassifiziert wurde (siehe net._is_internet). Die gleiche Zeile
    landet parallel über push_log() im normalen stdout - dieser Channel
    ist nur die zusätzliche, gefilterte Sicht für das Internet-Panel.

    KEIN print()-Side-Effect: das hat push_log() schon gemacht.
    """
    stamp = datetime.now().strftime("%H:%M:%S")
    with _lock:
        _internet_logs.append({"text": line, "time": stamp})


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


def queue_sensor(name: str):
    """
    Reiht einen extern eingegangenen Sensor-Trigger in die Queue.
    Aufrufer: ui/app.py POST /api/sensor/<name>.

    name: Sensor-Bezeichner wie "button", "light", "motion", "door".
          Validierung passiert im Flask-Handler – hier landet nur, was
          schon durch die Whitelist durch ist.
    """
    with _lock:
        _sensor_queue.append(name)


def drain_sensor_queue() -> list:
    """
    Gibt alle gequeueten Sensor-Trigger zurück und leert die Queue
    in einem Rutsch. Aufrufer: main.py einmal pro Tick.

    Kopiert atomar (Lock!) und gibt eine normale Liste raus – der
    Aufrufer kann frei darüber iterieren, ohne dass nebenher noch
    was reinkommt und die Reihenfolge verwirrt.
    """
    with _lock:
        items = list(_sensor_queue)
        _sensor_queue.clear()
        return items


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
            "events":        list(_events),
            "sensors":       dict(_sensors),
            "vocab":         _vocab,
            "logs":          list(_logs),
            "internet_logs": list(_internet_logs),
        }
