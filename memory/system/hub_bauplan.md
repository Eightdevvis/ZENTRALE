# Hub-Bauplan — ZENTRALE als Plattform, die Module als Apps

**Stand 2026-10-09, Entwurf zum Entscheiden.** Sasha: *„du lädst zentrale
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

1. **Tutor** — erste App, eigenes Repo, eigener Prozess. Braucht vom Hub nur:
   starten, Ereignis `anwesenheit`, Modell-Zugang (eigener Schlüssel,
   eigenes Budget). Fällt weg: `core/tutor_port.py`, `/api/tutor/*`, das
   Text-Panel. Er ist die Probe, ob die Schnittstelle trägt.
2. **Hub-Schnittstelle + `zentrale_sdk`** (klein, Python) — entsteht MIT dem
   Tutor, nicht vorher auf Vorrat.
3. Kalender, Notizen/Listen, Mail (neu), Karte, Morgenblick — je eine App.
4. **Assistent** zuletzt: er nutzt die anderen nur über Rechte.
5. Hub selbst wird leer installierbar (Sashas Installation = eine von vielen).

Bis Schritt 5 bleibt alles in einem Repo außer dem Tutor; der Kern-Bauplan
(`bauplan_kern.md`) gilt weiter für den Hub-Teil.

## Offene Entscheidungen (Sasha)

- Schnittstelle: HTTP (wie heute) oder lokaler Socket? Vorschlag: HTTP auf
  localhost, gleich wie die Fronten heute.
- Manifest-Format: toml (lesbar) — ok?
- Ab wann fremde Apps: erst nach Sandbox + Rechte-Dialog.
