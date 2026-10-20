# Kalender: Jetzt-Linie (seit 2026-10-20)

Sasha: „füge einen goldenen kleinen strich mit kleinem pfeil links dran
hinzu, der genau anzeigt, wo die zeit grade runterläuft, in der
wochenansicht".

Code: `tui/ansichten/kalender_jetzt.py` (reine Funktionen), eingehängt in
`kalender_ansichten.ansicht_c` (nach `_c_achse`, das jetzt `(lo, takt,
zeilen)` des Fensters zurückgibt) und `_a_liste`. Tests:
`tests/test_kalender_jetzt_tui.py`.

## Aussehen

- **C (Woche):** in der Spalte von heute, zur Uhrzeit auf die nächstliegende
  Rasterzeile gerundet: `▸` im Spalt links der Tagesspalte, dann dünn `─`
  über die Spalte. Nur wenn heute in der gezeigten Woche liegt und die
  Uhrzeit im Fenster. Golden übermalt werden nur freie Zellen (leer,
  Punktlinie, Phasen-Muster, Glas über Freiem); im Leerraum eines Termins
  läuft der Strich in dessen Schrift weiter, Text und Deadlines bleiben.
- **A (Liste):** `▸` vor dem laufenden, sonst dem nächsten Termin von heute
  (ohne Ganztägiges, Ausgefallenes, Deadlines).
- Gegen die Deadline (rot, dick `━`, `⚑`) nicht zu verwechseln.

## Regler

- Farbe: `farben.KAL["jetzt"]` — nachts Gold 220 (nicht „heute" 227, nicht
  Bernstein 214), tags dunkles Gold 136 (3,3:1 auf Weiß; Strich, kein Text).
- `kalender_jetzt.PFEIL`, `STRICH`, `C_ZEIGEN`, `A_ZEIGEN`, `DURCH_BLOCK`
  (False: über Terminen nur der Pfeil).

## Uhr

Jedes Zeichnen fragt `uhr.jetzt()` (core/uhr.py), Spalte nach dem echten
Datum — nicht nach `today` der gepufferten Antwort. Die TUI zeichnet
mindestens alle 250 ms neu (`stdscr.timeout`), die Linie wandert von selbst.
