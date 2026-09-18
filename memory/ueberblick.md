# Projekt-Überblick & Status

**Stand 2026-09-18:** ZENTRALE ist ein event-getriebener Assistent für
Sashas Wohnung: der **PC** ist der Kern (Flask + Event-Loop, Whisper, TTS,
Ollama; daheim an, nachts/unterwegs Suspend, Wecken über den Pi —
`memory/betrieb/wachplan.md`), der **Pi** an der Wand ist Aussenposten (Sensor-Bridge
mit PIR, Kiosk mit dem **Persona-Zimmer** des Sprach-Tutors als Wandbild,
TUI dahinter), der **Laptop** hängt per SSH-Tunnel dran. Die Front, an der
gearbeitet wird, ist die **TUI**; die Browser-Fronten sind aufgegeben.
Der Kern-Chat denkt seit 2026-08 **in der Cloud** (Opt-in, Tools laufen
lokal, hartes Erlaubnis-Gate für Schreibendes), das Gedächtnis sind
Markdown-Dateien, die Uhr trägt Sasha am Handgelenk (Morgen-Messenger
gelöscht), erinnert wird über den Takt. Der **Tutor** (eigenes Projekt in
`tutor/`, Bauplan mit Drift-Test) läuft mit drei Sprachen (es/zh/de), ohne
Gate, ein Spielstand je Sprache. Werkzeuge: Kalender, Mail (Outlook live),
News (geparkt am schwachen lokalen Modell), Notizen, Listen/Fokus, Graphen,
Zyklus, Karte, Klavier. „Offline by default" gilt nur noch für das, was nicht
bewusst nach draußen darf (`memory/betrieb/sicherheit.md`). Prioritäten unten
(2026-09-14) sind verbindlich.

## Was ZENTRALE ist

Event-getriebene Zentrale für einen Wand-Monitor auf Raspberry Pi, gerechnet
auf einem Linux-PC. Sensoren und Zeitgeber erzeugen Events, der Core
verarbeitet sie, die Fronten zeigen alles an. Zwei Dinge verlassen das Haus
nur bewusst: die gegatete Internet-Pipe der KI (Tools `web_search`/`fetch_url`,
jeder Call per Knopf bestätigt, sichtbar im Internet-Monitor) und der
Cloud-Kern als Opt-in (`memory/ki/ki_system.md`). Die KI hat Lese-Zugriff auf eine
Whitelist von Dateien (`memory/betrieb/datei_zugriffe.md`) und ein persistentes
Gedächtnis (`memory/ki/gedaechtnis_dateien.md`).

## Wo was steht

| Frage | Bereich |
|---|---|
| Wie starten, ausrollen, absichern | `memory/betrieb/INDEX.md` |
| Wie gebaut, wer läuft wo, Routen | `memory/system/INDEX.md` |
| Wie die KI denkt und sich erinnert | `memory/ki/INDEX.md` |
| Kalender, Mail, News, Notizen, Zyklus | `memory/werkzeuge/INDEX.md` |
| Die Karte | `memory/maps/INDEX.md` |
| Der Tutor | `memory/tutor/INDEX.md` (Struktur: `memory/tutor/bauplan.md`) |
| Regeln für diese Doku | `memory/doku_regeln.md` |

## Prioritäten (Stand 2026-09-14) — Reihenfolge ist verbindlich

Die Verkabelung steht komplett: Monitor an der Wand, Pi am LAN, PC als
Kern zuhause (`memory/betrieb/wachplan.md`). Was fehlt, ist **Nutzbarkeit**
— zu viele Blockaden zwischen »ich gehe am Pi vorbei« und »ZENTRALE spricht
mich an«. Ziel: fertig werden, schnell, in dieser Reihenfolge:

1. **Pi↔PC-Pipe stabil aufspannen.** Sasha geht vorbei, ZENTRALE kann ihn
   ansprechen und er sie — ohne Knöpfe. Blocker am 09-14: Pi-Bildschirm geht
   schnell aus; PC schläft dauernd ein; KI nur per Tastendruck, Voice nur per
   zweitem Tastendruck; die Tastatur liegt auf dem Boden (Monitor + Mikro
   oben) → entweder Knöpfe hoch oder KI dauerhaft freischalten. Daheim
   bleibt der PC durchgehend an; nachts schläft er mit. Seither erledigt:
   Wandmonitor bleibt an (b8c25cb), Zimmer als Wandbild, Mikro immer offen,
   PIR an der Bridge; der Auto-Suspend am PC ist ein COSMIC-Setting
   (`memory/betrieb/wachplan.md`, erster Schritt).
2. **Tutor-Kerngedanke aufstellen und funktional machen.** Der Tutor hängt an
   der Wand, merkt wenn Sasha da ist, spricht ihn von sich aus in der
   Zielsprache an — organisches Lernen nebenbei, er lässt einen nie ganz in
   Ruhe. Am 09-14: nur per Knopf, dann Menü, dann Drill, muss erst
   freigeschaltet werden, sieht insgesamt schlecht aus. Seither: Gate weg,
   Anwesenheit über Mikro/PIR, Skill `no_entiendo` (loggt), Bauplan —
   der Ausbau steht in `memory/tutor/naturalisierung.md`. **Wichtiger als der
   Assistent.**
3. **KI-Assistent.** Memory-Struktur ist überkompliziert und kaputt, die
   Tests dazu taugten nichts, Tool-Calls inkonsistent. Kommt danach.

**Ausdrücklich später:** die Pipe von draußen zum PC (Router, WAN-Zugang,
Wecken von unterwegs) — erst wenn der Router da ist **und** der Tutor läuft.

## Historie

- **2026-05** — Pi als Core gedacht, zu schwach für die KI-Last → Migration
  auf den PC, Pi wird Kiosk + Sensor-Bridge (`memory/system/topologie.md`).
- **2026-06** — Monolith-Dashboard, Konzept-Graph, Bild-Marker,
  Internet-Pipe mit Gate, Kalender + Alarm, News-System, Mail-Triage,
  Kassetten (monolith/laptop/tui), Karte, Klavier.
- **2026-07** — Tutor als Persona-Portal, eigenes Projekt, Sprach-Framework,
  Drill + Spiel, Zimmer; Listen/Fokus, Notizen; Theme-Kopplung der Umgebung.
- **2026-08** — Cloud-Kern, Datei-Gedächtnis, Takt, Anwesenheit,
  Systemeinheit; Arbeit nur noch an der TUI.
- **2026-09** — Aussenposten-Paket für den Pi, Spielstände, gemalte Puppe,
  Wachplan statt Always-on, Morgen-Messenger gelöscht (Smartwatch), Gate
  abgeschafft, Zimmer als Wandbild, PIR, ein Stand = eine Sprache, Bauplan +
  Drift-Test, Lena (de). Die alte Roadmap („echter GPIO", „RSS-News") ist
  damit erledigt; offen aus ihr: Anbindung ans Security-System,
  Multi-Monitor — beides nicht priorisiert.
