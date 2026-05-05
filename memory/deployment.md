# Deployment auf Raspberry Pi

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

## 3) systemd-Service

Template liegt in `deploy/zentrale.service`. Wird vom Deploy-Script
nach `/etc/systemd/system/` kopiert und enabled.

**Wichtig:**
- Der Service startet **nur `core/main.py`** – Whisper und TTS laufen
  NICHT automatisch via systemd. Wenn der Tutor auf dem Pi voll
  funktionieren soll, brauchst du eigene `whisper.service` und
  `tts.service` Units (oder ein Master-Skript).
- `User=<dein-pi-user>` (vom Deploy-Script gesetzt) – also **kein**
  `sudo`. Das heißt die Tastatur-Simulation funktioniert auf dem Pi
  nicht, was ja eh ok ist, weil dort der echte PIR-Sensor (geplant)
  übernehmen soll.

## 4) Kiosk-Modus (Auto-Start im Vollbild)

`~/.config/autostart/zentrale.desktop`:

```ini
[Desktop Entry]
Type=Application
Exec=firefox-esr --kiosk http://localhost:5000
```

Wenn der Pi hochfährt, startet automatisch Firefox im Kiosk-Modus auf
das Dashboard. Kein Desktop, kein Browser-UI – nur ZENTRALE.

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

**d) Passwordless sudo für genau den Restart-Befehl:**

```bash
echo "$USER ALL=(ALL) NOPASSWD: /bin/systemctl restart zentrale.service" \
  | sudo tee /etc/sudoers.d/zentrale-autopull
sudo chmod 440 /etc/sudoers.d/zentrale-autopull
```

Bewusst eng: nur dieser eine Befehl, kein Generalfreibrief.

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
- **Pull ist `--ff-only`**: Merges aus dem Cron sind ausgeschlossen.
  Wenn auf dem Pi ein lokaler Commit existiert, schlägt der Pull fehl
  statt heimlich zu mergen.
- **SSH-Key-Pfad im Cron:** Cron erbt nicht das volle Login-Environment.
  Wenn der Key woanders liegt als `~/.ssh/id_*`, muss er entweder über
  die `~/.ssh/config` (siehe oben) gefunden werden oder im Script via
  `GIT_SSH_COMMAND` gesetzt werden.
- **Whisper/TTS-Services** werden hier nicht neu gestartet, nur
  `zentrale.service`. Wenn dort später Änderungen einfließen, eigene
  systemd-Units bauen und das Script erweitern.
