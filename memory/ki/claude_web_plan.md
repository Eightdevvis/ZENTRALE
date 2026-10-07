# Claude-Web im ZENTRALE-Assistenten — der Plan

Stand 2026-10-07. **Geplant und von Sasha entschieden (Abschnitt 6).
Phase 0, 1, 2, 3, 4, 5 und 7 sind gebaut (Abschnitte 5 und 7), der Rest noch nicht.** Sasha hat am 06.10. gesagt: erst aufräumen, dann vor dem
Übertragen anhalten und gemeinsam planen. Das ist am 07.10. geschehen.

Grundregel aus [../claude_hinweise.md](../claude_hinweise.md) („Das
Strukturziel"): nichts hinbauen ohne Plan, wie die Architektur damit skaliert.
Jede Funktion unten hat deshalb eine **Ebene**, in die sie gehört, und die
Ebenen stehen vor den Funktionen.

---

## 1. Was es heute gibt (Bestandsaufnahme 07.10.)

| Bereich | Heute in ZENTRALE |
|---|---|
| **Eingabe** | TUI-Chatfeld (`space`/`a`): eine Zeile, nur ASCII, max. 1000 Zeichen, kein Cursor, keine Slash-Befehle im Chat |
| **Antwort** | SSE von `/api/chat`; Text kommt pro Runde am Stück (nicht Token für Token), Denken läuft live als „denkt: …" mit |
| **Sichtbar** | Werkzeug-Aufrufe (`⚙ … ↳ …`), Denken als Log-Zeile, Markdown (Überschriften, Listen, Code), Modell + € heute im Titel, ⚠ ab 80 % Budget |
| **Verlauf** | EIN Gespräch, nur im RAM (`state._chat_history`, 50 Einträge), weg nach Neustart. Das Transkript (`data/ai_transcripts/`) wird geschrieben, aber nie gelesen. *(Seit Phase 2: viele Gespräche auf der Platte, [gespraeche.md](gespraeche.md).)* |
| **Gedächtnis** | Dateien in `data/gedaechtnis/`: Hausregeln/Steckbrief/Ziele stehen immer im Prompt (nur Cloud), dazu Titel aller Bereiche; Rest per `read_note`/`search_memory` |
| **Werkzeuge** | Kalender, Dateien lesen, News, Mail-Zahlen, Websuche, Webseite holen, Auswahlknöpfe, Gedächtnis, Messreihen. Erlaubnis-Gate für alles Schreibende |
| **Proaktiv** | Takt: Termin-Erinnerung 60/30 min vorher, landet im selben Gespräch |
| **Einstellungen** | Nur `/cloud on|off`, `/local on|off` aus der TUI. Anbieter, Modell, Effort, Budget, Backend: Setter existieren im Kern, aber **kein Kabel** — nur per Hand in `data/ai_config.json` |
| **Fehlt ganz** | Stoppen, Neu, Wiederholen, Bearbeiten, Gesprächsliste, Anhänge, Bilder rein, Kopieren, Ablage/Artefakte, Skills, Projekte |

## 2. Was Claude Web hat — und was davon Sinn ergibt

| Claude Web | Sinn für ZENTRALE? | Ebene (Abschnitt 3) |
|---|---|---|
| Gespräche: Liste, neu, umbenennen, suchen | **ja, Kern** — ohne das keine weiteren Schritte | Gespräch |
| Stoppen während der Antwort | **ja**, billig, spart Geld | Steuerung |
| Antwort neu erzeugen / letzte Nachricht bearbeiten | ja | Steuerung + Gespräch |
| Modell- und Effort-Wahl | **ja** — Kabel liegt schon fast | Steuerung |
| Memory (Claude merkt sich Dinge über Chats hinweg, Nutzer kann es sehen/ändern) | gibt es schon (Kernakten), aber **unsichtbar** in der TUI | Gedächtnis |
| „Frühere Chats durchsuchen" | ja — Transkript liegt schon da, wird nur nie gelesen | Gedächtnis |
| Projekte (eigene Anweisungen + Wissensdateien pro Thema) | später; Dossiers sind fast schon das | Projekt |
| Skills (Anleitungspakete, die nur bei Bedarf geladen werden) | **ja**, passt genau zur Kosten-Logik | Skill |
| Werkzeuge: Websuche, Webseite holen | gibt es | Werkzeug |
| Code ausführen | **Entscheidung Sasha** — Sicherheitsfrage | Werkzeug |
| Artefakte (Dokumente/Seiten neben dem Chat) | ja, als **Ablage** in der TUI | Ausgabe |
| Dateien/Bilder anhängen | ja (Dateipfad; Bilder nur Cloud) | Eingabe |
| Konnektoren (MCP: Drive, Kalender, …) | später, nur als Gedanke | Werkzeug |
| Stile (knapp/ausführlich) | klein, über Skills lösbar | Skill |
| Token-für-Token-Streaming | Sasha 06.10.: „Streaming egal" → hinten | Ausgabe |

## 3. Die Ebenen — wie es zusammenspielt

```
      TUI (tui/ansichten/chat.py)             ← Frontend: zeigt, nimmt Tasten
            │  HTTP + SSE (ein Vertrag: Events)
      ui/routen/ki.py                          ← nur Übersetzung, keine Logik
            │
      kern.chat(gespraech_id, …)               ← der eine Einstieg (gibt es)
            │
   ┌────────┼──────────────┬──────────────┬─────────────┐
 Gespräch  Prompt-Bau      Werkzeug-       Fahrzeug
 (Speicher) = Profil       Schleife        (Anbieter/Modell
            + Gedächtnis-  (gibt es)       = Variablen,
              Kopf          │              gibt es)
            + Projekt       Werkzeug-Register ── Erlaubnis-Gate
            + Skill-Liste   (EINE Tabelle)
```

**Die sechs Ebenen, von außen nach innen:**

1. **Steuerung** — was der Mensch am laufenden Gespräch dreht: stoppen,
   neu, wiederholen, Modell/Effort. Kein eigener Speicher; ruft nur die
   Ebenen darunter. Backend: Routen + ein Abbruch-Signal pro laufendem Strom.
2. **Gespräch** — *das fehlende Fundament.* Ein Gespräch = eine Datei
   `data/gespraeche/<id>.jsonl` (Nachrichten, Werkzeug-Ergebnisse, Titel,
   Anbieter je Antwort). `state._chat_history` wird zum Cache des aktiven
   Gesprächs. Ein Modul `core/gespraeche.py`: `neu`, `liste`, `laden`,
   `anhaengen`, `kuerzen_ab(n)` (für Bearbeiten/Wiederholen), `umbenennen`,
   `archivieren`.
3. **Gedächtnis** — gibt es. Neu nur: (a) in der TUI **sichtbar und
   bearbeitbar** (Kernakten anzeigen, Bestätigungen aus dem Gate), (b) ein
   Werkzeug `search_chats` über Gespräche + Transkript.
4. **Skill** — eine Datei `data/gedaechtnis/skills/<name>.md` mit Kopf
   (`name`, `beschreibung`, wann benutzen). Im Prompt steht **nur die
   Liste** (eine Zeile pro Skill); den Inhalt holt sich das Modell per
   `load_skill(name)`, wenn es ihn braucht. So kostet ein Skill fast nichts,
   solange er nicht dran ist — dasselbe Prinzip wie heute „Titel im Kopf,
   Inhalt per `read_note`". Abgrenzung: **Profil** = wie die Schiene
   grundsätzlich denkt (klein/gross), **Skill** = Anleitung für eine Aufgabe,
   **Projekt** = Rahmen für ein Thema.
5. **Werkzeug** — lag bis 07.10. an drei Stellen (Beschreibung in
   `profil/klein.py` + `gross.py`, Ausführung in `ki_werkzeuge._verteilen`,
   Erlaubnis in `erlaubnis.py`). Seit Phase 0: **ein Register**
   (`core/werkzeug_register.py`), ein Eintrag pro Werkzeug mit Schema,
   Beschreibung je Schiene, Erlaubnis-Regel + Frage; die Ausführer melden
   sich aus `ki_werkzeuge` an. Ein neues Werkzeug ist ein Eintrag plus seine
   Funktion — dieselbe Idee wie die Anbieter-Tabelle („eine Zeile, kein
   Umbau"). Anleitung: [ki_system.md](ki_system.md), „Das Werkzeug-Register".
6. **Ausgabe** — die Events sind der Vertrag zwischen Kern und TUI. Neu:
   `ablage` (ein Dokument entstand → TUI zeigt es in einer Liste, öffnet es
   im Pager/Editor), `titel` (Gespräch bekam einen Namen), `gestoppt`.

**Projekt** (später) ist kein eigener Speicher, sondern eine Klammer: ein
Ordner unter `data/gedaechtnis/projekte/<name>/` mit `anweisungen.md` und
Wissensdateien; ein Gespräch gehört optional zu einem Projekt, und der
Prompt-Bau hängt dessen Anweisungen hinter den Gedächtnis-Kopf.

## 4. Die Fallen, die vorher klar sein müssen

- **Sync ist nur additiv** (rsync, neueste Datei gewinnt). Gelöschte
  Gespräche kämen vom anderen Rechner zurück. Deshalb **nie löschen, nur
  archivieren** (Flag in der Datei), und **eine Datei pro Gespräch** — sonst
  überschreiben sich zwei Rechner gegenseitig das ganze Verlaufsbuch.
- **Prompt-Cache.** Der Anthropic-Cache hängt an einem festen Anfang
  (Werkzeuge + Persona + Gedächtnis-Kopf). Skills und Projekt-Anweisungen
  dürfen ihn nicht bei jedem Zug verändern: Skill-*Liste* in den festen Teil,
  geladener Skill-*Inhalt* als Werkzeug-Ergebnis (wandert mit dem Verlauf).
- **Stoppen muss bis in die Schleife reichen.** Verbindung schließen reicht
  nicht: der Kern läuft weiter und bezahlt. Die Werkzeug-Schleife prüft vor
  jeder Runde ein Abbruch-Signal; laufende Anbieter-Ströme werden geschlossen.
- **Das lokale qwen bleibt klein.** Alles Neue erst auf der Cloud-Schiene;
  `klein` bekommt nur, was gegen ein echtes qwen gemessen ist
  ([bench_history.md](bench_history.md)).
- **Code ausführen** heißt: das Modell startet Programme auf Sashas Rechner.
  Nur in einer Sandbox: eigener Arbeitsordner, kein Zugriff auf `data/` und
  Keys, Zeitlimit, Ausgabe gekappt, jeder Lauf über das Erlaubnis-Gate.
- **Gespräche auf zwei Rechnern.** Sasha will EIN Gedächtnis, egal von wo
  (Entscheidung 2). Der Sync kennt aber nur „neueste Datei gewinnt": schreiben
  PC und Laptop in dieselbe Gesprächsdatei, verliert einer. Deshalb ist ein
  Gespräch ein **Ordner** `data/gespraeche/<id>/` mit **einer Datei pro
  Rechner** (`<knoten>.jsonl`, nur anhängen) plus `kopf.json` (Titel, Projekt,
  archiviert; klein, neueste gewinnt ist dort harmlos). Beim Lesen werden die
  Rechner-Dateien nach Zeitstempel zusammengelegt. So kann der Sync nie eine
  Nachricht überschreiben.
- **Der Riese** ist weg: seit 611d186 (07.10.) hat der Chat sein eigenes
  Modul `tui/ansichten/chat.py` (Klasse `Chat`, siehe
  `memory/system/tui_bauplan.md`). Neue Chat-Funktionen gehören dorthin.

## 5. Reihenfolge

| Phase | Was | Warum zuerst | Größe |
|---|---|---|---|
| ~~**0 Fundament**~~ | ~~TUI-Zerlegung~~ (erledigt 07.10.); ~~Werkzeug-Register~~ (erledigt 07.10., siehe unten) | Ohne ein Register wächst jedes neue Werkzeug an drei Stellen | mittel |
| **1 Steuerung** ✔ 07.10. | Stoppen (bis in die Schleife), mehrzeilige Eingabe mit Cursor, Slash-Befehle im Chat (`/neu`, `/modell`, `/effort`), Kabel für die vorhandenen Setter (Route + TUI) | sofort spürbar, kleines Risiko, Setter liegen schon da | klein |
| **2 Gespräche** ✔ 07.10. | `core/gespraeche.py` (Ordner pro Gespräch, Datei pro Rechner), Gesprächsliste in der TUI, neu/wechseln/umbenennen/archivieren, automatischer Titel, Wiederholen + letzte Nachricht bearbeiten, **Denken mitgespeichert und aufklappbar**, Gespräch „Erinnerungen" | das Fundament für alles Weitere; Verlauf überlebt Neustarts | mittel |
| **3 Gedächtnis sichtbar** ✔ 07.10. | Kernakten in der TUI ansehen/ändern, **`search_chats` über alle Gespräche** | Sasha orientiert sich nach Thema, nicht nach Datum — die Suche quer durch Gespräche ist dafür die Bedingung | klein |
| **4 Skills** ✔ 07.10. | Skill-Dateien, Liste im Prompt, `load_skill`, erste Skills; **`propose_skill`**: die KI schlägt Skills vor, angelegt wird erst nach Bestätigung (Gate) | billig, passt zur Kostenlogik; Grundlage dafür, dass sie sich später selbst weiterentwickelt | klein |
| **5 Ablage + Anhänge** ✔ 07.10. | `ablage`-Event + Ablage-Liste in der TUI; Datei anhängen per Pfad; Bilder an die Cloud | Artefakte in Terminal-Form | mittel |
| **6 Projekte** | Projekt-Ordner, Zuordnung Gespräch→Projekt | erst wenn 2–4 stehen | mittel |
| **7 Sandbox (Grundlage)** ✔ 07.10. | `run_code` in einem abgeschotteten Arbeitsordner (Python + Shell, Zeitlimit, kein `data/`, keine Keys, Gate); Ergebnis als Werkzeug-Ergebnis, Dateien in die Ablage | Sasha: die KI soll später wie ein Coder arbeiten — jetzt nur das Fundament, keine volle Coding-KI | klein |
| später | echtes Token-Streaming, Konnektoren (MCP), Coding-Werkzeuge über die Sandbox hinaus (Repo lesen/ändern), Ollama über denselben OpenAI-Weg (erst messen) | Sasha: Streaming egal; „erstmal wird der Assistent ordentlich" | — |

Jede Phase: eigener Worktree, Tests, Doku hier nachziehen, Leitplanken-Test
(`tests/test_kern_bauplan.py`) bekommt neue Module eingetragen.

**Phase 0, Werkzeug-Register — erledigt 07.10.2026.** Gebaut:
- `core/werkzeug_register.py` (Schicht 3): `WERKZEUGE`, ein `Werkzeug`-Eintrag
  je Werkzeug (Name, `parameter`, `klein`/`gross`-Beschreibung, `klein_name`,
  `erlaubnis` False/True/f(args), `frage`, `terminal`, `in_der_schleife`).
  Lookups: `schema(schiene)`, `terminal`, `kanonisch`/`ALIASE`, `eintrag`,
  `braucht_erlaubnis`, `frage`, `immer_bestaetigen`.
- Die Ausführer melden sich aus `ki_werkzeuge.py` per `@ausfuehrer("name")` an
  (kein Import-Kreis: `ki_werkzeuge` schlägt im Register nach).
- `profil/klein.py`, `gross.py`, `profil.ALIASE`/`kanonisch`, `erlaubnis.py`
  und `ki_werkzeuge._verteilen` sind Durchreichen; alle alten öffentlichen
  Namen (`ai.TOOLS`, `ai._dispatch_tool`, `erlaubnis.PERMISSION_REQUIRED_TOOLS`
  …) bleiben.
- Beweis: `tests/test_werkzeug_schnappschuss.py` vergleicht die Listen beider
  Schienen in beiden Dialekten byte-genau und Gate + Frage-Text für alle
  Werkzeuge mit einem Schnappschuss von VOR dem Umbau;
  `tests/test_werkzeug_register.py` prüft Waisen in beide Richtungen und dass
  keine zweite Werkzeugliste mehr existiert.

## 6. Entscheidungen (Sasha, 07.10.2026)

1. **Viele Gespräche wie im Web**, kein Tagesgespräch. „Mein Kopf kann sich
   thematisch viel besser orientieren als datiert — solang der Assistent eh
   einfach crossgespräche suchen kann wie Claude Web." → `search_chats` ist
   Pflicht, nicht Zugabe.
2. **Gespräche synchron auf allen Rechnern** — als Folge davon, dass das
   Gedächtnis überall gleich sein muss: „der Assistent ist konsistent, egal
   von wo ich ihn anspreche." → Ordner pro Gespräch, Datei pro Rechner
   (Abschnitt 4).
3. **Erinnerungen bekommt der Assistent alle**: Kalender, Zeitplan, gestellte
   Timer und Ähnliches. Das Wort „Takt" verwirrt Sasha und kommt aus allem
   raus, was er sieht. Wo sie landen, hat Sasha offengelassen — angenommen:
   ein eigenes Gespräch „Erinnerungen" oben in der Liste; der Assistent sieht
   es aus jedem Gespräch über die Suche.
4. **Die KI soll Skills vorschlagen**, damit sie sich später selbst
   weiterentwickeln kann. Anlegen nach Bestätigung.
5. **Code ausführen: ja**, als Grundlage — die Idee ist, dass der Assistent
   später coden kann wie Claude Code oder mit ihm zusammen. Jetzt nur das
   Fundament; „Hauptsache der Assistent wird erstmal ordentlich."
6. **Denken mitspeichern**, zum Anschauen. Ob es langfristig gebraucht wird,
   wird später anhand der Nutzung entschieden.

## 7. Gebaut

### Phase 1 — Steuerung (2026-10-07)

- **Stoppen bis in die Schleife.** `/api/chat` meldet jeden Zug mit einer
  Strom-Nummer an (`state.chat_zug_beginnen`, ein `threading.Event` je Zug)
  und schickt sie als erstes SSE-Event `strom`. `POST /api/chat/stop
  {strom?}` setzt das Signal (ohne Nummer: jeden laufenden Zug) und beendet
  eine offene Erlaubnis-Frage mit „nein". `kern.chat(…, abbruch=)` reicht es
  an den Weg; `werkzeug_schleife.laufen` prüft es vor jeder Runde und vor
  jedem Werkzeug, die drei Adapter (Ollama, Anthropic, OpenAI) im Strom bei
  jedem Stück: Strom schließen, Verbrauch buchen (Anthropic: Eingabe + Cache
  aus `message_start`, Ausgabe nur, falls schon gemeldet; OpenAI meldet erst
  am Ende → dann „nichts gebucht" im Log), `Gestoppt(text)` werfen. Die
  Schleife gibt den halben Text roh aus und dann `{"gestoppt": True}` —
  nichts wird gemerkt. Die Route speichert Text mit dem Vermerk
  „(abgebrochen)", einen Zug ohne Text gar nicht. TUI: Esc während einer
  Antwort stoppt („stoppe …" → „gestoppt"), sonst schließt Esc wie bisher.
- **Eingabe** (`tui/ansichten/eingabe.py`, reine Funktionen): mehrzeilig
  mit Cursor, ←→, Pos1/Ende (auch Strg+A/E), ⌫/Entf an der Cursorstelle,
  Alt+Enter = neue Zeile (ESC + Enter, kurz gewartet wie bei Alt+Pfeil in
  der Karte), Umlaute und alles Unicode (UTF-8-Bytes werden zusammengesetzt;
  die Hauptschleife bleibt bei `getch`), wächst bis 5 Zeilen, dann scrollt
  es. ↑↓ scrollen den Verlauf, solange kein Zeilenumbruch in der Eingabe
  ist; sonst bewegen sie den Cursor (Verlauf dann mit Bild↑↓). Tippen geht
  auch während einer Antwort, nur Abschicken wartet.
- **Slash-Befehle im Chat** (`tui/ansichten/chat_befehle.py`): `/neu`,
  `/modell [name]`, `/anbieter [name|auto]`, `/effort [stufe]`,
  `/budget [euro|aus]`, `/lokal` `/cloud` `/auto`, `/hilfe`; `//` schickt
  einen wörtlichen Schrägstrich. Unbekannter Befehl → Hinweis, nichts geht
  an die KI. Ohne Argument öffnen `/modell`, `/anbieter`, `/effort` eine
  Auswahl (↑↓, Enter oder Ziffer, Esc). `/neu` steckt in genau einer
  Methode (`Chat.neues_gespraech`) — in Phase 2 wird nur sie umgebaut.
- **Kabel für die Setter:** `GET/POST /api/ai/einstellungen` über
  `core/ki_einstellungen.py` (prüft alles, dann setzt es alles; 400 mit
  Klartext, z. B. „Für grok ist kein Schlüssel hinterlegt."). Ein Modell, das
  nur bei einem anderen Anbieter mit Schlüssel in der Liste steht, nimmt
  diesen Anbieter mit. Nach jedem Setzen holt die TUI `/api/ai/status` für
  den Titel.

Angenommen (Sasha war nicht erreichbar): Modell-Liste = Standard + billig
aus `providers.py` + gespeichertes, ein freier Name geht per `/modell <name>`
an den aktuellen Anbieter; Budget-Grenze 10.000 €; Eingabe bis 4.000
Zeichen (vorher 1.000).

### Phase 4 — Skills (2026-10-07)

- **`core/skills.py`** (Schicht 2): Skills als `data/gedaechtnis/skills/<name>.md`
  mit Kopf (`beschreibung`, `erstellt`, `herkunft` sasha|ki, `status`
  aktiv|vorgeschlagen|aus) im Katalog-Schema des Gedächtnisses. Bewusst nicht
  in `gedaechtnis.BEREICHE` (sonst schriebe `write_note` sie ungefragt).
  Details: [gedaechtnis_dateien.md](gedaechtnis_dateien.md), „Skills".
- **Prompt:** `skills.prompt_block()` — eine Zeile je aktivem Skill, nach Name
  sortiert — im festen Kopf (`cloud._static_system`, nur wenn die Schiene
  `MERKMALE["skills"]` hat: `gross`). Meta-Regel 6 in `profil/gross.py`: wann
  laden, wann vorschlagen, Abgrenzung zu den Hausregeln.
- **Werkzeuge** (nur `gross`, hinten an): `load_skill` (frei),
  `propose_skill` und `edit_skill` (gegatet; `.bak` beim Ändern).
  Schnappschuss neu gezogen: nur die drei Einträge, `klein` byte-gleich.
  Eigener Text-Deckel (< 600 Zeichen) in `tests/test_profil.py`.
- **Erste Skills** `wochenplan`, `recherche`, `kurz` in
  `core/skill_vorlagen/`; kommen beim ersten Zugriff nach `skills/`, wenn der
  Ordner noch fehlt, nie überschreibend, mit altem Datei-Datum (Sync).
- **`GET /api/skills`** (`ui/routen/skills.py`).
- Tests: `tests/test_skills.py`; Wächter in `test_keine_seiteneffekte.py`.

Angenommen (Sasha war nicht erreichbar): Vorlagen unter
`core/skill_vorlagen/` (nicht `memory/`, das ist Doku); `propose_skill`
legt nach Ja sofort `aktiv` an (`vorgeschlagen` bleibt für später);
`load_skill` gibt ausgeschaltete nicht heraus; Grenzen 160 Zeichen
Beschreibung, 6.000 Inhalt. ~~Offen: `/skills` im TUI-Chat, Skills
ansehen/schalten in der TUI~~ — erledigt in Phase 3. Die KI kann einen Skill
weiterhin nicht abschalten (nur Sasha, jetzt in der TUI).

### Phase 7 — Sandbox, Grundlage (2026-10-07)

- **`core/sandbox.py`** (Schicht 2): `ausfuehren(code, sprache, zeitlimit_s,
  dateien, lauf_id) → {ausgabe, fehler, rc, dauer_s, dateien_neu,
  abgebrochen, ordner}` über bubblewrap; `als_text()` fürs Modell,
  `aufraeumen()`, `verfuegbar()`. Was abgeschottet ist und was nicht:
  [ki_system.md](ki_system.md), Abschnitt „Sandbox".
- **Werkzeug `run_code`** im Register (nur `gross`, hinten an, immer
  gegatet). Schnappschuss neu gezogen: nur der neue Eintrag, `klein`
  byte-gleich.
- Tests: `tests/test_sandbox.py` (Netz zu, Repo/`data/`/`~` unsichtbar,
  Zeit-, Speicher-, Prozess-, Ausgabe-, `/tmp`-Grenze, neue Dateien, Shell,
  bwrap fehlt/scheitert → nichts läuft, Gate, Schiene); überspringen sich
  ohne bwrap. Wächter in `test_keine_seiteneffekte.py`.

Angenommen (Sasha war nicht erreichbar): Arbeitsordner unter
`~/.cache/zentrale/sandbox/` statt `data/sandbox/` (sonst synct
`zentrale-sync` ihn); jeder Lauf ein frischer Ordner (Zuordnung zum Gespräch
kommt, wenn Phase 2 eine Gesprächs-id liefert — `lauf_id` ist dafür schon
da); Aufbewahrung 7 Tage; Grenzen 30/120 s, 512 MB, 64 Prozesse, 50 MB je
Datei, 20.000 Zeichen Ausgabe. Offen: Dateien in die Ablage (Phase 5),
Stoppen eines laufenden Code-Laufs, Pi (bwrap dort nicht geprüft).

### Phase 2 — Gespräche (2026-10-07)

Ausführlich: [gespraeche.md](gespraeche.md). Kurz:

- **Speicher** `core/gespraeche.py` (Schicht 2): Ordner pro Gespräch mit
  `kopf.json` und einer `.jsonl` pro Rechner (nur anhängen). Ereignisse
  `nachricht` / `verwerfen`; Lesen legt die Rechner-Dateien nach Zeit
  zusammen. Nie löschen, nur archivieren. Aktives Gespräch + „gelesen" pro
  Rechner in `_knoten/<knoten>.json`. `state._chat_history` ist **ganz
  ersetzt** (kein Spiegel — zwei Wahrheiten wären die nächste Falle).
- **Verlauf an die KI** aus dem Gespräch (Fenster 50 wie vorher). Denken
  (alle `reflect` eines Zugs, ≤ 20 000 Zeichen) und eine Werkzeug-Liste
  werden mit der Antwort gespeichert, dazu Anbieter und Modell; gestoppte
  Antworten mit `abgebrochen: true`.
- **Titel**: sofort die ersten Wörter, nach der ersten Antwort das billige
  Modell (nur wenn der Zug über die Cloud lief). Der Einmal-Aufruf steht in
  `core/billig.py` und wird jetzt auch vom Graph-Extraktor benutzt (vorher
  dort allein).
- **Erinnerungen** landen im festen Gespräch `erinnerungen` (oben, nicht
  umbenennbar/archivierbar), der Auftrag versteckt. „Takt" steht in keinem
  sichtbaren Text mehr (Log-Zeilen heißen jetzt `ERINNERUNG`).
- **Routen**: `GET/POST /api/gespraeche`, `POST /api/gespraeche/aktiv`,
  `GET /api/gespraeche/<id>`, `POST …/<id>/titel`, `POST …/<id>/archiv`,
  `POST /api/chat/wiederholen`; `/api/chat` mit `gespraech` und `ersetzt`;
  `/api/chat/clear` = neues Gespräch; `/api/chat/history` liefert ids,
  Denken, Werkzeuge und geht auch ohne KI-Backend.
- **TUI**: Gesprächsliste als Überlagerung im Chat-Kasten (Tab bei leerer
  Eingabe oder `/liste`), Befehle `/neu /liste /titel /archiv /wiederholen
  /bearbeiten /denken`, Denken eingeklappt als „▸ gedacht (1 234 Zeichen)",
  Strg+D klappt alles auf/zu, Gesprächstitel im Kasten-Titel.

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| Liste als **Überlagerung** im Chat-Kasten | Seitenleiste (auf 80×24 bliebe zu wenig Verlauf) |
| Öffnen mit **Tab bei leerer Eingabe** (mit Text bleibt Tab ein Leerzeichen) und `/liste` | eigene Taste (z. B. Strg+L) |
| In der Liste **`/` startet das Filtern**, weil r/a/n/z sonst zugleich Befehl und Suchbuchstabe wären | direkt tippen filtert, Befehle per Strg+Taste |
| **`z`** zeigt das Archiv, dort holt **`a`** zurück | eigener Befehl `/archiv zeigen` |
| `/archiv` = **dieses Gespräch archivieren**, dann neues | `/archiv` zeigt die archivierten |
| Denken auf/zu mit **Strg+D** und `/denken`, für alle Antworten zugleich | einzeln pro Antwort (bräuchte einen Zeiger im Verlauf) |
| Denken gekappt auf **20 000 Zeichen, das Ende bleibt** | den Anfang behalten / Mitte kappen |
| Neues Gespräch wird erst **beim ersten Senden** angelegt; leere Gespräche fehlen in der Liste | sofort anlegen (leere Ordner im Sync) |
| Titel sofort aus den **ersten 6 Wörtern**, dann vom Modell | nur das Modell (Liste zeigt bis dahin „neues gespräch") |
| Titel vom Modell **nur, wenn der Zug über die Cloud lief** | immer (dann ginge ein lokales Gespräch für den Titel nach draußen) |
| Route wartet höchstens **1,5 s** auf den Titel, sonst holt ihn die Liste | gar nicht warten (Titel erst nach ≤ 20 s) |
| „Erinnerungen" **nicht umbenennbar, nicht archivierbar** | frei behandeln wie jedes Gespräch |
| Ungelesen und offenes Gespräch **pro Rechner** | geteilt (dann schaltet der Laptop den PC um) |
| Beim Öffnen des Chats **kein** automatischer Sprung zu „Erinnerungen", nur ein Hinweis „neues in einem anderen gespräch" | automatisch dorthin wechseln |
| Auftrag einer Erinnerung **gespeichert, aber versteckt** und für die KI als automatischer Auftrag gekennzeichnet | gar nicht speichern (so war es vorher; dann fehlt der KI später, worauf sie antwortete) |
| `/api/chat/history` und die Gesprächs-Routen gehen **ohne KI-Backend** | wie vorher `[]` ohne Backend |
| `state._chat_history` **ganz entfernt** | als Spiegel behalten |

### Phase 3 — Gedächtnis sichtbar, Suche quer durch Gespräche (2026-10-07)

- **`search_chats(query)` + `read_chat(id, query?, anzahl?)`** (Register,
  nur `gross`, ungegatet, hinten an) über `core/chat_suche.py` (Schicht 2):
  alle Gespräche inkl. Archiv und „Erinnerungen" plus das alte Transkript
  (ein Treffer pro Tag); kein Denken, keine versteckten Aufträge, das
  laufende Fenster des aktiven Gesprächs nicht doppelt, Transkript-Züge, die
  es als Gespräch gibt, auch nicht. Normalisierte Wörter, alle müssen
  vorkommen, Rang Dichte × Aktualität, ≤ 8 Treffer. Ausführlich:
  [gespraeche.md](gespraeche.md), „Suche". `transkript.alle()` liest dafür.
- **Meta-Regel 7** in `profil/gross.py` (ein Satz): bezieht sich Sasha auf
  Früheres, erst `search_chats`. Kopf jetzt 4.974 von 5.000 Zeichen.
  Schnappschuss neu gezogen: nur die zwei Einträge, `klein` byte-gleich.
  Eigener Text-Deckel < 450 Zeichen in `tests/test_profil.py`.
- **Gedächtnis in der TUI:** `tui/ansichten/gedaechtnis.py`, Überlagerung im
  Chat-Kasten über `/gedaechtnis` bzw. `/skills`: Hausregeln, Steckbrief,
  Ziele, Bereiche (Titel), Skills (Name · an/aus · von wem). Kernakte im
  Editor ändern (`$VISUAL`/`$EDITOR`/nano/vi), Skill an/aus per Enter.
- **Routen** (in `ui/routen/skills.py`): `GET /api/gedaechtnis`,
  `PUT /api/gedaechtnis/<akte>` (nur die drei Kernakten, atomar + `.bak`,
  409 bei veraltetem `stand`), `POST /api/skills/<name>/status`.
  Dahinter `gedaechtnis.kernakte_lesen/_schreiben/_stand`,
  `skills.status_setzen`.
- **Aufräumen aus Phase 0:** `werkzeug_schleife.run_tool` fragt das
  Register (`in_der_schleife` → `SELBST`, `terminal` →
  `_terminal_ausgeben`) statt fester Namen; die Verhaltens-Tests liefen auch
  gegen den alten Code grün.
- Tests: `test_chat_suche.py`, `test_gedaechtnis_routen.py`,
  `test_gedaechtnis_ansicht.py`, `test_werkzeug_schleife_register.py`,
  Wächter in `test_keine_seiteneffekte.py`; headless `ki_gedaechtnis` bei
  80×24 und 136×30.
### Phase 5 — Ablage + Anhänge (2026-10-07)

Ausführlich: [ablage.md](ablage.md). Kurz:

- **`core/ablage.py`** (Schicht 2): `data/ablage/<id>/kopf.json` + eine Datei
  je Fassung (`v<n>-<rechner><endung>`), nie überschreiben, nie löschen, nur
  archivieren; umlenkbar per `ablage_dir`; gitignored, in der Datensicherung.
- **`core/zug.py`** (Schicht 1): der laufende Zug — Gesprächs-id für die
  Werkzeuge, Ereignisse an die TUI. Die Route schickt sie als SSE `ablage`.
- **Werkzeuge** (nur `gross`, hinten an, ungegatet): `create_document`,
  `read_document`, `update_document`, `save_from_sandbox`. Schnappschuss neu
  gezogen: nur die vier Einträge, `klein` byte-gleich. Text-Deckel < 650.
- **Sandbox**: `run_code` benennt den Lauf `<gespräch>--…` (offener Punkt aus
  Phase 7), `sandbox.datei_lesen` ohne Ausbruch/Verweise.
- **`core/anhang.py`** (Schicht 2) + `POST /api/anhang`: Sperrliste
  (`context.anhang_gesperrt`), PDF über `gedaechtnis.pdf_text` (herausgelöst
  aus `fetch_document`), Kopie in die Ablage, im Gespräch nur der Verweis;
  Bilder als Block an Anthropic (`image`) bzw. OpenAI (`image_url`), lokal 400.
- **TUI**: `/ablage` (Liste + Lesen im Kasten), „▤ Titel — enter öffnet",
  `/anhang <pfad>`.
- Tests: `tests/test_ablage.py`, `tests/test_ablage_tui.py`, Wächter;
  headless `ki_ablage` bei 80×24 und 136×30.

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| **Zwei Werkzeuge** `search_chats` + `read_chat` | ein Werkzeug mit Modus-Parameter `gespraech` (größeres Schema, Modus muss richtig gesetzt werden) |
| `read_chat` mit optionalem **`query`**: Fenster um die Fundstelle statt nur die letzten N | nur die letzten N (dann fehlt der Treffer in langen Gesprächen) |
| Einheit = **ein Gespräch** (Wörter dürfen über Nachrichten verteilt sein); Transkript = **ein Tag** | jede Nachricht einzeln (ein Gespräch füllte alle 8 Plätze; „geige ferien" über zwei Nachrichten fände nichts) |
| **Teilwort**-Treffer („geige" findet „Geigenstunde") + kleine **Füllwort**-Liste | ganze Wörter (Deutsch setzt zusammen); keine Füllwörter („das mit dem umzug" verlangte „das") |
| Rang **Dichte × (0,4 + 0,6 · Halbwert 60 Tage)** | nur Datum (Sasha: Thema vor Datum) oder nur Dichte (Uraltes gleichauf mit Gestern) |
| „Laufendes Gespräch" = **`gespraeche.aktiv()`** (die Route setzt es vor jedem Zug); nur sein **Fenster** wird ausgelassen | Gesprächs-id per Thread-Kontext durchreichen (hätte `ui/routen/ki.py` angefasst, an dem Phase 5 baut); ganzes Gespräch auslassen |
| Doppeltes aus dem Transkript über **gleiche KI-Antwort** erkennen | nach Datum abschneiden (Transkript nur vor dem ersten Gespräch — verlöre Züge, die es nicht als Gespräch gibt) |
| Versteckte Aufträge im Transkript am **Wortlaut** („Erinnere Sasha", Auftrags-Vorsatz) erkannt | Transkript-Nutzertext ganz weglassen |
| Gedächtnis als **Überlagerung im Chat-Kasten** | eigene Ansicht in der Mitte mit Rad-Platz (Pixel-Symbol, Taste, Rad-Index verschiebt sich) — offen, ob Sasha es dort will |
| Ändern über den **externen Editor** ($VISUAL → $EDITOR → nano → vi) | Inline-Editor in der TUI (gibt es noch nicht; ein mehrzeiliger Editor wäre ein eigenes Projekt) |
| **`stand`** (Fingerabdruck) beim Speichern, 409 bei Abweichung, Text bleibt in der Zwischendatei | blind überschreiben (eine Hausregel der KI aus derselben Minute wäre still weg) |
| Kernakte höchstens **20.000 Zeichen** (wie ein Dossier) | keine Grenze |
| Skill-Schalter: **an ↔ aus**, vorgeschlagen → an; Status-Route nimmt nur den **genauen Dateinamen** | dreistufig durchschalten; Namen über `slug` auflösen |
| Gedächtnis-Routen **in `ui/routen/skills.py`** | eigene `ui/routen/gedaechtnis.py` (fasst `ui/routen/__init__.py` an, wo Phase 5 einhängt) |
| Für Sasha sichtbar: „an/aus", „von dir/von der ki" | die Datei-Wörter „aktiv", „sasha/ki" |

**Offen:** Platz im Rad/auf der Startseite (siehe oben); Bereiche nur als
Titel (Inhalte liest die KI, Sasha noch nicht in der TUI); Erinnerungen in
der Suche gehen mit — falls das stört, lassen sie sich ausnehmen.
| Ablage-Werkzeuge **ungegatet** | gegatet wie `fetch_document` (ein Ja pro Dokument) |
| Ordner pro Dokument, **Fassung mit Rechnername** im Dateinamen | `<name>.v2.md` flach (zwei Rechner → eine Fassung verloren) |
| **`read_document`** zusätzlich | nur create/update (dann ändert die KI blind) |
| `save_from_sandbox` **explizit**, nur Läufe **dieses Gesprächs** | alles automatisch in die Ablage (Zwischendateien) |
| Ereignisse über **`core/zug.py`**, abgeholt in der Route | `run_tool` umbauen (Phase 3 baut dort parallel) |
| **Alle Anhänge** (auch Text/PDF) als Kopie in die Ablage, im Gespräch nur Verweis | Text direkt in die Nachricht (TUI zeigt dann den ganzen Anhang) |
| **TUI liest die Datei** und schickt Bytes | Backend liest den Pfad (unterwegs falscher Rechner) |
| Anhänge gehen **bei jedem Zug** mit (gecacht), Text ≤ 30.000 Zeichen Cloud / 8.000 lokal | nur im Zug, in dem angehängt wurde |
| Lesen **im Chat-Kasten** | `$PAGER`/less (curses verlassen; Pi-Kiosk ohne less) |
| Enter bei leerer Eingabe öffnet das **neueste** Dokument | Zeiger im Verlauf, Enter auf der gewählten Zeile |
| Zwischenablage **nicht gebaut** (gibt es in der TUI nicht) | xclip/wl-copy einbauen |
| Grenzen: Text 200.000 Zeichen, Bild 5 MB, Datei 10 MB | — |
