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
  Zeile und Breite, die die Quelle angibt. Seit 2026-10-11 keine
  Tasten-Hinweise mehr im Kasten (`[a neu]`, Tipps hinter dem Leer-Text,
  „enter anhängen …" sind weg; `kopf_frei` der Quelle bleibt ungenutzt).
  Die Wurzel (Projekte/Listen-Zonen) setzt dieselben Kästen
  (`listen_bild.kasten`) in ihre zwei Zonen.
- **Tasten (TUI):** Tastentabelle `Fokus.TASTEN` (tui/ansichten/tasten.py) —
  aus ihr verteilt die Ansicht ihre Tasten und liest die Leiste ganz unten.
  Ansichten: `wald` (ganze Liste gewählt) · `wald:ordner` / `wald:punkt`
  (Projekt-Eintrag mit/ohne Unterpunkte; nur am Blatt hakt space/enter ab) ·
  `wald:leer` · `wald:frage` · `wald:neu` / `wald:umbenennen` · `liste`
  (Eintrag gewählt) · `liste:bernstein` (+ `:leer`, enter zeigt das
  Abgeschlossene) · `liste:leer` · `liste:neu` / `liste:umbenennen` ·
  `einordnen` (+ `:leer`) · `verschieben` · `verschieben:name`. Wege in jede
  Ansicht: `tests/tasten_zustaende/fokus.py`.
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

## Das Werkzeug in der TUI und im Canvas

(Am 2026-10-11 aus `system/dashboard.md` hierher gezogen, Regel 9.)

**Fokus-Werkzeug (Mitte, Taste `f`):** EIN gemergtes Werkzeug —
abhakbare Todo-/Sammel-Listen im **FOCUS-Look** (früher zwei getrennte Sachen:
schlichtes Listen-Werkzeug `l` + Projektansicht/Fokus `f`; jetzt verschmolzen und
einheitlich **„Fokus"** genannt, Taste `f`). `l` öffnet dasselbe noch als
**stiller Alt-Alias** (Muskelgedächtnis), taucht aber in KEINER Legende/Einladung
mehr auf — überall steht nur noch `f · fokus`. Geteilte Logik (`core/lists.py` + `/api/lists`),
hier in curses verbaut. Seit 2026-10-11 ist **jeder Knoten ein Kasten**
(Rahmen `┌─┐│└┘`, 3 Zeilen, volle Breite) mit **nur dem
Titel** drin. Das Aussehen steht NICHT hier, sondern in `core/listen_bild.py` —
dasselbe Bild zeigt die Listen-Kachel (Regel *Programm und Kachel teilen EIN
Bild*, siehe oben); `Fokus._malen` bildet nur Rollen
auf Farben ab, `kasten_render` malt `listen_bild.kasten` — kein Zähler, keine Erfüllungsleiste mehr je Eintrag. `▸` =
reindivebar, `◆` = Fokus, `★` = Projekt-Eintrag. Gewählt: Rahmen hell, Titel
invers; sonst Rahmen dezent. **Status** zeigt allein die Bernsteinleiste oben in
der Ebenen-Sicht. (`proj_render` mit Leisten zeichnet nur noch die Fokus-Box
im Backup-Dashboard.) Zustandsmodell `L` (`view`: `forest`/`view`/`place`/`move`/`move_new`).
Die **Wurzel** (`forest`) ist **zweigeteilt**: oben die geflaggten Projekte
(`/api/projects`), Trennlinie `── listen ──`, drunter **alle Nicht-Projekt-Listen**
— beide top-level, per **Enter reindivebar** (wie die frühere Projektansicht;
Deskriptor-Modell `{lid,iid}`, `l_forest_rows`/`l_desc_view`/`l_open_desc`). In der
Wurzel: `↑↓` wählen, **Enter** rein (Liste/Ordner) bzw. Blatt abhaken, `n` neue
Liste (inline), `s` reindiven + gleich anhängen, `r` umbenennen (Liste ODER Eintrag,
inline), `d` löschen (Liste mit `j`/Enter-Nachfrage `L["confirm"]`, Eintrag direkt),
`p` Projekt-Flag (schiebt in die obere Zone), `m` verschieben, `>` forest-weit
einordnen, **`f` setzt den Knoten als alleinigen Fokus** (`/api/projects/focus`,
Toggle; als Box angezeigt nur im Backup-Dashboard, `/dashboard an`). `Esc`/`l` schließt.
Reindivt man in eine Liste, ist es die normale Ordner-Sicht (`view`, s.u.); `Esc`
geht eine Ebene zurück, auf der obersten zurück zur Wurzel.
In **view** die Einträge der offenen Liste — **Ordner-Navigation statt
aufgeklapptem Baum**: jeder Eintrag kann eigene
Unterpunkte tragen; ein Eintrag MIT Kindern ist eine anklickbare Ordner-Zeile
(Marker `▸`), KEIN eingerückter Teilbaum. `L["path"]`
ist der Drill-Pfad (Eintrags-ids) in der offenen Liste, `l_container()` löst die
gerade offene Ebene + Breadcrumb auf, `isel` zählt nur die DIREKTEN Kinder —
und zwar in der **Anzeige-Reihenfolge** `l_vitems()` = `liste_ordnen(…)`:
**Abgeschlossenes ist ausgeblendet**, der **Fokus** (oder ein Ordner, in dem er
steckt) **klebt oben**, der Rest sortiert sich nach **Erfülltheit absteigend**
(was kaum noch Saft braucht, steht oben; Gleichstand = gespeicherte Reihenfolge).
Ganz oben über der Ebene steht die **Bernsteinleiste** (Stelle und Breite aus
`listen_bild.ebene`, veredelt von `Fokus._bernstein` in `tui/ansichten/fokus.py`, 2 Zeilen):
ein Stein je Blatt der Ebene, jeder abgehakte leuchtet, die offenen sind derselbe
Stein fast durchsichtig, der zuletzt abgehakte glimmt im Takt nach; rechts
`erledigt/gesamt`. Gemalt wird sie vom **Pixel-Baustein `tui/pixel.py`** (curses-frei,
`tests/test_tui_pixel.py`): Sashas Stein im **Treppenschliff** (Vorlage war ein
16×16-PNG) als Bauregel `gem(w, h, ay)`, fein gemalt mit 2×6 Pixeln je Zeichenfeld
und je Feld aufs treueste Zeichen gerechnet (**Mix**: Halbblock ▀, Viertel ▚ oder
Sextant 🬗 — VTE zeichnet alle selbst; zwei Farben je Feld). Steinbreite 4/3/2
Zeichen je nach Anzahl, sonst durchgehende Füllung. Farben: 24 Bit, wenn curses es
kann (`TERM=tmux-direct`), sonst die nächste der 256; eigene Farbpaare ab dem
Theme-Ende bis 255 (`PIX`, `pix_attr`). `ZENTRALE_PIXEL=half` = nur Halbblöcke (für
Terminals ohne Sextanten, z.B. E-Ink-App), `=off` bzw. <256 Farben = schlichte
Rückfall-Leiste (`bernstein_steine`, Farbrollen `amber`/`amberhi`/`amberdk`).
Entwürfe dazu entstanden in einer Vorschau-Seite, die dieselbe Umrechnung zeigt. `↑` über
den ersten Eintrag hinaus wählt die Leiste (`isel = -1`), **Enter** darauf schaltet
`L["showdone"]` → nur die **abgeschlossenen** Einträge der Ebene; Enter/`Esc`
wieder zurück (aus einem erledigten Ordner, in den man von dort reinging, geht
`Esc` erst eine Ebene hoch). ↑/↓
wählen, **Enter** geht in einen Ordner REIN (bzw. hakt ein Blatt ab), **`space`**
hakt ein **Blatt** ab/auf (`…/items/<iid>/toggle`), `a` hängt einen Eintrag in die
GERADE OFFENE Ebene an (`L["addparent"]` = Container-id), **`s` hängt einen
Unterpunkt** unter den markierten (macht ein Blatt zum Ordner), **`r` benennt** den
markierten um (vorbefüllt, `POST …/items/<iid>/rename`), **`m` verschiebt** ihn RAUS
in eine andere Liste (→ **move**: Ziel wählen — erste Option `[+ neue Liste]` führt
über **move_new** zu Name-Tippen + `POST /api/lists` und dann
`POST …/items/<iid>/move {into}`; sonst direkt `move` in die gewählte Liste).
Eingabezeile-Modus steckt in `L["imode"]` (`add`/`sub`/`rename`); `a`/`s` bleiben
für Schnell-Eingabe offen, `r` ist einmalig. `d` löscht den markierten samt
Teilbaum. **Abhaken:** nur Blätter sind direkt abhakbar; ein **Ordner** ist NICHT
direkt abhakbar (`space` darauf = Hinweis), sein Häkchen ist **abgeleitet**
(`l_done()` = alle Kinder erledigt → Ordner gilt erledigt; `core.lists.is_done`/
`toggle`→400 spiegeln das). Fortschritt `(erledigt/gesamt)` zählt die **Blätter**
(`l_count`). **Erledigte** Einträge werden **transparent (faint) + durchgestrichen**
gerendert (`addclip(..., strike=True)`, Combining-Overlay U+0336; der Cursor-Pfeil
`›` bleibt normal sichtbar). Lange Ebenen scrollen um den
Cursor. Alles synchron per `api_call()`; nach jeder Aktion `l_load()`+`l_sync_def()`
(offene Liste aus der frischen Registry neu greifen, Drill-Pfad wird validiert/
gekürzt). `Esc`/`l` geht eine Ebene zurück, auf der obersten zurück zur Wurzel
(`forest`); in der Wurzel schließt `Esc`/`l` das Werkzeug.
`--selftest` listet die Listen inkl. erledigt-Zähler (und `◆projekt`-Flag, ohne TTY).
Eine Liste ist kein Zeitreihen-Plot, taucht also nicht in der `lifestyle`-Überlagerung
auf. **Projekt-Flag:** `p` schaltet das Projekt-Flag — in der Wurzel für die
gewählte **Liste** (`POST /api/lists/<lid>/project`) ODER den gewählten
Projekt-Eintrag, in der view-Ebene für den markierten **Eintrag/Unterordner**
(`…/items/<iid>/project`); geflaggte wandern in die obere Zone bzw. tragen ein `◆`/`★`.

**Im Canvas (Browser):** dasselbe Werkzeug, aber der Tab heißt **„Fokus"** und ist
zusätzlich per **Taste `f`** erreichbar (nacktes `f`, wenn kein Eingabefeld
fokussiert ist → synthetischer Klick auf den Fokus-Tab; `data-ex` bleibt intern
`listen`). Die Wurzel ist gleich zweigeteilt (Projekte oben, `── listen ──`
drunter), nur ist die **listen-Zone unten angedockt** (Flex-Feder `.lf-spring` in
`.lf-root`): die Nicht-Projekt-Listen **füllen sich von unten nach oben** auf,
Projekte bleiben oben. Reindive per Klick auf eine Zeile, Aktionen (Fokus ◆ /
Projekt ☆★ / ＋ / ✎ / ✕) als Hover-Icons.
