# Bauplan des Kerns — Schichten, Türen, Altlasten

**Wozu:** Sasha, 2026-10-05: *„ich will nich dass wir irgendwann an einen
punkt kommen an dem der code unwartbar wird und alles um die ohren fliegt!"*
ZENTRALE hatte an diesem Tag 71.000 Zeilen. Die Außengrenze hielt (Backend
und Fronten getrennt, `state.py` als einzige Brücke, Tutor hinter einer Tür),
aber **innen** sagte nichts, wer wen benutzen darf. So entstanden 15
Import-Kanten im Kreis im KI-Kern und eine TUI-Funktion mit 7.700 Zeilen.

**Es driftet nicht, weil ein Test es erzwingt:** `tests/test_kern_bauplan.py`
liest die Tabellen dieser Datei und wird rot, wenn eine Kern-Datei keine
Schicht hat, eine Abhängigkeit nach oben zeigt, ein neuer Import-Kreis
entsteht, jemand an einer Tür vorbeigeht oder ein Riese wächst.
**Pflegeregel:** Struktur ändern → Bauplan im selben Commit ändern.

Verhalten steht woanders: Gesamtbild in [architektur.md](architektur.md),
der Tutor hat seinen eigenen Bauplan in
[../tutor/bauplan.md](../tutor/bauplan.md).

## Die Schichten

```
   Fronten — eigene Programme, reden per HTTP mit den Routen
   tui/zentrale_tui.py · tutor/room.py
                     │ HTTP
 ┌───────────────────▼──────────────────────────────────────────────┐
 │ 5  Routen         ui/app.py + ui/routen/ — darf alles darunter   │
 ├──────────────────────────────────────────────────────────────────┤
 │ 4  Ablauf         Event-Loop, Hot Reload, die Tür zum Tutor      │
 ├──────────────────────────────────────────────────────────────────┤
 │ 3  KI-Kern        denken: Modelle, Schleife, Prompt-Schienen     │
 ├──────────────────────────────────────────────────────────────────┤
 │ 2  Dienste        das Fach: Kalender, Mail, Listen, Gedächtnis … │
 ├──────────────────────────────────────────────────────────────────┤
 │ 1  Fundament      weiß nichts vom Fach: state, net, Config …     │
 └──────────────────────────────────────────────────────────────────┘
```

**Die eine Regel:** Ein Modul darf Module aus seiner **eigenen oder einer
tieferen** Schicht importieren, nie aus einer höheren. Gezählt wird auch der
Import innerhalb einer Funktion — er ist dieselbe Abhängigkeit, nur
versteckt.

Braucht ein tieferes Modul doch etwas von oben, gibt es zwei saubere Wege:
das Gebrauchte nach unten verschieben, oder es von oben **hereingeben**
(als Argument oder Callback), statt es zu importieren.

## Module

Die Schicht-Nummer ist die Wahrheit, die der Test liest. Pakete (`profil/`,
`map/`) zählen als ein Modul.

| Modul | Schicht | Was |
|---|---|---|
| `state` | 1 | Geteilter Zustand, thread-safe — die einzige Brücke zwischen Event-Loop und Flask |
| `events` | 1 | Event-Konstanten |
| `net` | 1 | HTTP-Wrapper mit Terminal-Logging |
| `datasync` | 1 | Push-on-write zum Peer nach echter Daten-Änderung |
| `dateien` | 1 | Atomar schreiben (alte oder neue Fassung, nie eine halbe) — für alle Datendateien; Rechnername für Dateien pro Rechner |
| `ai_config` | 1 | Kill-Switches und API-Keys aus `data/ai_config.json`, `setting()`-Rangfolge |
| `providers` | 1 | Anbieter-Liste des Kerns (URL, Key, Dialekt, Modelle) |
| `prices` | 1 | Preistabelle der Cloud-Modelle, keine Logik |
| `usage` | 1 | Buchführung der Cloud-Kosten pro Tag und Monat |
| `kidebug` | 1 | Devtools-Bus der KI (`scripts/ai_devtools.py`) |
| `transkript` | 1 | Rohes Gesagtes, append-only jsonl |
| `context` | 1 | Datei-Zugriff nur über die Whitelist |
| `melden` | 1 | Meldung auf dem Desktop |
| `glossary` | 1 | Kuratiertes Mini-Glossar |
| `categories` | 1 | Data-Collection-Kategorien |
| `host_metrics` | 1 | CPU/GPU/VRAM/Temp/RAM des PCs |
| `aussenposten` | 1 | Pakete für Knoten ohne Backend |
| `theme` | 1 | Tag/Nacht-Modus, die Datei als einzige Wahrheit |
| `tone` | 1 | Ton-Erzeuger fürs TUI-Klavier |
| `pc_status` | 1 | Ist der andere Knoten gerade da? |
| `kalender` | 2 | Termine, Routinen, Konflikt-Alarm — die Fassade, Speicher austauschbar |
| `kalender_zeitraum` | 2 | Relative Zeiträume („diese_woche") in Daten übersetzen |
| `kalender_regel` | 2 | Wann eine Routine stattfindet (RRULE → Tage), eine Stelle für Fassade und .ics |
| `kalender_speicher` | 2 | Wählt den Kalender-Speicher (`kalender_speicher`: json/ics), alle Kalender-Pfade |
| `kalender_json` | 2 | Der alte Speicher `data/ai_calendar.json`, atomar, mit Rückfall-Sperre |
| `kalender_ics_abbildung` | 2 | Ein Termin/eine Routine ↔ VEVENT, verlustfrei oder gar nicht |
| `kalender_ics` | 2 | Der .ics-Speicher: vdir lesen (Cache), nur Unterschiede schreiben, Nebendaten |
| `kalender_sicherung` | 2 | Atomar schreiben, Datei-Sperre, Verlauf, Grabsteine, Snapshots, Massenlösch-Sperre |
| `kalender_spiegel` | 2 | git-Spiegel der Kalenderdaten außerhalb von `data/` |
| `kalender_migration` | 2 | Umzug JSON → .ics: prüfen (alle Lesefunktionen über beide Speicher, Feld-Inventar), ausführen, Rückweg |
| `lists` | 2 | Listen-Registry (To-Do, Checklisten) |
| `notes` | 2 | Notiz-Registry des TUI-Notiz-Werkzeugs |
| `melodies` | 2 | Melodie-Registry des Klaviers |
| `graphs` | 2 | Lifestyle-Messreihen (≠ `graph`) |
| `cycle` | 2 | Zyklus/PMS-Vorhersage aus dem »periode«-Graphen |
| `mail` | 2 | Mail-Triage: IMAP rein, sortieren, zurückschreiben |
| `mail_rules` | 2 | Triage-Keymap (Sender → Ordner/Aktion) |
| `mail_oauth` | 2 | OAuth2 für Outlook.com-IMAP |
| `mail_secrets` | 2 | Verschlüsselter Speicher der Mail-Zugangsdaten |
| `mail_puffer` | 2 | Puffer des Mail-Panels (Live-Zählung, Ordner-Inhalte) und seine Hintergrund-Jobs |
| `news` | 2 | Persönliche Tagesschau: RSS und Briefing |
| `web` | 2 | Gegatete Internet-Pipe (Suche, Seite holen) |
| `embeddings` | 2 | Vektoren lokal (bge-m3) oder in der Cloud |
| `graph` | 2 | Konzept-Graph der KI (seit 18.08.2026 aus) |
| `gedaechtnis` | 2 | Das Datei-Gedächtnis, das die KI liest und fortschreibt |
| `gespraeche` | 2 | Chat-Gespräche auf der Platte: Ordner pro Gespräch, Datei pro Rechner, Ereignisse (nachricht/verwerfen), Liste, aktiv pro Rechner |
| `chat_suche` | 2 | Suche quer durch alle Gespräche und das alte Transkript (search_chats, read_chat): normalisierte Wörter, Rang nach Dichte und Aktualität |
| `ascii_lib` | 2 | ASCII-Bibliothek für Bild-Marker |
| `audio` | 2 | HTTP-Client für Whisper und TTS |
| `telemetry` | 2 | Telemetrie-Aggregat PC + Pi |
| `anwesenheit` | 2 | Ist Sasha da, schaut er hin? |
| `takt` | 2 | Wann ZENTRALE von sich aus spricht |
| `map` | 2 | Geo-Layer-System der Weltkarte |
| `ollama` | 2 | Anbindung an Ollama: Adresse, Modell, Kontext, Sampling, Erreichbarkeit, Warmup — einmal |
| `sandbox` | 2 | Code abgeschottet ausführen (bubblewrap): eigener Arbeitsordner, kein Netz, keine Dateien von Sasha, Zeit-/Speicher-/Ausgabe-Grenzen |
| `skills` | 2 | Skills der KI: Anleitungen je Art Aufgabe als Dateien im Gedächtnis, Liste für den Prompt, laden/vorschlagen/ändern |
| `ai` | 3 | Ollama-Weg, Tool-Liste und -Ausführung, Erlaubnis-Abfrage, Prompt-Bausteine |
| `ai_backends` | 3 | Wer denkt: lokal oder Cloud, Anbieter, Modell, Effort, Rundengrenze |
| `cloud` | 3 | Anthropic-Weg |
| `cloud_openai` | 3 | OpenAI-kompatibler Weg |
| `werkzeug_schleife` | 3 | Die eine Tool-Schleife aller Wege |
| `profil` | 3 | Prompt-Schienen klein und gross |
| `consolidation` | 3 | Nach dem Zug: Transkript (und Graph-Extraktion, wenn an) |
| `erlaubnis` | 3 | Das Erlaubnis-Gate: die Tür, durch die die Schleife fragt (Regeln und Fragen stehen im Werkzeug-Register) |
| `ki_antwort` | 3 | Fertige Antwort: Bild-Marker ziehen, Zug zum Merken vormerken |
| `ki_prompt` | 3 | Prompt-Bausteine für jeden Weg: Jetzt-Block, Imprint, Alarme, Denk-Heuristik, Schalter |
| `ki_einstellungen` | 3 | Chat-Einstellungen (Anbieter, Modell, Effort, Budget, Weg) lesen und mit Klartext-Prüfung setzen — für `/api/ai/einstellungen` |
| `ki_werkzeuge` | 3 | Was ein KI-Werkzeug tut: ausfuehren(name, args) → Kalender, Notizen, Netz, Mail, Messreihen |
| `werkzeug_register` | 3 | Ein Eintrag pro KI-Werkzeug: Schema, Beschreibung je Schiene, Erlaubnis-Regel + Frage; die Ausführer melden sich aus `ki_werkzeuge` an |
| `kern` | 3 | Der eine Einstieg: kern.chat(verlauf) wählt den Weg (lokal/Anthropic/OpenAI) und fährt ihn |
| `billig` | 3 | Ein Einmal-Aufruf beim billigen Modell des aktiven Anbieters (beide Dialekte, Kosten gebucht) — Graph-Extraktor, Gesprächstitel |
| `gespraech_titel` | 3 | Gesprächstitel: sofort aus den ersten Wörtern, nach der ersten Antwort vom billigen Modell |
| `main` | 4 | Event-Loop |
| `brain` | 4 | Input → neue Events |
| `actions` | 4 | Events → Nebenwirkungen |
| `clock` | 4 | Uhrzeit-Events |
| `sensors` | 4 | Sensor-Simulation |
| `hot_reload` | 4 | Hot Reload fürs Backend |
| `tutor_port` | 4 | Die einzige Tür vom Kern zum Tutor |
| `takt_treiber` | 4 | Der Takt-Thread: fragt `takt`, spricht über den KI-Kern ins Gespräch „Erinnerungen“, meldet |

Schicht 5 liegt außerhalb von `core/` und steht deshalb nicht in der
Tabelle, sondern im nächsten Abschnitt.

## Routen (Schicht 5)

Seit 2026-10-06 hat jede Gruppe von HTTP-Routen ein eigenes Modul. Vorher
standen alle 89 Routen in `ui/app.py` (2.400 Zeilen), und jede Änderung,
egal woran, ging durch dieselbe Datei.

- `ui/app.py` legt nur die App an, hängt die Bereiche ein (`routen.einhaengen`)
  und startet. **Hier steht keine Route** — der Test prüft das.
- `ui/routen/<bereich>.py` hält die Routen eines Bereichs als Flask-Blueprint
  `bp`. Jedes Modul steht in `ui/routen/__init__.py` unter `BEREICHE` — der
  Test prüft auch das, sonst gäbe es Routen, die nie eingehängt werden.
- `ui/routen/gemeinsam.py` hält, was mehrere Bereiche brauchen (Pfad zu
  `data/`, die 503-Antworten für „keine KI" und „kein Tutor-Backend").
- Routen sind **dünne Adapter**: Anfrage lesen, Kern fragen, Antwort formen.
  Zustand, Caches und Hintergrund-Threads gehören in den Kern.

| Bereich | Was |
|---|---|
| `zustand` | State-Polling, Sensor-Webhook, Telemetrie, Aussenposten-Pakete |
| `erfassung` | Data-Collection, `/api/log`, Lifestyle-Graphen, Zyklus |
| `klavier` | Melodien |
| `listen` | Listen, Einträge, Projekte |
| `notizen` | Block-Notizen |
| `karte` | Weltkarte |
| `kalender` | Kalender |
| `ki` | Chat-Stream, Wiederholen, Stoppen, Verlauf, Erlaubnis, Status, Backend-Wahl, Einstellungen, Devtools |
| `gespraeche` | Gesprächs-Liste, neu, öffnen, laden, umbenennen, archivieren |
| `stimme` | Sprechen und Zuhören |
| `tutor` | alles unter `/api/tutor/` |
| `mail` | Mail-Triage |
| `skills` | Skills der KI (Liste, an/aus) und das Gedächtnis für Sasha: Kernakten, Bereiche, Kernakte ändern |

## Türen

Zwei Fronten und ein Addon wohnen im selben Repo, gehören aber nicht zum
Kern. Was sie aus dem Kern importieren dürfen, steht hier und **nur** hier:

| Bereich | Darf aus dem Kern | Warum |
|---|---|---|
| `tui/` | `theme`, `tone`, `pc_status` | Reine Helfer ohne Kern-Abhängigkeit. Alles andere holt die TUI per HTTP von den Routen (`ui/routen/`). |
| `tutor/` | `ai`, `ai_backends`, `state` | Der Tutor ist ein eigenes Programm, nutzt aber die Modell-Anbindung und das Log des Kerns. Wird mit der „Straße“ zu einem einzigen Einstieg. |

Umgekehrt erreichen Kern und Routen den Tutor **nur** über
`core/tutor_port.py`.

## Altlasten

Was am 05.10.2026 schon gegen die Regeln verstieß. Die Listen dürfen nur
schrumpfen: der Test meldet eine erledigte Altlast und verlangt, sie hier
auszutragen. Neues kommt nie hinzu — wer eine neue Ausnahme braucht, löst
das Problem statt es einzutragen.

### Altlast: Kreis-Kanten

Ein Import-Kreis heißt: A braucht B, B braucht A — auch über Umwege.

**Keine mehr.** Am 2026-10-05 verbanden 15 Kanten sechs Module des KI-Kerns
zu einem Knoten (`ai`, `ai_backends`, `cloud`, `cloud_openai`,
`consolidation`, `werkzeug_schleife`). Ursache: `ai.py` war ab Mai 2026 die
einzige KI-Datei und wurde zum Ersatzteillager; jeder neue Teil wurde
daneben gebaut und bediente sich dort. Am 2026-10-06 in fünf Schritten
aufgelöst (`memory/ki/kern_aufbau.md`, K1–K5): Ollama-Anbindung, Merken,
Erlaubnis, Antwort, Prompt-Bausteine und Werkzeuge bekamen je ein eigenes
Modul, und `kern.chat` wurde der eine Einstieg. Die Tabelle bleibt für den
Test stehen; ein neuer Kreis wird rot und darf hier NICHT eingetragen werden.

| Kante | Wofür |
|---|---|

### Altlast: Türen

Keine mehr — die letzte (`ui/app.py → tutor.debug`) ist am 2026-10-06 über
`tutor_port.debug_bus()` gelöst. Die Tabelle bleibt für den Test stehen.

| Weg | Wofür |
|---|---|

### Altlast: Riesen

Grenze: eine Funktion über 250 Zeilen, eine Datei über 1.500 Zeilen (in
`core/`, `ui/`, `tui/`, `tutor/`). Die Zahl rechts ist **eingefroren**: der
Riese darf nicht wachsen, und wenn er schrumpft, wird die Zahl hier gesenkt.
Sasha, 05.10.2026: einfrieren, dann zerlegen (Punkt 3).

| Wo | Zeilen höchstens |
|---|---|
| `tutor/room.py` | 4034 |
| `tutor/room.py::main` | 1829 |
| `core/mail.py` | 1924 |

## Wenn der Test rot wird

- **„steht nicht im Bauplan"** — neues Modul in die Tabelle *Module*, in die
  niedrigste Schicht, deren Regel es erfüllt.
- **„Abhängigkeit nach OBEN"** — das Gebrauchte eine Schicht tiefer ziehen,
  oder es als Argument hereingeben.
- **„Neuer Import-Kreis"** — was beide brauchen, in ein eigenes, tieferes
  Modul ziehen. Nicht als Altlast eintragen.
- **„Tür umgangen"** — TUI: über eine Route in `ui/routen/` gehen. Kern zum
  Tutor: über `tutor_port`.
- **„Riese gewachsen"** — das Neue in eine eigene Funktion oder Datei legen.
  In der TUI heißt das: eine eigene Ansicht in `tui/ansichten/`
  ([tui_bauplan.md](tui_bauplan.md)).
- **„Gut gemacht — kleiner geworden"** — die Zahl oben senken oder die Zeile
  streichen. Das ist der Sinn der Sache.
