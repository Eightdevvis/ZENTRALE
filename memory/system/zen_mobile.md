# ZEN-MOBILE — die Handy-App

**Stand 2026-10-08.** Flutter-App in `mobile/` (Android). Sasha: „sie muss
eigentlich nicht viel können" — die ZENTRALE-KI unterwegs, statt der
Claude-App, damit Gedächtnis und Gespräche nicht auseinanderlaufen
(Fahrplan Punkt 3).

## Was man sieht

- **Start:** ein Auge in der Mitte — dasselbe Wesen wie das KI-Auge der TUI
  (`tui/pixel.py`, `AUGE_FARBEN`), nur glatt gezeichnet: Mandel, schweres
  Oberlid, große Iris, blinzelt, schaut sich gelassen um, denkt mit Funkenring.
  Tag/Nacht folgt dem Handy.
- **Auge antippen → KI-Chat**, schlicht wie die Claude-App: Gesprächsliste im
  Seitenmenü, Sashas Nachrichten als Blasen, Antworten als Markdown,
  aufklappbare Gedanken, Stopp, Kopieren, Neu antworten.
- **Knöpfe um das Auge:** die Liste `bereiche` in `lib/start/startseite.dart`.
  Heute leer, weil außer der KI nichts drin ist. Ein neuer Bereich = ein
  Eintrag, die Knöpfe ordnen sich von selbst im Kreis.

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
| `auge/`, `start/`, `thema/` | Auge, Startseite mit Bereichs-Ring, Farben Tag/Nacht |
| `einstellungen/` | Keystore + Einstellungsseite |

Tests: `mobile/test/` (Format, Zusammenlegen, Abgleich, Strom-Parser, Anfrage).

## Offen

1. **Mitte anschließen**, sobald das Format steht (verschlüsselt, von Dart
   lesbar): `GitHubMitte` implementiert `Mitte`, in `main.dart` statt
   `abgleich: null`. Einstellungen für Token + Schlüssel.
2. `core/mobil_kontext.py` (ASSISTANT-Seite).
3. Auf dem Handy ausprobieren — bisher nur Tests und Analyse, kein Gerätelauf.
