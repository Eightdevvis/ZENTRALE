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
import time
from datetime import datetime
from collections import deque

# Der Lock ist ein Mutex (mutual exclusion).
# Er wird einmal erstellt und von allen Funktionen dieses Moduls geteilt.
_lock = threading.Lock()

# Prozess-Start (monotone Uhr) – Basis fuer die Backend-Uptime im Dashboard.
# state.py wird beim Prozessstart importiert, also ist das ~der Start des
# Backends. monotonic() ist immun gegen Systemzeit-Spruenge (NTP/Zeitzone).
_started = time.monotonic()

# deque (double-ended queue) aus collections ist wie eine Liste,
# aber mit maxlen: wenn das Limit erreicht ist, fliegt automatisch
# das älteste Element raus. Kein manuelles Aufräumen nötig.
#
# maxlen=20 → wir merken uns die letzten 20 Events (für das Terminal-Log)
_events = deque(maxlen=20)

# Sensor-Status als einfaches Dict.
# Werte sind immer bool: True = aktiv, False = inaktiv.
_sensors = {"button": False, "light": False}

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

# ── Offene Kalender-Alarme (Alarm-Kanal) ──────────────────────────────
# Strukturierte Alarme/Warnungen aus dem Kalender (Reise-KONFLIKT, Pflicht-
# ABSAGEN, Tages-Kollisionen). Bewusst eine FLACHE LISTE mit Replace-Semantik,
# KEIN Append-Deque: Python rechnet nach jeder Kalenderänderung (+ periodisch)
# das KOMPLETTE Alarm-Set neu und ersetzt es hier ganz - so sammeln sich keine
# Dubletten und gelöste Alarme verschwinden von selbst.
#
# Dieser Kanal ersetzt das alte Inline-Mischen der ⚠-Zeilen in die
# read_calendar-Ausgabe: dort kaperten sie die Aufmerksamkeit des kleinen
# Modells. Jetzt fließen sie randständig in zwei Senken: (a) das Dashboard
# (Warndreieck-Ecke im KI-Canvas, via get_snapshot) und (b) den KI-System-
# Prompt (ai._alarm_prompt, "offene Erinnerungen"). Quelle: kalender.open_alarms.
# Form je Alarm: {"id": <stabil>, "kind": str, "text": str}.
_alarms: list = []


def set_alarms(alarms: list):
    """
    Ersetzt das komplette Alarm-Set (Replace, nicht Append).

    Aufrufer: kalender.open_alarms-Recompute (nach jeder Mutation via _save_raw,
    beim Boot und periodisch aus dem main.py-Loop). Ein voll neu gerechnetes Set
    kommt rein und überschreibt das alte - gelöste Konflikte sind damit sofort
    weg, neue da. Thread-safe, weil der Recompute aus verschiedenen Threads
    kommt (Chat-Thread beim Schreiben, Event-Loop-Thread periodisch).
    """
    global _alarms
    with _lock:
        _alarms = list(alarms)


def get_alarms() -> list:
    """Aktuelles Alarm-Set (Kopie). Für get_snapshot + ai._alarm_prompt."""
    with _lock:
        return list(_alarms)


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

# ── Pi-Telemetrie (Push vom Pi) ───────────────────────────────────────
# Das Backend laeuft auf dem PC, der Pi-FS ist read-only. Der Pi kann
# seine Telemetrie (CPU/Temp/RAM/SD) also nicht lokal anzeigen - er POSTet
# sie periodisch an /api/telemetry/pi. Wir halten hier nur den LETZTEN
# Stand plus den Empfangs-Zeitpunkt (monotone Uhr), damit das Dashboard
# erkennen kann ob der Pi noch frisch sendet oder offline ist (stale).
_pi_telemetry = {"data": None, "ts": 0.0}


def set_pi_telemetry(data: dict):
    """Letzten Pi-Telemetrie-Push speichern (mit Empfangs-Zeitstempel)."""
    with _lock:
        _pi_telemetry["data"] = data
        _pi_telemetry["ts"] = time.monotonic()


def get_pi_telemetry() -> dict:
    """
    Letzte Pi-Telemetrie + Alter in Sekunden. Gibt {} zurueck wenn der Pi
    noch nie gesendet hat. age_s erlaubt dem Frontend die Stale-Anzeige.
    """
    with _lock:
        data = _pi_telemetry["data"]
        ts = _pi_telemetry["ts"]
    if data is None:
        return {}
    return {**data, "age_s": round(time.monotonic() - ts, 1)}


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


# ── Erlaubnis-Rückfrage (KI ↔ Mensch, blockierend) ────────────────────
# Wenn die KI ein bestätigungspflichtiges Tool ruft (PERMISSION_REQUIRED_
# TOOLS in ai.py), fängt das Backend den Call ab und hält den Tool-Loop
# MITTEN im Zug an, bis Sasha Ja/Nein klickt. Technisch sind das zwei
# verschiedene HTTP-Requests in zwei verschiedenen Threads:
#
#   Thread A – der offene /api/chat-Stream. Sein Generator blockiert in
#              wait_permission() und hält die SSE-Verbindung offen.
#   Thread B – ein frischer POST /api/permission_answer mit dem Klick.
#              Er ruft answer_permission() und WECKT Thread A auf.
#
# Das Bindeglied ist ein threading.Event – ein Ein/Aus-Signal zwischen
# Threads. .wait() blockiert bis ein anderer Thread .set() ruft (oder bis
# der Timeout greift). Das funktioniert nur, weil Flask multi-threaded
# läuft (app.run(threaded=True)) – sonst würde der blockierte Stream den
# Antwort-Request gar nicht erst durchlassen und wir hätten ein Deadlock.
#
# Nur EINE offene Frage gleichzeitig (Kiosk = ein Mensch, ein Chat), also
# reicht ein einzelnes geteiltes Event + ein Antwort-Slot.
_perm_event   = threading.Event()
_perm_answer  = None           # gewähltes Knopf-Label / None (noch keine Antwort)
_perm_options = ["ja", "nein"] # aktuell angebotene Knopf-Labels
_perm_default = "nein"         # Rückgabe bei Timeout (kein Klick)


def request_permission(options=None, timeout_default="nein"):
    """
    Macht das Erlaubnis-Event scharf für eine neue Frage.

    Aufrufer: ai.chat_stream, direkt bevor es das permission-Event yieldet
    und in wait_permission() blockiert. Setzt einen evtl. alten Antwort-
    Rest zurück (clear), damit eine verspätete Antwort der letzten Frage
    nicht fälschlich diese hier beantwortet.

    options: Liste der angebotenen Knopf-Labels. None → ["ja","nein"]
             (das Auto-Gate der Schreib-Tools). Das KI-Tool `frage_knopf`
             gibt hier eigene Labels rein (z.B. ["Deutsch","Englisch"]).
    timeout_default: was wait_permission bei Timeout zurückgibt. Für das
             Gate "nein" (sicher: keine Antwort erlaubt nie eine Aktion),
             für freie Fragen ein neutrales Sentinel.
    """
    global _perm_answer, _perm_options, _perm_default
    with _lock:
        _perm_answer  = None
        _perm_options = list(options) if options else ["ja", "nein"]
        _perm_default = timeout_default
    _perm_event.clear()


def get_permission_options() -> list:
    """Aktuell angebotene Knopf-Labels (für die Antwort-Validierung in app.py)."""
    with _lock:
        return list(_perm_options)


def answer_permission(answer: str):
    """
    Liefert das gewählte Knopf-Label und weckt den wartenden chat_stream.

    Aufrufer: ui/app.py POST /api/permission_answer (anderer Thread).
    answer: eines der Labels aus get_permission_options() (im Flask-Handler
    schon gegen die angebotenen Optionen validiert).
    """
    global _perm_answer
    with _lock:
        _perm_answer = answer
    _perm_event.set()   # weckt den .wait() in wait_permission()


def wait_permission(timeout: float = 180.0) -> str:
    """
    Blockiert bis answer_permission() kommt – oder bis der Timeout greift.

    Gibt das gewählte Knopf-Label zurück. Timeout (kein Klick) liefert den
    bei request_permission gesetzten timeout_default (beim Gate "nein" -
    keine Antwort darf NIE versehentlich eine Aktion erlauben). 180 s =
    großzügig, der Mensch soll in Ruhe lesen können, aber der Thread hängt
    nicht ewig wenn der Tab zugeht.
    """
    got = _perm_event.wait(timeout)
    with _lock:
        if not got:
            return _perm_default
        return _perm_answer if _perm_answer is not None else _perm_default


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
            "logs":          list(_logs),
            "internet_logs": list(_internet_logs),
            "uptime_s":      round(time.monotonic() - _started),
            "alarms":        list(_alarms),
        }
