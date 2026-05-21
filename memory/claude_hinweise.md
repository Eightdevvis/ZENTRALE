# Claude-spezifische Hinweise

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
  Das Mapping `TIME_REACHED → MORNING_WAKEUP` macht `brain.py`.
- `PRESENCE_DETECTED → TUTOR_START` hat **keinen** Tageszeit-Check;
  einzige Sperre ist `tutor_session.is_active()`.

### Ollama-Anbindung

- `ai.py` ist der primäre Ollama-Client für **Chat**. Daneben reden
  `embeddings.py` (Embed-Calls) und `consolidation.py` (Extraktor-LLM)
  direkt mit Ollama – aber alle drei gehen durch `net.py`, also fliegt
  kein Request unter dem Radar.
- `net.py` wrapt alle HTTP-Calls (außer Audio – `audio.py` loggt selbst,
  weil multipart-Upload Sonderbehandlung braucht) und loggt sie.
- **Memory-Injection im Chat-Modus:** `graph.context_for_query(user_query)`
  liefert das "Aktiviertes Wissen"-Stück in den System-Prompt
  (Spread-Aktivierung im Konzept-Graph). Im Tutor-Modus
  (`tools=...` an `chat_stream` gesetzt) wird **nichts** injiziert –
  der System-Prompt bleibt rein der Tutor-Prompt. Wer das ändern will:
  in `ai.py` die `if tools is None`-Bedingung anpassen.
- `memory.py` (Legacy LTM/STM) wird nur noch vom `save_memory`-Tool
  geschrieben – nicht mehr automatisch in den Prompt injiziert.
- Tool-Use: Ollama schickt `tool_calls` im **letzten** Streaming-Chunk
  (`done=true`). Nicht früher abbrechen, sonst gehen Tool-Calls verloren.
- Tool-Loop ist via `max_rounds = 5` gegen Endlosschleifen abgesichert.

### Tutor vs. Chat

- Beide nutzen dieselbe `ai.chat_stream()`-Infrastruktur.
- Unterschied: anderer System-Prompt + andere Tool-Liste
  (`tutor.TUTOR_TOOLS`) – die Standard-Tools sind im Tutor-Modus
  **deaktiviert**, nicht zusätzlich aktiv.
- `tutor_session.py` hat eine eigene History (getrennt von der
  Chat-History), damit sich Lernkontext und allgemeine Konversation
  nicht vermischen.
- `introduce_new(word, pinyin)` legt ein **neues** Wort an – die KI
  wählt das Wort selbst, es gibt keinen Pool aus dem geschöpft wird.

### Audio-Architektur

- **Kein Python-Audio auf dem Pi**: Aufnahme über Browser-MediaRecorder,
  Wiedergabe über Browser-`<audio>`. `core/audio.py` ist nur ein
  HTTP-Client zu den beiden Services auf Port 5050 (Whisper) und
  5051 (TTS).
- Drei separate Prozesse (ZENTRALE, Whisper, TTS) sind bewusst – siehe
  `audio_system.md`.
- TTS-Service ist **hardcoded** auf sherpa-onnx + `vits-zh-aishell3`.
  Kein Auto-Switch zu MeloTTS. Whisper-Service ist hardcoded auf
  `language="zh"`.

### Deployment-Eigenheiten

- Lokal: `venv/`. Auf dem Pi (durch `deploy_pi.sh`): `.venv/`. Zwei
  verschiedene Namen – wer auf dem Pi manuell arbeitet, muss
  `.venv/bin/python` nutzen.
- Der systemd-Service (`deploy/zentrale.service`) startet **nur**
  `core/main.py`. Whisper/TTS müssen manuell gestartet werden bzw.
  brauchen eigene Service-Units.
- **Auto-Update-Trigger:** der Pi pullt nicht bei jedem `git push`,
  sondern nur wenn sich `deploy/RELEASE` ändert. Wenn ein Deploy
  auslösen soll: Zahl in `deploy/RELEASE` hochziehen, committen,
  pushen. Code-only-Commits ohne RELEASE-Bump bleiben auf dem Pi
  unsichtbar bis zum nächsten Bump. Details: `deployment.md`.

## Workflow-Regeln (gelten für Claude beim Mitarbeiten)

### Code-Änderungen

- Bei jeder Code-Änderung: erklären **was** geändert wurde und **warum**.
- Neue Funktionen / Klassen / nicht-triviale Blöcke bekommen Kommentare,
  die das **WARUM** erklären.
- Lieber zu viele Kommentare als zu wenige – der User möchte den Code
  ohne externe Erklärung lesen können.

### Doku-Änderungen

- Jede strukturelle Änderung (Dateipfade, Modulnamen, neue Features) →
  passendes File im `memory/`-Ordner aktualisieren **und** den Index
  prüfen.
- README und CLAUDE.md sind bewusst kurz gehalten und verweisen auf den
  Memory-Index. Inhalte gehören in die Theme-Files, nicht ins README.
- Bei Umbenennungen / Löschungen: alle Stellen mitziehen, sonst tote
  Referenzen.

### Ungetesteter Code

- Niemals annehmen, dass neu geschriebener Code „funktioniert".
- Wenn möglich: direkt selbst per Bash testen.
- Sonst: explizit benennen, was noch getestet werden muss und wie.

## Memory-System (dieser Ordner)

- Modulare Wissensbasis – jedes Thema ein File.
- `INDEX.md` ist die Landing Page. Erst Index lesen, dann gezielt das
  passende Theme-File. So bleibt der Token-Verbrauch klein, wenn nur
  ein Teilaspekt gefragt ist.
- Neue Themen → neues File anlegen + im Index ergänzen.
