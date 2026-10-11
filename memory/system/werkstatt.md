# Werkstatt — der Schmied baut eigene Apps aus Vorlagen

**Stand 2026-10-10: gebaut, auf `main` (Commit b195f79).** Sasha: ein
drittes Rad „erschaffen" neben App- und Technik-Rad, darin die **Werkstatt**
und ein Platz für den **Shop**. In der Werkstatt fragt der Schmied mit
kurzen Sätzen Schritt für Schritt und baut aus einer Vorlage eine eigene
App, die danach im App-Rad steht. „So simpel wie's geht."

## Was Sasha entschieden hat (2026-10-10)

1. Drittes Rad **erschaffen** (rechts neben technik): Plätze `werkstatt`,
   `shop`. alt+←/→ geht einen Schritt (am Rand bleibt es stehen), Stellung
   reist beim Hot Reload mit, Pixel-Symbole wie im App-Rad.
2. **Desk ist ein Baustein, keine App**: raus aus dem App-Rad; Desks werden
   in der Werkstatt verwaltet („deine desks").
3. **Elektronik** bleibt fest im App-Rad und öffnet direkt den Desk
   „Elektronik" (beim ersten Mal angelegt); Esc führt zurück aufs Rad. Der
   leere Elektronik-Bereich (`ELEK`) ist weg.
4. Der Schmied fragt: **Name → Symbol → Vorlage → Agent → bauen.**
5. Ablage in **Standards**: Ordner mit `app.toml` (dasselbe Hub-Manifest)
   + `icon.png`, abgeglichen; Adresse `zentrale://<slug>/`.
6. Verwalten: eigene Apps (öffnen, umbenennen, Symbol ändern, wegwerfen —
   mit Rückfrage, ob der Desk mit soll) und die Desks.

## Der Ablauf (tui/ansichten/werkstatt.py)

Bedienung nur ↑↓ Enter Esc und Tippen; ↑↓ laufen rundherum. Esc geht einen
Schritt zurück, am Anfang zu. Der Schmied sagt je Schritt einen Satz
(`SAETZE`); rechts steht das Symbol der App, um die es geht.

| Schritt | Schmied | Wahl |
|---|---|---|
| start | „Moin. Ich bin der Schmied. Was bauen wir?" | neue app bauen · vorlagen ansehen · deine apps · deine desks |
| name | „Wie soll die neue App heißen?" | tippen, Enter → `POST /api/werkstatt/name` prüft gleich (leer, ungültig, vergeben, reserviert) |
| icon | „Welches Symbol soll sie im Rad tragen?" | ein bild aus dem input-ordner · ein zufälliges symbol (aus `pixel.FESTE_MOTIVE`) · Symbole aus dem Shop, wenn es `GET /api/shop/besitz` gibt |
| bild | „Such dir ein Bild aus deinem Input-Ordner aus." | Bilder aus `~/Zentrale/Input` (leer: Hinweis + zurück) |
| vorlage | „Woraus soll ich sie bauen?" | heute nur **Desk View** |
| agent | „Einen eigenen Agenten bekommt sie später …" | weiter (Platzhalter, keine Logik) |
| fertig | „Also: „Geige", bild „geige.png", aus „Desk View". Soll ich?" | ja, bauen · abbrechen |
| gebaut | „Fertig. „Geige" steht jetzt im App-Rad." | öffnen · zurück in die werkstatt |

Öffnet die Werkstatt einen Desk (App öffnen, Desk öffnen), bleibt sie
darunter offen: Esc auf dem Desk führt in die Werkstatt zurück.

## Ablage (core/werkstatt.py, Schicht 2)

```
<apps_ordner>/<slug>/app.toml     # Standard data/apps/, Einstellung apps_ordner
<apps_ordner>/<slug>/icon.png     # nur bei Symbol aus einem Bild
<desk_ordner>/<Name>.canvas       # der Desk, wie jeder andere (Verweis, keine Kopie)
```

```toml
name = "Geige"
version = "0.1.0"
vorlage = "desk"
icon = "icon.png"        # oder: icon_motiv = "post"
desk = "Geige"           # Name des Desks, auf den die App zeigt
erstellt = "2026-10-10T17:34:30"
```

- **Kurzname (slug)** aus dem Namen: klein, ä→ae …, a–z 0–9 „-", höchstens
  16 Zeichen (passt als Schriftzug aufs Symbol), vorn ein Buchstabe. Er ist
  Ordnername und Adresse und bleibt beim Umbenennen gleich. Reserviert:
  Namen der festen Apps, der Räder und des Hubs (`RESERVIERT`).
- **Symbol aus einem Bild**: `bild_vorschau.icon_machen` — quadratisch
  beschnitten, 16×16, höchstens 16 Farben (xterm-256), Durchsichtiges ganz
  oder gar nicht; nur aus `Input/` (kein freier Pfad). Die TUI bekommt das
  Raster (`icon_raster`) über `GET /api/werkstatt/apps` und malt es wie jedes
  Motiv (`pixel.symbol_eintragen`).
- **Bauen** legt den Desk gleichen Namens an; gibt es ihn schon, nimmt die
  App ihn (nichts wird überschrieben). Geht etwas schief, bleibt kein halber
  Ordner liegen.
- **Löschen** wirft den App-Ordner weg; den Desk nur, wenn Sasha „desk auch
  wegwerfen" wählt. Ein Desk, auf dem eine App steht, lässt sich nicht
  löschen (409); umbenennen zieht die Apps mit.
- Fund: `core/apps.py` (`eigene_ordner`, `eigene_namen`, `eigene`,
  `installiert` = Prozess-Apps + eigene). Abgleich: `data/apps/**` auf der
  Positivliste ([../betrieb/abgleich.md](../betrieb/abgleich.md)).

## In der TUI

- `ansichten/eigene_apps.py`: holt die Liste (Start, nach jeder Änderung,
  sonst jede Minute — eine App kann über den Abgleich von einem anderen
  Rechner kommen), trägt Platz im Rad (`startseite.EIGENE_APPS`, hinter den
  festen), Symbol (`pixel.symbol_eintragen`) und Adresse im Router
  (`sprung.Router.registrieren`, Handler öffnet den Desk) ein; Gelöschtes
  wieder aus.
- `ansichten/rad_wahl.py`: Enter auf einem Rad öffnet über eine Tabelle
  (`OEFFNEN`) statt einer if-Kette; eine eigene App (`app:<slug>`) geht über
  ihre Adresse an den Router. Der Shop-Platz ruft `u.shop.oeffnen()` —
  fehlt die Ansicht noch, steht „shop kommt gleich" in der Befehlszeile.
- Routen: [api_endpoints.md](api_endpoints.md), genau in `openapi.yaml`.

## Später (nicht gebaut)

- **Agent-Schritt** mit Inhalt: der App einen eigenen Agenten geben.
- **Agent-Macher**: eigener Platz im Erschaffen-Rad.
- **Mehr Vorlagen** (`VORLAGEN` + ein Weg in `anlegen()` und ein Öffner in
  `eigene_apps._oeffner`).
- **Bauteile-Shop**: Vorlagen, Symbole, Kacheln kaufen; Symbole aus dem
  Besitz erscheinen schon jetzt beim Symbol-Schritt, sobald der Shop
  `GET /api/shop/besitz` liefert (Liste oder `{icons: [{name, motiv}]}`).
- **Atelier**: Symbole selbst zeichnen statt aus einem Bild.
