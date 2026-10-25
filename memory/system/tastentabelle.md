# Tastentabelle und Leiste (seit 2026-10-11)

Wie die TUI zeigt, welche Tasten gerade gehen — und warum das nicht mehr
auseinanderlaufen kann. Einstieg aus [tui_bauplan.md](tui_bauplan.md);
das Format für Apps steht in [hub_bauplan.md](../hub/hub_bauplan.md)
(„Tastentabelle") und `openapi.yaml` (`GET /api/tasten`).

## Wie es gebaut ist

Sasha: „es gibt ganz unten eine leiste mit shortcuts … und dann je nach
programm noch eine zweite leiste drüber … die shortcuts sind gehardcoded und
fliegen deswegen so komisch rum. stattdessen will ich es dynamisch." Seitdem:

- **Eine Leiste**, die unterste Zeile. Im Kasten eines Programms stehen keine
  Tasten mehr — nur Frage, Rückmeldung (msg) und Status (z. B. „24×6").
- **Jedes Programm hat EINE Tastentabelle** (`TASTEN`, `tui/ansichten/tasten.py`,
  Format neutral in `core/tastentabelle.py`, genauso im app.toml unter
  `[tasten]`, `GET /api/tasten`): je Ansicht `(taste, aktion[, text])`.
  `taste(ch)` ist `self.TASTEN.verteilen(self, self.ansicht(), ch)`, die
  Logik steht in `aktion_<name>(taste)`. Was die Leiste zeigt, IST also, was
  verarbeitet wird. Ohne `text` = verarbeitet, nicht gezeigt (k/j,
  Großbuchstaben, q). `type` = Freitext, `any key` = alles übrige.
- **Ansichten schneiden:** jeder Zustand mit anderen Tasten ist eine eigene
  Ansicht (Nachfrage, Dialog, leere Liste, „nur ein Eintrag" …), damit dort
  nur steht, was wirkt. Teile mit eigener Tabelle (Chat-Überlagerungen,
  Kalender-Kästen, Desk-Canvas/Modale, Bausteine Stylebox/Farbwähler)
  bindet `Tasten.zusammen` als „teil:ansicht" ein.
- **Der Horcher** (`horcher.py`) ist der Client der Leiste: `fenster.verkabeln`
  meldet nach dem Bau jedes Programm an, er liest die Tabelle EINMAL und merkt
  sich die Einträge je Ansicht; die Leiste schlägt beim Zeichnen nur nach.
  Ohne Tabelle: Tabelle aus dem app.toml, sonst **abhören** (eine Fabrik baut
  das Programm in einer Wegwerf-Umgebung, er drückt in jeder Ansicht jede
  Kandidaten-Taste und notiert, was etwas ändert; im Hintergrund, einmal,
  ohne Namen). Heute hat jedes eingebaute Programm eine Tabelle.
- **Hauptschleife:** `taste_verteilen` erledigt nur die Überlagerungen
  (Reminder, Hilfe, Befehlszeile, '/') und gibt die Taste sonst an
  `z.programme[aktives_programm(z)]`. '/' öffnet die Befehlszeile, außer die
  offene Ansicht nimmt Freitext oder '/' selbst (`fenster.in_text_entry`).
- **'/'-Fenster und /help** lesen ebenfalls den Horcher
  (`fussleiste.programm_tasten`, `fussleiste.hilfe`: je Programm die Tasten
  seiner Hauptansicht: `HAUPTANSICHT` am Programm, sonst die erste der
  Tabelle — der Kalender nennt `a:termine`, seine erste ist das
  Ansehen-Fenster, /help zeigte dort bis 25.10.2026 nur „any key close").
  Die Leiste unten nimmt nur ganze Einträge, die in die Breite passen —
  vollständig ist erst das '/'-Fenster. Weg sind `befehle.CTX_KEYS`, `CTX_TITLES`,
  `TUI_KEYS`, `fenster.current_ctx` und alle Hinweiszeilen in den Kästen.
- **Tasten-Namen:** `enter esc tab shift+tab space ⌫ del home end pgup pgdn`,
  Pfeile `↑↓←→`, `alt+…`, `shift+↑↓←→`, `ctrl+x`, `f1`–`f12`, einzelne
  Zeichen; mehrere mit `/` oder Leerzeichen (`a/s`, `pgup pgdn`).
  Leisten-Text englisch (Sasha, 07.10.2026). Umlaute in Freitext: die
  Tabelle kennt nur ASCII; Programme mit Freitext setzen UTF-8-Bytes vorher
  zusammen (Post-Antwort, Chat, Desk, Kalender-Kästen, Klavier-Name).

**Tests:** `tests/test_tastentabellen.py` verlangt für jedes Programm: eine
Tabelle, zu jeder Aktion eine Methode, zu jeder Ansicht einen Aufbau in
`tests/tasten_zustaende/<programm>.py` (`ZUSTAENDE = {ansicht: aufbau}`;
`None` = kommt hier nicht vor), dort zeigt die echte Leiste genau die Tabelle,
und JEDE Taste der Tabelle (auch ungezeigte) tut etwas.
`tests/test_fussleiste.py` hält die Überlagerungen und Chat-Zustände und die
TUI ohne Bildschirm (`welt`), die beide Tests benutzen.

**Ein neues Programm:** `TASTEN`, `ansicht()`, `taste()`, `aktion_*`; ein
Eintrag in `fenster.PROGRAMME`; eine Datei in `tests/tasten_zustaende/`.

## Je Programm

Weg in jede Ansicht: `tests/tasten_zustaende/<programm>.py`. Die Tabelle
selbst steht im Code (`TASTEN`) — hier nur, wie die Ansichten geschnitten sind.

- **Graph** (`Graphen.TASTEN`): `liste` · `liste:leer` · `liste:frage` ·
  `neu` · `erinnerung` · `solo:zahl|zeit|skala|periode|periode:bis`. Im
  Kasten nur msg und „N t zurück". Im Skala-Solo öffnet `/` die Befehlszeile.
- **Kalender** (`Kalender.TASTEN` = `Tasten.zusammen`): die Ansichten aus
  `kalender_bedienung.TASTEN_A/B/C` — `a:termine`, `a:kalender`, `a:todo`
  (+ `_leer`/`_ohne`, wenn nichts zu wählen ist, + `_vom_monat`: Esc „back to
  month"), `b:monat`, `c:woche` (+ `_leer`), `ansehen` (jede Taste schließt);
  dazu jeder Kasten mit eigener Tabelle: `frage:` (`text`, `ny`, `at`, `ant`,
  Rückfall `wahl`), `formular:` (`text`/`wahl`/`advanced`), `advanced:`,
  `quellen:`, `rhythmus:`, `stylebox:` (der Baustein bringt seine Tabelle
  samt Farbwähler `stylebox:farbe:…` selbst mit). `Kalender.ansicht()` nennt
  den innersten offenen Kasten (`Bedienung.kette()`), sonst Ansehen, sonst
  A/B/C. Ungezeigt: k/j, Großbuchstaben, Strg-A/V/G/T, q.
- **Post** (`Post.TASTEN`): `post.taste` ist der einzige Eingang, auch für
  den Antwort-Editor. `kategorien` (+ `:leer`) · `ordner:leer` · `liste` ·
  `lesen` (Vorschau) · `lesen:offen` — die drei je auch `…:eingang` (f hakt
  ab, d löscht nicht) · `einsortieren` · `loeschen:frage` · `antwort` ·
  `antwort:frage`.
- Die übrigen (Liste, Notizen, Klavier, Karte, Desk, Werkstatt, Shop, Chat,
  Startseite, Technik) beschreiben ihre Ansichten in ihrer eigenen Doku
  (`hub/listen_app.md`, `hub/desk_view.md`, `ki/chat_bedienung.md` …).
