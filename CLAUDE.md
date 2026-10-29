# ZENTRALE – Entwicklungshinweise für Claude

**Zuerst: das Leitbild** (`memory/leitbild.md`). ZENTRALE ist das Nervensystem
von Sashas Zuhause — sie hört, sieht, spricht und handelt; jede Entscheidung
wird zuerst daran gemessen (Messlatte dort). Hub/Cloud/Apps sind Unterbau.

Event-getriebenes Dashboard mit eigenem KI-Assistenten (Laptop, Linux-PC,
Raspberry Pi; später Handy als weiterer Knoten). Die KI läuft über die
Cloud (Claude, andere Anbieter per Einstellung) mit lokalem Ollama als
Option. Sashas Daten bleiben auf seinen Rechnern; abgeglichen wird heute
noch per rsync, die Mitte ist gebaut und greift erst nach `umstellen mitte`
(`memory/betrieb/abgleich.md`; Fahrplan: `memory/ueberblick.md`). Ein
Gedächtnis, ein Assistent — egal von welchem Gerät.

## Language: English for everything new (Sasha, 2026-10-29 — permanent)

ZENTRALE is meant to be English throughout. **Nothing new is built in German.**

- **New code is English:** identifiers, file and module names, comments,
  docstrings, log messages, test names, commit messages, new `memory/` docs.
- **No hard-coded UI text.** Every string a human sees (TUI, phone app,
  notifications, CLI output, KI-facing UI labels) goes through a translation
  table so more languages can be added later. German stays the first UI
  language for Sasha. Use the platform standard, no own format: Flutter
  `gen-l10n` with ARB files (`mobile/`), Python `gettext` (`.po`) for core/TUI/CLI.
  One table per app/front.
- **Existing German stays until a dedicated renaming wave** (a planned, large
  agent run). Until then: when touching old German code, don't extend it in
  German — new functions/fields next to it are English; don't rename old
  things piecemeal unless that is the task.
- Conversation language with Sasha and the KI's answers to him stay German —
  that is content, not code.

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
  newest-wins, Push-on-write — der rsync-Weg, heute noch Vorgabe):
  `memory/system/topologie.md`; der Weg über die Mitte (gebaut, aktiv erst
  nach `umstellen mitte`): `memory/betrieb/abgleich.md`.

## Tests — Regeln (Anlass 10.10.2026)

Die volle Suite brauchte 16+ min, etwa die Hälfte davon durch eine schlechte
Fixture-Architektur: 8 autouse-Fixtures riefen bei jedem Test
`tmp_path_factory.mktemp()` — jeder Aufruf liest den ganzen Basetemp-Ordner,
die Kosten wuchsen quadratisch. Das darf nicht wieder passieren:

- conftest-Autouse-Fixtures nehmen `_test_ordner` + `_frisch()`, nie
  `tmp_path`/`tmp_path_factory`; `mktemp` nie im Funktions-Scope
  (Wächter: `tests/test_testarchitektur.py`).
- PTY-Tests warten auf den Schirm (`warte_auf`/`warte_auf_antwort` in
  `tests/_tui_fuzz.py`), keine festen Sleeps.
- Parametrize nur für Fälle, die einzeln etwas bedeuten; keine Regex über
  eingebettete Blobs; `kalender_beide` nur an Tests mit Kalender-Speicher.

Details, Messwerte, alle Regeln: `memory/betrieb/tests.md`.

**Gefahrzonen** (Fehler, die versteckt wiederkommen — z. B. „heute" nie
einfrieren, immer `core/uhr.py` + Tageswechsel): `memory/system/gefahrzonen.md`.

## Wo die Doku liegt

Die gesamte Projekt-Doku ist modular nach Thema abgelegt im Ordner
`memory/`. Einstieg ist immer das Inhaltsverzeichnis:

→ **`memory/INDEX.md`**

Statt das ganze README/diese Datei zu lesen: über den Index gezielt
das Thema öffnen, das gerade gebraucht wird – das spart Tokens und
hält die Antworten fokussiert.

**KI-Bibel — vor jeder Arbeit an der KI lesen.** Wer am Prompt, an
Werkzeugen, Schienen oder Prüfern baut, liest vorher die betroffenen Einträge
(Einstieg `memory/ki/bibel/README.md`) und stellt danach deren Status um, mit
Commit-Hash.

## Schnell-Zeiger nach Bereich

Die Doku hat seit 2026-08-15 **zwei Ebenen**: `memory/INDEX.md` nennt nur die
Bereiche, jeder Bereich hat einen eigenen Index mit seinen Themen. Nicht hier
nach dem Thema suchen — in den Bereich springen und dessen Index lesen.

| Bereich | Was drinsteht | Index |
|---|---|---|
| KI | denkt: lokal + Cloud, Datei-Gedächtnis (Graph seit 18.08. aus), Tools, Gate, Sprache, Pläne, Benchmarks | `memory/ki/INDEX.md` |
| KI-Bibel | wonach die KI gebaut wird: Regeln mit Quelle und Status (vor KI-Arbeit lesen) | `memory/ki/bibel/README.md` |
| Werkzeuge | tut: Kalender, Mail, News, Notizen, Zyklus | `memory/werkzeuge/INDEX.md` |
| System | gebaut (Kern): Architektur, Schichten, Events, Topologie, API, TUI, Tastatur, Handy | `memory/system/INDEX.md` |
| Hub | Plattform: Hub-Schnittstelle, Apps, Werkstatt, Shop, Desk, Bausteine, Produkt | `memory/hub/INDEX.md` |
| Betrieb | läuft: Setup, Starten, Deployment, Hardware, Sicherheit, Zugriffe | `memory/betrieb/INDEX.md` |
| Maps | seit 2026-10-22 eigene App (Repo `zentrale-karte`), hier nur Zeiger | `memory/maps/INDEX.md` |
| Tutor | seit 2026-10-09 eigene App (Repo `language-tutor`), hier nur Zeiger | `memory/tutor/INDEX.md` |
| Offen | konkrete offene Sachen, eine Datei je Sache (nicht der Tracker) | `memory/open/INDEX.md` |

Flach geblieben: `memory/ueberblick.md` (Einstieg, was ZENTRALE ist) und
`memory/claude_hinweise.md` (Architektur-Entscheidungen für mich).

## Pflege

- Jede strukturelle Änderung (neue Module, umbenannte Dateien, neue
  Features) → das passende `memory/`-File aktualisieren **und** den
  Index des Bereichs prüfen. Der Haupt-Index bleibt unangetastet, solange
  kein neuer *Bereich* entsteht.
- Inhalte gehören in die Theme-Files, nicht in diese Datei und nicht in
  einen Index. Ein Index sagt, WO etwas steht, nie WAS gilt.
- Offenes, das ich finde und nicht selbst erledige → eine Datei in
  `memory/open/` (Regeln: `memory/open/README.md`), nicht in Chat oder
  Gedächtnis.
- Bei Umbenennungen/Verschiebungen: alle Stellen im ganzen Repo mitziehen,
  nicht nur im Index — auch Code-Kommentare zeigen auf `memory/`-Dateien.
