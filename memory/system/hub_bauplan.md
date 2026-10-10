# Hub-Bauplan — ZENTRALE als Plattform, die Module als Apps

**Stand 2026-10-10: entschieden, Schritt 1 (Tutor) erledigt; Kacheln
gebaut und neutral (Adressen, Katalog, Farbrollen — unten).** Sasha: *„du lädst zentrale
runter, evt kaufst du schon hardware dazu, und am anfang ist zentrale blank.
dann kann man kalender, mail, ki assistenz, tutor usw reinladen … alle module
die bisher gebaut wurden sind somit die ersten apps … wenn wir zentrale hub
selbst einigermaßen offen lassen, können leute ihren eigenen code schreiben
… und das ding wächst allein."*

Sasha ist Kunde Nr. 1. Seine Daten gehören zu SEINER Installation, nie zum
Produkt.

**Auslöser:** Der Tutor kam über geliehenen Kern-Code an Sashas Kalender
(Gedächtnis-Verdichtung rief `ai.chat_stream` ohne Werkzeug-Liste → voller
Assistent, seit 16.07., behoben 08.10.). Die Grundidee des Kerns — Module
reden nur über Türen — galt INNEN; zwischen Tutor und Kern hielt sie nicht,
weil der Tutor Kern-Code importierte. Der Hub macht aus der Abmachung eine
Grenze.

## Leitlinie: Standards statt Eigenformat (Sasha, 2026-10-10)

Keine eigenen Daten- oder Schnittstellen-Formate: Feld-/Datenbeschreibungen
sind **JSON Schema** (2020-12), HTTP-Schnittstellen **OpenAPI 3.1**
(`openapi.yaml`), Adressen **URIs** (RFC 3986), Flächen **JSON Canvas**.

## Die eine Regel

**Eine App importiert keinen Code einer anderen App und keinen Hub-Code.
Sie spricht nur über die Hub-Schnittstelle** (ein eigener Prozess, HTTP/
Socket mit festem Protokoll). Was sie darf, steht in ihrem Manifest und
wurde vom Nutzer erlaubt. Ein Test pro App erzwingt das (keine Imports
außerhalb der eigenen Wurzel + `zentrale_sdk`).

## Was der Hub ist (leer, klein)

| Dienst | Was | Heute im Code |
|---|---|---|
| **Apps** | installieren, starten, stoppen, aktualisieren; Liste | — (fest eingebaut) |
| **Manifest + Rechte** | App erklärt, was sie braucht; Nutzer erlaubt einmal/immer; widerrufbar | Erlaubnis-Gate nur für KI-Werkzeuge |
| **Datenordner je App** | `daten/<app>/` gehört allein der App; fremde Daten nur über Rechte | alles in `data/` gemischt |
| **Ereignisse** | veröffentlichen/abonnieren: `anwesenheit`, `termin.beginnt`, `mail.neu` … | `events.py`, Event-Loop, `state.py` |
| **Sensoren** | Hardware → Ereignisse (Pi-Bridge, Mikro) | `pi_sensor_bridge`, `brain.py` |
| **Modell-Zugang** | Anbieter, Modell, Budget je App; zwei Ziele: eigener Schlüssel (Selbstbetrieb) oder Sashas Server (verkauft, pro Nutzer gezählt) | die Straße `kern.fahrzeug/fahren` |
| **Abgleich** | Geräte eines Nutzers gleichen ab, verschlüsselt | `abgleich*.py` (Mitte) |
| **Zugang** | Anmeldung am Hub, Schlüssel für fremde Geräte | `zugang.py` |
| **Oberfläche** | Rahmen (Seitenleiste, Fenster, Tasten); Apps bringen ihre Ansichten | TUI-Ansichten fest verdrahtet |

## Manifest (Entwurf)

```
app.toml
  name        = "tutor"
  version     = "0.4.0"
  start       = "python -m tutor.server"     # eigener Prozess
  ansichten   = ["terminal", "fenster"]       # leicht / schick
  rechte      = ["modell", "ereignis:anwesenheit", "mikro", "lautsprecher"]
  liefert     = ["ereignis:tutor.gelernt"]    # was andere abonnieren dürfen
```

Rechte sind fein und lesbar: `kalender:lesen`, `kalender:schreiben`,
`notizen:lesen`, `modell`, `netz:<host>`. Der Assistent bekommt
`kalender:schreiben`, weil Sasha es erlaubt — nicht, weil er die Datei kennt.

## Ansichten: leicht und schick

Eine App liefert Daten und Logik; Ansichten gibt es in zwei Stufen:
- **terminal** — curses, läuft auf billiger Hardware und per ssh;
- **fenster** — grafisch (Pixel-Zimmer, Karte, später schicker).

Der Hub zeigt, was die Hardware kann. Eine App ohne Fenster-Ansicht läuft
trotzdem überall.

## Fremde Apps (offen)

Offen heißt: jeder kann `app.toml` + Code schreiben. Damit das sicher
bleibt, gilt von Anfang an:
- jede App als eigener Prozess, eigener Nutzer/Ordner, nur ihr Datenordner
  schreibbar (Grundlage: die Sandbox aus P7, `bubblewrap`);
- Netz nur zu im Manifest genannten Hosts;
- Rechte fragt der Hub, nie die App selbst;
- Modell-Zugang zählt je App (keine fremde App leert Sashas Budget).

Ohne diese Sandbox gibt es keine fremden Apps — eigene Apps dürfen vorher
schon umziehen.

## Verkaufen (später, nur so viel, dass jetzt nichts im Weg steht)

- Schlüssel nie beim Kunden. Verkaufte Apps sprechen mit Sashas Server; der
  hält den Schlüssel, zählt pro Nutzer, prüft das Abo.
- Kundendaten bleiben beim Kunden (wie bei Sasha). Datenschutz (Stimmen,
  Gespräche), Bedingungen der Modell-Anbieter klären, bevor verkauft wird.

## Umzug der heutigen Module (Reihenfolge)

1. **Tutor** — ✅ erledigt 2026-10-09 (siehe unten „Schritt 1: so ist es
   gebaut"). Erste App, eigenes Repo, eigener Prozess. Braucht vom Hub nur:
   starten, Ereignis `anwesenheit`, Modell-Zugang (eigener Schlüssel,
   eigenes Budget). Weggefallen: `core/tutor_port.py`, `/api/tutor/*`, das
   Text-Panel.
2. **Hub-Schnittstelle + `zentrale_sdk`** (klein, Python) — entsteht MIT dem
   Tutor, nicht vorher auf Vorrat.
3. Kalender, Notizen/Listen, Mail (neu), Karte, Morgenblick — je eine App.
4. **Assistent** zuletzt: er nutzt die anderen nur über Rechte.
5. Hub selbst wird leer installierbar (Sashas Installation = eine von vielen).

Bis Schritt 5 bleibt alles in einem Repo außer dem Tutor; der Kern-Bauplan
(`bauplan_kern.md`) gilt weiter für den Hub-Teil.

## Entscheidungen (Sasha, 2026-10-09)

- Schnittstelle: **HTTP auf localhost** (wie die Fronten heute).
- Manifest: **toml**, Datei `app.toml` im Wurzelordner der App.
- Fremde Apps: erst nach Sandbox + Rechte-Dialog.

## Schritt 1: so ist es gebaut (2026-10-09)

- **Repo** `language-tutor` (GitHub `Eightdevvis/language-tutor`, privat),
  liegt neben ZENTRALE; Geschichte von `tutor/`, den Tutor-Tests und
  `memory/tutor/` (jetzt `docs/`) mitgenommen.
- **Manifest** `app.toml`: `name`, `version`, `start = "python -m tutor.server"`,
  `adresse = "http://127.0.0.1:5070"`, `ansichten`, `rechte = ["modell",
  "ereignis:anwesenheit", "mikro", "lautsprecher"]`, `[ansicht.fenster] start`
  (das Zimmer), `[ereignisse] ziel = "/hub/ereignis"`.
- **Hub-Seite** (ZENTRALE): `core/apps.py` (Ordner per Einstellung
  `app_pfad_<name>`, Manifest lesen, Abonnenten), `core/hub_ereignisse.py`
  (POST an Abonnenten, im Hintergrund, Fehler nur geloggt; `brain.py` schickt
  `anwesenheit`), `scripts/open_tutor_room.py` (App starten: Stimm-Dienste,
  Server, Zimmer; nur Eigenes abräumen), `tui/ansichten/app_start.py`
  (Taste `u`, `/tutor`), Aussenposten-Paket mit `app:tutor/…` → `apps/tutor/`.
- **App-Seite**: eigener Server, eigene Modell-Leitung (Ziel `direkt` mit
  eigenem Schlüssel aus `~/.config/language-tutor/schluessel` oder `hub` =
  Platzhalter mit klarer Meldung), Kosten je Rechner + Monatsbudget, eigene
  Einstellungen statt `ai_config`. Ein Test im Tutor-Repo erzwingt: kein
  Import außerhalb der eigenen Wurzel, und die Leitung bekommt nur den
  Tutor-Prompt.
- **Noch nicht**: `zentrale_sdk` (bisher nicht nötig — der Tutor braucht vom
  Hub nur HTTP), Rechte-Dialog, Datenordner `daten/<app>/` (die Lernstände
  liegen noch am alten Ort `ZENTRALE/tutor/data`, der Tutor findet sie dort),
  Sashas Server für Ziel `hub`.

## Kacheln (entschieden 2026-10-09)

Anlass: Desk View (Fläche je Projekt, JSON-Canvas-Dateien, in der TUI) legt
Dinge anderer Apps als Kacheln auf die Fläche.

**Gebaut 2026-10-10** (Einzelheiten [desk_view.md](desk_view.md) „Kacheln"):
Hub `core/kacheln.py` mit `QUELLEN` (ein Modul je Quelle, im Prozess, Anfrage
und Antwort durch `json.dumps`/`loads`), Form/Fehler `core/kachel_form.py`,
erste Quelle `core/kachel_kalender.py` (App `kalender`, Art `ausschnitt`),
Routen `POST /api/kachel` und `POST /api/kachel/aktion`
([api_endpoints.md](api_endpoints.md)), in der TUI Holen im Hintergrund aus
dem Puffer. **Neutral gemacht 2026-10-10** (die Schnittstelle kennt keine
Oberfläche mehr): Adressen, Katalog und Farbrollen — die drei Abschnitte
unten, alle gebaut. **Listen (`fokus`) und Graphen (`graph`) gebaut
2026-10-10** (Abschnitt „Quellen: Listen und Graphen" unten). Noch nicht:
Manifest-Einträge `liefert`/`[kachel.<art>]` (die eingebauten Quellen
tragen `ARTEN` und `RECHTE` selbst), Abbruch nach 0,5 s (erst für Apps
hinter HTTP; im Prozess wird gemessen und geloggt).

- **Begriff:** Eine Kachel ist ein **Verweis** auf ein Objekt einer anderen
  App — seit 2026-10-10 seine **Adresse** `zentrale://<app>/<art>?<parameter>`
  (vorher App + Art + `ref`) —, keine Kopie. Leitlinie *„dasselbe Objekt, nicht
  kopiert"* (wie AFFiNE): die Wahrheit bleibt in der liefernden App. Der
  Rückfall-Text in der Canvas-Datei ist nur Anzeige-Cache für fremde
  Programme (Obsidian), wird beim Anzeigen überschrieben, nie dort bearbeitet.
- **Offene Formate:** keine eigenen Datenformate. Die Canvas-Datei bleibt
  JSON Canvas 1.0; die Kachel ist ein `text`-Knoten mit Rückfall-Text und
  genau einem Zusatzfeld `zentrale_kachel: {v: 2, adresse}` (die alte Form
  `{v: 1, app, art, ref}` wird beim Lesen umgeschrieben, beim Speichern neu
  geschrieben).
- **App-Namen:** Listen und Graphen sind schon eigene Apps in ZENTRALE und
  heißen **`fokus`** (Listen) und **`graph`** (Graphen). Ihr Code liegt noch
  im Kern, darum zuerst Adapter im Prozess hinter derselben Schnittstelle
  (Anfrage/Antwort gehen durch `json.dumps`/`loads`); beim Auszug wird nur
  der Adapter gegen HTTP getauscht.
- **Manifest:** `liefert = ["kachel:<art>"]`, optional `[kachel.<art>]` mit
  denselben Schlüsseln wie ein Katalog-Eintrag (`titel`, `min`, `bevorzugt`,
  `max`, `ttl`, `parameter`) — heute stehen sie in `ARTEN` der Quelle.
- **Weg:** immer über den Hub (`POST /api/kachel`), nie direkt an die App.
  Anfrage `{adresse, w, h, oben?, stand?, form?}` (`groesse: {w, h}` geht
  auch; `oben` = Blätter-Lage, die Antwort sagt `oben`/`oben_max`). Antwort:
  `form: "zeilen"`, `zeilen` aus Stücken `[text, rolle]` mit Rollen aus dem
  Wörterbuch (unten „Farbrollen"), `text` als Klartext-Rückfall, `stand` +
  `ttl`, `bevorzugt` = Größe für genau diesen Bezug. Die App kürzt selbst
  auf w×h („… 5 weitere"). Ältere Oberflächen dürfen noch `{app, art, ref}`
  schicken.
- **Einheiten:** `w`/`h` sind abstrakte **Zellen** eines Rasters (Spalten ×
  Zeilen), immer das Innere ohne Rahmen. Ein Terminal zeigt eine Zelle als
  ein Zeichen; Fenster und Handy rechnen sie in ihr eigenes Raster um. Die
  Grenze 400 je Richtung schützt die Quelle (ihre Arbeit wächst mit w×h),
  sie beschreibt keinen Bildschirm.
- **Zeitbudget:** eine Antwort soll in 0,5 s da sein. Für Apps hinter HTTP
  bricht der Hub ab („aus"); eine Quelle im Prozess wird gemessen und, wenn
  zu langsam, geloggt. Für jede Oberfläche gilt: nie auf eine Antwort
  warten, aus dem eigenen Puffer zeichnen, im Hintergrund holen.
- **Zu klein / weg / aus:** unter `min` → `{"zu_klein": {w, h}}`, Hinweis
  statt Inhalt; Bezug gelöscht → 404 `{"fehler": "weg"}`; App aus oder
  > 0,5 s → `{"fehler": "aus"}`, letzter Stand in `faint`. Abruf im
  Hintergrund, gezeichnet wird aus dem Puffer.

### Entscheidungen

- **Öffnen** (`POST /api/kachel/aktion`, Hub reicht weiter, App sagt mit
  `{"zeige": {"adresse"}}`, WAS aufgehen soll; die Oberfläche entscheidet,
  wie — bis 2026-10-10 war es ein Ansichtsname der TUI). Kein Abhaken auf der
  Kachel. Geändert 2026-10-10: nicht Enter, sondern **`o`** — Enter greift
  jedes Element, auch Kacheln (eine Regel für alles; desk_view.md).
- **Frisch halten:** nur Pull mit TTL (mit `stand` → `{"unveraendert": true}`).
  Push-Meldungen später.
- **Rohdaten** für Fenster/Handy später; das Feld `roh` ist im
  Antwort-Schema als optional reserviert, damit nichts verbaut wird.
- **Rechte:** `<app>:lesen` reicht, kein Extra-Recht je Art; geprüft im Hub.

### Adressen: ein Objekt, eine Adresse (Leitlinie, gebaut 2026-10-10)

Sasha: jedes Objekt in ZENTRALE hat **genau eine** neutrale Adresse

    zentrale://<app>/<pfad>[?<abfrage>]

z. B. `zentrale://kalender/2026-10-12` (ein Tag) oder
`zentrale://kalender/ausschnitt?modus=mitlaufend&tage=7` (ein Stück
Kalender). Dieselbe Adresse steht im Kachel-Verweis auf der Fläche, kommt
als Antwort von „oeffnen" und dient später als Link in Notizen und auf dem
Handy.

- **Form:** eine gewöhnliche URI (RFC 3986), gebaut und gelesen nur mit
  `urllib.parse` (`core/adressen.py`, kein eigenes Format). Schema immer
  `zentrale`; Autorität = App-Name (klein, `a–z 0–9 _ -`); Pfad = das Objekt
  in der App (Abschnitte prozent-kodiert); Abfrage = Merkmale des Objekts,
  jeder Name höchstens einmal; Fragment reserviert (Stelle in einem Objekt),
  heute abgelehnt.
- **Kanonisch:** Namen der Abfrage sortiert, Werte als Text (Wahr/Falsch =
  `true`/`false`) — dasselbe Objekt ergibt dieselbe Zeichenkette.
- **Kachel:** erster Pfad-Abschnitt = Art aus dem Katalog, Abfrage = deren
  `parameter` (Werte als Text; der Hub liest sie nach dem `type` des
  Schemas, wie OpenAPI Query-Parameter).
- **Wer was tut:** die App vergibt die Adresse und weiß nichts von
  Ansichten. Jede Oberfläche bildet Adressen auf ihre Ansicht ab — in der
  TUI ein kleiner **Router** (`tui/ansichten/sprung.py`: App → Handler(pfad,
  abfrage)), keine if-Kette. Eine neue App bringt einen Handler mit.

### Katalog: was jede App als Kachel liefern kann (gebaut 2026-10-10)

`GET /api/kacheln` → Liste von Einträgen `{app, art, titel, min: {w, h},
bevorzugt: {w, h}, max: {w, h}, ttl, parameter, aktionen: ["oeffnen"],
formen: ["zeilen"]}` (`"roh"` reserviert), nur Apps mit `<app>:lesen`.
Heute gebaut aus `ARTEN` der Quellen im Prozess (`core/kacheln.py`), später
aus `[kachel.<art>]` im `app.toml` derselben App. Genaue Form aller
Kachel- und Desk-Routen: **`openapi.yaml`** (Repo-Wurzel, OpenAPI 3.1, seit
2026-10-10) — `tests/test_openapi.py` prüft, dass jede Route unter
`/api/kachel*`, `/api/kacheln`, `/api/desk*` dort steht und umgekehrt, dass
die Datei gültig ist und echte Antworten zu ihren Schemas passen.

- **Parameter = JSON Schema** (2020-12, `core/kachel_parameter.py`, seit
  2026-10-10; die eigene `felder`-Liste davor ist ganz weg). Benutzte
  Teilmenge: `properties` (type string|integer|number|boolean, `title`,
  `description`, `default`, `minimum`/`maximum`, `minLength`/`maxLength`,
  `format: date`, Auswahl als `oneOf [{const, title}]` oder `enum`),
  `required`, `allOf [{if: {properties: {x: {const}}}, then: {required,
  properties: {y: false}}}]` (Felder, die nur bei einem Wert gelten),
  `additionalProperties: false`. Reihenfolge der `properties` =
  Reihenfolge im Dialog (die Route liefert unsortiert).
- **Zur Fragezeit** trägt die Quelle mit `parameter_jetzt(art, schema)` ein,
  was erst dann feststeht: die Listen/Graphen zur Wahl (`oneOf`), die
  Vorgaben von heute (Kalender von/bis). Geprüft wird gegen das Schema
  der Quelle ohne diese Auswahl — eine gelöschte Liste heißt so „weg".
- **Prüfen:** der Hub liest die Werte der Adresse nach `type`, prüft mit
  dem Paket `jsonschema` (nur Backend; fehlt es → `aus`) und gibt den
  wichtigsten Fehler als einen deutschen Satz zurück (400 `ungueltig`).
- **Nicht in JSON Schema ausdrückbar:** Beziehungen zwischen zwei Werten,
  hier der Abstand zweier Daten (Kalender: „bis" nicht vor „von",
  höchstens 31 Tage). Das prüft die Quelle in `pruefen(art, ref)`, der Hub
  ruft es gleich nach dem Schema; 400 mit ihrem Text. Im Schema steht die
  Regel nur als `description` („höchstens 31 tage ab „von“").
- **Fach-Regeln wohnen in der App:** jede Oberfläche baut ihren
  Anlege-Dialog **generisch** aus dem Schema (TUI:
  `tui/bausteine/feld_dialog.py`, nur Standardbibliothek, prüft leicht:
  Typ, Grenzen, Pflicht); Herr über die Regeln ist der Hub, sein Satz
  steht im Dialog.
- **Desk:** der `+`-Wähler = eigene Arten (Zettel, Bild) + alle
  Katalog-Einträge; eine neue App erscheint von selbst. Die Startgröße
  sagt der Hub für genau die gewählten Werte (`bevorzugt` in der Antwort).

### Farbrollen: die App sagt die Bedeutung, die Oberfläche die Farbe (gebaut 2026-10-10)

Das Wörterbuch steht neutral in `core/farbrollen.py` (Name + eine Zeile
Bedeutung): `text`, `leise`, `kopf`, `betont`, `heute`, `spanne`, `mehr`,
`warnung`, `erledigt`. Kachel-Antworten tragen nur diese Namen (der Hub
macht aus Unbekanntem `text`). Jede Oberfläche bildet jede Rolle auf ihre
Farben ab — die TUI in `tui/ansichten/farben.py` `FARBROLLEN` (ein Test
verlangt, dass jede Rolle abgedeckt ist); Unbekanntes zeichnet sie neutral
wie `text`. Neue Rolle = Eintrag im Wörterbuch + in jeder Oberfläche.

### Quellen: Listen und Graphen (gebaut 2026-10-10)

Wie der Kalender ein Modul je Quelle im Prozess, eingetragen in `QUELLEN`;
beide **lesen nur** (Sasha: `o` = nur öffnen, kein Abhaken auf der Kachel).

- **`fokus`/`liste`** (`core/kachel_fokus.py`): Parameter `liste` (Text,
  Auswahl zur Fragezeit), `erledigte` (boolean, Standard nein), `tiefe` (integer 1–9,
  Standard 3, „ebenen"). Adresse z. B.
  `zentrale://fokus/liste?erledigte=false&liste=l_einkauf&tiefe=3`. Kopf =
  Name, Bernstein-Steine, „erledigt/alle" (Blätter); darunter die Punkte
  wie in der Listen-Ansicht geordnet (offen, Fokus oben, wenig Offenes
  zuerst; Erledigtes dahinter, wenn gewünscht), `○`/`✓`, Ordner `▾`/`▸`
  mit „d/t", 2 Zellen Einrückung je Ebene; blättern mit `oben`, „+N
  weitere". `oeffnen` → `zentrale://fokus/<liste>`; der Router der TUI
  versteht auch `zentrale://fokus/<liste>/<eintrag>`. Gelesen über
  `lists.read_lists()` (neu: schreibt garantiert nie, auch nicht die
  einmalige »week«-Migration).
- **`graph`/`verlauf`** (`core/kachel_graph.py`): Parameter `graph` (Text,
  Auswahl zur Fragezeit), `tage` (integer 2–365, Standard 14). Kopf = Name (+ Einheit),
  rechts der letzte Wert; darunter Balken aus `▁▂▃▄▅▆▇█`, je Tag eine
  Spalte (bis 3 breit), heute rechts in `heute`, Tage ohne Wert als leiser
  Punkt; mehr Tage als Spalten → Mittel je Spalte; unten min/max (und der
  Zeitraum, wenn Platz ist). Typen: number/scale als Zahl (scale fest
  0–5), time als Uhrzeit, period als Dauer („7h30"). Keine Werte im
  Zeitraum → „keine werte in N tagen". `oeffnen` →
  `zentrale://graph/<gid>`.
- **Werte zur Laufzeit** (`parameter_jetzt` der Quelle, seit 2026-10-10
  statt `dynamisch`/`werte`): welche Liste/welcher Graph steht erst beim
  Fragen fest — der Katalog trägt sie als `oneOf` ein; gibt es keine, fehlt
  der Eintrag im Katalog. Der Hub prüft nur die Form (Text); gibt es den
  Wert nicht mehr → 404 `weg`.
- **Geteilte Helfer:** die Ansicht der TUI und die Kachel rechnen mit
  denselben reinen Funktionen (`core/listen_baum.py`,
  `core/graph_reihen.py`, umgezogen aus `tui/ansichten/fokus.py`,
  `graphen.py`, `basis.py`) — Leitlinie „dasselbe Objekt, nicht kopiert".

**Offen:** Behält Obsidian beim Speichern unbekannte Knotenfelder? Noch
nicht geprüft (Kacheln sind trotzdem gebaut — verliert Obsidian das Feld,
bleibt ein Zettel mit dem Rückfall-Text übrig, nichts geht kaputt).

**Nachtrag 2026-10-10 (Größe ändern im Desk):** Der Katalog trägt `max`
jetzt immer. Nennt die Quelle keins, setzt der Hub seine neutrale Grenze
`{w: 400, h: 400}` (`GROESSE_GRENZE`) ein — eine Oberfläche braucht dafür
keine eigene Zahl. Die TUI holt `min`/`max` beim Druck auf `r` und lässt
eine Kachel nicht kleiner als `min` ziehen.
