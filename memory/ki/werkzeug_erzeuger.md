# Werkzeug-Erzeuger — KI-Werkzeuge aus dem Schema einer Quelle

**Stand 2026-10-10.** Gebaut nach Sasha: „kalender api gibt format für
termin anlegen — ki harness wird aus den feldern GEBAUT — ki tool ist so
strukturiert damit ki keine scheiße macht — auch schwächere ki kann mit
fremden kalender/anderem programm arbeiten, weil unser programm die
schnittstelle zum fremden programm so ergänzt, dass die ki damit arbeiten
MUSS." Und: „so können wir dann ja alles mögliche anbinden und wir müssen
nur das MCP pflegen". Plan: [hub_bauplan.md](../system/hub_bauplan.md)
„KI-Werkzeuge aus dem Schema erzeugen".

Erste Quelle: der eigene Kalender (inkl. Tagesphasen, Gruppen, Ebene
„vielleicht").

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
| Kalender-Schemas | `core/werkzeug_kalender.py` | die 11 Aktionen des Kalenders |
| Kalender-Adapter | `core/ki_kalender_adapter.py` | jede Aktion auf `kalender_kennung`, was nachgelesen dastehen muss |

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
