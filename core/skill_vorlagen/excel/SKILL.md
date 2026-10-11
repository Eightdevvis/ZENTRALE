---
name: excel
description: "Tabellen als Excel (.xlsx) oder CSV: Listen, die wachsen und selbst rechnen — Kosten, Stunden, Budget, Restbetrag, Einkäufe, Tracking. Anlegen, lesen (Formeln und gespeicherte Werte), Zellen ändern, Zeilen anhängen; SUMMEWENN & Co. Auch wenn Sasha nur „Tabelle“, „Excel“, „tracken“ oder „zusammenrechnen“ sagt."
---

# Excel und CSV

Drei Werkzeuge, alles in Sashas Ablage (er sieht die Datei in
`~/Zentrale/Ablage` und öffnet sie mit Excel oder LibreOffice):

- `read_xlsx(id, blatt?, bereich?)` — Zellen mit Adresse; Text in `"…"`,
  Formeln mit dem Wert, den Excel zuletzt gespeichert hat (`→ 440`), oder
  „kein gespeicherter Wert".
- `create_xlsx(titel, blaetter=[{name, zeilen, spaltenbreiten?}], format?)` —
  neue Tabelle (`format: "csv"` für reine Werte).
- `edit_xlsx(id, aenderungen=[{blatt?, zelle, wert}], anhaengen=[[…]], blatt?, daneben?)`
  — Zellen setzen, Zeilen unten anhängen.

## Wann eine Tabelle statt PDF

- **Alles, was wächst oder rechnet:** Kosten, Fahrstunden, Budget,
  Ausgaben, Zählungen, Listen mit Status (offen/bezahlt). Eine neue Zeile
  ist ein `edit_xlsx` mit `anhaengen` — keine neue Datei.
- **PDF nur für Endfassungen**, die so bleiben (Brief, Bewerbung,
  Ausdruck). Ein PDF, das Sasha jede Woche ändern will, ist eine Tabelle.
- CSV nur, wenn Sasha ausdrücklich CSV will oder die Daten woandershin
  gehen; CSV kann keine Formeln.

## Gut anlegen

- Erste Zeile = Überschriften (`Datum`, `Was`, `Betrag`, `Status`).
- **Zahlen als Zahlen** (`60`, nicht `"60 €"`) — sonst rechnet keine Formel.
  Das Euro-Zeichen gehört in die Überschrift („Betrag (€)").
- Datum als Text `2026-10-11` oder wie Sasha es schreibt.
- Summen und Reste als **Formeln**, nie ausgerechnet hineinschreiben —
  dann stimmen sie auch nach der nächsten Zeile noch.
- `spaltenbreiten` für Lesbares (z. B. `[14, 30, 10, 10]`).

## Formeln

Deutsch oder englisch — gespeichert wird der Excel-Standard (englisch,
Komma); das deutsche Excel zeigt sie beim Öffnen wieder deutsch.

| Was | deutsch | in der Datei |
|---|---|---|
| Summe | `=SUMME(B2:B50)` | `=SUM(B2:B50)` |
| Summe mit Bedingung | `=SUMMEWENN(D:D;"bezahlt";C:C)` | `=SUMIF(D:D,"bezahlt",C:C)` |
| Restbetrag | `=B1-SUMMEWENN(D:D;"bezahlt";C:C)` | `=B1-SUMIF(…)` |
| Zählen mit Bedingung | `=ZÄHLENWENN(E:E;"Pflicht")` | `=COUNTIF(E:E,"Pflicht")` |
| Wenn | `=WENN(C2>0;"offen";"")` | `=IF(C2>0,"offen","")` |

- **Bereiche nicht über die Summenzeile**: Summe in Zeile 20 →
  `B2:B19`; oder die Summe in eine eigene Spalte/nach oben legen und ganze
  Spalten (`C:C`) nehmen, wenn darin sonst nur Zahlen stehen.
- Restbetrag: Budget in eine eigene Zelle (z. B. `B1`), dann
  `=B1-SUMMEWENN(…)` — schrumpft von selbst mit jeder bezahlten Zeile.
- **Werte rechnet ZENTRALE nicht aus.** Nach dem Anlegen steht eine Formel
  ohne Wert in der Datei; nenn Sasha nie eine Summe, die du nicht selbst
  aus den Zellen zusammengezählt hast (und sag dann, dass du gezählt hast).
  Eine Datei, die Sasha in Excel gespeichert hat, bringt ihre Werte mit
  (`→ 440` in read_xlsx).
- Unbekannte Funktion → Abbruch `T-FORMEL`, nichts geschrieben.

## Ändern

- Erst `read_xlsx`, dann `edit_xlsx` mit den genauen Zellen.
- Deine eigene Tabelle: die neue Fassung ersetzt sie, die alte kommt in den
  Papierkorb (zurück mit `restore_document`). Sashas Tabelle (angehängt
  oder von ihm in den Ordner gelegt): er wird gefragt; sagt er nein, ist
  nichts passiert — `daneben: true` legt dann eine geänderte Kopie
  daneben, ohne Frage.
- Tabellen mit Diagrammen, Bildern, Pivot-Tabellen oder Makros ändert das
  Werkzeug nicht (`T-VERLUST`): Sasha sagen, er ändert sie selbst.
- `anhaengen` setzt unter die letzte gefüllte Zeile — steht dort eine
  Summenzeile, die Summe lieber nach oben oder in eine eigene Spalte legen.

## Ehrlich sagen

- Was du angelegt/geändert hast, steht im Ergebnis-Satz (Zellen, Zeilen,
  Formeln, was übersetzt wurde) — gib das wieder, nichts dazu.
- Ist eine Spalte Text statt Zahl (`"60 €"`), sag es: dann rechnet die
  Summe sie nicht mit.
