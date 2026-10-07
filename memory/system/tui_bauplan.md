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
| `ansichten/gespraechsliste.py` | `Gespraechsliste`: Überlagerung im Chat-Kasten (Tab/`/liste`); reine Helfer `alter_text`, `filtern`, `listen_zeilen` | `AI["liste"]` |
| `ansichten/gedaechtnis.py` | `Gedaechtnis`: Überlagerung im Chat-Kasten (`/gedaechtnis`, `/skills`) — Kernakten, Bereiche, Skills; Kernakte im Editor ändern, Skill an/aus; reine Helfer `reiter`, `inhalt_zeilen`, `naechster_status`, `editor_befehl` | `AI["gedaechtnis"]` |
| `ansichten/sprachtutor.py` | `Sprachtutor`: Text-Panel, Zimmer-Fenster | `TUTOR` |
| `ansichten/post.py` | `Post`: Mail, Antwort-Editor, Mail-Worker | `MAIL` |
| `ansichten/kalender.py` | `Kalender`: Woche/Monat, Formular, Routinen, Sidebar | `K` |
| `ansichten/kalender_ansichten.py` | Entwürfe A/B/C als reine Funktionen (Daten rein → Zeilen raus, kein curses); im Kalender per `v` eingehängt (`_kal_stil`), siehe [kalender_ansichten_vorschau.md](../werkzeuge/kalender_ansichten_vorschau.md) | — |
| `ansichten/kalender_beispiel.py` | Beispieltermine für Tests und `scripts/kalender_vorschau.py` | — |
| `ansichten/graphen.py` | `Graphen`: Graph-Werkzeug, Überlagerung (auch lifestyle-Box) | `G` |
| `ansichten/fokus.py` | `Fokus`: Listen-/Fokus-Werkzeug, Bernsteinleiste, `proj_render` | `L` |
| `ansichten/notizen.py` | `Notizen`: Notiz-Werkzeug | `NOTE` |
| `ansichten/klavier.py` | `Klavier` + Klaviatur-Geometrie (`piano_*`) | `PIANO` |
| `ansichten/karte.py` | `Karte`: Weltkarte, Overlays, Länder-Fokus | `M` |
| `ansichten/technik.py` | `Technik`: external, telemetrie, stdout (Laufschrift), outbound | `TECH` |
| `ansichten/startseite.py` | `Startseite`: Rad, Galaxie + ihre Geometrie | liest `RAD`/`META`/`TRAD` |
| `ansichten/dashboard.py` | `Dashboard`: rechte Spalte des alten Dashboards | — |
| `ansichten/befehle.py` | Befehle, `TUI_KEYS`/`CTX_KEYS`, `Befehlszeile` | `cmd_mode` … |
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
  sie den Cursor — der Verlauf geht dann mit Bild↑↓. Esc: läuft eine Antwort,
  stoppt sie; offene Auswahl/Erlaubnis-Frage: abbrechen/ablehnen; sonst zu.
- **Esc vs. Alt:** `Chat._esc_lesen` wartet nach ESC 50 ms auf Folgetasten
  (wie `karte.m_alt_arrow`); allein → Esc, + Enter → Alt+Enter, sonst
  nichts. Die Deutung ist `eingabe.esc_folge` (testbar).
- **Umlaute:** die Hauptschleife bleibt bei `getch` (alle Ansichten rechnen
  mit Ganzzahlen); der Chat setzt UTF-8-Bytes in `eingabe.utf8_byte`
  zusammen, wie der Post-Antwort-Editor.
- **Cursor** zeichnet `draw_ai` selbst (invers), `curs_set` bleibt 0.
- Die Tastenzeile ganz unten liefert `Chat.fusszeile()`, solange der Chat
  den Fokus hat.
- Headless geprüft mit `tests/tui_schirm/lauf.py` (Szenarien `ki_eingabe`,
  `ki_befehle`; Größe per `ZTUI_GROESSE=80x24`), das Abspiel-Backend liefert
  dafür erfundene Einstellungen.

## Chat: Gespräche (seit 2026-10-07)

Claude-Web-Plan Phase 2 ([../ki/gespraeche.md](../ki/gespraeche.md)). Was
für die TUI gilt:

- **Gesprächsliste** = Überlagerung im Chat-Kasten (nicht Seitenleiste: auf
  80×24 bliebe zu wenig Verlauf). Öffnen: **Tab bei leerer Eingabe** (mit
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
  an). Zeile: `● name … an · von dir` (○ aus, ◌ vorgeschlagen), darunter die
  Beschreibung; auf breiten Schirmen höchstens 64 Spalten, damit der Status
  beim Namen bleibt.
- **Nicht im Rad:** ein Rad-Platz braucht ein Pixel-Symbol, eine Taste und
  verschiebt die gespeicherte Rad-Stellung (`ZENTRALE_TUI_RAD`); offen, ob
  Sasha es dort will.
- Headless: Szenario `ki_gedaechtnis` in `tests/tui_schirm/lauf.py` (das
  Abspiel-Backend liefert ein erfundenes Gedächtnis, der „Editor" ist ein
  Skript, das eine Zeile anhängt); ohne Bildschirm:
  `tests/test_gedaechtnis_ansicht.py`.

## Historie

- **2026-10-05** — Kern-Bauplan friert `run_ui` (7.701 Zeilen) als Riese ein.
- **2026-10-06/07** — In 16 Schritten zerlegt (Plan zuerst, dann Gerüst,
  Chat, Tutor, Post, Kalender, Graphen, Fokus, Notizen, Klavier, Karte,
  Technik, Startseite, Befehlszeile, Dashboard/Reminder, Fokus-Fragen,
  Schleife). Branch `worktree-agent-ac95c51a142500eaa`.
