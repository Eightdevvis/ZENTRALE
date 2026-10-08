# Bauplan der TUI — wie `tui/` geschnitten ist

**Stand 2026-10-07:** Die TUI ist in Ansichten geschnitten. `tui/zentrale_tui.py`
(1.410 Zeilen, vorher 10.013) ist nur noch Einstieg, Store, Hot Reload,
Selbsttest und `run_ui` = Aufbau + Hauptschleife (162 Zeilen, vorher 7.701);
die Schleife ruft `taste_verteilen(u, ch)` und `bild_zeichnen(u)`. Jede
Ansicht ist eine Klasse in `tui/ansichten/` und bekommt ein Kontext-Objekt `z`
statt Closure-Variablen. Keine Funktion und keine Datei in `tui/` ist mehr ein
Riese nach dem Kern-Bauplan ([bauplan_kern.md](bauplan_kern.md)). Gebaut auf
dem Branch `worktree-agent-ac95c51a142500eaa`; Verhalten unverändert (Tests +
Bildschirm-Vergleich, siehe unten).

## Warum

Sasha, 05.10.2026: *„ich will nich dass wir irgendwann an einen punkt kommen
an dem der code unwartbar wird und alles um die ohren fliegt!"* Die TUI ist
die am häufigsten geänderte Datei (46 Commits seit August). In einer
7.700-Zeilen-Funktion sah man nicht, wer welchen Zustand anfasst: jede
Closure konnte jede Variable von `run_ui` lesen, und nichts sagte, welche sie
wirklich braucht. Als Nächstes sollen Claude-Web-artige Chat-Funktionen ins
Chat-Panel — dafür musste der Chat ein eigenes Modul werden, in das man
hineinbauen kann, ohne den Rest zu lesen.

## Wo was wohnt

| Modul | Was | Zustand |
|---|---|---|
| `tui/zentrale_tui.py` | `main()`, `Store` (Poller), Hot Reload, Lebenslauf, Weglegen, Selbsttest, Lauf-/Dashboard-Wunsch (Dateien), Zustand der Räder; `befehl_ausfuehren`, `taste_verteilen`, `bild_zeichnen`, `run_ui` | `RAD`, `META`, `TRAD`, `PEER`, `RELOAD`, `ENDE`, `NEUSTART` |
| `ansichten/basis.py` | `BASE_URL`, `api_call`, `venv_python`, `PROJEKT`, `BEENDEN`, Uhrzeit-Helfer | — |
| `ansichten/farben.py` | Rollen und Paletten Tag/Nacht | — |
| `ansichten/kontext.py` | `Kontext`: stdscr, store, Farben `C`, Pixel-Paare `PIX`, Theme, `safe_addstr`/`addclip`/`draw_box` | `C`, `PIX` |
| `ansichten/text.py` | Umbruch, Markdown (Chat, Tutor, Post) | — |
| `ansichten/chat.py` | `Chat`: KI-Chat, Stream, Erlaubnis-Frage, Verlauf-Poll, Auge | `AI` |
| `ansichten/eingabe.py` | Eingabefeld des Chats als reine Funktionen: Cursor, Umlaute (UTF-8-Bytes), Alt+Enter, Umbruch/Scrollen der Anzeige | — |
| `ansichten/chat_befehle.py` | Slash-Befehle im Chat lesen (`/neu`, `/modell` …), Hilfe-Text | — |
| `ansichten/chat_gespraeche.py` | Mixin `GespraechsSteuerung` des Chats: neu, öffnen, umbenennen, archivieren, wiederholen, bearbeiten, Verlauf laden, Poll; `verlauf_aus` (History → Verlaufszeilen) | (in `AI`) |
| `ansichten/ablage.py` | `Ablageliste`: Überlagerung im Chat-Kasten (`/ablage`), Liste + Lesen eines Dokuments; reine Helfer `listen_zeilen`, `lese_zeilen` | `AI["ablage"]` |
| `ansichten/chat_ablage.py` | Mixin `AblageSteuerung` des Chats: `/anhang` (Datei lesen, an `/api/anhang`), „▤"-Zeilen, Enter auf das neueste Dokument | `AI["anhaenge"]` |
| `ansichten/chat_layout.py` | Aufteilung des Chat-Kastens wie Claude Web (Skizze im Kopf): `aufteilen` → Seitenleiste / Symbolspalte / Mitte / rechts, `spalte` (Textspalte mittig ≤ 92), `seite_auto` | — |
| `ansichten/chat_zeichnen.py` | Mixin `ChatZeichnen`: `draw_ai` (Leiste, Kopf „Titel ▾ … ▤ n", Verlauf, Fuß, Eingabekasten, „+ attach … Modell · Effort"), Klickflächen, Denk-Adern im Verlauf, Auge im leeren Chat | `AI["fokus"]` … |
| `ansichten/chat_bedienung.py` | Mixin `ChatBedienung`: Fokus (F6), Tab = Gespräche auf/zu, Ziele im Verlauf (auf/zu, copy, retry, Dokument), Strg-Tasten, Maus, Zwischenablage | — |
| `ansichten/verlauf.py` | Verlauf als Zeilen aus Stücken (text, stil, ziel): Nutzer rechts abgesetzt, „Used memory ›", Denken eingeklappt, copy · retry; `benutzt` für „Used in this session" | — |
| `ansichten/seitenleiste.py` | `Seitenleiste`: Menü (Search, New, Projects, Files, Customize) mit Symbolen (Braille, 2 Zeilen), Gespräche nach Today/Yesterday/Datum; zugeklappt eine Symbolspalte | `AI["seite"]`, `AI["seite_menu"]` |
| `ansichten/rechts.py` | `Rechts`: Dokument neben dem Verlauf (▾ Fassungen, ⤢ groß, × zu) und „Outputs" (Kärtchen + „Used in this session") | `AI["rechts"]`, `AI["gross"]` |
| `ansichten/einstellungen.py` | `Einstellungen` („Customize"): Skills, Memory, Usage, Capabilities, Permissions, Model | `AI["einstellungen"]` |
| `ansichten/denkadern.py` | Denk-Animation als reine Funktion `adern_zellen(t, dauer, breite, hoehe, thema, ausklang)` | — |
| `ansichten/symbole.py` | Symbole der Seitenleiste als Braille, 4×2 Felder = 8×8 Punkte (`BILDER`, `codieren`, `symbol_zellen`) | — |
| `ansichten/maus.py` | Maske, `deuten`, `treffer`, `rad_treffer`; warum Markieren im Terminal heil bleibt | — |
| `ansichten/gespraechsliste.py` | `Gespraechsliste`: Überlagerung im Chat-Kasten (Tab/`/liste`); reine Helfer `alter_text`, `filtern`, `listen_zeilen` | `AI["liste"]` |
| `ansichten/gedaechtnis.py` | `Gedaechtnis`: Überlagerung im Chat-Kasten (`/gedaechtnis`, `/skills`) — Kernakten, Bereiche, Skills; Kernakte im Editor ändern, Skill an/aus; reine Helfer `reiter`, `inhalt_zeilen`, `naechster_status`, `editor_befehl` | `AI["gedaechtnis"]` |
| `ansichten/projekte.py` | `Projekte`: `/projekt` (Auswahl, zuordnen, anlegen, lösen) und die Übersicht `/projekte` als Überlagerung im Chat-Kasten — Projekte, ein Projekt im Einzelnen (Anweisungen, Wissen, Gespräche), Anweisungen im Editor, Wissen per Pfad; reine Helfer `projekt_name`, `finden`, `wahl`, `liste_zeilen`, `detail_zeilen` | `AI["projekte"]`, `AI["projekt"]` |
| `ansichten/sprachtutor.py` | `Sprachtutor`: Text-Panel, Zimmer-Fenster | `TUTOR` |
| `ansichten/post.py` | `Post`: Mail, Antwort-Editor, Mail-Worker | `MAIL` |
| `ansichten/kalender.py` | `Kalender`: seit 07.10.2026 nur noch Rahmen für A/B/C (`v` dreht), zeichnet die gewählte Ansicht; der alte Woche/Monat-Kalender mit Formular und Seitenliste ist raus | `K` |
| `ansichten/kalender_ansichten.py` | Entwürfe A/B/C als reine Funktionen (Daten rein → Zeilen raus, kein curses); alle drei bedienbar, markieren die Auswahl per Identität (`t["roh"] is …`), siehe [kalender_ansichten_vorschau.md](../werkzeuge/kalender_ansichten_vorschau.md) | — |
| `ansichten/kalender_beispiel.py` | Beispieltermine für Tests und `scripts/kalender_vorschau.py` | — |
| `ansichten/kalender_werkzeuge.py` | Bearbeiten wie calcurse als reine Logik: Eingaben lesen (Zeit, Dauer, Datum, Wochentage), Formular (Modal) zum Anlegen/Ändern, kurze Rückfragen, daraus Backend-Aufrufe; Auswahl in derselben Reihenfolge wie die Ansicht | — |
| `ansichten/kalender_bedienung.py` | `Bedienung`: Tasten von A/B/C (EINE Auswahl Tag/Termin/Kasten, Kästen ausführen, Kollisions-Rückfrage, Modal und Ansehen-Fenster zeichnen) | `K["w"]` |
| `ansichten/graphen.py` | `Graphen`: Graph-Werkzeug, Überlagerung (auch lifestyle-Box) | `G` |
| `ansichten/fokus.py` | `Fokus`: Listen-/Fokus-Werkzeug, Bernsteinleiste, `proj_render` | `L` |
| `ansichten/notizen.py` | `Notizen`: Notiz-Werkzeug | `NOTE` |
| `ansichten/klavier.py` | `Klavier` + Klaviatur-Geometrie (`piano_*`) | `PIANO` |
| `ansichten/karte.py` | `Karte`: Weltkarte, Overlays, Länder-Fokus | `M` |
| `ansichten/technik.py` | `Technik`: external, telemetrie, stdout (Laufschrift), outbound | `TECH` |
| `ansichten/startseite.py` | `Startseite`: Rad, Galaxie + ihre Geometrie | liest `RAD`/`META`/`TRAD` |
| `ansichten/dashboard.py` | `Dashboard`: rechte Spalte des alten Dashboards | — |
| `ansichten/befehle.py` | Befehle, `TUI_KEYS`/`CTX_KEYS`, `Befehlszeile` | `cmd_mode` … |
| `ansichten/fussleiste.py` | Tastenzeile ganz unten: `eintraege(u)` (wer hat den Fokus → welche Tasten), `zeile`, `text`, `codes` (Beschriftung → Tastencodes, für den Test) | — |
| `ansichten/erinnerung.py` | `Erinnerung`: Graph-Reminder-Kästchen | `nag_*` |
| `ansichten/fenster.py` | `in_text_entry(z)`, `current_ctx(z)`: wer hat den Fokus | — |

## Wie eine Ansicht gebaut ist (und eine neue gebaut wird)

- **Eine Klasse, ein Zustands-Dict.** `Chat(z)` legt `self.AI` an und hängt
  es auch an den Kontext (`z.AI`), weil `fenster.py` und die Hauptschleife
  wissen müssen, wer den Fokus hat. Interne Dinge (Locks, Queues) bleiben am
  Objekt, nicht am Kontext.
- **Schnittstelle zur Schleife:** `oeffnen()` (was die Startseite beim Öffnen
  tut), `taste(ch)` (gibt `BEENDEN` zurück, wenn die TUI enden soll — 'q'),
  `draw_*`-Methoden, ggf. `start()` für Hintergrund-Threads (Chat-Poll,
  Mail-Worker). Eine neue Ansicht braucht dazu je eine Zeile in
  `taste_verteilen`, `bild_zeichnen`, `fenster.py` und der Startseite.
- **Kopfzeilen.** Die Methoden sind die alten Closures mit unverändertem
  Rumpf; die erste Zeile holt, was die Methode von außen braucht:
  `AI, AI_LOCK, ai_stream = self.AI, self.AI_LOCK, self.ai_stream`. Das hielt
  den Umbau reviewbar und zeigt die Abhängigkeiten, die vorher unsichtbar
  waren. Neuer Code darf direkt `self.`/`self.z.` schreiben.
- **Reine Helfer** ohne Zustand sind Modul-Funktionen — ohne curses testbar.
- **Nie `import zentrale_tui`** aus einer Ansicht: als Skript gestartet heißt
  die Datei `__main__`, ein Import lüde sie ein zweites Mal mit eigenem
  `RELOAD`/`ENDE`/`RAD`, und Hot Reload oder `/quit` liefen ins Leere. Was von
  dort gebraucht wird, kommt über den Konstruktor oder `z`
  (`tests/test_tui_ansichten.py` prüft das).
- **Nie `__file__` für Pfade:** eine Ansicht liegt eine Ebene tiefer als
  `zentrale_tui.py`; Projekt-Pfade kommen aus `basis.PROJEKT` (auch geprüft).
- **Importe:** innerhalb von `ansichten/` relativ (`from .basis import …`),
  `pixel` per `try: from tui import pixel / except ImportError: import pixel`.
  So läuft beides, Skript (`python tui/zentrale_tui.py`) und Paket (Tests).
- **Türen:** auch Ansichten dürfen aus `core/` nur `theme`, `tone`,
  `pc_status` (Kern-Bauplan, der Test scannt `tui/` rekursiv).
- **Keine Riesen:** Methode ≤ 250, Datei ≤ 1.500 Zeilen. Beim Umzug wurden
  `draw_calendar` (432), `draw_overlay` (499), `draw_list_tool` (259) und der
  Listen-Tasten-Zweig (369) in Abschnitte geteilt (`_kal_*`, `_overlay_*`,
  `_bernstein`, `_taste_*`).

## Was beim Schneiden auffiel

- **Kein einziges `nonlocal`** in `run_ui`: aller geteilte Zustand lief über
  Dicts. Deshalb ging das mechanisch — ein Dict wandert als Attribut mit,
  wer es braucht, bekommt dieselbe Referenz.
- **Hot Reload** sah nur `tui/*.py`. Jetzt `code_dateien()` rekursiv (ohne
  `__pycache__`), sonst lüde eine geänderte Ansicht nicht neu. Ende-zu-Ende
  geprüft: eine Änderung in `ansichten/chat.py` lädt neu, das Rad bleibt stehen.
- **Aussenposten:** `deploy/aussenposten.txt` fehlte `tui/pixel.py` — die
  TUI wäre auf dem Pi beim Import gestorben. Jetzt dabei, plus `tui/ansichten/`;
  ein Test hält die Liste vollständig.
- Der Klavier-Kommentar stand zwischen ELEK und TECH (beim Einbau der
  Elektronik dazwischengerutscht) und steht wieder über `PIANO`.

## Sicherheitsnetz (wie verifiziert wurde)

- `pytest` komplett nach jedem Schritt, dazu `tests/test_tui_fuzz.py` (echte
  TUI im PTY, tausende Zufallstasten in alle Ansichten — ein `NameError`
  fällt dort als Frame-Fehler auf) und einmal 40 Sitzungen × 3.000 Tasten.
- **Bildschirm-Vergleich** (`tests/tui_schirm/`): die TUI läuft in tmux
  (eigener Socket, 150×46) gegen ein Aufzeichnen-und-Abspielen-Backend —
  GETs einmal vom laufenden Backend geholt und eingefroren (Cache außerhalb
  des Repos, persönliche Daten), POST/PUT/DELETE beantwortet es selbst mit
  `{}`, Mail-Bodies und Reminder sind erfunden. Uhr eingefroren per
  `sitecustomize` (Wanduhr und `time.monotonic` der TUI; threading und
  Sockets behalten die echte Uhr). 30 Tastenwege mit 176 Mitschnitten durch alle Ansichten,
  mitgeschnitten mit `capture-pane -e`, verglichen Zelle für Zelle (Zeichen
  + sichtbare Farbe). Zwei Läufe desselben Codes ergeben dasselbe Bild; nach
  jedem der 16 Schnitte war es gleich.
- Beim Schneiden selbst: AST-Vergleich jedes verschobenen Rumpfs mit dem
  Original (ohne Kopfzeile) und eine Prüfung auf unaufgelöste Namen.
- `tests/test_tui_ansichten.py` (Hot Reload rekursiv, Aussenposten-Liste,
  keine Ansicht importiert `zentrale_tui`, `PROJEKT`, Zeichen-Primitive) und
  `tests/test_tui_teile.py` (Befehlszeile, Reminder) halten das Neue fest.

## Chat: Eingabe, Stoppen, Befehle (seit 2026-10-07)

Claude-Web-Plan Phase 1 ([../ki/claude_web_plan.md](../ki/claude_web_plan.md)
Abschnitt 7). Was für die TUI gilt:

- **Tasten im Chat:** Enter schickt, Alt+Enter = neue Zeile, ←→ Pos1 Ende
  (Strg+A/E) ⌫ Entf am Cursor. **↑↓-Regel:** ohne Zeilenumbruch in der
  Eingabe scrollen sie den Verlauf (wie vorher), mit Zeilenumbruch bewegen
  sie den Cursor — der Verlauf geht dann mit Bild↑↓. Esc: offene Auswahl/
  Erlaubnis-Frage: abbrechen/ablehnen; sonst zu — seit der Durchsicht auch
  während einer Antwort (sie läuft weiter); Stoppen ist Strg+C (unten).
- **Esc vs. Alt:** `Chat._esc_lesen` wartet nach ESC 50 ms auf Folgetasten
  (wie `karte.m_alt_arrow`); allein → Esc, + Enter → Alt+Enter, sonst
  nichts. Die Deutung ist `eingabe.esc_folge` (testbar).
- **Umlaute:** die Hauptschleife bleibt bei `getch` (alle Ansichten rechnen
  mit Ganzzahlen); der Chat setzt UTF-8-Bytes in `eingabe.utf8_byte`
  zusammen, wie der Post-Antwort-Editor.
- **Cursor** zeichnet `draw_ai` selbst (invers), `curs_set` bleibt 0.
- Die Tastenzeile ganz unten liefert `Chat.tasten()`, solange der Chat
  den Fokus hat (seit 2026-10-07, siehe „Fußleiste"). Esc/Strg+C und die
  englischen Befehle: „Nachbesserungen nach Sashas Durchsicht".
- Headless geprüft mit `tests/tui_schirm/lauf.py` (Szenarien `ki_eingabe`,
  `ki_befehle`; Größe per `ZTUI_GROESSE=80x24`), das Abspiel-Backend liefert
  dafür erfundene Einstellungen.

## Chat: Gespräche (seit 2026-10-07)

Claude-Web-Plan Phase 2 ([../ki/gespraeche.md](../ki/gespraeche.md)). Was
für die TUI gilt:

- **Gesprächsliste** = seit dem Claude-Web-Umbau die Seitenleiste (siehe
  „Chat wie Claude Web"); bis dahin eine Überlagerung im Kasten. Öffnen: **Tab bei leerer Eingabe** (mit
  Text bleibt Tab ein Leerzeichen) oder `/liste`. In der Liste: ↑↓ Bild↑↓
  wählen, Enter öffnen, `n` neu, `r` umbenennen (Feld im Fuß), `a`
  archivieren (im Archiv: zurückholen), `z` Archiv zeigen/zurück, `/` filtert
  nach Titel (Enter fertig, Esc Suche weg), Esc/Tab schließt. Filtern startet
  mit `/`, weil r/a/n/z sonst zugleich Befehl und Suchbuchstabe wären.
  Zeile: Zeiger, ● ungelesen bzw. · offenes Gespräch, Titel, Alter rechts
  („vor 2 Std.", „gestern", „28.08.").
- **Befehle**: `/neu`, `/liste`, `/titel [text]`, `/archiv` (dieses ins
  Archiv, dann neues), `/wiederholen`, `/bearbeiten` (letzte eigene Nachricht
  in die Eingabe; Enter ersetzt ab dort, Esc bricht ab), `/denken`.
- **Denken**: eingeklappt eine Zeile „▸ gedacht (1 234 Zeichen)" über der
  Antwort, **Strg+D** (oder `/denken`) klappt alle auf/zu.
- **Kasten-Titel** zeigt den Gesprächstitel (`Chat.ai_titel(breite)` kürzt
  ihn zuerst, Kern und Kosten bleiben).
- **●** im Kasten-Titel und auf der Startseite: etwas Ungelesenes in einem
  Gespräch, das gerade nicht vor Sasha liegt (meist „Erinnerungen"). Beim
  Öffnen des Chats steht dann ein Hinweis in der Statuszeile.
- **Laden**: jedes Öffnen des Chats lädt das aktive Gespräch im Hintergrund
  neu; der Poll (20 s) holt die Liste und lädt das offene Gespräch nach, wenn
  dort etwas dazukam (anderer Rechner, Erinnerung).
- Headless: Szenario `ki_gespraeche` in `tests/tui_schirm/lauf.py` (das
  Abspiel-Backend liefert erfundene Gespräche); ohne Bildschirm:
  `tests/test_gespraechsliste.py`.

## Chat: Gedächtnis (seit 2026-10-07)

Claude-Web-Plan Phase 3 ([../ki/gedaechtnis_dateien.md](../ki/gedaechtnis_dateien.md),
„Für Sasha sichtbar und änderbar"). Was für die TUI gilt:

- **Überlagerung im Chat-Kasten** wie die Gesprächsliste, geöffnet mit
  `/gedaechtnis` (auch `/gedächtnis`, `/memory`) oder `/skills` (dann gleich
  bei den Skills). Im Chat-Code nur fünf Haken (Konstruktor, `befehl`,
  `taste`, `draw_ai`, `fusszeile`); alles andere steht in `gedaechtnis.py`.
- **Abschnitte** hausregeln · steckbrief · ziele · bereiche · skills in einer
  Leiste oben (zu schmal → nur der gewählte als „‹ name › n/5"). ←→ oder
  Tab/Shift+Tab wechseln, 1–5 springen, ↑↓ Bild↑↓ blättern, `r` neu laden,
  Esc zurück zum Chat.
- **Kernakte ändern:** `e` oder Enter → `curses.def_prog_mode` + `endwin`,
  Editor auf einer Zwischendatei (`$VISUAL`, `$EDITOR`, sonst nano, sonst
  vi), danach `reset_prog_mode` und neu zeichnen; unverändert → nichts
  geschickt; sonst `PUT /api/gedaechtnis/<akte>` mit `stand`. Scheitert das
  (409, keine Verbindung), bleibt die Zwischendatei liegen und die
  Statuszeile nennt ihren Pfad.
- **Skills:** ↑↓ wählen, Enter/Leertaste schaltet an ↔ aus (vorgeschlagen →
  an). Zeile: `● name … an · von dir` (○ aus, ◌ vorgeschlagen; Herkunft
  auch „von anthropic", „mitgeliefert" für ZENTRALEs eigene wie import-memory), darunter die Beschreibung (2 Zeilen) und, falls da,
  `braucht: …` / `hinweis: …` (seit 2026-10-07); auf breiten Schirmen
  höchstens 64 Spalten, damit der Status beim Namen bleibt.
- **Nicht im Rad:** ein Rad-Platz braucht ein Pixel-Symbol, eine Taste und
  verschiebt die gespeicherte Rad-Stellung (`ZENTRALE_TUI_RAD`); offen, ob
  Sasha es dort will.
- Headless: Szenario `ki_gedaechtnis` in `tests/tui_schirm/lauf.py` (das
  Abspiel-Backend liefert ein erfundenes Gedächtnis, der „Editor" ist ein
  Skript, das eine Zeile anhängt); ohne Bildschirm:
  `tests/test_gedaechtnis_ansicht.py`.
## Chat: Ablage und Anhänge (seit 2026-10-07)

Claude-Web-Plan Phase 5 ([../ki/ablage.md](../ki/ablage.md)). Was für die TUI gilt:

- **`/ablage`** öffnet die Liste als Überlagerung im Chat-Kasten (wie die
  Gesprächsliste): ↑↓ Bild↑↓, Enter lesen, `a` archivieren / zurückholen,
  `z` Archiv, Esc zu. **Lesen** ebenfalls im Kasten, mit `md_zeilen` (Code und
  CSV wörtlich): ↑↓ Bild↑↓ Leertaste Pos1 Ende, ←→ Fassungen, Esc eine Stufe
  zurück. Kein externer Pager (curses verlassen + neu aufbauen, und auf dem
  Pi-Kiosk liegt kein less hinter dem Bild).
- **Im Verlauf**: SSE `ablage` → Zeile „▤ Titel — enter öffnet" (Log-Rolle
  `ablage`, Text `id⇥titel`). Nur das neueste öffnet Enter bei leerer
  Eingabe, ältere zeigen „— in /ablage".
- **`/anhang <pfad>`**: die TUI liest die Datei selbst (Tunnel!), schickt sie
  im Hintergrund an `/api/anhang`, merkt die id vor; die Statuszeile zeigt
  wartende Anhänge, Senden nimmt sie mit („▤ anhang: name" unter der
  Nachricht). Lehnt `/api/chat` ab (Bild ohne Cloud), bleiben sie vorgemerkt.
- Chat-Haken in `chat.py`: Event `ablage`, Befehle, Tasten- und Zeichen-
  Weiche, Enter-Sonderfall, Anhänge im Body — alles Weitere in den zwei Modulen.
- Headless: Szenario `ki_ablage` in `tests/tui_schirm/lauf.py` (erfundene
  Ablage im Abspiel-Backend); ohne Bildschirm: `tests/test_ablage_tui.py`.

## Chat: Projekte (seit 2026-10-07)

Claude-Web-Plan Phase 6 ([../ki/projekte.md](../ki/projekte.md)). Was für
die TUI gilt:

- **`/projekt`** ohne Argument: Auswahl im Fuß (wie `/modell`) — die
  Projekte, „kein projekt", „neues projekt …" (schreibt `/projekt neu ` in
  die Eingabe). Die Auswahl bringt ihre Aktion mit (`wahl["aktion"]`, sonst
  wie bisher `setzen`). `/projekt <name>` ordnet direkt zu (Name oder id,
  Groß/klein egal), `/projekt neu <name>` legt an und ordnet zu,
  `/projekt kein` (auch `aus`) löst. Ohne offenes Gespräch (nach `/neu`) gilt
  es für das nächste neue.
- **`/projekte`**: Überlagerung im Chat-Kasten. Liste: ↑↓ Enter, `n` neues
  Projekt (Name im Fuß), `a` archivieren/zurückholen, `z` Archiv, Esc zu. Ein
  Projekt: Anweisungen, Wissen (Name + Größe), Gespräche (auch archivierte);
  ↑↓ Gespräch, Enter öffnet es, `n` neues Gespräch in diesem Projekt, `e`
  Anweisungen im externen Editor (wie die Kernakten: Zwischendatei,
  `stand`, 409 lässt sie liegen), `w` Wissen per Pfad (`~` geht), `r` neu
  laden, Esc zurück. Listen-Zeilen höchstens 64 Spalten breit.
- **Kasten-Titel** „ki-chat · Projekt · Gespräch" (`AI["projekt"]`, aus der
  Gesprächsliste: `projekt_name`, ohne Gespräch `neu_projekt`).
  **Gesprächsliste**: Projektname vorn an der Zeile („Geige · Partita …"),
  `/`-Suche findet auch den Projektnamen.
- `/neu` aus einem Projekt bleibt im Projekt (Backend), die Statuszeile sagt
  „neues gespräch im projekt „…"".
- Im Chat-Code nur Haken (Konstruktor, `befehl`, `taste`, `draw_ai`,
  `fusszeile`, `ai_titel`, `_taste_wahl`); alles andere in `projekte.py`.
- Headless: Szenario `ki_projekte` in `tests/tui_schirm/lauf.py` (erfundene
  Projekte im Abspiel-Backend); ohne Bildschirm:
  `tests/test_projekte_ansicht.py`.

## Chat: Erlaubnis mit Geltung, /permissions, /model mit Filter (seit 2026-10-07)

- Die Erlaubnis-Frage zeigt die Knöpfe aus dem Backend („1) ja, nur dieses
  mal 2) ja, für dieses gespräch 3) ja, immer 4) nein"); j/n/Ziffer/Esc wie
  bisher — kein neuer Code in `chat.py`, die Knöpfe kamen schon als
  `optionen`. Regeln: `memory/ki/ki_system.md`, „Geltungsbereiche".
- `/permissions` (früher `/erlaubnis`, `tui/ansichten/chat_erlaubnis.py`, Mixin
  `ErlaubnisSteuerung`): listet im Verlauf, was ohne Frage erlaubt ist, und
  öffnet eine Auswahl zum Zurücknehmen.
- `/model` bekommt alle Modelle der Anbieter; die Auswahl hat dann
  `alle` + `filter`: Tippen filtert (alle Wörter müssen vorkommen), ⌫ nimmt
  zurück, Ziffern gehören zum Filter, Titel „· n von m · filter: …"
  (`chat.wahl_filtern`, `_taste_wahl`, `_fuss_wahl`).
- Headless: Szenario `ki_erlaubnis` in `tests/tui_schirm/lauf.py`; zwei Läufe
  gleichzeitig brauchen `ZTUI_SOCK` und `ZTUI_PORT` je Lauf. Ohne
  Bildschirm: `tests/test_erlaubnis_tui.py`.

## Nachbesserungen nach Sashas Durchsicht (2026-10-07)

- **Esc schließt den Chat immer**, auch während einer Antwort — sie läuft im
  Hintergrund weiter; wird sie fertig, während das Fenster zu ist, steht ● an
  der Leertaste der Startseite (`AI["fertig_ungesehen"]`, `Chat.ungelesen()`;
  eigenes Feld, weil der Poll `neu` alle 20 s neu rechnet). Esc bricht zuerst
  noch `/edit`, eine Auswahl oder eine Überlagerung ab (eine Stufe zurück).
- **Strg+C stoppt** eine laufende Antwort. Vorgefunden: `curses.wrapper` fährt
  cbreak, Strg+C war SIGINT → `KeyboardInterrupt` → `main()` beendete die TUI
  („ENDE ctrl-c"), auch mitten im Chat. Jetzt `curses.raw()` in `run_ui`:
  Strg+C kommt als Zeichen 3. `taste_verteilen`: hat der Chat den Fokus, geht
  es an ihn (stoppt; ohne Antwort nur ein Hinweis — **nie** Ende); sonst
  wirft es `KeyboardInterrupt` wie früher, `main()` beendet sauber.
  Nebenwirkung von raw: Strg+Z und Strg+Backslash wirken nicht mehr.
- **`\` + Enter** = neue Zeile (wie die Shell), `\\` + Enter = ein `\` und
  senden; nur am Zeilenende (`eingabe.enter_deuten`). Alt+Enter bleibt.
- **Eingabe-Grenze 20 000** (`eingabe.GRENZE`), ab 80 % Zähler rechts in der
  Info-Zeile, an der Grenze fett „grenze erreicht — nicht mehr platz · N
  zeichen nicht übernommen · 20 000 / 20 000" (`AI["zu_viel"]`).
- **Einfügen als Stoß** (`Chat._stoss`): was gleich hinter einem Zeichen im
  Puffer liegt, wird in einem Rutsch gelesen (vorher ein ganzes Bild pro
  Byte, und ein Zeilenumbruch im Eingefügten schickte ab). Enter mitten im
  Stoß = neue Zeile; ein Stoß unter 10 Zeichen, der mit Enter endet, schickt
  ab (schnell getippt).
- **Englische Befehle** im Chat (`/new /chats /rename /archive /retry /edit
  /thinking /memory /files /attach /project /projects /model /provider /local
  /help`; `/effort /budget /skills /cloud /auto` bleiben; `/permissions` ist
  für die Erlaubnis-Seite reserviert). Die deutschen gehen still weiter
  (`chat_befehle.ANDERE_NAMEN`), innen heißen die Befehle wie vorher
  (`chat_befehle.INNEN`). `/project new <name>`, `/project none`.

## Chat wie Claude Web (seit 2026-10-07)

Sasha: „das frontend für unsere ki soll lowk auch einfach claude web grad
kopieren. natürlich in der tui und ihrem eigenen kantigeren stil … nur dass
man halt mit maus UND tastatur navigieren könnte." Vorlagen:
`claude_web_template/*.png` im Haupt-Checkout. Der Kasten bleibt („der kasten
in der mitte is basically vollbild lass das so"), aufgeteilt wird sein
Inneres (Skizze: `chat_layout.py`).

- **Seitenleiste links** (`seitenleiste.py`): Search, New, Projects, Files
  (= Ablage), Customize, darunter die Gespräche nach Today / Yesterday /
  Datum, ● ungelesen, ▤ bei Gesprächen mit Dokument,
  Projektname davor. **Tab** (leere Eingabe) klappt auf und gibt ihr den
  Fokus, Tab klappt zu; Esc gibt den Fokus an die Eingabe zurück. Von selbst
  offen erst ab 127 Spalten (`seite_auto`), sonst eine Spalte Symbole. Die
  Gespräche selbst (Suche, umbenennen, Archiv) macht weiter
  `Gespraechsliste` mit `AI["liste"]` — nur nicht mehr als Überlagerung.
  **Symbole** (seit 2026-10-08, Sasha nach Bildvergleich): Braille-Punkte,
  4 breit × 2 Zeilen hoch = 8×8 Punkte (Regel und Warum in
  [pixelstil.md](pixelstil.md)). Offen: Einträge zweizeilig, Beschriftung
  auf der oberen Zeile; zugeklappt eine Spalte von 6 (1 Rand + 4 + 1).
  Ohne 256 Farben oder mit `ZENTRALE_PIXEL=half` dieselben Zeichen in der
  Schriftfarbe. Die Zwischenstufe (Sextanten oder ein Zeichen, umschaltbar
  über `tui_symbole` / Customize → Appearance) ist wieder raus. Headless:
  Szenario `ki_symbole`; Bild wie im Terminal: `scripts/icon_probe.py`.
- **Verlauf** (`verlauf.py`): Antworten ohne „ki:", Sashas Nachrichten rechts
  auf eigener Fläche, Schritte „Used memory ›" (Enter/Klick: Name,
  Argumente, Ergebnis gekürzt — das Backend speichert seit 07.10. 300
  Zeichen des Ergebnisses), Denken „▸ thought · n chars" (Strg+D alles,
  Enter/Klick eins), unter jeder Antwort „copy", unter der letzten auch
  „retry". **👍/👎 bewusst nicht**: das Backend kennt keine Bewertung, ein
  Knopf ohne Wirkung wäre gelogen. Kopieren: wl-copy/xclip/xsel, sonst liegt
  der Text in `~/.cache/zentrale/kopie.txt` (nur für Sasha lesbar) und die Statuszeile sagt es.
- **Eingabekasten**: Rahmen (Fokus = Akzentfarbe), Platzhalter „Reply",
  Anhänge als `[▤ name]` darüber, darunter „+ attach" und rechts Modell ·
  Effort (Klick oder Strg+P / Strg+T öffnet die vorhandene Auswahl).
- **Rechts** (`rechts.py`): ein Dokument aus der Ablage (Enter/Klick auf
  „▤ Titel ›", Kärtchen) steht neben dem Verlauf (ab 96 Spalten Platz rechts
  der Seite), sonst ersetzt es ihn; `f` groß, `v` oder ▾ Fassung, Esc/× zu.
  **Outputs** (Strg+O, „▤ n" oben rechts): Kärtchen der Dokumente dieses
  Gesprächs + „Used in this session" aus den Schritten.
- **Customize** (`einstellungen.py`, `/customize`, Menü links): Skills
  (an/aus, Beschreibung, Herkunft, braucht), Memory (Kernakten im Editor wie
  `/memory`), Usage (`/api/ai/kosten`), Capabilities (`/api/ai/werkzeuge`,
  gruppiert; Schalter nur für Cloud/lokal), Permissions (zurücknehmen),
  Model (öffnet `/model`, `/provider`, `/effort`; Weg dreht
  auto → cloud → local).
  Skills zeigt oben „Liste zu lang: N von 6 000 Zeichen — …", wenn die
  Skill-Liste für die KI über der Grenze ist (`skill_liste` aus
  `/api/gedaechtnis`).
- **Fokus**: Seitenleiste → Verlauf → Eingabe → rechts mit **F6** (wie im
  Browser zwischen Bereichen; Tab gehört den Gesprächen, Shift+Tab wäre
  „Tab rückwärts"). Im Verlauf ↑↓ wählt Ziele, Enter löst aus.
- **Strg-Tasten** im Eingabefeld: O Outputs, P Modell, T Effort, U Anhang,
  N neues Gespräch (raw-Modus liefert sie als 15/16/20/21/14; Strg+B bleibt
  frei, das ist tmux).
- **Maus** (`maus.py`): Klick, Doppelklick (tut nichts, verhindert nur einen
  doppelten Klick), Rad. Nur an, solange der Chat offen ist
  (`Chat.maus_pflegen` in `run_ui`); **Shift + Ziehen markiert weiter** in
  xfce4-terminal und tmux; keine Bewegungsmeldungen; `/mouse` schaltet aus,
  `ZENTRALE_TUI_MAUS=aus` von Anfang an. Jede Fläche wird beim Zeichnen
  angemeldet (`klickbar`), Klick und Bild sind also immer dasselbe.
- **Denk-Adern** (`denkadern.py`, Stil: [pixelstil.md](pixelstil.md)): solange
  auf Text gewartet wird, wachsen an der Stelle der kommenden Antwort
  Spiralarme mit eingerollten Windungen aus einem Kern, Reichweite
  `R_max·(1−e^(−dauer/9 s))`, eine Helligkeitswelle läuft nach außen; mit dem
  ersten Text ziehen sie sich 0,9 s zurück. Bild höchstens 10×/s, die
  Schleife tickt dann mit 100 ms statt 33 (`Chat.nur_adern`). Gemessen
  (120×35, dieser Laptop): Chat offen 5 % CPU (vorher 29 % — das Auge lief
  oben mit), Denken 9–14 % (vorher 37–51 %); 160×45: 12–19 % (vorher 38–50 %).
- **Das Auge** steht nur noch im leeren Chat (Begrüßung); über einem
  Gespräch nahm es 15 Zeilen und kostete die meiste CPU.
- Headless: Szenarien `ki_web`, `ki_customize`, `ki_denken` (echte Uhr, das
  Abspiel-Backend denkt `ZTUI_DENK_S` Sekunden) in `tests/tui_schirm/lauf.py`;
  ohne Bildschirm `tests/test_chat_web.py`, `tests/test_chat_web_teile.py`,
  `tests/test_denkadern.py`, neue Zustände in `tests/test_fussleiste.py`.

## Fußleiste (seit 2026-10-07)

Sasha: „die leiste zeigt NUR das an was auch tatsächlich in dem modus grad
genommen werden kann". `fussleiste.eintraege(u)` entscheidet:

1. Überlagerungen der Schleife: Reminder, Hilfe, offene Befehlszeile.
2. Eine Ansicht mit `tasten()` liefert ihre Liste selbst — heute der Chat
   (`fussleiste.ANSICHTEN = {"ai": "chat"}`), der seine Überlagerungen fragt
   (`Gespraechsliste/Gedaechtnis/Ablageliste/Projekte.tasten()`). Dieselbe
   Liste ergibt den Hinweis IM Kasten (`fusszeile()` = `fussleiste.text(…)`).
3. Sonst `befehle.CTX_KEYS[current_ctx(z)]` — dieselbe Tabelle wie das
   `/`-Overlay. Neue Kontexte: `mail:list:eingang`, `mail:read:eingang`
   (dort hakt f ab, d löscht nicht); der Kalender liefert `cal:a:termine|
   kalender|todo`, `cal:b`, `cal:c` (Belegung von der Kalender-Sitzung).
4. `/ commands` nur, wo `/` die Befehlszeile öffnet (`in_text_entry`); die
   Zeile darüber zeigt „/ for commands" ebenso nur dort.

Freitext-Zustände ohne Kontext (Formular, Antwort-Editor, Namen tippen)
zeigen keine Leiste — ihr Kasten hat eigene Hinweise.

**Warum Tabelle + Test statt einer Tabelle, aus der auch `taste()` liest:**
das hieße jede `taste()` (zusammen einige tausend Zeilen in 12 Ansichten)
umzubauen, mitten in der Kalender-Arbeit der parallelen Sitzung.
Stattdessen baut `tests/test_fussleiste.py` die echte TUI ohne Bildschirm
(alle Ansichten, gefälschtes Backend, Hintergrund-Threads synchron), bringt
sie in jeden Zustand und drückt **jede Taste, die die echte Leiste zeigt**,
über `taste_verteilen`; ändert sich nichts (Zustand, Backend-Aufruf,
Fenster, Ende), ist der Test rot. Gefunden und behoben: `f` in Post-Listen
außerhalb des Eingangs, `m` auf einer ganzen Liste im Fokus-Wald und
Pfeile in leeren Listen.

**Eine neue Ansicht** (z. B. der geplante Chat nach Claude-Web-Vorbild):
eine Methode `tasten()` → `[(taste, was), …]`, ein Eintrag in
`fussleiste.ANSICHTEN`, ein Zustand im Test. Beschriftungen, die
`fussleiste.codes()` lesen kann: `enter esc tab space ⌫ del home end pgup
pgdn shift+tab alt+enter`, Pfeile `↑↓←→`, `alt+←→`, `ctrl+x`, einzelne
Zeichen, mehrere mit `/` oder Leerzeichen (`a/s`, `pgup pgdn`); `type` und
`any key` sind keine Taste.

Headless: Szenario `ki_nachbesserung` in `tests/tui_schirm/lauf.py` (neuer
Schritt `paste` = tmux-Puffer einfügen; Socket per `ZTUI_SOCK`).

## Historie

- **2026-10-05** — Kern-Bauplan friert `run_ui` (7.701 Zeilen) als Riese ein.
- **2026-10-06/07** — In 16 Schritten zerlegt (Plan zuerst, dann Gerüst,
  Chat, Tutor, Post, Kalender, Graphen, Fokus, Notizen, Klavier, Karte,
  Technik, Startseite, Befehlszeile, Dashboard/Reminder, Fokus-Fragen,
  Schleife). Branch `worktree-agent-ac95c51a142500eaa`.
