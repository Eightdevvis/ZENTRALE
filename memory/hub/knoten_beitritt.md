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
| **Programm** | Hub + Apps (Code) | Hub: einmal herunterladen (heute Repo-Fassung `deploy/RELEASE`); Apps: durch den Hub aus dem Katalog | ja |
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

### 3. Programm holen — der Hub einmal, alles andere durch ihn

Den Hub lädt man **einmal** aus dem Internet (heute: das Repo in der Fassung
aus `deploy/RELEASE`, später eine Download-Seite). Er ist kein Stück in
seinem eigenen Katalog — er trägt selbst, wo seine Updates liegen. Apps holt
er danach aus dem Katalog ([shop.md](shop.md)).

**Achtung (2026-10-22): eine leere Hub-Fassung gibt es noch nicht.**
Kalender, Listen, Graphen, Assistent stecken im Kern; nur der Tutor ist
ausgezogen. Installation/Paket/Updates „fehlt ganz"
([produkt_inventur.md](produkt_inventur.md)). Für den Mini-PC heißt das:
er bekommt vorerst den ganzen Kern, wie Laptop und PC.

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

1. **Programm holen** — den Hub einmal herunterladen
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
5. **Leere Hub-Fassung** — Kern-Apps ausziehen (hub_bauplan.md Schritt 3–5), Download-Weg für den Hub.
6. Später: Router/WireGuard eintragen, Sashas Server als Mitte und Katalog.

Nach 1–4 ist der Mini-PC ein echter Knoten. 5–6 machen daraus den
Produkt-Weg für jeden Kunden.

## Offen

- Mini-PC läuft mit **EndeavourOS** (Arch). Die Setup-Doku kennt bisher nur
  Debian/Pop!_OS — Systempakete und Python-Fassung (Arch ist meist neuer)
  beim Beitritt eigens prüfen.
- Welche Apps hat die Installation — braucht es dafür eine eigene Liste in
  den Daten, oder reicht der Besitz aus dem Shop (`/api/shop/besitz`)?
  Vorschlag: der Shop-Besitz, dann gibt es eine Wahrheit, nicht zwei.

---

# Bauplan v1 — Login, Cloud, installierbarer Hub (entschieden 2026-10-22)

Sasha, 22.10. abends: *„eine installierbare quelle für den hub — begrüßung,
wie man den zentrale befehl erhältlich macht, -h gut ausgeschmückt, programm
leicht aufmachbar, per terminal oder TUI. login muss drin sein. der login
zieht deine ganzen online daten und synced dich komplett."* Beim Einrichten:
**alles übernehmen / einzeln an- und abwählen / clean slate**. Zielgruppe
international.

## Entscheidungen

| Frage | Entscheidung |
|---|---|
| Cloud | **Cloudflare** Workers + D1 (Konten, Sitzungen, Codes, Kopf der Mitte) + R2 (verschlüsselte Dateien, Pakete). Weltweit, anfangs kostenlos, kein Server zu pflegen. Adresse vorerst `*.workers.dev`. |
| Schutz | **Zero-Knowledge** (Bitwarden-Modell): der Server sieht nie Passwort, Schlüssel oder Klartext. |
| Passwort weg | **Notfallschlüssel**, einmal gezeigt beim Konto-Anlegen. |
| Download | **Nur mit Einladungscode** (private Beta). `install.sh` ist öffentlich, das Paket nicht. |
| Sprache | **Englisch** für CLI, Begrüßung, Assistent; Texte in einer eigenen Datei, Deutsch später als zweite Sprache. |
| Login | **optional.** Ohne Login läuft ZENTRALE rein lokal. |
| Wählbare Einheiten | **Apps** (seit 2026-10-23, [cloud_app.md](cloud_app.md)): jede sagt in `[daten]`, was sie hat; eingebaute in `core/eingebaute_apps.py`. Bis dahin Bereiche aus der Positivliste (`abgleich_bereiche`, wird übernommen). |
| Besitz | gehört dem **Konto**, nicht dem Gerät: jedes eingeloggte Gerät sieht ihn. Installiert ist je Gerät (Knoten-Beschreibung). |
| Konto-Kennung | **Anonym** (23.10.): ein selbst gewählter **Benutzername**, keine Mail — weder gefragt noch gespeichert. 3–32 Zeichen `a-z 0-9 . _ -`, vorn ein Buchstabe, NFC + klein; reservierte Namen (admin, root, support, zentrale…) gehen nicht; `@` → Hinweis „No email needed". Sasha: *„jedem das Recht und die Freiheit geben, komplett anonym zu bleiben."* |
| Keine erzeugten Kontonummern | Erst angeboten (Mullvad-Art), am 23.10. wieder gestrichen: **ein Weg für alle**. Eine Wahl wäre selbst Metadaten („diese Person nahm die anonyme Option") und verkleinert die Anonymitätsmenge (Tor-Prinzip). Der Assistent fragt nur `username:`. |
| Sashas Konto | Sasha legt einen Namen fest und das Konto selbst an (Passwort nur bei Sasha); dann kommt der Name in die Var `BETREIBER_NAMEN`. Echte Daten werden erst dann hochgeladen. |

## Schlüssel (alles auf dem Gerät)

```
passwort ─Argon2id(salz, t=3, m=64 MiB, p=4)→ hauptschluessel (32 B)
hauptschluessel ─HKDF-SHA256 info="zentrale/anmelden/v1"→ anmelde_schluessel → an den Server (base64url)
hauptschluessel ─HKDF-SHA256 info="zentrale/verpacken/v1"→ verpack_schluessel (als Fernet-Schlüssel)
konto_schluessel  = Fernet.generate_key()     ← verschlüsselt ALLE Daten (dasselbe Format wie die Mitte heute)
verpackt_passwort = Fernet(verpack_schluessel).encrypt(konto_schluessel)
notfall           = 32 zufällige Bytes, gezeigt als Base32 in Vierergruppen
verpackt_notfall  = Fernet(HKDF(notfall, info="zentrale/notfall/v1")).encrypt(konto_schluessel)
notfall_beweis    = base64url(HKDF(notfall, info="zentrale/notfall-beweis/v1", 32 B)) → an den Server
```

- Der Name geht in keine Ableitung ein (Schema oben unverändert, die
  Testvektoren gelten weiter).
- Der Server speichert: Benutzername (klein, NFC), `salz`, KDF-Werte,
  HMAC-SHA256 (Schlüssel = 32 zufällige Server-Bytes je Konto, Spalte
  `hash_art`) über `anmelde_schluessel` und über `notfall_beweis`,
  `verpackt_passwort`, `verpackt_notfall`. Kein langsamer Hash auf dem
  Server (geändert 22.10.): Argon2id auf dem Gerät trägt die Last, ein
  abgeleiteter 256-Bit-Schlüssel ist nicht durchprobierbar — so reicht der
  Gratis-Plan von Cloudflare (10 ms CPU je Anfrage).
- Passwort ändern = nur `verpackt_passwort` neu, mit dem alten
  `anmelde_schluessel` als Beweis. Notfall = mit dem Notfallschlüssel
  `konto_schluessel` auspacken, neues Passwort setzen (ohne altes).
- Auf dem Gerät liegt nach dem Login: Sitzung + `konto_schluessel` in
  `~/.config/zentrale/konto.json` (Rechte 600). Abmelden löscht beides.

## Schnittstelle (`cloud/openapi.yaml`, OpenAPI 3.1, Präfix `/v1`)

Antworten JSON; Fehler `{"fehler": "<code>", "text": "<english sentence>"}`.
Sitzung als `Authorization: Bearer <token>`.

| Route | Was |
|---|---|
| `GET /install.sh` | öffentlich; das Installationsskript |
| `GET /v1/paket` | `?code=` oder Bearer → `{version, sha256, groesse}` der neuesten Fassung |
| `GET /v1/paket/<version>.tar.gz` | `?code=` oder Bearer → das Paket |
| `POST /v1/konto` | `{name, code, salz, kdf, anmelde_schluessel, verpackt_passwort, verpackt_notfall, notfall_beweis}` → 201 `{name, erstellt}`. Code wird verbraucht (der Download verbraucht ihn nicht). Name vergeben → **409** `name_vergeben`, Code bleibt frei — die einzige Stelle, die verrät, dass es einen Namen gibt (nur wer einen freien Code hat). |
| `POST /v1/vorab` | `{name}` → `{salz, kdf}`. Unbekannter Name: erfundene, aber für diesen Namen feste Werte (verrät nicht, ob es das Konto gibt). |
| `POST /v1/sitzung` | `{name, anmelde_schluessel, knoten}` → `{token, laeuft_ab, verpackt_passwort}`. Gedrosselt (5 Fehlversuche/15 min je Name und IP; Zähler nur als HMAC mit Tagesschlüssel, nie Name/IP im Klartext). |
| `DELETE /v1/sitzung` | abmelden |
| `POST /v1/notfall` | `{name, notfall_beweis}` → `{verpackt_notfall, token, laeuft_ab}`; der Token gilt 15 min und nur für `PUT /v1/konto/passwort`. Gedrosselt wie die Sitzung. |
| `PUT /v1/konto/passwort` | `{salz, kdf, anmelde_schluessel, verpackt_passwort, altes_anmelde_schluessel}` — `altes_…` Pflicht mit normaler Sitzung (gedrosselt), nicht mit dem Notfall-Token. Beendet alle anderen Sitzungen (nach Notfall: alle). |
| `GET /v1/mitte` | `{kennung|null, namen: [...]}` |
| `GET /v1/mitte/datei/<name>` | Bytes der Datei im aktuellen Stand |
| `POST /v1/mitte/fehlende` | `{sha256: [hex, …]}` (bis 20 000) → `{fehlen: [...]}` — welche Blobs das Konto noch nicht hat |
| `PUT /v1/mitte/blob/<sha256>` | rohe Bytes (bis 24 MiB) → 204; Prüfsumme falsch → 400 `pruefsumme` |
| `POST /v1/mitte/stand` | `{basis: kennung|null, verweise: {name: sha256}, schreiben: {name: base64}, loeschen: [...]}` (JSON bis 4 MiB, `schreiben` zusammen bis 256 KiB) → 200 `{kennung}` oder **409** `jemand_schneller` (Compare-and-Swap auf den Kopf in D1); verwiesener Blob fehlt → 400 `blob_fehlt` mit `fehlen` |
| `GET /v1/mitte/enthaelt/<kennung>` | `{enthaelt: bool}` |
| `PUT /v1/knoten/<name>` / `GET /v1/knoten` | Knoten-Beschreibung (Klartext-Metadaten ohne Inhalt, siehe oben); schreiben nur der eigene Name der Sitzung; GET → `{knoten: [...]}` |
| `GET/PUT /v1/besitz` | Besitz des Kontos (schema.org `ItemList`, verschlüsselt als ein Blob): `{besitz: string|null, aktualisiert}` / PUT `{besitz: string}` |
| `GET /v1/nutzung` | nur Konten aus der Var `BETREIBER_NAMEN`, sonst 403 `nur_betreiber` → `{zeit, grenzen_geprueft, grenzen: [{id, name, used, limit, unit, period, percent, level, source, self, cloudflare, cloudflare_at, costs_money}], warnungen: [{id, name, level, percent, text}]}`; `level` = `ok`/`50`/`80`/`95`/`voll`. Gratis-Grenzen und Zählweise: [../betrieb/cloud.md](../betrieb/cloud.md) |
| Bremse | `PUT /v1/mitte/blob/…` und Inline-Dateien eines Stands → **507** `speicher_voll`, wenn R2 dadurch über den Gratis-Speicher käme (Var `BREMSE_SPEICHER`, Vorgabe `an`) |

`<name>` in der Mitte sind die schon verschlüsselten Namen (`inhalt.enc`,
`d/<hmac>.enc`, `knoten/<k>/<hmac>.enc`) — der Server sieht dasselbe, was
heute GitHub sieht. Ein Stand = Liste (Name → R2-Objekt nach Prüfsumme);
`vorbereiten` + `senden` der Mitte-Schnittstelle werden auf dem Gerät zu
`fehlende` → je fehlendem Blob ein `PUT /v1/mitte/blob/…` → EIN
`POST /v1/mitte/stand` mit `verweise` (die `HttpMitte` merkt sich die
Änderung bis `senden`). Blobs hochladen ist harmlos, wenn der Stand danach
mit 409 scheitert — sie liegen nach Prüfsumme und werden beim nächsten
Versuch wiederverwendet.

## Das Programm (`zentrale`) — gebaut 2026-10-22 (Client-Seite)

Was es wirklich gibt (Branch `cloud-client`; der Server entsteht getrennt
gegen dieselbe Schnittstelle):

| Teil | Wo |
|---|---|
| Schlüssel-Schema, nur Rechnen | `core/konto_schluessel.py` |
| Draht zur Cloud (urllib, Fehler als englischer Satz) | `core/cloud_api.py` — Adresse an EINER Stelle: `VORGABE`, Env `ZENTRALE_CLOUD` |
| Konto: anlegen, anmelden, abmelden, Notfall, Passwort ändern | `core/konto.py` → `~/.config/zentrale/konto.json` (600) |
| Mitte über die Cloud | `HttpMitte` in `core/abgleich_mitte.py` ([../betrieb/abgleich.md](../betrieb/abgleich.md)) |
| Apps je Gerät | `core/abgleich_apps.py`, `core/eingebaute_apps.py` |
| Knoten-Beschreibung, Hardware erkannt | `core/knoten.py` |
| Der Befehl | `zentrale_cli/` (Front, Tür im Kern-Bauplan), Starter `bin/zentrale`, `pyproject.toml` (Einstiegspunkt für `pip install -e .`) |
| Alle Texte (Englisch) | `zentrale_cli/texte.py` — Deutsch = zweites Wörterbuch mit denselben Schlüsseln |
| Paket | `deploy/paket.txt` + `scripts/paket_bauen.py` → `dist/` |
| Installieren | `deploy/install.sh` (gerendert aus `install.sh.in`), Ablauf in [../betrieb/setup.md](../betrieb/setup.md) |
| Verteilung (seit 23.10.) | apt/.deb, pacman/PKGBUILD, curl-Einzeiler aus demselben tar.gz; öffentlich erst nach Schalter + Durchsicht — [../betrieb/verteilung.md](../betrieb/verteilung.md) |
| Grundlage ohne lokale KI | `requirements-basis.txt` |

- **Befehle:** `zentrale` (TUI über `scripts/start_tui.sh`; beim allerersten
  Start ohne Einrichtung erst der Assistent — nicht im Entwickler-Checkout mit
  `.git`), `-h` (Banner, Gruppen, Beispiele; Farbe nur am Terminal und ohne
  `NO_COLOR`), `welcome`, `setup`, `login`, `logout`, `account create`,
  `account recover`, `account password` (dazugekommen), `sync`, `status`,
  `devices`, `update`, `version`.
- **`account create`** rechnet alles auf dem Gerät (`konto.Entwurf`), zeigt
  den Notfallschlüssel EINMAL mit Warnung und legt das Konto erst an, wenn
  bestätigt ist, dass er gesichert ist (sonst bleibt der Code unverbraucht).
- **`setup`:** abgemeldet → anmelden / Konto anlegen / lokal bleiben; dann
  nur die Apps, die hier oder in der Cloud schon Daten haben: alle / einzeln
  (Pfeiltasten + Leertaste, über ssh; ohne Terminal über Nummern) / keine.
  Hat keine Daten: „Nothing to sync yet — new apps will ask when they have
  data." (`abgleich_apps = {}`). Danach immer `abgleich_mitte_art=http`,
  `abgleich_weg=mitte` (die App `cloud` ist an), Gerät melden, abgleichen.
- **Neue App mit Daten:** fragt einmal bei `sync` und beim Start; ohne
  Terminal eine Zeile. **`status`** zeigt unter „Apps" die Cloud und je App
  synced / stays on this device / not decided yet.
- **`devices`:** meldet zuerst die eigene Beschreibung (`PUT /v1/knoten/<hostname>`,
  Sorte `vollknoten`, Hardware gpu/bildschirm/mikro/lautsprecher erkannt),
  dann `GET /v1/knoten`.
- **Ohne Terminal im Kern:** `konto`, `HttpMitte`, `knoten` fragen nichts und
  drucken nichts; Handy, Browser, Tablet, Pi, AR rufen dieselben Abläufe.

### Festlegungen, die die Schnittstelle offen ließ

| Frage | Festgelegt |
|---|---|
| HKDF-Salz | keins (RFC 5869: 32 Null-Bytes), Länge 32, SHA-256 |
| Kodierung von `salz`, `anmelde_schluessel`, `notfall_beweis` | base64url **ohne** `=` |
| Fernet-Schlüssel (`verpack`, `notfall`, `konto_schluessel`) | base64url **mit** `=` (Fernet-Format) |
| Passwort-Bytes | UTF-8 nach Unicode-NFC |
| `kdf` | `{"name": "argon2id", "t": 3, "m": 65536, "p": 4}`, `m` in KiB; der Client liest auch `iterations`/`memory`/`parallelism` |
| `salz` | 16 zufällige Bytes |
| Notfallschlüssel als Text | Base32 (RFC 4648) ohne `=`, 52 Zeichen, 13 Vierergruppen mit `-`; beim Eingeben egal: Groß/klein, Leerzeichen, `0/1/8` → `O/I/B` |
| `knoten` in `POST /v1/sitzung` | Hostname als Text |
| Hochladen in die Mitte (abgesprochen mit dem Server-Teil, 22.10.) | Blobs nach sha256: `POST /v1/mitte/fehlende` → `PUT /v1/mitte/blob/<sha256>` (rohe Bytes, ≤ 24 MiB, 400 `pruefsumme`) → `POST /v1/mitte/stand {basis, verweise: {name: sha256}, loeschen}`; 400 `blob_fehlt` → einmal nachladen. Das alte `schreiben` (Base64) nutzt der Client nicht |
| `GET /v1/knoten` | `{knoten: [...]}` (eine nackte Liste wird auch gelesen) |
| `PUT /v1/knoten/<name>` | nur unter dem Namen, mit dem die Sitzung angemeldet ist (sonst 403 `fremder_knoten`) |
| Notfall | `POST /v1/notfall` → `{verpackt_notfall, token, laeuft_ab}`; der Token darf NUR `PUT /v1/konto/passwort`; danach normal anmelden |
| Passwort ändern | `PUT /v1/konto/passwort` mit der Sitzung + `altes_anmelde_schluessel` (altes Passwort, altes Salz/KDF über `/v1/vorab`); der Server beendet die anderen Sitzungen |
| KDF-Untergrenze | `m` ≥ 19456 KiB — der Client nimmt schwächere Werte auch vom Server nicht an |
| Einladungscode | `ZB-XXXX-XXXX-XXXX-XXXX`; der Client schickt ihn groß und ohne Leerzeichen |
| Mindestlänge Passwort | 10 Zeichen (nur Client) |
| Fehler 401 | Client sagt „Wrong username or password." bzw. „Not logged in" |

### Testvektoren für andere Oberflächen

`tests/daten/konto_testvektoren.json`: festes Passwort, Salz und KDF-Werte →
`hauptschluessel`, `anmelde_schluessel`, `verpack_schluessel`; feste
Notfall-Bytes → Base32-Text, `notfall_schluessel`, `notfall_beweis`; dazu
`verpackt_passwort`/`verpackt_notfall` mit fester Zeit und festem IV (nur zum
Nachprüfen — echte Clients würfeln den IV). Wer das Schema nachbaut (Dart,
WebCrypto + argon2-wasm, der Cloudflare-Server), prüft sich Byte für Byte
daran. `tests/test_konto_schluessel.py` friert die Werte ein und rechnet HKDF
unabhängig aus HMAC nach. Eine Änderung am Schema = neue `…/v2`-Infos und
neue Vektoren, nie still.

### Offen

- ~~Die echte Cloud-Adresse eintragen~~ (erledigt 23.10.; steht nur noch in
  `core/cloud_api.py` `VORGABE`, install.sh bekommt sie beim Rendern).
- `GET/PUT /v1/besitz` nutzt der Client noch nicht.
- Dateien der Mitte kommen ohne Stand-Angabe („aktueller Stand"); ein
  optionales `?stand=<kennung>` an `GET /v1/mitte/datei/<name>` machte das
  Lesen exakt statt „neu holen, wenn es sich bewegt".
- Einzelne Dateien über 24 MiB lehnt der Client mit klarem Satz ab (Grenze
  eines Blobs); Anhänge in der Ablage könnten so groß sein.
- Ein ganzer Lauf von `install.sh` auf einem frischen EndeavourOS steht aus
  (geprüft: Syntax, shellcheck, Schutz des vorhandenen Befehls).
- **Sashas Entwickler-Checkout bleibt unberührt:** `~/.local/bin/zentrale`
  auf dem Laptop wird nicht angefasst (install.sh bricht ab); rsync bleibt
  dort Vorgabe, bis Sasha umstellt.
