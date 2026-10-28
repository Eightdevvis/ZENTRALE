# Wo ein Zustand lebt: rohes ZENTRALE oder App (Sasha, 2026-10-29)

**Die Prüffrage vor jedem Entwurf: Gehört das zur App oder zum rohen
ZENTRALE-Paket?** Sasha: „die apps syncen wir ohne gnade, das rohe zentrale
ist halt einfach nur das gestell was man pro node hat … was halt verschieden
sein kann, weils halt nur so basic stuff speichert und viel näher auf
maschinen ebene is als die apps." (ZENTRALE wird so im Kern ein
Betriebssystem, die Apps laufen obendrauf.)

| Schicht | Was dazugehört | Synct? |
|---|---|---|
| **Rohes ZENTRALE** — das Gestell je Knoten: Hub („die Pforte der Pforten"), Store, die zwingenden Start-Adapter; sonst nichts ab Werk | Anmeldung und Zugang zur Mitte, Rechte, Steckplätze; welche Apps auf diesem Knoten stationiert sind (`abgleich_apps`, beim Einrichten gefragt: „was planst du hier?") und wie viel man von anderen sieht (z. B. ihre Nachrichten im Postfach); Maschinennahes (Bildschirm, Hardware, Pfade) | nein — darf je Knoten verschieden sein |
| **App-Instanz** — alles andere, auch die Vernetzungskarte | ALLES über die App: Einstellungen (z. B. die Quelle eines Kalenders), Daten, Gedächtnis | **ja, ohne Gnade** — auf jedem Knoten, an dem sie läuft, 1:1 dieselbe |

Sashas Bild dazu: ein Geschäftsmann mit Standorten (Küste, Inland) und
Arbeitern (Apps). Er entscheidet je Standort, wer dort stationiert ist —
aber dieselbe Sekretärin an zwei Standorten ist dieselbe Sekretärin: was er
im Inland mit ihr gemacht hat, weiß sie an der Küste.

- Soll eine App irgendwo anders arbeiten (z. B. Daten aus Google statt aus
  der ZENTRALE-Cloud), ist das eine **zweite App-Instanz** — beide dürfen
  gleichzeitig laufen. Nie eine Instanz, die je Knoten anders ist.
- Das rohe Paket kennt keine Einstellung irgendeiner App. Was dort neu
  dazukommt, bleibt maschinennah und klein; im Zweifel ist es App.
- Anlass: ein Kalender-Schalter „Google oder Cloud je Gerät" (1f32e6a),
  umgebaut zur Einstellung der Kalender-App.
