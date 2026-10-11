# Projekt-Überblick & Status

**Stand 2026-10-11:** ZENTRALE ist ein event-getriebener Assistent für
Sashas Wohnung und wird zum **Hub**: eine anfangs leere Plattform, in die
Module als Apps geladen werden (Fahrplan unten, Bauplan
`memory/hub/hub_bauplan.md`). Der **PC** ist der Kern (Flask + Event-Loop,
Whisper, TTS, Ollama; schläft nach Plan, Wecken per Router/Pi —
`memory/betrieb/wachplan.md`, Umbau zum Gehirn ohne Bildschirm:
`memory/system/heimnetz.md`), der **Pi** an der Wand ist Aussenposten
(Sensor-Bridge mit PIR, Kiosk mit dem Zimmer des Tutors als Wandbild, TUI
dahinter), der **Laptop** hängt per SSH-Tunnel dran. Andere Geräte brauchen
seit 08.10. einen Zugangsschlüssel (`memory/betrieb/zugang.md`). Die Front ist
die **TUI**; die Browser-Fronten sind archiviert. Der Kern-Chat denkt **in
der Cloud** (Opt-in, Tools lokal, hartes Erlaubnis-Gate für Schreibendes) und
hat seit 07.10. die Claude-Web-Funktionen (`memory/ki/claude_web_plan.md`);
das Gedächtnis sind Markdown-Dateien, erinnert wird über den Takt.

Seit Oktober neu:
- **Tutor** — seit 09.10. eigene App im Repo `language-tutor`, erste App nach
  dem Hub-Bauplan (`memory/tutor/INDEX.md`).
- **Werkstatt** — drittes Rad „erschaffen", der Schmied baut eigene Apps aus
  Vorlagen (`memory/hub/werkstatt.md`).
- **Shop** — Schaufenster, alles kostenlos (`memory/hub/shop.md`).
- **Desk** — unendliche Fläche mit Zetteln und Schnüren, ein Baustein, keine
  App (`memory/hub/desk_view.md`).
- **ZEN-MOBILE** — Handy-App (Flutter, `mobile/`), noch nicht auf dem Gerät
  gelaufen (`memory/system/zen_mobile.md`).

Werkzeuge: Kalender, Mail (Outlook live), News (geparkt), Notizen,
Listen/Fokus, Graphen, Zyklus, Karte, Klavier, Morgenblick. „Offline by
default" gilt nur noch für das, was nicht bewusst nach draußen darf
(`memory/betrieb/sicherheit.md`).

## Was ZENTRALE ist

Event-getriebene Zentrale für einen Wand-Monitor auf Raspberry Pi, gerechnet
auf einem Linux-PC. Sensoren und Zeitgeber erzeugen Events, der Core
verarbeitet sie, die Fronten zeigen alles an. Zwei Dinge verlassen das Haus
nur bewusst: die gegatete Internet-Pipe der KI (Tools `web_search`/`fetch_url`,
jeder Call per Knopf bestätigt, sichtbar im Internet-Monitor) und der
Cloud-Kern als Opt-in (`memory/ki/anbieter_modelle.md`). Die KI hat Lese-Zugriff auf eine
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
| Der Tutor (eigenes Repo) | `memory/tutor/INDEX.md` |
| Regeln für diese Doku | `memory/doku_regeln.md` |

## Fahrplan (Sasha, Stand 2026-10-09)

**Leitbild:** ZENTRALE wird ein Hub wie ein App-Store, anfangs leer.
Kalender, Mail, Assistent, Tutor … sind Apps, die nur über die
Hub-Schnittstelle reden. Reihenfolge laut 09.10.:

1. Hub-Bauplan als Dokument — ✅ `memory/hub/hub_bauplan.md`
2. Tutor als erste App in eigenem Repo — ✅ 09.10., Repo `language-tutor`
3. Übrige Module nacheinander (Kalender, Notizen/Listen, Mail, Karte,
   Morgenblick, Assistent zuletzt) — offen, Reihenfolge in
   `memory/hub/hub_bauplan.md` → „Umzug der heutigen Module"

**Reihenfolge der Arbeit (08.10.):**

1. **Must-haves im Assistenten** — Claude-Web-Funktionen ✅ (Phasen 0–7,
   07.10.), Morgenblick ✅, Erinnerungen-Import (Skill `import-memory`) ✅,
   Bewertungen good/bad ✅ (alle 08.10., `memory/ki/claude_web_plan.md`).
2. **Sprach-Tutor funktional** — läuft als eigene App; weiterer Stand im
   Tutor-Repo (`docs/INDEX.md`).
3. **Mobile-App ZEN-MOBILE** — am 08.10. abends vorgezogen; ein Gedächtnis
   überall. Vorbedingung Zugangsschutz ✅ (`memory/betrieb/zugang.md`, Vorgabe
   noch „melden", nicht „an"). App gebaut, aber: Mitte nicht angeschlossen,
   kein Gerätelauf (`memory/system/zen_mobile.md` → „Offen").
   Ziel (Sasha, 11.10.): das Handy hat **dasselbe Gedächtnis wie der PC**.
   Gebaut als eigener Knoten (spricht Claude selbst, gleicht über die Mitte
   ab), weil der PC nach Plan schläft; die frühere Idee „dünner Client der
   Backend-API" ist damit verworfen.
4. **ZENTRALE Code** — nur Ausblick, nicht bauen
   (`memory/ki/claude_web_plan.md` §6b).

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
- **2026-09-14** — Prioritäten (bis zum Fahrplan vom 08.10.): 1. Pi↔PC-Pipe
  ohne Knöpfe (erledigt: Wandmonitor bleibt an, Zimmer als Wandbild, Mikro
  offen, PIR; Auto-Suspend war ein COSMIC-Setting), 2. Tutor funktional
  (Gate weg, Anwesenheit über Mikro/PIR), 3. KI-Assistent. Die Pipe von
  draußen zum PC war ausdrücklich später.
- **2026-10** — Claude-Web-Funktionen im Assistenten (07.10.), Zugangsschlüssel
  und ZEN-MOBILE (08.10.), Hub-Bauplan und Tutor-Auszug ins Repo
  `language-tutor` (09.10.), Desk, Werkstatt, Shop (10.10.).
