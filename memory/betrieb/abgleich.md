# Abgleich über die Mitte

**Stand 2026-10-08, ergänzt 2026-10-29.** Sasha: *„der sync zum pc war immer iwie etwas cursed,
weil sich die sachen gegenseitig verwirrt haben. besser wenn jetzt gegen eine
cloud, einen server einfach geprüft wird. die idee war ja schon git als cloud
zu nutzen und dann später wenn der pc mit netzwerk ready ist, die cloud mit
ihm auszutauschen."*

Drei Wörter, die hier immer dasselbe heißen:

- **Rechner** — Laptop (`0RAMMachine`) oder PC (`pop-os`). Später auch mehr.
- **Mitte** — der eine Ort, gegen den jeder Rechner abgleicht. Heute das
  private GitHub-Repo `Eightdevvis/data` (Zweig `abgleich`), später der PC
  als Server.
- **fremder Knoten** — ein Gerät, das die Mitte selbst liest, aber nur
  eigene Dateien schreibt (das Handy, unten). Rechner führen zusammen,
  fremde Knoten nicht.
- **abgleichen** — den eigenen Stand mit der Mitte zusammenführen: holen,
  zusammenführen, das Ergebnis zurück in die Mitte und auf den Rechner.

## Warum der alte Weg verwirrt hat

Bis heute schiebt `rsync` die Dateien direkt zwischen Laptop und PC hin und
her („neueste Datei gewinnt", nur hinzufügen,
[../system/topologie.md](../system/topologie.md)). Das hat drei Fehler, die
sich nicht wegflicken lassen:

1. **Ganze Datei statt Eintrag.** Hakt der Laptop in `lists.json` etwas ab
   und legt der PC in derselben Datei etwas an, gewinnt die neuere Datei —
   die andere Änderung ist weg.
2. **Gelöschtes kommt zurück.** rsync löscht nie. Was ein Rechner löscht,
   bringt der andere beim nächsten Mal wieder.
3. **Die Uhr entscheidet.** „Neuer" heißt: die Uhr des Rechners sagt es.

## Das Modell: ein Stern

```
   Laptop ──┐                ┌── PC
            ├──▶  M I T T E ◀─┤
   (später  ┘   (verschlüsselt)└── weitere)
```

Kein Rechner redet mehr mit dem anderen. Jeder gleicht nur mit der Mitte ab.
Die Mitte hält **einen** Stand plus seine ganze Geschichte (git).

**Das Herzstück: jeder Rechner merkt sich, worauf er sich zuletzt mit der
Mitte geeinigt hat** (die *Basis*, eine Kopie unter
`~/.local/share/zentrale/abgleich/basis/`). Mit der Basis sieht man bei jeder
Datei, *wer* was geändert hat — ohne auf eine Uhr zu schauen:

| Basis → hier | Basis → Mitte | Ergebnis |
|---|---|---|
| gleich | geändert | Mitte übernehmen |
| geändert | gleich | eigene Fassung in die Mitte |
| geändert | geändert | **zusammenführen** (Regeln unten) |
| gelöscht | gleich | in der Mitte löschen (Grabstein) |
| gleich | gelöscht | hier beiseitelegen (nicht wegwerfen) |
| gelöscht | geändert | **Änderung gewinnt** gegen Löschen + Hinweis |

Damit ist „Gelöschtes kommt zurück" erledigt, und die Uhr spielt nur noch an
einer Stelle mit (Zeitstempel-Felder, unten).

## Grundsatz: die Cloud wird nie überschrieben

Sasha, 28.10.2026, für ALLE Daten in der Cloud: *„Was in der Cloud ist, darf
nie einfach so überschrieben werden. Die Cloud synct immer automatisch. Wenn
jemand lokal eine neue Version erstellt und erst danach die Cloud verbindet,
muss er selbst prüfen, welche Version er will.“* Zusammenführen ohne
Widerspruch ist gut, aber nicht vorrangig.

- **Erstes Verbinden** (keine Basis, `erstabgleich`): die Mitte gilt Datei für
  Datei; eine abweichende Fassung von hier liegt unter `konflikte/<zeit>/`
  mit Hinweis — nie still weg. Was es nur hier gibt, kommt dazu.
- **Fremde Knoten** (Handy) schreiben nie ins Inhaltsverzeichnis. Ein
  Gesprächskopf gilt nur, wo es noch keinen gibt; ein Termin darf geändert
  oder gelöscht werden, aber nur auf der Fassung, die das Handy gesehen hat
  (`basis_sha`) — ein Widerspruch wird abgelehnt, beide Fassungen bleiben, mit
  Hinweis und Quittung ([abgleich_fremde_knoten.md](abgleich_fremde_knoten.md)
  „Termine vom Handy“). Das erste Anmelden am Handy ersetzt nichts in der Cloud.
- **App neu dabei** (seit 29.10.2026, vorher offen): wird eine App auf einem
  Gerät (wieder) angewählt — oder darf sie erst jetzt abgleichen (Quelle der
  Kalender-App wird `zencloud`) —, laufen ihre Dateien wie im `erstabgleich`: die
  Mitte gilt, eine abweichende Fassung von hier liegt unter
  `konflikte/<zeit>/` (Hinweis „App neu dabei“), Gelöschtes kommt nicht
  zurück, was es nur hier gibt, kommt dazu. Vorher lief es über die alte
  Basis — eine .ics mit späterem LAST-MODIFIED konnte die der Mitte ersetzen.
  Merkzettel je Gerät: `<abgleich_dir>/apps_dabei.json` (die Muster des
  letzten erfolgreichen Abgleichs; fehlt er, gilt nichts als neu). Pflicht-Apps
  (Adapter, z. B. Zugangsdaten ab der Anmeldung) zählen nie als neu.

## Die Mitte ist austauschbar

Der Abgleich kennt die Mitte nur über vier Handgriffe (`core/abgleich_mitte.py`):

| Handgriff | Was |
|---|---|
| `holen()` | den aktuellen Stand der Mitte (Kennung + Dateien) |
| `vorbereiten(dateien, weg, basis_stand)` | den neuen Stand bauen, Kennung zurück |
| `senden(kennung)` | in die Mitte stellen — **nur wenn** die Mitte noch auf dem Stand ist, von dem man ausging. Sonst „jemand war schneller": neu holen, neu zusammenführen |
| `enthaelt(kennung)` | ist dieser Stand in der Mitte angekommen? (für das Weitermachen nach einem Absturz) |

- **Heute: git.** Ein eigener Klon unter
  `~/.local/share/zentrale/abgleich/mitte/`, Zweig `abgleich`. „Nur wenn noch
  derselbe Stand" erledigt git von selbst: ein normaler Push wird abgelehnt,
  wenn die Mitte weitergelaufen ist. **Nie `--force`.**
- **Seit 2026-10-22: die ZENTRALE-Cloud** (`HttpMitte`, Art `http`,
  [../hub/knoten_beitritt.md](../hub/knoten_beitritt.md) „Bauplan v1").
  Umstellen über `abgleich_mitte_art` = `http` (macht `zentrale setup`).
  Der Rest des Abgleichs ändert sich nicht — unten „Die Mitte als Cloud".
  Der git-Weg verhält sich wie vorher.

### Die Mitte als Cloud (`HttpMitte`)

| Handgriff | Route |
|---|---|
| `holen()` | `GET /v1/mitte` → `{kennung|null, namen}`; die Dateien erst beim Lesen, je `GET /v1/mitte/datei/<name>` |
| `vorbereiten(...)` | nur im Speicher; gibt eine **vorläufige** Kennung zurück: `vorlaeufig-` + Prüfwert des neuen `inhalt.enc` |
| `senden(kennung)` | sha256 je Datei → `POST /v1/mitte/fehlende {sha256: [...]}` → `{fehlen}`; nur die fehlenden als `PUT /v1/mitte/blob/<sha256>` (rohe Bytes, je höchstens 24 MiB); dann `POST /v1/mitte/stand {basis, verweise: {name: sha256}, loeschen}` → `{kennung}`; **409** = jemand war schneller → `False`; **400 `blob_fehlt`** → einmal nachladen, nochmal |
| `enthaelt(kennung)` | `GET /v1/mitte/enthaelt/<kennung>`; eine vorläufige Kennung (Absturz nach dem Senden) erkennt sie daran, dass genau dieses `inhalt.enc` in der Mitte liegt — Fernet würfelt, also stammt es dann von uns |

- **Schlüssel:** bei `http` der `konto_schluessel` aus `~/.config/zentrale/konto.json`
  (`abgleich.schluessel_laden()`), nicht `abgleich.schluessel`. Dasselbe
  Fernet-Format, dieselben versteckten Namen. Abgemeldet → klarer Fehler,
  nichts gesendet.
- **Echte Kennung:** erst der Server vergibt sie. Nach dem Senden trägt der
  Abgleich sie ins Vorhaben ein (`_vorhaben_kennung`), die Basis merkt sich den
  Stand des Servers.
- **Mitten im Lesen weitergelaufen:** die Dateien kommen einzeln und immer aus
  dem aktuellen Stand. Fehlt eine, die das Inhaltsverzeichnis nennt, prüft
  `HttpMitte` den Kopf; hat er sich bewegt → `MitteBewegt`, der Abgleich holt
  neu. Gemischt Gelesenes scheitert beim Senden am 409 und wird ebenso neu
  geholt.
- Prüfstein: `tests/test_abgleich_http.py` (zwei gespielte Geräte gegen
  `devkit/fake_cloud.py`).

### Apps je Gerät (seit 2026-10-23, vorher Bereiche)

Daten haben nur Apps ([../hub/cloud_app.md](../hub/cloud_app.md)). Jede sagt
in `[daten]` (app.toml; eingebaute: `core/eingebaute_apps.py`), welche
Muster ihr gehören; `core/abgleich_apps.py` schneidet sie mit der
Positivliste (nur was dort **genau so** steht, deny by default) und gibt
jedes Muster nur einer App. Eingebaut: fokus, notizen, kalender (`kalender_neben.json`, since 2026-10-29 `calendar_colours.json`; Termine nur mit
Kalender-Anschluss), graph, assistent (Gedächtnis, Gespräche, Transkripte,
Rückmeldungen, Kontextpaket, Kosten), ablage, desk, werkstatt (eigene Apps +
Schaufenster), mail (Regeln), klavier, adapter (Pflicht: immer, nie gefragt); dazu tutor (Ersatz-Eintrag, bis sein
app.toml `[daten]` hat). Test: jedes Muster der Positivliste gehört genau
einer App.

- Die Wahl steht je Gerät in `abgleich_apps` (`data/ai_config.json`, wandert
  nie): `{app: true|false}`. **Nicht gesetzt = alles** (Sashas git-Weg bleibt).
  `{}` = noch nichts entschieden. Eine App ohne Eintrag wird weder geholt noch
  gesendet, bis sie gefragt hat.
- **Alte Wahl** `abgleich_bereiche` wird beim Lesen übernommen (nicht
  gelöscht): ganz gewählt → ja, gar nicht → nein; nur zum Teil (memory ohne
  conversations → assistent) → keine Entscheidung, die App fragt einmal.
  „Alles" ergibt dieselben Muster wie vorher (Test mit zwei Geräten).
- **Fragen:** eine App mit Daten (hier oder laut `inhalt.enc` in der Cloud —
  nur das Inhaltsverzeichnis, `abgleich.cloud_pfade()`) und ohne Entscheidung
  fragt einmal bei `zentrale sync`, `zentrale setup` und beim Start von
  `zentrale` (dort nur hier nachgesehen). Ohne Terminal: eine Zeile, kein
  Abgleich dieser App.
- Abgewählt: hier **weder geholt noch gesendet**; in der Mitte bleibt sie
  unberührt. Auch die Basis wird zugeschnitten — sonst sähe sie aus wie
  „überall gelöscht". Wieder anwählen: die Mitte gilt wie bei einem neuen
  Gerät (oben „App neu dabei“).

## Verschlüsselt — was auf GitHub liegt

Auf GitHub liegen nur unlesbare Daten. Bewertet wurden drei Wege:

| Weg | Urteil |
|---|---|
| **git-crypt** | Neues Systempaket, verschlüsselt erst beim Commit über einen git-Filter — ein falsch eingerichteter Klon schiebt still Klartext hoch. Dateinamen bleiben lesbar. Nein. |
| **age / sops** pro Datei | Neues Programm auf jedem Rechner; sops verschlüsselt nur Werte, Schlüssel und Struktur der JSON bleiben lesbar. Nein. |
| **Selbst verschlüsseln vor dem Commit (Fernet)** | `cryptography` ist schon im venv (die Mail-Zugänge nutzen es). Kein neues Paket. Der Klartext erreicht den git-Klon nie. **Ja.** |

So liegt es in der Mitte:

```
LIESMICH.md                 fester Erklärtext, kein Inhalt
inhalt.enc                  verschlüsselt: welche Datei wie heißt, ihr Prüfwert, Grabsteine, Quittungen fürs Handy
d/<name>.enc                jede Datei einzeln verschlüsselt (schreiben nur die Rechner)
knoten/<knoten>/<name>.enc  Eingang eines fremden Knotens, z. B. des Handys
```

**Format and the read rule (since 2026-10-30, building kit step 5).**
`inhalt.enc` and every envelope carry `"format": 1`. A device that finds a
major it does not know never interprets or writes it (`core/formats.py`):
a newer `inhalt.enc` → the sync stops with "cloud data is newer than this
version — read only" (nothing read, nothing sent; the account key change
refuses too); a newer envelope is skipped with a note. `zentrale status`
lists every such note until an update reads the format again. Fields a newer
version added — at the top of `inhalt.enc` and per file — are written back
unchanged. Vectors: `contracts/cloud-sync/1/` (contracts/README.md); every
published release must keep syncing with HEAD (`tests/test_alte_fassung.py`).

**Warum Fernet, auch mit Blick aufs Handy (Dart):** Fernet ist ein
offengelegtes, kleines Format (AES-128-CBC + HMAC-SHA256, unten Byte für Byte).
In Dart gibt es es fertig (`package:encrypt`, Klasse `Fernet`), und notfalls
ist es mit `package:cryptography`/`pointycastle` in zwanzig Zeilen
nachgebaut — `tests/test_abgleich_handy.py` tut genau das in Python aus
Grundbausteinen. AES-GCM wäre gleich gut machbar gewesen, hätte aber eine
eigene Schlüsselableitung und eine zweite Schreibweise neben `mail_secrets`
gebracht. git-crypt/gpg gehen auf dem Handy nicht.

- **Auch die Dateinamen sind versteckt.** `<name>` ist ein Prüfwert aus
  Schlüssel und Pfad (HMAC) — `gedaechtnis/dossiers/<person>.md` verrät auf
  GitHub nicht, wer drinsteht. Sichtbar bleibt nur: wie viele Dateien, wie
  groß, wann geändert.
- **Unveränderte Dateien werden nicht neu verschlüsselt** (Fernet würfelt
  jedes Mal neu). Sonst wäre jeder Abgleich ein Commit über alle Dateien.
- **Klartext gibt es nur auf den Rechnern** (in `data/` und in der Basis),
  beide auf verschlüsselten Platten (LUKS, [sicherheit.md](sicherheit.md)).

### Der Schlüssel

Ein einziger Schlüssel, eine Zeile aus 44 Zeichen. Er liegt auf jedem Rechner
in `~/.config/zentrale/abgleich.schluessel` (nur für Sasha lesbar), **nie in
`data/`, nie in einem Repo.** Und als Sicherung in KeePass.

> ⚠ **Das einzige echte Risiko:** Ist der Schlüssel weg — auf beiden
> Rechnern UND in KeePass —, sind die Daten in der Mitte **für immer
> unlesbar.** Niemand kann sie zurückholen, auch GitHub nicht, auch Claude
> nicht. Deshalb gehört er in KeePass, bevor der erste Abgleich läuft.
> (Die Daten auf den Rechnern selbst sind davon nicht betroffen.)

**So kommt er in KeePass (einmal):**

1. Auf dem Laptop den Abgleich-Befehl mit `schluessel-anlegen` aufrufen.
   Er legt den Schlüssel an und sagt, wo er liegt.
2. Denselben Befehl mit `schluessel-zeigen-fuer-keepass` aufrufen. Er zeigt
   die eine Zeile.
3. In KeePass einen neuen Eintrag anlegen: Titel **„ZENTRALE Abgleich"**,
   Benutzername leer, die Zeile ins **Passwort**-Feld kopieren. In die
   Notizen: „Schlüssel für die Mitte (Eightdevvis/data, Zweig abgleich).
   Ohne ihn ist die Mitte unlesbar." Speichern.
4. Die Zwischenablage leeren (oder einmal etwas anderes kopieren).
5. Auf dem PC: den Befehl mit `schluessel-eingeben` aufrufen und die Zeile
   aus KeePass einfügen. Er prüft sie gegen die Mitte, bevor er sie ablegt.

Neuer Rechner = Schritt 5. Das Handy bekommt die Zeile ebenfalls aus KeePass
(in den sicheren Speicher der App). Schlüssel wechseln ist auf dem git-Weg
bewusst nicht gebaut (alles neu verschlüsseln) — braucht es erst, wenn er
einmal draußen war. **Über die Cloud (`http`) gebaut `d1dc8fd`:** `zentrale devices
remove` fragt „lost or stolen?" und bietet dann den Kontoschlüssel-Wechsel an
(`core/key_rotation.py`, Ablauf in [../hub/knoten_beitritt.md](../hub/knoten_beitritt.md)
„Kontoschlüssel wechseln"). ⚠ Das Handy trägt Schlüssel und GitHub-Token mit sich: geht es
verloren, den Token bei GitHub sperren und den Schlüssel als „draußen"
behandeln.

## Was abgeglichen wird

**Dieselbe Positivliste wie die Datensicherung** (eine Stelle:
`core/abgleich_auswahl.py`), ohne `ai_calendar.json`, dazu `NUR_ABGLEICH`
(Kontextpaket, Brücke, Zugangsdaten). Nur was dort steht, verlässt
den Rechner. Nie dabei: `ai_config.json` (Keys), `mail_secrets*`,
Zwischenspeicher (Mail-Zähler, News), Sandbox, `_beiseite/`. Seit 2026-10-10
dabei: `data/apps/**` — die selbst gebauten Apps der Werkstatt
(`app.toml` + `icon.png`, [../hub/werkstatt.md](../hub/werkstatt.md));
ihr Desk liegt ohnehin in `data/desk/`.

**Cloud folder (since 2026-10-29):** `~/Zentrale/Cloud` is `data/cloud/**`
in the sync (sync only, never the backup), app `cloud_folder`. Its files are
never merged inside (both changed → the cloud wins, the version from here
goes to `konflikte/`). **Held back** — not read, not sent, not deleted, base
untouched, one note, `held_back` in the state — is any file that does not fit
into one cloud blob (> 24 MiB encrypted ≈ 18 MiB file; applies to every
file, not only this folder), and a missing/empty cloud folder whose files
(3 or more) the cloud still has. Details: [../hub/cloud_folder.md](../hub/cloud_folder.md).

**Kalender: über die Cloud, seit 2026-10-24** ([../hub/adapter.md](../hub/adapter.md)).
Bis dahin glich jeder Rechner selbst mit Google ab, `data/kalender/**` stand
in `NICHT_ABGLEICHEN` (ein zweiter Weg brächte Doppelte und Geister). Jetzt
gehört `data/kalender/**` zur App `kalender`; ob es abgleicht, sagt die
**Quelle der Kalender-App** — `google` | `zencloud` | `lokal`
([../hub/adapter.md](../hub/adapter.md) „Die Quelle der Kalender-App“,
`core/kalender_einstellung.py`): nur bei `zencloud` (bzw. ohne Einstellung der
alte Weg mit Google-Anschluss und Brücke) läuft der Kalender über die Cloud
(`adapter.kalender_ueber_cloud`, sonst schneidet `abgleich_apps.jetzt_erlaubt`
ihn heraus). Gegen Geister und Doppelte:

- **Ein Weg je Termin:** Google ↔ Brücke ↔ Cloud ↔ alle anderen (alter Weg:
  Google fährt nur, wer den Mietvertrag hält). Dateiname bleibt (vdirsyncer
  benennt nichts um) → keine Doppelten durch Runden.
- **Erstes Mal je Gerät** = die Basis kennt noch keine Datei unter
  `data/kalender/` (`abgleich.basis_kennt`; kein Merkzettel). Dann vor dem
  Abgleich (`adapter.vor_abgleich`, beides vom Abgleich hereingegeben):
  Cloud hat schon Termine (`abgleich.mitte_hat_kalender`) → der hiesige
  `data/kalender/` wandert nach `<abgleich_dir>/kalender-vor-cloud/<zeit>/`
  (nie gelöscht, Sasha wählt), das Gerät übernimmt die Cloud; Cloud leer →
  der hiesige füllt sie; unbekannt (offline) → `MitteFehler`, kein Abgleich.
- **Wieder dabei** (die Basis kennt den Kalender schon, er war nur eine Weile
  aus — Quelle umgestellt): „App neu dabei“ (oben) — die Mitte gilt je Datei,
  Abweichendes von hier liegt unter `konflikte/`, kein Drei-Wege über die
  alte Basis.
- **.ics je Termin zusammenführen** (`core/abgleich_ics.py`, Art `ics`): je
  VEVENT (UID + RECURRENCE-ID) über die Basis; beide geändert → späterer
  LAST-MODIFIED, sonst die Mitte, mit Hinweis. Nie die Text-Regel (zwei
  Fassungen in einer Datei wären kein iCalendar mehr).
- **Nur Termine wandern:** im Kalender-Ordner nur `*.ics`, `displayname`,
  `color` — nie `.zentrale.lock` oder Zwischendateien.
- **Je Gerät bleiben:** `ai_calendar.json` (alter Speicher), Verlauf und
  Grabsteine (`kalender_verlauf/`), Snapshots — Löschen trägt der Abgleich
  selbst (Grabsteine der Mitte), die Kalender-Grabsteine waren für rsync.
- Die Löschsperre der Brücke bleibt: fehlen seit dem letzten Abgleich mehr
  als 5 Termine aus `termine/`, fährt sie nicht. Basis ist der mitreisende
  vdirsyncer-Status, die eigene Liste (reist ebenfalls mit) nur Rückfall
  ([../werkzeuge/kalender_ics_bauplan.md](../werkzeuge/kalender_ics_bauplan.md)).

**Zugangsdaten: nur im Abgleich, nie in der Sicherung.** `data/adapter/geheim.enc`
steht in `GEHEIM` ⊂ `NUR_ABGLEICH`, nie in `SICHERN` (das Sicherungs-Skript
schickt Klartext nach GitHub; Test `tests/test_adapter_geheim.py`). Sie
gleicht nur angemeldet ab — Einträge mit dem Kontoschlüssel verschlüsselt,
die Mitte verschlüsselt sie noch einmal. Regel: Art `json` (Eintrag für
Eintrag). Vertrag und vdirsyncer-Stand (`data/adapter/bruecke/**`): Art
`mitte` (beide geändert → die Mitte, ohne Hinweis).

**Was mit der Umstellung NICHT mehr mitwandert** (rsync nahm es mit):
`ai_config.json` — die KI-Schlüssel kommen seit 2026-10-24 über den Adapter;
`mail_secrets.enc`; der Konzept-Graph `ai_graph*.json` (seit 18.08. aus, seit 31.10. aus dem
Code; die Dateien liest nichts mehr); Takt-Merkzettel und Caches (pro Rechner,
werden neu erzeugt).

## Zusammenführen — was für welche Datei gilt

Inventar über `data/` (08.10.2026) und die Regel je Art:

| Art | Dateien | Regel |
|---|---|---|
| **Pro Rechner** | `gespraeche/<id>/<rechner>.jsonl`, `gespraeche/_knoten/<rechner>.json`, `ablage/<id>/v<n>-<rechner>.*`, `rueckmeldungen/<rechner>.jsonl`, `shop/besitz-<rechner>.jsonld` (Schaufenster, seit 2026-10-10: `.jsonld` liefe sonst als Text) | Schreibt nur ein Rechner — kann nicht kollidieren. Läuft durch dieselbe Regel, sie greift nie. Dateien des Handys (`handy.jsonl` …) kommen aus seinem Eingang und gelten unverändert (unten). |
| **Abgeleitet** | `mobil/kontext.json` (Kontextpaket fürs Handy) | Die frische Fassung von hier gilt, ohne Hinweis. |
| **Nur anhängen** (`.jsonl`) | `ai_transcripts/*.jsonl` (beide Rechner hängen an) | Zeilen: was in der Mitte steht, plus was hier dazukam, minus was hier gelöscht wurde. Reihenfolge: Mitte zuerst. |
| **JSON mit Einträgen** | `lists.json`, `features.json`, `notes.json`, `graphs.json`, `g_*.json`, `melodies.json`, `sleep_quality.json`, `mail_rules.json`, `kalender_neben.json`, `gespraeche/*/kopf.json`, `ablage/*/kopf.json`, Tutor-Stände, `desk/*.canvas` (seit 2026-10-09: JSON Canvas, `nodes`/`edges` nach `id`) | Eintrag für Eintrag, Feld für Feld (unten). |
| **Zähler-JSON** | `ai_usage.json` (Kostenbuch) | Wie JSON, aber haben beide eine Zahl verändert, werden beide Zuwächse addiert — sonst verschluckt der eine Rechner die Kosten des anderen. |
| **Text** | `gedaechtnis/**/*.md`, Skills, Ablage-Fassungen `.md`, `apps/*/app.toml` (selbst gebaute Apps, seit 2026-10-10: ein Schlüssel je Zeile) | Zeilen-Zusammenführen über die Basis (Drei-Wege). |
| **Course colours** (since 2026-10-29) | `calendar_colours.json` (calendar app, [../werkzeuge/calendar_colours.md](../werkzeuge/calendar_colours.md)) | Union of keys; a key both sides know keeps the cloud's slot — silently, no conflict copy, deletions ignored (`calendar_colours.merge`). Every device converges to the cloud's table. |
| **Termine** (seit 2026-10-24) | `kalender/**/*.ics` | Je VEVENT (UID + RECURRENCE-ID) über die Basis, `core/abgleich_ics.py` (oben „Kalender"). |
| **Wer zuerst kam** | `adapter/bruecke/**` (Mietvertrag, vdirsyncer-Stand) | Beide geändert → die Mitte, ohne Hinweis. |
| **Sonstiges** (Bilder, PDFs, kaputtes JSON) | Anhänge in der Ablage, Symbole `apps/*/icon.png` | Als Ganzes. |

### JSON, Eintrag für Eintrag

- **Objekte** werden Schlüssel für Schlüssel zusammengeführt.
- **Listen mit `id`** (Listen, Einträge, Notizen, Blöcke) Eintrag für Eintrag
  nach `id`. Zwei neue Einträge an verschiedenen Stellen derselben Liste →
  **beide bleiben.**
- **Gleiche Nummer für zwei verschiedene neue Einträge** (beide Rechner
  haben offline den nächsten Eintrag angelegt, beide heißen `7`): der eigene
  bekommt die nächste freie Nummer — beide bleiben. Zähler wie `next_item`
  werden danach über alle Nummern hochgezogen.
- **Listen ohne `id`** (Messwerte `g_*.json`, Reihenfolgen) als Menge:
  Mitte, plus hier Hinzugekommenes, minus hier Gelöschtes.
- **Zeitstempel-Felder** (`modified`, `last_seen` …): das spätere gewinnt,
  ohne Hinweis. Die einzige Stelle, an der eine Uhr mitredet.
- **Dasselbe Feld auf beiden Rechnern verschieden geändert** (z. B. derselbe
  Eintrag hier abgehakt, dort umbenannt — das sind zwei Felder, das geht
  gut; aber hier „Milch", dort „Hafermilch" — das ist ein Feld): **die
  Fassung aus der Mitte bleibt** (wer zuerst abgeglichen hat), die eigene
  Fassung der ganzen Datei wird unter `~/.local/share/zentrale/abgleich/konflikte/`
  aufgehoben, und es gibt einen **Hinweis**. Nie still verlieren.

### Text (Gedächtnis), Drei-Wege

Beide Fassungen werden gegen die Basis gelegt. Änderungen an verschiedenen
Stellen kommen beide hinein. Haben beide **dieselbe Stelle** verschieden
geändert, stehen **beide Fassungen untereinander in der Datei**, eingerahmt:

```
⟪ Abgleich: hier gibt es zwei Fassungen — eine behalten, den Rest löschen ⟫
⟪ Fassung von 0RAMMachine ⟫
…
⟪ Fassung aus der Mitte ⟫
…
⟪ Ende der zwei Fassungen ⟫
```

So geht nichts verloren, die KI sieht beim Lesen, dass da etwas offen ist,
und Sasha bekommt einen Hinweis.

## Löschen

- **Grabsteine** in der Mitte (im verschlüsselten Inhaltsverzeichnis): wer
  wann welche Datei gelöscht hat, mit ihrem letzten Prüfwert. Kommt dieselbe
  Datei unverändert von einem Rechner zurück, der von dem Löschen noch nichts
  weiß, bleibt sie gelöscht.
- **Auf dem Rechner wird nie weggeworfen:** eine in der Mitte gelöschte Datei
  wandert nach `~/.local/share/zentrale/abgleich/beiseite/<Datum>/`.
- Einträge *in* einer Datei verschwinden über die Basis-Regel (oben);
  Gespräche und Ablage werden ohnehin archiviert, nicht gelöscht.

## Wann abgeglichen wird

- **Bei jeder Änderung:** `datasync.notify_change` (der Haken, den Listen,
  Notizen, Gedächtnis, Gespräche usw. schon rufen) stößt den Abgleich im
  Hintergrund an — **gedrosselt**: höchstens einer alle 20 Sekunden, eine
  Änderung dazwischen wird nicht vergessen, sondern beim nächsten Fenster
  mitgenommen. Wie bisher nur mit `ZENTRALE_AUTOPUSH=1` (Start-Skripte).
- **Alle 5 Minuten:** Timer `zentrale-abgleich` → `zentrale sync --automatic`
  (seit 24.10. von `zentrale setup` / `zentrale timers install` gerendert,
  [setup.md](setup.md) „Timer"; vorher `deploy/zentrale-abgleich.timer`).
- Beide laufen nur, wenn `abgleich_weg` = `mitte` ist. Zwei Läufe
  gleichzeitig gibt es nicht (Sperre); der zweite wartet.

## Absturzsicher

- Daten werden atomar geschrieben (`core/dateien.py`).
- Vor dem Senden legt der Abgleich ein **Vorhaben** ab: das fertige Ergebnis
  und die Kennung des neuen Stands. Stürzt er nach dem Senden ab, findet der
  nächste Lauf das Vorhaben, sieht, dass die Mitte den Stand hat, und
  schreibt das Ergebnis zu Ende auf den Rechner. Stürzt er vorher ab, wird
  das Vorhaben verworfen — die Mitte hat nichts bekommen.
- **Schreibt die App während des Abgleichs an einer Datei**, wird diese
  Datei in diesem Lauf nicht überschrieben; der nächste Lauf nimmt die neue
  Fassung mit (als Basis gilt dann, was gelesen wurde).

## Übergang vom rsync-Weg

Die Einstellung `abgleich_weg` (`rsync` | `mitte`, Vorgabe `rsync`) schaltet
um. Bis Sasha umstellt, bleibt alles wie es ist. Die Umstellung ist ein
bewusster Schritt:

1. **Laptop:** Schlüssel anlegen, in KeePass (oben).
2. **Laptop:** einmal abgleichen → **Erstbefüllung**: die Mitte ist leer,
   der Laptop füllt sie.
3. **Laptop:** umstellen auf `mitte` (der Befehl `umstellen mitte` prüft,
   dass Schlüssel und Mitte da sind). Den Boot-Sync abschalten (in
   `zentrale-launch` den Abschalter für den Boot-Sync setzen,
   [../system/topologie.md](../system/topologie.md)). Timer einschalten.
4. **PC** (ist gerade aus): beim nächsten Start Schlüssel eingeben, dann
   einmal abgleichen → **Erstabgleich**: der PC hat noch keine Basis. Dann
   gilt: **die Mitte gewinnt.** Wo der PC eine abweichende Fassung hat, wird
   sie beiseitegelegt (mit Hinweis), nicht zusammengeführt — sonst brächte
   sein alter rsync-Stand genau das Gelöschte zurück, das wir loswerden
   wollen. Was es nur auf dem PC gibt, kommt dazu (außer es hat einen
   Grabstein). Dann umstellen, Boot-Sync-Unit aus `zentrale-pc.service`
   nehmen, Timer an.

Zurück geht es mit `umstellen rsync` — die Mitte bleibt dann einfach stehen.

## Und die Datensicherung?

Die Mitte **ersetzt** sie: ein Stand mit ganzer Geschichte, verschlüsselt,
alle paar Minuten statt einmal am Tag. Nach der Umstellung kann der Timer
`zentrale-sicherung.timer` aus. ⚠ Die alten Sicherungs-Zweige
`knoten/<rechner>` im selben Repo liegen **im Klartext** auf GitHub
([datensicherung.md](datensicherung.md)). Ob sie gelöscht werden, entscheidet
Sasha (das löscht Geschichte — Claude tut es nicht).

## Das Handy und andere fremde Knoten

Ein fremder Knoten (das Handy) liest die Mitte, führt nie zusammen und
schreibt nur in seinen Eingang `knoten/<knoten>/`: eigene Dateien, den Kopf
eines neuen Gesprächs, neue Termine als Vorschlag. Das ganze Format (Fernet,
versteckte Namen, Umschlag, Routen der Cloud, Kontextpaket, was die Rechner
übernehmen) steht in [abgleich_fremde_knoten.md](abgleich_fremde_knoten.md).

## Bedienen

Der Befehl `scripts/abgleich.py` (Sasha tippt ihn selbst):

| Zusatz | Was |
|---|---|
| `status` (oder nichts) | letzter Abgleich, Weg, offene Hinweise |
| `jetzt` | jetzt abgleichen |
| `--trocken` | zeigen, was ein Abgleich täte — nichts schreiben, nichts senden |
| `schluessel-anlegen` | neuen Schlüssel anlegen (weigert sich, wenn schon einer da ist) |
| `schluessel-zeigen-fuer-keepass` | die Schlüssel-Zeile zum Abschreiben |
| `schluessel-eingeben` | Schlüssel aus KeePass auf diesem Rechner ablegen |
| `umstellen mitte` / `umstellen rsync` | den Weg wechseln |

Sichtbar ist der Zustand in der TUI unter **Technik** (eine Zeile: wann
zuletzt, Hinweise) und über `GET /api/abgleich`.

## Einstellungen

| Name | Vorgabe | Was |
|---|---|---|
| `abgleich_weg` | `rsync` | `rsync` = alter Weg, `mitte` = dieser |
| `abgleich_mitte_art` | `git` | `http` = die ZENTRALE-Cloud (Adresse und Sitzung aus dem Konto) |
| `abgleich_apps` | (nicht gesetzt = alles) | `{app: true\|false}` je Gerät; `{}` = noch nichts, neue Apps fragen |
| `abgleich_bereiche` | — | alt (bis 2026-10-23), wird nur noch gelesen und in `abgleich_apps` übernommen |
| `cloud` | `core/cloud_api.py` `VORGABE` | Adresse der Cloud (Env `ZENTRALE_CLOUD`) |
| `konto_datei` | `~/.config/zentrale/konto.json` | Sitzung + Kontoschlüssel (600) |
| `abgleich_mitte` | `git@github.com:Eightdevvis/data.git` | Adresse der Mitte |
| `abgleich_dir` | `~/.local/share/zentrale/abgleich` | Basis, Klon, Hinweise, Beiseite |
| `abgleich_schluessel` | `~/.config/zentrale/abgleich.schluessel` | wo der Schlüssel liegt |

## Wo im Code

| Datei | Was |
|---|---|
| `core/abgleich_auswahl.py` | die Positivliste (auch für die Datensicherung) |
| `core/cloud_folder.py` | cloud folder: where it lives, what in it never syncs (2026-10-29) |
| `core/abgleich_schluessel.py` | Schlüssel anlegen, laden, ver-/entschlüsseln, versteckte Namen |
| `core/abgleich_zusammenfuehren.py` | die Regeln oben: JSON, Zeilen, Text, Ganzes, Wer-zuerst-kam |
| `core/abgleich_ics.py` | Termine je VEVENT (seit 2026-10-24) |
| `core/abgleich_mitte.py` | die vier Handgriffe, Umsetzung git und http (`HttpMitte`) |
| `core/abgleich_apps.py`, `core/eingebaute_apps.py` | Apps mit Daten, die Wahl je App und Gerät, Übernahme der alten Bereiche |
| `core/konto.py`, `core/konto_schluessel.py`, `core/cloud_api.py` | Konto, Schlüssel-Schema, Draht zur Cloud |
| `core/cloud_notices.py`, `core/key_rotation.py` | what the cloud said about this device (insecure release, removed) · account key change (2026-10-30) |
| `core/abgleich.py` | ein Abgleich von vorn bis hinten: Basis, Eingang fremder Knoten (Quittungen), Apps neu dabei, Vorhaben, Hinweise, Zustand |
| `core/abgleich_vorschlaege.py` | was ein fremder Knoten vorschlagen darf: Gesprächskopf, Termine (neu/ändern/löschen/Ebene, je VEVENT und Feldgruppe ohne Überschreiben) |
| `core/vevent_merge.py` | three-way merge inside one VEVENT per group of fields (time, title, note, reminders, …) — since 2026-10-29 |
| `core/mobil_kontext.py` | Kontextpaket fürs Handy (Schicht 3) |
| `scripts/abgleich.py` | der Befehl |
| `ui/routen/abgleich.py` | `GET /api/abgleich` |
| `zentrale_cli/timer.py` | Timer alle 5 Minuten (`deploy/zentrale-abgleich.*` = alter Checkout-Weg) |
| `tests/test_abgleich*.py` | zwei gespielte Rechner gegen eine Wegwerf-Mitte |
