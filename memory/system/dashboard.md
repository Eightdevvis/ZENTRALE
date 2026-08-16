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
  Env-Var). Siehe `memory/betrieb/starten.md`.

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
Karte/Graphen/Kalender/Listen/Post/Klavier, Telemetrie, Logs, Data-Collection
(Alt+K).
Statt der Chat-Zeile steht unten die **Tastenkürzel-Box** (Quelle:
`memory/system/tastatur.md`).

> **Sensoren-Panel entfernt (2026-06):** in ALLEN Kassetten ist die Sensoren-
> Anzeige raus — kein echter Sensor angeschlossen. Das **Backend bleibt
> verkabelt** (Event-Loop, `/api/sensor/<name>`-Webhook, `sensors` in
> `/api/state`); zum Wiederanzeigen Box + Handler aus der git-History
> zurückholen (das tote `.srow`-CSS steht im Template noch bereit).

- **Mitte:** dieselben Werkzeug-Tabs wie im Monolith — **Graph**, **Kalender**,
  **Fokus** (Listen·Fokus, auch per Taste `f`), **Post** (Mail), **Karte**
  (Globus/Welt), **Klavier** (auch per Taste `k`) — plus die Animationen.
  In der **TUI** dieselben Werkzeuge über Tasten (`g`/`c`/`l`/`p`/`m`/`k`),
  das Klavier inklusive (Ton rechnet `core/tone.py` selbst, siehe unten).
- **Minimale Boot-Dependencies:** nur `flask` + `python-dateutil` (kein
  Whisper/TTS/sherpa/piper nötig — die Kassette ist KI-frei). Siehe `memory/betrieb/starten.md`.

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

**Wann die Applier laufen (seit 2026-07-27):** die TUI färbt sich selbst sofort
um (~18 ms), die **Umgebungs-Applier** sind davon entkoppelt — sie färben die
ganze XFCE-Sitzung um (GTK-, Fenster- **und Icon-Theme**), und besonders der
Icon-Wechsel lässt jede GTK-App neu laden, das ruckelt sichtbar. Deshalb:
(1) sie laufen nur, wenn sich das **aufgelöste** Theme (hell/dunkel) wirklich
ändert — `t` zykliert `auto→day→night→auto`, und zwei dieser drei Schritte
lassen die Farbe gleich (z.B. `auto(night)→night`); früher färbte jeder davon
den Desktop um. (2) Danach 0,5 s **Debounce**: dreimal schnell `t` löst EINEN
Umbau aus statt drei. Die Datei `~/.config/zentrale/theme` wird weiterhin
sofort geschrieben (nvim und der systemd-Timer lesen den MODUS, nicht die
Farbe) — sie ist billig, aber **atomar** (tmp + `os.replace`, siehe
nvim-Kopplung unten).

**Die TUI zieht Fremdänderungen seit 2026-08-16 nach (`_pull_term_theme`).**
Bis dahin war sie der einzige Teilnehmer der Kopplung **ohne Rückkanal**: nvim
beobachtet die Datei (fs_event + Tick), Terminal/Browser/Desktop/bat ziehen sie
per Minuten-Timer nach — die TUI las sie einmal beim Start und behauptete
danach ihren eigenen Modus. Schrieb irgendwer sonst hinein, lief die Anzeige
gegen den Rest der Umgebung: **alles dunkel, TUI zeigt weiter hell.** Genau
dieses Bild ist am 2026-08-16 aufgetreten (Datei um 15:21:38 auf `night`
gesetzt, die Applier zogen erst beim Timer-Tick 62 s später nach — also hatte
sie *nicht* die TUI geschrieben, die stößt sie sofort an). Erkannt wird über
die mtime; das eigene Schreiben merkt sich `_push_term_theme` in `_theme_seen`
und kommt daher nicht als fremd zurück. Beim Mitziehen wird **nicht**
zurückgeschrieben — die Datei bleibt die Wahrheit.

**Änderungsprotokoll + Beobachter.** Wer die Datei ändert, war rückwirkend
nicht feststellbar (der Zeitstempel verrät nur das WANN). Seitdem:
- Die TUI schreibt jeden Wechsel nach `~/.cache/zentrale/theme-changes.log`,
  mit Quelle `tui` (Taste/Befehl) oder `fremd` (Datei änderte sich unter uns).
- `scripts/zentrale-theme-watch` hängt per inotify am **Verzeichnis** (die
  Datei wird atomar per tmp+rename ersetzt — ein Watch auf der Datei säße
  danach auf einem toten inode) und protokolliert jede echte Inhaltsänderung
  nach `~/.cache/zentrale/theme-watch.log`, mit Prozess-Schnappschuss und dem
  Hinweis, ob die TUI sich als Urheber eingetragen hat. **Grenze:** inotify
  meldet das Ereignis, nicht den Verursacher — den sauber zu benennen bräuchte
  fanotify/auditd und damit root. Ein kurzlebiger Schreiber (`printf > datei`
  aus einer Shell) ist im Schnappschuss schon wieder weg; auch das ist eine
  Aussage (kein Dauerläufer). Läuft als User-Dienst
  `deploy/zentrale-theme-watch.service`, aktiviert von
  `install_theme_coupling.sh`, sofern `inotifywait` da ist.
  `zentrale-theme-watch --status` zeigt beide Protokolle.

**Der Start-Modus kommt seit 2026-08-16 aus der Datei, nicht mehr hart aus
`auto`.** Vorher stand `theme_mode = "auto"` fest im Code und wurde beim Start
sofort in die Datei geschrieben: **jeder** TUI-Start — auch ein tmux-Restore,
ein Neustart nach Absturz oder eine zweite Instanz — hat damit ein von Hand
gesetztes `day`/`night` überschrieben, worauf nvim und Terminal auf die
Uhrzeit-Auflösung sprangen. Jetzt liest die TUI die Datei beim Start und
schreibt nur noch, wenn SIE etwas ändert.

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
jede Minute nach → die 05/21-Rotation greift auch ohne laufende TUI.
**Die Applier fassen dabei seit 2026-08-16 nur noch an, was sich wirklich
ändert** — vorher schrieben sie jede Minute bedingungslos die volle Palette
bzw. GTK-/Fenster-/Icon-Theme neu. Sichtbare Folgen: das Terminal färbte im
Minutentakt live um (ein Zucken mitten in nvim), jede GTK-App lud ihre Icons
neu, und jedes `gsettings set` feuerte ein Portal-Signal, auf das Brave mit
einem Theme-Neuaufbau antwortete. `zentrale-term-theme` merkt sich den zuletzt
gesetzten Modus in `~/.cache/zentrale/term-theme.applied` (erst NACH dem
Setzen gestempelt, damit ein Abbruch beim nächsten Lauf erneut greift;
`--force` übergeht das Gate); `zentrale-desktop-theme` und
`zentrale-browser-theme` vergleichen stattdessen den aktiven
xfconf-/gsettings-Wert und setzen nur bei Abweichung, `zentrale-bat-theme` die
`--theme`-Zeile in seiner Config. Beim Umschalten in der TUI werden **alle
vier** Applier direkt angestoßen (bat inklusive — sonst zöge es erst beim
nächsten Minuten-Tick nach). Nur lokal,
kein Sync, kein Backend — TUI ist die einzige Quelle. **Setup reproduzierbar
in git:** Unit-Templates `deploy/zentrale-theme.{service,timer}` (zwei
`ExecStart`-Zeilen: Terminal + Browser), Einrichten per
`scripts/install_theme_coupling.sh` (Symlinks + Units nach
`~/.config/systemd/user/` + `enable --now`, nimmt nvim mit; idempotent, kein
sudo; hieß bis 2026-07-25 `install_term_theme.sh`, die alten Unit-Namen räumt
es beim Lauf ab).

**bat-Kopplung (`batcat`, seit 2026-08-16):** zwei eigene Themes,
`zentrale-cyber` (night) und `zentrale-paper` (day), im Repo unter
`bat/themes/*.tmTheme`.

- **Generiert, nicht handgepflegt:** `scripts/build_bat_themes.py` liest die
  Farben aus **derselben** `nvim/lua/zentrale_theme/palettes.lua` wie nvim und
  die Fläche aus `scripts/zentrale-term-theme`. Zwei handgepflegte XML-Dateien
  daneben wären beim nächsten Palette-Nachjustieren still auseinandergelaufen
  (das Papier ist schon einmal von Creme auf Sepia gewandert). Die erzeugten
  Dateien sind eingecheckt; `--check` vergleicht sie gegen die Palette und
  `tests/test_bat_theme.py` schlägt bei Drift Alarm.
- **Fläche vom TERMINAL, nicht von nvim — bewusster Unterschied.** nvim setzt
  sich ab (Sepia `#ece0c0` gegen Terminal-Creme `#f3ecd9`), damit man sieht,
  dass man im Editor ist. bat ist kein Editor, sondern Terminalausgabe: sie
  soll nahtlos in den Scrollback fließen. Praktischer Nebenbefund: **bat malt
  die Grundfläche ohnehin nicht** — es setzt nur Vordergrundfarben und erbt den
  Terminalhintergrund. Der `background`-Wert im tmTheme dient der Hell/Dunkel-
  Einordnung; gemalt wird eine Fläche nur bei `--highlight-line`
  (`lineHighlight`). Die Syntaxfarben sind gegen nvims dunklere Fläche
  gerechnet, stehen hier also auf hellerem Grund → Kontrast wird besser, nie
  schlechter. Der Kontrast-Wächter im Test misst gegen die Terminalfläche.
- **Scope→Rolle spiegelt `highlights.lua`:** dieselbe Rolle bekommt dieselbe
  Farbe, damit eine Datei in bat und nvim gleich aussieht. Sublime-Scopes sind
  feiner als nvims Gruppen, deshalb mehrere Scopes pro Rolle. Kommentare kursiv
  wie in nvim.
- **Umgeschaltet wird über die Config:** bat ist kein laufender Prozess, den man
  umfärben könnte — es liest `~/.config/bat/config` bei **jedem** Aufruf.
  `scripts/zentrale-bat-theme` schreibt dort nur die `--theme`-Zeile um (Rest
  der Datei bleibt, Schreiben über tmp + `mv`), der nächste `batcat` hat die
  neue Farbe. Eigenes „nur bei Änderung"-Gate wie die anderen Applier.
- **Einhängen:** `scripts/install_bat_theme.sh` (kopiert die Themes nach
  `~/.config/bat/themes/`, **baut den bat-Cache neu** — ohne das kennt bat
  eigene Themes nicht — und verlinkt den Applier). Läuft aus
  `install_theme_coupling.sh` mit, wenn `bat`/`batcat` da ist; der
  systemd-Service ruft den Applier mit führendem `-` auf, weil bat optional ist.
  Auf Debian/Mint heißt das Binary **`batcat`** (Paketnamen-Kollision), sonst
  `bat` — beide Installer und Tests suchen erst `batcat`, dann `bat`.

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

> **Korrektur 2026-08-03 — der „Use GTK"-Teil griff bei Brave nie.**
> Der Absatz darüber beschreibt die *Absicht*, nicht das, was passiert ist. Brave
> ist hier ein **Flatpak**, und daran sind drei Dinge gescheitert:
> 1. **Brave stand gar nicht auf GTK.** Pref `extensions.theme.system_theme` war
>    `0` (= klassisches Theme), nicht `1` (= GTK). Damit ignoriert Brave das
>    GTK-Theme vollständig. Das war die Hauptursache.
> 2. **Der Sandkasten sah die Theme-Dateien nicht.** Unter `/usr/share/themes`
>    lagen dort nur „Default" und „Emacs". Durchreichen per
>    `flatpak override --filesystem=/usr/share/themes:ro` wird **abgelehnt**:
>    *„Not sharing /usr/share/themes with sandbox: Path /usr is reserved by
>    Flatpak"* — der Exit-Code ist trotzdem 0, es fällt also nur auf, wenn man
>    hinterher nachsieht. Der einzige Weg führt übers Heimverzeichnis.
> 3. **Flatpaks lesen den Theme-NAMEN aus GSettings, nicht aus xfconf.** Dort
>    standen noch die Vor-ZENTRALE-Werte (`Mint-L-Darker-Teal`, `HighContrast`),
>    weil `zentrale-desktop-theme` nur xfconf beschrieben hat.
>
> **Gefixt** (Commit `a73af03`): aktives Theme wird nach
> `~/.local/share/themes` gespiegelt (~3–4 MB je Theme, das Skript heilt das
> selbst), Sandkasten geöffnet mit
> `flatpak override --user com.brave.Browser --filesystem=xdg-data/themes:ro`,
> und `zentrale-desktop-theme` spiegelt `gtk-theme`/`icon-theme` zusätzlich nach
> `org.gnome.desktop.interface`. `color-scheme` bleibt dort außen vor — das
> gehört `zentrale-browser-theme`.
> Nebenbefund: `cp -al` (Hardlinks, 0 Byte) geht **nicht** —
> `fs.protected_hardlinks` verbietet Hardlinks auf fremde Dateien.
>
> **Zwei Handgriffe bleiben von Hand:** `brave://settings/appearance` auf **GTK**
> stellen (Chromium überschreibt `Preferences` beim Beenden, solange es läuft —
> kein Skript kann das) und Brave **neu starten** (neue Sandkasten-Rechte gelten
> nur für eine frisch gestartete Instanz).
>
> **Nachprüfen, ob es im Sandkasten ankommt:**
> ```
> flatpak run --command=sh com.brave.Browser -c \
>   'ls ~/.local/share/themes; gsettings get org.gnome.desktop.interface gtk-theme'
> ```
> Ausführlich in `memory/betrieb/browser.md`.

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
- **Nvims eigene Erkennung wird ABGESCHALTET (seit 2026-08-16) — das war die
  Ursache für dauerndes Theme-Flackern.** nvim hängt beim TTY-Start in der
  Gruppe `nvim.tty` eine `TermResponse`-autocmd ein, die bei **jeder**
  OSC-11-Antwort des Terminals die Luminanz misst und `background` danach setzt
  — die ganze Sitzung lang. Sie räumt sich bei `VimEnter` selbst weg, aber nur
  wenn `background` gesetzt wurde **und** `last_set_sid ~= -8`; `-8` ist
  `SID_LUA`, also gilt alles aus Lua Gesetzte dort als „nicht vom Benutzer".
  Wir setzen aus Lua → sie überlebte und kämpfte gegen unser Theme: Terminal
  färbt um (der systemd-Timer tat das **im Minutentakt bedingungslos**), eine
  OSC-11-Antwort trudelt ein — bei mehreren nvims an EINEM tmux-Server gern in
  der falschen Pane —, nvim stellt `background` um, unsere `OptionSet`-autocmd
  trug alles neu auf, die nächste Antwort drehte es zurück. Ping-Pong.
  `M._disarm_nvim_bg_detect()` löscht die autocmd jetzt in `setup()` und
  nochmal bei `VimEnter`. Für uns ist die Terminal-Luminanz ohnehin keine
  Quelle — die Wahrheit steht in `~/.config/zentrale/theme`.
- **Gegen fremde `background`-Wechsel verteidigt:** ein Wechsel von `background`
  löscht in nvim ALLE Highlights samt `colors_name`. Abgefangen per
  `OptionSet background` **und** einmaligem `VimEnter` (während des Startups
  feuert OptionSet nicht). Beide reagieren nur noch, wenn `_needs_reapply()`
  eine echte Abweichung vom Soll sieht — Wert **oder** `colors_name` (nvim
  wischt auch dann, wenn der neue Wert derselbe ist, den wir wollten). Das
  frühere blinde `refresh(true)` bei jedem Ereignis war der halbe Flacker-Motor.
- **Kein Blitz beim Umschalten mehr:** `load()` setzt `colors_name` auf `nil`,
  BEVOR `background` kippt. Sonst lud nvim bei jedem Wechsel das noch
  eingetragene — also das gegenteilige — Scheme neu, das per `_applying` zum
  No-Op wurde und für einen Frame nackte Default-Highlights stehen ließ.
- **Kein Fehl-Flip bei halb geschriebener Datei:** wer die Theme-Datei per
  truncate+write ersetzt, ist dazwischen kurz bei **null Bytes** — und genau da
  feuert der fs_event. Das als `auto` zu lesen hieß: auf die Uhrzeit fallen und
  beim Folge-Event zurückspringen. `resolve()` behält bei leerem Inhalt jetzt
  den aktuellen Modus; die TUI schreibt zusätzlich **atomar** (tmp + `os.replace`).
  Der Watcher sammelt Events außerdem 60 ms auf, statt pro Schreibvorgang zwei-
  bis dreimal den vollen Highlight-Aufbau zu fahren, und gibt sein altes
  fs_event-Handle beim Neu-Bewaffnen wirklich frei (`:close()`, vorher leckte
  eines pro Theme-Wechsel).
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
bleiben leer; der rechte Rand ist IMMER heute und rollt tageweise weiter, auch
die Zyklus-Vorhersage schiebt ihn nicht vor), Y **bewusst mehrdeutig** — jeder Graph nutzt seine *eigene*
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

**Zyklus/PMS (nur beim Graphen »periode«):** aus den Werten dieses
Graphen leitet `core/cycle.py` ab, wann die nächste Periode fällig ist (letzter
Block-Start + Schnitt der echten Abstände) und färbt die Woche davor als
PMS-Fenster. Quelle `GET /api/cycle`. Drei Orte:
- **als Zeile** im Graph-Werkzeug, leise in Altrosa — TUI: Liste `◆ dd.mm.` am
  periode-Graphen, Solo die volle Zeile über der Eingabe; Browser: `.gcyc`
  unter der Kurve.
- **in der Kurve (nur TUI)**: die Zeitachse der Überlagerung — kleine
  `lifestyle`-Box wie große Ansicht, beides `draw_overlay` — tönt PMS-Woche und
  erwarteten Start als **Zellen-Hintergrund** (wie die Schlaf-Bande, nur so
  liegt es hinter den Werten), `◆` + Datum in Altrosa markieren den Starttag.
  **Vorrang: Schlaf-Bande vor Zyklus-Fläche**, Werte über beidem. Die **Achse
  bleibt unangetastet** — sie endet heute und rollt tageweise weiter, getönt
  wird nur, was schon im Bild ist (`cycle_axis`). Im Browser gibt es das nicht:
  dessen Plot hat keine Datumsachse (x = Nr. des Werts).
- **im Kalender** als Tages-Tönung.

Volle Beschreibung: `memory/werkzeuge/zyklus_pms.md`.

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
`/api/map/layer/trade` (Provenienz/Lizenz: [memory/maps/maps_quellen.md](memory/maps/maps_quellen.md)).
Mit **`w`** klappt die Karte im
**nativen pygame-Fenster** auf (`scripts/map_window.py`, echte antialiased
Vektorgrafik, gleicher Viewport — wie `/slide` PDFs extern öffnet; dort Taste
**`t`** fürs selbe Overlay als Bernstein-Marker); der
ASCII-Grid in der TUI ist nur die reduzierte Variante. Architektur + die drei
Achsen (Detail/Layer/Zeit): [memory/maps/maps_system.md](memory/maps/maps_system.md).

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
Browser-Fronten: [memory/werkzeuge/kalender_system.md](memory/werkzeuge/kalender_system.md).

- **Nur stdlib:** `curses` + `urllib` + `json` + `threading` — null Extra-Deps.
  Setzt UTF-8-Locale vor curses-Init (für Box-/Block-Zeichen).
- Ein Hintergrund-Thread pollt, der curses-Loop liest den Snapshot (thread-safe
  über Lock). Bei Backend-Ausfall: Header zeigt `[backend ?]`, kein Crash.
- `--selftest` gibt einen Text-Snapshot ohne curses aus (Verifikation ohne TTY).
- Backend läuft im `tui`-Mode (KI aus, wie laptop). Start: `zentrale-tui`
  fährt Backend (stdout → Logdatei, nicht ins Terminal) + TUI hoch. Siehe
  `memory/betrieb/starten.md`. Env `ZENTRALE_URL` überschreibt das Backend-Ziel (Default
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
> `memory/tutor/tutor_system.md`.

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
(s.u., interaktives Panel statt ASCII), `kalender` (s.u.) und `klavier` (s.u.).
`graph`, `kalender` und `klavier` sind **nicht** im Auto-Direktor (interaktiv,
nicht zum Durchzappen).

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
> [memory/werkzeuge/kalender_system.md](memory/werkzeuge/kalender_system.md).

> **Klavier (Exhibit `klavier`, Taste `k`)** — der Mittelbereich wird zur
> Klaviatur: **unten die gezeichneten Tasten, darüber das Notensystem**, in das
> das Gespielte einläuft. Eigenes `#piano-panel` (`.ppanel`, `frameTick` blendet
> wie bei `graph` `#core` aus). Gespielt wird auf der **Computertastatur**: untere
> Buchstabenreihe = weiße Tasten (`y x c v b n m , . -`), die Reihe darüber die
> schwarzen, genau dort wo sie physisch dazwischen liegen (`s d · g h j · l ö`).
> `f` und `k` fallen dabei in die Lücken E–F und H–C, wo es **keine** schwarze
> Taste gibt — beide bleiben so für ihre Shortcuts frei (`f` = Fokus, `k` =
> Klavier auf/zu). `←`/`→` verschiebt die Oktave (C3…C6), `Esc` schließt.
>
> - **Ton:** WebAudio (ein Dreieck-Oszillator + Hüllkurve pro klingender Note),
>   kein Sample, kein Download → läuft offline im Pi-Kiosk. Der AudioContext wird
>   erst beim ersten Tastendruck gebaut (Autoplay-Policy braucht die Nutzergeste).
> - **Noten:** Violinschlüssel + 5 Linien, Hilfslinien nach Bedarf, `♯` vor
>   schwarzen Tasten, lang gehaltene Töne als **hohler** Notenkopf, klingende Noten
>   in Akzentfarbe. Bewusst **kein Takt/Notenwert** — die Noten stehen in
>   Spielreihenfolge nebeneinander (Quantisieren würde das Gespielte verfälschen).
>   Der Schlüssel ist ein **SVG-Pfad**, kein Zeichen `𝄞`: das Glyph steckt nur in
>   Musik-Fonts, auf dem Pi käme ein Ersatzkästchen.
> - **Aufnahme:** `Leertaste` startet/stoppt. Beim Stoppen fragt es einmal nach
>   dem Namen (Abbrechen verwirft — nichts wird heimlich gespeichert) und legt sie
>   über `POST /api/melodies` in `data/melodies.json` ab. Die Chips oben sind die
>   gespeicherten Melodien: Klick = abspielen (Tasten leuchten mit, die Noten
>   stehen im System), nochmal Klick = stopp, `✎` umbenennen, `✕` löschen.
>   `Enter` spielt die zuletzt aufgenommene. Details: [memory/system/api_endpoints.md](memory/system/api_endpoints.md).
> - **Kassetten:** monolith + laptop (dasselbe Template, nicht KI-gegatet) **und
>   die TUI** (Taste `k`, s.u.). Alle drei arbeiten auf derselben Melodien-
>   Registry (`core/melodies.py` → `data/melodies.json`), im Browser
>   Aufgenommenes lässt sich also im Terminal abspielen und umgekehrt.

> **Klavier in der TUI (Taste `k`)** — dieselbe Klaviatur, dieselben Melodien,
> gezeichnet in curses: unten mittig die Tasten in **Aufsicht** wie auf einem
> echten Klavier — weiße Tasten als Kästchen nebeneinander, die schwarzen
> schmaler (gut halb so breit), bis an die Hinterkante reichend und mittig auf
> der Kante zwischen zwei weißen; vorne bleibt die weiße Taste frei, dort steht
> ihr Buchstabe. Darüber das Notensystem. Anschlagene Tasten und klingende
> Notenköpfe leuchten in der Akzentfarbe. Solange das Panel offen ist, tickt die
> Zeichenschleife schnell (33 ms statt 250 ms) — sonst käme der Ton spürbar nach
> dem Tastendruck.
>
> - **Ton:** `core/tone.py` rechnet die Wellenform selbst (Grundton + vier
>   Obertöne, Anschlag-Rampe + exponentielles Abklingen) und schiebt sie über
>   **sounddevice** raus; gemischt wird im Audio-Callback, mehrere Töne
>   gleichzeitig sind also Akkorde. Kein Sample, kein Download. Der Import
>   passiert **erst beim Öffnen des Panels** — die TUI bleibt sonst stdlib-only
>   und startet unverändert, wenn numpy/sounddevice oder das Audio-Gerät fehlen
>   (dann steht `♪ stumm` im Kopf, Noten und Aufnahme laufen weiter).
>   `ZENTRALE_NO_AUDIO=1` schaltet den Ton bewusst ab (nutzt der TUI-Fuzzer).
> - **Wenn das Gerät hängt:** läuft der System-Default über einen Audio-Server,
>   der gerade nicht erreichbar ist (PipeWire ohne Session — z.B. in einem
>   Hintergrund-Job oder headless über SSH), **blockiert PortAudio beim Öffnen**
>   und lässt sich aus Python nicht abbrechen. Deshalb geht das Gerät in einem
>   Daemon-Thread auf und der Kopf sagt `♪ ton öffnet…` bzw. nach 4 s
>   `♪ ton reagiert nicht`; die TUI bleibt die ganze Zeit bedienbar. Ausweg:
>   **`ZENTRALE_AUDIO_DEVICE`** (Index wie `0` oder Name wie `hw:0,0`) geht an
>   der ALSA-/PipeWire-Kette vorbei direkt auf die Karte.
> - **Gedrückt halten klingt wie am Flügel** — obwohl das Terminal **kein
>   Loslassen** meldet. Das Halte-Signal ist die **Tastenwiederholung des
>   Systems**, und die wird dafür passend gemacht: solange das Klavier gespielt
>   wird, stellt die TUI sie auf **kurz und dicht** (`xset r rate 80 30`) und
>   beim Schließen zurück. Damit setzt die Salve schon nach ~80 ms ein und läuft
>   alle ~33 ms weiter — alles unter `PIANO_HOLD_MS` (120 ms) ist sicher
>   „gehalten" (`piano_is_hold`), so schnell drückt keine Hand dieselbe Taste
>   zweimal, und ein bewusster zweiter Anschlag (≥150 ms) wird nie verschluckt.
>   Bleibt die Salve aus, ist der Finger weg.
>   **Warum das nötig war:** mit der Voreinstellung (~500 ms bis zur ersten
>   Wiederholung) klaffte zwischen Anschlag und Salve ein halbsekundenlanges
>   Loch — der Ton war da längst gedämpft und schlug danach neu an. Gemessen:
>   Anschlag, nach 144 ms Loslassen, bei 520 ms neuer Anschlag. Genau das hat
>   man als „unterbrochen" gehört. Jetzt: ein Anschlag, durchgehendes Halten,
>   ein Loslassen.
> - **Zwei Vorsichtsmaßnahmen dabei:** beim Tippen (Melodie benennen) geht die
>   Wiederholung zurück auf normal — mit 80 ms verdoppelt sonst jeder längere
>   Tastendruck Buchstaben. Und der Ursprungswert wird per `atexit` immer
>   zurückgesetzt; findet die TUI beim Start schon den Spiel-Wert vor (die
>   letzte Sitzung wurde hart abgeschossen, `SIGKILL` überspringt `atexit`),
>   nimmt sie NICHT den als Original, sondern den X-Standard 500/20 — sonst
>   bliebe die Tastatur des ganzen Rechners für immer auf hektisch.
> - **Der Ton selbst** läuft in `tone.Voice(hold=True)`: er fällt nur langsam
>   (`HOLD_TAU_S`), und beim Loslassen klingt er ab der erreichten Lautstärke
>   normal aus — nahtlos, weil die zweite Kurve genau dort ansetzt, wo die erste
>   steht. **Jeder Teilton hat seine eigene Hüllkurve** und die oberen sterben
>   schneller (`PARTIAL_DECAY`): der Anschlag ist hell, das Ausklingen dunkel und
>   weich — mit einer gemeinsamen Hüllkurve klingt es die ganze Zeit gleich hell,
>   also nach Orgel statt nach Klavier. Ohne Halten bleibt alles wie vorher
>   (`PIANO_NOTE_MS`, 420 ms); gespeicherte Melodien laufen NIE über die
>   Halte-Kurve, die tragen ihre echten Haltedauern. Beim Loslassen wandert die
>   wirklich gehaltene Dauer in die Note — im Browser klingt sie dann genauso
>   lang.
> - **Noten:** 5 Linien im Violinschlüssel (E4…F5), eine Terminal-Zeile pro
>   diatonischer Stufe, Hilfslinien nach Bedarf, `♯` vor der Note. Kein
>   Notenschlüssel-Glyph — `𝄞` fehlt in Terminal-Fonts; stattdessen ein
>   Taktstrich links. Noten außerhalb des Systems (Oktave 3/6) werden an den
>   Rand geklemmt und als `◇` markiert, statt unsichtbar zu verschwinden.
> - **Rücktaste löscht die letzte Note** — wie beim Tippen von Text. Ein
>   Anschlag = eine Note, also fällt genau einer weg (bei einem Akkord der
>   zuletzt getippte Ton). Läuft eine Aufnahme, fliegt die Note auch dort raus.
> - **Grober Rhythmus** (`piano_beat`/`piano_flow`): wie lang eine Note war,
>   meldet das Terminal nicht — messbar ist nur der **Abstand zum nächsten
>   Anschlag**, und der ist die Notenlänge: wer wartet, hält. Vier Stufen
>   (achtel/viertel/halbe/ganze, `PIANO_BEAT_MS`), mehr wäre vorgetäuschte
>   Genauigkeit. Achtel und Viertel sind volle Köpfe, Halbe und Ganze hohle mit
>   einem Halte-Strich daneben (`─` bzw. `═`) — sonst sähen beide gleich aus.
>   Bleibt nach dem Runden Zeit übrig, wird daraus eine **Pause**: ein Block auf
>   der Mittellinie, je länger die Stille, desto höher (`▁▂▄█`).
>   **Zwei Stellen schreiben bewusst KEINE Pause** — vor der ersten Note und
>   nach dem Löschen (die Note danach trägt `np`): das ist Bedenkzeit, keine
>   Musik, sonst wäre das Blatt voller Pausen statt Noten. Die **letzte** Note
>   ist immer „offen" (hohl) und bekommt ihre Länge erst, wenn es weitergeht.
>   Alles davon wird beim Zeichnen aus den Zeitstempeln abgeleitet — Löschen
>   räumt seine Pause deshalb von selbst mit weg.
> - **Aufnahme:** `Leertaste` startet/stoppt, beim Stoppen wird der Name im
>   Panel getippt (`Esc` verwirft). `↑↓` wählt eine Melodie, `Enter` spielt sie
>   ab (nochmal `Enter` = stopp, die Noten laufen dabei live ins System),
>   `r` benennt um, **`D`** (groß!) löscht — das nackte `d` ist eine
>   Klaviertaste (D♯) und darf nichts wegwerfen.
> - **Tastenbeleuchtung (Taste `L`, groß — `l` ist A♯):** drei Stufen, die die
>   schwarzen Tasten als **Keycaps** behandeln (ab 3 Spalten Breite kriegen sie
>   eine Umrandung, der Buchstabe sitzt mittendrin):
>   `neon` (Standard) = jede Keycap trägt ihre eigene Leuchtfarbe (im Dunkeln
>   echtes Neon 51/201/46/226/208/199/129 — auf **Papier gibt es das bewusst
>   nicht**, Leuchttasten sind eine Nacht-Sache; tagsüber bleibt die Keycap
>   schlicht schwarz-weiß und der Kopf sagt bei `L` „nur nachts"); `regenbogen` = dieselben Farben **wandern** über die
>   Klaviatur (6 Stufen/s, aus `time.time()` — der Lauf hängt damit nicht daran,
>   wie oft neu gezeichnet wird) und die Buchstaben der **weißen** Tasten glühen
>   mit; `aus` = schlichte Umrandung wie der Rest der TUI. Ohne 256 Farben
>   bleiben die Paletten leer und alles sieht aus wie vorher.
> - **Wie das technisch geht:** `piano_keyboard` liefert zu jeder Zone eine
>   **Art** — `face` (Tastenfläche), `frame` (Rand der Keycap), `label` (die eine
>   Zelle mit dem Buchstaben). Damit kann der Zeichner jede Taste in Teilen
>   einfärben, statt nur ganz — die Grundlage für „nur Teile der Klaviatur
>   leuchten lassen".
> - **Farben:** die schwarze Taste hat ein **eigenes Farbpaar** (`C["key_black"]`,
>   weiß auf Schwarz; im Nacht-Theme 236 statt 16, sonst verschwände sie im
>   schwarzen Panel-Grund), **nicht** `A_REVERSE` — invertiert würde ihr
>   Buchstabe in Hintergrundfarbe gezeichnet und stanzte ein Loch in die Taste.
>   Gedrückt wird die Fläche zur Akzentfarbe (`C["key_press"]`, dunkle Schrift);
>   eine gedrückte weiße Taste leuchtet weiter per Invertierung.
> - **Größe wächst mit dem Fenster:** weiße Taste 2…9 Spalten breit, Klaviatur
>   5…13 Zeilen hoch (`piano_keyboard(width, height)` sucht das größte, was
>   passt, und der Aufrufer zentriert). Wird es eng, hat die **Klaviatur
>   Vorrang** vor dem Notensystem — gespielt wird auf den Tasten; erst wenn
>   nicht mal die Mindestgröße passt, steht dort nur noch die Textzeile
>   `tasten: y x c v b n m , . -`. In der Statuszeile stehen deshalb **nur die
>   Funktionstasten**, nicht die Notentasten: welcher Buchstabe welchen Ton
>   spielt, steht auf der Taste selbst.
> - **Testbar ohne Terminal und ohne Soundkarte:** die Geometrie steckt in den
>   puren Funktionen `piano_keyboard`/`piano_staff`/`piano_columns`
>   (`tests/test_tui_piano.py`), die Klangrechnung in `tone.Voice`
>   (`tests/test_tone.py`). Der PTY-Fuzzer drückt `k` und die Klaviatur mit.

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
  Würfel/Globus/Welt/Filter/Graph/Kalender/Fokus/Post/Klavier/Auto) + dem ASCII-Kern `#core` (s.u.) + der
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
sagen (Hintergrund: `memory/ki/grounding_recherche.md`).

### ASCII-Kern / Bild-Marker (KI redet visuell)

Tippt die KI in ihrer Antwort den Marker `[[bild: stichwort]]` (Backend-
Pipeline + Begründung der Marker-statt-Tool-Entscheidung siehe
`memory/ki/ki_system.md`), übernimmt das gematchte ASCII-Bild den Kern **auf Zeit**:

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
`_should_think` → nur Verständnis-/Verifikations-Turns, siehe `memory/ki/ki_system.md`),
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
- Kill-Switch `ZENTRALE_THINK=0` (siehe `memory/betrieb/starten.md`) → kein Thinking, kein
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
`chatMuted` aus. Voller Mechanismus: [memory/werkzeuge/news_system.md](memory/werkzeuge/news_system.md).

### Knopf-Leiste (2–4 Knöpfe statt Eingabe)

Zwei Auslöser, dieselbe Leiste: das Backend fängt ein bestätigungspflichtiges
Schreib-Tool ab (Auto-Gate, Default JA/NEIN) **oder** die KI ruft selbst
`frage_knopf` mit eigenen Labels (Backend-Mechanik + Begründung siehe
`memory/ki/ki_system.md`). Der Chat-IIFE tauscht die Konsolen-Eingabe gegen die Knöpfe:

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

(Vollständige Tastenliste inkl. Smiley- und Date-Edit: `memory/system/tastatur.md`.)

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
