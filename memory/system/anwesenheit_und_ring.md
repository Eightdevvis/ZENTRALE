# Anwesenheit, Aufmerksamkeit — und der Ring

`core/anwesenheit.py` · `tui/zentrale_tui.py` (`ring_zeilen`) · `ui/app.py`

## Warum

Sasha, 20.08.2026:

> *„ich würde sagen, dass die ai den unterschied jetzt mitkriegt von ‚sasha sieht
> mich nicht direkt an, ich spreche sie an um aufmerksamkeit zu erregen' und
> ‚sasha sieht mich direkt an, ich habe ihre aufmerksamkeit sicher und kann ihr
> mitteilen worum es geht'. … die anwesenheit wird per code assessed."*

Das ist die richtige Arbeitsteilung. **Ob jemand am Rechner sitzt, ist eine
Messung, keine Einschätzung** — ein Sprachmodell, das darüber spekuliert,
spekuliert falsch und selbstbewusst. Es bekommt eine fertige Lage und
entscheidet nur noch, WAS es damit sagt.

## Die vier Lagen

| Lage | Bedeutung | Was folgt |
|---|---|---|
| `offen` | ZENTRALE steht sichtbar vor ihm | Sie hat seine Aufmerksamkeit — direkt sagen, worum es geht. Kein Popup. |
| `woanders` | Er ist an der Maschine, ZENTRALE ist zu | Aufmerksamkeit erst holen: Benachrichtigung, **ein Satz**. |
| `weg` | Niemand an der Maschine | Trotzdem melden — er sieht es beim Zurückkommen. Aber keine Frage stellen, auf die jemand antworten müsste. |
| `unbekannt` | Kein X, kein i3 (Pi, ssh) | Wird wie `woanders` behandelt. **Lieber einmal zu viel gemeldet als eine Erinnerung verschluckt.** |

## Woraus die Lage entsteht

- **Anwesenheit** (`da()`): X11-Leerlaufzeit über die XScreenSaver-Erweiterung,
  per `ctypes` statt über ein externes Programm — `xprintidle` ist hier nicht
  installiert, und eine Abhängigkeit, die man erst nachinstallieren muss, fällt
  genau dann aus, wenn niemand hinschaut. Schwelle: 10 Minuten, bewusst
  großzügig — **wer liest, tippt nicht.**
- **Sperre** (`gesperrt()`): logind, `LockedHint`. Das ist die Auskunft der
  Sitzungsverwaltung selbst.

  > **Die Falle:** der erste Versuch suchte nach laufenden Sperrprogrammen.
  > `light-locker` steht in Sashas i3-Autostart und **läuft dauernd** — die
  > Erkennung meldete „gesperrt", solange die Maschine an war, und ZENTRALE
  > hätte ihn permanent für abwesend gehalten. Daemons taugen nicht als
  > Sperr-Signal. Der Prozess-Weg blieb nur als Rückfall für Sperrer, die es
  > während der Sperre überhaupt erst gibt (`i3lock` & Co.).

- **Aufmerksamkeit**: `melden.sichtbar()` — liegt ZENTRALEs Fenster im
  Scratchpad oder auf einem verlassenen Workspace, sieht er es nicht
  (→ `memory/betrieb/systemeinheit.md`).

**Hier dockt später Sensorik an.** Ein PIR-Melder oder ein Mikrofon ändert
`da()` — nicht den Prompt, nicht den Takt, nicht die TUI.

## Was die KI davon sieht

Einen Satz. Keine Millisekunden, keine Schwellen:

> *„Sasha ist an der Maschine, hat ZENTRALE aber zu — er arbeitet gerade an
> etwas anderem."*

Zahlen im Prompt wären eine Einladung, daraus etwas abzuleiten, und Modelle
rechnen an solchen Zahlen gern vorbei. Der Satz hängt am Takt-Auftrag, **nicht**
im Prompt jedes Turns: wenn Sasha selbst schreibt, ist die Aufmerksamkeitsfrage
ohnehin beantwortet, und ein Satz pro Turn wäre bezahlter Ballast.

Bei `woanders`/`weg`/`unbekannt` kommt eine Anweisung dazu: *ein Satz, mehr
liest er in der Einblendung nicht; reicht das nicht, sag ihm, er soll in den
Chat kommen, und leg das Ausführliche dort ab.* Das ist Sashas „die
benachrichtigungen sind flexibel".

Die Lage wird **einmal pro Anstoß** bestimmt und entscheidet dann beides —
Formulierung und Kanal. Zweimal fragen hieße zwei i3-Abfragen und die
Möglichkeit, dass sie sich widersprechen: dann passt der Text nicht zum Weg,
auf dem er ankommt.

## Der Ring

Sasha: *„die ganzen befehle die in der mitte stehen rutschen einfach in die
leiste unten. in der mitte bleibt stehen zentrale ai. sie zeigt sich als einen
mit ascii gezeichneten ring."*

Die Mitte zeigte bis dahin `KASSETTE · TUI` und eine Liste der Tastenbefehle.
Eine Merkhilfe gehört an den Rand; **die Mitte gehört ihr.**

- **Gerechnet, nicht gemalt** (`ring_punkte`/`ring_zeilen`, reine Funktionen).
  Ein festes ASCII-Bild passt genau in eine Fenstergröße; dieser Ring wächst
  mit dem Kasten. Und weil er aus Winkeln entsteht, ist die wandernde Helle
  beim Denken nur ein Offset — kein zweites Bild, das man synchron halten muss.
- **`rx = 2·ry`**, weil Terminalzellen doppelt so hoch wie breit sind. Ohne die
  Korrektur wäre es ein liegendes Ei.
- **Doppelt so fein abgetastet wie der Umfang Zellen hat.** Bei einer Probe pro
  Zelle war die Schrittzahl ungerade, der Winkel für „ganz unten" wurde nie
  getroffen — und im Ring klaffte eine Lücke an der auffälligsten Stelle.
- **Ein Zeichen pro Lage** (`● ◦ ·`): man soll den Zustand sehen, ohne den Text
  darunter zu lesen. Beim Denken wandert ein heller Bogen — **nur dann**. Ein
  dauernd kreisender Ring zöge im Augenwinkel, und das wäre das Gegenteil von
  „stört nicht".
- Die TUI bestimmt die Lage **lokal** (eigener Thread, alle 5 s), nicht über das
  Backend: die Frage ist, ob jemand an *dieser* Maschine sitzt und ob *dieses*
  Fenster offen ist. Auf dem Laptop hängt die TUI am PC-Backend; dessen
  Anwesenheit hilft hier niemandem.

## Die Fußleiste

Trägt jetzt alle Befehle, aus **einer** Quelle (`CTX_KEYS["home"]` — die Liste,
die `/` ohnehin zeigt). Zwei Eigenheiten, beide aus einem gemessenen Problem:

- **`q beenden` steht vorn.** Die Leiste wird bei schmalem Fenster hinten
  abgeschnitten; stand das Beenden am Ende, fiel ausgerechnet die Taste weg,
  die man sucht, wenn man nicht weiterweiß.
- **Kurzformen nur hier** (`post`, `lauf`, `ki`). Bei 140 Spalten passte die
  volle Fassung nicht, und was hinten abfiel, war der Theme-Zustand. Die
  `/`-Übersicht behält die ausführlichen Namen.
