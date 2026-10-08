# Claude-Web im ZENTRALE-Assistenten — der Plan

Stand 2026-10-07. **Geplant und von Sasha entschieden (Abschnitt 6).
Phase 0, 1, 2, 3, 4, 5, 6 und 7 sind gebaut (Abschnitte 5 und 7), dazu das Frontend nach Claude Web (Ende von Abschnitt 7), der Rest noch nicht.** Sasha hat am 06.10. gesagt: erst aufräumen, dann vor dem
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
| **6 Projekte** ✔ 07.10. | Projekt-Ordner, Zuordnung Gespräch→Projekt | erst wenn 2–4 stehen | mittel |
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

## 6b. Ausblick: ZENTRALE Code (nicht bauen — Richtung für die Architektur)

Sasha, 07.10.2026: „ich denke wir sollten generell eine eigene zentrale code
machen quasi. mit eigenem prompt und der umgebung die es ja schon gibt …
claude code is ja auch total spezialisiert auf richtig coding, ganz anders als
der normale chat" — und gleich danach: „erstmal sauber den assistant aufziehen
… bevor wir die code ai großziehen. das is nur damit du so den grand scope im
auge hast."

Was das für alles heißt, was jetzt gebaut wird:

- **Eine zweite Schiene, kein zweites Programm.** Code = eigenes Profil
  (`core/profil/…`, eigener Prompt fürs Programmieren: lesen, planen,
  ändern, testen) + eigener Werkzeugsatz im Register (Schiene `code` neben
  `klein`/`gross`) + derselbe Kern: Gespräche, Gedächtnis, Ablage, Sandbox,
  Erlaubnis-Gate, Anbieter-Wahl. Nichts davon darf heute so gebaut werden,
  dass es nur für den Chat taugt.
- **Oberfläche:** der Schalter Chat ↔ Code oben in der Seitenleiste (wie
  Claude Web, Screenshot `claude_web_template/main.png`).
- **Werkzeuge, die dann dazukommen:** Dateien in einem Projektordner lesen
  und ändern (gegatet), Befehle in der Sandbox mit einer eigenen
  Arbeitskopie des Projekts, Versionsverwaltung nur in dieser Arbeitskopie
  (nie direkt auf Sashas Stand), Tests laufen lassen.
- **Ersetzt `claude -p`** in den Skripten des skill-creator (Testläufe,
  Beschreibung verbessern).
- **Offene Fragen an Sasha (wenn es soweit ist):** Welche Ordner darf es
  anfassen (nur `~/codicus`, `learning/` immer tabu)? Darf es committen und
  pushen oder nur vorschlagen? Darf es ins Netz (Pakete installieren)?

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
- *(Seit dem Abend im Format von Claude, siehe „Skills im Format von
  Claude" unten; `kurz` ist jetzt eine Hausregel.)*
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

### Phase 6 — Projekte (2026-10-07)

Ausführlich: [projekte.md](projekte.md). Kurz:

- **Speicher** `core/projekte.py` (Schicht 2): `data/gedaechtnis/projekte/<id>/`
  mit `projekt.json`, `anweisungen.md`, `wissen/`. Anlegen, Liste, finden,
  laden, Anweisungen (atomar, `.bak`, `stand`), Wissen aus Text oder Datei
  (Sperrliste `context.anhang_gesperrt` wie bei Anhängen: Zugangsdaten,
  gesperrte Ordner wie `learning/`, ZENTRALEs `data/`; nur Text), archivieren — nie löschen. Nicht in
  `gedaechtnis.BEREICHE` (Konstante `gedaechtnis.PROJEKTE`).
- **Gespräch → Projekt**: `kopf.json` → `projekt`;
  `gespraeche.projekt_setzen/projekt_von`, `liste(projekt=)`; `/neu` bleibt
  im Projekt (`neu_projekt` pro Rechner im `_knoten`-File).
- **Prompt**: `projekte.prompt_block(id)` im festen Kopf
  (`cloud._static_system(…, projekt=)`, hinter Gedächtnis und Skills, nur
  `MERKMALE["projekte"]` = `gross`). Das Projekt kommt als Parameter
  (Route → `kern.chat(projekt=)` → Cloud-Weg). Keine neue Meta-Regel.
- **Werkzeuge**: `read_project_file(name, ab?)` (nur `gross`, frei, nur das
  Projekt des Zugs über `@braucht_projekt`), `search_chats` mit optionalem
  `projekt`. Schnappschuss neu gezogen: nur der neue Eintrag und der neue
  Parameter, `klein` byte-gleich. Eigener Text-Deckel < 200 Zeichen.
- **Routen** `ui/routen/projekte.py`: Liste, anlegen, laden, Anweisungen PUT
  (409), Wissen, archivieren, zuordnen; `/api/chat/clear {projekt?}`,
  `/api/gespraeche?projekt=` + `projekt_name`/`neu_projekt`.
- **TUI** `tui/ansichten/projekte.py`: `/projekt` (Auswahl/Name/neu/kein),
  `/projekte` (Übersicht, Editor, Wissen per Pfad, neues Gespräch im
  Projekt), Kasten-Titel „Projekt · Gespräch", Projektname in der
  Gesprächsliste.
- Tests: `test_projekte.py`, `test_projekte_routen.py`,
  `test_projekte_ansicht.py`, Wächter; headless `ki_projekte` 80×24/136×30.

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| Projekte unter dem Gedächtnis, aber **nicht in `BEREICHE`** (wie Skills) | als Bereich (dann schriebe `write_note` ungefragt in Anweisungen, und alle Projekte stünden als Titel in jedem Kopf) |
| id = **Slug des Namens**; Name umbenennen gibt es (noch) nicht | zufällige id + freier Name (umbenennbar, aber Ordner unlesbar) |
| Projekt-Block **hinter Skills, vor dem Imprint** | vor dem Gedächtnis-Kopf (dann stünden Projekt-Anweisungen vor Sashas Hausregeln, die Vorrang haben sollen) |
| **Keine Meta-Regel**; der Block erklärt sich („gelten zusätzlich; Hausregeln gehen vor") | eine Meta-Regel in `gross.system()` (dort fehlen ~26 Zeichen bis zur Grenze) |
| Anweisungen im Kopf **≤ 4.000 Zeichen**, Datei ≤ 20.000, Rest per `read_project_file("anweisungen")` | ganz in den Kopf (teuer bei jedem Cache-Write) / hart abweisen |
| Projekt als **Parameter** durch `kern.chat` → Cloud-Weg → Ausführer (`@braucht_projekt`) | `gespraeche.aktiv()` wie bei `search_chats` (globaler Zustand; ein Erinnerungs-Zug bekäme das Projekt des offenen Gesprächs) |
| `read_project_file` **ungegatet** (nur lesen, nur dieses Projekt) | gegatet |
| `read_project_file` liefert **20.000 Zeichen je Aufruf**, weiter mit `ab` | ganze Datei (bis 200.000 Zeichen in einem Werkzeug-Ergebnis) |
| Wissen **nur Text**; PDF/Bild abgewiesen | PDF wie `dokument_holen` extrahieren (später möglich) |
| Wissen-Sperre = **dieselbe wie für Anhänge** (`context.anhang_gesperrt`, Phase 5) — eine Sperrliste, keine zweite | `context.erlaubt` (dann gingen nur Dateien unter `~/codicus`, nicht aus Downloads) / eigene Liste |
| Gleicher Wissens-Name **ersetzt, alte Fassung `.bak`** | Fehler „gibt es schon" / Nummer anhängen |
| Backend liest den Pfad; **fehlt er dort, schickt die TUI den Text** (Sperre prüft trotzdem den Pfad) | nur Backend (Laptop gegen PC-Backend ginge nicht) / immer die TUI (Secret-Inhalt ginge erst über die Leitung) |
| `/neu` aus einem Projekt **bleibt im Projekt**, vorgemerkt **pro Rechner** im `_knoten`-File bis zum ersten Senden | neues Gespräch sofort anlegen (leere Ordner im Sync) / ohne Projekt |
| `/projekt <name>` ordnet nur **bestehende** zu; anlegen nur mit `/projekt neu <name>` | unbekannter Name legt an (ein Tippfehler erzeugte ein Projekt) |
| `kein`/`aus`/`neu` (u. a.) als Projektnamen **reserviert** | Sonderzeichen-Syntax (`/projekt -`) |
| Übersicht als **eigene Überlagerung** `projekte.py` | Abschnitt der Gedächtnis-Ansicht (zweite Ebene + Eingabefelder wären dort Sonderfälle in jedem Zweig) |
| „Erinnerungen" **gehört zu keinem Projekt** | frei zuordenbar |
| Archiviertes Projekt: Gespräche **behalten** Zuordnung **und** Block | Block entfällt mit dem Archivieren |
| `search_chats(projekt=…)` lässt das **alte Transkript weg** | Transkript immer mit (kennt keine Projekte) |
| Sichtbar: „projekt", „anweisungen", „wissen", „kein projekt" | „Kontext", „Knowledge" (Claude-Web-Wörter) |

**Offen:** Projekt umbenennen; Wissen entfernen (ginge nur als „aus" mit
Flag, nie löschen); PDFs als Wissen; die KI kann keine Projekte anlegen
oder Anweisungen vorschlagen (bewusst — Sasha pflegt sie); Projekt-Block
für das lokale qwen (erst messen).


### Nachbesserungen nach Sashas Durchsicht (2026-10-07, Backend)

Sashas Worte vom 07.10. und was daraus gebaut ist (TUI-Teil — Esc/Strg+C,
`\`-Umbruch, Eingabe-Grenze mit Zähler, Fußleiste — baut ein eigener Strang):

- **Erlaubnis mit Geltung** („beides einstellbar machen"): Knöpfe „ja, nur
  dieses mal" / „ja, für dieses gespräch" / „ja, immer" / „nein"
  (`core/erlaubnis.py`, Register-Felder `immer_erlaubbar`, `nur_einmal`,
  `alltag`). Gespräch = bis das Gespräch wechselt (Gesprächs-id über
  `core/zug.py`, nur im Speicher); immer = `ai_config` `immer_erlaubt`;
  `/erlaubnis` im Chat listet und nimmt zurück (`/api/erlaubnis`). Kein
  „immer" für Kernakten, Löschen/Überschreiben und `save_from_sandbox`.
  Details: [ki_system.md](ki_system.md), „Geltungsbereiche".
- **/modell zeigt alles** („alle die available is"): `core/modell_liste.py`
  holt die Liste vom Anbieter, 24 h Cache pro Rechner unter `~/.cache`,
  Rückfall `providers.py`, nur Chat-Modelle (Wortliste). In der TUI-Auswahl
  filtert Tippen. Preise: Datums-Fassungen finden ihren Grundpreis,
  opus/fable den Familienpreis, sonst vorsichtig; Hinweis im Log.
- **Budget 0–100 €** (`ki_einstellungen.BUDGET_HOECHSTENS`).
- **20.000 Zeichen kommen an**: `cloud.kappen` mit zwei Grenzen
  (`nutzer_msg_chars` 20.000 für Sashas Nachrichten, `cloud_msg_chars` 4.000
  für alte KI-Antworten), Vermerk „[… N Zeichen gekürzt …]"; `/api/chat`
  lehnt Längeres mit Klartext ab.
- **Gestoppt bei OpenAI-kompatiblen Anbietern wird gebucht** — geschätzt
  (Zeichen / 3,5), als `geschaetzt` markiert, mit Log-Zeile.
- **Sandbox**: Stoppen tötet einen laufenden `run_code` sofort („vom Nutzer
  gestoppt"); länger als 2 min (bis 30) nur nach eigener Frage mit der
  Dauer, nur „einmal"; `save_from_sandbox` gegatet, nur auf Sashas Wunsch;
  das Modell erfährt PIL, bs4, lxml, yaml (kein numpy/pandas).
- Schnappschuss neu gezogen: `run_code` (Beschreibung + Parameter
  `zeitlimit`) und `save_from_sandbox` (Beschreibung, jetzt gegatet);
  `klein` byte-gleich.
- Tests: `test_erlaubnis_geltung.py`, `test_erlaubnis_tui.py`,
  `test_modell_liste.py`, `test_stoppen_buchen_laenge.py`, Wächter.

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| Geltung **pro Werkzeug** („run_code immer" = jedes Programm bis 2 min) | pro Argument/Befehl wie Claude Code (bei frei geschriebenem Code nicht sinnvoll prüfbar) |
| „Für dieses Gespräch" **nur im Arbeitsspeicher**, Neustart fragt wieder | auf der Platte pro Gespräch (überlebte Neustarts, wäre aber eine stille Dauer-Erlaubnis) |
| Gesprächswechsel = jedes Öffnen eines **anderen** Gesprächs (auch hin und zurück) | erst beim nächsten Senden in einem anderen Gespräch |
| „Immer" in `data/ai_config.json` — **synct** auf alle Rechner | pro Rechner (dann fragt der Laptop, was der PC schon darf) |
| Kein „immer" auch für `fetch_document` (gleicher Name überschreibt) und `edit_calendar_routine` (auch ändern) | nur für echtes Löschen |
| „Für dieses Gespräch" **bleibt** bei Kernakten/Löschen erlaubt | dort nur „einmal" |
| Knöpfe „ja, nur dieses mal / ja, für dieses gespräch / ja, immer / nein" — j/n/Esc wie bisher | eigene Tasten (e/g/i) |
| Ein altes „ja" (alter Client) = **einmal** | ablehnen (400) |
| Modell-Cache unter **`~/.cache/zentrale/modelle.json`**, pro Rechner | `data/` (synct sinnlos, zwei Rechner überschreiben sich) |
| Fehler beim Holen **10 min gemerkt** | jedes Mal neu versuchen (offline wartet /modell 6 s) |
| Chat-Filter per **Wortliste** im Namen | Felder der Anbieter (uneinheitlich, fehlen oft) |
| Unbekanntes Modell: **Sonnet-Preis**, opus/fable **Familienhöchstpreis** | immer den teuersten Preis der Tabelle (Budget-Deckel griffe bei billigen Qwen-Modellen 50× zu früh) |
| Zu lange Nachricht: **400 mit Klartext** | annehmen und mit Vermerk kürzen |
| Schätzung **3,5 Zeichen je Token**, Denken und halbe Werkzeug-Aufrufe zählen mit | nur Eingabe buchen |
| Anthropic beim Stopp **unverändert** (Eingabe + Cache, halbe Ausgabe nicht) | Ausgabe auch dort schätzen |
| run_code-Stopp: Signal alle **0,1 s** geprüft | eigener Wächter-Thread |
| Lange Läufe bis **30 min** | 10 min / unbegrenzt |
| Lokal (Ollama) **nicht** gekappt; `num_ctx` 8.192 Token begrenzt | lokal eigene Grenze |

**Offen:** Fähigkeiten im Kopf — `gross.system()` hat keinen Fähigkeiten-
Block (Budget fast voll, 4.974/5.000); was die KI kann, steht in den
Werkzeug-Beschreibungen (Sandbox, Ablage, Skills, Suche, Projekte je dort).
Anhänge brauchen kein Werkzeug, sie stehen als Blöcke in der Nachricht.

### Skills im Format von Claude + Skills von Anthropic (2026-10-07, abends)

Sasha: Claudes Skill-Format übernehmen (echte Claude-Skills ohne Umbau
hineinkopieren), die offenen Skills von Anthropic übernehmen, `kurz` ist kein
Skill („skills sind eher komplexere abläufe"), `recherche` ist ein Kandidat
zum Ersetzen (Claude im Web recherchiert selbst). Ausführlich:
[gedaechtnis_dateien.md](gedaechtnis_dateien.md) „Skills",
[ki_system.md](ki_system.md) „Skills" und „Sandbox".

- **Format** (`core/skill_format.py`, Schicht 2): Ordner `<name>/` mit
  `SKILL.md` (YAML-Kopf `name`, `description`, fremde Felder erlaubt) und
  optional `scripts/`, `references/`, `assets/`. ZENTRALEs Angaben (status,
  herkunft, erstellt, braucht, vermerk, quelle) in `<name>/_zentrale.json`.
- **Prompt-Liste** = name + description, je ≤ 1.024, ganze Liste ≤ 6.000
  Zeichen. Start: ~4.300. *(Bis 08.10. darüber gleichmäßig gekürzt; seitdem
  siehe „Nachbesserungen 08.10." unten.)*
- **`load_skill(name, datei?, ab?)`**: Anleitung + Dateiliste, Dateien aus
  dem Skill ohne Pfad-Ausbruch, seitenweise 20.000 Zeichen.
  **`run_code(skill=…)`**: Skill-Ordner nur lesend unter `/skills/<name>`.
  `propose_skill`/`edit_skill` schreiben Claude-taugliche SKILL.md, edit
  behält den Kopf wörtlich. Schnappschuss neu gezogen: nur `load_skill`,
  `propose_skill`, `run_code` (Beschreibung/Parameter), `klein` byte-gleich,
  Gate und Fragen unverändert.
- **Umzug** (`core/skill_umzug.py`, Schicht 2) bei jedem Zugriff, alte
  Dateien nach `skills/_alt/`, nichts gelöscht; `kurz` → Hausregel (über
  `kernakte_schreiben`, `.bak`, einmal) + aus; `recherche` mit Vermerk.
- **Anthropic**: 14 Skills (nur Apache 2.0, Commit 683bc88) in
  `core/skill_vorlagen/anthropic/` mit `README.md` (Quelle, Lizenz,
  Änderungen) und `THIRD_PARTY_NOTICES.md`; Erstbefüllung je Skill, nie
  überschreibend, alt datiert. skill-creator bekam `references/zentrale.md`.
- **TUI** (nur `tui/ansichten/gedaechtnis.py`): „von anthropic", Zeilen
  „braucht: …" und „hinweis: …".
- Tests: `test_skills.py` (neu), `test_skill_format.py`,
  `test_skill_umzug.py`, `test_skill_skripte.py` (quick_validate.py echt in
  bwrap), Wächter in `test_keine_seiteneffekte.py`; `test_kern_bauplan.py`
  überspringt `core/skill_vorlagen/` (fremder Code, nie importiert).

Start-Status der Anthropic-Skills (aus `core/skill_vorlagen/anthropic/zentrale.json`):

| Skill | Status | Warum |
|---|---|---|
| skill-creator | an | Sasha: an. Skripte ohne `claude`/Netz laufen in der Sandbox (geprüft: quick_validate, package_skill); Rest steht in `references/zentrale.md` |
| academy-guide | an | braucht nur `fetch_url` (Academy-Katalog lesen) — hat ZENTRALE |
| claude-api | an | Nachschlagewerk; Text, eigene Dateien per `load_skill(datei=…)` (SKILL.md ist 103 KB → 6 Seiten) |
| discernment-nudge | an | reine Antwort-Anleitung (2–3 Rückfragen nach gewichtigen Antworten), braucht nichts |
| frontend-design | an | Gestaltungs-Anleitung für Code/Text; braucht nichts |
| internal-comms | an | Text-Vorlagen (`examples/`), braucht nichts — inhaltlich für Firmen gedacht |
| algorithmic-art | aus | Ergebnis ist eine HTML-Seite mit p5.js aus dem Netz → Browser zum Ansehen |
| brand-guidelines | aus | Farben/Schriften für Folien und Seiten — die Ablage kann nur Text |
| canvas-design | aus | Bildausgabe PNG/PDF (Schriften liegen bei), nichts zum Ansehen |
| mcp-builder | aus | MCP gibt es noch nicht; Node/npm und Internet beim Bauen |
| slack-gif-creator | aus | Slack, GIF-Ausgabe, numpy/imageio fehlen in der Sandbox |
| theme-factory | aus | Folien/Seiten mit Farben und Schriften, `theme-showcase.pdf` zeigen |
| webapp-testing | aus | Playwright-Browser und Netz zur Seite — Sandbox hat beides nicht |
| web-artifacts-builder | aus | Node/npm/pnpm mit Internet, Browser zum Ansehen |

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| ZENTRALE-Felder in **`_zentrale.json` je Skill-Ordner** | eine zentrale Statusdatei (Sync „neueste gewinnt" verlöre Schalter, die auf zwei Rechnern umgelegt wurden) |
| Skill **ohne `_zentrale.json` = an** (hineinkopiert = gewollt) | = vorgeschlagen (Sasha müsste jeden kopierten erst einschalten) |
| `load_skill` mit Parameter **`datei`** (+ `ab`) | eigenes Werkzeug `read_skill_file` (größeres Schema im Kopf, ein Werkzeug mehr zum Verwechseln) |
| Skill-Ordner in der Sandbox unter **`/skills/<name>`** | `/skill` (package_skill.py benennte das Paket dann „skill") |
| `run_code(skill=…)` nur für **aktive** Skills | jeder Skill (dann liefen Skripte eines abgeschalteten) |
| Listen-Deckel **6.000 Zeichen**, Kürzen gleichmäßig, dann nur Namen | kein Deckel (jeder kopierte Skill machte jeden Zug teurer) / ältere zuerst weglassen (nicht deterministisch über Rechner) |
| Anleitung **≤ 20.000** Zeichen für propose/edit (eine `load_skill`-Seite) | 6.000 wie bisher (Claude empfiehlt < 500 Zeilen; der skill-creator schriebe sonst keine üblichen Skills) |
| `description` mit **`<` `>` abgelehnt** | durchlassen (dann fiele der Skill durch Claudes Prüfung) |
| `edit_skill` ändert **nicht** die description | mit optionalem `beschreibung` (Sasha bestimmt bisher den Auslöser) |
| Erstbefüllung **je Skill** (fehlender Ordner → nachliefern) | nur bei ganz fehlendem Ordner (dann kämen die Anthropic-Skills auf Sashas Rechnern nie an) |
| Anthropic-Skills **unverändert** im Repo, Status in `anthropic/zentrale.json`; einzige Zutat `skill-creator/references/zentrale.md` | `_zentrale.json` in jeden Vorlagen-Ordner (Vorlagen wichen vom Original ab) / Hinweis als zweiter Ordner, beim Kopieren drübergelegt (mehr Mechanik) |
| Alles übernommen inkl. **Schriften von canvas-design** (Repo +8,7 MB, Daten +8,7 MB je Rechner) | Schriften weglassen (Skill wäre nicht mehr „ohne Umbau"; ist ohnehin aus) |
| `test_kern_bauplan` überspringt `core/skill_vorlagen/` | Anthropic-Code als Riesen-Altlast eintragen (er ist kein Kern-Code) |
| `load_skill` weist vorn auf **`references/zentrale.md`** hin, wo vorhanden | SKILL.md des skill-creator ändern (dann nicht mehr Claude-gleich) |
| Umzug bei **jedem Zugriff** (billig), alte Dateien nach **`_alt/`**, gleiche Fassung ersetzt gleiche, andere bekommt `.2` | einmal mit Merker (der Sync brächte alte Dateien trotzdem zurück) / umbenennen an Ort und Stelle (`kurz.md.alt` läge zwischen den Skills) |
| Neue Dateien tragen die **Zeit der alten Datei** | jetzt (ein später umziehender Rechner überschriebe Sashas Schalter) |
| `kurz` → Hausregel **nur, wenn kurz an war** | immer (ein abgeschalteter Stil würde über die Hausregel wieder wirksam) |
| Hausregel-Text: „Bin ich im Stress, unterwegs oder sag „kurz": Antwort zuerst, in ein bis drei Sätzen, eine Sache nach der anderen, höchstens eine Rückfrage." | die ganze alte Anleitung (fünf Punkte) als Regel |
| Ein-Zeilen-Herkunft „**von anthropic**", Vermerk als „**hinweis:**" | eigene Spalte / „vermerk" (kein Alltagswort) |
| YAML: **PyYAML wenn da**, sonst eigener kleiner Leser | nur PyYAML (steht nicht in requirements.txt; der Pi könnte es nicht haben) / nur eigener Leser (weicht bei Sonderfällen von Claude ab) |

**Offen:** Die KI kann nur die SKILL.md schreiben — keine `references/`
oder `scripts/` (der skill-creator sagt es ihr in `references/zentrale.md`).
Beschreibungs-Optimierung des skill-creator braucht einen eigenen Weg statt
`claude -p` („ZENTRALE Code"). `discernment-nudge` greift nach fast jeder
gewichtigen Antwort (ein `load_skill` je Gespräch) — beobachten, ob Sasha
das will. `internal-comms` ist für Firmen geschrieben; an, weil nichts
fehlt, aber vielleicht unnütz. Die alten Dateien in `skills/_alt/` kann
Sasha irgendwann wegwerfen, wenn beide Rechner umgezogen sind.

### Nachbesserungen nach Sashas Durchsicht — TUI (2026-10-07)

Ausführlich: [../system/tui_bauplan.md](../system/tui_bauplan.md),
„Nachbesserungen nach Sashas Durchsicht" und „Fußleiste". Kurz:

- **Esc schließt** den Chat immer, die Antwort läuft weiter (● an der
  Leertaste der Startseite, wenn sie bei geschlossenem Fenster fertig wurde);
  **Strg+C stoppt** (curses jetzt im raw-Modus; außerhalb des Chats beendet
  Strg+C die TUI wie vorher, im Chat nie).
- **`\` + Enter** = neue Zeile, `\\` + Enter = ein `\` und senden.
- **Eingabe bis 20 000 Zeichen**, Zähler ab 80 %, an der Grenze deutliche
  Meldung samt Zahl der nicht übernommenen Zeichen; Einfügen wird als ein
  Stoß gelesen (ein Zeilenumbruch darin schickt nicht mehr ab).
- **Befehle und Tasten englisch** (`/new /chats /model …`, „esc close ·
  ctrl+c stop"); die deutschen Befehle gehen still weiter. Inhaltliche
  Hinweise bleiben deutsch.
- **Fußleiste zeigt nur, was wirkt**: je Fenster/Überlagerung aus `CTX_KEYS`
  bzw. `tasten()` der Ansicht; `tests/test_fussleiste.py` drückt jede
  beworbene Taste in der echten TUI ohne Bildschirm.

### Frontend nach dem Vorbild von Claude Web — TUI (2026-10-07)

Sasha: „das frontend für unsere ki soll lowk auch einfach claude web grad
kopieren … nur dass man halt mit maus UND tastatur navigieren könnte."
Ausführlich: [../system/tui_bauplan.md](../system/tui_bauplan.md), „Chat wie
Claude Web"; Pixelstil: [../system/pixelstil.md](../system/pixelstil.md).

- Im Chat-Kasten: **Seitenleiste** (Search, New, Projects, Files, Customize,
  Gespräche nach Today/Yesterday/Datum; Tab auf/zu), **Verlauf** wie Claude
  (Schritte „Used … ›", Denken eingeklappt, copy · retry), **Eingabekasten**
  mit „Reply", Anhang-Kärtchen, „+ attach", Modell · Effort, **rechts** ein
  Dokument (▾ Fassungen, groß, zu) oder „Outputs" mit „Used in this session",
  **Customize** (Skills, Memory, Usage, Capabilities, Permissions, Model).
- **Maus** (Klick, Rad) nur im offenen Chat, Shift + Ziehen markiert weiter;
  Fokuswechsel F6; Strg+O/P/T/U/N.
- **Denk-Adern**: Spiralen mit eingerollten Windungen wachsen aus dem Kern,
  solange sie denkt, pulsieren nach außen und ziehen sich beim ersten Text
  zurück (`tui/ansichten/denkadern.py`).
- Backend dazu: `/api/ai/kosten`, `/api/ai/werkzeuge` (nur lesen), Ergebnis
  eines Werkzeugs gekürzt im Verlauf (`werkzeuge[].ergebnis`).
- Nicht gebaut: ~~👍/👎 (das Backend kennt keine Bewertung)~~ — seit
  08.10. gebaut, siehe „Bewertungen" unten; Zeitstempel beim
  Darüberfahren (braucht Bewegungsmeldungen der Maus — kosten Akku), „Code"-
  Schalter oben (nur als Platz gedacht, wie gewünscht).

### Nachbesserungen 08.10.2026 (Symbole, Skill-Liste, Stopp bei Claude)

- **Symbole der Seitenleiste** waren nicht zu erkennen (3×1 Felder = 6×3
  Pixel). Kurz umschaltbar (Sextanten 4×2 oder ein Zeichen), nach Sashas
  Bildvergleich am selben Tag entschieden: **Braille, 4 Felder × 2 Zeilen =
  8×8 Punkte** (Lupe, Plus, Ordner, Blatt, Zahnrad, Leiste); Umschaltung
  `tui_symbole` und Customize → Appearance wieder entfernt. Regel und Warum
  in [../system/pixelstil.md](../system/pixelstil.md). Das Blatt hinter
  Gesprächen mit Dokument ist ▤.
- **Skill-Liste**: Beschreibungen vollständig, Hinweis „Liste zu lang" in
  Customize → Skills, Kürzen nur noch als letzte Rettung und nur die
  längsten (ki_system.md, „Skills").
- **Stopp bei Claude** bucht die bis dahin erzeugte Ausgabe geschätzt mit
  (ki_system.md, „Gestoppt = geschätzt gebucht").
- **Offen, für später:** bei sehr vielen Skills ein Werkzeug „Skill suchen"
  statt einer langen Liste im Kopf.

### Skill `import-memory` — Erinnerungen aus einer anderen KI (2026-10-08)

Sasha: seine Erinnerungen aus Claude (ggf. ChatGPT/Gemini) nach ZENTRALE
holen, als Vorbereitung für den Umzug. Vorlage war Claudes eingebauter Skill
gleichen Namens, sinngemäß für ZENTRALE neu geschrieben. Ausführlich:
[gedaechtnis_dateien.md](gedaechtnis_dateien.md), „Import aus einer anderen KI".

- **Skill** `core/skill_vorlagen/import-memory/`: `SKILL.md` (deutsch,
  Ablauf in sechs Schritten + Regeln) und `references/` (Export-Text für die
  andere KI, Datenschutz-Filter, Abbildung auf ZENTRALEs Gedächtnis).
  Erstbefüllung wie die anderen eigenen Skills, an, `herkunft: zentrale`
  (neu; TUI zeigt „mitgeliefert"), ehrlicher `quelle`-Vermerk.
- **Werkzeug-Lücke geschlossen** mit einem Parameter statt eines neuen
  Werkzeugs: `write_note(…, herkunft)` → `gedaechtnis.import_ergaenzen` —
  zeilenweise nur Neues (Dubletten auch in anderer Schreibweise), Vermerk
  `[import <herkunft> <Datum>]` vom Code, nie Kataloge/Tagebuch, keine
  Link-Zeilen, ≤ 30 Zeilen je Aufruf, atomar. Kernakten über das
  vorhandene Gate (Frage nennt Herkunft und Zeilen).
- **Schnappschuss** neu gezogen: nur der `write_note`-Parameter auf `gross`
  (+217 Zeichen), `klein` byte-gleich, Gate und Fragen der Schnappschuss-
  Argumente unverändert. Textbudget: eigener Deckel < 200 Zeichen für die
  Parameter-Beschreibung (`tests/test_profil.py`).
- **Probelauf** mit erfundenem Export und gefälschtem Modell
  (`tests/test_import_memory.py`, `tests/fixtures/import_memory_beispiel.txt`).
- **Offen:** ein „Import-Modus", der `rewrite_note`/`edit_skill` während
  eines Imports verweigert (beide fragen ohnehin jedes Mal).

### Morgenblick (2026-10-08)

Nach dem Vorbild von Claudes „morning", in ZENTRALEs Form; nur auf Abruf
(`/morning` im Chat). Ausführlich:
[../werkzeuge/morgenblick.md](../werkzeuge/morgenblick.md).

- `core/morgenblick_daten.py` (Schicht 2): Sammler je Quelle (Kalender über
  die Fassade, Mail aus dem lokalen Triage-Stand, Erinnerungen, Gespräche,
  Listen, Projekte, Ablage) — nur lesen, kein Netz; neue Quelle = ein
  Eintrag. Form HEAVY/NORMAL/OPEN und die drei Akte deterministisch.
- `core/morgenblick.py` (Schicht 3): billiges Modell schreibt Sätze als JSON
  (Daten in `<daten>`, nie Anweisung), ohne Cloud feste Sätze; signierte
  Knöpfe → `GET /api/morgenblick/auftrag` legt ein Gespräch mit dem Auftrag
  als Vorschlag an (nur localhost).
- `core/morgenblick_bild.py` (Schicht 2): HTML aus Python, alles escaped,
  Gelände-SVG, Fraunces eingebettet (`core/morgenblick_assets/`, OFL).
- Ablage: Art `html`, `GET /api/ablage/<id>/roh` mit strenger CSP.
- TUI: `chat_morgenblick.py`, eine Zeile in `Chat.befehl`.
- Offen: „wartet auf Antwort" (Rückfall ungelesen 2 Tage), Fälligkeit in
  Listen, Chat-Quellen (Slack/Teams) möglich später.

### Bewertungen (2026-10-08)

Sasha: „bewertungen für uns um unser eigenes system zu verbessern.. ja safe.
machs rein, so dass ich nen kommentar hinzufügen könnte wenn ich wollte. also
am besten einfach so n kleines modal das aufgeht." Wofür und was nicht:
[ki_system.md](ki_system.md) „Bewertungen"; Bedienung:
[../system/tui_bauplan.md](../system/tui_bauplan.md) „Bewerten".

- **Speicher** `core/rueckmeldungen.py` (Schicht 2):
  `data/rueckmeldungen/<rechner>.jsonl`, je Bewertung ein Ereignis {id, ts,
  knoten, gespraech, nachricht, wert ±1, kommentar?, anbieter, modell,
  werkzeuge, skills}; ändern = neues Ereignis, das letzte gilt; nie löschen.
  Umlenkbar per `rueckmeldungen_dir` (Env `ZENTRALE_RUECKMELDUNGEN_DIR`),
  gitignored, in der Datensicherung (`data/rueckmeldungen/*.jsonl`).
- **Routen** (in `ui/routen/gespraeche.py`): `POST /api/rueckmeldung`,
  `GET /api/rueckmeldungen[?gespraech=]` mit Gesprächstitel und Ausschnitt.
- **TUI**: „copy · retry · good · bad" unter jeder Antwort, kleines Fenster
  mit Kommentar (`tui/ansichten/bewertung.py`), Customize → Feedback.
- Tests: `test_rueckmeldungen.py`, `test_bewertung_tui.py`,
  `test_chat_web.py`, `test_fussleiste.py` (neue Zustände), Wächter in
  `test_keine_seiteneffekte.py`; headless `ki_bewertung` 80×24,
  `ki_bewertung_breit` 136×30.

Angenommen (Sasha war nicht erreichbar) — die Kleinentscheidungen:

| Wahl | Alternative |
|---|---|
| Wörter **„good · bad"**, bewertet „good ✓" / „bad ✗" | 👍/👎 (zwei Spalten breit, verschöben die Klickflächen) / ▲▼ (in Unicode „mehrdeutig" breit) |
| **Esc bricht ab** und speichert nichts | Esc speichert ohne Kommentar (ein Fehlklick hinterließe eine Bewertung) |
| Enter speichert **auch ohne Kommentar** | Kommentar Pflicht |
| **Tab** wechselt im Fenster gut ↔ schlecht | Fenster schließen und den anderen Knopf nehmen |
| Taste **+ / −** im Verlauf, wenn ein Ziel unter einer Antwort gewählt ist | eigene Buchstaben (g/b) — kollidieren mit nichts, sind aber nicht so eindeutig |
| Kommentar höchstens **2.000 Zeichen** | 20.000 wie die Eingabe |
| Nachricht-id über die **Reihenfolge der Antworten** im geladenen Verlauf; fehlt sie, einmal frisch holen | ids in jeden Verlaufseintrag (hätte das Tupel-Format des ganzen Chats geändert) / id im SSE-Ende mitschicken (`ui/routen/ki.py` anfassen) |
| Routen in **`ui/routen/gespraeche.py`** | eigenes `ui/routen/rueckmeldungen.py` (fasst `ui/routen/__init__.py` an, woran parallel gebaut wird) |
| Bewertung einer später **verworfenen** Antwort bleibt, Liste zeigt „(antwort später ersetzt)" | mit dem Verwerfen ausblenden (gerade „schlecht, deshalb retry" ist lehrreich) |
| Skills = was `load_skill` lud und `run_code(skill=…)` nutzte | nur `load_skill` |
| Ausschnitt **beim Lesen** aus dem Gespräch | in der Bewertung mitspeichern (doppelte Kopie privater Antworten) |
| Keine KI liest die Bewertungen (kein Werkzeug, kein Prompt) | ein Werkzeug „read_feedback" (erst wenn Sasha das will) |

**Offen:** eine Bewertung ganz zurücknehmen (nur umdrehen geht);
Einfügen mit Zeilenumbruch ins Fenster; eine Auswertung (z. B. „schlecht je
Werkzeug/Modell") — kommt, wenn genug Bewertungen da sind.
