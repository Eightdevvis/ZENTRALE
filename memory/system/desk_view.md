# Desk View — eine unendliche Fläche je Desk

**Stand 2026-10-10: Grundgerüst + Kacheln (Kalender) gebaut** (Branches
`worktree-desk-view`, `worktree-desk-kalender`).
Im Rad Taste/Platz `d` („desk", zwischen tutor und elektronik). Erst die
Auswahl der Desks (+ neuer Desk), dann die Fläche: Zettel liegen darauf,
Schnüre verbinden sie, W A S D (Großbuchstaben) schieben den Ausschnitt.

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
| | enter | greifen — immer, jedes Element, auch Bilder und Kacheln (seit 2026-10-10) |
| | + | Wähler „neu": zettel, bild, kalender (↑↓ enter, esc). Zettel: mitten im Ausschnitt, gleich gegriffen (`+` enter = schneller Zettel). Bild: Liste der Bilder in `~/Zentrale/Input` + „pfad tippen …". Kalender: erst der kleine Dialog (unten), dann gegriffen |
| | e | Zettel bearbeiten (Modal mittig); beim Bild der Titel (leer = Dateiname) |
| | o | öffnen: Bild im Bildbetrachter; Kachel in ihrer App an der richtigen Stelle (Kalender an dem Tag) |
| | f | Bild: Vorschau mono ↔ farbe (gespeichert) |
| | v | verbinden: Schnur von hier zu einem Ziel |
| | d / Entf | löschen — Rückfrage unten, j ja, n/esc nein |
| | Bild↑ Bild↓ | im gewählten Kasten blättern (langer Zettel; Kalender-Kachel: alle Tage zugleich, „+N" zeigt Verstecktes) |
| | esc | zurück zur Auswahl |
| Wähler „neu" | ↑↓ enter esc | wählen, anlegen, abbrechen |
| Kalender-Dialog | ↑↓ / tab | Feld: art, tage bzw. von/bis |
| | ←→ / leertaste | art: mitlaufend ↔ fest |
| | ziffern, -, ⌫ | tage bzw. Datum JJJJ-MM-TT tippen |
| | enter | anlegen (über 31 Tage: klare Meldung, bleibt offen); esc bricht ab |
| Greifen | ↑↓←→ | eine Zelle je Druck |
| | enter | ablegen (gespeichert) |
| | esc | zurück an die alte Stelle; ein neuer Zettel verschwindet |
| Verbinden | ↑↓←→ | Ziel springt durch die Kästen, die Schnur wird vorgezeigt |
| | enter / v | verbinden; ist das Paar schon verbunden: Rückfrage „schnur lösen?" |
| | esc | abbrechen |
| Modal | tippen, enter | Text, enter = neue Zeile; ←→↑↓ Pos1 Ende ⌫ Entf |
| | ctrl+s | speichern |
| | esc | abbrechen, nichts gespeichert |
| überall außer Modal | **W A S D** (groß) | Ausschnitt schieben (6 Spalten / 3 Zeilen), W hoch, A links, S runter, D rechts; beim Greifen reist der Zettel mit. Gedrückt halten wird schneller (bis 4×). Kleinbuchstaben bleiben, was sie sind (d = löschen) |
| | shift+↑↓←→, alt+↑↓←→ | dasselbe, zusätzlich |

**W A S D** ist seit 2026-10-10 die Hauptbelegung (Sasha: ZENTRALE soll
überall gleich gut gehen): Großbuchstaben kommen in jedem Terminal, tmux,
macOS und Handy gleich an; xfce4-terminal schluckt Shift+↑↓ von Haus aus.
Alt+Pfeil kommt als `kLFT3`/`kRIT3`/`kUP3`/`kDN3`, als ESC + Pfeil, als
`ESC [1;3A…D` oder `ESC ESC [A` (wie in der Karte).

Shift+Pfeil erkennt der Baustein am **Namen** (`curses.keyname`: `kLFT2`,
`kRIT2`, `kUP2`, `kDN2`, `KEY_SLEFT`, `KEY_SR` …), nicht an der Nummer —
die wechselt mit Terminal und tmux. Rohe Folgen `ESC [1;2A…D` gehen auch.
Die Fußleiste unten zeigt die Tasten je Zustand (`befehle.CTX_KEYS`,
Kontexte `desk:wahl|canvas|bild|kachel|neu|greifen|verbinden|frage`; Modal
und Kalender-Dialog sind Freitext ohne Leiste, ihr Kasten zeigt die Tasten).
Die Leiste zeigt „W/A/S/D move view"; „shift/alt+↑↓←→" und „pgup/pgdn"
stehen nur in der Hinweiszeile im Kasten, weil `fussleiste.codes()`
„shift+" nicht lesen kann (Datei gehörte in dieser Runde einer anderen
Sitzung).

**Weich schieben** (2026-10-10, Sasha: *„ich möchte dass die bewegung über
das canvas weicher ist"*): `vx/vy` bleibt die Lage, mit der alles rechnet.
Gezeichnet wird eine Anzeige-Lage, die je Bild 38 % der Reststrecke auf
sie zugleitet (wie das Rad der Startseite), unter einer halben Zelle
einrastet und spätestens nach 6 Bildern steht (Pi). Gilt fürs Schieben und
fürs Nachziehen bei Fokus-Sprung und Greifen; der gegriffene Kasten selbst
bewegt sich zellgenau. Solange es gleitet, meldet `Desk.bewegt_sich()` —
dann tickt `zentrale_tui.py` mit 33 ms, sonst ruhig. Gedrückt halten
(Wiederholung derselben Richtung unter 80 ms) macht den Schritt je Druck
×1,5 bis 4× größer; nach einer Pause wieder der Grundschritt. Der Baustein
macht beides nur, wenn die Ansicht es einschaltet (`weich`, `uhr`).

## Wie es geschnitten ist

- **Baustein** `tui/bausteine/canvas.py` (+ `schnur.py`, `textfeld.py`,
  `canvas_arten.py`): weiß nichts vom Desk, speichert nichts, fragt kein
  Backend. Bekommt Elemente (`id, x, y, w, h, art …`) und Verbindungen
  (`id, von, nach, label?`), verarbeitet Ereignisse und meldet ein
  `Ergebnis` (`geaendert` mit Grund, `bearbeiten`, `zu`). Zeichnet als
  Zeilen aus (spalte, text, rolle). Regeln für Bausteine:
  [tui_bauplan.md](tui_bauplan.md) „Bausteine".
- **Arten** über eine Registrierung (`canvas.Arten`): `zeichne`, `modal`,
  `neu`, optional `rolle` (Rahmenfarbe), `oeffnen` (Taste `o`, meldet eine
  Aktion an die Ansicht), `taste(element, zeichen)` (eigene Tasten wie `f`),
  `neu_label` (Name im Wähler von `+`), `neu_dialog()` (erst fragen, dann
  `neu(eid, x, y, werte)`; seit 2026-10-10 für den Kalender) und `blaettern`
  (eigene Scroll-Lage im Kasten, nie gespeichert). Enter greift immer
  (vorher `bei_enter`). Unbekannte Arten zeichnen sich als „? art" und gehen
  nicht verloren.
- **Schnüre** werden nie gespeichert, sondern bei jedem Bild aus den
  aktuellen Lagen gelegt: Andockseite nach Lage (senkrecht zählt doppelt),
  einmal abbiegen auf halber Strecke, Box-Zeichen, Kreuzungen ergeben sich
  von selbst, Spitze ▸◂▴▾ am Ziel, unter den Kästen. Ein gelöschter Kasten
  nimmt seine Schnüre mit (Baustein und Backend).
- **App** `tui/ansichten/desk.py`: Auswahl, laden/speichern über HTTP,
  Modal, Hinweise. Speichert nach jedem Ablegen, Verbinden, Lösen, Löschen
  und Bearbeiten den ganzen Desk (ohne Puffer-Felder „_…").
- **Kalender im `+`-Wähler** `tui/ansichten/desk_neu.py`: der Wähler ist
  die eine Registrierung `canvas.Arten` (alles mit `neu_label`, in
  Reihenfolge: zettel, bild, kalender). `KalenderWahl` trägt sich dort unter
  „kachel:kalender" ein (kein Element heißt so), hat `neu_dialog()` →
  `KalenderDialog` und legt mit `neu(eid, x, y, werte)` ein Element der
  allgemeinen Art `kachel` an. Weitere Kachel-Quellen kommen genauso dazu.
- **Kacheln holen** `tui/ansichten/desk_kacheln.py`: bei jedem Bild prüft
  `pflegen`, welche Kachel fällig ist (kein Puffer, Frist `ttl` um, Größe
  oder Blätter-Lage anders) und holt sie im Hintergrund-Thread über
  `POST /api/kachel`; gezeichnet wird immer aus dem Puffer `_inhalt`. Mit
  `stand` antwortet der Hub „unverändert". Unbekannte Farbrollen → `dim`.
- **Springen** `tui/ansichten/sprung.py`: `o` → `POST /api/kachel/aktion`
  → `{"zeige": {ansicht, ziel}}` → `zeigen(ansicht, ziel)`, das
  zentrale_tui.py hereingibt. Heute kennt es `kalender` (Kalender öffnen,
  Tag = ziel). Der Desk kennt keine andere Ansicht.
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
- **Bild** (Art `bild`, 2026-10-10) = Knoten `type: "file"`, `file` =
  Pfad relativ zum Desk-Ordner (`bilder/foto.jpg`) — Obsidian zeigt das
  echte Bild, wenn der Desk-Ordner der Tresor ist. Endungen png, jpg, jpeg,
  gif, webp, bmp. Eigene Zusatzfelder, nur mit Vorsilbe:
  `zentrale_titel` (fehlt = Dateiname ohne Endung) und
  `zentrale_bildmodus` (`farbe`; fehlt = mono).
- Andere Knoten (file mit anderer Endung, link, group) kommen als Art
  `fremd`, lassen sich verschieben und verbinden, nicht bearbeiten.
  Unbekannte Felder (color …) bleiben stehen.
- Speichern mit `stand` (Hash der Datei vom Laden): wurde sie woanders
  geändert, 409 — die TUI lädt neu und sagt es; die letzte Änderung fehlt
  dann. Eine kaputte Datei wird nie überschrieben (422).

## Kacheln (seit 2026-10-10)

Form und Weg: [hub_bauplan.md](hub_bauplan.md) „Kacheln". In der Datei ein
text-Knoten mit Rückfall-Text und `zentrale_kachel: {v, app, art, ref}` —
ein Verweis, nie eine Kopie. Der Rückfall-Text ist nur Anzeige für Obsidian:
beim Speichern schickt die TUI den letzten Klartext der App als `rueckfall`
mit, `core/desk.py` schreibt ihn in `text`; den Verweis ändert es nie.
Breite/Höhe stehen wie bei jedem Knoten in `width`/`height`; die App kürzt
selbst auf das Innere (w−2 × h−2).

**Kalender** (App `kalender`, Art `ausschnitt`, Quelle
`core/kachel_kalender.py`): Bezug `{"modus": "mitlaufend", "tage": 7}` (ab
heute, rechnet jeden Tag neu) oder `{"modus": "fest", "von": …, "bis": …}`;
höchstens 31 Tage. Standard beim Anlegen: mitlaufend 7 Tage.
- **bis 7 Tage → Woche:** eine Spalte je Tag (│ dazwischen), Kopf
  „Mo 12.10.", darunter Ganztägiges zuerst (Rolle `span`), dann
  „HH:MM titel" (`faint` + `ink`). Startgröße 13 Spalten je Tag, 6 Zeilen.
- **8–31 Tage → Monat:** Raster Mo–So, Wochen als Zeilen, Tageszahl (am
  Ersten und am ersten Tag mit Monat, „1.11."), darunter so viele Termine
  wie passen. Tage außerhalb des Bereichs leise und leer. Startgröße 11
  Spalten × 3 Zeilen je Tag, so viele Wochen, wie der Bereich je nach
  Wochentag schneiden kann.
- **Heute** in der Kalender-Farbe `kal`. Passt ein Tag nicht: „+N" (Rolle
  `acc`) — in der Woche als letzte Zeile der Spalte, im Monat rechts neben
  der Zahl. Bild↓/↑ blättert alle Tage zugleich um eine Zeile (bis die
  längste Liste ganz zu sehen ist).
- **Zu klein:** „zu klein / mind. W×H" statt Inhalt. **App weg/aus:**
  „nicht mehr da" bzw. der letzte Stand leise.
- `o` öffnet den Kalender an dem Tag, an dem der Ausschnitt beginnt
  (mitlaufend: heute). Esc dort führt zur Startseite, nicht zurück zum Desk.

**Entschieden 2026-10-10** (für Sasha, er kann umstellen): **enter greift
jedes Element**, auch Kacheln — eine Regel für alles, wie Sashas
Grundregel. **`o` öffnet** die Quelle des gewählten Elements. Damit ist die
Frage aus der vorigen Runde („wie verschiebt man eine Kachel ohne Enter")
erledigt; hub_bauplan.md hatte „Enter = öffnen" vorgesehen.

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

## Bilder (seit 2026-10-10)

Sasha: *„Images soll man auch draufbappen. Fürs Terminal eine
Zwischenlösung: es wird eine Preview mit Titel als Kachel angezeigt, die
Preview das Bild verpixelt …, und man kann es im Imageviewer direkt
geöffnet kriegen wenn man es selected."*

- **Hinlegen:** `+` → bild → ein Bild aus `~/Zentrale/Input` (auch eine
  Ebene tiefer) oder einen Pfad tippen. Das Backend **kopiert** es nach
  `<desk_ordner>/bilder/` (`core/desk_bild.py`): der Desk-Ordner wird
  abgeglichen, Input/ nicht, und Input/ ist ein Durchgangsort. Das Bild
  im Desk-Ordner ist danach das Objekt, auf das der Knoten zeigt. Nur
  Dateien, die Pillow als Bild liest (≤ 50 MB) — ein getippter Pfad holt
  nichts anderes in den abgeglichenen Ordner. Gleicher Name mit gleichem
  Inhalt → dieselbe Datei; anderer Inhalt → `name-2.png`.
- **Kachel:** Rahmen, erste Zeile Titel (fett), darunter die Vorschau,
  die den Kasten füllt. Neue Bilder sind 34 Zellen breit, die Höhe folgt
  dem Seitenverhältnis (Zelle 2:1, 4–16 Zeilen Vorschau).
- **Vorschau:** Sashas ASCII-Filter aus dem alten Browser-Frontend
  (`memory/archive/browser_front/`, `canvasToAscii` + Foto-Filter), nach
  Python übertragen in `core/bild_vorschau.py`: Bild formatfüllend
  beschnitten, Auto-Levels je Kanal (1 %/99 %), Blockmittel, Rampe
  ` .,:;-~=+ox*#%8B@`. **farbe:** jedes Zeichen in der Durchschnittsfarbe
  seines Blocks, auf höchstens 32 Farben (xterm-256) gebracht — jede Farbe
  kostet ein curses-Farbpaar. Auf hellem Grund (Tag) dreht die Ansicht die
  Rampe um. Das Backend merkt sich 64 Vorschauen (Datei, Stand, Größe,
  Modus); die Ansicht holt nur für sichtbare Bilder, deren Größe/Modus
  sich geändert hat, und legt sie als `_vorschau` am Element ab (nie
  gespeichert). Fehlt die Datei (z. B. noch nicht vom anderen Rechner da):
  leise „bild fehlt: …"; kein Bild: „das ist kein bild …"; Pillow fehlt:
  steht so in der Kachel.
- **Öffnen (`o`):** auf dem Rechner, auf dem die TUI läuft
  (`tui/ansichten/bild_betrachter.py`, aus Sashas viscope übernommen).
  Einstellung **`bild_betrachter`** (Env `ZENTRALE_BILD_BETRACHTER`, liefert
  das Backend): `system` (Standard: xdg-open, sonst gio) oder ein Befehl
  wie `feh`, `eog -f`. Abgelöst gestartet, die TUI wartet nicht. Liegt das
  Bild auf diesem Rechner nicht (TUI an einem anderen Backend), holt sie es
  über `GET /api/desk-bild/datei` nach `/tmp/zentrale-bilder-<uid>/`.
- **Abgleich:** `bilder/` liegt unter `data/desk/**` und geht mit. Bilder
  sind binär: `abgleich_zusammenfuehren.art` → „ganz" — hat nur eine Seite
  geändert, gilt sie; haben beide verschieden geändert, bleibt die Fassung
  der Mitte (mit Hinweis). Zusammengeführt wird ein Bild nie.
- **Pillow** (requirements.txt, ≥ 12.3) braucht nur das Backend; die TUI
  importiert es nie. Aussenposten bekommen es nicht (sie haben kein Backend).

## Offene Punkte

- **Zettel später auf echte Notizen umstellen**, sobald das Notiz-Tool ein
  offenes Format hat (Leitlinie: dasselbe Objekt, nicht kopiert). Bis dahin
  sind Zettel Canvas-eigene Text-Knoten.
- **Weitere Kacheln:** Listen (`fokus`) und Graphen (`graph`) fehlen noch —
  je ein Quell-Modul in `core/kacheln.py` QUELLEN, eine Wahl mit
  `neu_label` (wie `KalenderWahl`), ein Sprungziel in `sprung.py`.
- Größe einer Kachel ändern geht nicht (Startgröße beim Anlegen); den
  Bereich einer Kalender-Kachel ändern auch nicht (neu anlegen).
- Esc im Kalender nach `o` führt zur Startseite, nicht zurück zum Desk.
- Desks löschen/umbenennen gibt es nicht (Datei von Hand).
- Größe eines Zettels ändern gibt es nicht (Standard 24×6); auch ein Bild
  behält seine Größe vom Hinlegen.
- Viele farbige Bilder auf einmal können das Farbpaar-Budget der TUI
  (~200 Paare) füllen; dann zeichnen die letzten in Bernstein statt in
  ihren Farben, bis weniger zu sehen ist.
- Ein Bild vom Desk löschen lässt die Datei in `bilder/` liegen (nie
  löschen); aufräumen gibt es nicht.
- Eine Vorschau, die wegen „backend nicht erreichbar" fehlt, wird erst
  beim nächsten Öffnen des Desks neu geholt.
- Desks und Chat-Projekte sind unabhängig; ob ein Desk zu einem Projekt
  gehört, entscheidet Sasha.
- Esc im Modal verwirft ohne Rückfrage.
- Konflikt (409) verliert die letzte Änderung hier.
- Breite Zeichen (Emoji) im Zettel verschieben die Zeile um eine Spalte.

## Historie

- **2026-10-10** — Weich schieben (gleitender Ausschnitt, schneller beim
  Gedrückthalten), W A S D als Hauptbelegung, Alt+Pfeile zusätzlich.

- **2026-10-10** — Kacheln: „kalender" im `+`-Wähler (mit Dialog), Kalender-Kachel
  (Woche/Monat, fest/mitlaufend, +N, blättern), Holen im Hintergrund über
  `/api/kachel`, `o` öffnet (Aktion → Sprung), enter greift immer.
- **2026-10-09** — Grundgerüst: Baustein Canvas, Schnüre, Zettel, Desk View,
  `/api/desk`, Abgleich. Ein Zwischenstand mit Verweisen auf das Notiz-Tool
  wurde am selben Tag zurückgenommen (dessen Format kommt zuerst dran).
- **2026-10-10** — Bilder: Art `bild`, Sashas ASCII-Filter als
  `core/bild_vorschau.py`, `core/desk_bild.py`, `/api/desk-bild…`,
  Bildbetrachter; `o` öffnet, Enter greift immer, `+` mit Wähler.
