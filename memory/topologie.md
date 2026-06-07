# Topologie: PC ↔ Pi

Seit der Migration im Mai 2026 läuft ZENTRALE **nicht mehr alles auf
dem Pi**, sondern aufgeteilt zwischen Linux-PC und Raspberry Pi. Grund:
Pi-RAM ist zu knapp für Ollama (~5–9 GB je Modell), Whisper
(~500 MB) und TTS gleichzeitig. Der Pi war ursprünglich als Core
gedacht – das war für die AI-Last zu schwer.

```
┌──────────────────────────────────────────────────────────────┐
│  PC  (pop-os, enp4s0 = 192.168.50.1, fest)                   │
│                                                              │
│   ollama           (Port 11434, localhost)                   │
│   whisper_service  (Port 5050, 0.0.0.0)                      │
│   tts_service      (Port 5051, 0.0.0.0)                      │
│   core/main.py + ui/app.py (Flask, Port 5000, 0.0.0.0)       │
│                                                              │
│   WLAN (Hotspot, dyn. IP)  → nur fuer Internet               │
│                                                              │
└──────────┬───────────────────────────────────────────────────┘
           │  Gigabit-Switch (kein Router, vergibt nichts)
           │  192.168.50.0/24 — stabil, unabh. vom Hotspot
           ▼
┌──────────────────────────────────────────────────────────────┐
│  Pi  (zentrale, eth0 = 192.168.50.10, fest)                  │
│                                                              │
│   Firefox-Kiosk → http://192.168.50.1:5000                   │
│   scripts/pi_sensor_bridge.py                                │
│      liest GPIO/Tastatur                                     │
│      pusht Trigger via HTTP an 192.168.50.1                  │
│                                                              │
│   WLAN (Hotspot, dyn. IP)  → nur fuer Internet (Apt-Updates) │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Was wo läuft

| Komponente              | Host | Begründung                                |
|-------------------------|------|-------------------------------------------|
| Ollama (qwen3.5:9b)     | PC   | ~8,8 GB Modell, läuft auf RTX 4070-GPU.   |
| Whisper STT             | PC   | ~500 MB Modell + CPU-intensiv.            |
| TTS (sherpa-onnx)       | PC   | ~120 MB Modell + CPU-intensiv.            |
| Flask + Event-Loop      | PC   | Damit AI-Calls direkt lokal sind (kein   |
|                         |      | HTTP-Hop zum Pi und zurück).              |
| Browser-Kiosk           | Pi   | Anzeige am Wand-Monitor.                  |
| Hardware-Sensoren       | Pi   | GPIO/PIR/Türsensor sitzen physisch hier.  |
| `pi_sensor_bridge.py`   | Pi   | Übersetzt GPIO-Events in HTTP-POSTs.      |

## Datenflüsse

**PC → Pi** läuft ausschließlich HTTP-Pull: Der Firefox-Kiosk holt
`/api/state` (alle 1 s), `/api/chat`, `/api/tutor/...` usw. vom
PC-Flask. Keine Push-Verbindung in die Richtung – wenn das Dashboard
neue Daten will, fragt es einfach erneut. SSE wird für Streaming-Calls
genutzt (AI-Antworten), das ist immer noch Pull (Browser hält den
Stream offen).

**Pi → PC** läuft ausschließlich über den Sensor-Webhook
`POST /api/sensor/<name>`. Erlaubte Namen: siehe `ui/app.py`
(`_ALLOWED_SENSORS`). Der Endpoint legt den Trigger in
`state.queue_sensor()`; `core/main.py` drainet die Queue pro Tick und
mapped sie auf die internen Events (`_SENSOR_TO_EVENT` in `main.py`).
Wenn ein neuer Sensor dazukommt: an drei Stellen ergänzen
(`_ALLOWED_SENSORS`, `_SENSOR_TO_EVENT`, `KEYBOARD_MAP` in der Bridge).

Zweiter **Pi → PC**-Push seit 2026-06-06: **Telemetrie**. Dieselbe
Bridge (`pi_sensor_bridge.py`) pollt alle ~30s CPU/Temp/RAM/SD (aus
`core/host_metrics.py`, dependency-frei) und POSTet sie an
`POST /api/telemetry/pi`. Der PC hält nur den letzten Stand
(`state.set_pi_telemetry()`), das Dashboard zeigt ihn im Telemetrie-Panel
(PC-Block lokal, Pi-Block aus dem Push; stale ab >90s). PC-Telemetrie
kommt dagegen lokal aus `core/telemetry.pc_snapshot()` (inkl. GPU/VRAM via
`nvidia-smi`) — kein Push nötig, der PC ist ja das Backend.

## Netzwerk

Seit 2026-05-19 hängen PC und Pi an einem **unmanaged Gigabit-Switch**
mit festen IPs im LAN-Subnetz `192.168.50.0/24`:

| Host | Interface | LAN-IP        | Methode    |
|------|-----------|---------------|------------|
| PC   | enp4s0    | 192.168.50.1  | NetworkManager static (ipv4.method manual, never-default) |
| Pi   | eth0      | 192.168.50.10 | NetworkManager static (ipv4.method manual, never-default) |

Wichtig:
- Der „Switch" ist kein Router – er hat keinen DHCP-Server, vergibt
  keine IPs, kennt keine Subnetze. Wir definieren das LAN selbst.
- `never-default yes` auf beiden LAN-Connections: Default-Route bleibt
  am WLAN/Hotspot. Das LAN ist nur fuer Pi↔PC.
- Latenz Pi↔PC ueber LAN: ~0.5 ms (vs. ~6 ms ueber Hotspot).
- **Kein** `ip=...`-Kernel-Boot-Parameter fuer enp4s0 in
  `/etc/kernelstub/configuration`. NetworkManager macht die IP-Config
  ohnehin, der Kernel-Boot-Param ist nur fuer NFS-Root / Diskless-
  Setups gedacht. Wenn dort `ip=<ip>:::<mask>::<iface>:off` steht und
  das Gateway-Feld leer ist, schreibt der Kernel-IP-Stack eine
  `default dev enp4s0 scope link`-Route in die Routing-Tabelle, die
  NM nicht aufraeumen kann. Symptom: viele Websites laden nicht
  (ARP-Aufloesung schlaegt im LAN-Subnetz fehl, weil dort nur der Pi
  sitzt). Aufraeumen mit
  `sudo kernelstub --delete-options "ip=..."` und einmal
  `sudo ip route del default dev enp4s0 scope link`. War 2026-05-26
  ein Tag lang das Mystery „Internet kaputt nach LAN-Setup".

**Hotspot ist damit unkritisch.** WLAN-Reconnects wechseln zwar
weiterhin die Hotspot-IP, aber `192.168.50.1` und `192.168.50.10`
bleiben stabil → Pi-Kiosk und Bridge muessen nie wieder umgebogen
werden. Der Hotspot dient PC und Pi nur noch fuer Internet (Apt,
Modell-Downloads). Wer kein Internet braucht, kann WLAN ganz abdrehen.

### Wenn das LAN doch mal nicht da ist

Fallback-Pfad zum Pi ueber WLAN: `find-zentrale` scant per ARP nach
der Pi-WLAN-MAC `b8:27:eb:34:8b:1c` und schreibt eine passende IP in
`~/.ssh/config`. Nur als Notfall-Tool gedacht – im Normalbetrieb laeuft
`ssh zentrale` ueber die feste LAN-IP `192.168.50.10`.

## Was der Pi NICHT mehr macht

- Kein `zentrale.service` mehr (stopped + disabled).
- Kein `whisper.service`, kein `tts.service`.
- Kein Ollama-Container.
- Keine direkten Disk-Writes nach `data/<category>.json` – Logging
  geht über den PC-Flask.

## Was der Pi (noch) tut

- Firefox-Kiosk auf das PC-Dashboard.
- `pi_sensor_bridge.service` (sobald installiert): leitet Hardware-
  Sensoren weiter.
- Auto-Update via `pi_autopull.sh` + `deploy/RELEASE` – funktioniert
  weiterhin, sodass Codeänderungen am Bridge-Skript oder am
  Kiosk-Autostart-Skript ohne manuellen rsync auf den Pi kommen.

## Erweiterbarkeit

Das Bridge-Pattern (Pi-Hardware → HTTP-POST → PC-Flask) ist nicht
Pi-spezifisch. Spätere Knoten (PoE-ESP32 mit Türsensor, ein zweiter
Anzeige-Pi-Zero, ein Pi an einer Schlafzimmer-Wand) können denselben
`/api/sensor/<name>`-Endpoint nutzen. Der Sensor-Name wird in beiden
Schichten geführt – einmal als Eingangskanal, einmal als logisches
Event.
