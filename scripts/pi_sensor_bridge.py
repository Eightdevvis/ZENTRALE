#!/usr/bin/env python3
# =============================================================================
# pi_sensor_bridge.py
# -----------------------------------------------------------------------------
# ZENTRALE Sensor-Bridge fuer den Pi.
#
# Seit der PC<->Pi-Topologie-Migration laeuft das schwere Backend
# (Flask + AI + Whisper + TTS) auf dem PC. Der Pi ist nur noch Anzeige-
# Klient + Hardware-Bruecke. Echte Sensoren (Tuersensor, PIR, Buttons)
# haengen aber am Pi-GPIO – dieses Skript liest sie und pusht den
# Trigger via HTTP an das PC-Backend:
#
#   Pi (GPIO/Keyboard)  ->  pi_sensor_bridge.py  ->  POST /api/sensor/<name>
#                                                       |
#                                                       v
#                                               PC core/main.py
#                                                       |
#                                               state.queue_sensor()
#                                                       |
#                                               event_queue -> brain -> actions
#
# Quellen:
#   - Tastatur (keyboard-Library, braucht root) – fuer Demo/Test, gleiche
#     Belegung wie auf dem PC in core/sensors.py.
#   - GPIO (gpiozero) – Skelett-Kommentar unten. Aktivieren, sobald die
#     erste Hardware (Reed-Switch an der Haustuer, PIR im Flur) physisch
#     angeschlossen ist.
#
# Konfig via Umgebungsvariablen:
#   ZENTRALE_BACKEND_URL  Wo das PC-Backend lauscht.
#                         Default http://localhost:5000 (Solo-Test am PC).
#                         Auf dem Pi sinnvoll z.B.
#                           http://10.117.205.127:5000
#                         Bei Hotspot/IP-Wechsel: EnvironmentFile in der
#                         systemd-Unit aktualisieren (deploy/
#                         pi_sensor_bridge.service).
#   ZENTRALE_BRIDGE_POLL  Sekunden zwischen Polls. Default 0.2.
#   ZENTRALE_BRIDGE_KB    "1" = Tastatur-Reader an, "0" = aus. Default "1".
#   ZENTRALE_TELEMETRY        "1" = Telemetrie-Push an, "0" = aus. Default "1".
#   ZENTRALE_TELEMETRY_POLL   Sekunden zwischen Telemetrie-Pushes. Default 30.
#
# Telemetrie: der Pi POSTet zusaetzlich periodisch CPU/Temp/RAM/SD an
#   POST /api/telemetry/pi  (das Backend kann der Pi nicht selbst anzeigen,
#   FS read-only). Werte kommen aus core/host_metrics.py (dependency-frei).
#
# Manueller Aufruf (lokal testen, ggf. mit sudo wegen keyboard-Library):
#   ZENTRALE_BACKEND_URL=http://10.117.205.127:5000 \
#     sudo /opt/zentrale/.venv/bin/python scripts/pi_sensor_bridge.py
#
# Als systemd-Service: siehe deploy/pi_sensor_bridge.service.
# =============================================================================

import os
import sys
import time

# keyboard ist optional – ohne root throwt das Modul beim ersten Aufruf,
# ohne Library garnicht importierbar. Beide Faelle muessen leise bleiben,
# damit GPIO-only-Setups (Pi in production) nicht zerbrechen.
try:
    import keyboard
except Exception:
    keyboard = None

# requests ist nicht optional – ohne HTTP-Client kann die Bridge nichts
# Sinnvolles tun, also lieber laut sterben als still kaputt sein.
try:
    import requests
except Exception as e:
    print(f"FATAL: requests-Library fehlt: {e}", file=sys.stderr)
    sys.exit(1)

# host_metrics liegt in core/ (dependency-frei). Wir legen core/ auf den
# Suchpfad – genauso wie ui/app.py das macht. Optional: wenn der Import
# scheitert (alter Checkout o.ae.), laeuft die Bridge ohne Telemetrie weiter.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
try:
    import host_metrics
except Exception as e:
    host_metrics = None
    print(f"HINWEIS: host_metrics nicht importierbar – Telemetrie aus: {e}", flush=True)


# ── Konfig ───────────────────────────────────────────────────────────
BACKEND_URL = os.environ.get("ZENTRALE_BACKEND_URL", "http://localhost:5000")
POLL_SEC    = float(os.environ.get("ZENTRALE_BRIDGE_POLL", "0.2"))
KB_ENABLED  = os.environ.get("ZENTRALE_BRIDGE_KB", "1") == "1"
TELEMETRY_ENABLED = os.environ.get("ZENTRALE_TELEMETRY", "1") == "1" and host_metrics is not None
TELEMETRY_POLL    = float(os.environ.get("ZENTRALE_TELEMETRY_POLL", "30"))

# Sensor-Name -> Taste fuer die Tastatur-Simulation.
# Muss synchron bleiben mit:
#   ui/app.py        _ALLOWED_SENSORS
#   core/main.py     _SENSOR_TO_EVENT
# Wenn ein neuer Sensor dazukommt: an allen drei Stellen ergaenzen.
KEYBOARD_MAP = {
    "button": "b",
    "light":  "l",
    "motion": "m",
    "door":   "h",
}

# Edge-Detection-Zustand: nur beim Uebergang "nicht gedrueckt" ->
# "gedrueckt" wird gefeuert. Sonst pusht eine halbe Sekunde Tastendruck
# ueber den 0.2s-Polltakt 2-3 POSTs ans Backend.
_kb_last_state = {name: False for name in KEYBOARD_MAP}


# ── HTTP-Push ────────────────────────────────────────────────────────
def _post_sensor(name: str):
    """
    Pusht einen Sensor-Trigger an das PC-Backend.
    Fehler werden geloggt aber nicht propagiert – die Bridge soll auch
    dann weiter laufen, wenn das Backend kurz weg ist (Restart, Reboot).
    """
    url = f"{BACKEND_URL}/api/sensor/{name}"
    try:
        # timeout=2: lange genug fuer Hotspot-Wackler, kurz genug damit
        # ein totes Backend nicht den ganzen Poll-Loop blockiert.
        r = requests.post(url, timeout=2, json={})
        print(f"PUSH {name} -> {url} = {r.status_code}", flush=True)
    except Exception as e:
        print(f"PUSH {name} -> {url} FAIL: {e}", flush=True)


# ── Telemetrie-Push ──────────────────────────────────────────────────
def _build_telemetry():
    """
    Baut den Pi-Telemetrie-Block in der Shape, die das Dashboard erwartet
    (je Metrik ein .v). Der Pi hat keine nvidia-GPU → nur CPU/Temp/RAM/SD.
    Disk ist '/' = die SD-Karte. None-Werte bleiben None (Frontend zeigt '–').
    """
    ram  = host_metrics.mem_percent()       # (pct, used_gb, total_gb) | None
    disk = host_metrics.disk_percent("/")   # (pct, used_gb, total_gb) | None
    return {
        "cpu":  {"v": host_metrics.cpu_percent()},
        "temp": {"v": host_metrics.temp_c()},
        "ram":  {"v": ram[0]  if ram  else None, "used": ram[1]  if ram  else None, "total": ram[2]  if ram  else None},
        "disk": {"v": disk[0] if disk else None, "used": disk[1] if disk else None, "total": disk[2] if disk else None},
    }


def _post_telemetry():
    """Telemetrie an das PC-Backend pushen. Fehler tolerant (wie _post_sensor)."""
    url = f"{BACKEND_URL}/api/telemetry/pi"
    try:
        r = requests.post(url, timeout=2, json=_build_telemetry())
        print(f"TELEMETRY -> {url} = {r.status_code}", flush=True)
    except Exception as e:
        print(f"TELEMETRY -> {url} FAIL: {e}", flush=True)


# ── Quellen ──────────────────────────────────────────────────────────
def _poll_keyboard():
    """
    Pollt die Tastatur. Bei rising-edge auf einer Sensor-Taste feuert
    der HTTP-POST. Edge-Detection passiert ueber _kb_last_state.

    Stiller No-Op falls:
      - keyboard-Library nicht importierbar
      - is_pressed() wirft (kein root, kein /dev/input/...)
    """
    if not keyboard:
        return
    for sensor_name, key in KEYBOARD_MAP.items():
        try:
            pressed = keyboard.is_pressed(key)
        except Exception:
            # Erster Fehlversuch -> Tastatur-Reader fuer diesen Run aufgeben.
            # Wir wollen nicht 5x/Sekunde dieselbe Exception loggen.
            return
        if pressed and not _kb_last_state[sensor_name]:
            _post_sensor(sensor_name)
        _kb_last_state[sensor_name] = pressed


def _poll_gpio():
    """
    Skelett – noch nicht aktiv.

    Sobald die erste Hardware angeschlossen ist (Reed-Switch an der
    Haustuer, HC-SR501 PIR im Flur, …), wird hier mit gpiozero
    ausgelesen. Beispiel-Anbindung (kommentiert, damit der Skelett-Run
    ohne gpiozero im venv nicht crasht):

        from gpiozero import Button
        door_switch = Button(17, pull_up=True)   # Reed an GPIO17 + GND
        pir         = Button(4)                   # PIR DOUT an GPIO4
        if door_switch.is_pressed: _post_sensor('door')
        if pir.is_pressed:         _post_sensor('motion')

    Mittelfristig: weg vom Polling, hin zu gpiozero's when_pressed-
    Callbacks (echte Edge-Interrupts statt 5Hz-Polling).
    """
    pass


# ── Main-Loop ────────────────────────────────────────────────────────
def main():
    print(f"## ZENTRALE Sensor-Bridge", flush=True)
    print(f"## Backend: {BACKEND_URL}", flush=True)
    print(f"## Keyboard-Reader: {'an' if (KB_ENABLED and keyboard) else 'aus'}", flush=True)
    print(f"## Telemetrie: {'an (' + str(TELEMETRY_POLL) + 's)' if TELEMETRY_ENABLED else 'aus'}", flush=True)
    print(f"## Poll-Intervall: {POLL_SEC}s", flush=True)

    if KB_ENABLED and not keyboard:
        # Nicht fatal: GPIO-only-Setup ist ein gueltiger Modus.
        # Nur einmalig hinweisen, dann weiter.
        print("HINWEIS: keyboard-Library nicht importierbar – Tastatur-Reader inaktiv.",
              flush=True)

    # CPU-Auslastung ist ein Delta zwischen zwei Messungen → einmal "primen",
    # damit der erste Push gleich einen sinnvollen Wert hat statt None.
    # _last_tele so setzen, dass der erste Telemetrie-Push schon nach ~3s
    # kommt (Pi erscheint zuegig im Dashboard), danach alle TELEMETRY_POLL s.
    if TELEMETRY_ENABLED:
        host_metrics.cpu_percent()
    _last_tele = time.monotonic() - TELEMETRY_POLL + 3

    while True:
        if KB_ENABLED:
            _poll_keyboard()
        _poll_gpio()
        if TELEMETRY_ENABLED and (time.monotonic() - _last_tele) >= TELEMETRY_POLL:
            _post_telemetry()
            _last_tele = time.monotonic()
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
