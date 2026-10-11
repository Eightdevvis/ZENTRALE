# Kalender-Werkzeuge der KI — ohne Fallen

**Stand 2026-10-11:** Auf `gross` arbeitet die KI mit festen Kennungen
(`#t…`/`#r…`, aus der UID des Kalender-Kerns), ändert genau EINEN Eintrag und
nur genannte Felder, nimmt nichts an (fehlendes Ende wird gemeldet), legt Serien
nur mit Zeitraum `von`/`bis` an und meldet in fester Form aus dem echten Stand.
Die schreibenden Werkzeuge werden seit 2026-10-10 aus dem Schema erzeugt
([werkzeug_erzeuger.md](werkzeug_erzeuger.md)). `klein` liest und schreibt wie
gemessen. Der Kalender selbst: [../werkzeuge/kalender_system.md](../werkzeuge/kalender_system.md).

**Warum:** Sashas Kalender-Testlauf am 08.10. (Gespräch `20261008-132404`):
erledigt gemeldet, aber ohne Ende gespeichert; eine Pause traf die Routine
nicht; Uni-Fächer liefen „für immer". Jede Regel unten schließt eine dieser
Fallen. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Kalender ohne Fallen — `core/ki_kalender.py`, `ki_kalender_aendern.py` (seit 2026-10-08)

- **Kennungen** (nur `gross`): `read_calendar` zeigt je Zeile `#t…` (Termin)
  bzw. `#r…` (Routine), dazu die Serien mit allen Feldern. Seit 2026-10-09
  abgeleitet aus der FESTEN Kennung des Kalender-Kerns
  (`core/kalender_kennung.py`, UID): 4 Zeichen, bei Kollision länger, und
  dieselbe auch nach Umbenennen, neuer Uhrzeit, neuem Ort. Eine gelöschte
  trifft nichts mehr (`K-KENNUNG-UNBEKANNT`). `klein` liest wie gemessen.
- **Per Kennung schreiben** (2026-10-09): ändern, löschen, absagen, pausieren
  laufen über die Funktionen von `kalender_kennung` — der Kern prüft vorher
  und schreibt ganz oder gar nicht; seine Ablehnung kommt als `K-<CODE>`
  durch. Neu anlegen: nachlesen, und steht es anders da als verlangt, per
  Kennung wieder löschen (`W-NICHT-GESPEICHERT`). Rückmeldung in fester
  Form aus dem echten Stand: „Kalendereintrag „Geigenstunde" am Do
  08.10.2026 18:10–19:00 @ Geigenschule EINGETRAGEN (#t3f9c)."
- **Genau EIN Eintrag.** Ändern/Löschen per Kennung; per Name nur bei genau
  einem Treffer (genauer Titel vor Teilstring), sonst nichts ändern und die
  Treffer mit Kennungen zurück. Wo der Kalender-Kern per Teilstring trifft,
  wird vorher nachgerechnet, ob er genau das Gemeinte träfe.
- **Nur genannte Felder.** `edit_calendar_routine` (auch `nur_am`: ein Datum
  ändern oder absagen), `edit_calendar_entry` (neu). Ende vor Beginn wird
  abgelehnt statt still verworfen.
- **Nichts annehmen.** `add_calendar_*` haben auf `gross` `ende` und `ort`;
  fehlt das Ende, steht im Ergebnis „ohne Ende — die Ansicht zeichnet eine
  Stunde, frag nach". Kein Pflichtfeld: sonst müsste die KI eins erfinden,
  wenn Sasha keins genannt hat.
- **Serien nur mit Zeitraum** (gross, 2026-10-09): Sashas Uni-Fächer liefen
  „für immer", auch in den Wochen vor Semesterbeginn. `add_calendar_routine`
  verlangt `von`/`bis` (YYYY-MM-DD); gespeichert als `seit` = von und
  `UNTIL=<bis>T235959` in der RRULE (Standard, .ics-tauglich). Abbrüche:
  fehlt eins → `K-ZEITRAUM-FEHLT` (frag Sasha), UNTIL/COUNT schon in der
  rrule → `K-RRULE-MIT-ENDE` (Ende nur über bis), bis < von →
  `K-SPANNE-VERDREHT`. Nachgelesen werden auch seit und UNTIL. Rückmeldung,
  Frage und `read_calendar` nennen den Zeitraum („… vom 12.10.2026 bis
  13.02.2027"); Serien ohne Ende zeigt `read_calendar` als „(ohne
  Enddatum)". `edit_calendar_routine` setzt/ändert ihn mit `von`/`bis`
  (dieselben Prüfungen); eine neue `rrule` behält das bisherige Ende.
  `klein` unverändert (kein Zeitraum).
- **Pausen** hängen seit 09.10. per Kennung fest an GENAU einer Routine;
  heißt keine genau so, bricht es ab (`K-PAUSE-KEINE-ROUTINE`, mit
  Vorschlag, nichts gespeichert) — vorher wurde eine wirkungslose Pause
  gespeichert (am 08.10. traf „Geigenstunde" die Routine „Geigenstunde @
  Geigenschule" nicht).
  Auf `gross` ist `bis` kein Pflichtfeld (2026-10-08): ohne Ende fällt nur
  der Tag `von` aus, und das Ergebnis sagt „Ende noch offen — frag nach".
  Vorher schob die KI bei „fällt jetzt aus, bis wann?" die ganze Pause auf,
  und die Geige am selben Abend blieb stehen.
- **Was beim Löschen verloren geht** (2026-10-09): löscht `edit_calendar_routine`
  eine Routine und bleibt eine gleichnamige, sagt das Ergebnis, welche Felder
  (Ort, Ende) mit der gelöschten weg sind. Beim Ändern nennt es gleichnamige,
  die mehr Felder haben.
- **Termin per Name ohne Tag** (gross): trifft der Name genau einen Termin,
  der noch nicht vorbei ist, ist er gemeint; sonst die Liste.
- **Warnungen:** `read_calendar_warnings` rechnet sie frisch
  (`kalender.open_alarms`, dieselben wie Sashas ⚠); jeder Beleg nennt die
  Warnungen zum Titel.
- Die Fragen an Sasha nennen bei einer Kennung den Termin („"Geigenstunde"
  (wöchentlich do 18:10–19:10)"), bei Routinen auch Uhrzeit, Ende, Ort.
- Was der Kalender-Kern dafür noch können müsste: `claude_web_plan.md` §7.

## Historie

- **2026-10-08** — Kennungen, genau ein Eintrag, nur genannte Felder, `bis` bei
  Pausen optional.
- **2026-10-09** — feste Kennungen aus der UID, Schreiben per Kennung, Serien nur
  mit Zeitraum, Pausen fest an einer Routine, was beim Löschen verloren geht.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
