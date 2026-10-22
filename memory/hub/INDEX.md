# Hub — Index

ZENTRALE als Plattform: die Hub-Schnittstelle, das App-Modell, wie Apps
entstehen und geholt werden, die Bausteine, die Apps nutzen, und der Weg
zum Produkt. Wie der Kern darunter gebaut ist (Threads, Schichten, TUI,
Topologie): [../system/INDEX.md](../system/INDEX.md).

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Hub-Bauplan — die eine Regel, Hub-Dienste, Manifest `app.toml`, Rechte, Umzug der Module, Kacheln, Adressen `zentrale://…`, Katalog, Farbrollen, KI-Werkzeuge aus dem Schema, Anbindungs-Pipe | [hub_bauplan.md](hub_bauplan.md) |
| **Listen-App (`fokus`)** — Programm und Kachel teilen EIN Bild (`core/listen_bild.py`), was zum Listenprogramm gehört, wie der spätere Auszug aussieht, Tasten und Ebenen des Fokus-Werkzeugs in TUI/Canvas | [listen_app.md](listen_app.md) |
| **Werkstatt** — Erschaffen-Rad, der Schmied baut eigene Apps aus Vorlagen, Ablage unter `data/apps/`, Desks verwalten | [werkstatt.md](werkstatt.md) |
| **Schaufenster (Shop)** — Katalog als schema.org-ItemList, Kategorien, holen, Besitz je Rechner, später bezahlen | [shop.md](shop.md) |
| **Desk View** — der Canvas-Baustein: Fläche je Desk, Zettel, Schnüre, Bilder, Kacheln, Format JSON Canvas, Tasten | [desk_view.md](desk_view.md) |
| **Farbwähler und Stylebox** — Bausteine für jede Ansicht: Farbkreis, Stil als CSS-dict mit Angebot als JSON Schema, Aufruf, Tasten | [bausteine_farbe_stil.md](bausteine_farbe_stil.md) |
| **Knoten beitreten (Plan)** — neues Gerät (Mini-PC) tritt der Installation bei statt kopiert zu werden: drei Schichten (Programm/Daten/Gerät), Knoten-Beschreibung als JSON + Schema, Einladung als `zentrale://`-Adresse; leere Hub-Fassung fehlt noch | [knoten_beitritt.md](knoten_beitritt.md) |
| **Kern-Auszug: Inventur** (2026-10-22) — Logik, die nur in der TUI steckt (mit Stellen und fehlenden Routen), App-Kandidaten mit Fan-in/Fan-out, was der leere Kern behält, Reihenfolge (Karte zuerst, dann Listen; Graphen erst entflechten), Grenz-Wächter | [kern_auszug_inventur.md](kern_auszug_inventur.md) |
| **Produkt-Inventur** — welche App/welcher Hub-Teil wie weit ist, Lizenz-Ecke, was vor dem Verkauf fehlt | [produkt_inventur.md](produkt_inventur.md) |

Routen-Überblick (Kachel, Desk, Shop, Werkstatt):
[../system/api_endpoints.md](../system/api_endpoints.md); genaue Form in
`openapi.yaml` (Repo-Wurzel).
