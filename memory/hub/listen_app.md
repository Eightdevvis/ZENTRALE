# Listen-App (`fokus`) — ein Programm, ein Bild

**Stand 2026-10-11.** Das Listenprogramm wird ein eigenständiges Programm,
das man später aus ZENTRALE herausziehen kann (noch NICHT ausgezogen).

## Die Regel: Programm und Kachel teilen EIN Bild (Sasha, 2026-10-11)

> Das Aussehen eines Listeneintrags wird an EINER Stelle beschrieben;
> Vollansicht und Kachel zeigen beide nur das an. Ändert sich das Design,
> formt sich die Kachel automatisch mit — Kacheln werden nie per Hand
> nachgeschrieben.

Die Stelle ist **`core/listen_bild.py`**. Sie liefert für eine Ebene einer
Liste neutrale Zeilen aus Stücken `[text, rolle]` (dasselbe Format wie eine
Kachel-Antwort, [hub_bauplan.md](hub_bauplan.md) „Kacheln"; Rollen aus
`core/farbrollen.py`):

```
Einkauf                          Kopf (Pfad der Ebene), Rolle kopf
▐███ ░░░░ ░░░░ ░░░░ ░░░░░▌ 1/5   Bernstein = Status der Ebene (2 Zeilen)
▐███ ░░░░ ░░░░ ░░░░ ░░░░░▌
──────────────────────────────   Trennlinie
┌────────────────────────────┐
│ ▸ Baumarkt                 │   Kasten: nur Titel + Marker
└────────────────────────────┘   (▸ Ordner, ★ Projekt, ◆ Fokus)
┌────────────────────────────┐
│ Milch                      │   gewählt: Rahmen betont, Titel „auswahl"
└─────────────────────── +1 ─┘   „+N" = so viele folgen noch
```

- **Kachel** (`core/kachel_fokus.py`): ruft `listen_bild.ebene(...)` für die
  oberste Ebene und reicht die Zeilen unverändert durch — kein eigener
  Zeichner. Parameter: `erledigte` = die abgeschlossenen zeigen statt der
  offenen (wie enter auf den Bernstein); `tiefe` ist seit 2026-10-11
  **veraltet** (`deprecated: true` im Schema, ohne Wirkung — das Programm
  zeigt eine Ebene, Ordner als ▸-Kasten), wird nur noch für alte Adressen
  angenommen, Dialoge bieten es nicht mehr an. Mindestgröße 12×7 (Kopf,
  Bernstein, Strich, ein Kasten).
- **Vollansicht** (`tui/ansichten/fokus.py`, Ebenen-Sicht): malt dieselben
  Zeilen; sie bildet nur Rollen auf curses-Farben ab (`FARBROLLEN`, neue
  Rolle `auswahl` → `sel` = hell invers). Veredelung, die die Struktur
  nicht ändert: Pixel-Bernstein (oder schattierte Rückfall-Spalten) genau an
  Zeile und Breite, die die Quelle angibt; `[a neu]` rechts im Kopf (dafür
  hält die Quelle `kopf_frei` Zellen frei); Tasten-Hinweise hinter dem
  Leer-Text. Die Wurzel (Projekte/Listen-Zonen) setzt dieselben Kästen
  (`listen_bild.kasten`) in ihre zwei Zonen.
- **Wächter:** `tests/test_listen_bild.py` — dieselbe Liste ergibt in Kachel
  und TUI dieselben Zeilen; die Kachel reicht nur durch; `kachel_fokus.py`
  enthält keine Rahmen-/Marker-Zeichen und keine Zeichen-Funktionen;
  `listen_bild` importiert nur `listen_baum` und benutzt nur Rollen aus dem
  Wörterbuch.

## Was zum Listenprogramm gehört

| Datei | Teil | Schicht |
|---|---|---|
| `core/lists.py` | Logik + Speicher (Listen-Registry) | 2 |
| `core/listen_baum.py` | Rechnen über den Eintrags-Baum (zählen, ordnen, Steine) | 1 |
| `core/listen_bild.py` | DAS Bild einer Ebene | 1 |
| `core/kachel_fokus.py` | Kachel-Quelle (Katalog, Bild, `oeffnen`) | 2 |
| `ui/routen/listen.py` | HTTP `/api/lists` | 5 |
| `tui/ansichten/fokus.py` | Terminal-Ansicht (malt, Tasten) | Front |

**Warum flache Dateien statt eines Pakets `core/listen/` (jetzt):** Der
Kern-Bauplan zählt ein Paket als EIN Modul mit EINER Schicht — die Teile
liegen aber in Schicht 1 (rein, auch auf dem Aussenposten) und Schicht 2
(Speicher). Die TUI und der Aussenposten dürfen nur die reinen Teile
(`listen_baum`, `listen_bild`) bekommen, nie `lists.py`. Und `lists.py`
umzuziehen hieße sieben Importstellen plus Prüfstand mitzuziehen — ohne
Gewinn, solange das Programm im Repo wohnt. Zusammengehalten wird es durch
diese Tabelle, den Namen (`listen_*`) und die Import-Wächter.

## So sieht der spätere Auszug aus

Wie beim Tutor ([hub_bauplan.md](hub_bauplan.md) „Schritt 1"): eigenes Repo,
eigener Prozess, `app.toml` mit `liefert = ["kachel:liste"]`.

1. `lists.py`, `listen_baum.py`, `listen_bild.py`, `kachel_fokus.py` und
   die Terminal-Ansicht ziehen als **ein Paket** um (dann mit eigener
   Ordnerstruktur, z. B. `fokus/`).
2. Die Kachel-Quelle wird zum HTTP-Handler der App; im Hub wird nur der
   Adapter in `core/kacheln.py` (`QUELLEN`) gegen HTTP getauscht. Das Bild
   bleibt `listen_bild`, die Kachel-Antwort bleibt dieselbe.
3. Was die App heute noch vom Hub importiert und dann über die
   Hub-Schnittstelle bekommt: `kachel_form` (Fehlerklassen), `kachel_parameter`
   (Schema-Konstante, `mit_auswahl`), `adressen` (Adresse bauen),
   `dateien` (in `lists.py`, Speicherort → `daten/fokus/`).
4. Andere Hub-Teile, die heute direkt `lists` lesen, müssen dann über HTTP
   fragen: `core/kalender_quelle.py`, `core/morgenblick_daten.py`,
   `ui/routen/kalender.py`, der Prüfstand.
5. Die TUI-Ansicht wird die `terminal`-Ansicht der App; ihre Rollen-Farben
   kommen weiter aus der Oberfläche.
