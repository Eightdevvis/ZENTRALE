# Hub-Bauplan — ZENTRALE als Plattform, die Module als Apps

**Stand 2026-10-09: entschieden, Schritt 1 (Tutor) erledigt; Kacheln nur
Vorschlag (unten).** Sasha: *„du lädst zentrale
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

## Kacheln (Vorschlag, 2026-10-09 — Sasha entscheidet)

**Stand: nur Vorschlag, nichts gebaut, nichts entschieden.** Anlass: die
App „Desk View" (unendliche Fläche je Projekt, JSON-Canvas-1.0-Dateien, in
der TUI) will Dinge anderer Apps als Kacheln auf die Fläche legen — Listen,
Graphen, allgemein jede Ausgabe einer ZENTRALE-App. Leitplanken aus der
Assistent-Session sind eingearbeitet; Unentschiedenes ist **(offen)**.

### Begriff

Eine **Kachel** ist ein Ausschnitt dessen, was eine App weiß, so gezeichnet,
dass eine *andere* Oberfläche ihn einbetten kann, ohne den Code der App zu
kennen. Die App rechnet den Inhalt, der Verbraucher (Desk View, später
Morgenblick, Handy) zeichnet Rahmen und Position. Eine Kachel hat drei
Kennzeichen: **App** (wer liefert), **Art** (welche Sorte, z. B. `liste`),
**Bezug** `ref` (welches Ding, z. B. `{"id": "l_einkauf"}`). Auf der Fläche
ist die Kachel eine Element-Art der Canvas-Registry; der Canvas selbst weiß
nichts von Listen.

### Manifest

```
liefert = ["kachel:liste", "kachel:graph"]
[kacheln]
ziel   = "/hub/kachel"          # POST, Standard wie bei [ereignisse]
aktion = "/hub/kachel/aktion"   # Enter/Klick
[kachel.liste]
min = [16, 3]                   # kleinste sinnvolle Größe (Zellen w×h)
ttl = 30                        # Sekunden, wie lange eine Antwort frisch ist
```

Ohne `[kachel.<art>]` gelten Standardwerte (min 10×2, ttl 60).

### Anfrage und Antwort

Der Verbraucher fragt **nie die App direkt, sondern den Hub**
(`POST /api/kachel`); der Hub prüft das Recht und reicht weiter (HTTP oder
Adapter). Größe = Innenfläche *ohne* Rahmen — den zeichnet der Verbraucher
(`draw_box`).

```
→ {"app": "listen", "art": "liste", "ref": {"id": "l_einkauf"},
   "groesse": {"w": 32, "h": 8}, "ansicht": "terminal",
   "roh": false, "stand": "a41f"}            # stand = was ich schon habe
← {"titel": "Einkauf", "stand": "a52c", "ttl": 30,
   "groesse": {"w": 28, "h": 4},              # tatsächlich belegt, ≤ Anfrage
   "zeilen": [
     [["☐ ", "faint"], ["Milch", "dim"]],
     [["☑ ", "acc"],   ["Brot", "dim", {"durch": true}]],
     [["… 5 weitere", "faint"]]],
   "ziele": [{"zeile": 0, "eintrag": 3}, {"zeile": 1, "eintrag": 4}],
   "text": "Einkauf\n- [ ] Milch\n- [x] Brot\n…",   # Klartext-Rückfall
   "roh": null}                               # bei roh:true: z. B. die Liste wie /api/lists
```

- **Farben nur als Rollen** aus `tui/ansichten/farben.py` (`ROLES`: `dim`,
  `faint`, `bright`, `acc`, `warn`, `graph`, `num`, `kal` …). Nie curses-
  Nummern oder RGB — Tag/Nacht und Mono-Rückfall bleiben Sache des
  Verbrauchers (`Kontext.apply_theme`). Unbekannte Rolle → `dim`.
  `{"durch": true}` = durchgestrichen (wie `addclip(strike=True)`).
- **Größe aushandeln:** die App füllt höchstens die angefragte Fläche, darf
  kleiner antworten, kürzt selbst („… 5 weitere"). Ist die Fläche unter
  `min` → `{"zu_klein": {"w": 16, "h": 3}}`, der Verbraucher zeigt einen
  Hinweis statt Inhalt.
- **Fehler / nicht erreichbar:** unbekannter Bezug → 404
  `{"fehler": "weg", "text": "Liste gelöscht"}`; App aus oder > 0,5 s →
  der Hub antwortet `{"fehler": "aus"}`, der Verbraucher zeigt den letzten
  Stand in `faint` mit „‹listen aus›". Nie blockieren: abgerufen wird im
  Hintergrund (wie der `Store`), gezeichnet wird immer aus dem Puffer.
- **Frisch halten — Vorschlag: Pull mit TTL, Push nur als Anstoß.** Der
  Verbraucher fragt neu, wenn die Kachel sichtbar und `ttl` abgelaufen ist;
  mit `stand` antwortet die App `{"unveraendert": true}`, wenn sich nichts
  tat (billig). Zusätzlich darf eine App `ereignis:kachel.geaendert`
  `{art, ref}` liefern; der Hub setzt dann nur die TTL der betroffenen
  Kacheln auf 0 — der Inhalt kommt trotzdem per Pull. So gibt es *einen*
  Weg für Daten und Push ist reine Beschleunigung. **(offen, Frage 2)**

### Kachel in der Canvas-Datei

JSON Canvas kennt nur `text`, `file`, `link`, `group`. Eine Kachel wird ein
**`text`-Knoten mit Rückfall-Text** plus einem eigenen Feld, damit Obsidian
sie als lesbare Notiz zeigt und ZENTRALE sie als Kachel erkennt:

```
{"id": "k7", "type": "text", "x": 120, "y": 40, "width": 320, "height": 200,
 "text": "**Einkauf** · _Kachel listen/liste_\n- [ ] Milch\n- [x] Brot",
 "zentrale_kachel": {"v": 1, "app": "listen", "art": "liste",
                     "ref": {"id": "l_einkauf"}, "stand": "a52c"}}
```

`text` = letzter Klartext-Rückfall (`text` der Antwort), beim Speichern
geschrieben. Zellengröße ↔ Pixel (`width`/`height`) rechnet Desk View, nicht
die Kachel. ⚠ prüfen: ob Obsidian unbekannte Felder beim Speichern behält —
sonst ist die Kachel nach einem Obsidian-Edit nur noch Text (still verloren,
kein Absturz).

### Listen und Graphen: Adapter im Prozess

Listen und Graphen sind noch Kern-Module, keine Apps. Damit der Umzug später
nur den Adapter tauscht:

- `core/kacheln.py` (Hub-Seite): `holen(anfrage) → antwort`,
  `aktion(anfrage) → antwort`; Tabelle `QUELLEN = {"listen": ImProzess(…),
  "graphen": ImProzess(…), <app>: Http(manifest)}`. Eingebaute Quellen tragen
  ein Pseudo-Manifest (`liefert`, `[kachel.*]`), damit Rechte und Standard-
  werte gleich laufen.
- `core/kachel_listen.py`, `core/kachel_graphen.py`: je `kachel(anfrage) →
  dict`, lesen nur `lists.list_lists()` bzw. `graphs.list_graphs()` +
  `read_values()`; Graph im Terminal als Funken-Zeile in Rolle `graph`.
- **Regel, per Test:** Anfrage und Antwort gehen beim Adapter durch
  `json.dumps`/`loads` (nichts, was HTTP nicht könnte); Desk View importiert
  weder `core/lists` noch `core/graphs`, nur den Hub-Aufruf.
- **Umzug:** die Listen-App bedient dieselbe Funktion unter
  `POST /hub/kachel`; in `QUELLEN` wird `ImProzess` zu `Http` — eine Zeile.

### Enter → Ereignis

Enter/Klick auf eine Kachel (oder auf eine Zeile mit Eintrag in `ziele`) →
Verbraucher an Hub `POST /api/kachel/aktion {app, art, ref, aktion:
"oeffnen", ziel: {"eintrag": 3}}` → Hub an die App (`[kacheln] aktion`).
Die App entscheidet, was „öffnen" heißt, und antwortet z. B.
`{"zeige": {"ansicht": "listen", "ziel": {"lid": "l_einkauf", "iid": 3}}}`;
der Rahmen (Hub-Oberfläche) springt dorthin. Vorerst nur `oeffnen` — alles,
was ändert (Abhaken auf der Kachel), erst mit Schreib-Recht. **(offen, Frage 4)**

### Rechte

- Eine Kachel ist Lesen. Wer Kacheln von App X will, braucht dasselbe
  Recht wie für ihre Daten: `listen:lesen`, `graphen:lesen` … — kein
  Extra-Recht je Art.
- Geprüft wird im Hub (`/api/kachel`), nie in der App, nie im Verbraucher.
- `oeffnen` braucht kein Schreib-Recht (navigiert nur, geändert wird in der
  Ansicht der App selbst).
- Der Rückfall-Text in der Canvas-Datei trägt Daten der App aus ihrem
  Datenordner heraus (in die Projektdatei, evtl. in einen Obsidian-Tresor).
  **(offen, Frage 3)**

### Offene Fragen an Sasha

1. Heißen die eingebauten Quellen schon jetzt `listen`/`graphen` (wie die
   künftigen Apps), oder bekommen sie bis zum Umzug einen Kern-Namen?
2. Frisch halten: nur Pull mit TTL reicht für den Anfang — oder soll
   `kachel.geaendert` (Push als Anstoß) gleich mit?
3. Darf der Rückfall-Text (Inhalt der Kachel) in die Canvas-Datei, oder nur
   ein neutraler Platzhalter („Kachel listen/liste")?
4. Soll man auf einer Kachel direkt etwas ändern dürfen (abhaken), oder ist
   Enter immer nur „in der App öffnen"?
5. Brauchen Kacheln eigene feine Rechte (`kachel:listen/liste`), oder reicht
   `<app>:lesen` wie vorgeschlagen?
6. Rohdaten (`roh`) schon jetzt mitdenken (Fenster, Handy) oder erst, wenn
   eine solche Ansicht wirklich kommt?
