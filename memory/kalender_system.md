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
    "routinen": { ..., "routines": [{"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "18:00"}] },
    "erlebt":   { ..., "default_visible": false }
  }
}
```

- **entries** – Einmal-Einträge pro Datum (Liste, mehrere am gleichen Tag möglich).
- **routines** – iCal-RRULE-basierte Wiederholungen, beim Lesen pro Zeitfenster expandiert.
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
