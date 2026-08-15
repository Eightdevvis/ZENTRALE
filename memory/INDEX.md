# ZENTRALE — Memory Index

Die modulare Wissensbasis des Projekts. **Nicht alles lesen** — über diesen
Index in den passenden Ordner springen, dort steht ein eigener Index mit den
Themen dieses Bereichs.

Zwei Ebenen, damit es das bleibt, was es sein soll: dieser Index nennt nur
**Bereiche**, die Ordner-Indizes nennen **Themen**, und der Inhalt steht in
den Dateien. Sonst wächst hier wieder eine 40-Zeilen-Tabelle heran, die man
überfliegt statt zu benutzen.

## Bereiche

| Bereich | Was drinsteht | Index |
|---|---|---|
| **KI** | Wie ZENTRALE denkt: lokal + Cloud, Konzept-Graph, Tools, Erlaubnis-Gate, Sprache, Pläne, Benchmarks | [ki/INDEX.md](ki/INDEX.md) |
| **Werkzeuge** | Was ZENTRALE tut: Kalender, Mail, News, Notizen, Zyklus, Morgen-Messenger | [werkzeuge/INDEX.md](werkzeuge/INDEX.md) |
| **System** | Wie es gebaut ist: Architektur, Events, Topologie, API, Dashboard, Tastatur | [system/INDEX.md](system/INDEX.md) |
| **Betrieb** | Wie es läuft: Setup, Starten, Deployment, Hardware, Sicherheit, Dateizugriffe | [betrieb/INDEX.md](betrieb/INDEX.md) |
| **Maps** | Die interaktive Karte: Layer, Quellen-Charta, Design-Brief | [maps/INDEX.md](maps/INDEX.md) |
| **Tutor** | Der Sprach-Tutor — eigenes Projekt in `tutor/`, am Stück rausziehbar | [tutor/INDEX.md](tutor/INDEX.md) |

## Flach geblieben

| Datei | Warum hier |
|---|---|
| [ueberblick.md](ueberblick.md) | Der Einstieg. Was ZENTRALE ist und wo sie gerade steht — gehört in keinen Bereich, sondern davor. |
| [claude_hinweise.md](claude_hinweise.md) | Architektur-Entscheidungen speziell für Claude. Bereichsübergreifend. |

## Pflege

- **Neues Thema** → Datei in den passenden Ordner, Zeile in dessen `INDEX.md`.
  Der Haupt-Index bleibt unangetastet, solange kein neuer *Bereich* entsteht.
- **Neuer Bereich** erst, wenn mehrere Dateien wirklich ein Thema teilen — ein
  Ordner für eine Datei ist Ordnung als Selbstzweck.
- **Verschoben oder umbenannt** → Verweise im ganzen Repo mitziehen, nicht nur
  im Index. Code-Kommentare zeigen auch hierher.
- Inhalte gehören in die Dateien, nicht in einen Index. Ein Index sagt, WO
  etwas steht, nie WAS gilt.
