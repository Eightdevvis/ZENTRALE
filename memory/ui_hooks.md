# UI-Schnittstellen (Anker für Erweiterungen)

> # ⚠ DIESE DATEI IST VERALTET — NICHTS HIER STIMMT MEHR
>
> Sie beschreibt `ui/templates/index.html`. **Diese Datei existiert nicht mehr**
> (Monolith-Umbau, siehe `dashboard.md`). Nachgemessen am 2026-07-17 gegen das
> heutige `ui/templates/monolith.html`: **keiner** der unten genannten Hooks
> existiert — `#main-display`, `#panel-ai`, `#panel-chat`, `#panel-tutor`,
> `goToTutor()` → je **0 Treffer**.
>
> Konkret falsch, wenn du hier ansetzt:
> - Es gibt **kein** Panel-Tauschen in einer Mitte-Card. Der Tutor ist ein
>   **Kanalwechsel**: `Alt+T` → `toggleTutor()` → `body.tutor-mode` (roter Rahmen
>   um `#col-mid`), Eingaben gehen an `/api/tutor/respond`.
> - Es gibt **keinen** Motion-Sensor-Trigger, der ein Tutor-Panel aufmacht.
> - Die Space-Taste ist **nicht** für den Tutor belegt.
> - Nur `/api/tutor/speak` + `/api/tutor/transcribe` sind entfernt; **sieben**
>   andere `/api/tutor/*`-Routen sind live (`api_endpoints.md`).
>
> **Wo die Wahrheit steht:** `dashboard.md` (UI/Modi/Polling), `tastatur.md`
> (Tasten), `api_endpoints.md` (Routen), `tutor_system.md` (Tutorkanal).
>
> Der Rest unten bleibt nur als Historie stehen — **nicht** als Anleitung.
> Ob die Datei gelöscht oder gegen `monolith.html` neu geschrieben wird, ist
> offen (Sashas Entscheidung); bis dahin darf sie niemanden mehr in die Irre
> führen.

Alles was an `ui/templates/index.html` ein „Hook" war und von späterem
Code gegriffen wurde. Wenn Namen geändert werden – diese Datei mitziehen,
sonst raten Future-Claude/User wo sie ansetzen sollen.

## DOM-IDs (HTML-Anker)

| ID                  | Wozu                                                |
|---------------------|-----------------------------------------------------|
| `#view-main`        | Haupt-Grid (3 Spalten + Term-Footer)                |
| `#main-display`     | Mitte-Card; tauscht zwischen `#panel-ai/-chat/-tutor` |
| `#panel-ai`         | Default-Inhalt der Mitte (Orb + Mini-Log)           |
| `#ai-orb`           | Der Orb selbst – CSS-Class-Target für State-Toggle  |
| `#mini-log`         | Letzte 5 Konversationszeilen unter dem Orb          |
| `#panel-chat`       | Chat-View (per Taste C)                             |
| `#panel-tutor`      | Tutor-View (Taste T oder Motion-Sensor)             |
| `#panel-graph`      | Sleep-Quality-Chart (liegt in `.side-graph`)        |
| `#terminal`         | stdout-Footer (volle Breite)                        |
| `#chat-input`       | Chat-Texteingabe                                    |
| `#chat-mic-btn`     | Mic-Toggle (Aufnahme → Whisper), Alt+M              |
| `#chat-mute-hint`   | State-aware Footer-Hinweis für Alt+S (Mute); kein Button (Pi hat keine Maus) |
| `#chat-status`      | Ollama-Verfügbarkeitsanzeige im Chat-Mode           |

## JS-Hooks

| Funktion                | Was sie macht                                       |
|-------------------------|-----------------------------------------------------|
| `setOrbActive(bool)`    | Toggelt `.active` auf `#ai-orb` → schaltet zwischen idle (sanft) und active (volle Cyberpunk-Animation, Partikel an) |
| `fetchMiniLog()`        | Pollt `/api/chat/history`, rendert letzte 5 Einträge |
| `renderMiniLog(items)`  | Pure-Render aus Items-Array – kein Fetch            |
| `goToMain()`            | AI-Panel sichtbar machen, andere panels aus         |
| `goToChat()`            | Chat-Panel rein, AI-Panel raus, History laden       |
| `goToTutor()`           | Tutor-Panel rein, Tutor-Session starten             |
| `goToCategory()`        | Data-Collection-View aufrufen (Taste K)             |
| `toggleChatMute()`      | Stimme an/aus (Shortcut `Alt+S`), merkt sich Zustand in `localStorage` (`zentraleChatMuted`); stoppt beim Muten laufende Wiedergabe |
| `renderMuteHint()`      | Footer-Hinweis `#chat-mute-hint` an Mute-State angleichen (zeigt nächste Aktion) |
| `changeVolume(delta)`   | Lautstärke ± (klemmt 0..1), in `localStorage` (`zentraleChatVolume`) + live aufs laufende `<audio>`; Shortcut `Alt+S`+`↑`/`↓` |
| `showVolumeFeedback()`  | Zeigt kurz „Lautstärke X%" im `#chat-mute-hint`, nach 1.2s zurück auf den Mute-Hinweis |
| `enqueueSpeak(text)`    | Einen Satz in `speakQueue` legen + `drainSpeakQueue` anstossen |
| `drainSpeakQueue()`     | Queue seriell: `/api/speak` → `<audio>` → nächster Satz (kein Überlappen) |
| `stopSpeaking()`        | Queue leeren + laufendes `<audio>` pausieren (auch in `goToMain`) |
| `extractSentences(txt)` | Streaming-Text → `[fertigeSätze[], rest]`; Satzende = `.!?…\n` + Whitespace |

## CSS-Grid-Areas (swappable)

```
grid-template-areas:
  "sensors ai     graph"
  "term    term   term";
```

Layout-Swap (AI ↔ Graph) später per JS-Class:

```js
document.getElementById('view-main').classList.toggle('swapped');
```

und im CSS:

```css
#view-main.swapped {
  grid-template-areas:
    "sensors graph  ai"
    "term    term   term";
}
```

Sensoren-Spalte ist `auto`-breit (so schmal wie der längste Sensor-Text),
Graph-Spalte `clamp(220px, 22vw, 340px)`, AI-Mitte nimmt den Rest.

## Voice-Pipeline (Backend ready, Main-Mode-Frontend offen)

Backend-Endpoints (sprachneutral, Core):

- **STT**: `POST /api/transcribe` – multipart `audio` + `lang` (default `de`).
  Liefert `{"text": "...", "language": "...", "confidence": ...}`.
- **LLM**: `POST /api/chat` (deutsch, lokales Ollama-Modell, mit Memory) – SSE-Stream.
- **TTS**: `POST /api/speak` – JSON `{text, lang?, speed?, speaker?}`.
  `lang='de'` → Piper (Voice via `PIPER_DE_VOICE`), `lang='zh'` → sherpa-onnx
  (vits-zh-aishell3), andere → 503.

Die früheren `/api/tutor/*`-Aliase sind entfernt (Tutor pausiert) – Voice
läuft über die sprachneutralen `/api/transcribe` + `/api/speak` mit `lang`.

Was fehlt für Main-Mode-Voice (Frontend):

- **Trigger** im Main-Mode (Space-Taste belegt bisher den Tutor; eigene
  Voice-Geste wählen, z.B. lang-drücken Space oder PIR-Motion ohne
  Tutor-Session).
- **Frontend-Flow** in `panel-ai`: Mikrofon → `/api/transcribe?lang=de`
  → `/api/chat` (SSE) → `/api/speak?lang=de` → `<audio>`-Wiedergabe.
- **Orb-Lebenszyklus** im Main-Mode (das einzig schon Verdrahtete):
  ```js
  setOrbActive(true);
  // ... stream tokens, dann tts wiedergeben ...
  await audio.play(); await onended;
  setOrbActive(false);
  ```

Die Orb-Animation läuft also so lange wie zwischen den beiden Calls.
User-Wunsch: bei TTS-Wiedergabe weiter aktiv bleiben (also `false` erst
nach `audio.onended`, nicht direkt nach dem Stream-Ende).

## Stil-Anker

- Neon-Akzentfarbe: `#00ff88` (rgba-Varianten für Glow/Border)
- User-Farbe im Mini-Log: `#00aaff`
- AI-Farbe im Mini-Log: `#00ff88` (mit text-shadow)
- Card-Border: `rgba(0, 255, 136, 0.35)`
- Background-Card: `rgba(8, 14, 18, 0.65)` (durchscheinend dunkel)
- Scanlines: 1px alle 3px in `body::after`, **kein** `mix-blend-mode`
  (war auf Pi-VC4-GPU der Hauptverursacher der 3-FPS-Lags)
