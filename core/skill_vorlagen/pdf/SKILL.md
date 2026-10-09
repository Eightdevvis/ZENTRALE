---
name: pdf
description: "Alles mit PDF-Dateien: lesen (auch lange, mit Seitenangaben), Tabellen herausziehen, Formularfelder ansehen, ein neues PDF schreiben (Brief, Liste, Übersicht, Tabelle), mehrere PDFs zusammenfügen oder einzelne Seiten herausnehmen. Auch wenn Sasha nur ein angehängtes PDF erwähnt."
---

# PDF

Du arbeitest mit drei Werkzeugen: `read_pdf` (lesen), `create_pdf` (neues
PDF aus Markdown) und `combine_pdf` (zusammenfügen, Seiten herausnehmen).
Neue Dateien landen immer als neues Dokument in Sashas Ablage — nichts wird
überschrieben, die Originale bleiben, wie sie sind. Vor jedem neuen PDF fragt
ZENTRALE Sasha; du musst nicht selbst vorher nachfragen, wenn der Auftrag klar
ist.

`run_code` hilft hier nicht: die Sandbox hat keine PDF-Bibliothek und sieht
weder die Ablage noch Sashas Dateien.

## Woher die Datei kommt

`quelle` ist entweder

- eine **Ablage-id** — so heißen auch Anhänge, die Sasha in den Chat gibt
  (die id steht im Anhang: „Original in der Ablage, id …"), oder
- ein **Dateipfad** in `Input/` oder `Output/` des Nutzerordners (z. B.
  `Input/stundenplan.pdf`; ein bloßer Name meint `Input/`). Was woanders
  liegt (Downloads, USB-Stick, Projektordner), darfst du nicht öffnen — bitte
  Sasha dann, die Datei nach `Input/` zu legen oder anzuhängen.

Ein Anhang aus der Zeit vor dem 08.10.2026 liegt nur als Text vor; dann sagt
das Werkzeug, dass das Original fehlt. Den Text liest `read_document`.

## Lesen

1. Erst ohne `seiten` lesen. Die erste Zeile sagt, wie viele Seiten es sind
   und ob es Formularfelder gibt.
2. Ist das PDF lang, kommt es in Stücken (bis ~20.000 Zeichen); das Ergebnis
   sagt `[ergebnis: teilweise]` und mit welchen Seiten es weitergeht. Lies nur
   weiter, was du für die Frage brauchst — bei einer Frage nach einem Thema
   lieber gezielt die Seiten, auf die das Inhaltsverzeichnis zeigt.
3. Nenne Seitenzahlen, wenn du etwas aus dem PDF wiedergibst („steht auf
   Seite 4"). Die Zahlen in `--- Seite n ---` zählen ab der ersten Seite der
   Datei — die aufgedruckte Seitenzahl kann davon abweichen (römische Vorwort-
   seiten, Deckblatt). Steht eine andere Zahl im Text, sag beide.

**Tabellen:** `was='tabellen'` lässt die Spalten an ihrem Platz und baut
daraus Tabellen. Das ist geraten: bei verbundenen Zellen, mehrzeiligen Zellen
oder schiefen Spalten können Werte in die falsche Spalte rutschen. Prüfe
Zahlen, auf die es ankommt (Beträge, Noten, Uhrzeiten), gegen den Text und
sag Sasha, wenn etwas unsicher ist. Wird keine Tabelle erkannt, kommt der Text
mit seinen Spalten — lies die Spalten dann selbst.

**Formulare:** `was='formular'` listet die Felder mit Name, Art und Wert
(Ankreuzfelder zeigen ihre möglichen Werte). Ausfüllen kann ZENTRALE ein
Formular noch nicht — schreib Sasha stattdessen auf, was in welches Feld
gehört.

## Wenn es nicht geht — ehrlich sagen

- **Kein Text** (`kein Text auf dieser Seite`): das PDF ist gescannt, also nur
  Bilder. Eine Texterkennung gibt es nicht. Sag das so; rate nicht, was
  draufsteht.
- **Passwort**: geschützte PDFs gehen nicht auf. Sasha kann es ohne Passwort
  neu speichern und anhängen.
- **Kaputt / dauert zu lange**: sag es, schlag vor, die Datei neu zu holen.

## Ein neues PDF schreiben

`create_pdf(titel, inhalt)`; `inhalt` ist Markdown:

- `#`, `##`, `###` Überschriften; Leerzeile trennt Absätze; `**fett**`
- Listen mit `-` oder `1.`, eingerückt eine Ebene tiefer
- Tabellen: `| Kopf | Kopf |`, darunter `|---|---|`, dann die Zeilen
- Code zwischen ``` , eine Linie mit `---`

A4, Seitenzahlen unten, Tabellen laufen über Seiten und wiederholen ihre
Kopfzeile. Bilder, Kursiv, Farben und Fußnoten gibt es nicht.

**Zeichen:** die PDF-Schrift kennt westeuropäische Zeichen (Umlaute, ß, €,
„“, –). Pfeile und ≤ ≥ werden umschrieben (→ wird `->`). Alles andere —
chinesische Zeichen, Emoji — wird zu „?". Das Ergebnis sagt dann
`[ergebnis: teilweise]` und welche Zeichen fehlen; sag es Sasha und schlag
die Word-Datei vor (die kann alle Zeichen).

Den Titel nimmt die Ablage als Namen; eine Überschrift im Dokument schreibst
du selbst in `inhalt`.

## Zusammenfügen und Seiten herausnehmen

`combine_pdf(titel, teile)` — die Teile in der gewünschten Reihenfolge, jeder
mit `quelle` und optional `seiten`:

- zwei PDFs hintereinander: `[{quelle: A}, {quelle: B}]`
- nur Seite 2–4 aus A: `[{quelle: A, seiten: "2-4"}]`
- Seite 3 aus A entfernen (A hat 10 Seiten): `seiten: "1-2,4-10"`
- Deckblatt aus B vor A: `[{quelle: B, seiten: "1"}, {quelle: A}]`

Seitenzahl unsicher? Erst `read_pdf` — die erste Zeile nennt sie.

## Danach

Das Ergebnis enthält einen Beleg („Nachgelesen: … N Seiten, Seite 1 beginnt
mit …"). Melde Sasha genau das: Titel und Seitenzahl aus dem Beleg. Steht dort
`fehlgeschlagen`, ist keine brauchbare Datei entstanden — sag das, statt
Erfolg zu melden.
