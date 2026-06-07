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
- `add_routine(layer, label, rrule_str, time=None, **extras)` – Wiederholungs-Regel.
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
Knapp-Warnung. Die ⚠-Zeilen erscheinen automatisch in jeder `read_calendar`-
Antwort; der Tool-Hinweis in `ai.py` weist das Modell an, sie aktiv weiterzugeben.

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
