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
LIESMICH.md        fester Erklärtext, kein Inhalt
inhalt.enc         verschlüsselt: welche Datei wie heißt, ihr Prüfwert, Grabsteine
d/<name>.enc       jede Datei einzeln verschlüsselt
```

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

Neuer Rechner = Schritt 5. Schlüssel wechseln ist bewusst nicht gebaut (alles
neu verschlüsseln) — braucht es erst, wenn er einmal draußen war.

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
| **Pro Rechner** | `gespraeche/<id>/<rechner>.jsonl`, `gespraeche/_knoten/<rechner>.json`, `ablage/<id>/v<n>-<rechner>.*`, `rueckmeldungen/<rechner>.jsonl` | Schreibt nur ein Rechner — kann nicht kollidieren. Läuft durch dieselbe Regel, sie greift nie. |
| **Nur anhängen** (`.jsonl`) | `ai_transcripts/*.jsonl` (beide Rechner hängen an) | Zeilen: was in der Mitte steht, plus was hier dazukam, minus was hier gelöscht wurde. Reihenfolge: Mitte zuerst. |
| **JSON mit Einträgen** | `lists.json`, `features.json`, `notes.json`, `graphs.json`, `g_*.json`, `melodies.json`, `sleep_quality.json`, `mail_rules.json`, `kalender_neben.json`, `gespraeche/*/kopf.json`, `ablage/*/kopf.json`, Tutor-Stände | Eintrag für Eintrag, Feld für Feld (unten). |
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
| `core/abgleich.py` | ein Abgleich von vorn bis hinten: Basis, Vorhaben, Hinweise, Zustand |
| `scripts/abgleich.py` | der Befehl |
| `ui/routen/abgleich.py` | `GET /api/abgleich` |
| `deploy/zentrale-abgleich.{service,timer}` | alle 5 Minuten |
| `tests/test_abgleich*.py` | zwei gespielte Rechner gegen eine Wegwerf-Mitte |
