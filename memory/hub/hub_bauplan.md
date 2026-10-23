# Hub-Bauplan — ZENTRALE als Plattform, die Module als Apps

> **Unterbau.** Seit 2026-10-23 steht das Leitbild darüber
> ([../leitbild.md](../leitbild.md)): der Hub wird nur so weit ausgebaut, wie
> eine Etappe dort es braucht.

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

## Grundpfeiler

Anonymität, Datenschutz, Open Source und „überall deploybar“ stehen im
Leitbild ([../leitbild.md](../leitbild.md)).

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
- **Schaufenster** (gebaut 2026-10-10, [shop.md](shop.md)): Katalog als
  schema.org-ItemList, heute alles Preis 0 und nur „holen"; Tauschstelle für
  Sashas Server ist `shop._katalog_roh()`.

## Umzug der heutigen Module (Reihenfolge)

1. **Tutor** — ✅ erledigt 2026-10-09 (siehe unten „Schritt 1: so ist es
   gebaut"). Erste App, eigenes Repo, eigener Prozess. Braucht vom Hub nur:
   starten, Ereignis `anwesenheit`, Modell-Zugang (eigener Schlüssel,
   eigenes Budget). Weggefallen: `core/tutor_port.py`, `/api/tutor/*`, das
   Text-Panel.
2. **Hub-Schnittstelle + `zentrale_sdk`** (klein, Python) — entsteht MIT dem
   Tutor, nicht vorher auf Vorrat.
3. Kalender, Notizen/Listen, Mail (neu), Karte, Morgenblick — je eine App.
   **Karte ✅ erledigt 2026-10-22** (unten „Schritt Karte: so ist es gebaut").
   Reihenfolge der übrigen: [kern_auszug_inventur.md](kern_auszug_inventur.md) D.
4. **Assistent** zuletzt: er nutzt die anderen nur über Rechte.
5. Hub selbst wird leer installierbar (Sashas Installation = eine von vielen).

Bis Schritt 5 bleibt alles in einem Repo außer Tutor und Karte; der Kern-Bauplan
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

## Apps starten, stoppen, weiterreichen (gebaut 2026-10-22)

Hub-Grundlagen aus der Kern-Inventur ([kern_auszug_inventur.md](kern_auszug_inventur.md)
D Schritt 1): was jede ausziehende App vom Hub braucht. Alles über HTTP,
genaue Form in `openapi.yaml` (Tag `apps`; was die App selbst beantwortet:
Tag `app-seite`, Pfade `/hub/…`).

**Manifest, neue Schlüssel** (Prozess-Apps = `start` + `adresse`):

```toml
autostart = true                 # startet mit dem Backend
routen    = ["/api/map"]         # diese Pfade (und alles darunter) gehören der App
liefert   = ["kachel:liste"]     # Kachel-Quelle über HTTP, dazu:
[kachel.liste]                   # derselbe Eintrag wie ARTEN einer Quelle im Prozess
titel = "liste"
min = [12, 7]
ttl = 30
parameter = "kachel/liste.schema.json"    # JSON Schema (Datei im App-Ordner oder Tabelle)
kann = ["aktion", "parameter_jetzt", "pruefen", "bevorzugt"]   # optionale Fragen
```

- **Daten** `[daten]` (`muster`, `abgleichen`; seit 2026-10-23): was der App
  gehört und abgeglichen werden darf — nur, was genau so auf der Positivliste
  steht. Form und Regeln: [cloud_app.md](cloud_app.md).
- **Liste** `GET /api/apps`: alle installierten Apps aus ihren Manifesten
  (Prozess- und selbst gebaute), je `laeuft` (parallel `GET
  <adresse>/hub/gesund`, kurz), `gestartet_vom_hub`, `routen`, `daten` …
- **Start/Stopp** `POST /api/apps/<name>/start|stop` (`core/app_verwaltung.py`).
  Start: läuft sie schon — egal, wer sie gestartet hat —, passiert nichts;
  sonst `start` im App-Ordner, Python der App, Log `/tmp/zentrale-app-<name>.log`,
  bis 15 s auf `/hub/gesund` warten. Stopp **nur, was der Hub gestartet hat**
  (sonst 409 `fremd`). Damit der Hot Reload (exec) seine Apps nicht vergisst,
  liegt je gestarteter App eine Marke (Prozessnummer + Startzeit) im
  Laufzeit-Ordner (`$XDG_RUNTIME_DIR/zentrale-apps-<uid>/`, Einstellung
  `app_lauf_ordner`). **Autostart:** `core/main.py` startet beim Hochfahren
  jede App mit `autostart = true` im Hintergrund und räumt beim Ende nur das
  Eigene ab; Einstellung `apps_autostart` (Standard an; `aus` z. B. am
  Laptop). Die Handgriffe (Python, Befehl, lebt, anhalten) teilt der Hub mit
  dem Zimmer-Starter des Tutors: `core/app_prozess.py` (stdlib, auch im
  Pi-Paket).
- **Weiterleitung** (`core/app_weiterleitung.py`, eingehängt in
  `ui/routen/hub_apps.py` direkt nach der Tür `zugang`): gehört ein Pfad laut
  `routen` einer App (nur an Abschnittsgrenzen: `/api/map` besitzt
  `/api/map/base`, nicht `/api/mapx`), reicht der Hub Methode, Pfad, rohe
  Abfrage, Körper und Inhalts-Köpfe (`Content-Type`, `Accept` …) unverändert
  an die `adresse`; Status, Inhalts-Köpfe und Körper kommen byte-gleich
  zurück. Nie mit: `Authorization`, `Cookie`, `Set-Cookie`, `Host`,
  Verbindungs-Köpfe. Umleitungen der App gehen an den Aufrufer (der Hub folgt
  nicht). App aus / nicht erreichbar / 30 s still → 503 `{"fehler": "aus"}`.
  Die App lauscht nur auf 127.0.0.1 — wer sie will, geht durch die Tür des
  Hubs. Die alten Pfade bleiben so für TUI, Browser und Pi gleich. Die
  Routen-Tabelle wird 2 s gepuffert; ein neues `routen` greift ohne Neustart.
- **Kachel-Quelle über HTTP** (`core/kachel_http.py`): eine App mit
  `liefert = ["kachel:<art>"]` hängt `core/kacheln.py` als Quelle ein —
  dieselbe Schnittstelle wie im Prozess, Fragen an `POST <adresse>/hub/kachel`
  (und `/aktion`, `/parameter`, `/pruefen`, `/bevorzugt`, je nach `kann`), je
  höchstens **0,5 s**, sonst „aus". Heißt die App wie eine Quelle im Prozess,
  gewinnt die App (so zieht `fokus` später aus, ohne dass eine Oberfläche es
  merkt). Ein Test zeigt: dieselbe Quelle im Prozess und hinter HTTP gibt
  byte-gleiche Antworten (`tests/test_hub_grundlagen.py`).
- **Wächter** (Inventur E1–E4): E1 ausgezogene Apps importiert niemand
  (`bauplan_kern.md` „Ausgezogene Apps"), E2 die TUI-Tür schrumpft nur, E3 je
  App im App-Repo (Grenz-Test, Vorlage `language-tutor/tests/test_tutor_grenze.py`),
  E4 jede Route der TUI steht in `openapi.yaml` oder gehört einer App
  (Altlasten: [routen_altlast.md](routen_altlast.md)).

## Schritt Karte: so ist es gebaut (2026-10-22)

- **Repo** `zentrale-karte` neben ZENTRALE (noch ohne GitHub-Gegenstück).
  Geschichte mitgenommen (`git filter-branch` auf einer Kopie, 27 Commits):
  `core/map/` → `karte/map/`, `core/glossary.py` → `karte/glossary.py`,
  `ui/routen/karte.py` → `karte/routen.py` (Code unverändert),
  `scripts/map_window.py` → `karte/fenster.py`, `map_render_proto.py` und
  `ingest_shipdensity.py` → `werkzeuge/`, `tests/test_map_*.py`,
  `memory/maps/*.md` → `docs/`. Gecachte Layer-Daten (gitignored) aus
  `core/map/data/cache/` nach `karte/map/data/cache/` kopiert.
- **Manifest** `app.toml`: `start = "python -m karte.server"`, `adresse =
  "http://127.0.0.1:5071"`, `autostart = true`, `routen = ["/api/map"]`,
  `[ansicht.fenster] start = "python -m karte.fenster"`, keine Rechte.
- **Beweis, dass nichts kaputt ist:** 30 Anfragen an alle fünf Routen (mit
  Fehlern 400/404/405) auf festem Stand (Netz zu, dieselben Cache-Dateien)
  vor dem Umzug gegen ZENTRALE aufgenommen (zweimal, gleich) und danach durch
  die Weiterleitung — Status, Inhaltstyp und Körper byte-gleich. Die
  Aufnahme liegt im Karten-Repo (`tests/aufnahme_vor_umzug.json`) und wird
  dort für alle Anfragen ohne Live-Daten bei jedem Testlauf wiederholt.
- **Hub-Seite:** `apps.BEKANNT["karte"]`, Weiterleitung `/api/map/*`,
  Autostart; die TUI-Ansicht `tui/ansichten/karte.py` bleibt (ruft nur
  HTTP), Taste `w` ruft `scripts/open_app_window.py karte` (öffnet
  `[ansicht.fenster]` jeder App). Weg aus ZENTRALE: `core/map/`,
  `core/glossary.py`, `ui/routen/karte.py`, die drei Skripte, drei Tests.
- **Wächter:** E1 (`karte`, `map`, `glossary` in „Ausgezogene Apps"), E3 im
  Karten-Repo (`tests/test_karte_grenze.py`), Test-App
  `tests/fixtures/app_karte`.

## Selbst gebaute Apps: Manifest ohne Prozess (2026-10-10)

Die Werkstatt ([werkstatt.md](werkstatt.md)) baut Apps ohne Code aus einer
Vorlage. Sie tragen **dasselbe `app.toml`** wie eine Prozess-App, nur ohne
`start` (kein Prozess) und mit `vorlage`:

```toml
name = "Geige"           # Anzeige
version = "0.1.0"
vorlage = "desk"         # was beim Öffnen aufgeht (heute nur desk)
icon = "icon.png"        # Pixel-Icon neben app.toml — oder icon_motiv = "post"
desk = "Geige"           # Vorlage desk: Name des Desks (Verweis, keine Kopie)
```

Ort: `<apps_ordner>/<slug>/` (Standard `data/apps/`, abgeglichen). Gefunden
über `core/apps.py` (`eigene()` durchsucht den Ordner; `BEKANNT` bleibt für
Prozess-Apps). Adresse `zentrale://<slug>/` — der TUI-Router öffnet den Desk.
Sie haben keine `rechte`, abonnieren also nichts.

## Tastentabelle: welche Tasten in welcher Ansicht (gebaut 2026-10-11)

Sasha: die Leiste ganz unten zeigt nur, was in der offenen Ansicht geht, und
niemand schreibt sie von Hand. Jede App sagt es mit einer **Tastentabelle**
(`core/tastentabelle.py`, JSON; Schema in `openapi.yaml`):

```toml
[[tasten.liste]]                 # Ansicht "liste"
taste = "↑↓"                     # Beschriftung = woraus die Oberfläche die Tasten liest
aktion = "waehlen"
text = "select"                  # englisch; ohne text: genommen, nicht gezeigt
[[tasten.liste]]
taste = "d"
aktion = "loeschen"
text = "delete"
```

`GET /api/tasten` liefert die Tabellen aller installierten Apps. Die
eingebauten TUI-Programme tragen dasselbe Format im Code und **verteilen ihre
Tasten über genau diese Tabelle** (`tui/ansichten/tasten.py`) — Anzeige und
Verhalten können nicht auseinanderlaufen. Die Oberfläche fragt beim
Verkabeln einmal (der Horcher, `tui/ansichten/horcher.py`) und merkt sich die
Einträge je Ansicht; wer keine Tabelle hat, wird abgehört (Tasten probieren
in einer Wegwerf-Umgebung, ohne Namen). Einzelheiten:
[tui_bauplan.md](../system/tui_bauplan.md) „Tastentabelle".

## Kacheln (entschieden 2026-10-09)

Anlass: Desk View (Fläche je Projekt, JSON-Canvas-Dateien, in der TUI) legt
Dinge anderer Apps als Kacheln auf die Fläche.

**Gebaut 2026-10-10** (Einzelheiten [desk_view.md](desk_view.md) „Kacheln"):
Hub `core/kacheln.py` mit `QUELLEN` (ein Modul je Quelle, im Prozess, Anfrage
und Antwort durch `json.dumps`/`loads`), Form/Fehler `core/kachel_form.py`,
erste Quelle `core/kachel_kalender.py` (App `kalender`, Art `ausschnitt`),
Routen `POST /api/kachel` und `POST /api/kachel/aktion`
([api_endpoints.md](../system/api_endpoints.md)), in der TUI Holen im Hintergrund aus
dem Puffer. **Neutral gemacht 2026-10-10** (die Schnittstelle kennt keine
Oberfläche mehr): Adressen, Katalog und Farbrollen — die drei Abschnitte
unten, alle gebaut. **Listen (`fokus`) und Graphen (`graph`) gebaut
2026-10-10** (Abschnitt „Quellen: Listen und Graphen" unten). Seit 2026-10-22
auch über HTTP: Manifest-Einträge `liefert`/`[kachel.<art>]` und Abbruch nach
0,5 s (oben „Apps starten, stoppen, weiterreichen"); die eingebauten Quellen
im Prozess tragen `ARTEN` und `RECHTE` weiter selbst (gemessen und geloggt).

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
`warnung`, `erledigt`, `auswahl` (seit 2026-10-11: das Gewählte, auf dem
der Cursor steht — Listen-Bild). Kachel-Antworten tragen nur diese Namen (der Hub
macht aus Unbekanntem `text`). Jede Oberfläche bildet jede Rolle auf ihre
Farben ab — die TUI in `tui/ansichten/farben.py` `FARBROLLEN` (ein Test
verlangt, dass jede Rolle abgedeckt ist); Unbekanntes zeichnet sie neutral
wie `text`. Neue Rolle = Eintrag im Wörterbuch + in jeder Oberfläche.

### Quellen: Listen und Graphen (gebaut 2026-10-10)

Wie der Kalender ein Modul je Quelle im Prozess, eingetragen in `QUELLEN`;
beide **lesen nur** (Sasha: `o` = nur öffnen, kein Abhaken auf der Kachel).

- **`fokus`/`liste`** (`core/kachel_fokus.py`): Parameter `liste` (Text,
  Auswahl zur Fragezeit), `erledigte` (boolean, Standard nein: die
  abgeschlossenen statt der offenen zeigen), `tiefe` seit 2026-10-11
  veraltet (`deprecated`, ohne Wirkung, nur für alte Adressen). Adresse z. B.
  `zentrale://fokus/liste?erledigte=false&liste=l_einkauf`. **Das Bild
  zeichnet die Kachel nicht selbst** (Regel seit 2026-10-11: *Programm und
  Kachel teilen EIN Bild*): es kommt aus `core/listen_bild.py`, derselben
  Quelle, die die Listen-Ansicht der TUI malt — oberste Ebene, Kopf,
  Bernstein als Status, Einträge als Kästen mit Titel und Markern, „+N" im
  letzten Kasten; blättern mit `oben`. Einzelheiten, Wächter und der
  spätere Auszug: [listen_app.md](listen_app.md). `oeffnen` →
  `zentrale://fokus/<liste>`; der Router der TUI versteht auch
  `zentrale://fokus/<liste>/<eintrag>`. Gelesen über `lists.read_lists()`
  (schreibt garantiert nie, auch nicht die einmalige »week«-Migration).
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
  Bei Listen seit 2026-10-11 auch das Bild selbst (`core/listen_bild.py`).
  **Regel für jede App mit Kachel:** Programm und Kachel teilen EIN Bild —
  die Kachel ruft dieselbe Bild-Quelle wie die Vollansicht, nie einen
  eigenen Zeichner ([listen_app.md](listen_app.md)).

**Offen:** Behält Obsidian beim Speichern unbekannte Knotenfelder? Noch
nicht geprüft (Kacheln sind trotzdem gebaut — verliert Obsidian das Feld,
bleibt ein Zettel mit dem Rückfall-Text übrig, nichts geht kaputt).

**Nachtrag 2026-10-10 (Größe ändern im Desk):** Der Katalog trägt `max`
jetzt immer. Nennt die Quelle keins, setzt der Hub seine neutrale Grenze
`{w: 400, h: 400}` (`GROESSE_GRENZE`) ein — eine Oberfläche braucht dafür
keine eigene Zahl. Die TUI holt `min`/`max` beim Druck auf `r` und lässt
eine Kachel nicht kleiner als `min` ziehen.

## KI-Werkzeuge aus dem Schema erzeugen (Sasha, 2026-10-10)

Sasha: „wir wollen unseren agenten so fit machen, dass er auch mit anderen
kalendern arbeiten könnte … kalender api gibt format für termin anlegen — ki
harness wird aus den feldern GEBAUT — ki tool ist so strukturiert damit ki
keine scheiße macht — auch schwächere ki kann mit fremden kalender/anderem
programm arbeiten, weil unser programm die schnittstelle zum fremden programm
so ergänzt, dass die ki damit arbeiten MUSS."

Heute sind die KI-Werkzeuge je Bereich von Hand geschrieben
(core/ki_kalender*.py, werkzeug_register.py). Ziel: sie werden ERZEUGT.

```
Quelle (Schema)  →  Adapter (Grundaktionen)  →  Werkzeug-Erzeuger (Harness)  →  KI
JSON Schema /       lesen · anlegen · ändern    Felder/Pflicht/Enums aus Schema
OpenAPI / MCP /     löschen · nachlesen(id)     + Gate · Nachlesen · ganz-oder-gar-nicht
CalDAV / Kern                                   + Kennungen · Fehlercodes · Erledigt-Zeile
                                                + Selbstauskunft · Auftrags-Abrechnung
                                                + Zuschnitt je Modellprofil (schwach: weniger
                                                  Felder, einfache Texte, erst nachsehen)
```

- **Quelle:** eine App oder ein fremdes Programm beschreibt seine Aktionen als
  Schema (Standard statt Eigenformat: JSON Schema, OpenAPI 3.1, MCP-Server).
- **Adapter:** dünn, je Quelle; übersetzt auf die Grundaktionen. Pflicht:
  Nachlesen per Kennung (sonst kein Beleg) und Ablehnung mit Code statt
  stiller Korrektur.
- **Erzeuger:** baut die Werkzeug-Einträge (Name, Beschreibung, Parameter je
  Schiene) und hängt die Schutzschichten an, die heute pro Werkzeug von Hand
  stehen. Prompt-Cache: das erzeugte Schema ist pro Prozess fest.
- **Prüfstein:** zuerst der eigene Kalender — erzeugte Werkzeuge müssen auf
  dem Prüfstand mindestens so gut sein wie die handgeschriebenen (f01k, f02,
  f03, f06, f10, f11). Danach Tagesphasen/Kategorien direkt so, dann ein
  fremder Kalender (CalDAV/Google), später Mail.
- **MCP:** Fremde MCP-Server lassen sich so anbinden — ZENTRALE nimmt deren
  Werkzeug-Schemas und legt dieselben Schutzschichten darum; ein MCP-Server,
  der kein Nachlesen kann, bekommt nur Lesen frei.

**Schritt 1 gebaut (2026-10-10):** der eigene Kalender als erste Quelle,
mit Tagesphasen, Gruppen und Ebene „vielleicht". Erzeuger
`core/werkzeug_erzeuger/` (Aktion = MCP-Werkzeug-Definition + `x-zentrale`),
Schemas `core/werkzeug_kalender.py`, Adapter `core/ki_kalender_adapter.py`;
Einstellung `werkzeuge_erzeugt` (Standard an), klein byte-gleich. Mechanik,
Anbinden einer neuen Quelle, was „sauber" für einen Adapter heißt:
[werkzeug_erzeuger.md](../ki/werkzeug_erzeuger.md). Offen: Messung mit
echten Modellen (Prüfstand inkl. neuer Fälle f12 Phase, f13 Gruppe), dann
der handgeschriebene gross-Weg weg; danach ein fremder Kalender.

## Anbindungs-Pipe der Werkstatt (Sasha, 2026-10-11)

Sasha: „wir preppen jetzt die werkstatt und dann wenn wir ein neues
programm, einen neuen baustein usw anbinden wollen … können wir die pipe
ausprobieren, ob die werkstatt das schaffen könnte. aber dafür müssten wir
erstmal die coding ai fit machen.. das stell ich mir aber schwer vor".

**Kern-Idee: die Werkstatt schreibt keinen Code, sie füllt eine Beschreibung
aus.** Der Kalender-Adapter (core/ki_kalender_adapter.py) ist heute Python;
fast alles darin lässt sich aber als feste, prüfbare Beschreibung sagen. Ein
**allgemeiner Adapter** (einmal gebaut) führt solche Beschreibungen aus; der
Werkzeug-Erzeuger (oben) macht daraus die KI-Werkzeuge mit allen
Schutzschichten.

Eine **Anbindungs-Beschreibung** (offenes Format: JSON/YAML, Aktionen als
MCP-Werkzeug-Definitionen bzw. OpenAPI-Operationen) sagt je Aktion:
- Art (lesen | anlegen | ändern | löschen), Bereich, Wörter für Frage und
  Erledigt-Zeile;
- Aufruf (MCP-Werkzeug oder HTTP-Methode + Pfad) und wo die Kennung in der
  Antwort steht;
- **Nachlesen** (Aufruf per Kennung) und **Vergleich** (welche Felder wie
  normalisiert verglichen werden, z. B. Uhrzeit, Zeitzone);
- **Zurückbauen** (anlegen → löschen; ändern → alten Stand zurückschreiben;
  löschen → nur mit Wiederherstellen-Aufruf, sonst gar nicht frei).

**Stufen, automatisch ermittelt:**
1. Schema + Kennung + Nachlesen + Zurückbauen → volle Schutzschicht.
2. Schema ohne Nachlesen → Lesen frei; Schreiben fragt jedes Mal, Ergebnis
   „nicht belegt", kein Zurückbauen.
3. Kein Schema (GUI) → nur Browser/Bildschirm; nicht für schwache Modelle.

**Die Pipe:**
1. *Ansehen* — die KI liest die Selbstbeschreibung (MCP-Liste, OpenAPI, Doku).
2. *Ausfüllen* — sie schreibt die Anbindungs-Beschreibung (streng geprüftes
   Format → auch schwächere Modelle schaffen das; Formularwerk, keine
   Programmierung).
3. *Probefahrt* — Prüfstand gegen eine Test-Kopie/Test-Konto des Programms:
   je Aktion anlegen → nachlesen → zurückbauen; Bericht je Aktion.
4. *Freigabe* durch Sasha; bis dahin Stufe 2 (Lesen frei, Schreiben mit
   Rückfrage, „nicht belegt").

**Codicus** (die Coder-App, ≠ Ordner ~/codicus) wird nur für Fälle
gebraucht, die echten eigenen Code verlangen. Bis es Codicus gibt,
übernimmt das Claude Code.

**Reihenfolge:** (a) allgemeiner Adapter für MCP + OpenAPI nach den Regeln
oben — **gebaut 2026-10-11** (Format `core/werkzeug_erzeuger/anbindung.schema.json`, Adapter `allgemein.py`, Probefahrt `scripts/anbindung_probe.py`; MCP über stdio und HTTP, OpenAPI nur von Hand als http-Aufrufe; Doku: [werkzeug_erzeuger.md](../ki/werkzeug_erzeuger.md) „Anbindungs-Beschreibung"); (b) Probe: den eigenen Kalender einmal per Beschreibung statt per
Python anbinden und auf dem Prüfstand vergleichen; (c) Werkstatt-Ansicht für
Ansehen/Ausfüllen/Probefahrt/Freigabe (gehört zur Werkstatt-Sitzung).

**Stand (b) 2026-10-11:** die Probe am eigenen Kalender läuft (`core/anbindungen/kalender_kern.json`, HTTP gegen `/api/calendar`, Probefahrt voll grün, Anbindung standardmäßig aus); Unterschiede zu den Handwerkzeugen stehen in werkzeug_erzeuger.md. Auf dem Prüfstand mit echtem Modell noch nicht gemessen. (c) bleibt bei der Werkstatt-Sitzung.
