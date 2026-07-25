# Dashboard & Frontend

> **AKTUELLER STAND (2026-06): EIN Browser-Template, mehrere Kassetten.**
> Die gelebte Haupt-UI ist `ui/templates/monolith.html` — und das ist seit
> 2026-06 die **einzige** Browser-Front. Die frühere separate `laptop.html`
> ist **weg**: monolith und laptop liefen auseinander (laptop verlor Karte/
> Graphen, Mail/Listen kamen nie an). Jetzt rendert `/` für **alle** Browser-
> Kassetten dasselbe Template; der Unterschied ist allein der Flag
> `ki_aus` (aus `core/kassette.py`), den `app.py` ans Template durchreicht —
> bei laptop/tui werden die KI-Blöcke per `{% if not ki_aus %}` weggelassen
> (Chat/Audio/Tutor/News/OLLAMA-Status), und unten erscheint statt der Chat-
> Zeile eine **Shortcut-Übersicht**. Alles Nicht-KI (Karte, Graphen, Kalender,
> Listen, Post/Mail, Telemetrie, Logs) ist damit in allen Fronten gleich.
> Das alte `index.html` (AI-Orb, `#view-main`-Grid) ist ebenfalls **weg**.
> Was Sasha real sieht steht unter „## Monolith-Dashboard".

## Kassetten (monolith | laptop | tui)

Eine Codebase, ein Backend, **mehrere Fronten** — bewusst getrennte Fronten
statt eines Modus-Schalters im Monolith (damit sie sich unabhängig entwickeln,
ohne „Zusammendatschen"):

- **`core/kassette.py`** ist die einzige Wahrheit: liest die Env-Var
  `ZENTRALE_KASSETTE` (Default `monolith`; unbekannte Werte → `monolith`).
  `name()`, `is_laptop()`, `is_tui()`, `ki_aus()`, `template()`.
  `ki_aus()` ist `True` für **laptop und tui** (alles außer monolith).
- **`core/main.py`** fährt den KI-Auto-Bootup (Ollama-Warmup + News-Fetcher)
  **nur wenn `ki_aus()` False** ist (also nur monolith) hoch. Sonst: nichts
  davon → Ollama wird nie angesprochen.
- **`ui/app.py`** rendert `kassette.template()` auf `/` (+ `/monolith`-Alias).
  Wenn `ki_aus()`: KI-Endpoints abgeriegelt — `/api/chat`,
  `/api/permission_answer`, `/api/speak`, `/api/transcribe` → **503**;
  `/api/ai/status` → `{available:false, kassette:<name>}`; `/api/chat/history` → `[]`.
- Gestartet wird die Wahl über den Start-Befehl: `zentrale` zeigt ein
  **Kassetten-Menü** (`tui/select_kassette.py`, ↑/↓ + Enter, animierter Stern,
  Regenbogen-Ladebalken) und exec't in die gewählte Kassette; `zentrale-laptop`
  → laptop, `zentrale-tui` → tui überspringen das Menü direkt (setzen die
  Env-Var). Siehe `starten.md`.

Die drei Fronten:

| Kassette | Front | KI | Datei |
|----------|-------|----|-------|
| monolith | Browser, voll | an | `ui/templates/monolith.html` |
| laptop   | Browser, lean | aus | `ui/templates/monolith.html` (`ki_aus`-gegated) |
| tui      | **Terminal (curses)** | aus | `tui/zentrale_tui.py` |

### Laptop-Kassette (KI-frei, gleiches Template)

**Keine eigene Datei mehr** — laptop rendert `monolith.html`, nur mit
`ki_aus=True`. Was dadurch wegfällt (per `{% if not ki_aus %}` im Template +
`if (!window.KI_AUS)` im JS): OLLAMA-Header-Status, AI-State/Minilog, die
Chat-Konsole (Input/Mic/Permission), Cinema-Mode, Tutor — und `engine.js`
überspringt die KI-Polls (`/api/ai/status`, `/api/chat/history`), pollt also
nur `/api/state` (1 s) + `/api/telemetry` (2 s). **Bleibt** für alle Fronten:
das Mittel-Exhibit mit ASCII-Animationen + Tabs (das ist Visualizer, keine KI),
Karte/Graphen/Kalender/Listen/Post, Telemetrie, Logs, Data-Collection (Alt+K).
Statt der Chat-Zeile steht unten die **Tastenkürzel-Box** (Quelle:
`tastatur.md`).

> **Sensoren-Panel entfernt (2026-06):** in ALLEN Kassetten ist die Sensoren-
> Anzeige raus — kein echter Sensor angeschlossen. Das **Backend bleibt
> verkabelt** (Event-Loop, `/api/sensor/<name>`-Webhook, `sensors` in
> `/api/state`); zum Wiederanzeigen Box + Handler aus der git-History
> zurückholen (das tote `.srow`-CSS steht im Template noch bereit).

- **Mitte:** dieselben Werkzeug-Tabs wie im Monolith — **Graph**, **Kalender**,
  **Fokus** (Listen·Fokus, auch per Taste `f`), **Post** (Mail), **Karte**
  (Globus/Welt) — plus die Animationen.
  In der **TUI** dieselben Werkzeuge über Tasten (`g`/`c`/`l`/`p`/`m`).
- **Minimale Boot-Dependencies:** nur `flask` + `python-dateutil` (kein
  Whisper/TTS/sherpa/piper nötig — die Kassette ist KI-frei). Siehe `starten.md`.

### Terminal-Kassette (`tui/zentrale_tui.py`)

KEIN Browser — rendert direkt im Terminal (curses). Motivation: ein Browser-Tab
frisst auf einer RAM-schwachen Maschine 300–600 MB+, das Backend selbst nur
~32 MB. Die TUI ist ein **eigenständiger Client** (kein Flask-Template): sie
pollt dasselbe `/api/state` (1 s) + `/api/telemetry` (2 s) über HTTP und zeichnet
ein 3-Spalten-Layout analog zur Laptop-Kassette (telemetrie/stdout |
mitte-skelett | lifestyle/outbound; Sensoren-Panel entfernt, s.o.). Header mit
NET/UP/Uhr. Tasten: `q` beendet,
`t` zykliert das Theme (auto/hell/dunkel — auto nach Uhrzeit, wie im Web).
Themes: Light-Mode mit weißem Hintergrund (kein Gelb auf Weiß), Dark-Mode
**ultra-high-contrast** (reinweißer Text 231 auf hartem Schwarz 16, Rahmen Grau
245). Akzent-Grün ist gedämpft (Salbei 108, nie bold → kein Neon). Box-Inhalte
werden auf die jeweilige Box-Innenbreite gekürzt (kein Überlauf in Nachbarspalten).

**Terminal-Kopplung (Sashas Laptop, xfce4-terminal):** die TUI schreibt bei
jedem Moduswechsel den Modus (`auto`/`day`/`night`) nach
`~/.config/zentrale/theme` und stößt `zentrale-term-theme`
(`scripts/zentrale-term-theme`, per Symlink in `~/.local/bin`) an — der färbt
das umgebende xfce4-terminal live per `xfconf-query` um. **Seit 2026-07-25
nicht mehr Solarized, sondern dieselben zwei Welten wie in nvim** (day = paper
`#ece0c0`, night = cyber `#000000`), inklusive **voller 16er-ANSI-Palette** —
vorher blieben `ls`/Prompt/git in den alten Tönen stehen, weil nur bg/fg gesetzt
wurden. Auf Papier sind die „hellen" Farben 9–14 bewusst **dunkler** als 1–6:
auf hellem Grund hebt nur mehr Tiefe hervor (aufgehellt lagen sie bei 3.1–4.2:1,
jetzt 7:1). `auto` löst nach Uhrzeit auf, exakt wie `resolved_theme`.
Ein **systemd-User-Timer** `zentrale-theme.timer` zieht dieselbe Datei
jede Minute nach → die 05/21-Rotation greift auch ohne laufende TUI. Nur lokal,
kein Sync, kein Backend — TUI ist die einzige Quelle. **Setup reproduzierbar
in git:** Unit-Templates `deploy/zentrale-theme.{service,timer}` (zwei
`ExecStart`-Zeilen: Terminal + Browser), Einrichten per
`scripts/install_theme_coupling.sh` (Symlinks + Units nach
`~/.config/systemd/user/` + `enable --now`, nimmt nvim mit; idempotent, kein
sudo; hieß bis 2026-07-25 `install_term_theme.sh`, die alten Unit-Namen räumt
es beim Lauf ab).

**Browser-Kopplung (Brave, seit 2026-07-25):** `scripts/zentrale-browser-theme`.
Brave läuft hier als **Flatpak** — ein Flatpak sieht Hell/Dunkel nicht am
GTK-Theme, sondern am **xdg-desktop-portal**
(`org.freedesktop.appearance color-scheme`: 0 = keine Vorgabe, 1 = dunkel,
2 = hell). Chromium/Brave abonniert das SettingChanged-Signal → schaltet **live**
um, ohne Neustart, und zwar Browser-Oberfläche **und** `prefers-color-scheme`
für die Seiten. Der Applier setzt also nicht den Browser, sondern die
Portal-Einstellung; welches gsettings-Schema das Portal liest, hängt am Backend:

- **Linux Mint (Sashas Laptop): `org.x.apps.portal`** (`xdg-desktop-portal-xapp`)
  — das GNOME-Schema `org.gnome.desktop.interface color-scheme` bleibt hier
  **wirkungslos** (geprüft: Portal meldete stur 0). Beide werden gesetzt, damit
  ein Knoten mit anderem Desktop ohne Sonderfall funktioniert.
- **Voraussetzung im Browser:** Erscheinungsbild auf **System**
  (`brave://settings/appearance`, Pref `browser.theme.color_scheme2 = 0`).
  Steht dort fest Hell/Dunkel, ignoriert Brave das Portal.
- **Nebenwirkung, bewusst:** die Portal-Einstellung gilt für **alle**
  portal-bewussten Apps (jedes Flatpak, GTK4/libadwaita). Ein laufendes Chromium
  browser-exklusiv live umzuschalten geht nicht — Flags brauchen Neustart, und
  eine Extension kann die Browser-Oberfläche gar nicht umfärben. Der GTK-Theme
  des Desktops (xsettings `/Net/ThemeName`) bleibt unangetastet.
- **Diagnose:** `zentrale-browser-theme --status` (Datei, aufgelöster Modus,
  was das Portal gerade meldet), `--resolve`/`--dry-run` seiteneffektfrei.

**Desktop-Kopplung (XFCE, seit 2026-07-25):** `scripts/zentrale-desktop-theme`
setzt GTK-Theme (`xsettings /Net/ThemeName`) und Fensterrahmen
(`xfwm4 /general/theme`). **Das ist kein Beiwerk, sondern der sichtbare Teil der
Browser-Kopplung:** Brave steht auf „Use GTK" und holt seine Oberflächenfarben
aus dem GTK-Theme — bei fest dunklem Theme bewegt das Portal-Signal nur noch die
Seiten, und man „erkennt nicht viel" (genau Sashas Beobachtung).

- **Paare, angelehnt an die nvim-Paletten** (Mint hat kein Neon, also die
  nächstverwandten Stock-Themes): `night` → **Mint-L-Darker-Aqua** (dunkelste
  Variante, kühl-cyaner Akzent `#6cabcd` ≈ cyber), `day` → **Mint-L-Sand**
  (warmer Ocker `#c8ac69` ≈ Sepia/Papier). Rahmen laufen mit; „Darker" bringt
  kein `xfwm4` mit → nachts `Mint-L-Dark-Aqua`.
- **Überstimmbar per Env** (`ZENTRALE_GTK_DAY/_NIGHT`, `ZENTRALE_WM_DAY/_NIGHT`)
  — Paar tauschen, ohne das Skript anzufassen.
- **Umkehrbar:** der Vorzustand wird beim ersten Lauf nach
  `~/.config/zentrale/desktop-theme.bak` gesichert (hier: GTK
  `Mint-L-Darker-Teal`, Rahmen `Mint-L-Dark-Red`), `--restore` setzt zurück.
- **Icons laufen mit:** `ZENTRALE-Cyber` / `ZENTRALE-Paper`, gebaut von
  `scripts/build_icon_themes.py`. **Kein Download nötig:** Papirus liegt hier
  ohnehin und bringt seine Ordner in 78 Farbvarianten mit — die abgeleiteten
  Themes erben Papirus-Dark bzw. -Light und legen nur die Ordner in Akzentfarbe
  darüber (cyan nachts, palebrown tagsüber), als **Symlinks** (938 Stück, ein
  paar MB statt ~200 MB Fremd-Set). Das ist die Logik von `papirus-folders`,
  aber als eigenes Theme im Benutzerverzeichnis: kein sudo, System-Papirus
  bleibt unberührt, Umschalten heißt Theme-Name wechseln statt Dateien
  umschreiben. Vorher stand hier `HighContrast` (in der Sicherung).

**Tor Browser wird bewusst NICHT gekoppelt.** Tor vereinheitlicht Fingerprints;
unter `resistFingerprinting` ist das Farbschema Teil der Angriffsfläche, und an
Tors Prefs zu automatisieren macht genau den Browser unterscheidbarer, den man
unauffällig haben will. Dort den eingebauten Dunkel-Schalter von Hand nutzen.

**nvim-Kopplung (dieselbe Datei, seit 2026-07-25):** nvim folgt
`~/.config/zentrale/theme` mit zwei EIGENEN Colorschemes (Code im Repo unter
`nvim/`, siehe `nvim/lua/zentrale_theme/`):

- `night` → **`zentrale-cyber`**: echtes Schwarz `#000000` + Neon (Cyan `#00f0ff`
  Funktionen, Magenta `#ff2bd6` Keywords, Spring `#00ff9c` Strings, Violett
  Konstanten, Gelb Typen).
- `day` → **`zentrale-paper`**: Papier `#eee7d3` + pflanzliche Akzente
  (Blattgrün Strings, Tannentiefe Typen, Rinde Konstanten, Terracotta Zahlen,
  Beere Keywords, Wasser-Indigo Funktionen); Kommentare wie verblasster
  Bleistift, kursiv.
- **Bewusst NICHT die Terminal-Palette geerbt:** die nvim-Fläche soll sich
  sichtbar abheben (Papier `#eee7d3` gegen Terminal-Creme `#fdf6e3`, Cyber-
  Schwarz gegen Terminal-Petrol `#002b36`) — man soll sehen, dass man im Editor
  ist. Deshalb braucht nvim `termguicolors` (die Paletten sind 24-bit).
- **Warum überhaupt Code?** nvim fragt die Terminal-Hintergrundfarbe per OSC 11
  nur **beim Start** ab. Ein schon LAUFENDES nvim erfährt vom Live-Umfärben
  nichts — genau die Lücke. Zwei Netze: **fs_event-Watcher** auf der Theme-Datei
  (instant beim `t` in der TUI) + **60-s-Tick** (fängt die 05/21-Rotation, bei
  der sich der Dateiinhalt gar nicht ändert — dieselbe Rolle wie der systemd-
  Timer fürs Terminal). Beides No-Op, solange der Modus gleich bleibt.
- **Gegen nvims eigene Erkennung verteidigt:** ein Wechsel von `background`
  löscht in nvim ALLE Highlights samt `colors_name`, und nvims OSC-11-Erkennung
  schlägt erst nach `plugin/` zu → das Theme wäre beim Öffnen wieder weg.
  Abgefangen per `OptionSet background` (nach dem Startup) **und** einmaligem
  `VimEnter` (während des Startups feuert OptionSet nicht).
- **Einhängen:** `scripts/install_nvim_theme.sh` schreibt
  `~/.config/nvim/plugin/zentrale_theme.lua` (nvim sourced `plugin/` selbst) →
  **Sashas `init.lua` bleibt unangetastet**. Deinstallieren = diese Datei
  löschen. Manuell/ad hoc: `:ZentraleTheme day|night|auto` (Sitzungs-Override,
  schreibt die Theme-Datei NICHT), oder `:colorscheme zentrale-cyber|-paper`.
- **Tests:** `tests/test_nvim_theme.py` fährt echtes nvim headless — Auflösung,
  Live-Umschalten im laufenden Prozess, Timer-Fallback, Erholung nach fremdem
  `background`-Wechsel, plus **Kontrast-Wächter** (jede Rolle ≥4.5:1 auf ihrer
  Fläche; die erste Papier-Palette lag bei 2.9–4.1:1 und war zu blass).

**Befehlszeile (unten):** `/` öffnet eine Eingabezeile am unteren Rand (die
Shell ist im Alternate-Screen nicht erreichbar — das ist der Ersatz). Beim
Tippen klappt eine **Live-Liste** der passenden Befehle nach oben auf und filtert
mit; Enter führt aus, `Esc` (oder den Slash wegbackspacen) schließt wieder.
Befehle: `/help` (latcht die volle Hilfe inkl. Tastenkürzel, klappt bei der
nächsten Taste weg), `/theme [auto|hell|dunkel]`, `/quit`. Die Logik liegt
curses-frei auf Modulebene (`parse_command`, `overlay_rows`) und ist ohne TTY
unit-testbar. Im Normal-Modus (Zeile zu) wirken `q`/`t` weiter als Shortcuts.

**Graph-Werkzeug (Mitte, Taste `g`):** dieselbe geteilte Logik wie im Monolith
(`core/graphs.py` + `/api/graphs`), hier in curses verbaut. `g` gibt der
MITTE-Box den Fokus; ein kleines Zustandsmodell `G` (`view`: `list`/`new`/`view`)
steuert die Bedienung: in **list** mit ↑/↓ wählen, `n` neu, `d` löschen
(öffnet einen **Mini-Bestätigungsdialog** über der Liste: `j`/Enter löscht,
jede andere Taste bricht ab — `G["confirm"]`), Enter öffnet; in **new** Name
tippen, `Tab` zykliert den **Typ** (s.u.),
Enter legt an (`POST /api/graphs`); in **view** trägt man Werte für *heute* ein,
gespeichert über `/api/log` — dieselbe Route wie die Data-Collection.

**Übersicht = großer Kombigraph mit Zeit-Achse (`draw_overlay(labeled=True)`):**
oben über der Liste liegt die beschriftete Überlagerung aller Graphen. Unten
läuft eine **sparse Datums-Zeile** (ein paar `dd.mm.`-Marken übers Fenster
verteilt) — grobe Orientierung, wann was war. Passt die ganze Historie in die
Breite, wird sie wie gehabt **gestreckt** (heute rechts, ältester Wert links);
ist sie **breiter als der Platz**, zeigt die Übersicht ein **festes Fenster
(1 Tag/Spalte)** mit *heute* rechts, das man mit **←/→** in die Vergangenheit
bzw. zurück Richtung heute **pant** (`G["gscroll"]` = Tage zurück, in `list`
per ←/→; beim Öffnen/Zurück auf 0, auf die echte Historie geclampt). `‹`/`›`
in der Datums-Zeile zeigen, dass links Älteres bzw. rechts Neueres außerhalb
liegt; der Hint nennt den Offset (`←→ zeit (N t zurück)`). Solo (Enter) nutzt
←/→ weiter für den **Ziel-Tag** (`dayoff`), nicht fürs Fenster.

Vier **Graph-Typen** (`GRAPH_TYPES`, Validierung in `core/graphs.py`):
- `number` — freie Messwerte (Ziffern + Enter), `blockspark`-Kurve.
- `scale` — 1–5 Bewertung (Taste 1–5 trägt sofort ein).
- `time` — **Uhrzeit pro Datum** (z.B. Einschlafzeit). Eingabe `HH:MM`
  (`parse_clock`), gespeichert als `value` = Minuten seit Mitternacht.
- `period` — **Zeitspanne pro Datum** (z.B. Schlaf `23:00–07:00`). Zwei-Stufen-
  Eingabe von→bis (`pstage`/`input2`), gespeichert als `value`=Start-Minute +
  `end`=End-Minute. `end < value` = über Mitternacht.

`time`/`period` werden als **24h-Gitter** gezeichnet (`draw_time_plot`):
X = letzte Einträge (Datum), Y = Uhrzeit (00:00 **unten** … 24:00 **oben**,
Stunden-Marken), `time` → Punkt `●`, `period` → Balken `█` (über Mitternacht in
zwei Segmente gesplittet via `fill()`, da die Achse an Mitternacht verankert
ist — orientierungs-unabhängig). Formatierung über `fmt_clock` / `graph_last`;
die Sparkline-Reihe liefert `graph_series` (`period` → Dauer via
`period_duration`).

Werte/Definitionen holt das Werkzeug synchron per `api_call()` (POST/DELETE).
Die `lifestyle`-Box rechts zeigt **alle Graphen überlagert** in EINEM Gitter:
X = **festes Fenster der letzten 7 Tage** (heute rechts, 6 Tage zurück nach
links, über die volle Breite verteilt — egal wie viel gefüllt ist; leere Tage
bleiben leer), Y **bewusst mehrdeutig** — jeder Graph nutzt seine *eigene*
Achse + Darstellung, alles übereinandergelegt zum Vergleich. Gezeichnet als
**dünne Linien**, je Graph in einer eigenen **Farbe** (Unterscheidung über die
Farbe, nicht über fette Symbole):
- `period` → dünne **vertikale** Linie `│` über die Zeitspanne (24h-Skala,
  00:00 unten; Wrap über Mitternacht in zwei Segmente),
- `time` → Punkt auf der 24h-Skala,
- `scale` → Punkt auf der eigenen 1–5-Skala,
- `number` → Punkt auf der eigenen min/max-Spanne (über die sichtbaren Werte).

Die Punkt-Typen (`time`/`scale`/`number`) werden über die Tage zu einer
**Liniengrafik verbunden** (Steigung → `╱` steigt, `╲` fällt, `─` flach,
`│` senkrecht; einzelner Punkt → `·`). Farb-Palette `LIFE_COL` (durchgezykelt),
darunter eine gepackte Legende (farbiges `─`-Sample → Name). Es geht um Verlauf
& Gleichzeitigkeit, nicht um absolute Werte (`row_clock`/`row_norm`). Quelle ist
das langsame Hintergrund-Polling (`Store._poll_graphs`, alle 5 s). `Esc`/`g`
schließt das Werkzeug wieder. `--selftest` listet die Graphen inkl.
Typ/Sparkline (ohne TTY).

**Vorhersage-Ergänzung (`predict`-Flag, default aus):** Trägt ein Graph
`predict: true`, schätzt die `lifestyle`-Box **fehlende Tage** im Fenster aus dem
Schnitt der letzten ~7 echten Werte (ab dem ersten echten Eintrag, nichts vor
Tracking-Beginn) und zeichnet sie **blass/schraffiert** (`predicted_days`,
TUI-Rendering). Bewusst nur dort sinnvoll, wo ein stabiles Muster existiert —
default ist es überall **aus**, nur `g_sleep` ist migriert auf an. Geschaltet wird
es im Graph-Werkzeug: TUI-Listenansicht Taste `p` (geflaggte tragen ein `~`),
Browser-Panel `[~vorhersage: an/aus]` neben `[löschen]`; beides ruft
`POST /api/graphs/<gid>/predict {predict}` (→ `core.graphs.set_predict`). Die
Schätzung rendert aktuell in der TUI-`lifestyle`-Box; das Flag liegt aber pro
Graph zentral, Fronten honorieren es, wo sie schätzen.

**Tages-Reminder (`remind`/`remind_at`, default aus):** ein Graph kann täglich
ans Eintragen erinnern. `remind: true` + `remind_at: "HH:MM"` → ab dieser Uhrzeit
gilt der Graph als **fällig**, SOLANGE für *heute* noch kein Wert da ist; sobald
geloggt, fällt er raus (erfüllt). Quelle ist `GET /api/graphs/reminders`
(`core.graphs.due_reminders`: remind an, Uhrzeit erreicht, heute ungeloggt).
Gesetzt wird's im Graph-Werkzeug: **Browser** Toggle + Uhrzeit-Feld im
Anlege-Formular und `[⏰ remind: …]` nachträglich am Graphen; **TUI** Taste `r`
(Uhrzeit eintippen; in der Liste steht `@HH:MM`). Beides ruft
`POST /api/graphs/<gid>/remind {remind, at?}` (→ `core.graphs.set_remind`). Der
Nag selbst poppt **einmal pro Sitzung**: Browser als »bitte eintragen«-Modal
(`#rem-overlay`, `eintragen` öffnet das Graph-Werkzeug), TUI als zentriertes
Kästchen (`g` = ins Werkzeug, sonst wegklicken). Wegklicken = Ruhe bis
Sitzungsende für die gezeigten Graphen; neu fällige nagen weiter.

**Fokus-Werkzeug (Mitte, Taste `f`):** EIN gemergtes Werkzeug —
abhakbare Todo-/Sammel-Listen im **FOCUS-Look** (früher zwei getrennte Sachen:
schlichtes Listen-Werkzeug `l` + Projektansicht/Fokus `f`; jetzt verschmolzen und
einheitlich **„Fokus"** genannt, Taste `f`). `l` öffnet dasselbe noch als
**stiller Alt-Alias** (Muskelgedächtnis), taucht aber in KEINER Legende/Einladung
mehr auf — überall steht nur noch `f · fokus`. Geteilte Logik (`core/lists.py` + `/api/lists`),
hier in curses verbaut. Gezeichnet wird durchweg über `proj_render`: jede Zeile =
**Titel + Erfüllungsleiste** (2 Zeilen), `▸` = reindivebar, `◆`/Bernstein-Balken =
Fokus. Zustandsmodell `L` (`view`: `forest`/`view`/`place`/`move`/`move_new`).
Die **Wurzel** (`forest`) ist **zweigeteilt**: oben die geflaggten Projekte
(`/api/projects`), Trennlinie `── listen ──`, drunter **alle Nicht-Projekt-Listen**
— beide top-level, per **Enter reindivebar** (wie die frühere Projektansicht;
Deskriptor-Modell `{lid,iid}`, `l_forest_rows`/`l_desc_view`/`l_open_desc`). In der
Wurzel: `↑↓` wählen, **Enter** rein (Liste/Ordner) bzw. Blatt abhaken, `n` neue
Liste (inline), `s` reindiven + gleich anhängen, `r` umbenennen (Liste ODER Eintrag,
inline), `d` löschen (Liste mit `j`/Enter-Nachfrage `L["confirm"]`, Eintrag direkt),
`p` Projekt-Flag (schiebt in die obere Zone), `m` verschieben, `>` forest-weit
einordnen, **`f` setzt den Knoten als alleinigen Fokus** (`/api/projects/focus`,
Toggle → rendert dann allein in der rechten FOCUS-Box). `Esc`/`l` schließt.
Reindivt man in eine Liste, ist es die normale Ordner-Sicht (`view`, s.u.); `Esc`
geht eine Ebene zurück, auf der obersten zurück zur Wurzel.
In **view** die Einträge der offenen Liste — **Ordner-Navigation statt
aufgeklapptem Baum**: jeder Eintrag kann eigene
Unterpunkte tragen; ein Eintrag MIT Kindern ist eine anklickbare Ordner-Zeile
(Marker `▸`, Anzeige `(erledigt/gesamt)`), KEIN eingerückter Teilbaum. `L["path"]`
ist der Drill-Pfad (Eintrags-ids) in der offenen Liste, `l_container()` löst die
gerade offene Ebene + Breadcrumb auf, `isel` zählt nur die DIREKTEN Kinder. ↑/↓
wählen, **Enter** geht in einen Ordner REIN (bzw. hakt ein Blatt ab), **`space`**
hakt ein **Blatt** ab/auf (`…/items/<iid>/toggle`), `a` hängt einen Eintrag in die
GERADE OFFENE Ebene an (`L["addparent"]` = Container-id), **`s` hängt einen
Unterpunkt** unter den markierten (macht ein Blatt zum Ordner), **`r` benennt** den
markierten um (vorbefüllt, `POST …/items/<iid>/rename`), **`m` verschiebt** ihn RAUS
in eine andere Liste (→ **move**: Ziel wählen — erste Option `[+ neue Liste]` führt
über **move_new** zu Name-Tippen + `POST /api/lists` und dann
`POST …/items/<iid>/move {into}`; sonst direkt `move` in die gewählte Liste).
Eingabezeile-Modus steckt in `L["imode"]` (`add`/`sub`/`rename`); `a`/`s` bleiben
für Schnell-Eingabe offen, `r` ist einmalig. `d` löscht den markierten samt
Teilbaum. **Abhaken:** nur Blätter sind direkt abhakbar; ein **Ordner** ist NICHT
direkt abhakbar (`space` darauf = Hinweis), sein Häkchen ist **abgeleitet**
(`l_done()` = alle Kinder erledigt → Ordner gilt erledigt; `core.lists.is_done`/
`toggle`→400 spiegeln das). Fortschritt `(erledigt/gesamt)` zählt die **Blätter**
(`l_count`). **Erledigte** Einträge werden **transparent (faint) + durchgestrichen**
gerendert (`addclip(..., strike=True)`, Combining-Overlay U+0336; der Cursor-Pfeil
`›` bleibt normal sichtbar). Lange Ebenen scrollen um den
Cursor. Alles synchron per `api_call()`; nach jeder Aktion `l_load()`+`l_sync_def()`
(offene Liste aus der frischen Registry neu greifen, Drill-Pfad wird validiert/
gekürzt). `Esc`/`l` geht eine Ebene zurück, auf der obersten zurück zur Wurzel
(`forest`); in der Wurzel schließt `Esc`/`l` das Werkzeug.
`--selftest` listet die Listen inkl. erledigt-Zähler (und `◆projekt`-Flag, ohne TTY).
Eine Liste ist kein Zeitreihen-Plot, taucht also nicht in der `lifestyle`-Überlagerung
auf. **Projekt-Flag:** `p` schaltet das Projekt-Flag — in der Wurzel für die
gewählte **Liste** (`POST /api/lists/<lid>/project`) ODER den gewählten
Projekt-Eintrag, in der view-Ebene für den markierten **Eintrag/Unterordner**
(`…/items/<iid>/project`); geflaggte wandern in die obere Zone bzw. tragen ein `◆`/`★`.

**Im Canvas (Browser):** dasselbe Werkzeug, aber der Tab heißt **„Fokus"** und ist
zusätzlich per **Taste `f`** erreichbar (nacktes `f`, wenn kein Eingabefeld
fokussiert ist → synthetischer Klick auf den Fokus-Tab; `data-ex` bleibt intern
`listen`). Die Wurzel ist gleich zweigeteilt (Projekte oben, `── listen ──`
drunter), nur ist die **listen-Zone unten angedockt** (Flex-Feder `.lf-spring` in
`.lf-root`): die Nicht-Projekt-Listen **füllen sich von unten nach oben** auf,
Projekte bleiben oben. Reindive per Klick auf eine Zeile, Aktionen (Fokus ◆ /
Projekt ☆★ / ＋ / ✎ / ✕) als Hover-Icons.

**FOCUS-Box (rechts, alle Fronten):** zwischen `lifestyle` und `outbound` steht
eine `focus`-Box. Quelle ist der schlanke Endpoint **`/api/projects/focused`**
(`core.lists.focused_subtree`): der EINE aktuell fokussierte Knoten (per `f` im
Listen·Fokus-Werkzeug gesetzt, `set_focus`) als Teilbaum — oder **nichts** (Box
entfällt dann ganz). **Darstellung rekursiv:** Knoten **ohne** Unterprojekte →
**Titel + Erfüllungsleiste** (erledigte/alle Blätter rekursiv, `node_progress`);
Knoten **mit** Unterprojekten → **gerahmter Kasten** (Titel im Rahmen, Unterprojekte
drin, KEINE eigene Leiste). Bei Platzmangel wird ab dem Punkt einfach aufgehört
(kein Überlauf). **Reine Anzeige** (Zusammenfassung) — gesetzt/geändert wird im
Listen·Fokus-Werkzeug. In der TUI teilt sie sich `proj_render` mit dem Werkzeug
(BYTE-gleiche Optik, Rahmen aus `┌─┐│└┘`); die Box nimmt `outbound` Höhe ab, nur
wenn dort ≥5 Zeilen bleiben; pollt über `Store._poll_projects` (alle 5 s).
Monolith/Laptop (`#projects`) pollen `/api/projects/focused` (30 s) und rendern
rekursiv `renderNode` (verschachtelte `.prj-box`/`.prj`, `overflow:hidden` clippt).

**Karte (Mitte, Taste `m`):** Maps-System Schritt 1 — grobe Weltkarte (Küsten
1:110m) in der MITTE-Box, analog zum Graph-Werkzeug. Die TUI ist reiner
Zeichner: holt fertig projizierte Linien über `/api/map/base` (Engine in
`core/map/`) und rastert sie per Bresenham. Steuerung `↑↓←→`/`hjkl` pan,
`+`/`−` zoom, `0` reset, `esc`/`m` zu. **`f`** schaltet den Stil um: `outline`
(Küsten-Bresenham `▓`) ↔ `braille` (gefülltes Land in Braille-Punkten, 2×4
Subpixel/Zelle — Endpoint `/api/map/braille`, gerendert in
`core/map/render.py:base_braille`; die TUI druckt nur die fertigen Zeilen). **`o`**
schaltet das **Handelsrouten-Overlay** (Achse 2) ein/aus: leuchtende
`◆`-Marker an den maritimen Engstellen + Detail (Name/heutiger Verkehr) der dem
Fadenkreuz nächsten Stelle, samt Datenstand. Quelle: IMF PortWatch über
`/api/map/layer/trade` (Provenienz/Lizenz: [maps_quellen.md](maps_quellen.md)).
Mit **`w`** klappt die Karte im
**nativen pygame-Fenster** auf (`scripts/map_window.py`, echte antialiased
Vektorgrafik, gleicher Viewport — wie `/slide` PDFs extern öffnet; dort Taste
**`t`** fürs selbe Overlay als Bernstein-Marker); der
ASCII-Grid in der TUI ist nur die reduzierte Variante. Architektur + die drei
Achsen (Detail/Layer/Zeit): [maps_system.md](maps_system.md).

**Kalender (Mitte, Taste `c`):** blätterbare **Woche** (Mo-So-Tagesliste) bzw.
**Monat** (Zeichen-Gitter), umschaltbar. Wie die Karte reiner Zeichner: holt
fertig gruppierte Tage über `/api/calendar` (Logik in `core/kalender.py`,
`week_view`/`month_view`). Steuerung `←`/`h` bzw. `→` blättern (`l` ist jetzt
Sidebar-Fokus, s.u.), `v`/`Tab` Woche↔Monat,
`0` heute, `esc`/`c` zu. Heute hervorgehoben, Monats-Randtage ausgegraut,
`ausfall`-Routinen als `ℹ`. **Anlegen/Ändern/Löschen + Routine-Deaktivieren:**
der ›-Cursor (`↑↓`) läuft über ALLE Einträge (`k_selectable()`); `a` legt neu an,
`e`/Enter bearbeitet (Einmal → gestaffeltes Formular, speichert per PUT; Routine →
De-/Aktivieren-Screen; Spanne → Uhrzeit für diesen Tag), `d` löscht Einmal-Termine
bzw. öffnet bei Routinen denselben Screen. Das Anlege-Formular (`a`) hat drei Typen
(Tab: Termin → Routine → **Mehrtägig**); mehrtägige (ganztägige) Termine spannen
über Von–Bis und erscheinen als **durchgehende Klammer in einer eigenen linken
Spalte** (außerhalb der Tagesdaten), mit dem **Titel senkrecht am Stück** — der
gewählte Tag wird invers markiert (unten `▶ titel · datum`). Einzelne Routine-Vorkommen werden so pro Tag ab-/angeschaltet
(`deaktiviert`, ausgegraut „(aus)"), ohne die Routine zu zerstören. **`x`** blendet
**erledigtes** ein/aus — EIN Schalter über deaktivierte Termine, per Zeitraum
ausgefallene (`ausfall`, Ferien) UND abgehakte Sidebar-Items zusammen (Default
aus, startet aufgeräumt). **Sidebar-Liste (rechts):** die flache »week«-Liste
(`week_items`), wochenunabhängig, Items mit Abstand + Ombre (nach unten
transparenter). **`l`** schiebt den Fokus in die Liste (nur Wochenansicht); dort
`↑↓` wählen, `space`/enter abhaken, `a` neu, `r` umbenennen, `d` löschen, **`s`
Sortier-Modus** (dann verschieben `↑↓` das fokussierte Item), `l`/esc zurück —
**kein** Verschieben in andere Listen. Items, die per Listentool in die
»week«-Liste kopiert wurden, sind verlinkt (`↔`): abhaken spiegelt bidirektional
in die Quelle, Löschen bricht nur den Link. Defensiv wie
der Karten-Pfad (Fehler-Marker statt Dauer-Refetch). Details + die zwei
Browser-Fronten: [kalender_system.md](kalender_system.md).

- **Nur stdlib:** `curses` + `urllib` + `json` + `threading` — null Extra-Deps.
  Setzt UTF-8-Locale vor curses-Init (für Box-/Block-Zeichen).
- Ein Hintergrund-Thread pollt, der curses-Loop liest den Snapshot (thread-safe
  über Lock). Bei Backend-Ausfall: Header zeigt `[backend ?]`, kein Crash.
- `--selftest` gibt einen Text-Snapshot ohne curses aus (Verifikation ohne TTY).
- Backend läuft im `tui`-Mode (KI aus, wie laptop). Start: `zentrale-tui`
  fährt Backend (stdout → Logdatei, nicht ins Terminal) + TUI hoch. Siehe
  `starten.md`. Env `ZENTRALE_URL` überschreibt das Backend-Ziel (Default
  `http://localhost:5000`).

## Stack

- **Backend**: Flask (`ui/app.py`).
- **Frontend**: ein einziges `index.html` mit Vanilla JS, SVG-Charts,
  kein CDN, kein Build-Step. Bewusst gewählt – das Ding muss auf einem
  Pi im Kiosk-Modus offline laufen.

## Polling-Modell

Drei separate Polling-Loops im Frontend, jeder mit eigener Frequenz:

| Endpoint              | Intervall | Was es liefert                                  |
|-----------------------|-----------|-------------------------------------------------|
| `GET /api/state`      | 1 s       | Events, Sensoren, Logs (Haupt-State). Das frühere Feld `vocab` ist **entfernt** (2026-07-17): es kam aus `main.py:_load_vocab()`, das die längst gelöschte `vocab_mandarin.json` las (immer `null`) und über den Port hinweg in Tutor-Daten griff — samt der toten `set_vocab`/`_vocab`-Kette in `state.py` raus |
| `GET /api/ai/status`  | 30 s      | Ollama erreichbar? + Modell-Name                |

> Das frühere 3 s-**Dauer**-Polling gegen `/api/tutor/status` ist raus — nicht
> weil der Tutor pausiert (er läuft), sondern weil es nichts kostet, den Status
> **bei Bedarf** zu holen: `startTutor()` fragt ihn einmal vor dem Kanalwechsel
> (`monolith.html`). Die TUI pollt ihn weiterhin für ihr Panel. Siehe
> `tutor_system.md`.

Kein WebSocket, kein SSE für Statusdaten – Polling reicht für
ein Single-User-Dashboard und ist deutlich simpler.

Streaming wird **nur** dort benutzt, wo es wirklich nötig ist:

- `POST /api/chat` – Server-Sent Events (SSE), damit Tokens live
  erscheinen.

## Monolith-Dashboard (Route `/`, source of truth)

Das gelebte Dashboard (`ui/templates/monolith.html`, ein einziges großes HTML mit
mehreren IIFE-Script-Blöcken). Seit 2026-06-08 unter `/` (Alias `/monolith` bleibt
für Kiosk/Bookmarks). Herzstück ist ein
animierter **ASCII-Kern** (`#core`), gesteuert vom *Exhibit-Direktor*
(`frameTick`, 90 ms/Frame). Umschaltbare Exhibits über Tabs: `gesicht`
(Avatar), `torus`, `würfel`, `globus`, `welt` (Weltkarte), `filter`
(Bild→ASCII-Filter aus `data/photos/`, mono/farbe per Re-Klick), `graph`
(s.u., interaktives Panel statt ASCII) und `kalender` (s.u.). `graph` und
`kalender` sind **nicht** im Auto-Direktor (interaktiv, nicht zum Durchzappen).

> **Graph-Werkzeug (Exhibit `graph`)** — der Mittelbereich wird zum
> interaktiven Lifestyle-Tracker: eigene Graphen **anlegen** (Typ `number`
> = freie Messwerte/Kurve, oder `scale` = 1–5), **Werte eintragen** (Datum
> + Wert), **Kurve sehen** (SVG-Plot via `viz.js`). Bei `graph` blendet
> `frameTick` `#core` aus und `#graph-panel` (`.gpanel`) ein und steigt
> früh aus (kein ASCII-Tick). Definitionen serverseitig in
> `data/graphs.json` (`core/graphs.py`, Endpoints `GET/POST /api/graphs`,
> `DELETE /api/graphs/<id>`); die Messwerte teilen sich die
> Data-Collection (`/api/log` schreibt nach `data/<graph_id>.json`,
> `/api/data/<id>` liest). Jeder gespeicherte Wert feuert `zentrale:logged`
> → die `lifestyle`-Box rechts zeigt jeden angelegten Graphen automatisch
> als Sparkline (Quelle: `/api/graphs`, Feld `value`).
>
> **Geteilte Logik, pro Kassette verbaut:** `core/graphs.py` + die
> `/api/graphs`-Endpoints existieren für ALLE Kassetten; nur die UI ist
> kassetten-spezifisch verkabelt — Monolith hier (Browser-Panel), TUI in
> der curses-Mitte (Taste `g`, siehe „Terminal-Kassette"). `laptop.html`
> ist (noch) nicht verkabelt. Das **Anlege-Formular im Monolith** bietet nur
> `number`/`scale`; die Uhrzeit-Typen `time`/`period` (Y-Achse = Uhrzeit)
> legt man in der TUI an (Backend kennt alle vier). Ein so angelegter
> `time`/`period`-Graph erscheint in der Monolith-`lifestyle`-Box als
> Sparkline über `value` (Minuten) — funktioniert, nur ohne HH:MM-Format.

> **Kalender (Exhibit `kalender`)** — der Mittelbereich zeigt den Kalender:
> blätterbare **Woche** (Mo-So-Liste) bzw. **Monat** (Gitter), umschaltbar,
> heute hervorgehoben, `ausfall`-Routinen als `ℹ`, Header-Zähler `⚠N` aus den
> offenen Alarmen. Eigenes `#calendar-panel` (`.cpanel`, `frameTick` blendet wie
> bei `graph` `#core` aus). Reiner Zeichner: Daten von `/api/calendar`
> (`view`+`ref`), Datums-Logik in `core/kalender.py`. **Derselbe Endpoint** für
> alle Fronten (Browser-Tab „Kalender", TUI-Taste `c`). „＋ Termin"-
> Form hat drei Typen (Termin / Routine / **Mehrtägig** mit Von–Bis); pro Termin
> ✎ (bearbeiten → PUT) / ✕ (löschen); mehrtägige Spannen als gepunkteter Chip mit
> `┌│└`-Marker (Titel nur am ersten Tag), ✎ = Uhrzeit für diesen Tag, ✕ = ganze Spanne;
> Routine-Vorkommen ⊘/↺ (diesen Tag de-/aktivieren → `…/routine/skip`),
> deaktivierte durchgestrichen-grau. Der Knopf „🚫/👁 erledigte" blendet
> deaktivierte + ausgefallene (Ferien) Termine + abgehakte Sidebar-Items **gemeinsam** ein/aus
> (Default aus). **Rechte Sidebar** (`renderSidebar`): die flache »week«-Liste
> (Abstand + Ombre nach unten) — klick abhaken, `▲▼` sortieren, `✎` umbenennen,
> `✕` löschen, Add-Feld; verlinkte Kopien (`↔`) spiegeln beim Abhaken
> bidirektional in die Quelle. Kein Move in andere Listen.
> Schreiben ist direkte Nutzeraktion, **nicht** KI-gegatet. Details:
> [kalender_system.md](kalender_system.md).

> Die IIFEs sind getrennte Scopes. Cross-Scope-Signale laufen über den
> CustomEvent-Bus auf `window` (`zentrale:logged`, `zentrale:ascii`),
> nicht über geteilte Funktionen.

### Layout (was Sasha real sieht)

`#stage` ist 1920×1080 (Kiosk, scale-to-fit). Oben eine schmale Statusleiste
(`.top`: „ZEN · monolith · adaptive konsole", Ollama/Netz/Uptime, Theme
AUTO/HELL/DUNKEL). Darunter `.body` als 3 Spalten:

```
+------------+----------------------+------------+
| LINKS      |  MITTE (#col-mid)    | RECHTS     |
| telemetrie |  ki-kern:            | lifestyle  |
| stdout     |   tabs + #core       |  (tracker) |
| (#term)    |   + ⚠ alarm-corner   | outbound   |
|            |  konsole (chat-in)   |  (#term-net|
|            |  minilog + cinema-sub|   tripwire)|
+------------+----------------------+------------+
```

> **Sensoren-Panel entfernt (2026-06)** — in allen Kassetten, inkl. Monolith
> (Details + Backend-bleibt-verkabelt: siehe „## Kassetten"). Auch der
> `_DASHBOARD_VIEW`-Prompt in `core/ai.py` nennt die Sensoren nicht mehr.

- **LINKS:** `telemetrie` (PC·CPU-Meter), `stdout` (`#term`, voller Log-Stream
  aus `state.push_log`).
- **MITTE (`#col-mid`):** die `ki-kern`-Box mit Exhibit-Tabs (Gesicht/Torus/
  Würfel/Globus/Welt/Filter/Graph/Auto) + dem ASCII-Kern `#core` (s.u.) + der
  Alarm-Ecke; darunter `core-readout` (AI-State „BEREIT", „zeigt: gesicht"), das
  `minilog` (letzte Konversationszeilen) und `#cinema-sub`. Darunter die
  `konsole` (`#chat-input`, wo Sasha tippt). Der `Graph`-Tab macht den
  Mittelbereich zum Graph-Werkzeug (s.o.).
- **RECHTS:** `lifestyle` (Tracker: hartkodierte Kategorien + jeder im
  Graph-Werkzeug angelegte Graph als Sparkline) + `projects` (`#projects`,
  als Projekt geflaggte Listen/Einträge, verschachtelt mit Leisten & gerahmten
  Unterprojekten, Quelle `/api/projects`) +
  `outbound` (`#term-net`, Internet-Tripwire, Idle „// offline ✓").

### Alarm-Ecke (`#alarm-corner`) — die ⚠-Warnsymbole

Unten links **in `.core-wrap`** (also am ASCII-Kern), `position:absolute`
left/bottom 12px, `flex column-reverse`. Pro offenem Kalender-Alarm ein
Pixel-**Warndreieck** (`.alarm-tri`, `<title>`=Volltext für Hover), gedeckelt auf
`ALARM_MAX=5` + „+N"-Indikator. Quelle: `e.alarms` aus `/api/state`
(= `kalender.open_alarms`), gerendert von `renderAlarms()`. Leer → Ecke leer.
Im Cinema-Modus verblasst sie (`opacity .12`, Puls aus). **Das ist „die Warnung im
Dashboard", auf die Sasha zeigt** — die KI weiß davon seit 2026-06 über den
`_DASHBOARD_VIEW`-Prompt-Block (`core/ai.py`), damit sie die Frage „was ist diese
Warnung?" mit dem Alarm-Block verbindet statt „kenne dein Dashboard nicht" zu
sagen (Hintergrund: `grounding_recherche.md`).

### ASCII-Kern / Bild-Marker (KI redet visuell)

Tippt die KI in ihrer Antwort den Marker `[[bild: stichwort]]` (Backend-
Pipeline + Begründung der Marker-statt-Tool-Entscheidung siehe
`ki_system.md`), übernimmt das gematchte ASCII-Bild den Kern **auf Zeit**:

- **Transport:** Das Backend zieht den Marker aus dem Antworttext und
  yieldet das Bild **inline** im SSE-Antwort-Stream → Event `data.ascii`
  (der Marker selbst erreicht das Frontend nie als Text). Der Chat-IIFE-
  Leser feuert daraus ein `window`-Event `zentrale:ascii` `{art, name}`;
  der Exhibit-Direktor (andere IIFE) hört darauf und ruft `showAiArt()`.
  So erscheint das Bild synchron, während die Worte streamen.
- **Anzeige:** `showAiArt` setzt `aiArt` (Vorrang vor allen Exhibits).
  `frameTick` blendet das Bild zeilenweise ein (`AI_ART_REVEAL` ≈ 14
  Frames), hält es `AI_ART_HOLD` ≈ 110 Frames (~10 s) und kehrt dann
  automatisch zum normalen Auto-Programm zurück (`syncTabs`).
- Kein Text → nicht im Minilog, kein TTS. Reine Mimik zur Antwort.

### KI-Reflexion im Kern (sichtbares Thinking)

Denkt die KI vor einer Antwort (adaptives Thinking, `core/ai.py`
`_should_think` → nur Verständnis-/Verifikations-Turns, siehe `ki_system.md`),
**tickert ihr innerer Monolog live in den Kern** — sichtbares „ich schau kurz
nach…" statt totem Warten (so wird die ~3× Latenz UX-Gewinn statt -Verlust).

- **Transport:** Ollama liefert die Denk-Tokens getrennt im `thinking`-Feld.
  `chat_stream` yieldet sie als `{"reflect": …}`; `app.py` reicht sie als SSE-
  Event `data.reflect` durch (NICHT in `collected` → nicht gespeichert, nicht
  gesprochen). Der Chat-IIFE-Leser feuert daraus `zentrale:reflect` `{text}`;
  der Exhibit-Direktor hört darauf (wie bei `zentrale:ascii`).
- **Anzeige:** `reflectActive` hat **allerhöchsten Vorrang** im `frameTick`
  (über KI-Bild, Graph und Kalender). `wrapReflect` bricht den Strom auf feste
  Breite um und zeigt tail-scrollend die letzten Zeilen; CSS-Klasse
  `#core.reflecting` (gedämpft, linksbündig, kursiv, sanfter Puls) setzt ihn vom
  restlichen Kern ab. Meta-Zeile = „ki denkt nach…".
- **Ende:** Beim ersten echten Antwort-Token (oder Stream-Ende/Fehler) feuert
  der Chat-IIFE `zentrale:reflect-end` → Kern frei, Direktor übernimmt wieder
  (`syncTabs`). Die eigentliche Antwort erscheint wie gewohnt im Minilog.
- Kill-Switch `ZENTRALE_THINK=0` (siehe `starten.md`) → kein Thinking, kein
  Reflexions-Strom (Verhalten wie davor).

### Sendungs-/Cinema-Modus (News-Sendung)

Liest die KI eine News-Sendung vor (Tool `lies_news`), schaltet das Dashboard
in einen Kino-Modus: **Seiten-Spalten + Header dimmen sanft** (`opacity .3`),
die **Mittelspalte (`#col-mid`) bleibt hell** und der **Kern (`#core`) voll
sichtbar** (Animationen/Bilder laufen weiter — kein schwarzer Vollvorhang!).
Der **gerade gesprochene Satz** erscheint groß als **Lower-Third** (`#cinema-sub`
unten in `.core-wrap`), synchron zur Satz-TTS (`drainSpeakQueue`/`audio.onended`).
`#minilog` (letzte User-Zeile) faded raus; Konsole schrumpft + dimmt (klart beim
Tippen). Trigger: SSE-Event `data.cinema` (Backend yieldet `{cinema:true}` wenn
`lies_news` läuft) → `enterCinema()` setzt `data-cinema="on"` aufs Stage.
Schließt am Sendungsende (`done` + letzter Satz) oder bei `stopSpeaking`; bei
`chatMuted` aus. Voller Mechanismus: [news_system.md](news_system.md).

### Knopf-Leiste (2–4 Knöpfe statt Eingabe)

Zwei Auslöser, dieselbe Leiste: das Backend fängt ein bestätigungspflichtiges
Schreib-Tool ab (Auto-Gate, Default JA/NEIN) **oder** die KI ruft selbst
`frage_knopf` mit eigenen Labels (Backend-Mechanik + Begründung siehe
`ki_system.md`). Der Chat-IIFE tauscht die Konsolen-Eingabe gegen die Knöpfe:

- **Transport:** SSE-Event `data.permission {frage, optionen}` (parallel zu
  `token` und `ascii` im selben `/api/chat`-Stream; `optionen` fehlt beim
  Auto-Gate → Default `['ja','nein']`). Der Reader zeigt die Frage als KI-Zeile
  im Minilog + TTS, ruft `showPermissionDialog(optionen)` und liest **weiter** –
  der Stream bleibt offen, das Backend blockiert.
- **Anzeige:** `#perm-bar` (im `.console`-Row, default `display:none`) blendet
  sich ein, `#chat-input`/`#chat-mic-btn` aus (der `›`-Prompt bleibt als Anker).
  Die Knöpfe baut das JS dynamisch in `#perm-btns` (ein `.perm-btn` pro Label,
  Großschreibung per CSS), der angewählte trägt `.sel` (Akzentfarbe).
- **Navigation:** Pfeil ← → zykliert `permSel` modulo durch die N Knöpfe, Enter
  wählt den aktiven (`permOptions[permSel]`). Listener auf `document` mit
  `capture=true`, weil das versteckte Input keinen Fokus mehr hat. Maus-Klick
  geht auch (jeder Knopf hat seinen eigenen Click-Handler).
- **Antwort:** `submitPermission(label)` blendet die Leiste zurück, stoppt eine
  noch laufende TTS-Frage, setzt AI-State `thinking` und feuert `POST
  /api/permission_answer {answer: label}` (fire-and-forget) → entsperrt den
  wartenden Stream, der Rest der Antwort streamt auf demselben Reader weiter.
  Bricht der Stream beim Warten ab, stellt der `finally`-Zweig die normale
  Eingabe wieder her (kein Hängenbleiben).

## Data Collection

Taste `K` öffnet den Data-Collection-Modus.

**Kategorie-Auswahl:**
- `1`, `2`, … – Kategorie wählen
- `ESC` oder `K` – zurück

**Formular:**
- `↑` / `↓` – zwischen Feldern navigieren
- `Enter` – Feld bearbeiten
- `K` – **speichern** und zurück
- `ESC` – zurück **ohne** zu speichern

(Vollständige Tastenliste inkl. Smiley- und Date-Edit: `tastatur.md`.)

**Feld-Typen:**
- `date` – Datum, mit `↑`/`↓` tageweise ändern
- `smiley_scale` – 5 SVG-Smileys (😞→😄), mit `←`/`→` auswählen
- `text` – einfaches Eingabefeld (Placeholder-Implementierung)

### Aktuell vorhandene Kategorien

In `core/categories.py` sind bereits zwei Kategorien definiert:

| `id`            | Name           | Felder                                            |
|-----------------|----------------|---------------------------------------------------|
| `sleep_quality` | Sleep Quality  | `date` (date), `quality` (smiley_scale, 5 Stufen) |
| `food_intake`   | Food Intake    | `date` (date), `meal` (text)                      |

Das Sleep-Quality-Chart auf dem Haupt-Dashboard ist hardcoded auf die
`sleep_quality`-Daten – andere Kategorien werden aktuell nur im
Data-Collection-Modus verwaltet, nicht visualisiert.

### Neue Kategorie hinzufügen

In `core/categories.py`:

```python
{
    "id": "meine_kategorie",
    "name": "Meine Kategorie",
    "fields": [
        {"id": "date",    "label": "Date",    "type": "date"},
        {"id": "quality", "label": "Qualität", "type": "smiley_scale", "steps": 5},
    ],
}
```

Daten landen automatisch in `data/<id>.json`.
