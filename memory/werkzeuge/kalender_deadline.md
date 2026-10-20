# Kalender: Termintyp „deadline" und gestapeltes Ganztägiges (20.10.2026)

Sasha: „ganztägige events: ich habe 2 am freitag angelegt und es wird nur
eins angezeigt, fix das, sie sollen sich oben stacken. füg noch einen eigenen
typen ‚deadline' hinzu den man togglen kann … die deadline soll rot leuchten
in einem zeitfenster was man selbst vorher einstellen kann, je näher man ihr
kommt. sie soll auch nich oben stehen wie die ganztagsevents, sondern halt
mit ner uhrzeit, nur nen textoverlap machen und so ne deadline hingemalt halt."

## Ganztägiges gestapelt (Woche C)

Vorher zeigte die Zeile „ganzt." je Tag nur den ersten Eintrag („+n"). Jetzt
stehen alle Ganztägigen eines Tages untereinander (`_c_ganztags` in
`tui/ansichten/kalender_ansichten.py`), in der Reihenfolge der Auswahl. Die
Zone ist so hoch wie der Tag mit den meisten (für die ganze Woche gleich),
höchstens `GANZTAGS_ZEILEN` (Regler, 4); die Zeitachse behält mindestens
`GANZTAGS_ACHSE_MIN` Zeilen und rückt darunter. Passt ein Tag nicht hinein,
steht in der letzten Zeile „+n mehr" — liegt der gewählte Eintrag dahinter,
steht er dort. Uncommitted liegt als Glas in seiner eigenen Zeile, Stil wie
gehabt. A (Liste) und B (Monat) zeigten schon jeden Eintrag einzeln.

## Datenmodell

Ein Einmal-Termin oder eine Routine mit `typ: "deadline"` und `vorwarnung`
(Minuten vor dem Zeitpunkt, Vorgabe `VORWARNUNG_STANDARD` = 3 Tage, höchstens
366 Tage). Ein normaler Termin hat kein `typ`. Regeln (`core/kalender_deadline.py`,
geprüft beim Anlegen und bei jedem Ändern, Ablehnung schreibt nichts):

| Code | Wann |
|---|---|
| `DEADLINE-OHNE-ZEIT` | ohne Uhrzeit — eine Deadline ist ein Zeitpunkt |
| `DEADLINE-MIT-ENDE` | mit `ende` (erst `ende=""`, dann Typ; oder beides in einem Aufruf) |
| `DEADLINE-SPANNE` | mehrtägig |
| `TYP-UNBEKANNT`, `VORWARNUNG-UNGUELTIG` | anderer Typ / keine Dauer |
| `IST-PHASE` | eine Phase des Tagesrhythmus |

Wiederholung ist erlaubt (jede Woche Abgabe Fr 12:00): `typ`/`vorwarnung`
gehen wie Gruppe und Stil an jedes Vorkommen (`kalender._MITGEGEBEN`).

## .ics (`core/kalender_ics_abbildung.py`)

- `X-ZENTRALE-TYP:DEADLINE` am VEVENT.
- `DTEND` = `DTSTART` (Dauer 0) — ohne DTEND gäbe Google eine Stunde dazu.
  Ein Ende, das ein Server trotzdem dazugibt, wird bei Deadlines beim Lesen
  verworfen (sonst lehnte das nächste Ändern `DEADLINE-MIT-ENDE` ab).
- Vorwarnung als Standard-`VALARM` (`ACTION:DISPLAY`, `TRIGGER:-P3D`,
  `DESCRIPTION:Deadline: <Titel>`, Marke `X-ZENTRALE-VORWARNUNG:TRUE`), damit
  Handy und Google erinnern. Gelesen wird der markierte Alarm, ohne Marke der
  mit unserer DESCRIPTION, sonst der erste relative (am Handy umgestellt).
- Zusammenführen: fremde Alarme (Handy, Google) bleiben; unserer wird ersetzt,
  auch wenn ein Server Marke und Text verworfen hat (gleicher TRIGGER wie alte
  oder neue Vorwarnung) — so vermehren sich die Alarme nie.
- Ungetestet mit echtem Google-Konto: ob Google Dauer 0 und die X-Marke am
  VALARM behält. Fällt beides weg, bleibt die Deadline (X-ZENTRALE-TYP am
  VEVENT überlebt laut Messung) und die Vorwarnung kommt aus dem TRIGGER.

## Kollisionen, Alarme, KI-Lesen

- Kollidiert nie (`kalender_konflikte._interval` nimmt sie aus) und macht
  keinen Reise-Konflikt (man muss nicht hin).
- Alarm-Kanal: im Vorwarn-Fenster EIN Hinweis `kind: "Deadline"`, Text
  „Deadline Analysis HÜ in 2 Tagen (Fr 23.10. 23:59)" — auf den Tag genau,
  damit sich Text und id höchstens einmal am Tag ändern (weggeklickt bleibt
  weggeklickt, morgen kommt „morgen"). Vorbei = kein Alarm. Uncommitted = kein
  Alarm. Horizont wie alle Alarme 30 Tage.
- Imprint/`read_calendar`: `[deadline] 23:59 Analysis HÜ (in 2 Tagen)`
  (`[uncommitted · vielleicht · deadline]`, mit Gruppe `[deadline · Uni]`),
  dazu ein Satz unter dem Imprint, nur wenn eine Deadline dasteht. Die
  KI-Zeile (`ki_kalender`) nennt `deadline · Vorwarnung 3d` und den Rest.
- KI-Werkzeuge (anlegen/ändern mit `typ`, `vorwarnung`):
  [../ki/ki_kalender.md](../ki/ki_kalender.md), „Deadlines über die Werkzeuge".

## Schnittstelle

- `POST /api/calendar/entry` und `POST /api/calendar/routine` (beide Wege)
  nehmen `typ`, `vorwarnung` (Minuten oder Text „3d", „12h", „1d12h").
- `POST /api/calendar/typ` `{kennung, typ: deadline|normal, vorwarnung?}` →
  `kalender_kennung.typ_setzen` (normal entfernt beide Felder).
- `PUT /api/calendar/eintrag` / `…/routine` per Kennung: `new.typ`,
  `new.vorwarnung` (zusammen mit `new.ende: ""` in EINEM Aufruf).
- `GET /api/calendar`: Einträge tragen `typ`/`vorwarnung`.
- Kern: `kalender.add_entry/add_routine(..., typ=, vorwarnung=)`,
  `kalender_kennung.eintrag_aendern/routine_aendern(k, typ=, vorwarnung=)`,
  `typ_setzen(k, typ, vorwarnung)`; rechnen: `kalender_deadline.rest_text`,
  `im_fenster`, `dauer_lesen`/`dauer_text`.

## TUI

- Formular → Advanced → **Typ** `‹ normal | liste | deadline ›` (←→), neue
  Zeile **Vorwarnung** (immer da, gedämpft „—" außer bei deadline; tippen „3d",
  „1d12h", ⌫, Strg-U). Bei deadline stehen im Formular „Letzter Tag",
  „Ganztägig" und „Bis" gedämpft „—" an ihrem Platz; „Von" ist die Uhrzeit,
  leer = 23:59 (`DEADLINE_ZEIT`). Eine tägliche Deadline bis X bleibt eine
  Serie (keine Spanne). „ganze spanne" bietet deadline nicht an. Keine eigene
  Taste (Sasha: über Advanced reicht).
- Ändern: Typ zurück auf normal → `POST …/typ` VOR dem Ändern; zur Deadline
  oder neue Vorwarnung → NACH dem Ändern (dann ist das Ende schon weg).
- Zeichnen: `tui/ansichten/kalender_deadline.py`. C: „⚑ 23:59 Titel ━━━" über
  die Tagesspalte zur Uhrzeit, über allem, keine Bahn; außerhalb des Fensters
  am Rand mit ▲/▼; mindestens `LINIE_MIN` Zeichen Linie. A: „⚑ 23:59 Titel ·
  in 2 T". B: „⚑23:59 Titel". Gewählt = Akzentfläche. Uncommitted = blass mit
  „╍". Kopieren (c/p) behält den Typ.
- **Leucht-Stufen** (Regler oben in `kalender_deadline.py`, Farben in
  `farben.KAL` dl0–dl3, dlx): außerhalb der Vorwarnung Stufe 0 (gedämpft:
  nachts 131, tags 95); im Fenster nach verbrauchtem Anteil (`STUFEN_AB`
  ⅓, ⅔) Stufe 1 (167 / 124), 2 (160 / 160), 3 = Neon (196 / weiß auf 160) als
  Fläche ab `FLAECHE_AB`; überschritten grau (`k_dlx`, Text „vorbei";
  `VORBEI_ZEIGEN=False` blendet sie aus). Gerechnet bei jedem Zeichnen mit
  `uhr.jetzt()` — die TUI zeichnet ohnehin neu, so wird es von selbst kräftiger.

Tests: `tests/test_kalender_deadline.py` (Kern, .ics, Routen),
`tests/test_kalender_deadline_tui.py` (Stapel, Stufen über die Zeit,
Formular). Bildschirm-Probe 20.10.2026 im Job-Ordner (Woche/Monat/Liste,
nachts und tags).
