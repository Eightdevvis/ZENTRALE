# Starten (lokal)

Seit der PC↔Pi-Migration (siehe `topologie.md`) laufen alle drei
Backend-Prozesse auf dem **PC**, nicht mehr auf dem Pi. Der Pi
ist Display-Kiosk + Sensor-Bridge.

ZENTRALE besteht aus **drei Prozessen** (Event-Loop+Flask, Whisper, TTS).
Drei Wege sie hochzufahren:

## Variante 0 — systemd Auto-Start (Headless, Boot-getriggert)

Fuer den Alltag: drei System-Units in `deploy/*-pc.service`, die ohne
Login beim Boot starten. Setup + Befehle: siehe `deployment.md`,
Abschnitt „PC-systemd-Services". Vorteil: PC anschalten reicht – nichts
zu tippen. Nachteil: keine Tastatur-Sensor-Sim (sudo waere noetig).

## Variante A — Ein-Befehl-Start: Kassetten-Menü (interaktiv, Dev)

```bash
zentrale
```

(Symlink in `~/.local/bin/zentrale` → `scripts/select_kassette.sh`. Funktioniert
von jedem Verzeichnis aus. Falls der Symlink mal fehlt:
`ln -s "$PWD/scripts/select_kassette.sh" ~/.local/bin/zentrale` aus dem
Projekt-Root.)

`zentrale` zeigt seit 2026-06 ein **Kassetten-Menü** („Welche Kassette wählen?",
`tui/select_kassette.py`): mit ↑/↓ wählen (ein animierter Stern ✶ funkelt auf der
aktuellen Zeile), Enter startet — danach läuft ein Regenbogen-Ladebalken und das
Menü exec't in das passende Start-Skript:

| Auswahl    | startet            | KI   |
|------------|--------------------|------|
| monolith   | `start_local.sh`   | an   |
| laptop     | `start_laptop.sh`  | aus  |
| tui        | `start_tui.sh`     | aus  |

Das Menü selbst ist reine stdlib (termios + ANSI, kein curses); Render-/Logik
sind ohne TTY testbar (`venv/bin/python tui/select_kassette.py --selftest`).
Direkt ohne Menü: `zentrale-laptop` / `zentrale-tui` (s.u.).

**monolith** (die Vollvariante) startet alle drei Services parallel in einem
Terminal, jede Zeile mit farbigem `[main]`/`[whisper]`/`[tts]`-Prefix. Kein
`sudo`, dafür keine Tastatur-Sensor-Simulation – Sensoren manuell triggern via:

```bash
curl -X POST http://localhost:5000/api/sensor/button
curl -X POST http://localhost:5000/api/sensor/motion
curl -X POST http://localhost:5000/api/sensor/light
curl -X POST http://localhost:5000/api/sensor/door
```

Mit `./scripts/start_local.sh --with-keyboard` läuft `core/main.py`
unter `sudo`, dann geht auch die `b`/`l`/`m`-Tasten-Sim.

`Ctrl+C` beendet alle drei sauber.

## Variante A-Laptop — Laptop-Kassette (KI-frei, „ZENTRALE in klein")

Für eine RAM-schwache Laptop-Maschine. Eigener Start-Befehl, eigene
Kassette (`ui/templates/laptop.html`, siehe `dashboard.md` → „Kassetten"):

```bash
zentrale-laptop
```

(Symlink `~/.local/bin/zentrale-laptop` → `scripts/start_laptop.sh`. Falls er
fehlt: `ln -s "$PWD/scripts/start_laptop.sh" ~/.local/bin/zentrale-laptop` aus
dem Projekt-Root.)

Unterschiede zum normalen `zentrale`:

- Setzt `ZENTRALE_KASSETTE=laptop` → `main.py` lässt Ollama-Warmup + News-
  Fetcher weg (kein Auto-Bootup), `app.py` riegelt die KI-Endpoints ab.
  **Ollama wird nie angesprochen.**
- Startet **nur** `core/main.py` (Event-Loop + Flask) — **kein** Whisper,
  **kein** TTS. Spart RAM.
- Flask liefert `laptop.html` statt `monolith.html`.

**Minimal-Dependencies** (das KI-freie Backend braucht nicht den vollen
Stack): es reichen `flask` + `python-dateutil`:

```bash
venv/bin/pip install flask python-dateutil
```

(`keyboard` nur für `--with-keyboard`/Tasten-Sim; Whisper/TTS/sherpa/piper
werden hier nicht gebraucht.)

`--with-keyboard` geht auch hier (main.py via `sudo -E`, damit die Kassetten-
Env-Var root erreicht). Dashboard auf `http://localhost:5000`.

## Variante A-TUI — Terminal-Kassette (kein Browser)

Die leanste Front: ZENTRALE direkt im Terminal (curses), gegen dasselbe
Backend. Motivation: ein Browser-Tab kostet auf einer RAM-schwachen Maschine
300–600 MB+, das Backend nur ~32 MB — die TUI spart genau den Browser.

```bash
zentrale-tui
```

(Symlink `~/.local/bin/zentrale-tui` → `scripts/start_tui.sh`. Falls er fehlt:
`ln -s "$PWD/scripts/start_tui.sh" ~/.local/bin/zentrale-tui`.)

Was passiert: `ZENTRALE_KASSETTE=tui` → Backend ki-frei (wie laptop). Das Skript
startet `core/main.py` im Hintergrund mit **stdout → Logdatei**
(`/tmp/zentrale-tui-backend.log`, sonst würde es die curses-Oberfläche
zerschießen — die Logs erscheinen ohnehin im stdout-Panel der TUI) und dann die
TUI. `q` in der TUI beendet alles (TUI, tmux-Fenster, Backend).

- **Dependencies:** nur `flask` + `python-dateutil` fürs Backend; die TUI selbst
  ist reine stdlib (`curses`). Kein Browser, kein Whisper/TTS. Für das untere
  echte Terminal (s.u.): `tmux` (sonst Fallback = TUI im Vollbild).
- **Standalone** (TUI gegen ein schon laufendes Backend, z.B. auf einer anderen
  Maschine): `ZENTRALE_URL=http://<host>:5000 venv/bin/python tui/zentrale_tui.py`
- **Selbsttest** (ein Text-Snapshot, ohne curses):
  `venv/bin/python tui/zentrale_tui.py --selftest`

### Unten angeklebtes ECHTES Terminal (tmux-Split)

Ist `tmux` installiert, bootet `zentrale-tui` ein **tmux-Fenster mit zwei Panes**:
oben die TUI (Dashboard), unten eine **echte bash**. Die untere Shell ist ein
vollwertiges Terminal — `cd`, `ls`, Tab-Completion, History, Pipes, alles. Kein
nachgebautes „Fake-Terminal": die TUI bleibt reine Anzeige, fürs Navigieren/
Öffnen nutzt man die echte Shell drunter.

- **Dateien öffnen:** terminal-nativ mit `xdg-open` — erkennt den Typ und nimmt
  die Standard-App. PDF-Default ist **zathura** (gesetzt via
  `xdg-mime default org.pwmt.zathura.desktop application/pdf`). Also einfach:
  ```
  xdg-open ~/Downloads/bericht.pdf    # → zathura
  xdg-open /pfad/bild.png             # → Standard-Bildviewer
  zathura x.pdf                       # spezifische App direkt
  ```
  Default pro Typ ändern: `xdg-mime default <app>.desktop <mime/typ>`. App
  auswählen statt Default: `mimeopen -a <datei>`.
- **Pane wechseln:** Maus-Klick (Maus-Modus an) oder `Ctrl-b` dann `↑`/`↓`.
  Fokus startet oben auf der TUI; die untere bash startet im `$HOME`.
- **Höhe der bash:** `ZENTRALE_TERM_LINES=16 zentrale-tui` (Default 12 Zeilen).
- **Kein tmux:** Fallback = TUI im Vollbild + Hinweis `sudo apt install tmux`.

> Hinweis: Der frühere TUI-Befehl `/slide` (festes zathura auf `data/slides/`)
> ist damit überflüssig — er bleibt als Kurzbefehl bestehen, aber der normale
> Weg ist jetzt `xdg-open` in der echten Shell unten.

## Variante B — 3 Terminals manuell

Sinnvoll wenn man einen einzelnen Service oft neustartet oder dessen
stdin braucht (z.B. zum Debuggen).

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
OLLAMA_MODEL=qwen3.5:9b             # default
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
