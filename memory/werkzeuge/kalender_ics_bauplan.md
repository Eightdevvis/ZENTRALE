# Kalender auf iCalendar (.ics) — Bauplan und Umstieg

**Stand 2026-10-11:** Auf Sashas Rechnern seit Oktober **live als .ics**
(`kalender_speicher: ics` in `data/ai_config.json`, Ordner `data/kalender/`
mit `termine/`, `rhythmus/`, `uncommitted/`; Google-Sync live seit 07.10.,
Abschnitt „Stand Sync" unten). Der **Code-Default** bleibt `json`
(`core/kalender_speicher.py` `modus()`) — ein frischer Knoten ohne Einstellung
läuft also auf der alten JSON (`data/ai_calendar.json`).

**Stand 2026-10-06 (Historie):** Gebaut und getestet. Der Kalender
kann seine Daten wahlweise in der alten JSON (`data/ai_calendar.json`) oder
als iCalendar-Ordner (`data/kalender/`, eine `.ics` pro Termin, vdir-Format)
halten. Umgeschaltet wird mit der Einstellung `kalender_speicher`
(`json` | `ics`, Default `json`), umgezogen mit
`scripts/kalender_migrieren.py`, Schritte unten unter „Was Sasha tun muss".
Die öffentlichen Funktionen von `core/kalender.py` sind unverändert; nur die
Speicherschicht darunter ist getauscht. Die Prüfung an einer Kopie der
echten Daten (06.10.2026) war fehlerfrei. Google-Sync per vdirsyncer ist
vorbereitet (`deploy/vdirsyncer.config.example`, `scripts/kalender_sync.py`)
— eingerichtet am 07.10.

## Kennungen und Ablehnungen (09.10.2026)

Anlass: die KI änderte per Titel BEIDE gleichnamigen Geigenstunde-Serien.
`core/kalender_kennung.py` (Wunschliste von ASSISTANT, claude_web_plan §7):
- **Kennung** = UID im .ics-Speicher (überlebt Umbenennen/Zeit/Ort), im
  JSON-Speicher Feld `uid` (beim ersten Zugriff vergeben). `entries_in_range`
  & Co. liefern sie als `kennung` mit (Routinen-Vorkommen: die der Routine,
  Spannentage: die der Spanne). `alle_eintraege()` statt `_load_raw`.
- **Per Kennung:** `eintrag_aendern/_loeschen` (einmal + Spanne mit
  `times`/`enden` je Tag, `von`/`bis` verschieben), `routine_aendern/
  _loeschen/_absagen/_tag_aendern/_pause`.
- **Ablehnen statt still korrigieren:** `KalenderAbgelehnt(code, grund)`,
  Codes nur in `CODES` (die KI-Werkzeuge reichen sie als „K-…" durch). Jede
  Funktion ist ein Schreibvorgang; abgelehnt = nichts geschrieben (Test
  vergleicht alle Dateien vorher/nachher). Auch die alten Wege
  (`kalender.routine_aendern`, `kalender_bearbeiten.*`) werfen jetzt bei
  Ende ≤ Beginn statt das Ende still zu verwerfen; die Routen antworten 400
  mit `{error, code}`.
- **Pausen** hängen per `routine_uid` an IHRER Routine (Umbenennen nimmt sie
  mit); alte Pausen ohne sie über den Titel, beim Umbenennen werden sie fest
  angebunden. `kalender_ics.pause_gehoert` ist die eine Regel.
- **Alarme** (`open_alarms`) tragen `tag`, wo sie an einem Tag hängen.
- **Alarm „Wochentag"** (seit 2026-10-22): Titel nennt einen Wochentag, an
  dem der Eintrag nicht stattfindet („Titel nennt Montag, die Serie läuft
  mittwochs: …"; Erkennung `core/titel_wochentag.py`). Je Eintrag im Horizont
  ein Alarm, auch uncommitted/Deadline; nicht Phasen, Spannen, monatlich.
- Konflikt-/Alarm-Rechnung ist nach `core/kalender_konflikte.py` gezogen
  (kalender.py stand bei 1.499/1.500 Zeilen); `kalender.<name>` gilt weiter.
- **Ohne Import-Kreise:** `CODES`/`KalenderAbgelehnt`/Zeitprüfung stehen in
  `core/kalender_fehler.py` (braucht nichts); `kalender_konflikte` importiert
  `kalender` nicht, `kalender.py` schließt `_load_raw`/`entries_in_range`
  per `kalender_konflikte.anschliessen()` an.

## Routen per Kennung (11.10.2026, Wunsch ASSISTANT)

Fremde Anbindungen gehen nicht mehr über Tag+Titel (`ui/routen/kalender.py`,
Test `tests/test_kalender_routen_kennung.py`):
- `GET /api/calendar/eintrag?kennung=…` → Dict wie `kalender_kennung.eintrag`.
- `PUT /api/calendar/eintrag {kennung, new:{day→tag, label, time, ende, ort,
  von, bis, times, enden, kategorie, kategorie_name}}` und `PUT
  /api/calendar/routine {kennung, new:{label, time, ende, ort, rrule, seit,
  bis, motiv, kategorie, kategorie_name | wiederholung:{freq, intervall,
  bis, wochentage}}}` → `{ok, eintrag}`. Fehlend = unverändert, "" = löschen;
  `wiederholung` wird zur Regel ab dem `seit` der Routine (Aus-Tage und
  Abweichungen bleiben, anders als über Tag+Titel), nicht mit rrule/bis.
- `DELETE /api/calendar/eintrag|routine {kennung}` → `{ok:true}`.
- Ohne `kennung` alles wie vorher. Ablehnung immer 400 `{error, code}` —
  auch eine unbekannte Kennung (KENNUNG-UNBEKANNT, beim GET ebenso; kein
  404, wie bei allen Kennung-Routen), falsche Art FALSCHE-ART, ein fremdes
  Feld in `new` UNBEKANNTES-FELD. Abgelehnt = nichts geschrieben.

## Ebene „uncommitted" (10.10.2026)

Sasha: „ich will nen 2. layer … ‚uncommitted' … mehr transparent … sachen
verschieben committed <-> uncommitted … immer AUF den normalen drüber, nicht
getrennt angucken". Umsetzung:
- Eigene Ebene in `_DEFAULT_LAYERS`, im .ics-Speicher eigener Ordner
  `data/kalender/uncommitted/` (gleiche UID beim Wechseln, Datei wandert).
- `kalender_kennung.ebene_wechseln(k, ziel=None)` — umschalten oder fest
  `termine`/`uncommitted`; Route `POST /api/calendar/ebene {kennung, ziel?}`.
- Nur Hinweis (`kalender_konflikte._verbindlich`): kein Alarm, keine
  Kollisions-Rückfrage, keine Abwesenheit durch eine Vielleicht-Reise; die KI
  sieht `[uncommitted · vielleicht]` und soll es höchstens als Möglichkeit
  nennen.
- TUI: immer in A/B/C über den Terminen; Taste `u` schaltet, im Formular
  Advanced → Status (neu und bearbeiten; bis 11.10.2026 Feld „Verbindlich"). Seit dem Abend als **Glas** (Sasha: „es
  sieht nicht transparent aus da der hintergrund nicht durchscheint"):
  Flächen in B und C liegen als Scheibe über allem — Punktlinien und feste
  Termine bleiben sichtbar, nur ihr Grund wird mit der Kursfarbe gemischt
  (`Leinwand.glas`, `kalender.py _glas_attr`, `farben.DECKKRAFT["glas"]`).
  In C teilen sich uncommitted keine Bahnen mit festen. Nur die Schrift in A
  und in den Textzeilen von B bleibt blass (`k_…_blass`). Tags landet jede
  Mischung mit Weiß wieder auf dem Pastell; wo sie auf dem Grund darunter
  landen würde, wird kräftiger gemischt, damit die Scheibe sichtbar bleibt.
  Seit 19.10.2026 „kaum sichtbar" (Sasha: „nen dicken ticken
  transparenter"): im 256er-Modus runden Glas und blasse Flächen auf die
  nächste der 256 MIT Graurampe (nicht `pixel.bunt` — dessen dunkelste Töne,
  Stufe 95, sind nachts zu laut) → nachts ein grauer Hauch (~232–234), tags
  Pastell oder Grau 238. Die Kursfarbe trägt das Label, leise gemischt, aber
  stufenweise kräftiger bis ≥ 3:1. Regler `farben.DECKKRAFT` (night glas
  .15 schrift .45, day glas .20 schrift .50); 24 Bit mischt exakt.
- Google: eigener zweiter Kalender, damit es auf Handy/Tablet mitkommt
  (zweite Sammlung im Paar `zentrale`).
- Nebenbei gefunden: die Marke `kalender_beide` lief bis heute beide Male
  gegen JSON (Fixture nie aktiv) — repariert in `tests/conftest.py`, alle
  Beide-Speicher-Tests laufen jetzt wirklich auch gegen .ics.

## Tagesrhythmus „rhythmus" (10.10.2026)

Sasha: „jeder mensch hat nen rythmus … ‚ich werde gegen 10 hungrig' ist kein
termin … eine leichte hintergrund ebene … wenn ich heute come down um 9:30
habe, dann 3 tage um 2 in sbett gehe, muss das änderbar sein … bau das
gerüst, dann is das gleich für jeden anderen auch nutzbar."
- **Ebene** `rhythmus` in `_DEFAULT_LAYERS`, .ics-Ordner `data/kalender/rhythmus/`.
  NICHT im Google-Paar (das hat nur `termine`/`uncommitted`) — so lassen.
- **Phase** = Routine dieser Ebene: `label`, `rrule` (Standard `FREQ=DAILY`),
  `time` (Pflicht), `ende` (optional), `seit` (erster Tag, Standard heute),
  UNTIL in der Regel = letzter Tag (fehlt = „bis auf Weiteres"), **`motiv`**
  aus dem festen Katalog `kalender_rhythmus.MOTIVE` (nachthimmel, schlaf,
  essen, sonne, fokus, sport, ruhe, unterwegs; je `name`/`was`; erweitern =
  eine Zeile, Schlüssel nie umbenennen).
- **Über Mitternacht:** nur in dieser Ebene darf `ende` vor `time` liegen
  (Schlaf 23:00–07:00 = endet am Folgetag; `kalender_fehler.reihenfolge(…,
  ueber_mitternacht=True)`, Ende == Beginn bleibt ENDE-VOR-BEGINN). Normale
  Termine bleiben streng. `entries_in_range` markiert solche Vorkommen mit
  `ueber_nacht: True` (am Tag des Beginns).
- **.ics:** `TRANSP:TRANSPARENT`, `X-ZENTRALE-MOTIV:<schlüssel>`, Ende am
  Folgetag als echtes DTEND am Folgetag (auch bei Abweichungen; „00:00" geht
  in die Extras, weil es sich als „24:00" zurücklesen würde). Die Abbildung
  bekommt `rhythmus=True` vom Speicher (Ebene), gelesen wird generisch.
- **Variabel** (alles per Kennung, `kalender_kennung`): ab jetzt
  `phase_aendern`, ein Tag `routine_tag_aendern`, ein Zeitraum
  `routine_zeitraum_aendern(k, von, bis, time/ende/label/ort)` — je Tag eine
  Abweichung (RECURRENCE-ID), „" = wieder wie die Regel (die Abweichung fällt
  weg), höchstens 366 Tage. Gilt für alle Routinen, nicht nur Phasen.
- **Nie ein Termin** (`kalender_konflikte.NUR_HINWEIS`): kein Alarm, keine
  Kollisions-Rückfrage, keine Abwesenheit, kein Countdown/Takt
  (`naechster_termin`), nicht im Morgenblick. `ebene_wechseln` lehnt Phasen ab
  (IST-PHASE).
- **KI:** `render_range_for_tool`/Imprint zeigen `[rhythmus · schlaf]
  23:00-07:00 (bis Folgetag) Schlaf`; der Imprint sagt dazu, dass das Sashas
  Tagesrhythmus ist, kein Termin, stiller Hintergrund.
- **TUI** (seit 10.10.2026 abends): Phasen sind dort keine Zeilen/Blöcke,
  sondern ein Muster im Hintergrund der Woche (C), Taste **R** öffnet den
  Kasten „Rhythmus" (neu, ab jetzt ändern, löschen, nur an einem Tag, für einen
  Zeitraum — alles über die Routen oben). Beides beschrieben in
  `kalender_ansichten_vorschau.md` (Abschnitt „Tagesrhythmus").

## Gruppen (CATEGORIES, 10.10.2026)

Sasha: „in der monatsansicht seh ich lieber uni uni uni statt jeden tag welche
fächer genau". Eine Gruppe fasst Einträge in der Monatsansicht zu EINEM Block
zusammen („Uni 08:30–16:00"), sonst nichts; Standard keine.
- **Felder** an Termin, Spanne, Routine, Phase: `kategorie` = Schlüssel aus
  dem festen Katalog `kalender_kategorie.KATEGORIEN` (`uni`, `arbeit`) oder
  `custom`; bei `custom` der Name in `kategorie_name`. Keine Gruppe = Feld
  fehlt. Eingaben über `kalender_kategorie.pruefen(kategorie, name)`:
  ""/„keine" → entfernen; Groß/Klein egal; ein custom-Name, der zum Katalog
  passt („Uni"), wird dessen Schlüssel. Codes KATEGORIE-UNBEKANNT,
  KATEGORIE-NAME-FEHLT, UNBEKANNTES-FELD (Name ohne custom).
- **.ics:** `CATEGORIES:<Anzeigename>` („Uni" bzw. der eigene Name), beim
  Lesen wieder Schlüssel; weitere Kategorien von außen bleiben in
  `kategorien_weitere`. Namen mit Komma/Semikolon gehen verlustfrei in die
  Extras. `CATEGORIES` ist jetzt eine von ZENTRALE verwaltete Property.
- **Ausgaben:** `kalender_kennung`-Dicts haben immer `kategorie` („keine",
  wenn leer); `entries_in_range` reicht die Felder durch (auch an
  Routinen-Vorkommen, mit `motiv`); `/api/calendar` setzt `kategorie:
  "keine"` an jede Zeile. Lesetext der KI: `[termine · Uni]`.
- **Kurs:** `kalender_kategorie.titel_schluessel` (aus der TUI in den Kern
  gezogen; die TUI hat noch ihre Kopie) und
  `kalender_kennung.kategorie_fuer_kurs(schluessel, kategorie, name,
  probe=False)` — alle Einträge des Kurses in EINEM Schreibvorgang, ohne
  Phasen und `erlebt`; `probe=True` schreibt nichts.
- **Routen:** `GET /api/calendar/motive`, `GET /api/calendar/kategorien`,
  `GET /api/calendar/phasen`, `POST|PUT|DELETE /api/calendar/phase`,
  `POST /api/calendar/routine/zeitraum`, `POST /api/calendar/kategorie`,
  `POST /api/calendar/kategorie/kurs`; `POST /api/calendar/entry`, die
  Wochen-Routine und (seit 10.10.2026 abends, fürs TUI-Formular) auch die
  calcurse-Routine (`freq`, `kalender_bearbeiten.routine_neu`) und
  `POST /api/calendar/spanne` (`spanne_neu`) nehmen `kategorie`/`kategorie_name` mit.
- **TUI:** B fasst je Tag zusammen, Formularfeld „Gruppe" —
  `kalender_ansichten_vorschau.md`. Die Kurs-Route hat seit 11.10.2026 keinen
  TUI-Aufrufer mehr (Taste G entfernt), bleibt für KI/Schnittstelle.
  `titel_schluessel` bleibt in der TUI eine Kopie (die Tür `tui/` erlaubt nur
  reine Helfer, `kalender_kategorie` hängt an `kalender_fehler`); ein Test
  (`tests/test_kalender_gruppen_tui.py`) hält beide gleich.
- Tests: `tests/test_kalender_rhythmus.py` (beide Speicher).

## Titel aus Liste/Projekt „quelle" (10.10.2026)

Sasha: „ich hab im kalender den variablen container der todo liste drin
stehen, und im kalender wird als termintitel einfach das höchste item
angezeigt. wenn ich die liste umsortiere dann ändert sich der containertitel
mit … diese zeit ist für genau diesen schritt von diesem projekt … man wählt
ja eigentlich einfach nur ne liste für nen termin slot aus, ansonsten soll
sich das ganze ganz normal als termin bearbeiten lassen."
- **Feld** an Einmal-Termin, Spanne, Routine (nicht an Phasen, IST-PHASE):
  `quelle = {"art": "liste"|"projekt", "id": …}`. Liste: id der Liste
  (`l_todo`). Projekt: ein als Projekt markierter Knoten der Listen
  (`lists.projects_tree`, PROJECTS-Box) — `l_haus` (ganze Liste) oder
  `l_haus/7` (Eintrag 7). Die KI-Projekte (`core/projekte.py`) haben keine
  Schritte und zählen hier nicht. `label` bleibt gespeichert als
  **Rückfall-Titel** (Name der Liste/des Projekts): das zeigen Google/Handy,
  das gilt bei gelöschter Liste.
- **.ics:** `X-ZENTRALE-QUELLE:liste:l_todo` + `URL:zentrale://fokus/l_todo`
  (Adresse des Objekts wie bei der Listen-Kachel; Projekt-Eintrag
  `zentrale://fokus/l_haus/7`). Gelesen wird X-ZENTRALE-QUELLE, fehlt sie,
  die URL. Unsere `zentrale://`-URL wird beim Zusammenführen nicht von der
  alten Datei übernommen (sonst käme eine gelöste Quelle zurück); fremde URLs
  bleiben.
- **Live** (`core/kalender_quelle.py`): Titel = oberstes OFFENES Blatt in
  Anzeige-Reihenfolge (`listen_baum.ordnen`, wie Listen-Ansicht und Kachel;
  Ordner oben → sein oberstes offenes Blatt; ein Projekt-Eintrag ohne
  Unterpunkte ist selbst der Schritt). Leer → „<Name> — alles erledigt",
  `leer`; weg → label, `fehlt`. Umsortieren/Abhaken schreibt den Kalender NIE.
  Listen werden je `entries_in_range` höchstens einmal gelesen
  (`lists.read_lists`, schreibt nie).
- **Ausgaben:** `entries_in_range`, `/api/calendar`, `kalender_kennung`-Dicts
  tragen bei solchen Einträgen `quelle`, `titel_live`, `quelle_name`,
  `quelle_zustand` (ok/leer/fehlt), `quelle_eintrag` ({liste, id} des
  angezeigten Punkts, zum Abhaken; sonst null). Lesetext/Imprint:
  `10:00-12:00 Steuern planen (aus Liste: todo)`; der Imprint erklärt das nur,
  wenn so eine Zeile drinsteht. gross-Schiene (`ki_kalender`) genauso.
- **Setzen:** `kalender_kennung.quelle_setzen(k, art, id, label=None)` (label
  None = Name der Quelle), `quelle_loesen(k, titel_uebernehmen=False)`;
  `kalender.add_entry/add_span/add_routine(..., quelle={art, id})` prüfen
  (ohne label → Name der Quelle). Codes QUELLE-ART-UNBEKANNT,
  QUELLE-UNGUELTIG, QUELLE-UNBEKANNT (auch: Knoten ist kein Projekt),
  OHNE-QUELLE.
- **Routen:** `GET /api/calendar/quellen` (Listen + Projekte mit dem, was
  jetzt oben steht), `POST /api/calendar/quelle {kennung, art, id, label?}`,
  `DELETE /api/calendar/quelle {kennung, titel_uebernehmen?}`,
  `GET /api/calendar/quelle?art=&id=&n=` (die ersten n offenen Punkte,
  `vorschau`, fürs Ansehen in der TUI);
  `POST /api/calendar/entry`, `/api/calendar/spanne` und beide Routinen-Wege
  nehmen `quelle` (label darf bei entry dann fehlen). TUI: Abschnitt in
  [kalender_ansichten_vorschau.md](kalender_ansichten_vorschau.md).
- Kollisionen/Alarme: ganz normaler Termin (reservierte Zeit); `uncommitted`
  und Gruppen funktionieren unverändert. Tests: `tests/test_kalender_quelle.py`.

## Aussehen des Kastens „stil" (10.10.2026)

Sasha: „Im Terminformular gibt es NUR eine Option ‚Stylebox' (kein eigenes
‚color'-Feld). Von dort öffnen sich die Bausteine, und das Ergebnis wird auf
den Termin (seinen Container/Kasten im Kalender) angewendet."
- **Feld** an Einmal-Termin, Spanne, Routine (nicht an Phasen, IST-PHASE):
  `stil = {css-name: wert}` — kein eigenes Format, CSS-Eigenschaften aus
  `core/stil.py`, Angebot `stil.KASTEN`: `border-style`, `border-color`,
  `background-color`, `color`, `--zentrale-muster`, `background-image`
  (Icon, gesperrt). Farben `#rrggbb`. Gilt für den ganzen Eintrag bzw. die
  ganze Serie (Routinen geben es jedem Vorkommen mit, `_MITGEGEBEN`).
- **.ics:** EINE Zeile `X-ZENTRALE-STIL:border-style: double\; border-color:
  #ff8800\; …` — eine CSS-Deklarationsliste wie im HTML-`style`-Attribut
  (`stil.als_css`/`aus_css`, `;` in Klammern trennt nicht), als iCalendar-TEXT
  escaped (`\;` `\,` `\\`, gelesen mit `_text_lesen`, weil icalendar eine
  unbekannte X-Property roh liefert). Dazu der Standard **`COLOR`** (RFC
  7986): der nächste der 147 CSS3-Farbnamen (`stil.css_name`, Abstand
  „redmean") zur Fläche, sonst zum Rahmen, sonst zur Schrift
  (`stil.kastenfarbe`); den genauen Hex trägt die Stil-Zeile. Andere
  Kalender lesen den Termin unverändert, Thunderbird & Co. färben nach COLOR.
- **Zurück:** X-ZENTRALE-STIL gewinnt; fehlt sie, wird ein `COLOR` von außen
  zu `{"background-color": <hex des Namens>}`. `COLOR` ist verwaltet
  (`VERWALTET`): ein entfernter Stil bringt die alte Farbe beim
  Zusammenführen nicht zurück. Was sich nicht exakt als CSS zurücklesen
  lässt (ungeprüfter Altwert), bleibt verlustfrei in X-ZENTRALE-EXTRAS.
  Ein altes `border-style: none` / `--zentrale-muster: none` heißt seit
  11.10.2026 **nicht gesetzt**: `stil.pruefen` lässt es beim Lesen weg, also
  schreibt der Schreiber dafür nichts (es gibt kein `none` mehr im
  Wortschatz, [bausteine_farbe_stil.md](../hub/bausteine_farbe_stil.md)).
- **Setzen:** `kalender_kennung.stil_setzen(k, stil)` ERSETZT den Stil (die
  TUI schickt ihn ganz), `{}` entfernt ihn; ein Schreibvorgang.
  `kalender.add_entry/add_span/add_routine(..., stil={…})` und
  `kalender_bearbeiten.routine_neu/spanne_neu(..., stil=…)` prüfen vor dem
  Laden (`kalender.stil_pruefen`). Code **STIL-UNGUELTIG** (auch K- in
  `core/fehlercodes.py`), Phasen IST-PHASE.
- **Routen:** `POST /api/calendar/stil {kennung, stil}`; `POST
  /api/calendar/entry`, `/api/calendar/spanne`, `/api/calendar/routine`
  nehmen `stil`. `/api/calendar` und die `kalender_kennung`-Dicts liefern
  ihn mit. TUI: Abschnitt in
  [kalender_ansichten_vorschau.md](kalender_ansichten_vorschau.md). Tests:
  `tests/test_kalender_stil.py` (beide Speicher).

## Stand Sync (07.10.2026) — eingerichtet und live

- **Ein Kalender.** Die Ebene `routinen` ist nach `termine` gezogen
  (`scripts/kalender_ebenen_vereinen.py`, Probe an Kopie, 715 Tage ohne
  Abweichung). Neue Routinen landen in `termine`; sagt die KI „routinen",
  leitet `ki_werkzeuge` um (Werkzeugtexte bewusst byte-gleich gelassen).
- **Jeder Rechner synct selbst gegen Google** (Sasha: „sauber jeder synct
  gegen die cloud"; später nimmt der PC als Server die Rolle von Google ein).
  Damit ist die frühere Regel „vdirsyncer nur auf dem PC" überholt:
  `data/kalender/` ist aus `zentrale-sync` (~/.local/bin, nicht in git)
  herausgenommen — ein zweiter Weg daneben brächte Doppelte/Geister. ⚠ Auf
  dem PC muss dieselbe Ausnahme in sein `zentrale-sync`, bevor er synct.
- **Paar** `zentrale`: `data/kalender/termine` ↔ Google-Hauptkalender
  `fyyres@gmail.com`; bewusst OHNE `metadata` (sonst hieße der
  Google-Hauptkalender danach „Termine"). „Feiertage in Deutschland"
  (`…@virtual`) bleibt draußen. Konfig `~/.config/vdirsyncer/config` (600,
  enthält das Client-Geheimnis), Token in `~/.local/share/vdirsyncer/`.
- **Absicherung zusätzlich** (`scripts/kalender_sync.py`, Sasha: „bitte
  bitte lösch nix aus google calendar"): vor jedem Lauf Nur-Lese-Kopie von
  Google (Paar `google_probe` → `~/.local/share/vdirsyncer/google_kopie`),
  einmal am Tag als Archiv nach `~/.local/share/zentrale/google-sicherung/`
  (14 Tage); fehlen lokal seit dem letzten Sync mehr Termine als die
  Löschsperre, läuft vdirsyncer nicht (`ZENTRALE_KALENDER_SYNC_LOESCHEN_OK=1`
  für Gewolltes).
- **Sichtbar** (seit 16.10.): jeder Lauf schreibt seinen Stand (Zugang
  abgelaufen, kein Netz, …), TUI und Alarm-Kanal zeigen Probleme —
  [kalender_sync_zustand.md](kalender_sync_zustand.md).
- **Automatisch:** `deploy/zentrale-kalender-sync.{service,timer}` (alle
  3 min, 1 min nach Anmeldung), in `~/.config/systemd/user/` verlinkt.
- **Erster Sync:** ZENTRALE 48 → 518 Dateien, Google 470 → 518, von den 470
  alten Google-Terminen fehlt keiner (gegen das Archiv geprüft).
- **Was Google mit unseren Feldern macht (gemessen):** Termine ohne Ende
  bekommen 1 h Dauer (28 Stück) — Sasha: passt meistens, für Merker beim
  Anlegen selbst eine Dauer angeben (`+2`). Mehrere gleichnamige
  X-ZENTRALE-Felder schrumpft Google auf eins: von zwei Pausen einer Routine
  blieb eine (Sommerferien-Beschriftung weg). Die Ausfalltage selbst stehen
  als EXDATE drin und bleiben; Sasha: die Beschriftung ist nur Metadata.
  Einzelne X-ZENTRALE-Felder (ART, ABSAGE-NOETIG, POS …) überleben.

## Warum

Sasha, 2026-10-06: *„bisherige daten übertragen ohne verluste, und nach
fertigstellung den kalender gegen datenverlust weitgehend absichern und gut
backups immer überall hinzuschmeißen."*

- **.ics ist die einzige Quelle der Wahrheit.** iCalendar ist der Standard,
  den Handy (Android, über Google heute, später DAVx⁵), Google, Posteo und
  jeder CalDAV-Server sprechen. Eine eigene JSON hätte für jeden dieser Wege
  einen eigenen Übersetzer gebraucht.
- **Sync macht vdirsyncer, nicht ZENTRALE.** Der Anbieterwechsel (Google →
  eigener Server/Posteo) ist dann nur eine andere vdirsyncer-Konfiguration.
- **ZENTRALE zeichnet die Ansicht selbst** (eigener Auftrag, nicht Teil
  dieses Bauplans). Kollisionen, Fahrzeiten, Alarme, Imprint und Takt bleiben
  in ZENTRALE und lesen jetzt eben `.ics`.

## Die Abbildung (mit Sasha entschieden)

| Alt (JSON) | Neu (.ics) |
|---|---|
| Ebene (`termine`, `routinen`, eigene) | ein Kalender = ein Unterordner im vdir (`data/kalender/<ebene>/`, mit `displayname`/`color` für vdirsyncer) |
| Einmal-Termin, `time`, `ende`, `ort` | VEVENT mit DTSTART/DTEND (TZID=Europe/Berlin), LOCATION |
| ganztags (ohne `time`) | DTSTART;VALUE=DATE |
| Spanne über Tage (`bis`) | **ein** VEVENT, ganztags von DTSTART bis DTEND |
| Spanne mit Beginn am ersten / Ende am letzten Tag | **ein** VEVENT mit Uhrzeiten („Fr 18:00 bis So 14:00") |
| Spanne mit eigener Zeit pro Tag (`times`) | tägliche RRULE (COUNT) + Abweichungs-VEVENTs mit RECURRENCE-ID **in derselben Datei** (gleiche UID) — sonst bricht vdirsyncer; nicht in Einzeltermine zerlegt, weil Sasha die Spanne zusammenhängend sehen will |
| Routine (`rrule`) | RRULE; `ende` → DTEND |
| `aus` (einzeln deaktiviert) | EXDATE + `X-ZENTRALE-AUS` |
| `pausen` (Ferien) | EXDATEs an jeder Routine gleichen Namens + `X-ZENTRALE-PAUSE` (die Notiz mit Grund) |
| `absage_noetig` | `X-ZENTRALE-ABSAGE-NOETIG:TRUE` |
| `typ: deadline`, `vorwarnung` (20.10.2026) | `X-ZENTRALE-TYP:DEADLINE`, DTEND = DTSTART, Vorwarnung als `VALARM` (`TRIGGER:-P3D`) — [kalender_deadline.md](kalender_deadline.md) |
| Ebene `erlebt` | fällt weg — Inhalt wandert **unverändert** ins Archiv der Nebendaten |
| `reisezeiten`, `puffer_min`, Ebenen-Titel/Farbe/Sichtbarkeit, `version` | Nebendaten `data/kalender_neben.json` |

Was dazu nicht passt, geht nie verloren — das Prinzip: ein Feld wird nur
dann auf eine Property abgebildet, wenn es sich **exakt** zurücklesen lässt.

- Unbekannte Zusatzfelder und alles, was sich nicht ausdrücken lässt (Ende
  ohne Beginn, Ende vor Beginn, leere Titel) → `X-ZENTRALE-EXTRAS` (JSON,
  base64-verpackt, weil Server Kommas und Semikolons in unbekannten
  Properties verschieden behandeln). Extras füllen beim Lesen nur **Lücken** —
  was am Handy geändert wurde, gewinnt.
- Uhrzeiten, wie sie in Sashas echten Daten stehen (`"10"`, `"9:30"`, `"8"`),
  gehen als 10:00 / 09:30 / 08:00 nach DTSTART — Google zeigt die richtige
  Stunde. Der Originaltext steht in `X-ZENTRALE-ZEIT-ROH` und gilt nur, solange
  die Zeit unverändert ist. Dasselbe für RRULEs, die icalendar umordnet
  (`X-ZENTRALE-RRULE-ROH`).
- Was gar nicht als Ereignis geht (kaputtes Datum als Schlüssel, Spanne mit
  `bis` vor `von`, leere Tage) → `nicht_abbildbar` in den Nebendaten, liest
  sich aber genauso zurück.
- Die Reihenfolge (wichtig für gleichzeitige Termine und damit für den
  Wortlaut der Alarme) trägt `X-ZENTRALE-POS`.
- Jede Schreibfunktion liest ihr Ergebnis sofort zurück; weicht es ab, landet
  das Stück roh in den Nebendaten statt verfälscht im vdir.

Routinen hatten im alten Modell **keinen Anfang** (sie galten rückwirkend
für immer). Damit sich daran nichts ändert, bekommen sie in .ics einen
technischen DTSTART (erster echter Termin ab dem Anker: bei der Migration der
früheste Tag der alten Daten, sonst der Tag des Anlegens) plus
`X-ZENTRALE-OHNE-ANFANG:TRUE`; ZENTRALE rechnet sie weiter wie vorher, Google
zeigt sie ab dem Anker. Routinen, die von außen kommen, haben einen echten
Anfang (`seit`) und werden ab dort gerechnet. **DTSTART = erstes echtes
Vorkommen ab `seit`** (seit 22.10.2026): liegt `seit` auf keinem Regel-Tag
(Do bei BYDAY=MO), steht `seit` zusätzlich in `X-ZENTRALE-SEIT` — sonst zeigte
Google am Starttag einen Phantom-Termin (RFC 5545 zählt DTSTART immer mit,
dateutil in ZENTRALE nicht). Gelesen gilt `X-ZENTRALE-SEIT` nur, solange sein
erstes Vorkommen noch DTSTART ist (außerhalb verschoben → DTSTART). Siehe
`memory/system/gefahrzonen.md` §3. Neu im Daten-Dict (nur von
außen gelesen): `seit`, `enden` (Ende pro Tag einer Spanne) und
`abweichungen` (am Handy verschobene/abgesagte Einzeltermine einer Routine,
RECURRENCE-ID).

Ob Google die `X-ZENTRALE-*`-Properties behält, ist **ungetestet**. Fällt
eine weg, verliert ZENTRALE Bedeutung, nicht den Termin (getestet): ein
EXDATE ohne `X-ZENTRALE-AUS` wird als „deaktiviert" gelesen, ein Termin ohne
`X-ZENTRALE-POS` kommt hinten an. Gegen den Rest helfen Verlauf, Snapshots
und git-Spiegel (unten).

## Module (Schicht 2, siehe `memory/system/bauplan_kern.md`)

| Modul | Aufgabe |
|---|---|
| `kalender` | öffentliche Fassade, Rechenlogik (Kollisionen, Alarme, Imprint) — Namen und Signaturen unverändert |
| `kalender_zeitraum` | relative Zeiträume („diese_woche") in Daten (aus `kalender.py` gelöst) |
| `kalender_regel` | RRULE → Tage, die eine Stelle für Fassade und Abbildung |
| `kalender_speicher` | wählt den Speicher, alle Pfade, Einstellungen |
| `kalender_json` | der alte Speicher, jetzt atomar, mit Rückfall-Sperre |
| `kalender_ics_abbildung` | ein Termin/eine Routine ↔ VEVENT-Komponenten, rein rechnend |
| `kalender_ics` | der vdir-Speicher: lesen (mit Cache), nur Unterschiede schreiben, Nebendaten |
| `kalender_sicherung` | atomares Schreiben, Datei-Sperre, Verlauf, Grabsteine, Snapshots, Massenlösch-Sperre |
| `kalender_spiegel` | git-Spiegel außerhalb von `data/` |
| `kalender_migration` | Prüfen, Ausführen, Rückweg, Feld-Inventar |

Die Fassade arbeitet weiter auf dem gewohnten Daten-Dict (`_load_raw` →
ändern → `_save_raw`). Der ics-Speicher übersetzt beim Laden die Dateien in
genau dieses Dict (jeder Eintrag trägt intern `_ics` mit UID und Position,
die Fassade gibt das nie nach außen) und schreibt beim Speichern **nur die
Dateien, die sich geändert haben**. Dadurch blieb die Rechenlogik unberührt,
und ein Schreiben fasst nie den ganzen Kalender an. Beim Zurückschreiben einer
vorhandenen Datei bleibt alles erhalten, was ZENTRALE nicht verwaltet
(DESCRIPTION, Erinnerungen, Teilnehmer, Google-Felder, andere UIDs).

Einstellungen (alle über `ai_config.setting`, also auch als Env
`ZENTRALE_<NAME>`): `kalender_speicher` (`json`/`ics`),
`kalender_loeschsperre` (Default 5), `kalender_git_spiegel` (Pfad oder
`aus`; Default `~/.local/share/zentrale/kalender-git`).

## Absicherung gegen Datenverlust

Die Falle: `data/` wird zwischen PC und Laptop per rsync Datei für Datei
abgeglichen, **nur hinzufügend, neueste Datei gewinnt**
([../system/topologie.md](../system/topologie.md)). Ein git-Repo IN `data/`
würde dabei zerstört (refs und index würden dateiweise überschrieben).
Umgekehrt ist das .ics-Format hier ein Gewinn: der Sync gleicht pro Termin
ab — ändert der PC die Geige und der Laptop den Zahnarzt, überleben beide
(mit der einen JSON gewann eine Datei, die andere Änderung war weg).

1. **Atomar schreiben:** temporäre Datei (Name endet nicht auf `.ics`),
   fsync, `os.replace`. Ein Absturz hinterlässt nie eine halbe Datei. Gilt
   jetzt auch für die alte JSON.
2. **Sperre:** ein Thread-Lock im Prozess plus eine Datei-Sperre
   (`data/kalender/.zentrale.lock`) zwischen Prozessen. Nach 15 s ohne
   Sperre: Fehler statt Hängen.
3. **Verlauf** `data/kalender_verlauf/<Monat>/`: vor jeder Änderung und jeder
   Löschung landet die alte Fassung dort, Name aus Zeitstempel + Knoten +
   Ebene + UID + Aktion. Eindeutige Namen übersteht der Sync. Zurückholen:
   `IcsSpeicher.wiederherstellen(<verlaufsdatei>)` — die dann aktuelle
   Fassung wandert vorher selbst in den Verlauf.
4. **Grabsteine** `data/kalender_verlauf/grabsteine/<uid>.json`: Weil der Sync
   nichts löscht, käme eine auf dem Laptop gelöschte Datei vom PC zurück.
   Eine `.ics`, die nicht neuer ist als ihr Grabstein (LAST-MODIFIED), gilt
   als Geist: nicht angezeigt, beim nächsten Schreiben (oder vor vdirsyncer)
   in den Verlauf geräumt. Ist sie neuer, gilt sie — neueste gewinnt.
5. **Massenlösch-Sperre:** löscht eine einzige Operation mehr als
   `kalender_loeschsperre` Termine, wird **gar nichts** geschrieben
   (`KalenderGesperrt`). Die KI sieht das als Werkzeug-Fehler; eine Route
   antwortet mit 500 (die Routen sind unverändert). Wiederherstellen,
   Migration und Rückweg dürfen ausdrücklich mehr.
6. **Tägliche Snapshots** `data/kalender_snapshots/kalender_<datum>_<knoten>.tar.gz`
   vor der ersten Änderung des Tages; behalten werden 30 Tage plus jeder
   Monatserste für zwei Jahre (für alle Knoten gleich, sonst hielte der
   additive Sync alte Snapshots ewig). Weil sie in `data/` liegen, wandern sie
   auf den anderen Knoten.
7. **git-Spiegel** (Sasha, Nachtrag 2026-10-06: *„daten können gern in ein
   extra git repo"*): nach jedem Schreiben spiegelt ZENTRALE vdir +
   Nebendaten nach `~/.local/share/zentrale/kalender-git` (außerhalb von
   `data/`, ein Repo pro Knoten) und committet — im Hintergrund; ein Fehler
   dort verhindert nie das Schreiben des Termins (getestet). Gepusht wird
   nichts. Neben dem Verlaufsordner sinnvoll, weil er auch Änderungen
   festhält, die vdirsyncer von außen hereinbringt (der Wrapper committet
   vorher und nachher), und weil er sich als zusätzliche Kopie an ein privates
   Remote hängen lässt.
8. **Rückfall-Sperre:** Nach der Migration steht in den Nebendaten
   `migriert_am`. Ein Knoten, der noch auf `json` steht, darf dann nicht mehr
   in die alte JSON schreiben (er liefe sonst still auseinander) — Lesen
   geht, Schreiben wird verweigert.
9. **vdirsyncer** bricht ab, wenn eine Seite plötzlich ganz leer ist
   (lokal geprüft mit vdirsyncer 0.21.0). Diese Sicherung bleibt an; den
   Zwangs-Löschschalter nie ohne Nachsehen benutzen.

Kalenderdaten gehen nicht ins Code-Repo: `.gitignore` deckt `data/kalender/`,
Verlauf, Snapshots, `data/kalender_*.json` und die umbenannte Alt-Datei ab.
Testläufe fassen sie nie an (`tests/conftest.py` biegt jeden Kalender in ein
Wegwerf-Verzeichnis, der git-Spiegel ist in Tests aus).

## Migration

`scripts/kalender_migrieren.py` hat drei Modi (Hilfe im Skript selbst):

- **prüfen** (Standard, ändert nichts): schreibt die alte JSON in einen
  Wegwerf-Ordner, liest durch die neue Schicht zurück und vergleicht: das
  ganze Daten-Dict samt Reihenfolge der Ebenen und Tage, dann ~900 Aufrufe der
  öffentlichen Lesefunktionen über beide Speicher (`entries_in_range` über
  ±2 Jahre, die ganze Datenspanne und je Ebene; jede Woche und jeder Monat;
  `render_range_for_tool` je Monat und je Titel; `routine_finden`;
  `open_alarms` mit 0/30/90/400 Tagen; Imprint 0–7 Tage; `naechster_termin`
  zu sieben Uhrzeiten an 38 Tagen; `conflicts_for_proposed` an 181 Tagen).
  Dazu das **Feld-Inventar**: jedes Blatt der alten Datei muss wieder
  auftauchen, und es wird gezählt, wohin es ging. Jede Abweichung = kein
  Umzug. Dass die Prüfung Verluste wirklich findet, ist getestet (absichtlich
  verlorener Ort, falsche Uhrzeit, fehlende Reihenfolge).
- **ausführen**: prüft erst; Ziel muss leer sein; schreibt `data/kalender/`
  und die Nebendaten, liest sie zurück und vergleicht noch einmal, setzt den
  Rückfall-Marker, stellt `kalender_speicher=ics` (in `data/ai_config.json`)
  und benennt `ai_calendar.json` in `ai_calendar.json.vor-ics-<datum>` um
  (nie löschen).
- **zurück**: schreibt aus dem vdir wieder eine `ai_calendar.json` (mit
  `erlebt` an seinem alten Platz), nimmt die Rückfall-Sperre weg, stellt auf
  `json`. Der vdir-Ordner bleibt liegen.

**Ergebnis an einer Kopie der echten Daten (2026-10-06):** 3 Ebenen,
38 Einmal-Termine, 4 Spannen (eine mit Uhrzeit pro Tag: Basel), 6 Routinen,
2 Pausen, 27 Einträge in `erlebt` → 48 `.ics`-Dateien, nichts roh,
893 Vergleichs-Aufrufe, **alles gleich**; `erlebt` exakt im Archiv.
Auffällig: sechs Termine haben Uhrzeiten ohne Minuten oder führende Null
(`"10"`, `"18"`, `"8"`, `"2"`, `"9:30"`) — ZENTRALE behandelt sie wie bisher
(keine Kollisionsprüfung, kein Countdown), Google zeigt sie als volle Stunde.
`"2"` wird dort zu 02:00.

## Was Sasha tun muss (Umstieg, in Worten)

1. Auf **einem** Knoten arbeiten (PC). Vorher beide Knoten abgleichen und auf
   dem anderen bis zum Ende nichts am Kalender ändern.
2. Das ZENTRALE-Backend auf diesem Knoten anhalten — es liest die Einstellung
   nur beim Start, und während des Umzugs soll niemand schreiben.
3. Das Migrations-Skript mit dem venv-Python ohne Zusatz laufen lassen (das
   ist der Prüf-Modus) und die Meldung lesen: Zahlen, „alles gleich",
   Feld-Inventar.
4. Ist alles gleich: dasselbe Skript im Ausführen-Modus. Danach liegen der
   vdir-Ordner und die Nebendaten in `data/`, die alte Datei ist umbenannt,
   die Einstellung steht auf `ics`.
5. Backend wieder starten, Kalender in der TUI anschauen.
6. Abgleich zum anderen Knoten anstoßen; dort ebenfalls das Backend neu
   starten (die Einstellung liegt in `data/ai_config.json` und kommt mit).
   Bis dahin verweigert der andere Knoten Kalender-Schreibzugriffe — das ist
   die Rückfall-Sperre, kein Fehler.
7. Google (wenn gewollt): in der Google-Weboberfläche zwei Kalender anlegen
   (Termine, Routinen); in der Google Cloud Console einen OAuth-Client
   „Desktop-App" für die Calendar API; die Vorlage
   `deploy/vdirsyncer.config.example` in den vdirsyncer-Konfigurationsordner
   kopieren und die Platzhalter füllen; vdirsyncer die Kalender entdecken
   lassen (beim ersten Mal öffnet sich der Browser für die Anmeldung); danach
   immer über `scripts/kalender_sync.py` synchronisieren, nicht vdirsyncer
   direkt. vdirsyncer nur auf dem PC; sein Status-Ordner liegt außerhalb von
   `data/`. Einen regelmäßigen Lauf (Timer) gibt es noch nicht.
8. git-Remote (optional): auf der GitHub-Weboberfläche ein **privates**,
   leeres Repo anlegen; im Spiegel-Repo (`~/.local/share/zentrale/kalender-git`)
   dieses Repo als Remote eintragen, mit dem vorhandenen SSH-Zugang, und von
   Hand pushen, wann immer gewünscht. ZENTRALE pusht nie selbst.

## Offene Fragen

- Behält Google `X-ZENTRALE-*`? Erst mit echtem Konto prüfbar.
- Routinen „seit immer": soll ZENTRALE neue Routinen künftig erst ab heute
  rechnen? Dann reicht es, `X-ZENTRALE-OHNE-ANFANG` beim Anlegen wegzulassen.
- Regeln, die vom Startdatum abhängen (`INTERVAL=2`, `COUNT`), rechnete das
  alte Modell vom jeweiligen Abfragebeginn aus — Google ab dem Anker. In den
  echten Daten gibt es keine; die Prüfung fände sie.
- Abweichungen einzelner Routine-Termine (am Handy verschoben) zeigt ZENTRALE
  an, kann sie aber nicht selbst anlegen; Titel-/Ortsänderungen an
  Abweichungen einer Spanne liest sie nicht.
- Fügt ein Server einem Termin ohne Ende eins hinzu (Google: oft +1 h), hat
  ZENTRALE danach ein Ende und prüft Kollisionen damit (dokumentiert, getestet).
- Die Ansicht (eigener Agent) kennt die neuen Felder `enden`/`abweichungen`
  noch nicht; über `entries_in_range` kommen sie als normales `ende`/`time`.

## Historie

- **2026-10-06** — Plan, Bau der Schicht, Migration geprüft an einer Kopie
  der echten Daten; Umschalter bleibt auf `json`.
- **2026-10-22** — DTSTART von Routinen auf das erste echte Vorkommen
  (`X-ZENTRALE-SEIT`), 16 Serien im Bestand einmalig neu geschrieben
  (Phantom-Termine bei Google am Starttag).
