# Schaufenster — der kleine Laden in ZENTRALE

**Stand 2026-10-10: gebaut als Schaufenster, alles kostenlos.** Stücke ansehen
und „holen"; bezahlen kommt später über Sashas eigenen Server. Katalog als
schema.org-`ItemList` (JSON-LD) in `core/shop_katalog.jsonld`, Dienst
`core/shop.py`, Routen `ui/routen/shop.py` (`/api/shop*`, in `openapi.yaml`),
Ansicht `tui/ansichten/shop.py` (`Shop.oeffnen()`). Einen Platz im Rad hat
das Schaufenster noch nicht — den bringt die Werkstatt (Rad-Platz `shop` →
`u.shop.oeffnen()`).

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
| Apps | `SoftwareApplication` | noch leer — Sashas eigene Apps sind „noch zu wonky" für den Laden |
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
Rad, Name, Preis („kostenlos"), Beschreibung, Themen, „enter = holen" bzw.
„geholt ✓". Enter holt („geholt ✓", nochmal: „hast du schon ✓"), Esc zurück.
Fußleiste: Kontext `shop` in `befehle.CTX_KEYS`. Nach Hot Reload geht das
Schaufenster wieder auf (`_offen_apps`).

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

- Ein Rad-Platz (kommt mit der Werkstatt).
- `zentrale://shop/…` im Adress-Router der TUI (`sprung.py`) — eine Adresse
  aus einer Notiz öffnet das Stück noch nicht.
- Echte Apps, Agenten, Avatare, sobald es sie gibt.
