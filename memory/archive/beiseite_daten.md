# Beiseite gelegte Daten — `data/_beiseite/`

**Stand 2026-10-06.** Sasha: *„verwaiste dateien erstmal beiseite legen,
auflisten, zählen, wir gucken dann stück für stück durch."* Diese Dateien lagen
in `data/` und werden von keinem Code mehr gelesen oder geschrieben (geprüft
per Suche in `core/`, `ui/`, `tui/`, `tutor/`, `scripts/`, `services/` und
`~/.local/bin`). Gelöscht ist nichts — sie liegen auf diesem Rechner (Laptop)
in `data/_beiseite/`.

⚠ **Der Sync löscht nie** (`zentrale-pull`/`-push` sind nur hinzufügend, siehe
[../system/topologie.md](../system/topologie.md)). Auf dem PC liegen die Dateien
noch in `data/`, und beim nächsten Pull kommen sie hier zurück. Beim
Durchgehen also auf beiden Rechnern entscheiden.

**14 Einträge, 4,8 MB** (davon `photos/` mit 12 Bildern):

| Eintrag | Größe | Was es war | Warum verwaist |
|---|---|---|---|
| `ai_stm.json` | 4 KB | Kurzzeit-Gedächtnis der alten KI (Phase D) | STM→LTM-Pipeline entfernt, heute Datei-Gedächtnis |
| `ai_ltm.json` | 196 KB | Langzeit-Gedächtnis der alten KI (Phase E) | dito |
| `persona_hist_zh.json` | 7 KB | Verlauf der Mandarin-Persona, alter Ort | Tutor speichert heute in `tutor/data/<lang>/` |
| `persona_mem_zh.json` | 1 KB | Persona-Notizen Mandarin, alter Ort | dito |
| `morgen_state.json` | 2 KB | Zustand des Morgen-Messengers | Messenger am 14.09.2026 entfernt |
| `autosync_probe.json` | 14 B | Probe-Datei eines Sync-Tests | Test längst vorbei |
| `None.json` | 57 B | ein Eintrag ohne Kategorie (Fehler vom 08.06.2026) | Artefakt, nur ein Zeitstempel |
| `photos/` | 12 Bilder | Quelle des Bild→ASCII-Filters im Browser | Browser-Front archiviert ([browser_front.md](browser_front.md)) |
| `ai_calendar.json.bak` | 4 KB | Kalender-Sicherung vom 15.06. | Handsicherung, kein Code liest sie |
| `ai_calendar.json.bak-vor-zeitputz` | 9 KB | Kalender vor dem Zeit-Putz am 17.08. | dito |
| `ai_graph.json.bak.20260531_135440` | 1,4 MB | Konzept-Graph vom 31.05. | dito; der Graph ist ohnehin aus |
| `ai_graph_cloud.json.bak-vor-testputz` | 1 MB | Cloud-Graph vor dem Test-Putz | dito |
| `ai_graph_cloud.json.bak-vor-zeitputz` | 0,9 MB | Cloud-Graph vor dem Zeit-Putz | dito |
| `mail_secrets.enc.bak` | 1 KB | Sicherung der verschlüsselten Mail-Zugänge (22.08.) | dito — vor dem Löschen prüfen, ob `mail_secrets.enc` aktuell ist |

**Bewusst NICHT beiseite gelegt (schlafend, nicht verwaist):**
`ai_graph.json` und `ai_graph_cloud.json`. Der Konzept-Graph ist seit
18.08.2026 aus, aber der Seed beim ersten Chat schreibt noch hinein, und mit
`ZENTRALE_GRAPH_KONTEXT=1` wäre er sofort wieder da. Gehören zur Entscheidung
„Graph ganz rückbauen oder behalten“.
