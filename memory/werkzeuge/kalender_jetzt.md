# Kalender: Jetzt-Linie (seit 2026-10-20)

Sasha: „füge einen goldenen kleinen strich mit kleinem pfeil links dran
hinzu, der genau anzeigt, wo die zeit grade runterläuft, in der
wochenansicht".

Code: `tui/ansichten/kalender_jetzt.py` (reine Funktionen), eingehängt in
`kalender_ansichten.ansicht_c` (nach `_c_achse`, das jetzt `(lo, takt,
zeilen)` des Fensters zurückgibt) und `_a_liste`. Tests:
`tests/test_kalender_jetzt_tui.py`.

## Aussehen

Seit 21.10.2026 durchgehend sichtbar (Sasha: „ja der soll immer drüber
laufen, immer sichtbar sein, klaro.").

- **C (Woche):** in der Spalte von heute, zur Uhrzeit auf die nächstliegende
  Rasterzeile gerundet: `►` im Spalt links der Tagesspalte, dann `─` über die
  GANZE Spalte, golden — auch über Terminen, Glas, Phasen und Deadlines. Nur
  wenn heute in der gezeigten Woche liegt und die Uhrzeit im Fenster.
  - Freie Zellen (leer, Punktlinie, Phasen-Muster): `─` in „jetzt"-Gold.
  - Leerraum auf einer Fläche/Glas: `─`, Zellen mit Text (Blocktitel,
    Zeitzeile, Glas-Label) behalten ihr Zeichen — beide in goldener Schrift
    auf dem Grund der Zelle (Rolle `^<darunter>`, `kalender_jetzt.zelle`).
  - Deadline in derselben Zeile: `⚑` und Text bleiben rot, nur ihre Linie
    `━` wird golden; der goldene `►` links steht immer.
- **A (Liste):** `►` vor dem laufenden, sonst dem nächsten Termin von heute
  (ohne Ganztägiges, Ausgefallenes, Deadlines).

## Regler

- Farbe: `farben.KAL["jetzt"]` — nachts Gold 220 (nicht „heute" 227, nicht
  Bernstein 214), tags dunkles Gold 136 (3,3:1 auf Weiß).
- Über Flächen: `kalender.py _jetzt_attr` nimmt den echten Grund der Zelle
  (auch Glas-Mischung, Stylebox) und `kalender_jetzt.gold` die Theme-Farbe,
  sonst die nächste Stufe aus `GOLDSTUFEN` mit ≥ `KONTRAST_MIN` (3:1) —
  gemessen an der Farbe, die das Terminal zeigt (256er-Rundung). Tags auf
  Pastell meist 94 (135,95,0), nachts auf Neon dunkles bis Schwarz-Gold.
  Ohne 256 Farben: „k_jetzt" fett.
- `kalender_jetzt.PFEIL` (►), `STRICH`, `C_ZEIGEN`, `A_ZEIGEN`, `MARKE`.
  (`DURCH_BLOCK` ist weg: die Linie läuft immer durch.)

## Uhr

Jedes Zeichnen fragt `uhr.jetzt()` (core/uhr.py), Spalte nach dem echten
Datum — nicht nach `today` der gepufferten Antwort. Die TUI zeichnet
mindestens alle 250 ms neu (`stdscr.timeout`), die Linie wandert von selbst.
