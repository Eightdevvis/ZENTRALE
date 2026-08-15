# ZENTRALE – Entwicklungshinweise für Claude

Event-getriebenes Dashboard (Raspberry Pi + Linux-PC), vollständig
offline. KI läuft lokal via Ollama (Default-Modell: qwen3.5:9b, per
`OLLAMA_MODEL` umstellbar).

## Git-Workflow (gilt für ALLE Agenten — überschreibt die Default-Regel)

Dieses Projekt gehört **einem** Menschen (Sasha), das GitHub-`origin` ist
**privat**. Deshalb gilt hier **nicht** die generische „niemals auf main
mergen / niemals nach origin pushen"-Vorsicht. Der Ablauf ist bewusst
schlank — kein Branch/PR-Zeremoniell:

1. Arbeit im (Harness-erzwungenen) Worktree machen, testen.
2. Committen, dann lokalen `main` per **`git -C <haupt-checkout> merge
   --ff-only <branch>`** vorziehen. Fast-forward hält die History linear.
   Geht kein FF (main ist weitergelaufen) → Commit auf die main-Spitze
   **rebasen**, neu testen, dann ff. Nie `--no-ff`, nie `--force`.
3. **`git push origin main` ist erwünscht, nicht »nur auf Ansage«.** Sasha
   will die Änderungen direkt live auf den anderen Knoten (PC/Pi) anschauen
   können, ohne Umstand — ein normaler ff-Push nach dem Merge ist genau
   dafür da und der Normalfall.

**Die einzigen zwei echten Gefahren** (die bleiben hart tabu):
- **`push --force` / History umschreiben.** Ein normaler Push wird von git
  *abgelehnt*, wenn origin divergierte — das ist der Schutz. Niemals mit
  `--force`/`--force-with-lease` drüberbügeln, das zerstört Historie, auf
  die ein anderer Knoten/Agent baut. Bei Ablehnung: erst `pull --rebase`,
  prüfen, dann normal pushen.
- **Secrets committen.** Ein versehentlich mitcommitteter Key/Token/die
  Mail-Passphrase ist lokal per `reset`/`amend` folgenlos zurückzunehmen —
  einmal bei origin (selbst privat, liegt auf GitHubs Servern) gilt er als
  kompromittiert → rotieren. Deshalb: `data/*.json`, Keys, Passphrasen
  bleiben gitignored (siehe `memory/betrieb/datei_zugriffe.md`). **Der Push selbst
  ist harmlos; gefährlich ist nur, WAS im Commit steckt.** Vor dem ersten
  Push eines neuen Pfades kurz `git status`/`git diff --cached` prüfen.

Alles andere (versehentlich mal einen WIP-Commit gepusht o.ä.) ist bei
einem privaten Solo-Repo folgenlos und leicht per weiterem Commit zu
glätten — kein Grund zur Zurückhaltung.

## Feature-Tracking — die »zentrale«-Liste (pflegt CLAUDE, grundsätzlich)

Die **Feature-Verwaltung des ZENTRALE-Projekts** ist die Liste **`zentrale`**
(id `l_zentrale`, `project: true` → erscheint in der PROJECTS-Box). Sie ist die
**einzige** Liste, die **ich (Claude) pflege**, und liegt **strukturell isoliert**
in einer **eigenen Datei**: `data/features.json`.

- **Zwei-Dateien-Modell (`core/lists.py`):** `data/lists.json` = Sashas private
  Listen, `data/features.json` = der `zentrale`-Tracker (Inhalt pflege ich).
  `_load()` merged beide (TUI + Box sehen alles); `_save()` schreibt jede Liste
  in IHRE Datei und fasst nur die wirklich geänderte an. **Wichtig — kein
  sauberer Besitz-Schnitt:** `features.json` schreiben **beide** — ich den
  Inhalt (Features/Status/done), Sasha aber auch, sobald er ein Feature in der
  TUI als Projekt **flaggt** oder abhakt (`l_zentrale` lebt in dieser Datei).
  Die früher hier behauptete „features.json=Claude, lists.json=Sasha → kein
  Clash"-Logik war **falsch** und hat genau zum Flag-Verlust geführt.
- **Sync (`data/*.json`, nicht in git, siehe `memory/system/topologie.md`):** läuft über
  rsync per SSH, **beide Richtungen vom jeweiligen Knoten aus** (Laptop→`pc`
  via `find-pc`, PC→`0RAMMachine` via `find-0RAMMachine`). Zwei Schutzschichten
  gegen Überschreiben: (1) **`zentrale-push`/`zentrale-pull` sind jetzt
  newest-wins** (`--update` per Default — eine ältere Datei kann eine neuere
  nicht mehr blind überschreiben; `ZENTRALE_SYNC_FORCE=1` für den bewussten
  Holzhammer). (2) **Push-on-write:** das Backend stößt nach JEDER echten
  Daten-Änderung (`core/datasync.py` ← lists/graphs/kalender, `ZENTRALE_AUTOPUSH=1`)
  im Hintergrund `zentrale-push-data` an → der Peer hat sofort den frischen
  Stand, die Divergenz-Zeitfenster sind winzig. Zusätzlich gleicht
  `zentrale-sync-boot` beim Start einmal ab. **Praxis für mich:** vor dem
  Editieren des Trackers `zentrale-pull` (Sashas Stand holen), danach genügt in
  der Regel der Auto-Push; ein manuelles `zentrale-push` schadet nie. NIE mit
  `ZENTRALE_SYNC_FORCE` über frische Peer-Änderungen bügeln.
- **Struktur:** `zentrale` → jedes Kind ist ein **Feature**; die Unterpunkte
  eines Features sind, **was dafür noch offen ist** (Status). Erledigtes wird
  abgehakt (`done: true`); der Status eines Feature-Ordners leitet sich aus
  seinen Blättern ab (`is_done`), die Leiste in der Box zeigt erledigte/alle.
- **Meine Pflicht:** Bei jeder Feature-Arbeit diesen Baum aktualisieren —
  neues Feature als Kind von `zentrale` anlegen, offene Punkte als Unterpunkte
  führen, Erledigtes abhaken, abgeschlossene Punkte sauber halten. Im Stil von
  Sasha: **kurz und kleingeschrieben**, kein Roman — **aber jeder Punkt muss
  beim Drüberlesen für sich verständlich sein**. Sag konkret, WAS offen bzw.
  erledigt ist; kein Insider-Kürzel, kein nichtssagendes Schlagwort
  (»verschachtelt« → »unterprojekte rekursiv verschachtelt anzeigen«). Faustregel:
  Sasha liest die Zeile in drei Monaten ohne Kontext und weiß sofort, was gemeint
  ist. Lieber ein paar Wörter mehr als ein kryptisches Stichwort.
- **Wie aktualisieren (sauber):** über `core/lists.py` (kümmert sich um
  `next_item`/eindeutige ids, Routing in die richtige Datei) — z.B.
  `add_item("l_zentrale", "<text>", parent_iid=…)`, `toggle_item`,
  `rename_item`, `delete_item`, `set_item_project` (ein Feature als Projekt
  flaggen → erscheint im gerahmten `zentrale`-Kasten der Box). Den `zentrale`-
  Knoten **per Name/`l_zentrale`** finden, nicht hart auf Eintrags-ids verlassen.
- **Grenze:** **Alle anderen Listen gehören Sasha** (privat, in `lists.json`).
  Da NICHT reinschreiben, nichts abhaken, nichts umbauen — nur `l_zentrale`.

## Wo die Doku liegt

Die gesamte Projekt-Doku ist modular nach Thema abgelegt im Ordner
`memory/`. Einstieg ist immer das Inhaltsverzeichnis:

→ **`memory/INDEX.md`**

Statt das ganze README/diese Datei zu lesen: über den Index gezielt
das Thema öffnen, das gerade gebraucht wird – das spart Tokens und
hält die Antworten fokussiert.

## Schnell-Zeiger nach Bereich

Die Doku hat seit 2026-08-15 **zwei Ebenen**: `memory/INDEX.md` nennt nur die
Bereiche, jeder Bereich hat einen eigenen Index mit seinen Themen. Nicht hier
nach dem Thema suchen — in den Bereich springen und dessen Index lesen.

| Bereich | Was drinsteht | Index |
|---|---|---|
| KI | denkt: lokal + Cloud, Graph-Memory, Tools, Gate, Sprache, Pläne, Benchmarks | `memory/ki/INDEX.md` |
| Werkzeuge | tut: Kalender, Mail, News, Notizen, Zyklus, Morgen-Messenger | `memory/werkzeuge/INDEX.md` |
| System | gebaut: Architektur, Events, Topologie, API, Dashboard, Tastatur | `memory/system/INDEX.md` |
| Betrieb | läuft: Setup, Starten, Deployment, Hardware, Sicherheit, Zugriffe | `memory/betrieb/INDEX.md` |
| Maps | die Karte: Layer, Quellen-Charta, Design-Brief | `memory/maps/INDEX.md` |
| Tutor | eigenes Projekt in `tutor/` | `memory/tutor/INDEX.md` |

Flach geblieben: `memory/ueberblick.md` (Einstieg, was ZENTRALE ist) und
`memory/claude_hinweise.md` (Architektur-Entscheidungen für mich).

## Pflege

- Jede strukturelle Änderung (neue Module, umbenannte Dateien, neue
  Features) → das passende `memory/`-File aktualisieren **und** den
  Index des Bereichs prüfen. Der Haupt-Index bleibt unangetastet, solange
  kein neuer *Bereich* entsteht.
- Inhalte gehören in die Theme-Files, nicht in diese Datei und nicht in
  einen Index. Ein Index sagt, WO etwas steht, nie WAS gilt.
- Bei Umbenennungen/Verschiebungen: alle Stellen im ganzen Repo mitziehen,
  nicht nur im Index — auch Code-Kommentare zeigen auf `memory/`-Dateien.
