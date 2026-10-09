---
name: word
description: "Word-Dateien (.docx): lesen mit Überschriften und Tabellen, eine neue schreiben (Brief, Bewerbung, Protokoll, Vorlage) oder eine vorhandene ändern — Text ersetzen, Abschnitt anhängen — immer als neue Kopie, das Original bleibt. Auch wenn Sasha nur eine angehängte Word-Datei erwähnt."
---

# Word

Drei Werkzeuge: `read_docx` (lesen), `create_docx` (neue Datei aus
Markdown) und `edit_docx` (geänderte Kopie). Neue Dateien kommen als neues
Dokument in Sashas Ablage; eine vorhandene Datei wird nie verändert. Vor jeder
neuen Datei fragt ZENTRALE Sasha.

`run_code` hilft hier nicht: die Sandbox hat keine Word-Bibliothek und sieht
weder die Ablage noch Sashas Dateien.

## Woher die Datei kommt

`quelle` ist eine **Ablage-id** (auch Anhänge — die id steht beim Anhang)
oder ein **Pfad in `Input/` oder `Output/`** des Nutzerordners (z. B.
`Input/brief.docx`). Liegt sie woanders, bitte Sasha, sie nach `Input/` zu
legen oder anzuhängen. Alte `.doc`-Dateien und Dateien mit Passwort gehen nicht auf; Sasha
kann sie in Word oder LibreOffice als `.docx` ohne Passwort speichern.

## Lesen

`read_docx` liefert Markdown: `#` für Überschriften (nach dem Stil in Word,
nicht nach der Schriftgröße), `-`/`1.` für Listen, `| … |` für Tabellen. Die
erste Zeile nennt Absätze, Überschriften, Tabellen und was NICHT mitgelesen
wurde (Kopf-/Fußzeilen, Kommentare, Bilder, Textfelder). Sieht ein Abschnitt
im Dokument wie eine Überschrift aus, ist aber nur fett formatiert, steht er
als normaler Absatz da. Lange Dateien kommen in Stücken; weiter mit `ab`.

Bei Änderungsverfolgung zeigt das Lesen den Stand MIT den eingefügten und
OHNE die gelöschten Stellen — so, als wären alle Änderungen angenommen.

## Neu schreiben

`create_docx(titel, inhalt)`, `inhalt` als Markdown: `#`/`##`/`###`,
Absätze, `**fett**`, Listen (`-`, `1.`, eingerückt eine Ebene tiefer),
Tabellen (`| a | b |` + `|---|---|`; die erste Zeile wird Kopfzeile), Code
zwischen ```. Daraus werden echte Word-Überschriften (Navigationsbereich und
Inhaltsverzeichnis funktionieren), echte Listen und Tabellen mit Rahmen. A4,
Calibri 11. Alle Zeichen gehen (auch Chinesisch).

Für einen Brief: Absender, Empfänger, Datum, Betreff jeweils als eigene
Absätze; die Anrede als eigener Absatz.

## Ändern — immer als Kopie

`edit_docx(quelle, ersetzen?, anhaengen?, titel?)`:

1. **Erst lesen** (`read_docx`), damit du den Text genau kennst.
2. **Ersetzen:** `ersetzen: [{alt, neu}]`. `alt` muss **wörtlich** so im
   Dokument stehen (Groß/klein, Leerzeichen, Bindestriche). Jeder Treffer wird
   ersetzt, auch in Kopf- und Fußzeilen und auch, wenn Word den Text intern in
   Stücke mit verschiedener Formatierung zerlegt hat; der neue Text übernimmt
   die Formatierung des ersten Stücks. Für eine einzelne Stelle nimm genug
   Text drumherum, dass er nur einmal vorkommt.
3. **Anhängen:** `anhaengen` ist Markdown wie bei `create_docx` und kommt ans
   Ende. Die Überschriften nehmen die Stile des Dokuments (auch im deutschen
   Word „Überschrift 1").
4. Ein **Titel** für die Kopie ist optional (sonst „… (geändert)").

Was das Ergebnis sagt, ist die Wahrheit: „kommt nicht vor" heißt, `alt` stand
so nicht drin — lies nach und versuch es mit dem genauen Wortlaut, statt
Erfolg zu melden. „über einen Tab/Zeilenumbruch" heißt, diese Stelle konnte
nicht ersetzt werden; sag Sasha, welche.

Nicht möglich: Formatierung ändern (Schrift, Farbe), Bilder einfügen, Text
mitten im Dokument einfügen (außer über Ersetzen einer vorhandenen Stelle),
Änderungen nachverfolgt („rot") eintragen. Brauchst du das, sag es Sasha.

## Danach

Melde, was der Beleg sagt (Titel der Kopie, Absätze, Überschriften), und dass
das Original unverändert ist. Bei `fehlgeschlagen` ist keine Datei entstanden.
