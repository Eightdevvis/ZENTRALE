# ZEN-MOBILE — die Handy-App

**Stand 2026-10-08.** Flutter-App in `mobile/` (Android). Sasha: „sie muss
eigentlich nicht viel können" — die ZENTRALE-KI unterwegs, statt der
Claude-App, damit Gedächtnis und Gespräche nicht auseinanderlaufen
(Fahrplan Punkt 3, `memory/ueberblick.md` → „Fahrplan").

## Was man sieht

- **Start:** ein Auge in der Mitte — dasselbe Wesen wie das KI-Auge der TUI
  (`tui/pixel.py`, `AUGE_FARBEN`), nur glatt gezeichnet: Mandel, schweres
  Oberlid und gespiegeltes Unterlid, große Iris, blinzelt, schaut sich gelassen
  um, denkt mit Funkenring.
  Tag/Nacht folgt dem Handy.
- **Auge antippen → KI-Chat** (die Pupille füllt erst das Auge, siehe
  „Das Auge"), schlicht wie die Claude-App: Gesprächsliste im
  Seitenmenü, Sashas Nachrichten als Blasen, Antworten als Markdown,
  aufklappbare Gedanken, Stopp, Kopieren, Neu antworten.
- **Knöpfe um das Auge:** die Liste `bereiche` in `lib/start/startseite.dart`.
  Standard: Auge offen, keine Knöpfe. Runterwischen schließt das Auge und
  lässt die Knöpfe herauswachsen (siehe „Das Auge"). Ein neuer Bereich = ein
  Eintrag, die Knöpfe ordnen sich für jede Anzahl selbst auf einer Ellipse.

## Das Auge (`lib/auge/`, Stand 2026-10-28)

**Alle Stellschrauben** (Lidtiefe, Falten, Pupille nach Uhrzeit, Launen-
Häufigkeit, Zeiten fürs Antippen und den Knopf-Ring, Bahn- und Chip-Stil)
stehen in `lib/auge/auge_regler.dart` — Ästhetik entscheidet Sasha, dort
wird gedreht. Probebilder aller Zustände: `flutter test test/auge_test.dart`
schreibt PNGs nach `mobile/build/auge_vorschau/` (nicht im Repo).

- **Form:** Das Unterlid ist das Spiegelbild des schweren Oberlids an der
  Waagrechten durch die Pupille („einfach ne x-achse durch die pupille nehmen
  und das design spiegeln") — halb geschlossen, ruhig, nicht erschrocken.
  Die Lider laufen zur Mandelkante hin durchsichtig aus (Haut, kein Glas).
  Falten oben und gespiegelt unten sind halbe Sinusbögen, in der Mitte am
  dicksten, zu den Enden auf null. Blinzeln: beide Lider treffen sich in der
  Mitte. Maler: `auge_maler.dart`; Bewegung (Blick, Blinzeln): `zeit.dart`.
- **Uhrzeit:** 21–7 Uhr ist die Pupille etwas größer, 3–5 Uhr winzig
  („extra spooky"); Übergänge weich über je eine Stunde um die Grenze.
  Lokale Zeit, die Uhr ist ins Widget steckbar (`Auge(uhr: ...)`, Tests).
- **Launen** (`launen.dart`): selten (Zeitfenster 3 min, in ~65 % davon
  eine, also etwa alle 4–5 min), fest gewürfelt je Fenster wie `_rnd`, nie
  beim Denken, Aufgehen, Antippen oder geschlossen. Jede kommt und geht weich
  und ist bei Stärke 0 das normale Auge. Heute zwölf: stern (wandert statt
  der Pupille), zwillinge (zwei Iriden umkreisen sich), unscharf, katze
  (Schlitz, gelblich), spirale, farbreise (einmal durch alle Farben),
  doppelblinzeln, funken (Pupille zerspringt und fügt sich wieder),
  mond (Sichel spiegelt sich), augenrollen, zwinkern, herz (schlägt, Iris
  rosa). Neue Laune = eine Klasse + ein Eintrag in `alleLaunen`; der Maler
  kennt nur die Schnittstelle `Laune` (formen / maleIris / malePupille /
  maleLicht).
- **Vorschau:** langes Drücken aufs Auge der Startseite spielt die nächste
  Laune der Reihe nach und nennt ihren Namen unten.
- **Antippen:** die Pupille wächst in ~0,6 s, bis sie die ganze Mandel füllt;
  genau diese Mandel wächst dann in Pupillenfarbe über den Schirm, aus dem
  Dunkel blendet der Chat auf (`pupillen_route.dart`). Zurück endet es in der
  vollen Mandel, dann zieht sich die Pupille wieder zusammen.
- **Knopf-Ring** (`lib/start/leiterbahnen.dart`): Runterwischen (irgendwo auf
  dem Schirm) → das Auge schließt sich ruhig, dann zeichnen sich Leiterbahnen
  vom Lid zu jedem Knopf (gerade raus, ein Knick um 45°, Lötaugen am Anfang
  und am Knick, leiser Schein in den Augenfarben), am Ende wachsen die Knöpfe
  als kleine Chips auf. Hochwischen oder Tippen aufs geschlossene Auge → alles
  rückwärts. Knöpfe sind nur fertig gezeigt tippbar.
- **Kleine Augen im Chat** (Leer-Zustand, Denk-Anzeige) nutzen denselben
  Maler; die Denk-Anzeige bekommt nie Launen.

## Warum das Handy ein eigener Knoten ist (kein Client des Backends)

Kein Rechner läuft zuverlässig dauerhaft, das Handy soll aber von überall
gehen. Darum spricht es die KI **selbst** (Claude-API) und gleicht über die
**Mitte** ab (heute das private Git-Repo `Eightdevvis/data`, später der
Heimserver — Abgleich-Plan: `memory/betrieb/abgleich.md`). Abgestimmt mit der
ASSISTANT-Session am 08.10.2026.

- **Gespräche:** exakt das Format von `core/gespraeche.py`. Das Handy heißt
  Knoten `handy` und schreibt nur `gespraeche/<id>/handy.jsonl` und
  `gespraeche/_knoten/handy.json` — darum keine Konflikte. Zeitstempel
  Byte-gleich zu Pythons `isoformat(timespec="microseconds")` (Test).
- **Eine KI, nicht zwei:** den System-Prompt baut nur der Kern. Er legt ihn
  als `data/mobil/kontext.json` in die Mitte (`core/mobil_kontext.py`, baut
  die ASSISTANT-Seite): `{version, stand, anbieter, modell, effort, system}`.
  Das Handy hängt nur einen Absatz an: läuft auf dem Handy, **keine Werkzeuge**,
  ehrlich sagen, was es von hier nicht sehen kann. Fehlt das Paket:
  Notbetrieb mit `claude-sonnet-5` / effort `low` und Minimal-Prompt.
- **Abgleich** (`lib/mitte/abgleich.dart`): holt `gespraeche/**` und
  `mobil/kontext.json`, bringt nur Eigenes plus den `kopf.json` eines hier
  neu begonnenen Gesprächs, solange die Mitte noch keinen hat.
- **Geheimnisse** (API-Schlüssel, später Git-Token + Abgleich-Schlüssel)
  liegen im Android-Keystore, nie in der Ablage.

## Aufbau `mobile/lib/`

| Ordner | Aufgabe |
|---|---|
| `ablage/` | Dateien des Handys, Pfade wie unter `data/` (Platte / Speicher für Tests) |
| `gespraeche/` | Format und Regeln von `core/gespraeche.py` (Zusammenlegen, Verwerfen, Titel) |
| `ki/` | Schnittstelle `KiAnbieter`, Claude per HTTP+SSE, Kontextpaket |
| `mitte/` | Schnittstelle `Mitte` + Abgleich; GitHub-Umsetzung folgt |
| `chat/` | `ChatSteuerung` (Logik) und die Seiten (zeichnen nur) |
| `auge/`, `start/`, `thema/` | Auge (Stellschrauben `auge_regler.dart`), Startseite mit Knopf-Ring, Farben Tag/Nacht |
| `einstellungen/` | Keystore + Einstellungsseite |

Tests: `mobile/test/` (Format, Zusammenlegen, Abgleich, Strom-Parser, Anfrage, Auge).

## Offen

1. **Mitte anschließen**, sobald das Format steht (verschlüsselt, von Dart
   lesbar): `GitHubMitte` implementiert `Mitte`, in `main.dart` statt
   `abgleich: null`. Einstellungen für Token + Schlüssel.
2. `core/mobil_kontext.py` (ASSISTANT-Seite).
3. Auf dem Handy ausprobieren — bisher nur Tests und Analyse, kein Gerätelauf.
