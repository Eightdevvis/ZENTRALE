# Deployment auf Raspberry Pi

**Stand 2026-09-18:** Der Pi ist **Aussenposten**: kein Backend, nur
`pi_sensor_bridge.service` (Sensoren + PIR → HTTP an den PC), der Kiosk und
der Wecker für den PC (`zentrale-wake-pc.service`, Wake-on-LAN). Der
**Kiosk-Default ist `room`** (seit 2026-09-14): das Persona-Zimmer
(`tutor/room.py`) als randloses Wandbild, die TUI liegt dahinter (Alt+Z).
`tui` und `browser` bleiben als Modi wählbar. Erst-Bespielung per
`scripts/deploy_pi.sh` (Positivliste `deploy/aussenposten.txt`), danach holt
sich der Knoten sein Paket alle 5 Minuten selbst vom Backend (kein git). Auf
dem PC laufen die drei Backend-Units `deploy/*-pc.service`. Der Git-Weg
(`pi_autopull.sh` + `deploy/RELEASE`) und die Vollspiegel-Units
(`zentrale.service` usw.) gelten nur noch für einen vollwertigen Backend-Host
(`--voll`).

## Pi-Sensor-Bridge (aktiver Service)

Einmalig auf dem Pi:

```bash
sudo cp /opt/zentrale/deploy/pi_sensor_bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
echo 'ZENTRALE_BACKEND_URL=http://192.168.50.1:5000' | sudo tee /etc/zentrale-bridge.env
sudo systemctl enable --now pi_sensor_bridge.service
```

Die PC-IP `192.168.50.1` ist seit der LAN-Migration (siehe
`memory/system/topologie.md`) **fest**. Sollte sich die IP doch mal aendern
(anderes LAN-Subnetz, z.B. nach dem Router-Umbau aus `wachplan.md`), alle
Endpunkte konsistent anpassen: hier, im Pi-Kiosk-Autostart
(`install_xfce_autostart.sh` mit `ZENTRALE_BACKEND_URL=...`) und in den
PC-systemd-Services.

Die Bridge liest seit 2026-09-14 auch den **PIR** (gpiozero, GPIO4 =
Board-Pin 7, `PI_PIR_GPIO=0` schaltet ab) — Hardware-Details in
`memory/betrieb/hardware.md`.

## PC-systemd-Services (zentrale-pc, whisper-pc, tts-pc)

Damit ZENTRALE beim PC-Boot automatisch hochkommt (ohne Login,
ohne manuellen `zentrale`-Aufruf), gibt es drei System-Units analog
zum Pi-Schema. Liegen in `deploy/*-pc.service`:

| Unit                 | Was laeuft                           | Scheduling |
|----------------------|--------------------------------------|------------|
| `zentrale-pc.service`| `core/main.py` (Event-Loop + Flask)  | normal     |
| `whisper-pc.service` | `services/whisper_service.py`        | Nice=19, IO idle, CPU idle |
| `tts-pc.service`     | `services/tts_service.py`            | Nice=19, IO idle, CPU idle |

Whisper + TTS haben `After=zentrale-pc.service`, damit das Dashboard
zuerst erreichbar ist und der Modell-Load nicht den Boot ausbremst.
Alle drei laufen als `User=sasha`, **kein** sudo → Tastatur-Sensor-Sim
geht hier nicht (das war eh nur Dev-Modus, im echten Betrieb liefert
der Pi die Sensor-Events ueber `/api/sensor/<name>`).

> **Genau ein Backend pro Rechner:** `zentrale-kern.service` (Benutzer-Dienst,
> `systemeinheit.md`) macht dasselbe wie `zentrale-pc.service`; beide zusammen
> streiten sich um `:5000`.

**Kopplung:** `zentrale-pc.service` hat zusaetzlich
`Wants=whisper-pc.service tts-pc.service`. Damit zieht `systemctl restart
zentrale-pc.service` die Audio-Sidecars mit hoch. **Bewusst nur `Wants=`,
KEIN `After=`** auf die Sidecars: die deklarieren selbst schon
`After=zentrale-pc` → ein `After=` zurueck erzeugt einen Ordering-Cycle, den
systemd durch Verwerfen des Sidecar-Starts bricht (sie kommen dann nie hoch).
`Wants=` ist ordering-frei. Faustregel bei stummer KI / totem Mikro: **zuerst
`systemctl is-active zentrale-pc whisper-pc tts-pc`** — stehen die Sidecars,
`restart zentrale-pc` oder gezielt `sudo systemctl start whisper-pc tts-pc`.
(Warum die Kopplung kam: Historie 2026-06-07.)

Einmalig installieren:

```bash
cd /home/sasha/codicus/ZENTRALE
sudo cp deploy/zentrale-pc.service deploy/whisper-pc.service deploy/tts-pc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zentrale-pc.service whisper-pc.service tts-pc.service
sudo systemctl start zentrale-pc.service whisper-pc.service tts-pc.service
```

Status / Logs:

```bash
systemctl status zentrale-pc.service whisper-pc.service tts-pc.service
journalctl -u zentrale-pc.service -f      # live tail
```

Manueller Dev-Modus (Tastatur-Sim, Farb-Prefixe, alles in einem
Terminal) bleibt parallel verfuegbar: erst die System-Services
stoppen, dann `zentrale --with-keyboard` aufrufen. Sonst Port-Konflikt
auf 5000/5050/5051.

## Wake-on-LAN (Pi weckt PC)

Der Weck-Weg von unterwegs (`wachplan.md`: der PC darf unterwegs schlafen,
SSH weckt ihn nicht — nur dieses Magic-Packet vom Pi). Der Pi bleibt 24/7
an, der PC darf schlafen; das Paket weckt aus Suspend wie aus S5 (soft-off).

**PC-Seite (einmalig):**

1. NIC-WoL persistent ueber NetworkManager:
   ```bash
   sudo nmcli con mod "Wired connection 1" 802-3-ethernet.wake-on-lan magic
   sudo ethtool -s enp4s0 wol g
   sudo ethtool enp4s0 | grep -iE 'wake'
   # erwartet: "Wake-on: g"
   ```
2. BIOS: „Wake on LAN" / „Power On by PCI-E" aktivieren, „ErP Ready" /
   „EuP 2013" deaktivieren (sonst killt EU-Standby den NIC im
   Soft-Off). Mainboard-Hersteller-Manual lesen, Bezeichnungen
   variieren.

**Pi-Seite (automatisch beim Boot):**

`zentrale-wake-pc.service` (in `deploy/`) feuert nach
`network-online.target` einmal `scripts/wake_pc.sh`. Wird vom
`install_pi_services.sh` mit-installiert und enabled. Type=oneshot
mit `TimeoutSec=120` — das deckt die bis zu 90s `wake_pc.sh`-Polling-
Phase ab.

Status / Log nachschauen:
```bash
ssh zentrale 'systemctl status zentrale-wake-pc.service; journalctl -u zentrale-wake-pc.service -n 50'
```

Manueller Trigger zum Testen (PC vorher schlafen legen):
```bash
ssh zentrale 'sudo systemctl start zentrale-wake-pc.service'
# oder direkt das Skript:
ssh zentrale 'bash /opt/zentrale/scripts/wake_pc.sh'
```

`wake_pc.sh` ist idempotent: prueft erst per `curl` ob die ZENTRALE
auf `http://192.168.50.1:5000/` antwortet. Falls ja, kein Paket – PC
ist schon wach. Falls nein, wird das Magic-Packet als UDP-Broadcast
(`192.168.50.255`) an die PC-eth-MAC (`a8:a1:59:ab:c0:02`) gesendet
und das Script wartet bis zu 90s auf eine ZENTRALE-Antwort.

Konfig per Env-Vars: `PC_MAC`, `LAN_BROADCAST`, `PROBE_URL`.

Der Boot-Trigger deckt nur das „Pi geht an"-Szenario (Stromausfall,
manueller Pi-Start). Spaeter sinnvoll: zusaetzlicher Aufruf aus
`pi_sensor_bridge.py` bei PIR-/Tuer-/Button-Trigger fuer den „Sasha kommt zur
Tuer rein"-Flow — mit der Falle aus `wachplan.md` (ein pollender Pi darf
einen schlafenden PC nicht dauernd wecken).

## 1) Pi vorbereiten (einmalig)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

Systempakete fuer das Zimmer (libSDL2, PortAudio …): `deploy/aussenposten-system.txt`
— werden **nicht** automatisch installiert (root), der Updater prueft nur, ob
die Python-Pakete sich importieren lassen.

## 2) Deployen — zwei Sorten Knoten

`scripts/deploy_pi.sh` kennt **zwei Modi**, weil es zwei Sorten Knoten gibt.
Der Default ist der Aussenposten.

### Aussenposten (Default) — Anzeige, Ton, Sensorik, KEIN Backend

Der Pi an der Wand bekommt **nur die Positivliste `deploy/aussenposten.txt`**
(deny-by-default) und die kurze `deploy/requirements-aussenposten.txt`;
systemd-Units werden **uebersprungen**.

Was drin ist: die TUI (`tui/`, stdlib-only), die Sensor-Bridge samt
`core/host_metrics.py`, das Persona-Zimmer (`tutor/room.py` +
`scripts/open_tutor_room.py` + Handschrift-Font), der Updater und die
Einrichtungs-Skripte. Die Liste selbst ist die Wahrheit, hier keine Kopie.

Warum die Liste existiert: der alte Vollspiegel schob **alles** rueber —
darunter `data/tts_model/` (1,0 GB Sprachmodelle) und `core/map/` (37 MB) —
und installierte faster-whisper/sherpa-onnx/piper-tts in den Pi-venv. Auf
einem Pi 3 (armv7l, 1 GB RAM) ist das ein langer Build aus dem Quellcode fuer
Code, der dort nie ausgefuehrt wird.

`room.py` und die TUI importieren **nichts** aus dem Projekt (nur stdlib,
plus pygame beim Zimmer) — sie sind reine HTTP-Clients gegen das PC-Backend.
Genau darum ist die Liste so kurz und bleibt stabil.

```bash
./scripts/deploy_pi.sh sasha@192.168.50.10 /opt/zentrale
```

Das ist die **Erst-Bespielung**. Danach haelt der Knoten sich selbst aktuell:
einmal `crontab /opt/zentrale/deploy/aussenposten-update.cron` eintragen, und
er holt sich sein Paket alle 5 Minuten per HTTP vom Backend, sobald sich
dessen Inhalts-Hash aendert. Wie das funktioniert, steht in
`memory/system/topologie.md` (Abschnitt »Wie ein Aussenposten seinen Code
kriegt«) und `memory/system/api_endpoints.md`.

Der Modus legt zusaetzlich die Marker-Datei **`.aussenposten`** an. Die liest
`pi_autopull.sh` (Abschnitt 6, der alte Git-Weg) und nimmt dann ebenfalls die
kurze Requirements-Liste — relevant nur noch fuer Knoten, die weiter am
Git-Clone haengen.

**Kein `--delete` im Aussenposten-Modus:** bei einer Positivliste besitzen wir
den Zielbaum nicht; `--delete` wuerde dort alles ausserhalb der Liste
wegraeumen (u.a. `.venv` und lokale Configs).

### `--voll` — vollwertiger Backend-Host

Spiegelt das ganze Projekt (`rsync -az --delete`, excludes `__pycache__`,
`.git`, `.venv`), installiert die komplette `requirements.txt` und
installiert/enabled/restartet `zentrale.service`, `whisper.service`,
`tts.service`. Das war frueher der einzige Modus.

```bash
./scripts/deploy_pi.sh --voll sasha@192.168.50.10 /opt/zentrale
```

**Achtung – venv-Inkonsistenz:** lokal heißt der Virtualenv-Ordner
`venv` (siehe `memory/betrieb/setup.md`), auf dem Pi heißt er `.venv` (mit Punkt!).
Das deploy-Script erstellt automatisch `.venv` auf dem Pi und der
systemd-Service erwartet ebenfalls `.venv`. Wenn du manuell auf dem Pi
arbeitest: nutze `.venv/bin/python`, nicht `venv/bin/python`.

## 3) systemd-Services (nur `--voll`)

Drei Unit-Templates liegen in `deploy/`:

| Unit                  | Was lauft     | Scheduling                       |
|-----------------------|---------------|----------------------------------|
| `zentrale.service`    | `core/main.py` (Event-Loop + Flask) | normal |
| `whisper.service`     | `services/whisper_service.py` (Port 5050) | Nice=19, SCHED_IDLE, IO idle |
| `tts.service`         | `services/tts_service.py` (Port 5051) | Nice=19, SCHED_IDLE, IO idle |

Alle drei werden vom Deploy-Script nach `/etc/systemd/system/` kopiert
und enabled. **Whisper und TTS haben `After=zentrale.service`** und
laufen mit niedrigster Scheduling-Priorität, damit der Boot des
Dashboards nicht durch den 500-MB-Modell-Load von Whisper ausgebremst
wird — sobald der Core idle ist, kriegen sie CPU.

Auf dem Pi an der Wand sind sie **`disabled`** (liegen noch in
`/etc/systemd/system/` vom alten Vollspiegel, starten aber nicht).

**Wichtig:**
- `User=<dein-pi-user>` (vom Deploy-Script gesetzt) – also **kein**
  `sudo`. Das heißt die Tastatur-Simulation funktioniert auf dem Pi
  nicht; dort uebernimmt der echte Sensor-Pfad der Bridge.
- Die Templates haben `User=pi` als Platzhalter, der zur Laufzeit
  durch den SSH-User ersetzt wird.

## 4) Kiosk-Modus (Auto-Start im Vollbild, ohne XFCE-UI)

**Drei Modi** (`ZENTRALE_KIOSK_MODE`, Default **`room`**), alle schreibt
dasselbe `install_xfce_autostart.sh`:

| Modus | Was an der Wand steht | Warum |
|---|---|---|
| `room` (Default) | das Persona-Zimmer (`scripts/open_tutor_room.py --wand`), randloses Fenster in Desktop-Groesse, Mikro immer offen, die Persona spricht von sich aus; TUI per Alt+Z drueber (`q`/`u` = zurueck). Endet das Zimmer (Esc, Crash), kommt es nach 2 s wieder; Backend weg faengt das Zimmer selbst ab. stderr → `/tmp/zentrale-tutor-room.log`. | Entscheidung Sasha 2026-09-14: der Tutor ist wichtiger als das Dashboard, und »am Pi vorbeigehen« muss reichen — kein Knopf. |
| `tui` | maximiertes xterm mit der curses-TUI gegen das PC-Backend. Stdlib-only → **kein venv noetig**. **KI-frei** (kein Chat/Kino/Reflexion an der Wand). | Der Pi 3 (1 GB RAM, VideoCore IV) rendert das animierte 1080p-Dashboard nur in **Software** → ein Kern dauerhaft am Anschlag (`firefox-esr` ~120 % CPU), ruckelig. Die TUI malt nur geaenderte Zellen. |
| `browser` | der selbstheilende Firefox-Kiosk auf `$ZENTRALE_BACKEND_URL` (volle KI-Optik / PC-Solo-Test). | der urspruengliche Kiosk. |

**`-maximized` / `--wand`, NICHT Fullscreen:** Ein echtes Fullscreen-Fenster
liegt bei xfwm4 in einem eigenen Layer ganz oben → Zusatzfenster (die TUI per
Alt+Z, Karte `w` → `scripts/map_window.py`, `/slide`-PDFs) oeffnen
**dahinter** und sind unerreichbar. Ein normales Fenster auf voller Groesse
stapelt sich normal. Randlos macht es das xfconf-Setting
`xfwm4 /general/borderless_maximize = true` (setzt das Skript selbst).

**Anwenden nach Deploy:** Weder der Paket-Updater noch der alte Autopull ruft
`install_xfce_autostart.sh` auf. Nach einer Aenderung am Skript also einmalig
auf dem Pi: `bash /opt/zentrale/scripts/install_xfce_autostart.sh && sudo
systemctl restart lightdm`.

Ziel: Pi bootet → kurze Konsole → schwarzer Bildschirm → Kiosk. **Kein
XFCE-Panel, kein Wallpaper, kein Mauszeiger** dazwischen.

`scripts/install_xfce_autostart.sh` macht das komplett (User-Ebene):

1. **Custom `xfce4-session.xml`** (`~/.config/xfce4/xfconf/xfce-perchannel-xml/`):
   überschreibt die Default-Failsafe-Session der XFCE-Installation.
   Startet **nur xfwm4 + xfsettingsd** — kein xfce4-panel, kein
   xfdesktop, kein Thunar. Root-Window bleibt schwarz bis der Kiosk
   übernimmt.
2. **xfwm4 backup-autostart** in `~/.config/autostart/xfwm4.desktop`.
   Belt-and-Suspenders falls die Session-XML mal nicht greift —
   der Kiosk braucht den WM.
3. **`~/.xsessionrc`** (nicht `.xprofile` — die liest Debians Xsession
   nicht): Bildschirm-Modus via `aussenposten_bildschirm.py` + Blanking aus
   (`xset s off`, `-dpms`), der Wandmonitor bleibt an.
4. **`~/.config/autostart/zentrale.desktop`** je nach Modus (Tabelle oben).
   Im `browser`-Modus ist der Exec eine **selbstheilende Schleife**: wartet
   endlos bis der Core antwortet, startet Firefox, und laedt bei
   Backend-Abriss (3× Fehler in Folge, ~30 s) automatisch neu. Kein
   Timeout — der Pi bootet regelmaessig VOR dem PC (BIOS + LUKS + Warmup),
   und ein Zeitfenster haengt dann fuer immer auf der Fehlerseite
   (Historie 2026-06-02). Ziel-URL Default **`http://192.168.50.1:5000`**
   (PC-LAN-IP, NICHT localhost — Footgun unten).
5. **Notaus-Hotkey `Ctrl+Alt+Esc`** → `scripts/emergency_exit.sh`
   (lightdm-stop → Pi auf TTY1).

Plus auf Root-Ebene (via `install_pi_services.sh`):

6. **lightdm-Drop-in** `/etc/lightdm/lightdm.conf.d/10-zentrale.conf`
   aus `deploy/lightdm-zentrale.conf`. Setzt `xserver-command=X -nocursor`
   → kein Mauszeiger ab X-Start (wir haben keine Maus am Kiosk).

Aufruf auf dem Pi nach jedem RE-Setup:

```bash
bash /opt/zentrale/scripts/install_xfce_autostart.sh
# Solo-Test direkt am PC stattdessen:
#   ZENTRALE_BACKEND_URL=http://localhost:5000 bash .../install_xfce_autostart.sh
```

Idempotent. Der Hotkey-Teil funktioniert nur aus einer aktiven
XFCE-Session (DBus muss laufen).

> **FOOTGUN (real passiert 2026-06-02):** Wer das Skript auf dem Pi OHNE
> `ZENTRALE_BACKEND_URL` aufruft und der Default waere `localhost`, bekommt
> einen Kiosk, der das Backend auf der **Pi selbst** sucht. Ergebnis: „unable
> to connect" den ganzen Tag, egal wie gesund der PC war. Seitdem ist der
> Default die PC-LAN-IP `192.168.50.1:5000`. Diagnose-Merker: wenn der Kiosk
> tot ist, ZUERST `grep -i url ~/.config/autostart/zentrale.desktop` auf dem
> Pi — zeigt die URL, auf die der Kiosk wirklich zielt.

### Mikrofon-Berechtigung im Kiosk (nur `browser`-Modus)

Im `room`-Modus nimmt das Zimmer selbst per `sounddevice` auf — Firefox ist
nicht beteiligt. Fuer den Browser-Kiosk gilt: damit der Mic-Button
(`#chat-mic-btn`, siehe `memory/ki/audio_system.md`) auf `http://192.168.50.1:5000`
funktioniert, mussten zwei Hindernisse weg:

1. **Insecure-Origin-Block:** Firefox laesst `getUserMedia()` per default
   nur auf HTTPS oder `localhost` zu. Eine LAN-HTTP-Origin ist „insecure"
   und wird komplett geblockt — bevor irgendein Permission-Dialog
   ueberhaupt erschiene.
2. **Permission-Dialog im Kiosk:** Selbst wenn der Insecure-Block weg
   waere, gibt's im `--kiosk`-Modus keine Toolbar und damit keinen
   anklickbaren Doorhanger.

Beides wird vom `install_xfce_autostart.sh` mit-installiert:

- **Insecure-Prefs** (Profil-spezifisch, weil Mozilla diese Prefs nicht
  per Policy zulaesst): in `~/.zentrale-kiosk-profile/user.js` werden
  `media.devices.insecure.enabled` und `media.getusermedia.insecure.enabled`
  auf `true` gesetzt. Der Kiosk-Autostart startet Firefox mit
  `--profile ~/.zentrale-kiosk-profile --no-remote`, damit dieses Profil
  garantiert genutzt wird.
- **Permission-Whitelist** (systemweit ueber Enterprise-Policy):
  `scripts/install_firefox_mic_policy.sh` schreibt
  `/etc/firefox-esr/policies/policies.json` mit
  `Permissions.Microphone.Allow = ["http://192.168.50.1:5000"]` und
  `BlockNewRequests=true`. Das Skript wird vom Autostart-Skript per
  passwordless sudo gerufen (siehe `install_pi_sudoers.sh`).

Reihenfolge beim Erstsetup: erst `sudo install_pi_sudoers.sh`, dann
`install_xfce_autostart.sh` — sonst fehlt die NOPASSWD-Berechtigung
und die Policy wird nicht geschrieben (laute Warnung, restliches
Autostart laeuft trotzdem durch).

Aenderung der Kiosk-URL (z.B. neues LAN-Subnetz):

```bash
sudo KIOSK_ORIGIN=http://<neue-ip>:5000 bash /opt/zentrale/scripts/install_firefox_mic_policy.sh
ZENTRALE_BACKEND_URL=http://<neue-ip>:5000 bash /opt/zentrale/scripts/install_xfce_autostart.sh
sudo systemctl restart lightdm
```

### Notaus-Hotkey: Ctrl+Alt+Esc

Wenn der Kiosk zickt oder man ans Terminal will:

- **Drücken:** `Ctrl+Alt+Esc` → `lightdm` stoppt, Pi landet auf
  **TTY1** (Konsole, Login-Prompt).
- **Zurück zum Kiosk:** `sudo systemctl start lightdm`.
- Die Bridge und (auf einem `--voll`-Host) `zentrale.service` laufen
  weiter im Hintergrund — wenn man auch das stoppen will, dann manuell.
- Voraussetzung: `scripts/install_pi_sudoers.sh` wurde einmal mit
  `sudo` ausgeführt, sonst kann `emergency_exit.sh` lightdm nicht
  stoppen (siehe unten).

## 5) Logs prüfen

Aussenposten: Bridge-Log `sudo journalctl -u pi_sensor_bridge.service -f`,
Zimmer-stderr `/tmp/zentrale-tutor-room.log`, Updater-Log siehe
`memory/system/topologie.md`.

Backend-Host (`--voll`):

```bash
ssh pi@192.168.1.xx "sudo journalctl -u zentrale.service -f"
```

Live-Tail des systemd-Logs. Was hier ankommt:

- `print()`-Ausgaben aus `main.py` (z. B. `EVENT IN:` / `EVENT OUT:`)
  und `actions.py` (z. B. `ACTION: Good Morning ☀️`).
- Flask-Request-Logs von `ui/app.py` (Standard-Werkzeug-Output).

Was hier **nicht** ankommt: die `NET →` / `STT →` / `TTS →`-Einträge
aus `net.py` und `audio.py`. Die landen ausschließlich in
`state.push_log` und damit nur im Dashboard-Terminal, nicht in
journalctl. Wer sie auch in journalctl sehen will, müsste
`state.push_log` zusätzlich `print()` lassen.

## 6) Auto-Update via RELEASE-Marker (Pull-Cron) — der Git-Weg

> **Fuer Aussenposten abgeloest** (2026-09-04). Ein Knoten ohne Backend
> braucht kein git mehr: er holt sich ein zugeschnittenes Paket
> (`deploy/aussenposten-update.cron` → `scripts/aussenposten_update.py`,
> siehe `memory/system/topologie.md`). Der hier beschriebene Weg — Git-Clone
> auf dem Knoten, `pi_autopull.sh`, manueller Bump in `deploy/RELEASE` —
> bleibt fuer einen vollwertigen **Backend-Host** gueltig.

### Idee

Nicht jeder `git push` soll automatisch deployen. Stattdessen prüft ein
Cronjob auf dem Pi alle 5 Minuten, ob im Remote-Repo die Datei
[`deploy/RELEASE`](../../deploy/RELEASE) einen anderen Inhalt hat als
lokal auf dem Pi. Nur dann wird gepullt + Service neu gestartet.

**Workflow:**

1. Code ändern, committen, pushen → der Pi ignoriert das.
2. Wenn deployt werden soll: in `deploy/RELEASE` die Zahl hochziehen,
   committen, pushen → Pi zieht beim nächsten Cron-Tick und startet
   den Service neu.

### Komponenten

| Datei | Funktion |
|---|---|
| `deploy/RELEASE` | Trigger-Datei. Nur wenn dieser Inhalt sich ändert, deployt der Pi. |
| `scripts/pi_autopull.sh` | Cron-Worker auf dem Pi: fetch → diff → ggf. pull + pip + restart. |
| `deploy/zentrale-autopull.cron` | Crontab-Snippet, alle 5 min. |
| `.aussenposten` (auf dem Knoten, nicht im Repo) | Marker von `deploy_pi.sh`. Liegt er, nimmt der Autopull `deploy/requirements-aussenposten.txt` statt `requirements.txt`. |

**Der pip-Schritt haengt an der richtigen Datei:** Der Autopull prueft, ob
sich *die fuer diesen Knoten gueltige* Requirements-Liste geaendert hat — auf
einem Aussenposten also die kurze. Ohne diesen Schnitt haette jede Aenderung
an der grossen `requirements.txt` (Backend-Pakete wie faster-whisper oder
sherpa-onnx) per Cron einen minutenlangen Quellcode-Build auf dem 32-bit-Pi
angeworfen.

### Einmal-Setup auf dem Pi

**a) Erstdeployment** wie oben (`scripts/deploy_pi.sh --voll`). Dadurch liegt
das Projekt unter `/opt/zentrale` und der systemd-Service läuft.

**b) Repo als Git-Clone hinterlegen** (rsync-Kopie hat kein `.git`,
also kann der Cron nicht pullen). Auf dem Pi einmalig:

```bash
sudo mv /opt/zentrale /opt/zentrale.bak
sudo git clone git@github.com:Eightdevvis/ZENTRALE.git /opt/zentrale
sudo cp -r /opt/zentrale.bak/.venv /opt/zentrale/   # venv übernehmen
sudo cp -r /opt/zentrale.bak/data /opt/zentrale/    # Daten übernehmen
sudo chown -R $USER:$USER /opt/zentrale
```

**c) SSH-Deploy-Key auf dem Pi erzeugen:**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/zentrale_deploy -N ""
cat ~/.ssh/zentrale_deploy.pub
```

Den `.pub`-Inhalt bei GitHub eintragen unter
**Repo → Settings → Deploy keys → Add deploy key** (read-only reicht
völlig).

Damit Git den Key automatisch nutzt, in `~/.ssh/config` auf dem Pi:

```
Host github.com
  IdentityFile ~/.ssh/zentrale_deploy
  IdentitiesOnly yes
```

Test: `ssh -T git@github.com` muss „Hi <user>! You've successfully
authenticated…" sagen.

**d) Passwordless sudo für autopull + Notaus:**

```bash
sudo bash /opt/zentrale/scripts/install_pi_sudoers.sh
```

Schreibt `/etc/sudoers.d/zentrale` mit eng definierten Befehlen:

- `systemctl restart zentrale.service` (autopull-Restart)
- `systemctl restart whisper.service` (autopull-Restart)
- `systemctl restart tts.service` (autopull-Restart)
- `systemctl stop lightdm` (Notaus-Hotkey)
- `chvt 1` (Notaus → TTY1)
- `/opt/zentrale/scripts/install_pi_services.sh` (autopull patcht
  Unit-Files wenn sich `deploy/*.service` im Repo ändert)
- `/opt/zentrale/scripts/install_firefox_mic_policy.sh`
  (`install_xfce_autostart.sh` laesst damit die Kiosk-Mic-Policy
  ohne Passwort schreiben — siehe Abschnitt "Mikrofon-Berechtigung
  im Kiosk")

Bewusst eng — keine `ALL`-Freibriefe. Die alte
`/etc/sudoers.d/zentrale-autopull`-Datei wird vom Skript automatisch
aufgeräumt.

**e) Manueller Trockenlauf** vor Cron-Aktivierung:

```bash
/opt/zentrale/scripts/pi_autopull.sh
cat ~/.zentrale_autopull.log
```

Sollte ohne Aktion durchlaufen (RELEASE noch unverändert).

**f) Cron aktivieren:**

```bash
crontab /opt/zentrale/deploy/zentrale-autopull.cron
crontab -l
```

### Bedienung

- **Deploy auslösen:** Zahl in `deploy/RELEASE` hochziehen, committen,
  pushen. In max. 5 Minuten ist das Update auf dem Pi.
- **Log live mitlesen:** `tail -f ~/.zentrale_autopull.log` auf dem Pi.
- **Verbose-Modus** (jeden Tick loggen statt nur Aktionen): in der
  Crontab `AUTOPULL_VERBOSE=1` vor dem Befehl setzen.

### Stolperstellen

- **Lokale Änderungen auf dem Pi** (z.B. mal schnell was zum Debuggen
  editiert) blockieren den Cron-Pull. Das Script wird laut im Log und
  startet **nicht** den Service neu. Lokale Änderungen müssen manuell
  weggeräumt werden (`git stash` oder commit + push).
- **`pip install`** läuft nur wenn sich `requirements.txt` zwischen
  HEAD und origin geändert hat (Optimierung, sonst 30+ Sek pro Deploy).
- **Unit-File-Sync** läuft nur wenn sich `deploy/*.service` zwischen
  HEAD und origin geändert hat → ruft `install_pi_services.sh` via
  passwordless sudo. Patched User=, kopiert nach `/etc/systemd/system/`,
  daemon-reload + enable.
- **Restart** trifft alle drei Units: zentrale, whisper, tts.
- **Pull ist `--ff-only`**: Merges aus dem Cron sind ausgeschlossen.
  Wenn auf dem Pi ein lokaler Commit existiert, schlägt der Pull fehl
  statt heimlich zu mergen.
- **SSH-Key-Pfad im Cron:** Cron erbt nicht das volle Login-Environment.
  Wenn der Key woanders liegt als `~/.ssh/id_*`, muss er entweder über
  die `~/.ssh/config` (siehe oben) gefunden werden oder im Script via
  `GIT_SSH_COMMAND` gesetzt werden.

## Historie

- **2026-05** — PC↔Pi-Migration: Backend vom Pi auf den PC, Pi nur noch
  Kiosk + Bridge. Vorher musste bei jedem Hotspot-Wechsel die Bridge-Env
  angepasst werden; seit der festen LAN-IP `192.168.50.1` entfaellt das.
- **2026-06-02** — Firefox-Kiosk wurde selbstheilend (Endlos-Schleife statt
  „240 s warten, dann starten"): der Pi bootete vor dem PC, das Fenster lief
  ab, Firefox hing fuer immer auf der Fehlerseite. Gleicher Tag: der
  `localhost`-Footgun (oben).
- **2026-06-07** — `Wants=`-Kopplung der PC-Units: `restart zentrale-pc`
  startete NUR das Backend, Whisper/TTS blieben unten, im Dashboard stand
  dauerhaft `[TTS nicht erreichbar]`.
- **2026-06-27** — Kiosk-Default `tui` statt Firefox (Pi 3 rendert das
  Dashboard nur in Software, ein Kern am Anschlag).
- **2026-09-03/04** — `deploy_pi.sh` mit zwei Modi (Aussenposten-Positivliste
  vs. `--voll`); Aussenposten holen ihr Paket per HTTP statt git.
- **2026-09-14** — Kiosk-Default `room`: das Persona-Zimmer ist das Wandbild,
  die TUI liegt dahinter (Commit f499953).
