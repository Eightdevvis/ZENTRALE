# Maps — Index

Die interaktive Karte: Layer-Architektur, woher die Daten kommen und wie sie
aussehen soll.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Layer-Architektur, die drei Achsen, Rendering, wie ein Layer dazukommt | [maps_system.md](maps_system.md) |
| Welcher Layer aus welcher offiziellen Quelle kommt, mit Lizenz — die Charta | [maps_quellen.md](maps_quellen.md) |
| Look-Handoff: wie die Karte aussehen soll (Design-Brief) | [maps_design_brief.md](maps_design_brief.md) |

## Zwei harte Regeln

- **Primärquellen, tagesaktuell, sauber lizenziert.** Lizenzierte Daten werden
  nur gecacht, nie committet (siehe `.gitignore`, `core/map/data/cache/`).
- **Keine Produkt- oder Designentscheidung ohne Sashas Freigabe.** Quellen
  stapeln statt verschmelzen; Überschneidungen sind ein eigener Konsens-Layer.
