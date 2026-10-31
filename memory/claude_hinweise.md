# Claude-spezifische Hinweise

**Stand 2026-09-18:** Was aus dem Code allein nicht hervorgeht und beim
Mitarbeiten nicht verletzt werden darf: Threads reden nur über `state.py`;
Events laufen Sensor → `main.py` → `brain.py`/`actions.py`; der Tutor ist
seit 2026-10-09 eine eigene App (Repo `language-tutor`): ZENTRALE importiert
nichts von ihm, startet ihn nur und schickt ihm Ereignisse per HTTP
(`core/apps.py`, `core/hub_ereignisse.py`, `memory/hub/hub_bauplan.md`);
Logik lebt front-agnostisch in `core/` hinter einem `/api/`-Kontrakt, Fronten
zeichnen nur; Struktur des Tutors steht im Repo `language-tutor` (`docs/bauplan.md`, Drift-Test),
Doku folgt `memory/doku_regeln.md`; jede Änderung wird erklärt, kommentiert (WARUM)
und getestet oder als ungetestet benannt. Git-Workflow und Feature-Tracker:
`CLAUDE.md`.

Dieses File ist für Claude (oder einen anderen LLM-Assistenten), der
am Code mitarbeitet. Hier stehen die Architektur-Entscheidungen und
Workflow-Regeln, die nicht aus dem Code allein hervorgehen.

## Das Strukturziel (Sasha, 2026-10-06)

> „ich will nich dass wir irgendwann an einen punkt kommen an dem der code
> unwartbar wird und alles um die ohren fliegt!" — „nie irgendwas hinbauen
> ohne plan wie die große architektur damit skalieren könnte."

Die Memory ist modular gebaut, der Code muss es genauso sein. ZENTRALE wächst
ständig; die Struktur muss mit dem Wachstum **besser** werden, nicht schlechter.

- **Jede Aufgabe hat genau einen Ort.** Taucht dieselbe Logik zum zweiten Mal
  auf, wird eine gemeinsame Stelle geschaffen, keine dritte Kopie.
- **Teile sind austauschbar statt verknotet.** Anbieter, Modell, lokal oder
  Cloud sind Werte, keine eigenen Code-Wege.
- **Vor jedem Feature: anschauen, planen, dann bauen.** Wo sitzt es in den
  Schichten? Wird dadurch eine Datei größer oder ein Knoten fester? Dann erst
  die Struktur richten.
- **Gehört es zur App oder zum rohen ZENTRALE?** Das rohe Paket (Hub,
  Store, Start-Adapter) ist das Gestell je Knoten und darf dort verschieden
  sein; Apps syncen ohne Gnade und sind überall dieselben — anders arbeiten
  heißt zweite Instanz. Regel: [hub/standort_und_app.md](hub/standort_und_app.md).
- **Leitplanken sind Tests, keine Hoffnung.** Schichten, Türen und Altlasten
  stehen in [system/bauplan_kern.md](system/bauplan_kern.md); der Test
  `tests/test_kern_bauplan.py` macht Verstöße rot. Altlasten dürfen nur
  schrumpfen.

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
  `hub_ereignisse.senden("anwesenheit")` (seit 2026-10-09): das Ereignis geht
  per HTTP an jede App, die es in ihrer `app.toml` abonniert hat — heute der
  Tutor. Ob er reagiert (nonverbal, nur in eine laufende Session, Cooldown),
  entscheidet er selbst (seine Einstellung `presence_react`). Der Hub
  importiert nie App-Code.
  Wann die Persona von sich aus spricht, entscheidet die App selbst (Repo
  `language-tutor`, `tutor/ansprache.py`, `docs/bauplan.md`), nicht dieser Pfad.
- Wann ZENTRALE selbst spricht (Termin-Erinnerung), entscheidet der Takt im
  Code, nie der Prompt (`memory/system/takt.md`). Die Uhrzeit steht bewusst nicht im
  Prompt.

### KI-Anbindung

- `ai.py` ist der Chat-Client für **Ollama**; `core/cloud.py` /
  `core/cloud_openai.py` sind Drop-ins für die Cloud, `ai_backends.pick("chat")`
  wählt (Stand: `cloud`). Tools werden **immer lokal** ausgeführt
  (`ki_werkzeuge.ausfuehren`, Liste im Werkzeug-Register
  `core/werkzeug_register.py`), egal wer denkt.
- `net.py` wrapt alle HTTP-Calls (außer Audio – `audio.py` loggt selbst,
  weil multipart-Upload Sonderbehandlung braucht) und loggt sie.
- **Gedächtnis:** Datei-Gedächtnis (`core/gedaechtnis.py`,
  `memory/ki/gedaechtnis_dateien.md`). Der Konzept-Graph ist seit
  2026-10-31 aus dem Code (`memory/archive/associative_graph/`). Das
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
  Tool-Calls): `memory/ki/anbieter_modelle.md` → „Fallen der aktuellen API".

### Tutor vs. Chat

- Der Tutor ist seit 2026-10-09 ausgezogen (eigenes Repo `language-tutor`,
  eigener Server, eigene Schleifen); `kern.fahren()`/`kern.fahrzeug()` sind
  mit ihm aus `core/kern.py` verschwunden. Wie er fährt, steht in dessen
  `docs/`; was in ZENTRALE bleibt: [tutor/INDEX.md](tutor/INDEX.md).

### Cloud→Lokal-Trennung (HARTE Invariante)

Die **Tutor-KI darf NICHT in die lokale AI greifen.** Lokale AI =
`ai.py`-Chat + Gedächtnis (`gedaechtnis.py`, ehemals Graph) + Consolidation.
Tutor-Interna (was die Tutor-KI sieht, Choke-Point `_ALLOWED`, ihre Tools):
Repo `language-tutor`, Datei `docs/tutor_system.md` → „Cloud→Lokal-Trennung".

ZENTRALE-seitig gilt:

- Der Tutor ist seit 2026-10-09 eigener Prozess; ZENTRALE importiert nichts
  von ihm und er nichts von ZENTRALE (Hub-Regel, `memory/hub/hub_bauplan.md`).
  Kontakt nur per HTTP-Ereignis (`core/hub_ereignisse.py`).
- Die **Gates für fremde Tool-Sets** bleiben: `ai.py` (`if tools is None`) und
  `core/cloud.py`/`core/cloud_openai.py` (`tutor_mode = tools is not None`) —
  bei gesetzten Tools keine Gedächtnis-Injektion, keine Consolidation
  (Transkript), kein Gate, keine Bild-Marker, kein Jetzt-Block. Heute übergibt kein
  Aufrufer in ZENTRALE `tools=`; wer das wieder tut, muss diese Gates kennen.

Umgekehrt gilt für den **Cloud-Kern**: lokal sieht alles von Cloud, Cloud
nichts von lokal (eigener Store; `memory/ki/anbieter_modelle.md` → Isolations-Invariante).

Wer hier etwas ändert (ein Tool-Set an einen Cloud-Pfad hängen, die Gates
lockern), weicht diese Trennung bewusst auf – im Zweifel sein lassen.

### Audio-Architektur

- `core/audio.py` ist nur ein HTTP-Client zu den beiden Services auf Port
  5050 (Whisper) und 5051 (TTS); beide sind **sprachneutral** (`lang`-Feld,
  Engine-Registry im TTS: zh/de/es). Nichts ist auf eine Sprache hartkodiert.
- Drei separate Prozesse (ZENTRALE, Whisper, TTS) sind bewusst – siehe
  `memory/ki/audio_system.md`.
- Das Zimmer (`tutor/room.py` im Repo language-tutor) nimmt auf dem Pi **selbst** auf
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

### Renderer-Prinzip: geteilte Logik, pro Front gerendert

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
und das **Maps-System** (seit 2026-10-22 eigene App `zentrale-karte`, Zeiger
`memory/maps/INDEX.md`; `/api/map` reicht der Hub weiter).
Wer ein Feature „nur schnell ins Template" baut, das später überall hin soll,
verletzt dieses Prinzip — Logik gehört nach `core/`, nicht in die Front.

## Workflow-Regeln (gelten für Claude beim Mitarbeiten)

### Code-Änderungen

- Bei jeder Code-Änderung: erklären **was** geändert wurde und **warum**.
- Neue Funktionen / Klassen / nicht-triviale Blöcke bekommen Kommentare,
  die das **WARUM** erklären.
- Lieber zu viele Kommentare als zu wenige – der User möchte den Code
  ohne externe Erklärung lesen können.
- Struktur des Kerns (neues Modul) → `memory/system/bauplan_kern.md` im
  selben Commit, sonst wird `tests/test_kern_bauplan.py` rot. Der Tutor hat
  seinen Bauplan seit 2026-10-09 im eigenen Repo `language-tutor`.

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
- **2026-07** — Cloud→Lokal-Trennung (Tutor-Sandbox), Renderer-Prinzip (damals „Kassetten-Prinzip") mit
  der „alle Fronten"-Regel.
- **2026-08** — Cloud-Kern, Datei-Gedächtnis, nur noch TUI.
- **2026-09-18** — auf `memory/doku_regeln.md` gebracht; veraltete Sätze (Audio
  hartkodiert auf zh, `memory.py`, RELEASE-Bump für den Pi, 15 Tools)
  entfernt.
- **2026-10-11** — Tutor-Interna der Cloud→Lokal-Trennung ins Repo
  `language-tutor` verschoben (`docs/tutor_system.md`); hier bleibt die
  ZENTRALE-Seite.
