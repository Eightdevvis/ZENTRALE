# Archiv: der assoziative Graph (Konzept-Graph, Phase G)

**Stand 2026-10-14:** Hier liegen die Testskripte des Konzept-Graphen. Nichts
davon läuft. Der Graph selbst ist seit 2026-08-18 abgeschaltet, sein Code lebt
weiter und ist wieder einschaltbar.

- **Was er war:** ein assoziatives Gedächtnis. Ein LLM-Extraktor zog aus jedem
  Zug Konzepte und typisierte Kanten (`Sasha ─[fühlt]─► Krankheit`,
  `Fieber ─[geschah-am]─► 2026-08`), Embeddings fanden die Einstiegsknoten,
  Aktivierungs-Spread über zwei Hops lieferte den Kontext für den Prompt.
- **Warum aus:** Der Extraktor machte aus Fragen Ereignisse und aus
  „vor ein paar Tagen" einen erfundenen Tag (17.08.2026: „bis gestern
  Fieber"); der Kontext wechselte jeden Zug und reiste ungecacht mit. Seit
  2026-08-18 ersetzt ihn das Datei-Gedächtnis
  ([../../ki/gedaechtnis_dateien.md](../../ki/gedaechtnis_dateien.md)).
- **Wieder einschalten:** Env `ZENTRALE_GRAPH_KONTEXT=1` (Kontext in den
  Prompt, `ki_prompt.GRAPH_KONTEXT`) und `ZENTRALE_GRAPH_EXTRAKTION=1` (neue
  Extraktionen, `consolidation.GRAPH_EXTRAKTION`).

## Was hier liegt

| Datei | Was | Herkunft |
|---|---|---|
| `test_graph_memory.py` | Phase-G-Harness, 23 Tests (Seed, Extraktion, Zeit, Spread); 20 schlagen bei abgeschaltetem Graph fehl | `scripts/test_graph_memory.py`, per `git mv` am 2026-10-14 |
| `gedaechtnis_probe_graph.py` | Graph-Teil der Live-Probe: Graph-Seed, Falle 1 (Fieber/Monat), drei Extraktions-Fallen, wörtlich; Kopfkommentar sagt, wie man sie zurückholt | aus `scripts/gedaechtnis_probe.py` (Commit 7e9229c) herausgelöst am 2026-10-14 |

Die Probe in `scripts/gedaechtnis_probe.py` läuft weiter, mit den Kalender-
und Werkzeug-Fallen.

## Fallen beim Wiederbeleben

- `test_graph_memory.py` rechnet `ROOT` zwei Ebenen über der Datei — von hier
  aus findet es `core/` nicht. Zurück nach `scripts/` legen.
- `temp_graph()` biegt nur `graph._GRAPH_FILE` um. Mit eingeschalteter
  Extraktion schreibt `feed()` die Testsätze ins **echte** Transkript
  (`data/ai_transcripts/`). Vorher Transkript, Gedächtnis und Cloud-Graph
  umlenken wie `sandkasten()` in `scripts/gedaechtnis_probe.py`.

## Wo der lebende Code ist

- `core/graph.py` — Graph, Speicher, Seed, Kontext
- `core/consolidation.py` — Extraktor (`GRAPH_EXTRAKTION`)
- `memory/ki/konzept_graph.md` — wie er arbeitet und warum

## Historie

- **2026-10-14** — Ordner angelegt; beide Skripte hierher (Branch `graph-archiv`).
