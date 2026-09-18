# Claude-spezifische Hinweise

**Stand 2026-09-18:** Was aus dem Code allein nicht hervorgeht und beim
Mitarbeiten nicht verletzt werden darf: Threads reden nur über `state.py`;
Events laufen Sensor → `main.py` → `brain.py`/`actions.py`; der Kern fasst
den Tutor nur über `core/tutor_port.py` an, die Tutor-KI sieht nie den Kern
(Sandbox `tutor.tools._ALLOWED`, 12 Tools, `ai.py`-Gate `if tools is None`);
Logik lebt front-agnostisch in `core/` hinter einem `/api/`-Kontrakt, Fronten
zeichnen nur; Struktur des Tutors gehört in `memory/tutor/bauplan.md` (Drift-Test),
Doku folgt `memory/doku_regeln.md`; jede Änderung wird erklärt, kommentiert (WARUM)
und getestet oder als ungetestet benannt. Git-Workflow und Feature-Tracker:
`CLAUDE.md`.

Dieses File ist für Claude (oder einen anderen LLM-Assistenten), der
am Code mitarbeitet. Hier stehen die Architektur-Entscheidungen und
Workflow-Regeln, die nicht aus dem Code allein hervorgehen.

## Was Claude unbedingt wissen muss

### Threading-Disziplin

- Zwei Threads, ein Prozess: Event-Loop (`core/main.py`) und Flask
  (`ui/app.py`).
- **Kommunikation NUR über `state.py`** (Lock-geschützt). Niemals
  direkter Datenaustausch zwischen den Threads – auch wenn es im
  konkreten Fall „klappen" würde.

### Event-Pipeline

- `main.py` macht den State (`state.set_sensor`, `state.push_event`,
  `state.push_log`). `actions.py` ist absichtlich klein und macht nur
  `print()` für ein paar Events – nicht „der Side-Effect-Layer".
- `clock.py` feuert `TIME_REACHED` (nicht `MORNING_WAKEUP` direkt).
  Das Mapping `TIME_REACHED → MORNING_WAKEUP` macht `brain.py`; am Ende hängt
  seit dem Ende des Morgen-Messengers (2026-09-14) nur noch ein `print`.
- `PRESENCE_DETECTED` löst **kein** `TUTOR_START` aus — diese Kante gibt es nicht
  (die Konstante hat weder Sender noch Handler). `brain.py` ruft stattdessen
  `tutor_port.presence_ping()`: eine **nonverbale** Reaktion in eine bereits
  laufende Session, die nie eine startet. Gates, in dieser Reihenfolge: Env
  `TUTOR_PRESENCE_REACT != "0"` (default AN) → `tutor_port.available()`
  (Kill-Switch + Backend erreichbar) → Session-interne Guards (Cooldown).
  Kein Tageszeit-Check. Der Kern fragt nie `tutor.*` direkt, immer den Port.
  Dass die Persona von sich aus spricht, entscheidet das **Zimmer** aus
  Mikro/PIR (`memory/tutor/tutor_system.md`), nicht dieser Pfad.
- Wann ZENTRALE selbst spricht (Termin-Erinnerung), entscheidet der Takt im
  Code, nie der Prompt (`memory/system/takt.md`). Die Uhrzeit steht bewusst nicht im
  Prompt.

### KI-Anbindung

- `ai.py` ist der Chat-Client für **Ollama**; `core/cloud.py` /
  `core/cloud_openai.py` sind Drop-ins für die Cloud, `ai_backends.pick("chat")`
  wählt (Stand: `cloud`). Tools werden **immer lokal** ausgeführt
  (`ai._dispatch_tool`), egal wer denkt.
- `net.py` wrapt alle HTTP-Calls (außer Audio – `audio.py` loggt selbst,
  weil multipart-Upload Sonderbehandlung braucht) und loggt sie.
- **Gedächtnis:** Datei-Gedächtnis (`core/gedaechtnis.py`,
  `memory/ki/gedaechtnis_dateien.md`). Der Konzept-Graph (`graph.py`) ist
  abgeschaltet (`GRAPH_KONTEXT`/`GRAPH_EXTRAKTION`), nicht gelöscht. Das
  alte Legacy-`memory.py` (LTM/STM) existiert nicht mehr.
- **Im Tutor-Modus** (`tools=...` an `chat_stream` gesetzt) wird **nichts**
  injiziert – der System-Prompt bleibt rein der Tutor-Prompt. Wer das ändern
  will: in `ai.py` die `if tools is None`-Bedingung anpassen.
- Prompt-Schienen: `profil/klein.py` (lokal, Kanon der Namen) und
  `profil/gross.py` (Cloud); `profil.kanonisch()` übersetzt Tool-Namen, das
  Gate prüft immer den kanonischen (`ai.braucht_erlaubnis()`).
- Tool-Use lokal: Ollama schickt `tool_calls` im **letzten** Streaming-Chunk
  (`done=true`). Nicht früher abbrechen, sonst gehen Tool-Calls verloren.
  Tool-Loop ist via `max_rounds = 5` gegen Endlosschleifen abgesichert.
- Cloud-API-Fallen (`temperature` → 400, `thinking: disabled` verliert
  Tool-Calls): `memory/ki/ki_system.md` → Modell-Parameter.

### Tutor vs. Chat

- Beide nutzen dieselbe `ai.chat_stream()`-Infrastruktur (lokal) bzw. ihre
  eigenen Cloud-Pfade (`tutor/openai_compat.py`, `tutor/cloud.py`).
- Unterschied: anderer System-Prompt + andere Tool-Liste
  (`tutor.tools.tools_for(lang)`) – die Standard-Tools sind im Tutor-Modus
  **deaktiviert**, nicht zusätzlich aktiv.
- `tutor/session.py` hat eine eigene History (getrennt von der
  Chat-History), damit sich Lernkontext und allgemeine Konversation
  nicht vermischen.
- Die aktive Sprache kommt **nur** aus dem aktiven Spielstand
  (`tutor/staende.py`); `tutor_config` kennt kein `lang`. Alle Datenpfade über
  `staende.pfad(root, lang)`, unter `stand_lock`.
- `introduce_new(word, reading="", lang=None)` legt ein **neues** Wort an – die KI
  wählt das Wort selbst, es gibt keinen Pool aus dem geschöpft wird. Der Parameter
  heißt `reading`, nicht `pinyin` (was `reading` bedeutet, sagt das
  Sprach-Profil); `pinyin` wird beim Lesen alter Einträge als Alias toleriert
  (`tools._read()`). Zählen tut nie die KI: `spoken`/`listened` kommen
  deterministisch aus Eingabe und Drill.

### Cloud→Lokal-Trennung (HARTE Invariante)

Die **Cloud-/Tutor-AI darf NICHT in die lokale AI greifen.** Lokale AI =
`ai.py`-Chat + Gedächtnis (`gedaechtnis.py`, ehemals Graph) + Consolidation.
Die Tutor-KI (auf einem Cloud-Provider) lebt in ihrem eigenen Environment.
Was sie sieht/anfassen kann, ist GENAU: ihr Tutor-Prompt, ihre eigene
Tutor-History, und die **12 Tutor-Tools** (`tutor.tools.tools_for(lang)`,
Liste in `memory/tutor/bauplan.md`). Die fassen an: die Dateien des aktiven
Spielstands (`tutor/data/staende/<id>/<lang>/…`) und **UI-State des
Persona-Zimmers** (`express`, `show_thought`, `watch_tv`, `play_music`) —
mehr nicht, nie die Core-KI. Durchgesetzt durch:

- **Choke-Point `tutor.tools.execute_tool`** – geschlossene Allowlist (`_ALLOWED`);
  jeder andere Tool-Name wird abgelehnt **und** ins stdout-Log geflaggt.
- **`ai.py`-Gates** (`if tools is None`): bei gesetzten Tools KEINE
  Gedächtnis-Injektion und KEINE Consolidation → Tutor-Gespräche landen NIE
  im lokalen Memory.
- **Cloud-Backends** (`tutor/openai_compat.py`, `tutor/cloud.py`) importieren
  `ai`/`graph`/`consolidation`/`context` NICHT und führen selbst keine Tools aus.

Umgekehrt gilt für den **Cloud-Kern**: lokal sieht alles von Cloud, Cloud
nichts von lokal (eigener Store; `memory/ki/ki_system.md` → Isolations-Invariante).

Wer hier etwas ändert (neuen Tutor-Tool, anderes Tool-Set an einen Cloud-Pfad
hängen), weicht diese Trennung bewusst auf – im Zweifel sein lassen.

### Audio-Architektur

- `core/audio.py` ist nur ein HTTP-Client zu den beiden Services auf Port
  5050 (Whisper) und 5051 (TTS); beide sind **sprachneutral** (`lang`-Feld,
  Engine-Registry im TTS: zh/de/es). Nichts ist auf eine Sprache hartkodiert.
- Drei separate Prozesse (ZENTRALE, Whisper, TTS) sind bewusst – siehe
  `memory/ki/audio_system.md`.
- Das Zimmer (`tutor/room.py`) nimmt auf dem Pi **selbst** auf
  (`sounddevice` + VAD) und spielt ab; es importiert nichts aus dem Projekt.
  Die Straße für weitere Agenten ist als Design offen
  (`memory/system/audio_strasse.md`). Der Browser-Weg (MediaRecorder) gehört zur
  aufgegebenen Browser-Front.

### Deployment-Eigenheiten

- Lokal: `venv/`. Auf dem Pi (durch `deploy_pi.sh`): `.venv/`. Zwei
  verschiedene Namen – wer auf dem Pi manuell arbeitet, muss
  `.venv/bin/python` nutzen.
- Der Pi ist **Aussenposten**: er bekommt nur die Positivliste
  `deploy/aussenposten.txt` und holt sich sein Paket per HTTP — kein git,
  kein `RELEASE`-Bump mehr. Wer etwas auf den Pi bringen will, trägt es in
  die Liste ein (`memory/betrieb/deployment.md`, `memory/system/topologie.md`). Der
  RELEASE-Weg gilt nur noch für einen `--voll`-Backend-Host.
- Auf dem PC: `zentrale-pc.service` zieht Whisper/TTS per `Wants=` mit
  (nie `After=` zurück — Ordering-Cycle). Genau **ein** Backend pro Rechner
  (`zentrale-pc` **oder** `zentrale-kern`).
- Ein Testlauf oder ein Worktree darf nie Sashas Theme umschalten
  (`memory/system/dashboard.md` → Riegel); `scripts/zentrale-systemeinheit` weigert
  sich aus einem Worktree.

### Kassetten-Prinzip: geteilte Logik, pro Front gerendert

Generelles Bau-Prinzip für **jedes** neue Feature:

- **Logik einmal, front-agnostisch** in `core/` (kein curses, kein HTML, kein
  SVG dort). Die Front-spezifischen Renderer bleiben **bewusst dumm**: sie
  holen fertige Daten über einen `/api/...`-Kontrakt und *zeichnen nur*.
- **Ein HTTP-Kontrakt für alle Fronten.** Eine neue Front = nur ein neuer
  Zeichner gegen denselben Endpoint, keine Logik-Duplikation. Das Zimmer
  (`tutor/room.py`) ist genau so gebaut.
- **Zuerst in der TUI bauen & testen.** Die TUI ist die schnellste,
  schlankeste Front (stdlib-only, kein Browser, `--selftest` ohne TTY). Was
  dort gegen `core/` + `/api/` läuft, ist die Logik bewiesen.
- **Backend bleibt zustandslos** (Polling-Modell): View-/UI-State lebt pro
  Front im Client, das Backend beantwortet nur Anfragen.
- ⚠ prüfen: die Regel **„Fertig heißt: in ALLEN Fronten (monolith, laptop
  UND tui)"** stammt aus 2026-07, als ein Feature browser-only blieb. Seit
  2026-08-15 wird nur noch an der TUI gearbeitet und die Browser-Fronten sind
  praktisch aufgegeben (`memory/system/INDEX.md`) — ob die Regel damit auf „TUI +
  Zimmer" schrumpft oder weiter gilt, hat Sasha nicht entschieden.

Gelebte Vorbilder: das **Graph-Werkzeug** (`core/graphs.py` + `/api/graphs`)
und das **Maps-System** (`memory/maps/maps_system.md`, `core/map/` + `/api/map`).
Wer ein Feature „nur schnell ins Template" baut, das später überall hin soll,
verletzt dieses Prinzip — Logik gehört nach `core/`, nicht in die Front.

## Workflow-Regeln (gelten für Claude beim Mitarbeiten)

### Code-Änderungen

- Bei jeder Code-Änderung: erklären **was** geändert wurde und **warum**.
- Neue Funktionen / Klassen / nicht-triviale Blöcke bekommen Kommentare,
  die das **WARUM** erklären.
- Lieber zu viele Kommentare als zu wenige – der User möchte den Code
  ohne externe Erklärung lesen können.
- Struktur des Tutors (neue Datei, Route, Sprachpaket) → `memory/tutor/bauplan.md`
  im selben Commit, sonst wird `tests/test_tutor_bauplan.py` rot.

### Doku-Änderungen

- Regeln in `memory/doku_regeln.md`: Stand zuerst, Warum bleibt, Historie unten, ein
  Fakt eine Datei, Widersprüche mit `⚠ prüfen:` markieren statt raten,
  Struktur in Bauplan + Test, Index nur Zeiger. Jede Datei, die man aus
  einem anderen Grund anfasst, wird dabei auf diese Regeln gebracht.
- Jede strukturelle Änderung (Dateipfade, Modulnamen, neue Features) →
  passendes File im `memory/`-Ordner aktualisieren **und** den Index des
  Bereichs prüfen.
- README und CLAUDE.md sind bewusst kurz gehalten und verweisen auf den
  Memory-Index. Inhalte gehören in die Theme-Files, nicht ins README.
- Bei Umbenennungen / Löschungen: alle Stellen mitziehen, sonst tote
  Referenzen.

### Ungetesteter Code

- Niemals annehmen, dass neu geschriebener Code „funktioniert".
- Wenn möglich: direkt selbst per Bash testen — aber nie so, dass ein
  Testlauf Sashas laufende Umgebung anfasst (Theme-Riegel, `tests/conftest.py`).
- Sonst: explizit benennen, was noch getestet werden muss und wie.

## Memory-System (dieser Ordner)

- Modulare Wissensbasis – jedes Thema ein File, sechs Bereiche mit eigenem
  Index.
- `INDEX.md` ist die Landing Page. Erst Index lesen, dann gezielt das
  passende Theme-File. So bleibt der Token-Verbrauch klein, wenn nur
  ein Teilaspekt gefragt ist.
- Neue Themen → neues File anlegen + im Bereichs-Index ergänzen.

## Historie

- **2026-05** — erste Fassung: Threads, Event-Pipeline, Ollama, Legacy-LTM.
- **2026-07** — Cloud→Lokal-Trennung (Tutor-Sandbox), Kassetten-Prinzip mit
  der „alle Fronten"-Regel.
- **2026-08** — Cloud-Kern, Datei-Gedächtnis, nur noch TUI.
- **2026-09-18** — auf `memory/doku_regeln.md` gebracht; veraltete Sätze (Audio
  hartkodiert auf zh, `memory.py`, RELEASE-Bump für den Pi, 15 Tools)
  entfernt.
