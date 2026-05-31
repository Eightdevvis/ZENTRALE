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
- **default_visible** – steuert ob ein Layer im Standard-Jetzt-Block der KI auftaucht
  (`erlebt` ist standardmäßig aus, sonst wird der Prompt zu noisy).

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
- `render_week_for_prompt(reference=None)` – Wochen-Block für `ai._now_prompt`.

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
| `read_calendar`         | User fragt nach Zeitraum > diese Woche              |
| `add_calendar_entry`    | User nennt einmaligen Termin/Frist                  |
| `add_calendar_routine`  | User nennt regelmäßige Aktivität                    |

`read_calendar(start_date, end_date, layers?)` liefert pro-Tag-Liste,
Routinen werden expandiert. `add_calendar_entry(layer, day, label, time?)`
und `add_calendar_routine(layer, label, rrule, time?)` schreiben in
benannte Layer. Default-Layer im Tool-Prompt: `termine` bzw. `routinen`.

RRULE-Beispiele die die KI im Prompt kennt:
- `FREQ=WEEKLY;BYDAY=TU` – jeden Dienstag
- `FREQ=WEEKLY;BYDAY=MO,WE,FR` – Mo/Mi/Fr
- `FREQ=MONTHLY;BYMONTHDAY=1` – jeder 1. im Monat
- `FREQ=MONTHLY;BYDAY=2TU` – zweiter Dienstag im Monat
- `FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25` – jedes Jahr 25.12.

## Integration in den Jetzt-Block

`core/ai.py:_now_prompt()` baut bei jedem Turn:

```
## Jetzt
Heute ist Sonntag, der 31. Mai 2026. Aktuelle Uhrzeit: 13:46.
[Hinweis: nur diese Zeile ist verlässliche Zeitquelle.]

## Heute und der Rest der Woche
So 31.5. (heute) — (leer)

Frühere Tage stehen nicht hier - wenn der User danach fragt, ruf das
read_calendar-Tool mit Vergangenheits-Range.
```

**Bewusst nur heute + Zukunft** — wenn der User „was steht an" fragt,
soll die KI nicht erst durch vergangene Termine waten und dabei in den
Tempus-Default rutschen („diese Woche **hast** du am Dienstag…"
obwohl Dienstag schon vorbei ist). Erster Versuch mit Klammer-Markern
(`(vergangen)`) und Sektion-Headern hat das Modell ignoriert. Lehrgeld:
**bei Modell-Schwäche nicht mehr Hints stapeln, sondern die Daten-
Auswahl ändern.** Vergangenheit ist über `read_calendar`-Tool erreichbar.

Default-sichtbare Layer (`termine`, `routinen`) gehen in den Block,
der `erlebt`-Layer ist `default_visible=False` und kommt nur per
explizitem `read_calendar`-Aufruf — sonst flutet er den Prompt jeden
Turn neu.

## Cross-Reference Graph ↔ Kalender (typisches Beispiel)

User: „wie war Geige letzte Woche?"

1. Aus dem Jetzt-Block weiß die KI: heute Sonntag 31.5., letzter Di = 26.5.
2. Kalender sagt: 26.5. → Routine „Geige 18:00" (also fand statt).
3. Graph-Aktivierung um Time-Node `2026-05-26` liefert verknüpfte
   Konzepte (Stimmung, was danach kam, falls erwähnt).
4. Antwort kombiniert beides.

Wichtig: beide Systeme dürfen unabhängig wahrheitsgemäß sein. Wenn der
Kalender „Geige am 26.5." sagt, der Graph aber nichts zur Stimmung
weiß, sagt die KI „weiß ich nicht" statt zu raten – Anti-Konfabulation
gilt für beide Schichten.
