# Morgen-Messenger

ZENTRALE meldet sich von selbst, sobald der Laptop morgens aufgeklappt wird —
**auch wenn ZENTRALE gar nicht läuft**. Ein kleines Fenster fragt die
Schlafzeiten ab und bietet die oberste offene Aufgabe der »week«-Liste an.

Das ist der Unterschied zum Vorher-Zustand: die Schlaf-Abfrage gab es schon,
aber nur **drinnen** — der Reminder des `sleep`-Graphen (`remind_at 05:00`)
nagt im Dashboard und in der TUI, also erst, wenn man ZENTRALE selbst öffnet.
Der Messenger löst genau diese Fälligkeit vom Backend ab.

## Die vier Teile

| Datei                              | Rolle                                        |
|------------------------------------|----------------------------------------------|
| `core/morgen.py`                    | **die Logik**: was fällig ist, was gespeichert wird |
| `scripts/morgen_messenger.py`       | **das Fenster** (curses) — zeichnet nur      |
| `scripts/morgen_start.sh`           | **der Rahmen**: Terminal, Größe, Platzierung |
| `scripts/morgen_watcher.py`         | **der Wächter**: merkt das Aufklappen        |
| `scripts/install_morgen_autostart.sh` | hängt den Wächter in die Sitzung           |

Kassetten-Prinzip wie bei der Karte: das Fenster ist ein dummer Renderer,
gerechnet und gespeichert wird in `core/`.

## Der Ablauf im Fenster

```
schlaf_von → schlaf_bis → aufgabe ⇄ uebernommen → bestaetigen → y → ZU
                             ↓ (l = später)
                      vertagen_datum → vertagen_zeit → nächste aufgabe
```

**Abgehakt heißt Schluss**: nach dem `y` macht das Fenster zu, es schiebt
nicht die nächste Aufgabe nach. Der Messenger bietet morgens EINE an, er ist
keine Abarbeitungs-Schleife. Weitergeblättert wird nur beim Vertagen (`l`)
und beim Überspringen (`n`).

| Taste            | Wo                    | Was                                     |
|------------------|-----------------------|-----------------------------------------|
| Ziffern / `:`    | Schlaf, Vertagen-Zeit | Uhrzeit tippen (`23:15`, `2315`, `7`)   |
| Enter            | überall               | weiter / bestätigen                     |
| `s`              | Schlaf-Frage          | überspringen (kommt heute nicht wieder) |
| `l`              | Aufgabe               | später erinnern (Datum + Uhrzeit)       |
| `n`              | Aufgabe               | nächste Aufgabe zeigen (ändert nichts)  |
| `y` / `n`        | Erledigt-Rückfrage    | wirklich abhaken / doch nicht           |
| Esc              | überall               | zurück, bzw. Fenster zu (Tag geschlossen)|

Beim Vertagen ist ein **leeres Datum = heute**; `5`, `05.09.`, `2026-12-24`
werden ebenso verstanden. Fehlt bei `TT.MM.` das Jahr und läge der Termin
schon hinter uns, rutscht er ins nächste Jahr.

Ein Zeitpunkt, der **schon vorbei ist**, wird abgelehnt (»das ist schon
vorbei«) statt gespeichert — sonst stünde die eben vertagte Aufgabe sofort
wieder im Angebot. Das leere Datum macht den Fehler leicht: abends um 18:00
auf »17:30« zu vertagen ist ein Tippfehler, kein Wunsch.

## Wo was landet

- **Schlaf** → in den `sleep`-Graphen, als Zeitspanne (`value` = Einschlaf-,
  `end` = Aufwach-Minute; `end < value` heißt über Mitternacht). Exakt
  derselbe Eintrag, den das Graph-Werkzeug schreiben würde, ein Eintrag pro
  Tag (upsert). Geschrieben über `graphs.log_value()`.
- **Erledigt** → `lists.toggle_item()`, also mit dem week-Kopie-Link zur
  Quell-Liste (siehe `core/lists.py`).
- **Alles andere** → `data/morgen_state.json`: pro Tag, ob der Messenger
  durch ist; pro Aufgabe, ob übernommen oder auf einen Zeitpunkt vertagt.
  Bewusst NICHT gespiegelt wird, was schon woanders steht (Schlafwert,
  Erledigt-Status) — sonst gäbe es zwei Wahrheiten.

Kein HTTP, kein Backend, keine KI: alles direkt über `core/graphs.py` und
`core/lists.py` auf `data/`. Genau deshalb kann der Messenger reden, bevor
ZENTRALE wach ist. **Achtung:** `graphs.log_value()` ist damit eine ZWEITE
Schreibstelle für Messwerte neben `ui/app.py::api_log` — wer das Format
ändert, muss beide anfassen.

## Wann er aufgeht

Drei Bedingungen, alle nötig (`morgen.is_due()`):

1. Die Uhrzeit ist durch — Quelle ist die **Reminder-Uhrzeit des
   `sleep`-Graphen** (05:00), damit es genau eine Stellschraube gibt: im
   Graph-Werkzeug verstellen, der Messenger zieht mit.
2. Heute wurde er noch nicht geschlossen.
3. Es gibt überhaupt etwas zu sagen — offene Schlaf-Abfrage **oder** eine
   offene Aufgabe. Sonst bleibt er still statt ein leeres Fenster aufzureißen.

## Wie das Aufklappen erkannt wird

Ohne root, ohne dbus, ohne systemd-Hook: `CLOCK_MONOTONIC`
(`time.monotonic`) steht während Suspend **still**, die Wanduhr läuft weiter.
Klaffen die beiden zwischen zwei Runden weiter auseinander als die Rundenzeit
(30 s), war die Maschine schlafen — und ist es jetzt nicht mehr. Läuft auf
jedem Linux, hängt an keiner Desktop-Umgebung und braucht keine Rechte.

Aufgemacht wird **höchstens einmal pro Aufwach-Ereignis**: wer das Fenster
wegklickt, ohne zu antworten, bekommt nicht alle 30 Sekunden ein neues. Beim
nächsten Deckel-Auf ist der Messenger wieder da.

## Das Fenster auf dem Schirm

`morgen_start.sh` startet ein kleines `xfce4-terminal` (**52×12 Zeichen**, ohne
Menü- und Werkzeugleisten; Alacritty/kitty/xterm/gnome-terminal als
Ausweichlösungen) mit dem Titel `ZENTRALE · morgen`.

Der gezeichnete Kasten **füllt das Terminal ganz aus** — sein Rahmen ist die
Fensterkante, es gibt keinen toten Rand dazwischen. Deshalb muss `put()` die
allerletzte Zelle unten rechts beschreiben können: `addstr` wirft dort immer
(curses kann den Cursor danach nicht mehr setzen), dem Rahmen fehlte sonst
die Ecke — das letzte Zeichen geht über `insstr` rein. Wer die Fenstergröße
ändern will, ändert `COLS`/`ROWS` in `morgen_start.sh`; der Kasten zieht mit.

Die Maße sind knapp geschnitten: 52 Spalten sind die längste Tastenzeile
(»enter erledigt · l später · n nächste · esc zu«, 45 Zeichen) plus Rand —
`tests/test_morgen.py` wacht darüber und schlägt an, wenn eine Tastenzeile
darüber hinauswächst. 12 Zeilen lassen 6 Zeilen Inhalt; ein längerer
Aufgabentext wird mit »…« gekürzt, **nie** die Frage darunter (sonst stünde
man vor einem Eingabefeld ohne zu wissen, was gefragt ist).

Unter **i3** wird das Fenster danach per `i3-msg` auf schwebend gesetzt und
mittig gerückt — **ohne `resize`**. Die Größe bringt das Terminal über
`--geometry` schon mit, und i3 behält sie beim Umschalten auf schwebend bei.
Eine Pixelgröße zu setzen war genau der Fehler, der das Fenster einmal fast
doppelt so groß machte: 680×340 px ergaben mit dieser Schrift **85×19
Zeichen** statt der gewollten 60×14. In Zeichen zu denken ist auch das
einzige, was bei anderer Schriftgröße oder DPI noch stimmt.

Gesetzt wird **nicht** per `for_window`: das ist eine reine
Konfigurations-Direktive, i3-msg weist sie zur Laufzeit zurück (geprüft an
i3 4.23). Ein Kriterien-Kommando auf ein bereits offenes Fenster geht dagegen
— also wartet ein Hintergrund-Zweig per `xdotool search` auf das Fenster und
setzt es dann. Die i3-Konfiguration wird nicht angefasst; der Messenger
bringt sein Fensterverhalten selbst mit.

Das Farbschema kommt aus `~/.config/zentrale/theme` — derselben Datei, an der
Terminal, Browser und nvim hängen (`auto` = hell zwischen 05:00 und 21:00).

## Einrichten

```bash
bash scripts/install_morgen_autostart.sh     # schreibt den Autostart-Eintrag
python3 scripts/morgen_watcher.py &          # ohne Neuanmeldung starten
bash scripts/morgen_start.sh --force         # Fenster sofort anschauen
```

Der Autostart-Eintrag (`~/.config/autostart/zentrale-morgen.desktop`) trägt
**bewusst kein `OnlyShowIn`**: i3 startet die XDG-Einträge über
`dex --autostart --environment i3` (steht so in `~/.config/i3/config`), XFCE
von Haus aus — ein Eintrag, beide Sitzungen. Log: `/tmp/zentrale-morgen.log`.

Wieder loswerden: `rm ~/.config/autostart/zentrale-morgen.desktop` und
`pkill -f morgen_watcher.py`.

## Nebenwirkung: die »week«-Liste sortiert nach oben

`lists.add_item()` **hängt** neue Einträge an — außer bei der »week«-Liste,
da wird jetzt **oben eingefügt**. Grund: der Messenger greift sich das erste
Item; frisch Notiertes versänke sonst sofort unter dem Altbestand und käme
morgens nie dran. Unterpunkte eines Eintrags hängen weiter hinten an, sonst
läse sich jede Checkliste rückwärts.

## Tests

`tests/test_morgen.py` — Fälligkeit, Schlaf-Eintrag, Warteschlange
(übernehmen/erledigen/vertagen), Datums-Parser und der komplette
Zustandsautomat des Fensters, durchgespielt ohne curses.
