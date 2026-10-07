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

## Suche quer durch die Gespräche (seit 2026-10-07)

Phase 3 des Plans. Sasha: „mein kopf kann sich thematisch viel besser
orientieren als datiert. solang der assistant eh einfach crossgespräche
suchen kann wie claude web." Die KI sucht mit `search_chats(query)` und liest
mit `read_chat(id, query?, anzahl?)` nach ([ki_system.md](ki_system.md),
„Frühere Gespräche"). Code: `core/chat_suche.py` (Schicht 2).

- **Was:** alle Gespräche aus `gespraeche.liste()` und
  `liste(archivierte=True)` (also auch „Erinnerungen") und das alte
  Transkript (`transkript.alle()`, `data/ai_transcripts/`, lokal + Cloud),
  dort **ein Treffer pro Tag** (id `transkript:JJJJ-MM-TT`, Titel „Früherer
  Chat vom …"). Testmüll im Transkript (von vor dem Riegel in
  `tests/conftest.py`) bleibt drin — er ist nicht sicher erkennbar.
- **Was nicht:** Denken, Werkzeug-Listen, versteckte Aufträge (Gespräche:
  Flag `versteckt`; Transkript: Nutzertext, der mit „Erinnere Sasha" oder dem
  Auftrags-Vorsatz beginnt). Ein Transkript-Zug, dessen KI-Antwort es als
  Gesprächs-Nachricht gibt, fällt raus (die Konsolidierung schreibt jeden
  Zug weiter ins Transkript). Vom **aktiven** Gespräch fehlen die letzten
  `FENSTER` Nachrichten — die hat die KI schon im Verlauf; Älteres daraus
  wird gefunden. „Aktiv" = `gespraeche.aktiv()`, das die Chat-Route vor
  jedem Zug setzt.
- **Wie:** Wörter normalisiert (klein, ä→ae, ö→oe, ü→ue, ß→ss, Akzente weg,
  Satzzeichen weg), Füllwörter (der, das, mit, letztens …) und Einzelzeichen
  fallen weg; **alle** übrigen Wörter müssen als Teilwort in der Einheit
  (Gespräch / Tag) stehen — verteilt über mehrere Nachrichten ist erlaubt.
- **Rang:** Stellen / √(Wörter + 20) × (0,4 + 0,6 · ½^(Alter/60 Tage)); das
  Alter zählt ab der besten Nachricht (die mit den meisten verschiedenen
  Suchwörtern). Höchstens 8 Treffer, je ein Ausschnitt um die erste
  Fundstelle.

Kein Index, keine Vektoren: es sind ein paar hundert Nachrichten, das Lesen
nutzt den Cache von `gespraeche.nachrichten`, und ein Wortfund ist für Sasha
nachprüfbar, ein Ähnlichkeitswert nicht. Wird es zu langsam (tausende
Gespräche), ist ein Index pro Rechner der nächste Schritt.
