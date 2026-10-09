# PDF und Word — die Skills `pdf` und `word`

Stand 2026-10-08. Die KI liest PDFs und Word-Dateien, schreibt neue und legt
geänderte Kopien an — alles landet als neues Dokument in der Ablage
([ablage.md](ablage.md)), Originale werden nie verändert.

## Was sie kann

| Werkzeug | Was | Gefragt? |
|---|---|---|
| `read_pdf(quelle, seiten?, was?)` | Text je Seite (`--- Seite n ---`), Stücke bis 20.000 Zeichen; `was=tabellen` (Spalten wie gesetzt, Tabellen geraten), `was=formular` (Feldname, Art, Wert) | nein |
| `create_pdf(titel, inhalt)` | neues PDF aus Markdown | **ja** („immer" möglich) |
| `combine_pdf(titel, teile[{quelle, seiten?}])` | zusammenfügen, Seiten herausnehmen, umsortieren | **ja** |
| `read_docx(quelle, ab?)` | Text als Markdown: `#` Überschriften (nach Stil), Listen, Tabellen | nein |
| `create_docx(titel, inhalt)` | neue .docx aus Markdown | **ja** |
| `edit_docx(quelle, ersetzen?[{alt, neu}], anhaengen?, titel?)` | geänderte Kopie: wörtlich ersetzen (auch über Formatwechsel, in Kopf-/Fußzeilen), Markdown hinten anhängen | **ja** |

`quelle` = Ablage-id (auch Anhänge) oder Pfad in Input/ bzw. Output/ des
Nutzerordners (seit 2026-10-09; vorher ~/codicus, außerhalb jetzt
`P-QUELLE-AUSSERHALB`) — dieselbe Sperre wie `read_file` (`context.erlaubt`). Nur Cloud-Schiene (`gross`); das
lokale qwen sieht die Werkzeuge nicht.

Markdown für neue Dateien (`core/textbloecke.py`, ein Zerleger für beide):
`#`–`###`, Absätze, `**fett**`, Listen `-`/`1.` (eine Ebene eingerückt),
Tabellen `| … |` mit `|---|` (erste Zeile = Kopf), Code zwischen ```, `---`.
Nicht: Bilder, Kursiv, Farben, Fußnoten.

Die Anleitung für die KI (wie lesen, wann Tabellen gegenprüfen, was ehrlich
zu sagen ist) steht in den Skills `core/skill_vorlagen/pdf/` und `word/`
(an, `herkunft: zentrale`); die Werkzeug-Beschreibungen sind bewusst kurz.

## Wie es gebaut ist

| Modul | Schicht | Rolle |
|---|---|---|
| `core/pdf_datei.py` | 2 | lesen, Tabellen raten, Formular, zusammenfügen — **pypdf in einem Kindprozess** (`python -I pdf_datei.py`) mit 60 s, CPU- und 1,5-GB-Grenze |
| `core/pdf_schreiben.py` | 2 | eigener kleiner PDF-Schreiber: A4, Helvetica/Courier (eingebaute Grundschriften), Umbruch nach echten Zeichenbreiten, Tabellen über Seiten mit wiederholtem Kopf, „Seite n von N" |
| `core/word_datei.py` | 2 | .docx nur mit zipfile + ElementTree: lesen, anlegen (= leeres Dokument + anhängen, EIN Weg), ersetzen, anhängen |
| `core/textbloecke.py` | 2 | Markdown → Blöcke |
| `core/ablage_text.py` | 2 | Text einer PDF/Word-Datei der Ablage, gemerkt nach Inhalt (sha256, 32 Stück) |
| `core/werkzeug_pdf_word.py` | 3 | die sechs Register-Einträge + Fragen; ans Register hinten angehängt |
| `core/werkzeug_eintrag.py` | 3 | die Klasse `Werkzeug` (aus dem Register gezogen — es stand an der 1.500-Zeilen-Grenze) |
| `core/ki_pdf_word.py` | 3 | die Ausführer: Quelle finden, lesen, ablegen, **aus der Ablage nachlesen**, Befund mit Beleg |

**Ablage:** neue Arten `pdf` und `docx` (Bytes wie `bild`, bis 30 MB, keine
neue Fassung — eine Änderung ist ein neues Dokument). `GET /api/ablage/<id>`
liefert für sie `text` (Vorschau) und `pfad`; `GET /api/ablage/<id>/roh`
liefert die Datei als Download. TUI `/ablage`: „pdf"/„word", Lesen zeigt Ort
und Text.

**Anhänge:** PDF und .docx liegen seit 08.10. als **Original** in der Ablage
(vorher nur der PDF-Text — damit gingen weder Formulare noch Zusammenfügen).
Die KI bekommt ihren Text mit einer Kopfzeile („PDF, 12 Seiten — Original in
der Ablage, id …; read_pdf"). Gescanntes wird angenommen (Hinweis „kein Text
drin"), Passwort/kaputt/`.doc` abgelehnt. Alte Text-Anhänge erkennt
`read_pdf` und sagt, dass das Original fehlt.

**Ein PDF-Weg:** `gedaechtnis.pdf_text` (fetch_document) geht seit 08.10.
auch über `pdf_datei.text_alle` (mit Seitenmarken) statt `pdftotext` —
poppler wird nicht mehr gebraucht.

## Warum so (Entscheidungen 2026-10-08, Sasha schlief)

| Wahl | Alternative |
|---|---|
| **Werkzeuge im Register**, Skill = Anleitung | Skripte in der Sandbox wie Claudes Skills (Sandbox hat kein pypdf, sieht weder Ablage noch Dateien, jeder Lauf gefragt, Ergebnis nur über das gefragte `save_from_sandbox`) |
| **pypdf** (BSD, reines Python) | pdfplumber (bessere Tabellen, braucht pypdfium2 + Pillow — keine reinen Python-Pakete), pdftotext (System-Paket, nicht überall) |
| **eigener PDF-Schreiber** mit Grundschriften | reportlab/fpdf2 (brauchen Pillow) |
| **Word nur Standardbibliothek** | python-docx (braucht lxml, kein reines Python) |
| pypdf im **Kindprozess mit Grenzen** | im Backend (ein bösartiges PDF hielte einen Thread fest, den niemand beenden kann) |
| Schreiben **gefragt, „immer" möglich** | frei wie `create_document` (Auftrag: schreibende Aktionen durchs Gate; es wird nie überschrieben, daher „immer" erlaubt) |
| Ändern = **neues Dokument**, Titel „… (geändert)" | neue Fassung desselben Dokuments (Auftrag: „immer als NEUE Datei") |
| Zeichen außerhalb Windows-1252 im PDF → „?", **seit 09.10. ABGEBROCHEN mit `P-ZEICHEN`, nichts angelegt** (vorher „teilweise"); Pfeile/≤≥ umschrieben | Schrift einbetten (DejaVu liegt nicht auf jedem Rechner; Teilmengen bräuchten fonttools) |
| Passwort-PDFs: nur „leeres Passwort" geht auf | Passwort als Parameter (stünde im Verlauf und im Log) |
| Tabellen aus spaltentreuem Text **geraten**, mit Hinweis „gegen den Text prüfen" | keine Tabellen |
| Formulare **nur lesen** | ausfüllen (eigene Arbeit: Erscheinungsbild der Felder; offen) |
| `edit_docx`: Treffer über Tab/Zeilenumbruch **ausgelassen und gemeldet** | Tab mit ersetzen (änderte Layout ungefragt) |
| Kopf-/Fußzeilen werden **ersetzt, aber nicht gelesen** (Hinweis) | auch lesen (mehr Text bei jedem Lesen; selten gefragt) |
| Anhang-Grenze bleibt **10 MB** | 20 MB (TUI-Grenze und Flask-Körper mitziehen — später) |
| pypdf `>=6,<7`, Breiten aus `pypdf._codecs.core_font_metrics` (fehlt es: geschätzt) | eigene Breitentabelle (Adobe-AFM abschreiben) |

## Grenzen und offen

- Keine Texterkennung (OCR) für Scans — die KI sagt es.
- PDF-Formulare ausfüllen, Seiten drehen, Wasserzeichen: nicht gebaut.
- Word: keine Formatierung ändern, keine Bilder, keine nachverfolgten
  Änderungen schreiben, kein Einfügen mitten im Text (außer per Ersetzen),
  `.doc` nicht.
- Der Pi: pypdf muss dort per `pip install -r requirements.txt` nachkommen.

## Tests

`tests/test_pdf_word_dateien.py` (Dienste: Rundreise, Tabellen über Seiten,
Formular, Scan, Passwort, kaputt, Zeitgrenze, Zusammenfügen; Word mit
deutschen Stil-ids, Ersetzen über Läufe/Kopfzeile, Anhängen mit fremden
Stilen, mc:Ignorable, Zip-Bombe, .doc), `tests/test_pdf_word_werkzeuge.py`
(Werkzeuge mit Status und Beleg, Original bleibt, Gate-Fragen, Anhänge,
Routen, TUI, Skills nennen nur echte Werkzeuge), Belege in
`test_werkzeug_belege.py`.
