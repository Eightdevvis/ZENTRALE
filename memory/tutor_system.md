# Mandarin-Tutor

## Position in der Architektur

Tutor ist ein **Addon** auf der Core-AI, nicht der Owner der
Voice-Pipeline. STT (Whisper) und TTS (sherpa-onnx / Piper) leben
zentral in `services/whisper_service.py` und `services/tts_service.py`
und sind sprachneutral nutzbar via `/api/transcribe` und `/api/speak`
(siehe `audio_system.md`). Der Tutor ruft diese Endpoints **als
Aufrufer** mit `lang='zh'` auf – er besitzt sie nicht.

Die alten Pfade `/api/tutor/transcribe` und `/api/tutor/speak` existieren
als dünne Aliase mit `lang='zh'`-Default, damit das Tutor-Frontend ohne
Änderung weiterläuft.

## Idee

Smalltalk auf Mandarin mit der KI – mit Spracheingabe (Whisper-STT)
und Sprachausgabe (sherpa-onnx-TTS, Modell `vits-zh-aishell3`).
Vokabeln kommen aus `vocab_mandarin.json`. Die KI nutzt 80 % bekannte
Vokabeln (zur Festigung) und 20 % neue (zum Erweitern).

## Vokabel-Daten-Modell

Jeder Eintrag in `vocab_mandarin.json` hat:

```json
{ "word": "你好", "pinyin": "nǐ hǎo", "correct_use": 0, "confirmed": false }
```

- `confirmed: false` → **Testing-Pool** (20 % der Konversation)
- `confirmed: true`  → **Confirmed-Pool** (80 % der Konversation)
- `correct_use` zählt korrekte Verwendungen. Bei
  `correct_use ≥ CONFIRM_THRESHOLD` (= 5, in `tutor.py`) flippt
  `confirmed` automatisch auf `true`.

## Aufbau

### `core/tutor.py`
- Definiert den System-Prompt für den Tutor-Modus.
- Definiert `TUTOR_TOOLS` – die Liste der Tools, die nur im Tutor-Modus
  verfügbar sind.

### `core/tutor_session.py`
- Verwaltet eine laufende Session: Zustand, History, Audio-Aufrufe.
- History ist **getrennt** von der Chat-History (sonst vermischen sich
  Lernkontext und allgemeine Konversation).

### Verhältnis zum Chat-Modus

Tutor und Chat nutzen dieselbe `ai.chat_stream()`-Infrastruktur.
Der Unterschied liegt nur in:

- **System-Prompt** (Tutor: „Du bist Mandarin-Sprachtutor für Sasha …")
- **Tool-Set** – im Tutor-Modus sind die Standard-Tools (`save_memory`,
  `read_file`, `list_files`) **deaktiviert** und durch die
  Tutor-spezifischen Vokabel-Tools ersetzt (siehe unten).

Das hält den Code DRY – kein doppelter Streaming-Mechanismus.

## Tutor-Tools

Aktiv nur während einer Tutor-Session (`TUTOR_TOOLS` in `core/tutor.py`).
Diese **ersetzen** die Standard-Tools (save_memory, read_file, list_files)
während des Tutor-Modus.

| Tool                      | Argumente              | Funktion                                                                        |
|---------------------------|------------------------|---------------------------------------------------------------------------------|
| `get_confirmed_vocab`     | –                      | Liefert alle Vokabeln mit `confirmed: true` als Prompt-formatierten String      |
| `get_testing_vocab`       | –                      | Liefert alle Vokabeln mit `confirmed: false` + `count`                          |
| `increment_correct_use`   | `word`                 | +1 auf `correct_use`. Bei ≥ 5 → auto-confirmed                                  |
| `introduce_new`           | `word`, `pinyin`       | **Neues** Wort in `vocab_mandarin.json` hinzufügen (nicht aus einem Pool wählen) |

Logik (laut System-Prompt): wenn `get_testing_vocab` `count < 10`
zurückmeldet → KI soll `introduce_new(word, pinyin)` aufrufen mit einem
selbstgewählten neuen Wort. Es gibt keinen vorgefertigten Pool.

Zusätzlich existiert in `tutor.py` die Hilfsfunktion `get_vocab_stats()`
(„total / confirmed / testing"). Sie ist **kein** AI-Tool, sondern für
Dashboard-Anzeige gedacht.

## Bedienung

- Start: Taste `T` (im Frontend) oder automatisch über Motion-Sensor
  (`PRESENCE_DETECTED` → `TUTOR_START`, siehe `event_system.md`).
  Es gibt **keine** Tageszeit-Bedingung – einzige Sperre ist eine
  bereits aktive Session.
- Aufnehmen: `Space` startet die Aufnahme, `Space` nochmal stoppt und
  schickt die Aufnahme an den Whisper-Service.
- KI antwortet – Antwort wird sofort durch den TTS-Service gesprochen
  (Default-Speed `0.9`, langsamer als normal für besseres Hörverstehen).
- Stop: `ESC` oder Stop-Button → `tutor_session.deactivate()`.

## Vokabel-Datei

`vocab_mandarin.json` – flache JSON-Liste mit den vier Feldern
`word`, `pinyin`, `correct_use`, `confirmed` (vollständiges Schema
siehe „Vokabel-Daten-Modell" oben). Die KI darf hier lesen und über
`introduce_new` / `increment_correct_use` auch schreiben.

## Audio-Pipeline

Siehe `audio_system.md` – das ist der ganze STT/TTS-Stack, der hier
mit dranhängt.
