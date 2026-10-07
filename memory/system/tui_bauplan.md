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
| `ansichten/sprachtutor.py` | `Sprachtutor`: Text-Panel, Zimmer-Fenster | `TUTOR` |
| `ansichten/post.py` | `Post`: Mail, Antwort-Editor, Mail-Worker | `MAIL` |
| `ansichten/kalender.py` | `Kalender`: Woche/Monat, Formular, Routinen, Sidebar | `K` |
| `ansichten/kalender_ansichten.py` | Entwürfe A/B/C als reine Funktionen (Daten rein → Zeilen raus, kein curses); noch nicht eingehängt, siehe [kalender_ansichten_vorschau.md](../werkzeuge/kalender_ansichten_vorschau.md) | — |
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

## Historie

- **2026-10-05** — Kern-Bauplan friert `run_ui` (7.701 Zeilen) als Riese ein.
- **2026-10-06/07** — In 16 Schritten zerlegt (Plan zuerst, dann Gerüst,
  Chat, Tutor, Post, Kalender, Graphen, Fokus, Notizen, Klavier, Karte,
  Technik, Startseite, Befehlszeile, Dashboard/Reminder, Fokus-Fragen,
  Schleife). Branch `worktree-agent-ac95c51a142500eaa`.
