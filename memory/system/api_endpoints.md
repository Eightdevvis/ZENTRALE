# REST API Endpoints

**Stand 2026-10-06:** Alle Endpoints bedient die Routen-Schicht — `ui/app.py`
hängt die Bereiche aus `ui/routen/` ein, je ein Modul pro Bereich (siehe
`memory/system/bauplan_kern.md`, Abschnitt *Routen*) — reiner Adapter auf
`core/`), Streaming per SSE. Die Fronten (TUI, Zimmer, Browser) sind reine
HTTP-Clients. Direkte Nutzeraktionen (Kalender schreiben, Listen, Graphen,
Melodien, Karte, Notizen, Aussenposten-Paket) sind **nicht** KI-gegatet;
Chat hängt an Kill-Switches (`/api/ai/backends`). Die `/api/tutor/*`-Routen
gibt es hier seit 2026-10-09 nicht mehr — sie gehören dem Tutor-Server der
App `language-tutor` (`memory/tutor/INDEX.md`). Mail-Endpoints: Details in
`memory/werkzeuge/mail_system.md`, Notizen in `memory/werkzeuge/notizen_system.md`.
Diese Liste hat **keinen** Drift-Test; zuletzt gegen `ui/routen/`
abgeglichen 2026-09-18.

## Zugang (vor ALLEN Routen, `ui/routen/zugang.py`, seit 2026-10-08)

Jede Anfrage läuft zuerst durch die Tür (Details: `memory/betrieb/zugang.md`):

- **frei:** von diesem Rechner (`remote_addr` 127.0.0.1/::1 **und** Host
  `localhost`/`127.0.0.1`/`[::1]`); `/api/aussenposten/manifest` und `/paket`.
- **von draußen:** Kopf `Authorization: Bearer <zugangsschlüssel>` oder Keks
  `zentrale_zugang` (gesetzt über einen Link `?zugang=<marke>`, 10 min
  gültig → `303` auf dieselbe Adresse ohne Marke + Keks, 30 Tage).
- Stellung `zugang` = `aus | melden | an` (Vorgabe `melden`). Bei `an` ohne
  passenden Schlüssel: `401`, `WWW-Authenticate: Bearer`, JSON `{error}` (bzw.
  eine kleine Seite, wenn der Browser `text/html` will). Bei `melden`:
  durchgelassen, Log-Zeile `ZUGANG: …` (je Absender+Pfad höchstens alle 10 min).

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/zugang` | GET | Nur lokal (sonst 403, auch mit Schlüssel). `{modus, schluessel_da, ohne_schluessel: [{am, von, pfad, grund, durchgelassen}]}` — die letzten 50 seit dem Start. |
| `/api/zugang` | POST | Nur lokal. Body `{modus: aus\|melden\|an}` → live + dauerhaft in `ai_config.json`. 400 bei anderem Wert. |

## Dashboard / State

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/`                   | —       | Entfernt 2026-10-06: die Browser-Front ist archiviert (`memory/archive/browser_front.md`). |
| `/api/state`          | GET     | Aktueller State (Events, Sensoren, Logs, Alarme, Uptime) – wird vom Frontend jede Sekunde gepollt. (Ein Feld `vocab` gab es bis 2026-07-17 — toter Tutor-Tentakel, entfernt.) |

## Sensor-Webhook

| Endpoint                  | Methode | Beschreibung                          |
|---------------------------|---------|---------------------------------------|
| `/api/sensor/<name>`      | POST    | Externes Sensor-Signal entgegennehmen und in die Event-Queue legen. Erlaubte `<name>`: `button`, `light`, `motion`, `door` (Whitelist `_ALLOWED_SENSORS` in `ui/routen/zustand.py`). Body wird aktuell ignoriert. |

Verwendet von `scripts/pi_sensor_bridge.py` (Pi → PC) und kann von
beliebigen LAN-Clients aufgerufen werden (Mikrocontroller, anderer Pi,
manueller curl-Test). Siehe `memory/system/topologie.md`.

## Telemetrie

Zwei Maschinen: PC liest lokal (`/proc` + `/sys` + `nvidia-smi` via
`core/host_metrics.py` → `core/telemetry.pc_snapshot()`), der Pi POSTet
seine Werte rüber (FS read-only, kann nicht selbst anzeigen). Quelle ist
dependency-frei (kein psutil), voll offline.

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/telemetry`      | GET     | PC + Pi kombiniert: `{pc:{cpu,gpu,vram,temp,ram}, pi:{cpu,temp,ram,disk,age_s}}`. Jede Metrik ist ein `{v, …}`-Objekt; `v=null` = Quelle fehlt. `pi={}` solange der Pi nie gesendet hat, `age_s` = Alter des letzten Pushes (Frontend zeigt Pi ab >90s als stale). Dashboard pollt ~2s. |
| `/api/telemetry/pi`   | POST    | Telemetrie-Push vom Pi. JSON-Body mit Top-Level-Keys aus `{cpu,temp,ram,disk}` (Whitelist `_ALLOWED_PI_METRICS`), gleiche Shape wie ein Meter-Block. Landet via `state.set_pi_telemetry()`. Sender: `scripts/pi_sensor_bridge.py`. |

## Aussenposten-Versorgung

Ein Aussenposten (Knoten ohne Backend — der Pi an der Wand, spaeter einer pro
Raum) hat **kein git-Checkout**. Er holt sich hier sein zugeschnittenes Paket
ab: Manifest fragen, Version vergleichen, bei Abweichung das tar.gz ziehen.
Inhalt = `deploy/aussenposten.txt`, geschnuert von `core/aussenposten.py`,
eingebaut von `scripts/aussenposten_update.py` (stdlib-only, ohne venv).

Die `version` ist ein **Hash ueber den Paket-Inhalt**, keine hochgezaehlte
Nummer: aendert sich eine der enthaltenen Dateien, aendert sie sich; sonst
nicht. Es gibt nichts zu bumpen und nichts zu vergessen.

**Bewusst ohne KI-Gate:** ein Knoten muss sich auch dann
aktualisieren koennen, wenn die KI gedrosselt ist — sonst friert genau die
Maschine ein, die man gerade reparieren will.

| Endpoint                     | Methode | Beschreibung                     |
|------------------------------|---------|----------------------------------|
| `/api/aussenposten/manifest` | GET     | `{version, dateien, bytes, gebaut}`. Billig (nur hashen, nicht packen) — gedacht fuer einen Poll alle paar Minuten. |
| `/api/aussenposten/paket`    | GET     | Das Paket als `application/gzip`. Deterministisch gepackt (sortiert, `mtime=0`) → gleicher Inhalt, gleiche Bytes. Version zusaetzlich im Header `X-Paket-Version`, damit der Knoten nach dem Download abgleichen kann. |

## Data Collection

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/categories`     | GET     | Verfügbare Kategorien                 |
| `/api/data/<id>`      | GET     | Geloggte Einträge einer Kategorie     |
| `/api/log`            | POST    | Neuen Eintrag speichern               |

## Lifestyle-Graphen (`core/graphs.py`)

Zur Laufzeit angelegte Mess-Graphen (Definition in `data/graphs.json`; die
Werte teilen sich `/api/log` + `/api/data/<id>` mit der Data Collection).

| Endpoint                       | Methode | Beschreibung                          |
|--------------------------------|---------|---------------------------------------|
| `/api/graphs`                  | GET     | Alle Graph-Definitionen               |
| `/api/graphs`                  | POST    | Anlegen. Body `{name, type, unit, remind?, remind_at?}` |
| `/api/graphs/<id>`             | DELETE  | Definition + Messwerte-Datei löschen  |
| `/api/graphs/<id>/predict`     | POST    | Vorhersage-Flag (Lücken schätzen) `{predict}` |
| `/api/graphs/<id>/remind`      | POST    | Tages-Reminder setzen `{remind, at?}` (`at`=HH:MM, optional → unverändert) |
| `/api/graphs/reminders`        | GET     | Heute fällige Reminder `[{id,name,remind_at}]`: remind an, Uhrzeit erreicht, heute noch nicht geloggt. Quelle für das »bitte eintragen«-Modal (monolith/laptop) und den TUI-Nag. |

## Zyklus/PMS-Rechner (`core/cycle.py`)

Abgeleitet aus dem Lifestyle-Graphen namens **»periode«** — kein eigener
Speicher, keine eigene Datei, kein Kalender-Layer. Details siehe
`memory/werkzeuge/zyklus_pms.md`.

| Endpoint       | Methode | Beschreibung                                        |
|----------------|---------|-----------------------------------------------------|
| `/api/cycle`   | GET     | Vorhersage `{graph_id, graph_name, last_start, cycle_len, len_source, n_cycles, spread, next_start, pms_from, pms_to, days_to_next, overdue, phase, summary}` — oder `{}`, wenn es keinen »periode«-Graphen bzw. noch keine Werte gibt (kein 404: der Graph ist optional, die Fronten zeichnen dann nichts). Nicht KI-gegatet. |

Zusätzlich hängt `/api/calendar` (Woche **und** Monat) ein Feld
`cycle: {"<iso>": "pms"|"next"}` für die sichtbaren Tage an — damit die Fronten
nur noch einfärben und keine Datums-Mathematik machen.

## Melodien (Klavier-Werkzeug, `core/melodies.py`)

Auf der Computertastatur gespielte und aufgezeichnete Melodien
(`data/melodies.json`). Eine Melodie ist eine flache Noten-Liste, so wie
gespielt: `n` = MIDI-Note (21–108), `t` = Startzeit ab Aufnahmebeginn in ms,
`d` = Klingdauer in ms. **Kein Takt/Tempo** — nicht quantisiert, damit das
Gespielte nicht verfälscht wird. Nicht KI-gegatet (direkte Nutzeraktion), also
auch ohne lokale KI offen. Fronten: Canvas-Exhibit „Klavier" (Browser, geparkt,
Taste `k`) **und das TUI-Klavier** (dieselbe Taste) — beide lesen und schreiben
dieselbe Registry, im Browser Aufgenommenes spielt also auch das Terminal ab.

| Endpoint                  | Methode | Beschreibung                              |
|---------------------------|---------|-------------------------------------------|
| `/api/melodies`           | GET     | Alle Melodien inkl. Noten (`[{id,name,created,dur,notes:[{n,t,d}]}]`) |
| `/api/melodies`           | POST    | Aufnahme ablegen. Body `{name, notes}`. Noten werden geputzt (nur 21–108, Zeiten ≥0, sortiert, max 5000). 400 bei leerem Namen/leerer Melodie. id = `m_<slug>` (kollisionsfrei) |
| `/api/melodies/<id>/rename` | POST  | Umbenennen. Body `{name}`. id bleibt stabil. 400 leer, 404 unbekannt |
| `/api/melodies/<id>`      | DELETE  | Melodie löschen (still bei unbekannter id) |

## Listen (Todo-/Sammel-Listen)

Zur Laufzeit angelegte, abhakbare Listen — Pendant zum Lifestyle-Graph-Werkzeug
(`/api/graphs`), aber für „random stuff" statt Zeitreihen. Definition UND
Einträge liegen inline (`core/lists.py`); kein `/api/log`-Sharing. Front:
TUI-Mitte Taste `l` (`memory/system/dashboard.md` → TUI).

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
die Front einfach ab. Reine Anzeige; markiert wird im **Listen·Fokus-Werkzeug**
(TUI Taste `l`/`f` → `p` auf einer Liste/einem Eintrag in der Wurzel bzw. in der
view-Ebene; geflaggte tragen ein `◆`).

**Fokus (FOCUS-Box):** genau EIN Knoten (Liste ODER Eintrag) kann als alleiniger
*Fokus* markiert sein (`focus: bool`, `set_focus`, höchstens einer). Ist ein Fokus
gesetzt, zeigt die rechte **`focus`-Box** in allen Fronten NUR ihn (Quelle
`/api/projects/focused`); sonst ist die Box leer. Gesetzt wird per `f` im
Listen·Fokus-Werkzeug (Toggle).

| Endpoint                              | Methode | Beschreibung                          |
|---------------------------------------|---------|---------------------------------------|
| `/api/lists`                          | GET     | Alle Listen inkl. Einträge (`[{id,name,created,next_item,project,items:[{id,text,done,items?:[…]}]}]`). |
| `/api/lists`                          | POST    | Neue Liste. Body `{name}`. 400 bei leerem Namen. id = `l_<slug>` (kollisionsfrei). |
| `/api/projects`                       | GET     | Verschachtelter Projekt-Baum: `[{id,name,lid,done,total,children:[…]}]` (geflaggte Top-Level-Listen + rekursiv geflaggte Unter-Einträge). done/total = erledigte/alle Blätter rekursiv. Quelle der oberen Zone im Listen·Fokus-Werkzeug. |
| `/api/projects/focused`               | GET     | Der EINE fokussierte Knoten als Teilbaum `{name,done,total,focus,children:[…]}` — oder `null`. Quelle der rechten `focus`-Box in allen Fronten. |
| `/api/projects/focus`                 | GET/POST| GET → der Fokus `{lid,iid,name}` oder `null`. POST setzt (Toggle) mit `{lid,iid?}` bzw. löscht mit `{clear:true}`. |
| `/api/lists/<lid>`                    | DELETE  | Liste samt Einträgen löschen.         |
| `/api/lists/<lid>/project`            | POST    | Projekt-Flag einer LISTE setzen/löschen. Body `{project:bool}`. 404 unbek. Liefert die Liste. |
| `/api/lists/<lid>/items/<int:iid>/project` | POST | Projekt-Flag eines EINTRAGS (Unterordner, egal wie tief) setzen/löschen. Body `{project:bool}`. 404 unbek. Liefert den Eintrag. |
| `/api/lists/<lid>/rename`             | POST    | Listen-Namen ändern. Body `{name}`. id bleibt stabil. 400 leer, 404 unbek. |
| `/api/lists/<lid>/items`              | POST    | Eintrag anhängen. Body `{text}`, optional `{parent:<iid>}` → Unterpunkt von `<iid>`. 400 leer, 404 unbek. Liste/Eltern. Liefert `{id,text,done}`. |
| `/api/lists/<lid>/nest`               | POST    | Ganze Liste in eine andere einordnen (Quelle → Eintrag, verschwindet aus Top-Level). Body `{into:<ziel-lid>}`, optional `{parent:<iid>}`. ids des Teilbaums werden im Ziel neu vergeben. 400 in-sich-selbst, 404 unbek. Liefert den neuen Eintrag. |
| `/api/lists/<lid>/items/<int:iid>/toggle` | POST | Erledigt-Status umschalten (egal wie tief). 404 unbekannt. |
| `/api/lists/<lid>/items/<int:iid>/rename` | POST | Eintrags-Text ändern (egal wie tief). Body `{text}`. 400 leer, 404 unbek. |
| `/api/lists/<lid>/items/<int:iid>/move`   | POST | Eintrag (samt Teilbaum) RAUS in eine andere/dieselbe Liste. Body `{into:<ziel-lid>}`, optional `{parent:<iid>}`. ids im Ziel neu. **Ziel = »week«-Liste → KOPIE statt Move** (Quelle bleibt, Kopie trägt `link`, Abhaken bidirektional). 400 Zyklus, 404 unbek. |
| `/api/lists/<lid>/items/<int:iid>/reorder`| POST | Eintrag innerhalb SEINER Geschwister-Ebene verschieben. Body `{delta:-1\|+1}` (rauf/runter, am Rand No-op). 404 unbek. Liefert `{moved:bool}`. |
| `/api/lists/<lid>/items/<int:iid>`    | DELETE  | Eintrag (samt Teilbaum) löschen, egal wie tief. 404 unbek. Liste/Eintrag. |

## Notizen (`core/notes.py`)

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/notes`          | GET     | Übersicht aller Notizen (ohne Block-Inhalte), neueste zuerst. |
| `/api/notes`          | POST    | Neue (leere) Notiz. Body `{title?}`.  |
| `/api/notes/<nid>`    | GET     | Vollständige Notiz mit allen Blöcken. |
| `/api/notes/<nid>`    | PUT     | Inhalt ersetzen. Body `{title?, blocks?}`, nur Übergebenes wird angefasst. |
| `/api/notes/<nid>`    | DELETE  | Notiz löschen.                        |

Datenmodell + Bedienung: `memory/werkzeuge/notizen_system.md`.

## Chat

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|
| `/api/chat`           | POST    | Chat-Nachricht senden (SSE-Stream). JSON-Body: `{message: str, via_mic?: bool, gespraech?: id, ersetzt?: nachricht_id}` — seit 2026-10-07 in ein Gespräch (`core/gespraeche.py`, `memory/ki/gespraeche.md`): `gespraech` oder das aktive dieses Rechners (keins → neu angelegt); `ersetzt` = Bearbeiten (ab dieser eigenen Nachricht verwerfen, dann normal; unbekannt → 404, KI-Nachricht → 400). Unbekanntes Gespräch → 404. `via_mic=true` triggert `_MIC_INPUT_HINT` im System-Prompt (Whisper-Fehler-Awareness, siehe `memory/ki/ki_system.md`). Wer denkt, entscheidet `ai_backends.chat_available()` (cloud: `core/cloud.py`/`core/cloud_openai.py`, local: `core/ai.py`); keins da → 503. SSE-Events: `token` (Antworttext), `reflect` (Denk-Strom → dim in der TUI, seit 2026-10-07 mit der Antwort gespeichert, nie gesprochen), `werkzeug` (Tool-Call, `{phase: start\|fertig\|fehler, name, …}`; alle drei Wege seit 10/2026), `fehler` (Backend-Fehler, Cloud-Ablehnung, Rundengrenze → TUI-Statuszeile, NICHT im Verlauf), `ascii` (Inline-Bild), `permission` (Knopf-Rückfrage), `cinema` (News-Sendung), `strom` (erstes Event: Nummer des Zugs, fürs Stoppen), `gespraech` (zweites Event: `{gespraech, nachricht}` — Gesprächs- und Nachricht-id), `gestoppt` (Zug wurde gestoppt; Text bis dahin steht mit `abgebrochen: true` im Gespräch, ohne Text gar nicht), `titel` (`{titel, gespraech}`, nur im ersten Zug eines Gesprächs), `ablage` (`{id, titel, art, fassung}`: ein Werkzeug hat ein Dokument abgelegt, seit 2026-10-07; steht als `dokumente` mit der Antwort im Gespräch), `antwort` (`{antwort: nachricht_id, ablauf: n}` nach dem Speichern, nur wenn die Antwort ein Ablauf-Protokoll hat — Cloud, Schiene gross, seit 2026-10-09), `quellen` (`[{titel, url, werkzeug}]`: die in diesem Zug tatsächlich gelesenen Seiten, von Python aus den Werkzeug-Ergebnissen — nie web_search; nur gross, seit 2026-10-10, `core/quellen.py`; steht als `quellen` mit der Antwort im Gespräch), `done`. Seit 2026-10-07 auch `anhaenge: [ablage-id]` (aus `POST /api/anhang`; unbekannt → 400, Bild ohne Cloud → 400 „Bilder gehen nur mit der Cloud-KI"); bei `ersetzt` gehen die Anhänge der alten Nachricht mit, wenn keine neuen kommen. Länge: bis `nutzer_msg_chars` (Standard 20.000 Zeichen) kommt die Nachricht vollständig bei der KI an; länger → 400 „Die Nachricht ist zu lang (… höchstens 20.000). Längeres als Datei: /anhang <pfad>." (seit 2026-10-07). |
| `/api/chat/wiederholen` | POST  | Letzte Antwort neu erzeugen (seit 2026-10-07): ab der letzten eigenen Nachricht verwerfen, dieselbe neu schicken. Body `{gespraech?}`. SSE wie `/api/chat`. Nichts zu wiederholen → 400, unbekanntes Gespräch → 404, kein Backend → 503. |
| `/api/chat/stop`      | POST    | Laufenden Zug stoppen, bis in die Werkzeug-Schleife (seit 2026-10-07). Body `{strom?}` (aus dem ersten SSE-Event; ohne → jeder laufende Zug). Beendet auch eine offene Erlaubnis-Frage mit „nein“. Antwort `{ok, gestoppt: bool}` — `false` heißt, es lief nichts mehr. |
| `/api/chat/history`   | GET     | Nachrichten eines Gesprächs (`?gespraech=<id>`, sonst das aktive; keins → `[]`): `[{id, role, content, ts, denken?, werkzeuge?, abgebrochen?, anbieter?, modell?}]` (`werkzeuge`: `[{name, args, fehler?, ergebnis?}]`, `ergebnis` seit 2026-10-07 auf 300 Zeichen gekürzt — die TUI klappt damit „Used … ›" auf), versteckte Aufträge fehlen. Seit 2026-10-09 `ablauf_n` (Zahl der Einträge), wenn die Antwort ein Ablauf-Protokoll hat — den Inhalt liefert `GET /api/gespraeche/<id>/ablauf/<nachricht>`. Seit 2026-10-10 `quellen` (`[{titel, url, werkzeug}]`, gelesene Seiten des Zugs). Markiert als gelesen. Geht seit 2026-10-07 auch ohne KI-Backend. Unbekannt → 404. |
| `/api/chat/clear`     | POST    | Neues Gespräch (TUI: `/neu`): das aktive wird abgewählt, das nächste Senden legt eins an. Gelöscht wird nichts. Seit Phase 6: gehörte das offene Gespräch zu einem Projekt, gehört das neue auch dazu; Body `{projekt: id\|null}` setzt es ausdrücklich (unbekannt → 404). → `{ok, projekt, name}` |

## Gespräche (seit 2026-10-07)

`ui/routen/gespraeche.py`, Speicher `core/gespraeche.py`, Doku `memory/ki/gespraeche.md`. Kein KI-Backend nötig.

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/gespraeche` | GET | `{aktiv, neu_projekt, gespraeche: [{id, titel, erstellt, letzte, anzahl, archiviert, ungelesen, projekt, projekt_name}]}` — neueste Aktivität zuerst, „Erinnerungen“ oben, leere fehlen. `?archiv=1` → nur die archivierten; `?projekt=<id>` → nur die eines Projekts (unbekannt → 404). `neu_projekt`: `{id, name}` des Projekts, in dem das nächste neue Gespräch beginnt, oder `null`. |
| `/api/gespraeche` | POST | Neu anlegen und öffnen. Body `{titel?}` → 201 `{ok, id}`. |
| `/api/gespraeche/aktiv` | POST | Öffnen (auf diesem Rechner). Body `{id}`; `null` → das nächste Senden beginnt ein neues. Unbekannt → 404. |
| `/api/gespraeche/<id>` | GET | `{id, kopf, nachrichten}` mit Denken und Werkzeugen; das Ablauf-Protokoll nur als `ablauf_n`. Unbekannt → 404. |
| `/api/gespraeche/<id>/ablauf/<nachricht>` | GET | Ablauf-Protokoll einer Antwort (seit 2026-10-09, `core/zug_ablauf.py`, `memory/ki/ki_system.md` „Ablauf-Protokoll"): `{gespraech, nachricht, ablauf: [{art, zeit, t, …}]}` in Reihenfolge (system, kontext, text, werkzeug, frage, pruefung, fehler, gestoppt, antwort, kosten). `nachricht` = `letzte` → die letzte Antwort mit Protokoll. Gespräch/Nachricht unbekannt oder ohne Protokoll (ältere Antwort, lokale KI) → 404. |
| `/api/gespraeche/<id>/ablauf/<nachricht>/ablage` | POST | Dasselbe als Textdatei in die Ablage (`/trace` im Chat; Herkunft `ablauf`) → 201 `{ok, dokument: {id, titel, art, fassung}}`; ohne Protokoll → 404. |
| `/api/gespraeche/<id>/titel` | POST | Umbenennen, Body `{titel}`. Leer → 400, `erinnerungen` → 400, unbekannt → 404. |
| `/api/gespraeche/<id>/archiv` | POST | Archivieren `{an: true}` (Standard) oder zurückholen `{an: false}`. Nie löschen. War es das aktive, wird es abgewählt. `erinnerungen` → 400, unbekannt → 404. |
| `/api/rueckmeldung` | POST | Eine Antwort der KI bewerten oder die Bewertung ändern (seit 2026-10-08, `core/rueckmeldungen.py`). Body `{gespraech, nachricht, wert: 1\|-1, kommentar?}` → `{ok, rueckmeldung: {id, ts, knoten, gespraech, nachricht, wert, kommentar?, anbieter?, modell?, werkzeuge?, skills?}}`. Falscher Wert / Kommentar über 2.000 Zeichen → 400; Gespräch oder Antwort (Rolle assistant, geltend) unbekannt → 404. Ändern = neues Ereignis, das letzte gilt. |
| `/api/rueckmeldungen` | GET | `{rueckmeldungen: [...]}`: die geltende Bewertung je Antwort, neueste zuerst, dazu `gespraech_titel` und `ausschnitt` (160 Zeichen der Antwort) bzw. `verworfen: true` (Antwort inzwischen wiederholt/bearbeitet). `?gespraech=<id>` → nur die eines Gesprächs. |

## Ablage und Anhänge (`ui/routen/ablage.py`, seit 2026-10-07)

Speicher `core/ablage.py`, Anhänge `core/anhang.py`, Doku `memory/ki/ablage.md`. Kein KI-Backend nötig.

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/ablage` | GET | `{dokumente: [{id, titel, art, herkunft, gespraech, gespraech_titel?, erstellt, geaendert, fassung, archiviert}]}`, neueste Änderung zuerst. `?archiv=1` → nur archivierte. |
| `/api/ablage/<id>` | GET | `{kopf, fassung, inhalt (Text) \| null (Bild, PDF, Word), bytes, mime?, pfad}`; PDF/Word zusätzlich `text` (gelesener Text, Vorschau) und `text_fehler` (seit 2026-10-08, `memory/ki/pdf_word.md`); `?fassung=n` für eine ältere. Unbekannt → 404. |
| `/api/ablage/<id>/roh` | GET | Die neueste Fassung einer **html**-Seite (der Morgenblick) als `text/html`, mit strenger CSP (`default-src 'none'`, kein Skript, `sandbox`). **pdf/docx** (seit 2026-10-08) als Download (`Content-Disposition: attachment`, `nosniff`). Andere Arten / unbekannt → 404. Seit 2026-10-08, `memory/werkzeuge/morgenblick.md`. |
| `/api/ablage/<id>/archiv` | POST | `{an: true}` archivieren (Standard), `{an: false}` zurückholen. Nie löschen. |
| `/api/anhang` | POST | `{pfad, daten (base64), gespraech?}` — die TUI schickt die Bytes, das Backend öffnet den Pfad nie, prüft ihn aber gegen die Sperrliste. → `{id, titel, art, zeichen, gekappt, hinweis}`; gesperrt/zu groß/unlesbar/kaputt → 400 mit Klartext. |

## Morgenblick (`ui/routen/morgenblick.py`, seit 2026-10-08)

Kern `core/morgenblick.py`, Doku `memory/werkzeuge/morgenblick.md`.

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/morgenblick` | POST | Body `{ki?: bool}` (Standard true). Sammelt lokal (kein Netz), lässt das billige Modell Sätze schreiben (ohne Cloud: feste Sätze), legt die Seite in die Ablage. → `{id, titel, url: "/api/ablage/<id>/roh", mit_ki, modell}`. Dauert mit KI einige Sekunden. |
| `/api/morgenblick/auftrag` | GET | Ein Knopf aus dem Morgenblick: `?d=&b=&a=&s=` (Datum, Beschriftung, Auftrag, HMAC-Signatur aus dem Speicher dieses Prozesses). Nur von localhost UND an localhost gerichtet (sonst 403), nur gültig signiert, heute/gestern, nichts zu Geld/Gesundheit/Zugangsdaten (sonst 400). Legt EIN Gespräch an (Auftrag als Vorschlag der KI), setzt es aktiv; derselbe Link zweimal → dasselbe Gespräch. Antwort: kleine HTML-Seite. |

## Abgleich über die Mitte (`ui/routen/abgleich.py`, seit 2026-10-08)

Kern `core/abgleich.py`, Doku `memory/betrieb/abgleich.md`. Nur anschauen;
abgleichen tun Timer, Änderungs-Haken und `scripts/abgleich.py`.

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/abgleich` | GET | `{weg: "rsync"\|"mitte", rechner, schluessel_da, letzter_versuch, letzter_erfolg, fehler, geholt, gesendet, hinweise: [{am, text}] (neueste zuletzt, höchstens 50), konflikte_ordner}`. Die TUI zeigt daraus eine Zeile in Technik · System. |

## KI-Status & Erlaubnis

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/ai/status`         | GET     | Kann ich chatten, und über welchen Kern: `{available, backend: cloud\|local\|null, url, model, provider?, effort?, kosten}`. Die TUI schreibt es in den Titel des KI-Kastens. |
| `/api/ai/kosten` | GET | Was die KI kostet (seit 2026-10-07, „Customize → Usage" im TUI-Chat): `usage.uebersicht()` = `{heute, monat, calls_heute, geschaetzt_monat, modelle: {modell: euro}}` plus `budget` (`ai_backends.budget_lage()`). Nur lesen. |
| `/api/ai/werkzeuge` | GET | Was die KI kann (seit 2026-10-07, „Customize → Capabilities"): `{werkzeuge: [{name, alltag, beschreibung (erster Satz, ≤160), fragt: nie\|immer\|manchmal, schienen: [klein, gross]}]}` in Register-Reihenfolge (`core/werkzeug_register.py`). Nur lesen. |
| `/api/ai/backends`       | GET/POST| Welche Backends erreichbar sind (local/cloud) — speist die EXTERNAL-Box und das kapazitätsbasierte Modul-Gating. POST `{cloud_enabled?, local_enabled?}` legt die Kill-Switches um (persistiert in `data/ai_config.json`). Siehe `memory/ki/ki_system.md`. |
| `/api/permission_answer` | POST    | Antwort auf eine `ask_choice`-/Erlaubnis-Frage (JSON `{answer}`), gegen die angebotenen Knöpfe geprüft (Groß/klein egal). Entsperrt den wartenden Chat-Stream. Seit 2026-10-07 hat die Erlaubnis-Frage Knöpfe mit Geltung (SSE `permission`: `{frage, optionen: ["ja, nur dieses mal", "ja, für dieses gespräch"?, "ja, immer"?, "nein"], erlaubnis: true, geltung: [einmal, gespraech?, immer?, nein]}`); ein altes `"ja"` zählt als „ja, nur dieses mal". Siehe `memory/ki/ki_system.md` → Geltungsbereiche. |
| `/api/erlaubnis` | GET | Was die KI ohne Frage darf (seit 2026-10-07, `/erlaubnis` im Chat): `{immer: [{name, was}], gespraech: [{name, was}], gespraech_id}` — `was` in Alltagswörtern. |
| `/api/erlaubnis/zuruecknehmen` | POST | `{werkzeug: name}` oder `{alle: true}` → „immer" und „für dieses Gespräch" weg; `{weg: [namen], …übersicht}`. Ohne beides → 400. |
| `/api/ai/einstellungen` | GET/POST| Chat-Einstellungen (seit 2026-10-07, `core/ki_einstellungen.py`): GET `{anbieter, anbieter_aktiv, modell, effort, effort_stufen, effort_wirkt, budget, budget_lage, weg, anbieter_liste: [{name, schluessel: bool, spricht, modell, modelle, modelle_quelle}]}` — seit 2026-10-07 `modelle` = alle Chat-Modelle, die der Anbieter meldet (`core/modell_liste.py`, 24 h gecacht; `modelle_quelle` "anbieter" oder "tabelle" = Rückfall auf `providers.py`) — nie ein Schlüssel selbst. POST beliebige von `{anbieter, modell, effort, budget, weg}` (`budget`: Zahl über 0 bis 100 €, "12,50" oder "aus"; `weg`: lokal/cloud/auto), dauerhaft in `data/ai_config.json`. Erst alles prüfen, dann setzen: Unsinn → 400 `{error: Klartext}` und nichts geändert. Hinter den Slash-Befehlen des TUI-Chats. |
| `/api/ai/debug/stream`   | GET     | Devtools-Stream (SSE) für `scripts/ai_devtools.py`: der VOLLE Request (System-Prompt, alle Messages, Tool-Namen, Cache-Breakpoints), die Roh-Antwort, jeder Tool-Call, was der Extraktor in den Graphen schrieb. Verbinden schaltet den Bus (`core/kidebug.py`) an. ⚠ Enthält den kompletten Prompt inkl. Graph-Kontext. |

> `/api/memory` + `/api/memory/<id>` (Legacy-LTM) sind entfallen – Memory
> läuft jetzt über den Konzept-Graphen (siehe `memory/ki/ki_system.md`).

## Skills und Gedächtnis (`ui/routen/skills.py`, seit 2026-10-07)

Für Sashas Gedächtnis-Ansicht in der TUI (`/gedaechtnis`, `/skills`). Geschrieben
wird hier nur, was Sasha selbst tut; die KI schreibt über ihre Werkzeuge.
Doku: `memory/ki/gedaechtnis_dateien.md` → „Für Sasha sichtbar und änderbar".

| Endpoint      | Methode | Beschreibung |
|---------------|---------|--------------|
| `/api/skills` | GET     | Alle Skills (`core/skills.py`, Claude-Format), nach Name: `{skills: [{name, beschreibung, status, herkunft, erstellt, braucht, vermerk}]}` — auch ausgeschaltete und vorgeschlagene — und `skill_liste: {laenge, grenze, zu_lang, gekuerzt, nur_name}` (seit 2026-10-08: wie lang die Liste der aktiven im Prompt mit vollen Beschreibungen wäre, die Grenze 6 000, und wen die letzte Rettung gerade kürzt). `beschreibung` = `description` der SKILL.md; `herkunft` sasha\|ki\|anthropic\|`-`; `braucht` = was ZENTRALE fehlt (warum aus), sonst `""`. Siehe `memory/ki/ki_system.md` → Skills. |
| `/api/skills/<name>/status` | POST | Skill schalten, Body `{status: aktiv\|aus\|vorgeschlagen}` → `{skill, skill_liste}`. Nur `_zentrale.json` ändert sich, die SKILL.md bleibt. Unbekannter Skill (nur der genaue Ordnername) → 404, anderer Status → 400. |
| `/api/gedaechtnis` | GET | `{kernakten: [{akte, text, stand}], bereiche: [{bereich, titel: [...]}], skills: [...], skill_liste}` — Kernakten in der Reihenfolge `hausregeln`, `steckbrief`, `ziele` (ganzer Text, `stand` = Fingerabdruck), Bereiche nur mit Titeln. |
| `/api/gedaechtnis/<akte>` | PUT | Eine Kernakte ersetzen, Body `{text, stand?}` → `{akte, text, stand}`. Nur `hausregeln`, `steckbrief`, `ziele` (sonst 404). Atomar, alte Fassung als `.bak`. `stand` weicht ab (die KI hat inzwischen geschrieben) → 409; kein Text → 400; über 20.000 Zeichen → 400. |

## Projekte (`ui/routen/projekte.py`, seit 2026-10-07)

Claude-Web-Plan Phase 6, Speicher `core/projekte.py`, Doku `memory/ki/projekte.md`.
Kein KI-Backend nötig; geschrieben wird nur, was Sasha in der TUI tut. Unbekanntes Projekt → 404.

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/projekte` | GET | `{projekte: [{id, name, erstellt, archiviert, wissen}]}` nach Name; `?archiv=1` → nur die archivierten. |
| `/api/projekte` | POST | Anlegen, Body `{name, anweisungen?}` → 201 mit dem Projekt. Leer, reserviert (neu, aus, kein …) oder schon da → 400. |
| `/api/projekte/<id>` | GET | `{id, name, erstellt, archiviert, anweisungen, stand, wissen: [{name, groesse}], gespraeche: [...]}` (Gespräche wie `/api/gespraeche`, auch archivierte). |
| `/api/projekte/<id>/anweisungen` | PUT | Body `{text, stand?}` → `{anweisungen, stand}`. Atomar, alte Fassung als `.bak`. `stand` veraltet → 409, kein Text → 400, über 20.000 Zeichen → 400. |
| `/api/projekte/<id>/wissen` | POST | Body `{name, text}` oder `{pfad, name?, text?}` → 201 `{name, groesse}`. Gesperrt (Zugangsdaten, gesperrte Ordner), keine Textdatei, leer, zu lang → 400. Pfad fehlt auf diesem Rechner → 404 `{fehlt: true}` (dann `text` mitschicken). |
| `/api/projekte/<id>/archiv` | POST | `{an: true}` (Standard) oder `{an: false}` → das Projekt. Nie löschen. |
| `/api/projekte/zuordnen` | POST | Body `{gespraech: id\|null, projekt: id\|null}` → `{gespraech, projekt, name}`. `projekt` null löst. `gespraech` null → das nächste neue Gespräch dieses Rechners (ist eins offen → 400). Unbekanntes Gespräch → 404, „Erinnerungen“ → 400. |

## Fotos (ASCII-Bild-Filter)

| Endpoint              | Methode | Beschreibung                          |
|-----------------------|---------|---------------------------------------|

## Maps (Karten-System)

Front-agnostisch: jede Front schickt ihren Viewport (`cx,cy,zoom`) + ihr
Zielraster (`cols,rows,aspect`); die Engine in `core/map/` projiziert fertig.
**Nicht** KI-gegatet (Karte gibt es auch ohne lokale KI). Architektur +
drei Achsen: `memory/maps/maps_system.md`; Quellen/Lizenzen: `memory/maps/maps_quellen.md`.

| Endpoint                 | Methode | Beschreibung                          |
|--------------------------|---------|---------------------------------------|
| `/api/map/base`          | GET     | Basiskarte (Küsten, Achse-1-LOD nach Zoom) als projizierte Linien fürs Zellraster. Query: `cx,cy,zoom,cols,rows,aspect`. |
| `/api/map/braille`       | GET     | Basiskarte als gefülltes Land in Braille (2×4 Subpixel/Zelle), fertige Zeilen. Query: `cx,cy,zoom,cols,rows`. |
| `/api/map/layers`        | GET     | Registry der thematischen Overlays (Achse 2): Layer + Sub-Layer + Quelle (Provenienz) + ob zeitfähig (Achse 3). |
| `/api/map/layer/<id>`    | GET     | Features eines Overlays, projiziert. Query wie `/base` + `sub` (Sub-Layer, z.B. `chokepoints`) + `at` (Zeitpunkt, Achse 3). Antwort trägt `source/vintage/retrieved_at`. 404 bei unbekanntem Layer. |
| `/api/map/countries`     | GET     | Länder-Mittelpunkte (Richtungs-Navigation) + projizierter Umriss des fokussierten Landes. Query wie `/base` + `focus=<Name>`. |

Live: `trade` (IMF PortWatch) — ohne `sub` das **Komposit** (Routenlinien +
Chokepoint-Punkte); `?sub=routes` (Schifffahrtslinien, statisch) bzw.
`?sub=chokepoints` (Engstellen + täglicher Verkehr) einzeln. Lizenziert →
lokal gecacht, nicht committet; Refresh per `python -m map.layers.portwatch`.

## Kalender (Anzeige)

Front-agnostisch wie die Maps: die geteilte Quelle für die Kalender-Mitte
jeder Front (TUI-Modus `c`, Browser-Tab „Kalender" im geparkten Template).
**Nicht** KI-gegatet — reine Anzeige, kein KI-Tool-Pfad (die KI greift den
Kalender weiter über `read_calendar`, nicht über diesen Endpoint), läuft also
auch ohne lokale KI. Datums-Arithmetik macht Python
(`core/kalender.py`), die Front klassifiziert nur `view` + blättert über `ref`.

| Endpoint                | Methode | Beschreibung                          |
|-------------------------|---------|---------------------------------------|
| `/api/calendar`         | GET     | Woche (Mo-So) oder Monatsgitter, nach Tag gruppiert. Query: `view=week`(Default)`|month`, `ref=YYYY-MM-DD` (Default heute). |
| `/api/calendar/entry`   | POST    | Einmal-Termin direkt anlegen. Body `{day=YYYY-MM-DD, label, time?, ende?, ort?, layer?}` (Default-Layer `termine`). Antwort `{ok, conflicts:[…]}` — Konflikt-Zeilen (Reise/Kollision/Knapp) nur als HINWEIS, kein Block. **`bis=YYYY-MM-DD` gesetzt → MEHRTÄGIGER (ganztägiger) Termin** (`add_span`, Spanne [day,bis], kein Konflikt-Check, Antwort `{ok, spanning:true}`; 400 bei bis<day/kaputt). 400 bei fehlendem label/ungültigem day. |
| `/api/calendar/entry/spantime` | POST | Uhrzeit für EINEN Tag einer mehrtägigen Spanne setzen/löschen (leer = ganztägig). Body `{layer?, von, label, day, time?}`. Antwort `{ok:bool}`. 400 ohne von/label/day. |
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

Details zu Modellen + Sprachen: `memory/ki/audio_system.md`.

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
| `/api/mail/reconcile`       | POST    | Gleicht die Server-Ordner an die Keymap an (schon einsortierte Mail nachziehen), Hintergrund-Thread, kehrt sofort zurück. `409` ohne Key, Lock gegen Parallel-Läufe. |
| `/api/mail/inbox`           | GET     | Eingang-Tray: INBOX mit Gelesen-Flag + vermuteter Kategorie je Mail. LIVE; ohne Key leer. |
| `/api/mail/inbox-body?uid=&account=` | GET | Voller Text einer Eingang-Mail, read-only (PEEK, hakt nicht ab). `409` ohne Key. |
| `/api/mail/read`            | POST    | Eingang-Mail abhaken: `\Seen` setzen und bei bekanntem Absender sofort einsortieren. Body `{uid, account?}`. `409` ohne Key. |

Details: `memory/werkzeuge/mail_system.md` (Panel/Drill-down/Hybrid, Passphrase-Quellen, Keyring-CLI).

## Desk View (seit 2026-10-09)

`core/desk.py` über `ui/routen/desk.py`. Ein Desk = eine Datei
`<desk_ordner>/<name>.canvas` (JSON Canvas 1.0). Die TUI rechnet in Zellen
(1 Spalte = 10 px, 1 Zeile = 20 px); Format, Arten und Tasten:
[desk_view.md](desk_view.md). Auch diese Routen beschreibt `openapi.yaml`
(seit 2026-10-10; bei Abweichung gilt die Datei).

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/desk` | GET | `{desks: [{name, elemente, geaendert}]}`, zuletzt geändert zuerst; `elemente` = None bei kaputter Datei. |
| `/api/desk` | POST | Leeren Desk anlegen. Body `{name}` → 201 mit dem Desk; `400` Name ungültig, `409` gibt es schon. |
| `/api/desk/<name>` | GET | `{name, elemente: [{id, x, y, w, h, art, text?, typ?, titel?, datei?, modus?, kachel?}], verbindungen: [{id, von, nach, label?}], stand}`; `404`, `422` kaputte Datei (wird nie überschrieben). |
| `/api/desk/<name>` | PUT | Ganzen Desk schreiben. Body `{elemente, verbindungen, stand}` (Verbindungen dürfen `von_seite`/`nach_seite` tragen; ohne `verbindungen` bleiben die Schnüre der Datei). Fehlende Elemente sind gelöscht, ihre Schnüre auch. Neu anlegen: `art` `notiz`, `bild` oder `kachel` (mit `kachel: {v, app, art, ref}`); eine Kachel darf `rueckfall` (Klartext für Obsidian) mitbringen, ihr Verweis ändert sich danach nie. `409 {error, stand}` wenn die Datei seit dem Laden woanders geändert wurde — nichts geschrieben. |
| `/api/desk-bild/quellen` | GET | Bilder in `~/Zentrale/Input` (und eine Ebene tiefer), neueste zuerst: `{quellen: [{name, pfad}]}` (2026-10-10). |
| `/api/desk-bild` | POST | Bild in `<desk_ordner>/bilder/` kopieren. Body `{quelle}` (Name in Input/ oder Pfad) → 201 `{datei, titel, w, h}` (`datei` relativ zum Desk-Ordner, w/h Vorschlag in Zellen); `400` keine Bild-Endung, `404` nicht gefunden, `422` kein lesbares Bild, `503` Pillow fehlt. Gleicher Name + gleicher Inhalt → dieselbe Datei, sonst `name-2.png`. |
| `/api/desk-bild/vorschau` | POST | Body `{datei, w, h, modus: mono\|farbe, invert?}` → `{status: ok, zeilen: [[[zeichen, "#rrggbb"\|null], …], …]}` (Sashas ASCII-Filter, `core/bild_vorschau.py`, höchstens 32 Farben) oder `{status: weg\|kein_bild\|ohne_pillow, text}`; `400` Pfad hinaus / falscher Modus. |
| `/api/desk-bild/oeffnen` | POST | Body `{datei}` → `{pfad, da, betrachter}` — die TUI öffnet selbst (Einstellung `bild_betrachter`). |
| `/api/desk-bild/datei` | GET | `?datei=bilder/x.png` → das Bild selbst (für eine TUI auf einem anderen Rechner); `404` fehlt. |

## Kacheln (seit 2026-10-10)

`core/kacheln.py` über `ui/routen/kachel.py` — der Hub, durch den jede
Oberfläche den Katalog liest und den Inhalt einer Kachel holt (nie direkt
bei der App). Verweis = Adresse `zentrale://<app>/<art>?<parameter>`
(`core/adressen.py`). **Autorität für Anfragen, Antworten und Fehler dieser
Routen ist `openapi.yaml`** im Repo-Wurzelordner (OpenAPI 3.1, seit
2026-10-10; `tests/test_openapi.py` hält Routen und Datei gleich) — die
Tabelle hier ist nur der Überblick. Form und Regeln: [hub_bauplan.md](hub_bauplan.md)
„Kacheln", „Adressen", „Katalog", „Farbrollen"; Desk:
[desk_view.md](desk_view.md).

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/api/kacheln` | GET | Katalog: `[{app, art, titel, min, bevorzugt, max, ttl, parameter, aktionen, formen}]`; `parameter` = JSON Schema 2020-12 (seit 2026-10-10). Genaues: `openapi.yaml`. |
| `/api/kachel` | POST | Inhalt einer Kachel `{adresse, w, h, oben?, stand?}` → Zeilen mit Farbrollen \| unverändert \| zu klein; Fehler `ungueltig` (400, auch Schema- und Spannen-Fehler), `recht` (403), `weg` (404), `aus` (503). Genaues: `openapi.yaml`. |
| `/api/kachel/aktion` | POST | `{adresse, aktion: "oeffnen"}` → `{zeige: {adresse}}`. Genaues: `openapi.yaml`. |

Quellen heute: `kalender`/`ausschnitt` (`core/kachel_kalender.py`, Adresse
`zentrale://kalender/ausschnitt?modus=mitlaufend&tage=N` oder
`…?bis=JJJJ-MM-TT&modus=fest&von=JJJJ-MM-TT`, höchstens 31 Tage).
Seit 2026-10-10 dazu `fokus`/`liste` (`core/kachel_fokus.py`,
`zentrale://fokus/liste?erledigte=false&liste=<lid>&tiefe=3`, `oeffnen` →
`zentrale://fokus/<lid>`) und `graph`/`verlauf` (`core/kachel_graph.py`,
`zentrale://graph/verlauf?graph=<gid>&tage=14`, 2–365 Tage, `oeffnen` →
`zentrale://graph/<gid>`). Welche Liste/welcher Graph: im Katalog als
`oneOf [{const, title}]` mit den Listen/Graphen von jetzt (gibt es keine,
fehlt der Eintrag); der Hub prüft nur die Form, gelöschte Liste/Graph →
`404 {fehler: "weg"}`.

## Tutor (eigene App, seit 2026-10-09)

Der Tutor ist eine eigene App mit eigenem Server (Repo `language-tutor`,
Port 5070); seine Routen (`/api/tutor/*`, dazu `/hub/ereignis`) und die
Bedeutung der Status-Felder stehen dort im Bauplan (`docs/bauplan.md`).
ZENTRALE hat dafür keine Route mehr. `/api/speak` und `/api/transcribe` hier
bleiben sprachneutral für ZENTRALE selbst; der Tutor spricht direkt mit den
Stimm-Diensten.

## Historie

- **2026-05** — Sensor-Webhook + Telemetrie-Push für den Pi.
- **2026-06/07** — Graphen, Listen, Melodien, Kalender-Schreib-Endpoints,
  Karte, Mail-Triage; Legacy `/api/memory*` entfallen (Konzept-Graph).
- **2026-07-17** — Tutor-Abschnitt korrigiert (behauptete „entfernt",
  der Tutor lief), `present`/`reason` im Status, `vocab` aus `/api/state`.
- **2026-09-04** — Aussenposten-Versorgung (`manifest`/`paket`).
- **2026-09-17** — Tutor-Routen in den Bauplan mit Drift-Test verschoben.
- **2026-10-08** — Zugangsschlüssel vor allen Routen, `/api/zugang`.
- **2026-10-09** — `/api/desk` (Desk View).
- **2026-10-10** — `/api/desk-bild…` (Bilder auf dem Desk).
- **2026-10-10** — `/api/kachel`, `/api/kachel/aktion` (Kacheln, Kalender).
- **2026-10-10** — `/api/kacheln` (Katalog); Kacheln mit Adresse statt
  app/art/ref, `oeffnen` antwortet mit einer Adresse.
- **2026-10-10** — `/api/kacheln` liefert `max` immer (ohne Angabe der
  Quelle die Hub-Grenze 400×400; für `r` = Größe ändern im Desk).
- **2026-10-10** — Kachel-Quellen `fokus`/`liste` und `graph`/`verlauf`;
  Wahl-Felder mit `dynamisch` (Werte frisch im Katalog).
- **2026-10-10** — Katalog `felder` (eigenes Format) → `parameter` (JSON
  Schema 2020-12); Kachel- und Desk-Routen in `openapi.yaml` (OpenAPI 3.1)
  beschrieben, mit Drift-Test.
