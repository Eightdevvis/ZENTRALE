# Projekte — Anweisungen und Wissen pro Thema

Stand 2026-10-07 (Claude-Web-Plan Phase 6, [claude_web_plan.md](claude_web_plan.md)).
Wie die Projekte in Claude Web: ein Rahmen für ein Thema (Geige, Umzug,
Steuern) mit **eigenen Anweisungen** („wie ich in diesem Thema arbeiten
will") und **Wissensdateien** (Texte, die die KI darin nachlesen kann). Ein
Gespräch gehört optional zu einem Projekt.

Code: `core/projekte.py` (Schicht 2), Routen `ui/routen/projekte.py`, TUI
`tui/ansichten/projekte.py`. Abgrenzung: **Hausregeln** gelten immer,
**Skills** sind Anleitungen für eine Art Aufgabe, ein **Projekt** ist der
Rahmen für ein Thema.

## Speicher

```
data/gedaechtnis/projekte/<id>/
  projekt.json      {name, erstellt, archiviert}
  anweisungen.md    Sashas Anweisungen (+ .bak der vorigen Fassung)
  wissen/<datei>    Wissen als Text (+ .bak, wenn ersetzt)
```

- **id** = Slug des Namens (`gedaechtnis.slug`: „Umzug Berlin" →
  `umzug-berlin`). Damit führt keine id aus dem Ordner heraus. Reserviert
  (weil sie in `/projekt` etwas bedeuten): neu, aus, kein, keins, keines,
  zuordnen.
- **Unter der Gedächtnis-Wurzel**: dieselbe Test-Umlenkung
  (`ZENTRALE_GEDAECHTNIS_DIR`), derselbe Sync, dieselbe Sicherung
  (`data/gedaechtnis/**` steht in der Positivliste von
  `scripts/daten_sichern.py`).
- **Nicht in `gedaechtnis.BEREICHE`** (wie `skills/`, Konstante
  `gedaechtnis.PROJEKTE`): sonst erreichte `write_note` die Anweisungen
  ungefragt, und `kopf_block` schriebe alle Projekt-Ordner als Titel in den
  Kopf jedes Gesprächs. Die KI schreibt in Projekten nichts.
- **Nie löschen**: Projekte werden archiviert (Flag in `projekt.json`),
  ersetzte Anweisungen und Wissensdateien liegen als `.bak` daneben. Der Sync
  ist additiv — ein Gelöschtes käme vom anderen Rechner zurück.
- `projekt.json` schreiben beide Rechner (klein, „neueste gewinnt" ist dort
  harmlos, wie `kopf.json` der Gespräche).

## Wissen

- Nur **Text** (`.md .txt .csv .json .yaml .py …` und Dateien ohne Endung),
  höchstens 200.000 Zeichen je Datei (von der Platte höchstens 2 MB).
  PDFs und Bilder nimmt ein Projekt nicht.
- Dateiname = Slug des Stamms + Text-Endung („Übungsplan.txt" →
  `uebungsplan.txt`, „bericht.pdf" → `bericht-pdf.md`). Gleicher Name →
  ersetzt, die alte Fassung als `.bak`.
- **Aus einer Datei**: erst die Sperrliste — `context.anhang_gesperrt(pfad)`,
  **dieselbe Regel wie für Anhänge** (Phase 5, eine Liste, keine zweite):
  Zugangsdaten nach Dateiname (`.env`, `*.key`, `ai_config.json`,
  `…token…`), `learning/` und Versionsverwaltung, ZENTRALEs `data/`,
  Schlüssel- und Browser-Ordner im Home, Systemdateien. Ohne die
  Wurzel-Whitelist: Sasha legt auch Dateien aus Downloads ab.
- **TUI auf einem anderen Rechner** (`zentrale-remote`): das Backend liest
  den Pfad selbst; gibt es ihn dort nicht (404 mit `fehlt: true`), liest die
  TUI die Datei und schickt den Text mit — die Sperrliste prüft das Backend
  trotzdem am Pfad.

## Gespräch → Projekt

- `kopf.json` des Gesprächs: `projekt` = id oder `null`
  (`gespraeche.projekt_setzen`, `projekt_von`). „Erinnerungen" gehört zu
  keinem Projekt.
- **/neu bleibt im Projekt**: `/api/chat/clear` merkt sich das Projekt des
  offenen Gesprächs pro Rechner (`_knoten/<knoten>.json` → `neu_projekt`);
  das nächste Senden legt das Gespräch darin an. Body `{projekt}` setzt es
  ausdrücklich (Übersicht → n). Wer ein Gespräch öffnet, löscht die Vormerkung.
- Archivierte Projekte behalten ihre Gespräche, und deren Projekt-Block gilt
  weiter (ein Gespräch ändert sich nicht, weil das Projekt aus der Liste ist).

## Im Prompt

Hat das Gespräch ein Projekt, setzt `cloud._static_system(…, projekt=)` den
Block `projekte.prompt_block(id)` in den **festen, gecachten Teil** — hinter
Gedächtnis-Kopf und Skill-Liste, vor dem Imprint, nur auf einer Schiene mit
`MERKMALE["projekte"]` (`gross`; `klein` nicht):

```
## Projekt: Geige
Dieses Gespräch gehört zu Sashas Projekt. Seine Anweisungen dafür gelten
hier zusätzlich; die Hausregeln gehen vor.

### Anweisungen
… (höchstens 4.000 Zeichen, sonst gekürzt mit Hinweis auf
read_project_file("anweisungen"))

### Wissen
Dateien des Projekts — Inhalt mit read_project_file(name), wenn es darum geht:
- noten.md (2 KB)
```

Byte-stabil (kein Datum, Dateien nach Name, höchstens 40 genannt). Der Cache
gilt damit **pro Projekt**: das erste Gespräch eines Projekts schreibt ihn,
jedes weitere liest. Keine neue Meta-Regel in `gross.system()` (dort ist
der Kopf bei ~4.974 von 5.000 Zeichen) — der Block erklärt sich selbst.

**Wie das Projekt dorthin kommt** — als Parameter, kein globaler Zustand:
`ui/routen/ki.py` (`gespraeche.projekt_von(gid)`) → `kern.chat(…, projekt=)`
→ `cloud.chat_stream` bzw. `cloud_openai.chat_stream(…, projekt=)` →
`_static_system` und `ki_werkzeuge.mit_projekt(projekt)` (der Ausführer des
Zugs). Der lokale Weg bekommt es nicht.

## Werkzeuge

| Werkzeug | Was | Gate |
|---|---|---|
| `read_project_file(name, ab?)` | eine Wissensdatei des Projekts dieses Gesprächs, höchstens 20.000 Zeichen ab Stelle `ab`; „anweisungen" liefert die ungekürzten Anweisungen | nein |
| `search_chats(query, projekt?)` | wie bisher; mit `projekt` (Name oder id) nur dessen Gespräche, ohne das alte Transkript | nein |

`read_project_file` bekommt das Projekt von `ki_werkzeuge._verteilen`
(Ausführer mit `@braucht_projekt`), **nie aus den Argumenten des Modells** —
ein mitgeschicktes `projekt` wird ignoriert. Gefunden wird nur über die Liste
des Projekts (genauer Name oder Slug des Stamms), ein Pfad im Namen führt
nirgendwo hin. Ohne Projekt sagt es das. Text-Budget: eigener Deckel < 200
Zeichen in `tests/test_profil.py`.

## Routen

[../system/api_endpoints.md](../system/api_endpoints.md), Abschnitt Projekte.

## TUI

[../system/tui_bauplan.md](../system/tui_bauplan.md), „Chat: Projekte".

## Tests

`tests/test_projekte.py` (Speicher, Sperrliste, Zuordnung, Prompt-Block,
`read_project_file`, Suche), `tests/test_projekte_routen.py`,
`tests/test_projekte_ansicht.py`, Wächter in
`tests/test_keine_seiteneffekte.py`; headless `ki_projekte` bei 80×24 und
136×30.
