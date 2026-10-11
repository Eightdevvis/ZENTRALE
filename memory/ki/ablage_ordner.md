# Die Ablage als Ordner — ~/Zentrale/Ablage

Stand 2026-10-11. Sasha: „das problem mit der ablage ist ja momentan nur das
sie wo liegt? der user soll nich im code fischen gehen müssen" und „den
ordner wo ich sachen direkt reinschmeißen kann direkt nachrüsten". Wie Claude
Web gibt es EINEN Ort für Dateien: die Ablage. Was die KI dort ablegt, sieht
Sasha im Dateimanager; was er hineinwirft, sieht die KI.

## Auf der Platte

```
~/Zentrale/Ablage/                         Einstellung ablage_dir (Env ZENTRALE_ABLAGE_DIR)
  Führerschein-Tracking.xlsx               neueste Fassung jedes Dokuments, lesbar
  Preise Fahrschule.pdf                    … auch Eingeworfenes (bleibt, wo es liegt)
  .ablage/dokumente/<id>/kopf.json         Titel, Art, Herkunft, abgelegt_von, Papierkorb …
  .ablage/dokumente/<id>/v<n>-<rechner>.x  jede Fassung, nie überschrieben (wie bisher)
  .ablage/sichtbar-<rechner>.json          was DIESER Rechner in den Ordner gelegt hat
  .ablage/papierkorb/<id>--<name>          lesbare Datei eines Dokuments im Papierkorb
```

- Die ids bleiben (alte Gespräche, `/api/ablage/<id>/roh`, Morgenblick).
- Dateiname = Titel + Endung (ohne doppelte Endung), Konflikt → „ (2)". Eine
  ersetzte Datei übernimmt den Namen der alten.
- `core/ablage_ort.py` (Schicht 1) sagt WO, `core/ablage.py` hält Köpfe und
  Fassungen, `core/ablage_sichtbar.py` die lesbaren Dateien,
  `core/ablage_wache.py` schaut alle 3 s nach (Einstellung `ablage_wache`).

## Was nachgezogen wird (`ablage_sichtbar.abgleichen`)

| Was passiert | Folge |
|---|---|
| Neues Dokument / neue Fassung (KI, anderer Rechner) | Datei anlegen bzw. neu schreiben (sofort nach dem Schreiben über `ablage.NACH_SCHREIBEN`) |
| Sasha legt eine Datei hinein | nach **zwei Blicken mit gleicher Größe** (fertig kopiert) ein Dokument: Herkunft `einwurf`, `abgelegt_von: sasha`, Titel = Dateiname. Nicht: Verstecktes, `~$…`, `.part`/`.crdownload`/`.tmp`, nach Schlüssel Aussehendes, leer, über 10 MB (wie Anhänge), Binäres ohne bekannte Art |
| Sasha ändert eine Datei | neue Fassung (auch PDF/Word/Excel — hier entscheidet er, nicht die KI) |
| Sasha benennt um | neuer Titel (erkannt an Größe + Prüfsumme) |
| Sasha löscht | Papierkorb mit Grund „von Sasha entfernt", nichts neu angelegt, Fassungen bleiben |
| Papierkorb | Datei nach `.ablage/papierkorb/`; zurückgeholt liegt sie wieder da |

Die TUI zeigt Eingeworfenes der letzten 10 Minuten dezent beim Öffnen von
`/ablage` („neu in der ablage: …"); das Backend-Log schreibt „ABLAGE: neu
eingeworfen …".

## Mehrere Rechner (Entscheidung 2026-10-11)

- Abgeglichen werden nur Köpfe und Fassungen — unter ihrem **alten Namen**
  `data/ablage/<id>/…` (`abgleich_auswahl.AUSSEN`/`pfad()`): kein Umzug in der
  Mitte, keine Doppelten. Nur für den echten ZENTRALE-Ordner und erst, wenn
  der neue Ort existiert (sonst sähe der Abgleich eine leere Ablage und
  hielte alles für gelöscht). Datensicherung genauso.
- Die lesbaren Dateien baut jeder Rechner selbst. Was er hingelegt hat, steht
  in `sichtbar-<rechner>.json` — **eine Datei pro Rechner**, nur er schreibt
  sie. Nur damit lässt sich „Sasha hat es hier gelöscht" (stand drin) von
  „lag hier noch nie" (neu vom anderen Rechner) unterscheiden.
- Kein gemeinsamer Index je Knoten: der Kopf je Dokument IST der Index, und
  der Abgleich führt JSON feldweise zusammen (`abgleich_zusammenfuehren`) —
  archivieren auf dem PC und umbenennen auf dem Laptop überleben beide.

## Umzug

`scripts/ablage_umzug.py` (Standard `--trocken`: zeigt alt → neu und den
lesbaren Namen); `--wirklich` kopiert `data/ablage/<id>/` nach
`.ablage/dokumente/<id>/` (überschreibt nie, alt bleibt als Sicherung) und
legt die lesbaren Dateien an. `--alt <pfad>` für eine andere Quelle.
**Vor dem ersten Abgleich nach dem Merge laufen lassen** — bis dahin sieht
die Ablage leer aus (der Abgleich bleibt dank der Sperre oben beim alten Ort).

## Tests

`tests/test_ablage_sichtbar.py` (Datei sichtbar, Einwurf mit Wartezeit,
Ausschlüsse, ändern/umbenennen/löschen, anderer Rechner, Abgleich-Namen,
Umzug, Papierkorb/ersetzen/wem es gehört, Routen), `tests/test_ablage_tui.py`
(Papierkorb-Filter, Hinweis).
