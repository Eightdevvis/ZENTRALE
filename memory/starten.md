# Starten (lokal)

Seit der PC↔Pi-Migration (siehe `topologie.md`) laufen alle drei
Backend-Prozesse auf dem **PC**, nicht mehr auf dem Pi. Der Pi
ist Display-Kiosk + Sensor-Bridge.

ZENTRALE besteht aus **drei Prozessen**, die in eigenen Terminals laufen
sollten – jeder hat sein eigenes Terminal-Logging und Crash-Verhalten.

## 3 Terminals

```bash
# Terminal 1 – ZENTRALE (Event-Loop + Flask)
sudo venv/bin/python core/main.py

# Terminal 2 – Whisper STT (lädt Modell beim ersten Start, ~500 MB)
venv/bin/python services/whisper_service.py

# Terminal 3 – TTS
venv/bin/python services/tts_service.py
```

Browser dann auf:

```
http://localhost:5000
```

## Warum `sudo` für ZENTRALE?

Die `keyboard`-Library braucht Root, um globale Keypress-Events
mitzuhören (Tastatur-Simulation der Sensoren).

Ohne `sudo`: alles läuft, nur die Tastatur-Erkennung schweigt. Das
Dashboard zeigt keine simulierten Sensor-Events mehr, ist aber sonst
voll funktional.

Wenn der echte GPIO-Pfad implementiert ist (`RPi.GPIO`, User in der
Gruppe `gpio`), entfällt `sudo` ganz.

## Konfiguration via Umgebungsvariablen

Alle haben sinnvolle Defaults – nur setzen, wenn du was verschieben
willst:

```bash
# ZENTRALE (core/main.py) verwendet:
OLLAMA_URL=http://localhost:11434   # default
OLLAMA_MODEL=mistral                # default
WHISPER_URL=http://localhost:5050   # default (gegen den Whisper-Service)
TTS_URL=http://localhost:5051       # default (gegen den TTS-Service)

# whisper_service.py verwendet zusätzlich:
WHISPER_MODEL=small                 # default (tiny|base|small|medium)
```

Beispiel: Whisper läuft auf einer anderen Maschine im LAN.

```bash
WHISPER_URL=http://192.168.1.42:5050 sudo venv/bin/python core/main.py
```

## Reihenfolge des Hochfahrens

Egal. Die Services hängen lose über HTTP zusammen – wenn ZENTRALE einen
Service nicht erreicht, loggt sie das im Terminal und versucht es beim
nächsten Request erneut.

## Auf dem Pi: Bridge + Kiosk, KEIN Backend

Seit der Migration läuft auf dem Pi nur noch:

- `pi_sensor_bridge.service` — leitet GPIO/Tastatur-Trigger per HTTP
  an das PC-Backend (`/api/sensor/<name>`).
- Firefox-Kiosk auf `http://<PC-IP>:5000` (via XFCE-Autostart, siehe
  `deployment.md`).

`zentrale.service`, `whisper.service`, `tts.service` sind auf dem Pi
**deaktiviert** (`systemctl disable`). Sie liegen physisch in
`/etc/systemd/system/`, weil das deploy-Script sie installiert hat,
aber sie werden nicht mehr beim Boot gestartet.

Logs der Pi-Bridge:

```bash
ssh zentrale "sudo journalctl -u pi_sensor_bridge.service -f"
```

Setup + IP-Wechsel-Pfad: `topologie.md` und `deployment.md`.
