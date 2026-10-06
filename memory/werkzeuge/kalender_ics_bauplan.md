# Kalender auf iCalendar (.ics) — Bauplan und Umstieg

**Stand 2026-10-06:** Gebaut und getestet, aber **nicht live**. Der Kalender
kann seine Daten wahlweise in der alten JSON (`data/ai_calendar.json`) oder
als iCalendar-Ordner (`data/kalender/`, eine `.ics` pro Termin, vdir-Format)
halten. Umgeschaltet wird mit der Einstellung `kalender_speicher`
(`json` | `ics`, Default `json`). Sasha legt um — mit
`scripts/kalender_migrieren.py`, Schritte unten unter „Was Sasha tun muss".
Die öffentlichen Funktionen von `core/kalender.py` sind unverändert; nur die
Speicherschicht darunter ist getauscht. Die Prüfung an einer Kopie der
echten Daten (06.10.2026) war fehlerfrei. Google-Sync per vdirsyncer ist
vorbereitet (`deploy/vdirsyncer.config.example`, `scripts/kalender_sync.py`),
aber nicht eingerichtet.

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
| Ebene (`termine`, `routinen`, eigene) | ein Kalender = ein Unterordner im vdir (`data/kalender/<ebene>/`, mit `displayname`/`color` für vdirsyncer) |
| Einmal-Termin, `time`, `ende`, `ort` | VEVENT mit DTSTART/DTEND (TZID=Europe/Berlin), LOCATION |
| ganztags (ohne `time`) | DTSTART;VALUE=DATE |
| Spanne über Tage (`bis`) | **ein** VEVENT, ganztags von DTSTART bis DTEND |
| Spanne mit Beginn am ersten / Ende am letzten Tag | **ein** VEVENT mit Uhrzeiten („Fr 18:00 bis So 14:00") |
| Spanne mit eigener Zeit pro Tag (`times`) | tägliche RRULE (COUNT) + Abweichungs-VEVENTs mit RECURRENCE-ID **in derselben Datei** (gleiche UID) — sonst bricht vdirsyncer; nicht in Einzeltermine zerlegt, weil Sasha die Spanne zusammenhängend sehen will |
| Routine (`rrule`) | RRULE; `ende` → DTEND |
| `aus` (einzeln deaktiviert) | EXDATE + `X-ZENTRALE-AUS` |
| `pausen` (Ferien) | EXDATEs an jeder Routine gleichen Namens + `X-ZENTRALE-PAUSE` (die Notiz mit Grund) |
| `absage_noetig` | `X-ZENTRALE-ABSAGE-NOETIG:TRUE` |
| Ebene `erlebt` | fällt weg — Inhalt wandert **unverändert** ins Archiv der Nebendaten |
| `reisezeiten`, `puffer_min`, Ebenen-Titel/Farbe/Sichtbarkeit, `version` | Nebendaten `data/kalender_neben.json` |

Was dazu nicht passt, geht nie verloren — das Prinzip: ein Feld wird nur
dann auf eine Property abgebildet, wenn es sich **exakt** zurücklesen lässt.

- Unbekannte Zusatzfelder und alles, was sich nicht ausdrücken lässt (Ende
  ohne Beginn, Ende vor Beginn, leere Titel) → `X-ZENTRALE-EXTRAS` (JSON,
  base64-verpackt, weil Server Kommas und Semikolons in unbekannten
  Properties verschieden behandeln). Extras füllen beim Lesen nur **Lücken** —
  was am Handy geändert wurde, gewinnt.
- Uhrzeiten, wie sie in Sashas echten Daten stehen (`"10"`, `"9:30"`, `"8"`),
  gehen als 10:00 / 09:30 / 08:00 nach DTSTART — Google zeigt die richtige
  Stunde. Der Originaltext steht in `X-ZENTRALE-ZEIT-ROH` und gilt nur, solange
  die Zeit unverändert ist. Dasselbe für RRULEs, die icalendar umordnet
  (`X-ZENTRALE-RRULE-ROH`).
- Was gar nicht als Ereignis geht (kaputtes Datum als Schlüssel, Spanne mit
  `bis` vor `von`, leere Tage) → `nicht_abbildbar` in den Nebendaten, liest
  sich aber genauso zurück.
- Die Reihenfolge (wichtig für gleichzeitige Termine und damit für den
  Wortlaut der Alarme) trägt `X-ZENTRALE-POS`.
- Jede Schreibfunktion liest ihr Ergebnis sofort zurück; weicht es ab, landet
  das Stück roh in den Nebendaten statt verfälscht im vdir.

Routinen hatten im alten Modell **keinen Anfang** (sie galten rückwirkend
für immer). Damit sich daran nichts ändert, bekommen sie in .ics einen
technischen DTSTART (erster echter Termin ab dem Anker: bei der Migration der
früheste Tag der alten Daten, sonst der Tag des Anlegens) plus
`X-ZENTRALE-OHNE-ANFANG:TRUE`; ZENTRALE rechnet sie weiter wie vorher, Google
zeigt sie ab dem Anker. Routinen, die von außen kommen, haben einen echten
Anfang (`seit`) und werden ab dort gerechnet. Neu im Daten-Dict (nur von
außen gelesen): `seit`, `enden` (Ende pro Tag einer Spanne) und
`abweichungen` (am Handy verschobene/abgesagte Einzeltermine einer Routine,
RECURRENCE-ID).

Ob Google die `X-ZENTRALE-*`-Properties behält, ist **ungetestet**. Fällt
eine weg, verliert ZENTRALE Bedeutung, nicht den Termin (getestet): ein
EXDATE ohne `X-ZENTRALE-AUS` wird als „deaktiviert" gelesen, ein Termin ohne
`X-ZENTRALE-POS` kommt hinten an. Gegen den Rest helfen Verlauf, Snapshots
und git-Spiegel (unten).

## Module (Schicht 2, siehe `memory/system/bauplan_kern.md`)

| Modul | Aufgabe |
|---|---|
| `kalender` | öffentliche Fassade, Rechenlogik (Kollisionen, Alarme, Imprint) — Namen und Signaturen unverändert |
| `kalender_zeitraum` | relative Zeiträume („diese_woche") in Daten (aus `kalender.py` gelöst) |
| `kalender_regel` | RRULE → Tage, die eine Stelle für Fassade und Abbildung |
| `kalender_speicher` | wählt den Speicher, alle Pfade, Einstellungen |
| `kalender_json` | der alte Speicher, jetzt atomar, mit Rückfall-Sperre |
| `kalender_ics_abbildung` | ein Termin/eine Routine ↔ VEVENT-Komponenten, rein rechnend |
| `kalender_ics` | der vdir-Speicher: lesen (mit Cache), nur Unterschiede schreiben, Nebendaten |
| `kalender_sicherung` | atomares Schreiben, Datei-Sperre, Verlauf, Grabsteine, Snapshots, Massenlösch-Sperre |
| `kalender_spiegel` | git-Spiegel außerhalb von `data/` |
| `kalender_migration` | Prüfen, Ausführen, Rückweg, Feld-Inventar |

Die Fassade arbeitet weiter auf dem gewohnten Daten-Dict (`_load_raw` →
ändern → `_save_raw`). Der ics-Speicher übersetzt beim Laden die Dateien in
genau dieses Dict (jeder Eintrag trägt intern `_ics` mit UID und Position,
die Fassade gibt das nie nach außen) und schreibt beim Speichern **nur die
Dateien, die sich geändert haben**. Dadurch blieb die Rechenlogik unberührt,
und ein Schreiben fasst nie den ganzen Kalender an. Beim Zurückschreiben einer
vorhandenen Datei bleibt alles erhalten, was ZENTRALE nicht verwaltet
(DESCRIPTION, Erinnerungen, Teilnehmer, Google-Felder, andere UIDs).

Einstellungen (alle über `ai_config.setting`, also auch als Env
`ZENTRALE_<NAME>`): `kalender_speicher` (`json`/`ics`),
`kalender_loeschsperre` (Default 5), `kalender_git_spiegel` (Pfad oder
`aus`; Default `~/.local/share/zentrale/kalender-git`).

## Absicherung gegen Datenverlust

Die Falle: `data/` wird zwischen PC und Laptop per rsync Datei für Datei
abgeglichen, **nur hinzufügend, neueste Datei gewinnt**
([../system/topologie.md](../system/topologie.md)). Ein git-Repo IN `data/`
würde dabei zerstört (refs und index würden dateiweise überschrieben).
Umgekehrt ist das .ics-Format hier ein Gewinn: der Sync gleicht pro Termin
ab — ändert der PC die Geige und der Laptop den Zahnarzt, überleben beide
(mit der einen JSON gewann eine Datei, die andere Änderung war weg).

1. **Atomar schreiben:** temporäre Datei (Name endet nicht auf `.ics`),
   fsync, `os.replace`. Ein Absturz hinterlässt nie eine halbe Datei. Gilt
   jetzt auch für die alte JSON.
2. **Sperre:** ein Thread-Lock im Prozess plus eine Datei-Sperre
   (`data/kalender/.zentrale.lock`) zwischen Prozessen. Nach 15 s ohne
   Sperre: Fehler statt Hängen.
3. **Verlauf** `data/kalender_verlauf/<Monat>/`: vor jeder Änderung und jeder
   Löschung landet die alte Fassung dort, Name aus Zeitstempel + Knoten +
   Ebene + UID + Aktion. Eindeutige Namen übersteht der Sync. Zurückholen:
   `IcsSpeicher.wiederherstellen(<verlaufsdatei>)` — die dann aktuelle
   Fassung wandert vorher selbst in den Verlauf.
4. **Grabsteine** `data/kalender_verlauf/grabsteine/<uid>.json`: Weil der Sync
   nichts löscht, käme eine auf dem Laptop gelöschte Datei vom PC zurück.
   Eine `.ics`, die nicht neuer ist als ihr Grabstein (LAST-MODIFIED), gilt
   als Geist: nicht angezeigt, beim nächsten Schreiben (oder vor vdirsyncer)
   in den Verlauf geräumt. Ist sie neuer, gilt sie — neueste gewinnt.
5. **Massenlösch-Sperre:** löscht eine einzige Operation mehr als
   `kalender_loeschsperre` Termine, wird **gar nichts** geschrieben
   (`KalenderGesperrt`). Die KI sieht das als Werkzeug-Fehler; eine Route
   antwortet mit 500 (die Routen sind unverändert). Wiederherstellen,
   Migration und Rückweg dürfen ausdrücklich mehr.
6. **Tägliche Snapshots** `data/kalender_snapshots/kalender_<datum>_<knoten>.tar.gz`
   vor der ersten Änderung des Tages; behalten werden 30 Tage plus jeder
   Monatserste für zwei Jahre (für alle Knoten gleich, sonst hielte der
   additive Sync alte Snapshots ewig). Weil sie in `data/` liegen, wandern sie
   auf den anderen Knoten.
7. **git-Spiegel** (Sasha, Nachtrag 2026-10-06: *„daten können gern in ein
   extra git repo"*): nach jedem Schreiben spiegelt ZENTRALE vdir +
   Nebendaten nach `~/.local/share/zentrale/kalender-git` (außerhalb von
   `data/`, ein Repo pro Knoten) und committet — im Hintergrund; ein Fehler
   dort verhindert nie das Schreiben des Termins (getestet). Gepusht wird
   nichts. Neben dem Verlaufsordner sinnvoll, weil er auch Änderungen
   festhält, die vdirsyncer von außen hereinbringt (der Wrapper committet
   vorher und nachher), und weil er sich als zusätzliche Kopie an ein privates
   Remote hängen lässt.
8. **Rückfall-Sperre:** Nach der Migration steht in den Nebendaten
   `migriert_am`. Ein Knoten, der noch auf `json` steht, darf dann nicht mehr
   in die alte JSON schreiben (er liefe sonst still auseinander) — Lesen
   geht, Schreiben wird verweigert.
9. **vdirsyncer** bricht ab, wenn eine Seite plötzlich ganz leer ist
   (lokal geprüft mit vdirsyncer 0.21.0). Diese Sicherung bleibt an; den
   Zwangs-Löschschalter nie ohne Nachsehen benutzen.

Kalenderdaten gehen nicht ins Code-Repo: `.gitignore` deckt `data/kalender/`,
Verlauf, Snapshots, `data/kalender_*.json` und die umbenannte Alt-Datei ab.
Testläufe fassen sie nie an (`tests/conftest.py` biegt jeden Kalender in ein
Wegwerf-Verzeichnis, der git-Spiegel ist in Tests aus).

## Migration

`scripts/kalender_migrieren.py` hat drei Modi (Hilfe im Skript selbst):

- **prüfen** (Standard, ändert nichts): schreibt die alte JSON in einen
  Wegwerf-Ordner, liest durch die neue Schicht zurück und vergleicht: das
  ganze Daten-Dict samt Reihenfolge der Ebenen und Tage, dann ~900 Aufrufe der
  öffentlichen Lesefunktionen über beide Speicher (`entries_in_range` über
  ±2 Jahre, die ganze Datenspanne und je Ebene; jede Woche und jeder Monat;
  `render_range_for_tool` je Monat und je Titel; `routine_finden`;
  `open_alarms` mit 0/30/90/400 Tagen; Imprint 0–7 Tage; `naechster_termin`
  zu sieben Uhrzeiten an 38 Tagen; `conflicts_for_proposed` an 181 Tagen).
  Dazu das **Feld-Inventar**: jedes Blatt der alten Datei muss wieder
  auftauchen, und es wird gezählt, wohin es ging. Jede Abweichung = kein
  Umzug. Dass die Prüfung Verluste wirklich findet, ist getestet (absichtlich
  verlorener Ort, falsche Uhrzeit, fehlende Reihenfolge).
- **ausführen**: prüft erst; Ziel muss leer sein; schreibt `data/kalender/`
  und die Nebendaten, liest sie zurück und vergleicht noch einmal, setzt den
  Rückfall-Marker, stellt `kalender_speicher=ics` (in `data/ai_config.json`)
  und benennt `ai_calendar.json` in `ai_calendar.json.vor-ics-<datum>` um
  (nie löschen).
- **zurück**: schreibt aus dem vdir wieder eine `ai_calendar.json` (mit
  `erlebt` an seinem alten Platz), nimmt die Rückfall-Sperre weg, stellt auf
  `json`. Der vdir-Ordner bleibt liegen.

**Ergebnis an einer Kopie der echten Daten (2026-10-06):** 3 Ebenen,
38 Einmal-Termine, 4 Spannen (eine mit Uhrzeit pro Tag: Basel), 6 Routinen,
2 Pausen, 27 Einträge in `erlebt` → 48 `.ics`-Dateien, nichts roh,
893 Vergleichs-Aufrufe, **alles gleich**; `erlebt` exakt im Archiv.
Auffällig: sechs Termine haben Uhrzeiten ohne Minuten oder führende Null
(`"10"`, `"18"`, `"8"`, `"2"`, `"9:30"`) — ZENTRALE behandelt sie wie bisher
(keine Kollisionsprüfung, kein Countdown), Google zeigt sie als volle Stunde.
`"2"` wird dort zu 02:00.

## Was Sasha tun muss (Umstieg, in Worten)

1. Auf **einem** Knoten arbeiten (PC). Vorher beide Knoten abgleichen und auf
   dem anderen bis zum Ende nichts am Kalender ändern.
2. Das ZENTRALE-Backend auf diesem Knoten anhalten — es liest die Einstellung
   nur beim Start, und während des Umzugs soll niemand schreiben.
3. Das Migrations-Skript mit dem venv-Python ohne Zusatz laufen lassen (das
   ist der Prüf-Modus) und die Meldung lesen: Zahlen, „alles gleich",
   Feld-Inventar.
4. Ist alles gleich: dasselbe Skript im Ausführen-Modus. Danach liegen der
   vdir-Ordner und die Nebendaten in `data/`, die alte Datei ist umbenannt,
   die Einstellung steht auf `ics`.
5. Backend wieder starten, Kalender in der TUI anschauen.
6. Abgleich zum anderen Knoten anstoßen; dort ebenfalls das Backend neu
   starten (die Einstellung liegt in `data/ai_config.json` und kommt mit).
   Bis dahin verweigert der andere Knoten Kalender-Schreibzugriffe — das ist
   die Rückfall-Sperre, kein Fehler.
7. Google (wenn gewollt): in der Google-Weboberfläche zwei Kalender anlegen
   (Termine, Routinen); in der Google Cloud Console einen OAuth-Client
   „Desktop-App" für die Calendar API; die Vorlage
   `deploy/vdirsyncer.config.example` in den vdirsyncer-Konfigurationsordner
   kopieren und die Platzhalter füllen; vdirsyncer die Kalender entdecken
   lassen (beim ersten Mal öffnet sich der Browser für die Anmeldung); danach
   immer über `scripts/kalender_sync.py` synchronisieren, nicht vdirsyncer
   direkt. vdirsyncer nur auf dem PC; sein Status-Ordner liegt außerhalb von
   `data/`. Einen regelmäßigen Lauf (Timer) gibt es noch nicht.
8. git-Remote (optional): auf der GitHub-Weboberfläche ein **privates**,
   leeres Repo anlegen; im Spiegel-Repo (`~/.local/share/zentrale/kalender-git`)
   dieses Repo als Remote eintragen, mit dem vorhandenen SSH-Zugang, und von
   Hand pushen, wann immer gewünscht. ZENTRALE pusht nie selbst.

## Offene Fragen

- Behält Google `X-ZENTRALE-*`? Erst mit echtem Konto prüfbar.
- Routinen „seit immer": soll ZENTRALE neue Routinen künftig erst ab heute
  rechnen? Dann reicht es, `X-ZENTRALE-OHNE-ANFANG` beim Anlegen wegzulassen.
- Regeln, die vom Startdatum abhängen (`INTERVAL=2`, `COUNT`), rechnete das
  alte Modell vom jeweiligen Abfragebeginn aus — Google ab dem Anker. In den
  echten Daten gibt es keine; die Prüfung fände sie.
- Abweichungen einzelner Routine-Termine (am Handy verschoben) zeigt ZENTRALE
  an, kann sie aber nicht selbst anlegen; Titel-/Ortsänderungen an
  Abweichungen einer Spanne liest sie nicht.
- Fügt ein Server einem Termin ohne Ende eins hinzu (Google: oft +1 h), hat
  ZENTRALE danach ein Ende und prüft Kollisionen damit (dokumentiert, getestet).
- Die Ansicht (eigener Agent) kennt die neuen Felder `enden`/`abweichungen`
  noch nicht; über `entries_in_range` kommen sie als normales `ende`/`time`.

## Historie

- **2026-10-06** — Plan, Bau der Schicht, Migration geprüft an einer Kopie
  der echten Daten; Umschalter bleibt auf `json`.
