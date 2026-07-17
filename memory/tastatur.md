# Tastatur-Belegung

Solange kein echter GPIO da ist, simulieren wir alle Sensoren über die
Tastatur. Damit das funktioniert, muss `core/main.py` **mit `sudo`**
laufen – die `keyboard`-Library braucht Root, um globale Keypress-
Events abzugreifen.

Ohne `sudo` startet alles bis auf die Tastatur-Erkennung; die Sensoren
bleiben dann einfach still (das Dashboard funktioniert weiterhin, nur
ohne Inputs).

## Globale Tasten (Haupt-Dashboard)

| Taste  | Funktion                              |
|--------|---------------------------------------|
| `b`    | Button gedrückt (Sensor)              |
| `l`    | Light Sensor Trigger                  |
| `m`    | Motion Sensor (Presence) – `PRESENCE_DETECTED` → `tutor_port.presence_ping()`: nonverbale Reaktion (schaut hoch, Mimik) **nur bei laufender Tutor-Session**, kein Auto-Start, kein verbaler Gruß. Default an, per `TUTOR_PRESENCE_REACT=0` aus |
| `k`    | Data-Collection-Modus öffnen          |
| `c`    | Chat-Panel öffnen                     |
| `ESC`  | Zurück zum Haupt-Dashboard            |

> Der Sprachtutor ist **reaktiviert** und wird im Chat-Modus per `Alt + T`
> umgeschaltet (nicht mehr über diesen Sensor-Trigger). Der Presence-Auto-Start
> bleibt bewusst aus – siehe `tutor_system.md`.

## Im Chat-Modus (zusätzlich)

| Taste     | Funktion                                                    |
|-----------|-------------------------------------------------------------|
| `Enter`   | Nachricht senden                                            |
| `Alt + M` | Mikrofon-Toggle (Aufnahme an/aus → Whisper-Transkription)   |
| `Alt + S` | Stimme stumm/an (Auto-Speak der KI-Antwort, Zustand gemerkt) |
| `Alt + S` + `↑`/`↓` | Lautstärke lauter/leiser (Schritt 10%, in `localStorage` gemerkt) |
| `Alt + T` | Tutorkanal an/aus (Sprachtutor). Roter Rahmen um die Mitte, Eingaben gehen an den Tutor statt die Haupt-KI. Toggle. Siehe `tutor_system.md`. |
| `ESC`     | zurück zum Haupt-Dashboard                                  |

Alt-Modifier verhindert dass das `m`/`s` als Buchstabe ins Input-Feld
geht. `Alt + S` toggelt die Sprachausgabe (Zustand in `localStorage`,
übersteht Reload/Kiosk-Neustart) — bewusst **nur** als Shortcut, kein
klickbarer Button, weil der Pi-Kiosk keine Maus hat. Der Footer-Hinweis
`#chat-mute-hint` ist state-aware. `Alt + S` **gehalten** + `↑`/`↓` regelt
die Lautstärke (Mute feuert dann erst beim Loslassen, und nur wenn keine
Pfeiltaste kam — siehe `audio_system.md`). Siehe `dashboard.md`,
`audio_system.md`.

## System-Hotkeys (Pi-Kiosk, OS-Ebene)

Wirken auf OS-Ebene (XFCE-Keyboard-Shortcuts, nicht in der Webapp).
Verdrahtung passiert in `scripts/install_xfce_autostart.sh` via
`xfconf-query` und ist persistent.

| Taste              | Funktion                                              |
|--------------------|-------------------------------------------------------|
| `Ctrl+Alt+Esc`     | **Notaus** — stoppt `lightdm`, Pi landet auf TTY1. Backend-Services laufen weiter. Zurueck zum Kiosk: `sudo systemctl start lightdm`. Details: `deployment.md` → „Notaus-Hotkey". |
| `Ctrl+Alt+T`       | **Pi-Terminal aufrufen** — oeffnet ein xterm floating ueber dem Firefox-Kiosk. Zum Schliessen `Ctrl+D` oder Fenster zu, dann ist der Kiosk wieder vorn. Nuetzlich um schnell etwas auf dem Pi zu checken ohne SSH-Umweg. |

## Im Data-Collection-Modus (zusätzlich)

Im Kategorie-Auswahlbildschirm:

| Taste     | Funktion                         |
|-----------|----------------------------------|
| `1`, `2`… | Kategorie wählen                 |
| `ESC` / `k` | zurück                         |

Im Formular:

| Taste     | Funktion                                          |
|-----------|---------------------------------------------------|
| `↑` / `↓` | zwischen Feldern navigieren                       |
| `Enter`   | Feld bearbeiten (oder Smiley-Auswahl bestätigen)  |
| `←` / `→` | Smiley-Skala auswählen (im Smiley-Feld)           |
| `↑` / `↓` | Datum tageweise ändern (im date-Feld)             |
| `k`       | **speichern** und zurück zum Dashboard            |
| `ESC`     | zurück zum Dashboard **ohne** zu speichern        |

> Der Unterschied `k` vs. `ESC` im Formular ist wichtig: `k` ist die
> einzige Taste, die den Eintrag tatsächlich nach `data/<id>.json`
> schreibt.
