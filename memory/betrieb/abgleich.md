# Abgleich über die Mitte

**Stand 2026-10-08.** Sasha: *„der sync zum pc war immer iwie etwas cursed,
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
- **Später: der PC als Server** (HTTP). Dieselben vier Handgriffe als Routen.
  Umstellen über die Einstellungen `abgleich_mitte_art` (`git` | `http`) und
  `abgleich_mitte` (Adresse). Der Rest des Abgleichs ändert sich nicht.

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
inhalt.enc                  verschlüsselt: welche Datei wie heißt, ihr Prüfwert, Grabsteine
d/<name>.enc                jede Datei einzeln verschlüsselt (schreiben nur die Rechner)
knoten/<knoten>/<name>.enc  Eingang eines fremden Knotens, z. B. des Handys
```

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
(in den sicheren Speicher der App). Schlüssel wechseln ist bewusst nicht
gebaut (alles neu verschlüsseln) — braucht es erst, wenn er einmal draußen
war. ⚠ Das Handy trägt Schlüssel und GitHub-Token mit sich: geht es
verloren, den Token bei GitHub sperren und den Schlüssel als „draußen"
behandeln.

## Was abgeglichen wird

**Dieselbe Positivliste wie die Datensicherung** (eine Stelle:
`core/abgleich_auswahl.py`), ohne den Kalender. Nur was dort steht, verlässt
den Rechner. Nie dabei: `ai_config.json` (Keys), `mail_secrets*`,
Zwischenspeicher (Mail-Zähler, News), Sandbox, `_beiseite/`.

**Kalender: bleibt bei seinem eigenen Weg.** Jeder Rechner gleicht seinen
Kalender selbst mit Google ab (vdirsyncer, seit 07.10.2026,
[../werkzeuge/kalender_ics_bauplan.md](../werkzeuge/kalender_ics_bauplan.md)).
Liefe `data/kalender/` zusätzlich über die Mitte, gäbe es zwei Wege für
dieselben Termine — genau die Doppelten und Geister, die der Kalender schon
einmal hatte. Draußen also: `data/kalender/**`, `ai_calendar.json`, Verlauf
und Snapshots (die sind ohnehin pro Rechner). **Drin bleibt
`kalender_neben.json`** (Reisezeiten, Puffer, Ebenen): Google kennt sie nicht,
ohne Mitte hätte jeder Rechner seine eigenen.

**Was mit der Umstellung NICHT mehr mitwandert** (rsync nahm es mit):
`ai_config.json` — die Keys trägt Sasha auf jedem Rechner selbst ein;
`mail_secrets.enc`; der Konzept-Graph `ai_graph*.json` (seit 18.08. aus,
groß, wäre eine Zeile in der Liste); Takt-Merkzettel und Caches (pro Rechner,
werden neu erzeugt).

## Zusammenführen — was für welche Datei gilt

Inventar über `data/` (08.10.2026) und die Regel je Art:

| Art | Dateien | Regel |
|---|---|---|
| **Pro Rechner** | `gespraeche/<id>/<rechner>.jsonl`, `gespraeche/_knoten/<rechner>.json`, `ablage/<id>/v<n>-<rechner>.*`, `rueckmeldungen/<rechner>.jsonl` | Schreibt nur ein Rechner — kann nicht kollidieren. Läuft durch dieselbe Regel, sie greift nie. Dateien des Handys (`handy.jsonl` …) kommen aus seinem Eingang und gelten unverändert (unten). |
| **Abgeleitet** | `mobil/kontext.json` (Kontextpaket fürs Handy) | Die frische Fassung von hier gilt, ohne Hinweis. |
| **Nur anhängen** (`.jsonl`) | `ai_transcripts/*.jsonl` (beide Rechner hängen an) | Zeilen: was in der Mitte steht, plus was hier dazukam, minus was hier gelöscht wurde. Reihenfolge: Mitte zuerst. |
| **JSON mit Einträgen** | `lists.json`, `features.json`, `notes.json`, `graphs.json`, `g_*.json`, `melodies.json`, `sleep_quality.json`, `mail_rules.json`, `kalender_neben.json`, `gespraeche/*/kopf.json`, `ablage/*/kopf.json`, Tutor-Stände, `desk/*.canvas` (seit 2026-10-09: JSON Canvas, `nodes`/`edges` nach `id`) | Eintrag für Eintrag, Feld für Feld (unten). |
| **Zähler-JSON** | `ai_usage.json` (Kostenbuch) | Wie JSON, aber haben beide eine Zahl verändert, werden beide Zuwächse addiert — sonst verschluckt der eine Rechner die Kosten des anderen. |
| **Text** | `gedaechtnis/**/*.md`, Skills, Ablage-Fassungen `.md` | Zeilen-Zusammenführen über die Basis (Drei-Wege). |
| **Sonstiges** (Bilder, PDFs, kaputtes JSON) | Anhänge in der Ablage | Als Ganzes. |

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
- **Alle 5 Minuten:** `deploy/zentrale-abgleich.timer` (systemd-Benutzer-
  Timer wie beim Kalender). Sasha schaltet ihn ein.
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

Sasha, 08.10.2026: **das Handy wird ein eigener Knoten an der Mitte** (eigene
App in Dart/Flutter). Es liest und schreibt die Mitte selbst (GitHub-API mit
einem eng begrenzten Token, nur dieses Repo), ruft das Sprachmodell selbst
auf und schreibt **nur eigene Dateien**.

Ein fremder Knoten ist anders gebaut als ein Rechner: er **führt nie
zusammen und schreibt nie ins Inhaltsverzeichnis.** Sonst stritten Handy und
Rechner um `inhalt.enc`. Stattdessen legt er seine Dateien in seinen
**Eingang** `knoten/<knoten>/`. Die Rechner lesen jeden Eingang bei jedem
Abgleich und übernehmen daraus:

| Datei im Eingang | Was der Rechner tut |
|---|---|
| **eigene Datei** des Knotens: `data/gespraeche/<id>/<knoten>.jsonl`, `data/gespraeche/_knoten/<knoten>.json`, `data/rueckmeldungen/<knoten>.jsonl` | gilt so, wie sie ist; auf jeden Rechner geschrieben, **nie überschrieben**, nie ins Inhaltsverzeichnis. Eine örtliche Änderung daran wird beim nächsten Abgleich zurückgesetzt. Konfliktfrei durch Bauart: nur dieser Knoten schreibt sie. |
| `data/gespraeche/<id>/kopf.json` (neues Gespräch) | **Vorschlag**: gilt nur, solange die Mitte für dieses Gespräch noch keinen Kopf hat. Dann übernimmt ihn der erste Rechner ins Inhaltsverzeichnis; ab da gilt der dort (Umbenennen usw. machen die Rechner). |
| alles andere, falscher Name, unlesbar | übergangen, mit Hinweis |

**Abweichung vom Vorschlag „Pfad-Spiegel" (Klartext-Pfade):** die Pfade
bleiben auch für das Handy versteckt (`<name>` = HMAC des Pfads, unten).
Klartext-Pfade verrieten auf GitHub Gesprächszeiten, Rechnernamen und die
Namen der Dossiers (Personen). Das Handy kann den Namen genauso leicht
berechnen; zum Aufzählen liest es das Inhaltsverzeichnis.

### Format für fremde Knoten

Alles, was ein Client braucht, ohne Python-Code zu lesen. Prüfstein:
`tests/test_abgleich_handy.py` baut einen Knoten nur nach diesem Abschnitt.

**Die Mitte:** git-Repo `Eightdevvis/data`, Zweig **`abgleich`**. Über die
GitHub-API: Dateien lesen mit der Contents- oder Trees-API, schreiben mit
`PUT /repos/Eightdevvis/data/contents/<pfad>` (`branch: abgleich`, Inhalt
base64, bei vorhandener Datei deren `sha`). Gibt es den Zweig noch nicht,
hat noch kein Rechner abgeglichen — warten.

**Der Schlüssel:** eine Zeile aus 44 ASCII-Zeichen (Base64url **mit**
`=`-Auffüllung) = 32 Bytes. Bytes 0–15 = Signierschlüssel, Bytes 16–31 =
Verschlüsselungsschlüssel (Fernet-Standard). Auf dem Handy im sicheren
Speicher der App, eingegeben aus KeePass.

**Verschlüsseln (Fernet, Version 0x80):** Eine `.enc`-Datei enthält genau
ein Token als ASCII-Text (Base64url mit Auffüllung, kein Zeilenumbruch):

```
token = base64url( 0x80 ‖ zeit ‖ iv ‖ chiffrat ‖ hmac )
  zeit    8 Bytes, Sekunden seit 1970 (UTC), Big-Endian
  iv      16 zufällige Bytes
  chiffrat AES-128-CBC(Verschlüsselungsschlüssel, iv, PKCS7(klartext))
  hmac    HMAC-SHA256(Signierschlüssel, 0x80 ‖ zeit ‖ iv ‖ chiffrat), 32 Bytes
```

Entschlüsseln: erst den HMAC prüfen (stimmt er nicht → falscher Schlüssel),
dann AES-CBC, PKCS7 entfernen. Die Zeit wird nicht geprüft.

**Versteckte Namen:**

```
namen_schluessel = SHA256( "zentrale-abgleich-namen" ‖ 0x00 ‖ <die 44 Zeichen der Schlüssel-Zeile als ASCII> )
name(pfad)       = die ersten 32 Zeichen von hex( HMAC-SHA256(namen_schluessel, pfad als UTF-8) )   (klein geschrieben)
```

`pfad` ist immer relativ zum ZENTRALE-Ordner mit `/`, z. B.
`data/gespraeche/20261008-101500-a1b2c3/handy.jsonl`.

**Das Inhaltsverzeichnis** `inhalt.enc` entschlüsselt ist UTF-8-JSON:

```json
{"format": 1,
 "dateien":   {"<pfad>": {"name": "<name(pfad)>", "sha": "<SHA256-hex des Klartexts>"}},
 "geloescht": {"<pfad>": {"sha": "…", "von": "<knoten>", "am": "<ISO-Zeit>"}}}
```

Den Inhalt einer Datei liest man aus `d/<name>.enc`; der `sha` muss zum
entschlüsselten Klartext passen. Nur lesen — ein fremder Knoten schreibt
weder `inhalt.enc` noch `d/`.

**Schreiben in den Eingang:** für jede eigene Datei genau eine Datei
`knoten/<knoten>/<name(pfad)>.enc`. Der Klartext darin ist ein Umschlag
(UTF-8-JSON), verschlüsselt wie oben:

```json
{"format": 1, "pfad": "data/gespraeche/<id>/handy.jsonl", "inhalt": "<Datei-Bytes, Standard-Base64 mit Auffüllung>"}
```

Immer die **ganze** Datei (eine `.jsonl` wächst, die Eingangsdatei wird
ersetzt). Da nur dieser Knoten in `knoten/<knoten>/` schreibt, kann ein `PUT`
nur scheitern, wenn er selbst gleichzeitig schreibt; die Rechner fassen den
Eingang nie an. Löschen gibt es nicht (Gespräche werden archiviert).

**Der Knotenname:** Rechner heißen wie ihr Hostname (`0RAMMachine`,
`pop-os`). Das Handy heißt fest **`handy`**. Ein weiterer Knoten wählt
einmal einen eigenen Namen aus `A–Z a–z 0–9 @ . -`, der weder als
`knoten/<name>/` noch als `data/gespraeche/_knoten/<name>.json` schon
vorkommt — und behält ihn für immer (er steht in Dateinamen).

**Gespräche aus Sicht des Handys** (abgeglichen mit `core/gespraeche.py`,
08.10.2026 — passt): Gesprächs-id `%Y%m%d-%H%M%S-<6 hex>` (UTC);
Ereignis-Zeilen JSON je Zeile mit `id` (uuid4-hex), `ts` (UTC, ISO mit
Mikrosekunden und `+00:00`), `knoten: "handy"`; `kopf.json` mit `titel`,
`titel_von` (`"sasha"` | `"modell"` | `"woerter"` | null), `erstellt`,
`archiviert`, `projekt`; `_knoten/handy.json` mit `aktiv`, `gelesen` {id:
ts}, `neu_projekt`. Eine Antwort (`rolle: assistant`) kann seit 09.10.
zusätzlich `erledigt` ({`zeile`, `schritte`}), `pruefung` und `offen` (Liste
von Sätzen) tragen ([../ki/ehrlichkeit_live.md](../ki/ehrlichkeit_live.md));
wer sie nicht kennt, übergeht sie. Seit 09.10. (spät) außerdem `warnungen`
(Liste von Sätzen, je mit „⚠" vorn — fertig zum Anzeigen, ÜBER der Antwort,
in Warnfarbe) und `modell_wechsel` ({`von`, `zu`, `von_anbieter`,
`zu_anbieter`, `grund`, `satz`} — `satz` ist die fertige Zeile, ebenfalls
über der Antwort). `erledigt` kann dann auch ohne `schritte` kommen, mit
`zeile` „✗ keine Änderung in diesem Zug"; `pruefung` kann `korrekturen`
(Zahl) tragen. Das Handy schreibt nichts davon. Seit 09.10. (abends) kann eine Antwort
außerdem `ablauf` tragen: eine Liste von Einträgen `{art, zeit, t, …}` (art:
`system`, `kontext`, `text`, `werkzeug`, `frage`, `pruefung` (mit `runde`),
`warnung` (`text`), `fehler`,
`gestoppt`, `antwort`, `kosten`; je Eintrag höchstens 50.000 Zeichen) —
das Ablauf-Protokoll des Zugs ([../ki/ki_system.md](../ki/ki_system.md),
„Ablauf-Protokoll"). Nur zum Nachlesen; das Handy muss es weder schreiben
noch lesen, und es geht nie an die KI. Ebenfalls seit 09.10. (abends): ein
abgebrochener Zug (Fehler, Rundengrenze, gestoppt ohne Text) steht als
Antwort mit `fehler` (Meldung als Text, höchstens 500 Zeichen) und meist
leerem `text` da, mit `werkzeuge` und `ablauf` wie sonst. Anzeigen als
„✗ abgebrochen: <fehler>"; der KI gibt `gespraeche.fehler_hinweis` ihn als
Systemhinweis „[System, nicht deine Worte: …]" weiter — schreibt das Handy
selbst Züge, legt es einen Abbruch genauso ab. Daneben liegt pro Rechner
`gespraeche/<id>/zusagen-<rechner>.json` (offene Zusagen der KI) — das Handy
schreibt sie nicht und braucht sie nicht. Hinweis: ein Kopf mit `titel_von` `"woerter"` oder null
darf ein Rechner später automatisch umbenennen (`"modell"`); `"sasha"` nie.

### Das Kontextpaket fürs Handy

Damit das Handy wie ZENTRALE spricht, legt jeder Rechner bei jedem Abgleich
`data/mobil/kontext.json` ab (`core/mobil_kontext.py`; gelesen wie jede
Datei über das Inhaltsverzeichnis):

```json
{"version": 1, "stand": "<UTC-ISO>", "anbieter": "claude", "modell": "claude-sonnet-5",
 "effort": "low", "system": "<fester System-Prompt der Cloud-Schiene als ein Text>"}
```

- `system` = der feste Teil, den die Cloud-Schiene jedem Zug voranstellt
  (Persona, Gedächtnis-Kopf, Hausregeln, Skill-Liste, Tagesübersicht) —
  **ohne Werkzeug-Beschreibungen**. Das Handy hängt selbst einen Absatz an
  (keine Werkzeuge, ehrlich sagen, was es nicht sehen kann).
- `anbieter`/`modell`/`effort` aus den Einstellungen des Rechners.
  **Nie Schlüssel** — den API-Key hat das Handy selbst.
- Neu geschrieben nur, wenn sich außer `stand` etwas ändert. Schreiben zwei
  Rechner verschiedene Fassungen, gilt ohne Hinweis die zuletzt abgeglichene
  (abgeleitete Datei, kein echter Widerspruch).

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
| `abgleich_mitte_art` | `git` | später `http` (PC als Server) |
| `abgleich_mitte` | `git@github.com:Eightdevvis/data.git` | Adresse der Mitte |
| `abgleich_dir` | `~/.local/share/zentrale/abgleich` | Basis, Klon, Hinweise, Beiseite |
| `abgleich_schluessel` | `~/.config/zentrale/abgleich.schluessel` | wo der Schlüssel liegt |

## Wo im Code

| Datei | Was |
|---|---|
| `core/abgleich_auswahl.py` | die Positivliste (auch für die Datensicherung) |
| `core/abgleich_schluessel.py` | Schlüssel anlegen, laden, ver-/entschlüsseln, versteckte Namen |
| `core/abgleich_zusammenfuehren.py` | die Regeln oben: JSON, Zeilen, Text, Ganzes |
| `core/abgleich_mitte.py` | die vier Handgriffe, Umsetzung git |
| `core/abgleich.py` | ein Abgleich von vorn bis hinten: Basis, Eingang fremder Knoten, Vorhaben, Hinweise, Zustand |
| `core/mobil_kontext.py` | Kontextpaket fürs Handy (Schicht 3) |
| `scripts/abgleich.py` | der Befehl |
| `ui/routen/abgleich.py` | `GET /api/abgleich` |
| `deploy/zentrale-abgleich.{service,timer}` | alle 5 Minuten |
| `tests/test_abgleich*.py` | zwei gespielte Rechner gegen eine Wegwerf-Mitte |
