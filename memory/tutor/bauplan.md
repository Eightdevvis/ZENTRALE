# Bauplan eines Tutors — der Blueprint

**Wozu:** Sasha, 2026-09-17: ein einheitliches Dokument, das den Bauplan eines
Tutors festhält, damit künftige Tutoren (neue Sprachen, neue Personas, ein
zweiter Knoten) nach demselben Muster entstehen. Es hält **Struktur und
Artefakte**, nicht Verhalten — das steht in `tutor_system.md` (Mechanik,
Historie) und `naturalisierung.md` (Ausbau).

**Es driftet nicht, weil ein Test es erzwingt:** `tests/test_tutor_bauplan.py`
liest die Artefakt-Tabellen dieser Datei und prüft, dass jeder Pfad existiert,
jedes aktive Sprachpaket vollständig ist und jede Route hier auch in
`ui/app.py` steht (und umgekehrt). **Pflegeregel:** Struktur ändern → Bauplan im
selben Commit ändern, sonst wird der Test rot.

## 1. Die Struktur darüber

```
                    ┌────────────────────────────────────────────────────┐
                    │  INHALT  — pro Sprache/Land, tutor/langs/<code>/    │
                    │  Persona, Prompt, Kernwörter, Texte, Seeds, Avatar  │
                    └───────────────────────┬────────────────────────────┘
                                            │ Profil (langs.get)
 ┌──────────────────────────────────────────▼──────────────────────────────┐
 │  SKELETT — für jede Sprache gleich, tutor/*.py                          │
 │  session (Turn, Prompt-Bau)  tools (Vokabel, Spiel, Tool-Calls)         │
 │  skills (Situations-Auslöser)  memory (Persona-Gedächtnis)  srs (FSRS)  │
 │  staende (Spielstand = Sprache + Level)  config (Einstellungen)         │
 │  providers/cloud/openai_compat (Modell-Anbindung)  debug (Devtool-Bus)  │
 └───────────────┬──────────────────────────────────────────┬─────────────┘
                 │ einzige Naht                              │ HTTP (/api/tutor/*, /api/speak, /api/transcribe)
        core/tutor_port.py ──► ui/app.py                     │
        (Kern: Kill-Switch, Keys,                    ┌───────▼────────────────────────┐
         cloud/local-Wahl)                           │  FRONT — tutor/room.py (Zimmer) │
                                                     │  hört, spricht, zeigt; rechnet  │
                                                     │  nichts; importiert nichts aus  │
                                                     │  dem Projekt (nur stdlib+pygame)│
                                                     └────────────────────────────────┘
        services/whisper_service.py (STT)   services/tts_service.py (Stimme je Sprache)
```

Drei Regeln, die alles zusammenhalten:
1. **Ein Spielstand = eine Sprache + ein Level.** Die aktive Sprache kommt nur
   aus dem aktiven Stand (`staende.aktive_sprache`). Es gibt keine zweite Quelle.
2. **Skelett kennt keine Sprache.** Alles Sprachliche kommt aus dem Profil des
   Pakets; der Code fragt `langs.get(code)`.
3. **Das Zimmer ist dumm.** `room.py` importiert nichts aus dem Projekt, damit
   es auf dem Pi ohne Backend-Code läuft (Aussenposten-Paket).

## 2. Verzeichnisbaum mit Rolle je Artefakt

Diese Tabelle liest der Drift-Test: jeder Pfad muss existieren.

| Pfad | Rolle |
|---|---|
| `tutor/__init__.py` | Paket |
| `tutor/session.py` | Ein Turn: History, System-Prompt-Bau (Persona + Vokabel-Status + Kern-Hinweis + Gedächtnis + `{native}`), Streaming, Token-Guard gegen Stand-Wechsel |
| `tutor/tools.py` | Vokabel-Modell (spoken/listened → Status), Kernwörter, Spiel (Münzen/Kisten/Teile), Level, Glosse (Muttersprache), die Tool-Calls fürs Modell |
| `tutor/skills.py` | Situations-Auslöser (deterministisch), erster: `no_entiendo` |
| `tutor/memory.py` | Persona-Gedächtnis (Notizen je Stand), Verdichtung nach dem Turn mit Token-Prüfung |
| `tutor/srs.py` | Langzeit-Wiederholung (FSRS) je Stand |
| `tutor/staende.py` | Spielstände: `stand.json {name, lang, level}`, `stand_lock`, `pfad()` weigert fremde Sprache, `token()/pruefen()`, Migration |
| `tutor/config.py` | Einstellungen: provider, model, history_window, native — **kein** lang |
| `tutor/providers.py` | Provider-Registry (qwen, …), trains_on_data, Jurisdiktion |
| `tutor/cloud.py` | Anthropic-Pfad (Tool-Loop, Streaming) |
| `tutor/openai_compat.py` | OpenAI-kompatible Cloud (DashScope/qwen u.a.) |
| `tutor/debug.py` | Devtool-Ereignisbus (`emit`, SSE über `ui/app.py`) |
| `tutor/room.py` | Das Zimmer: pygame-Fenster, Mikro-Schleife (VAD → Whisper), Stimme, Persona-Figur, Esc-Menü, Hauptmenü (Stände), Drill als Spiel |
| `tutor/sprites.py` | Lädt die Figur (Rig + gemalte Teile) |
| `tutor/gelenke.py` | Drehpunkte/Posen der Figur |
| `tutor/schablone.py` | Mal-Schablone für neue Figuren |
| `tutor/langs/__init__.py` | Paket-Discovery: jeder Ordner mit `PROFILE` ist eine Sprache |
| `tutor/langs/base.py` | `profile()`, DEFAULTS, `load_text/load_json` |
| `tutor/langs/PROMPT_TEMPLATE.en.md` | Sprach-neutraler Master-Prompt (Roleplay-Rahmen), Vorlage jeder Übersetzung |
| `tutor/prompts/` | Kern-nahe Prompt-Bausteine (Tools, Nudge, Fallback) |
| `tutor/assets/figuren/` | Eine Figur je Ordner (`rig.json`, Teile-PNGs) |
| `tutor/assets/figuren/lucia/rig.json` | Bauplan der Figur Lucía |
| `tutor/assets/PermanentMarker-Regular.ttf` | Handschrift für die Karteikarte |
| `tutor/data/tutor_config.json.example` | Vorlage der Einstellungen (echte Datei gitignored) |
| `core/tutor_port.py` | Die einzige Naht zum Kern: Verfügbarkeit, Kill-Switch, Stände, Config, Devtool-Snapshot |
| `ui/app.py` | Flask-Routen `/api/tutor/*`, `/api/speak`, `/api/transcribe` |
| `services/whisper_service.py` | STT (faster-whisper, Sprache per Aufruf) |
| `services/tts_service.py` | Stimme: eine Engine je Sprache (`zh` sherpa, `es` Piper, `de` Piper) |
| `services/download_tts_model.py` | Modelle je Sprache holen |
| `scripts/open_tutor_room.py` | Zimmer starten (fährt lokale Audio-Dienste nur hoch, wenn das Backend lokal ist) |
| `scripts/tutor_devtools.py` | Terminal-Devtool: Prompt, Antworten, Tool-Calls, Vokabel, Skills live |
| `scripts/install_xfce_autostart.sh` | Pi-Kiosk (Modus `room` = Zimmer als Wandbild) |
| `deploy/aussenposten.txt` | Was der Pi bekommt (Positivliste, u.a. `tutor/room.py`) |
| `tests/test_tutor_staende.py` | Spielstände, Bluten, Level, Glosse |
| `tests/test_tutor_skills.py` | Skill-Auslöser |
| `tests/test_tutor_isolation.py` | Stände bluten nicht: Vokabeln, Gedächtnis, SRS, Spiel, Session-Guard, Löschen |
| `tests/test_tutor_room_flows.py` | Zimmer headless gegen Fake-Backend: Zwischenmenü, Hauptmenü-Stop, Schließen-Dialog, Stand-Wechsel, Stimme folgt Stand |
| `tests/test_tutor_bauplan.py` | Dieser Bauplan gegen den Code |
| `tutor/test_memory.py` | Prompt-Checks der Pakete (Zielsprache, Länge, Persona) |
| `memory/tutor/tutor_system.md` | Mechanik + Historie (Verhalten) |
| `memory/tutor/naturalisierung.md` | Ausbau-Referenz (Umgebung, Skills, geplante Tools) |

Laufzeit-Daten (gitignored, nicht im Test): `tutor/data/aktiver_stand`,
`tutor/data/staende/<id>/stand.json`, `tutor/data/staende/<id>/<lang>/{vocab,
game, progress, structures, fsrs, persona_mem, persona_hist, news, tv}.json`,
`tutor/data/tutor_config.json`, `tutor/data/vocab_images/`, `tutor/data/persona_music/`.

## 3. Routen (`ui/app.py`)

Der Drift-Test vergleicht diese Liste mit den `@app.route('/api/tutor…')` im
Code — in beide Richtungen.

| Route | Methode | Wozu |
|---|---|---|
| `/api/tutor/status` | GET | verfügbar? aktiv? Stimme da? |
| `/api/tutor/config` | GET, POST | Einstellungen (provider, model, native); `lang` wird abgelehnt |
| `/api/tutor/start` | POST | Session aktivieren + Begrüßung (`still: true` = nur aktivieren) |
| `/api/tutor/respond` | POST | ein User-Turn, streamt |
| `/api/tutor/nudge` | POST | Lage-Meldung (Stille / Ankunft), streamt |
| `/api/tutor/stop` | POST | Session beenden |
| `/api/tutor/room_state` | GET | Ausdruck, Laune, Gedanke, Musik, TV, Modus, Tempo, presence_age |
| `/api/tutor/assessment` | GET | Kernwörter + Lernstand fürs Drill |
| `/api/tutor/assessment/answer` | POST | Drill-Antwort verbuchen (Spiel-Ökonomie) |
| `/api/tutor/staende` | GET, POST | Stände listen / neu (`name, lang, level`) |
| `/api/tutor/staende/waehlen` | POST | Stand laden |
| `/api/tutor/staende/loeschen` | POST | Stand löschen |
| `/api/tutor/debug/stream` | GET | SSE für das Devtool |
| `/api/speak` | POST | Text → WAV (Sprache per Feld) |
| `/api/transcribe` | POST | WAV → Text (Sprache per Feld) |

## 4. Checkliste: eine neue Sprache

Der Drift-Test prüft für jedes Paket mit `enabled = True` die Pflichtdateien
und -felder. Ein Paket ist ein Ordner `tutor/langs/<code>/` — mehr Registrierung
gibt es nicht.

**Pflichtdateien**

| Datei | Inhalt |
|---|---|
| `__init__.py` | `PROFILE = profile(code, …)` mit den Pflichtfeldern unten |
| `prompt.md` | System-Prompt **in der Zielsprache**, Übersetzung von `PROMPT_TEMPLATE.en.md`; `{native}` bleibt Platzhalter |
| `vocab_hint.md` | ein Satz mit `{words}` (Zielsprache) |
| `expect.json` | Register-Leiter, heute `[]` |
| `core_vocab.json` | ≈76 Einträge `{word, reading, priority, category, gloss:{en, de}}`, Kategorien aus `room._CAT_DE` |
| `tool_texts.json` | Beschreibung der lebenden Tools in der Zielsprache (`introduce_new, express, get_structures, introduce_structure, increment_structure, watch_tv, turn_off_tv, play_music, stop_music, get_local_news, get_due_reviews, show_thought`) |
| `seeds/news.json`, `seeds/tv.json` | 8 leichte Themen, 8 Sendungen `{title, mood, level, note}` |

**Pflichtfelder im Profil:** `name, persona_name, country, enabled, reading,
stt_lang, tts_lang, provider, model, system_prompt, vocab_hint, core_vocab,
core_hint, situation` (10 Keys: `prefix suffix join open open_focus nudge_idle
nudge_focus_yes nudge_focus_no nudge_sound`), `status_labels` (5),
`vocab_labels` (`structs join sep`), `phrases` (die 28 Keys aus
`tools._DEFAULT_PHRASES`), `native_names`, `seeds`.

**Außerhalb des Pakets:** eine TTS-Engine für den Code in
`services/tts_service.py` (`_engines[<code>]`), Whisper kennt die Sprache
(Code = ISO), eine Figur (`avatar` im Profil, Default `lucia`), Zeile in
`memory/tutor/tutor_system.md`. Sonst nichts.

**Was NICHT mehr dazugehört (Legacy):** `assessment_prompt.md`, Tool-Texte für
`mark_known`, `get_confirmed_vocab`, `get_testing_vocab`, `increment_correct_use`.

## 5. Datenflüsse

```
Mikro (Pi) ─VAD─► Segment ─► /api/transcribe ─► Text ─► skills.pruefen (loggt)
   ─► session.respond_stream: note_spoken → Prompt (Profil + Status + Kern + Gedächtnis)
   ─► Modell (provider) ─► Text + Tool-Calls (express / show_thought / …)
   ─► Zimmer: Blase, Geste, Gedanke; /api/speak ─► WAV ─► Lautsprecher (Mikro gegated)
   ─► danach: memory.remember (Thread, Token-geprüft), srs, Graduierung

Spielstand ──► aktive Sprache ──► Profil (Prompt, Persona, Stimme) und Pfade
   staende/<id>/<lang>/…   ◄── tools / memory / srs (nur diese Sprache, stand_lock)
```

## 6. Pflege

- Neuer Code-Baustein, neue Route, neues Paket → hier eintragen, im selben Commit.
- `tutor_system.md` beschreibt **Verhalten**, dieser Bauplan **Struktur**; wer
  beides in einer Datei sucht, sucht falsch.
- Verhalten, das noch nicht gebaut ist, steht in `naturalisierung.md`, nie hier.
