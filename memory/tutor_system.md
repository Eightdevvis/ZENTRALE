# Sprach-Tutor (Persona-Portal)

> **Status (2026-07-16): SPRACH-FRAMEWORK — eine Sprache ist ein Ordner.**
> Der Tutor war nominell ein „Framework, auf das Sprachen draufgelegt werden" —
> auf Datenebene war das aber eine **Fassade**: `vocab_file`, `reading`, `script`,
> `stt_lang`, `tts_lang` standen im Profil, hatten aber **null Leser** (verifiziert
> per Grep). Die Mechanik war mandarin-fest verdrahtet. `/lang fr` ließ Jacqueline
> Französisch reden, aber französische Wörter mit einem **`pinyin`-Feld in Ling
> Lings Mandarin-Liste** schreiben — mit chinesischen Tool-Beschreibungen und
> China-News (live nachgestellt). Ursache: `tools.py` hatte **Modul-Konstanten**
> (`_VOCAB_FILE` & Co., beim Import einmal gesetzt), an denen ein Sprachwechsel
> zur Laufzeit gar nicht vorbeikonnte.
>
> - **Eine Sprache = ein Ordner** (`tutor/langs/<code>/`): Profil, Prompt in der
>   Zielsprache (`prompt.md`) + deutsche Referenz (`prompt.de.md`),
>   `tool_texts.json`, `expect.json` (Register-Leiter, war eine if-Kaskade in
>   Code), `vocab_hint.md`, `seeds/news.json` + `seeds/tv.json`. Die Registry
>   (`tutor/langs/__init__.py`) **findet die Pakete selbst** — eine Sprache
>   dazubauen heißt einen Ordner anlegen, nichts Zentrales anfassen.
> - **`tools.py` + `session.py` sind jetzt sprach-NEUTRAL.** Kein Mandarin, keine
>   Pinyin, keine China-Themen mehr im Mechanik-Code. Alles wird pro Aufruf über
>   `session.active_lang()` aufgelöst — **nicht** über die Config direkt: sonst
>   würde ein `/lang fr` mitten in einer zh-Session die nächsten Tool-Calls in die
>   fr-Dateien schreiben und beide Lernstände verderben. Die Session friert ihre
>   Sprache beim Start ein.
> - **Datenmodell generisch:** `{word, reading, correct_use, confirmed}`. Was
>   `reading` bedeutet, sagt das Profil (zh=Pinyin, ru=Betonung, ar=Translit,
>   fr/es=leer). Das Tool heißt `introduce_new(word, reading)`; der Dispatcher
>   nimmt ein halluziniertes `pinyin` weiterhin an, damit die Angabe nicht still
>   verloren geht.
> - **Statisches `TUTOR_TOOLS` → `tools_for(lang)`.** Struktur (Namen, Parameter,
>   Enums) ist sprach-neutral, die Beschriftung kommt aus dem Paket; fehlt sie,
>   greifen deutsche Defaults — genau wie beim Prompt (getunte Sprache bringt ihre
>   eigene, Skizze nimmt den Fallback).
> - **Lernstand pro Sprache:** `tutor/data/<lang>/` (`vocab.json`,
>   `structures.json`, `persona_mem.json`, `persona_hist.json`, Rotations-Cursor)
>   — gitignored, konsistent. Vorher war es gespalten: `vocab_mandarin.json`
>   getrackt, `structures_mandarin.json` ignoriert, obwohl beides derselbe
>   emergente Fortschritt ist. **Die Seeds** (Landes-Themen, TV-Katalog) sind
>   dagegen SPRACHE, liegen unter `tutor/langs/<lang>/seeds/` und bleiben getrackt.
> - **Kein Verhaltens-Drift:** alle fünf System-Prompts, der Vokabel-Hinweis und
>   die Register-Leiter sind nach dem Umbau **byte-identisch** zum alten Stand
>   (gegen `git show HEAD:tutor/langs.py` verifiziert). Die Texte wurden
>   programmatisch extrahiert, nicht abgetippt.
> - **Ehrliche Grenze:** vier Tools (`get_confirmed_vocab`, `get_testing_vocab`,
>   `increment_correct_use`, `introduce_new`) sind in `zh/tool_texts.json` noch
>   **deutsch** beschriftet — ein Rest aus der Zeit vor dem Tuning, der der
>   Zielsprachen-Regel widerspricht. Beim Umzug bewusst **wortgleich** übernommen
>   statt nebenbei übersetzt: eine Prompt-Änderung ohne Gegentest an echtem qwen
>   ist Glückssache. Offener Punkt im Tracker.
> - **Nebenbei gefixt:** war der Vokabel-Pool leer, hängte `session` trotzdem ein
>   nacktes „她在学：" ohne Wörter an den Prompt (`body.strip("：；")` war truthy).
>   Jetzt: keine Wörter → kein Block.
>
> **Status (2026-07-16): EIGENES PROJEKT im Ordner `tutor/` — am Stück rausziehbar.**
> Der Tutor ist ein **Python-Paket** (`tutor/`), kein Haufen `tutor_*`-Dateien in
> `core/` mehr. Alles, was ihm gehört, liegt drin: Code, Prompts, Vokabeln,
> Laufzeit-Daten (`tutor/data/`), sein eigener Test (`tutor/test_memory.py`).
>
> - **Die einzige Naht ist `core/tutor_port.py`.** Kein Core-/UI-Modul importiert
>   `tutor.*` direkt; der Port macht auch den `sys.path`-Bootstrap, damit kein
>   Aufrufer den Tutor-Pfad kennen muss. **Verifiziert mit physisch entferntem
>   Ordner:** ZENTRALE startet, `tutor_port.present()` → False, kein Crash.
> - **Warum ein Paket und nicht flach** (nachgemessen 2026-07-16, die erste
>   Fassung dieser Notiz war in einem Punkt falsch — siehe unten):
>   1. **Kurze Namen kollidieren STILL und reihenfolge-abhängig.** Flach lägen
>      `core/providers.py` und `tutor/providers.py` beide als `providers` auf
>      `sys.path` — zwei reguläre Module, gleicher Name. Es gewinnt schlicht der
>      erste `sys.path`-Eintrag. Nachgestellt: der Tutor verdeckte cores Registry,
>      und beim Umdrehen der Reihenfolge kippte es zurück. **Kein Fehler, nur die
>      falsche Tabelle** — das ist der gefährliche Fall. Gälte für jeden kurzen
>      Namen (`config`, `session`, `tools`, `memory`).
>   2. **Der Ordner `tutor/` und ein Modul `tutor` schließen sich flach aus** —
>      aber *deterministisch*, NICHT „mal so mal so": nach PEP 420 ist ein
>      Namespace-Package (Ordner ohne `__init__.py`) der **Fallback letzter
>      Instanz**. Python scannt den ganzen `sys.path` zu Ende; findet es irgendwo
>      ein reguläres Modul, gewinnt IMMER das — egal an welcher Position. Flach
>      hätte `import tutor` also stur `tutor/tutor.py` geliefert und
>      `from tutor import session` **immer** mit `ImportError` gebrochen. Kein
>      Race, aber ein harter Blocker: man müsste `tutor.py` umbenennen.
>   Als echtes Paket (`__init__.py`) ist der Ordner das Modul, und alle Namen
>   liegen im Paket-Namensraum (`tutor.providers` ≠ `providers`) → beide Probleme
>   sind strukturell weg, nicht nur umschifft.
> - **Namen** (alle Referenzen in dieser Datei sind nachgezogen):
>   `tutor/session.py` `tools.py` `langs/` `providers.py` `config.py`
>   `memory.py` `cloud.py` `openai_compat.py` `room.py` — importiert als
>   `from tutor import session` bzw. paket-intern relativ (`from . import langs`).
> - **KEINE Secrets in `tutor/`.** Die API-Keys sind beim Umzug nach
>   `data/ai_config.json` gewandert (der Kern besitzt den Key-Store);
>   `tutor/data/tutor_config.json` hält nur noch Sprache/Provider/Modell. Damit
>   kann ein vergessener `.gitignore`-Eintrag unter `tutor/` **nichts** leaken —
>   die Regel dafür (`tutor/data/**/*.json`) steht trotzdem, und `tutor/test_memory.py`
>   prüft die Secret-Freiheit als Regression. **Lernstand** (Vokabeln etc.) liegt
>   seit dem Framework-Umbau in `tutor/data/<lang>/` und ist ebenfalls gitignored.
> - **Migration:** `tutor/config.py` fällt auf `data/tutor_config.json` zurück,
>   `core/ai_config.py` ebenso → Knoten ohne den neuen Ordner laufen unverändert
>   weiter. Der Sync nimmt `tutor/` automatisch mit (Blacklist-Prinzip).
> - **Was tutor/ vom „basic core" braucht** (bewusst klein, Liste im Kopf von
>   `tutor/__init__.py`): `ai.chat_stream` / `ai.is_available`, optional
>   `ai_backends.status` (nur `tutor/memory.py`, lazy + try/except) und
>   `state.push_log`. Der Cloud-Pfad braucht **nichts** aus ZENTRALE.
> - **Aufgeräumt:** `scripts/test_persona_memory.py` war seit dem Notiz-Umbau
>   (2026-07-10) kaputt (`KeyError: 'nodes'` — testete den toten Graph-Store) →
>   ersetzt durch `tutor/test_memory.py` auf dem Notiz-Modell (grün). Der
>   verwaiste `vocab.py` vom Repo-Root (las die alte Vokabel-Datei per CWD-Pfad,
>   niemand importierte ihn) ist beim Framework-Umbau **gelöscht** worden.
>
> **Fronten sagen jetzt die Wahrheit (2026-07-17).** Der Port formulierte den
> Grund („Cloud ist per Kill-Switch gedrosselt" …) schon seit dem Infra-Schnitt —
> er kam nur nirgends an: `/api/tutor/status` baute sich **neben**
> `tutor_port.status()` ein eigenes Dict und warf `present` + `reason` weg
> (`status()` war damit tote Zeile, die niemand aufrief). Folge: `startTutor()`
> setzte `tutorActive = true` **vor** jeder Prüfung und `streamTutor` sah nie auf
> `resp.ok` → ohne Tutor/mit gedrosselter Cloud landete man im roten Rahmen fest,
> jedes Enter lief in einen 503 und wurde als **leere KI-Blase** geschluckt. Die
> TUI riet stattdessen („cloud gedrosselt? · /cloud on" — mit Fragezeichen, weil
> sie den Grund nicht hatte), auch wenn in Wahrheit Ollama tot oder `tutor/` weg war.
> Jetzt: Endpunkt reicht den Port-Status **1:1** durch; der Monolith fragt **erst**
> und wechselt den Kanal nur bei `available`, sonst steht der Grund im Minilog; bei
> 503 im Stream zeigt er den `detail` und verlässt den toten Kanal; die TUI schreibt
> `reason` unter den `x_x`-Smiley (umgebrochen per `_wrap`). **Regel:** der Grund wird
> an genau EINER Stelle formuliert (`tutor_port.unavailable_reason()`) — Fronten
> geben ihn wörtlich weiter, formulieren nie selbst.
>
> **Noch offen (Fronten, nicht Struktur):** `monolith.html` kapert über
> `tutorActive` den Chat-Sendepfad der Mitte statt ein eigenes Exhibit zu haben;
> die TUI hält TUTOR-State im Input-Dispatch/Fokus-Router/Layout (nur HTTP, bricht
> also nicht). Beides ist Aufwand beim endgültigen Ausbau, nicht beim Trennen.
>
> **Status (2026-07-16): INFRA-SCHNITT — der Tutor ist kein versteckter Core mehr.**
> Der Tutor war rückwärts ins System verhakt: `core/ai_backends.py` importierte
> `tutor.config`/`tutor.providers`, d.h. die **ZENTRALE-weiten Kill-Switches**
> (`cloud_enabled`/`local_enabled`, die `chat`/`news`/EXTERNAL gaten) wohnten in
> **`data/tutor_config.json`** — einer Tutor-Datei. Ohne die `tutor_*.py` startete
> ZENTRALE nicht. Der Pfeil zeigte falsch herum. Jetzt:
>
> - **`core/ai_config.py` (neu)** besitzt die Kill-Switches + den API-Key-Store
>   (`data/ai_config.json`). **Migrations-Fallback:** fehlt ein Wert dort, wird
>   `data/tutor_config.json` gelesen → PC/Pi/Laptop laufen unverändert weiter,
>   niemand muss einen Key umziehen. Geschrieben wird immer die neue Datei, die
>   Migration wächst also von selbst. Der Sync nimmt sie automatisch mit
>   (Blacklist-Prinzip, siehe `zentrale-push`).
> - **`core/providers.py` (neu)** ist die Cloud-Registry des **Kerns** (nur
>   Erreichbarkeit: „ist von hier eine Cloud-KI da?"). Der Tutor behält seine
>   **eigene**, größere `tutor/providers.py` — bewusst getrennt, weil er am Ende
>   andere Modelle nutzt als der Kern. Preis: base_url/key_env stehen an zwei
>   Stellen.
> - **`core/tutor_port.py` (neu) ist der EINZIGE Griff des Kerns am Tutor.**
>   `brain.py` und `ui/app.py` importieren **kein** `tutor_*` mehr. Der Import ist
>   lazy + geschützt → **ZENTRALE läuft jetzt ohne die Tutor-Dateien** (verifiziert
>   mit geblocktem Import: `ai_backends`/`consolidation` kommen hoch,
>   `tutor_port.present()` → False, kein Crash).
> - **Die Drossel ist Core-Policy, nicht Tutor-Sache.** `tutor.session.available()`
>   beantwortet nur noch **Kapazität** („ist mein Backend erreichbar?") und kennt
>   `cloud_enabled` **nicht mehr**. Ob der Tutor *darf*, entscheidet
>   `tutor_port.allowed()`. `/cloud off` schaltet Ling Ling also weiterhin stumm —
>   nur kommt die Entscheidung jetzt aus dem Kern (verifiziert bis in die
>   HTTP-Schicht: `POST /api/tutor/start` → 503 „Cloud ist per Kill-Switch
>   gedrosselt"). Neue Kontrakt-Funktion: `tutor.session.backend_kind()`.
> - **Toter Code weg:** `consolidation._cloud_graph_extractor` (~70 Zeilen) war ein
>   Rest der alten Graph-basierten Persona-Memory und wurde seit dem Notiz-Umbau
>   (2026-07-10) von **niemandem** mehr gerufen. Er war der einzige Grund, warum
>   `core/` je `tutor.providers`/`tutor.openai_compat` brauchte → gelöscht, samt der
>   toten `backend`/`provider`/`model`-Parameter von `extract_turn_into_graph`.
>
> **Ziel dahinter:** `tutor/` als eigener, rausziehbarer Ordner. **Schritt 2 ist
> noch am selben Tag erledigt** — siehe den Block ganz oben.
>
> **Status (2026-07-07): PERSONA-PORTAL + EIGENE MEMORY gebaut.** Der Tutor ist
> vom Lehrer zum **chilligen Mitbewohner** umgestellt: pro Sprache eine benannte
> **Persona** (Ling Ling/zh, Jacqueline/fr, …) mit eigenem Charakter, eigenem
> Land und eigenem AI-Anbieter. Sie ist ein **natürlicher, KURZER Gesprächs-
> partner** (kein Lehrer): redet **nur die Zielsprache**, hält sich knapp, kein
> Fake-Lob, **kein Fake-Mensch** (ehrlich KI, keine erfundene Vergangenheit/
> Nationalität). Kultur liegt ihr **beiläufig** nahe — NICHT erzwungen, kein
> Vortrag. Der zh-Prompt (Ling Ling) wurde dafür gegen echtes qwen getunt
> (Log: `memory/tutor_persona_tuning.md`). Sie **quatscht direkt los**
> (TUI-Taste `u` startet die Session sofort, kein „Stunde starten"-Enter mehr).
> Jede Persona hat ein **eigenes, GROBES Gedächtnis** (`tutor/data/<lang>/persona_mem.json`
> = kleine Notiz-Liste `facts`/`topics`, kein Graph, kein Wortprotokoll, Umbau
> 2026-07-10) → erinnert sich session-übergreifend *ungefähr* an dich. Roher
> Verlauf wird NICHT mehr persistiert (nur in-session). **Einzige echte Grenze:**
> dieses Persona-Gedächtnis und die lokale **Core-KI-Memory** (`ai_graph.json`)
> fassen sich **nie** an. Die Verdichtung läuft **kapazitätsbasiert** (Ollama daheim
> erreichbar → lokal, sonst Cloud). Details unten unter „Persona-Portal" und
> „Persona-Memory".
>
> **Noch offen:** Presence-Auto-Start (Sensor → Persona spricht dich an) ist
> weiter **bewusst nicht** verkabelt (`brain.py`, Sequencing). Voice pro Sprache
> und ein eigenes Tutor-Exhibit fehlen weiter.
>
> **Reaktivierungs-Stand (2026-06-30, gilt weiter):**
>
> Der Tutor wurde am 2026-05-14 weich deaktiviert. Grund war **nicht** der
> schlechte Auto-Trigger (das war nur der Anlass), sondern Sequencing:
> erst die Core-KI sauber aufstellen, ohne den KI-Layer mit dem Tutor-Addon
> zu vermischen. Jetzt wird er wieder angeschaltet.
>
> **Reaktivierungs-Stand:**
> - `ui/app.py`: `/api/tutor/{status,start,respond,stop}` **wieder aktiv**
>   (seit 2026-07-16 über `tutor_port`, nicht mehr `tutor.session` direkt).
>   Audio läuft über die generische
>   Voice-API (`/api/transcribe`, `/api/speak`) mit `lang='zh'` – keine
>   eigenen Tutor-Audio-Aliase mehr nötig.
> - Start ist **rein manuell**. **`Alt+T` ist LIVE** (Toggle, beide Richtungen):
>   schaltet im Dashboard den Tutorkanal an/aus (`toggleTutor` → `startTutor`/
>   `stopTutor`). Nacktes `T` ginge nicht – es landet im immer fokussierten
>   Chat-Input. Zusätzlich weiter per `/tutor` / `/tutorstop`. KEIN Presence-
>   Auto-Start in `brain.py` (bewusst, siehe Sequencing oben).
> - **Frontend (`monolith.html`) – Kanalwechsel gebaut, Exhibit noch offen:**
>   der sichtbare **Kanalwechsel** ist da: bei aktivem Tutor legt `body.tutor-mode`
>   einen **prägnanten roten Rahmen** um die ganze Mittelspalte (`#col-mid` =
>   Kern-Canvas + Konsole drunter, CSS-Var `--tutor`), Reiter „● TUTOR", roter
>   Prompt-Pfeil, Eingaben gehen an `/api/tutor/respond`. Das ist der „erstmal
>   nur umschalten"-Schritt. **Noch offen:** ein eigenes Tutor-**Exhibit** im
>   AI-Canvas (neben `gesicht`/`graph`, wie `graph-panel`); aktuell läuft der
>   Tutor text-first im Minilog. Drumherum nicht anfassen.
> - **Backend-Wahl per `TUTOR_BACKEND`:** `cloud` → Claude (Anthropic),
>   `local` (Default) → Ollama. Siehe „Cloud-Backend" unten.
> - `tutor/tools.py`, `tutor/session.py`, `tutor/cloud.py`,
>   die Vokabeln und die Audio-Modelle sind aktiv/intakt.
> - **Fronten (»alle Kassetten«-Regel):** der Tutorkanal ist bisher **nur im
>   Browser** (`monolith.html`) gebaut. In die **TUI** ist davon erst der
>   `/cloud`-Kill-Switch + die EXTERNAL-Backend-Box gewandert – ein Tutor-Start/
>   -Kanal in der TUI fehlt noch komplett (offener Punkt).
>
> Der Rest dieses Files beschreibt das Design; Abweichungen sind oben vermerkt.

## Persona-Portal: eine Figur pro Sprache

Der Tutor ist ein **Persona-Portal**: jede Sprache = eine benannte **Persona**
mit eigenem Charakter, eigenem Land und eigenem AI-Anbieter (Provider/Modell
entkoppelt). **Eine Sprache = ein Ordner** `tutor/langs/<code>/` mit allem, was
sie ausmacht (Profil, Prompt, Tool-Beschriftung, Register-Leiter, Seeds); die
Registry `tutor/langs/__init__.py` findet die Pakete selbst.
**LIVE: `zh` → Ling Ling (China, qwen).** Skizzen (`enabled=False`): `fr`
Jacqueline, `ru` Ludmila, `ar` Amira, `es` Lucía.

**Charakter — gegen echtes qwen getunt** (Log: `memory/tutor_persona_tuning.md`):
- **Kein Lehrer, kein Kurs.** Natürlicher, KURZER Gesprächspartner — 1-2 Sätze,
  kein Monolog, kein Fake-Lob, kein Abfragen/Benoten, nicht dreifach erklären.
- **Nur die Zielsprache.** Antwortet auf Mandarin; nur wenn Sasha ausdrücklich
  nach einer Wort-Bedeutung fragt, EIN kurzer deutscher Halbsatz, dann zurück.
- **Kein Fake-Mensch:** ehrlich eine KI, keine erfundene Vergangenheit/Herkunft,
  hat im Land „nie gelebt". Auf „bist du Chinesin?" → „ich bin eine KI".
- **Kultur beiläufig, NICHT erzwungen:** sie kennt Essen/Alltag, streut das nur
  gelegentlich knapp ein — kein Reiseführer, kein Geschichts-/Politik-Vortrag.
- **Wie es zuverlässig wird (WICHTIG):** der zh-Prompt ist **auf Chinesisch**
  verfasst (hält qwen in der Sprache), mit **Few-Shot-Beispielen + harten
  Verboten**; dazu **`TUTOR_TEMPERATURE` (0.4) + `TUTOR_MAX_TOKENS` (200)** im
  Cloud-Pfad (`tutor.openai_compat`/`tutor.cloud`). Prompt-Wording ALLEIN war
  Glückssache — qwen driftete sonst in deutsche Monologe.
- **Skizzen** nutzen die schlanke generische `_build_prompt` (deutsch); beim
  Aktivieren einer Sprache: eigenen Prompt IN DER ZIELSPRACHE hand-tunen wie zh.

**Vokabel:** der Persona-Prompt sagt keine Tool-Calls mehr an. Der bekannte
Wortschatz wird als **zielsprachiger Kontext** (`vocab_hint`, `{words}`) in
`tutor.session` ans Prompt-Ende gehängt (ein deutscher Block kippt qwen ins
Deutsche). Tools (`increment_correct_use`/`introduce_new`) bleiben verfügbar;
verlässliche Auto-Progression wäre ein Hintergrund-Follow-up.

**Direkt-Start (kein Enter):** TUI-Taste `u` (`zentrale_tui.tutor_open`) holt den
Status und lässt die Persona **sofort** loslegen, wenn das Backend da ist und
keine Session läuft. Der Browser (`monolith.html`) startet über `Alt+T` schon
immer direkt. `/api/tutor/config` liefert jetzt `persona_name`/`country` fürs UI.

## Persona-Zimmer (natives pygame-Fenster)

Der Tutor ist keine Chat-Box, sondern eine Person — sie **wohnt** in einem
gezeichneten Wohnzimmer: **`tutor/room.py`** (pygame, wie
`scripts/map_window.py`). **TUI-Taste `u` öffnet DIREKT das Zimmer** (kein Umweg
über Panel/`/room`); `zentrale_tui.tutor_window()` startet es **detached**
(Single-Instance über `TUTOR['proc']`, Fehler nach `/tmp/zentrale-tutor-room.log`)
und reicht `BASE_URL` mit (findet auch vom Laptop via `zentrale-remote` ans PC-
Backend). **Ohne `DISPLAY`** (headless/ssh) fällt `u` auf das Text-Panel zurück.
Das **Text-Panel** (Slash-Commands `/lang /provider /cloud …`) gibt's weiter per
**`/tutor`**; `/room` aus dem Panel geht auch noch. Standalone: `venv/bin/python
tutor/room.py [--url … --speaker N --speed X --mute]`.

- **Szene:** Wand + Dielenboden, Nachtfenster mit Mond, Stehlampe mit Glühen,
  Couch, Teppich, Pflanze — warme Palette (bewusst anders als die Karte).
- **Persona-Sprite** (`Persona`-Klasse, aus pygame-Primitiven, kein Sprite-Sheet):
  läuft rum, **sitzt sich auf die Couch**, blinzelt; kleine Verhaltens-Maschine
  (idle → schlendern → sitzen → aufstehen). Redet sie (SSE läuft), nickt sie
  zugewandt mit Mund-Animation.
- **Stimme:** nach jeder (kurzen) Antwort holt das Fenster die WAV vom Backend-
  TTS (`POST /api/speak`, `lang` aus der Config → zh = sherpa-onnx **MeloTTS
  `vits-melo-tts-zh_en`, 44.1 kHz** — klar; das alte `vits-zh-aishell3` war nur
  8 kHz/telefonig und bleibt nur Fallback, `tts_service._try_load_sherpa_zh`
  bevorzugt MeloTTS) und spielt sie über `pygame.mixer` — **der Mund bewegt sich,
  solange Audio läuft**. `play_wav` initialisiert den Mixer auf die Sample-Rate der
  Datei (pygame resampelt nicht → sonst falsche Tonhöhe). Tempo: `--speed`
  (`TUTOR_TTS_SPEED`). `--speaker` (`TUTOR_TTS_SPEAKER`) greift nur bei Multi-
  Sprecher-Modellen; MeloTTS hat 1 Sprecher (sid wird sonst auf 0 geklemmt).
  **Alt+M** schaltet stumm. Kein TTS → das Fenster zeigt
  ehrlich „🔇 keine Stimme (tts-service aus?)" (aus `status['tts']`, alle 4 s
  nachgepollt) statt still zu scheitern.
  - **Damit die Stimme wirklich kommt, muss laufen:** (1) der **`tts_service`**
    (Port 5051, `venv/bin/python services/tts_service.py`) — er hard-importiert
    `soundfile`, die zh-Engine braucht `sherpa-onnx` (beide in requirements.txt,
    auf frischen Maschinen ggf. `pip install -r requirements.txt`); Modell via
    `services/download_tts_model.py zh`. (2) `/api/speak` war über
    `kassette.ki_aus()` gegated → **gelockert**: blockt nur noch, wenn AUCH der
    Tutor kein Backend hat (`kassette.ki_aus() and not tutor_port.available()`),
    sonst spricht die Cloud-Persona trotz „lokale KI aus". Backend nach dem
    Update **neu starten**.
- **Warum das Rezept stabil bleibt gilt auch hier:** kurze Mandarin-Antworten
  passen in Blase UND in einen TTS-Call; nichts am Prompt/Temperatur geändert.
- **Wovon es lebt:** rein Renderer + Client. Session/Sprache/Persona/Memory liegen
  im Backend; das Fenster spricht `/api/tutor/{status,config,start,respond}` +
  `/api/speak` und streamt die Antwort als SSE in eine **Sprechblase** (CJK-Font
  `notosanscjksc`). Beim Öffnen begrüßt die Persona von selbst (wenn Backend da +
  keine Session). Eingabe: tippen + Enter (auch IME/Unicode), Esc schließt.
  Backend weg → `zzz…`.
- **Wand-tauglich:** natives Fenster, stapelt sich übers Wand-TUI (Deployment
  startet die Kiosk-TUI `-maximized`, damit solche Fenster oben liegen). Der
  Browser bekommt KEIN Zimmer (kann keinen nativen Prozess starten; text-first
  bleibt).
- **Teilweise gebaut (2026-07-09), REVIEW:** Presence gibt jetzt eine **nonverbale**
  Reaktion — `brain.py PRESENCE_DETECTED` → `tutor.session.presence_ping()` (schaut
  hoch, Mimik happy, +Batterie), aber **NUR** hinter Env-Flag
  `TUTOR_PRESENCE_REACT=1` (default aus) UND nur bei bereits **laufender** Session.
  Es STARTET keine Session und macht **keinen** verbalen Auto-Gruß (das bleibt
  bewusst aus — genau der schlechte Auto-Trigger). Details:
  `memory/tutor_roleplay_features.md` §5.
- **Offen/Skizze:** verbaler Presence-Gruß (erst nach Core-KI-Sequencing /
  Sashas Freigabe), Auto-Öffnen des Fensters, reichere Sprites/Möbel, eigene
  Fallback-Aktivitäten (schlafen, malen), auf die sie beim Chillen zurückfällt.

### Eigenleben: Ausdruck + Feedback-Loop (nicht nur ein Chatfenster)

- **Gesagtes verhallt:** die Sprechblase bleibt nicht ewig hängen — sie steht
  kurz voll (`BUBBLE_LINGER`) und blendet aus (`BUBBLE_FADE`). Unten eine
  translucente **Verlaufs-Leiste** (Sasha kühl, Persona warm), die lange
  Antworten umbricht und mit **↑/↓** scrollbar ist — so geht nichts verloren.
- **Bewegung ist ein KI-Tool, kein Random:** die Persona läuft/pact/sitzt nur,
  wenn die KI sich selbst ausdrückt. Neues **`express`-Tool** (`tutor/tools.py`,
  Enum: sit/stand/pace/wander/come_closer + wave/nod/look/stretch) → schreibt in
  `tutor.session._expr` (Haltung + Gesten-Zähler). Das Fenster pollt
  **`GET /api/tutor/room_state`** (~4 Hz) und animiert; `Persona.set_stance`/
  `play_gesture`. Der zh-Prompt hat eine kurze chinesische Zeile dazu (gegen
  echtes qwen verifiziert: Rede bleibt kurz, sie ruft `express` z.B. beim Nudge).
- **Feedback-Loop (gedeckelt, winzige Kosten):** das Fenster merkt Stille. Nach
  `NUDGE_AFTER_S` (25 s) EIN Cloud-Anstoß **`POST /api/tutor/nudge`** → die KI
  reagiert von selbst (schaut/winkt/„在吗？"); der Nudge-Text wird NICHT in der
  History gespeichert. Danach **chillt** sie (client-seitig, kein weiterer Call);
  erst nach `CHILL_RECHECK_S` (15 min) ein neuer Versuch. Eingabe von Sasha setzt
  die Stille-Uhr zurück.

## Persona-Memory: der Mitbewohner erinnert sich an dich

Jede Persona hat ein **eigenes Gedächtnis**, getrennt von Sashas privatem
Core-Graphen — **Modul `tutor/memory.py`**:
- **GROB, nicht exakt (Umbau 2026-07-10):** ein Mitbewohner merkt sich *ungefähr*
  ein paar wichtige Dinge, nicht wann genau was gesagt wurde. Darum ist der Store
  **kein** Konzept-Graph mehr (der von der Core-KI kopierte war eh nie gebaut
  worden) und **kein** Wortprotokoll, sondern eine kleine, gedeckelte **Notiz-
  Liste**: `tutor/data/persona_mem_<lang>.json` = `{"facts": [kurze Sätze], "topics":
  [Stichworte]}` (je max 12, auf Chinesisch, keine Zeitstempel). Enthält nur
  Wissen **über Sasha** aus euren Chats — **keine** erfundene Persona-Biografie.
- **Kein persistenter roher Verlauf mehr:** früher lud `activate()` `persona_hist_
  <lang>.json` Turn-für-Turn — das füllte sich mit „你在吗？"-Nudge-Fillern und
  zog die Persona beim Öffnen in Echo-Schleifen. Jetzt: `_history` ist **reiner
  In-Session-Puffer** (Kohärenz), wird NICHT über Sessions gespeichert. Kontinuität
  kommt allein aus den Grob-Notizen.
- **Loop (`tutor.session.respond_stream`):** vor der Antwort wird der Notiz-Kontext
  („关于 Sasha（只是大概印象…）") an den System-Prompt gehängt; nach einem echten
  Turn destilliert `remember()` im Hintergrund neue Fakten/Themen in die Notizen
  (leichter LLM-Pass, merged + deckelt). Der Öffnungs-/Nudge-Turn wird **nicht**
  gemerkt (ambient, kein Gespräch).
- **Verdichtungs-Backend kapazitätsbasiert** (`persona_memory.remember` via
  `ai_backends.status()`): **Ollama erreichbar** → **lokaler** Pass; sonst →
  **Cloud** (der Anbieter, der eh redet, z.B. qwen); **kein Backend** →
  übersprungen. `_distill()` macht einen tool-losen Ein-Schuss-Call, `_parse_notes()`
  zieht das JSON raus.

- **Was hier NICHT stimmt (ehrliche Grenze — kein Marketing):** Läuft die
  Persona über die Cloud, liegt ihr **Gesprächs- und Memory-Inhalt beim Cloud-
  Anbieter** — unvermeidbar, das Reden läuft ja dort, und der Kontext-Block wird
  jede Session wieder mitgeschickt (wächst sogar an). Die lokale Verdichtung ist
  **kein** Privacy-Schutz fürs Tutor-Material (das war beim Reden längst beim
  Anbieter); sie ist nur billiger + hält alles offline, **wenn** Ollama da ist.
  Die **einzige** harte Garantie: die **Core-KI-Memory** (`ai_graph.json`, das
  was du dem lokalen Chat offline erzählst) wird der Tutor-Persona **nie**
  gefüttert — die Stores fassen sich nicht an, die Sandbox aus `tutor/tools.py`
  bleibt intakt. Persona-Turns werden zudem **nicht** in Sashas gemeinsamen
  Kalender gespiegelt.

Tests: die Notiz-Funktionen (`_load_notes`/`_save_notes`/`context`) sind ohne
Backend prüfbar; der Destillations-Pfad (`remember`/`_distill`) braucht ein
Backend (lokal Ollama oder Cloud-Key). `tutor/test_memory.py` ist auf
den alten Graph-Store gemünzt — beim nächsten Anfassen auf das Notiz-Modell
nachziehen.

## Framework: Sprachen + Provider (austauschbar)

Der Tutor ist ein **Sprach-Framework**: Sprachen werden als **Personas**
draufgelegt, der **Anbieter/das Modell ist davon entkoppelt**. Beides wird zur
Laufzeit aufgelöst (`tutor.session._resolve`): Sprache → Profil → Provider →
Modell.

**Module:**
- `tutor/langs/` – **ein Ordner pro Sprache**: System-Prompt,
  Vokabel-Datei, `reading` (zh=Pinyin, ru=Betonung, ar=Translit, es=—),
  `script` (ar=RTL), STT/TTS-Lang, Default-Provider+Modell.
  **LIVE: `zh` (Chinesisch).** Skizzen (enabled=False, stückweise reinziehen):
  `ru`, `ar`, `es`.
- `tutor/providers.py` – **Provider-Registry**. Pro Eintrag: `kind`
  (`ollama` | `anthropic` | `openai_compat`), `base_url`, `key_env`,
  `default_model`, **`trains_on_data`**, `jurisdiction`, `enabled`.
  **LIVE:** `local` (Ollama), `claude` (Sashas Pfad), `qwen` (Verteil-Default).
  Skizzen: `openai`, `mistral`, `groq`, `deepseek`, `gemini`.
- `tutor/openai_compat.py` – **Drop-in für `ai.chat_stream()`**, bedient
  JEDEN OpenAI-`/v1`-kompatiblen Provider (Qwen/DeepSeek/Mistral/OpenAI/Groq/
  Gemini) durch Tausch von base_url+Key+Modell. `TUTOR_TOOLS` sind schon
  OpenAI-Schema → ohne Übersetzung. Streaming-Tool-Loop.
- `tutor/cloud.py` – **Anthropic-SDK-Pfad** (Claude), Sashas persönliche
  Verifikation. Übersetzt `TUTOR_TOOLS` ins Anthropic-Format.

**Steuerung – lokale Config-Datei (kein `export` nötig):**
- `data/tutor_config.json` (`tutor/config.py`) hält `lang` / `provider` /
  `model` / `history_window` **und die API-Keys**. Modell durchprobieren =
  `provider`/`model` dort ändern, neu starten. Vorlage:
  `tutor/data/tutor_config.json.example`.
- **Sicherheit:** `data/*.json` ist in `.gitignore` → die echte Config (mit
  Keys) wandert NIE ins Repo (verifiziert via `git check-ignore`). Keys aus der
  Config werden beim Import in `os.environ` injiziert, damit die SDKs sie finden.
- **Precedence:** Env-Var > Config-Datei > Profil-Default. D.h. `TUTOR_LANG` /
  `TUTOR_PROVIDER` / `TUTOR_MODEL` / `TUTOR_HISTORY_WINDOW` im Terminal
  übersteuern die Config für ein schnelles Einzel-Experiment.
- `history_window` (Default 30) = wieviele letzte Turns gesendet werden
  (Kosten-Hebel: zustandslose API sendet History sonst komplett neu).
- **Caching:** noch NICHT explizit gesetzt. OpenAI-kompatible Provider mit
  Auto-Cache (OpenAI/DeepSeek) profitieren schon vom cache-freundlichen Aufbau
  (stabiler System-Prompt zuerst, History nur angehängt); Qwen-Context-Cache
  noch zu verifizieren. → offener Punkt.

**Default pro Sprache (verifiziert, billig × gut × Privacy):**
zh → Qwen (Singapur, no-train) · es → Mistral (EU) · ru → Qwen · ar →
gpt-4o-mini (ALLaM/Groq als Option, Policy noch prüfen).

**Privacy-Flag (HART):** Provider mit `trains_on_data=True` (deepseek, gemini-
free) **oder unverifiziert** (`None`, z.B. groq) werden NICHT verboten, aber bei
Session-Start **laut geflaggt**: `tutor.session.activate()` setzt eine Warnung
(Log + `privacy_notice()`), die `/api/tutor/status` als `privacy_warning`
liefert → UI muss sie deutlich anzeigen.

**Offline-Prinzip:** Default bleibt `local` (Ollama, offline). Cloud-Provider
sind bewusster Opt-in. **Dependencies:** `openai` ist seit 2026-06-26 im venv +
in `requirements.txt` – der **qwen-Cloud-Pfad** (openai_compat) lief vorher gar
nicht, `import openai` knallte. `anthropic` ist **inzwischen ebenfalls im venv
installiert** (für den Claude-Verifikations-Pfad `tutor/cloud.py`), bleibt
aber **policy-mäßig Opt-in**: in `requirements.txt` bewusst auskommentiert, also
kein Pflicht-Dep für die Verteilung (`venv/bin/pip install anthropic` bei Bedarf).
**Cloud-Live steht:** `DASHSCOPE_API_KEY` ist in `data/tutor_config.json`
(`keys`-Block) **gesetzt** (Secret, gitignored) → der qwen-Pfad ist startklar
(`provider=qwen`, `model=qwen-plus`, `lang=zh`). Provider/Modell/Prompt stehen;
**offen bleibt nur ein echter End-to-End-Call** zur Auth-Verifikation – der ist
noch nicht protokolliert.

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
Vokabeln kommen aus `tutor/data/zh/vocab.json`. Die KI nutzt 80 % bekannte
Vokabeln (zur Festigung) und 20 % neue (zum Erweitern).

## Vokabel-Daten-Modell

Jeder Eintrag in `tutor/data/<lang>/vocab.json` hat:

```json
{ "word": "你好", "reading": "nǐ hǎo", "correct_use": 0, "confirmed": false }
```

- `confirmed: false` → **Testing-Pool** (20 % der Konversation)
- `confirmed: true`  → **Confirmed-Pool** (80 % der Konversation)
- `correct_use` zählt korrekte Verwendungen. Bei
  `correct_use ≥ CONFIRM_THRESHOLD` (= 5, in `tutor.py`) flippt
  `confirmed` automatisch auf `true`.

## Aufbau

### `tutor/tools.py`
- Definiert den System-Prompt für den Tutor-Modus.
- Definiert `TUTOR_TOOLS` – die Liste der Tools, die nur im Tutor-Modus
  verfügbar sind.

### `tutor/session.py`
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

Aktiv nur während einer Tutor-Session (`TUTOR_TOOLS` in `tutor/tools.py`).
Diese **ersetzen** die Standard-Tools (save_memory, read_file, list_files)
während des Tutor-Modus.

| Tool                      | Argumente              | Funktion                                                                        |
|---------------------------|------------------------|---------------------------------------------------------------------------------|
| `get_confirmed_vocab`     | –                      | Liefert alle Vokabeln mit `confirmed: true` als Prompt-formatierten String      |
| `get_testing_vocab`       | –                      | Liefert alle Vokabeln mit `confirmed: false` + `count`                          |
| `increment_correct_use`   | `word`                 | +1 auf `correct_use`. Bei ≥ 5 → auto-confirmed                                  |
| `introduce_new`           | `word`, `reading`      | **Neues** Wort in `tutor/data/<lang>/vocab.json` hinzufügen (nicht aus einem Pool wählen) |
| `express`                 | `action` (Enum)        | Haltung/Geste/Mimik im Zimmer setzen (sit/stand/pace/…/wave/nod/happy/tired…)    |
| `get_structures`          | –                      | Aktuelle Satzmuster/Strukturen im Lernen (Feinmodell, `structures_mandarin.json`)|
| `introduce_structure`     | `pattern`, `note?`     | Neues Satzmuster/„neue Sagweise" einführen                                       |
| `increment_structure`     | `pattern`              | +1 auf ein Muster; ab 3× → „掌握"                                                |
| `show_thought`            | `word`, `meaning?`     | Vokabel-Gedanke: Wort + Übersetzung (+ Bild aus `tutor/data/vocab_images/`) im Zimmer  |
| `get_local_news`          | –                      | Ein leichtes Landes-Thema (persona-isolierter Seed, rotierend; NIE `core/news.py`)|
| `play_music` / `stop_music`| `mood?`               | Musik nach Stimmung aus `tutor/data/persona_music/<mood>/` (Fenster spielt); Content-Lücke|
| `watch_tv` / `turn_off_tv`| `mood?`                | TV an + level-gerechter Titel (`_TV_SEED`); Video-Playback deferred              |

Logik (laut System-Prompt): wenn `get_testing_vocab` `count < 10`
zurückmeldet → KI soll `introduce_new(word, reading)` aufrufen mit einem
selbstgewählten neuen Wort. Es gibt keinen vorgefertigten Pool.

Die Tools ab `express` sind die **Roleplay-Erweiterung** (2026-07-09, Feature 1–8,
Log: `memory/tutor_roleplay_features.md`). ALLE fassen nur tutor-isolierte Daten +
UI-State an (Sandbox-Choke-Point `_ALLOWED` in `tutor.py`) — nie die Core-KI.

Zusätzlich existiert in `tutor.py` die Hilfsfunktion `get_vocab_stats()`
(„total / confirmed / testing"). Sie ist **kein** AI-Tool, sondern für
Dashboard-Anzeige gedacht.

## Bedienung – Konsolen-Commands

Gesteuert wird über die **Dashboard-Konsole** (das immer fokussierte Chat-
Eingabefeld in `monolith.html`). Kein Hotkey-Konflikt, passt zum „Terminal"-
Charakter. Befehle (Handler in der Chat-IIFE, `handleConsoleCommand`):

| Command | Wirkung |
|---|---|
| `/tutor` | Tutor starten; Begrüßung streamt in den Minilog. Danach gehen Eingaben an `/api/tutor/respond` statt an den Chat. |
| `/tutorstop` | Tutor beenden (`/api/tutor/stop`). |
| `/provider <name>` | Anbieter **live** umschalten (qwen, deepseek, mistral, …). |
| `/model <id>` | Modell live umschalten (z.B. qwen-turbo). |
| `/lang <code>` | Sprache umschalten (zh, ru, ar, es). |
| `/models` | Aktuelle Wahl + wählbare Provider mit Jurisdiktion + Privacy-Flag. |
| `/cloud on\|off` | **Cloud-Kill-Switch** (Datenschutz/Kosten). Aus → kein Cloud-Backend, EXTERNAL zeigt „gedrosselt". Auch in der TUI. |

Backend dahinter: `POST/GET /api/tutor/config` (Live-Override in
`tutor.config`, optional `persist`) für Sprache/Provider/Modell;
`POST /api/ai/backends {cloud_enabled}` für die Cloud-Drossel. Schaltet ohne
Neustart. Privacy-Warnung (`trains_on_data`) erscheint beim Start im Minilog
und über `/api/tutor/status` (`privacy_warning`).

**Verfügbarkeit (kapazitätsbasiert, nicht kassetten-hart):** Der Tutor wird
nicht per `kassette.ki_aus()` gegated, sondern per **`tutor_port.available()`**
(seit 2026-07-16 — Fronten fragen IMMER den Port, nie `tutor.session` direkt).
Der Port prüft zwei Dinge getrennt:

1. **Darf er?** — `tutor_port.allowed()` fragt die ZENTRALE-Drossel
   (`ai_backends.cloud_enabled()` bzw. `local_enabled()`, je nach
   `tutor.session.backend_kind()`). Das ist **Core-Policy**.
2. **Kann er?** — `tutor.session.available()` prüft nur noch die **Kapazität**
   (lokaler Provider → Ollama da; Cloud → Key gesetzt + Host erreichbar, 5s
   gecacht). Der Tutor kennt die Drossel bewusst NICHT.

Damit nutzbar auf laptop/tui, sobald cloud (oder via SSH lokal) erreichbar ist.
Fehlt das Backend, ist Cloud gedrosselt oder der Tutor gar nicht installiert:
`/api/tutor/{start,respond}` → 503 mit ehrlichem Grund aus
`tutor_port.unavailable_reason()` (z.B. „Cloud ist per Kill-Switch gedrosselt").

**Noch offen / Skizze:** das **zentrale Tutor-Exhibit** (eigene Ansicht im
AI-Canvas statt nur Minilog) und **Voice** für den Tutor (Mic→`/api/transcribe`
+ TTS→`/api/speak`, beides mit der Profil-`lang`, nicht dem `de`-Default) sind
noch nicht gebaut – aktuell läuft der Tutor **text-first** im Minilog. Der
generische Voice-Stack (siehe „Audio-Pipeline") existiert, muss aber pro
Sprache verkabelt werden.

## Vokabel-Datei

`tutor/data/<lang>/vocab.json` – flache JSON-Liste mit den vier Feldern
`word`, `reading`, `correct_use`, `confirmed` (vollständiges Schema
siehe „Vokabel-Daten-Modell" oben). Die KI darf hier lesen und über
`introduce_new` / `increment_correct_use` auch schreiben.

## Audio-Pipeline

Siehe `audio_system.md` – das ist der ganze STT/TTS-Stack, der hier
mit dranhängt.
