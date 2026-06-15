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
monolith.html  (Browser pollt /api/state jede Sekunde)
   │
   ▼
 ai.py ── graph.py / consolidation.py / embeddings.py
   │       └─ context.py (Datei-Whitelist) / kalender.py / ascii_lib.py / web.py / news.py
   │
   ├──▶ Ollama (qwen3.5:9b Chat, bge-m3 Embeddings)
   └──▶ audio.py ──▶ Whisper (Port 5050) / TTS (Port 5051)
```

> Mandarin-Tutor: Reaktivierung läuft. `tutor.py` / `tutor_session.py` /
> `tutor_cloud.py` sind aktiv; Backend per `TUTOR_BACKEND` (local|cloud).
> Siehe `tutor_system.md`.

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
│   ├── graph.py             # KONZEPT-Graph Memory der KI (PRIMARY, data/ai_graph.json)
│   ├── graphs.py            # Lifestyle-GRAPHEN-Registry (Messreihen-Werkzeug, ≠ graph.py!)
│   ├── consolidation.py     # async Fakt-Extraktor in den Graphen
│   ├── embeddings.py        # bge-m3 via Ollama (Alias-Resolution, Entry-Points)
│   ├── context.py           # Whitelist-Dateizugriff (Cap 8000 Zeichen)
│   ├── kalender.py          # Kalender-Layer (Termine, Routinen, Konflikt-Alarm)
│   ├── lists.py             # Dynamische Listen-Registry (To-Do/Checklisten, Listen-Werkzeug)
│   ├── glossary.py          # Kuratiertes Mini-Glossar (front-agnostisch, `?`-Suche)
│   ├── kassette.py          # Welche "Kassette" läuft (monolith|laptop|tui) + KI-Gate
│   ├── mail.py              # Mail-Triage: IMAP rein, sortieren, zurückschreiben
│   ├── mail_rules.py        # Triage-Keymap (Sender → Ordner/Aktion)
│   ├── mail_secrets.py      # Verschlüsselter Zugangsdaten-Speicher (Mail-Konten)
│   ├── mail_oauth.py        # OAuth2/XOAUTH2 für Outlook.com-IMAP
│   ├── ascii_lib.py         # ASCII-Bibliothek für Bild-Marker [[bild: name]]
│   ├── web.py               # gegatete Internet-Pipe (web_suche / hole_url)
│   ├── news.py              # Persönliche Tagesschau: RSS-Fetch + KI-Briefing (lies_news)
│   ├── host_metrics.py      # PC-Host-Metriken (CPU/GPU/VRAM/Temp/RAM)
│   ├── telemetry.py         # Telemetrie-Aggregat (PC + Pi) fürs Dashboard
│   ├── audio.py             # HTTP-Client für Whisper + TTS
│   ├── tutor.py             # Tutor-Vokabel-Tools (Reaktivierung läuft, siehe tutor_system.md)
│   ├── tutor_session.py     # Tutor Session-State + Auflösung Sprache→Provider→Modell
│   ├── tutor_langs.py       # Sprach-Profile (zh live; ru/ar/es Skizzen)
│   ├── tutor_providers.py   # Provider-Registry (kind/base_url/key/trains_on_data-Flag)
│   ├── tutor_openai_compat.py # OpenAI-/v1-Backend (Qwen/DeepSeek/Mistral/OpenAI/Groq/…)
│   ├── tutor_cloud.py       # Anthropic-Backend (Claude, Sashas persönlicher Pfad)
│   └── map/                 # Geo-Layer-System (front-agnostisch, pure stdlib)
│       ├── basemap.py       # Basiskarte (Natural Earth, data/*.geojson)
│       ├── projection.py    # Geo→Pixel-Projektion
│       ├── render.py        # ASCII/Braille-Rasterung
│       └── layers/          # Overlay-Registry: trade.py, portwatch.py, density.py
├── ui/
│   ├── app.py               # Flask Backend + REST API (reiner Adapter auf core/)
│   ├── static/              # engine.js, viz.js, ascii.js, fonts/ (Monolith-Assets)
│   └── templates/
│       ├── monolith.html    # DAS Dashboard, KI sichtbar (Route / bei Kassette monolith)
│       └── laptop.html      # KI-freie Front (Kassette laptop/Fallback, gleiches Layout)
├── tui/                     # Terminal-Kassette (curses), redet NUR via HTTP mit ui/app.py
│   ├── zentrale_tui.py      # Die TUI (Sensoren, Karte, Kalender, Listen, Graphen, Mail)
│   └── select_kassette.py   # Kassetten-Auswahl beim Start
├── services/
│   ├── whisper_service.py   # STT (Port 5050)
│   ├── tts_service.py       # TTS (Port 5051)
│   └── download_tts_model.py
├── data/                    # Auto-generiert, nicht committen
│   ├── sleep_quality.json   # Geloggte Einträge
│   ├── ai_graph.json        # Konzept-Graph (primary memory)
│   ├── ai_ltm.json          # Legacy LTM (save_memory-Tool)
│   └── ai_stm.json          # Legacy STM (Session-Turns)
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

## Wie Bausteine andocken (Baustein-Konvention)

Die Feature-Module in `core/` (kalender, mail, news, web, lists, glossary,
graphs, map …) sind **autonom gekapselt**: keine zirkulären Importe, alle
Abhängigkeiten hierarchisch (Stern-Muster: `ai.py` → Features; `mail.py` →
`mail_*`; `map/layers` → Sub-Layer). Geteilter Zustand läuft ausschließlich
über `state.py`. Jeder Baustein dockt über genau **zwei Konventions-Stellen**
an – es gibt (bewusst) keine zentrale Plugin-Registry:

1. **KI-Tool:** Tool-Definition in `ai.py` → `TOOLS` eintragen **und** den
   Aufruf in `_dispatch_tool()` ergänzen (Schreib-Tools zusätzlich in
   `PERMISSION_REQUIRED_TOOLS`). Damit kann die KI den Baustein nutzen.
2. **Front:** eine REST-Route in `ui/app.py`, die 1:1 an die Baustein-Funktion
   delegiert. `ui/app.py` ist reiner Adapter (keine Business-Logik), die TUI
   spricht nur über HTTP, beide Browser-Fronts teilen dieselbe API.

Optionaler Bootstrap (Hintergrund-Fetcher wie `news`/`mail`) wird in `main.py`
kassetten-abhängig gestartet. Folge: ein neuer Baustein berührt 2–3 zentrale
Stellen – sauber genug für „plug-and-play per Konvention", aber keine
Selbst-Registrierung. Wer echtes Hot-Plug will, müsste `TOOLS`/`_dispatch_tool`
und das Event-Routing (`brain.py`/`actions.py`, heute `if-elif`) auf eine
Registry/Dispatch-Tabelle heben.

> **`graph.py` vs. `graphs.py`** – leicht zu verwechseln: `graph.py` ist der
> **Konzept-Graph** des KI-Memorys (eine globale Wissensstruktur, primary
> memory). `graphs.py` ist die **Lifestyle-Graphen-Registry** des Mess-/
> Tracking-Werkzeugs (viele benannte Messreihen, zur Laufzeit anlegbar).
> Verschiedene Systeme, nur namensähnlich.
