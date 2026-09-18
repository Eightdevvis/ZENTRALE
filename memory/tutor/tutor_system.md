# Sprach-Tutor (Persona-Portal)

**Stand 2026-09-18:** Der Tutor ist ein eigenes Projekt in `tutor/`
(Struktur, Artefakte, Routen, Checkliste neue Sprache: **`bauplan.md`**, mit
Drift-Test; Ausbau-Referenz: `naturalisierung.md`). Drei Sprachen **live**:
`es` Lucía, `zh` Ling Ling, `de` Lena (seit 2026-09-18, Lucías Konstrukt 1:1
übersetzt) — alle über den Provider `qwen`; Skizzen `fr`/`ru`/`ar`
(`enabled=False`). **Ein Spielstand = eine Sprache + ein Startlevel**
(`tutor/staende.py`); die aktive Sprache kommt nur aus dem aktiven Stand,
`tutor_config.json` kennt kein `lang`, Alt+L im Zimmer ist weg. Muttersprache
für Glossen = Einstellung `native` (Default `en`). **Das Assessment-Gate ist
abgeschafft** (`tools.GATE_AKTIV = False`): die Persona redet von Anfang an,
das Drill ist ein Spiel daneben (Alt+D). Vokabel-Modell: nur `spoken`/`listened`
je Wort → Status `new/understood/learning/learned/intuitive`; die KI zählt
nie. 12 Tools in der Sandbox (`tools._ALLOWED`). Skill-Catcher `tutor/skills.py`
erkennt `no_entiendo` und **loggt nur**. An der Wand ist das Zimmer
(`tutor/room.py`) das Kiosk-Bild des Pi (`../betrieb/deployment.md`);
Anwesenheit kommt über Mikro und PIR (`../system/audio_strasse.md`,
`../betrieb/hardware.md`), die Persona spricht nur nach verstandenen Worten
oder PIR-Treffer von sich aus. Die einzige Naht zum Kern ist
`core/tutor_port.py`; Keys und Kill-Switches gehören dem Kern.
⚠ prüfen: das TUI-Textpanel (`/tutor`) bietet noch `/lang` an, obwohl
`/api/tutor/config` ein `lang` ablehnt.

Diese Datei beschreibt **Verhalten** und das Warum; Struktur steht im
Bauplan, die Entstehungsgeschichte unten in der Historie.

## Persona-Portal: eine Figur pro Sprache

Der Tutor ist ein **Persona-Portal**: jede Sprache = eine benannte **Persona**
mit eigenem Charakter, eigenem Land und eigenem AI-Anbieter (Provider/Modell
entkoppelt). **Eine Sprache = ein Ordner** `tutor/langs/<code>/` (Pflichtdateien
und -felder: `bauplan.md` §4); die Registry `tutor/langs/__init__.py` findet die
Pakete selbst — eine Sprache dazubauen heißt einen Ordner anlegen, nichts
Zentrales anfassen. Figur: Profil-Feld `avatar` (Default `lucia`), bis eine
Persona ihre eigene Schablone hat (`tutor_puppe.md`). Provider zeigt bewusst
auf `qwen` statt der Skizzen-Wahl `mistral`: qwen läuft heute (Key da,
no-train, solide bei es), umstellbar über `tutor/data/tutor_config.json`.

**Standard-Prompt-Template.** `tutor/langs/PROMPT_TEMPLATE.en.md` ist DER
sprach-neutrale Master-System-Prompt (Englisch, Platzhalter `{persona}/{target_language}/
{country}/{native}`). Jedes Paket-`prompt.md` ist eine **Hand-Übersetzung** davon in die
Zielsprache (kein Code-Generat — target-language hält qwen dort). Inhalt = Sashas
**Roleplay-Rahmen** (commit `1d915f9`): Zimmer als IHRS, Emotion, **leichte emergente
Vokabel-Handhabung** (nutze Bekanntes aus der Liste, streu dosiert Neues ein). BEWUSST
RAUS: der Assessment-Ära-Anfänger-Ballast (Wort-für-Wort, Abtasten/`mark_known`,
`show_thought`-Zwang pro Wort, Register-Leiter) — darum ist `expect.json` heute leer.
zh + es sind aus dem Master abgeleitet und gegen echtes qwen-plus getestet
(2026-07-25: kurze echte Sätze, in-character, kein „yo/tú"-Abtasten).

**Charakter — gegen echtes qwen getunt** (Log: `tutor_persona_tuning.md`):
- **Kein Lehrer, kein Kurs.** Natürlicher, KURZER Gesprächspartner — 1-2 Sätze,
  kein Monolog, kein Fake-Lob, kein Abfragen/Benoten, nicht dreifach erklären.
- **Nur die Zielsprache.** Nur wenn Sasha ausdrücklich nach einer Wort-Bedeutung
  fragt, EIN kurzer Halbsatz in der Muttersprache, dann zurück.
- **Kein Fake-Mensch:** ehrlich eine KI, keine erfundene Vergangenheit/Herkunft,
  hat im Land „nie gelebt". Auf „bist du Chinesin?" → „ich bin eine KI".
- **Kultur beiläufig, NICHT erzwungen:** sie kennt Essen/Alltag, streut das nur
  gelegentlich knapp ein — kein Reiseführer, kein Geschichts-/Politik-Vortrag.
- **Wie es zuverlässig wird (WICHTIG):** der Prompt ist **in der Zielsprache**
  verfasst (hält qwen in der Sprache), mit **Few-Shot-Beispielen + harten
  Verboten**; dazu **`TUTOR_TEMPERATURE` (0.4) + `TUTOR_MAX_TOKENS` (200)** im
  Cloud-Pfad (`tutor.openai_compat`/`tutor.cloud`). Prompt-Wording ALLEIN war
  Glückssache — qwen driftete sonst in deutsche Monologe.
- **Skizzen** nutzen die schlanke generische `_build_prompt`; beim Aktivieren
  einer Sprache: eigenen Prompt IN DER ZIELSPRACHE hand-tunen wie zh/es.

**Vokabel im Prompt:** der Persona-Prompt sagt keine Tool-Calls an. Der bekannte
Wortschatz wird als **zielsprachiger Kontext** (`vocab_hint`, `{words}`) in
`tutor.session` ans Prompt-Ende gehängt (ein deutscher Block kippt qwen ins
Deutsche) — mit Status je Wort, nie mit Zahlen.

### Vokabel-Modell: spoken / listened

Nur **zwei Zähler** pro Wort (Sasha, 2026-07), `tutor/tools.py`:
- `spoken` +1, sobald der User das Wort **selbst** benutzt hat — deterministisch
  aus seiner Eingabe gematcht (`note_spoken`), die KI zählt nicht.
- `listened` +1, wenn die KI es sagt und der User sinnhaft antwortet, ODER beim
  ersten Aufdecken im Drill (nur einmal).

Daraus der Status (`word_status`, spoken schlägt listened): `understood` ab
4× gehört, `learning` ab 2× selbst benutzt, `learned` ab 4×, `intuitive` ab
12×. Die KI kriegt **nie** die Zahlen, nur `{wort: status}`. Offen: die
„sinnhafte Antwort"-Wertung im Gespräch und die Embedding-Auswahl bei langen
Listen.

### Kern-Syllabus (pro Sprache)

Zusätzlich zum emergenten Vokabular trägt ein Paket ein festes
**Curriculum** `core_vocab.json` (≈76 Kern-Wörter, `{word, reading, priority,
category, gloss:{en,de}}`; Glosse in der Muttersprache `native`). `tutor.session`
hängt daraus in der Zielsprache einen `core_hint` ans Prompt-Ende — Fortschritt
(`{got}/{total}`) + die nächsten noch-nicht-gefestigten Kern-Wörter nach
Priorität (`tools.core_todo`) — damit die Persona das Grund-Vokabular **aktiv
abarbeitet** statt beliebig. Seit dem Ende des Gates ist das Grundvokabular der
Persona sofort freigegeben (`tools.prompt_vocab()`, Status ehrlich `new`). Die
**Deckung** misst sich, indem die Curriculum-Wörter gegen den Lernstand
geschnitten werden (`tools.core_coverage`) — kein zweiter Zähler. Bei **100 %**
(`GRADUATE_AT=1.0`, Sasha: ALLE) feuert `tools.check_graduation` **genau
einmal** einen Meilenstein (`state.push_log` „🎓 Kern-Wortschatz gemeistert"),
danach fällt der `core_hint` weg. Der einmalige Zustand liegt in
`progress.json` des Standes — **bewusst NICHT** in den Persona-Notizen
(`persona_mem`), denn die wandern in den Cloud-Prompt; ein Steuer-Flag hat da
nichts zu suchen. **Level beim Anlegen eines Standes** (`tools.level_anwenden`):
0 von vorn · 1 Grundlagen (critical+high gelten als gehört) · 2 kann mich
verständigen (alle, graduiert).

### Drill: ein Spiel daneben (kein Gate mehr)

**Warum kein Gate:** Sasha, 2026-09-14: „der Tutor ging nie um den Drill, das
genaue Gegenteil". Die Mechanik der alten Sperre (die Persona war „verdient",
erst nach allen Kern-Wörtern sichtbar) läuft unverändert weiter, nur die
Pflicht ist weg: `tools.GATE_AKTIV = False` → `assessment_active()` immer
False. Im Zimmer per `Alt+D`, `Esc` zurück.

**Deterministisch, kein LLM.** Vokabeln abfragen ist deterministisch — ein
LLM brachte da nur Latenz (2 Min bis ein Wort kam), Zufall und keine Ansage.
Backend: `tools.assessment_queue(lang)` liefert die Kern-Wörter + Lernstand,
`tools.assessment_answer(lang, word, known|learned|again)` verbucht eine
Antwort UND die Spiel-Ökonomie, `tools.game_state(lang)` den Spielstand;
Routen `GET /api/tutor/assessment`, `POST /api/tutor/assessment/answer` (via
`core/tutor_port.py`; **kein** `available()`-Gate — braucht kein Modell).
Frontend (`room.py`, `asv`-Controller) geht die Wörter Karte für Karte durch,
die Stimme liest jedes Wort vor (`be.speak`, Speed-Rampe `tools.tts_speed_for`
0.7 → 1.0); im Drill stößt `feedback_loop` NIE die KI an.

**Steuerung — der Weg bestimmt die Wertung** (seit 2026-09-04):

| Taste | Wirkung |
|---|---|
| `↓` | aufdecken (Übersetzung + nochmal vorlesen) |
| `→` / `Enter` | weiter |
| `←` | zurückblättern und nachschauen |

Wer *ohne* Aufdecken weitergeht, hat das Wort gewusst — der Normalfall ist ein
Tastendruck. Wer aufdeckt, sagt damit »wusste ich nicht«, und die Karte kommt
per Session-SR in ein paar Karten wieder. Keine Extra-Taste fürs Abhaken. Der
**Rückblick** (`←`) verbucht **nichts** — Nachschlagen, kein Wiederholen, sonst
holte man sich per Zurückblättern Münzen; gedeckelt auf `VERLAUF_MAX` (20)
Karten. Das Auto-Weiter drei Sekunden nach dem Aufdecken ist weg: der Mensch
entscheidet, wie lange er auf die Übersetzung schaut.

**Spiel-Schicht** (persistiert je Stand in `game.json`: `coins`, `parts`,
`reviews`, `crates`, `srs`; Konstanten in `tutor/tools.py`):
- **Statusleiste = erstes Wissen.** Das erste Wissen eines Worts festigt es
  (`got` +1); weitere Reviews bewegen die Leiste NICHT. Ziel: schnell eine
  Working-Memory-Basis; echte Tage-SR dann im Gespräch (FSRS).
- **Session-SR (Frontend) — Due-Time-Scheduler**, KEIN Positions-Insert (das
  driftet). Jede Karte hat `due` = „ab Karten-Zahl `seen` wieder fällig";
  `_pick` nimmt die fällige mit kleinstem `due`, neue Wörter interleaven.
  **Expanding retrieval** (belegt für Kurzzeit-Retention, Landauer&Bjork; ~2×
  wie Anki/Leitner): gewusst → `due=seen+SR_LADDER[streak]`, `SR_LADDER=(7,14,25)`,
  nach dem 3. Review graduiert das Wort aus der Runde; nicht gewusst →
  `due=seen+SR_LAPSE(3)`, Streak 0; übersprungen → `SR_SKIP(5)`. Die Abstände
  sind **Minimums** — bei vielen aktiven Wörtern strecken sie sich, gewollt
  (nie zu früh = effortful retrieval).
- **Münze NUR zufällig** und **nur beim ERSTEN Wissen** (`COIN_CHANCE=0.35`) —
  Wiederholungen geben KEINE Münzen (kein Coin-Farming). Sie fällt direkt AM
  Wort runter (Sasha: nicht nur in der Ecke), Gesamtzähler oben rechts.
- **Kisten** an distinkten Wort-Meilensteinen (`CRATE_GAPS=(15,20)`
  abwechselnd: 15/35/50/70), nur beim ersten Wissen, damit die Kisten-Symbole
  exakt auf der Leiste sitzen. Inhalt zufällig: **Körperteil**
  (`CRATE_PART_CHANCE=0.6`) oder Münzen (`_open_crate`).
- **Die Persona baut sich zusammen** (`_draw_lucia`): erhaltene Teile schweben
  herein und rasten ein; komplett bei Graduierung.
- **Phase 2/3 (offen):** Shop + Küche/Tür-Mechaniken, Etappen + Profil-Quiz.

**Langzeit-SR fürs GESPRÄCH (FSRS, `tutor/srs.py`).** Klare Arbeitsteilung: das
Drill baut die Working-Memory-Basis (Abstände in **Karten**), die echte
Tage-Retention läuft über **FSRS** — Ankis Open-Source-Scheduler (`fsrs`,
PyPI, MIT, pure Python, kein Netz; NICHT selbstgebaut). Bewusst NICHT im Drill:
FSRS rechnet in Tagen, im Sekundentakt wäre alles „in 1 Tag fällig".
Speicher `fsrs.json` je Stand; **Soft-Import** (fehlt `fsrs` → No-ops, der
Tutor läuft). Anbindung: erstes Wissen im Drill legt eine Karte an
(`srs.ensure`); Tool **`get_due_reviews`** gibt der Persona die fälligen Wörter,
sie baut sie beiläufig ein. Offen: kein „Again"-Signal aus dem freien Gespräch;
das Surfacing hängt daran, dass das Modell das Tool ruft.

### Skills: deterministische Situations-Auslöser

`tutor/skills.py` (seit 2026-09-17): erkennt aus Sashas Eingabe Situationen,
die der Prompt nicht verlässlich abfängt — erster Skill **`no_entiendo`**
(Unverständnis). Stufe 1: erkennen und **loggen**, noch nicht behandeln
(`skills.pruefen` läuft vor `respond_stream`). Was daraus werden soll —
runterschalten auf ≤3 Wörter, langsam, Gedanke, Geste — steht in
`naturalisierung.md`.

### Devtools-Terminal

`scripts/tutor_devtools.py [--url …]` in einem eigenen Terminal → zeigt LIVE +
zeitgestempelt: Snapshot beim Verbinden (komplette Vokabel mit Status), jede
Vokabel-Statusänderung, den KOMPLETTEN AI-Stream (`ai.req` voller Prompt —
was sie KRIEGT; `ai.out` Roh-Ausgabe inkl. versteckter Regie/Tool-Leaks — was
sie AUSGIBT; `ai.tool` jeder Call), Skill-Treffer. Naht: Ereignisbus
`tutor/debug.py` (Ring-Puffer + Subscriber), Snapshot `tools.debug_snapshot`,
SSE `GET /api/tutor/debug/stream`. `debug.emit()` schluckt jeden Fehler.

### Direkt-Start

TUI-Taste `u` öffnet **mit `DISPLAY` das Persona-Zimmer** (eigenes
pygame-Fenster, detached, Single-Instance, Fehler nach
`/tmp/zentrale-tutor-room.log`, `BASE_URL` wird mitgereicht — findet auch vom
Laptop via `zentrale-remote` ans PC-Backend); **ohne `DISPLAY`** (headless/ssh)
das Text-Panel (`/tutor`), das die Persona sofort loslegen lässt. Der Browser
(`monolith.html`, aufgegeben) startet über `Alt+T`. Standalone:
`venv/bin/python tutor/room.py [--url … --wand --speaker N --speed X --mute]`.

## Persona-Zimmer (natives pygame-Fenster)

Der Tutor ist keine Chat-Box, sondern eine Person — sie **wohnt** in einem
gezeichneten Wohnzimmer: `tutor/room.py` (pygame). **Das Zimmer ist dumm:**
rein Renderer + Client, importiert nichts aus dem Projekt (läuft auf dem Pi
ohne Backend-Code), spricht `/api/tutor/*`, `/api/speak`, `/api/transcribe`.
Session/Sprache/Persona/Memory liegen im Backend.

- **Szene:** Wand + Dielenboden, Fenster (nachts Mond, tags Sonne), Stehlampe mit
  Glühen, Couch, Teppich, Pflanze.
- **Theme an ZENTRALE gekoppelt** (light/dark): `apply_theme(mode)` + zwei Paletten
  (`_NIGHT`/`_DAY`). Liest `~/.config/zentrale/theme.now` wie alle Teilnehmer
  (`../system/dashboard.md`); ein `watch_theme`-Thread pollt alle 3 s, angewandt
  im Render-Frame (kein Farb-Race). Der Drill nutzt semantische Keys
  (`ASSESS_INK/INK2/PANEL/KEY_INK/BAR_BG/NODE`).
- **Figur:** gemalte Puppe mit Rig (`tutor_puppe.md`); läuft rum, sitzt sich auf
  die Couch, blinzelt; kleine Verhaltens-Maschine (idle → schlendern → sitzen →
  aufstehen). Redet sie (SSE läuft), nickt sie zugewandt mit Mund-Animation.
- **Stimme:** nach jeder Antwort holt das Fenster die WAV vom Backend-TTS
  (`POST /api/speak`, `lang` aus dem Profil; Engines je Sprache:
  `../betrieb/setup.md`). Gespielt über `pygame.mixer` — **der Mund bewegt sich,
  solange Audio läuft**. `play_wav` initialisiert den Mixer auf die Sample-Rate
  der Datei (pygame resampelt nicht → sonst falsche Tonhöhe). Tempo `--speed`
  (`TUTOR_TTS_SPEED`); `--speaker` greift nur bei Multi-Sprecher-Modellen.
  Smileys und Sternchen-Regie werden vor dem Sprechen entfernt (Commits d33856a,
  e4df6ad). Kein TTS → ehrlich „🔇 keine Stimme (tts-service aus?)" (aus
  `status['tts']`, alle 4 s nachgepollt) statt still zu scheitern.
  - **Damit die Stimme wirklich kommt, muss laufen:** der `tts_service`
    (Port 5051; hard-importiert `soundfile`, zh braucht `sherpa-onnx`), Modelle
    via `services/download_tts_model.py`. `/api/speak` blockt nur, wenn AUCH der
    Tutor kein Backend hat (`kassette.ki_aus() and not tutor_port.available()`)
    — sonst spricht die Cloud-Persona trotz „lokale KI aus".
- **Mikro:** immer offen, VAD → Segment → `/api/transcribe` (Sprache aus dem
  Profil); Whisper-Untertitel-Floskeln gehen nicht als Sashas Worte durch
  (e4df6ad). Während die Stimme spricht, ist das Mikro gegated. Details und die
  offene Weiche für den Assistenten: `../system/audio_strasse.md`.
- **Wand-tauglich:** `--wand` = randloses Fenster in Desktop-Größe (kein echtes
  Fullscreen, sonst läge die per Alt+Z geöffnete TUI dahinter). Nach einem
  Backend-Neustart holt sich das Zimmer selbst eine neue Session (32a1f03).
  Der Browser bekommt KEIN Zimmer (kann keinen nativen Prozess starten).
- **Esc-Menü** (18d77c1): Weiter, Hauptmenü (Stände), Einstellungen (`native`),
  Beenden. Tasten im Zimmer: `Esc` Menü · `↑/↓` Verlauf · `Enter` reden ·
  `Alt+P` Pause (lässt sie in Ruhe) · `Alt+D` Drill · `Alt+Z` Zentrale (TUI).

### Eigenleben: Ausdruck + Feedback-Loop (nicht nur ein Chatfenster)

- **Gesagtes verhallt:** die Sprechblase steht kurz voll (`BUBBLE_LINGER`) und
  blendet aus (`BUBBLE_FADE`). Unten eine translucente **Verlaufs-Leiste**
  (Sasha kühl, Persona warm), mit **↑/↓** scrollbar — so geht nichts verloren.
- **Bewegung ist ein KI-Tool, kein Random:** die Persona läuft/pact/sitzt nur,
  wenn die KI sich selbst ausdrückt (Tool **`express`**, Enum
  sit/stand/pace/wander/come_closer + wave/nod/look/stretch) → `tutor.session._expr`.
  Das Fenster pollt **`GET /api/tutor/room_state`** (~4 Hz) und animiert.
- **Anwesenheit statt Stille-Timer.** Sie redet nicht mehr ins Leere: anquatschen
  nur, wenn sie GERADE jemanden hört (verstandene Worte) oder der PIR meldet
  (`presence_age` in `room_state`) — Geräusche allein wecken sie nicht (e46f419,
  933a2be, 4e1487b). Grundrauschen lernt nur aus Stille (4141cd5). Der Nudge
  (`POST /api/tutor/nudge`, nicht in der History) ist gedeckelt: nach
  `NUDGE_AFTER_S` (90 s — 25 s war Spam) EIN Anstoß, danach **chillt** sie
  client-seitig, erst nach `CHILL_RECHECK_S` (15 min) ein neuer Versuch; sie
  zieht dabei ins Gespräch statt nur zurückzugrüßen (a049aa0). `Alt+P` lässt
  sie in Ruhe.
- **Presence vom Kern:** `brain.py PRESENCE_DETECTED` → `tutor_port.presence_ping()`
  = nonverbale Reaktion (schaut hoch, Mimik happy) nur bei **laufender**
  Session, Default AN, `TUTOR_PRESENCE_REACT=0` aus. Es STARTET keine Session
  (der alte Auto-Trigger war genau das Problem). Details: `tutor_roleplay_features.md` §5.

## Spielstände: ein Stand = eine Sprache + ein Level

```
tutor/data/staende/<id>/stand.json    name, lang, level, angelegt, zuletzt gespielt
tutor/data/staende/<id>/<lang>/…      vocab, fsrs, game, progress, persona_mem, …
tutor/data/aktiver_stand              eine Zeile: welcher gerade läuft
```

**Warum eine Sprache je Stand (2026-09-18):** vorher war ein Stand global
(ein Durchgang über alle Sprachen, Sprache per `/lang`/Alt+L getrennt gewählt)
— und Stände konnten ineinander bluten. Jetzt trägt `stand.json` `lang` und
`level`; die aktive Sprache kommt **nur** aus dem aktiven Stand
(`staende.aktive_sprache()`), `tutor_config` kennt kein `lang` mehr, Sprache
wechseln = im Hauptmenü (Esc) einen anderen Stand laden. Bluten ist physisch
unmöglich: `pfad(root, lang)` wirft `StandSprache` bei fremder Sprache; Wechsel
und jede Lese-Änder-Schreib-Folge in tools/memory/srs laufen unter derselben
`stand_lock`; lange Operationen (`memory.remember`, `respond_stream`) prüfen
ein `token()` und verwerfen bei Wechsel (`StandGewechselt`); `deactivate()`
vergisst Sprache + Verlauf. Alte Stände ohne `lang` werden beim ersten Zugriff
in Ein-Sprach-Stände aufgeteilt (`migrieren_sprachen`).

**Ein Griff für alle Datenpfade:** `tutor/staende.py`. `memory`, `srs` und
`tools` hatten ihren Ordner früher je selbst zusammengesetzt; läge einer
daneben, mischten sich zwei Stände still. Alle drei fragen `staende.pfad`; ein
Test prüft, dass sie beim Wechsel gemeinsam mitwandern
(`tests/test_tutor_staende.py`).

Der Zeiger steht bewusst **nicht** in `tutor_config.json`: die hält
Einstellungen (Provider/Modell/`native`) — welchen Spielstand man spielt, ist
keine Einstellung.

**Umzug statt Verlust:** beim ersten Start nach dem Umbau (2026-09-04) wanderte
der alte Lernstand in einen Stand »Erster Anlauf« — je Knoten einmalig,
idempotent. Gemeinsame Ordner (`vocab_images`, `persona_music`) gehören keinem
Stand.

**Gewählt wird im Hauptmenü des Zimmers**: vorhandene Stände, darunter »Neuer
Spielstand« (Name, Sprache, Level); ↑↓ und Enter, vorgewählt der zuletzt
gespielte. Beim Wechsel wird die laufende Persona-Sitzung beendet: ihr Verlauf
liegt im Speicher, nicht auf der Platte — sonst redete Lucía im neuen Stand
mit den Erinnerungen des alten weiter.

**Löschen** liegt auf `Entf` und fragt nach — mit Namen, Fortschritt und dem
Satz, dass das Gelernte endgültig weg ist. Solange die Rückfrage offensteht,
beantworten *alle* Tasten sie; sonst blättert man im Hintergrund weiter und
löscht am Ende den falschen Stand. Auch der aktive darf weg; `aktiv()` liefert
nie `None` (wer alle löscht, bekommt einen neuen). Routen: `bauplan.md` §3 —
bewusst POST mit id im Body statt DELETE auf einen Pfad (die Fronten sprechen
nur GET/POST, ein versehentlicher Browser-Aufruf kann nichts löschen), und
**kein `available()`-Gate**: das sind Dateien auf der Platte, den Stand soll
man auch bei gedrosselter Cloud wechseln können.

## Persona-Memory: der Mitbewohner erinnert sich an dich

Jede Persona hat ein **eigenes Gedächtnis**, getrennt von Sashas privatem
Core-Graphen — `tutor/memory.py`:
- **GROB, nicht exakt:** ein Mitbewohner merkt sich *ungefähr* ein paar wichtige
  Dinge. Darum kein Konzept-Graph und kein Wortprotokoll, sondern eine kleine,
  gedeckelte **Notiz-Liste**: `persona_mem.json` je Stand = `{"facts": [kurze
  Sätze], "topics": [Stichworte]}` (je max 12, in der Zielsprache, keine
  Zeitstempel). Nur Wissen **über Sasha** — keine erfundene Persona-Biografie.
- **Kein persistenter roher Verlauf:** `_history` ist reiner In-Session-Puffer.
  (Ein persistierter Verlauf füllte sich mit Nudge-Fillern und zog die Persona
  in Echo-Schleifen — Historie 2026-07-10.)
- **Loop (`tutor.session.respond_stream`):** vor der Antwort wird der
  Notiz-Kontext an den System-Prompt gehängt; nach einem echten Turn
  destilliert `remember()` im Hintergrund neue Fakten/Themen (leichter
  LLM-Pass, merged + deckelt, Token-geprüft gegen Stand-Wechsel). Der
  Öffnungs-/Nudge-Turn wird **nicht** gemerkt (ambient, kein Gespräch).
- **Verdichtungs-Backend kapazitätsbasiert** (`ai_backends.status()`): Ollama
  erreichbar → lokal; sonst Cloud (der Anbieter, der eh redet); kein Backend →
  übersprungen.
- **Was hier NICHT stimmt (ehrliche Grenze):** läuft die Persona über die
  Cloud, liegt ihr Gesprächs- und Memory-Inhalt beim Cloud-Anbieter — das Reden
  läuft ja dort, der Kontext-Block wird jede Session mitgeschickt. Die lokale
  Verdichtung ist **kein** Privacy-Schutz fürs Tutor-Material, nur billiger und
  offline, **wenn** Ollama da ist. Die **einzige** harte Garantie: die
  **Core-KI-Memory** (`ai_graph.json`) wird der Persona **nie** gefüttert — die
  Stores fassen sich nicht an, die Sandbox aus `tutor/tools.py` bleibt intakt.
  Persona-Turns werden nicht in Sashas Kalender gespiegelt.

Tests: `tutor/test_memory.py` (Notiz-Modell, Sandbox, Persona-Prompt,
Backend-Wahl, Sprach-Isolation, Secret-Freiheit) läuft nicht unter pytest
(`testpaths = tests`), sondern von Hand: `venv/bin/python tutor/test_memory.py`.

## Framework: Sprachen + Provider (austauschbar)

Sprachen werden als **Personas** draufgelegt, der **Anbieter/das Modell ist
davon entkoppelt**; beides wird zur Laufzeit aufgelöst (`tutor.session._resolve`):
Stand → Sprache → Profil → Provider → Modell.

- `tutor/langs/` – ein Ordner pro Sprache. Im Profil: `reading` (zh=Pinyin,
  ru=Betonung, ar=Translit, es/de=—), STT/TTS-Lang, Default-Provider+Modell.
  **Keine Vokabel-Datei** — die ist LERNSTAND und liegt im Stand (gitignored);
  `langs/` ist die SPRACHE und wird getrackt.
- `tutor/providers.py` – **Provider-Registry** des Tutors (`kind`
  `ollama|anthropic|openai_compat`, `base_url`, `key_env`, `default_model`,
  **`trains_on_data`**, `jurisdiction`, `enabled`). LIVE: `local` (Ollama),
  `claude` (Sashas Pfad), `qwen` (Verteil-Default). Skizzen: `openai`,
  `mistral`, `groq`, `deepseek`, `gemini`. Bewusst getrennt von
  `core/providers.py` (Kern: nur Erreichbarkeit) — Preis: base_url/key_env an
  zwei Stellen.
- `tutor/openai_compat.py` – Drop-in für `ai.chat_stream()`, bedient JEDEN
  OpenAI-`/v1`-kompatiblen Provider durch Tausch von base_url+Key+Modell; Tools
  aus `tools.tools_for(lang)` (schon OpenAI-Schema). Streaming-Tool-Loop.
- `tutor/cloud.py` – Anthropic-SDK-Pfad (Claude), Sashas persönliche
  Verifikation; übersetzt die Tools ins Anthropic-Format.

**Steuerung:** `tutor/data/tutor_config.json` (`tutor/config.py`) hält
`provider` / `model` / `history_window` / `native` — **kein `lang`, KEINE
API-Keys**. Vorlage `tutor/data/tutor_config.json.example`. **Keys gehören dem
Kern**: `core/ai_config.py` → `data/ai_config.json` (`keys`-Block) injiziert
sie in `os.environ`; `tutor/config.py` injiziert nichts (Regression in
`tutor/test_memory.py`). So kann ein vergessener gitignore-Eintrag unter
`tutor/` kein Secret leaken. **Precedence:** Runtime-Override > Env-Var
(`TUTOR_PROVIDER` / `TUTOR_MODEL` / `TUTOR_HISTORY_WINDOW`) >
`tutor/data/tutor_config.json` > `data/tutor_config.json` (Legacy, nur gelesen)
> Profil-Default. `history_window` (Default 30) = wieviele letzte Turns
gesendet werden (Kosten-Hebel). **Caching:** nicht explizit gesetzt;
cache-freundlicher Aufbau (stabiler Prompt zuerst) — Qwen-Context-Cache
offen.

**Backend-Wahl über den aufgelösten Provider:** `tutor.session._stream`
verzweigt auf `provider.kind`. **Ein `TUTOR_BACKEND` liest kein Code** — die
Env-Var stand lange falsch dokumentiert.

**Privacy-Flag (HART):** Provider mit `trains_on_data=True` (deepseek,
gemini-free) **oder unverifiziert** (`None`, z.B. groq) werden NICHT verboten,
aber bei Session-Start **laut geflaggt**: `tutor.session.activate()` setzt eine
Warnung, die `/api/tutor/status` als `privacy_warning` liefert → UI muss sie
deutlich anzeigen.

**Offline-Prinzip:** Default bleibt `local` (Ollama). Cloud ist Opt-in.
`openai` ist in `requirements.txt`; `anthropic` bewusst auskommentiert (Opt-in
für den Claude-Pfad). `DASHSCOPE_API_KEY` liegt in `data/ai_config.json` —
**einzige Key-Quelle**; ein `keys`-Block in der Legacy-Datei wird ignoriert
und beim Start angemahnt.

**Verfügbarkeit (kapazitätsbasiert, nicht kassetten-hart):** Fronten fragen
IMMER `tutor_port.available()`, nie `tutor.session` direkt. Der Port prüft
zwei Dinge getrennt: **Darf er?** — `tutor_port.allowed()` fragt die
ZENTRALE-Drossel (`ai_backends.cloud_enabled()`/`local_enabled()`, je nach
`tutor.session.backend_kind()`), Core-Policy. **Kann er?** —
`tutor.session.available()` prüft nur Kapazität (Ollama da bzw. Key + Host,
5 s gecacht); der Tutor kennt die Drossel bewusst NICHT. Fehlt etwas:
`/api/tutor/{start,respond}` → 503 mit dem Grund aus
`tutor_port.unavailable_reason()` — an genau EINER Stelle formuliert, Fronten
geben ihn wörtlich weiter (Felder: `../system/api_endpoints.md`).

## Position in der Architektur

Tutor ist ein **Addon** auf der Core-AI, nicht der Owner der Voice-Pipeline.
STT und TTS leben zentral in `services/` und sind sprachneutral nutzbar via
`/api/transcribe` und `/api/speak` (`../ki/audio_system.md`); der Tutor ruft
sie als Aufrufer, die Sprache kommt aus dem Profil. Die einzige Naht ist
`core/tutor_port.py`; kein Core-/UI-Modul importiert `tutor.*` (verifiziert
mit physisch entferntem Ordner: ZENTRALE startet, `present()` → False). Was
`tutor/` vom Kern braucht (Liste im Kopf von `tutor/__init__.py`):
`ai.chat_stream`/`ai.is_available`, optional `ai_backends.status`,
`state.push_log`. Der Cloud-Pfad braucht nichts aus ZENTRALE.

**Warum ein Paket und nicht flach** (nachgemessen 2026-07-16): kurze Namen
kollidieren still und reihenfolge-abhängig (`core/providers.py` vs.
`tutor/providers.py` — es gewinnt der erste `sys.path`-Eintrag, kein Fehler,
nur die falsche Tabelle); und ein Ordner `tutor/` neben einem Modul `tutor.py`
liefert nach PEP 420 **immer** das Modul (Namespace-Package ist Fallback
letzter Instanz) → `from tutor import session` bräche deterministisch. Als
echtes Paket sind beide Probleme strukturell weg.

## Tutor-Tools (Sandbox)

Aktiv nur während einer Session (`tools_for(lang)`); ersetzen die
Standard-Tools des Kerns. **12 Stück** in `tools._ALLOWED` — alles andere wird
abgelehnt UND geflaggt (eine Cloud-AI, die ein lokales Tool ruft, soll
sichtbar sein). Beschriftung je Sprache aus `tool_texts.json`.

| Tool | Argumente | Funktion |
|---|---|---|
| `introduce_new` | `word`, `reading?` | Neues Wort in den Lernstand (Status `new`) |
| `express` | `action` (Enum) | Haltung/Geste/Mimik im Zimmer |
| `get_structures` | – | Satzmuster im Lernen (`structures.json`) |
| `introduce_structure` | `pattern`, `note?` | Neues Satzmuster |
| `increment_structure` | `pattern` | +1; ab `STRUCT_THRESHOLD` (3) gefestigt |
| `show_thought` | `word`, `meaning?`, `reading?` | Vokabel-Gedanke (Wort + Glosse + Bild aus `vocab_images/`) im Zimmer |
| `get_local_news` | – | Ein leichtes Landes-Thema (Seed, rotierend; NIE `core/news.py`) |
| `get_due_reviews` | – | Fällige FSRS-Wörter |
| `watch_tv` / `turn_off_tv` | `mood` | TV an + level-gerechter Titel (Seed `tv.json`) |
| `play_music` / `stop_music` | `mood` | Musik aus `persona_music/<mood>/` (Content-Lücke) |

**Legacy, bewusst weg:** `get_confirmed_vocab`, `get_testing_vocab`,
`increment_correct_use`, `mark_known` (Zählmodell `confirmed`/`correct_use`,
siehe Historie) — die KI zählt nicht mehr. ALLE Tools fassen nur Daten des
aktiven Standes + UI-State an, nie die Core-KI (`tutor_roleplay_features.md`).

## Bedienung

- **Zimmer:** siehe oben (Esc-Menü, Alt+D/P/Z). Das ist die Bedienung, die zählt.
- **TUI-Textpanel** (`/tutor`, ohne DISPLAY): Slash-Befehle `/tutorstop`,
  `/provider <name>`, `/model <id>`, `/models`, `/cloud on|off`
  (Cloud-Kill-Switch, `POST /api/ai/backends`). ⚠ prüfen: `/lang` steht noch
  im Panel-Hinweis, das Backend lehnt `lang` ab.
- **Browser** (`monolith.html`, aufgegeben): `Alt+T` Kanalwechsel (roter
  Rahmen um `#col-mid`), Eingaben an `/api/tutor/respond`, `/tutor`/`/tutorstop`
  in der Konsole. Ein eigenes Tutor-Exhibit wurde nie gebaut.

## Historie

- **2026-05-14** — Tutor weich deaktiviert. Grund war Sequencing (erst die
  Core-KI sauber aufstellen), nicht der schlechte Presence-Auto-Trigger.
- **2026-06-30** — Reaktivierung: Routen über `ui/app.py`, Audio über die
  generischen `/api/transcribe`+`/api/speak` (Tutor-Aliase entfernt), `Alt+T`
  im Browser, `u` in der TUI; Start rein manuell.
- **2026-07-07** — Persona-Portal: vom Lehrer zum chilligen Mitbewohner, zh-Prompt
  gegen echtes qwen getunt (`tutor_persona_tuning.md`). **07-09** Roleplay-Tools
  (`tutor_roleplay_features.md`), nonverbaler Presence-Ping. **07-10** Memory
  von Graph/Wortprotokoll auf Notiz-Liste; roher Verlauf nicht mehr persistiert
  (Nudge-Filler zogen sie in Echo-Schleifen).
- **2026-07-16** — Drei Schnitte an einem Tag: (1) **Infra-Schnitt** —
  Kill-Switches und Keys vom Tutor in `core/ai_config.py`, `core/providers.py`
  für den Kern, `core/tutor_port.py` als einzige Naht, toter
  `consolidation._cloud_graph_extractor` weg; (2) **eigenes Paket `tutor/`**
  (Warum oben); (3) **Sprach-Framework** — eine Sprache ist ein Ordner. Vorher
  war das Framework eine Fassade: Profilfelder ohne Leser, Mechanik
  mandarin-fest (Modul-Konstanten `_VOCAB_FILE`), `/lang fr` schrieb
  französische Wörter mit `pinyin`-Feld in Ling Lings Liste. Umzug byte-identisch
  für alle Prompts (gegen `git show` verifiziert).
- **2026-07-17** — Fronten sagen die Wahrheit: `/api/tutor/status` reicht
  `present`/`reason` durch (vorher hing der Monolith im 503, die TUI riet);
  `vocab` aus `/api/state`; Keys nur noch aus `data/ai_config.json`.
- **2026-07 (Ende)** — Kern-Syllabus `core_vocab.json` (es), deterministisches
  Drill statt LLM-Assessment (2 Min bis ein Wort kam), hartes Gate „Persona ist
  verdient", Spiel-Schicht (Münzen/Kisten/Teile), FSRS fürs Gespräch, Devtools;
  **07-25** Standard-Prompt-Template `PROMPT_TEMPLATE.en.md`, es-Stimme;
  Vokabel-Modell auf `spoken`/`listened` vereinheitlicht (vorher
  `confirmed`/`correct_use` mit `CONFIRM_THRESHOLD=5`, 80/20-Pools).
- **2026-09-03/04** — Zimmer als Aussenposten-Client auf dem Pi; mehrere
  Spielstände statt eines Lernstands; Drill auf Pfeiltasten, Löschen mit
  Rückfrage; Figur als gemalte Puppe (`tutor_puppe.md`).
- **2026-09-14** — **Gate abgeschafft** (Sasha: „ging nie um den Drill"); das
  Zimmer ist das Wandbild des Pi; Anwesenheit über Mikro (verstandene Worte)
  und PIR; keine Smileys/Regie in der Stimme; Grundrauschen aus Stille.
- **2026-09-17** — Skill `no_entiendo` Stufe 1 (loggt); Esc-Menü im Zimmer.
- **2026-09-18** — **ein Stand = eine Sprache** (Bluten unmöglich), Alt+L weg,
  `native` als Einstellung; Bauplan + Drift-Test; Ling Ling auf Lucías vollem
  Bauplan; Lena (`de`) als dritte Sprache; das Zwischenmenü friert auch Leiste
  und Stimme ein.
