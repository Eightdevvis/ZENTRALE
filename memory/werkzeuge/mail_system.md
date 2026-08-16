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
fürs KI-Tool `read_mail` (in der `klein`-Schiene `lies_mail`; read-only, kein
Netz). Review-CLI:
`python -m core.mail review` arbeitet den Stapel interaktiv ab (schreibt nur
die Keymap, keine Passphrase nötig).

### `core/mail_secrets.py` (verschlüsselter Zugangsdaten-Speicher)
Fernet-Blob `data/mail_secrets.enc`, Schlüssel via scrypt aus Passphrase
`ZENTRALE_MAIL_KEY`. **Warum so:** Mail-Passwörter = HIGH-value-Asset
(`memory/betrieb/sicherheit.md`); Anforderung war Security **+** Multi-Device. Ciphertext →
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

**Token-abgelehnt-Retry (2026-07-02):** Outlook lehnte gelegentlich ein
gecachtes, laut `expires_at` noch gültiges Access-Token ab
(`[AUTHENTICATIONFAILED]` beim `authenticate` in `_connect` → früh invalidiert /
Uhr-Skew) und der **ganze Sweep fiel um** („Ordnerzählung fehlgeschlagen", danach
loggte ein späterer Call `OAUTH → refresh_token"). Fix: `access_token_for(account,
force_refresh=True)` umgeht den Cache; `_session` fängt den `IMAP4.error` beim
Verbinden und baut **einmal** mit erzwungenem Token-Refresh eine frische
Verbindung auf (kein Endlos-Retry — scheitert auch das, propagiert der Fehler:
echtes Re-Login nötig). Tests in `tests/test_mail_pool.py` (Retry-mit-Force,
Doppel-Fehler-propagiert, `force_refresh` umgeht Cache).

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

### Verbindungs-Pool (Panel-Speed, 2026-06-30)
**Problem:** Das Mail-Panel war zäh — jede Lese-/Schreib-Op (`folder_counts`,
`folder_mails`, `mail_body`, `delete_mail`, `refile_sender`) baute eine
**frische TLS-Verbindung** auf, meldete sich per XOAUTH2 an und loggte sich
danach **wieder aus**. Bei Outlook kostet allein dieses Handshake ~1-3 s — und
das pro Kategorie-Klick, pro geöffneter Mail, pro `n`/`N`. Das OAuth-
Access-Token war zwar gecacht (1 h, `mail_oauth`), aber TLS + `AUTHENTICATE`
liefen jedes Mal neu.

**Fix:** ein **warmer Verbindungs-Pool** in `core/mail.py` (`_session(account)`
als Context-Manager). Pro Konto wird **eine** IMAP-Verbindung gehalten und
wiederverwendet; ein Lock pro Konto serialisiert den Zugriff (imaplib ist nicht
thread-safe). Vor jeder Nutzung ein billiger `NOOP`-Lebens-Check — ist die
Verbindung tot (Server-Idle-Timeout, Outlook-Drossel-EOF), fliegt sie raus und
der nächste Borrow verbindet transparent neu. `_pselect` merkt sich den zuletzt
selektierten Ordner+Modus und **überspringt redundante `SELECT`** (n/N im selben
Ordner → nur noch `FETCH`). Nur der **erste** Zugriff nach Backend-Start/Idle
zahlt noch ein Handshake; das Browsen danach ist warm.
- **Außen vor:** `poll_account` (Bulk-Schreiben, eigene Reconnect/Resume-Logik)
  und SMTP — die nutzen weiter `_connect` direkt.
- **Socket-Timeout** `MAIL_NET_TIMEOUT_S` (Default 30s) auf `_connect`, damit
  ein halb-toter gepoolter Socket nicht ewig blockiert.

**Body-Cache + Prefetch (n/N instant):** Der `mail_load_body`-Aufruf der TUI
läuft **synchron im Zeichen-Loop** — eine neue Mail (n/N) blockierte also auf
dem FETCH zum Server. Zwei Schichten dagegen:
- **Body-Cache** (`core/mail.py`, `_body_cache`, LRU, `MAIL_BODY_CACHE` Default
  128): Mail-Text ist unveränderlich → einmal holen, dann aus dem RAM. `mail_body`
  ist jetzt ein Cache-Wrapper um `_fetch_body`; **Fehler werden NICHT gecacht**.
- **Prefetch**: `GET /api/mail/body` nimmt optional `prefetch=uid,uid` (Nachbar-
  uids) und holt deren Body in einem Hintergrund-Thread in den Cache
  (`prefetch_bodies`, überspringt schon Gecachtes). Die TUI schickt die vorige/
  nächste **gleichkontige** Mail mit → beim Weiterblättern liegt der Text schon
  da, der synchrone Render-Fetch kommt ohne Netz aus.
- Tests: `tests/test_mail_pool.py` (Pool: Wiederverwendung, Reconnect,
  SELECT-Skip, Drop-bei-Bruch; Cache: Treffer, kein Fehler-Cache, Prefetch wärmt
  + überspringt — ohne Netz, Fake-IMAP).

### TUI-Mail läuft im Hintergrund-Worker (2026-07-01)
**Der eigentliche Grund für „unusable":** Pool + Cache senken nur die *Netz-
kosten pro Op*. Die TUI rief die Mail-Ops aber **synchron im Zeichnen/Tasten-
Loop** auf (`mail_open_category` ~Sekunden, `mail_load_body`, `refile_sender`
~lange bei Outlook). Solange so eine Op lief, **fror die ganze TUI ein** — auch
`esc` klemmte —, und man sah **nicht, WAS** gerade lud. „Ordner leer" war
oft ein **verschluckter Fehler** (Outlook drosselt die SEARCH direkt nach einem
STATUS-Zähl-Sweep → `NO`/leer), fälschlich als leerer Ordner angezeigt.

**Fix (`tui/zentrale_tui.py`):** EIN Mail-Worker-Thread (`_mail_worker`, Queue
`MAIL_Q`) arbeitet alle IMAP-Jobs ab; der Render/Input-Loop **liest nur** den
Zustand und **blockiert nie**. `_mail_submit(key, label, fn)` reiht Jobs ein,
**dedupt per `key`** (schnelles n/N staut keine Body-Jobs) und setzt
`MAIL["busy"]` = was gerade lädt (Header zeigt `⟳ lädt ordner… / lädt text… /
sortiere absender ein… / löscht…`). Leeres Label = stiller Job (der billige
3s-Auto-Refresh `/api/mail`, kein IMAP → kein Flackern).
- Umgestellt: `mail_open_category` (Ansicht sofort um, Ordner im Worker),
  `mail_load_body`→`mail_request_body`/`_do_body`, `mail_assign`, `mail_delete`
  (baut die Liste ohne die gelöschte uid neu, kein Refetch nötig), `mail_poll`,
  `mail_reply_send`. Body wird nur gezeigt, wenn `bodyfor == aktuelle uid` (sonst
  „lädt Text…") — kein Fremd-Body beim schnellen Blättern.
- **Echte Fehler statt „(Ordner leer)":** `_mail_fetch_folder` unterscheidet
  Fehler von leer und schreibt den Grund nach `MAIL["msg"]`; die Leer-Anzeige
  zeigt jetzt `msg or "(Ordner leer)"`. Stale-Guard: Ergebnis nur übernehmen,
  wenn `MAIL["cat"]` noch dieselbe Kategorie ist.

### Einsortieren: Batch-MOVE (2026-07-01)
`refile_sender` verschiebt **alle** Mails eines Absenders ins Ziel. Früher
verschob es Mail für Mail (ein `UID MOVE` pro Treffer, Outlook drosselt das).
`_move_uid_set(imap, uids, target)` schiebt alle Treffer in **einem** `UID MOVE
<set>` (Fallback COPY+`\Deleted`+EXPUNGE), in 200er-Blöcken gegen zu lange
Kommandozeilen. Läuft in der TUI im Hintergrund-Worker → das Panel bleibt
bedienbar. (Die frühere „nur den bisherigen Ordner durchsuchen"-Optimierung ist
2026-07-02 durch den keymap-getriebenen Abgleich ersetzt — siehe unten.)

### Keymap = Wahrheit: Reconcile + Trie-Matcher (2026-07-02)
**Der Fehler:** Die Keymap war nur eine **Vorwärts-Regel** — sie griff bloß für
Mail, die noch in der INBOX lag (der Poll scannt ausschließlich `INBOX`). Schon
einsortierte Mail (inkl. `ZENTRALE/Review`) wurde **nie wieder** gegen die Keymap
geprüft. Einen Absender zuzuordnen zog seine **vorhandene** Mail also NICHT nach.
Schlimmer: `refile_sender` las die Herkunft aus `classify()` VOR dem Umschreiben
— zeigte die Keymap (z.B. per Bulk/CLI) schon auf die neue Kategorie, war Quelle
== Ziel → **0 Moves**, die Mail blieb in Review liegen.

**Der Fix — keymap-getrieben, nicht mehr prev-folder-getrieben:**
- **`refile_sender`** durchsucht jetzt **JEDEN** sortierbaren Ordner
  (`_sortable_folders()` = INBOX + alle move-Ordner inkl. Review, **ohne**
  Papierkorb) per `SEARCH FROM <absender>` und schiebt alle Treffer ins Ziel.
  Zuweisen ⇒ alle vorhandenen Mails ziehen mit — egal, wo sie liegen. `moved_from`
  ist jetzt die **Liste** der tatsächlich angefassten Ordner.
- **`reconcile_account` / `reconcile_all`** gleichen den **ganzen** Kontostand an
  die Keymap an: pro Ordner EIN `SEARCH` + EIN gebündelter FROM-Header-FETCH,
  jede Mail über den Absender neu klassifiziert, per Zielordner **ein** Batch-MOVE.
  Unbekannte bleiben in Review, der Papierkorb ist keine Quelle (nichts zurück-
  holen), **idempotent** (zweiter Lauf = 0 Moves). DRY-RUN meldet nur, WAS es täte.
- **Trie-Matcher (`mail_rules.Matcher`):** Regeln hängen in einem Knoten-
  Wörterbuch-Baum, Schlüssel = **umgedrehte Domain-Labels** + optional Local-Part
  (`maria.kern@pearl.de` → `["de","pearl","@","maria.kern"]`). `classify` läuft den
  Pfad hinab und nimmt die **tiefste** Regel → **Longest-Match**. Damit sind
  **Domain-Regeln** möglich: `pearl.de` deckt ALLE `@pearl.de` (+ Subdomains) ab
  (eine Zuweisung, viele Adressen), eine Adress-Regel `boss@pearl.de` schlägt sie
  für genau die Adresse. Das Umdrehen macht Domains zu Präfixen mit sauberer
  Label-Grenze → `pearl.de` matcht **nicht** `pearl.de.evil.com`. Gecacht
  (`matcher()`, baut nur bei Keymap-Änderung neu) → `classify` kostet im Reconcile
  über tausende Mails keinen Datei-Zugriff.
- **Trigger, non-blocking:** `POST /api/mail/reconcile` startet den Abgleich im
  **Backend-Hintergrund-Thread** (kehrt sofort zurück, key-gegatet, Parallel-Lock);
  in der TUI Taste **`x`** = »abgleich«, über den Mail-Worker → die GUI friert nie.
  CLI: `venv/bin/python -m core.mail reconcile` (DRY-RUN; `MAIL_DRY_RUN=0 …` LIVE).
- Assign verwirft jetzt den **ganzen** Ordner-Cache (der Move kann aus mehreren
  Ordnern gezogen haben). Tests: `tests/test_mail_pool.py` (Trie: Domain/Subdomain,
  Adresse schlägt Domain, kein Label-Leak, stale→Review; refile: alle Ordner außer
  Ziel, Domain-Absender; reconcile: Fehl-Ablage→Ziel, idempotent, Dry-Run),
  `tests/test_backend_api.py` (assign leert Cache).

### Eingang-Tray: INBOX + `\Seen`, einsortieren erst beim Lesen (2026-07-03)
Sashas Modell: neue Mail soll **sichtbar liegen bleiben**, bis er sie liest —
erst dann einsortieren. Kein neues read/unread-System und **kein neuer Ordner**:
- **Der Tray IST die INBOX** (das „INBOX-als-Arbeitsschlange"-Modell), das
  Gelesen-Flag ist der **native IMAP-`\Seen`** (jeder Client setzt es beim Öffnen).
- **Poll gated auf `\Seen`:** `_handle_uid(..., seen)` sortiert eine INBOX-Mail
  nur noch dann in ihre Kategorie, wenn sie **gelesen UND der Absender bekannt**
  ist. Ungelesenes/Unbekanntes bleibt im Eingang; der nächste Poll prüft erneut
  (selbstheilend). `poll_account` holt die Gelesen-Menge per `SEARCH SEEN`.
  (Vorher: bekannte Mail wurde sofort bei Ankunft weggeräumt.)
- **`mark_seen_and_file(uid)` = abhaken:** setzt `\Seen` und sortiert bekannte
  Absender sofort ein (trash-Kategorien → Papierkorb); unbekannt → nur gelesen,
  bleibt im Eingang bis zur Zuordnung. `inbox_tray()` liefert die INBOX mit
  Gelesen-Flag + vermuteter Kategorie; `inbox_body()` liest den Volltext read-only
  (BODY.PEEK → hakt NICHT versehentlich ab).
- **Reconcile lässt die INBOX in Ruhe** (`folder == "INBOX": continue`): der
  Eingang gehört dem Poll + Abhaken, nicht dem „alles-ausrichten"-Hammer `x` —
  sonst würde ein Abgleich die ungelesene neue Mail vorzeitig rausräumen.
- **Routen:** `GET /api/mail/inbox` (Tray), `GET /api/mail/inbox-body`,
  `POST /api/mail/read {uid}` (abhaken, key-gegatet, leert danach den Ordner-Cache).
- **TUI:** Taste **`e`** öffnet den Eingang (ungelesene INBOX; `●`=ungelesen,
  `○`=gelesen, das vermutete Ziel `→ …` steht an der **Adresszeile**, nicht am
  Betreff — sonst schnitt ein langer Betreff das Ziel ab), **`f`** = abhaken
  (gelesen + einsortieren), **`s`** ordnet unbekannte Absender zu, **`a`** =
  **direkt aus dem Eingang antworten** (s.u.). `d` (löschen) ist im Eingang
  weiter gesperrt (erst einsortieren, dann löschen). Alles über den Mail-Worker
  → non-blocking.
- **Nebenwirkung, gewollt:** unbekannte neue Mail wandert NICHT mehr automatisch
  in `ZENTRALE/Review` — sie bleibt im Eingang (INBOX). Der Review-Ordner ist
  damit weitgehend Legacy; die Triage passiert im Eingang. Siehe
  [[mail-keymap-source-of-truth]] (Reconcile/Trie) und „Ordner ist Status".
- Tests: `tests/test_mail_pool.py` (Poll filet nur seen+known; unbekannt bleibt
  auch gelesen; abhaken bekannt/unbekannt; Tray parst `\Seen`+Kategorie; Reconcile
  lässt INBOX in Ruhe).

### Direkt aus dem Eingang antworten + Auto-Einsortieren (2026-07-12)
Sashas Modell: die Mail zuerst abzuhaken/einzusortieren, **bevor** man antworten
darf, war Quatsch — man will aus dem Eingang **direkt antworten**. Beim Antworten
sortiert sie sich **von selbst** ein.
- **`a` im Eingang entsperrt:** öffnet den normalen Split-Antwort-Editor (links
  Original aus der INBOX via `inbox_body`, rechts der Text). Kein „erst abhaken".
- **Auto-Einsortieren nach dem Senden:** `reply_to_mail`/`draft_reply` erkennen
  den **Eingang-Sentinel** `EINGANG = "__eingang__"` (deckungsgleich mit dem
  TUI-`MAIL_EINGANG`) und rufen nach erfolgreichem Senden/Entwurf
  `mark_seen_and_file(uid)` → die Original-Mail wird gelesen markiert und in ihre
  Kategorie einsortiert (bekannter Absender) bzw. bleibt gelesen im Eingang
  (unbekannt). Ergebnis trägt dann `filed`. **Auch der Entwurf** (`e`) sortiert
  ein — man hat die Mail ja bearbeitet.
- **Warum es vorher scheiterte:** `_fetch_body` löste `cat` über
  `category_action` zu einem Ordner auf; für `__eingang__` gab es keinen →
  `reply_to_mail` fand das Original nicht. Jetzt: `cat == EINGANG` ⇒ Ordner
  `INBOX`.
- **TUI:** `_do_reply`/`_do_reply_draft` melden „gesendet + einsortiert → <kat>"
  bzw. „Absender unbekannt, bleibt im Eingang" und nehmen die Mail per
  `_eingang_drop(uid)` sofort aus der Ansicht (Liste + Cache + Body, Zahlen
  frisch). Best-effort: schlägt das Einsortieren fehl, ist die Antwort trotzdem
  raus.
- Tests: `tests/test_mail_pool.py` (`_fetch_body` Eingang→INBOX; Reply/Draft aus
  Eingang ruft `mark_seen_and_file` + trägt `filed`; Reply aus Kategorie rührt es
  NICHT an).

### Abgelehnter Login → Konto aussetzen (kein Panel-Spam) (2026-07-12)
Ein Konto mit falschem Passwort / totem Token (z.B. posteo) lehnte **jeden**
Login ab, und weil `_session` das pro Counts-Sweep / Ordner-Abruf erneut
versuchte, spammte „Login abgelehnt" laufend das Internet-Panel.
- **Quarantäne (`_suspended`, `_suspend_account`, `_is_suspended`):** nach der
  **ersten endgültigen** Ablehnung (auch der eine Token-Refresh-Retry scheiterte)
  wird das Konto ausgesetzt — **einmal** geloggt (mit Konto-Name + Fix-Hinweis),
  dann für eine Abkühlphase (`MAIL_SUSPEND_COOLDOWN_S`, Default 3600s)
  übersprungen. Danach ein stiller neuer Versuch (self-healing).
- **`_accounts_for` filtert ausgesetzte Konten** → weder die Panel-Ops
  (`_session`) noch der Poll (`poll_all` läuft jetzt über `_accounts_for()`)
  rennen weiter dagegen. `poll_account` setzt bei `imaplib.IMAP4.error` (Login
  abgelehnt, kein `.abort`) ebenfalls aus.
- Tests: `tests/test_mail_pool.py` (Aussetzen nach dauerhafter Auth-Ablehnung →
  `_accounts_for` leer, genau 1× geloggt; Abkühlphase abgelaufen → wieder frei).

### Zähl-Cache: TTL + Persistenz (2026-07-01)
`POST /api/mail/refresh-counts` sweept STATUS über **alle** Kategorie-Ordner —
das belegt die (eine) gepoolte Verbindung und lässt einen gleichzeitigen
Ordner-Aufruf warten. Zwei Bausteine:
- **TTL** (`MAIL_COUNTS_TTL_S`, Default 90s): innerhalb der Frist werden Zahlen
  aus dem Cache bedient statt neu zu sweepen; `?force=1` umgeht die TTL (die TUI
  erzwingt es nach Umsortieren/Löschen, weil die Zahlen sich dann geändert haben).
- **Persistenz** (`data/mail_counts.json`): der `_mail_live`-Cache lag nur im
  RAM des Backends → nach jedem Neustart zeigte das Panel erst den mageren
  lokalen Schnappschuss (nur letzte ~200 Mails, z.B. „171") und musste die echten
  Zahlen (1000+) neu ersweepen. Jetzt wird der frische Stand nach jedem Sweep auf
  Disk geschrieben und beim Start geladen → die letzten ECHTEN Zahlen stehen
  sofort da, die TTL frischt danach einmal im Hintergrund auf. **Kein „171→1000"-
  Flackern, kein Neu-Zählen bei jedem Start.**
- **Merge-Schutz beim Speichern (2026-07-02):** die 171 kam trotz Persistenz
  wieder, weil ein **gedrosselter/abgebrochener** Sweep eine leere/lückenhafte
  Zählung liefert (ein Ordner, den Outlook throttlet, fehlt einfach) und die
  guten Zahlen früher **blind überschrieb**. Jetzt in `_run`: leeres Ergebnis
  (Totalausfall) überschreibt **gar nichts**; sonst wird frisch **über** alt
  gemergt (ein Ordner, der diesmal nicht antwortete, behält seinen letzten
  echten Wert), begrenzt auf aktuell gültige Kategorien (gelöschte spuken nicht).
  Ein echtes 0 (STATUS meldet MESSAGES 0) ist im Ergebnis präsent und
  überschreibt normal — nur ein *Fehler* lässt den alten Wert stehen.
Tests dazu in `tests/test_backend_api.py` (TTL-Cache, force, Persist-Roundtrip,
Empty-Sweep-behält-alt, Partial-Merge+Prune).

**Die EIGENTLICHE Ursache der wiederkehrenden „171" (2026-07-02, bewiesen):**
Persistenz + Merge-Guard reichten NICHT, weil `mail_counts.json` (und
`mail_folders.json`) über `zentrale-sync` zwischen Laptop und PC synchronisiert
wurden — **newest-wins**. Der PC hat **keinen Mail-Key** → sein `folder_counts()`
liefert `{}` → er persistierte einen LEEREN Cache. War dessen mtime neuer (PC
zuletzt geschrieben), überschrieb der **Boot-Pull** (`zentrale-sync-boot`) die
guten Laptop-Zahlen `1286` mit `{}`. Backend lud `{}` → Panel „171" → der Panel-
Sweep zählte neu. Intermittierend, je nachdem welcher Knoten zuletzt schrieb —
genau das „mal 171, mal ok". Deterministisch reproduziert (PC-Datei neuer
getouched → `>f.st...... data/mail_counts.json` im Dry-Run-Pull).
**Fix:** diese vom Postfach abgeleiteten Pro-Knoten-Dateien werden **nicht mehr
synchronisiert** — Ausschluss `(^|/)mail_(counts|folders|state)\.json$` in der
`list_cmd`-Blockliste von `~/.local/bin/zentrale-sync` (auf BEIDEN Knoten
deployt). Neben `mail_counts`/`mail_folders` ist auch **`mail_state.json`** (der
Klassifikations-Verlauf) raus — gleicher Fall, nur der Laptop mit Key füllt es.
Jeder Knoten hält seinen eigenen Stand; nur der Knoten mit Key hat echte Daten.
Verifiziert: mit neueren PC-Leerdateien taucht keine davon im Dry-Run-Pull auf,
Laptop behält 1286 / 200 items. **News bleibt im Sync** (trägt Nutzer-Status
`gesehen_von_sasha`, von beiden Knoten befüllbar, rsync nur Delta). Siehe
[[mail-caches-not-synced]].

### Ordner-Inhalts-Cache: instantes (Wieder-)Öffnen (2026-07-02)
`GET /api/mail/folder?cat=…` machte bei JEDEM Öffnen einen vollen IMAP
SELECT+SEARCH+FETCH → das spürbare „lädt ordner…" auch beim zigsten Mal. Jetzt
cacht das Backend die Header-Liste je Kategorie (`_mail_folders`, persistiert in
`data/mail_folders.json`):
- **Serviert sofort aus dem Cache** (kein IMAP-Warten). Nur der allererste Aufruf
  je Kategorie (kalter Cache) holt synchron; danach kommt die Liste instant.
- **Abgelaufen (`MAIL_FOLDER_TTL_S`, Default 120s) → Hintergrund-Refresh:** die
  Antwort trägt trotzdem sofort den (leicht alten) Cache, `refreshing:true` sagt
  „ziehe frisch nach". Die TUI holt dann nach ~2s still nach → die frische Liste
  schwenkt ein, ohne Warten.
- **Persistenz:** auch das erste Öffnen NACH Neustart ist instant (aus der Datei),
  danach ein Hintergrund-Refresh.
- **`?force=1`** umgeht den Cache und holt synchron frisch — die TUI nutzt das
  nach dem Umsortieren, damit die verschobenen Mails wirklich rausfallen.
- **Cache-Kohärenz bei Mutationen:** `assign` verwirft Herkunfts- **und**
  Ziel-Ordner-Cache (`refile_sender` liefert dafür `moved_from`); `delete` nimmt
  die uid sofort aus dem Cache; ein **Poll** leert den ganzen Ordner-Cache
  (er hat Mails umgeräumt).
- **TUI-seitig** hält das Panel zusätzlich `MAIL["fcache"]` (zuletzt geholte Liste
  je Kategorie) → Reopen zeigt ohne Flackern sofort den alten Stand, während der
  Worker still auffrischt.

Tests in `tests/test_backend_api.py` (kalt→dann-Cache, force-bypass, assign-dropt-
beide, delete-entfernt-uid).

### SORT nur mit CAPABILITY — sonst kappt Outlook die Verbindung (2026-07-07)
**Bug:** Ordner (arbeit antworten & Co.) öffneten sich, luden, kamen dann **leer**
(»Ordner leer«) bzw. der Body meldete **`TimeoutError`** — intermittierend, etwa
bei jedem 2.–3. Öffnen, während der Zähler (298) stimmte. Ursache: das seit
`f4c12a0` (»chronologisch sortieren«) eingeführte `_folder_uids_by_date` schickte
**blind `UID SORT (REVERSE DATE)`** (sogar 2×, UTF-8 + US-ASCII) vor jedem
Ordner-Öffnen. **Outlook/Exchange kann kein SORT** (nicht in CAPABILITY) und
quittiert mit **`BAD`**. Ein `BAD` ist NICHT gratis: nach ~3 gesammelten BADs auf
der **gepoolten** Verbindung **kappt Outlook die TLS-Verbindung** — die
unmittelbar folgende `SEARCH`/`FETCH` läuft in einen `abort` (»Connection
closed«), Ordner leer / Body-Timeout. Der Zähler stimmte, weil `STATUS` kein
abgelehntes Kommando ist. Betraf **alle** move-Ordner (nicht nur einen), nur
phasenverschoben je nach BAD-Zähler.
**Fix (`_folder_uids_by_date`):** `UID SORT` nur senden, wenn der Server es in
`imap.capabilities` bewirbt. Outlook → direkt `SEARCH UID 1:*` (kein BAD, keine
gekappte Verbindung); die Datums-Sortierung macht `folder_mails`/`inbox_tray`
ohnehin clientseitig nach dem Header-FETCH. Servern mit SORT (Dovecot/posteo)
bleibt die serverseitige Datums-Ordnung erhalten (relevant bei >200 Mails).
Gleiche Disziplin wie beim **MOVE** (»Outlook kann kein MOVE« → immer COPY-Pfad):
**erst CAPABILITY prüfen, nicht auf try/except-Fallback verlassen** — ein
abgelehntes Kommando kostet bei Outlook die Verbindung. Tests in
`tests/test_mail_pool.py` (SORT nur mit Capability; ohne → nur SEARCH, kein
BAD-Sturm).

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
| `MAIL_NET_TIMEOUT_S`| `30`  | Socket-Timeout je Verbindung (gepoolte tote Sockets blockieren nicht ewig) |
| `MAIL_BODY_CACHE`   | `128` | Max. Mail-Texte im RAM-Body-Cache (LRU; Text ist unveränderlich) |
| `MAIL_COUNTS_TTL_S` | `90`  | Live-Zähl-Cache-Alter, bis `refresh-counts` neu sweept (`?force=1` umgeht es) |
| `MAIL_FOLDER_TTL_S` | `120` | Ordner-Inhalts-Cache-Alter, ab dem `/api/mail/folder` im Hintergrund frisch nachzieht (`?force=1` umgeht es) |
| `MAIL_SUSPEND_COOLDOWN_S` | `3600` | Abkühlphase, für die ein Konto nach endgültig abgelehntem Login ausgesetzt (übersprungen) wird, bevor es still neu versucht wird |

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
      Zeilen). **Navigation (2026-07-02 umgestellt):** `←`/`→` = **vorige/nächste
      Mail** im Stapel; `↓` = aus der Vorschau **ausklappen**, im ausgeklappten
      Text **runterscrollen**; `↑` = **hochscrollen**, ganz oben nochmal `↑` klappt
      wieder ein. (`↑↓` scrollen also den Text, nicht mehr den Stapel — das machen
      jetzt `←→`; `e` ist kein Ausklappen mehr.) `Bild↑↓` scrollt seitenweise.
    - **Liste:** Blöckchen (Absender + Titel), `↑↓` wählen, `enter`/`→` öffnet im
      Lesen-Modus, `←` zurück.
    - Aktions-Tasten in beiden Modi: `s` = **einsortieren** (öffnet Kategorie-
      Picker; ordnet den **ABSENDER** der Kategorie zu UND verschiebt **alle**
      seine vorhandenen Mails — alt + neu — in den Ziel-Ordner; künftige sortiert
      der Poll automatisch dorthin), `d` = **löschen** (eine Mail in den
      Papierkorb, umkehrbar, mit `j/n`-Nachfrage), `a` = **antworten** (Split-
      Editor), `esc` zurück zu den Kategorien.
  - **Antwort-Editor (`a`):** die MITTE wird breit (Seitenpanels schrumpfen, bis
    der Editor zu ist), gesplittet in zwei Kästen — **links** die Original-Mail
    (scrollbar mit ↑↓), **rechts** dein Text-Editor (tippen, `enter`=Zeile).
    `esc` öffnet die Verlassen-Leiste: `j` senden · **`e` als Entwurf** · `n`
    verwerfen · `w` weiter. Senden geht **echt** raus via Outlook-SMTP (XOAUTH2);
    `e` legt die Antwort als **echten Entwurf** in den Drafts-Ordner (IMAP APPEND,
    `\Draft`) — nichts geht raus, in Outlook/Handy weiterschreibbar.
    To/Betreff/Threading leitet das Backend in beiden Fällen aus dem Original ab
    (`Re:`, In-Reply-To/References).
  - `r` = Live-Poll anstoßen, **`z` = Ordnerzahlen jetzt neu zählen** (manueller
    Refresh, umgeht die TTL), `p` = Panel zu. Auto-Refresh ~3s (nur Anzeige).
  - **Alle IMAP-Ops laufen im Hintergrund-Worker** (s.o.) — die TUI friert nie
    ein, `esc` greift sofort, der Header zeigt per `⟳ …`, was gerade lädt.
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
  Hintergrund-Thread auf (STATUS-Sweep). `409` ohne Key, Parallel-Lock.
  **TTL-gegatet** (`MAIL_COUNTS_TTL_S`, Default 90s): frische Zahlen kommen aus
  dem Cache (`{cached:true}`), `?force=1` erzwingt den Sweep. Die TUI feuert es
  beim Panel-Öffnen und (mit `force`) nach Umsortieren/Löschen.
- `GET /api/mail/folder?cat=NAME` → die Mails einer Kategorie. Mit Key + eigenem
  Ordner LIVE (`source:"live"`), sonst Schnappschuss (`source:"snapshot"`).
- `GET /api/mail/body?cat=&uid=&account=&prefetch=` → voller Text + Header EINER
  Mail (Lesen-Modus), LIVE; `409` ohne Key. Core: `mail_body()` (Cache-Wrapper
  um `_fetch_body`, MIME→Klartext, text/plain bevorzugt, sonst html grob
  entschärft). `prefetch` = Komma-Liste von Nachbar-uids → werden im Hintergrund
  in den Body-Cache geholt (`prefetch_bodies`), damit n/N im Panel instant ist.
- `POST /api/mail/assign {sender, category}` → ordnet den **Absender** der
  Kategorie zu (Keymap) UND verschiebt mit Key **alle** seine vorhandenen Mails
  (INBOX + jeder move-Ordner, via `SEARCH FROM`) in den Ziel-Ordner. Antwort
  `{assigned, category, moved, live}`. Ohne Key: nur Keymap (`moved=0`). Core:
  `refile_sender()`.
- `POST /api/mail/delete {cat, uid, account?}` → eine Mail in den Papierkorb
  (umkehrbar), LIVE; `409` ohne Key. Core: `delete_mail()`.
- `POST /api/mail/reply {cat, uid, text, account?, draft?}` → **Senden** via
  **SMTP XOAUTH2** (Outlook `smtp.office365.com:587` STARTTLS) ODER, mit
  `draft:true`, als **Entwurf** in den Drafts-Ordner (**IMAP APPEND** `\Draft`,
  Ordner per Special-Use `\Drafts` gefunden, sonst `Drafts`). To/Betreff/
  Threading aus dem Original (gemeinsamer Nachrichten-Bau `_compose_message`).
  `409` ohne Key. Core: `reply_to_mail()`→`send_reply()` bzw. `draft_reply()`→
  `save_draft()`. **`cat == "__eingang__"`** (Antwort aus dem Eingang): Original
  wird aus der INBOX geholt und nach Erfolg **auto-einsortiert**
  (`mark_seen_and_file`, Ergebnis-Feld `filed`) — siehe „Direkt aus dem Eingang
  antworten".

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
