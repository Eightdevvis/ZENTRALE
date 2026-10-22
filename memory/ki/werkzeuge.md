# Werkzeuge der KI — Liste, Register, Belege

**Stand 2026-10-11:** Der Kern spricht ein englisches Werkzeug-Vokabular; alle
Werkzeuge stehen im Werkzeug-Register (`core/werkzeug_register.py`), aus dem
beide Schienen, das Erlaubnis-Gate und die Verteilung ihre Listen holen.
Werkzeuge laufen **immer lokal**, nur die Entscheidung wandert in die Cloud.
Jedes Ergebnis beginnt mit `[ergebnis: ok|fehlgeschlagen|keine_antwort|abgelehnt]`;
schreibende Werkzeuge lesen nach und geben den echten Stand als Beleg zurück.
Neue Werkzeuge nur auf `gross`, hinten ans Register.
Wonach Werkzeuge gebaut werden (Beschreibungen, Fehlertexte, Ergebnisse):
KI-Bibel [bibel/werkzeuge.md](bibel/werkzeuge.md).

**Warum:** Ehrlichkeit war eine Bitte im Prompt und ist jetzt Bauweise
(„Belegt oder gesagt"); ein Register statt verstreuter Listen, damit Schiene,
Gate und Ausführer nicht auseinanderlaufen. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen). Eigene Dateien haben:
[ki_kalender.md](ki_kalender.md), [sandbox.md](sandbox.md),
[skills.md](skills.md), [nutzerordner.md](nutzerordner.md),
[browser.md](browser.md), [internet_netz.md](internet_netz.md),
[erlaubnis_gate.md](erlaubnis_gate.md),
[werkzeug_schleife.md](werkzeug_schleife.md).

## Tool-Use

Das Modell kann Tools "aufrufen" – ZENTRALE führt sie aus und schickt
das Ergebnis zurück in den Kontext. Funktioniert mit jedem Tool-Use-
fähigen Ollama-Modell; Default `qwen3.5:9b` (Env `OLLAMA_MODEL`).

Der Kern spricht **ein** Vokabular (englisch, Spalte „kanonisch"). Wie eine
Schiene ihr Tool nennt, ist ihre Sache — `profil.kanonisch()` übersetzt darauf
und nimmt beide Schreibweisen an (siehe „Zwei Schienen" in [prompt_aufbau.md](prompt_aufbau.md)).

| kanonisch | in `klein` | Funktion |
|---|---|---|
| `read_file`   | =            | `klein`: Datei aus der Whitelist bzw. ~/codicus lesen. `gross` (seit 2026-10-11): ein Dokument der Ablage per id oder genauem Titel ([nutzerordner.md](nutzerordner.md)) |
| `read_series` | nur `gross`  | Messreihen lesen (Liste mit letztem Wert, oder Werte einer Reihe, Standard letzte 30 Tage) — ersetzt `read_file` auf `data/<reihe>.json` |
| `list_files`  | =            | `klein`: Gesamtliste der lesbaren Dateien (höchstens 300, wie bisher). `gross` (seit 2026-10-11): die Ablage wie ls, `papierkorb=true` den Papierkorb |
| `find_files`  | nur `gross`  | Dokumente der Ablage nach Titel suchen, wie find — mit Vollständigkeits-Angabe (s. [nutzerordner.md](nutzerordner.md)) |
| `search_files` | nur `gross` | Text in den Dokumenten der Ablage (auch PDF/Word/Excel), wie grep — mit Vollständigkeits-Angabe |
| `import_skill` | nur `gross` | Claude-Skill(s) aus einer Zip der Ablage übernehmen, gegatet |
| `unzip` | nur `gross` | Eine Zip der Ablage auspacken: jede Datei ein Dokument (gegatet), `ansehen=true` zeigt nur den Inhalt (frei) |
| `replace_document`, `trash_document`, `restore_document` | nur `gross` | Ablage: ersetzen (alt in den Papierkorb), wegräumen, zurückholen — KI-Dokumente frei, Sashas jedes Mal gefragt ([ablage.md](ablage.md); ersetzt `remove_input`, 2026-10-11) |
| `read_xlsx`, `create_xlsx`, `edit_xlsx` | nur `gross` | Tabellen (Excel/CSV) in der Ablage ([tabellen.md](tabellen.md)) |
| `read_calendar` / `add_calendar_*` / `edit_calendar_routine` / `delete_calendar_entry` | = | Kalender lesen/schreiben/löschen (s. `memory/werkzeuge/kalender_system.md`); auf `gross` mit Kennungen, Ende/Ort, `nur_am` und Pflicht-Zeitraum `von`/`bis` bei Routinen, `typ` deadline + `vorwarnung` (s. [ki_kalender.md](ki_kalender.md)) |
| `edit_calendar_entry` | nur `gross` | Einen Einzeltermin ändern, nur genannte Felder (gegatet) |
| `read_calendar_warnings` | nur `gross` | Die Kalender-Warnungen frisch, dieselben wie Sashas ⚠ |
| `web_search`  | `web_suche`  | Im Internet suchen (gegatet, s. [internet_netz.md](internet_netz.md)) |
| `fetch_url`   | `hole_url`   | Webseite laden + Text holen (gegatet) |
| `read_news`   | `lies_news`  | Weltpolitik-Briefing lesen (s. `memory/werkzeuge/news_system.md`) |
| `read_mail`   | `lies_mail`  | Stand der Mail-Triage (s. `memory/werkzeuge/mail_system.md`) |
| `ask_choice`  | `frage_knopf`| Sasha eine Frage mit Knöpfen stellen (s. [erlaubnis_gate.md](erlaubnis_gate.md)) |
| `antwort`     | = | Finale Antwort über den Tool-Kanal — auf `klein` Framing-Effekt (9B-Krücke), auf `gross` seit 2026-10-10 mit **Selbstauskunft** (`erledigt`, `fragt_erlaubnis`, `schiebt_auf`, `ungeprueft`, `auftrag`, `nicht_gefunden`; s. [ehrlichkeit_live.md](ehrlichkeit_live.md)) |
| `run_code`    | nur `gross`  | Python/Shell abgeschottet ausführen, jeder Lauf gegatet (s. [sandbox.md](sandbox.md)) |
| `load_skill` / `propose_skill` / `edit_skill` | nur `gross` | Skill-Anleitung (oder mit `datei` eine Datei daraus) holen; neuen vorschlagen bzw. bestehenden umschreiben (beide gegatet) (s. [skills.md](skills.md)) |
| `search_chats` / `read_chat` | nur `gross` | Frühere Gespräche durchsuchen/nachlesen; `search_chats` mit `projekt` nur in einem Projekt (s. „Frühere Gespräche") |
| `read_project_file` | nur `gross` | Wissensdatei des Projekts dieses Gesprächs lesen (s. „Projekte") |
| `browser_open` / `browser_click` / `browser_type` / `browser_find` / `browser_read` / `browser_back` / `browser_close` / `browser_screenshot` | nur `gross` | Echter Browser ohne Fenster, über Text bedient; gefragt einmal je Host und Gespräch (s. [browser.md](browser.md)) |

Gegen das Erlaubnis-Gate wird **nie** direkt geprüft, sondern über
`erlaubnis.braucht_erlaubnis()` — die normalisiert erst. Ein Schreib-Tool, das unter
seinem Alias am Gate vorbeirutscht, würde ungefragt in den Kalender schreiben,
und der Fehler wäre völlig lautlos.

Tool-Calls werden streng ans Dashboard-Terminal geloggt
(`AI → TOOL read_file(...)` / `AI ← TOOL read_file → ok`). Sichtbar
machen ob die KI ein Tool wirklich gerufen hat oder es nur behauptet.

### Das Werkzeug-Register — `core/werkzeug_register.py` (seit 2026-10-07)

Ein Eintrag pro Werkzeug: kanonischer Name, Parameter-Schema (für beide
Schienen gleich), Beschreibung je Schiene (`klein`/`gross`, `None` = dort
nicht angeboten), alter `klein_name`, Erlaubnis-Regel (`False`/`True`/
`f(args)`) mit Frage-Text, `terminal`. Die Reihenfolge der Einträge ist die
Reihenfolge im Prompt. `profil/klein.py`, `profil/gross.py` (`TOOLS`,
`TERMINAL`), `profil.ALIASE`/`kanonisch`, `erlaubnis` und
`ki_werkzeuge._verteilen` holen sich alles von dort. Die Ausführer melden
sich aus `ki_werkzeuge.py` mit `@ausfuehrer("name")` an — so herum, weil
`ki_werkzeuge` im Register nachschlägt und ein Import in die andere Richtung
ein Kreis wäre.

**Ein neues Werkzeug anlegen:**
1. Eintrag in `WERKZEUGE` in `core/werkzeug_register.py`, **hinten** an
   (Umsortieren bricht den Anthropic-Cache). Neue Werkzeuge nur mit
   `gross=` — `klein=None`, das qwen bekommt nur Gemessenes.
2. Schreibt, löscht, geht ins Netz oder kostet Geld → `erlaubnis=True` (oder
   eine Funktion der Argumente) **und** eine eigene `frage=`.
3. Die Funktion in `core/ki_werkzeuge.py` mit `@ausfuehrer("name")`.
   Verändert sie Sashas Daten: `schreibt=True` und `beweis=` (was danach
   nachgelesen wird), und die Funktion gibt einen `werkzeug_befund.Befund`
   mit `beleg` zurück (s. „Belegt oder gesagt"). `tests/test_werkzeug_belege.py`
   führt jedes schreibende Werkzeug einmal echt aus — ein neues muss dort in
   `AUFRUFE`.
4. Auf gross: in `core/werkzeug_gruppen.py` eintragen — in `IMMER` (immer
   geladen) oder in eine Gruppe von `GRUPPEN` (erst nach `search_tools`,
   wenn die Werkzeug-Suche an ist; [werkzeug_suche.md](werkzeug_suche.md)).
   `tests/test_werkzeug_suche.py` meldet ein Werkzeug ohne beides.
5. Schnappschuss neu ziehen (`venv/bin/python tests/test_werkzeug_schnappschuss.py --neu`)
   und den Diff ansehen: nur das neue Werkzeug darf dazukommen.
   `tests/test_werkzeug_register.py` meldet Waisen in beide Richtungen.
6. Die gross-Beschreibung nach der KI-Bibel ([bibel/werkzeuge.md](bibel/werkzeuge.md)):
   3–4 Sätze — was, wann ja, wann nein, was es nicht liefert; normale
   Schreibung statt Großbuchstaben (`tests/test_werkzeug_texte.py` prüft
   das). Nennt sie ein Werkzeug, das nicht in `IMMER` steht, und ist das
   Werkzeug selbst in `IMMER`: Feld `mit_suche` mit einem Satz „… holst du
   vorher mit search_tools" (hängt nur mit eingeschalteter Werkzeug-Suche an).

**Seit 2026-10-22** (KI-Bibel W-05, W-08): Feld `mit_suche` (siehe 6.) und
Aufruf-Beispiele `input_examples` für wenige Werkzeuge mit typischen
Fehlgriffen in `core/werkzeug_beispiele.py` (read_calendar,
add_calendar_routine, edit_calendar_routine). Sie gehen nur auf gross über
den Anthropic-Weg mit (`cloud._to_anthropic_tools(beispiele=True)`), nur an
Werkzeuge ohne `defer_loading` und nur, wenn sie gegen das Schema des
laufenden Prozesses bestehen; OpenAI-kompatible Wege bekommen sie nicht.

### Belegt oder gesagt — Status und Belege (seit 2026-10-08)

Anlass: Sashas Kalender-Testlauf am 08.10. (Gespräch `20261008-132404`). Die
KI meldete „Geige donnerstags 18:10–19:00" als erledigt — gespeichert war
18:10 ohne Ende, das Werkzeug hatte nur „OK, Routine eingetragen" gesagt. Sie
gab ein Ferienende aus dem Vorwissen als Suchergebnis aus, sagte „ohne Login
komm ich nicht tiefer" (geraten) und „die Warnungen sollten verschwinden"
(nie geprüft). Ehrlichkeit war eine Bitte im Prompt; jetzt ist sie Bauweise:

- **Kopfzeile.** Jedes Werkzeug-Ergebnis an die KI beginnt mit
  `[ergebnis: ok|fehlgeschlagen|keine_antwort|abgelehnt]`, gesetzt
  in `werkzeug_schleife.run_tool` (`core/werkzeug_befund.py`). Ein Ausführer
  sagt den Status mit einem `Befund` (ein `str` mit `status` und `beleg`);
  alte Text-Ausführer werden an „[Fehler …]" erkannt. Nie „None": ein leeres
  Ergebnis heißt `fehlgeschlagen`. Der Tutor (fremdes Tool-Set) bekommt
  keinen Kopf. Das `werkzeug`-Event „fertig" trägt `status` mit.
- **Belege.** Jedes schreibende Werkzeug (Register: `schreibt`, `beweis`)
  liest nach dem Schreiben nach und gibt zurück, was **wirklich** dasteht —
  Kalender (Zeit von–bis, Ort, Wiederholung, Pausen, Warnungen dazu),
  Notizen („steht im Tagebuch …"), Messkurven, Skills, Ablage. Steht es nicht
  da: `fehlgeschlagen` und „melde keinen Erfolg".
- **Zwei Ausgänge, feste Codes** (seit 2026-10-09). Ein schreibendes
  Werkzeug ist ERLEDIGT (`ok`, Satz aus dem nachgelesenen Stand: „Notiz in
  den Hausregeln GESPEICHERT — steht jetzt drin: …") oder ABGEBROCHEN
  (`fehlgeschlagen`, nichts geändert): „<was> ABGEBROCHEN – nichts
  eingetragen. Fehler K-ENDE-VOR-BEGINN: …". `teilweise` gibt es nicht mehr
  — es hieß, das Werkzeug tat etwas anderes als verlangt. Erst prüfen, dann
  schreiben, dann nachlesen; steht es nicht so da, wird der alte Stand
  zurückgelegt (`core/schreib_sicherung.py`; der Kalender-Kern kann das per
  Kennung selbst). Codes an EINER Stelle: `core/fehlercodes.py`; die KI
  schlägt sie mit `explain_error` nach (gross, frei). Lesen in Stücken
  (read_pdf/read_docx über 20.000 Zeichen) ist `ok` mit „Seiten 1–20 von 45
  gelesen, weiter mit seiten=21-45". Tests: `tests/test_fehlercodes.py`
  (jeder Code erklärt, kein Abbruch ohne Code, Abbruch nach dem Schreiben
  lässt die Daten Byte für Byte wie vorher).
- **ask_choice ohne Antwort** (Zeit um, gestoppt) → `keine_antwort`: „Sasha
  hat NICHT geantwortet — ändere nichts, was davon abhängt, frag nach".
  `wait_permission` liefert dafür `None` statt des Texts „(keine Antwort)".
  Das Ergebnis geht als `werkzeug`-Event raus und steht im Verlauf (vorher
  fehlte es dort — wer das Gespräch nachlas, sah bei ask_choice nichts und
  hielt es für „None"). Laut Journal hatte Sasha am 08.10. tatsächlich „ja"
  geklickt; gefunden und behoben wurde dabei ein echtes Rennen in der TUI:
  `ai_answer_perm` löschte nach dem POST `AI["perm"]` — auch wenn dort schon
  die NÄCHSTE Frage stand. Jetzt nur noch die beantwortete.
- **Websuche** beginnt auf klein mit „Treffer = Hinweise, NICHT gelesen …",
  auf gross (seit 2026-10-22, KI-Bibel R-01) mit dem nächsten Schritt: „Das
  sind nur Vorschautexte … die 1–3 besten Treffer mit fetch_url lesen, bevor
  du antwortest oder etwas verneinst" (`web.SUCHE_HINWEIS_GROSS`);
  **fetch_url** warnt (Status `ok`), wenn eine Seite kaum Inhalt hatte
  (unter 80 Wörtern oder 3 ganzen Sätzen: Navigation, Menü, Anmeldung) und
  sagt nur, was zu sehen war.
- **Browser** (seit 2026-10-09): jedes Ergebnis nennt „Adresse: <URL>" und
  darf als „gelesen auf <URL>" angegeben werden — Gegenstück zu den
  Suchtreffern. Abbrüche mit Codes `B-…` (Tabelle in `core/fehlercodes.py`,
  s. [browser.md](browser.md)).
- **Prompt (gross), Meta-Regel 2:** „Als Tatsache sagst du nur, was ein
  Werkzeug in diesem Gespräch belegt oder Sasha gesagt hat; alles andere als
  Vermutung oder ‚weiß ich nicht'. Erfolg erst nach dem Beleg." Nach
  Anthropic: „Reduce hallucinations" (weiß-ich-nicht erlauben, an Belege
  binden) und „Writing effective tools for agents" (Ergebnisse mit hohem
  Signal statt „OK", Fehler, die zum richtigen Gebrauch lenken).

### Ehrlichkeit live — Prüfer vor jeder Antwort (seit 2026-10-09)

Auf gross prüft Python jede fertige Antwort gegen das Werkzeug-Protokoll des
Zugs (`core/ehrlichkeit.py`): Erledigt-Behauptung ohne passendes
schreibendes Werkzeug mit ok, oder eine Kalender-Kennung, die nirgends
steht → Korrekturrunden (`<pruefung_automatisch>` als Nutzer-Nachricht),
bis die Antwort besteht, höchstens `pruefer_runden` (5); danach geht sie mit
Warnungen davor raus (Feld `warnungen`). Dazu Erledigt-Zeile aus dem
Protokoll (auch „✗ keine Änderung in diesem Zug") und offene Zusagen im
Kontext-Umschlag. Läuft der Zug im Budget-Rückfall auf einem anderen Modell,
meldet `kern.chat` das am Anfang (`{"modell_wechsel": …}`,
`ai_backends.modell_wechsel`). Einstellung `ehrlichkeit_pruefer`. Seit
2026-10-10 dazu die **Quellen-Zeile** (`core/quellen.py`, Feld `quellen`):
welche Seiten der Zug wirklich gelesen hat — Python, nicht die KI, nennt die
Adresse. Und „frag nicht im Text, ruf das Werkzeug": endet die Antwort mit
„Soll ich im Netz suchen?" o. ä., obwohl Sasha gefragt/beauftragt hat, gibt
es eine Korrekturrunde (alle Modelle, vorher nur qwen); ebenso bei einem
Aufschub („trag ich erst ein, wenn …") eines klaren Auftrags — Sicheres
sofort, nur das Fehlende fragen (auch als Satz im Antwortverhalten). Seit
2026-10-10 sprachfrei: die KI gibt jede Antwort über `antwort` mit festen
Feldern ab (**Selbstauskunft**, `core/selbstauskunft.py`), Python vergleicht
sie mit dem Protokoll; freier Text → Wortlisten wie bisher, Widerspruch →
„unsicher" (`core/klassifikator.py`, Einstellung `klassifikator`, Standard
aus); jede geprüfte Antwort wird ein lokales Beispiel
(`core/klassifikator_beispiele.py`). Ebenfalls 10.10.: die **Auftrags-
Abrechnung** (`auftrag` an `antwort`, `core/auftrag_abrechnung.py`) — kein
Teil eines Auftrags fällt still weg, „offen: …" steht unter der Antwort —
und „nicht gefunden" nach nur einer Stichwortsuche für alle Modelle. Alles
Weitere: [ehrlichkeit_live.md](ehrlichkeit_live.md).

### Werkzeuge aus dem Schema — `core/werkzeug_erzeuger/` (seit 2026-10-10)

Die schreibenden Kalender-Werkzeuge der gross-Schiene werden aus Aktions-
Schemas (MCP-Form, `core/werkzeug_kalender.py`) ERZEUGT; Schutzschicht
(Schema-Prüfung, Gate-Frage aus Feldern, Nachlesen, Zurücknehmen, feste
Satzform) einmal im Erzeuger, Fach im Adapter (`core/ki_kalender_adapter.py`).
Neu: Phasen (`set/edit/delete_calendar_phase`), `set_calendar_group`,
`set_calendar_layer`, Gruppe Pflicht beim Anlegen, `nur_von`/`nur_bis` an
`edit_calendar_routine`. Seit 2026-10-22 nimmt `add_calendar_entry`/`_routine`
die Ebene direkt (`layer` 'uncommitted' = vielleicht), auch auf qwen
([ki_kalender.md](ki_kalender.md)). Eintrag-Felder `gross_ausfuehrer`, `erzeugt`,
`bereich`, `worte`, `zuschnitt` (`core/werkzeug_eintrag.py`);
`ki_werkzeuge._verteilen` nimmt auf gross den `gross_ausfuehrer`.
Einstellung `werkzeuge_erzeugt` (an|aus). Alles Weitere:
[werkzeug_erzeuger.md](werkzeug_erzeuger.md).

## Werkzeuge zu Gesprächen, Projekten, Ablage, PDF/Word

### Frühere Gespräche — `search_chats`, `read_chat` (seit 2026-10-07)

Phase 3 des [Claude-Web-Plans](claude_web_plan.md). Sasha orientiert sich
nach Thema, nicht nach Datum; seit es viele Gespräche gibt
([gespraeche.md](gespraeche.md)), muss die KI aus jedem Gespräch heraus
finden, was in einem anderen gesagt wurde. Modul `core/chat_suche.py`
(Schicht 2), beide Werkzeuge nur `gross`, **ungegatet** (nur lesen).

| Werkzeug | Was |
|---|---|
| `search_chats(query)` | höchstens 8 Treffer: Titel, id, Datum, Zahl der Stellen, ein Ausschnitt (~220 Zeichen, Sasha oder KI) |
| `read_chat(id, query?, anzahl?)` | ein Gespräch nachlesen: die letzten `anzahl` (20, max 40) Nachrichten, mit `query` das Fenster um die beste Fundstelle; jede Nachricht ≤ 1.500 Zeichen |

Durchsucht werden alle Gespräche (auch archivierte, „Erinnerungen") und das
alte Transkript, nach Tag gruppiert (id `transkript:JJJJ-MM-TT`). Wie
gesucht wird, was ausgelassen wird (Denken, versteckte Aufträge, das
laufende Fenster, Doppeltes aus dem Transkript): [gespraeche.md](gespraeche.md),
Abschnitt „Suche". Wann suchen: Meta-Regel 7 in `profil/gross.py` („bezieht
sich Sasha auf Früheres … erst search_chats"). Text-Budget der zwei
Beschreibungen: eigener Deckel < 450 Zeichen in `tests/test_profil.py`.

Zwei Werkzeuge statt eines mit Modus: jedes Schema bleibt klein und
eindeutig, und das Modell muss keinen Modus-Parameter richtig setzen.

Seit Phase 6 hat `search_chats` einen optionalen Parameter `projekt` (Name
oder id): dann nur die Gespräche dieses Projekts, ohne das alte Transkript.

### Projekte — Projekt-Block und `read_project_file` (seit 2026-10-07)

Phase 6 des [Claude-Web-Plans](claude_web_plan.md), ausführlich
[projekte.md](projekte.md). Ein Gespräch kann zu einem Projekt gehören
(eigene Anweisungen + Wissensdateien). Dann steht `projekte.prompt_block(id)`
im **festen, gecachten Kopf** (`cloud._static_system(…, projekt=)`, hinter
Gedächtnis-Kopf und Skill-Liste, vor dem Imprint; nur mit
`MERKMALE["projekte"]`, also `gross`): Name, Anweisungen (≤ 4.000 Zeichen,
sonst gekürzt) und die LISTE der Wissensdateien mit Größe. Byte-stabil, solange
Sasha am Projekt nichts ändert — der Cache gilt pro Projekt; ein Gespräch ohne
Projekt sieht keinen Block, sein Kopf bleibt wie vorher.

Das Projekt reist als **Parameter**: Chat-Route (`gespraeche.projekt_von`) →
`kern.chat(projekt=)` → `cloud.chat_stream` / `cloud_openai.chat_stream`
(`projekt=`) → `_static_system` und `ki_werkzeuge.mit_projekt(projekt)`. Kein
globaler Zustand; der lokale Weg und der Erinnerungs-Takt bekommen keins.

| Werkzeug | Was | Gate |
|---|---|---|
| `read_project_file(name, ab?)` | Wissensdatei des Projekts DIESES Gesprächs (≤ 20.000 Zeichen ab `ab`); „anweisungen" → die ungekürzten Anweisungen | nein |

Das Projekt bekommt der Ausführer von `ki_werkzeuge._verteilen` (markiert mit
`@braucht_projekt`), nie aus den Argumenten des Modells; gefunden wird nur
über die Dateiliste des Projekts — kein Pfad-Ausbruch, kein fremdes Projekt.
Keine neue Meta-Regel (der Kopf von `gross.system()` steht bei ~4.974 von
5.000 Zeichen); der Block erklärt sich selbst. Text-Budget: eigener Deckel
< 200 Zeichen in `tests/test_profil.py`.

### Ablage und Anhänge — `create_document` & Co. (seit 2026-10-07)

Phase 5 des [Claude-Web-Plans](claude_web_plan.md), ausführlich in
[ablage.md](ablage.md). Die KI legt Dokumente in `data/ablage/` ab
(`core/ablage.py`), Sasha gibt ihr Dateien mit (`core/anhang.py`).

| Werkzeug | Was | Gate |
|---|---|---|
| `create_document(titel, inhalt, art?, sprache?)` | neues Dokument (markdown/text/code/csv) | nein |
| `read_document(id, ab?)` | Text-Inhalt lesen, lange Texte in Stücken zu 30.000 Zeichen (seit 2026-10-22) | nein |
| `update_document(id, inhalt)` | neue Fassung, alte bleibt | nein |
| `save_from_sandbox(lauf, datei, titel?)` | Datei aus einem `run_code`-Lauf dieses Gesprächs — nur auf Sashas Wunsch | **ja** (seit 2026-10-07, ohne „immer") |

Die ersten drei ungegatet, weil nur in den eigenen Ordner geschrieben, nie überschrieben,
nie gelöscht wird und nichts nach draußen geht. Ein Werkzeug meldet ein neues
Dokument über **`core/zug.py`** (der laufende Zug, Schicht 1): die Chat-Route
öffnet ihn mit der Gesprächs-id, holt nach jedem `werkzeug`-Event die
Meldungen ab und schickt sie als SSE `ablage`; so musste die Schleife nicht
umgebaut werden. Über denselben Zug bekommt `run_code` die Gesprächs-id für
seinen Arbeitsordner (`<gespräch>--<zeit>-<hex>`). Text-Budget der vier
Beschreibungen: eigener Deckel < 780 Zeichen in `tests/test_profil.py` (seit
2026-10-22; vorher 650 — read_document und update_document grenzen sich jetzt
gegen read_file und replace_document ab).

**Anhänge** gehen als eigene Blöcke an die Cloud (Anthropic: `image`
base64 + `text`; OpenAI-kompatibel: Inhalt als Liste mit `image_url`); im
Gespräch steht nur ein Verweis, der Inhalt kommt beim Bauen des Verlaufs
dazu (`anhang.verlauf_einsetzen`). Lokal: Text ja, Bilder nein (400 mit
Hinweis auf `/cloud`).

### PDF und Word — `read_pdf` & Co. (seit 2026-10-08)

Sechs Werkzeuge nur auf `gross`, hinten an (Einträge in
`core/werkzeug_pdf_word.py`, Ausführer in `core/ki_pdf_word.py`):
`read_pdf`, `read_docx` frei; `create_pdf`, `combine_pdf`, `create_docx`,
`edit_docx` gefragt („immer" möglich — es entsteht nur eine neue Datei in der
Ablage, nie wird etwas überschrieben). Jede neue Datei wird aus der Ablage
nachgelesen (Seitenzahl/Text bzw. Überschriften/ersetzter Text) und als Beleg
zurückgegeben. Die Anleitung steht in den Skills `pdf` und `word`. Text-Budget
der Beschreibungen: eigener Deckel < 800 in `tests/test_profil.py`.
Ausführlich: [pdf_word.md](pdf_word.md).

## Historie

- **2026-06-07** — Internet-Pipe, erste gegatete Werkzeuge.
- **2026-10-07** — Werkzeug-Register; Phasen 3–7 des Claude-Web-Plans bringen
  `search_chats`/`read_chat`, Projekte, Ablage, Skills, Sandbox.
- **2026-10-08** — Status-Kopfzeile und Belege; PDF/Word; Kalender ohne Fallen.
- **2026-10-09** — zwei Ausgänge mit festen Fehlercodes; Ehrlichkeit live.
- **2026-10-10** — Werkzeuge aus dem Schema; Selbstauskunft über `antwort`.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
- **2026-10-22** — Texte nach der KI-Bibel (W-01/W-04/W-11), `mit_suche`,
  `input_examples`, read_document in Stücken.
