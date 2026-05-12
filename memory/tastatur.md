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
| `m`    | Motion Sensor (Presence) – startet den Tutor, sofern keine Session läuft |
| `k`    | Data-Collection-Modus öffnen          |
| `c`    | Chat-Panel öffnen                     |
| `t`    | Mandarin-Tutor starten                |
| `ESC`  | Zurück zum Haupt-Dashboard            |

## System-Hotkey (Pi-Kiosk, OS-Ebene)

| Taste              | Funktion                                              |
|--------------------|-------------------------------------------------------|
| `Ctrl+Alt+Esc`     | **Notaus** — stoppt `lightdm`, Pi landet auf TTY1.    |

Wirkt auf OS-Ebene (XFCE-Keyboard-Shortcut, nicht in der Webapp).
Backend-Services (`zentrale`, `whisper`, `tts`) laufen weiter. Zurück
zum Kiosk: `sudo systemctl start lightdm`. Details:
`deployment.md` → „Notaus-Hotkey".

## Im Tutor-Modus (zusätzlich)

| Taste   | Funktion                            |
|---------|-------------------------------------|
| `Space` | Aufnahme starten / stoppen          |
| `ESC`   | Session beenden                     |

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
