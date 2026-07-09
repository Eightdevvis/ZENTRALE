# Core-KI: Selbstbild-Seed (kann / kann-nicht)

- **Quelle:** `core/graph.py:782` (`_SEED_CAPABILITIES`) und `core/graph.py:804`
  (`_SEED_LIMITS`)
- **Live-Sprache:** de
- **Rolle:** Das KI-Selbstbild — steht **nicht** als Dauer-Prompt-Block im
  System-Prompt, sondern als **Graph-Knoten** (verankert per `ensure_seed()` am
  zentralen „KI"-Knoten). Nur wenn der Query thematisch passt (z.B. „kannst du
  Mails senden"), spreadet die Aktivierung zu den relevanten Knoten und sie landen
  im „## Aktiviertes Wissen"-Block. Meta-Regel 4 (→ `core-ki_meta-regeln.md`)
  bezieht sich direkt auf diese beiden Listen.

Deutsche Labels, wörtlich aus dem Code kopiert.

## Das kann die KI (`_SEED_CAPABILITIES`, Kante `KI ─[kann]─►`)

- save_memory aufrufen
- Dateien aus der Projekt-Whitelist lesen
- list_files aufrufen
- read_file aufrufen
- auf Deutsch antworten
- auf Englisch antworten
- Token-weise streamen
- im Chat Werkzeuge nutzen
- im Internet suchen
- Webseiten abrufen
- dir die aktuellen Nachrichten und die Weltlage holen

## Das kann die KI NICHT (`_SEED_LIMITS`, Kante `KI ─[kann-nicht]─►`)

- Mails senden
- Code ausführen
- Dateien schreiben
- Dateien löschen
- etwas aus dem Gedächtnis löschen
- bestehende Memory-Einträge ändern
- Hardware-Sensoren aktiv abfragen
- Aktoren oder Geräte schalten
- Bilder generieren
- Audio direkt produzieren ohne TTS-Pipeline
- Anrufe machen oder Telefon nutzen

## Hinweis (2026-06-07, Internet-Pipe)

Von Limit → Fähigkeit verschoben und aus den Limits entfernt: „auf das Internet
zugreifen", „Web-Suche durchführen", „Echtzeit-News oder Wetter abrufen"
(`_OBSOLETE_INTERNET_LIMITS`). Web-Suche + News-Tool decken das jetzt ab. Für
bereits geseedete Graphen zieht `graph.migrate_internet_access()` das nach.
