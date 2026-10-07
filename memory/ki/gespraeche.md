# Gespräche — Speicher, Sync, Ereignisse

Stand 2026-10-07 (Claude-Web-Plan Phase 2, [claude_web_plan.md](claude_web_plan.md)).
Vorher war der Verlauf EIN Gespräch im RAM (`state._chat_history`, 50
Einträge), weg nach jedem Neustart. Jetzt: viele Gespräche wie im Web, auf
der Platte, auf allen Rechnern gleich (Sashas Entscheidungen 1, 2, 6).

Code: `core/gespraeche.py` (Schicht 2), Titel `core/gespraech_titel.py` +
`core/billig.py` (Schicht 3), Routen `ui/routen/ki.py` (Chat-Strom) und
`ui/routen/gespraeche.py` (Verwaltung), TUI `tui/ansichten/chat_gespraeche.py`
und `gespraechsliste.py`.

## Speicherformat

```
data/gespraeche/
  <id>/kopf.json          {titel, titel_von, erstellt, archiviert, projekt}
  <id>/<knoten>.jsonl     Ereignisse DIESES Rechners, nur angehängt
  erinnerungen/…          das feste Gespräch „Erinnerungen"
  _knoten/<knoten>.json   {aktiv, gelesen: {id: ts}} — nur für diesen Rechner
```

- **id**: `JJJJMMTT-hhmmss-<6 hex>` (sortiert nach Erstellzeit, auf zwei
  Rechnern eindeutig); fest: `erinnerungen`.
- **knoten** = `socket.gethostname()`, dateinamen-tauglich
  (`dateien.knoten()`, derselbe Name wie in `scripts/daten_sichern.py` und im
  Kalender-Verlauf).
- **titel_von**: `sasha` (von Hand), `modell` (billiges Modell), `woerter`
  (die ersten Wörter). Automatisch wird nie über einen Hand-Titel geschrieben.
- **projekt**: immer `null` — für Phase 6 reserviert.
- Ordner per `ZENTRALE_GESPRAECHE_DIR` umlenkbar (Tests: `tests/conftest.py`,
  jeder Test einen eigenen Ordner; Wächter in `test_keine_seiteneffekte.py`).
- gitignored (`data/gespraeche/`), gesichert über `scripts/daten_sichern.py`.

## Ereignisse

Jede Zeile einer `.jsonl` ist ein Ereignis `{id, ts, knoten, art, …}`;
`ts` ist UTC-ISO mit Mikrosekunden, im Prozess streng steigend.

| art | Felder | Bedeutung |
|---|---|---|
| `nachricht` | `rolle` user/assistant, `text`, optional `denken` (≤ 20 000 Zeichen, das Ende bleibt), `werkzeuge` [{name, args, fehler?}], `anbieter`, `modell`, `abgebrochen`, `versteckt` | eine Nachricht |
| `verwerfen` | `ab` (Nachricht-id) | diese und alle späteren Nachrichten zählen nicht mehr (Wiederholen, Bearbeiten) |

**Lesen** = alle Rechner-Dateien zusammenlegen, nach `(ts, knoten, Zeile)`
sortieren, der Reihe nach anwenden. Eine halbe Zeile (Absturz beim Schreiben)
wird übersprungen. Ein `verwerfen` vom Laptop trifft Nachrichten vom PC
genauso; was nach dem Verwerfen geschrieben wird, zählt wieder.

**Schreiben**: eine Zeile, ein `write()` mit `O_APPEND`, `fsync`. `kopf.json`
atomar (`dateien.json_schreiben`). Danach `datasync.notify_change()`
(Push-on-write).

**Versteckt**: der Erinnerungs-Auftrag (`takt_treiber`) steht als
`user`-Nachricht mit `versteckt: true` im Gespräch „Erinnerungen". Die TUI
zeigt ihn nicht; die KI sieht ihn mit dem Vorsatz „[Automatischer Auftrag
von ZENTRALE, nicht von Sasha geschrieben]".

**Abgebrochen**: gespeichert wird der halbe Text mit `abgebrochen: true`; der
Vermerk „(abgebrochen)" kommt beim Lesen dazu (für die KI und die Anzeige).

## Warum so (Sync)

Der Sync ist rsync, additiv, „neueste Datei gewinnt"
([../system/topologie.md](../system/topologie.md)). Daraus folgt alles:

- **Eine Datei pro Rechner**: schrieben PC und Laptop in dieselbe Datei,
  gewänne eine Fassung, die Nachrichten der anderen wären weg. Eine
  Rechner-Datei schreibt nur ihr Rechner; drüben liegt höchstens eine ältere
  Kopie, also ist „neueste gewinnt" dort immer richtig.
- **Ereignisse statt Umschreiben**: Wiederholen/Bearbeiten löschen nichts,
  sie hängen ein `verwerfen` an. So kann der Sync nie eine Zeile verlieren.
- **Nie löschen, nur archivieren**: ein gelöschter Ordner käme vom anderen
  Rechner zurück.
- **kopf.json** schreiben beide Rechner — er ist klein, eine verlorene
  Umbenennung harmlos.
- **Aktiv und gelesen pro Rechner** (`_knoten/`): sonst schalteten sich PC und
  Laptop gegenseitig das offene Gespräch um.
- Uhren: die Reihenfolge über Rechner hinweg hängt an der Systemzeit. Laufen
  die Uhren Sekunden auseinander, kann eine Nachricht vom anderen Rechner an
  der falschen Stelle stehen — verloren geht nichts.

## An die KI

`gespraeche.verlauf_fuer_ki(id)` → `[{role, content}]` der letzten 50
Nachrichten (`FENSTER`, wie früher die deque). Die Länge einer Nachricht kappt
weiter `cloud.kappen`. `/api/chat` hängt die Frage an, schickt das Fenster an
`kern.chat`, speichert die Antwort mit allem Denken des Zugs (`reflect`) und
den Werkzeugen.

## Titel

1. Beim ersten Senden sofort die ersten 6 Wörter (`titel_von: woerter`).
2. Nach der ersten Antwort im Hintergrund das billige Modell des aktiven
   Anbieters (`billig.einmal`, Kosten über `usage.buchen`, Log `TITEL ←`) —
   **nur wenn der Zug selbst über die Cloud lief**: ein lokal geführtes
   Gespräch geht für einen Titel nicht nach draußen. Fehler → die Wörter
   bleiben. Die Route wartet höchstens 1,5 s (`TITEL_WARTEN`) und meldet ihn
   als SSE `titel`; später holt ihn die Liste.

## Erinnerungen

`takt_treiber.sprechen` schreibt Auftrag (versteckt) + Antwort ins Gespräch
`erinnerungen` (immer oben in der Liste, nicht umbenennbar, nicht
archivierbar). Das offene Gespräch bleibt unberührt. Die TUI zeigt ● im
Kasten-Titel und auf der Startseite (ungelesen), die Desktop-Meldung kommt
wie bisher.

## Zuschnitt in der TUI

Siehe [../system/tui_bauplan.md](../system/tui_bauplan.md), Abschnitt
„Chat: Gespräche".
