# Kalender: Stand des Google-Syncs (seit 16.10.2026)

**Anlass.** Vom 10.10. 17:32 bis 13.10. lief der Sync-Timer gar nicht
(behoben in 7e9229c, OnCalendar statt OnBootSec), ab 14.10. 16:33 brach jeder
Lauf ab: vdirsyncer meldete beim Holen der Sicherungskopie (`google_probe`)
`(invalid_grant) Token has been expired or revoked` → Exit 3. Beides war in
ZENTRALE unsichtbar. Sasha: „dass es expired is hätte in zentrale angezeigt
werden müssen".

## Die Datei

`scripts/kalender_sync.py` schreibt nach **jedem** Lauf (Exit 0/1/2/3 und
bei einer Ausnahme) eine kleine JSON-Datei, pro Rechner:

- Pfad `~/.local/share/zentrale/kalender_sync.json`, umlenkbar über
  `ZENTRALE_KALENDER_SYNC_ZUSTAND` (Tests: `tests/conftest.py` und der
  venv-Riegel `scripts/zentrale_testguard.py`).
- Felder: `letzter_versuch`, `letzter_erfolg`, `ok`, `art`, `fehler`
  (Klartext), `seit` (erster Fehlschlag nach dem letzten Erfolg), `exit`.
- `art` aus der Ausgabe von vdirsyncer (die der Wrapper mitliest und
  weiterreicht, das Journal behält alles) und der Stufe des Laufs:

| art | woran erkannt | fehler |
|---|---|---|
| `zugang` | `invalid_grant`, „Token has been expired or revoked" | Google-Zugang abgelaufen — neu anmelden |
| `netz` | Namensauflösung, keine Verbindung, Zeitüberschreitung | kein Netz — Google nicht erreichbar |
| `loeschsperre` | Exit 2 (lokal fehlen zu viele Termine) | Löschsperre: lokal fehlen Termine — nicht gesynct |
| `sicherung` | Exit 3 ohne erkannten Grund | Sicherungskopie von Google fehlgeschlagen — nicht gesynct |
| `einrichtung` | Kalender nicht auf ics, vdirsyncer fehlt | Sync nicht eingerichtet |
| `sonstig` | alles andere, auch Absturz | Abgleich fehlgeschlagen (Exit n): letzte error-Zeile |

Code: `core/kalender_sync_zustand.py` (Schicht 1: lesen, schreiben,
erkennen, bewerten, alarme).

## Mit dem Adapter (seit 24.10.2026)

Google fährt nur das Gerät mit dem Mietvertrag ([../hub/adapter.md](../hub/adapter.md)).
Es legt seinen Stand nach jedem Lauf mit `bruecke: <gerät>` in den Vertrag;
jedes andere Gerät übernimmt ihn bei seinem Timer-Lauf in die eigene Datei
(`kalender_sync_zustand.uebernehmen`) — so zeigt jedes Gerät denselben Stand,
ohne Problem leise „google ✓ 16:31 · laptop". Hält niemand den Vertrag,
altert der übernommene Stand und wird nach `ALT_MIN` zur Warnung „läuft
nicht" — auf allen Geräten.

## Urteil

`bewerten()` ergänzt `bekannt`, `alt`, `problem`, `hinweis`, `kurz`:

- Keine Datei → `bekannt: false`, nichts wird gezeigt (auf dem Rechner läuft
  kein Sync).
- `alt`: seit mehr als `ALT_MIN` (10) Minuten kein Erfolg oder kein Versuch.
- Problem, wenn der letzte Versuch älter als `ALT_MIN` ist („⚠ google-sync
  läuft nicht — letzter Versuch 13.10. 17:32") oder der letzte Lauf
  scheiterte („⚠ google-sync: Zugang abgelaufen — seit 14.10. 16:33").
  Ausnahme `netz`: erst nach `NETZ_GEDULD_MIN` (60) Minuten ohne Erfolg —
  offline sein ist auf dem Laptop oft gewollt.
- Ohne Problem: `kurz` = „google ✓ 16:31".

## Wo man es sieht

- `GET /api/calendar/sync` → das Urteil; dasselbe als Feld `sync` in
  `GET /api/calendar`.
- Alarm-Kanal: `kalender.alarme()` = Sync-Alarm (kind `Google-Sync`) +
  `open_alarms()`; so setzen es `kalender._save_raw` und `core/main.py`
  (Start, alle ~5 min). Damit steht es in `/api/state` → `alarms` und im
  KI-Prompt („offene Erinnerungen"). `open_alarms` selbst bleibt reiner
  Kalender-Inhalt (Werkzeuge, Messläufe).
- TUI Kalender (`tui/ansichten/kalender_ansichten.py`): Problem → rechts in
  der Statuszeile von A (Warnfarbe) und rechts im Kopf von B und C. Ohne
  Problem nur leise „google ✓ 16:31" in der Statuszeile von A — Regler
  `SYNC_OK_ZEIGEN` (False → gar nichts).
- TUI Startseite (`tui/ansichten/startseite.py` `sync_warnung`): unter
  „up · net" oben rechts die Warnung aus dem Alarm-Kanal.
