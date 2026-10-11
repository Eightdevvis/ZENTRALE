# Werkzeug-Erzeuger — KI-Werkzeuge aus dem Schema einer Quelle

**Stand 2026-10-11.** Gebaut nach Sasha: „kalender api gibt format für
termin anlegen — ki harness wird aus den feldern GEBAUT — ki tool ist so
strukturiert damit ki keine scheiße macht — auch schwächere ki kann mit
fremden kalender/anderem programm arbeiten, weil unser programm die
schnittstelle zum fremden programm so ergänzt, dass die ki damit arbeiten
MUSS." Und: „so können wir dann ja alles mögliche anbinden und wir müssen
nur das MCP pflegen". Plan: [hub_bauplan.md](../hub/hub_bauplan.md)
„KI-Werkzeuge aus dem Schema erzeugen".

Erste Quelle: der eigene Kalender (inkl. Tagesphasen, Gruppen, Ebene
„vielleicht"). Seit 2026-10-11 gibt es dazu den **allgemeinen Adapter**: ein
neues Programm wird nicht mehr mit Python angebunden, sondern mit einer
Datei — siehe [Anbindungs-Beschreibung](#anbindungs-beschreibung--ein-programm-anbinden-ohne-python).

## Mechanik

```
Quelle: Aktions-Schemas (MCP-Form)  ──┐
Adapter: Grundaktionen              ──┴→ werkzeug_erzeuger.werkzeuge(quelle)
                                          → Register-Einträge (nur gross)
                                          → jeder mit derselben Schutzschicht
```

| Teil | Datei | Was |
|---|---|---|
| Erzeuger | `core/werkzeug_erzeuger/__init__.py` | `Quelle`, `werkzeuge()`, `einsetzen()` ins Register, `zuschneiden()` je Modellprofil, Einstellung `werkzeuge_erzeugt` |
| Schema | `core/werkzeug_erzeuger/schema.py` | Aktion prüfen, Fassung fürs Modell (ohne `x-zentrale`), Argumente prüfen |
| Schutzschicht | `core/werkzeug_erzeuger/harness.py` | Ausführer jedes erzeugten Werkzeugs; Ja/Nein-Frage aus den Feldern |
| Kalender-Schemas | `core/werkzeug_kalender.py` | die 15 Aktionen des Kalenders |
| Kalender-Adapter | `core/ki_kalender_adapter.py` | jede Aktion auf `kalender_kennung`, was nachgelesen dastehen muss |
| Anbindung (Format) | `core/werkzeug_erzeuger/anbindung.schema.json`, `anbindung.py` | JSON Schema der Beschreibung, strenge Prüfung, Stufen, Dateien finden |
| Allgemeiner Adapter | `core/werkzeug_erzeuger/allgemein.py` | führt eine Beschreibung aus: Aufruf bauen, Fehler abbilden, Kennung, Nachlesen, Vergleich, Rückbau |
| Transporte | `core/werkzeug_erzeuger/transport.py` | HTTP (urllib), MCP über stdio (schlank, ohne SDK), Python (nur Vorlagen/Tests) |
| Vorlagen, Zeiger, Vergleich | `vorlage.py`, `vergleich.py` | Platzhalter + JSON-Pointer; Normalisierung (text, zahl, datum, uhrzeit, zeitpunkt, liste-ungeordnet, wahrheit) |
| Probefahrt | `core/werkzeug_erzeuger/probefahrt.py`, `scripts/anbindung_probe.py` | je Aktion prüfen, ohne Modell und Geld |
| Eingeschaltete | `core/werkzeug_erzeuger/aktive.py` | welche Anbindungen laufen, Werkzeuge fürs Register |

**Die Schutzschicht** (für JEDES erzeugte Werkzeug gleich, `harness.ausfuehren`):

1. Argumente gegen das Schema: unbekannte Felder (`<P>-UNBEKANNTES-FELD`),
   Pflichtfelder (`<P>-PFLICHTFELD` oder die Code-Endung aus dem Feld),
   Typ und Auswahl (`<P>-WERT-UNGUELTIG` oder eigene Endung), `format:
   date`. Leer ("", None) zählt als nicht angegeben. Abbruch BEVOR etwas
   geschrieben wird.
2. Der Adapter führt aus oder lehnt ab: `Ablehnung(code, grund)`.
3. Nachlesen per Kennung; `verlangt` (Feld → Wert) und `pruefe(eintrag)`
   müssen stimmen. Beim Löschen: nachgelesen muss es weg sein.
4. Stimmt es nicht: zurücknehmen (anlegen → `loeschen`, ändern →
   `wiederherstellen`) und `W-NICHT-GESPEICHERT`. Scheitert das
   Zurücknehmen, sagt das Ergebnis „NICHT belegt — nachlesen" (nie „nichts
   geändert", wenn es nicht stimmt).
5. Feste Satzform aus dem NACHGELESENEN Eintrag: „<Satzanfang des Adapters>
   EINGETRAGEN|GEÄNDERT|GELÖSCHT (#kennung)<Nachsatz>." bzw. „<was>
   ABGEBROCHEN – nichts … . Fehler <P>-<CODE>: <grund>"
   (`core/werkzeug_befund.py`).

Dazu am Register-Eintrag: Erlaubnis-Gate für alles Schreibende (Frage aus
den Feldern: „Soll ich <frage> <Ziel>: <Wort> <Wert>, …?"; eine Kennung wird
über `adapter.ziel` in Alltagswörter aufgelöst; der Adapter darf eine eigene
Frage liefern), „immer erlauben" nur beim Anlegen, `bereich`/`worte` für
Ehrlichkeit, Erledigt-Zeile und Auftrags-Abrechnung (`core/ehrlichkeit.py`
übernimmt sie aus `werkzeug_register.ERZEUGT`), `zuschnitt` je
Modellprofil-Art.

**Prompt-Cache:** Schemas sind Konstanten (Kataloge aus festen Konstanten
des Kerns), `werkzeuge()` baut dieselben Bytes; das Register setzt sie beim
Import ein (`profil.gross.TOOLS` entsteht beim Import) — pro Prozess fest.

## Form einer Aktion

Eine **MCP-Werkzeug-Definition** (`name`, `description`, `inputSchema` als
JSON Schema 2020-12, `annotations` mit `readOnlyHint`/`destructiveHint`) plus
die Erweiterung `x-zentrale` (wie `x-…` in OpenAPI):

| `x-zentrale` an der Aktion | |
|---|---|
| `art` | `lesen` · `anlegen` · `aendern` · `loeschen` (ohne: aus den MCP-Hinweisen) |
| `alltag`, `worte` | Sashas Wörter für /erlaubnis und die Erledigt-Zeile |
| `frage` | Satzanfang der Ja/Nein-Frage („die Phase eintragen") |
| `immer_erlaubbar` | Standard: nur `anlegen` |
| `beweis`, `nichts` | was nachgelesen wird; Wortlaut im Abbruch |
| `einfach` | Beschreibung für schwache Modelle (Profil qwen) |

| `x-zentrale` an einem Feld | |
|---|---|
| `wort` | wie Sasha das Feld in der Frage liest |
| `fehlt`, `ungueltig` | Code-Endung statt PFLICHTFELD / WERT-UNGUELTIG |
| `ziel: true` | der Wert ist eine Kennung (in der Frage aufgelöst) |
| `schwach: false` | schwache Modelle sehen das Feld nicht (nur freiwillige Felder) |

Das Modell sieht reines JSON Schema — `x-zentrale` wird entfernt.

## Eine neue Quelle anbinden (auch einen MCP-Server)

1. **Schemas:** die Aktionen in MCP-Form. Ein MCP-Server liefert sie schon
   (`tools/list`); `x-zentrale` ergänzen, wo die Standardwerte nicht passen
   (Art, Sashas Wörter, Code-Endungen).
2. **Adapter** (Duck-Typing, Liste im Kopf von `werkzeug_erzeuger/__init__.py`):
   `ausfuehren(name, args) -> Ergebnis`, `nachlesen(kennung)`, `loeschen`,
   `wiederherstellen`, `beschreiben(eintrag)`; optional `kurz`, `frage`,
   `ziel`, `was`. Für einen MCP-Server: `ausfuehren` ruft `tools/call`,
   `nachlesen` die lesende Aktion per Kennung.
3. **Vorsilbe** der Fehlercodes wählen und die Codes in `core/fehlercodes.py`
   eintragen (mindestens `<P>-PFLICHTFELD`, `-WERT-UNGUELTIG`,
   `-UNBEKANNTES-FELD` und die eigenen).
4. Im Register: `ERZEUGT += werkzeug_erzeuger.werkzeuge(QUELLE)`; Bereich in
   `selbstauskunft.BEREICHE`, wenn es ein neuer ist.
5. Tests wie `tests/test_werkzeug_erzeuger.py` (Fake-Quelle) und ein
   Prüfstand-Fall.

**Was „sauber" für einen Adapter heißt:**

- **Kennung:** jeder Eintrag über eine feste Kennung, die Umbenennen
  überlebt. Ein Name, der zwei treffen kann, ändert nichts (Liste zurück).
- **Nachlesen:** `nachlesen(kennung)` liefert den echten Stand (oder None).
  Ohne Nachlesen kein Beleg — **eine Quelle ohne `nachlesen` bekommt nur
  ihre lesenden Aktionen frei.**
- **Ablehnung mit Code** statt stiller Korrektur: was nicht passt, wird
  abgelehnt, und dann ist nichts geschrieben.

## Der Kalender (erste Quelle)

| Werkzeug | Art | Neu/bisher |
|---|---|---|
| `add_calendar_entry` | anlegen | bisher; + `ende`, `ort`, **`kategorie` (Pflicht)**, `kategorie_name` |
| `add_calendar_routine` | anlegen | bisher; `von`/`bis` Pflicht, **`kategorie` Pflicht** |
| `edit_calendar_routine` | ändern | bisher; + **`nur_von`/`nur_bis`** (Tage einer Serie, Kern `routine_zeitraum_aendern`) |
| `add_calendar_pause` | ändern | bisher |
| `delete_calendar_entry`, `edit_calendar_entry` | löschen/ändern | bisher |
| `set_calendar_phase`, `edit_calendar_phase`, `delete_calendar_phase` | | neu: Tagesrhythmus (Motiv, über Mitternacht, ab jetzt / ein Tag / Zeitraum) |
| `set_calendar_group` | ändern | neu: Gruppe eines Eintrags |
| `set_calendar_layer` | ändern | neu: fest (`termine`) ↔ vielleicht (`uncommitted`) |
| `set_calendar_style` | ändern | neu: Aussehen eines Eintrags per Kennung (Rahmen, Rahmen-/Hintergrund-/Schriftfarbe, Muster; `entfernen: ja` = zurück auf Standard) |
| `read_calendar_sources` | lesen | neu: wählbare Listen/Projekte mit `quelle_art`/`quelle_id` (Kern `kalender_quelle.auswahl`) — die KI erfindet keine id |
| `set_calendar_source`, `clear_calendar_source` | ändern | neu: Titel live aus Liste/Projekt setzen bzw. lösen (`titel_uebernehmen`) |

Anlegen (`add_calendar_entry`/`_routine`) nimmt optional `quelle_art` +
`quelle_id` (flach statt eines Objekts: für schwache Modelle einfacher);
`label` ist dann Rückfall-Titel und darf fehlen (dann Name der Quelle).
Satz aus dem Nachgelesenen: „… EINGETRAGEN (#t…) (aus Liste: todo, jetzt:
„Steuern planen“)." Codes `K-QUELLE-ART-UNBEKANNT`, `-UNGUELTIG`,
`-UNBEKANNT`, `K-OHNE-QUELLE`; Phase mit Quelle → `K-IST-PHASE`.

`read_calendar` bleibt handgeschrieben; die Zeilen zeigen seit 10.10. Motiv,
Gruppe und „(bis Folgetag)": `23:00–07:00 (bis Folgetag) Schlaf [rhythmus ·
schlaf]`, `[termine · Uni]`, `[uncommitted · vielleicht]`.

Entscheidungen (2026-10-10):

- **Namen bleiben**, klein-Felder unverändert drin (Prompts, Skills,
  Prüfstand-Fälle passen weiter; `tests/test_profil.py`).
- **Phasen, Gruppe, Ebene als eigene Werkzeuge**, nicht als Felder an den
  bestehenden: ein schwaches Modell sieht am Namen, was geht, und eine Phase
  braucht andere Pflichtfelder (motiv, Beginn; kein Zeitraum-Zwang; Ende vor
  Beginn = Folgetag).
- **Gruppe beim Anlegen Pflicht** (Sasha: im Normalfall „keine"; eine Gruppe
  nur für Einträge, die im Monat als Block zusammengefasst werden). Beim
  Ändern nur über `set_calendar_group`.
- **Phasen zählen nie als Termin:** nicht in „der Tag hat n Einträge", keine
  Warnung, kein „ohne Ende"-Hinweis.
- Die Fach-Regeln (Ziel per Kennung oder eindeutigem Namen, Uhrzeit/Datum,
  Zeitraum, Hinweise) kommen aus `ki_kalender_aendern` — beide Wege
  entscheiden gleich (`tests/test_ki_kalender.py` läuft mit beiden).

## Umschalten

Einstellung **`werkzeuge_erzeugt`** = `an` (Standard) | `aus`
(`ai_config.setting`, Env `ZENTRALE_WERKZEUGE_ERZEUGT`). `aus` = die
handgeschriebenen gross-Werkzeuge von vorher (ohne Phasen/Gruppe/Ebene).
`klein` ist in beiden Fällen byte-gleich (Schnappschuss). Prüfstand:
`--einstellung werkzeuge_erzeugt=aus` zum Vergleich.

Standard `an`, weil alle bisherigen Kalender-Fälle (`tests/test_ki_kalender.py`,
beide Speicher) mit den erzeugten Werkzeugen dieselben Codes, Sätze,
Belege und Rücknahmen liefern. Mit echten Modellen ist es noch NICHT
gemessen (f01k, f02, f03, f06, f10, f11, f12, f13, f14 mit Haiku und qwen).

## Zuschnitt für schwache Modelle

`werkzeug_erzeuger.zuschneiden(tools, "schwach", eintrag)` — vom Profil qwen
(`core/profil/modelle/qwen.py`) vor seinen eigenen Zusätzen angewandt:
Felder mit `schwach: false` weg (`layer`, `kategorie_name`, seltene
Phasen-Felder), `einfach` statt der Beschreibung. Dazu im qwen-Profil zwei
Gruppen der Werkzeug-Auswahl: `rhythmus` (Schlaf, Bett, Phase …),
`gruppe` (Gruppe, Uni, vielleicht, fest …) und `quelle` (Liste, Todo,
Projekt, blocken …). Ungemessen.

## Anbindungs-Beschreibung — ein Programm anbinden, ohne Python

**Gebaut 2026-10-11** (Hub-Bauplan, „Anbindungs-Pipe der Werkstatt", Schritt
(a)). Kern-Idee: ein neues Programm bekommt keinen Python-Adapter, sondern eine
**Beschreibung** in einem offenen Format (JSON, auch YAML). Der allgemeine
Adapter führt sie aus; der Erzeuger macht daraus die KI-Werkzeuge mit allen
Schutzschichten (wie beim Kalender). Später füllt die Werkstatt (eine KI) solche
Beschreibungen aus — darum ist die Prüfung streng und die Sprache klein.

**Standards statt Eigenformat:** das Format ist ein **JSON Schema** (2020-12,
`core/werkzeug_erzeuger/anbindung.schema.json`); jede Aktion ist eine
**MCP-Werkzeug-Definition** (`name`, `description`, `inputSchema`,
`annotations`) plus `x-zentrale` und die Teile der Anbindung; Zeiger sind
**JSON-Pointer** (RFC 6901, einzige Erweiterung: `*` = alle Werte dieser Ebene).
Schlüssel stehen NIE in der Datei: `auth` nennt nur den Namen einer Einstellung.

### Dateien und Einschalten

| | |
|---|---|
| Vorlagen | `core/anbindungen/<name>.json` (mit dem Programm geliefert; heute `kalender_kern`) |
| Nutzerdaten | `data/anbindungen/<name>.json` (Einstellung `anbindungen_dir`, Env `ZENTRALE_ANBINDUNGEN_DIR`); ersetzt eine Vorlage gleichen Namens |
| Einschalten | Einstellung `anbindung_<name>` = `an` (Standard **aus**; das ist Sashas Freigabe). Beim Start gelesen: das Schema ist pro Prozess fest (Prompt-Cache) |
| Eine Datei kaputt | fällt aus, `aktive.FEHLER[name]` nennt die Stellen; der Start läuft weiter |
| Transport `python` | nur in Vorlagen; eine Datei aus `data/` (von der Werkstatt) darf kein Python laden |

### Aufbau

Kopf: `format` (`zentrale-anbindung/1`), `name`, `praefix` (Fehlercodes, 1–3
Großbuchstaben; alle Werkzeugnamen beginnen klein damit: `kk_add_entry`),
`bereich` (kalender, notiz, ablage, messreihe, skill, netz), `zeitzone` (nur nötig
für `zeitpunkt`), `transport`, `nachlesen` (benannte Nachlese-Aufrufe), `fehler`
(Regeln für alle Aktionen).

`transport`: `{"art": "http", "basis": "http://…", "zeitlimit": 15, "auth": {"art": "bearer"
| "kopfzeile", "einstellung": "<NAME>", "kopfzeile": "X-Api-Key"}}` ·
`{"art": "mcp", "kommando": [...], "umgebung": {"VAR": "<Einstellungsname>"}}`
(`{python}` im Kommando = der laufende Interpreter) · `{"art": "python", "modul": "…"}`.

Je Aktion (Pflicht: `name`, `description`, `inputSchema`, `x-zentrale.art`, `aufruf`):

| Feld | Bedeutung |
|---|---|
| `inputSchema`, `annotations`, `x-zentrale` | wie beim Erzeuger (Kopf dieser Datei). Zusätzlich erzwingt der Erzeuger jetzt `pattern`, `items`, `minItems`, `minLength` … des Schemas — Auflagen stehen nicht nur in der Beschreibung für die KI |
| `aufruf` | http: `{methode, pfad, abfrage?, body?}` · mcp: `{werkzeug, argumente?}` (ohne `argumente`: alle durchgereicht) · python: `{funktion, argumente?}` |
| `kennung_aus` | woher die Kennung kommt: `{"antwort": "/id"}` (Zeiger in der Antwort) · `{"argument": "kennung"}` (ändern/löschen: das Argument) · `{"teile": ["day", "label"]}` (das Programm vergibt keine: Kennung = Angaben mit `\|` verbunden, „2026-11-03\|Zahnarzt“) |
| `nachlesen` | Name eines Nachlese-Aufrufs aus dem Kopf: `aufruf`, `teile` (bei zusammengesetzter Kennung), `eintraege` (Zeiger auf Liste/Eintrag), `wo` (Feld → Vorlage; genau EIN Treffer, gleiche Serien-Vorkommen zählen einmal), `zeile` (Satzanfang aus dem Nachgelesenen), `nicht_da` (Bedingungen; Standard Status 404) |
| `vergleich` | Argument → `{norm, feld?, muster?}`; verglichen wird nur, was angegeben wurde. `feld`: Zeiger in den Eintrag (Standard `/<argument>`), `muster`: Ausdruck mit einer Gruppe (Kalender: `UNTIL=(\d{8})` aus der Wiederholungsregel) |
| `zurueck` | anlegen → `{"loeschen": <aufruf>}` · ändern → `{"schreiben": <aufruf>}` mit dem alten Stand `{alt.feld}` · löschen → `{"wiederherstellen": <aufruf>}` · oder `{"keins": true}` · beim Wiederherstellen optional `kennung_neu` (Zeiger auf die neue Kennung in der Antwort, wenn das Programm eine neue vergibt) |
| `fehler` | Regeln `{wenn, code, grund | grund_aus}`; `wenn`: `status`, `mcp_fehler`, `text_enthaelt`, `antwort` + `gleich` / `vorhanden`. Aktions-Regeln gelten vor denen des Kopfs; ohne Treffer: jeder Fehler des Programms → `<P>-ABGELEHNT` mit seiner Begründung |
| `ausgabe` | nur lesen: `eintraege` (Zeiger), `kopf`, `zeile`, `leer`, `hoechstens` (Standard 50). Ohne `ausgabe` bekommt die KI die rohe Antwort (gekürzt auf 8000 Zeichen) |
| `probe` | Beispiel-Argumente für die Probefahrt; `vorher`: Name einer anlegenden Aktion, die das Probe-Objekt anlegt (ändern/löschen/lesen); `kennung_in`, `erwartet` nur für lesen |

**Platzhalter** (`vorlage.py`): `{day}` = Argument, `{kennung}` / `{kennung.day}`
(ändern/löschen, Rückbau, Nachlesen), `{alt.time}` = Stand vor dem Ändern/Löschen,
`{e.label}` = ein Eintrag in `zeile`. Ist der Text genau ein Platzhalter, bleibt der Typ
(Zahl, Liste); fehlt der Wert, **fällt das Feld weg** (freiwillige Argumente);
`{alt.ort|}` setzt den Text hinter `|` ein, wenn nichts da ist — so wird ein früher
leeres Feld beim Zurückschreiben wieder geleert statt vergessen. In Pfaden wird
URL-kodiert; fehlt dort etwas, ist es ein Fehler (`<P>-PFLICHTFELD`).

**Normalisierung** (`vergleich.py`) — fremde Programme schreiben dasselbe anders:
`text` (Leerraum, Unicode), `zahl` (3 = 3.0 = „3“), `datum` (auch `20261103`, Tag eines
Zeitstempels), `uhrzeit` („9:00“ = „09:00:00“ = „…T09:00+01:00“), `zeitpunkt` (derselbe
Moment mit Zeitzone; ohne Angabe die der Anbindung, ohne beides: keine Raterei, eine
Abweichung), `liste-ungeordnet`, `wahrheit`. Was sich nicht normalisieren lässt, ist eine
Abweichung mit Begründung, kein Absturz.

### Stufen (automatisch, je Aktion — `anbindung.stufe`)

| Stufe | Wann | Verhalten |
|---|---|---|
| `lesen` | lesende Aktion | frei |
| `voll` | `kennung_aus` + `nachlesen` + Rückbau (anlegen: `loeschen`, ändern: `schreiben`, löschen: `wiederherstellen`) | volle Schutzschicht: Schema-Prüfung, Gate, Nachlesen, Vergleich, Zurücknehmen, feste Satzform. Anlegen mit zusammengesetzter Kennung: gibt es sie schon, `<P>-GIBT-ES-SCHON` statt Dopplung |
| `gefragt` | Schreiben ohne eines davon | jedes Mal Rückfrage (kein „immer erlauben"), die Frage sagt, dass ZENTRALE nichts nachprüfen kann; Ergebnis „AUSGEFÜHRT – aber NICHT belegt", kein Nachlesen, kein Zurückbauen |
| `einmalig` | Löschen ohne `wiederherstellen` | wie `gefragt`; die Frage sagt „nur dieses eine Mal" |

Ein Aufruf, bei dem unklar bleibt, ob das Programm geschrieben hat (Zeitüberschreitung
NACH dem Senden, keine Kennung zurück), endet nie in „nichts geändert", sondern in
`W-NICHT-GESPEICHERT` mit „NICHT belegt — nachlesen". Stufe 3 (Programm ganz ohne Schema,
nur Bildschirm) gehört nicht hierher.

### Prüfung der Beschreibung

`anbindung.pruefen(besch)` — zuerst das JSON Schema, dann, was ein Schema nicht sagt, und
nennt ALLE Fehler mit Stelle (`/aktionen/1 (nt_edit_note)/kennung_aus: …`), so dass eine
KI sie beheben kann: Werkzeugnamen mit Vorsilbe und eindeutig; `inputSchema` ist gültiges
JSON Schema; Aufruf passt zum Transport; jeder Platzhalter gibt es (Argument, `kennung.<teil>`);
Kennung und Nachlesen passen zusammen (gleiche Teile; Teile nicht änderbar); Rückbau passt zur
Art; Vergleich nennt nur vorhandene Argumente, `zeitpunkt` braucht `zeitzone`, `muster` hat
genau eine Gruppe; Probe-Argumente gibt es; **kein Schlüssel in der Datei** (Muster wie
`sk-…`, `Bearer …`, `password=…`); Python-Transport nur in Vorlagen. Hinweise (nicht Fehler):
Aktion ohne `probe`, lesende ohne `ausgabe`.

### Probefahrt (Pipe-Schritt 3) — ohne Modell, ohne Geld

```
venv/bin/python scripts/anbindung_probe.py <name|pfad> [--nur a,b] [--alles] [--ausfuehrlich] [--json]
venv/bin/python scripts/anbindung_probe.py kalender_kern --test-kalender      # eigener Kalender, Wegwerf-Kopie
venv/bin/python scripts/anbindung_probe.py --liste
```

Aus Python: `probefahrt.fahren(besch, quelle=None, nur=None, alles=False, sender=None)` →
Liste `{aktion, art, stufe, ok, warum, schritte:[{schritt, ok, text}]}`;
`probefahrt.gruen(zeilen)`, `probefahrt.bericht(zeilen)`. Je Aktion: anlegen → nachlesen →
vergleichen → zurückbauen (weg?); ändern/löschen mit einem Probe-Objekt, das die Fahrt
selbst anlegt und wegräumt (ändern: alter Stand wieder da?; löschen: weg? wiederhergestellt?);
lesen: ein Aufruf (mit `erwartet`: das Probe-Objekt kommt vor). Alles läuft durch dieselbe
Schutzschicht wie im Gespräch. Aktionen ohne Rückbau (`gefragt`/`einmalig`) werden nur mit
`--alles` ausgeführt (sie lassen sich nicht aufräumen — also nur gegen eine Test-Kopie).
Rückgabewert 0 = alles in Ordnung.

### Vollständiges Beispiel (MCP-Server mit Notizen; kürzer als `tests/fixtures/anbindung_notizen.json`)

```json
{
  "format": "zentrale-anbindung/1",
  "name": "notizen",
  "praefix": "NT",
  "bereich": "notiz",
  "transport": {"art": "mcp", "kommando": ["npx", "-y", "notizen-mcp-server"], "umgebung": {"NOTIZEN_TOKEN": "notizen_token"}},
  "nachlesen": {
    "notiz": {
      "aufruf": {"werkzeug": "get_note", "argumente": {"id": "{kennung}"}},
      "nicht_da": [{"mcp_fehler": true, "text_enthaelt": "not found"}],
      "zeile": "Notiz „{e.title}“"
    }
  },
  "aktionen": [
    {
      "name": "nt_create_note",
      "description": "Legt eine neue Notiz an (Titel Pflicht).",
      "inputSchema": {
        "type": "object",
        "properties": {
          "title": {"type": "string", "description": "Titel der Notiz.", "x-zentrale": {"wort": "Titel", "fehlt": "TITEL-LEER"}},
          "tags": {"type": "array", "items": {"type": "string"}, "description": "Schlagwörter.", "x-zentrale": {"wort": "Schlagwörter"}}
        },
        "required": ["title"]
      },
      "x-zentrale": {"art": "anlegen", "alltag": "Notizen anlegen", "worte": ["Notiz angelegt", "Notiz anlegen"], "frage": "eine Notiz anlegen"},
      "aufruf": {"werkzeug": "create_note", "argumente": {"title": "{title}", "tags": "{tags}"}},
      "kennung_aus": {"antwort": "/id"},
      "nachlesen": "notiz",
      "vergleich": {"title": {"norm": "text"}, "tags": {"norm": "liste-ungeordnet"}},
      "zurueck": {"loeschen": {"werkzeug": "delete_note", "argumente": {"id": "{kennung}"}}},
      "fehler": [{"wenn": {"mcp_fehler": true}, "code": "ABGELEHNT", "grund_aus": "/message"}],
      "probe": {"argumente": {"title": "Probe", "tags": ["b", "a"]}}
    },
    {
      "name": "nt_edit_note",
      "description": "Ändert den Titel einer Notiz (Kennung aus nt_list_notes).",
      "inputSchema": {
        "type": "object",
        "properties": {
          "kennung": {"type": "string", "description": "Kennung der Notiz.", "x-zentrale": {"ziel": true}},
          "title": {"type": "string", "description": "Neuer Titel.", "x-zentrale": {"wort": "Titel"}}
        },
        "required": ["kennung", "title"]
      },
      "x-zentrale": {"art": "aendern", "alltag": "Notizen ändern", "frage": "die Notiz ändern"},
      "aufruf": {"werkzeug": "update_note", "argumente": {"id": "{kennung}", "title": "{title}"}},
      "kennung_aus": {"argument": "kennung"},
      "nachlesen": "notiz",
      "vergleich": {"title": {"norm": "text"}},
      "zurueck": {"schreiben": {"werkzeug": "update_note", "argumente": {"id": "{kennung}", "title": "{alt.title}"}}},
      "probe": {"vorher": "nt_create_note", "argumente": {"title": "Geändert"}}
    },
    {
      "name": "nt_list_notes",
      "description": "Listet alle Notizen mit Kennung.",
      "inputSchema": {"type": "object", "properties": {}, "required": []},
      "x-zentrale": {"art": "lesen"},
      "aufruf": {"werkzeug": "list_notes"},
      "ausgabe": {"eintraege": "/notes", "zeile": "#{e.id} {e.title}", "leer": "Keine Notizen."},
      "probe": {"vorher": "nt_create_note", "erwartet": "Probe", "argumente": {}}
    }
  ]
}
```

Die Beschreibung des Kalenders über HTTP (`core/anbindungen/kalender_kern.json`) ist das
Gegenstück für ein Programm ohne eigene Kennungen: dort besteht die Kennung aus
`Tag|Titel`, das Nachlesen filtert die Wochenansicht.

### Probe am eigenen Kalender (`kalender_kern`) — Unterschiede zu den handgeschriebenen Werkzeugen

Gleich: Schutzschicht, Satzform, Rücknahme, `immer erlauben` nur beim Anlegen. Anders
(2026-10-11, Probefahrt gegen die `/api/calendar`-Routen mit dem Flask-Test-Client):

- **Weniger Werkzeuge**, kleinere Felder: Termin anlegen/ändern/löschen, Routine anlegen
  (wöchentlich, von/bis) / löschen, einen Tag lesen. Keine Pausen, Phasen, Gruppen, Ebene,
  Quellen, Serie-Ausschnitte — dafür bräuchte die HTTP-Schnittstelle erst Routen mit Kennung.
- **Kennung = die echte des Kalenders** (seit 2026-10-11, Routen 8d96228): `kennung_aus: {"antwort": "/kennung"}`, Nachlesen `GET /api/calendar/eintrag?kennung=`, Ändern/Löschen per `kennung` (`PUT/DELETE /eintrag`, `/routine`); `kk_read_day` zeigt sie. Gleichnamige Termine sind trennbar. Wiederherstellen eines gelöschten Termins vergibt der Kalender eine neue Kennung: `zurueck/wiederherstellen` trägt `kennung_neu: "/kennung"`, der Adapter führt die alte dorthin.
- **Routine löschen ist Stufe `einmalig`**: die HTTP-Route liefert nichts, woraus sich die
  Routine wiederherstellen ließe (Regel steht nur als `RRULE` mit UNTIL). Die
  Handwerkzeuge können es (`kalender_kennung`). Ein ehrliches Beispiel für die Stufen.
- **Routine ändern fehlt** (`PUT /api/calendar/routine` braucht Tag + Titel, ändert alle
  Vorkommen; `nur_von`/`nur_bis` gibt es nur im Kern).
- **Konflikt-Warnungen** der Routen (`conflicts`) werden nicht gezeigt; die Handwerkzeuge
  warnen.
- **Fund der Probefahrt:** `POST /api/calendar/entry` speichert `time` unverändert („9:00“)
  und vergleicht Uhrzeiten danach als Text — `ende 10:30` gegen `time 9:00` lehnt der Kalender
  ab („Ende liegt nicht nach Beginn“). Die Beschreibung schreibt deshalb im Schema zweistellige
  Uhrzeiten vor (`pattern`), und der Erzeuger erzwingt das jetzt. Der Kern (`core/kalender*.py`)
  ist unverändert; Normalisieren beim Speichern wäre Sache der KALENDER-Sitzung.
- Beide Wege nebeneinander: Namen `kk_…`, Vorsilbe `KK-`, Anbindung standardmäßig aus.
  Auf dem Prüfstand ist sie noch NICHT gemessen (kein Modell).

### Neue Fehler-Endungen

`core/fehlercodes.py`: `ANBINDUNG_CODES` — Endungen, die für jede Vorsilbe gelten
(`KK-NICHT-GEFUNDEN`, `NT-ABGELEHNT`, `…-NICHT-ERREICHBAR`, `-ZEITUEBERSCHREITUNG`,
`-AUTH-FEHLT`, `-MEHRDEUTIG`, `-GIBT-ES-SCHON`, `-KENNUNG-UNGUELTIG`, `-NICHTS-ZU-AENDERN`,
`-KEIN-RUECKBAU`, `-GESPERRT`, dazu `-PFLICHTFELD`, `-WERT-UNGUELTIG`, `-UNBEKANNTES-FELD`).
`explain_error` erklärt sie; ein eigener Eintrag (`K-…`) hat Vorrang.

### Grenzen und Offenes

- Kein OpenAPI-Import: die Beschreibung ist die Zusammenfassung dessen, was ZENTRALE
  braucht; die Werkstatt liest die OpenAPI-Datei des Programms und füllt aus.
  (Schritt (a) im Plan nannte „MCP + OpenAPI"; OpenAPI-Operationen sind hier als `http`-Aufrufe
  abgebildet, ein automatischer Import fehlt.)
- Genau EIN Mitwirkender je Nachlesen (`wo`, ein Treffer); keine Seiten (Paginierung) —
  ein Nachlesen, das die Liste nur seitenweise liefert, braucht einen Filter in der Abfrage.
- MCP: nur stdio, nur `tools/list` und `tools/call`; kein HTTP/SSE-Transport, keine
  Ressourcen/Prompts, keine Anmeldung per OAuth.
- Backend-Zugangsschlüssel (`core/zugang.py`) liegt in einer Datei, nicht in einer
  Einstellung — `kalender_kern` läuft deshalb nur von dem Rechner, auf dem das Backend
  läuft (dort braucht es keinen).
