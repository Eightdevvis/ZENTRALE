# Kalender-Formular: feste Plätze (18.10.2026)

Sasha: „wenn ganztag is und dann eine wiederholung eingestellt wird dann
shiftet sich die box so rum dass es desorientiert weil plötzlich die optionen
den platz wechseln usw das sollte eigentlich nie passieren".

**Regel:** In einem Kasten wechseln Felder nie den Platz, und der Kasten
ändert seine Höhe nicht, solange man darin ist.

- Alle Felder eines Formulars stehen immer da (`Formular.felder`, `zeilen()`
  liefert jedes). Ob ein Feld gerade gilt, sagt `Feld.aktiv(werte)` (früher
  `zeigen=`, das ausblendete) — z. B. Von/Bis bei ganztägig, Tage nur
  ganztägig ohne Wiederholung, Abstand/Wiederholen bis nur mit Wiederholung,
  An Tagen nur wöchentlich, Name der Gruppe nur bei „eigene".
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
der Regel erbt). „Tage" gibt es bei Serien nicht (`mit_tage=False`).
Tests: `tests/test_kalender_formular_fest.py`.
