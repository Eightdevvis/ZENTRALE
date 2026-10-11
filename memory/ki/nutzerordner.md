# Nutzerordner, Suchen, Claude-Skills übernehmen

**Stand 2026-10-11:** Auf `gross` arbeitet der Assistent nur mit dem
Nutzerordner (`~/Zentrale`, `Input/` und `Output/`) und seinem Gedächtnis.
Dateien findet er durch Suchen (`find_files`, `search_files`, `list_files` für
einen Ordner), jede Suche sagt, wie vollständig sie war. `import_skill`,
`unzip` und `remove_input` arbeiten nur aus Input/, gegatet, ganz oder gar
nicht. Nach dem Verarbeiten fragt die KI, ob die Datei aus Input weg soll.
`klein` ist unverändert (Whitelist + ~/codicus).

**Warum:** Gespräch 20261009-155510 (Chefkoch-Zip übersehen, weil `list_files`
bei 300 von ~5.000 Dateien kappte). Sasha: Dateien findet man durch Suchen, nicht
durch Listen; Code-Zugriff auf ~/codicus gehört später zur Coder-App „Codicus".
Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Nutzerordner, Suchen, Claude-Skills übernehmen (seit 2026-10-09)

Anlass: Gespräch 20261009-155510. Sasha legte „Chefkoch ai-v1.zip" in den
ZENTRALE-Ordner; `list_files` war bei 300 von ~5.000 Dateien gekappt (Hinweis
nur am Ende), die KI sagte „ich seh keine chefkoch-Datei", und übernehmen
konnte sie ohnehin nicht. Sasha danach: Dateien findet man durch Suchen, nicht
durch Listen — und der Assistent bekommt keinen Zugriff mehr auf den
Code-Dschungel unter ~/codicus (das wird eine eigene Coder-App).

**Der Nutzerordner** (`core/nutzer_ordner.py`, Einstellung `nutzer_ordner`,
Env `ZENTRALE_NUTZER_ORDNER`, Standard `~/Zentrale`): zwei Unterordner,
`Input/` (was Sasha der KI hineinlegt) und `Output/` (was die KI Sasha gibt),
beim ersten Zugriff angelegt. Pfade wie „x.zip", „Input/x.zip" oder absolut;
was (Verweise aufgelöst) hinausführt, gilt nicht. `read_file` liest dort auch
(„Input/notiz.md"; Secrets und Verstecktes gesperrt). Tests lenken ihn per
conftest um (Wächter in `tests/test_keine_seiteneffekte.py`).

**Suchen** (`core/nutzer_suche.py`, nur gross, frei), NUR in Input/ und
Output/ (oder einem Ordner darin), ohne Verstecktes und Secret-Namen:
- `find_files(muster, ordner?)` — wie find: `*.zip`, `*chefkoch*`; ohne
  Platzhalter ein Namensteil (Groß/Klein und Trenner egal: „chefkoch-ai" trifft
  „Chefkoch ai-v1.zip"). Zählt alle, zeigt 50, flache zuerst.
- `search_files(text, ordner?, muster?)` — wie `grep -i -F`: `pfad:zeile:
  auszug`, höchstens 100 Treffer, Binärdateien übersprungen, Dateien über 2 MB
  nicht durchsucht.
- `list_files(ordner?)` auf gross — EIN Ordner wie ls (Unterordner mit `/`).
- **Jede Suche sagt, wie vollständig sie war**, in der ersten Zeile und in
  fester Form: „Suche vollständig: N Treffer — durchsucht: Input/, Output/
  (K Dateien)." oder „Suche NICHT vollständig: abgebrochen nach 100 Treffern
  …" / „… 2 Dateien über 2 MB oder unlesbar, nicht durchsucht …".
  Maschinenlesbar zusätzlich `Befund.vollstaendig` (core/werkzeug_befund.py).
  Der Prüfer „nicht da" ([ehrlichkeit_live.md](ehrlichkeit_live.md)) lässt
  „gibt es nicht" nur nach „Suche vollständig: 0 Treffer" durch.
- Die Ablage (core/ablage.py) durchsuchen die Werkzeuge noch nicht (offen).

**`import_skill(pfad)`** (gegatet, kein „immer"): `core/skill_import.py`.
So importiert man einen Claude-Skill: Zip oder Ordner in `~/Zentrale/Input/`
legen, der KI sagen „übernimm den Skill" — sie sucht mit `find_files`, Sasha
bestätigt „Skill „chefkoch-ai“ aus „Chefkoch ai-v1.zip“ übernehmen?" (die
Frage packt vorab aus und nennt die echten Namen).
- **Nur aus Input/**; alles andere → `S-QUELLE-AUSSERHALB`.
- **Formen:** Plugin (`.claude-plugin/plugin.json` + `skills/<name>/SKILL.md`,
  auch eigene Skill-Pfade aus plugin.json), Skill-Ordner (`<name>/SKILL.md`,
  auch mehrere), Zip mit `SKILL.md` in der Wurzel, die `SKILL.md` selbst. Ein
  einzelner Hüllordner in der Zip wird übersprungen.
- **Sicher:** erst alle Einträge prüfen — absolute Pfade, `..`, Symlinks →
  `S-UNSICHER`; > 20 MB entpackt oder > 500 Dateien → `S-ZU-GROSS` (beim
  Auspacken mitgezählt, die Angabe der Zip kann lügen). Versteckte Dateien,
  `__MACOSX`, `__pycache__` und Schlüssel-Namen bleiben draußen (gezählt).
- **Prüfen** wie Claude: `name` (Claudes Regeln) und `description` (≤ 1.024,
  ohne `<` `>`) im Kopf, Anleitung nicht leer, kein Name doppelt → sonst
  `S-SKILL-UNGUELTIG`; keine SKILL.md → `S-KEIN-SKILL`.
- **Gibt es den Namen schon:** `S-SKILL-GIBT-ES`, nichts geschrieben — die KI
  fragt Sasha, statt umzubenennen oder zu überschreiben.
- **Ablegen:** ausgepackt in einen versteckten Arbeitsordner IM Skill-Ordner,
  dann je Skill `os.rename` nach `skills/<name>/` (atomar). `_zentrale.json`:
  `status: aktiv`, `herkunft: sasha`, `quelle`: „Chefkoch ai-v1.zip (Plugin
  chefkoch-ai 1.0.0, Autor …, Lizenz …)" — keine Mail-Adressen. Nachgelesen in
  `skills.aktive()`; fehlt einer, sind ALLE neuen Ordner wieder weg
  (`W-NICHT-GESPEICHERT`). Mehrere Skills: ganz oder gar nicht.
- **Ergebnis:** „Skill „chefkoch-ai“ ÜBERNOMMEN (aktiv): SKILL.md + 2
  Referenzen." Skripte (`scripts/`) kommen mit und werden genannt — sie laufen
  nur in der Sandbox (`run_code(skill=…)`).
- **Wann er in der Liste steht:** der feste Kopf wird je Nachricht neu gebaut
  (`cloud._static_system` → `skills.prompt_block()`), also ab Sashas nächster
  Nachricht (der Cache-Anfang ändert sich dabei einmal); `load_skill` sofort.

Fehlercodes: `S-QUELLE-FEHLT`, `S-QUELLE-AUSSERHALB`, `S-QUELLE-GESPERRT`,
`S-ZIP-KAPUTT`, `S-UNSICHER`, `S-ZU-GROSS`, `S-KEIN-SKILL`,
`S-SKILL-UNGUELTIG`, `S-SKILL-GIBT-ES` (`core/fehlercodes.py`). Einträge in
`core/werkzeug_nutzer_ordner.py`, Ausführer in `core/ki_nutzer_ordner.py`
(list_files: `ki_werkzeuge`, nach Schiene). Text-Budget der drei
Beschreibungen: Deckel < 550 in `tests/test_profil.py`. Tests:
`tests/test_skill_import.py`, „nicht da" in `tests/test_ehrlichkeit.py`.

**`unzip(datei, ansehen?)`** (`core/input_dateien.py`, seit 2026-10-09): Zips,
die kein Skill sind. Nur aus Input/. `ansehen=true` (frei): Pfade, Größen,
Anzahl, was ausgelassen würde, ob Auspacken ginge — nichts ausgepackt. Sonst
gegatet: „„Fotos.zip“ nach Output/Fotos/ auspacken? 2 Dateien, 1 KB, 3
ausgelassen." Dieselben Regeln wie import_skill aus `core/zip_sicher.py`
(geteilt, nicht kopiert): `..`/absolut/Symlink → `Z-UNSICHER`, > 20 MB oder
> 500 Dateien → `Z-ZU-GROSS`, Verstecktes/Ballast/Schlüssel-Namen ausgelassen
und im Ergebnis genannt. Ziel `Output/<name ohne .zip>/`; gibt es das schon →
`Z-ZIEL-GIBT-ES`, nichts überschrieben. Ganz oder gar nicht: ausgepackt in
einen versteckten Ordner in Output/, nachgezählt, dann `os.rename`. Ergebnis:
„„Fotos.zip“ AUSGEPACKT nach Output/Fotos/: N Dateien (…)". Die Zip bleibt in
Input/.

**`remove_input(datei)`** (gegatet: „„x“ aus Input entfernen? (kommt in den
Papierkorb)"): VERSCHIEBT einen Eintrag direkt aus Input/ nach
`<nutzer_ordner>/.Papierkorb/<YYYY-MM-DD>/` — Namenskonflikt → „x (2).pdf";
gelöscht wird nie (der Abgleich ist additiv). Unterordner → `Z-NICHT-DIREKT`.
Nachgesehen: am neuen Ort da, am alten weg — sonst zurückgelegt
(`W-NICHT-GESPEICHERT`). Der Papierkorb ist versteckt, also für Suchen und
`read_file` unsichtbar.

**Input aufräumen** (`core/input_aufraeumen.py`; Sasha: „damit der ordner nich
zur halde wird"): Hat ein Werkzeug eine Datei DIREKT aus Input/ fertig
verarbeitet — `import_skill`, `unzip`, `read_pdf` (alle Seiten), `read_docx`
(letztes Stück), `read_file`, `fetch_document` mit Input-Pfad —, hängt an sein
Ergebnis die feste Zeile „Frag Sasha jetzt, ob <datei> aus Input weg soll
(remove_input)." und im Gespräch steht eine offene Zusage (`core/zusagen.py`,
Feld `art: "input_aufraeumen: <datei>"`). Sie steht in jedem Zug im
Kontext-Umschlag („Noch offen von dir zugesagt"), bis `remove_input` für die
Datei lief, die Datei sonst weg ist, oder Sasha nein sagte — am Gate von
`remove_input` oder in einem `ask_choice`, dessen Frage die Datei nennt
(Wahl „Nein"/„behalten"/…). Werkzeug-Zusagen verfallen nicht und werden nicht
von irgendeinem anderen Werkzeug abgehakt (`zusagen.nachfuehren` lässt Einträge
mit `art` in Ruhe; abgehakt in `ehrlichkeit.Pruefer` →
`input_aufraeumen.nachfuehren`). Nicht nach Lesefehlern/Abbrüchen, nicht für
Dateien in Unterordnern, nur auf gross.

Fehlercodes `Z-…` (Vorsilbe Z = Nutzerordner ~/Zentrale): `Z-QUELLE-FEHLT`,
`Z-QUELLE-AUSSERHALB`, `Z-QUELLE-GESPERRT`, `Z-KEINE-ZIP`, `Z-ZIP-KAPUTT`,
`Z-UNSICHER`, `Z-ZU-GROSS`, `Z-LEER`, `Z-ZIEL-GIBT-ES`, `Z-NICHT-DIREKT`,
`Z-VERSCHIEBEN`. Text-Budget der beiden Beschreibungen: Deckel < 300 in
`tests/test_profil.py`. Tests: `tests/test_input_aufraeumen.py`.

Relative Pfade lösen `read_file`, `read_pdf`/`read_docx` und `fetch_document`
seit 2026-10-09 an EINER Stelle auf (`context.pfad_aufloesen`) — vorher kannte
nur `read_file` „Input/…".

## Reichweite von gross: nur der Nutzerordner (Rückbau 2026-10-09)

Sasha: der Assistent arbeitet nur mit `~/Zentrale` (Input/, Output/) und
seinem Gedächtnis; Datei- und Code-Zugriff auf ~/codicus gehört später zur
Coder-App „Codicus". Umgesetzt an der einen Stelle, die alle fragen
(`context.erlaubt`, `context.pfad_aufloesen`), abhängig von der Schiene des
laufenden Werkzeug-Aufrufs (`werkzeug_befund.schiene()`):

- **gross:** `read_file`, `read_pdf`/`read_docx` (Dateipfad) und
  `fetch_document` (lokal) lesen NUR in Input/ und Output/; relativ heißt im
  Nutzerordner, ein bloßer Name meint Input/ („[Datei nicht gefunden:
  Input/core/x.py]" sagt, wo gesucht wurde). Absolut oder per Verweis hinaus →
  `Z-AUSSERHALB` (read_file, fetch_document) bzw. `P-QUELLE-AUSSERHALB`
  (read_pdf/read_docx). Ablage-ids (Anhänge, eigene Dokumente) gehen weiter.
  `unzip`/`import_skill`/`remove_input` waren schon auf Input/ begrenzt.
- **klein:** unverändert (Whitelist + ~/codicus, Gesamtliste in `list_files`);
  das qwen ist auf die Texte gemessen. Zieht später nach.
- **Was wegfällt und wodurch ersetzt:** `data/*.json` (Schlaf, Messreihen) →
  `read_series`; `notes.md` → das Gedächtnis (`read_note`/`write_note`,
  Bereich `notizen`; die Datei war nur noch die leere Vorlage);
  `core/*.py`, `ui/app.py`, ~/codicus → nichts (Coder-App). Kalender, Notizen,
  Mail, News lesen ohnehin ihre eigenen Werkzeuge.
- Tests: `tests/test_reichweite_gross.py`.

## Historie

- **2026-10-09** — Nutzerordner, Suchen, `import_skill`, `unzip`,
  `remove_input`, Input aufräumen; Rückbau der Reichweite von gross.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
