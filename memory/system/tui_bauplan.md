# Bauplan der TUI — wie `tui/` geschnitten ist

**Stand 2026-10-06:** Plan, Umbau läuft auf dem Branch
`worktree-agent-ac95c51a142500eaa`. Bis dahin steckte fast die ganze TUI in
EINER Funktion: `run_ui` in `tui/zentrale_tui.py`, 7.701 Zeilen, alles als
verschachtelte Closures (Chat, Kalender, Listen, Notizen, Mail, Graphen,
Karte, Klavier, Tastatur-Dispatch …). Ziel: jede Ansicht ein eigenes Modul
unter `tui/ansichten/`, `run_ui` nur noch Aufbau, Hauptschleife und
Verteiler. **Verhalten exakt gleich** — reine Struktur-Arbeit.

## Warum

Sasha, 05.10.2026: *„ich will nich dass wir irgendwann an einen punkt kommen
an dem der code unwartbar wird und alles um die ohren fliegt!"* Die TUI ist
die am häufigsten geänderte Datei (46 Commits seit August). In einer
7.700-Zeilen-Funktion sieht man nicht, wer welchen Zustand anfasst: jede
Closure kann jede Variable von `run_ui` lesen, und nichts sagt, welche sie
wirklich braucht. Als Nächstes sollen Claude-Web-artige Chat-Funktionen ins
Chat-Panel — dafür muss der Chat ein eigenes, sauberes Modul sein, in das
man hineinbauen kann, ohne den Rest zu lesen.

Der Kern-Bauplan ([bauplan_kern.md](bauplan_kern.md)) friert die Riesen ein
und verlangt, die Zahlen zu senken, wenn sie schrumpfen. Dieser Bauplan
sagt, wohin die Teile gehen.

## Was die Bestandsaufnahme ergab (06.10.2026)

- **Kein einziges `nonlocal`.** Alle Closures teilen Zustand über
  veränderliche Dicts (`AI`, `K`, `L`, `G`, `MAIL`, `NOTE`, `PIANO`, `M`,
  `TUTOR`, `C` …), nie über umgebundene Variablen. Das macht das Schneiden
  mechanisch: ein Dict wandert als Attribut mit, wer es braucht, bekommt
  dieselbe Referenz.
- **Die Zustände sind sauber getrennt.** Fast jede Closure-Gruppe fasst nur
  ihr eigenes Dict an, dazu die Zeichen-Primitive (`safe_addstr`,
  `addclip`, `draw_box`), die Farben `C` und `stdscr`. Quer greifen nur:
  `in_text_entry`/`current_ctx` (lesen alle `active`-Flags), die Startseite
  (öffnet jede App) und `cycle_theme` (Taste `t` in mehreren Apps).
- **Die Hauptschleife** (1.900 Zeilen) ist zwei lange `elif`-Ketten: Tasten
  (je App ein Zweig, nur deren Dict + Funktionen) und Zeichnen (je App zwei
  Zeilen). Die Schleifen-Variablen `cmd_mode`, `cmd_buf`, `cmd_msg`,
  `help_latched`, `nag_*` fasst nur die Schleife selbst an.
- **Threads:** der Store-Poller und `peer_wach` (aus `main`), `ai-poll` und
  `mail-io` (aus `run_ui`), dazu kurze Threads pro Aktion (Chat-Stream,
  Tutor, Mail-Aufträge, Klavier-Wiedergabe). Alle reden über die Dicts,
  geschützt durch `AI_LOCK`/`TUTOR_LOCK`/`MAIL_PLOCK`.
- **Hot Reload** (`RELOAD`, `code_dateien`, `os.execv` in `main`) beobachtet
  `tui/*.py` — **nicht rekursiv**. Neue Module in einem Unterordner muss er
  mit beobachten, sonst lädt ein Merge, der nur eine Ansicht ändert, nicht neu.
  Nach dem exec reisen Rad-Stellung und Galaxie (`ZENTRALE_TUI_RAD`,
  `ZENTRALE_TUI_META`) über die Umgebung; `RAD`/`META`/`TRAD` bleiben darum
  Modul-Zustand von `zentrale_tui.py`.

## Zielstruktur

```
tui/
  zentrale_tui.py        Einstieg: main(), Store, Hot Reload, Selbsttest,
                         Startseiten-Rad; run_ui = Aufbau + Schleife + Verteiler
  ansichten/             je Ansicht ein Modul (eine Klasse)
    basis.py             BASE_URL, api_call, venv_python, ENDE — was jede braucht
    farben.py            Rollen und Paletten (Tag/Nacht)
    kontext.py           Kontext: stdscr, store, Farben C/PIX, Theme, Zeichen-Primitive
    text.py              Umbruch und Markdown (Chat, Tutor, Post teilen das)
    chat.py              KI-Chat
    sprachtutor.py       Tutor-Panel (Text-Fallback ohne Display)
    post.py              Mail + Antwort-Editor
    kalender.py          Kalender + Sidebar-Liste
    graphen.py           Graph-Werkzeug + Überlagerung (auch lifestyle-Box)
    fokus.py             Listen-/Fokus-Werkzeug + Projektkästen
    notizen.py           Notiz-Werkzeug
    klavier.py           Klavier (+ Tastatur-/Notenhelfer)
    karte.py             Karte
    technik.py           external, telemetrie, stdout, outbound, Technik-Ansicht
```

## Wie eine Ansicht an den geteilten Zustand kommt

- **Ein explizites Kontext-Objekt `z`** statt Closure-Variablen. Es trägt,
  was ALLE brauchen: `stdscr`, `store`, Farben `C`, Pixel-Paare `PIX`, die
  Zeichen-Primitive und den Theme-Zugriff. `run_ui` baut es einmal pro Lauf.
- **Jede Ansicht ist eine Klasse** `Ansicht(z)`. Ihr Zustands-Dict bleibt
  ein Dict mit demselben Namen (`self.AI`, `self.K` …) und hängt zusätzlich
  am Kontext (`z.AI`), damit `in_text_entry`/`current_ctx` und die
  Startseite es lesen können. Die Closures werden Methoden mit **unverändertem
  Rumpf**; oben steht eine **Kopfzeile**, die sagt, was die Methode von
  außen braucht:

  ```python
  def ai_submit(self):
      AI, AI_LOCK, ai_stream = self.AI, self.AI_LOCK, self.ai_stream
  ```

  Das hält den Diff reviewbar (der Rumpf ist Zeile für Zeile der alte) und
  macht die Abhängigkeiten sichtbar, die vorher unsichtbar waren. Neuer Code
  darf direkt `self.`/`self.z.` schreiben.
- **Reine Helfer** (ohne Zustand) werden Modul-Funktionen ihrer Ansicht —
  testbar ohne curses.
- **Ansichten importieren nie `zentrale_tui`.** Als Skript gestartet heißt
  sie `__main__`; ein `import zentrale_tui` lüde sie ein zweites Mal, mit
  eigenem `RELOAD`/`ENDE`/`RAD` — Hot Reload und `/quit` liefen dann ins
  Leere. Was aus `zentrale_tui` gebraucht wird, kommt über `z`.
- **Schnittstelle zur Hauptschleife:** `oeffnen()` (was die Startseite beim
  Öffnen tut), `taste(ch)` (der alte Tasten-Zweig; gibt `ENDE` zurück, wo
  früher `break` stand) und die `draw_*`-Methoden. Die `elif`-Ketten in
  `run_ui` bleiben: ihre Reihenfolge ist Verhalten (wer gewinnt, wenn zwei
  `active` sind), und sie ist dort auf einen Blick lesbar.
- **Importe innerhalb von `ansichten/` sind relativ** (`from .basis import
  api_call`), `pixel` und `core/` per `try: from tui import … except
  ImportError: import …` wie bisher — so geht beides, Skript und Paket.
- **Türen:** auch die neuen Module dürfen aus `core/` nur `theme`, `tone`,
  `pc_status` (Kern-Bauplan, „Türen"; der Test scannt `tui/` rekursiv).
  Keine Datei heißt wie ein Kern-Modul *und* wird absolut importiert.

## Reihenfolge des Schneidens

Ein Schritt = ein Commit, nach jedem: volle Testsuite + Bildschirm-Vergleich.

1. Gerüst: `ansichten/` mit `basis`, `farben`, `kontext`; Hot Reload
   beobachtet `tui/` rekursiv; Aussenposten-Liste nimmt `tui/ansichten/` mit.
2. Chat (mit `text.py`) — zuerst, weil dort als Nächstes gebaut wird.
3. Sprachtutor, 4. Post, 5. Kalender, 6. Graphen, 7. Fokus, 8. Notizen,
   9. Klavier, 10. Karte, 11. Technik.
12. Was übrig bleibt: Befehlszeile, Overlay, Nag, Startseite — in `run_ui`
    als Aufbau + Schleife + Verteiler.

Riesen-Methoden (`draw_calendar` 432, `draw_overlay` 499, `draw_list_tool`
259, der Listen-Tasten-Zweig 369 Zeilen) werden beim Umzug in Abschnitte
geteilt — ein neues Modul darf selbst kein Riese sein.

## Sicherheitsnetz

- `pytest` komplett, dazu `tests/test_tui_fuzz.py` (echte TUI im PTY,
  tausende Zufallstasten in alle Ansichten; ein `NameError` nach einem Schnitt
  fällt dort als Frame-Fehler auf).
- **Bildschirm-Vergleich:** die TUI läuft in tmux (eigener Socket, 150×46)
  gegen ein Aufzeichnen-und-Abspielen-Backend: GETs einmal vom laufenden
  Backend geholt und eingefroren, POST/PUT/DELETE antwortet es selbst mit
  `{}` (kein Tastendruck ändert Sashas Daten). Uhr eingefroren per
  `sitecustomize` (Wanduhr und `time.monotonic` in der TUI; threading und
  Sockets behalten die echte Uhr). Je Ansicht ein Tastenweg, mitgeschnitten
  mit `capture-pane -e` (Zeichen + Farben), verglichen Zelle für Zelle. Zwei
  Läufe desselben Codes ergeben dasselbe Bild — also zeigt jeder Unterschied
  nach einem Schnitt eine echte Verhaltensänderung.
- Beim Schneiden selbst: AST-Vergleich jedes verschobenen Rumpfs mit dem
  Original (ohne Kopfzeile) und eine Prüfung auf unaufgelöste Namen in
  `tui/**`.
