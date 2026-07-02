# Kalender-System (Layer-Modell)

Zeitlich strukturierte Schicht neben dem assoziativen Graph. Der Graph
ist gut für „wer mag was, was hängt mit was zusammen"; der Kalender ist
gut für „welcher Tag wann, was kommt noch, was ist regelmäßig". Beide
sind verknüpft über das ISO-Datum als gemeinsamen Schlüssel – keine
harte Referenz, jeder Teil bleibt unabhängig wartbar.

## Datenmodell

Datei: `data/ai_calendar.json`. Format:

```json
{
  "version": 1,
  "layers": {
    "termine": {
      "label": "Termine",
      "color": "#ff5500",
      "default_visible": true,
      "entries":  { "2026-06-03": [{"label": "TÜV-Frist"}, ...] },
      "routines": []
    },
    "routinen": { ..., "routines": [{"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45", "ende": "18:30", "ort": "Musikschule"}] },
    "erlebt":   { ..., "default_visible": false }
  },
  "reisezeiten": { "Musikschule": {"Fahrschule": 10}, "Zuhause": {"Fahrschule": 30} },
  "puffer_min": 15
}
```

- **entries** – Einmal-Einträge pro Datum (Liste, mehrere am gleichen Tag möglich).
- **routines** – iCal-RRULE-basierte Wiederholungen, beim Lesen pro Zeitfenster expandiert.
- **time / ende** – Start- und Endzeit (`HH:MM`). Erst MIT `ende` ist ein
  Eintrag ein echtes Intervall und nimmt an Kollisions-/Machbarkeits-Prüfung
  teil; ohne `ende` gilt er als ganztags/unbestimmt (löst nichts aus).
- **ort** – Freitext-Ortsname (der echte Ort, z.B. „Musikschule", nicht die
  Aktivität). Schlüssel in die `reisezeiten`-Matrix für die Knapp-Prüfung.
- **bis** – Enddatum (`YYYY-MM-DD`) macht aus einem Einmal-Eintrag einen
  Mehrtages-Block (Reise/Abwesenheit). Mit `ort` zusammen weiß der Kalender
  über die Spanne, WO du bist → lokale Termine in der Zeit an anderem Ort
  werden als `⚠ KONFLIKT` erkannt (z.B. „Ungarn-Reise" 8.–12. vs. Geige Di).
- **reisezeiten** (top-level, optional) – grobe, handgepflegte Fahrzeit-Matrix
  `{von: {nach: minuten}}`, symmetrisch nachgeschlagen. Offline, nie Google.
- **puffer_min** (top-level, optional, Default 15) – Reserve, die bei der
  Knapp-Prüfung auf jede Fahrzeit draufkommt.
- **default_visible** – Sichtbarkeits-Flag für die Dashboard-UI (`erlebt`
  ist standardmäßig aus). Seit dem Glue-Wegfall (2026-06) NICHT mehr für den
  Jetzt-Block relevant — `read_calendar` liefert per Default alle Layer.

## Default-Layer beim ersten Boot

| Name      | Quelle    | Sichtbar | Inhalt                                          |
|-----------|-----------|----------|-------------------------------------------------|
| termine   | manuell   | ja       | Arzt, Frist, Geburtstag, Einmal-Events          |
| routinen  | manuell   | ja       | Wiederholungs-Regeln                            |
| erlebt    | automatisch | nein   | Spiegelung aller `geschah-am`-Edges vom Graph   |

Weitere Layer (`ernaehrung`, `schlaf`, `training`, …) kommen via
`kalender.add_layer(name, label, color, default_visible)` dazu, sobald
das entsprechende Tracking-Feature gebaut wird.

## Module

### `core/kalender.py`

Public API:
- `ensure_init()` – Datei + Default-Layer beim Boot sicherstellen.
- `add_entry(layer, day, label, time=None, **extras)` – Einmal-Eintrag.
- `add_span(layer, von, bis, label, **extras)` – MEHRTÄGIGER (ganztägiger) Termin: Einmal-Eintrag mit `bis`-Datum unter `von`; `entries_in_range` expandiert über [von,bis]. bis<von → False.
- `set_span_time(layer, von, label, day, time)` – optionale Uhrzeit NUR für einen Tag der Spanne (`times[day]` an der Spanne; leer = löschen/ganztägig).
- `add_routine(layer, label, rrule_str, time=None, **extras)` – Wiederholungs-Regel.
- `add_pause(label, von, bis, grund=None)` – Routine über eine Spanne aussetzen (Tool `add_calendar_pause`, gegatet).
- `delete_entry(day, label, layer=None)` → `int` – Einträge an einem Tag löschen, gibt Anzahl zurück (Tool `delete_calendar_entry`, gegatet). Tool-Hinweis: DIREKT rufen, KEIN read_calendar davor – gemessen (2026-06-07): mit vorherigem read lenken die ⚠-Alarm-Zeilen das 9B 5/8-mal von der Löschung ab; direkt = 8/8. Deterministisch die Ablenkung wegnehmen schlägt Prompt-Nudging.
- `add_layer(name, label, color, default_visible)` – neuer Layer.
- `auto_capture(concept, day_iso)` – Spiegelung vom Graph-Extraktor.
- `entries_in_range(start, end, layers=None)` – Range-Query, Routinen werden expandiert.
- `week_view(reference=None, only_default_visible=True)` – laufende Woche um `reference`.
- `resolve_range(zeitraum, reference=None)` – relativer Bucket-Name
  (`dieser_monat`, `naechste_woche`, …) → konkretes `(start, end)`-Paar.
  Python rechnet die Datumsgrenzen, nicht das Modell. `None` bei
  unbekanntem Bucket (Aufrufer fällt dann auf ISO-Daten zurück).
- `render_range_for_tool(start, end, layers=None)` – Tool-Antwort für
  `read_calendar`, jeder Tag MIT ausgeschriebenem Wochentag
  („Dienstag, 09.06.2026: …").
- `RANGE_BUCKETS` – Liste der erlaubten `zeitraum`-Werte (Quelle für das
  Tool-Enum).
- `find_collisions(entries)` → `[(a, b, kind)]` – überlappende Paare eines
  Tages, `kind` ∈ {`voll`, `teil`}. Halboffen: 18:00↔18:00 berührt sich, keine
  Kollision.
- `travel_minutes(von, nach, matrix=None)` – **die eine Nahtstelle** für
  Ortsdistanz. Heute: handgepflegte `reisezeiten`-Matrix. Später ersetzbar
  durch eigenen Router (Dijkstra) / Transit-Grep, ohne den Kalender-Layer zu
  ändern — nie Google-Maps. `0` = gleicher Ort, `None` = unbekannt (rät nie).
- `day_warnings(entries, matrix=None, puffer_min=None)` → `[str]` – fertige
  ⚠-Zeilen für einen Tag (Voll-/Teil-Überlappung + Knapp-Übergang). Wird in
  `render_range_for_tool` pro Tag angehängt.
- `conflicts_for_proposed(layer, day, label, time=None)` → `[str]` – prüft einen
  NOCH NICHT geschriebenen Einmal-Termin HYPOTHETISCH gegen den Tag: holt die
  echten Einträge (alle Layer), hängt den Plan-Termin als Phantom dran und lässt
  `day_warnings` + `_conflict_lines` laufen (DRY, gleiche Logik wie der Render-
  Pfad). `_absage_alarms` bewusst NICHT (Reise-To-do, kein Konflikt dieses
  Termins). Genutzt von `_permission_question` (ai.py): die ⚠-Zeile steht damit
  schon im JA/NEIN-Gate-Dialog – Sasha entscheidet **informiert VOR dem
  Schreiben**, statt erst danach gewarnt zu werden. `[]` bei ungültigem Datum
  oder konfliktfrei. Hintergrund: Live-Tests 2026-06-07 zeigten erst, dass ein
  blindes `add` einen Termin stumm in eine Reise legte; ein erster Fix warnte
  NACH dem Schreiben (Tool-Ergebnis) – Sasha: „backwards"; daher die Warnung in
  die Gate-Frage vorgezogen. Henne-Ei-Trick nötig, weil der KONFLIKT erst durch
  das Schreiben entstünde – das Phantom umgeht das.
- `_away_blocks(start, end, data=None)` → `[{von, bis, ort, label}]` –
  Mehrtages-Abwesenheits-Blöcke (Einträge mit `bis`), die den Bereich
  überschneiden.
- `_conflict_lines(day, entries, away_blocks)` → `[str]` – `⚠ KONFLIKT`-Zeilen
  für lokale Termine, die in eine Reise-Spanne an anderem Ort fallen.

### Kollisions- & Machbarkeits-Layer (2026-06-06)

Auf den reinen Kalender ist ein Rechen-Layer gesetzt, der pro Tag drei Fälle
als fertige ⚠-Zeilen ausgibt (Python rechnet, das Modell liest nur ab — selbes
Prinzip wie `resolve_range`/`suche`):

- **voll überlappt** (einer steckt im anderen) → „entweder/oder".
- **teils überlappt** → Nachfrage „ersten früher verlassen, Rest beim
  nächsten?" (bewusste Ausnahme von der „keine Rückfragen"-Regel, weil echte
  User-Entscheidung).
- **kein Overlap, aber Lücke < Fahrzeit + Puffer** → „wird örtlich knapp".

Reisezeit ist `von`-`nach` (hängt vom Vor-Ort ab), nicht pauschal pro Ort. Fehlt
die Fahrzeit (kein `ort`, Paar nicht in Matrix), gibt es bewusst KEINE
Knapp-Warnung. **Seit 2026-06-07 erscheinen diese ⚠-Zeilen NICHT mehr inline in
`read_calendar`** (siehe „Alarm-Kanal" unten) — der Read ist reine Terminliste.
Die Rechenfunktionen (`day_warnings`, `_conflict_lines`, `_absage_alarms`)
bleiben, werden aber nur noch von `open_alarms` (Kanal) und `conflicts_for_proposed`
(Add-Gate) aufgerufen, nicht mehr von `render_range_for_tool`.

**Abwesenheits-Konflikt (`⚠ KONFLIKT`, 2026-06-06):** Ein Mehrtages-Block mit
`bis`+`ort` (Reise) macht dem Kalender bekannt, wo du über die Spanne bist. Fällt
ein lokaler Termin an anderem Ort hinein („du bist in Ungarn, hast aber Di
Geige"), wird er als `⚠ KONFLIKT` geflaggt.

**Drei Alarm-Typen bei Reisen (Verfeinerung 2026-06-07).** Auf einer Reise wird
NICHT alles gleich behandelt:

- **Einmal-Termine** (`termine`-Einträge mit Uhrzeit) → `⚠ KONFLIKT`
  (`_conflict_lines`): etwas Besonderes, das man verpasst/verschieben muss.
- **Routinen ohne Absagepflicht** (Parkour, Fahrschule) → **still**, kein Alarm:
  fallen auf einer Reise erwartbar weg. Bleiben gelistet.
- **Routinen mit `absage_noetig: true`** (z.B. Geige bei der Lehrerin) →
  `⚠ ABSAGEN` (`_absage_alarms`): aktive To-do-Absage. **Einmal pro Reise**
  (dedupliziert über `seen`), nicht pro Vorkommen - Sasha sagt einmal „bin
  von-bis weg", nicht jede Woche neu.

Routinen tragen `recurring=True` (aus `entries_in_range`); `absage_noetig` ist
ein optionales Feld pro Routine in der Kalender-Datei. Alarm-Verhalten in beiden
Fällen: erst beim User rückversichern, dann lauter Text + `[[bild: alarm]]`.

### Alarm-Kanal (2026-06-07) — Warnungen raus aus den Arbeitsdaten

**Problem:** Inline-⚠ in `read_calendar` kaperten die Aufmerksamkeit des 9B
(Löschen scheiterte 1/4, Add wurde blind). Gegenmaßnahme „nicht lesen lassen"
erzeugte Folgebugs. **Sashas Umkehrung:** KI nie vom Environment abschneiden —
die Ablenkung in einen eigenen Rand-Kanal ziehen, Read sauber halten, frei lesen
lassen.

- **Quelle:** `kalender.open_alarms(horizon_days=30)` → `[{id, kind, text}]`.
  Sammelt aus `_absage_alarms`/`_conflict_lines`/`day_warnings` (DRY). `id` =
  stabiler md5(kind|text)[:8] (kein Frontend-Flackern), `text` ohne führendes „⚠".
- **Recompute-Trigger:** zentral in `kalender._save_raw` (nach JEDER Mutation,
  try/except-gekapselt) + Boot + alle ~300 Loop-Ticks in `core/main.py` (Zeit-
  Drift: Reise rückt in den Horizont). Kein Deadlock — die `open_alarms`-Kette
  nimmt `_lock` nicht.
- **Speicher:** `state.set_alarms`/`get_alarms` — flache Liste mit **Replace-
  Semantik** (nicht Append-Deque), gelöste Alarme verschwinden von selbst. Geht
  in `get_snapshot()["alarms"]`.
- **Zwei Senken:** (a) Dashboard — `/api/state` → `engine.js` tick → Warndreieck-
  Ecke unten links im KI-Canvas (`#alarm-corner`, ein `.alarm-tri` pro Alarm,
  gedeckelt auf 5 + „+N"); (b) KI — `ai._alarm_prompt()` hängt einen „## Offene
  Erinnerungen"-Block an den System-Prompt (nur regulärer Chat, nach `mem_ctx`).
- **Lese-Sperren entfernt:** delete-Tool-Beschreibung erlaubt wieder
  `read_calendar` davor; Meta-Regel 8 („Aufgabe vor Hinweis") raus.

**Gemessen (2026-06-07, `scripts/bench_calendar_delete.py`, N=10, qwen3.5:9b).**
Eigener 3-Turn-Episoden-Bench (löschen → „was ist die Warnung" → „haben wir doch
gelöscht"), isolierte Fixture, Alarm-Kanal voll nachgebaut (state-Stub mit echter
Alarm-Box → recompute nach jeder Mutation wie in Prod). Lokalisiert den Bug:
- delete feuert **90 %**, ehrlich (kein Fake-„gelöscht") **100 %** → die
  Lese-Sperren-Hypothese hält, Löschen ist NICHT das Problem.
- **Alarm-ZUORDNUNG nur 30 %**: das 9B liest `⚠ ABSAGEN: Routine 'Geigenstunde'
  … Pflicht-Absage` und verkauft sie 7/10-mal als „Reise-vs-10-Uhr-KONFLIKT"
  (den schon gelöschten Einzeltermin), spiralt von da in Konfabulation
  (erfundenes Dashboard-Menü, „Neustart hilft"). Episode komplett sauber: 20 %.
- Konsequenz: Hebel ist die **Präsentation** der Alarm-Zeile, nicht ein
  weiterer Prompt-Knebel — `feedback_data_vs_model`.

**Fix (2026-06-07, `_absage_alarms`).** ABSAGEN-Zeile umgebaut: AKTION + Subjekt
nach vorn, eigener Wochentag des Vorkommens (Di — trennt die Routine vom
Mo-Einzeltermin), Reise als Grund nach hinten. Alt: „Routine 'Geigenstunde' liegt
in Reise Ungarn-Reise (…) - Pflicht-Absage." Neu: „⚠ Geigenstunde absagen: dein
wöchentlicher Termin am Dienstag (09.06.) fällt in die Reise Ungarn-Reise (…) -
du musst aktiv absagen (bei Geigenschule), er entfällt nicht von selbst."
**Re-Bench (N=20): Alarm-Zuordnung 30 % → ~60 %, Episode-sauber 20 % → ~45 %, delete
unverändert 100 %.** Reine Datenzeilen-Änderung. ~37 % Fehlattribution-Schwanz
bleibt (9B-Decke / History-Vergiftung) — weiter offen.

**Absage-Eskalation per Knopf-Dialog (2026-06-07):** nach jedem Absage-Alarm
(ABSAGEN, oder Einzeltermin den Sasha absagen müsste) hakt die KI per
`frage_knopf`-Tool nach - eskalierend: „Hast du es abgesagt?" (ja/nein) → bei
nein „Wirst du es jetzt absagen?" (ja/nein) → bei nochmal nein „Katastrophe."
mit optionen `['ja','ja']` (Schabernack). `frage_knopf` kann das nativ: Klick
kommt als Tool-Result zurück, die KI legt im selben Zug den nächsten Knopf nach
(Mechanik in `ai.py` chat_stream, kein Sonder-Code nötig). Anweisung steht in
der `read_calendar`-Tool-Beschreibung. Reliabilität des 3-Stufen-Chains beim 9B
ist noch zu messen - bei Flakiness ggf. deterministisch in Python treiben.

**Richtung 2 - die andere Seite sagt ab (Pausen/Ausfälle, 2026-06-07):** der
umgekehrte Fall - Ferien/Feiertag → Lehrerin/Anbieter zu, Sasha muss sich
erinnern „keine Geige". Modelliert als top-level `pausen`-Liste
(`[{label, von, bis, grund?}]`). Eine Routine, deren Vorkommen in eine Pause für
ihr Label fällt, bekommt in `entries_in_range` ein `ausfall`-Feld und wird im
Render als `ℹ <label> fällt aus (<grund>)` gezeigt statt als Termin - plus der
`⚠ ABSAGEN`-Alarm verstummt (Anbieter hat ja schon abgesagt). Eingetragen wird
manuell, am einfachsten über das KI-Tool `add_calendar_pause` (Sasha sagt's,
die KI trägt's ein). `_pause_grund(label, day, pausen)` ist die **Nahtstelle**:
heute manuelle Liste, später (KI mit Internet) erweiterbar um automatische
Ferien-/Feiertags-Abfrage - nie Google. Neue Funktionen: `add_pause(...)`,
`_pause_grund(...)`. Modell-Verhalten (Persona + Tool-
Hinweis): die KI **vergewissert sich erst einmal beim User** (stimmt Reise?
stimmt Termin?) und schlägt dann **laut Alarm** — deutlicher Text + `zeige_ascii`
mit Stichwort `alarm` (Motiv in `data/ascii/alarm.txt`). Verify-dann-Alarm ist
dieselbe Reflexions-Haltung wie gegen die History-Vergiftung: erst prüfen, dann
behaupten. Diese Rückfrage ist (wie die Teil-Überlappung) eine bewusste Ausnahme
von „keine Rückfragen".

Warum nicht `core/calendar.py`: Python's stdlib hat ein `calendar`-Modul,
und `dateutil.rrule` importiert intern `from calendar import monthrange`.
Lokales `core/calendar.py` würde das shadowen → ImportError. Deutscher
Name löst es eindeutig und passt zur ZENTRALE-Domain.

### Auto-Capture vom Graph

`core/consolidation.py:extract_turn_into_graph` ruft nach jedem
Graph-Write `kalender.auto_capture(concept, day_iso)` für jeden
`geschah-am`-Edge mit ISO-Datum als Ziel. „Sasha" und „KI" werden
übersprungen (sind Anker, keine Erlebnisse). Dedup auf `(concept, day)`,
damit dasselbe Konzept bei mehrfachem Erwähnen nicht mehrfach im
`erlebt`-Layer landet.

## Tools (KI-side)

| Tool                    | Wann                                                |
|-------------------------|-----------------------------------------------------|
| `read_calendar`         | JEDE Frage nach Terminen/Plänen/Daten (Pflicht)     |
| `add_calendar_entry`    | User nennt einmaligen Termin/Frist                  |
| `add_calendar_routine`  | User nennt regelmäßige Aktivität                    |
| `add_calendar_pause`    | Routine über eine Spanne aussetzen (gegatet)        |
| `delete_calendar_entry` | Eintrag löschen (gegatet)                           |

`read_calendar(zeitraum?, start_date?, end_date?, layers?)`. **Kein
Calendar-Glue mehr im Prompt** — die KI hat keine Termine im Gedächtnis und
MUSS dieses Tool bei jeder zeitlichen Frage rufen (Regel steht im
Jetzt-Block + in der Tool-Beschreibung). Zeitraum bevorzugt über `zeitraum`
(Bucket aus `RANGE_BUCKETS`, z.B. `dieser_monat`, `naechste_woche`,
`diese_und_naechste_woche`, `letzter_monat`); Python löst den Bucket in
exakte Daten auf. Für krumme Spannen („ab dem 15.", „in 3 Monaten")
`start_date`+`end_date` (ISO). Ausgabe pro Tag mit Wochentag, Routinen
expandiert. `add_calendar_entry(layer, day, label, time?)`
und `add_calendar_routine(layer, label, rrule, time?)` schreiben in
benannte Layer. Default-Layer im Tool-Prompt: `termine` bzw. `routinen`.

RRULE-Beispiele die die KI im Prompt kennt:
- `FREQ=WEEKLY;BYDAY=TU` – jeden Dienstag
- `FREQ=WEEKLY;BYDAY=MO,WE,FR` – Mo/Mi/Fr
- `FREQ=MONTHLY;BYMONTHDAY=1` – jeder 1. im Monat
- `FREQ=MONTHLY;BYDAY=2TU` – zweiter Dienstag im Monat
- `FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25` – jedes Jahr 25.12.

## Integration in den Jetzt-Block (kein Glue mehr)

`core/ai.py:_now_prompt()` baut bei jedem Turn NUR einen Zeit-Anker plus
die Pflicht-Regel zum Tool — **kein Kalender-Listing**:

```
## Jetzt
Heute ist Sonntag, der 31. Mai 2026. Aktuelle Uhrzeit: 13:46.
[Hinweis: nur diese Zeile ist verlässliche Zeitquelle.]

Kalender/Termine: du hast keine Termine im Kopf. Für JEDE Frage nach
Plänen, Terminen oder Daten (heute, diese/nächste Woche, Monat,
Vergangenheit, beliebiger Zeitraum) rufst du zuerst read_calendar -
nie raten, nie ohne Tool zurückfragen.
```

**Warum kein Glue (Designwechsel 2026-06):** Vorher wurde die laufende
(später: laufende + nächste) Woche fest in den Prompt geklebt. Das hatte
zwei Probleme:

1. **Skaliert nicht.** „Was steht den Monat an?" / „in 3 Monaten?" lässt
   sich nicht mitkleben, ohne den Prompt zu fluten.
2. **Split-Brain.** Mit geklebter Woche hatte das Modell einen faulen
   Halb-Weg: nahe Termine aus dem Block beantworten, für den Rest
   zurückfragen — statt konsequent das Tool zu rufen. Genau das war der
   Bug („steht diese oder nächste Woche was an?" → nur diese beantwortet,
   nach „nächste" unnötig gefragt).

Konsequenz: **ein** Mechanismus statt zwei. Der Kalender wird nicht mehr
mitgeschleppt, sondern ausschließlich per `read_calendar` gegriffen — für
JEDEN Zeitraum. Verlässlichkeit messbar gemacht (qwen2.5:14b, 4× dieselbe
Frage): 4/4 Tool gerufen, 0/4 Rückfrage, Wochentag korrekt.

**Zwei Reliability-Lecks, die der Wechsel mitgefixt hat:**

- *Datums-Arithmetik beim Modell* → schwach. Jetzt klassifiziert das
  Modell nur in einen `zeitraum`-Bucket, `resolve_range` rechnet die
  Grenzen in Python.
- *Nackte ISO-Ausgabe* → das Modell rechnete den Wochentag selbst aus und
  verrechnete sich („Montag" statt „Dienstag"). `render_range_for_tool`
  liefert den Wochentag jetzt fertig.

`feedback_data_vs_model` gilt weiter — nur war die richtige Daten-Auswahl
hier „gar nichts kleben, sauber greppen", nicht „mehr kleben".

## Sichtbare Anzeige (Mitte/Canvas jeder Kassette, 2026-06)

Neben dem KI-Tool `read_calendar` ist der Kalender jetzt **sichtbar** in der
Mitte jeder Front — blätterbar und zwischen **Woche** und **Monat**
umschaltbar. Geteilte, front-agnostische Quelle (wie die Maps):

- **Endpoint** `GET /api/calendar?view=week|month&ref=YYYY-MM-DD` (in `ui/app.py`).
  **Nicht** KI-gegatet — reine Anzeige, kein KI-Pfad, läuft auch in der ki-freien
  Kassette. Liefert `{view, ref, today, label, start, end, days, alarms}` (+
  `month/first/last` bei Monat). Details: `api_endpoints.md`.
- **Backend** (`core/kalender.py`): `week_view()` (bestand) liefert die Mo-So-
  Woche; neu `month_view(reference)` liefert das **Monatsgitter** — alle Tage vom
  Montag VOR dem Ersten bis zum Sonntag NACH dem Letzten (volle Wochenzeilen),
  plus `first`/`last` zum Ausgrauen der Rand-Tage. Beide nutzen
  `entries_in_range` (Routinen expandiert, `ausfall` bei Ferien). Monatsnamen:
  `_MONTHS_FULL_DE`. Datums-Arithmetik in Python, nie in der Front.
- **Drei Fronten, ein Endpoint:**
  - *TUI* (`tui/zentrale_tui.py`): Mittelbox-Modus `c` neben `g`/`m`. `←→`/`hl`
    blättern, `v`/Tab schaltet Woche↔Monat, `0` springt zu heute, `esc`/`c` zu.
    Woche = Tagesliste, Monat = Braille-freies Zeichen-Gitter. Defensiv wie der
    Karten-Pfad (Fehler-Marker statt Dauer-Refetch; `_for`-Tag gegen Refetch je
    Frame). Im Fuzz (`tests/_tui_fuzz.py`) mit eigenen `c/v`-Keys + Adversarial-
    `/api/calendar` abgedeckt.
  - *Browser* (`ui/templates/monolith.html`, alle Kassetten): Exhibit-Tab
    „Kalender" (eigenes `#calendar-panel` wie das Graph-Werkzeug, NICHT im
    Auto-Direktor). In der KI-freien Kassette (laptop) identisch — dasselbe
    Template, nur ohne KI-Blöcke.

Bewusst getrennt vom Alarm-Kanal: die Anzeige zeigt die Termin-Arbeitsdaten,
die ⚠-Warnungen bleiben randständig (Header-Zähler `⚠N` aus `alarms`), genau wie
`read_calendar` sauber von den Inline-Warnungen getrennt wurde.

### Kalender-Sidebar: die flache »week«-Liste (2026-07, ersetzt die Wochentag-Spalte)

Brücke Listen ↔ Kalender. Eine als **`week`** benannte Liste (`core/lists.py`)
ist speziell: sie ist die **flache Kalender-Sidebar** — EINE Liste, deren Items
in der Wochenansicht **rechts neben dem Gitter** stehen, **nicht** mehr nach
Wochentag sortiert, **wochenunabhängig** (blättern ändert die Liste nicht). Löst
das frühere Modell ab (7 Wochentag-Ordner + Datums-Rolling — von Sasha verworfen).

- **Einmalige Migration (`_migrate_week_flat`, in `_load`):** Altdaten mit
  Wochentag-Ordnern (mon…sun) werden beim ersten Laden pro Prozess flach gezogen
  (Items eine Ebene hoch, done bleibt, Ordner weg). Idempotent → danach No-op.
  `_WEEKDAY_NAMES`/`_weekday_index` bleiben nur noch dafür.
- **`lists.week_items(reference=None)`** (ersetzt `week_plan`): liefert
  `{lid, items:[{id,text,done,linked}]}` — flach, kein Datums-Mapping. `reference`
  wird ignoriert (Signatur kompatibel). Leeres `{lid:None, items:[]}` ohne
  week-Liste.
- **Reinschieben = kopieren + verlinken:** `move_item` mit der `week`-Liste als
  Ziel KOPIERT den Eintrag (Quelle/Projekt behält das Original) und stampft
  `link={lid,iid}` auf die Kopie. Man kann die `week`-Liste **weiterhin normal im
  Listentool** öffnen und dort Items reinkopieren.
- **Abhaken ist BIDIREKTIONAL (`_sync_linked_done` in `toggle_item`):** Kopie
  abhaken setzt die Quelle mit; Quelle abhaken setzt alle Kopien mit (Reverse-
  Lookup über `link`). **LÖSCHEN** der Kopie bricht nur den Link — die Quelle
  bleibt (dangling link wird beim Toggle still ignoriert).

Anzeige-/Interaktions-Pfad:
- **Backend:** `/api/calendar` hängt `weekplan = lists.week_items()` an die
  Antwort (in Woche UND Monat, defensiv `{lid:None,items:[]}`). Bearbeiten nutzt
  die vorhandenen `/api/lists/<l_week>/items…` (toggle/add/rename/delete); **neu**
  fürs Sortieren: `POST …/items/<iid>/reorder` `{delta:-1|+1}` (`lists.reorder_item`
  tauscht mit dem Nachbarn in der Geschwister-Ebene, am Rand No-op).
- **Sidebar-Optik:** Items stehen **etwas auseinander** (TUI: 1 Leerzeile Abstand;
  Browser: `gap:9px`) und haben eine **Ombre** — je weiter unten, desto
  transparenter (sichtbar ab ~4 Items, verblasst in den Hintergrund). TUI: eigene
  256-Grau-Rampe pro Theme (`C["ombre"]`, verblasst Richtung bg; Mono/8-Farb-
  Fallback = A_DIM-Stufen). Browser: `opacity` pro Item (`1 − idx·0.14`, Boden 0.38).
- **TUI** (`tui/zentrale_tui.py`): rechte Spalte ist EINE flache Liste über die
  volle Höhe (`k_sidebar_items()`/`k_sidebar_lid()`), Trenner `│`. **Taste `l`**
  (aus „nächste Periode" gelöst; nächste Periode nur noch `→`) schiebt den Fokus
  in die Sidebar (`K["listfocus"]`, ‹fokus›, erstes Item). Dort: `↑↓` wählen,
  `Space/Enter` abhaken (Link-Sync), `a` neu / `r` umbenennen (`K["linput"]`-
  Eingabe läuft unten in der breiten ›-Befehlszeile, nicht in der schmalen
  Kopfzeile; die Kopfzeile zeigt nur ‹umbenennen unten›) / `d` löschen,
  **`s` Sortier-Modus**
  (`K["lsort"]`: dann verschieben `↑↓` das fokussierte Item per `reorder`, Cursor
  zieht per id nach; `s`/Esc = fertig; Kopfzeile ‹sortieren ↑↓›, Item-Marker `⇅`),
  `l`/Esc/← zurück, `c` Kalender zu. **KEIN** `m`/`>` (kein Move in andere Listen
  — isolierte Einheit). Nur in der Wochenansicht. Verlinkte Items tragen `↔`.
  Kontexte `cal:list`/`cal:sort` in der Shortcut-Leiste.
- **Browser/Laptop** (`monolith.html`, `renderWeek`→`renderSidebar`): Flex-Row
  `[.cweek Tage] [.csidebar flache Liste]`. Items klickbar (abhaken), `▲▼`
  sortieren (`reorder`), `✎` umbenennen (prompt), `✕` löschen, Add-Feld unten
  (`sidebarAction` → dieselben `/api/lists`-Endpoints, danach `load()`). `↔` an
  verlinkten. Maus-getrieben → kein `l`-Tastensprung. Move in andere Listen ist im
  Browser ohnehin nie verdrahtet.
- Tests: `tests/test_lists.py` (Migration flach, copy+link, bidirektionaler
  Sync, delete-bricht-nur-Link, `week_items`-Form, `reorder` rauf/runter/Rand/
  Geschwister-Ebene), `tests/test_backend_api.py`, Fuzz mit adversarialem
  `weekplan` (neue `{lid,items}`-Form + Müll) + `s`-Taste im Sortier-Pfad.

### Mehrtägige Termine (2026-07)

Ganztägige Termine über eine Datumsspanne (Urlaub, Messe, Konferenz). Modell:
**ein** Einmal-Eintrag mit `bis`-Datum, gespeichert unter dem Start-Tag `von` in
`entries[von]` — `{label, bis, times?:{iso:HH:MM}, ort?}`. `entries_in_range`
**expandiert** ihn über [von,bis] ∩ Fenster: jeder Tag eine Kopie mit
`spanning:True`, `von`, `bis`, `span_first`/`span_last`; `bis`/`times` selbst
wandern NICHT roh in die Kopien.

- **Linke Spann-Gosse (2026-07, TUI):** mehrtägige Termine werden NICHT inline in
  den Tages-Zeilen gezeichnet (dort riss die Klammer, sobald ein Tag andere
  Termine hatte, + Leerzeilen), sondern in einer **eigenen linken Spalte außerhalb
  der Tagesdaten**: eine **durchgehende Klammer** `┌` (erster Tag) · `│`/Buchstaben
  · `└` (letzter Tag). Der **Titel läuft senkrecht AM STÜCK** nach unten (ein
  Buchstabe pro Zeile, ab Zeile unter `┌`; Rest der Höhe als `│`) — nicht mehr pro
  Tag wiederholt. Überlappende Spannen bekommen eigene **Lanes** (Greedy);
  `gw`=Gossenbreite, die Tages-Inhalte rücken um `gw+1` nach rechts (`cx`). Der
  Render erfasst pro Tag `day_top`/`day_bot` und zieht die Klammer vom ersten bis
  letzten sichtbaren Tag durch. Spannen bleiben **auswählbar** (di zählt in
  `k_selectable` mit, ohne Inline-Zeile): der gewählte Tag hebt seinen Klammer-
  Abschnitt **invers** hervor, unten steht `▶ <titel> · <datum>`.
- **Ganztägig by default; Uhrzeit optional PRO TAG:** bearbeitet man einen
  einzelnen Tag der Spanne, setzt `set_span_time` eine Uhrzeit nur für diesen Tag
  (`times[day]`, leer = wieder ganztägig). Kein pauschales `time` an der Spanne.
- **Endpoints:** `POST /api/calendar/entry` mit `{day:von, bis, label, ort?}` →
  `add_span` (kein Konflikt-Check, ganztägig). `POST /api/calendar/entry/spantime`
  `{layer?, von, label, day, time?}` → `set_span_time`. Löschen über den Start-Tag
  (`DELETE …/entry {day:von, label}`) entfernt die GANZE Spanne.
- **TUI:** Anlege-Formular hat einen **dritten Typ** (Tab: Termin→Routine→**Mehrtägig**);
  Mehrtägig fragt Von-Datum, Bis-Datum, Titel. Darstellung = linke Spann-Gosse
  (s.o.). `e` auf einer Spanne = Uhrzeit für DIESEN Tag (Eingabe unten in der
  ›-Leiste, `spantgt`/`lmode="spantime"`); `d` löscht über `von` die ganze Spanne.
  `k_selectable` trägt die Spann-Felder; `_k_entry_line` rendert Spannen NICHT
  (die macht der Gossen-Block).
- **Browser:** dritter Form-Typ „Mehrtägig" (Von/Bis-Datumsfelder); Spann-Chip
  `.cent.span` (gepunktet) mit `┌│└`-Marker je Tag; der **Titel steht nur am
  ersten Tag** (nicht pro Tag wiederholt), Folgetage nur Klammer (+ optionale
  Uhrzeit `.spantime`). `✎` = Uhrzeit für diesen Tag (`spanTime`, prompt),
  `✕` = ganze Spanne löschen (über `von`).
- Tests: `tests/test_backend_api.py` (Expansion + Marker, Delete über von,
  per-Tag-Zeit setzen/löschen, bis<von→400), Fuzz mit adversarialen `spanning`-
  Einträgen.

### Direktes Eintragen/Ändern/Löschen + Routine-Deaktivieren (2026-06)

Die Anzeige ist nicht read-only — aus der Mitte lassen sich Einmal-Termine
**anlegen, ändern, löschen** und **einzelne Routine-Vorkommen ab-/anschalten**,
in allen drei Fronten. Schreib-Endpoints (`ui/app.py`, alle direkt auf
`core/kalender.py`): `POST /api/calendar/entry` (anlegen → `add_entry`),
`PUT …/entry` (ändern = delete+add), `DELETE …/entry` (löschen → `delete_entry`),
`POST /api/calendar/routine/skip` (Vorkommen de-/aktivieren → `set_routine_skip`),
`DELETE /api/calendar/routine` (ganze Routine löschen → `delete_routine`).

- **NICHT KI-gegatet** — direkte Nutzeraktion (wie `/api/log` beim Graph-Werkzeug),
  kein KI-Schreibpfad. Das KI-Permission-Gate (JA/NEIN mit `conflicts_for_proposed`)
  bleibt unberührt; es greift nur, wenn die *KI* schreibt. POST/PUT geben die
  Konflikt-Zeilen trotzdem als **Hinweis** (`conflicts`) zurück, ohne zu blocken.
- **Einmal-Termine** (`termine`) werden voll editiert. **Routinen** lassen sich
  aus der Mitte **anlegen** (wöchentlich: ein/mehrere Wochentage + Zeit + Titel →
  `POST /api/calendar/routine`, baut `FREQ=WEEKLY;BYDAY=…`; krummere Wiederholungen
  wie monatlich/jährlich bleiben dem KI-Tool `add_calendar_routine` vorbehalten),
  **ganz löschen** ODER pro Tag ein **einzelnes Vorkommen** deaktivieren:
  - `set_routine_skip(layer,label,day,off)` führt eine Liste `aus=[iso,…]` AN der
    Routine. `entries_in_range` gibt das Vorkommen weiter aus, markiert es aber
    `deaktiviert=True` (sichtbar + wieder-aktivierbar, ausgegraut „(aus)").
  - `delete_routine(layer,label)` entfernt die ganze Regel (Gegenstück zu
    `add_routine`) — alle Vorkommen weg.
  - Deaktivierte Vorkommen lösen **keine** Alarme aus — Guards in `open_alarms`,
    `_absage_alarms` und `conflicts_for_proposed` (analog zum `ausfall`-Guard).
    Abgrenzung: `ausfall` = Anbieter/Ferien-Pause (`pausen`), `deaktiviert` = der
    User hat diesen einen Termin selbst abgeschaltet.
- **TUI:** der ›-Cursor (`↑↓`) läuft jetzt über **ALLE** Einträge (`k_selectable()`,
  nicht mehr nur Einmal-Termine — das war der Skip-Bug). `a` = neu anlegen
  (Formular, **Tab** schaltet Termin→Routine→**Mehrtägig**: Routine = Wochentag-
  Eingabe „Mo,Fr", Mehrtägig = Von/Bis-Datum). `e`/Enter bearbeiten: Einmal →
  vorbefülltes Formular (PUT), Spanne → Uhrzeit-für-diesen-Tag, Routine
  → Screen mit `d` (nur dieser Tag aus) / `a` (wieder an) / `x` (ganze Routine
  löschen, `j`-Nachfrage). `d` direkt: Einmal → Lösch-Bestätigung, Routine → Screen.
- **Browser** (Monolith-Panel + Laptop-Mittelbox): „＋ Termin"-Form mit
  Termin/Routine-Umschalter (Routine = Wochentag-Chips Mo–So statt Datum); pro
  Termin ✎ (bearbeiten, PUT) + ✕ (löschen); Routine-Vorkommen ⊘ (diesen Tag
  deaktivieren) / ↺ (wieder aktivieren), deaktivierte durchgestrichen-grau, + 🗑
  (ganze Routine löschen, `confirm()`). Schreib-Fehler (z.B. altes Backend ohne
  neue Route) werden jetzt sichtbar gemeldet statt still geschluckt.

Defensiv getestet: `tests/test_backend_api.py` (add/edit/skip, isolierte TEMP-
`CAL_PATH`), TUI-PTY-E2E (Edit + Routine-Deaktivieren/-Reaktivieren, Datei als
Wahrheit) und die Fuzz-Suite (`a/d/e/c/v/x`-Keys + Adversarial-`/api/calendar`
inkl. recurring/deaktiviert/PUT).

### Erledigtes ein-/ausblenden — EIN gemeinsamer Toggle (2026-06)

Ein **Anzeige-Schalter** über dreierlei „passiert nicht" zusammen: einzeln
**deaktivierte Routine-Vorkommen** (`deaktiviert`, „(aus)"), per Zeitraum-Pause
**ausgefallene** (`ausfall`, z.B. Ferien; kommt aus `add_pause`/`pausen`) UND
**abgehakte Wochenplan-Items** (`done`, durchgestrichen). Alle stehen gemeinsam da
oder sind gemeinsam weg. **Default: ausgeblendet** — der Kalender startet
aufgeräumt, der Toggle blendet alles **ein**.

- **Reiner Front-Filter, kein Backend-Pfad:** alle Flags liegen schon in der
  `/api/calendar`-Antwort (`entries_in_range` → `deaktiviert`/`ausfall`,
  `week_items` → `done`). Gefiltert wird pro Front, `core/kalender.py`/`lists.py`/
  `app.py` unverändert. Greift in Woche UND Monat (im Monat fällt der `•`-Marker
  eines Tags weg, der nur noch deaktivierte/ausgefallene Einträge hätte).
- **Zwei Deaktivierungs-Routen, EIN Toggle:** `deaktiviert` = einzelnes Vorkommen
  vom User abgeschaltet (`set_routine_skip` → `aus`-Liste an der Routine);
  `ausfall` = ganze Routine über einen Zeitraum pausiert (`add_pause` → `pausen`).
  Beide zählen als „findet nicht statt" und teilen sich denselben Schalter — sonst
  bleibt z.B. eine über Ferien pausierte Geigenstunde trotz „aus" sichtbar.
- **Browser** (`monolith.html`, Kalender-IIFE): Header-Knopf `🚫/👁 erledigte`
  (neben „＋ Termin"), Zustand `CS.showHidden`. `dayList()` filtert `deaktiviert`
  **und** `ausfall`, `planItems()` filtert `done` in der Sidebar (alle nur solange
  `!showHidden`). Toggle ruft nur `render()` (kein Reload).
- **TUI** (`tui/zentrale_tui.py`): Taste **`x`** im Kalender (`K["showhidden"]`).
  **Wichtig:** `k_selectable()` UND der Wochen-Render überspringen versteckte
  deaktivierte Einträge an der **exakt gleichen** Stelle (vor `di += 1`), sonst
  zeigt der ›-Cursor auf den falschen Termin. `ausfall`-Einträge sind ohnehin nie
  auswählbar (`di=None`), lassen sich also gefahrlos gleich mit verstecken.

## Cross-Reference Graph ↔ Kalender (typisches Beispiel)

User: „wie war Geige letzte Woche?"

1. Aus dem Zeit-Anker weiß die KI: heute Sonntag 31.5.
2. `read_calendar(zeitraum="letzte_woche")` → 26.5. Routine „Geige 18:00"
   (also fand statt).
3. Graph-Aktivierung um Time-Node `2026-05-26` liefert verknüpfte
   Konzepte (Stimmung, was danach kam, falls erwähnt).
4. Antwort kombiniert beides.

Wichtig: beide Systeme dürfen unabhängig wahrheitsgemäß sein. Wenn der
Kalender „Geige am 26.5." sagt, der Graph aber nichts zur Stimmung
weiß, sagt die KI „weiß ich nicht" statt zu raten – Anti-Konfabulation
gilt für beide Schichten.
