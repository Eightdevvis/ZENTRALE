# Knoten beitreten — ein neues Gerät kommt dazu, statt kopiert zu werden

**Stand 2026-10-22: Plan, noch nicht gebaut.** Anlass: der Mini-PC ist da
(im Netzplan schon als Vollknoten eingeplant, [../system/heimnetz.md](../system/heimnetz.md)).
Sasha: *„wir wollen es nich rüber copy pasten einfach sondern das ganze als
neue node in unserem system ansehen"* und *„wenn zentrale aufm server läuft
dann soll man sie auch wie so ein programm anwählen können um sie sich
runterzuziehen"* — also zusammen mit dem Hub-Plan
([hub_bauplan.md](hub_bauplan.md), Umzug Schritt 5: „Hub selbst wird leer
installierbar").

## Begriffe (alle schon in Gebrauch)

- **Installation** — Sashas ZENTRALE: alle seine Geräte und seine Daten.
  Später hat jeder Kunde seine eigene.
- **Knoten** — ein Gerät in einer Installation. Sorten aus dem Netzplan:
  Gehirn (PC), Vollknoten (Laptop, Mini-PC), Außenposten (Pi), Medienknoten,
  fremder Knoten (Handy).
- **Mitte** — der eine Ort, mit dem jedes Gerät seine Daten abgleicht
  ([../betrieb/abgleich.md](../betrieb/abgleich.md)). Heute ein verschlüsseltes
  privates GitHub-Repo, später der PC. **Gebaut, aber noch nicht
  eingeschaltet** (`abgleich_weg` steht auf `rsync`).

## Die Idee: drei Schichten, jede kommt von ihrem eigenen Ort

Ein neues Gerät wird nicht vom alten befüllt. Es holt sich jede Schicht
dort, wo sie wohnt:

| Schicht | Was | Woher | Für alle Knoten gleich? |
|---|---|---|---|
| **Programm** | Hub + Apps (Code) | Katalog: heute git-Tag aus `deploy/RELEASE`, später Sashas Server | ja |
| **Daten** | Listen, Kalender, Gedächtnis, Gespräche … (`data/`) | die Mitte, verschlüsselt | ja |
| **Gerät** | Name, Sorte, Hardware, Schlüssel, Dienste | entsteht **auf** dem Gerät beim Beitritt | nein — gehört nur ihm |

Das Gerät meldet sich danach mit einer **Knoten-Beschreibung** in der Mitte
an. So weiß jeder Knoten, wer noch dazugehört — ohne dass einer den anderen
kennen muss (Stern, nicht Kette).

Was dabei **nie** wandert: private Schlüssel (SSH, WireGuard) — jedes Gerät
erzeugt seine eigenen, nur der öffentliche Teil steht in der Beschreibung.
Der eine geteilte Abgleich-Schlüssel kommt aus KeePass, nicht über das Netz.

## Formate (Standards, kein Eigenformat)

### 1. Knoten-Beschreibung — JSON + JSON Schema

Eine Datei je Knoten, in der Mitte unter `knoten/<name>.json`, Schema
`core/knoten.schema.json` (2020-12). Nur der Knoten selbst schreibt seine
Datei — konfliktfrei durch Bauart, wie beim Handy-Eingang.

```json
{
  "name": "minipc",
  "sorte": "vollknoten",
  "beigetreten": "2026-10-22T18:00:00+00:00",
  "zuletzt_gesehen": "2026-10-22T18:05:00+00:00",
  "hardware": {"gpu": false, "bildschirm": true, "mikro": true, "lautsprecher": true, "dauerlaeufer": false},
  "dienste": ["backend", "tui", "abgleich"],
  "apps": [{"name": "tutor", "version": "0.4.0"}],
  "programm": "2026-10-22.1",
  "netz": {"lan": "192.168.50.21", "wireguard_oeffentlich": null, "ssh_oeffentlich": "ssh-ed25519 AAAA…"}
}
```

- `name` — Hostname, für immer (steht in Dateinamen; Regel aus abgleich.md).
- `sorte` — eine aus dem Netzplan. Daraus folgt, was installiert wird (unten).
- `hardware` — beim Beitritt **erkannt**, nicht gefragt (GPU da? Bildschirm?).
- `dienste` — was hier läuft. Andere Knoten lesen es (z. B. „wer hat Ollama?").
- `netz` — nur öffentliche Teile. Der Router-Eintrag (WireGuard) kommt, wenn
  der Router da ist; bis dahin `null`.

### 2. Einladung — eine `zentrale://`-Adresse

```
zentrale://hub/beitreten?installation=sasha&mitte=git%3Agithub.com%2FEightdevvis%2Fdata
```

URI (RFC 3986), gebaut mit `core/adressen.py`. Sagt dem neuen Gerät, **wohin**
es gehört — aber nie den Schlüssel. Als Text oder QR-Code vom alten Gerät
(Taste im Hub: „Gerät hinzufügen"). Später zeigt die Adresse auf Sashas
Server statt auf GitHub.

### 3. Programm holen — Katalog-Eintrag wie jede App

Der Hub selbst wird ein Stück im Katalog (schema.org `SoftwareApplication`,
[shop.md](shop.md)), mit `softwareVersion` und `downloadUrl`. „Wie ein
Programm anwählen und runterziehen" heißt: das Installations-Skript liest
diesen Eintrag, holt genau diese Fassung und prüft die Prüfsumme. Heute
zeigt `downloadUrl` auf das GitHub-Repo + Tag, später auf Sashas Server.
Apps genauso — ein Knoten holt Apps aus dem **selben** Katalog.

## Was eine Sorte bekommt

| Sorte | Programm | Daten | Dienste |
|---|---|---|---|
| **Gehirn** | alles | alles | Backend, Ollama, Whisper, TTS, Sunshine |
| **Vollknoten** | alles außer Modelle | alles | Backend (KI über Cloud), TUI, Abgleich-Timer |
| **Außenposten** | Positivliste `deploy/aussenposten.txt` | keine (nur HTTP zum Gehirn) | Kiosk, Sensoren |
| **fremder Knoten** | eigene App (Handy) | liest Mitte, schreibt nur Eigenes | — |

Der Mini-PC ist **Vollknoten**: er arbeitet auch allein (unterwegs, PC
schläft), mit der KI über die Cloud, und gleicht über die Mitte ab.

## Ablauf: `zentrale beitreten`

Auf dem neuen Gerät, einmal:

1. **Programm holen** — kleines Startskript (aus dem Katalog) holt den Hub
   in der Fassung aus `deploy/RELEASE`, legt venv + Test-Riegel an.
2. **Einladung lesen** — Adresse eingeben oder QR scannen.
3. **Schlüssel** — aus KeePass eintippen. Prüfen: Mitte erreichbar und lesbar.
4. **Gerät erkennen** — Name, Hardware; Sorte vorschlagen, Sasha bestätigt.
5. **Erstabgleich** — das Gerät hat noch nichts, also: die Mitte gewinnt
   (die Regel steht schon in abgleich.md).
6. **Anmelden** — Knoten-Beschreibung in die Mitte. Eigene SSH-/WireGuard-
   Schlüssel erzeugen, öffentlichen Teil eintragen.
7. **Apps holen** — welche Apps die Installation hat, steht in den Daten;
   der Knoten holt, was zu seiner Sorte und Hardware passt.
8. **Einschalten** — Dienste der Sorte aus `deploy/` (systemd-Nutzer-Units),
   Befehle in `~/.local/bin` verlinken, Abgleich-Timer an.

Wiederholbar: läuft es nochmal, prüft es nur und repariert, was fehlt.
Austreten (Gerät verkauft/verloren): Knoten-Beschreibung als Grabstein,
sein öffentlicher Schlüssel fliegt aus Router und `authorized_keys`.

## Was heute im Weg steht (Reihenfolge)

1. **Mitte einschalten.** Ohne sie gibt es nichts, dem man beitreten kann.
   Sasha: Schlüssel anlegen, in KeePass, Laptop füllt die Mitte
   (abgleich.md „Übergang vom rsync-Weg"). Der PC folgt beim nächsten Start.
2. **Befehle ins Repo.** `zentrale-launch`, `zentrale-sync*`, `zentrale-remote`,
   `find-pc`, `zentrale-pc-setup` liegen nur in `~/.local/bin` des Laptops
   (Kopien in `~/codicus/network`). Der alte Grund („damit sie nicht zum Pi
   syncen") gilt nicht mehr — der Pi bekommt nur seine Positivliste. Ein
   neuer Knoten fände sie sonst nicht.
3. **Knoten-Beschreibung + Schema** (`core/knoten.py`, `knoten.schema.json`),
   Abgleich kennt den Ordner `knoten/<name>.json`.
4. **`zentrale beitreten`** (Schritte oben), erst mit git als Quelle.
5. **Hub als Katalog-Stück** und Startskript — „runterziehen wie ein Programm".
6. Später: Router/WireGuard eintragen, Sashas Server als Mitte und Katalog.

Nach 1–4 ist der Mini-PC ein echter Knoten. 5–6 machen daraus den
Produkt-Weg für jeden Kunden.

## Offen

- Läuft auf dem Mini-PC schon Linux, und welches? (Startskript hängt davon ab.)
- Welche Apps hat die Installation — braucht es dafür eine eigene Liste in
  den Daten, oder reicht der Besitz aus dem Shop (`/api/shop/besitz`)?
  Vorschlag: der Shop-Besitz, dann gibt es eine Wahrheit, nicht zwei.
