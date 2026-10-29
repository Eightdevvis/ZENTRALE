# Die Cloud als App — Apps sagen, was sie haben

**Stand 2026-10-23: gebaut** (Branch `cloud-app`; was echt ist: „Gebaut“ unten). Sasha beim ersten `zentrale setup`:
*„das choose what this device syncs is fraglich … wenn ein user das neu
aufmacht dann sollte ja quasi kaum was kommen … lowk wird die cloud eine
weitere app in zentrale sein, ein dienst den man wahrnehmen kann, und der
spricht dann mit den anderen apps. außer daten aus den apps gibts ja nichts
was zentrale speichern will."*

Messlatte ([../leitbild.md](../leitbild.md)): Unterbau. Er kommt jetzt, weil
sonst jeder neue Nutzer als Erstes eine falsche Liste sieht und weil „lokal
zuerst" so zur Bauweise wird statt zur Einstellung.

## Was falsch war

Die Auswahl im Assistenten waren zwölf feste **Bereiche**
(`core/abgleich_bereiche.py`, seit 2026-10-23 gelöscht), gruppiert aus der
Positivliste der Dateien.
Ein neuer Nutzer mit leerem Hub sah Kalender, Tutor, Musik … — Dinge, die es
bei ihm nicht gibt.

## Das Modell

1. **Zentrale speichert nichts Eigenes.** Daten haben nur Apps.
2. **Jede App sagt im Manifest, welche Daten sie hat** und ob sie
   abgeglichen werden dürfen:

   ```toml
   [daten]
   muster = ["data/lists.json", "data/features.json"]   # relativ zum ZENTRALE-Ordner (wie die Positivliste)
   abgleichen = true        # fehlt/false = bleibt immer auf dem Gerät (z. B. Caches)
   ```

3. **Die Cloud ist eine App** (`cloud`): Konto, Abgleich, Geräteliste,
   Nutzungs-Wächter. Ist sie nicht eingeschaltet, gibt es keine Cloud — das
   Gerät ist rein lokal.
4. **Die Auswahl entsteht aus dem Hub:** installierte Apps mit `[daten]` und
   `abgleichen = true`, **die hier oder in der Cloud schon Daten haben.** Ein
   frischer Nutzer sieht deshalb nichts außer „noch nichts abzugleichen —
   neue Apps fragen selbst".
5. **Neue App mit Daten → einmal fragen:** beim nächsten Abgleich (CLI) bzw.
   beim Start: „App X hat Daten — mit abgleichen? [y/n]". Die Antwort gilt je
   Gerät.
6. Die Wahl gilt je **App** und je Gerät (Einstellung `abgleich_apps`,
   abgelöst von `abgleich_bereiche`; die alte Wahl wird beim Lesen
   übernommen).

## Übergang: eingebaute Apps

Solange Kalender, Listen usw. im Kern stecken, melden sie sich als
**eingebaute Apps** beim Hub an — mit Name, Titel und `[daten]` wie ein
echtes Manifest (eine Tabelle an einer Stelle, `core/eingebaute_apps.py`).
Zieht eine App aus (wie Tutor, Karte), kommt ihr `[daten]` aus ihrem
`app.toml`, und für die Cloud ändert sich nichts.

| Bereich bisher | wird App |
|---|---|
| lists | `fokus` |
| notes | `notizen` |
| calendar | `kalender` (Termine seit 2026-10-24 mit, sobald es einen Kalender-Anschluss gibt) |
| graphs | `graph` |
| memory, conversations | `assistent` |
| documents | `ablage` |
| desk | `desk` |
| apps (data/apps, data/shop) | `werkstatt` |
| mail | `mail` |
| music | `klavier` |
| tutor | `tutor` (echtes `app.toml`) |
| — (neu 2026-10-29) | `cloud_folder` — `~/Zentrale/Cloud` ([cloud_folder.md](cloud_folder.md)) |
| — (neu 2026-10-24) | `adapter` — Pflicht: immer abgeglichen, nie gefragt ([adapter.md](adapter.md)) |

Die Positivliste `core/abgleich_auswahl.py` bleibt der Schutz: ein Muster aus
einem Manifest wird nur abgeglichen, wenn es auch dort steht (deny by
default — eine App kann sich keine Schlüsseldatei erschleichen).

## Gebaut (2026-10-23)

- `[daten]` im app.toml: `apps.daten()` liest es (Muster mit `..`, absolut,
  `~`, `\` fallen weg; `abgleichen` fehlt = false). `GET /api/apps` zeigt
  `daten` (null = keine). Muster stehen relativ zum ZENTRALE-Ordner — dem
  Namensraum der Positivliste.
- `core/eingebaute_apps.py`: die Tabelle oben plus `cloud` (Dienst, ohne
  Daten) und der **Ersatz** für den Tutor, solange `language-tutor/app.toml`
  kein `[daten]` hat (gilt auch, wenn der Tutor auf dem Gerät nicht
  installiert ist — seine Daten liegen noch in `ZENTRALE/tutor/data`).
  Hat ein Manifest gleichen Namens `[daten]`, gewinnt das Manifest.
- `core/abgleich_apps.py`: Tabelle (Muster nur, wenn sie **genau so** auf
  der Positivliste stehen; jedes Muster nur einer App — eingebaute zuerst),
  Wahl `abgleich_apps` je Gerät, Übernahme von `abgleich_bereiche`, wer
  Daten hat, wer noch fragen muss. `core/abgleich.py` gleicht nur noch die
  Muster der gewählten Apps ab.
- Cloud-Seite ohne Herunterladen: `abgleich.cloud_pfade()` liest nur
  `inhalt.enc` (ein Blob) und gibt die Pfade.
- Die App `cloud` ist an, wenn `abgleich_mitte_art = http` und angemeldet
  (`abgleich.cloud_an()`); `zentrale status` zeigt sie unter „Apps“ mit dem
  Stand jeder App.
- Fragen: `zentrale setup` (nur Apps mit Daten; keine → „Nothing to sync
  yet …“, Cloud trotzdem an, `abgleich_apps = {}`), `zentrale sync` und Start
  von `zentrale` (dort nur lokal nachgesehen) fragen je neue App einmal; ohne
  Terminal eine Zeile, die App bleibt draußen.
- Übernahme: alte Wahl „alles“ → alle Apps ja, dieselben Muster wie vorher;
  `[]` → alle nein; teilweise (memory ohne conversations) → `assistent`
  unentschieden, fragt einmal; nicht gesetzt → alles wie bisher.
- Tests: `tests/test_abgleich_apps.py`, `tests/test_abgleich_http.py`
  (zwei Geräte, Sashas Stand, Manifest mit Schlüsseldatei),
  `tests/test_zentrale_cli.py`.
- **Offen:** `language-tutor/app.toml` bekommt `[daten]` (dann fällt der
  Ersatz weg); die TUI zeigt die Wahl noch nicht; ein Rechte-Dialog für
  fremde Manifeste fehlt (bis dahin schützt die Positivliste).

## Historie

- **2026-10-23** — Plan nach Sashas erstem Setup; am selben Tag gebaut.
