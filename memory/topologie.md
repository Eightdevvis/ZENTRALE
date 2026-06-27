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

`pc_snapshot()` legt seit 2026-06-27 auch `host` (`socket.gethostname()`)
ab: die Fronten sind nur HTTP-Clients, die gezeigten „pc"-Werte stammen vom
**Backend-Host**, nicht von der anzeigenden Maschine. Die TUI leitet daraus
ihr Telemetrie-Kürzel ab (`host_label`: pop-os→`PC`, 0RAMMachine→`LAP`,
zentrale→`PI`) — vorher stand dort hart `LAP`, was auf dem Pi-Kiosk (zeigt
die PC-Werte) falsch war.

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

## Laptop als 3. Knoten (seit 2026-06-15)

Ein Laptop (`0RAMMachine`, User `sasha`) greift von unterwegs/daheim auf
den PC zu. Beide hängen am **Handy-Hotspot** (`Bigme`), wo der PC eine
**dynamische IP** hat – die feste LAN-IP `192.168.50.1` ist nur am
Gigabit-Switch (Pi↔PC), für den Laptop nicht erreichbar.

Damit das trotzdem stabil ist, gibt es laptop-lokale Tools (in
`~/.local/bin/`, **bewusst außerhalb des Repos**, damit sie nicht zum Pi
syncen):

| Befehl          | Zweck |
|-----------------|-------|
| `find-pc`       | Spiegelbild zu `find-zentrale`: ARP-Scan nach der PC-WLAN-MAC `8c:86:dd:72:37:e7` (Fallback: `:5000`/api/state-Signatur), schreibt einen `# >>> find-pc >>>`-Block mit `Host pc` in `~/.ssh/config`. Überlebt IP-/Subnetzwechsel des Hotspots. |
| `zentrale-remote` | „Daheim"-Befehl: `find-pc` → SSH-Tunnel `localhost:15000 → pc:5000` → Laptop-TUI gegen das volle Ollama-Backend des PCs. `q` beendet + Tunnel-Teardown. |
| `zentrale-pull` / `zentrale-push` | Dateisync der **nicht-git-getrackten** Dateien (Daten/Caches/Configs/untracked) per rsync. Symlinks auf `zentrale-sync`. Listet `git ls-files --others` (untracked + ignoriert), filtert `venv/`, `__pycache__`, `.pyc`, `.pytest_cache` sowie `.history/` und `.claude/settings.local.json` (`ZENTRALE_SYNC_ALL=1` nimmt auch die mit). **Kein `--delete`** (nur additiv). **Newest-wins per Default (`--update`)** — eine ältere Datei überschreibt eine neuere NIE mehr blind (`ZENTRALE_SYNC_FORCE=1` für bedingungsloses Spiegeln). Peer per `ZENTRALE_FINDER`+`SSH_HOST_ALIAS`: Laptop→`pc` (`find-pc`), PC→`0RAMMachine` (`find-0RAMMachine`). `--dry-run` + extra rsync-Args werden durchgereicht. |
| `zentrale-push-data` | **Push-on-write-Helfer** (siehe unten). Vom Backend nach jeder echten Daten-Änderung fire-and-forget angestoßen; coalesct Bursts (flock+dirty), schiebt newest-wins zum Peer, komplett stumm + kurzer Timeout. |
| `zentrale-sync-boot` | **Einmaliger Abgleich beim Start** (siehe unten). Kein Daemon. |
| `zentrale-launch` | Wrapper hinter den Startern `zentrale`/`zentrale-tui`/`zentrale-laptop`; hängt den Boot-Sync ein. |

### Boot-Sync (einmalig beim Start, KEIN Daemon)

Modell nach mehreren Fehlschlägen mit Dauer-Sync (ein inotify/Reconcile-Daemon
racte mit aktiven Edits/Commits im selben Repo und überschrieb getrackte
Dateien, weil `git ls-files` mid-commit leer kam): **ein laufender Daemon ist
raus.** Stattdessen läuft **genau einmal beim ZENTRALE-Start**, *bevor* das
Backend hochfährt → kein Race.

`zentrale-sync-boot` macht: `find-pc`, dann `zentrale-sync pull --update` +
`push --update` (newest-wins per mtime; da immer nur eine Maschine zur Zeit
schreibt, clasht nichts). Best-effort: PC weg/aus → still überspringen, Start
läuft normal. **Nur nicht-git-getrackte Dateien**; `zentrale-sync` pull hat
einen **Fail-safe**: ist `git ls-files` leer (Index gesperrt), bricht der Pull
ab, statt Code zu überschreiben. Abschalten: `ZENTRALE_NO_BOOT_SYNC=1`.

Eingehängt über `zentrale-launch` je nach Pfad:
- **`zentrale` (Menü):** der Sync läuft **versteckt hinter dem Regenbogen-
  Ladebalken**. `tui/select_kassette.py` startet ihn beim Auswählen im
  Hintergrund, der 100%-Balken shimmert weiter bis der Sync fertig ist —
  keine separate Ladesequenz. (Auf PC/Pi ohne `zentrale-sync-boot` in PATH:
  No-Op, Start wie bisher.)
- **`zentrale-tui`/`zentrale-laptop` (Direktstart):** stiller Sync im Wrapper
  (Ausgabe ins Log `/tmp/zentrale-sync-boot.log`, kurze `⟳`-Zeile).

### Push-on-write (live, event-getrieben — ergänzt den Boot-Sync)

Der Boot-Sync allein ließ zwischen zwei Starts Stände auseinanderlaufen, und
die **manuellen** `push`/`pull` hatten lange **kein `--update`** → ein
versehentlicher Push einer älteren Datei hat eine neuere am Peer
**bedingungslos überschrieben** (so gingen wiederholt Sashas Projekt-Flags in
`features.json` verloren — die Datei wird von BEIDEN Seiten geschrieben). Fix
zweistufig: (1) `--update` ist jetzt Default (s.o.); (2) **Push-on-write** —
das Backend schiebt jede echte Daten-Änderung sofort zum Peer.

`core/datasync.py:notify_change()` hängt im **Schreib-Pfad** der user-getriebenen
Registries (`lists._save_file`, `graphs._save`, `kalender._save_raw`) und stößt
— nur wenn `ZENTRALE_AUTOPUSH=1` — fire-and-forget `zentrale-push-data` an.
Quelle der Variable je Knoten: **Laptop** `start_laptop.sh` (Shell-`export`),
**PC** die systemd-Unit `zentrale-pc.service` (`Environment=`). **Achtung
Stolperstein (gefixt 2026-06-25):** am PC lag das `Environment=` lange in einem
Drop-in `…/zentrale-pc.service.d/autopush.conf` **ohne `[Service]`-Header** →
systemd verwarf beide Zeilen still („Assignment outside of section") → der PC
hat **nie** autogepusht (PC→Laptop-Richtung tot, fiel nur als Asymmetrie auf:
News am PC frisch, am Laptop tagealt). Jetzt fest in der versionierten Unit
(`deploy/zentrale-pc.service`), inkl. `PATH` mit `~/.local/bin` (sonst findet
das vom Backend gespawnte `zentrale-push-data` seine Helfer nicht). **Bewusst im Schreib-Pfad, NICHT per
Datei-Watcher:** ein vom Sync eingehendes rsync schreibt die Datei direkt auf
Platte, NICHT durch `_save_*` → löst nie einen Gegen-Push aus ⇒ **kein
Ping-Pong** (ein Watcher hätte genau die Schleife). Bewusst **nicht** gehängt:
`graph.py` (KI-Konzeptgraph, würde während Chats stürmen) und die
Hochfrequenz-Sensorlogs (`/api/log`) — die bleiben beim Boot-Sync.

Das ist die event-getriebene Rückkehr zur Live-Propagierung, aber **leichter
als der frühere Daemon** (kein Polling/inotify-Reconcile, kein Race mit
Commits — nur ein Stups pro echtem App-Write).

PC-Seite: die Skripte sind jetzt **bidirektional** (Peer per `ZENTRALE_FINDER`;
der PC kennt den Laptop als `0RAMMachine`/`find-0RAMMachine`). Die
`~/.local/bin`-Skripte (`zentrale-sync` + `push`/`pull`-Symlinks,
`zentrale-push-data`, `zentrale-sync-boot`) müssen dort installiert sein.

**Boot-Sync am PC = eigene oneshot-Unit (seit 2026-06-25), NICHT `ExecStartPre`.**
Der frühere Plan „`ExecStartPre=zentrale-sync-boot` an `zentrale-pc`" ist eine
Falle: `zentrale-pc` hat `Restart=always`/`RestartSec=3`, ein `ExecStartPre`
feuert bei **jedem** Crash-Neustart erneut → im Crashloop ein Sync-Sturm. Statt
dessen: `deploy/zentrale-sync-boot.service` (`Type=oneshot`), die `zentrale-pc`
nur per `Wants=`+`After=` zieht. systemd löst Dependencies **nicht** bei jedem
`Restart=` neu auf → der Sync läuft genau **einmal pro echtem Start** (Boot /
`systemctl start`), crashloop-sicher. (Auf dem Laptop bleibt der Boot-Sync wie
gehabt im `zentrale-launch`-Wrapper, da Direktstart statt systemd.)

**Finder retry-gehärtet (2026-06-25):** `find-pc`/`find-0RAMMachine` machen den
ARP-Scan jetzt bis zu 3× (`FIND_RETRIES`), weil ein Einzelschuss flackert
(Peer im WLAN-Stromsparmodus / Ping-Verlust → MAC fehlt für eine Runde in
`ip neigh`, nächste Runde da). Eine Runde ~1s, hilft Boot-Sync **und** Autopush
(beide rufen denselben Finder; ein verpasster Scan = ein verlorener Push).

Voraussetzung am PC (einmalig): `openssh-server` installiert + `ssh.service`
aktiv (der PC hatte nur den SSH-**Client** → konnte zum Pi, aber niemand
zu ihm); MAC-Randomisierung für `Bigme` aus
(`nmcli connection modify Bigme wifi.cloned-mac-address permanent`), damit
`find-pc` die MAC trifft; Laptop-Key (`id_ed25519`) via `ssh-copy-id pc`.

Der „Frontend↔AI"-Weg läuft bewusst über den **SSH-Tunnel** statt direkt
auf `:5000` (verschlüsselt; `:5000` am PC kann später auf `localhost`
eingeschränkt werden, dann geht es nur noch via SSH).

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
