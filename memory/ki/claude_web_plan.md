# Claude-Web im ZENTRALE-Assistenten — der Plan

Stand 2026-10-07. **Geplant und von Sasha entschieden (Abschnitt 6).
Phase 0 und 1 sind gebaut (Abschnitte 5 und 7), der Rest noch nicht.** Sasha hat am 06.10. gesagt: erst aufräumen, dann vor dem
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
| **Verlauf** | EIN Gespräch, nur im RAM (`state._chat_history`, 50 Einträge), weg nach Neustart. Das Transkript (`data/ai_transcripts/`) wird geschrieben, aber nie gelesen |
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
| **2 Gespräche** | `core/gespraeche.py` (Ordner pro Gespräch, Datei pro Rechner), Gesprächsliste in der TUI, neu/wechseln/umbenennen/archivieren, automatischer Titel, Wiederholen + letzte Nachricht bearbeiten, **Denken mitgespeichert und aufklappbar**, Gespräch „Erinnerungen" | das Fundament für alles Weitere; Verlauf überlebt Neustarts | mittel |
| **3 Gedächtnis sichtbar** | Kernakten in der TUI ansehen/ändern, **`search_chats` über alle Gespräche** | Sasha orientiert sich nach Thema, nicht nach Datum — die Suche quer durch Gespräche ist dafür die Bedingung | klein |
| **4 Skills** | Skill-Dateien, Liste im Prompt, `load_skill`, erste Skills; **`propose_skill`**: die KI schlägt Skills vor, angelegt wird erst nach Bestätigung (Gate) | billig, passt zur Kostenlogik; Grundlage dafür, dass sie sich später selbst weiterentwickelt | klein |
| **5 Ablage + Anhänge** | `ablage`-Event + Ablage-Liste in der TUI; Datei anhängen per Pfad; Bilder an die Cloud | Artefakte in Terminal-Form | mittel |
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
