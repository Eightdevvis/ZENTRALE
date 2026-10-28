# Abgleich: das Handy und andere fremde Knoten

**Stand 2026-10-29.** Ausgelagert aus [abgleich.md](abgleich.md) (Regel 9,
600 Zeilen). Dort steht der Abgleich der Rechner; hier, wie ein Knoten mit
der Mitte spricht, der nie zusammenführt (das Handy, [../system/zen_mobile.md](../system/zen_mobile.md)).

## Das Modell

Sasha, 08.10.2026: **das Handy wird ein eigener Knoten an der Mitte** (eigene
App in Dart/Flutter). Es liest und schreibt die Mitte selbst, ruft das
Sprachmodell selbst auf und schreibt **nur eigene Dateien** (und Vorschläge).
Seit 28.10.2026 über die ZENTRALE-Cloud mit dem Konto (einmal anmelden, unten
„Über die Cloud“); der ursprüngliche GitHub-Weg bleibt hier beschrieben, weil
das Format dasselbe ist. Die App: [../system/zen_mobile.md](../system/zen_mobile.md).

Ein fremder Knoten ist anders gebaut als ein Rechner: er **führt nie
zusammen und schreibt nie ins Inhaltsverzeichnis.** Sonst stritten Handy und
Rechner um `inhalt.enc`. Stattdessen legt er seine Dateien in seinen
**Eingang** `knoten/<knoten>/`. Die Rechner lesen jeden Eingang bei jedem
Abgleich und übernehmen daraus:

| Datei im Eingang | Was der Rechner tut |
|---|---|
| **eigene Datei** des Knotens: `data/gespraeche/<id>/<knoten>.jsonl`, `data/gespraeche/_knoten/<knoten>.json`, `data/rueckmeldungen/<knoten>.jsonl` | gilt so, wie sie ist; auf jeden Rechner geschrieben, **nie überschrieben**, nie ins Inhaltsverzeichnis. Eine örtliche Änderung daran wird beim nächsten Abgleich zurückgesetzt. Konfliktfrei durch Bauart: nur dieser Knoten schreibt sie. |
| `data/gespraeche/<id>/kopf.json` (neues Gespräch) | **Vorschlag**: gilt nur, solange die Mitte für dieses Gespräch noch keinen Kopf hat. Dann übernimmt ihn der erste Rechner ins Inhaltsverzeichnis; ab da gilt der dort (Umbenennen usw. machen die Rechner). |
| `data/kalender/<ebene>/<uid>.ics` (Termin: neu seit 28.10., ändern/löschen/Ebene seit 29.10.2026) | **Vorschlag**, unten „Termine vom Handy“: neu, geändert (je VEVENT über die Fassung, die das Handy sah), einzelnes Vorkommen aus/an, Ebene gewechselt, gelöscht (nur ausdrücklich). Ein Widerspruch wird **abgelehnt** — nichts in der Mitte überschrieben. Jeder entschiedene Vorschlag bekommt eine **Quittung** in `inhalt.enc`. Die eine Regel: `core/abgleich_vorschlaege.kalender_vorschlag_annehmen`. |
| alles andere, falscher Name, unlesbar | übergangen, mit Hinweis |

Ein Vorschlag wird nur geprüft, wenn die App auf diesem Rechner abgleicht
(`abgleich_apps`): solange `data/kalender/**` nicht über die Mitte läuft,
wartet ein Termin-Vorschlag still im Eingang. Das Handy sieht den Kalender
erst, wenn ein Rechner ihn in die Mitte gibt (Quelle der Kalender-App
`zencloud`, `abgleich_apps.jetzt_erlaubt`) — bis dahin zeigt es „noch nicht in der Mitte“.

**Abweichung vom Vorschlag „Pfad-Spiegel" (Klartext-Pfade):** die Pfade
bleiben auch für das Handy versteckt (`<name>` = HMAC des Pfads, unten).
Klartext-Pfade verrieten auf GitHub Gesprächszeiten, Rechnernamen und die
Namen der Dossiers (Personen). Das Handy kann den Namen genauso leicht
berechnen; zum Aufzählen liest es das Inhaltsverzeichnis.

### Termine vom Handy (seit 2026-10-29)

Grundsatz (Sasha, 28.10.2026): **die Cloud wird nie überschrieben.** Anders
als zwischen zwei Rechnern (`core/abgleich_ics`, späterer LAST-MODIFIED
gewinnt) gewinnt hier nie eine Uhr: das Handy sagt, **welche Fassung der
Mitte es gesehen hat**, und ein Rechner nimmt nur an, was sich darauf
zurückführen lässt. Der Umschlag bekommt dafür drei Felder dazu:

```json
{"format": 1, "pfad": "data/kalender/<ebene>/<name>.ics",
 "inhalt":    "<die ganze neue .ics, Standard-Base64>",
 "basis_sha": "<sha aus inhalt.enc der Datei, die das Handy geändert hat>",
 "basis":     "<diese Datei selbst, Standard-Base64 — empfohlen>",
 "loeschen":  true}
```

| Fall | Was das Handy schickt | Was der Rechner tut |
|---|---|---|
| **neu** | `pfad` = Ebene + UID-Name (Zeichen außer `A–Z a–z 0–9 @ . -` → `_`) + `.ics`, `inhalt` mit genau einer UID; kein `basis_sha` | annehmen, solange es Pfad und UID nirgends gibt, die Ebene da ist und kein Grabstein auf dem Pfad liegt (wie seit 28.10.) |
| **ändern** | `pfad` = der **vorhandene** Pfad (auch fremde Namen wie `abc.ics` von Google), ganze `inhalt`, `basis_sha`, besser auch `basis` | je VEVENT (UID + RECURRENCE-ID) drei Wege: nur das Handy geändert → das Handy; nur die Mitte → die Mitte; **beide verschieden → abgelehnt**. Aus der Mitte bleibt, was das Handy nicht mitschickt und ZENTRALE nicht verwaltet (`VERWALTET` in `kalender_ics_abbildung`: DESCRIPTION, VALARMs, Google-Felder, `X-ZENTRALE-*`) |
| **Vorkommen aus** | ändern: am Haupt-VEVENT `EXDATE` (gleiche Zeitform wie DTSTART) **und** das Datum in `X-ZENTRALE-AUS` | wie ändern |
| **Vorkommen an** | ändern: das `EXDATE` weg und das Datum aus `X-ZENTRALE-AUS` | wie ändern; vergisst das Handy `X-ZENTRALE-AUS`, gleicht der Rechner die Liste an EXDATE an |
| **Ebene wechseln** | `pfad` = `data/kalender/<neue Ebene>/<UID-Name>.ics`, `inhalt`, `basis_sha` (+ `basis`) der Datei am **alten** Ort; kein Löschen dazu | in EINEM Stand: neue Datei da, alte mit Grabstein weg — keine Doppelten, kein Löschen+Neu |
| **löschen** | `pfad`, `"loeschen": true`, `basis_sha`; kein `inhalt` | nur, wenn die Mitte noch genau diese Fassung hat (sha gleich) → Grabstein; sonst abgelehnt |

- **Basis:** `sha256(Mitte) == basis_sha` → die Mitte ist unverändert, das
  Handy gilt. Sonst braucht der Rechner die gesehene Fassung: aus `basis`
  (sha muss passen) oder aus seiner eigenen Basis. Hat er sie nicht → abgelehnt
  („kenne ich nicht“). Ohne `basis_sha` wird nichts Vorhandenes geändert.
  LAST-MODIFIED/SEQUENCE als Ersatz sind bewusst nicht gebaut: die Uhr des
  Handys verrät nicht, ob die Mitte inzwischen geändert wurde.
- **Gelöscht wird nie, weil etwas fehlt:** eine fehlende Eingangsdatei
  bewirkt nichts; eine .ics ohne Haupt-VEVENT (nur RECURRENCE-IDs oder leer)
  wird abgelehnt. Eine weggelassene Abweichung (RECURRENCE-ID) gilt als
  zurückgenommen — nur, wenn die Mitte sie nicht geändert hat.
- **Entfernen durch Weglassen geht nicht** für DESCRIPTION, VALARM und andere
  nicht verwaltete Felder (sie kämen aus der Mitte zurück) — eine Notiz leert
  das Handy mit `DESCRIPTION:` (leer). Pausen (`X-ZENTRALE-PAUSE`) ändert nur
  ZENTRALE.
- **Abgelehnt** heißt: die Mitte bleibt, die Fassung vom Handy bleibt im
  Eingang, bis das Handy die Quittung liest, und liegt auf dem Rechner unter
  `<abgleich_dir>/konflikte/eingang-<knoten>/<umschlag>/<pfad>`; ein Hinweis
  steht im Zustand (TUI „Technik“, `GET /api/abgleich`) — einmal, nicht bei
  jedem Abgleich.
- **Quittung** in `inhalt.enc` (vom Rechner geschrieben):

```json
"eingang": {"handy": {"<pfad>": {"umschlag": "<sha256-hex des entschlüsselten Umschlags>",
                                 "ergebnis": "angenommen" | "abgelehnt" | "erledigt",
                                 "code": "<reason code>", "grund": "…", "am": "<ISO-Zeit>"}}}
```

  `code` (English, stable; `core/abgleich_vorschlaege.REASONS`, e.g.
  `conflict`, `base_unknown`, `needs_base`, `changed_not_deleted`) is what the
  phone translates with its own ARB table; `grund` is the text in the
  computer's UI language (gettext, `core/locale`).
  Das Handy vergleicht `umschlag` mit dem sha256 seines Umschlag-Klartexts
  (die JSON-Bytes vor dem Verschlüsseln): passt er, ist der Vorschlag
  entschieden → aus dem Eingang räumen; bei `abgelehnt` Sasha den `grund`
  zeigen und die eigene Fassung behalten, bis Sasha wählt (neu auf der
  aktuellen Mitte vorschlagen oder verwerfen). Ein Umschlag mit Quittung
  wird nicht noch einmal geprüft; die Quittung fällt, sobald der Umschlag
  aus dem Eingang ist. `erledigt` = es gab nichts mehr zu tun (schon drin,
  schon gelöscht). Ein noch nicht entschiedener Umschlag darf ersetzt werden
  (gleiche `basis_sha`, ganze neue Datei).
- `X-ZENTRALE-AUS` ist `b64:` + Base64url(JSON-Liste von `"JJJJ-MM-TT"`,
  `sort_keys`), roh-JSON wird auch gelesen.
- Prüfstein: `tests/test_abgleich_handy_aendern.py` (ein Handy nur nach
  dieser Beschreibung, wie `tests/test_abgleich_handy.py`).

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
 "geloescht": {"<pfad>": {"sha": "…", "von": "<knoten>", "am": "<ISO-Zeit>"}},
 "eingang":   {"<knoten>": {"<pfad>": {"umschlag": "…", "ergebnis": "…", "grund": "…", "am": "…"}}}}
```

`eingang` (seit 2026-10-29, fehlt, solange es keine Quittung gibt): die
Quittungen für Termin-Vorschläge, unten „Termine vom Handy“.

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
Eingang nie an. Gelöscht wird nur eines: ein **Termin-Vorschlag**, sobald `inhalt.enc` eine
Quittung mit seinem `umschlag` hat (oben „Termine vom Handy“; für neue
Termine reicht wie bisher: der Pfad steht im Inhaltsverzeichnis oder hat
einen Grabstein) — das räumt der Knoten selbst aus seinem Eingang (Gespräche
werden nie gelöscht, nur archiviert).

**Über die Cloud (seit 2026-10-28, das Handy):** dieselben Namen und
Umschläge, nur über die Routen der Cloud
([../hub/knoten_beitritt.md](../hub/knoten_beitritt.md) „Schnittstelle“):

- **Anmelden:** `POST /v1/vorab {name}` → `{salz, kdf}`; Argon2id → HKDF →
  `POST /v1/sitzung {name, anmelde_schluessel, knoten}` → `{token, laeuft_ab,
  verpackt_passwort}`; `konto_schluessel` = Fernet(verpack_schluessel) auf
  `verpackt_passwort`. Prüfstein `tests/daten/konto_testvektoren.json`. Der
  **Schlüssel** der Mitte ist dann der `konto_schluessel` (44 Zeichen wie
  oben), nicht `abgleich.schluessel`.
- **Lesen:** `GET /v1/mitte` → `{kennung, namen}`; `kennung` null = noch kein
  Rechner war da → warten, nichts schreiben. `GET /v1/mitte/datei/inhalt.enc`,
  dann je Datei `GET /v1/mitte/datei/d/<name>.enc` (sha prüfen; 404 oder
  falscher sha = die Mitte lief weiter → beim nächsten Mal).
- **Schreiben:** ein `POST /v1/mitte/stand {basis: kennung, schreiben: {name:
  base64(token)}, verweise: {name: sha256}, loeschen: [name]}` nur mit Namen
  unter `knoten/<knoten>/`. Inline zusammen ≤ 256 KiB, Größeres vorher als Blob
  (`POST /v1/mitte/fehlende`, `PUT /v1/mitte/blob/<sha256>` — sha256 der
  verschlüsselten Bytes) und als Verweis. **409 `jemand_schneller`** → `GET
  /v1/mitte` für die neue Kennung, dasselbe nochmal (der Eingang gehört nur
  dem Knoten, es gibt nichts zusammenzuführen); **400 `blob_fehlt`** → die
  `fehlen` hochladen, nochmal. Die Rechner übernehmen beim nächsten Stand alle
  Namen der Basis, der Eingang bleibt also erhalten.
- Prüfsteine: Dart-Tests in `mobile/test/` gegen eine gespielte Cloud und gegen
  `mobile/test/daten/mitte_testvektoren.json` (erzeugt mit dem echten Kern von
  `scripts/handy_testvektoren.py`); Rechner-Seite `tests/test_abgleich_handy.py`.

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
ts}, `neu_projekt`; optional `basis` (ts: Antworten davor gelten als gelesen —
ein Knoten setzt sie beim ersten Start, damit gezogene Gespräche nicht
ungelesen dastehen; Rechner seit 24.10.2026). Eine Antwort (`rolle: assistant`) kann seit 09.10.
zusätzlich `erledigt` ({`zeile`, `schritte`}), `pruefung` und `offen` (Liste
von Sätzen) tragen ([../ki/ehrlichkeit_live.md](../ki/ehrlichkeit_live.md));
wer sie nicht kennt, übergeht sie. Seit 09.10. (spät) außerdem `warnungen`
(Liste von Sätzen, je mit „⚠" vorn — fertig zum Anzeigen, ÜBER der Antwort,
in Warnfarbe) und `modell_wechsel` ({`von`, `zu`, `von_anbieter`,
`zu_anbieter`, `grund`, `satz`} — `satz` ist die fertige Zeile, ebenfalls
über der Antwort). `erledigt` kann dann auch ohne `schritte` kommen, mit
`zeile` „✗ keine Änderung in diesem Zug"; `pruefung` kann `korrekturen`
(Zahl) tragen. Seit 10.10. außerdem `quellen`: Liste `{titel, url, werkzeug}`
— die Seiten, die die KI in diesem Zug wirklich gelesen hat (Python zieht sie
aus den Werkzeug-Ergebnissen, nie aus Suchtreffern). Anzeigen dezent UNTER der
Antwort als eine Zeile „Quellen: „<titel>“ – <url> · …"; die Adresse steht
nicht mehr unbedingt im Text der KI. Seit 10.10. (abends) außerdem `auftrag`:
{`zeile`, `punkte`} — die Auftrags-Abrechnung der KI; `punkte` ist eine Liste
`{was, stand, werkzeug?, grund?, sicherer_teil?}` mit `stand` erledigt |
offen | abgelehnt, `zeile` die fertige Zeile („offen: Geige fällt aus — Ende
der Ferien unklar · nicht gemacht: …", nur offene und nicht gemachte Teile).
Anzeigen dezent UNTER der Antwort wie die Erledigt-Zeile; sie gehört zu dieser
einen Antwort (anders als `offen`, das fürs ganze Gespräch gilt). Das Handy schreibt nichts davon. Seit 09.10. (abends) kann eine Antwort
außerdem `ablauf` tragen: eine Liste von Einträgen `{art, zeit, t, …}` (art:
`system`, `kontext`, `text`, `werkzeug`, `frage`, `pruefung` (mit `runde`),
`warnung` (`text`), `quellen` (`liste`, seit 10.10.), `auftrag` (`punkte`,
seit 10.10.), `fehler`,
`gestoppt`, `antwort`, `kosten`; je Eintrag höchstens 50.000 Zeichen) —
das Ablauf-Protokoll des Zugs ([../ki/transparenz.md](../ki/transparenz.md),
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
