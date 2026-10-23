# Die Cloud als App — Apps sagen, was sie haben

**Stand 2026-10-23: Plan, Bau läuft.** Sasha beim ersten `zentrale setup`:
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
(`core/abgleich_bereiche.py`), gruppiert aus der Positivliste der Dateien.
Ein neuer Nutzer mit leerem Hub sah Kalender, Tutor, Musik … — Dinge, die es
bei ihm nicht gibt.

## Das Modell

1. **Zentrale speichert nichts Eigenes.** Daten haben nur Apps.
2. **Jede App sagt im Manifest, welche Daten sie hat** und ob sie
   abgeglichen werden dürfen:

   ```toml
   [daten]
   muster = ["data/lists.json", "data/features.json"]   # relativ zur Installation
   abgleichen = true        # false = bleibt immer auf dem Gerät (z. B. Caches)
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
   abgelöst von `abgleich_bereiche`; die alte Wahl wird beim ersten Lesen
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
| calendar | `kalender` |
| graphs | `graph` |
| memory, conversations | `assistent` |
| documents | `ablage` |
| desk | `desk` |
| apps (data/apps, data/shop) | `werkstatt` |
| mail | `mail` |
| music | `klavier` |
| tutor | `tutor` (echtes `app.toml`) |

Die Positivliste `core/abgleich_auswahl.py` bleibt der Schutz: ein Muster aus
einem Manifest wird nur abgeglichen, wenn es auch dort steht (deny by
default — eine App kann sich keine Schlüsseldatei erschleichen).

## Historie

- **2026-10-23** — Plan nach Sashas erstem Setup.
