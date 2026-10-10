# Kalender-Ansichten A/B/C — Vorschau

**Stand 2026-10-07 (nachts): fertig.** Alle drei bedienbar (EINE Auswahl,
dieselben Kästen); Anlegen/Ändern im **Modal** (alle Felder auf einmal:
Titel, Tag, Ganztägig/Tage, Von, Bis = Uhrzeit oder Dauer, Wiederholung mit
Intervall/Wochentagen/bis, Ort; ↑↓/Tab Feld, ←→ Auswahl, Enter speichert);
B: ←→ Tag, ↑↓ Woche, Tab Termin des Tages, m/M Monat; C: ↑↓ Termin, ←→ Tag,
w/W Woche. Der alte Kalender ist raus, der Kalender startet in A, `v` dreht
A → B → C. Im Kasten ist „/" Text (öffnete vorher die Befehlszeile).
Speichern hing nach dem Google-Sync (500+ Dateien, 2 s neu parsen): jetzt
Datei-Cache im .ics-Speicher, 0,3 s.

**Stand 2026-10-07 (Etappe 1): A ist bedienbar wie calcurse** — Tasten aus
calcurses eigener Tastendatei und Hilfe: ↑↓ Termin, ←→ Tag, t/T w/W m/M y/Y
springen, g gehe zu, Tab Kasten (Termine → Kalender → TODO), Enter ansehen,
a/e/d anlegen/ändern/löschen, r wiederholen (t/w/m/j, alle wie viele, bis),
c/p kopieren/einfügen, im TODO-Kasten a/e/d, ! erledigt (X), +/- Reihenfolge.
Fragen stehen unten wie bei calcurse. Ergänzungen: „nur dieser Tag oder
alle?" bei Routinen/Spannen (Handy-Kalender), ganztägig über mehrere Tage,
Wochentage bei wöchentlich, Kollisions-Rückfrage vor dem Speichern (j/n).
Logik: `tui/ansichten/kalender_werkzeuge.py`, Tasten: `kalender_bedienung.py`,
Backend: `core/kalender_bearbeiten.py` + Routen in `ui/routen/kalender.py`.
B/C bleiben bis Etappe 2 Anzeige; danach fliegt der alte Kalender raus.

**Stand 2026-10-07 (abends): eingehängt.** Im Kalender dreht `v`: der jetzige
Kalender → A Tagesliste → B Monatsraster → C Zeitachse → zurück zum
jetzigen (`naechste_ansicht`, None = jetziger). Woche↔Monat im jetzigen
Kalender jetzt mit **Tab**. A/B/C sind reine Anzeige (Sasha): ←→ blättern
(A/B monatsweise, C wochenweise), `0` heute, `x` erledigte, `esc` zu;
`a/e/d` bearbeiten nur im jetzigen Kalender. Daten über denselben
`/api/calendar` (`DATENANSICHT`), gewählte Ansicht gilt nur pro Sitzung.
↑↓ in C gibt es nicht: die Achse passt sich selbst der Höhe an. Code:
`Kalender._taste_stil` / `_kal_stil` in `tui/ansichten/kalender.py`; Test
mit echter TUI: `tests/test_kalender_ansichten_tui.py`.

**Stand 2026-10-06:** Die drei Entwürfe für den TUI-Kalender sind gebaut, aber
**noch nicht eingehängt**: reine Funktionen in `tui/ansichten/kalender_ansichten.py`
(Daten von `/api/calendar` rein → Zeilen aus (Text, Farbrolle) raus), Taste `v`
schaltet A → B → C → A (`naechste_ansicht`). Ob und wie sie in die (gerade
zerlegte) TUI kommen, entscheidet Sasha. Unten die Ausgabe für die
Beispieltermine des Entwurfs, als reiner Text (Farben fehlen hier; farbig:
`scripts/kalender_vorschau.py` im Terminal).

**2026-10-07:** Modul nach `tui/ansichten/` gezogen (reine Helfer neben
`kalender.py`, Bauplan [tui_bauplan.md](../system/tui_bauplan.md)), samt
Beispieldaten. Einhängen wartet auf eine Entscheidung: **`v` ist im
Kalender schon belegt** (`v`/`V`/Tab = Woche↔Monat, auch aus der
Listen-Sidebar heraus).

## Die drei Ansichten

- **A — Tagesliste + Kästen, wie calcurse** (Monatsdaten; seit 07.10.2026
  nach Sashas calcurse-Bild): Kastentitel mittig IM Kasten mit `├──┤`
  darunter, der aktive Kasten „Termine" mit Rahmen in Akzentfarbe (Rolle
  `k_akzent`, siehe „Ein Farbschema" unten; bis 09.10.2026 calcurse-Rot 196). **Nur 3 Tage ab `ref`,
  gleich hoch verteilt** (Sasha: lieber wenige mit Luft als viele gequetscht,
  Woche/Monat sind B/C) — ←→ blättert in A deshalb **tageweise**; was in
  einen Tagesblock nicht passt, wird still abgeschnitten (kein „noch n
  tage"). Je Tag: Datum rechtsbündig, Termine zweizeilig (`- 14:00 ->
  15:00` / Titel; Routinen `*`), Spannen mit `..:..`-Pfeilen, leere Tage
  `--`, Linie zwischen den Tagen. Rechts „Kalender" (KW, heute `[ 7]`) und
  **„TODO"** = offene Punkte der Wochenliste (`weekplan` aus
  `/api/calendar`, nummeriert; abgehakte nur mit `x`). Unten der **rote
  Statusbalken** über die ganze Breite (`[ Mi 2026-10-07 | 09:40 ] ──>
  18:00 :: Parkour <`). Unter 86 Spalten bleibt nur die Terminliste.
- **B — Monatsraster** (nach calcure, Monatsdaten): Termine in den Zellen mit
  Anfangszeit, Ganztägiges als farbiges Band, jede Spanne als **ein** Balken
  über ihre Zellen samt Trennern („ Fr 18:00 ━━ Wochenende Berlin ━━ So 14:00 ").
  Über die Woche hinaus: `▶` / `◀`. Wird es eng, wird zuerst der Titel gekürzt,
  von und bis bleiben.
- **C — Woche als Zeitachse** (Wochendaten): Termine als Flächen nach Dauer,
  Spannentage ohne Uhrzeit als volle Säule → durchgehende Fläche, Spannen
  reihum verschieden gefärbt, Überschneidungen nebeneinander. Bereich 08–22 Uhr,
  erweitert um jede echte Uhrzeit; ist Höhe übrig, beginnt die Achse früher.

## Warum so

- **Kein curses im Modul:** testbar ohne Terminal
  (`tests/test_kalender_ansichten.py`) und als Text vorzeigbar. Die Rollen sind
  die Wörter der TUI-Palette; `…_inv` heißt Fläche (eigenes Farbpaar, wenn
  es eins gibt, sonst `A_REVERSE`).
- **Eine Stelle für die Optik:** welche Bedeutung welche Farbrolle bekommt,
  steht nur in `ROLLE` / `SPANNEN_FARBEN` oben im Modul.
- **Ein Farbschema für A, B, C und den Kasten (09.10.2026).** Sasha: „das
  farbtheme in zentrale startansicht ist schön … der kalender passt nicht …
  mach ihn vorallem einheitlich". Die Farben stehen in `farben.KAL`, je Rolle
  Schrift + Fläche (nachts Neon auf Schwarz wie zentrale-cyber, tags
  Pastellflächen mit dunkler Pflanzenschrift wie zentrale-paper, Schrift
  ≥ 4,5:1 auf Weiß); `kontext.apply_theme` legt daraus `C["k_…"]` und
  `C["k_…_inv"]` an. Akzent (Neongrün / Salbei, seit 10.10.2026 statt
  Koralle) für Titel, Datumsköpfe, Auswahl, Statuszeile; heute Gelb /
  Butter; Spannen reihum Violett, Orange, Pink, Himmel; Sa/So helles Cyan /
  Tiefwasser.
- **Farbe je Titel (10.10.2026).** Sasha: „im stundenplan sind die meisten
  felder einfach grau, manche so grell türkis, wieso?" — vorher hieß Grau
  Routine, Türkis Einmal-Termin. Jetzt bekommt jeder Titel fest eine von 12
  Farben, Serie oder einzeln, in A, B und C gleich.
- **Kurse statt Titel (10.10.2026).** Sasha: „manche kurse heißen leicht
  anderes, sind aber dieselben. exphy = experimentalphysik … ich habe nur 4
  kurse." Die Farbe hängt am **ersten Wort** ohne „@ Ort"
  (`titel_schluessel`; „Analysis Saalübung" = „Analysis I"), Kurzformen in
  `KURZFORMEN` (`exphy` → `experimentalphysik`). Was in den geladenen Daten
  ≥ 2× vorkommt, bekommt beim ersten Auftauchen fest die nächste freie Farbe
  in `RANGFOLGE` (Cyan, Orange, Pink, Meergrün, Violett …; häufigste zuerst)
  — garantiert verschieden, gespeichert in
  `~/.local/state/zentrale/kalender_farben.json` (`ZENTRALE_KALENDER_FARBEN`,
  in Tests umgelenkt), damit nichts wandert. Einmaliges rechnet sich seine
  Farbe (crc32) und belegt keinen Platz. Farbe neu würfeln: Eintrag aus der
  Datei löschen. Selbst wählbare Farbe je Termin wäre iCal `COLOR` (RFC 7986).
- **Nie breiter als erlaubt:** alles läuft über eine Leinwand, die am Rand
  abschneidet; Titel enden mit „…".
- **Platz:** offene Apps haben die volle Fensterbreite (`DASH["an"]` aus), der
  Kalender-Kasten ist bei 140 Spalten innen 136 breit, bei 200 dann 196. Im
  alten 3-Spalten-Dashboard wären es ~67 (140) bzw. ~96 (200).

## Vorschau

### 136 Spalten × 30 Zeilen

```text
── Ansicht A (tagesliste) · 136×30 ────────────────────────────────────────────────────────────────────────────────────────────────────────
┌───────────────────────────────────────────────────────────────────────────────────────────────┐ ┌────────────────────────────────────┐
│                                            Termine                                            │ │              Kalender              │
├───────────────────────────────────────────────────────────────────────────────────────────────┤ ├────────────────────────────────────┤
│                                                                     Mittwoch, 7. Oktober 2026 │ │            Oktober 2026            │
│  - 10:00 -> 18:00                                                                             │ │       Mo  Di  Mi  Do  Fr  Sa  So   │
│    Messe                                                                                      │ │  40   28  29  30   1   2 [ 3]  4   │
│                                                                                               │ │  41    5   6   7   8   9  10  11   │
│                                                                                               │ │  42   12  13  14  15  16  17  18   │
│                                                                                               │ │  43   19  20  21  22  23  24  25   │
│                                                                                               │ │  44   26  27  28  29  30  31   1   │
│───────────────────────────────────────────────────────────────────────────────────────────────│ └────────────────────────────────────┘
│                                                                   Donnerstag, 8. Oktober 2026 │ ┌────────────────────────────────────┐
│  - 09:00 -> 17:00                                                                             │ │                TODO                │
│    Messe                                                                                      │ ├────────────────────────────────────┤
│                                                                                               │ │ nichts offen                       │
│  * 10:00 -> 11:00                                                                             │ │                                    │
│    Geige                                                                                      │ │                                    │
│                                                                                               │ │                                    │
│───────────────────────────────────────────────────────────────────────────────────────────────│ │                                    │
│                                                                      Freitag, 9. Oktober 2026 │ │                                    │
│  - 10:00 -> 14:00                                                                             │ │                                    │
│    Messe                                                                                      │ │                                    │
│                                                                                               │ │                                    │
│  - 18:00 -> ..:..                                                                             │ │                                    │
│    Wochenende Berlin                                                                          │ │                                    │
│                                                                                               │ │                                    │
│                                                                                               │ │                                    │
│                                                                                               │ │                                    │
└───────────────────────────────────────────────────────────────────────────────────────────────┘ └────────────────────────────────────┘
 [ Sa 2026-10-03 | 10:41 ] ──> 18:30 :: Parkour <
 ←→ tag · 0 heute · v monat · esc zurück

── Ansicht B (monat) · 136×30 ────────────────────────────────────────────────────────────────────────────────────────────────────────
 KALENDER · OKTOBER 2026
  Mo                 Di                 Mi                 Do                 Fr                 Sa                 So
 ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────┬──────────────────┐
 │                  │                  │                  │1                 │2                 │ 3                │4                 │
 │                  │                  │                  │10:00 Geige       │                  │Tag der Dt. Einhe…│                  │
 │                  │                  │                  │                  │                  │18:30 Parkour     │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │5                 │6                 │7                 │8                 │9                 │10                │11                │
 │                  │                  │ Mi 10:00 ━━ Messe ━━ Fr 14:00                          │                  │                  │
 │                  │                  │                  │                  │ Fr 18:00 ━━ Wochenende Berlin ━━ So 14:00              │
 │14:00 Zahnarzt    │10:00 Geige       │                  │10:00 Geige       │                  │18:30 Parkour     │                  │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │12                │13                │14                │15                │16                │17                │18                │
 │                  │10:00 Geige       │19:00 Kino        │10:00 Geige       │                  │18:30 Parkour     │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │19                │20                │21                │22                │23                │24                │25                │
 │                  │10:00 Geige       │                  │10:00 Geige       │                  │18:30 Parkour     │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 ├──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┼──────────────────┤
 │26                │27                │28                │29                │30                │31                │                  │
 │                  │10:00 Geige       │                  │10:00 Geige       │                  │18:30 Parkour     │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 │                  │                  │                  │                  │                  │                  │                  │
 └──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┴──────────────────┘


 ←→ monat · 0 heute · v woche · esc zurück

── Ansicht C (woche) · 136×30 ────────────────────────────────────────────────────────────────────────────────────────────────────────
┌─ WOCHE 41 · 05.–11. OKTOBER ─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│       Mo 05.            Di 06.            Mi 07.            Do 08.            Fr 09.            Sa 10.            So 11.             │
│06:00  ··························································································↔ Woche…··········→14 Wochenende B…· │
│                                                                                                 ████████          █████████████████  │
│                                                                                                 ████████          █████████████████  │
│08:00  ··························································································████████··········█████████████████· │
│                                                             Messe                               ████████          █████████████████  │
│                                                             ████████                            ████████          █████████████████  │
│10:00  ··················10–11 Geige      ·10–18 Messe      ·████████·Geige   ·10–14 Messe      ·████████··········█████████████████· │
│                         █████████████████ █████████████████ ████████ ████████ █████████████████ ████████          █████████████████  │
│                                           █████████████████ ████████          █████████████████ ████████          █████████████████  │
│12:00  ····································█████████████████·████████··········█████████████████·████████··········█████████████████· │
│                                           █████████████████ ████████          █████████████████ ████████          █████████████████  │
│                                           █████████████████ ████████          █████████████████ ████████          █████████████████  │
│14:00  14–15 Zahnarzt   ···················█████████████████·████████····························████████···························· │
│       █████████████████                   █████████████████ ████████                            ████████                             │
│                                           █████████████████ ████████                            ████████                             │
│16:00  ····································█████████████████·████████····························████████···························· │
│                                           █████████████████ ████████                            ████████                             │
│                                           █████████████████                                     ████████                             │
│18:00  ········································································18→ Wochenende B…·████████·Parkour ··················· │
│                                                                               █████████████████ ████████ ████████                    │
│                                                                               █████████████████ ████████ ████████                    │
│20:00  ········································································█████████████████·████████···························· │
│                                                                               █████████████████ ████████                             │
│                                                                               █████████████████ ████████                             │
│22:00  ········································································█████████████████·████████···························· │
│                                                                               █████████████████ ████████                             │
│                                                                               █████████████████ ████████                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 ←→ woche · 0 heute · v bearbeiten · esc zurück

```

### 110 Spalten × 30 Zeilen

```text
── Ansicht A (tagesliste) · 110×30 ──────────────────────────────────────────────────────────────────────────────
┌────────────────────────────────────────────────────────────────────────┐ ┌─────────────────────────────────┐
│                                Termine                                 │ │            Kalender             │
├────────────────────────────────────────────────────────────────────────┤ ├─────────────────────────────────┤
│                                              Mittwoch, 7. Oktober 2026 │ │          Oktober 2026           │
│  - 10:00 -> 18:00                                                      │ │     Mo  Di  Mi  Do  Fr  Sa  So  │
│    Messe                                                               │ │40   28  29  30   1   2 [ 3]  4  │
│                                                                        │ │41    5   6   7   8   9  10  11  │
│                                                                        │ │42   12  13  14  15  16  17  18  │
│                                                                        │ │43   19  20  21  22  23  24  25  │
│                                                                        │ │44   26  27  28  29  30  31   1  │
│────────────────────────────────────────────────────────────────────────│ └─────────────────────────────────┘
│                                            Donnerstag, 8. Oktober 2026 │ ┌─────────────────────────────────┐
│  - 09:00 -> 17:00                                                      │ │              TODO               │
│    Messe                                                               │ ├─────────────────────────────────┤
│                                                                        │ │ nichts offen                    │
│  * 10:00 -> 11:00                                                      │ │                                 │
│    Geige                                                               │ │                                 │
│                                                                        │ │                                 │
│────────────────────────────────────────────────────────────────────────│ │                                 │
│                                               Freitag, 9. Oktober 2026 │ │                                 │
│  - 10:00 -> 14:00                                                      │ │                                 │
│    Messe                                                               │ │                                 │
│                                                                        │ │                                 │
│  - 18:00 -> ..:..                                                      │ │                                 │
│    Wochenende Berlin                                                   │ │                                 │
│                                                                        │ │                                 │
│                                                                        │ │                                 │
│                                                                        │ │                                 │
└────────────────────────────────────────────────────────────────────────┘ └─────────────────────────────────┘
 [ Sa 2026-10-03 | 10:41 ] ──> 18:30 :: Parkour <
 ←→ tag · 0 heute · v monat · esc zurück

── Ansicht B (monat) · 110×30 ──────────────────────────────────────────────────────────────────────────────
 KALENDER · OKTOBER 2026
  Mo             Di             Mi             Do             Fr             Sa             So
 ┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
 │              │              │              │1             │2             │ 3            │4             │
 │              │              │              │10:00 Geige   │              │Tag der Dt. E…│              │
 │              │              │              │              │              │18:30 Parkour │              │
 │              │              │              │              │              │              │              │
 ├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
 │5             │6             │7             │8             │9             │10            │11            │
 │              │              │ Mi 10:00 ━━ Messe ━━ Fr 14:00              │              │              │
 │              │              │              │              │ Fr 18:00 ━━ Wochenende Berlin ━━ So 14:00  │
 │14:00 Zahnarzt│10:00 Geige   │              │10:00 Geige   │              │18:30 Parkour │              │
 ├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
 │12            │13            │14            │15            │16            │17            │18            │
 │              │10:00 Geige   │19:00 Kino    │10:00 Geige   │              │18:30 Parkour │              │
 │              │              │              │              │              │              │              │
 │              │              │              │              │              │              │              │
 ├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
 │19            │20            │21            │22            │23            │24            │25            │
 │              │10:00 Geige   │              │10:00 Geige   │              │18:30 Parkour │              │
 │              │              │              │              │              │              │              │
 │              │              │              │              │              │              │              │
 ├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
 │26            │27            │28            │29            │30            │31            │              │
 │              │10:00 Geige   │              │10:00 Geige   │              │18:30 Parkour │              │
 │              │              │              │              │              │              │              │
 │              │              │              │              │              │              │              │
 └──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘


 ←→ monat · 0 heute · v woche · esc zurück

── Ansicht C (woche) · 110×30 ──────────────────────────────────────────────────────────────────────────────
┌─ WOCHE 41 · 05.–11. OKTOBER ───────────────────────────────────────────────────────────────────────────────┐
│       Mo 05.        Di 06.        Mi 07.        Do 08.        Fr 09.        Sa 10.        So 11.           │
│06:00  ······································································↔ Woc…········→14 Wochenen…·   │
│                                                                             ██████        █████████████    │
│                                                                             ██████        █████████████    │
│08:00  ······································································██████········█████████████·   │
│                                                 Messe                       ██████        █████████████    │
│                                                 ██████                      ██████        █████████████    │
│10:00  ··············10–11 Geige  ·10–18 Messe  ·██████·Geige ·10–14 Messe  ·██████········█████████████·   │
│                     █████████████ █████████████ ██████ ██████ █████████████ ██████        █████████████    │
│                                   █████████████ ██████        █████████████ ██████        █████████████    │
│12:00  ····························█████████████·██████········█████████████·██████········█████████████·   │
│                                   █████████████ ██████        █████████████ ██████        █████████████    │
│                                   █████████████ ██████        █████████████ ██████        █████████████    │
│14:00  Zahnarzt     ···············█████████████·██████······················██████······················   │
│       █████████████               █████████████ ██████                      ██████                         │
│                                   █████████████ ██████                      ██████                         │
│16:00  ····························█████████████·██████······················██████······················   │
│                                   █████████████ ██████                      ██████                         │
│                                   █████████████                             ██████                         │
│18:00  ························································18→ Wochenen…·██████·Parko…···············   │
│                                                               █████████████ ██████ ██████                  │
│                                                               █████████████ ██████ ██████                  │
│20:00  ························································█████████████·██████······················   │
│                                                               █████████████ ██████                         │
│                                                               █████████████ ██████                         │
│22:00  ························································█████████████·██████······················   │
│                                                               █████████████ ██████                         │
│                                                               █████████████ ██████                         │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
 ←→ woche · 0 heute · v bearbeiten · esc zurück

```

### 70 Spalten × 30 Zeilen

```text
── Ansicht A (tagesliste) · 70×30 ──────────────────────────────────────
┌────────────────────────────────────────────────────────────────────┐
│                              Termine                               │
├────────────────────────────────────────────────────────────────────┤
│                                          Mittwoch, 7. Oktober 2026 │
│  - 10:00 -> 18:00                                                  │
│    Messe                                                           │
│                                                                    │
│                                                                    │
│                                                                    │
│                                                                    │
│────────────────────────────────────────────────────────────────────│
│                                        Donnerstag, 8. Oktober 2026 │
│  - 09:00 -> 17:00                                                  │
│    Messe                                                           │
│                                                                    │
│  * 10:00 -> 11:00                                                  │
│    Geige                                                           │
│                                                                    │
│────────────────────────────────────────────────────────────────────│
│                                           Freitag, 9. Oktober 2026 │
│  - 10:00 -> 14:00                                                  │
│    Messe                                                           │
│                                                                    │
│  - 18:00 -> ..:..                                                  │
│    Wochenende Berlin                                               │
│                                                                    │
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
 [ Sa 2026-10-03 | 10:41 ] ──> 18:30 :: Parkour <
 ←→ tag · 0 heute · v monat · esc zurück

── Ansicht B (monat) · 70×30 ──────────────────────────────────────
 KALENDER · OKTOBER 2026
  Mo       Di       Mi       Do       Fr       Sa       So
 ┌────────┬────────┬────────┬────────┬────────┬────────┬────────┐
 │        │        │        │1       │2       │ 3      │4       │
 │        │        │        │Geige   │        │Tag der…│        │
 │        │        │        │        │        │Parkour │        │
 │        │        │        │        │        │        │        │
 ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤
 │5       │6       │7       │8       │9       │10      │11      │
 │        │        │ Mi 10:00 Messe Fr 14:00  │        │        │
 │        │        │        │        │ Fr 18:00 Woche… So 14:00 │
 │Zahnarzt│Geige   │        │Geige   │        │Parkour │        │
 ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤
 │12      │13      │14      │15      │16      │17      │18      │
 │        │Geige   │Kino    │Geige   │        │Parkour │        │
 │        │        │        │        │        │        │        │
 │        │        │        │        │        │        │        │
 ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤
 │19      │20      │21      │22      │23      │24      │25      │
 │        │Geige   │        │Geige   │        │Parkour │        │
 │        │        │        │        │        │        │        │
 │        │        │        │        │        │        │        │
 ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤
 │26      │27      │28      │29      │30      │31      │        │
 │        │Geige   │        │Geige   │        │Parkour │        │
 │        │        │        │        │        │        │        │
 │        │        │        │        │        │        │        │
 └────────┴────────┴────────┴────────┴────────┴────────┴────────┘


 ←→ monat · 0 heute · v woche · esc zurück

── Ansicht C (woche) · 70×30 ──────────────────────────────────────
┌─ WOCHE 41 · 05.–11. OKTOBER ───────────────────────────────────────┐
│       Mo 05.  Di 06.  Mi 07.  Do 08.  Fr 09.  Sa 10.  So 11.       │
│06:00  ········································Wo…·····→14 Wo…·     │
│                                               ███     ███████      │
│                                               ███     ███████      │
│08:00  ········································███·····███████·     │
│                               Me…             ███     ███████      │
│                               ███             ███     ███████      │
│10:00  ········Geige  ·Messe  ·███·Ge…·Messe  ·███·····███████·     │
│               ███████ ███████ ███ ███ ███████ ███     ███████      │
│                       ███████ ███     ███████ ███     ███████      │
│12:00  ················███████·███·····███████·███·····███████·     │
│                       ███████ ███     ███████ ███     ███████      │
│                       ███████ ███     ███████ ███     ███████      │
│14:00  Zahnar…·········███████·███·············███·············     │
│       ███████         ███████ ███             ███                  │
│                       ███████ ███             ███                  │
│16:00  ················███████·███·············███·············     │
│                       ███████ ███             ███                  │
│                       ███████                 ███                  │
│18:00  ································18→ Wo…·███·Pa…·········     │
│                                       ███████ ███ ███              │
│                                       ███████ ███ ███              │
│20:00  ································███████·███·············     │
│                                       ███████ ███                  │
│                                       ███████ ███                  │
│22:00  ································███████·███·············     │
│                                       ███████ ███                  │
│                                       ███████ ███                  │
└────────────────────────────────────────────────────────────────────┘
 ←→ woche · 0 heute · v bearbeiten · esc zurück

```

Neu erzeugen: `venv/bin/python scripts/kalender_vorschau.py --farbe aus --breite 136 --hoehe 30`
(Beispieltermine: `tui/ansichten/kalender_beispiel.py`).
