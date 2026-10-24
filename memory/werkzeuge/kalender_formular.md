# Kalender-Formular: feste Plätze (18.10.2026)

Sasha: „wenn ganztag is und dann eine wiederholung eingestellt wird dann
shiftet sich die box so rum dass es desorientiert weil plötzlich die optionen
den platz wechseln usw das sollte eigentlich nie passieren".

**Regel:** In einem Kasten wechseln Felder nie den Platz, und der Kasten
ändert seine Höhe nicht, solange man darin ist.

- Alle Felder eines Formulars stehen immer da (`Formular.felder`, `zeilen()`
  liefert jedes). Ob ein Feld gerade gilt, sagt `Feld.aktiv(werte)` (früher
  `zeigen=`, das ausblendete) — z. B. Von/Bis bei ganztägig, Letzter Tag nur
  ganztägig ohne Wiederholung, Abstand/Wiederholen bis nur mit Wiederholung,
  An Tagen nur wöchentlich.
- Was nicht gilt: Wert „—" (`NICHT_AKTIV`), Beschriftung und Wert gedämpft
  (`_zeichne_felder(..., gilt=)` in `kalender_bedienung.py`); Tab/↑↓
  überspringen es (`_auf_aktives`); beim Speichern wird es ignoriert
  (`aktive()`), sein alter Text bleibt für später erhalten.
- Dasselbe im Fenster „advanced": die Zeile „Liste" steht immer, gilt nur
  bei Typ liste (`Advanced.gilt()`).
- Die Logik steht nur in `Formular`/`Advanced`, nie in einzelnen
  Formularen; ein neues Formular gibt nur `aktiv=` an. Gilt auch für die
  Rhythmus-Kästen (`kalender_phasen.py`).

## Ganztägige Serien (derselbe Tag)

„stylebox gemacht auf nen ganztag termin … stand da uhrzeit fehlt". Ursache:
Die Bearbeiten-Kästen einer Serie („alle termine der serie", „nur dieser
tag") hatten kein Feld „Ganztägig" (`mit_ganz=False`), „Von" war Pflicht —
eine ganztägige Serie ließ sich gar nicht speichern; aufgefallen nach
Advanced → Stylebox. Jetzt haben beide das Feld (vorbelegt aus der Uhrzeit;
„nur dieser Tag" nur bei ganztägigen Serien, weil eine Abweichung die Zeit
der Regel erbt). „Letzter Tag" gibt es bei Serien nicht (`mit_letzter=False`).
Tests: `tests/test_kalender_formular_fest.py`.

## Gruppe „eigene" in derselben Zeile (20.10.2026)

„name der gruppe muss in bearbeitung und erstellung nicht angezeigt werden,
einfach so wenn man neu anlegt dass sich das dann aufklappt". Keine Zeile
„Name der Gruppe" mehr: steht „Gruppe" auf „eigene", wird DIESELBE Zeile zum
Textfeld (`Feld(frei=…)`, Ansicht `wahltext`): „‹ eigene: Musik_ ›". Tippen
(auch Leertaste, Umlaute) schreibt den Namen, ⌫ löscht ein Zeichen, Strg-U
alles; ←→ wechseln weiter die Option (der Name bleibt fürs Zurückkommen);
↑↓/Tab verlassen die Zeile, Enter/Strg-S speichern. Leerer Name → „name
fehlt", Fokus bleibt auf der Zeile. Beim Bearbeiten steht „‹ eigene: <name> ›".
Gilt in neu, bearbeiten, Serie „alle", ganze Spanne (nie „nur dieser Tag").

## „Letzter Tag" statt „Tage" (20.10.2026)

„diese ‚tage'-Option ist etwas random". Jetzt ein Datum direkt unter „Tag"
(TT.MM.JJJJ wie „Tag"), gilt nur ganztägig ohne Wiederholung. Leer = nur
dieser Tag; später als „Tag" → Spanne (POST …/spanne, beim Bearbeiten eines
Einzeltermins: Spanne neu + alter Eintrag weg); früher → „letzter tag vor dem
tag" (`_letzter_pruefen`). Tests: `tests/test_kalender_formular_fest.py`,
`tests/test_kalender_gruppen_tui.py`.

## Typ deadline (20.10.2026)

Advanced → Typ deadline: „Letzter Tag", „Ganztägig", „Bis" bleiben an ihrem
Platz und stehen gedämpft „—"; im Fenster advanced die Zeile „Vorwarnung"
(immer da, gilt nur bei deadline), seit 24.10.2026 ebenso „Soll" (eigene
Abgabe vor der Muss-Zeit, „Di 18:00" oder „-2d18h"). Alles Weitere:
[kalender_deadline.md](kalender_deadline.md).
