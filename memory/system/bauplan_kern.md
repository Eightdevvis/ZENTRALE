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

Verhalten steht woanders: Gesamtbild in [architektur.md](architektur.md).
Der Tutor ist seit 2026-10-09 eine eigene App (Repo `language-tutor`, mit
eigenem Bauplan); wie Hub und Apps zusammenhängen, steht in
[hub_bauplan.md](hub_bauplan.md).

## Die Schichten

```
   Fronten — eigene Programme, reden per HTTP mit den Routen
   tui/zentrale_tui.py   (Apps wie der Tutor: eigene Prozesse, eigene Repos)
                     │ HTTP
 ┌───────────────────▼──────────────────────────────────────────────┐
 │ 5  Routen         ui/app.py + ui/routen/ — darf alles darunter   │
 ├──────────────────────────────────────────────────────────────────┤
 │ 4  Ablauf         Event-Loop, Hot Reload                         │
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
| `datasync` | 1 | Nach echter Daten-Änderung: Abgleich über die Mitte anstoßen (gedrosselt) bzw. alter Push-on-write zum Peer |
| `abgleich` | 1 | Abgleich über die Mitte, ein Lauf von vorn bis hinten: Basis, Vorhaben (absturzsicher), Hinweise, Zustand, Weg umstellen |
| `abgleich_auswahl` | 1 | Positivliste: was den Rechner verlassen darf (Datensicherung und Abgleich) |
| `abgleich_schluessel` | 1 | Der Schlüssel der Mitte: anlegen, laden, ablegen, Fernet, versteckte Dateinamen |
| `abgleich_zusammenfuehren` | 1 | Drei-Wege-Regeln über die Basis: JSON nach Eintrag/Feld, Zähler, Zeilen, Text mit beiden Fassungen |
| `abgleich_mitte` | 1 | Die Mitte hinter vier Handgriffen (holen, vorbereiten, senden, enthaelt); Umsetzung git |
| `zugang` | 1 | Zugangsschlüssel des Backends: anlegen, laden, zeitkonstant vergleichen, Modus aus/melden/an, Keks und Browser-Link (Prüfung selbst: `ui/routen/zugang.py`) |
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
| `aussenposten` | 1 | Pakete für Knoten ohne Backend (auch Dateien von Apps, `app:<name>/…`) |
| `apps` | 1 | Installierte Apps (Hub-Bauplan): Ordner (`app_pfad_<name>`), Manifest `app.toml`, Abonnenten eines Ereignisses — liest nur, importiert nie App-Code |
| `theme` | 1 | Tag/Nacht-Modus, die Datei als einzige Wahrheit |
| `tone` | 1 | Ton-Erzeuger fürs TUI-Klavier |
| `pc_status` | 1 | Ist der andere Knoten gerade da? |
| `zug` | 1 | Der laufende Chat-Zug: Gesprächs-id und Stopp-Signal für die Werkzeuge, Ereignisse von Werkzeugen an die TUI (z. B. `ablage`) |
| `zug_ablauf` | 1 | Ablauf-Protokoll des laufenden Chat-Zugs (nur Cloud, gross): Kontext, Text zwischen Werkzeugen, Werkzeuge mit vollem Ergebnis, Fragen, Prüfung, Antwort, Kosten — nur mitschreiben; als Text für /trace |
| `werkzeug_befund` | 1 | Was ein Werkzeug zurückgibt: Status (`[ergebnis: ok/fehlgeschlagen/…]`), Beleg und Fehlercode; feste Formen ERLEDIGT/ABGEBROCHEN; die Schiene des laufenden Werkzeug-Aufrufs |
| `fehlercodes` | 1 | Die eine Tabelle der Fehlercodes der KI-Werkzeuge (Code → Ursache, was tun); `explain_error` liest sie |
| `schreib_sicherung` | 1 | „Ganz oder gar nicht" für Dienste ohne eigenes Zurück: Dateien/Ordner vor dem Schreiben merken, bei Abbruch Byte für Byte zurücklegen |
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
| `kalender_bearbeiten` | 2 | Bearbeiten wie calcurse/Handy: Wiederholung (Typ/Intervall/Ende), Routine gezielt ändern, „nur dieser Tag", Spannen mit Zeit pro Tag, Einmal-Termine genau treffen |
| `kalender_konflikte` | 2 | Kollisionen, Fahrzeiten, Pausen-Grund, Abwesenheit, Alarme, Lese-Text und Abdruck für die KI (aus kalender.py ausgezogen, dort weitergereicht) |
| `kalender_kennung` | 2 | Termine/Routinen per fester Kennung (UID) lesen und ändern; `KalenderAbgelehnt` mit festen Codes (`CODES`), ein Schreibvorgang, Ablehnung schreibt nichts |
| `kalender_fehler` | 2 | Unterstes Kalender-Modul ohne Kalender-Abhängigkeit: `CODES`, `KalenderAbgelehnt`, Uhrzeit- und Reihenfolge-Prüfung (damit kalender/kalender_kennung/kalender_bearbeiten ohne Import-Kreis dieselbe Ablehnung werfen) |
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
| `rueckmeldungen` | 2 | Bewertungen der KI-Antworten (gut/schlecht + Kommentar): eine jsonl pro Rechner, nur anhängen, das letzte Ereignis je Antwort gilt; mit Anbieter, Modell, Werkzeugen und Skills der Antwort |
| `chat_suche` | 2 | Suche quer durch alle Gespräche und das alte Transkript (search_chats, read_chat): normalisierte Wörter, Rang nach Dichte und Aktualität |
| `ascii_lib` | 2 | ASCII-Bibliothek für Bild-Marker |
| `audio` | 2 | HTTP-Client für Whisper und TTS |
| `telemetry` | 2 | Telemetrie-Aggregat PC + Pi |
| `anwesenheit` | 2 | Ist Sasha da, schaut er hin? |
| `hub_ereignisse` | 2 | Ereignisse an Apps schicken, die sie abonniert haben (HTTP POST, im Hintergrund, Fehler nur geloggt) |
| `takt` | 2 | Wann ZENTRALE von sich aus spricht |
| `map` | 2 | Geo-Layer-System der Weltkarte |
| `ollama` | 2 | Anbindung an Ollama: Adresse, Modell, Kontext, Sampling, Erreichbarkeit, Warmup — einmal |
| `sandbox` | 2 | Code abgeschottet ausführen (bubblewrap): eigener Arbeitsordner, kein Netz, keine Dateien von Sasha, Zeit-/Speicher-/Ausgabe-Grenzen |
| `skills` | 2 | Skills der KI im Claude-Format (Ordner mit SKILL.md): Liste für den Prompt, laden samt Dateien, vorschlagen/ändern, an/aus, Erstbefüllung (eigene + Anthropic-Vorlagen) |
| `skill_format` | 2 | Das Skill-Format von Claude: SKILL.md mit YAML-Kopf lesen (auch fremde Felder) und schreiben, gültige Namen |
| `skill_umzug` | 2 | Umzug alter Skill-Dateien (`<name>.md`) ins Claude-Format, alte beiseite nach `_alt/`; „kurz“ → Hausregel |
| `ablage` | 2 | Die Ablage: Dokumente der KI, Sandbox-Dateien, Anhänge — Ordner pro Dokument, jede Fassung eine neue Datei, nie löschen |
| `anhang` | 2 | Anhänge im Chat: Sperrliste, Art erkennen (PDF/Word als Original, Text dazu), in die Ablage; Verweise für den Verlauf der KI auflösen |
| `ablage_text` | 2 | Der Text einer PDF- oder Word-Datei (Anhang, Ablage-Vorschau), gemerkt nach Inhalt |
| `textbloecke` | 2 | Kleines Markdown → Blöcke (Überschrift, Absatz, Liste, Tabelle, Code) und Stücke normal/fett — für PDF- und Word-Schreiber |
| `pdf_datei` | 2 | PDFs lesen (Text je Seite, Tabellen geraten, Formularfelder), zusammenfügen, Seiten herausnehmen — pypdf im begrenzten Kindprozess |
| `pdf_schreiben` | 2 | Neues PDF aus Markdown: A4, Grundschriften, Umbruch, Tabellen, Seitenzahlen — ohne Fremdbibliothek |
| `word_datei` | 2 | Word (.docx) lesen, aus Markdown anlegen, geänderte Kopie (ersetzen über Lauf-Grenzen, anhängen) — nur Standardbibliothek |
| `projekte` | 2 | Projekte: Rahmen für ein Thema mit Anweisungen und Wissensdateien im Gedächtnis, Block für den Prompt, Wissen lesen/hinzufügen (Sperrliste), archivieren |
| `modell_liste` | 2 | Welche Chat-Modelle ein Anbieter wirklich hat: vom Anbieter geholt, 24 h gecacht (pro Rechner unter `~/.cache`), Rückfall auf `providers.py` |
| `morgenblick_daten` | 2 | Was der Morgenblick weiß: Sammler je Quelle (Kalender, Mail, Erinnerungen, Gespräche, Listen, Projekte, Ablage), nur lesen, kein Netz; Form des Tages, drei Akte |
| `ehrlichkeit_erkennen` | 2 | Satzmuster in Antworten der KI: Erledigt-Behauptungen („hab ich eingetragen"), Zusagen („trag ich gleich ein"), Kalender-Kennungen — reines Python, auf wenige Falschtreffer gebaut |
| `zusagen` | 2 | Offene Zusagen der KI je Gespräch: eine Datei pro Rechner im Gesprächsordner, nur abhaken, nie löschen |
| `browser_sitzung` | 2 | Ein Browser ohne Fenster (Chromium über Playwright) in eigenem Thread: je Gespräch eine Sitzung, Seite als Text + nummerierte Elemente, klicken/tippen/zurück, Bild; nur erlaubte Hosts, nie das eigene Netz, keine Downloads, 10 min Leerlauf → zu |
| `morgenblick_bild` | 2 | Der Morgenblick als HTML: Gelände-SVG, Akte, Listen — deterministisch, alles escaped, Fraunces eingebettet |
| `ai` | 3 | Ollama-Weg, Tool-Liste und -Ausführung, Erlaubnis-Abfrage, Prompt-Bausteine |
| `ai_backends` | 3 | Wer denkt: lokal oder Cloud, Anbieter, Modell, Effort, Rundengrenze |
| `cloud` | 3 | Anthropic-Weg |
| `cloud_openai` | 3 | OpenAI-kompatibler Weg |
| `werkzeug_schleife` | 3 | Die eine Tool-Schleife aller Wege |
| `profil` | 3 | Prompt-Schienen klein und gross |
| `consolidation` | 3 | Nach dem Zug: Transkript (und Graph-Extraktion, wenn an) |
| `erlaubnis` | 3 | Das Erlaubnis-Gate: die Tür, durch die die Schleife fragt (Regeln und Fragen stehen im Werkzeug-Register); Geltungsbereiche einmal / dieses Gespräch / immer |
| `ki_antwort` | 3 | Fertige Antwort: Bild-Marker ziehen, Zug zum Merken vormerken |
| `ki_prompt` | 3 | Prompt-Bausteine für jeden Weg: Jetzt-Block, Imprint, Alarme, Denk-Heuristik, Schalter |
| `ki_einstellungen` | 3 | Chat-Einstellungen (Anbieter, Modell, Effort, Budget, Weg) lesen und mit Klartext-Prüfung setzen — für `/api/ai/einstellungen` |
| `ki_werkzeuge` | 3 | Was ein KI-Werkzeug tut: ausfuehren(name, args) → Kalender, Notizen, Netz, Mail, Messreihen |
| `werkzeug_register` | 3 | Ein Eintrag pro KI-Werkzeug: Schema, Beschreibung je Schiene, Erlaubnis-Regel + Frage; die Ausführer melden sich aus `ki_werkzeuge` an |
| `werkzeug_eintrag` | 3 | Wie ein Werkzeug-Eintrag aussieht (die Klasse `Werkzeug`), damit Einträge auch außerhalb des Registers stehen können |
| `werkzeug_pdf_word` | 3 | Einträge und Fragen der PDF-/Word-Werkzeuge (Skills pdf, word); hinten ans Register gehängt |
| `werkzeug_browser` | 3 | Einträge und Fragen der Browser-Werkzeuge; Erlaubnis je Host und Gespräch; hinten ans Register gehängt |
| `ki_browser` | 3 | Was die Browser-Werkzeuge tun: Seite als Text für die KI (Adresse als Beleg, Inhalt = Daten), Liste, Suchen, Bild in die Ablage |
| `ki_pdf_word` | 3 | Was die PDF-/Word-Werkzeuge tun: Quelle (Ablage oder Datei), lesen, neue Datei in die Ablage, nachlesen mit Beleg |
| `werkzeug_fragen` | 3 | Die Ja/Nein-Fragen an Sasha vor bestätigungspflichtigen Werkzeugen und die Regeln, die von den Argumenten abhängen |
| `ki_kalender` | 3 | Der Kalender, wie die KI ihn liest: Kennungen (`#r3f9c`), alle Felder, Warnungen frisch, Belege nach dem Schreiben |
| `ki_kalender_aendern` | 3 | Die schreibenden Kalender-Werkzeuge der KI: genau EIN Eintrag, nur genannte Felder, mit Beleg und Status |
| `ehrlichkeit` | 3 | Live-Prüfer eines Zugs: Tat gegen Wort und Kennungen (eine Korrekturrunde), Erledigt-Zeile aus dem Werkzeug-Protokoll, offene Zusagen in den Kontext-Umschlag; Einstellung `ehrlichkeit_pruefer` |
| `kern` | 3 | Der eine Einstieg: kern.chat(verlauf) wählt den Weg (lokal/Anthropic/OpenAI) und fährt ihn |
| `billig` | 3 | Ein Einmal-Aufruf beim billigen Modell des aktiven Anbieters (beide Dialekte, Kosten gebucht) — Graph-Extraktor, Gesprächstitel |
| `gespraech_titel` | 3 | Gesprächstitel: sofort aus den ersten Wörtern, nach der ersten Antwort vom billigen Modell |
| `morgenblick` | 3 | Morgenblick auf Abruf: sammeln, billiges Modell schreibt Sätze (JSON, Daten nie Anweisung; ohne Cloud feste Sätze), Seite in die Ablage; signierte Knöpfe → neues Gespräch |
| `mobil_kontext` | 3 | Kontextpaket fürs Handy (`data/mobil/kontext.json`): fester Cloud-System-Prompt + Anbieter/Modell/Effort, beim Abgleich abgelegt, nie Schlüssel |
| `main` | 4 | Event-Loop |
| `brain` | 4 | Input → neue Events |
| `actions` | 4 | Events → Nebenwirkungen |
| `clock` | 4 | Uhrzeit-Events |
| `sensors` | 4 | Sensor-Simulation |
| `hot_reload` | 4 | Hot Reload fürs Backend |
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
  `data/`, die 503-Antwort für „keine KI").
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
| `gespraeche` | Gesprächs-Liste, neu, öffnen, laden, umbenennen, archivieren; Bewertungen der Antworten |
| `stimme` | Sprechen und Zuhören |
| `mail` | Mail-Triage |
| `skills` | Skills der KI (Liste, an/aus) und das Gedächtnis für Sasha: Kernakten, Bereiche, Kernakte ändern |
| `ablage` | Ablage: Liste, Dokument lesen, archivieren; Anhänge annehmen |
| `projekte` | Projekte: Liste, anlegen, laden, Anweisungen ändern, Wissen hinzufügen, archivieren, Gespräch zuordnen |
| `morgenblick` | Morgenblick erstellen, Knopf einlösen (nur localhost, signiert) |
| `abgleich` | Zustand des Abgleichs über die Mitte (letzter Lauf, Fehler, Hinweise) |

## Türen

Eine Front wohnt im selben Repo, gehört aber nicht zum Kern. Was sie aus dem
Kern importieren darf, steht hier und **nur** hier. Apps (seit 2026-10-09 der
Sprach-Tutor) wohnen in eigenen Repos und importieren gar nichts von hier —
umgekehrt importiert hier niemand ein Modul namens `tutor` (der Test prüft
das für `core/`, `ui/`, `tui/`, `scripts/`).

| Bereich | Darf aus dem Kern | Warum |
|---|---|---|
| `tui/` | `theme`, `tone`, `pc_status` | Reine Helfer ohne Kern-Abhängigkeit. Alles andere holt die TUI per HTTP von den Routen (`ui/routen/`). |

Mit Apps redet der Hub nur über HTTP: starten (`scripts/open_tutor_room.py`
liest `app.toml`), Ereignisse schicken (`core/hub_ereignisse.py`).

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

Keine mehr — die letzte (`ui/app.py → tutor.debug`) ist am 2026-10-06
gelöst; seit 2026-10-09 ist der Tutor ganz ausgezogen. Die Tabelle bleibt für
den Test stehen.

| Weg | Wofür |
|---|---|

### Altlast: Riesen

Grenze: eine Funktion über 250 Zeilen, eine Datei über 1.500 Zeilen (in
`core/`, `ui/`, `tui/`). Die Zahl rechts ist **eingefroren**: der
Riese darf nicht wachsen, und wenn er schrumpft, wird die Zahl hier gesenkt.
Sasha, 05.10.2026: einfrieren, dann zerlegen (Punkt 3).

| Wo | Zeilen höchstens |
|---|---|
| `core/mail.py` | 1924 |

## Wenn der Test rot wird

- **„steht nicht im Bauplan"** — neues Modul in die Tabelle *Module*, in die
  niedrigste Schicht, deren Regel es erfüllt.
- **„Abhängigkeit nach OBEN"** — das Gebrauchte eine Schicht tiefer ziehen,
  oder es als Argument hereingeben.
- **„Neuer Import-Kreis"** — was beide brauchen, in ein eigenes, tieferes
  Modul ziehen. Nicht als Altlast eintragen.
- **„Tür umgangen"** — TUI: über eine Route in `ui/routen/` gehen. Zu einer
  App: nie per Import, nur per HTTP (`hub_ereignisse`, Starter).
- **„Riese gewachsen"** — das Neue in eine eigene Funktion oder Datei legen.
  In der TUI heißt das: eine eigene Ansicht in `tui/ansichten/`
  ([tui_bauplan.md](tui_bauplan.md)).
- **„Gut gemacht — kleiner geworden"** — die Zahl oben senken oder die Zeile
  streichen. Das ist der Sinn der Sache.
