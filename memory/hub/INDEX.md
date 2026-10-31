# Hub — Index

ZENTRALE als Plattform: die Hub-Schnittstelle, das App-Modell, wie Apps
entstehen und geholt werden, die Bausteine, die Apps nutzen, und der Weg
zum Produkt. Wie der Kern darunter gebaut ist (Threads, Schichten, TUI,
Topologie): [../system/INDEX.md](../system/INDEX.md).

**Rule (Sasha, 2026-10-31 — permanent):** apps live outside the core — every
new app is its own package; see CLAUDE.md „Apps live outside the core" and
[building_kit_plan.md](building_kit_plan.md) §3.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Hub-Bauplan — die eine Regel, Hub-Dienste, Manifest `app.toml`, Rechte, Umzug der Module, Kacheln, Adressen `zentrale://…`, Katalog, Farbrollen, KI-Werkzeuge aus dem Schema, Anbindungs-Pipe | [hub_bauplan.md](hub_bauplan.md) |
| **Building kit (plan, 2026-10-30)** — plug model (pieces offer/need typed ports, wires), versioned contracts without forced updates, tiny core + bundles, node lifecycle and keeper timers, wiring map on the Desk with Run (check → diff → switch) | [building_kit_plan.md](building_kit_plan.md) |
| **Port types, wires, Run gate, plug dialog (built 2026-10-30, building kit 9/9b/11)** — the type registry (TOSCA/NetBox terms, JSON Schema 2020-12, SemVer) and why the vocabulary is cut so, `needs`/`offers` in manifests, wires as a projection (`/api/wires`), the compiler's rules, generations, apply agent on the keeper, roll-back; the plug dialog at install and where plugs live; node wires in the node description; what steps 13–15 build on | [port_types.md](port_types.md) |
| **Wo ein Zustand lebt** — rohes ZENTRALE (Gestell je Knoten) oder App (synct ohne Gnade); Prüffrage vor jedem Entwurf (Sasha, 2026-10-29) | [standort_und_app.md](standort_und_app.md) |
| **App-Motor (Plan, 2026-10-29)** — App-Paket in Standardformaten, Ansichten als Bausteine (Handy/TUI), Logik als WASM hinter dem HTTP-Vertrag, Play-Regeln, Installieren/Aktualisieren je Knoten, Signatur, Weg für KI-Chat und Kalender am Handy, offene Fragen | [app_motor_plan.md](app_motor_plan.md) |
| **Listen-App (`fokus`)** — Programm und Kachel teilen EIN Bild (`core/listen_bild.py`), was zum Listenprogramm gehört, wie der spätere Auszug aussieht, Tasten und Ebenen des Fokus-Werkzeugs in TUI/Canvas | [listen_app.md](listen_app.md) |
| **Werkstatt** — Erschaffen-Rad, der Schmied baut eigene Apps aus Vorlagen, Ablage unter `data/apps/`, Desks verwalten | [werkstatt.md](werkstatt.md) |
| **Schaufenster (Shop)** — Katalog als schema.org-ItemList, Kategorien, holen, Besitz je Rechner, **Apps installieren** (Ansichten wählen, ins Rad, öffnen), später bezahlen | [shop.md](shop.md) |
| **Schematix (built 2026-10-30, building kit 13–15)** — the wiring map app: how to open and use it (keys), map of the account (this node + node descriptions), versions panel, layers, `+` picker, schemes and things, Run from the drawing | [schematix.md](schematix.md) |
| **Schematix style** — hacker × wizard, an "ethereal machine": thin traces of light on planes of near-black, a surface + texture per plane, sigils on plates, pixel-art device icons with the name below, glyphs per state, colour roles (text, surface, texture) with measured contrast | [schematix_style.md](schematix_style.md) |
| **Desk View** — der Canvas-Baustein: Fläche je Desk, Zettel, Schnüre, Bilder, Kacheln, Format JSON Canvas, Tasten | [desk_view.md](desk_view.md) |
| **Farbwähler und Stylebox** — Bausteine für jede Ansicht: Farbkreis, Stil als CSS-dict mit Angebot als JSON Schema, Aufruf, Tasten | [bausteine_farbe_stil.md](bausteine_farbe_stil.md) |
| **Knoten beitreten (Plan)** — neues Gerät (Mini-PC) tritt der Installation bei statt kopiert zu werden: drei Schichten (Programm/Daten/Gerät), Knoten-Beschreibung als JSON + Schema, Einladung als `zentrale://`-Adresse; leere Hub-Fassung fehlt noch. Dazu **Bauplan v1**: Login, Cloud (Zero-Knowledge-Schlüssel, Routen), Befehl `zentrale` + install.sh — Client gebaut 22.10., Testvektoren für andere Oberflächen | [knoten_beitritt.md](knoten_beitritt.md) |
| **Core extraction: inventory** (re-measured 2026-10-31) — logic that lives only in the TUI (places and missing routes, A1–A20), app candidates with fan-in/fan-out (incl. Schematix), what the bare core keeps, order with the next step (Lists ready to move inside the core), boundary guards E1–E8 and which exist, AI tools/skills hub vs. app (gap: apps cannot bring tools), device-adapter frame, decisions for Sasha | [kern_auszug_inventur.md](kern_auszug_inventur.md) |
| **Lists moves out — step plan** (2026-10-31) — what to do in the core first (A8/A9, resolve route, Prüfstand), then the move as a package, proofs, risks | [list_extraction_plan.md](list_extraction_plan.md) |
| **Altlast: Routen ohne Beschreibung** (Wächter E4, seit 2026-10-22) — welche Routen der TUI noch nicht in `openapi.yaml` stehen; die Liste darf nur schrumpfen | [routen_altlast.md](routen_altlast.md) |
| **Die Cloud als App** — Apps sagen im Manifest (`[daten]`), was sie haben; die Auswahl beim Abgleich entsteht aus den installierten Apps; eingebaute Apps im Übergang | [cloud_app.md](cloud_app.md) |
| **Cloud folder** (2026-10-29) — `~/Zentrale/Cloud`, anything dropped there syncs over the normal sync (`data/cloud/**`); the wheel icon opens it in the file manager; too-large files and a vanished folder are held back, the cloud wins | [cloud_folder.md](cloud_folder.md) |
| **Adapter** — die eine Tür zu fremden Diensten (Google, KI-Anbieter): Anschlüsse mit Beschreibung + verschlüsselten Zugangsdaten, überall abgeglichen; Brücke als Mietvertrag mit nahtlosem Wechsel; immer installiert (gebaut 24.10.); **Quelle der Kalender-App** (google | zencloud | lokal, eine Datei je Kalender-App, umstöpseln an einer Stelle, 29.10.) | [adapter.md](adapter.md) |
| **Produkt-Inventur** — welche App/welcher Hub-Teil wie weit ist, Lizenz-Ecke, was vor dem Verkauf fehlt | [produkt_inventur.md](produkt_inventur.md) |

Routen-Überblick (Kachel, Desk, Shop, Werkstatt, Apps):
[../system/api_endpoints.md](../system/api_endpoints.md); genaue Form in
`openapi.yaml` (Repo-Wurzel).
