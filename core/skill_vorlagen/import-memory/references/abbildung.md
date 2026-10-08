# Wohin was kommt

Geschrieben wird immer mit `write_note(name, text, herkunft)` — eine Datei
je Aufruf, eine Tatsache je Zeile, höchstens 30 Zeilen. Der Code hängt an
jede Zeile `[import <herkunft> <heute>]`, überspringt, was schon dasteht,
und lässt Zeilen mit Links weg.

| Im Export | Ziel | `name` | Ja-Knopf |
|---|---|---|---|
| Antwortstil, Ton, Format („sei knapp") | Hausregeln — **nur wenn Sasha es im Plan ausdrücklich will** | `hausregeln` | ja, jedes Mal |
| Wie du bei einer bestimmten Art Aufgabe vorgehen sollst | Notiz | `notizen/arbeitsweise` | nein |
| Stabile Eckdaten über ihn: was er macht (Beruf/Studium), Stadt, wichtigste Interessen in einem Satz | Steckbrief — **wenige Zeilen**, er steht in jedem Gespräch im Kopf | `sasha` | ja, jedes Mal |
| Ausdrücklich als Ziel genannt („will bis Sommer …") | Ziele | `ziele` | ja, jedes Mal |
| Beruf und Ausbildung im Einzelnen (Fach, Stelle, Werkzeuge) | Notiz | `notizen/beruf` | nein |
| Ein Projekt, zu dem es **schon ein Dossier** gibt | das Dossier (unter einer Überschrift „Datum · import …") | `dossiers/<titel>` | nein |
| Ein Projekt ohne Dossier | eine eigene Notiz je Projekt — Sasha macht später ein Vorhaben daraus, wenn er will | `notizen/<projekt>` | nein |
| Vorlieben (Essen, Musik, Werkzeuge, Medien) | eine Notiz, oder die passende vorhandene | `notizen/vorlieben` | nein |
| Interessen und Themen | eine Notiz, oder die passende vorhandene | `notizen/interessen` | nein |
| Menschen in seinem Leben (nach dem Filter: Beziehungswort statt Name bei Familie/Partner) | eine Notiz | `notizen/personen` | nein |
| Alles, was nirgends passt | Sammelnotiz der Quelle | `notizen/aus-<herkunft>` | nein |

## Nicht als Ziel

- **Kataloge** (`kataloge/…`): dort ersetzt ein gleichnamiger Eintrag den
  alten — ein Import würde Sashas Fassung überschreiben. Der Code lehnt das
  ab. Ideen aus dem Export kommen in eine Notiz; zum Katalog-Eintrag macht
  Sasha sie später.
- **Tagebuch**: das ist, was hier passiert ist, kein mitgebrachtes Wissen.
- **Projekte** von ZENTRALE (`/projekte`) und **Skills**: die legt nur Sasha
  an. Schlag sie ihm am Ende höchstens vor.

## Gibt es schon eine passende Datei?

Nimm die vorhandene (der Kopf nennt die Titel), statt eine neue mit fast
gleichem Namen anzulegen — `notizen/musik` statt zusätzlich
`notizen/vorlieben-musik`. Lies sie vorher mit `read_note`.
