# Altlast: Routen der TUI ohne Beschreibung

**Wächter E4** ([kern_auszug_inventur.md](kern_auszug_inventur.md) Abschnitt E,
seit 2026-10-22, Test `tests/test_routen_beschrieben.py`): jede Route, die die
TUI ruft, steht in `openapi.yaml` — oder gehört einer App, die sie laut
`routen` im `app.toml` besitzt und selbst beschreibt (der Hub reicht weiter).
Ziel ([hub_bauplan.md](hub_bauplan.md) „überall deploybar"): ein Dart-, JS-
oder Rust-Knoten baut jede Funktion allein aus der Doku.

Am 2026-10-22 standen die folgenden Pfade nirgends. Die Liste darf nur
**schrumpfen**: der Test wird rot, wenn die TUI eine neue unbeschriebene Route
ruft, und verlangt das Austragen, sobald eine hier beschrieben ist (oder einer
App gehört). Ein Pfad mit `/` am Ende ist ein Anfang (dahinter eine Kennung).
Nichts neu eintragen — beschreiben.

| Pfad | Bereich |
|---|---|
| `/api/abgleich` | abgleich |
| `/api/ablage` | ablage |
| `/api/ablage/` | ablage |
| `/api/ai/backends` | ai |
| `/api/ai/einstellungen` | ai |
| `/api/ai/kosten` | ai |
| `/api/ai/status` | ai |
| `/api/ai/werkzeuge` | ai |
| `/api/anhang` | anhang |
| `/api/calendar` | calendar |
| `/api/calendar/ebene` | calendar |
| `/api/calendar/eintrag` | calendar |
| `/api/calendar/entry` | calendar |
| `/api/calendar/kategorie` | calendar |
| `/api/calendar/kategorien` | calendar |
| `/api/calendar/konflikte` | calendar |
| `/api/calendar/motive` | calendar |
| `/api/calendar/phase` | calendar |
| `/api/calendar/phasen` | calendar |
| `/api/calendar/quelle` | calendar |
| `/api/calendar/quellen` | calendar |
| `/api/calendar/routine` | calendar |
| `/api/calendar/routine/abweichung` | calendar |
| `/api/calendar/routine/skip` | calendar |
| `/api/calendar/routine/zeitraum` | calendar |
| `/api/calendar/spanne` | calendar |
| `/api/calendar/spanne/tag` | calendar |
| `/api/calendar/stil` | calendar |
| `/api/calendar/typ` | calendar |
| `/api/chat` | chat |
| `/api/chat/clear` | chat |
| `/api/chat/history` | chat |
| `/api/chat/stop` | chat |
| `/api/chat/wiederholen` | chat |
| `/api/cycle` | cycle |
| `/api/data/` | data |
| `/api/erlaubnis` | erlaubnis |
| `/api/erlaubnis/zuruecknehmen` | erlaubnis |
| `/api/gedaechtnis` | gedaechtnis |
| `/api/gedaechtnis/` | gedaechtnis |
| `/api/gespraeche` | gespraeche |
| `/api/gespraeche/` | gespraeche |
| `/api/gespraeche/aktiv` | gespraeche |
| `/api/graphs` | graphs |
| `/api/graphs/` | graphs |
| `/api/graphs/reminders` | graphs |
| `/api/lists` | lists |
| `/api/lists/` | lists |
| `/api/log` | log |
| `/api/mail` | mail |
| `/api/mail/assign` | mail |
| `/api/mail/body` | mail |
| `/api/mail/delete` | mail |
| `/api/mail/folder` | mail |
| `/api/mail/inbox` | mail |
| `/api/mail/inbox-body` | mail |
| `/api/mail/poll` | mail |
| `/api/mail/read` | mail |
| `/api/mail/reconcile` | mail |
| `/api/mail/refresh-counts` | mail |
| `/api/mail/reply` | mail |
| `/api/melodies` | melodies |
| `/api/melodies/` | melodies |
| `/api/morgenblick` | morgenblick |
| `/api/notes` | notes |
| `/api/notes/` | notes |
| `/api/permission_answer` | permission_answer |
| `/api/projects` | projects |
| `/api/projects/focus` | projects |
| `/api/projects/focused` | projects |
| `/api/projekte` | projekte |
| `/api/projekte/` | projekte |
| `/api/projekte/zuordnen` | projekte |
| `/api/rueckmeldung` | rueckmeldung |
| `/api/rueckmeldungen` | rueckmeldungen |
| `/api/skills/` | skills |
| `/api/state` | state |
| `/api/telemetry` | telemetry |
