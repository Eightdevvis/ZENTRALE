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
| `c`    | Chat-Panel öffnen                     |
| `ESC`  | Zurück zum Haupt-Dashboard            |

## Im Canvas (Browser: monolith + laptop)

Nackte Buchstaben wirken nur, wenn **kein Eingabefeld fokussiert** ist (im
Monolith hängt der Fokus beim Start in der Chat-Konsole → einmal `ESC`, dann
greifen sie). Mit Modifier gehts immer.

| Taste     | Funktion                                                          |
|-----------|-------------------------------------------------------------------|
| `f`       | Fokus-Werkzeug (Listen) auf                                       |
| `k`       | **Klavier auf/zu** (Toggle; nochmal `k` → zurück ins Auto-Programm) |
| `Alt + K` | Data-Collection-Modus öffnen (**nicht** nacktes `k` — das ist das Klavier) |
| `ESC`     | offenes Klavier zu                                                |

### Im Klavier (Exhibit „Klavier")

Die Buchstabenreihen **sind** die Klaviatur: untere Reihe weiß, die Reihe
darüber schwarz — dort, wo sie physisch dazwischen liegt. `f` und `k` fallen
in die Lücken E–F und H–C (keine schwarze Taste) und bleiben deshalb frei.

| Taste                   | Funktion                                        |
|-------------------------|-------------------------------------------------|
| `y x c v b n m , . -`   | weiße Tasten (C D E F G A H C D E)              |
| `s d · g h j · l ö`     | schwarze Tasten                                 |
| `←` / `→`               | Oktave runter/rauf (C3 … C6)                    |
| `Leertaste`             | Melodie aufnehmen / stoppen (fragt beim Stoppen nach dem Namen) |
| `Enter`                 | zuletzt aufgenommene Melodie abspielen / Wiedergabe stoppen |
| `k` / `ESC`             | Klavier zu                                      |

Siehe `dashboard.md` → „Klavier".

### Im Klavier der TUI (Taste `k`, Terminal-Kassette)

Gleiche Klaviatur, gleiche Melodien (dieselbe Registry `data/melodies.json`).
Drei Unterschiede, die aus dem Terminal kommen:

| Taste        | Funktion                                                       |
|--------------|----------------------------------------------------------------|
| `↑` / `↓`    | Melodie wählen (der Browser klickt stattdessen ihren Chip)      |
| `Enter`      | **gewählte** Melodie abspielen / Wiedergabe stoppen             |
| `r`          | gewählte Melodie umbenennen                                     |
| `D` (groß)   | gewählte Melodie löschen — nacktes `d` ist die Taste D♯          |
| `t`          | Theme wechseln (gilt im Klavier wie überall sonst)               |

- **Die Tasten sind beschriftet:** die gezeichnete Klaviatur trägt jeden
  Buchstaben auf seiner Taste (weiße vorne, schwarze oben), deshalb steht in
  der Statuszeile nur noch, was man sonst nirgends sieht (Oktave, Aufnahme,
  Melodien).
- **Kein Halten:** curses meldet nur Tastendrücke, kein Loslassen. Jeder
  Anschlag klingt deshalb fest 420 ms aus; im Browser aufgenommene Melodien
  behalten ihre echten Haltedauern.
- **Ton kommt aus `core/tone.py`** (numpy + sounddevice, erst beim Öffnen
  geladen). Fehlt das Gerät, steht `♪ stumm` im Kopf und Noten + Aufnahme
  laufen trotzdem. `ZENTRALE_NO_AUDIO=1` schaltet den Ton bewusst ab.

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
