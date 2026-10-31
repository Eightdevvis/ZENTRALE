# KI — Index

Alles über den denkenden Teil von ZENTRALE: welches Modell wo läuft, wie das
Gedächtnis gebaut ist, wie die KI spricht und hört, und was an Plänen und
Messungen dazu existiert.

| Was du wissen willst | Datei |
|---|---|
| **KI-Bibel — vor jeder Arbeit an der KI lesen.** Wonach die KI gebaut wird: alle Regeln und Tipps (Anthropic, inoffiziell, Sasha) mit Kennung, Quelle und Status; Prompt, Werkzeuge, Recherche, Handeln, Skills, Kontext, Denken, Prüfung, Klassifikatoren, Baustellen | [bibel/README.md](bibel/README.md) |
| **Einstieg.** Überblick: wie der Chat läuft (lokal und Cloud), Architektur-Bild, wo welches Thema steht | [ki_system.md](ki_system.md) |
| Anbieter und Modelle: Cloud-Kern, zweiter Dialekt, Backend-Wahl, Lokal-Regel, Isolations-Invariante, Modell-Parameter, **Fallen der API**, gestoppt = geschätzt gebucht, Preistabelle (Sonnet-5-Preisfehler 26.10.), lokales Modell, Warmup | [anbieter_modelle.md](anbieter_modelle.md) |
| System-Prompt-Reihenfolge, zwei Schienen `klein`/`gross`, Prompt-Cache (statisch vorn, Wechselndes hinten), **Prompt-Budget** (21.000 Zeichen, Wächter-Test), Werkzeug-Beschreibungen als wichtigster Hebel, Nutzer im Prompt | [prompt_aufbau.md](prompt_aufbau.md) |
| Werkzeuge: Liste, Werkzeug-Register (neues Werkzeug anlegen), Status und Belege („Belegt oder gesagt"), Gespräche/Projekte/Ablage/PDF-Werkzeuge | [werkzeuge.md](werkzeuge.md) |
| **Werkzeug-Suche** (seit 2026-10-14, Schalter `werkzeug_suche`, Standard aus): fester Kern + `search_tools`, Anthropic mit `defer_loading`/`tool_reference`, OpenAI hängt an, Freischaltung über Züge hinweg, Gruppen-Tabelle, Skills mit Kurzfassung; Probelauf-Ergebnis, was offen ist | [werkzeug_suche.md](werkzeug_suche.md) |
| Die eine Werkzeug-Schleife: Adapter, Fehler sind keine Antwort, Stoppen, Rundengrenze | [werkzeug_schleife.md](werkzeug_schleife.md) |
| Erlaubnis-Gate und Knopf-Dialog, Geltungsbereiche einmal / Gespräch / immer | [erlaubnis_gate.md](erlaubnis_gate.md) |
| Kalender-Werkzeuge der KI ohne Fallen: Kennungen, genau ein Eintrag, Serien nur mit Zeitraum, nur übernehmen, was Sasha gesagt hat (K-TITEL-WOCHENTAG) | [ki_kalender.md](ki_kalender.md) |
| Sandbox `run_code`: bubblewrap, was abgeschottet ist, Zeitlimit, Arbeitsordner | [sandbox.md](sandbox.md) |
| Skills: drei Stufen, Liste im Kopf, `load_skill`/`propose_skill`/`edit_skill`, Anthropic-Skills | [skills.md](skills.md) |
| Dateien der KI (seit 2026-10-11 nur die Ablage, vorher Nutzerordner Input/Output): Suchen mit Vollständigkeit, `read_file`/`list_files` auf gross, Claude-Skills übernehmen, `unzip` | [nutzerordner.md](nutzerordner.md) |
| Internet-Pipe (`web_search`/`fetch_url`, SearXNG) und Netz-Transparenz | [internet_netz.md](internet_netz.md) |
| Transparenz: Devtools-Terminal, Tool-Calls und Denken im Chat, Ablauf-Protokoll „trace ›" | [transparenz.md](transparenz.md) |
| Chat in der TUI: Slash-Befehle, Markdown im Terminal, Bild-Marker `[[bild: name]]`, Bewertungen (wofür, wo sie liegen) | [chat_bedienung.md](chat_bedienung.md) |
| Konzept-Graph (seit 18.08. aus, seit 31.10. aus dem Code): wie er arbeitete — im Archiv | [../archive/associative_graph/konzept_graph.md](../archive/associative_graph/konzept_graph.md) |
| **Aufbau des KI-Kerns** — welches Modul wofür, wie die Abhängigkeiten laufen, die Umbau-Abschnitte K1–K5 | [kern_aufbau.md](kern_aufbau.md) |
| **Das Gedächtnis nach Themen** (seit 11.10.2026) — Aufbau `themen/<thema>/` im Format von Claudes Datei-Gedächtnis, Index im Kopf, Werkzeuge (anlegen, ergänzen, archivieren), Messreihen unter dem Thema, der Umzug per Skript | [gedaechtnis.md](gedaechtnis.md) |
| **Das Gedächtnis — das Warum.** Notiz/Dossier/Katalog, Nachprüf-Schritt, Skills, Import aus einer anderen KI, für Sasha sichtbar (TUI) — und warum der Konzept-Graph abgelöst wurde | [gedaechtnis_dateien.md](gedaechtnis_dateien.md) |
| Wie die KI hört und spricht: Whisper-STT + TTS als eigene Services, sprachneutral | [audio_system.md](audio_system.md) |
| **Zwischenstand Cloud.** Was der Umstieg gebracht hat, woran es hakte, was dagegen lief, was offen ist | [cloud_bericht.md](cloud_bericht.md) |
| **Plan: Claude-Web-Funktionen übertragen** — Bestand, Ebenen (Gespräch, Gedächtnis, Skill, Werkzeug, Ausgabe), Fallen, Phasen, Entscheidungen; was gebaut ist (Phase 0: Werkzeug-Register, Phase 1: Stoppen, Eingabe, Slash-Befehle, Phase 2: Gespräche, Phase 3: Gedächtnis sichtbar + Suche quer durch Gespräche, Phase 4: Skills — seit 07.10. abends im Claude-Format mit den Anthropic-Skills, Phase 5: Ablage + Anhänge, Phase 6: Projekte, Phase 7: Sandbox für `run_code`; 08.10.: Belege statt „OK", Kalender ohne Fallen, was der Kalender-Kern dafür braucht; Bewertungen good/bad mit Kommentar; Skills pdf und word) | [claude_web_plan.md](claude_web_plan.md) |
| **Browser der KI** — `browser_open` & Co.: Seiten wie das LSF per Text bedienen (Liste mit Nummern, Rahmen, Formulare), Erlaubnis je Host und Gespräch, Sicherheit, Skill `browser` | [browser.md](browser.md); Einrichten: [../betrieb/ki_browser.md](../betrieb/ki_browser.md) |
| **PDF und Word** — Skills `pdf`/`word`: lesen (Seiten, Tabellen, Formularfelder), neue Dateien aus Markdown, zusammenfügen, geänderte Word-Kopie; warum Register-Werkzeuge statt Sandbox, Bibliotheken, Grenzen | [pdf_word.md](pdf_word.md) |
| **Tabellen (Excel/CSV)** — Skill `excel`: `read_xlsx`/`create_xlsx`/`edit_xlsx` über die Ablage, Formeln deutsch → Excel-Standard, Werte rechnet Excel, ändern = ersetzen (Sashas nur nach Ja), Grenzen, openpyxl im Kindprozess | [tabellen.md](tabellen.md) |
| **Projekte** — Anweisungen + Wissensdateien pro Thema, Gespräch → Projekt, Projekt-Block im festen Prompt, `read_project_file`, Sperrliste beim Wissen | [projekte.md](projekte.md) |
| **Gespräche** — Speicherformat (Ordner pro Gespräch, Datei pro Rechner), Ereignisse (nachricht/verwerfen), warum so wegen des Syncs, Titel, Erinnerungen, Suche quer durch alle Gespräche (`search_chats`) | [gespraeche.md](gespraeche.md) |
| **Ablage und Anhänge** — Dokumente der KI (`create_document` …), Sandbox-Dateien, Anhänge per `/anhang` oder `/paste` aus der Zwischenablage (Text, PDF, Bilder nur Cloud); Speicherformat, Fassungen, Sync | [ablage.md](ablage.md) |
| **Die Ablage als Ordner** `~/Zentrale/Ablage` — lesbare Dateien, Einwurf (Sasha legt hinein), ändern/umbenennen/löschen von Hand, Papierkorb, mehrere Rechner, Umzug aus data/ablage | [ablage_ordner.md](ablage_ordner.md) |
| Warum überhaupt in die Cloud — das Entscheidungs-Dokument vom 10.08.2026 (historisch) | [cloud_umstieg_plan.md](cloud_umstieg_plan.md) |
| Warum das Memory so aussieht, wie es aussieht — Historie der Phasen A–G, verworfene Ansätze | [ki_memory_plan.md](ki_memory_plan.md) |
| Wohin die Persönlichkeit soll: vom System-Prompt zum eigenen Modell (Fine-Tuning-Plan) | [ki_personality_plan.md](ki_personality_plan.md) |
| Warum die KI nicht raten soll, sondern nachschaut — Recherche zum Grounding | [grounding_recherche.md](grounding_recherche.md) |
| Dialogischer Action-Scaffold fürs lokale 9b (WIP, geparkt) | [logic_loop_plan.md](logic_loop_plan.md) |
| Gemessenes statt Gefühltes: Benchmark-Protokolle, Sampling, Modell-Vergleiche | [bench_history.md](bench_history.md) |
| **Ehrlichkeit live** — vier Prüfer in Python vor jeder Antwort (gross): Tat gegen Wort mit einer Korrekturrunde, Kennungen, „nicht da“ nur nach vollständiger Suche, offene Zusagen im Kontext-Umschlag; Erledigt-Zeile aus dem Werkzeug-Protokoll; Selbstauskunft über `antwort` (sprachfrei), Auftrags-Abrechnung („offen: …“ unter der Antwort), Kalender-Nachprüfung (Werte ohne Grundlage, Behauptungen gegen Aufrufe), Klassifikator bei Zweifel, Beispiele sammeln; was Anthropic empfiehlt und was wir davon nehmen; Falschtreffer gemessen | [ehrlichkeit_live.md](ehrlichkeit_live.md) |
| **Prüfstand** — arbeitet die Cloud-KI ehrlich und richtig? Fälle aus Sashas Alltag (YAML) über den echten Weg gegen Wegwerf-Daten: Endzustand, Belegpflicht (jede Behauptung mit Zitat), Metriken, verdeckte Fälle, Ist-Stand vom 08.10.; Kosten im eigenen Topf, sparen (früh abbrechen, Richter im Batch, abspielen) | [pruefstand.md](pruefstand.md) |
| **Werkzeug-Erzeuger** — KI-Werkzeuge aus dem Schema einer Quelle (MCP-Form + `x-zentrale`) mit einer Schutzschicht für alle; Kalender als erste Quelle (Phasen, Gruppe, Ebene); wie man eine Quelle oder einen MCP-Server anbindet, was ein sauberer Adapter ist; Einstellung `werkzeuge_erzeugt`; **Anbindungs-Beschreibung** (ein Programm per JSON statt Python anbinden: Format, Stufen, Probefahrt `scripts/anbindung_probe.py`, Beispiel, Kalender über HTTP) | [werkzeug_erzeuger.md](werkzeug_erzeuger.md) |
| **Screen guide (plan, parked since 2026-10-31** until the core extraction inventory is clean) — the AI sees the screen and points where to click: tool `screen` (look/point) + skill `teacher` as app package `screen-guide`, port type `screen`, map with element ids (AT-SPI + local screenshot reading, no picture to the cloud), adapter per surface (X11 first); first use Arduino IDE | [screen_guide_plan.md](screen_guide_plan.md) |
| **Modell-Profile** — eine eigene Umgebung je Modell (Prompt, Werkzeuge, Pflicht-Werkzeug, Zusatz-Prüfer) über der Schiene; das qwen-Profil für den Budget-Rückfall, was half, was nicht, Zahlen, Quellen | [modell_profile.md](modell_profile.md) |
| **Zukunftsvisionen** — Sashas Ideen für später, nicht gebaut: Klassifikator „was mache ich gerade / wie viel freie Zeit“, Gesundheits-/Aktivitäts-/Krankheits-Logbuch, Prüfkette „stört es den Fokus?“ | [zukunftsvisionen.md](zukunftsvisionen.md) |

## Wo sonst noch KI drinsteckt

- Der **Sprach-Tutor** ist seit 2026-10-09 eine eigene App (Repo `language-tutor`) →
  [../tutor/INDEX.md](../tutor/INDEX.md)
- Was die KI im Dashboard **anzeigt** (Kern, Reflexion, Knöpfe) →
  [../system/dashboard.md](../system/dashboard.md)
- Was sie **nicht** sehen darf und was rausgeht →
  [../betrieb/sicherheit.md](../betrieb/sicherheit.md),
  [../betrieb/datei_zugriffe.md](../betrieb/datei_zugriffe.md)
