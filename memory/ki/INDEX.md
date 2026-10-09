# KI — Index

Alles über den denkenden Teil von ZENTRALE: welches Modell wo läuft, wie das
Gedächtnis gebaut ist, wie die KI spricht und hört, und was an Plänen und
Messungen dazu existiert.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Wie der Chat läuft: lokal (Ollama) und Cloud, Tools, Erlaubnis-Gate, System-Prompt-Reihenfolge, Prompt-Cache, Backend-Wahl, Bewertungen der Antworten (wofür, wo sie liegen) | [ki_system.md](ki_system.md) |

| **Einstieg.** Wie der Chat läuft: lokal (Ollama) und Cloud, Tools, Erlaubnis-Gate, Status und Belege in Werkzeug-Ergebnissen, System-Prompt-Reihenfolge, Prompt-Cache, Backend-Wahl | [ki_system.md](ki_system.md) |
| **Aufbau des KI-Kerns** — welches Modul wofür, wie die Abhängigkeiten laufen, die Umbau-Abschnitte K1–K5 | [kern_aufbau.md](kern_aufbau.md) |
| **Das Gedächtnis.** Steckbrief, Ziele, Dossiers, Tagebuch, Messreihen, Skills, für Sasha sichtbar und änderbar (TUI) — und warum der Konzept-Graph abgelöst wurde | [gedaechtnis_dateien.md](gedaechtnis_dateien.md) |
| Wie die KI hört und spricht: Whisper-STT + TTS als eigene Services, sprachneutral | [audio_system.md](audio_system.md) |
| **Zwischenstand Cloud.** Was der Umstieg gebracht hat, woran es hakte, was dagegen lief, was offen ist | [cloud_bericht.md](cloud_bericht.md) |

| **Plan: Claude-Web-Funktionen übertragen** — Bestand, Ebenen (Gespräch, Gedächtnis, Skill, Werkzeug, Ausgabe), Fallen, Phasen, Entscheidungen; was gebaut ist (Phase 0: Werkzeug-Register, Phase 1: Stoppen, Eingabe, Slash-Befehle, Phase 2: Gespräche, Phase 3: Gedächtnis sichtbar + Suche quer durch Gespräche, Phase 4: Skills — seit 07.10. abends im Claude-Format mit den Anthropic-Skills, Phase 5: Ablage + Anhänge, Phase 6: Projekte, Phase 7: Sandbox für `run_code`; 08.10.: Belege statt „OK", Kalender ohne Fallen, was der Kalender-Kern dafür braucht; Bewertungen good/bad mit Kommentar; Skills pdf und word) | [claude_web_plan.md](claude_web_plan.md) |
| **Browser der KI** — `browser_open` & Co.: Seiten wie das LSF per Text bedienen (Liste mit Nummern, Rahmen, Formulare), Erlaubnis je Host und Gespräch, Sicherheit, Skill `browser` | [ki_system.md](ki_system.md) Abschnitt „Browser"; Einrichten: [../betrieb/ki_browser.md](../betrieb/ki_browser.md) |
| **PDF und Word** — Skills `pdf`/`word`: lesen (Seiten, Tabellen, Formularfelder), neue Dateien aus Markdown, zusammenfügen, geänderte Word-Kopie; warum Register-Werkzeuge statt Sandbox, Bibliotheken, Grenzen | [pdf_word.md](pdf_word.md) |
| **Projekte** — Anweisungen + Wissensdateien pro Thema, Gespräch → Projekt, Projekt-Block im festen Prompt, `read_project_file`, Sperrliste beim Wissen | [projekte.md](projekte.md) |
| **Gespräche** — Speicherformat (Ordner pro Gespräch, Datei pro Rechner), Ereignisse (nachricht/verwerfen), warum so wegen des Syncs, Titel, Erinnerungen, Suche quer durch alle Gespräche (`search_chats`) | [gespraeche.md](gespraeche.md) |
| **Ablage und Anhänge** — Dokumente der KI (`create_document` …), Sandbox-Dateien, Anhänge per `/anhang` oder `/paste` aus der Zwischenablage (Text, PDF, Bilder nur Cloud); Speicherformat, Fassungen, Sync | [ablage.md](ablage.md) |
| **Gespräche** — Speicherformat (Ordner pro Gespräch, Datei pro Rechner), Ereignisse (nachricht/verwerfen), warum so wegen des Syncs, Titel, Erinnerungen | [gespraeche.md](gespraeche.md) |
| Warum überhaupt in die Cloud — das Entscheidungs-Dokument vom 10.08.2026 (historisch) | [cloud_umstieg_plan.md](cloud_umstieg_plan.md) |
| Warum das Memory so aussieht, wie es aussieht — Historie der Phasen A–G, verworfene Ansätze | [ki_memory_plan.md](ki_memory_plan.md) |
| Wohin die Persönlichkeit soll: vom System-Prompt zum eigenen Modell (Fine-Tuning-Plan) | [ki_personality_plan.md](ki_personality_plan.md) |
| Warum die KI nicht raten soll, sondern nachschaut — Recherche zum Grounding | [grounding_recherche.md](grounding_recherche.md) |
| Dialogischer Action-Scaffold fürs lokale 9b (WIP, geparkt) | [logic_loop_plan.md](logic_loop_plan.md) |
| Gemessenes statt Gefühltes: Benchmark-Protokolle, Sampling, Modell-Vergleiche | [bench_history.md](bench_history.md) |
| **Ehrlichkeit live** — vier Prüfer in Python vor jeder Antwort (gross): Tat gegen Wort mit einer Korrekturrunde, Kennungen, „nicht da“ nur nach vollständiger Suche, offene Zusagen im Kontext-Umschlag; Erledigt-Zeile aus dem Werkzeug-Protokoll; was Anthropic empfiehlt und was wir davon nehmen; Falschtreffer gemessen | [ehrlichkeit_live.md](ehrlichkeit_live.md) |
| **Prüfstand** — arbeitet die Cloud-KI ehrlich und richtig? Fälle aus Sashas Alltag (YAML) über den echten Weg gegen Wegwerf-Daten: Endzustand, Belegpflicht (jede Behauptung mit Zitat), Metriken, verdeckte Fälle, Ist-Stand vom 08.10.; Kosten im eigenen Topf, sparen (früh abbrechen, Richter im Batch, abspielen) | [pruefstand.md](pruefstand.md) |

## Wo sonst noch KI drinsteckt

- Der **Sprach-Tutor** ist ein eigenes Projekt mit eigenem Ordner →
  [../tutor/INDEX.md](../tutor/INDEX.md)
- Was die KI im Dashboard **anzeigt** (Kern, Reflexion, Knöpfe) →
  [../system/dashboard.md](../system/dashboard.md)
- Was sie **nicht** sehen darf und was rausgeht →
  [../betrieb/sicherheit.md](../betrieb/sicherheit.md),
  [../betrieb/datei_zugriffe.md](../betrieb/datei_zugriffe.md)
