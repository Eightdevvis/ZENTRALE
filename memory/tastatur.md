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
| `m`    | Motion Sensor (Presence) – aktuell ohne Folgewirkung, Tutor-Trigger pausiert |
| `k`    | Data-Collection-Modus öffnen          |
| `c`    | Chat-Panel öffnen                     |
| `ESC`  | Zurück zum Haupt-Dashboard            |

> `t` (Mandarin-Tutor) ist pausiert – siehe `tutor_system.md`.

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
