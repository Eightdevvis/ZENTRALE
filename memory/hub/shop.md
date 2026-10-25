# Schaufenster — der kleine Laden in ZENTRALE

**Stand 2026-10-10: gebaut als Schaufenster, alles kostenlos.** Stücke ansehen
und „holen"; bezahlen kommt später über Sashas eigenen Server. Katalog als
schema.org-`ItemList` (JSON-LD) in `core/shop_katalog.jsonld`, Dienst
`core/shop.py`, Routen `ui/routen/shop.py` (`/api/shop*`, in `openapi.yaml`),
Ansicht `tui/ansichten/shop.py` (`Shop.oeffnen()`). Platz im Rad: `shop` im
Erschaffen-Rad (seit 2026-10-10, [werkstatt.md](werkstatt.md),
`rad_wahl.OEFFNEN` → `u.shop.oeffnen()`). Geholte Icons bietet der Schmied
beim Symbol-Schritt an.

## Warum so

- **Keine eigenen Formate** (Sasha, 2026-10-10; [hub_bauplan.md](hub_bauplan.md)
  „Standards statt Eigenformat"): Katalog und Besitz sind schema.org in
  JSON-LD — jedes Werkzeug, das Produkte lesen kann, liest auch diesen Laden,
  und später kann Sashas Server dieselbe Liste ausliefern.
- **Nur Echtes.** Im Laden liegt nur, was es in ZENTRALE wirklich gibt.
  Eine Kategorie ohne Stücke zeigt „noch leer" — lieber leer als erfunden.
- **Dasselbe Objekt, nicht kopiert.** Der Besitz speichert nur die Adresse
  des Stücks; Name und Beschreibung liest `GET /api/shop/besitz` frisch aus
  dem Katalog.

## Kategorien und was drin ist

Reihenfolge der Leiste: Icons, Hintergründe, Apps, Bauteile, Agenten,
Avatare (`shop.KATEGORIEN`, ids `icons`, `hintergruende`, `apps`,
`bauteile`, `agenten`, `avatare`). Themen = `keywords` jedes Stücks.

| Kategorie | schema.org | Inhalt (Stand 2026-10-10) |
|---|---|---|
| Icons | `ImageObject` | **alle** Pixel-Symbole der Apps im Rad (Sasha, Nachtrag 2026-10-10): post, karte, kalender, klavier, notizen, graph, fokus, tutor, desk (`tui/pixel.py` `MOTIVE`) und elektronik. `additionalProperty` `pixel_motiv` = Name des Motivs; die TUI zeichnet daraus die Vorschau. Das Technik-Rad hat keine Pixel-Symbole. |
| Hintergründe | `CreativeWork` | Denk-Adern (Hintergrund des Chats, wenn die KI denkt), Nacht, Tag (die beiden Farbwelten der TUI) |
| Apps | `SoftwareApplication` | **Budget** (seit 2026-10-25, Repo `Eightdevvis/budgeter`) — installierbar, Abschnitt „Apps installieren" unten. Tutor und Karte stehen (noch) nicht im Laden, sie sind fest im Rad. |
| Bauteile | `SoftwareApplication` | Desk View als Vorlage (`applicationCategory` „Vorlage", der Canvas-Baustein), die drei Kacheln Kalender-Ausschnitt, Liste, Graph-Verlauf (`isBasedOn` = Adresse der Kachel-Art) |
| Agenten | `SoftwareApplication` | noch leer (`core/profil/` sind Modell-Schienen, keine Agenten) |
| Avatare | `ImageObject`/`Product` | noch leer |

Neues Stück: in `core/shop_katalog.jsonld` einen `ListItem` anhängen —
`@id` muss `zentrale://shop/<category>/<identifier>` sein, sonst lehnt
`shop.pruefen` den GANZEN Katalog ab (503, lieber laut als ein halber Laden).
`tests/test_shop.py` prüft Form, Adressen, Preis und dass die Icons genau
die Motive des Rads sind.

## Form

Katalog (`GET /api/shop`, Medientyp `application/ld+json`):

    {"@context": "https://schema.org", "@type": "ItemList", "numberOfItems": n,
     "itemListElement": [{"@type": "ListItem", "position": 1, "item": {
        "@type": "ImageObject", "@id": "zentrale://shop/icons/post",
        "identifier": "post", "name": "Post", "description": "…",
        "category": "icons", "keywords": ["pixel", "rad", "nachrichten"],
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "EUR", …},
        "additionalProperty": [{"@type": "PropertyValue", "name": "pixel_motiv", "value": "post"}]}}]}

Besitz (`GET /api/shop/besitz`): dieselbe `ItemList`, jedes `item` ein
`OwnershipInfo` mit `ownedFrom` (Zeitpunkt) und `typeOfGood` (das Stück aus
dem Katalog). Genaue Schemas: `openapi.yaml` (`Shop*`).

## Holen

`POST /api/shop/holen {"adresse"}` — idempotent: schon Geholtes bleibt mit
seinem ersten Datum (`neu: false`). Gespeichert in
`<shop_ordner>/besitz-<rechner>.jsonld` (Einstellung `shop_ordner`, Standard
`data/shop/`, gitignored, im Abgleich: `data/shop/**`). **Eine Datei pro
Rechner** (2026-10-10), weil `.jsonld` im Abgleich als Text zusammengeführt
würde und zwei Rechner, die gleichzeitig holen, sonst eine kaputte Datei
bekämen; gelesen wird die Vereinigung aller Dateien, das früheste Datum
gilt.

Die **Werkstatt** liest geholte Icons über
`GET /api/shop/besitz?kategorie=icons` und zeichnet sie nach `pixel_motiv`.

## In der TUI

`tui/ansichten/shop.py`, Kasten „Schaufenster": oben die Kategorien (←→,
leere blass), darunter „thema: alle" (tab vor, shift+tab zurück; die Themen
kommen aus der gewählten Kategorie, gefiltert wird beim Hub), links die
Stücke (↑↓, ✓ = geholt), rechts das Stück: bei Icons das Pixel-Symbol wie im
Rad, Name, Preis („kostenlos"), Beschreibung, Themen, ggf. „geholt ✓".
Enter holt („geholt ✓", nochmal: „hast du schon ✓"), Esc zurück.
Tasten: Tastentabelle `Shop.TASTEN` (2026-10-11), Ansichten `regal` ·
`regal:ohne_thema` · `leer` · `leer:thema` · `fehler`; die Leiste ganz unten
zeigt sie, im Kasten stehen keine Tastenhinweise mehr. Nach Hot Reload geht das
Schaufenster wieder auf (`_offen_apps`).

## Apps installieren (gebaut 2026-10-25)

Sasha: *„Keine Skripts. Ich will die App offiziell über den ZENTRALE-Store
runterladen. Vor dem Install wähle ich die Versionen, die ich will. Dann wird
die App in mein Rad geklatscht, ich wähle sie aus und kann die Version wählen,
die geöffnet werden soll."* Vorher konnte der Laden nur „holen" (Besitz), und
Prozess-Apps standen fest in `apps.BEKANNT`.

**Im Katalog** trägt ein Stück der Kategorie apps zusätzlich `downloadUrl`
(ein git-Repo, `https`/`ssh`/`file`) und `additionalProperty` `app_name` (der
`name` aus seinem app.toml). Fehlt eins, lehnt `shop.pruefen` den ganzen
Katalog ab (`app_installation.quelle_pruefen`). Mehr steht nicht im Katalog:
Titel, Ansichten, Symbol kommen aus dem app.toml der App.

**Ablauf** (`core/app_installation.py`, Routen in `ui/routen/hub_apps.py`):

1. `POST /api/apps/laden {adresse}` — `git clone` nach
   `<app_ordner>/.laden/<repo>` (ohne Rückfrage: `GIT_TERMINAL_PROMPT=0`,
   ssh `BatchMode`), app.toml lesen und prüfen (Name = `app_name`, kein
   Name einer festen/selbst gebauten App, mindestens eine Ansicht). Antwort:
   die Ansichten zur Wahl. Liegt am Platz schon ein Checkout **desselben**
   Repos (Herkunft `origin`, Schreibweise egal), wird er übernommen — so
   bleibt Sashas Entwickler-Checkout der eine Ordner. Ein fremder Ordner
   gleichen Namens → 409, nichts wird überschrieben.
2. `POST /api/apps/installieren {adresse, ansichten}` — mindestens eine
   Ansicht aus dem app.toml; der Ordner zieht an `<app_ordner>/<repo>`,
   die Wahl kommt ins Register, das Stück gilt als geholt. Nochmal aufrufen
   ändert nur die Wahl.

- **`app_ordner`** (Einstellung, Env `ZENTRALE_APP_ORDNER`): Standard der
  Ordner, in dem ZENTRALE liegt — neben Tutor und Karte.
- **Register** je Rechner: `<installiert_ordner>/apps-<rechner>.json`
  (Standard `data/hub/`, steht NICHT auf der Positivliste: der Code liegt nur
  hier, ein anderer Rechner wählt selbst). Nur Name, Quelle, Ordner, gewählte
  Ansichten, Datum.
- Der Hub findet die App danach wie jede andere (`apps.pfad`,
  `apps.installiert`, `GET /api/apps` mit `quelle`, `ansichten_installiert`,
  `icon`); die Werkstatt vergibt ihren Namen nicht mehr.

**Symbol:** `icon = "icon.png"` im app.toml — quadratisches PNG bis 32×32,
gelesen in voller Größe (`bild_vorschau.icon_raster(pfad, None)`; Werkstatt-
Symbole bleiben 16×16). Die TUI malt es wie ein Werkstatt-Symbol
(`pixel.symbol_eintragen`): es klappt auf, die Schriftplatte liegt drüber.

**In der TUI:** Kategorie Apps, Enter = installieren (Leiste „install"): die
App wird im Hintergrund geladen („lade …", Ansicht `laedt`), dann die Wahl
`[x] im browser` / `[x] im terminal` (Ansicht `wahl`: ↑↓, space an/aus,
enter installieren, esc abbrechen; ohne Haken: „mindestens eine ansicht
wählen"). Danach holt `eigene_apps` die Liste neu — die App steht im App-Rad
vor den selbst gebauten. Enter im Rad → Router `zentrale://<name>/` →
`tui/ansichten/app_oeffnen.py`: eine Ansicht geht direkt auf, mehrere zeigen
den Kasten „wie soll … aufgehen?" (↑↓ enter esc).

- **browser:** `POST /api/apps/<name>/start` (läuft sie, passiert nichts),
  dann `adresse` + `[ansicht.browser] pfad` mit `xdg-open` (nur mit
  grafischer Sitzung).
- **terminal:** `scripts/open_app_window.py <name> --ansicht terminal` im
  Terminal der TUI (curses tritt beiseite wie beim Editor), danach zurück.
- **fenster:** derselbe Starter im Hintergrund (wie die Karte).

TUI und Backend müssen dafür auf demselben Rechner laufen (Adresse
127.0.0.1, Starter liest den Ordner); unterwegs über einen fremden Hub geht
das Öffnen noch nicht.

**Offen:** Deinstallieren; Aktualisieren (heute: im Ordner selbst `git
pull`); Rechte-Dialog vor dem Einrichten (die Apps im Laden haben keine
Rechte); Tutor/Karte über denselben Weg statt `BEKANNT`; die Web-Oberfläche
zeigt weder Laden noch Rad.

## Später: bezahlen und Sashas Server

- **Tauschstelle:** `shop._katalog_roh()` liest heute die Datei (Einstellung
  `shop_katalog` überschreibt den Pfad). Später holt sie dieselbe ItemList
  von Sashas Server und fällt auf die Datei zurück.
- **Preis:** heute steht überall `price: "0"`. Ein Stück mit Preis > 0 lehnt
  `holen` mit **402** ab („bezahlen geht noch nicht"). Mit dem Server prüft
  er die Zahlung/das Abo, bevor der Besitz entsteht — die Besitz-Datei bleibt
  dieselbe (Schlüssel nie beim Kunden, [hub_bauplan.md](hub_bauplan.md)
  „Verkaufen").

## Offen

- `zentrale://shop/…` im Adress-Router der TUI (`sprung.py`) — eine Adresse
  aus einer Notiz öffnet das Stück noch nicht.
- Weitere Apps, Agenten, Avatare, sobald es sie gibt.
