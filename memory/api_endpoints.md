# REST API Endpoints

Alle Endpoints werden von `ui/app.py` bedient. Streaming-Endpoints
nutzen Server-Sent Events (SSE).

## Dashboard / State

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/`                   | GET     | Monolith-Dashboard (monolith.html) – die einzige UI |
| `/monolith`           | GET     | Alias auf `/` (Kiosk/Bookmark-Kompat), liefert dieselbe monolith.html |
| `/api/state`          | GET     | Aktueller State (Events, Sensoren, Vokabel, Logs) – wird vom Frontend jede Sekunde gepollt |

## Sensor-Webhook

| Endpoint                  | Methode | Beschreibung                          |
|---------------------------|---------|---------------------------------------|
| `/api/sensor/<name>`      | POST    | Externes Sensor-Signal entgegennehmen und in die Event-Queue legen. Erlaubte `<name>`: `button`, `light`, `motion`, `door` (Whitelist `_ALLOWED_SENSORS` in `ui/app.py`). Body wird aktuell ignoriert. |

Verwendet von `scripts/pi_sensor_bridge.py` (Pi → PC) und kann von
beliebigen LAN-Clients aufgerufen werden (Mikrocontroller, anderer Pi,
manueller curl-Test). Siehe `topologie.md`.

## Telemetrie

Zwei Maschinen: PC liest lokal (`/proc` + `/sys` + `nvidia-smi` via
`core/host_metrics.py` → `core/telemetry.pc_snapshot()`), der Pi POSTet
seine Werte rüber (FS read-only, kann nicht selbst anzeigen). Quelle ist
dependency-frei (kein psutil), voll offline.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/telemetry`      | GET     | PC + Pi kombiniert: `{pc:{cpu,gpu,vram,temp,ram}, pi:{cpu,temp,ram,disk,age_s}}`. Jede Metrik ist ein `{v, …}`-Objekt; `v=null` = Quelle fehlt. `pi={}` solange der Pi nie gesendet hat, `age_s` = Alter des letzten Pushes (Frontend zeigt Pi ab >90s als stale). Dashboard pollt ~2s. |
| `/api/telemetry/pi`   | POST    | Telemetrie-Push vom Pi. JSON-Body mit Top-Level-Keys aus `{cpu,temp,ram,disk}` (Whitelist `_ALLOWED_PI_METRICS`), gleiche Shape wie ein Meter-Block. Landet via `state.set_pi_telemetry()`. Sender: `scripts/pi_sensor_bridge.py`. |

## Data Collection

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/categories`     | GET     | Verfügbare Kategorien                 |
| `/api/data/<id>`      | GET     | Geloggte Einträge einer Kategorie     |
| `/api/log`            | POST    | Neuen Eintrag speichern               |
| `/api/debug`          | POST    | Debug-Log-Zeile ins Terminal (temporäre Dev-Hilfe) |

## Listen (Todo-/Sammel-Listen)

Zur Laufzeit angelegte, abhakbare Listen — Pendant zum Lifestyle-Graph-Werkzeug
(`/api/graphs`), aber für „random stuff" statt Zeitreihen. Definition UND
Einträge liegen inline (`core/lists.py`); kein `/api/log`-Sharing. Front:
TUI-Mitte Taste `l` (`dashboard.md` → Terminal-Kassette).

**Zwei-Dateien-Speicher (isoliert):** Sashas private Listen liegen in
`data/lists.json`, der **`zentrale`-Feature-Tracker** (Liste `l_zentrale`, von
Claude gepflegt) in `data/features.json`. `core/lists._load()` liest **beide
gemerged** (API/TUI/Box sehen alles), `_save()` schreibt jede Liste zurück in
ihre Datei und fasst nur die wirklich geänderte an — Feature-Pflege berührt
`lists.json` nicht und umgekehrt. Beide sind gitignored (`data/*.json`). Details
zur Konvention: `CLAUDE.md` → „Feature-Tracking".

**Einträge sind Mischtypen (verschachtelt):** jeder Eintrag kann selbst ein
optionales `items`-Array tragen — also Unterpunkt ODER eingeordnete Unterliste
ODER beides, beliebig tief. `next_item` ist die id-Quelle und über den GANZEN
Baum eindeutig. Alt-Dateien ohne `items`-Feld an Einträgen bleiben gültig (= Blatt).

**Abhaken:** Nur **Blätter** (Einträge ohne Kinder) sind direkt abhakbar — ihr
`done`-Feld wird per `toggle` gesetzt. Ein **Ordner** (Eintrag MIT Kindern) ist
NICHT direkt abhakbar; sein effektiver Status ist **abgeleitet** (`is_done` in
`core/lists.py`): erledigt genau dann, wenn alle Kinder (rekursiv) erledigt sind.
`toggle` auf einen Ordner → **400**. Fortschritt `(erledigt/gesamt)` zählt die
**Blätter** (Ordner selbst zählen nicht mit).

**Projekt-Flag (PROJECTS-Box):** Sowohl eine **Liste** als auch ein **Eintrag**
(Unterordner) kann als *Projekt* markiert werden (`project: bool`). Geflaggte
Knoten erscheinen in **allen** Fronten in einer eigenen `projects`-Box (rechts,
zwischen `lifestyle` und `outbound`). `/api/projects` liefert dafür einen
**verschachtelten Baum** (`projects_tree` in `core/lists.py`): geflaggte
Top-Level-Liste = Wurzel, ihre rekursiv geflaggten Unter-Einträge hängen als
`children` darunter. Nicht geflaggte Knoten werden nur durchschritten — ihre
geflaggten Nachfahren klettern hoch. Das gilt auch für eine **ganze nicht
geflaggte Liste**: deren geflaggte Einträge werden selbst zu Wurzeln (sonst
verstecken sich Projekte in einer ungeflaggten Liste und tauchen nie auf). Anzeige-Konvention: Knoten **ohne**
children → Titel + Erfüllungsleiste (erledigte/alle Blätter rekursiv,
`node_progress`); Knoten **mit** children → **gerahmter Kasten** (Titel im
Rahmen, children drin, KEINE eigene Leiste); rekursiv, bei Platzmangel bricht
die Front einfach ab. Reine Anzeige; markiert wird im **Listen-Werkzeug** (TUI
Taste `l` → `p` auf einer Liste in der Übersicht bzw. auf einem Eintrag in der
view-Ebene; geflaggte tragen ein `◆`).

| Endpoint                              | Methode | Beschreibung                          |
|---------------------------------------|---------|---------------------------------------|
| `/api/lists`                          | GET     | Alle Listen inkl. Einträge (`[{id,name,created,next_item,project,items:[{id,text,done,items?:[…]}]}]`). |
| `/api/lists`                          | POST    | Neue Liste. Body `{name}`. 400 bei leerem Namen. id = `l_<slug>` (kollisionsfrei). |
| `/api/projects`                       | GET     | Verschachtelter Projekt-Baum für die PROJECTS-Box: `[{id,name,done,total,children:[…]}]` (geflaggte Top-Level-Listen + rekursiv geflaggte Unter-Einträge). done/total = erledigte/alle Blätter rekursiv unter dem Knoten. |
| `/api/lists/<lid>`                    | DELETE  | Liste samt Einträgen löschen.         |
| `/api/lists/<lid>/project`            | POST    | Projekt-Flag einer LISTE setzen/löschen. Body `{project:bool}`. 404 unbek. Liefert die Liste. |
| `/api/lists/<lid>/items/<int:iid>/project` | POST | Projekt-Flag eines EINTRAGS (Unterordner, egal wie tief) setzen/löschen. Body `{project:bool}`. 404 unbek. Liefert den Eintrag. |
| `/api/lists/<lid>/rename`             | POST    | Listen-Namen ändern. Body `{name}`. id bleibt stabil. 400 leer, 404 unbek. |
| `/api/lists/<lid>/items`              | POST    | Eintrag anhängen. Body `{text}`, optional `{parent:<iid>}` → Unterpunkt von `<iid>`. 400 leer, 404 unbek. Liste/Eltern. Liefert `{id,text,done}`. |
| `/api/lists/<lid>/nest`               | POST    | Ganze Liste in eine andere einordnen (Quelle → Eintrag, verschwindet aus Top-Level). Body `{into:<ziel-lid>}`, optional `{parent:<iid>}`. ids des Teilbaums werden im Ziel neu vergeben. 400 in-sich-selbst, 404 unbek. Liefert den neuen Eintrag. |
| `/api/lists/<lid>/items/<int:iid>/toggle` | POST | Erledigt-Status umschalten (egal wie tief). 404 unbekannt. |
| `/api/lists/<lid>/items/<int:iid>/rename` | POST | Eintrags-Text ändern (egal wie tief). Body `{text}`. 400 leer, 404 unbek. |
| `/api/lists/<lid>/items/<int:iid>/move`   | POST | Eintrag (samt Teilbaum) RAUS in eine andere/dieselbe Liste. Body `{into:<ziel-lid>}`, optional `{parent:<iid>}`. ids im Ziel neu. 400 Zyklus (eigener Teilbaum), 404 unbek. Liefert den Eintrag. |
| `/api/lists/<lid>/items/<int:iid>`    | DELETE  | Eintrag (samt Teilbaum) löschen, egal wie tief. 404 unbek. Liste/Eintrag. |

## Chat

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/chat`           | POST    | Chat-Nachricht senden (SSE-Stream). JSON-Body: `{message: str, via_mic?: bool}`. `via_mic=true` triggert `_MIC_INPUT_HINT` im System-Prompt (Whisper-Fehler-Awareness, siehe `ki_system.md`). SSE-Events: `token` (Antworttext), `reflect` (Denk-/Reflexions-Strom bei adaptivem Thinking → HUD-Kern, NICHT gespeichert/gesprochen), `ascii` (Inline-Bild), `permission` (Knopf-Rückfrage), `cinema` (News-Sendung), `done`. |
| `/api/chat/history`   | GET     | Chat-History                          |
| `/api/chat/clear`     | POST    | Chat-History leeren                   |

## KI-Status & Erlaubnis

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/ai/status`         | GET     | Ollama-Verfügbarkeit + Modell-Name    |
| `/api/permission_answer` | POST    | Antwort auf eine `frage_knopf`-/Internet-Erlaubnis-Frage (JSON `{answer}`). Entsperrt den wartenden Chat-Stream. Siehe `ki_system.md` → Permission-Gate. |

> `/api/memory` + `/api/memory/<id>` (Legacy-LTM) sind entfallen – Memory
> läuft jetzt über den Konzept-Graphen (siehe `ki_system.md`).

## Fotos (ASCII-Bild-Filter)

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/photos`         | GET     | Liste der Bild-Dateinamen aus `data/photos/` (Quelle für den Canvas-Bild→ASCII-Filter im Monolith). |
| `/api/photos/<name>`  | GET     | Einzelnes Bild (same-origin, damit der Canvas `getImageData` darf). Path-Traversal-geschützt. |

## Maps (Karten-System)

Front-agnostisch: jede Front schickt ihren Viewport (`cx,cy,zoom`) + ihr
Zielraster (`cols,rows,aspect`); die Engine in `core/map/` projiziert fertig.
**Nicht** KI-gegatet (Karte gibt es in allen Kassetten). Architektur +
drei Achsen: `maps_system.md`; Quellen/Lizenzen: `maps_quellen.md`.

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/map/base`          | GET     | Basiskarte (Küsten, Achse-1-LOD nach Zoom) als projizierte Linien fürs Zellraster. Query: `cx,cy,zoom,cols,rows,aspect`. |
| `/api/map/braille`       | GET     | Basiskarte als gefülltes Land in Braille (2×4 Subpixel/Zelle), fertige Zeilen. Query: `cx,cy,zoom,cols,rows`. |
| `/api/map/layers`        | GET     | Registry der thematischen Overlays (Achse 2): Layer + Sub-Layer + Quelle (Provenienz) + ob zeitfähig (Achse 3). |
| `/api/map/layer/<id>`    | GET     | Features eines Overlays, projiziert. Query wie `/base` + `sub` (Sub-Layer, z.B. `chokepoints`) + `at` (Zeitpunkt, Achse 3). Antwort trägt `source/vintage/retrieved_at`. 404 bei unbekanntem Layer. |

Live: `trade` (IMF PortWatch) — ohne `sub` das **Komposit** (Routenlinien +
Chokepoint-Punkte); `?sub=routes` (Schifffahrtslinien, statisch) bzw.
`?sub=chokepoints` (Engstellen + täglicher Verkehr) einzeln. Lizenziert →
lokal gecacht, nicht committet; Refresh per `python -m map.layers.portwatch`.

## Kalender (Anzeige)

Front-agnostisch wie die Maps: die geteilte Quelle für die Kalender-Mitte
**aller** Kassetten (TUI-Modus `c`, Browser-Tab „Kalender" — auch in der
KI-freien laptop-Kassette, gleiches Template).
**Nicht** KI-gegatet — reine Anzeige, kein KI-Tool-Pfad (die KI greift den
Kalender weiter über `read_calendar`, nicht über diesen Endpoint), läuft also
auch in der ki-freien Kassette. Datums-Arithmetik macht Python
(`core/kalender.py`), die Front klassifiziert nur `view` + blättert über `ref`.

| Endpoint                | Methode | Beschreibung                          |
|-------------------------|---------|---------------------------------------|
| `/api/calendar`         | GET     | Woche (Mo-So) oder Monatsgitter, nach Tag gruppiert. Query: `view=week`(Default)`|month`, `ref=YYYY-MM-DD` (Default heute). |
| `/api/calendar/entry`   | POST    | Einmal-Termin direkt anlegen. Body `{day=YYYY-MM-DD, label, time?, ende?, ort?, layer?}` (Default-Layer `termine`). Antwort `{ok, conflicts:[…]}` — Konflikt-Zeilen (Reise/Kollision/Knapp) nur als HINWEIS, kein Block. 400 bei fehlendem label/ungültigem day. |
| `/api/calendar/entry`   | DELETE  | Einmal-Termin(e) löschen. Body `{day, label, layer?}`, Label-Match wie das KI-Tool (case-insensitiv, exakt/Teilstring). Antwort `{deleted:n}`. Wirkt NICHT auf Routinen. 400 ohne day/label. |
| `/api/calendar/entry`   | PUT     | Bestehenden Einmal-Termin ÄNDERN (= delete alt + add neu). Body `{day, label, layer?, new:{day, label, time?, ende?, ort?}}`. Antwort `{ok, conflicts:[…]}`. 400 bei fehlendem alt-day/label oder ungültigem new.day. |
| `/api/calendar/routine/skip` | POST | EINZELNES Routine-Vorkommen deaktivieren/aktivieren (reversibel, pro Tag). Body `{layer, label, day, off}` (`off=true` deaktiviert). Speichert die Datumsliste `aus` an der Routine; das Vorkommen bleibt sichtbar, aber als `deaktiviert` markiert. Antwort `{changed:bool}`. 400 ohne label/day. |
| `/api/calendar/routine` | POST   | Neue WÖCHENTLICHE Routine anlegen (ohne RRULE-Tipperei). Body `{label, byday, time?, ende?, ort?, layer?}`; `byday` = ein/mehrere Wochentage `MO..SU` (Liste ODER kommagetrennt) → `FREQ=WEEKLY;BYDAY=…`. Antwort `{ok:true}`. 400 ohne label/byday. Krummere Wiederholungen bleiben dem KI-Tool vorbehalten. |
| `/api/calendar/routine` | DELETE | GANZE Routine löschen (alle Vorkommen weg) — Gegenstück zum einzelnen Deaktivieren. Body `{layer, label}`, Label-Match wie sonst. Antwort `{deleted:n}`. 400 ohne label. |

GET-Antwort: `{view, ref, today, label, start, end, days:{iso:[entries]}, alarms}`;
bei `view=month` zusätzlich `month, first, last` (echte Monatsgrenzen, damit die
Front Rand-Tage aus Vor-/Folgemonat ausgraut). `days` nutzt `entries_in_range`
(Routinen expandiert, `ausfall`-Feld bei Ferien, `deaktiviert`-Feld bei einzeln
abgeschalteten Routine-Vorkommen). Müll-`ref` → 400, nie 500.

**Schreiben ist DIREKTE Nutzeraktion, NICHT KI-gegatet** (wie `/api/log` beim
Graph-Werkzeug) — das KI-Permission-Gate bleibt davon unberührt. Einmal-Termine
werden direkt angelegt/geändert/gelöscht; Routine-*Regeln* (rrule) entstehen
weiter über die KI, aber **einzelne Routine-Vorkommen** lassen sich pro Tag
ab-/anschalten. Front-Bedienung: TUI `a`=neu · `e`=bearbeiten (Einmal→Formular,
Routine→De-/Aktivieren) · `d`=löschen/aus; Browser „＋ Termin"-Form + pro Termin
✎ (bearbeiten) / ✕ (löschen) bzw. ⊘/↺ (Routine de-/aktivieren).

## Voice (sprachneutral, Core)

Die Voice-Pipeline gehört zur Core-AI, nicht zum Tutor. Sprache wird
per Parameter mitgegeben.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/speak`          | POST    | Text → WAV. JSON-Body: `{text, lang?, speed?, speaker?}`. `lang` Default `de`. Andere Sprachen ohne Modell → 503. |
| `/api/transcribe`     | POST    | Audio → Text. Multipart: `audio` + `lang?`. `lang` Default `de`.  |

Details zu Modellen + Sprachen: `audio_system.md`.

## Mail-Triage

| Endpoint                    | Methode | Beschreibung                          |
|-----------------------------|---------|---------------------------------------|
| `/api/mail`                 | GET     | Mail-Panel Ebene 1: `{categories, recent, live_counts, counts_age_s, counts_refreshing, can_poll, polling}`. Read-only, **key-frei** (`mail_state.json`). `categories[].count` = lokaler Schnappschuss, `live_counts` = echte Ordnergröße aus dem Cache. |
| `/api/mail/refresh-counts`  | POST    | Frischt den Live-Ordnerzähl-Cache im Hintergrund auf (IMAP `STATUS`-Sweep). `409` ohne Passphrase, Parallel-Lock. |
| `/api/mail/folder?cat=NAME` | GET     | Mail-Panel Ebene 2: die Mails einer Kategorie. Mit Key + eigenem Ordner LIVE (`source:"live"`), sonst lokaler Schnappschuss (`source:"snapshot"`). |
| `/api/mail/body?cat=&uid=&account=` | GET | Voller Text + Header EINER Mail (Lesen-Modus). LIVE; `409` ohne Key. MIME→Klartext. |
| `/api/mail/assign`          | POST    | Ordnet den **Absender** der Kategorie zu (Keymap) UND verschiebt mit Key **alle** seine vorhandenen Mails dorthin (`SEARCH FROM` über INBOX + move-Ordner). Body `{sender, category}` → `{assigned, category, moved, live}`. |
| `/api/mail/delete`          | POST    | Eine Mail in den Papierkorb (umkehrbar). LIVE; `409` ohne Key. Body `{cat, uid, account?}`. |
| `/api/mail/reply`           | POST    | Antwort senden via SMTP XOAUTH2 (Outlook). LIVE; `409` ohne Key. Body `{cat, uid, text, account?}`. Braucht `SMTP.Send`-Scope (Neu-Login). |
| `/api/mail/poll`            | POST    | Stößt einen **Live**-Poll im Hintergrund-Thread an. `409`, wenn keine Passphrase (Env/Keyring). Parallel-Polls per Lock verhindert. |

Details: `mail_system.md` (Panel/Drill-down/Hybrid, Passphrase-Quellen, Keyring-CLI).

## Tutor (entfernt)

Alle `/api/tutor/*`-Endpoints (status/start/respond/transcribe/speak/stop)
sind entfallen – der Mandarin-Tutor ist pausiert (siehe `tutor_system.md`).
Voice läuft über die sprachneutralen Core-Endpoints `/api/speak` +
`/api/transcribe` mit `lang`-Parameter.
