# Tabellen — Excel (.xlsx) und CSV, Skill `excel`

Stand 2026-10-11. Anlass: Führerschein-Gespräch 20261011-081303 — Sasha
wollte ein Dokument, das Kosten und Stunden trackt. Die KI legte ein PDF an,
konnte es nicht ändern, legte jedes Mal eine Kopie daneben und erklärte ihm
danach SUMMEWENN zum Abtippen. Sasha: „aber auch excel werkzeuge brauch sie."

## Was sie kann (nur Cloud-Schiene `gross`)

| Werkzeug | Was | Gefragt? |
|---|---|---|
| `read_xlsx(id, blatt?, bereich?)` | Zellen zeilenweise mit Adresse: Text in `"…"`, Zahlen blank, Formeln mit dem in der Datei gespeicherten Wert (`→ 440`) oder „kein gespeicherter Wert"; je Aufruf ≤ 2.000 gefüllte Zellen, weiter mit `bereich` | nein |
| `create_xlsx(titel, blaetter[{name, zeilen, spaltenbreiten?}], format?)` | neue Tabelle in der Ablage (`format: csv`: ein Blatt, keine Formeln) | nein (wie `create_document`) |
| `edit_xlsx(id, aenderungen[{blatt?, zelle, wert}]?, anhaengen[[…]]?, blatt?, daneben?, titel?)` | Zellen setzen, Zeilen unter die letzte gefüllte anhängen | eigene Tabelle nein; **Sashas jedes Mal** (nur einmal/nein); `daneben: true` nie |

Alles über die Ablage (Ablage-id; Anhänge und Eingeworfenes sind Ablage-
Dokumente). Ändern einer **xlsx**: neue Fassung als neues Dokument, das alte
in den Papierkorb (`ablage.ersetzen`, dieselbe Logik wie `replace_document`),
die lesbare Datei in `~/Zentrale/Ablage` behält ihren Namen. Eine **CSV** ist
Text: sie bekommt eine neue Fassung (die alte bleibt). Die Anleitung für die
KI (wann Tabelle statt PDF, Formel-Tipps, ehrlich sagen) steht im Skill
`core/skill_vorlagen/excel/`.

## Formeln (Entscheidung 2026-10-11)

- In der Datei steht **immer der Excel-Standard**: englische Namen, Komma,
  Punkt als Dezimalzeichen (so speichert auch das deutsche Excel).
- Deutsche Eingaben werden **übersetzt statt abgelehnt** (`core/tabelle_formel.py`):
  ~80 Funktionsnamen (SUMME, SUMMEWENN, WENN, ZÄHLENWENN, SVERWEIS …), `;` → `,`
  und `2,5` → `2.5`, beides nur außerhalb von `"…"` und `'Blatt'`. Danach muss
  jeder Name eine echte Excel-Funktion sein (Liste aus openpyxl + neuere wie
  XLOOKUP, die mit `_xlfn.` gespeichert werden) — sonst `T-FORMEL`, nichts
  geschrieben. Der Satz nennt, was übersetzt wurde.
- **Werte rechnet ZENTRALE nicht** (openpyxl kann es nicht): der Satz nennt
  Formeln als Formeln („hier ist KEIN Wert berechnet"), die Datei hat
  `fullCalcOnLoad`, Excel/LibreOffice rechnen beim Öffnen.
- Zahlen, die als Text kommen (`"60"`, `"60,5"`), werden Zahlen; `"1.000"`
  (drei Nachkommastellen — im Deutschen tausend), `"0815"`, `"60 €"` bleiben
  Text.

## Wie es gebaut ist

| Modul | Schicht | Rolle |
|---|---|---|
| `core/tabelle_formel.py` | 1 | übersetzen und prüfen |
| `core/tabelle_datei.py` | 2 | openpyxl im **Kindprozess** (`python -I`, 60 s, CPU, 1,5 GB) wie `pdf_datei`; vorher Zip-Prüfung im Elternprozess (≤ 30 MB, ≤ 5.000 Einträge, entpackt ≤ 200 MB); `.xls`/Passwort → `T-GESPERRT`; CSV im Prozess (Trenner `;`/`,`/Tab nach Gleichmäßigkeit, schreiben mit `;`) |
| `core/werkzeug_tabelle.py` | 3 | Einträge + Gate |
| `core/ki_tabelle.py` | 3 | Werte prüfen, anlegen/ändern, **nachlesen aus der Ablage** (jede gefüllte Zelle wie verlangt), sonst alles zurück (`W-NICHT-GESPEICHERT`) |

`ablage` kennt die Art `xlsx` (Bytes wie pdf/docx, keine neue Fassung),
`ablage_text` liefert ihren Text (Vorschau in `/ablage`, Anhang an die KI mit
Kopfzeile „mehr: read_xlsx, ändern: edit_xlsx"), `anhang` nimmt `.xlsx` an.

**Warum von Hand wie pdf/word, nicht über den Werkzeug-Erzeuger:** der
Erzeuger prüft flache Felder und belegt über einen Eintrag mit Kennung; hier
gehen verschachtelte Blätter/Zeilen hinein, der Beleg ist die zurückgelesene
Datei Zelle für Zelle, und lesen liefert langen Text in Stücken. Ersetzen
teilt die Ablage-Logik mit dem erzeugten `replace_document`.

**Bibliothek:** openpyxl 3.1 (MIT, reines Python, dazu et-xmlfile), in
`requirements.txt`. Auf dem Pi und den anderen Rechnern: `pip install -r
requirements.txt`. Fehlt sie: `T-BIBLIOTHEK`.

## Grenzen und offen

- Beim Ändern verlorene Teile → **kein** Ändern (`T-VERLUST`): Diagramme,
  Bilder, Pivot-Tabellen, Makros, externe Verknüpfungen (openpyxl nimmt sie
  nicht sicher mit). Lesen geht.
- Keine Formatierung (Farben, Zahlformat €, fett) außer Spaltenbreiten.
- Gespeicherte Werte gibt es nur, wenn Excel/LibreOffice die Datei
  gespeichert hat.
- Je Aufruf ≤ 100.000 Zellen, ≤ 50 Blätter, Zelle ≤ 32.767 Zeichen,
  Blattname ≤ 31 Zeichen ohne `[ ] : * ? / \`.

## Tests

`tests/test_tabellen.py` (Formeln übersetzen/ablehnen, anlegen → lesen →
ändern mit Papierkorb, gespeicherter Wert aus Excel, Sashas Tabelle fragt /
daneben nicht, Abbrüche ohne Spuren, Diagramm → kein Ändern, Zahlen als Text,
CSV mit Trenner und Fassung, kaputt/`.xls`/Zip-Bombe/Zeitgrenze, Vorschau und
Anhang).
