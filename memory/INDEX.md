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
| **KI** | Wie ZENTRALE denkt: lokal + Cloud, Datei-Gedächtnis (Konzept-Graph seit 2026-08-18 aus), Tools, Erlaubnis-Gate, Sprache, Pläne, Benchmarks | [ki/INDEX.md](ki/INDEX.md) |
| **Werkzeuge** | Was ZENTRALE tut: Kalender, Mail, News, Notizen, Zyklus | [werkzeuge/INDEX.md](werkzeuge/INDEX.md) |
| **System** | Wie der Kern gebaut ist: Architektur, Schichten, Events, Topologie, API, TUI, Tastatur, Handy | [system/INDEX.md](system/INDEX.md) |
| **Hub** | ZENTRALE als Plattform: Hub-Schnittstelle, App-Modell, Werkstatt, Shop, Desk, Bausteine für Apps, Produkt | [hub/INDEX.md](hub/INDEX.md) |
| **Betrieb** | Wie es läuft: Setup, Starten, Deployment, Hardware, Sicherheit, Dateizugriffe | [betrieb/INDEX.md](betrieb/INDEX.md) |
| **Maps** | Die Karte — seit 2026-10-22 eigene App (Repo `zentrale-karte`), hier nur Zeiger | [maps/INDEX.md](maps/INDEX.md) |
| **Tutor** | Der Sprach-Tutor — seit 2026-10-09 eigene App (Repo `language-tutor`); hier nur Zeiger und Hub-Seite | [tutor/INDEX.md](tutor/INDEX.md) |
| **Offen** | Sammelordner für konkrete offene Sachen, eine Datei je Sache (kein Tracker) | [offen/INDEX.md](offen/INDEX.md) |

## Flach geblieben

| Datei | Warum hier |
|---|---|
| **[leitbild.md](leitbild.md)** | **Zuerst lesen.** Wofür es ZENTRALE gibt (das Zuhause, das hört, sieht, spricht, handelt), Szenen, Grundpfeiler, Messlatte, Etappen 1–6. Steht über allem. |
| [ueberblick.md](ueberblick.md) | Der Einstieg. Was ZENTRALE ist und wo sie gerade steht — gehört in keinen Bereich, sondern davor. |
| [claude_hinweise.md](claude_hinweise.md) | Architektur-Entscheidungen speziell für Claude. Bereichsübergreifend. |
| [doku_regeln.md](doku_regeln.md) | Wie eine `memory/`-Datei aufgebaut ist (Stand zuerst, Warum, Historie unten, ein Fakt eine Datei) — gilt für jede Datei hier. |
| [archive/INDEX.md](archive/INDEX.md) | Entfernter, aber wiederverwendbarer Code (wörtlich, mit Herkunft). Kein Bereich — läuft nicht, nur zum Nachschlagen. |

## Pflege

- **Neues Thema** → Datei in den passenden Ordner, Zeile in dessen `INDEX.md`.
  Der Haupt-Index bleibt unangetastet, solange kein neuer *Bereich* entsteht.
- **Neuer Bereich** erst, wenn mehrere Dateien wirklich ein Thema teilen — ein
  Ordner für eine Datei ist Ordnung als Selbstzweck.
- **Verschoben oder umbenannt** → Verweise im ganzen Repo mitziehen, nicht nur
  im Index. Code-Kommentare zeigen auch hierher.
- Inhalte gehören in die Dateien, nicht in einen Index. Ein Index sagt, WO
  etwas steht, nie WAS gilt.
