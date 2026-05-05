# Gesamt-Architektur

## Zwei Threads, ein Prozess

ZENTRALE läuft als ein einziger Python-Prozess mit zwei Threads:

- **Thread 1 – Event-Loop** (`core/main.py`): pollt Sensoren im
  1-Sekunden-Takt, hält den State (`state.set_sensor`,
  `state.push_event`, `state.push_log`) und ruft pro Event sowohl
  `brain.process_event` (Logik-Mapping) als auch
  `actions.handle_action` (print-Logging) auf.
- **Thread 2 – Flask-UI** (`ui/app.py`): bedient HTTP-Requests vom
  Browser-Dashboard.

**Wichtig:** Die Threads kommunizieren ausschließlich über `state.py`.
`state.py` ist ein thread-safer In-Memory-Store mit Lock. Direkter
Zugriff zwischen den Threads ist verboten – jeder gemeinsam genutzte
Wert geht durch `state.py`.

## Datenfluss von Sensor bis Browser

```
   Tastatur / GPIO            Wanduhr
         │                       │
     sensors.py              clock.py
         │                       │
         └────────┬──────────────┘
                  ▼
              main.py  (1 s polling)
                  │
   ┌──────────────┼──────────────┬──────────────┐
   ▼              ▼              ▼              ▼
state.py     brain.py      actions.py     event-queue
(setzt)   (mapping →      (print-      (re-queued
          neue Events)    Logging)     new events)
   │
   │          state.py ist die einzige Brücke
   │          zwischen Event-Loop und Flask-Thread
   ▼
 app.py  (Flask, liest state.py auf /api/state)
   │
   ▼
index.html  (Browser pollt /api/state jede Sekunde)
   │
   ┌────┴──────────────┐
   │                   │
 ai.py             tutor_session.py
   │                   │
 memory.py         audio.py
 context.py            │
   │              ┌────┴────┐
 Ollama       Whisper    TTS
(Mistral)   (Port 5050) (Port 5051)
```

`brain.process_event(e)` und `actions.handle_action(e)` werden vom
Event-Loop **parallel pro Event** aufgerufen, nicht hintereinander.
Was `brain` als neue Events zurückgibt, landet in derselben Queue
und wird in der nächsten Iteration genauso behandelt.

## Verzeichnisstruktur

```
ZENTRALE/
├── core/                    # Backend, Event-Loop, KI
│   ├── __init__.py          # macht core/ zum Python-Package
│   ├── main.py              # Event-Loop, setzt State, queued Events
│   ├── clock.py             # Uhrzeit-Events (feuert TIME_REACHED)
│   ├── events.py            # Event-Konstanten
│   ├── brain.py             # Input → neue Events (Logik-Mapping)
│   ├── actions.py           # Events → print()-Side-Effects (klein gehalten)
│   ├── sensors.py           # Tastatur-Sim für Button/Light/Motion
│   ├── state.py             # Shared state, thread-safe
│   ├── categories.py        # Data-Collection-Kategorien (Sleep, Food)
│   ├── ai.py                # Ollama-Client (Chat, Streaming, Tools)
│   ├── net.py               # HTTP-Wrapper mit Terminal-Logging
│   ├── memory.py            # KI-Memory (data/ai_memory.json)
│   ├── context.py           # Whitelist-Dateizugriff (Cap 8000 Zeichen)
│   ├── audio.py             # HTTP-Client für Whisper + TTS
│   ├── tutor.py             # Tutor-Tools + Tool-Dispatcher (TUTOR_TOOLS)
│   └── tutor_session.py     # Tutor Session-State + System-Prompt
├── ui/
│   ├── app.py               # Flask Backend + REST API
│   └── templates/
│       └── index.html       # Dashboard (Vanilla JS, SVG, kein CDN)
├── services/
│   ├── whisper_service.py   # STT (Port 5050)
│   ├── tts_service.py       # TTS (Port 5051)
│   └── download_tts_model.py
├── data/                    # Auto-generiert, nicht committen
│   ├── sleep_quality.json   # Geloggte Einträge
│   └── ai_memory.json       # KI-Memory
├── deploy/
│   ├── zentrale.service          # systemd-Template
│   ├── RELEASE                   # Trigger für Auto-Update auf dem Pi
│   └── zentrale-autopull.cron    # Crontab-Snippet (5-min-Tick)
├── scripts/
│   ├── deploy_pi.sh              # rsync + systemd Erst-Deploy
│   ├── pi_autopull.sh            # Cron-Worker: fetch → diff → pull → restart
│   └── test_audio.py             # manueller Audio-Smoke-Test
├── memory/                  # Dieser Doku-Ordner
├── notes.md                 # Freie Notizen, KI kann sie lesen
└── vocab_mandarin.json      # Mandarin-Vokabeln (Wort + Pinyin)
```

## Eckpfeiler-Entscheidungen

- **Lokal & offline**: keine Cloud-Abhängigkeit – Ollama/Whisper/TTS
  laufen alle auf demselben Rechner.
- **Polling-basiert**: das Frontend pollt `/api/state` jede Sekunde.
  Bewusst gewählt statt WebSockets, weil simpler und für
  ein-Browser-Setups völlig ausreichend.
- **`state.py` als einziger Synchronisationspunkt**: erspart komplizierte
  Locking-Logik in jedem Modul.
- **`net.py` wrapped jeden HTTP-Call**: alle ausgehenden Requests werden
  ins Terminal geloggt – Transparenz, kein „Black-Box-KI"-Gefühl.
- **State-Mutation passiert in `main.py`**, nicht in `actions.py`. `main.py`
  ruft `state.set_sensor()` / `state.push_event()` direkt auf; `actions.py`
  ist absichtlich klein gehalten (nur `print()`-Side-Effects pro Event).
