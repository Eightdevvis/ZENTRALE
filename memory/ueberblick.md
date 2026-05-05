# Projekt-Überblick & Status

## Was ZENTRALE ist

Event-getriebene Zentrale für einen Wand-Monitor auf Raspberry Pi
(Entwicklung läuft parallel auf einem Linux-PC). Sensoren und Zeitgeber
erzeugen Events, der Core verarbeitet sie, das Web-Dashboard zeigt alles
an – **vollständig offline**.

Die KI ist lokal (Ollama + Mistral). Kein Cloud-Zugriff, keine Daten
verlassen das Heimnetz. Die KI hat Lese-Zugriff auf eine fest definierte
Whitelist von Projektdateien (siehe `datei_zugriffe.md`) und eine
persistente Memory über Sessions hinweg.

## Aktueller Stand (2026-05)

| Komponente                                    | Stand                              |
|-----------------------------------------------|------------------------------------|
| Dashboard, Data Collection, Chat              | fertig + getestet                  |
| KI-Memory, Tool-Use                           | fertig + getestet                  |
| Mandarin-Tutor                                | implementiert, Audio noch nicht voll getestet |
| Echter PIR-Sensor + GPIO                      | nicht angebunden – `sensors.py` simuliert via Tastatur |

## Geplante Features (Roadmap)

- Echter GPIO-Support für Pi (RPi.GPIO, kein sudo nötig wenn User in
  `gpio`-Gruppe ist)
- PIR-Sensor (HC-SR501) an GPIO für echte Motion Detection
- Nachrichten-Zusammenfassungen via RSS
- Anbindung an das hauseigene Security-System
- Multi-Monitor Support

## Verwandt

- Architektur-Details: `architektur.md`
- Was funktioniert wie: jeweils das Thema-File
