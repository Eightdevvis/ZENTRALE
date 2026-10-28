# App-Motor — wie Apps aus dem Store auf jedem Knoten laufen (Plan)

**Stand 2026-10-29: Plan, nichts gebaut. Ein paar Entscheidungen fehlen noch
(unten „Offene Fragen").** Der Motor ist der Teil des rohen ZENTRALE, der
App-Pakete ausführt. Auf dem Handy steckt er in der APK, auf den Rechnern im
Hub. Ein App-Paket ist **Inhalt, kein nativer Code**: Manifest (`app.toml`),
Daten-Schemas (JSON Schema), Ansichten aus einem festen Satz von Bausteinen
(JSON), Logik als WebAssembly-Modul hinter demselben HTTP-Vertrag, den
Prozess-Apps heute schon haben, KI-Werkzeuge als MCP-Definitionen, dazu
Bilder. Jeder Knoten führt dasselbe Paket aus. Jede Oberfläche zeichnet die
Bausteine mit eigenen Mitteln: das Handy in Flutter im Augen- und
Leiterbahn-Stil, die TUI mit curses. Übergangsregel (Sasha, 29.10.): Am
Handy wird weiter gebaut, aber jede Funktion kommt isoliert in einen
App-Ordner hinter die Schnittstelle, die der Motor später anbietet (Schritt 1
unten).

## Warum

- **Das Handy verdrahtet heute fest, was eine App sein sollte.** KI-Chat und
  Kalender stecken in `mobile/lib/` (`chat/`, `ki/`, `gespraeche/`,
  `kalender/`). `main.dart` steckt sie zusammen, `ChatSteuerung` bekommt
  `kalender.ueberblick` als Dart-Verweis (eine App greift direkt in eine
  andere), und `mitte/regeln.dart` legt fest im Code fest, welche Dateien
  geholt werden. Nach [standort_und_app.md](standort_und_app.md) gehören in
  die APK nur das Auge (Hub), Anmeldung und Mitte, der Store und die
  Pflicht-Adapter.
- **Google Play verbietet, ausführbaren Code nachzuladen** (dex, JAR, .so).
  Ausgenommen ist Code, der in einer VM oder einem Interpreter läuft und nur
  indirekt an Android-APIs kommt, etwa JavaScript im WebView. Spiele laden so
  ihre Inhalte nach. Daraus folgt: Der Motor ist in der APK und wird von Play
  geprüft. Die Apps sind Inhalt, den der Motor ausführt.
  ⚠ prüfen: vor der ersten Veröffentlichung den aktuellen Wortlaut der
  Play-Richtlinie „Device and Network Abuse" nachlesen und ihn hier mit Datum
  zitieren.
- **Dieselbe App überall.** Das folgt aus der Regel „Apps syncen ohne Gnade"
  und aus [../leitbild.md](../leitbild.md) („überall deploybar"). Heute ist
  die Kalender-Logik doppelt da, in Python (Kern) und Dart (Handy), und nur
  über die Testvektoren gleich gehalten (`mobile/test/daten/kalender_testvektoren.json`).
  Mit jedem weiteren Knoten (Pi, Browser, AR) käme eine weitere Kopie dazu.
  Ein Paket für alle Knoten beendet das.
- **Keine eigenen Formate** ([hub_bauplan.md](hub_bauplan.md) „Standards
  statt Eigenformat"). Jedes Protokoll muss sich aus der Doku nachbauen
  lassen und hat Testvektoren.

## 1. Das App-Paket

Ein Paket ist **ein ZIP-Archiv** (wie .apk, .jar, .epub), Endung `.zip`. Im
Katalog steht dazu ein SHA-256-Prüfwert und eine Signatur (Abschnitt 5).

| Teil | Datei im Paket | Format (Standard) | Heute schon da |
|---|---|---|---|
| Manifest | `app.toml` | TOML, Schlüssel wie heute + die neuen unten | ja (Tutor, Karte, Budget, Werkstatt-Apps) |
| Rechte | in `app.toml` `rechte` | Rechte-Wörter (`kalender:lesen`, `modell`, `netz:<host>` …) | ja, Vokabular in [hub_bauplan.md](hub_bauplan.md) |
| Daten | `daten/*.schema.json` + `[daten] muster` | JSON Schema 2020-12; Nutzdaten in offenen Formaten (.ics, JSON Canvas, Markdown, JSONL) | `[daten]` ja ([cloud_app.md](cloud_app.md)), Schemas teils (Kachel-Parameter) |
| Schnittstelle | `openapi.yaml` | OpenAPI 3.1, die Routen der App + `/hub/…` | ja für Prozess-Apps (Tag `app-seite`) |
| Ansichten | `ansichten/*.json` (oder von der Logik geliefert) | Baustein-Baum, beschrieben durch ein JSON Schema (Abschnitt 2) | Vorform: Kachel-Antwort `zeilen` + Farbrollen |
| Logik | `logik/app.wasm` | WebAssembly-Komponente, WASI 0.2 `wasi:http` (Abschnitt 3) | nein |
| KI-Werkzeuge | `ki/werkzeuge.json` | MCP-Werkzeug-Definitionen + `x-zentrale` bzw. Anbindungs-Beschreibung | ja (`core/werkzeug_erzeuger/`, `anbindung.schema.json`) |
| Tasten | `[[tasten.<ansicht>]]` in `app.toml` | Tastentabelle (Schema in `openapi.yaml`) | ja |
| Bilder | `icon.png`, `assets/` | PNG, SVG, Schriften | ja (`icon`) |
| Prüfsteine | `tests/vektoren.json` | JSON: Anfrage → erwartete Antwort | Muster: Kalender- und Konto-Vektoren |
| Version | `version` in `app.toml` | SemVer 2.0 | ja |

**Neue Schlüssel in `app.toml`:**

```toml
motor   = "1"                  # Hauptversion der Motor-Schnittstelle, die das Paket braucht
logik   = "logik/app.wasm"     # statt start/adresse: läuft im Motor
ansichten = ["motor"]          # neue Ansichts-Art: Bausteine, auf jeder Oberfläche
[daten]
muster = ["data/kalender/**"]
abgleichen = true
schema = "daten/termin.schema.json"
```

Ein Paket hat höchstens eine Ausführungsart: keine (nur Manifest und
Ansichten, wie die Werkstatt-Apps), `logik` (WASM) oder `start` (ein
Prozess am Rechner, wie heute). Der Hub behandelt alle drei hinter denselben
Routen.

## 2. Ansichten: wie sie beschrieben und gezeichnet werden

### Bewertung

| Weg | Offline | Sicherheit | Augen-/Leiterbahn-Stil | Leistung | Play | Dieselbe App in der TUI | Standard |
|---|---|---|---|---|---|---|---|
| **A Bausteine** (deklarativ, schema-getrieben; Erweiterung von Katalog/Kacheln) | ja | sehr gut: kein Code in der Ansicht | ja, der Motor zeichnet alles selbst | nativ | unbedenklich (Daten) | **ja** | JSON + JSON Schema; Formulare aus JSON Schema, Flächen als JSON Canvas, Text als CommonMark |
| B Remote Flutter Widgets (`rfw`) | ja | gut (keine Logik) | ja | nativ | unbedenklich | **nein**, nur Flutter | eigenes rfw-Text-/Binärformat von Google, kein offener Standard |
| C WebView, HTML+JS im Sandkasten | ja (Dateien im Paket) | mittel: großer Browser-Angriffsweg, CSP und Brücke nötig | nur, wenn jede App das CSS nachbaut | gut, auf schwachen Geräten schwer | ausdrücklich erlaubt | nein (Pi 3 mit 1 GB ohne Browser) | HTML/CSS/JS |
| D WASM zeichnet selbst (Canvas) | ja | gut | jede App malt selbst | gut | erlaubt (VM) | nein | WASM, aber die Zeichen-API wäre unsere eigene |

**Empfehlung: A als Pflicht, C als ausdrücklich erlaubter Ausweg.** Jede App
liefert eine `motor`-Ansicht aus Bausteinen. Die läuft überall, auch in der
TUI und auf dem Pi. Wer mehr braucht (Karte, Pixel-Zimmer), darf zusätzlich
eine `browser`-Ansicht mitbringen, also HTML+JS aus dem Paket im WebView. Auf
der TUI erscheint dann die Baustein-Fassung. B fällt weg, weil rfw nur
Flutter kann und ein Google-eigenes Format ist. Dazu kommt, dass die Augen-
und Leiterbahn-Optik bei A ohnehin der Motor zeichnet. D lohnt sich erst für
AR und 3D (Szene „ZENTRALE im Raum") und bleibt bis dahin außen vor.

### Wie A funktioniert

Hier wird verallgemeinert, was es bei Kacheln schon gibt
([hub_bauplan.md](hub_bauplan.md) „Kacheln"): Die App rechnet die Ansicht
aus, die Oberfläche zeichnet sie nur. Der Grundsatz bleibt: Die App gibt die
Bedeutung vor, die Oberfläche die Farbe.

- **Anfrage** `POST /hub/ansicht {adresse, w, h, faehig: [...], stand?}` →
  `{bausteine: [...], stand, ttl}`. Die Adresse ist `zentrale://<app>/…` wie
  heute. Größen werden in Zellen angegeben. `faehig` sagt, was die
  Oberfläche kann (Bilder, Berührung, Farbe).
- **Aktion** `POST /hub/aktion {adresse, aktion, werte}` → `{zeige: {adresse}}`
  oder eine neue Ansicht. Eingaben in Formularen bleiben bis zum Absenden auf
  der Oberfläche. Das passt zur Regel „Backend zustandslos".
- **Kachel = dieselbe Ansicht in klein.** Die Regel „Programm und Kachel
  teilen EIN Bild" ([listen_app.md](listen_app.md)) gilt so ganz von selbst:
  Es gibt nur einen Zeichner.
- **Bausteine (Satz 1, klein halten):** `zeilen` (Stücke `[text, rolle]`,
  gibt es schon), `liste` (Einträge mit Titel, Markern, Auswahl → Aktion),
  `formular` (JSON Schema + Reihenfolge; heute baut `feld_dialog.py` genau
  das), `text` (CommonMark), `gespraech` (Nachrichtenstrom: Blasen, Markdown,
  aufklappbare Gedanken, Stopp; für Assistent, Mail und Tutor), `zeitraster`
  (Tage × Stunden, Spannen, Ebenen; für den Kalender), `flaeche` (JSON
  Canvas), `bild`, `knopf`, `stapel`/`spalten` (Anordnung). Farben gibt es nur
  als Farbrollen (`core/farbrollen.py`).
- **Ein neuer Baustein** braucht einen Eintrag im Schema, einen Zeichner je
  Oberfläche und einen Testvektor. Das Vorgehen ist dasselbe wie bei einer
  neuen Farbrolle. Kennt eine ältere Oberfläche einen Baustein nicht, zeigt
  sie seinen Pflicht-Rückfall `text`.
- **Achtung beim Eigenformat:** Das Baustein-Vokabular ist die eine Stelle,
  an der wir selbst etwas festlegen, weil es keinen verbreiteten Standard für
  Oberflächen gibt, die auf Terminal und Handy gleich laufen. Adaptive Cards
  (Microsoft, offenes JSON Schema, Renderer für viele Plattformen, Stil
  bestimmt der Gastgeber) wurde geprüft. Es kann Karten und Formulare, aber
  keinen Kalender und keinen Chat. Deshalb: Das Vokabular erscheint als
  JSON-Schema-Datei mit Testvektoren. Formulare nehmen JSON Schema
  unverändert, Flächen JSON Canvas. Wo ein Baustein einem Adaptive-Cards-
  Element entspricht, heißen die Felder gleich.

## 3. Wo die Logik läuft

**Ein Vertrag, drei Orte.** Der Vertrag ist der HTTP-Vertrag, den Prozess-Apps
heute schon erfüllen: `routen`, `/hub/gesund`, `/hub/kachel`, dazu neu
`/hub/ansicht` und `/hub/aktion`, alles in OpenAPI beschrieben. Wo die App
läuft, ist dann nur eine Frage der Ausführung:

| Ort | Wie | Wann |
|---|---|---|
| **Im Motor des Knotens** (Empfehlung für alles, was auch am Handy gehen soll) | WASM-Komponente, die `wasi:http/incoming-handler` erfüllt: Anfrage rein, Antwort raus. Der Motor reicht Anfragen hinein wie heute `app_weiterleitung.py` an eine `adresse`. Die App erreicht den Hub nur über `wasi:http/outgoing-handler`, und dort prüft der Motor jedes Recht. Kein Dateisystem, kein Netz, keine Uhr, die der Motor nicht hineingibt. | Kalender, Listen, Assistent, Budget |
| **Als Prozess am Rechner** | wie heute: `start` + `adresse`, eigener Ordner, später bubblewrap | schwere Apps (Tutor mit Stimme, Karte mit großen Daten), Entwicklung |
| **In der Cloud** | nur Dienste, die ohnehin dort wohnen: Modell-Zugang über Sashas Server, Abo-Prüfung, die Mitte | keine App-Logik mit Nutzerdaten (Grundpfeiler Datenschutz) |

- **Warum WASM:** WASM ist ein W3C-Standard, die Schnittstelle (WIT/WASI) ist
  offen dokumentiert, und die Sprache ist frei (Rust, Python über
  componentize-py, JS, Go). Das Verhalten ist auf jedem Knoten gleich. Am
  Rechner läuft es mit wasmtime (Python-Bindung), am Handy mit einer Laufzeit
  in der APK, in der Cloud auf Workers. **Alternative:** JavaScript als
  `fetch`-Handler (WinterTC/Ecma TC55, genau die Form unserer Cloud auf
  Cloudflare Workers) in QuickJS. Dieser Weg ist leichter und am Handy
  ausgereifter, aber auf eine Sprache festgelegt.
- **Risiko, darum zuerst eine Probe (Schritt 3):** Wie gut sich
  `wasi:http`-Komponenten von Dart am Handy aufrufen lassen, ist der
  unsicherste Teil. Vermutlich braucht es eine kleine Rust-Hülle um wasmtime,
  über FFI angebunden. Zu messen sind: APK-Größe, Startzeit, RAM, Aufwand für
  die Bindung, JIT oder Interpreter (Play: ein Interpreter ist eindeutig
  erlaubt, bei einem JIT ⚠ prüfen). Weil der Vertrag HTTP ist, lässt sich
  nach der Probe WASM gegen JS tauschen, ohne dass sich eine App oder
  Oberfläche ändert.
- **Läuft eine App nur als Prozess auf einem Rechner,** dann liest das Handy
  ihre Daten trotzdem, sofern sie über die Mitte abgeglichen werden, und
  zeichnet die zuletzt geholte Ansicht blass (`faint`, wie Kacheln bei
  „aus"). Aktionen gehen als **Vorschlag in den Eingang**, wenn die App das
  erlaubt (`[offline] aktionen = "vorschlag"`), so wie heute neue Termine.
  Sonst steht da „läuft nur auf: pc". Einen Fernaufruf über die Cloud gibt es
  bewusst nicht, abgeglichen wird über die Daten. Wer eine App am Handy
  vollständig nutzen will, baut sie als WASM.
- **Was der Motor dem Handy-Teil bietet** (Dienste, je eines Rechts): Ablage
  im eigenen Datenordner, `modell` (Chat-Stream zum Anbieter über den
  Adapter, gezählt je App), `benachrichtigung` (geplante Erinnerungen; der
  Motor stellt die Android-Wecker), `ereignis:<name>`, `<app>:lesen` über
  Adressen, `netz:<host>`, `hintergrund` (regelmäßig aufwachen). Android-
  Eigenes bleibt im Motor. Die App nennt nur, was sie will.

## 4. Installieren, entfernen, aktualisieren

- **Welche Apps auf einem Knoten stationiert sind,** entscheidet das rohe
  ZENTRALE. Diese Wahl gilt nur für diesen Knoten und wird nicht abgeglichen.
  Sie wird beim Einrichten erfragt („was planst du hier?") und liegt im
  Register des Knotens (heute `core/app_register.py`
  `apps-<rechner>.json`, am Handy dieselbe Form). `abgleich_apps` folgt
  daraus.
- **Installieren:** Stück aus dem Katalog holen → Paket laden (`downloadUrl`
  zeigt künftig auf eine `.zip` statt auf ein git-Repo; git bleibt für
  Prozess-Apps und für Entwickler) → Prüfwert und Signatur kontrollieren →
  Rechte-Dialog → auspacken nach `<app_ordner>/<name>/<version>/` → ins
  Register. Ab da holt der Abgleich die `[daten]` der App. **App-Daten kommen
  nur, wenn die App hier installiert ist.** `mitte/regeln.dart` liest dann
  aus den Manifesten, statt Pfade fest einzutragen.
- **Entfernen:** Paket und lokale Kopie der Daten löschen, Eintrag aus dem
  Register nehmen. In der Mitte und auf anderen Knoten bleibt alles. „Daten
  überall löschen" ist ein eigener Schritt mit eigener Rückfrage.
- **Version gehört zur App und synct.** Eine App ist überall dieselbe, also
  auch dieselbe Version. Die gewünschte Version steht in den abgeglichenen
  App-Daten (`data/hub/versionen.json` ⚠ Name offen). Wird die App an einem
  Knoten aktualisiert, ziehen die anderen beim nächsten Abgleich nach. Ein
  Knoten mit älterem Motor (`motor` zu neu) oder ohne das Paket zeigt die App
  nur lesend: „braucht neuere ZENTRALE".
- **Daten-Schema mit Version:** Die Migration liefert die App selbst
  (Route `/hub/umziehen {von, nach}`). Ein Knoten schreibt nie in Daten,
  deren Schema-Version er nicht kennt.
- **Aktualisierungs-Wege:**

| Was | Woher | Play-Fassung | eigene APK / F-Droid |
|---|---|---|---|
| APK (Motor, Auge, Adapter) | nur aus dem Kanal, aus dem sie kam | nur über Play | eigener Dienst bzw. F-Droid |
| App-Pakete | immer unser Store | erlaubt (Inhalt für den Interpreter) | erlaubt |
| Neue Android-Rechte (Kamera, Mikro) | stehen im Android-Manifest der APK | brauchen ein APK-Update | ebenso |

  Daraus folgt eine Regel: **Ein Paket bekommt nie mehr, als die APK
  deklariert hat.** Braucht eine App ein Android-Recht, das der Motor nicht
  hat, ist sie am Handy „noch nicht möglich". Dasselbe Paket in der APK oder
  aus dem Store: Vorinstallierte Apps liegen als Pakete in den Assets der APK
  und laufen denselben Weg wie geladene.

## 5. Sicherheit

- **Rechte** stehen im Manifest. Der Hub fragt den Nutzer, nie die App.
  Erlaubt wird einmal oder immer, und jedes Recht ist widerrufbar. Geprüft
  wird bei jedem Aufruf im Motor an der einen Tür (`outgoing-handler` bzw.
  der Hub-Route). Das bestehende Vokabular bleibt.
- **Sandkasten:** WASM bekommt keinerlei Zugriff von außen außer den
  Importen, die der Motor bereitstellt: kein Dateisystem außer dem eigenen
  Datenordner, Netz nur zu `netz:<host>`, und Zeit- und Speichergrenzen je
  Aufruf (0,5 s wie Kacheln, dann „aus"). Ansichten enthalten keinen Code.
  Eine `browser`-Ansicht läuft im WebView mit CSP. Netz hat sie nur zu den
  Hosts aus dem Manifest. Sie spricht nur über eine `postMessage`-Brücke,
  die dieselben Hub-Routen mit denselben Rechten aufruft. Prozess-Apps
  bekommen bubblewrap (die alte Regel: fremde Apps erst mit Sandkasten).
- **Signatur:** Der Katalog nennt je Version den SHA-256 des Pakets (wie
  Subresource Integrity). Signiert wird mit Ed25519 (RFC 8032) über diesen
  Prüfwert. ⚠ Offen ist das Format: minisign-kompatibel oder JWS (RFC 7515).
  Der Motor vertraut dem Store-Schlüssel (in der APK und im Hub
  eingebaut) und dem eigenen Schlüssel des Nutzers für Werkstatt- und
  Entwickler-Apps. Ein unsigniertes Paket kommt nur als „Entwickler-Modus"
  auf einen Knoten. Später kommt TUF (The Update Framework) für Rückruf und
  Schutz vor alten Fassungen dazu.
- **Was der Hub zeigt:** nur die OpenAPI-beschriebenen Hub-Routen, gefiltert
  nach Rechten. Eine App sieht nie fremde Daten, Schlüssel (der Adapter
  entschlüsselt nur im Moment des Aufrufs, wie `lib/konto/geheim.dart`), den
  Prompt einer anderen App oder das Gestell. Die Positivliste
  (`core/abgleich_auswahl.py`) bleibt der Riegel für den Abgleich.
- **KI-Werkzeuge** einer App bekommt der Assistent nur mit dem passenden
  Recht. Der Werkzeug-Erzeuger legt die Schutzschichten darum
  (Gate, Nachlesen, Zurückbauen), wie in [hub_bauplan.md](hub_bauplan.md)
  „KI-Werkzeuge aus dem Schema".

## 6. Weg: KI-Chat und Kalender werden die ersten zwei Apps

Das Handy darf dabei nie kaputtgehen. Jeder Schritt ist für sich fertig und
lässt sich ausliefern.

### Schritt 1 — eingebaut, aber hinter „installiert" und isoliert (jetzt)

- **`lib/motor/`** (rohes ZENTRALE) bietet die Schnittstelle, die der Motor
  später hat, in Dart: `MotorApp` (Manifest, `ansicht(adresse, w, h)`,
  `aktion(...)`, `werkzeuge`), dazu die Dienste aus Abschnitt 3
  (`ablage` auf `daten/<app>/` beschränkt, `modell`, `benachrichtigung`,
  `lesen(adresse)` mit Rechteprüfung, `abgleichAnstossen`). Am Anfang sind
  das dünne Hüllen um den Code, der heute schon da ist.
- **`lib/apps/assistent/`** (heute `chat/`, `ki/`, `gespraeche/`) und
  **`lib/apps/kalender/`** (heute `kalender/`) ziehen um. Jede App bringt ihr
  `app.toml` als Asset mit, im selben Format wie am Rechner (Namen wie in
  `core/eingebaute_apps.py`: `assistent`, `kalender`).
- **Register am Handy:** `hub/apps-handy.json`, dieselbe Form wie
  `app_register`. Die Knöpfe um das Auge (`bereiche`) entstehen daraus statt
  aus der festen Liste. Beim ersten Start nach dem Update sind beide Apps
  „installiert", damit sich für Sasha nichts ändert. Abwählen nimmt Knopf
  und Daten-Abgleich weg.
- **Die eine Kreuzung auflösen:** `ChatSteuerung` bekommt den Kalender nicht
  mehr als Dart-Funktion. Sie fragt `lesen("zentrale://kalender/ueberblick?tage=14")`
  mit dem Recht `kalender:lesen`. Fehlt der Kalender, fehlt nur dieser
  Absatz im Prompt.
- **`mitte/regeln.dart` `holen`** entsteht aus den `[daten]` der
  installierten Apps plus dem Gestell (`mobil/kontext.json`,
  `adapter/geheim.enc`), wie `core/abgleich_apps.py`.
- **Grenz-Wächter (Dart-Test, wie E1/E3):** Eine Datei unter `lib/apps/<x>/`
  importiert nur `lib/motor/` und ihren eigenen Ordner. Das rohe ZENTRALE
  importiert Apps nur an einer Stelle (`lib/apps/eingebaut.dart`). Die
  Altlasten-Liste darf nur kürzer werden.
- **Das Auge:** Antippen öffnet die als Assistent eingetragene App. Ist
  keine installiert, steht dort ein Hinweis mit Weg in den Store (siehe
  Frage 1).
- **Übergangsregel für neue Funktionen am Handy:** Sie kommen in den Ordner
  ihrer App und rufen nur `lib/motor/` auf. Was je Knoten verschieden sein
  darf, kommt ins Gestell. Im Zweifel ist es App.

### Schritt 2 — Ansichten als Bausteine

- Ein Baustein-Schema (`core/bausteine.schema.json` ⚠ Ort offen) mit
  Testvektoren, ein Flutter-Zeichner (`lib/motor/zeichner/`, im Stil von Auge
  und Leiterbahnen) und ein TUI-Zeichner (erweitert den Kachel-Zeichner).
- Kalender und Assistent liefern ihre Seiten als `ansicht()`-Antwort, die
  Dart-Logik im Prozess bleibt vorerst. Das ist das Muster „Adapter im
  Prozess hinter derselben Schnittstelle" wie bei `fokus`. Der Test dazu:
  Die Antworten der eingebauten App und die eines Pakets sind byte-gleich.
- Erinnerungen laufen über `benachrichtigung`. Der Kalender gibt eine Liste
  von Zeitpunkten ab, der Motor stellt die Android-Wecker (heute
  `erinnerungen.dart`, das wandert in den Motor).

### Schritt 3 — Probe Laufzeit, dann echte Pakete

- **Probe:** wasmtime (`wasi:http`) gegen QuickJS (`fetch`) am echten Handy,
  mit derselben Mini-App. Gemessen wird wie in Abschnitt 3 beschrieben. Das
  Ergebnis kommt in diese Datei, und Sasha entscheidet.
- **Kalender als erstes Paket:** ics lesen und schreiben, RRULE, Vorkommen,
  Deadlines, Ansichten. Prüfstein sind die vorhandenen
  `kalender_testvektoren.json`: Das Paket muss sie bestehen. Danach fallen
  die Dart-Kopie (`regel.dart`, `termin_lesen.dart` …) und später auch die
  Python-Kopie im Kern weg. Dasselbe Paket läuft dann am Rechner im Hub.
- Das Paket wird signiert, steht im Katalog und liegt in den APK-Assets
  vorinstalliert. Der eingebaute Dart-Code geht raus.

### Schritt 4 — Assistent als Paket

- Zuletzt, wie in [hub_bauplan.md](hub_bauplan.md) Reihenfolge Punkt 4: Er
  nutzt die anderen Apps nur über Rechte. Seine Logik ist dünn (Gespräche
  im Format von `core/gespraeche.py`, Kontextpaket, Aufruf von `modell`).
  Schwer wiegen der Baustein `gespraech` und der Dienst `modell` im Motor.

### Was am Rechner passiert

Der Hub bekommt denselben Motor (wasmtime in Python, Baustein-Zeichner in
der TUI). Prozess-Apps bleiben, wie sie sind. `core/eingebaute_apps.py`
schrumpft mit jedem Paket, das daraus entsteht.

## 7. Offene Fragen an Sasha

1. **Ist das Auge der Assistent?** Öffnet Antippen eine austauschbare App
   (wie der Standard-Browser), oder gehört der Assistent zum rohen ZENTRALE?
   Vorschlag: Er ist eine App, und das Auge ist ihr fester Platz.
2. **Laufzeit:** Ist die Probe WASM gegen JS vor der Festlegung in Ordnung?
   Die Neigung geht zu WASM.
3. **Bezahlen am Handy:** Wer in einer Play-App digitale Inhalte kauft, muss
   bei Google über Play Billing zahlen (Google behält einen Anteil). Drei
   Wege: Play Billing nutzen, nur außerhalb der App verkaufen, oder die
   Play-Fassung ohne Kauf ausliefern.
4. **Vertriebswege:** nur Play, oder zusätzlich eine eigene APK oder
   F-Droid (dort ginge das Selbst-Update)?
5. **Ausweg WebView:** Am Handy für Apps wie die Karte erlauben, oder nur
   Bausteine?
6. **Versionen syncen:** Ist es richtig, dass ein Update an einem Knoten
   alle mitzieht? Das folgt aus „ohne Gnade", heißt aber auch: Ein altes
   Gerät zeigt die App nur lesend.
7. **Signier-Schlüssel:** Wo liegt der Store-Schlüssel (nie im Repo, nie
   beim Kunden), und sollen Werkstatt-Apps mit Sashas eigenem Schlüssel
   signiert werden?

## Historie

- **2026-10-29**: Plan geschrieben. Anlass: KI-Chat und Kalender sind am
  Handy fest eingebaut, obwohl sie nach [standort_und_app.md](standort_und_app.md)
  Apps sein sollen.
