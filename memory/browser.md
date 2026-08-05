# Browser — Ideen, Entscheidungen, offene Handgriffe

Stand 2026-08-05. Gesammelt aus den Sitzungen Ende Juli / Anfang August 2026.
Zwei Stränge, die hier zusammenlaufen:

- **Brave** (Flatpak) — der Browser, der tatsächlich läuft, samt Theme-Kopplung an ZENTRALE.
- **Terminal-Browsing** — der geplante Zweitweg für Doku, Recherche, Preise. Nicht als Ersatz.

Leitplanken sind die üblichen vier: maschinennah, RAM sparen, Speicher sparen, Workflow.
Auf 3,7 GB entscheidet fast alles der RAM-Posten.

---

## 1. Die Ausgangslage in Zahlen

| | RAM | Angriffsfläche | Was funktioniert |
|---|---|---|---|
| **Brave**, 5 Tabs | 492 MB | groß (JS/JIT), aber Sandbox | alles |
| **LibreWolf** | dasselbe Feld | dito | alles |
| **qutebrowser** | ~250–350 MB Basis | dito | fast alles |
| **w3m / lynx** | 10–20 MB | winzig, aber **keine** Sandbox | nur statisches HTML |

Der Wechsel Brave → LibreWolf liegt beim RAM **im Rauschen**. Er lohnt sich, wenn
man Firefox lieber mag oder Braves Krypto-Zeug loswerden will — nicht wegen
Speicher. qutebrowser wäre reizvoll (vim-Tasten, passt zu tmux/i3), aber man
tauscht Privacy gegen RAM, und das war nicht der Deal.

**Der einzige echte Sprung nach unten ist w3m.** Faktor 30, nicht 20 Prozent.

---

## 2. Der Werkzeugkasten (geplant, noch nicht installiert)

```
Suchmaschine im Terminal    ddgr          DuckDuckGo, Treffer nummeriert      127 KB
Seite als Text lesen        w3m           Tabellen, Formulare, sogar Bilder  2652 KB
Alles rausgreppen           lynx -dump    reiner Text, oder nur die Links    1984 KB
Bilder von einer Seite      gallery-dl    zieht alle Medien einer URL        1873 KB
Video/Audio                 yt-dlp        schon da                              ✓
Bild anschauen              feh                                                322 KB
Video ohne Browser          mpv           auch --vo=tct: Video IM Terminal      ✓
Voll gerendert, wenn nötig  brave <url>   ein Befehl, schon da                  ✓
```

Der Installationsbefehl, wartet auf sudo:

```
! sudo apt install --no-install-recommends w3m w3m-img lynx ddgr feh mpv
```

**`--no-install-recommends` diesmal geprüft, nicht blind gesetzt.** In w3ms
Recommends steht `ca-certificates` — die Wurzelzertifikate. Ohne die könnte w3m
HTTPS nicht prüfen. Die sind hier schon installiert, also unbedenklich; wäre das
nicht so gewesen, wäre der Schalter falsch. Merksatz: der Schalter ist ein
**Sparschalter, kein Sicherheitsschalter** — vorher immer nachsehen, was in den
Recommends steht.

Danach zu bauen (versprochen, noch offen):
- `such <begriff>` → ddgr
- `lies <url>` → w3m
- `links <url>` → lynx -dump -listonly
- `bwrap`-Wrapper für w3m ohne Home-Zugriff

### Typische Handgriffe

```bash
ddgr tiling window manager        # suchen, Treffer durchnummeriert
w3m https://wiki.archlinux.org/…  # lesen, Pfeiltasten und Leertaste
lynx -dump -listonly <url>        # nur die Links, nummeriert
lynx -dump <url> | grep -i preis  # genau das, wofür der Zweitbrowser da ist
gallery-dl <url>                  # alle Bilder in einen Ordner
brave <url>                       # wenn's doch das echte Web sein muss
w3m /usr/share/doc/i3-wm/userguide.html   # Doku liegt lokal, kein Netz nötig
```

---

## 3. Isolation: bwrap statt firejail

`w3m` läuft nackt als du. Die Angriffsfläche ist winzig, aber wenn doch mal ein
Parser-Fehler greift, steht er direkt im Home. Lösung: **`bwrap`** (bubblewrap) —
exakt dasselbe Werkzeug, mit dem der Flatpak-Brave eingesperrt ist. Liegt schon
auf der Platte, weil Flatpak es mitbringt.

Praktisch getestet: ein Dateisystem **ohne `/home`**. w3m sieht dann nichts, was
sich stehlen ließe.

**Kein `firejail`.** Das wäre sogar schlechter: firejail läuft selbst mit
Root-Rechten und hatte deswegen eigene, üblere CVEs.

Die eigentliche Denkfigur, die hier zählt — die Frage „hat es Lücken?" ist die
falsche, **die richtige ist „was passiert, wenn?"**

```
Brave              Sandbox greift
w3m nackt          dein Home
w3m in bwrap       leerer Raum
```

Isolation ist damit kein Zusatz, sondern die eigentliche Antwort.

---

## 4. Sicherheit, ehrlich

**CVEs sind erstmal ein gutes Zeichen.** Lücken wurden gefunden, gemeldet,
geschlossen. Software *ohne* CVEs ist meistens nur Software, die keiner
angeschaut hat.

**Die Versionsnummer lügt.** Ubuntu liefert `w3m 0.5.3+git20230121`, sieht uralt
aus. Debian-artige Distributionen **backporten** Sicherheitsfixes in die alte
Version, ohne die Nummer zu erhöhen. Man bekommt den Fix, nur nicht die neuen
Funktionen. Das ist der Grund, warum „alte Version" hier etwas anderes bedeutet
als anderswo.

**Warum Chromium wöchentlich Updates braucht:** weil seine Angriffsfläche
gigantisch ist. Eine JS-Engine mit JIT-Compiler ist ein Programm, das fremden
Code in Maschinencode übersetzt und ausführt — konstruktionsbedingt ein
Minenfeld. w3m tut das nicht, also gibt es dort wenig zu finden.

**Was trotzdem gegen w3m spricht:** rund 50.000 Zeilen C aus den Neunzigern. So
schreibt heute keiner mehr Parser. Google lässt Chromium rund um die Uhr in
Rechenzentren mit zufälligem Müll füttern (Fuzzing); für w3m macht das niemand.
Dazu: keine Sandbox ab Werk, Cookies landen in `~/.w3m/cookie` (abschaltbar,
standardmäßig an).

Unterm Strich ein **Unentschieden mit Vorzeichenwechsel**: weniger
Angriffsfläche, aber auch keine Sandbox und langsamere Updates.

---

## 5. Privacy, ehrlich — die Korrektur, die zählt

> **w3m ist nicht der privatere Browser, er ist der billigere.**

Der Privacy-Gewinn ist ein *Nebeneffekt* davon, dass er JS nicht kann — nicht das
Ergebnis besserer Abwehr. Ein Firefox mit uBlock Origin im „medium mode"
(Drittanbieter-Skripte grundsätzlich blockiert) plus `privacy.resistFingerprinting`
steht gegen Tracking praktisch **genauso gut** da.

```
Tracking-Schutz     etwa gleichauf
RAM                 w3m ~15 MB   gegen   Firefox ~400 MB     ← hier der Unterschied
Angriffsfläche      w3m gewinnt (keine JS-Engine)
Was funktioniert    Firefox gewinnt deutlich
```

### Der Fingerabdruck-Denkfehler

Zwei verschiedene Ziele, die man leicht verwechselt:

1. **Angriffsfläche verkleinern** — da gewinnt w3m haushoch. Kein JS, kein WebGL,
   kein PDF-Renderer, keine Medien-Codecs.
2. **In der Masse verschwinden** — da *verliert* w3m deutlich.

Der Grundsatz heißt **„anonymity loves company"**. Ein Fingerabdruck ist nicht
deshalb gut, weil er *klein* ist, sondern weil er **wie alle anderen aussieht**.
Mit w3m auf Linux ist man vielleicht einer von zehntausend Besuchern einer Seite:
kaum Merkmale — aber „hinterlässt kaum Merkmale" **ist** das Merkmal. Über
Sitzungen hinweg trivial wiederzuerkennen.

Dasselbe gilt für Randomisierung: **ein zufälliger Fingerabdruck ist selbst ein
Fingerabdruck.** Nicht *falsche* Spuren, sondern *generische*.

### Die drei Stufen

```
1  Spuren verkleinern       Adblocker, kein JS, w3m       gegen Werbetracking
2  Spuren vereinheitlichen  Tor Browser                   gegen Wiedererkennung
3  Spuren abkoppeln         Whonix (echte IP technisch
                            nicht erreichbar)             gegen alles darüber
```

Whonix/Qubes sind auf 3,7 GB **nicht machbar** — beide wollen mehrere VMs
gleichzeitig. Ehrlich gesagt: fällt weg.

---

## 6. Tor — die zwei Achsen

```
Tor-Netzwerk    verbirgt WOHER du kommst      (deine IP)
Tor Browser     verbirgt WER du bist          (dein Fingerabdruck)
```

```bash
sudo apt install tor torsocks     # 3,6 MB + 325 KB
torsocks w3m https://beispiel.de  # dieses eine Programm läuft durch Tor
torsocks curl ifconfig.me         # zeigt eine fremde IP
```

`torsocks` klinkt sich in ein beliebiges Programm ein und biegt dessen
Netzwerkzugriffe ins Tor-Netz um — curl, w3m, lynx, git, fast alles.

**Aber:** `torsocks w3m` ist **nicht** der Tor Browser. Man bekommt die versteckte
IP, nicht die Gleichförmigkeit. Man ist dann „der eine w3m-Nutzer, der über Tor
kommt" — in gewisser Weise auffälliger als vorher. Für „mein Provider soll nicht
sehen, was ich lese" reicht es völlig. Für „niemand soll wissen, dass ich es bin"
nicht.

**Der Tor Browser ist präzise das:** ein Browser, der auf jede Fingerabdruck-Frage
absichtlich **dieselbe** Antwort gibt wie alle anderen Tor Browser. Nicht „keine
Antwort" — dieselbe. Bildschirm immer 1000×1000 (daher die grauen Ränder, die
viele nervig finden), Zeitzone immer UTC, Schriftenliste immer dieselbe, egal was
installiert ist. Er lügt konsequent, und alle lügen identisch. Das kann kein VPN
leisten: ein VPN versteckt auch die IP, aber es macht keine zehntausend Nutzer
ununterscheidbar.

Und die Asymmetrie nicht vergessen:

```
die besuchte Webseite   sieht Tor Browser wie jeden anderen   → unauffällig
dein Internetanbieter   sieht, DASS du Tor benutzt            → auffällig
```

**ZENTRALE fasst den Tor Browser bewusst nie an** — steht so im Kommentar von
`zentrale-browser-theme`. Ein von außen gesetztes Theme wäre genau die
Ungleichförmigkeit, die er vermeiden soll.

---

## 7. Grenzen des Terminal-Browsings

- **Kein JavaScript** → Flok, Strudel, jede Single-Page-App fällt komplett aus.
  Das ist keine Konfigurationsfrage. Terminal-Browsing ist **Ergänzung**, nie Ersatz.
- **Umweg für SPAs:** viele holen ihre Daten selbst von einer API. Dann geht
  `curl <api-url> | jq …` — man redet direkt mit dem Programm, statt eine
  Oberfläche zu bedienen, die für Menschen gebaut ist.
- **`mailcap`** ist die Datei, die entscheidet, was mit allem passiert, das kein
  Text ist:
  ```
  image/jpeg      →  feh %s
  application/pdf →  zathura %s
  text/html       →  w3m -T text/html
  ```
  Der Name kommt aus der Mailwelt („mail capabilities") — Mailprogramme standen
  als Erste vor dem Problem, dass in einer Nachricht plötzlich ein Bild steckt.
  Heute nutzen w3m und lynx dieselbe Datei; sie ist der Vorfahre von `xdg-open`.
  Deshalb stand `mailcap` in den Recommends. Ist hier schon da.
- **`apt-cache show w3m | grep -A3 Suggests`** — die Suggests-Liste ist ein
  Hinweiszettel des Paketbauers („das passt gut dazu"), zum Lesen und Picken, nicht
  zum Installieren. Daraus kamen `w3m-img` (Bilder) und `xsel` (Zwischenablage).

**Die Überraschung:** w3m kann in einem X-Terminal tatsächlich Bilder anzeigen,
hat Maus-Unterstützung, versteht Formulare und Tabellen. Das ist kein
Text-Auszug, das ist ein Browser.

---

## 8. Suche: ddgr statt SearXNG

SearXNG selbst hosten klingt verlockend, ist aber eine Python-Anwendung mit
dauerhaft **150–300 MB**. Auf 3,7 GB teuer für etwas, das `ddgr` mit 127 KB
weitgehend erledigt. Öffentliche Instanzen gehen ohne eigenes Hosten — dann
schützt man sich vor den Suchmaschinen, muss aber dem Instanz-Betreiber trauen.
Selbst hosten lohnt erst, wenn *mehrere Leute* draufgehen.

---

## 9. Brave als Flatpak — was gelöst ist

Die Theme-Kopplung „Appearance: vom Gerät" hat bis 2026-08-03 nie gegriffen.
**Drei gestapelte Ursachen**, alle drei mussten weg:

1. **`extensions.theme.system_theme = 0`** in den Brave-Prefs — Brave stand aufs
   klassische Theme und hat GTK komplett ignoriert. *Die Hauptursache.*
   (0 = klassisch, 1 = GTK.)
2. **Der Sandkasten sah die Theme-Dateien nicht.** Unter `/usr/share/themes` lagen
   dort nur „Default" und „Emacs". Und `flatpak override --filesystem=/usr/share/themes`
   wird **abgelehnt**: *„Path /usr is reserved by Flatpak"*. Der einzige Weg führt
   übers Heimverzeichnis.
3. **Flatpaks lesen den Theme-*Namen* aus GSettings, nicht aus xfconf.** Dort
   standen noch die Vor-ZENTRALE-Werte (`Mint-L-Darker-Teal`, `HighContrast`),
   weil `zentrale-desktop-theme` nur xfconf beschrieben hat.

**Gefixt:** Themes nach `~/.local/share/themes` gespiegelt (6,8 MB), Sandkasten
per `flatpak override --user com.brave.Browser --filesystem=xdg-data/themes:ro`
geöffnet, und `zentrale-desktop-theme` spiegelt jetzt zusätzlich nach GSettings
und heilt die Theme-Kopie selbst. Commit `a73af03`.

`cp -al` (Hardlinks, 0 Byte Kosten) ging **nicht**: `fs.protected_hardlinks`
verbietet Hardlinks auf Dateien, die einem nicht gehören. Daher echte Kopie.

**Die Portal-Hälfte war nie kaputt** — `zentrale-browser-theme` setzt
`prefer-dark`/`prefer-light` korrekt, das Portal meldet es korrekt. Nur die
GTK-Hälfte fehlte.

### Noch von Hand zu tun

- [ ] `brave://settings/appearance` → auf **GTK** stellen (kann kein Skript
      machen: Chromium überschreibt `Preferences` beim Beenden, solange es läuft)
- [ ] Brave **neu starten** — neue Sandkasten-Rechte gelten nur für eine frisch
      gestartete Instanz

### Nebenbei aufgetaucht

Flatpaks exportieren ihren Starter nur unter der vollen Kennung
(`/var/lib/flatpak/exports/bin/com.brave.Browser`), und der Ordner steht in keinem
PATH — deshalb „No such file or directory" beim Tippen von `brave`. Gilt für
**jedes** Flatpak. Gelöst durch `~/.local/bin/flatpak-namen`, das Kurznamen-Symlinks
anlegt. Nach jeder Neuinstallation einmal aufrufen.

---

## 10. Offene Ideen, unsortiert

- **`gallery-dl`** erst installieren, wenn der Bedarf da ist.
- **Deklarativ denken** — falls irgendwann Nix: der ganze Werkzeugkasten ist eine
  Zeile, `environment.systemPackages = with pkgs; [ w3m lynx ddgr mpv yt-dlp tmux neovim ];`
- **`mpv --vo=tct`** — Video direkt im Terminal, truecolor. Spielerei mit
  Lerneffekt: `vo` = video output, und `--xyz=help` listet bei vielen Programmen
  die möglichen Werte auf, statt raten zu müssen.
- **Reines tty ohne X** wurde durchgerechnet und verworfen: Chinesisch tippen geht
  dort nicht (fcitx5 braucht X), Web-Apps auch nicht, und der Gewinn ist mit ~50 MB
  klein, weil dank tmux ohnehin nur ein Fenster nötig ist.

---

## Verwandt

- `scripts/zentrale-desktop-theme` — GTK/Icons/xfwm4 + GSettings-Spiegelung
- `scripts/zentrale-browser-theme` — Portal `color-scheme`, lässt Tor in Ruhe
- `memory/dashboard.md` — Theme-Kette im Überblick
- `~/.config/i3/spickzettel` — Tastengriffe
