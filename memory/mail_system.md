# Mail-System – Triage per Sender-Keymap (read + sortieren)

Pollt mehrere IMAP-Postfächer (Proton via Bridge, Outlook, Gmail),
klassifiziert jede neue Mail über eine **Absender→Kategorie-Keymap** und
führt die Kategorie-Aktion **am echten Server** aus (verschieben / Papierkorb).
Kern-Module: `core/mail.py`, `core/mail_rules.py`, `core/mail_secrets.py`,
`core/mail_oauth.py`. Eingeführt 2026-06-10. **Stand: Fundament + Rule-Engine
+ Outlook-OAuth (Device-Code) gebaut und ohne Netz verifiziert; noch nicht
gegen echte Postfächer live.**

## Idee (Sashas Modell)

Eine Mail ist ein Brief, ein Absender eine bekannte/unbekannte Hand:

- **Absender BEKANNT** → die ihm einmal zugewiesene Kategorie + deren Aktion.
- **Absender UNBEKANNT** → `sasha muss gucken` (Review-Stapel). Wird **nie**
  automatisch gelöscht; sobald Sasha zuordnet, ist er bekannt.

Kategorien sind **dynamisch** (einfach anlegen, was reinkommt). Start-Set:
`löschen`, `blocken`, `freizeit antworten`, `sasha muss gucken`, `zahlen`,
`arbeit antworten`.

## Provider-Reihenfolge: Outlook zuerst (2026-06-11 umentschieden)

Ursprünglich Proton zuerst; Sasha hat auf **Outlook zuerst** gedreht (Proton/
Gmail danach). Technisch ist alles Standard-IMAP, nur die Auth unterscheidet
sich (Config, kein Sondercode):

| Provider | Host:Port | Auth | Voraussetzung |
|----------|-----------|------|---------------|
| proton   | 127.0.0.1:1143 (STARTTLS, self-signed) | Bridge-Passwort | **Proton Bridge** läuft lokal (bezahlter Plan) |
| outlook  | outlook.office365.com:993 (SSL) | **OAuth2/XOAUTH2** | Login via Thunderbird-Client-ID (kein Azure nötig) |
| gmail    | imap.gmail.com:993 (SSL) | **App-Passwort** | 2FA aktiv |

Proton hat **kein natives IMAP** — die **Bridge** ist ein lokaler Daemon, der
localhost-IMAP bereitstellt und pro Gerät ein eigenes IMAP-Passwort erzeugt.
Ohne laufende Bridge kann Proton nicht angebunden werden.

## Module

### `core/mail_rules.py` (reine Triage-Logik, kein Netz)
Die Keymap + Kategorien in `data/mail_rules.json`. Unit-testbar ohne Postfach.
- `classify(from_addr) -> (kategorie, bekannt?)` — Kernfunktion.
- `assign(addr, kategorie)` — schreibt die Keymap (legt Kategorie dynamisch an).
- `ensure_category`, `category_action`, `normalize` (parseaddr + lowercase),
  `forget`, `keymap`.
- System-Kategorie `REVIEW = "sasha muss gucken"` existiert immer, nicht löschbar.

### `core/mail.py` (IMAP-Maschinerie)
Provider-agnostischer Poller. `PROVIDERS`-Vorlagen, `_connect` (SSL/STARTTLS,
`verify=False` für Bridge-localhost, XOAUTH2 für Outlook), `poll_account`,
`poll_all`, `start_fetcher` (Daemon-Thread). Store `data/mail_state.json`
(`last_poll` pro Konto + letzte klassifizierte Mails, Cap 200; **kein**
UID-Watermark mehr — die INBOX selbst ist die Arbeitsschlange).
Lese-/Auswert-Helfer: `recent()`, `counts()` (Kategorie→Anzahl),
`review_stack()` (unbekannte Absender) und `lies(modus)` — die Textfassung
fürs KI-Tool `lies_mail` (read-only, kein Netz). Review-CLI:
`python -m core.mail review` arbeitet den Stapel interaktiv ab (schreibt nur
die Keymap, keine Passphrase nötig).

### `core/mail_secrets.py` (verschlüsselter Zugangsdaten-Speicher)
Fernet-Blob `data/mail_secrets.enc`, Schlüssel via scrypt aus Passphrase
`ZENTRALE_MAIL_KEY`. **Warum so:** Mail-Passwörter = HIGH-value-Asset
(`sicherheit.md`); Anforderung war Security **+** Multi-Device. Ciphertext →
gefahrlos über Syncthing/scp auf alle Geräte sync-bar, eine Passphrase pro
Gerät entsperrt alles. **Kein OS-Keyring**, weil der PC-Backend als systemd
ohne Login-Session läuft (Keyring gesperrt). Graceful: fehlt Lib/Passphrase/
Datei → `load_accounts()` liefert `[]`, Mail bleibt einfach aus (kein Crash).
CLI: `venv/bin/python -m core.mail_secrets {add|list|remove}`.

### `core/mail_oauth.py` (Outlook-OAuth2, XOAUTH2)
Outlook.com (privat) lässt IMAP nur noch über OAuth2 zu. Im Betrieb tauscht
`access_token_for(account)` den `refresh_token` (verschlüsselt in
`mail_secrets`) gegen kurzlebige Access-Tokens (In-Memory-Cache, Token nie
auf Platte). Zwei **einmalige Login-Wege**, beide enden im selben
`refresh_token` — der Refresh-Pfad ist danach identisch:

- **Weg A – Thunderbird-Client-ID (Default, kein Azure):** Microsoft hat
  App-Erstellung ohne eigenes Verzeichnis abgeschafft, und ein Gratis-Entra-
  Tenant will eine Kreditkarte. Darum leihen wir Mozilla **Thunderbirds
  öffentliche Client-ID** (`9e5f94bc-…`, von MS für Privatkonten freigegeben,
  wie OfflineIMAP/mutt). Diese App spricht den **Auth-Code-Flow** mit PKCE
  (S256): Browser-Login → Code aus der Adressleiste zurückkopieren; Redirect
  ist der `nativeclient`-Endpunkt, **kein localhost-Server**. Authority
  `/common`. Kostet nichts, läuft nicht ab.
- **Weg B – eigene Azure-App (Device-Code):** nur mit eigenem Verzeichnis
  sinnvoll (z.B. 30-Tage-Trial-Tenant, läuft aber ab). Headless: `/devicecode`
  → user_code, dann `/token` pollen. Authority `/consumers`.

Verifiziert gegen Microsoft Learn (2026-06): Scope
`offline_access https://outlook.office.com/IMAP.AccessAsUser.All`, IMAP-Host
`outlook.office365.com:993`, SASL XOAUTH2. Calls gehen an
`login.microsoftonline.com` (echtes Internet, nicht über `net.py`) → eigenes
`push_internet_log`, **nie Tokens geloggt**. Login-CLI (fragt den Weg ab):
`python -m core.mail_oauth login`.

### Warum kein eigenes Azure (2026-06-11 entschieden)
Microsoft: „Apps außerhalb eines Verzeichnisses zu erstellen ist veraltet."
Ein privates `hotmail.com`-Konto hat kein Verzeichnis; ein Gratis-Entra-
Verzeichnis verlangt eine Kreditkarte zur Verifikation (wird nicht belastet),
das M365-Dev-Programm kostet. Kartenlos bleibt nur ein 30-Tage-Trial-Tenant
(läuft ab). **Karte soll draußen bleiben → Default = Thunderbird-Client-ID
(Weg A)**, die das Verzeichnis-Problem komplett umgeht.

## Safe-by-default (Write-back fasst echte Mails an!)

- **DRY-RUN ist default AN** (`MAIL_DRY_RUN`, Default `"1"`): klassifiziert +
  loggt, was es *täte*, fasst aber nichts an. Im Dry-Run wird nichts verschoben,
  die INBOX bleibt also unangetastet (nächster Lauf sieht dieselben Mails).
- Aktionen sind **umkehrbar**: `move` (in Ordner) / `trash` (Papierkorb via
  special-use `\Trash`). **Kein** Hard-Expunge über das Move hinaus.
- **Unbekannte Absender** → Review, nie destruktiv.
- Move via `UID MOVE` (RFC 6851), Fallback `COPY + \Deleted + EXPUNGE`.
  **Outlook/Exchange kann KEIN MOVE** (nicht in CAPABILITY) → immer der
  COPY-Pfad. Kategorie-Ordner werden bei Bedarf unter `MAIL_FOLDER_PREFIX`
  (Default `ZENTRALE`) angelegt.
- **LIST-Parsing** (`_list_name`, Regex): Format `(flags) "sep" name` — der Name
  ist gequotet *oder* ein Atom ohne Leerzeichen. Naives `split('"')[-2]` erwischte
  bei ungequoteten Namen den **Separator** `"/"` → `_find_trash` lieferte `"/"` →
  `COPY <uid> "/"` → `BAD Command Argument Error`. Jetzt sauber per Regex; kein
  \Trash gefunden → Fallback `Deleted Items` (Exchange-Default).

### Diagnose-Werkzeuge
- `python core/mail.py --probe` — verbindet, SELECT INBOX, probiert mehrere
  SEARCH-Formen durch und zeigt die rohe Server-Antwort (read-only).
- `MAIL_IMAP_DEBUG=1 …` — schaltet `imap.debug=4` ein (IMAP-Protokoll-Mitschnitt
  auf stderr). Wird **erst nach** der Authentifizierung gesetzt, damit das
  XOAUTH2-Token nie mitgeloggt wird.

### Verbindungs-Härtung (Outlook-Drossel)
Outlook drosselt Bulk-MOVE hart und **kappt dann die TLS-Verbindung** (EOF →
`imaplib.IMAP4.abort`). Drei Gegenmaßnahmen in `poll_account`:
1. **Ordner-Cache** (`_FolderCache`): Zielordner werden **einmal** aufgelöst
   statt pro Mail — vorher kostete jede Mail ein volles `LIST`, was den
   Befehls-Sturm erst auslöste.
2. **Drossel-Pause** `MAIL_ACTION_DELAY_S` (Default 0.4s) nach jeder Aktion.
3. **Reconnect + Resume**: bricht die Verbindung ab, wird mit Backoff neu
   verbunden und weitergemacht. Gefahrlos, weil verschobene Mails die INBOX
   verlassen — ein erneutes `SEARCH` sammelt sie nicht wieder ein.

**INBOX-als-Arbeitsschlange (kein Watermark):** `poll_account` sucht jeden Lauf
mit `SEARCH UID 1:*` *alles*, was aktuell in der INBOX liegt. Sortierte Mails
(move/trash) verlassen die INBOX und verschwinden damit aus der Schlange;
abgelehnte/offene Mails bleiben liegen und werden beim nächsten Poll automatisch
erneut versucht. Selbstheilend — kein UID-Hochwasserstand, der tieferliegende
(z.B. abgelehnte) UIDs überspringt. Grund für den Wechsel: ein Watermark `UID
N:*` ließ Outlook bei `N` > höchster UID `BAD Command Argument Error` werfen und
verwaiste abgelehnte Mails unterhalb der Marke. (`1:*` ist immer gültig, weil 1
nie über der höchsten UID liegt.)

## Trigger + Transparenz

`start_fetcher` (aus `main.py`, **kassetten-unabhängig**) ist hart gegated über
`ZENTRALE_MAIL=on` — **default AUS**, damit nichts ungewollt IMAP kontaktiert.
Intervall `MAIL_INTERVAL_MIN` (Default 10). IMAP läuft **nicht** durch
`net.py` (das ist HTTP) → jeder Lauf loggt explizit via
`state.push_internet_log` ins orangene Internet-Panel (wie SearXNG-localhost
im News-System).

## Env-Variablen

| Var | Default | Wirkung |
|-----|---------|---------|
| `ZENTRALE_MAIL`     | (aus) | `on` → Fetcher startet |
| `ZENTRALE_MAIL_KEY` | –     | Master-Passphrase, entsperrt die Konten |
| `MAIL_DRY_RUN`      | `1`   | `0` → sortiert wirklich am Server |
| `MAIL_INTERVAL_MIN` | `10`  | Poll-Intervall |
| `MAIL_START_DELAY_S`| `30`  | Verzögerung des ersten Laufs |
| `MAIL_FOLDER_PREFIX`| `ZENTRALE` | Prefix der angelegten Kategorie-Ordner |
| `MAIL_ACTION_DELAY_S`| `0.4` | Pause nach jeder Server-Aktion (Outlook-Drossel-Schutz; `0` = aus) |
| `MAIL_MAX_RECONNECT`| `5`   | Reconnect-Versuche, wenn der Server die Verbindung kappt |

## Selftest

- `venv/bin/python core/mail.py` (oder `-m core.mail`) — Rule-Engine-Demo
  (kein Netz): schickt synthetische Absender durch die Keymap, listet
  Kategorien. Nutzt eine **temporäre Keymap** (Wegwerf-Datei), fasst die
  echte `data/mail_rules.json` also NICHT an.
- `venv/bin/python -m core.mail review` — Review-Stapel interaktiv abarbeiten
  (unbekannte Absender → Kategorie). Pro Absender: Nummer ODER **neuer
  Kategoriename** (wird sofort angelegt; Suffix ` trash` → Papierkorb-
  Kategorie). Schreibt nur die Keymap, kein Netz/keine Passphrase.
- **Kategorie-Verwaltung auf Vorrat** (kein Netz, nur Keymap):
  - `… -m core.mail cats` — alle Kategorien + Aktion + Absenderzahl.
  - `… -m core.mail addcat "Reise Zeug"` — neue Kategorie (Default `move` in
    `ZENTRALE/Reise Zeug`); `… addcat "Werbung" trash` → Papierkorb-Kategorie.
  - `… -m core.mail delcat "Reise Zeug"` — Kategorie löschen; ihre Absender
    werden wieder **unbekannt** (Review-Stapel), nie destruktiv. System-
    Kategorie `sasha muss gucken` ist nicht löschbar.
- `venv/bin/python core/mail.py --poll` — echter **Dry-Run**-Poll aller Konten
  (braucht Passphrase + Konten). `MAIL_DRY_RUN=0 … --poll` = LIVE.

## Status / offen (nächste Bausteine)

- **Gebaut + getestet (ohne Netz):** Rule-Engine, Secrets-Schicht
  (`cryptography`), IMAP-Poller + safe Write-back, Dry-Run, Fetcher-Gating,
  `main.py`-Einbindung, **Outlook-OAuth2** (Thunderbird-Auth-Code **und**
  eigener Device-Code, refresh_token-Rotation), **KI-Tool `lies_mail`**
  (read-only, in `ai.py` verdrahtet + System-Prompt-Regel 9), **Review-CLI**
  `-m core.mail review`. **Noch nicht** gegen echte Postfächer live.
- **Outlook (Login erledigt 2026-06-11):** via Thunderbird-Client-ID
  eingeloggt, refresh_token verschlüsselt gespeichert. Offen: erster echter
  `--poll` Dry-Run gegen die INBOX → bei Zufriedenheit `MAIL_DRY_RUN=0`.
- **Proton (danach):** Bridge installieren (bezahlter Plan) → `mail_secrets
  add` (provider=proton, Bridge-User + Bridge-Passwort) → Dry-Run.
- **Gmail (danach):** App-Passwort → läuft sofort mit dem bestehenden Code.
- **UI (gebaut 2026-06-15):** TUI-Panel **Post/Mail** (Taste `p`), **Drill-down
  in zwei Ebenen**:
  - **Ebene 1 (cats):** beim Öffnen NUR die Kategorien zum Auswählen — der
    Review-Stapel ist einfach die Kategorie `sasha muss gucken` wie jede andere
    (nichts wird einem ins Gesicht geklatscht). `↑↓` wählen, `enter` rein.
  - **Ebene 2 (mails):** zwei umschaltbare Anzeige-Modi (`v`/Tab):
    - **Lesen** (Default): EINE Mail — Von / Betreff / Text-Vorschau (erste
      Zeilen), `e` klappt zum vollen Text auf (scrollbar), `n`/`N` blättert.
    - **Liste:** Blöckchen (Absender + Titel), `↑↓` wählen, `enter` öffnet im
      Lesen-Modus.
    - Aktions-Tasten in beiden Modi: `s` = **einsortieren** (öffnet Kategorie-
      Picker; ordnet den **ABSENDER** neu zu, NICHT die einzelne Mail —
      künftige Mails von ihm landen dann dort), `d` = **löschen** (in den
      Papierkorb, umkehrbar, mit `j/n`-Nachfrage), `a` = **antworten** (Split-
      Editor), `esc`/`←` zurück.
  - **Antwort-Editor (`a`):** die MITTE wird breit (Seitenpanels schrumpfen, bis
    der Editor zu ist), gesplittet in zwei Kästen — **links** die Original-Mail
    (scrollbar mit ↑↓), **rechts** dein Text-Editor (tippen, `enter`=Zeile).
    `esc` öffnet die Senden-Leiste: `j` senden · `n` verwerfen · `w` weiter.
    Senden geht **echt** raus via Outlook-SMTP (XOAUTH2), To/Betreff/Threading
    leitet das Backend aus dem Original ab (`Re:`, In-Reply-To/References).
  - `r` = Live-Poll anstoßen, `p` = Panel zu. Auto-Refresh ~3s.
  - **Hybrid-Datenquelle:** Zähler in Ebene 1 kommen LIVE aus den echten IMAP-
    Ordnern (`STATUS`-Sweep, im Backend gecacht), Fallback = lokaler 200er-
    Schnappschuss (`mail_state.json`). Klick auf eine Kategorie holt deren Mails
    LIVE aus dem echten Ordner (gebündelter Header-FETCH) — bei trash-Kategorien
    oder ohne Key der Schnappschuss. Header zeigt `[live]`/`[lokal]`. Begründung:
    folgt „Ordner ist Status" (das volle Postfach, nicht nur die letzten 200).
  - Core-Helfer: `category_overview()` (Ebene 1, lokal), `folder_counts()`
    (LIVE STATUS je move-Ordner), `folder_mails(cat)` (LIVE Header eines
    Ordners; trash→`in_category()`-Schnappschuss).

### Dashboard-Routen (`ui/app.py`)
- `GET /api/mail` → `{categories, recent, live_counts, counts_age_s,
  counts_refreshing, can_poll, polling}` — read-only, key-frei. `categories` =
  lokale Schnappschuss-Zähler, `live_counts` = echte Ordnergröße aus dem Cache.
- `POST /api/mail/refresh-counts` → frischt den Live-Ordnerzähl-Cache im
  Hintergrund-Thread auf (STATUS-Sweep). `409` ohne Key, Parallel-Lock. Die TUI
  feuert das beim Panel-Öffnen (fire-and-forget) — friert nicht ein.
- `GET /api/mail/folder?cat=NAME` → die Mails einer Kategorie. Mit Key + eigenem
  Ordner LIVE (`source:"live"`), sonst Schnappschuss (`source:"snapshot"`).
- `GET /api/mail/body?cat=&uid=&account=` → voller Text + Header EINER Mail
  (Lesen-Modus), LIVE; `409` ohne Key. Core: `mail_body()` (MIME→Klartext,
  text/plain bevorzugt, sonst html grob entschärft).
- `POST /api/mail/assign {sender, category}` → ordnet den **Absender** einer
  Kategorie zu (Keymap, key-frei). Verschiebt NICHT die Mail. Core:
  `reassign_sender()` → `mail_rules.assign()`.
- `POST /api/mail/delete {cat, uid, account?}` → eine Mail in den Papierkorb
  (umkehrbar), LIVE; `409` ohne Key. Core: `delete_mail()`.
- `POST /api/mail/reply {cat, uid, text, account?}` → sendet eine Antwort via
  **SMTP XOAUTH2** (Outlook `smtp.office365.com:587` STARTTLS). To/Betreff/
  Threading aus dem Original. `409` ohne Key. Core: `reply_to_mail()` →
  `send_reply()`.

### Senden (SMTP) + erneuter Login
Versand braucht den Scope `SMTP.Send` (in `mail_oauth.SCOPE`, zusammen mit IMAP —
**ein** Token deckt beides, da beide unter `outlook.office.com`). Wer den alten
**nur-IMAP**-refresh_token hat, muss **EINMAL neu einloggen** (Re-Consent):
`ZENTRALE_MAIL_KEY=… venv/bin/python -m core.mail_oauth login`. Erst danach
funktioniert `a` → senden. **Noch nicht live verifiziert** (braucht den
Re-Login + echtes Netz) — der XOAUTH2-SMTP-Pfad folgt dem Standard-Schema.
- `POST /api/mail/poll` → stößt einen **Live**-Poll im Backend-Thread an
  (explizite Nutzer-Aktion = Einwilligung; Move/Trash umkehrbar). `409`, wenn
  keine Passphrase. Parallel-Polls werden via Lock verhindert.

### Passphrase-Quellen (Env + OS-Keyring)
`mail_secrets._passphrase()`: **erst** `ZENTRALE_MAIL_KEY` (headless/systemd),
**dann** OS-Keyring (Secret Service via `secretstorage`, nur interaktive
Desktop-Session). So bleibt der headless-Pfad heil und der Desktop muss nicht
tippen. Verwaltung (Passphrase tippt der Nutzer per `getpass`, nie geloggt):
- `… -m core.mail_secrets keyring-set` — Passphrase in den Login-Keyring legen
  (mit Gegenprobe gegen den vorhandenen Store).
- `… keyring-test` / `keyring-clear` — prüfen / entfernen.
Deps: `secretstorage` + `jeepney` (pure-Python, im venv). Fehlen sie (headless),
greift einfach weiter nur die Env-Var.
