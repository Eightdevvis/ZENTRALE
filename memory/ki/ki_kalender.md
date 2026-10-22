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

## Deadlines über die Werkzeuge (seit 2026-10-20)

Termintyp und Kern: [../werkzeuge/kalender_deadline.md](../werkzeuge/kalender_deadline.md).
Auf `gross` (erzeugte Werkzeuge, `core/werkzeug_kalender.py`, Adapter
`core/ki_kalender_adapter.py`) haben `add_calendar_entry`,
`add_calendar_routine`, `edit_calendar_entry` und `edit_calendar_routine` die
Felder `typ` (`normal`|`deadline`) und `vorwarnung` („3d", „12h", „1d12h";
Vorgabe 3d). Die Erklärung steht in den Feldern (der Werkzeug-Text zählt gegen
den Kalender-Deckel in `tests/test_profil.py`); nur `add_calendar_entry` sagt
im Text „Frist (typ deadline)".

- **Zur Deadline machen** (edit): ein bisheriges Ende fällt von selbst weg —
  leere Felder kommen beim Modell nicht durch, `ende ""` ginge gar nicht.
  Ein ausdrücklich genanntes Ende → `K-DEADLINE-MIT-ENDE`.
- **`typ normal`** entfernt `typ` und `vorwarnung`. Bei Routinen gilt der Typ
  für die ganze Serie; mit `nur_am`/`nur_von` → `K-UNBEKANNTES-FELD`.
- **Fehlercodes mit nächstem Schritt:** bei `K-DEADLINE-OHNE-ZEIT`
  (23:59 vorschlagen oder fragen), `-MIT-ENDE`, `-SPANNE`,
  `K-VORWARNUNG-UNGUELTIG`, `K-TYP-UNBEKANNT` hängt der Adapter die Spalte
  „Was tun" aus `core/fehlercodes.py` an den Abbruch — ohne Umweg über
  `explain_error`. Mehrtägig + deadline meldet `K-DEADLINE-SPANNE` vor
  `K-SPANNE-UHRZEIT`.
- **Belege:** der Satz nennt „(Deadline, Vorwarnung 3d)"
  (`ki_kalender_aendern._deadline`); der Hinweis „Kein Ende angegeben" entfällt
  bei Deadlines (`ohne_ende`). Die Gate-Frage nennt „als Deadline, Vorwarnung …".
- **read_calendar** zeigt `[termine · deadline · Vorwarnung 3d]` und den Rest
  („in 2 Tagen", `ki_kalender._deadline_rest`).
- **qwen** bekommt dieselben gross-Werkzeuge (Zuschnitt „schwach" lässt
  `typ`/`vorwarnung` drin). **klein** und der handgeschriebene gross-Weg
  (`werkzeuge_erzeugt = aus`) haben die Felder nicht — klein bleibt, wie es
  gemessen ist, der Handweg fällt laut Adapter-Kopf weg.

Tests: `tests/test_ki_kalender_deadline.py`.

## Vielleicht gleich beim Anlegen (seit 2026-10-22)

**Anlass:** Gespräch `20261022-111358` — Sasha bat qwen, Sprechstunden
„regelmäßig uncommitted" einzutragen; sie landeten fest. qwen sah keinen Weg:
das Feld `layer` an `add_calendar_*` war für schwache Modelle ausgeblendet
(`schwach=False`), und `set_calendar_layer` kam auf „uncommitted" nicht in die
Vorauswahl (das Muster kannte nur vielleicht/unverbindlich/fest). Das Modell
behauptete trotzdem „alle mit uncommitted".

- **Feld `layer`** an `add_calendar_entry` und `add_calendar_routine` sehen jetzt
  alle Schienen mit Werkzeug-Erzeuger (gross, qwen). Text (`_EBENE_NEU` in
  `core/werkzeug_kalender.py`): „'uncommitted', wenn Sasha es uncommitted,
  vielleicht, unverbindlich oder noch nicht fest eintragen will. Sonst
  weglassen: dann steht es fest im Kalender (termine)." Typ bleibt Text ohne
  enum (das klein-Feld heißt genauso, `tests/test_profil.py`).
- **Adapter** (`ki_kalender_adapter._ebene`): nur `termine`/`uncommitted`
  (altes `routinen` → termine); alles andere → `K-EBENE-UNBEKANNT`, nichts
  gespeichert (vorher ging z. B. `rhythmus` durch). Nachgelesen wird auch die
  Ebene (`verlangt["layer"]`); Beleg und Gate-Frage sagen
  „als vielleicht (uncommitted)".
- **Umlegen** eines bestehenden Eintrags bleibt `set_calendar_layer`
  (`kalender_kennung.ebene_wechseln`); die qwen-Vorauswahl `gruppe` greift jetzt
  auch auf „uncommitted" (`core/werkzeug_gruppen.py`).
- Werkzeug-Beschreibungen unverändert (Kalender-Deckel); die Erklärung steht im Feld.
- `klein` unverändert (gemessen; war hier nicht beteiligt).

Tests: `tests/test_werkzeug_kalender_erzeugt.py` (Einmal, Routine, normal
bleibt fest, nur fest/vielleicht, Frage), `tests/test_modell_profile.py`
(`test_qwen_sieht_die_ebene_bei_uncommitted`).

## Nur übernehmen, was Sasha gesagt hat (seit 2026-10-22)

**Anlass:** dasselbe Gespräch `20261022-111358-dd6127`: qwen schrieb
„Sprechstunde Jonas Schömer (Mo)" an eine Serie BYDAY=WE, erfand den Zeitraum
26.10.–20.12. und behauptete „alle mit 'uncommitted'". Sasha: „der
wochentausch ist doch ziemlich böse."

- **Texte** (`core/werkzeug_kalender.py`, gross und qwen):
  add_calendar_entry „Füll nur Felder, die Sasha genannt hat — kein Ende,
  keine Ebene erfinden.", add_calendar_routine „… von/bis, Ende, Ebene nie
  erfinden; fehlt das Ende der Serie, frag nach." Das Genaue in den Feldern:
  `label` (`_TITEL_NEU`: wie Sasha die Sache nennt, ohne Wochentag, Uhrzeit,
  Ort), `ende`, `von` (ohne Angabe: ab heute), `bis` (nur aus Sashas Angabe,
  sonst fragen), `neuer_titel` der edit-Werkzeuge. Kalender-Deckel danach
  ~2.594 von 2.620.
- **Abbruch `K-TITEL-WOCHENTAG`** (`ki_kalender_adapter._wochentag_passt`):
  Titel nennt einen Wochentag, an dem der Eintrag nicht stattfindet (Regel
  bzw. Datum; beim Anlegen und bei neuer_titel) → nichts gespeichert, „Was
  tun" im Abbruch. „(Mo)" an einer Montags-Serie (wie Sashas eigene „Chemie
  (Mo)") geht durch. Erkennung: `core/titel_wochentag.py`.
- **Nachprüfung danach** (Prüfer, [ehrlichkeit_live.md](ehrlichkeit_live.md)):
  von/bis/ende ohne Grundlage, Behauptungen gegen die echten Aufrufe.
- **Offen beim Kalender-Kern:** eine Warnung für gespeicherte Einträge, deren
  Titel-Wochentag nicht zur Regel passt (z. B. die schon gespeicherte
  „Sprechstunde Jonas Schömer (Mo)", oder eine Serie wechselt den Tag und der
  Titel bleibt) — der Adapter sieht nur neue Titel.

Tests: `tests/test_kalender_nachpruefung.py`.

## Historie

- **2026-10-08** — Kennungen, genau ein Eintrag, nur genannte Felder, `bis` bei
  Pausen optional.
- **2026-10-09** — feste Kennungen aus der UID, Schreiben per Kennung, Serien nur
  mit Zeitraum, Pausen fest an einer Routine, was beim Löschen verloren geht.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
- **2026-10-20** — Deadlines über die Werkzeuge (`typ`, `vorwarnung`).
- **2026-10-22** — vielleicht (uncommitted) gleich beim Anlegen, auch für qwen.
- **2026-10-22** — nur übernehmen, was Sasha gesagt hat: Texte, K-TITEL-WOCHENTAG,
  Nachprüfung im Prüfer.
