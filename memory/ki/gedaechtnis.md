# Das Gedächtnis nach Themen (seit 2026-10-11)

**Stand 2026-10-11:** Das Gedächtnis liegt nach **Thema**, nicht mehr nach
Datenformat, im Format von Claudes eigenem Datei-Gedächtnis. Code:
`core/gedaechtnis.py` (was die KI tut), `core/gedaechtnis_ablage.py` (wie es
auf der Platte liegt), `core/gedaechtnis_katalog.py` (Katalog-Text). Der alte
Bestand zieht nur per Skript um (`scripts/gedaechtnis_umzug.py`), nie beim
Start; bis dahin liest der Code den alten Aufbau mit. Geschichte, Kataloge,
Skills, Import: [gedaechtnis_dateien.md](gedaechtnis_dateien.md).

## Warum

Sasha: *„die memory von zentrale ist ein haufen chaos … wir sortieren
momentan nach datenformat, FALSCH. wir sollten nach thema sortieren."* Der
Spagat lag in `dossiers/`, die Übungen in `kataloge/`, die Kurve in
`data/g_*.json` — drei Ordner für eine Sache. Und: *„guck dir einfach dich
selbst an, was du darfst und kannst in deiner memory und modellier genau
danach."* Also: eine Datei je Sache mit Kopf, ein Index im Prompt, Inhalte auf
Abruf, die KI legt selbst an, ändert und räumt weg. Weil das Format dasselbe
ist, geht ein Import aus Claude und ein Export zu Claude ohne Umbau.

## Aufbau

```
data/gedaechtnis/
  INDEX.md                          eine Zeile je Datei, nach Thema (= Claudes MEMORY.md)
  themen/<thema>/<name>.md          Notiz, Dossier, Quelle, Ziel, Projekt … (art im Kopf)
  themen/<thema>/<name>.katalog.md  viele gleichförmige Einträge (## Titel + Felder)
  themen/<thema>/<name>.reihe.json  Messreihe (Werte wie bisher) + <name>.reihe.md als Kopf
  themen/<thema>/dateien/           Binäres zu einer Quelle (immer mit Vermerk-Datei)
  themen/person/steckbrief.md, ziele.md
  themen/tagebuch/<JJJJ-MM>.md      je Tag eine Überschrift ## JJJJ-MM-TT
  ki/hausregeln.md                  Gedächtnis ÜBER die KI, getrennt von dem über Sasha
  ki/vorlagen/, ki/skills/<name>/SKILL.md
  projekte/                         unverändert (siehe unten)
  _archiv/                          was nicht mehr gilt — archiviert, nie gelöscht
  _alt_vor_themen_<datum>/          der alte Bestand nach dem Umzug, vollständig
```

Jede Datei beginnt mit Claudes Kopf:

```
---
name: spagat
description: Voller Spagat — wo es blockiert, Plan, Stand
metadata:
  art: dossier
  aktualisiert: 2026-10-11
---
```

- **`description` ist der Haken im Index** — danach entscheidet die KI, ob sie
  eine Datei liest. Er kommt von der KI (`beschreibung`), **nie aus dem
  Inhalt**: sonst stünde der Anfang jeder Notiz im gecachten Kopf.
- **`art`** steuert nur, wie angehängt wird: `notiz`, `quelle`, `steckbrief`,
  `ziel`, `regel`, `katalog` ohne Datum (Faktenliste), `dossier`, `projekt`
  und Unbekanntes unter `## JJJJ-MM-TT` (Verlauf). Fremde Felder (Claudes
  `type: feedback` u. a.) bleiben erhalten; ohne `art` gilt `type`.
- **Kataloge** haben eine eigene Endung, damit `training.md` (Dossier) und
  `training.katalog.md` nebeneinander liegen. Ein Dossier mit Katalog-Kopf
  trägt sich in den Katalog seines `katalog:`-Namens ein — gesucht in allen
  Themen, sonst neu im Thema des Dossiers.

## Was in den Prompt geht

`gedaechtnis.kopf_block()`: **Hausregeln + Steckbrief + Index + knappe Regeln**
— im gecachten Teil (`cloud._static_system`). Die **Ziele** stehen seit dem
Umbau nur noch als Indexzeile drin (`person/ziele`), nicht mehr ganz.
Der Index ist byte-stabil: `aktualisiert` steht nicht drin, er ändert sich
nur, wenn eine Datei dazukommt, wegfällt oder ihren Haken/ihre Art ändert;
das Tagebuch ist eine Zeile (Monate von … bis). `INDEX.md` wird bei jeder
solchen Änderung mitgeschrieben (nur wenn anders).

Die Regeln im Kopf (wie Claudes eigene): erst nach einer passenden Datei
suchen und die ergänzen; neue Datei mit `thema`, `art`, `beschreibung`;
nichts festhalten, was ohnehin nachlesbar ist; relative Zeitangaben als festes
Datum; bei Sashas Rückmeldungen das Warum und wann es gilt mitschreiben;
Falsches mit `archive_note` weglegen.

## Die Werkzeuge (`gross`-Schiene; `klein` unverändert)

| Werkzeug | Was | Gate |
|---|---|---|
| `read_note(name, thema?)` | Datei lesen: `sport/spagat` oder `spagat`, `ziele`, `tagebuch` (heute), `tagebuch/JJJJ-MM`, `index`, `vorlagen/dossier` | nein |
| `write_note(name, text, thema?, art?, beschreibung?)` | vorhandene Datei ergänzen (Katalog: upsert), sonst anlegen; `tagebuch`, `hausregeln` wie bisher | nur Kernakten |
| `write_note(…, herkunft)` | Import: nur Neues, zeilenweise, mit Vermerk | nur Kernakten |
| `rewrite_note(name, content, thema?)` | ganz neu schreiben, Kopf bleibt (außer der Inhalt bringt einen mit), `.bak` | ja |
| `archive_note(name, thema?)` | nach `_archiv/`, Index vergisst sie; Kernakten nie | nein |
| `search_memory(query)` | Kernakten, alle Themen samt Haken, Tagebuch; vor dem Umzug auch der alte Aufbau | nein |
| `fetch_document(url, name, thema?)` | holen und als Quelle unter dem Thema ablegen | ja |
| `create_series(name, typ, einheit?, thema?)` | neue Kurve; mit Thema liegt sie unter `themen/<thema>/` | ja |

Ein Name, der in zwei Themen vorkommt, wird **nicht geraten**: das Ergebnis
nennt beide, die KI gibt das Thema mit. Alte Präfixe (`dossiers/x`,
`kataloge/x`) versteht der Code weiter — das Modell kennt sie aus alten
Gesprächen. Ohne `thema` landet Neues in `allgemein`.

## Messreihen unter ihrem Thema

Die Werte bleiben im eigenen Format (Liste je Tag, `core/graphs.py`), nur der
Ort wandert: `graphs._values_path(gid)` → `themen/*/<gid ohne g_>.reihe.json`,
wenn es die gibt, sonst wie bisher `data/<gid>.json`. Dieselbe Stelle nutzen
`/api/log`, `/api/data`, der Zyklus (`cycle.py`), `log_series`, `read_series`.
Gelöschte Kurven unter einem Thema werden archiviert statt gelöscht. Die Id
kommt über `/api/log` von außen; `reihe_finden` lässt nichts mit `/` oder
führendem Punkt durch.

## Der Umzug (`scripts/gedaechtnis_umzug.py`)

1. Ohne Schalter (= `--trocken`): Tabelle alt → Thema, Name, Art, Haken, Ziel;
   mit `--tabelle <datei>` auch als Datei. Ändert nichts.
2. Sasha korrigiert die Spalten thema/name/art/haken; Zeilen mit „(fest)"
   (Kernakten, Vorlagen, Skills, Tagebuch) bleiben.
3. `--plan <datei> --wirklich`: alles Neue erst in `.umzug_zwischen/`, dann
   der alte Bestand nach `_alt_vor_themen_<datum>/` (auch `data/g_*.json`),
   dann Neues an seinen Platz, Index bauen. Bricht es ab, macht der nächste
   Lauf den Zwischenordner fertig. Ein zweiter Lauf findet nichts Altes mehr.
   Hat die KI nach dem Update schon in den neuen Aufbau geschrieben, wird
   zusammengeführt (alter Inhalt dazu, nie überschrieben).

Themen rät das Skript nach Stichworten (`THEMEN_REGELN`), sonst `allgemein`;
den Haken aus Katalog-Kopf, Quellen-Herkunft oder dem ersten Satz. Skills
werden nur umbenannt (`skills/` → `ki/skills/`); die mitgelieferte Fassung
von `import-memory` wird dabei erneuert, solange es Sashas unveränderte Kopie
ist. Auf EINEM Rechner laufen lassen — der Abgleich trägt es weiter
(`data/gedaechtnis/**` steht auf der Positivliste).

## Vor dem Umzug: lesen, was da ist

Nach dem Update, vor dem Umzug, wäre die KI sonst ohne Gedächtnis. Deshalb:
Kernakten, Dateien nach Name, Suche, Tagebuch und Skill-Ordner fallen auf den
alten Ort zurück; der Kopf zeigt den alten Aufbau als „alter aufbau" samt
Zielen. Geschrieben wird nur in den neuen Aufbau — ergänzt die KI eine Datei,
die es nur alt gibt, wird sie vorher in den neuen kopiert.

## Für Sasha (TUI)

`/gedaechtnis`, Abschnitt **themen**: je Thema die Dateien mit Art und Haken
(`GET /api/gedaechtnis` liefert `themen`, dazu `bereiche` in alter Form für
eine TUI, die noch nicht nachgezogen ist). Kernakten wie bisher im Editor;
den Datei-Kopf sieht Sasha dort nicht, er bleibt beim Speichern erhalten.

## Offen / späterer Schritt

- **Projekte** (`projekte/<id>/projekt.json`, `anweisungen.md`, `wissen/`)
  bleiben vorerst, wo sie sind. Als Thema mit `art: projekt` aufgehen könnten
  sie, aber dann müssten Gespräch→Projekt-Zuordnung, Projekt-Block im Prompt,
  `read_project_file` und die TUI-Projektansicht mitziehen — eigener Schritt.
- Verweise IM Text alter Dateien (`kataloge/training.md`) bleiben, wie sie
  sind; die KI versteht sie über die alten Präfixe.
