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
- **Glas (Ebene „uncommitted", 10.10.2026):** `Leinwand.glas(y, x, breite,
  glasrolle, text)` legt eine Scheibe über einen Bereich: die Zeichen darunter
  bleiben, ihre Rolle wird zu `„<darunter>~<glas>"` (Label: `„…~<glas>~<schrift>"`).
  `kalender.py` (`_glas_attr`) mischt den Grund der Rolle darunter mit der
  Kursfläche (`farben.DECKKRAFT[…]["glas"]`, gerundet über `pixel.bunt`) und
  holt das Paar über `z.pix_attr`; ohne 256 Farben oder bei vollen Paaren die
  alte blasse Fläche (`k_…_blass_inv`). In C bekommen uncommitted eigene Bahnen
  über die volle Spalte, nach den festen gezeichnet; der gewählte bleibt deckend.
- **Tagesrhythmus (Phasen, 10.10.2026).** Sasha: „fürs coming down ein paar
  sterne, wolken usw eingemalt wie ein nachthimmel, ab 10 uhr ein par z z z …
  eine leichte hintergrund ebene". Phasen (Ebene `rhythmus`, Feld `motiv`,
  Kern: `kalender_ics_bauplan.md`) sind **keine Termine**: `_tag_eintraege`
  lässt sie weg (nicht wählbar, keine Zeile in A/B, kein Block, keine Kursfarbe).
  In **C** malt `kalender_motive.zeichne_spalte` ihren Zeitbereich in der
  Tagesspalte mit wenigen einspaltigen Zeichen (nachthimmel ⋆✦✧☁☾, schlaf zZᶻ,
  essen ∘◦∪, sonne ✺✹✶, fokus ⋄▫, sport ⌃∧, ruhe ~∼, unterwegs ›⇢⋯) — vor
  den Terminen, die deckend darüber liegen; die Punktlinien lassen den Zeichen
  Platz. Gestreut deterministisch (crc32 aus Tag, Uhrzeit der Zeile, Spalte;
  Schachbrett), also still beim Neuzeichnen und Scrollen. Über Mitternacht:
  am Tag des Beginns bis 24:00, am Folgetag ab 0:00 (für den Montag holt die
  Bedienung den Sonntag davor nach). Das Fenster 08–22 bleibt fest, Phasen
  zählen nicht für ▲/▼. **Regler** in `tui/ansichten/kalender_motive.py`
  (`MUSTER`: Zeichen + Dichte je Motiv, `SCHACHBRETT`, `PUNKTLINIE_WEICHT`,
  `OHNE_ENDE_MINUTEN`, `A_HINWEIS`, `A_ZEICHEN`), Farben in
  `farben.MOTIV_FARBEN` (gedämpft: nachts ≈ 3–5:1 auf Schwarz, tags ≈ 2–3:1
  auf Weiß; ein Farbpaar je Motiv, Rolle `k_m_<motiv>`). In **A** steht
  (abschaltbar, `A_HINWEIS`) leise links im Tageskopf „∘ 10:00 ☾ 21:30 ᶻ 23:00".
- **Rhythmus einstellen (Taste R, 10.10.2026).** Sasha: „bau einfach das
  gerüst dafür in dem ich es selbst dann einstellen kann, mach alles möglich".
  R öffnet in A/B/C den Kasten „Rhythmus" (`kalender_phasen.PhasenListe`, Daten
  von `GET /api/calendar/phasen` und `/motive`): ↑↓ wählen, **n** neu, **e**/Enter
  ab jetzt ändern, **d** löschen, **t** nur am gewählten Tag, **z** für einen
  Zeitraum (Vorgabe: 3 Tage). Formular: Name, Motiv, Von, Bis (vor Von = endet
  am Folgetag), Wiederholung (täglich / werktags / wochenende / an Tagen + Abstand;
  eine nicht abbildbare Regel bleibt „wie bisher"), gültig ab/bis. t/z gehen
  beide über `POST /api/calendar/routine/zeitraum` (ein Tag = von gleich bis;
  „Wie die Regel: ja" setzt die Tage zurück); Zeit gilt am Tag des Beginns.
  Nach dem Speichern und bei Esc im Formular geht die Liste wieder auf.
- **Gruppen im Monat (B, 10.10.2026).** Sasha: „in der monatsansicht seh ich
  einfach lieber uni uni uni statt jeden tag welche fächer genau" — Form
  „08:30–16:00 Uni". `kalender_gruppen.zusammenfassen` macht aus allen
  Einträgen eines Tages mit gleicher `kategorie` (≠ „keine"; Spannen,
  Ganztägiges, Ausgeschaltetes bleiben einzeln) EINE Zeile: erste
  Anfangszeit bis letztes Ende, Name aus `/api/calendar/kategorien` (Rückfall
  `kalender_gruppen.NAMEN`) bzw. `kategorie_name`. Wird es eng: „08:30–16 Uni",
  „08:30 Uni", „Uni". Farbe: eigener Platz in derselben Farbtabelle
  (`gruppe:uni`). A und C zeigen weiter jedes Fach. Die Bedienung wählt in B
  aus genau dieser Liste (`kw.eintraege(…, monat=True)`): Tab springt auf die
  Gruppe, Enter zeigt die Glieder, e/d/r/c/u sagen „einzeln ändern in A oder C".
- **Gruppe setzen (10.10.2026):** im Formular (a/e) das Feld **Gruppe**
  (keine / Uni / Arbeit / eigene → Name; nicht im Kasten „nur dieser Tag" —
  die Gruppe gilt für die ganze Serie); geändert wird per Kennung
  (`POST /api/calendar/kategorie`), neu angelegt mit `kategorie` im Body.
  Die Taste G (ganzer Kurs) ist seit 11.10.2026 raus (Sasha: „wollte ich gar nicht").
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

## Monat nur ansehen, Tasten-Schema (10.10.2026)
- **B ist nur Ansicht.** Sasha: „besser wenn man auf einem datum im monat enter
  macht, dass man auf die tagansicht kommt und dort richtig bearbeiten kann,
  und in monat dann keine". Enter öffnet den Tag in A („geliehen", Esc führt
  zurück in den Monat); Bearbeitungstasten melden nur einen Hinweis.
- **Jede Ansicht merkt sich ihren Stand** (Tag, Termin, Fenster) in
  `K["staende"]`; der Sprung aus dem Monat überschreibt den von A nicht.
  Beim Öffnen des Kalenders stehen alle wieder auf heute.
- **Ansehen-Fenster** schließt nur noch bei einer echten Taste (der Takt der
  Hauptschleife, `ch == -1`, schloss es sofort).
- **Rückfragen, ein Schema** (`kalender_werkzeuge.py`, über `_wahl_umfang`):
  j/n · a alle · t nur dieser Tag · z Zeitraum · Auswahl per Anfangsbuchstabe
  (u Uni, k keine, e eigene), keine Ziffern; Esc bricht ab.

## Titel aus Liste/Projekt in der TUI (10.10.2026)
Kern: Abschnitt „quelle" in [kalender_ics_bauplan.md](kalender_ics_bauplan.md).
Sasha: „im container steht das dann als ‚titel' wie ein normaler termin titel
und unten drunter weniger stark sichtbar dezent ‚titel der liste' … ansonsten
soll sich das ganze ganz normal als termin bearbeiten lassen".
- **Anzeige** (`kalender_ansichten.quelle_info`/`quelle_unterzeile`): Titel =
  `titel_live`, darunter gedämpft der Name der Liste — in A als eigene Zeile
  unter dem Titel (Luft zum nächsten Termin bleibt), in C als zweite
  Blockzeile. B zeigt nur den Live-Titel. `leer` → „<Liste> — alles
  erledigt" gedämpft, ohne Namenszeile; `fehlt` → label + „liste fehlt".
  **Farbe fest nach der Quelle** (`kurs_rolle`, Schlüssel `quelle:<id>` in
  der FARBTABELLE), sonst wechselte der Block bei jedem Abhaken die Farbe.
- **C einheitlich** (Sasha: „wieso divergieren manche termine, bei manchen
  steht die uhrzeit davor bei manchen nicht?", `_c_zeilen`): Zeile 1 ist
  immer nur der Titel; ab 2 Zeilen Höhe darunter gedämpft die Zeit
  („10–12", „10:15–11:45"; Spannen ihre Marke 18→ / →14 / ↔), bei
  Quellen-Terminen erst die Liste, dann die Zeit. Einzeilige Blöcke: nur
  der Titel. Gilt auch für Glas und den gewählten Eintrag.
- **Leise Schrift auf Fläche:** Rolle `<fläche>_inv_leise` (`ka.LEISE`);
  `kalender.py _leise_attr` mischt die Schrift zum Grund (≥ 3:1), ohne 256
  Farben `A_DIM`.
- **Typ liste statt eigener Taste (seit 11.10.2026):** Sasha: „dann wird der
  listentermin zu nem termintypen und nicht zu so nem extra shortcut den
  kannst dann rausnehmen". Ein Listen-Termin entsteht über `a` → Formular →
  **Advanced** → Typ `liste` (Abschnitt „Fenster advanced" unten). Die Taste
  `A` (Shift+A, d75f21a) für „neuer Termin für eine Liste" ist raus; `A` ist
  wieder, was es vorher war: ein zweites `a` (im TODO-Kasten ohnehin
  „neue Aufgabe"). Den Kasten „welche Liste?" (`kalender_quellen.QuellenWahl`:
  ≡ Liste, ◆ Projekt, Name + was jetzt oben steht; Tippen filtert, ↑↓ wählt,
  Enter nimmt, Esc zurück ins Fenster) gibt es weiter, er liegt jetzt über
  dem Fenster. Titel: wird beim Wählen der Name der Liste, solange er leer
  ist oder noch der Name der alten Liste war; leer gespeichert = ihr Name
  (nur Rückfall). **`!`** auf einem Quellen-Termin hakt den angezeigten Punkt
  ab (`/api/lists/<lid>/items/<iid>/toggle`) → „erledigt: X — jetzt: Y".
- **Bearbeiten (e):** dasselbe Fenster. Neue/andere Liste → beim Speichern
  `POST /api/calendar/quelle` per Kennung; Typ zurück auf `normal` → danach
  „aktuellen Titel „X“ übernehmen? (j/n)" (`DELETE …/quelle`,
  `titel_uebernehmen`). Wird ein Einmal-Termin zur Wiederholung, wandert die
  Liste aus dem Fenster mit. Kopieren (c/p) nimmt Liste und Stil mit.
- **Ansehen (Enter):** Liste, „Jetzt", „Danach" (die nächsten offenen,
  neue Route `GET /api/calendar/quelle?art=&id=&n=4` → `kalender_quelle.
  vorschau`). `POST /api/calendar/spanne` und die Routine mit `freq` nehmen
  jetzt auch `quelle`.
- **Fußzeile** (`tasten_hinweis(ansicht, breite)`): drei Stufen, die längste,
  die passt (vorher in B/C bei 150 Spalten abgeschnitten); vollständig in der
  Fußleiste (`befehle.py`). Tests: `tests/test_kalender_quellen_tui.py`.

## Stylebox im Formular und der gestylte Kasten (10.10.2026)
Kern: Abschnitt „stil" in [kalender_ics_bauplan.md](kalender_ics_bauplan.md);
Bausteine: [bausteine_farbe_stil.md](../hub/bausteine_farbe_stil.md).
Sasha: „Im Terminformular gibt es NUR eine Option ‚Stylebox' … In der
Stylebox kann man den Kasten genau stylen: Rahmenstil + Rahmenfarbe,
Innenfarbe, Schriftfarbe, Innenmuster; ‚Icon hochladen' wird angezeigt,
bleibt aber gesperrt."
- **Fenster „advanced" (seit 11.10.2026, `kalender_advanced.py`):** Sasha:
  „bitte setz die stylebox unter ein eigenes fenster, also im formular für
  nen termin kann man auf ‚advanced' klicken und dort ist dann stylebox oder
  typus wählbar". Im Formular (a, e, r, „ganze Spanne", „alle termine der
  serie"; nicht „nur dieser Tag", gilt für die Serie wie die Gruppe) steht
  statt „Stylebox" und „Liste" EIN Feld **Advanced** (Feld-Art `advanced`)
  mit Zusammenfassung: „typ normal · stil keine" bzw. „typ liste: todo ·
  stil ╔═╗ · rand #ff8800"; die drei Rahmenzeichen darin farbig.
- **Tasten:** auf dem Feld öffnen Enter, Leertaste oder → das Fenster (Enter
  speichert hier also NICHT — Strg-S oder Enter auf einem anderen Feld). Im
  Fenster:

  | Taste | Wirkung |
  |---|---|
  | ↑↓ / Tab, Shift-Tab | Zeile (Typ · Liste, nur bei liste · Stylebox) |
  | ←→ / Leertaste auf **Typ** | `normal` ↔ `liste` |
  | Enter auf **Typ**, Strg-S überall | übernehmen, zurück ins Formular (Typ liste ohne Liste: Fehler, springt auf „Liste") |
  | Enter / Leertaste / → auf **Liste** | Kasten „welche Liste?" |
  | Enter / Leertaste / → auf **Stylebox** | die Stylebox (wie bisher) |
  | ⌫ / Entf auf **Stylebox** | kein Stil |
  | Esc | alles in diesem Fenster verwerfen (in Stylebox/„welche Liste?": nur die schließen) |

  Konsistent mit Formular (Enter = fertig, Strg-S = fertig, Esc = weg) und
  Stylebox (Enter nimmt, Esc zurück). Gespeichert wird erst mit dem
  Formular: neu → `quelle`/`stil` im Body, bestehend → `POST
  /api/calendar/stil` per Kennung nur bei Änderung. Gezeichnet in
  `kalender_bedienung._zeichne_advanced` (gleicher Feld-Kasten wie das
  Formular, `_zeichne_felder`), Stylebox bzw. Listen-Kasten darüber. Ansehen
  (Enter) zeigt „Stil …".
- **Anzeige** (`kalender_stil.py`, reine Funktionen): Rolle
  `$<schrift>$<grund>$<rückfall>` (Hex ohne #, leer = aus der Rückfall-Rolle);
  `kalender.py _stil_attr` macht daraus ein Paar über `pix_attr` (bunte Farben
  im 256er-Modus über `pixel.bunt`, sonst `pix_farbe`), ohne 256 Farben oder
  wenn die Paare ausgehen der Rückfall (Kursfarbe).
  - **C** der Block: Rahmen rundherum ab 4×4 Zellen, sonst nur links/rechts
    (ab 3 Spalten), darunter keiner; Fläche statt Kursfarbe (ohne Fläche
    bleibt die Kursfläche, nur der Rahmen färbt), Schrift (ohne: schwarz/weiß
    nach Helligkeit der Fläche), Muster in der leisen Schrift. Gewählt: die
    Akzentfarben, die Rahmenform bleibt.
  - **A** der Titel: davor das senkrechte Rahmenzeichen in der Rahmenfarbe,
    mit Fläche als Schild „ Uni " (+ zwei Musterzeichen), sonst in der
    Schriftfarbe.
  - **B** die Zeile in der Stilfarbe (Schrift, sonst Rahmen, sonst Fläche);
    Ganztägiges und Spannen-Balken als Fläche. Gruppen-Zeilen bleiben.
  - Ohne Stil alles wie vorher. uncommitted MIT Stil: der Stil gewinnt (kein
    Glas) — offen, ob Sasha dort lieber Glas sähe.
- Tests: `tests/test_kalender_stil_tui.py`.
- **Advanced ganz unten, ohne Vorschau (11.10.2026):** Sasha: „advanced ganz
  unten im formular haben und ohne vorschau rechts nebendran, stattdessen
  einfach nur mini erklärung". Die Zeile zeigt nur `ADVANCED_HINWEIS`
  („see for more options"); was gewählt ist, steht im Fenster selbst.
  „Verbindlich" (nur im Neu-Formular) rückt davor.
