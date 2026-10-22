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
| Wählbare Einheiten | Bis es eine leere Hub-Fassung gibt: **Bereiche** der Daten (aus `core/abgleich_auswahl.py`) + echte Apps (Tutor). |
| Besitz | gehört dem **Konto**, nicht dem Gerät: jedes eingeloggte Gerät sieht ihn. Installiert ist je Gerät (Knoten-Beschreibung). |
| Sashas Konto | `jenny_wolff@hotmail.com`; Sasha legt es selbst an (Passwort nur bei Sasha). Echte Daten werden erst dann hochgeladen. |

## Schlüssel (alles auf dem Gerät)

```
passwort ─Argon2id(salz, t=3, m=64 MiB, p=4)→ hauptschluessel (32 B)
hauptschluessel ─HKDF-SHA256 info="zentrale/anmelden/v1"→ anmelde_schluessel → an den Server (base64url)
hauptschluessel ─HKDF-SHA256 info="zentrale/verpacken/v1"→ verpack_schluessel (als Fernet-Schlüssel)
konto_schluessel  = Fernet.generate_key()     ← verschlüsselt ALLE Daten (dasselbe Format wie die Mitte heute)
verpackt_passwort = Fernet(verpack_schluessel).encrypt(konto_schluessel)
notfall           = 32 zufällige Bytes, gezeigt als Base32 in Vierergruppen
verpackt_notfall  = Fernet(HKDF(notfall, info="zentrale/notfall/v1")).encrypt(konto_schluessel)
```

- Der Server speichert: Mail (klein geschrieben), `salz`, KDF-Werte, einen
  PBKDF2-SHA256-Hash (eigenes Server-Salz, 600 000 Runden) über den
  `anmelde_schluessel`, `verpackt_passwort`, `verpackt_notfall`.
- Passwort ändern = nur `verpackt_passwort` neu. Notfall = mit dem
  Notfallschlüssel `konto_schluessel` auspacken, neues Passwort setzen.
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
| `POST /v1/konto` | `{mail, code, salz, kdf, anmelde_schluessel, verpackt_passwort, verpackt_notfall}` → 201. Code wird verbraucht. |
| `POST /v1/vorab` | `{mail}` → `{salz, kdf}`. Unbekannte Mail: erfundene, aber für diese Mail feste Werte (verrät nicht, ob es das Konto gibt). |
| `POST /v1/sitzung` | `{mail, anmelde_schluessel, knoten}` → `{token, laeuft_ab, verpackt_passwort}`. Gedrosselt (5 Fehlversuche/15 min je Mail und IP). |
| `DELETE /v1/sitzung` | abmelden |
| `POST /v1/notfall` | `{mail, notfall_beweis}` → `{verpackt_notfall, token}` für das Neusetzen; danach `PUT /v1/konto/passwort` |
| `PUT /v1/konto/passwort` | `{salz, kdf, anmelde_schluessel, verpackt_passwort}` |
| `GET /v1/mitte` | `{kennung|null, namen: [...]}` |
| `GET /v1/mitte/datei/<name>` | Bytes der Datei im aktuellen Stand |
| `POST /v1/mitte/stand` | `{basis: kennung|null, schreiben: {name: base64}, loeschen: [...]}` → 200 `{kennung}` oder **409** `jemand_schneller` (Compare-and-Swap auf den Kopf in D1) |
| `GET /v1/mitte/enthaelt/<kennung>` | `{enthaelt: bool}` |
| `PUT /v1/knoten/<name>` / `GET /v1/knoten` | Knoten-Beschreibung (Klartext-Metadaten ohne Inhalt, siehe oben) |
| `GET/PUT /v1/besitz` | Besitz des Kontos (schema.org `ItemList`, verschlüsselt als ein Blob) |

`<name>` in der Mitte sind die schon verschlüsselten Namen (`inhalt.enc`,
`d/<hmac>.enc`, `knoten/<k>/<hmac>.enc`) — der Server sieht dasselbe, was
heute GitHub sieht. Ein Stand = Liste (Name → R2-Objekt nach Prüfsumme);
`vorbereiten` + `senden` der Mitte-Schnittstelle werden auf dem Gerät zu
EINEM `POST /v1/mitte/stand` (die `HttpMitte` merkt sich die Änderung bis
`senden`).

## Das Programm (`zentrale`)

- **Paket:** `pyproject.toml` mit Einstiegspunkt `zentrale`; das Paket baut
  `scripts/paket_bauen.py` aus einer **Positivliste** (`deploy/paket.txt`,
  wie `aussenposten.txt`): kein `data/`, keine Keys, kein `memory/`,
  keine Tests.
- **`install.sh`:** fragt den Einladungscode (oder nimmt ihn als Argument),
  prüft Python ≥ 3.11 + venv, lädt das Paket, prüft sha256, legt es unter
  `~/.local/share/zentrale/hub/<version>/` ab, venv mit
  `requirements-basis.txt` (ohne Whisper/TTS/Ollama-Teile), verlinkt
  `~/.local/bin/zentrale`, sagt, falls `~/.local/bin` nicht im PATH ist, wie
  man es dazunimmt (bash/zsh/fish), dann die **Begrüßung**. Läuft auf
  Debian/Ubuntu/Pop!_OS **und Arch/EndeavourOS** (nennt fehlende
  Systempakete je Paketverwaltung, installiert nichts mit Root selbst).
- **Befehle:** `zentrale` (TUI), `zentrale -h` (ausgeschmückt: Banner,
  Gruppen, Beispiele), `zentrale welcome`, `zentrale setup` (Assistent:
  Login ja/nein → alles / auswählen / clean slate → holen),
  `zentrale login`, `zentrale logout`, `zentrale account create`,
  `zentrale account recover`, `zentrale sync`, `zentrale status`,
  `zentrale devices`, `zentrale update`, `zentrale version`.
  Erster Aufruf ohne Einrichtung → Assistent.
- **Abgleich:** `abgleich_mitte_art = "http"` → `HttpMitte` in
  `core/abgleich_mitte.py` (dieselben vier Handgriffe). Schlüssel = der
  `konto_schluessel`, nicht `abgleich.schluessel`.
- **Sashas Entwickler-Checkout bleibt unberührt:** `~/.local/bin/zentrale`
  auf dem Laptop wird nicht angefasst; rsync bleibt dort Vorgabe, bis Sasha
  umstellt.
