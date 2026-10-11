# Dateien der KI: Suchen, Skills übernehmen, Zips — alles in der Ablage

**Stand 2026-10-11:** Auf `gross` hat die KI EINEN Ort für Dateien: die
Ablage (`~/Zentrale/Ablage`, [ablage_ordner.md](ablage_ordner.md)). Sasha legt
Dateien dort hinein (oder hängt sie an), die KI legt dort ab. `find_files`,
`search_files`, `list_files`, `read_file`, `import_skill` und `unzip` arbeiten
nur noch dort; `remove_input` ist in `trash_document` aufgegangen
([ablage.md](ablage.md)). Kein Dateipfad mehr auf gross. `klein` ist
unverändert (Whitelist + ~/codicus).

**Warum:** Sasha, 2026-10-11: „ja einfach nur die ablage dann. den ordner wo
ich sachen direkt reinschmeißen kann direkt nachrüsten." Wie Claude Web: ein
Ort, kein Input/Output-Paar, in dem man suchen muss, was wohin gehört. Die
Ordner `~/Zentrale/Input` und `Output` bleiben auf der Platte (Sasha
entscheidet), die KI sieht sie nicht mehr; `core/nutzer_ordner.py` braucht
nur noch der Desk (Bilder) und die Werkstatt (Icons).

## Die Werkzeuge (nur gross)

| Werkzeug | Was | Gefragt? |
|---|---|---|
| `list_files(papierkorb?)` | die Ablage wie ls: „Titel“ — id, Art, Fassung, von wem; neueste zuerst, ≤ 200, sagt ob vollständig | nein |
| `find_files(muster, papierkorb?)` | nach Titel: `*.pdf`, `*chefkoch*`, Titelteil (Groß/Klein und Trenner egal); zählt alle, zeigt 50 | nein |
| `search_files(text, muster?, papierkorb?)` | Text IN den Dokumenten, wie `grep -i -F` — auch im Text von PDF/Word/Excel (`ablage_text`); „Titel“ (id):zeile: auszug, ≤ 100 Treffer, ≤ 30 s | nein |
| `read_file(path)` | ein Dokument per id oder genauem Titel (auch „Titel.endung"); zwei gleichnamige → Liste der ids, nie geraten | nein |
| `import_skill(id)` | Claude-Skills aus einer Zip der Ablage (Plugin, Ordner mit SKILL.md, SKILL.md in der Wurzel) | **jedes Mal** |
| `unzip(id, ansehen?)` | jede Datei der Zip wird ein Dokument („<zip>/<pfad>", Sashas, Herkunft `ausgepackt`), ≤ 50 Dateien, ≤ 20 MB; Binäres ohne bekannte Art wird genannt und ausgelassen | ja (`ansehen` frei) |

**Jede Suche sagt, wie vollständig sie war** — fest in der ersten Zeile:
„Suche vollständig: N Treffer — durchsucht: Ablage (M Dokumente)." bzw. „Suche
NICHT vollständig: abgebrochen nach …" oder „… Dokumente nicht lesbar". Der
Prüfer „nicht da" (`core/ehrlichkeit.py`, [ehrlichkeit_live.md](ehrlichkeit_live.md))
liest diese Zeile: „gibt es nicht" nur nach einer vollständigen Suche ohne
Treffer. Bilder und Zips haben keinen Text — übersprungen, die Suche bleibt
vollständig.

`import_skill` (`core/skill_import.py`): die Zip wird in einen Wegwerf-Ordner
kopiert, geprüft (kein `..`/absolut/Symlink, ≤ 20 MB/500 Dateien, Verstecktes
und Schlüssel ausgelassen — `core/zip_sicher.py`), dann ganz oder gar nicht
nach `data/gedaechtnis/skills/<name>/` (aktiv, Herkunft sasha, Quelle mit
Plugin-Name/Version/Autor/Lizenz). Einen vorhandenen Namen überschreibt es nie
(`S-SKILL-GIBT-ES`). Die Frage nennt Skill und Datei, vorab ausgepackt.

Zips sind seit 2026-10-11 eine Art der Ablage (`zip`): Anhang und Einwurf
nehmen sie als Original an; ihre Vorschau ist die Liste der Einträge.

## Wie es gebaut ist

| Modul | Schicht | Rolle |
|---|---|---|
| `core/ablage_suche.py` | 2 | finden, durchsuchen, auflisten — mit Vollständigkeit |
| `core/ablage_zip.py` | 2 | Zip ansehen/auspacken in Dokumente |
| `core/skill_import.py` | 2 | Skills aus einer Ablage-Zip |
| `core/werkzeug_dateien.py` | 3 | Einträge, Fragen, gross-Fassung von list_files/read_file |
| `core/ki_dateien.py` | 3 | Ausführer |

`context.erlaubt` sagt auf gross zu jedem Pfad `Z-AUSSERHALB` (auch
`fetch_document` mit lokalem Pfad); `read_pdf`/`read_docx` nehmen nur noch
Ablage-ids (`P-QUELLE-FEHLT`).

## Historie

- **2026-10-09** (Gespräch 20261009-155510, Chefkoch-Zip übersehen, weil
  `list_files` bei 300 von ~5.000 Dateien kappte): Nutzerordner `~/Zentrale`
  mit Input/ und Output/, Suchen wie find/grep mit Vollständigkeit,
  `import_skill`, `unzip` nach Output/, `remove_input` in
  `~/Zentrale/.Papierkorb/<Datum>/`, eine Aufräum-Zeile + Zusage „aus Input
  weg?" nach jedem Lesen (`core/input_aufraeumen.py`). gross las keinen Code
  mehr unter ~/codicus.
- **2026-10-11**: Input/Output für die KI abgebaut, alles in die Ablage
  (Module `nutzer_suche`, `input_dateien`, `input_aufraeumen`,
  `werkzeug_nutzer_ordner`, `ki_nutzer_ordner` entfernt). Die Aufräum-Zusage
  entfiel: die Ablage hat einen Papierkorb, und was Sasha hineinlegt, ist
  dort richtig aufgehoben.

## Tests

`tests/test_ablage_dateien.py` (Suchen, Vollständigkeit, Papierkorb, unzip,
list_files), `tests/test_skill_import.py` (Übernehmen aus der Ablage, alle
Abbrüche ohne Spuren, Gate), `tests/test_reichweite_gross.py` (kein Pfad auf
gross, read_file liest die Ablage, klein unverändert).
