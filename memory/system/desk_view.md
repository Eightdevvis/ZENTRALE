# Desk View — eine unendliche Fläche je Desk

**Stand 2026-10-09: Grundgerüst gebaut** (Branch `worktree-desk-view`).
Im Rad Taste/Platz `d` („desk", zwischen tutor und elektronik). Erst die
Auswahl der Desks (+ neuer Desk), dann die Fläche: Zettel liegen darauf,
Schnüre verbinden sie, Shift+Pfeile schieben den Ausschnitt.

Sasha: *„ich klappe z.B. ‚Elektronik' auf und habe einen infinity canvas vor
mir … Mit + fügt man ein neues hinzu, das ist dann autoselected, man bewegt
es mit Pfeiltasten über das Canvas, mit Enter legt man es ab … Die
Architektur muss sauber sein, der Canvas muss für andere Apps
wiederverwendbar sein."* Nachgereicht am selben Tag: Schnüre („wichtigstes
Feature") und „der Desk-Ordner soll IMMER mit ZENTRALE mitgesynct werden".

## Tasten (so gebaut — Sasha kann umstellen)

| Zustand | Taste | Was |
|---|---|---|
| Auswahl | ↑↓ enter | Desk wählen, öffnen; letzte Zeile „+ neuer desk" |
| | n | neuer Desk (Name unten tippen, enter legt an, esc bricht ab) |
| | esc | zurück zum Rad |
| Fläche, Ruhe | ↑↓←→ | Fokus springt zum nächsten Kasten in der Richtung (der erste Druck nimmt den Kasten nahe der Mitte); der Ausschnitt folgt |
| | enter | greifen |
| | + | neuer Zettel mitten im Ausschnitt, gleich gegriffen |
| | e | Zettel bearbeiten (Modal mittig) |
| | v | verbinden: Schnur von hier zu einem Ziel |
| | d / Entf | löschen — Rückfrage unten, j ja, n/esc nein |
| | Bild↑ Bild↓ | im gewählten Zettel blättern (langer Text) |
| | esc | zurück zur Auswahl |
| Greifen | ↑↓←→ | eine Zelle je Druck |
| | enter | ablegen (gespeichert) |
| | esc | zurück an die alte Stelle; ein neuer Zettel verschwindet |
| Verbinden | ↑↓←→ | Ziel springt durch die Kästen, die Schnur wird vorgezeigt |
| | enter / v | verbinden; ist das Paar schon verbunden: Rückfrage „schnur lösen?" |
| | esc | abbrechen |
| Modal | tippen, enter | Text, enter = neue Zeile; ←→↑↓ Pos1 Ende ⌫ Entf |
| | ctrl+s | speichern |
| | esc | abbrechen, nichts gespeichert |
| überall außer Modal | shift+↑↓←→ | Ausschnitt schieben (6 Spalten / 3 Zeilen); beim Greifen reist der Zettel mit |

Shift+Pfeil erkennt der Baustein am **Namen** (`curses.keyname`: `kLFT2`,
`kRIT2`, `kUP2`, `kDN2`, `KEY_SLEFT`, `KEY_SR` …), nicht an der Nummer —
die wechselt mit Terminal und tmux. Rohe Folgen `ESC [1;2A…D` gehen auch.
Die Fußleiste unten zeigt die Tasten je Zustand (`befehle.CTX_KEYS`,
Kontexte `desk:wahl|canvas|greifen|verbinden|frage`); „shift+↑↓←→" und
„pgup/pgdn" stehen nur in der Hinweiszeile im Kasten, weil
`fussleiste.codes()` „shift+" nicht lesen kann (Datei gehörte in dieser
Runde einer anderen Sitzung).

## Wie es geschnitten ist

- **Baustein** `tui/bausteine/canvas.py` (+ `schnur.py`, `textfeld.py`,
  `canvas_arten.py`): weiß nichts vom Desk, speichert nichts, fragt kein
  Backend. Bekommt Elemente (`id, x, y, w, h, art …`) und Verbindungen
  (`id, von, nach, label?`), verarbeitet Ereignisse und meldet ein
  `Ergebnis` (`geaendert` mit Grund, `bearbeiten`, `zu`). Zeichnet als
  Zeilen aus (spalte, text, rolle). Regeln für Bausteine:
  [tui_bauplan.md](tui_bauplan.md) „Bausteine".
- **Arten** über eine Registrierung (`canvas.Arten`): `zeichne`, `modal`,
  `neu`, optional `rolle` (Rahmenfarbe), `bei_enter` (eigene Aktion statt
  greifen) und `blaettern` (eigene
  Scroll-Lage im Kasten, nie gespeichert). Unbekannte Arten zeichnen sich
  als „? art" und gehen nicht verloren.
- **Schnüre** werden nie gespeichert, sondern bei jedem Bild aus den
  aktuellen Lagen gelegt: Andockseite nach Lage (senkrecht zählt doppelt),
  einmal abbiegen auf halber Strecke, Box-Zeichen, Kreuzungen ergeben sich
  von selbst, Spitze ▸◂▴▾ am Ziel, unter den Kästen. Ein gelöschter Kasten
  nimmt seine Schnüre mit (Baustein und Backend).
- **App** `tui/ansichten/desk.py`: Auswahl, laden/speichern über HTTP,
  Modal, Hinweise. Speichert nach jedem Ablegen, Verbinden, Lösen, Löschen
  und Bearbeiten den ganzen Desk.
- **Backend** `core/desk.py` (Schicht 2) + `ui/routen/desk.py`, Endpunkte in
  [api_endpoints.md](api_endpoints.md).

## Format: JSON Canvas 1.0

Eine Datei pro Desk, `<desk_ordner>/<name>.canvas`
([jsoncanvas.org/spec/1.0](https://jsoncanvas.org/spec/1.0/)) — Obsidian
öffnet sie direkt.

- **Zettel** (Art `notiz`) = Knoten `type: "text"`, Markdown; erste Zeile =
  Titel (ein `# ` davor fällt in der Anzeige weg). Rahmen in der Farbrolle
  `amber`, Titel `amberhi` fett.
- **Schnur** = Kante `{id, fromNode, toNode}`; beim Speichern kommen
  `fromSide`/`toSide` dazu (wie die Schnur gerade liegt), `label` wird
  angezeigt.
- **Zelle ↔ Pixel**: 1 Spalte = 10 px, 1 Zeile = 20 px. Eine Lage wird nur
  neu geschrieben, wenn sie sich in Zellen geändert hat — Obsidian-Lagen
  bleiben pixelgenau.
- Andere Knoten (file, link, group) kommen als Art `fremd`, lassen sich
  verschieben und verbinden, nicht bearbeiten. Unbekannte Felder (color …)
  bleiben stehen. Eigene Zusatzfelder: keine.
- Speichern mit `stand` (Hash der Datei vom Laden): wurde sie woanders
  geändert, 409 — die TUI lädt neu und sagt es; die letzte Änderung fehlt
  dann. Eine kaputte Datei wird nie überschrieben (422).

## Ort und Abgleich

Einstellung `desk_ordner` (Env `ZENTRALE_DESK_ORDNER`), Standard
`data/desk/` in ZENTRALE (gitignored). **Wird abgeglichen** (Sasha,
2026-10-09): `data/desk/**` steht auf der Positivliste
(`core/abgleich_auswahl.py`), `.canvas` wird wie JSON nach `id`
zusammengeführt (`abgleich_zusammenfuehren.art`) — zwei Rechner, die
verschiedene Zettel schieben, verlieren nichts. Warum nicht
`~/Zentrale/Desk/`: der Abgleich arbeitet relativ zur ZENTRALE-Wurzel; ein
Ordner im Nutzerordner hätte einen zweiten Wurzel-Begriff im Abgleich
gebraucht. Wer `desk_ordner` umstellt, gleicht NICHT ab. Tests lenken den
Ordner per conftest um (Wächter in `tests/test_keine_seiteneffekte.py`).

## Offene Punkte

- **Zettel später auf echte Notizen umstellen**, sobald das Notiz-Tool ein
  offenes Format hat (Leitlinie: dasselbe Objekt, nicht kopiert). Bis dahin
  sind Zettel Canvas-eigene Text-Knoten.
- **Kacheln** anderer Apps — Form entschieden in
  [hub_bauplan.md](hub_bauplan.md) „Kacheln": text-Knoten mit Rückfall-Text
  und `zentrale_kachel: {v, app, art, ref}`, App-Namen `fokus` (Listen),
  `graph`, `kalender`. **Schon da:** `core/desk.py` reicht solche Knoten
  als Art `kachel` durch (Feld `kachel`, Rückfall als `titel`) und ändert
  nur die Lage, nie Text oder Zusatzfeld; ohne registrierte Kachel-Art
  zeichnet „fremd" sie. Im Baustein meldet eine Art mit `bei_enter` bei
  Enter ein Ergebnis `aktion` (z. B. („oeffnen", ref)) statt zu greifen —
  die Art entscheidet, Zettel werden weiter gegriffen; Blättern im Kasten
  gibt es (`blaettern`). **Fehlt:** die Kachel-Art selbst, das Holen über
  `POST /api/kachel` in der Ansicht und das Weiterreichen von `aktion` an
  `POST /api/kachel/aktion` (Stelle in `desk.py` markiert). Wie man eine
  Kachel ohne Enter verschiebt, entscheidet die nächste Runde.
- Desks löschen/umbenennen gibt es nicht (Datei von Hand).
- Größe eines Zettels ändern gibt es nicht (Standard 24×6).
- Desks und Chat-Projekte sind unabhängig; ob ein Desk zu einem Projekt
  gehört, entscheidet Sasha.
- Esc im Modal verwirft ohne Rückfrage.
- Konflikt (409) verliert die letzte Änderung hier.
- Breite Zeichen (Emoji) im Zettel verschieben die Zeile um eine Spalte.

## Historie

- **2026-10-09** — Grundgerüst: Baustein Canvas, Schnüre, Zettel, Desk View,
  `/api/desk`, Abgleich. Ein Zwischenstand mit Verweisen auf das Notiz-Tool
  wurde am selben Tag zurückgenommen (dessen Format kommt zuerst dran).
