# Kalender auf iCalendar (.ics) — Bauplan und Umstieg

**Stand 2026-10-06:** Plan — wird gerade gebaut, **nicht live**. Der Kalender kann seine
Daten jetzt wahlweise in der alten JSON (`data/ai_calendar.json`) oder als
iCalendar-Ordner (`data/kalender/`, eine `.ics` pro Termin, vdir-Format)
halten. Umgeschaltet wird mit der Einstellung `kalender_speicher`
(`json` | `ics`, Default `json`). Sasha legt um — mit dem Migrations-Skript
`scripts/kalender_migrieren.py`, Schritte unten unter „Was Sasha tun muss".
Die öffentlichen Funktionen von `core/kalender.py` sind unverändert; nur die
Speicherschicht darunter ist getauscht. Google-Sync per vdirsyncer ist
vorbereitet (`deploy/vdirsyncer.config.example`), aber nicht eingerichtet.

## Warum

Sasha, 2026-10-06: *„bisherige daten übertragen ohne verluste, und nach
fertigstellung den kalender gegen datenverlust weitgehend absichern und gut
backups immer überall hinzuschmeißen."*

- **.ics ist die einzige Quelle der Wahrheit.** iCalendar ist der Standard,
  den Handy (Android, über Google heute, später DAVx⁵), Google, Posteo und
  jeder CalDAV-Server sprechen. Eine eigene JSON hätte für jeden dieser Wege
  einen eigenen Übersetzer gebraucht.
- **Sync macht vdirsyncer, nicht ZENTRALE.** Der Anbieterwechsel (Google →
  eigener Server/Posteo) ist dann nur eine andere vdirsyncer-Konfiguration.
- **ZENTRALE zeichnet die Ansicht selbst** (eigener Auftrag, nicht Teil
  dieses Bauplans). Kollisionen, Fahrzeiten, Alarme, Imprint und Takt bleiben
  in ZENTRALE und lesen jetzt eben `.ics`.

## Die Abbildung (mit Sasha entschieden)

| Alt (JSON) | Neu (.ics) |
|---|---|
| Ebene (`termine`, `routinen`, eigene) | ein Kalender = ein Unterordner im vdir (`data/kalender/<ebene>/`) |
| Einmal-Termin, `time`, `ende`, `ort` | VEVENT mit DTSTART/DTEND (TZID=Europe/Berlin), LOCATION |
| ganztags (ohne `time`) | DTSTART;VALUE=DATE |
| Spanne über Tage (`bis`) | **ein** VEVENT, ganztags von DTSTART bis DTEND |
| Spanne mit eigener Zeit pro Tag (`times`) | tägliche RRULE (COUNT) + Abweichungs-VEVENTs mit RECURRENCE-ID **in derselben Datei** (gleiche UID) — sonst bricht vdirsyncer; nicht in Einzeltermine zerlegt, weil Sasha die Spanne zusammenhängend sehen will |
| Routine (`rrule`) | RRULE; `ende` → DTEND |
| `aus` (einzeln deaktiviert) | EXDATE + `X-ZENTRALE-AUS` |
| `pausen` (Ferien) | EXDATEs an jeder Routine gleichen Namens + `X-ZENTRALE-PAUSE` (die Notiz mit Grund) |
| `absage_noetig` | `X-ZENTRALE-ABSAGE-NOETIG:TRUE` |
| Ebene `erlebt` | fällt weg — Inhalt wandert **unverändert** ins Archiv der Nebendaten |
| `reisezeiten`, `puffer_min`, Ebenen-Farben, `version` | Nebendaten `data/kalender_neben.json` |

Was dazu nicht passt, geht nie verloren:

- Unbekannte Zusatzfelder → `X-ZENTRALE-EXTRAS` (JSON).
- Werte, die sich in .ics nicht sauber ausdrücken lassen (z. B. die echte
  Uhrzeit `"10"` an der Basel-Spanne, ein Ende ohne Beginn) → zusätzlich
  `X-ZENTRALE-ROH` mit dem Original. Beim Lesen gewinnt ROH nur, solange
  niemand das Ereignis außerhalb geändert hat (Prüfsumme) — eine Änderung
  am Handy wird also nicht vom alten Rohwert überschrieben.
- Was gar nicht als Ereignis geht (kaputtes Datum als Schlüssel, Spanne mit
  `bis` vor `von`) → `nicht_abbildbar` in den Nebendaten, liest sich aber
  genauso zurück.
- Die Reihenfolge (wichtig für gleichzeitige Termine und damit für die
  Alarm-Texte) trägt `X-ZENTRALE-POS`.

Routinen hatten im alten Modell **keinen Anfang** (sie galten rückwirkend
für immer). Damit sich daran nichts ändert, bekommen sie in .ics einen
technischen DTSTART plus `X-ZENTRALE-OHNE-ANFANG:TRUE`; ZENTRALE rechnet sie
weiter wie vorher, Google zeigt sie ab dem Anker. Routinen, die von außen
kommen (Google), haben einen echten Anfang und werden ab dort gerechnet.

Ob Google die `X-ZENTRALE-*`-Properties behält, ist **ungetestet**. Fällt
eine weg, verliert ZENTRALE nur Bedeutung, nicht den Termin: ein
EXDATE ohne `X-ZENTRALE-AUS` wird als „deaktiviert" gelesen, ein Termin ohne
`X-ZENTRALE-POS` kommt hinten an. Gegen den Rest helfen Verlauf und
Snapshots (unten).

## Module (Schicht 2, siehe `memory/system/bauplan_kern.md`)

| Modul | Aufgabe |
|---|---|
| `kalender` | öffentliche Fassade, Rechenlogik (Kollisionen, Alarme, Imprint) — unverändert in Namen und Signaturen |
| `kalender_speicher` | wählt den Speicher (`kalender_speicher`), Pfade, Sperre gegen JSON-Schreiben nach der Migration |
| `kalender_json` | der alte Speicher, jetzt mit atomarem Schreiben |
| `kalender_ics_abbildung` | ein Termin/eine Routine ↔ VEVENT-Komponenten, rein rechnend |
| `kalender_ics` | der vdir-Speicher: lesen (mit Cache), Unterschiede schreiben, Nebendaten |
| `kalender_sicherung` | atomares Schreiben, Datei-Sperre, Verlauf, Grabsteine, Snapshots, Massenlösch-Sperre |
| `kalender_spiegel` | git-Spiegel außerhalb von `data/` |
| `kalender_migration` | Prüfen und Ausführen des Umstiegs, Feld-Inventar |

Die Fassade arbeitet weiter auf dem gewohnten Daten-Dict (`_load_raw` →
ändern → `_save_raw`). Der ics-Speicher übersetzt beim Laden die Dateien in
genau dieses Dict und schreibt beim Speichern **nur die Dateien, die sich
geändert haben**. Dadurch blieb die Rechenlogik unberührt, und ein Schreiben
fasst nie den ganzen Kalender an.

## Absicherung gegen Datenverlust

Die Falle: `data/` wird zwischen PC und Laptop per rsync Datei für Datei
abgeglichen, **nur hinzufügend, neueste Datei gewinnt**
(`memory/system/topologie.md`). Ein git-Repo IN `data/` würde dabei zerstört
(refs und index würden dateiweise überschrieben). Deshalb:

1. **Atomar schreiben:** temporäre Datei, fsync, `os.replace`. Ein Absturz
   hinterlässt nie eine halbe `.ics`.
2. **Sperre:** ein Thread-Lock im Prozess plus eine Datei-Sperre
   (`data/kalender/.zentrale.lock`) zwischen Prozessen (Backend, Skript,
   vdirsyncer-Wrapper).
3. **Verlauf** `data/kalender_verlauf/<Monat>/`: vor jeder Änderung und jeder
   Löschung landet die alte Fassung dort, Name aus Zeitstempel + Knoten +
   Ebene + UID + Aktion. Eindeutige Namen übersteht der Sync. Zurückholen:
   `kalender_sicherung.verlauf_liste()` / `wiederherstellen()`.
4. **Grabsteine** `data/kalender_verlauf/grabsteine/<uid>.json`: Weil der Sync
   nichts löscht, käme eine auf dem Laptop gelöschte Datei vom PC zurück.
   Der Grabstein sagt „gelöscht um …"; eine `.ics`, die nicht neuer ist
   (LAST-MODIFIED), gilt als Geist, wird nicht angezeigt und beim nächsten
   Schreiben weggeräumt.
5. **Massenlösch-Sperre:** löscht eine einzige Operation mehr als
   `kalender_loeschsperre` Termine (Default 5), wird **gar nichts**
   geschrieben, die Weigerung geloggt. Wiederherstellen und Rückweg dürfen
   das ausdrücklich.
6. **Tägliche Snapshots** `data/kalender_snapshots/kalender_<datum>_<knoten>.tar.gz`
   vor der ersten Änderung des Tages (und beim Start); behalten werden 30
   Tage plus jeder Monatserste für zwei Jahre. Weil sie in `data/` liegen,
   wandern sie auf den anderen Knoten.
7. **git-Spiegel** (Sasha, Nachtrag 2026-10-06: *„daten können gern in ein
   extra git repo"*): nach jedem Schreiben spiegelt ZENTRALE vdir +
   Nebendaten nach `~/.local/share/zentrale/kalender-git` (außerhalb von
   `data/`, ein Repo pro Knoten) und committet. Läuft im Hintergrund; ein
   Fehler dort verhindert nie das Schreiben des Termins. Gepusht wird nichts —
   ein privates Remote richtet Sasha selbst ein (Schritte unten). Einstellung
   `kalender_git_spiegel`: Pfad oder `aus`.
8. **Sperre gegen Rückfall:** Nach der Migration steht in den Nebendaten
   `migriert_am`. Ein Knoten, der noch auf `json` steht, darf dann nicht mehr
   in die alte JSON schreiben (er würde sonst still auseinanderlaufen) —
   Lesen geht, Schreiben wird verweigert und geloggt.
9. **vdirsyncer** bricht ab, wenn eine Seite plötzlich leer ist. Diese
   Sicherung bleibt in der Vorlage an und darf nie abgeschaltet werden.

Kalenderdaten gehen nicht ins Code-Repo: `.gitignore` deckt `data/kalender*`
und die umbenannte Alt-Datei ab.

## Migration

`scripts/kalender_migrieren.py` hat drei Modi:

- **prüfen** (Standard, ändert nichts): liest die alte JSON, schreibt in ein
  Temp-vdir, liest durch die neue Schicht zurück und vergleicht mit der alten:
  das ganze Daten-Dict, `entries_in_range` über ±2 Jahre (und mehr),
  `week_view`/`month_view`, `open_alarms`, `imprint_for_prompt`,
  `naechster_termin`, `render_range_for_tool`, `routine_finden`. Dazu das
  **Feld-Inventar**: jedes Feld der alten Datei muss im neuen Bestand wieder
  auftauchen, und es wird gezählt, wohin es ging (Property, X-Property,
  Nebendaten, Archiv). Jede Abweichung = Abbruch mit Meldung.
- **ausführen**: nur nach bestandener Prüfung; schreibt `data/kalender/`
  und die Nebendaten (Ziel muss leer sein), setzt `kalender_speicher=ics`,
  benennt `ai_calendar.json` in `ai_calendar.json.vor-ics-<datum>` um (nie
  löschen).
- **zurück**: der Rückweg — schreibt aus dem vdir wieder eine
  `ai_calendar.json`, setzt `kalender_speicher=json`, nimmt die
  Rückfall-Sperre weg.

## Was Sasha tun muss (Umstieg, in Worten)

1. Auf **einem** Knoten arbeiten (PC). Vorher beide Knoten abgleichen und
   auf dem anderen nichts am Kalender ändern.
2. Das ZENTRALE-Backend auf diesem Knoten anhalten (es liest die Einstellung
   nur beim Start).
3. Das Migrations-Skript im Prüf-Modus laufen lassen und die Meldung lesen:
   Zahlen, „alles gleich", Feld-Inventar.
4. Ist alles gleich: dasselbe Skript im Ausführen-Modus. Danach liegen der
   vdir-Ordner und die Nebendaten in `data/`, die alte Datei ist umbenannt.
5. Backend wieder starten, Kalender in der TUI anschauen.
6. Abgleich zum anderen Knoten anstoßen; dort ebenfalls das Backend neu
   starten (die Einstellung liegt in `data/ai_config.json` und kommt mit).
7. Google (wenn gewollt): vdirsyncer-Vorlage nach `~/.config/vdirsyncer/`
   kopieren, Pfade und Google-Zugang (OAuth-Client aus der Google Cloud
   Console) eintragen, vdirsyncer die Kalender entdecken lassen, dann den
   Sync **über den Wrapper** `scripts/kalender_sync.py` laufen lassen (er
   nimmt die Sperre, räumt Geister weg und spiegelt vorher und nachher ins
   git). vdirsyncer nur auf **einem** Knoten laufen lassen; sein Status-Ordner
   liegt außerhalb von `data/`.
8. git-Remote (optional, später): auf der Weboberfläche ein **privates**
   Repo anlegen, im Spiegel-Repo als Remote eintragen und von Hand pushen.
   ZENTRALE pusht nie selbst.

## Offene Fragen

- Behält Google `X-ZENTRALE-*`? Erst mit echtem Konto prüfbar.
- Routinen „seit immer": Google zeigt sie ab dem Anker (erster Termin der
  alten Daten bzw. Tag des Anlegens). Soll ZENTRALE neue Routinen künftig erst
  ab heute rechnen? Dann reicht es, `X-ZENTRALE-OHNE-ANFANG` wegzulassen.
- Regeln, die vom Startdatum abhängen (`INTERVAL=2`, `COUNT`), rechnete das
  alte Modell vom jeweiligen Abfragebeginn aus — in Google ab dem Anker. In den
  echten Daten gibt es keine; die Prüfung fände sie.
- Abweichungen einzelner Routine-Termine, die am Handy verschoben werden
  (RECURRENCE-ID), zeigt ZENTRALE an (Feld `abweichungen`), kann sie aber
  nicht selbst anlegen.

## Historie

- **2026-10-06** — Plan, Bau der Schicht, Migration geprüft an einer Kopie
  der echten Daten; Umschalter bleibt auf `json`.
