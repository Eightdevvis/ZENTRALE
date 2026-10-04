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

## Feature-Tracking — die »zentrale«-Liste (pflegt SASHA, seit 2026-10-04)

Die Feature-Verwaltung des ZENTRALE-Projekts ist die Liste **`zentrale`**
(id `l_zentrale`, in `data/features.json`, gelesen/geschrieben über
`core/lists.py`). **Sasha pflegt sie allein.** Dass ich dort mitgeschrieben
habe, hat ihn nachhaltig verwirrt.

- **Ich schreibe nicht hinein:** nichts anlegen, abhaken, umbenennen, löschen —
  auch nicht nach Feature-Arbeit. Lesen ist erlaubt (z. B. um offene Punkte
  zu nennen).
- **Nach Feature-Arbeit:** im Chat sagen, welcher Tracker-Punkt jetzt erledigt
  wäre (mit id) — Sasha hakt selbst ab.
- **Ausnahme:** nur wenn Sasha es in einer Session ausdrücklich erlaubt (wie
  beim gemeinsamen Aufräumen am 04.10.2026), und nur für diese Session.
- **Alle anderen Listen** (`data/lists.json`) gehören ohnehin Sasha.
- Technik zum Zwei-Dateien-Modell und zum Sync (`data/*.json` ungetrackt,
  newest-wins, Push-on-write): `memory/system/topologie.md`.

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
| Werkzeuge | tut: Kalender, Mail, News, Notizen, Zyklus | `memory/werkzeuge/INDEX.md` |
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
