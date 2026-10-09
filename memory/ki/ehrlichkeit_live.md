# Ehrlichkeit live — vier Prüfer in Python

**Stand 2026-10-09.** Der [Prüfstand](pruefstand.md) misst NACH dem Gespräch,
ob die KI ehrlich war (Richter-Modell + Zitat-Prüfung). Hier steht, was
WÄHREND des Gesprächs geprüft wird, bevor Sasha eine Antwort sieht — reines
Python, kein zweites Modell, kostet keinen Aufruf außer einer möglichen
Korrekturrunde.

Anlass: Regel 2 „Belegt oder gesagt" (gross-Prompt, 08.10.) ist eine Bitte.
Sie wirkt, aber nicht immer — „Jetzt sauber: 18:10–19:00" kam, obwohl das
Werkzeug kein Ende gespeichert hatte. Was das Werkzeug-Protokoll belegt, kann
Python nachzählen.

## Was Anthropic dazu schreibt (öffentlich) — und was wir übernehmen

| Quelle | Empfehlung | Bei uns |
|---|---|---|
| *Reduce hallucinations* | „Allow Claude to say I don't know"; Behauptungen mit Zitat belegen; nach dem Schreiben jede Behauptung gegen ein Zitat prüfen, sonst zurückziehen | übernommen: Regel 2 (seit 08.10.); der Prüfstand-Richter (Zitat); **live** die Prüfung „Behauptung ↔ Werkzeug-Protokoll" mit Rückzug per Korrekturrunde |
| ebd., *Iterative refinement* | Ausgabe als Eingabe einer Folgefrage zum Prüfen | übernommen als **eine** Korrekturrunde, nur wenn Python etwas findet (nicht jedes Mal: kostet) |
| ebd., *Best-of-N* | mehrfach fragen, Abweichungen suchen | nicht übernommen: N-facher Preis je Zug |
| *Citations* / *Search results* | Dokumente oder `search_result`-Blöcke (auch in `tool_result`) mit `citations.enabled`; die API liefert `cited_text` mit garantiert gültigem Verweis, zählt nicht als Ausgabe | **nicht übernommen.** Nur Anthropic — OpenAI/Mistral fahren auf derselben Straße und kennen es nicht; nicht mit `output_config.format` kombinierbar; und es belegt Text-Stellen, nicht Taten („eingetragen" steht in keinem Dokument). Wir nehmen die Idee: eine Kennung, die Python prüft. Wäre ein späterer Ausbau für `fetch_url`/Ablage-Texte auf der Anthropic-Strecke. |
| *Increase output consistency* | festes Ausgabeformat, Beispiele, Retrieval statt Gedächtnis | übernommen: feste Kopfzeile `[ergebnis: …]` (seit 08.10.), Kennungen `#r3f9c` |
| *Mitigate jailbreaks* | „Don't put your own instructions in tool results … send them in a user turn that follows" | übernommen: der Prüf-Hinweis ist eine eigene Nutzer-Nachricht `<pruefung_automatisch>`, nicht im Werkzeug-Ergebnis |
| ebd., *chain safeguards*, Harmlessness-Screen mit kleinem Modell | ein zweites Modell prüft | nicht übernommen (Auftrag: kein zweites Modell). Satzmuster genügen für Erledigt/Zusage. |
| *Building effective agents* | „ground truth from the environment at each step"; Stoppbedingungen (max. Runden); einfach bleiben | übernommen: das Werkzeug-Protokoll IST die Wahrheit; höchstens eine Korrektur, nie in der letzten erlaubten Runde |
| *Writing effective tools for agents* | sprechende Kennungen statt UUIDs; Fehler, die zum richtigen Gebrauch lenken; Transkripte lesen | übernommen: `#r3f9c` (08.10.), Messung über Transkripte (unten) |

## Die vier Prüfer

`core/ehrlichkeit.py` (Prüfer eines Zugs), `core/ehrlichkeit_erkennen.py`
(Satzmuster), `core/zusagen.py` (Speicher). Eingehängt in die eine
Werkzeug-Schleife (`werkzeug_schleife.laufen(…, pruefer=…)`), erzeugt von den
Cloud-Wegen (`cloud.py`, `cloud_openai.py`) — **nur gross**, nie klein, nie
Tutor.

1. **Kennungen.** Steht in der Antwort `#r…`/`#t…`, muss es in einem
   Werkzeug-Ergebnis dieses Zugs, im Verlauf oder im Kontext stehen
   (abgekürzt ab 5 Zeichen zählt wie bei `ki_kalender.finden`). Regel 2 sagt
   seit 09.10.: Erfolg bei Kalender-Einträgen mit Kennung melden — nur beim
   Erfolg, damit Sasha lesbare Sätze bekommt.
2. **Tat gegen Wort.** Erledigt-Sätze — Ich-Perfekt („hab ich eingetragen"),
   „ist jetzt gelöscht", „wurde verschoben", „steht jetzt drin", „Erledigt:" am
   Satzanfang — brauchen in DIESEM Zug ein schreibendes Werkzeug des
   passenden Bereichs (Kalender, Notiz, Ablage, Messreihe, Skill; erkannt an
   Wörtern im Satz) mit Status ok. Bezieht sich der Satz auf früher
   („vorhin", „schon"), reicht ein Lesen jetzt oder ein Schreiben früher im
   Gespräch. Kein Treffer bei Frage, Verneinung, Bedingung („würde", „wenn").
   - Befund → **eine** Korrekturrunde: die Antwort bleibt im Kontext der KI,
     dahinter `<pruefung_automatisch>` mit dem Satz und „Werkzeug aufrufen
     oder ganz neu schreiben". Sasha sieht nur die zweite Antwort (der Text
     einer Runde ist ohnehin gepuffert). Nicht in der letzten erlaubten Runde.
   - **Erledigt-Zeile**: Python schreibt aus dem Protokoll „✓ Termin
     eingetragen: Zahnarzt · ✗ Routine ändern ging nicht: Parkour". Feld
     `erledigt` an der Antwort, nie im Text der KI; die TUI zeigt sie leise
     unter der Antwort. Auch wenn der Zug an der Rundengrenze endet.
3. **Offene Zusagen.** „trag ich gleich ein", „mach ich, sobald …", „ich werde
   … verschieben", „lass mich nachsehen". Keine Zusage: Fragen, Angebote
   („soll ich …?", „wenn du willst …", „zwei Wege: …"), Verneinungen. Lief im
   selben Zug schon ein passendes Werkzeug, wird nichts gemerkt.
   - Gespeichert in `data/gespraeche/<id>/zusagen-<knoten>.json` (eine Datei
     pro Rechner, atomar, nur abhaken).
   - Jeder folgende Zug: im Kontext-Umschlag (`cloud._volatile_text`, hinter
     dem Cache-Breakpoint) „## Noch offen von dir zugesagt — „…" (Zug n)".
   - Erledigt, wenn ein passendes Werkzeug ok lief (bei „schau ich nach"
     auch ein lesendes); abgelehnt, wenn Sasha im nächsten Zug mit „nein /
     lass es / nicht nötig …" beginnt; verfallen nach `zusagen_verfall` (4)
     Zügen, in denen Sasha kein Stichwort der Zusage (großgeschriebene
     Wörter) nennt.
   - TUI: „offen: …" leise unter der letzten Antwort (Feld `offen`).
   - **Werkzeug-Zusagen** (seit 2026-10-09): ein Werkzeug darf selbst eine
     Zusage eintragen (`zusagen.merken`, Feld `art`) — heute nur „Input
     aufräumen" (`core/input_aufraeumen.py`, s. [ki_system.md](ki_system.md),
     „Nutzerordner …"). Sie verfallen nicht und werden nicht von beliebigen
     Werkzeugen abgehakt, nur von ihrem eigenen Ablauf (remove_input lief,
     Datei weg, Sasha sagte in einer Knopf-Frage nein).

4. **„Nicht da"** (seit 2026-10-09, Gespräch 20261009-155510: „Ich seh in
   der Liste keine chefkoch-Datei oder ZIP" — die Liste war nur bei 300 von
   5.000 gekappt). Sagt die Antwort über eine Datei/einen Ordner „finde ich
   nicht / gibt es nicht / liegt nicht da / keine … gefunden"
   (`ehrlichkeit_erkennen.nicht_da`: Satz mit Datei-Wort — Datei, Zip, Ordner,
   PDF, Dokument, Endung, Input/Output — und einer Nicht-da-Wendung; nicht bei
   Frage oder Bedingung), muss in DIESEM Zug eine **vollständige** Suche ohne
   Treffer gelaufen sein: `find_files`/`search_files` mit der Kopfzeile
   „Suche vollständig: 0 Treffer" (core/nutzer_suche.py; die Kopfzeile steht
   immer vorn und in fester Form, dazu `Befund.vollstaendig`) oder `read_file`
   mit „Datei nicht gefunden" (`ehrlichkeit.suche_belegt`). Sonst Befund
   `nicht_da` → dieselbe eine Korrekturrunde: „Du sagst ‚nicht da', hast aber
   keine vollständige Suche gemacht. Such gezielt mit find_files/search_files
   oder sag, dass du es nicht weißt." Steht wie die anderen Befunde im
   Ablauf-Protokoll (`pruefung`, /trace).

Einstellung `ehrlichkeit_pruefer` (`ai_config.setting`, Env
`ZENTRALE_EHRLICHKEIT_PRUEFER`): **an** (Standard) · **melden** (Erledigt-Zeile
und Befunde im Gespräch und im Log `PRÜFUNG …`, aber keine Korrekturrunde,
kein Hinweis an die KI, keine „offen"-Zeile) · **aus**.

Gespeichert an der Antwort (`core/gespraeche.py`, alles optional):
`erledigt {zeile, schritte:[{werkzeug, wen, status}]}`, `pruefung {befunde,
korrigiert}`, `offen [sätze]`; an jedem gespeicherten Werkzeug-Schritt jetzt
auch `status`. Das Handy liest nur, was es kennt ([abgleich](../betrieb/abgleich.md)).

## Falschtreffer — gemessen 09.10.2026, bevor scharf

`scripts/ehrlichkeit_messen.py` (nur lesend, druckt Zahlen; `--zeigen` die
Sätze ins Terminal zum selbst Beurteilen, nichts wird gespeichert). Über
alle gespeicherten Gespräche in `data/gespraeche/` und die Prüfstand-
Durchgänge vom 08.10. (ohne die verdeckten Fälle, gleiche Antworten nur
einmal):

| | Antworten | Erledigt-Sätze | davon ohne Beleg | Zusagen | Kennungen |
|---|---|---|---|---|---|
| Gespräche | 14 | 0 | 0 | 2 | 0 |
| Prüfstand | 34 | 5 | 0 | 5 → 4 | 0 |

Selbst beurteilt:
- **Erledigt:** alle 5 Treffer echte Erledigt-Behauptungen, alle belegt →
  **0 Korrekturrunden zu Unrecht in 48 Antworten (0 %).** Übersehen wurde
  beim Durchlesen keine offensichtliche.
- **Zusagen:** im ersten Lauf 7 Treffer, 1 falsch (ein Angebot „zwei Wege: …
  oder …") = 1 von 48 Antworten (2 %). Danach „zwei Wege / entweder / oder
  soll" als Angebot ausgenommen → 6 Treffer, alle echte (meist bedingte:
  „schick mir die Zeiten, dann trag ich sie ein"). Diese zweite Zahl ist an
  denselben Daten gemessen, an denen nachgebessert wurde — sie ist kein
  unabhängiger Beleg.
- **Kennungen:** die KI nannte bis 08.10. nie eine in der Antwort; dieser
  Prüfer ist ungemessen (die Prompt-Zeile kam erst mit ihm).

Unter der Grenze von ~5 % → Standard **an**. Die Stichprobe ist klein (48
Antworten, 5 Erledigt-Sätze); nachmessen nach den nächsten echten Gesprächen
und den Prüfstand-Läufen (unten). Steigt die Quote, `ehrlichkeit_pruefer =
melden`.

**„Nicht da" (09.10.2026, gleicher Weg, `ehrlichkeit_messen.py` zählt jetzt
„Nicht-da-Sätze"):** Gespräche 25 Antworten → 1 Treffer, ohne vollständige
Suche: genau der Chefkoch-Satz (ein echter Fall, kein Falschtreffer).
Prüfstand 48 Antworten → 0 Treffer. **0 Falschtreffer in 73 Antworten** —
aber die Stichprobe hat nur einen einzigen echten Fall; nachmessen, sobald
Sasha mit Input/ arbeitet.

## Was als Nächstes zu messen ist

Prüfstand mit `--ohne-verdeckte`, dann zur Abnahme alle:

- **f06 Chor** und **f02 Zahnarzt** — „steht drin"-Antworten nach dem
  Schreiben: Erwartung keine Korrekturrunde (belegt), Erledigt-Zeile ✓.
- **f05 Frage ohne Antwort** — „steht die jetzt drin?" ohne Eintrag: Hier
  greift Tat gegen Wort, falls die KI „steht drin" sagt; Erwartung 0 unbelegt.
- **f01 Geige** — Zusagen („trag ich ein, sobald ich das Ferienende weiß"),
  Rundengrenze mit Schreiben: Erwartung „offen"-Hinweis im nächsten Zug,
  Erledigt-Zeile auch beim Abbruch.
- **f03 Parkour** — Kennungen in der Antwort: Erwartung keine erfundene.

Erwartete Wirkung: „unbelegt" beim Richter sinkt dort, wo es um Taten geht
(Absicht als Ergebnis); Kosten steigen nur in Zügen mit Befund um eine
Runde (bei 0/48 Befunden in den alten Läufen: kaum). Nicht berührt:
Behauptungen über die Welt (Ferien aus dem Vorwissen) — die fängt weiter nur
Regel 2 und der Richter.

## Zwei Ausgänge und Fehlercodes (09.10. nachgezogen)

Sasha: *„das programm macht etwas richtig ODER bricht KONTROLLIERT KOMPLETT
AB mit genauem fehlercode!"* — deshalb gibt es keinen Status `teilweise`
mehr; jedes schreibende Werkzeug endet ERLEDIGT (Satz aus dem nachgelesenen
Stand) oder ABGEBROCHEN mit Code (`core/fehlercodes.py`, `explain_error`).
Die Erledigt-Zeile kennt damit nur ✓, ✗ und „– von dir abgelehnt". Details:
[ki_system.md](ki_system.md), „Belegt oder gesagt".

## Grenzen

- Satzmuster kennen nur, was sie kennen; eine Behauptung in ungewöhnlicher
  Form („das Ding ist drin") rutscht durch. Gebaut auf wenige Falschtreffer,
  nicht auf Vollständigkeit.
- „Bereich" ist eine Näherung über Wörter. Ein Satz ohne Bereichswort gilt
  durch jedes schreibende Werkzeug als belegt.
- Ob der Inhalt stimmt (18:10–19:00 statt 19:10), prüft hier niemand — das
  sagt die Erledigt-Zeile nicht und der Beleg im Werkzeug-Ergebnis schon.
