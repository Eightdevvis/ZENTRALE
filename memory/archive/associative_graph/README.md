# Archiv: der assoziative Graph (Konzept-Graph, Phase G)

**Stand 2026-10-31:** Der Graph ist **aus dem Code**. Abgeschaltet war er seit
2026-08-18; am 2026-10-31 hat Sasha entschieden, ihn ins Archiv zu legen
([../../hub/kern_auszug_inventur.md](../../hub/kern_auszug_inventur.md),
Abschnitt H). Entfernt: `core/graph.py`, der Extraktor in
`core/consolidation.py`, der Cloud-Embedder in `core/embeddings.py`, die
Schalter `ZENTRALE_GRAPH_KONTEXT` / `ZENTRALE_GRAPH_EXTRAKTION`,
`scripts/graph_cleanup.py` und die Graph-Tests. Der Code steht nur noch in der
Git-Historie: letzter Stand mit Graph ist der Elternteil des Commits
„Archive the concept graph" (`git log --oneline -- core/graph.py`).

- **Was er war:** ein assoziatives Gedächtnis. Ein LLM-Extraktor zog aus jedem
  Zug Konzepte und typisierte Kanten (`Sasha ─[fühlt]─► Krankheit`,
  `Fieber ─[geschah-am]─► 2026-08`), Embeddings fanden die Einstiegsknoten,
  Aktivierungs-Spread über zwei Hops lieferte den Kontext für den Prompt.
- **Warum aus:** Der Extraktor machte aus Fragen Ereignisse und aus
  „vor ein paar Tagen" einen erfundenen Tag (17.08.2026: „bis gestern
  Fieber"); der Kontext wechselte jeden Zug und reiste ungecacht mit. Seit
  2026-08-18 ersetzt ihn das Datei-Gedächtnis
  ([../../ki/gedaechtnis_dateien.md](../../ki/gedaechtnis_dateien.md)).
- **Was blieb:** das Transkript (`core/transkript.py`, geschrieben über
  `core/consolidation.py`, gelesen von `search_chats`) und der lokale
  Embedding-Client `core/embeddings.py` (News, ASCII-Bildsuche).

## Was hier liegt

| Datei | Was | Herkunft |
|---|---|---|
| `konzept_graph.md` | wie der Graph arbeitete: Zeit-Regeln, Alias als Kante, Extraktor, Embeddings, Memory unterwegs | aus `memory/ki/`, verschoben am 2026-10-31 |
| `memory-extraktor.md` | Lesefassung des Extraktor-Prompts | `prompts/memory-extraktor.md`, verschoben am 2026-10-31 |
| `core-ki_selbstbild.md` | kann/kann-nicht-Seed (Graph-Knoten, nie Prompt-Text) | `prompts/core-ki_selbstbild.md`, verschoben am 2026-10-31 |
| `test_graph_memory.py` | Phase-G-Harness, 23 Tests (Seed, Extraktion, Zeit, Spread) | `scripts/test_graph_memory.py`, per `git mv` am 2026-10-14 |
| `gedaechtnis_probe_graph.py` | Graph-Teil der Live-Probe: Graph-Seed, Falle 1 (Fieber/Monat), drei Extraktions-Fallen, wörtlich | aus `scripts/gedaechtnis_probe.py` (Commit 7e9229c) herausgelöst am 2026-10-14 |

Nichts davon läuft. Die Probe in `scripts/gedaechtnis_probe.py` läuft weiter,
mit den Kalender- und Werkzeug-Fallen.

## Daten von Sasha, die nichts mehr liest

Nicht gelöscht, nur nicht mehr gelesen oder geschrieben (Sasha archiviert sie
selbst): `data/ai_graph.json` und `data/ai_graph_cloud.json`. Die rsync-/
Mitte-Abgleiche nehmen sie als gewöhnliche `data/*.json` weiter mit, bis sie
aus `data/` verschwinden.

## Historie

- **2026-10-31** — Graph aus dem Code; `konzept_graph.md` und die zwei
  Prompt-Lesefassungen hierher.
- **2026-10-14** — Ordner angelegt; beide Skripte hierher (Branch `graph-archiv`).
