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
> (Log: `memory/tutor/tutor_persona_tuning.md`). Sie **quatscht direkt los**
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
> - `ui/app.py`: **sieben** Routen aktiv — `/api/tutor/{status,config,start,
>   respond,stop,room_state,nudge}` (seit 2026-07-16 über `tutor_port`, nicht mehr
>   `tutor.session` direkt). Vertrag der Felder: `memory/system/api_endpoints.md`.
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
> - **Backend-Wahl über den aufgelösten Provider**, nicht über `TUTOR_BACKEND`:
>   `tutor.session._stream` verzweigt auf `provider.kind` (`ollama` /
>   `openai_compat` / `anthropic`), und der Provider kommt aus der Config bzw.
>   `TUTOR_PROVIDER`. **Ein `TUTOR_BACKEND` liest kein Code** — die Env-Var stand
>   hier jahrelang falsch dokumentiert (Rest steht nur noch als toter Kommentar in
>   `tutor/cloud.py`). Siehe „Cloud-Backend" unten.
> - `tutor/tools.py`, `tutor/session.py`, `tutor/cloud.py`,
>   die Vokabeln und die Audio-Modelle sind aktiv/intakt.
> - **Fronten (»alle Kassetten«-Regel):** der Tutorkanal ist in **beiden** Fronten
>   gebaut — Browser (`monolith.html`, `Alt+T`) und **TUI** (Taste `u`, komplettes
>   `TUTOR`-Panel: `tutor_refresh/open/begin/say/sse/cmd/window`, Slash-Commands,
>   `zentrale_tui.py:1271-1460`). Die frühere Zeile „ein Tutor-Kanal in der TUI
>   fehlt noch komplett" war **falsch** und widersprach dieser Datei selbst
>   (siehe Direkt-Start unten).
>
> Der Rest dieses Files beschreibt das Design; Abweichungen sind oben vermerkt.

## Persona-Portal: eine Figur pro Sprache

Der Tutor ist ein **Persona-Portal**: jede Sprache = eine benannte **Persona**
mit eigenem Charakter, eigenem Land und eigenem AI-Anbieter (Provider/Modell
entkoppelt). **Eine Sprache = ein Ordner** `tutor/langs/<code>/` mit allem, was
sie ausmacht (Profil, Prompt, Tool-Beschriftung, Register-Leiter, Seeds); die
Registry `tutor/langs/__init__.py` findet die Pakete selbst.
**LIVE: `zh` → Ling Ling (China, qwen), `es` → Lucía (Spanien, qwen).** Skizzen
(`enabled=False`): `fr` Jacqueline, `ru` Ludmila, `ar` Amira. (Provider zeigt bewusst
auf `qwen` statt der Skizzen-Wahl `mistral`: qwen läuft heute [Key da, no-train, solide
bei es], umstellbar über `tutor/data/tutor_config.json`.)

**Standard-Prompt-Template (2026-07-25).** `tutor/langs/PROMPT_TEMPLATE.en.md` ist DER
sprach-neutrale Master-System-Prompt (Englisch, Platzhalter `{persona}/{target_language}/
{country}/{native}`). Jedes Paket-`prompt.md` ist eine **Hand-Übersetzung** davon in die
Zielsprache (kein Code-Generat — target-language hält qwen dort). Inhalt = Sashas
**Roleplay-Rahmen** (commit `1d915f9`): Zimmer als IHRS, Emotion, **leichte emergente
Vokabel-Handhabung** (nutze Bekanntes aus der Liste, streu dosiert Neues ein). BEWUSST
RAUS: der Assessment-Ära-Anfänger-Ballast (Wort-für-Wort, Abtasten/`mark_known`,
`show_thought`-Zwang pro Wort, Register-Leiter) — das trägt jetzt das deterministische
Assessment. Darum ist **`es/expect.json` leer** (keine Register-Injektion nach dem
Unlock). zh + es sind aus dem Master abgeleitet und gegen echtes qwen-plus getestet
(2026-07-25: kurze echte Sätze, in-character, kein „yo/tú"-Abtasten). **Offen:** `zh` hat
(noch) kein `core_vocab`/Assessment → sein Prompt setzt eine Basis voraus, die ein
frischer zh-Anfänger nicht hat; für zh entweder ein Kern-Syllabus wie bei `es` anlegen
oder eine Anfänger-Variante behalten. **Noch offen (nächster Schritt):** Assessment-
Wörter sollen in die Vokabelliste als **„wacklig"** einlaufen (nicht sofort „ya domina"),
und erst durch Sashas eigene Nutzung „fest" werden — Level-Modell neu/wacklig/fest.

**Charakter — gegen echtes qwen getunt** (Log: `memory/tutor/tutor_persona_tuning.md`):
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

**Kern-Syllabus (optional, pro Sprache).** Zusätzlich zum EMERGENTEN Vokabular
(das nur wächst, wenn die Persona zufällig ein Wort per `show_thought` zeigt)
kann eine Sprache ein festes **Curriculum** tragen: `langs/<lang>/core_vocab.json`
= die ersten ~75 Kern-Wörter (`{word, de, reading, priority, category}`, `de` =
deutsche Übersetzung fürs Drill/`show_thought`, Paket-DATEN, kommt mit dem Repo). `tutor.session` hängt daraus in der ZIELSPRACHE einen
`core_hint` ans Prompt-Ende — Fortschritt (`{got}/{total}`) + die nächsten
noch-nicht-gefestigten Kern-Wörter nach Priorität (`tools.core_todo`) — damit die
Persona das Grund-Vokabular **aktiv abarbeitet** statt beliebig. Die **Deckung**
misst sich, indem die Curriculum-Wörter gegen die `confirmed`-Vokabeln geschnitten
werden (`tools.core_coverage`) — kein zweiter Zähler. Bei **100 %** (alle Kern-
Wörter, `GRADUATE_AT=1.0`) feuert
`tools.check_graduation` **genau einmal** einen Meilenstein (`state.push_log`
„🎓 Kern-Wortschatz gemeistert"), danach fällt der `core_hint` weg (ab da trägt
die Konversation sich selbst, Register über die `expect`-Leiter). Der einmalige
Zustand liegt in `data/<lang>/progress.json` — **bewusst NICHT** in den
Persona-Notizen (`persona_mem`), denn die wandern in den Cloud-Prompt; ein
Steuer-Flag hat da nichts zu suchen. Sprache ohne `core_vocab.json` → Feature
still inaktiv (`core_hint` leer, nichts bricht). **LIVE für `es`** (76 Wörter);
`zh` trägt (noch) keinen Syllabus. Herkunft: adaptiert aus der
Bootcamp-Skizze (`tutor/assessment_extension/`, reine Markdown-Playbooks, nie
lauffähiger Code).

**Hartes Assessment-Gate (die Persona ist verdient) — DETERMINISTISCH, kein LLM.**
Der eigentliche Kern der Bootcamp-Skizze: **man sieht die Persona/das Zimmer NICHT,
bevor der Kern-Wortschatz KOMPLETT sitzt (alle Wörter).** Wichtige Korrektur (2026-07): die
Abfrage ist **reines Frontend + Logik**, KEIN Sprachmodell. Vokabeln abfragen ist
deterministisch — ein LLM brachte da nur Latenz (2 Min bis ein Wort kam), Zufall
und keine Ansage. Das Modell ist die **Belohnung nach** dem Gate, nicht das
Abfrage-Werkzeug. Solange `tools.assessment_active(lang)` (Sprache hat ein
Curriculum UND ist noch nicht gemeistert):
- **Backend (deterministisch, kein Modell):** `tools.assessment_queue(lang)` liefert
  die Kern-Wörter + Lernstand (`word/de/category/priority/confirmed/correct_use/reps`),
  `tools.assessment_answer(lang, word, known|learned|again)` verbucht eine Antwort UND
  die Spiel-Ökonomie und gibt sie zurück (`reps/mastered/coins/coin_gain/parts/crate`).
  `tools.game_state(lang)` liefert den Spielstand. Fronten:
  `GET /api/tutor/assessment` (enthält `game`), `POST /api/tutor/assessment/answer`
  (via `core/tutor_port.py`; **kein** `available()`-Gate — braucht kein Backend-Modell).
- **Frontend (`room.py`, `asv`-Controller):** das Zimmer geht die Wörter selbst Karte
  für Karte durch — welcome → card (`[Leer/Enter]` **Abhaken ✓** / `[R]` **Repeat**
  = Bedeutung zeigen + nochmal hören / `[N]`/`→` **Next** = kurz zurückstellen) →
  unlock. **Lucías Stimme (TTS) liest jedes Wort vor** (`be.speak`, gerampter Speed).
  `kickoff` startet im Gate das Drill statt der Persona (kein `run_stream`);
  `feedback_loop` stößt im Drill NIE die KI an.
- **Speed-Rampe** `tools.tts_speed_for`: 0.7 (Anfang) → linear → 1.0 an der Schwelle.
- **Freischaltung**, wenn ALLE Kern-Wörter durch sind (`GRADUATE_AT=1.0`): der `unlock`-
  Screen erscheint; `Enter` startet dann die
  Persona (`run_stream /api/tutor/start`) → Zimmer. `room_state.mode` kippt parallel
  auf `"room"`; der einmalige `check_graduation`-Meilenstein feuert.

Der alte LLM-`assessment_prompt` (`langs/<lang>/assessment_prompt.md`) bleibt als
Defense-in-Depth im `respond_stream`-Gate, wird aber im deterministischen Fluss nicht
mehr angesteuert. Sprache ohne `core_vocab` (`zh`) → **kein Gate**, sofort Persona.
**LIVE für `es`.**

**Spiel-Schicht (Phase 1, 2026-07) — aus dem trockenen Drill wird ein Spiel.**
Persistiert pro Sprache in `data/<lang>/game.json` (Laufzeit, gitignored):
`coins`, `parts` (erhaltene Lucía-Teile in **Erhalt-Reihenfolge**), `reviews`,
`crates` (Meilenstein-Cursor), `srs` (`{wort:{reps}}`, informativ). Regeln
(`tutor/tools.py`, alle Konstanten dort tunebar):
- **Statusleiste = erstes Wissen.** Das erste korrekte **Abhaken** eines Worts festigt
  es (Backend `confirmed` → `got` +1); weitere korrekte Reviews bewegen die Leiste NICHT
  mehr. **Freischaltung**, wenn ALLE Wörter einmal gewusst wurden (`GRADUATE_AT=1.0`,
  kein 75%-Frühstart). Ziel: schnell eine Working-Memory-Basis; echte Tage-SR dann im
  KI-Gespräch.
- **Session-SR (Frontend, `room.py`) — Due-Time-Scheduler**, KEIN Positions-Insert
  (das driftet). Jede Karte hat `due` = „ab Karten-Zahl `seen` wieder fällig"; `_pick`
  nimmt die fällige mit kleinstem `due` (Review vor Neu bei Gleichstand), neue Wörter
  (`due`=Index) interleaven dazwischen. **Erste Sicht eines Worts** (`shown`-Flag,
  `asv_show`): Übersetzung kommt automatisch (eigener sub=`'first'`) UND ist direkt
  **abhakbar** (kein Auto-Advance) — kennt man's schon, gleich abhaken; sonst Repeat
  (→ sub=`'learn'`, nicht abhakbar, Lapse +3). **Expanding retrieval** (belegt für Kurzzeit-
  Retention, Landauer&Bjork; ~2× wie Anki/Leitner): **Abhaken** (gewusst) → Streak
  hoch, `due=seen+SR_LADDER[streak]` mit `SR_LADDER=(7,14,25)` für 1./2./3. korrekt;
  nach dem 3. Review **graduiert** das Wort aus der Runde. **Repeat** (nicht gewusst) →
  Bedeutung zeigen, danach **nicht abhakbar**, nach `learn_hold≈3 s` automatisch
  `asv_lapse`: `due=seen+SR_LAPSE(3)`, Streak zurück auf 0. **Next** = überspringen →
  `due=seen+SR_SKIP(5)`. Die Abstände sind **Minimums** — bei vielen aktiven Wörtern
  strecken sie sich (1 Slot/Karte), das ist gewollt (nie zu früh = effortful retrieval).
- **Münze NUR zufällig** und **nur beim ERSTEN Abhaken** eines Worts (`COIN_CHANCE=0.35`,
  an `first_known` gekoppelt) — SR-Wiederholungen geben KEINE Münzen (kein Coin-Farming).
- **Kisten** an **distinkten Wort-Meilensteinen** (15/35/50/70, `crate_milestones` mit
  `CRATE_GAPS=(15,20)` abwechselnd) — nur beim ERSTEN Wissen eines Worts, damit die
  Kisten-Symbole exakt auf der Leiste (`got`) sitzen und Wiederholungen keine Kisten
  auslösen. Inhalt **zufällig**: **Körperteil** (`CRATE_PART_CHANCE=0.6`, `random.choice`
  aus den fehlenden → zufällige Reihenfolge) **oder** Münzen. `_open_crate`.
- **Lucía baut sich zusammen** (`_draw_lucia` in `room.py`, aus denselben Primitiven wie
  die Persona): erhaltene Teile schweben aus einer Streu-Richtung (`_PART_SCATTER`)
  herein und rasten ein (`new_part`-Anim); bei Freischaltung ist sie komplett.
  **Münze fällt direkt AM Wort** runter (`coin_drop`, Sasha: nicht nur in der Ecke),
  Münz-Gesamtzähler oben rechts; **Kisten-Symbole auf der Fortschrittsleiste**
  (`_draw_crate_icon`, erreichte golden); Kisten-Reveal-Banner (`_draw_reveal`).
- **Phase 2/3 (offen):** Shop + Küche/Tür-Mechaniken, Etappen + Profil-Quiz.
  Siehe `memory/gamified-assessment-plan.md` (Projekt-Notiz).

**Langzeit-SR fürs GESPRÄCH (FSRS, `tutor/srs.py`).** Klare Arbeitsteilung mit dem
Drill: das Drill baut die Working-Memory-Basis (Abstände in **Karten**); die echte
Tage-Retention läuft über **FSRS** — Ankis aktuellen Open-Source-Scheduler (`fsrs`,
PyPI, **MIT**, pure Python, kein Netz; NICHT selbstgebaut). Bewusst NICHT im Drill
benutzt: FSRS rechnet in **Tagen** (aus Ratings + über Zeit zerfallender Stabilität),
im Sekundentakt einer Session wäre alles „in 1 Tag fällig".
- **Speicher:** `data/<lang>/fsrs.json` `{wort: Card.to_dict()}` (Laufzeit, gitignored).
- **Soft-Import:** fehlt `fsrs` auf einem Knoten → `srs.available()==False`, alle
  Funktionen No-ops, der Tutor läuft normal weiter (nur ohne Langzeit-SR).
- **Anbindung:** (1) **Seed** — erstes Wissen eines Worts im Drill (`first_known` in
  `assessment_answer`) legt eine FSRS-Karte an (`srs.ensure`). (2) **Rating** —
  `increment_correct_use` (Persona-Tool bei korrekter Nutzung) und `mark_known` melden
  ein **„Good"** (`srs.review`) → FSRS terminiert in Tagen neu. (3) **Surfacing** —
  neues Tool **`get_due_reviews`** (Session-Beginn, wie `get_confirmed_vocab`) gibt die
  fälligen Wörter; die Persona baut sie beiläufig ein, kein Test. Alles in der
  Tutor-Sandbox (nur `tutor/data/<lang>/`-Zugriff).
- **API (`tutor/srs.py`):** `ensure(word)`, `review(word, again|hard|good|easy)`,
  `due_words(limit)`, `stats()`, `available()`.
- **Offen / MVP-Grenzen:** kein aktives **„Again"**-Signal aus dem freien Gespräch
  (vergessene Wörter bleiben einfach fällig, statt hart zurückgesetzt zu werden); das
  Ziehen fälliger Wörter hängt daran, dass das Modell `get_due_reviews` aufruft (wie
  bei den anderen Session-Start-Tools). Beides Kandidaten zum Nachschärfen.

**Devtools-Terminal (2026-07).** `scripts/tutor_devtools.py [--url …]` in einem eigenen
Terminal → zeigt LIVE + zeitgestempelt: (1) Snapshot beim Verbinden — komplette
User-Vokabel mit Level (neu/wacklig/fest) + Assessment-Routing (braucht noch Drill?),
(2) jede Vokabel-Statusänderung (`vocab`-Events aus `introduce_new`/`increment_correct_use`/
`mark_known`/`assessment_answer`), (3) den KOMPLETTEN AI-Stream: `ai.req` (voller
System-Prompt + Messages + Tools + Modell — was sie KRIEGT), `ai.out` (ROH-Ausgabe inkl.
versteckter (Regie)/Tool-Leaks — was sie AUSGIBT), `ai.tool` (jeder Tool-Call). Naht:
Ereignisbus `tutor/debug.py` (Ring-Puffer + Subscriber), Snapshot `tools.debug_snapshot`,
SSE-Endpunkt `GET /api/tutor/debug/stream`. `debug.emit()` schluckt jeden Fehler — stört
die echte Logik nie.

**Direkt-Start (kein Enter):** TUI-Taste `u` öffnet **mit `DISPLAY` das
Persona-Zimmer** (`zentrale_tui.tutor_window`, eigenes pygame-Fenster, siehe
unten); **ohne `DISPLAY`** fällt sie auf das Text-Panel zurück
(`zentrale_tui.tutor_open`), das den Status holt und die Persona **sofort**
loslegen lässt, wenn das Backend da ist und keine Session läuft. Das Text-Panel
gibt's immer per `/tutor`. Der Browser (`monolith.html`) startet über `Alt+T`.
`/api/tutor/config` liefert `persona_name`/`country` fürs UI.

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

- **Szene:** Wand + Dielenboden, Fenster (nachts Mond, tags Sonne), Stehlampe mit
  Glühen, Couch, Teppich, Pflanze.
- **Theme an ZENTRALE gekoppelt** (light/dark): `apply_theme(mode)` + zwei Paletten
  (`_NIGHT`/`_DAY`, alle Farben Modul-Globals). `resolve_theme_mode()` liest dieselbe
  Datei wie das Terminal (`~/.config/zentrale/theme`, `auto`→day 5–21 Uhr); ein
  `watch_theme`-Thread pollt alle 3 s, angewandt im Render-Frame (kein Farb-Race).
  Assessment-Screen nutzt semantische Keys (`ASSESS_INK/INK2/PANEL/KEY_INK/BAR_BG/
  NODE`). Sprach-Menü-Modal bleibt fix dunkel. Siehe [[terminal-theme-coupling]].
- **Persona-Sprite** (`Persona`-Klasse, aus pygame-Primitiven, kein Sprite-Sheet):
  läuft rum, **sitzt sich auf die Couch**, blinzelt; kleine Verhaltens-Maschine
  (idle → schlendern → sitzen → aufstehen). Redet sie (SSE läuft), nickt sie
  zugewandt mit Mund-Animation.
- **Stimme:** nach jeder (kurzen) Antwort holt das Fenster die WAV vom Backend-
  TTS (`POST /api/speak`, `lang` aus der Config → zh = sherpa-onnx). Rangfolge in
  `tts_service._try_load_sherpa_zh`: **`matcha-icefall-zh-baker` (22 kHz, beste
  Artikulation) > MeloTTS `vits-melo-tts-zh_en` (44.1 kHz) > `vits-zh-aishell3`
  (8 kHz, telefonig, letzter Fallback)** — geladen wird das beste vorhandene
  Modell. Das Fenster spielt sie über `pygame.mixer` — **der Mund bewegt sich,
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
  Reaktion — `brain.py PRESENCE_DETECTED` → `tutor_port.presence_ping()` (schaut
  hoch, Mimik happy, +Batterie). **Default AN**, per `TUTOR_PRESENCE_REACT=0`
  abschaltbar (`brain.py:36` prüft `!= "0"`) — hier stand bis 2026-07-17 das
  Gegenteil („`=1`, default aus"). Wirkt nur bei bereits **laufender** Session.
  Der Weg geht über den Port, nicht an `tutor.session` vorbei (Regel oben).
  Es STARTET keine Session und macht **keinen** verbalen Auto-Gruß (das bleibt
  bewusst aus — genau der schlechte Auto-Trigger). Details:
  `memory/tutor/tutor_roleplay_features.md` §5.
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
  `NUDGE_AFTER_S` (**90 s** — 25 s war Spam) EIN Cloud-Anstoß
  **`POST /api/tutor/nudge`** → die KI
  reagiert von selbst (schaut/winkt/„在吗？"); der Nudge-Text wird NICHT in der
  History gespeichert. Danach **chillt** sie (client-seitig, kein weiterer Call);
  erst nach `CHILL_RECHECK_S` (15 min) ein neuer Versuch. Eingabe von Sasha setzt
  die Stille-Uhr zurück.

## Spielstände: mehrere Lernstände nebeneinander

Bis 2026-09-04 hatte der Tutor **einen** Lernstand (`tutor/data/<lang>/`). Wer
noch einmal von vorn anfangen wollte, musste Dateien löschen und war den alten
Fortschritt los. Jetzt liegt dazwischen der **Stand**:

```
tutor/data/staende/<id>/stand.json    Name, angelegt, zuletzt gespielt
tutor/data/staende/<id>/<lang>/…      vocab, fsrs, game, persona_mem, …
tutor/data/aktiver_stand              eine Zeile: welcher gerade läuft
```

**Global, nicht pro Sprache.** Ein Spielstand ist *ein Durchgang* — wer neu
anfängt, fängt bei allen Sprachen neu an. Die Sprache wählt man weiterhin
getrennt (`/lang`, Alt+L): sie ist eine Eigenschaft des Spielens, nicht des
Spielstands.

Der Zeiger steht bewusst **nicht** in `tutor_config.json`. Die hält
Sprache/Provider/Modell, also Einstellungen — welchen Spielstand man spielt,
ist keine Einstellung.

**Ein Griff für alle Datenpfade:** `tutor/staende.py`. `memory`, `srs` und
`tools` haben ihren Ordner früher je selbst zusammengesetzt; läge einer davon
daneben, mischten sich zwei Stände still. Alle drei fragen jetzt
`staende.pfad(root, lang)`; ein Test prüft, dass sie beim Wechsel gemeinsam
mitwandern.

**Umzug statt Verlust:** Beim ersten Start nach dem Umbau wandert ein
vorhandener alter Lernstand in einen Stand namens »Erster Anlauf« — je Knoten
einmalig und idempotent. Gemeinsame Ordner (`vocab_images`, `persona_music`)
gehören keinem Stand und bleiben liegen.

**Gewählt wird im Zimmer**, auf dem Willkommens-Schirm unter »Hola, ich bin
Lucía«: die vorhandenen Stände, darunter »Neuer Spielstand«. ↑↓ und Enter,
vorgewählt ist der zuletzt gespielte — Weiterspielen ist ein Tastendruck. Die
Liste wird im Hintergrund geholt, damit das Fenster sofort da ist.

Beim Wechsel wird die laufende Persona-Sitzung beendet: ihr Verlauf liegt im
Speicher, nicht auf der Platte — sonst redete Lucía im neuen Stand mit den
Erinnerungen des alten weiter.

**API** (kein `available()`-Gate, das sind Dateien auf der Platte — den Stand
soll man auch bei gedrosselter Cloud wechseln können):

| Endpoint | Methode | Zweck |
|---|---|---|
| `/api/tutor/staende` | GET | alle Stände + welcher aktiv ist |
| `/api/tutor/staende` | POST | `{name}` → neu anlegen und aktivieren |
| `/api/tutor/staende/waehlen` | POST | `{id}` → umschalten |

## Persona-Memory: der Mitbewohner erinnert sich an dich

Jede Persona hat ein **eigenes Gedächtnis**, getrennt von Sashas privatem
Core-Graphen — **Modul `tutor/memory.py`**:
- **GROB, nicht exakt (Umbau 2026-07-10):** ein Mitbewohner merkt sich *ungefähr*
  ein paar wichtige Dinge, nicht wann genau was gesagt wurde. Darum ist der Store
  **kein** Konzept-Graph mehr (der von der Core-KI kopierte war eh nie gebaut
  worden) und **kein** Wortprotokoll, sondern eine kleine, gedeckelte **Notiz-
  Liste**: `tutor/data/<lang>/persona_mem.json` = `{"facts": [kurze Sätze], "topics":
  [Stichworte]}` (je max 12, auf Chinesisch, keine Zeitstempel). Enthält nur
  Wissen **über Sasha** aus euren Chats — **keine** erfundene Persona-Biografie.
- **Kein persistenter roher Verlauf mehr:** früher lud `activate()`
  `persona_hist.json` Turn-für-Turn — das füllte sich mit „你在吗？"-Nudge-Fillern und
  zog die Persona beim Öffnen in Echo-Schleifen. Jetzt: `_history` ist **reiner
  In-Session-Puffer** (Kohärenz), wird NICHT über Sessions gespeichert. Kontinuität
  kommt allein aus den Grob-Notizen.
- **Loop (`tutor.session.respond_stream`):** vor der Antwort wird der Notiz-Kontext
  („关于 Sasha（只是大概印象…）") an den System-Prompt gehängt; nach einem echten
  Turn destilliert `remember()` im Hintergrund neue Fakten/Themen in die Notizen
  (leichter LLM-Pass, merged + deckelt). Der Öffnungs-/Nudge-Turn wird **nicht**
  gemerkt (ambient, kein Gespräch).
- **Verdichtungs-Backend kapazitätsbasiert** (`tutor.memory.remember` via
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
Backend (lokal Ollama oder Cloud-Key). `tutor/test_memory.py` liegt **auf dem
Notiz-Modell** und prüft zusätzlich Sandbox, Persona-Prompt, Backend-Wahl,
Sprach-Isolation und Secret-Freiheit (die Zeile „ist auf den alten Graph-Store
gemünzt" galt für den Vorgänger `scripts/test_persona_memory.py` und war hier
seit dem Umbau falsch stehengeblieben). Läuft nicht unter pytest
(`testpaths = tests`), sondern von Hand: `venv/bin/python tutor/test_memory.py`.

## Framework: Sprachen + Provider (austauschbar)

Der Tutor ist ein **Sprach-Framework**: Sprachen werden als **Personas**
draufgelegt, der **Anbieter/das Modell ist davon entkoppelt**. Beides wird zur
Laufzeit aufgelöst (`tutor.session._resolve`): Sprache → Profil → Provider →
Modell.

**Module:**
- `tutor/langs/` – **ein Ordner pro Sprache** (`tutor/langs/<code>/`): Profil +
  `prompt.md` (in der Zielsprache) + `prompt.de.md` (Referenz, sieht das Modell
  NIE) + `tool_texts.json` + `expect.json` (Register-Leiter) + `vocab_hint.md` +
  `seeds/`. Im Profil: `reading` (zh=Pinyin, ru=Betonung, ar=Translit, fr/es=—),
  `script` (ar=RTL), STT/TTS-Lang, Default-Provider+Modell.
  **Keine Vokabel-Datei** — die ist LERNSTAND und liegt unter
  `tutor/data/<lang>/vocab.json` (gitignored); `langs/` ist die SPRACHE und wird
  getrackt. Ein `vocab_file`-Feld gibt es im Schema nicht (mehr).
  **LIVE: `zh` (Chinesisch), `es` (Spanisch).** Skizzen (enabled=False,
  stückweise reinziehen): `fr`, `ru`, `ar`. Optional trägt ein Paket einen
  **Kern-Syllabus** `core_vocab.json` (festes Grund-Vokabular, ~75 Wörter) +
  `core_hint`-Template — siehe Kern-Syllabus unten.
- `tutor/providers.py` – **Provider-Registry**. Pro Eintrag: `kind`
  (`ollama` | `anthropic` | `openai_compat`), `base_url`, `key_env`,
  `default_model`, **`trains_on_data`**, `jurisdiction`, `enabled`.
  **LIVE:** `local` (Ollama), `claude` (Sashas Pfad), `qwen` (Verteil-Default).
  Skizzen: `openai`, `mistral`, `groq`, `deepseek`, `gemini`.
- `tutor/openai_compat.py` – **Drop-in für `ai.chat_stream()`**, bedient
  JEDEN OpenAI-`/v1`-kompatiblen Provider (Qwen/DeepSeek/Mistral/OpenAI/Groq/
  Gemini) durch Tausch von base_url+Key+Modell. Die Tools kommen als Parameter
  rein (`tools.tools_for(lang)`) und sind schon OpenAI-Schema → ohne Übersetzung.
  Streaming-Tool-Loop.
- `tutor/cloud.py` – **Anthropic-SDK-Pfad** (Claude), Sashas persönliche
  Verifikation. Übersetzt die übergebenen Tools ins Anthropic-Format.

**Steuerung – lokale Config-Datei (kein `export` nötig):**
- `tutor/data/tutor_config.json` (`tutor/config.py`) hält `lang` / `provider` /
  `model` / `history_window` — **und KEINE API-Keys**. Modell durchprobieren =
  `provider`/`model` dort ändern, neu starten. Vorlage:
  `tutor/data/tutor_config.json.example`.
- **Keys gehören dem Kern**, nicht dem Tutor: `core/ai_config.py` →
  `data/ai_config.json` (`keys`-Block) besitzt sie und injiziert sie in
  `os.environ`, damit die SDKs sie finden. `tutor/config.py` injiziert **nichts**
  mehr (`tutor/test_memory.py` prüft das als Regression). Damit kann ein
  vergessener gitignore-Eintrag unter `tutor/` kein Secret leaken.
- **Sicherheit:** `data/*.json` UND `tutor/data/**/*.json` sind in `.gitignore` →
  weder Keys noch Lernstand wandern ins Repo (verifiziert via `git check-ignore`).
- **Precedence (`config.py:68-82`):** Runtime-Override > Env-Var >
  `tutor/data/tutor_config.json` > `data/tutor_config.json` (Legacy-Fallback) >
  Profil-Default. D.h. `TUTOR_LANG` / `TUTOR_PROVIDER` / `TUTOR_MODEL` /
  `TUTOR_HISTORY_WINDOW` im Terminal übersteuern die Config für ein schnelles
  Einzel-Experiment. Die Legacy-Datei wird nur GELESEN, nie geschrieben.
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
**Cloud-Live steht:** `DASHSCOPE_API_KEY` ist in **`data/ai_config.json`**
(`keys`-Block) gesetzt (Secret, gitignored) → der qwen-Pfad ist startklar
(`provider=qwen`, `model=qwen-plus`, `lang=zh`).

> **Single Source of Truth (Fix 2026-07-17):** Keys werden NUR noch aus
> `data/ai_config.json` injiziert (`ai_config._inject_keys`). Der doppelte
> `keys`-Block in der Legacy-Datei `data/tutor_config.json` ist auf diesem Knoten
> **entfernt**; liegt auf einem anderen Knoten noch einer, wird er **ignoriert
> und beim Start laut angemahnt** (nicht mehr injiziert). Damit gibt es genau
> eine Key-Quelle. Die Switches (`cloud_enabled`/`local_enabled`, kein Secret)
> lesen weiter mit Legacy-Fallback, das hält alte Knoten am Laufen.
>
> **Cross-Node-Rest:** Die Bereinigung des `keys`-Blocks propagiert per rsync
> (newest-wins) auf PC/Pi, sobald wieder gesynct wird — beide Config-Dateien
> syncen. Bis dahin tragen die dortigen Legacy-Dateien evtl. noch einen Key; er
> wird dort ebenfalls ignoriert (die Warnung feuert). Nichts bricht: `ai_config.json`
> syncte seit 2026-07-16 mit und ist die aktive Quelle.

## Position in der Architektur

Tutor ist ein **Addon** auf der Core-AI, nicht der Owner der
Voice-Pipeline. STT (Whisper) und TTS (sherpa-onnx / Piper) leben
zentral in `services/whisper_service.py` und `services/tts_service.py`
und sind sprachneutral nutzbar via `/api/transcribe` und `/api/speak`
(siehe `memory/ki/audio_system.md`). Der Tutor ruft diese Endpoints **als
Aufrufer** auf – er besitzt sie nicht. Die Sprache kommt aus dem aktiven Profil
(`stt_lang`/`tts_lang`), `zh` ist nur der heutige Default, kein Festwert.

Die alten Pfade `/api/tutor/transcribe` und `/api/tutor/speak` sind **entfernt**
(`ui/app.py:1243`) — es gibt nur noch die generischen `/api/transcribe` +
`/api/speak` mit `lang`-Parameter. Diese Datei behauptete bis 2026-07-17, die
Aliase existierten noch.

## Idee

Smalltalk in der Zielsprache mit der KI – mit Spracheingabe (Whisper-STT)
und Sprachausgabe (sherpa-onnx-TTS, zh = bestes vorhandenes Modell:
`matcha-icefall-zh-baker` > MeloTTS > `vits-zh-aishell3`, siehe Persona-Zimmer oben).
Vokabeln kommen aus `tutor/data/<lang>/vocab.json`.

**Zur „80 % bekannt / 20 % neu"-Regel:** die stand hier als Verhalten, ist aber
**nicht** im Live-Prompt. `langs/zh/prompt.md` fordert das Strengere: nur bekannte
Wörter, **höchstens EIN** unbekanntes pro Satz, und dann verpflichtend
`show_thought`. Die 80/20-Formulierung lebt nur noch in Tool-/Pool-Beschriftungen
(confirmed = Festigung, testing = Erweiterung).

## Vokabel-Daten-Modell

Jeder Eintrag in `tutor/data/<lang>/vocab.json` hat:

```json
{ "word": "你好", "reading": "nǐ hǎo", "correct_use": 0, "confirmed": false }
```

- `confirmed: false` → **Testing-Pool** (20 % der Konversation)
- `confirmed: true`  → **Confirmed-Pool** (80 % der Konversation)
- `correct_use` zählt korrekte Verwendungen. Bei
  `correct_use ≥ CONFIRM_THRESHOLD` (= 5, in `tutor/tools.py`) flippt
  `confirmed` automatisch auf `true`.

## Aufbau

### `tutor/tools.py`
- **Sprach-neutrale Mechanik** der Tools + die Sandbox-Allowlist. Definiert
  **nicht** den System-Prompt (der liegt in `langs/<code>/prompt.md`) und **kein**
  statisches `TUTOR_TOOLS` mehr — die Liste baut `tools_for(lang)` pro Aufruf:
  Struktur aus `_TOOL_SPECS`, Beschriftung aus dem Sprach-Paket
  (`tool_texts.json`), deutsche Defaults als Fallback.
- Sprache wird pro Aufruf über `session.active_lang()` aufgelöst, nicht über die
  Config — sonst schriebe ein `/lang`-Wechsel mitten in einer Session in die
  Dateien der falschen Sprache.

### `tutor/session.py`
- Verwaltet eine laufende Session: Zustand, History, Audio-Aufrufe.
- History ist **getrennt** von der Chat-History (sonst vermischen sich
  Lernkontext und allgemeine Konversation).

### Verhältnis zum Chat-Modus

Tutor und Chat nutzen dieselbe `ai.chat_stream()`-Infrastruktur.
Der Unterschied liegt nur in:

- **System-Prompt** — der Tutor nimmt `langs/<code>/prompt.md`. Für `zh` ist das
  ein **chinesischer** Prompt der Persona 玲玲/Ling Ling, ausdrücklich *keine*
  Lehrerin. Der hier früher zitierte deutsche Satz („Du bist Mandarin-Sprachtutor
  für Sasha …") steht **nirgends** im Code — ein deutscher Prompt wäre genau der
  Fehler, der qwen ins Deutsche kippt (`memory/tutor/tutor_persona_tuning.md`).
- **Tool-Set** – im Tutor-Modus sind die Standard-Tools (`save_memory`,
  `read_file`, `list_files`) **deaktiviert** und durch die
  Tutor-spezifischen Tools ersetzt (siehe unten).

Das hält den Code DRY – kein doppelter Streaming-Mechanismus.

## Tutor-Tools

Aktiv nur während einer Tutor-Session (`tools_for(lang)` in `tutor/tools.py`).
Diese **ersetzen** die Standard-Tools (save_memory, read_file, list_files)
während des Tutor-Modus. **15 Stück** (Stand 2026-07-17).

| Tool                      | Argumente              | Funktion                                                                        |
|---------------------------|------------------------|---------------------------------------------------------------------------------|
| `get_confirmed_vocab`     | –                      | Liefert alle Vokabeln mit `confirmed: true` als Prompt-formatierten String      |
| `get_testing_vocab`       | –                      | Liefert alle Vokabeln mit `confirmed: false` + `count`                          |
| `increment_correct_use`   | `word`                 | +1 auf `correct_use`. Bei ≥ 5 → auto-confirmed                                  |
| `introduce_new`           | `word`, `reading?`     | **Neues** Wort in `tutor/data/<lang>/vocab.json` hinzufügen (nicht aus einem Pool wählen) |
| `mark_known`              | `word`, `reading?`     | Wort, das Sasha schon kann, direkt als **confirmed** ablegen (überspringt den Testing-Pool) |
| `express`                 | `action` (Enum)        | Haltung/Geste/Mimik im Zimmer setzen (sit/stand/pace/…/wave/nod/happy/tired…)    |
| `get_structures`          | –                      | Aktuelle Satzmuster/Strukturen im Lernen (Feinmodell, `tutor/data/<lang>/structures.json`)|
| `introduce_structure`     | `pattern`, `note?`     | Neues Satzmuster/„neue Sagweise" einführen                                       |
| `increment_structure`     | `pattern`              | +1 auf ein Muster; ab 3× → „掌握"                                                |
| `show_thought`            | `word`, `meaning?`, `reading?` | Vokabel-Gedanke: Wort + Übersetzung (+ Bild aus `tutor/data/vocab_images/`) im Zimmer |
| `get_local_news`          | –                      | Ein leichtes Landes-Thema (Seed aus `langs/<lang>/seeds/news.json`, rotierend; NIE `core/news.py`)|
| `play_music` / `stop_music`| `mood`                | Musik nach Stimmung aus `tutor/data/persona_music/<mood>/` (Fenster spielt); Content-Lücke|
| `watch_tv` / `turn_off_tv`| `mood`                 | TV an + level-gerechter Titel (Seed aus `langs/<lang>/seeds/tv.json`, Rotations-Cursor in `data/<lang>/tv.json`); Video-Playback deferred |

Logik (laut System-Prompt): wenn `get_testing_vocab` `count < 10`
zurückmeldet → KI soll `introduce_new(word, reading)` aufrufen mit einem
selbstgewählten neuen Wort. Es gibt keinen vorgefertigten Pool.

Die Tools ab `express` sind die **Roleplay-Erweiterung** (2026-07-09, Feature 1–8,
Log: `memory/tutor/tutor_roleplay_features.md`). ALLE fassen nur tutor-isolierte Daten +
UI-State an (Sandbox-Choke-Point `_ALLOWED` in `tutor/tools.py`) — nie die Core-KI.

Zusätzlich existiert in `tutor/tools.py` die Hilfsfunktion `get_vocab_stats()`
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

Siehe `memory/ki/audio_system.md` – das ist der ganze STT/TTS-Stack, der hier
mit dranhängt.
