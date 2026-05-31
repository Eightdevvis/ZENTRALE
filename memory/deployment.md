# Deployment auf Raspberry Pi

**Stand (2026-05):** Seit der PC↔Pi-Migration (siehe `topologie.md`)
hostet der Pi **kein Backend mehr**. Auf dem Pi laufen nur noch:

- Firefox-Kiosk (zeigt das PC-Dashboard)
- `pi_sensor_bridge.service` (Hardware-Sensoren → HTTP an PC)

Die unten beschriebenen `zentrale.service` / `whisper.service` /
`tts.service` sind auf dem Pi `disabled`. Die Anleitung bleibt
trotzdem hier dokumentiert – falls ein Setup mal ohne PC laufen soll
oder ein zweiter Pi mit eigenem Backend aufgesetzt wird.

## Pi-Sensor-Bridge (aktiver Service)

Einmalig auf dem Pi:

```bash
sudo cp /opt/zentrale/deploy/pi_sensor_bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
echo 'ZENTRALE_BACKEND_URL=http://192.168.50.1:5000' | sudo tee /etc/zentrale-bridge.env
sudo systemctl enable --now pi_sensor_bridge.service
```

Die PC-IP `192.168.50.1` ist seit der LAN-Migration (siehe
`topologie.md`) **fest**. Frueher musste man bei jedem Hotspot-Wechsel
die env-Datei updaten – das entfaellt jetzt. Sollte sich die IP doch
mal aendern (anderes LAN-Subnetz), beide Endpunkte konsistent
anpassen: hier, im Pi-Kiosk-Autostart (`install_xfce_autostart.sh`
mit `ZENTRALE_BACKEND_URL=...`) und in den PC-systemd-Services.

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

Damit man nicht erst zum PC laufen und ihn anschalten muss, wenn man
heimkommt, weckt der Pi den PC ueber Wake-on-LAN aus S5 (soft-off).
Das Pi bleibt 24/7 an, der PC darf schlafen.

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

Manueller Trigger zum Testen (PC vorher in S5 bringen):
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

**Kiosk-Wartezeit angepasst:** Der Firefox-Kiosk-Autostart
(`install_xfce_autostart.sh`) wartet bis zu 240s (4 min) per `curl`
auf das Backend, bevor Firefox startet. Grund: PC-Boot inkl. LUKS-
Eingabe + Pop-Boot + systemd-Services kann 90-180s dauern, mit
Puffer 240s. Vorher waren das nur 60s, was bei WoL-Boot regelmaessig
zu fruehzeitigem Firefox-Start auf einer toten URL fuehrte.

Spaeter sinnvoll: zusaetzlicher Aufruf aus `pi_sensor_bridge.py` bei
PIR-/Tuer-/Button-Trigger fuer den „Sasha kommt zur Tuer rein"-Flow.
Der Boot-Trigger deckt nur das „Pi geht an"-Szenario (Stromausfall,
manueller Pi-Start).

## 1) Pi vorbereiten (einmalig)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip rsync firefox-esr
```

## 2) Deployen

`scripts/deploy_pi.sh` macht in 6 Schritten:

1. `rsync -az --delete` (excludes: `__pycache__`, `.git`, `.venv`)
2. `python3 -m venv .venv` auf dem Pi (falls noch nicht da)
3. `pip install --upgrade pip`
4. `pip install -r requirements.txt`
5. `zentrale.service` mit `User=<deine-pi-user>` patchen + nach
   `/etc/systemd/system/` kopieren, daemon-reload + enable
6. `systemctl restart zentrale.service` + Status anzeigen

```bash
chmod +x scripts/deploy_pi.sh
./scripts/deploy_pi.sh pi@192.168.1.xx /opt/zentrale
```

**Achtung – venv-Inkonsistenz:** lokal heißt der Virtualenv-Ordner
`venv` (siehe `setup.md`), auf dem Pi heißt er `.venv` (mit Punkt!).
Das deploy-Script erstellt automatisch `.venv` auf dem Pi und der
systemd-Service erwartet ebenfalls `.venv`. Wenn du manuell auf dem Pi
arbeitest: nutze `.venv/bin/python`, nicht `venv/bin/python`.

## 3) systemd-Services

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

**Wichtig:**
- `User=<dein-pi-user>` (vom Deploy-Script gesetzt) – also **kein**
  `sudo`. Das heißt die Tastatur-Simulation funktioniert auf dem Pi
  nicht, was ja eh ok ist, weil dort der echte PIR-Sensor (geplant)
  übernehmen soll.
- Die Templates haben `User=pi` als Platzhalter, der zur Laufzeit
  durch den SSH-User ersetzt wird.

## 4) Kiosk-Modus (Auto-Start im Vollbild, ohne XFCE-UI)

Ziel: Pi bootet → kurze Konsole → schwarzer Bildschirm → Firefox-Kiosk.
**Kein XFCE-Panel, kein Wallpaper, kein Mauszeiger** dazwischen.

`scripts/install_xfce_autostart.sh` macht das komplett (User-Ebene):

1. **Custom `xfce4-session.xml`** (`~/.config/xfce4/xfconf/xfce-perchannel-xml/`):
   überschreibt die Default-Failsafe-Session der XFCE-Installation.
   Startet **nur xfwm4 + xfsettingsd** — kein xfce4-panel, kein
   xfdesktop, kein Thunar. Root-Window bleibt schwarz bis Firefox
   übernimmt.
2. **xfwm4 backup-autostart** in `~/.config/autostart/xfwm4.desktop`.
   Belt-and-Suspenders falls die Session-XML mal nicht greift —
   Firefox-Kiosk-Fullscreen braucht den WM.
3. **`~/.xprofile`** mit `xrandr --mode 1920x1080`.
4. **`~/.config/autostart/zentrale.desktop`** mit Firefox-Kiosk auf
   `http://localhost:5000` — **wartet vorher per `curl` bis der Core
   auf Port 5000 antwortet**, damit man nicht initial die Fehlerseite
   sieht.
5. **Notaus-Hotkey `Ctrl+Alt+Esc`** → `scripts/emergency_exit.sh`
   (lightdm-stop → Pi auf TTY1).

Plus auf Root-Ebene (via `install_pi_services.sh`):

6. **lightdm-Drop-in** `/etc/lightdm/lightdm.conf.d/10-zentrale.conf`
   aus `deploy/lightdm-zentrale.conf`. Setzt `xserver-command=X -nocursor`
   → kein Mauszeiger ab X-Start (wir haben keine Maus am Kiosk).

Aufruf auf dem Pi nach jedem RE-Setup:

```bash
bash /opt/zentrale/scripts/install_xfce_autostart.sh
```

Idempotent. Der Hotkey-Teil funktioniert nur aus einer aktiven
XFCE-Session (DBus muss laufen).

### Mikrofon-Berechtigung im Kiosk

Der Pi-Kiosk laedt das Dashboard von `http://192.168.50.1:5000` (PC-LAN-
IP). Damit der Mic-Button (`#chat-mic-btn`, siehe `audio_system.md`)
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
- **`zentrale.service` läuft weiter** im Hintergrund — wenn man auch
  das stoppen will, dann manuell: `sudo systemctl stop zentrale whisper tts`.
- Voraussetzung: `scripts/install_pi_sudoers.sh` wurde einmal mit
  `sudo` ausgeführt, sonst kann `emergency_exit.sh` lightdm nicht
  stoppen (siehe unten).

## 5) Logs prüfen

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

## 6) Auto-Update via RELEASE-Marker (Pull-Cron)

### Idee

Nicht jeder `git push` soll automatisch deployen. Stattdessen prüft ein
Cronjob auf dem Pi alle 5 Minuten, ob im Remote-Repo die Datei
[`deploy/RELEASE`](../deploy/RELEASE) einen anderen Inhalt hat als
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

### Einmal-Setup auf dem Pi

**a) Erstdeployment** wie oben (`scripts/deploy_pi.sh`). Dadurch liegt
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
