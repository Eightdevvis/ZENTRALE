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
 │ 5  Routen         ui/app.py — darf alles darunter                │
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
| `kalender` | 2 | Termine, Routinen, Konflikt-Alarm |
| `lists` | 2 | Listen-Registry (To-Do, Checklisten) |
| `notes` | 2 | Notiz-Registry des TUI-Notiz-Werkzeugs |
| `melodies` | 2 | Melodie-Registry des Klaviers |
| `graphs` | 2 | Lifestyle-Messreihen (≠ `graph`) |
| `cycle` | 2 | Zyklus/PMS-Vorhersage aus dem »periode«-Graphen |
| `mail` | 2 | Mail-Triage: IMAP rein, sortieren, zurückschreiben |
| `mail_rules` | 2 | Triage-Keymap (Sender → Ordner/Aktion) |
| `mail_oauth` | 2 | OAuth2 für Outlook.com-IMAP |
| `mail_secrets` | 2 | Verschlüsselter Speicher der Mail-Zugangsdaten |
| `news` | 2 | Persönliche Tagesschau: RSS und Briefing |
| `web` | 2 | Gegatete Internet-Pipe (Suche, Seite holen) |
| `embeddings` | 2 | Vektoren lokal (bge-m3) oder in der Cloud |
| `graph` | 2 | Konzept-Graph der KI (seit 18.08.2026 aus) |
| `gedaechtnis` | 2 | Das Datei-Gedächtnis, das die KI liest und fortschreibt |
| `ascii_lib` | 2 | ASCII-Bibliothek für Bild-Marker |
| `audio` | 2 | HTTP-Client für Whisper und TTS |
| `telemetry` | 2 | Telemetrie-Aggregat PC + Pi |
| `anwesenheit` | 2 | Ist Sasha da, schaut er hin? |
| `takt` | 2 | Wann ZENTRALE von sich aus spricht |
| `map` | 2 | Geo-Layer-System der Weltkarte |
| `ai` | 3 | Ollama-Weg, Tool-Liste und -Ausführung, Erlaubnis-Abfrage, Prompt-Bausteine |
| `ai_backends` | 3 | Wer denkt: lokal oder Cloud, Anbieter, Modell, Effort, Rundengrenze |
| `cloud` | 3 | Anthropic-Weg |
| `cloud_openai` | 3 | OpenAI-kompatibler Weg |
| `werkzeug_schleife` | 3 | Die eine Tool-Schleife aller Wege |
| `profil` | 3 | Prompt-Schienen klein und gross |
| `consolidation` | 3 | Nach dem Zug: Transkript (und Graph-Extraktion, wenn an) |
| `main` | 4 | Event-Loop |
| `brain` | 4 | Input → neue Events |
| `actions` | 4 | Events → Nebenwirkungen |
| `clock` | 4 | Uhrzeit-Events |
| `sensors` | 4 | Sensor-Simulation |
| `hot_reload` | 4 | Hot Reload fürs Backend |
| `tutor_port` | 4 | Die einzige Tür vom Kern zum Tutor |

`ui/app.py` ist Schicht 5 und darf alles darunter. Es steht nicht in der
Tabelle, weil es nicht in `core/` liegt.

## Türen

Zwei Fronten und ein Addon wohnen im selben Repo, gehören aber nicht zum
Kern. Was sie aus dem Kern importieren dürfen, steht hier und **nur** hier:

| Bereich | Darf aus dem Kern | Warum |
|---|---|---|
| `tui/` | `theme`, `tone`, `pc_status` | Reine Helfer ohne Kern-Abhängigkeit. Alles andere holt die TUI per HTTP von `ui/app.py`. |
| `tutor/` | `ai`, `ai_backends`, `state` | Der Tutor ist ein eigenes Programm, nutzt aber die Modell-Anbindung und das Log des Kerns. Wird mit der „Straße“ zu einem einzigen Einstieg. |

Umgekehrt erreichen Kern und Routen den Tutor **nur** über
`core/tutor_port.py`.

## Altlasten

Was am 05.10.2026 schon gegen die Regeln verstieß. Die Listen dürfen nur
schrumpfen: der Test meldet eine erledigte Altlast und verlangt, sie hier
auszutragen. Neues kommt nie hinzu — wer eine neue Ausnahme braucht, löst
das Problem statt es einzutragen.

### Altlast: Kreis-Kanten

Ein Import-Kreis heißt: A braucht B, B braucht A — auch über Umwege. Diese
15 Kanten verbinden sechs Module des KI-Kerns zu einem Knoten. Ursache:
`ai.py` war ab Mai 2026 die einzige KI-Datei und wurde zum Ersatzteillager;
jeder neue Teil wurde daneben gebaut und bediente sich dort. Aufgelöst wird
das in Punkt 2 (KI-Kern entflechten).

| Kante | Wofür |
|---|---|
| `ai → consolidation` | gibt jeden Gesprächszug zum Speichern weiter |
| `ai → werkzeug_schleife` | der lokale Weg fährt durch die gemeinsame Schleife |
| `ai_backends → ai` | fragt, ob Ollama läuft |
| `ai_backends → cloud` | liefert das Modul für den Anthropic-Chat |
| `ai_backends → cloud_openai` | liefert das Modul für den OpenAI-Chat |
| `cloud → ai` | Tool-Liste, Tool-Ausführung, Prompt-Bausteine, Zeit- und Alarm-Block |
| `cloud → ai_backends` | Modell und Effort |
| `cloud → werkzeug_schleife` | die Schleife |
| `cloud_openai → ai` | Tool-Liste, Tool-Ausführung, Graph-Schalter |
| `cloud_openai → ai_backends` | Modell |
| `cloud_openai → cloud` | statischer Prompt, wechselnder Block, Cloud-Graph |
| `cloud_openai → werkzeug_schleife` | die Schleife |
| `consolidation → ai` | ob Ollama läuft, Graph-Zugriff |
| `werkzeug_schleife → ai` | Erlaubnis-Liste, Antwort mit Bild-Markern |
| `werkzeug_schleife → ai_backends` | Rundengrenze |

### Altlast: Türen

| Weg | Wofür |
|---|---|
| `ui/app.py → tutor` | die Devtools-Route holt sich `tutor.debug` direkt statt über `tutor_port` |

### Altlast: Riesen

Grenze: eine Funktion über 250 Zeilen, eine Datei über 1.500 Zeilen (in
`core/`, `ui/`, `tui/`, `tutor/`). Die Zahl rechts ist **eingefroren**: der
Riese darf nicht wachsen, und wenn er schrumpft, wird die Zahl hier gesenkt.
Sasha, 05.10.2026: einfrieren, dann zerlegen (Punkt 3).

| Wo | Zeilen höchstens |
|---|---|
| `tui/zentrale_tui.py` | 6645 |
| `tui/zentrale_tui.py::run_ui` | 4582 |
| `tui/zentrale_tui.py::run_ui.draw_overlay` | 499 |
| `tui/zentrale_tui.py::run_ui.draw_list_tool` | 259 |
| `tutor/room.py` | 4034 |
| `tutor/room.py::main` | 1829 |
| `ui/app.py` | 2434 |
| `core/mail.py` | 1924 |
| `core/kalender.py` | 1560 |

## Wenn der Test rot wird

- **„steht nicht im Bauplan"** — neues Modul in die Tabelle *Module*, in die
  niedrigste Schicht, deren Regel es erfüllt.
- **„Abhängigkeit nach OBEN"** — das Gebrauchte eine Schicht tiefer ziehen,
  oder es als Argument hereingeben.
- **„Neuer Import-Kreis"** — was beide brauchen, in ein eigenes, tieferes
  Modul ziehen. Nicht als Altlast eintragen.
- **„Tür umgangen"** — TUI: über eine Route in `ui/app.py` gehen. Kern zum
  Tutor: über `tutor_port`.
- **„Riese gewachsen"** — das Neue in eine eigene Funktion oder Datei legen.
  In der TUI heißt das: ein eigenes Modul neben `zentrale_tui.py`.
- **„Gut gemacht — kleiner geworden"** — die Zahl oben senken oder die Zeile
  streichen. Das ist der Sinn der Sache.
