# Der Adapter — die eine Tür zu fremden Diensten

**Stand 2026-10-24: gebaut** (Branch `adapter`; was echt ist: „Gebaut“ unten).
Sasha, als der Mini-PC beitrat und der Kalender fehlte:

> *„bleib beim gedanken dass der kalender eigentlich über zentrale komplett
> laufen soll und google nur da ist weil es noch keine app gibt. man soll auch
> die möglichkeit offen haben google und andere dienste zu verbinden aber das
> soll man auch nur über eine einzelne schnittstelle machen müssen. ich stelle
> mir im hub dafür eine app oder einen teil beim schmied vor namens „adapter"
> wo man so outsider sachen ankabeln kann. der adapter wird dann aber genauso
> überall durchgesynct in seiner konfiguration. … wenn man eine clean slate
> zentrale hat würde der adapter immer mit installiert. er ist quasi neben dem
> internen shop die zweite stelle wie man an apps und schnittstellen kommt."*

Nachgeschärft am selben Tag: ein festes Brücken-Gerät fällt aus, wenn es aus
ist — **der Wechsel muss nahtlos sein**, das ist der Sinn einer
abgeglichenen App. Also kein bevorzugtes Gerät, keine Anmeldung je Gerät.

Messlatte ([../leitbild.md](../leitbild.md)): Unterbau — jetzt nötig, weil
ein neues Gerät (Mini-PC) sonst ohne Kalender und ohne KI dasteht.

## Das Modell

1. **ZENTRALE ist die Wahrheit.** Kalender, Listen … gleichen über die Cloud
   ab. Ein fremder Dienst ist nur ein **Anschluss**, nie die Quelle.
2. **Der Adapter ist eine App** (`adapter`, eingebaut, `pflicht`: immer
   abgeglichen, nie gefragt, nie abgewählt). Werkstatt-Familie: die
   Anbindungs-Pipe ([hub_bauplan.md](hub_bauplan.md)) bleibt seine Maschine
   für Dienste mit API.
3. **Ein Anschluss** = Beschreibung (gleicht ab, nie ein Geheimnis) +
   **Zugangsdaten** (gleichen nur verschlüsselt mit dem Kontoschlüssel ab).
4. **Die Brücke ist ein Mietvertrag.** Ein Anschluss mit fremdem Dienst
   (Google-Kalender) läuft immer auf genau einem Gerät: wer den Vertrag hält.
   Jedes Gerät mit Adapter und vdirsyncer kann ihn nehmen, sobald er frei
   oder abgelaufen ist. Unsichtbar — niemand stellt etwas ein.
5. **Alles, was eine Brücke braucht, kommt über den Abgleich:** die
   vdirsyncer-Konfiguration wird je Gerät aus dem Anschluss erzeugt;
   Client-Geheimnis und OAuth-Token liegen in den Zugangsdaten; erneuert
   Google den Token, schreibt die Brücke ihn zurück.
6. **KI-Anbieter sind Anschlüsse** (`ki-anbieter`, ohne Brücke): die
   Schlüssel ziehen aus `data/ai_config.json` in die Zugangsdaten — ein neues
   Gerät hat nach dem Login und einem Abgleich eine KI.
7. **Ist keine Brücke online**, läuft ZENTRALEs Kalender weiter (Cloud);
   nur die Google-Seite hinkt hinterher und holt beim nächsten Lauf auf.

## Dateien

| Datei | was | gleicht ab | Sicherung (GitHub, Klartext) |
|---|---|---|---|
| `data/adapter/anschluesse/<id>.json` | Beschreibung, Schema `core/adapter_anschluss.schema.json` | ja | ja |
| `data/adapter/geheim.enc` | Zugangsdaten, JSON, **je Eintrag** Fernet (`zu: konto` / `geraet`) | nur angemeldet | **nie** (`GEHEIM`, Test) |
| `data/adapter/bruecke/<id>.json` | Mietvertrag `{inhaber, ablauf, seit, zustand}` | ja | nein |
| `data/adapter/bruecke/<id>.status.json` | Stand von vdirsyncer (`*.items`) + Liste der Löschsperre | ja | nein |
| `~/.config/zentrale/adapter.schluessel` | Geräteschlüssel (ohne Konto) | nie | nie |
| `~/.local/share/zentrale/adapter/<id>/` | erzeugte `vdirsyncer.config` (600), Merkzettel | nie | nie |

- **Je Eintrag verschlüsselt, nicht ein Block:** so gewinnen zwei Geräte, die
  verschiedene Einträge ändern (KI-Schlüssel hier, Token dort) — die
  JSON-Regel führt Eintrag für Eintrag zusammen. Lesbar bleiben nur die
  Namen (Datei 600; in der Cloud ohnehin noch einmal verschlüsselt).
- **Ohne Konto: Geräteschlüssel statt Klartext mit 600** — data/ wird an
  mehr Orte kopiert als ~/.config (alter rsync-Weg, Sicherungen, Stick).
  Anmelden → beim nächsten Abgleich auf `konto` umgeschlüsselt; vor
  `zentrale logout` zurück auf `geraet`.
- **Vertrag: „wer zuerst in der Mitte war"** — eigene Regel im Abgleich
  (Art `mitte`): beide geändert → die Mitte gilt, nie Feld für Feld (sonst
  bekäme einer den Namen, der andere die Ablaufzeit, und beide führen). Die
  Mitte nimmt nur an, was auf ihrem letzten Stand aufbaut (409 → neu holen).

## Ein Lauf des Kalender-Timers (jedes Gerät, alle 3 min)

`scripts/kalender_sync.py` → `adapter_ablauf.bruecke_lauf`:

1. kein vdirsyncer → nichts. Ohne Mitte (kein Konto/Schlüssel, rsync-Weg) →
   eigene Brücke, ohne Vertrag.
2. Kalender noch nicht hier (erstes Mal) → erst abgleichen.
3. Vertrag gehört jemand anderem und läuft noch → nichts tun; dessen Stand
   (`zustand`) hierher, damit die TUI „google ✓ 16:31 · laptop" zeigt.
4. Sonst: Vertrag auf mich (15 min), **abgleichen**. Kam mein Name zurück →
   Stand von vdirsyncer auspacken (wenn er von einem anderen Gerät stammt),
   Konfiguration bauen, bei geänderter Konfiguration `vdirsyncer discover`
   (liest nur), Google abgleichen (mit allen alten Sicherungen), Token und
   Stand zurück, verlängern, abgleichen.

Gemessen (vdirsyncer 0.21.0): ein kopierter Stand mit anderen Datei-Zeiten,
Inodes und Pfaden löst keine Übertragung aus — vdirsyncer vergleicht den
Inhalt. Nur `<paar>.collections` hängt an der Konfiguration des Geräts und
wird neu entdeckt.

## Gebaut (2026-10-24)

- Module (Schicht 1): `core/adapter.py` (Anschlüsse, Kalender-Schalter,
  Kalender kommt einmal je Gerät dazu), `adapter_geheim.py`,
  `adapter_bruecke.py`, `adapter_vdirsyncer.py` (Vorlage ↔ Konfiguration:
  `{"$geheim"}`, `{"$datei"}` für token_file, `{"$ort": "kalender"}` für
  den Kalender-Ordner, ~-Pfade bleiben ~), `adapter_ablauf.py` (einrichten,
  bruecke_lauf), `abgleich_ics.py` (Termine je UID zusammenführen).
- Abgleich: `abgleich_apps.jetzt_erlaubt` schneidet `data/kalender/**` ohne
  Kalender-Anschluss und `geheim.enc` ohne Konto heraus. Vor dem Abgleich
  umschlüsseln und `adapter.vor_abgleich`; danach Merkzettel
  `kalender_dabei.json` und KI-Schlüssel in die Umgebung.
- KI: Rangfolge echte Umgebung > Adapter > `ai_config.json`
  (`ai_config.injiziert`); `providers` legt beim Import ein;
  `ki_uebernehmen()` beim Start des Backends, bei `zentrale sync` und
  `zentrale adapter setup` — ein Schlüssel verlässt ai_config.json erst,
  wenn er im Adapter lesbar ist; ein abweichender bleibt dort (Rückfall).
- `kalender_speicher.modus`: nicht eingestellt + `migriert_am` in den
  Nebendaten → `ics` (sonst stünde ein neues Gerät auf `json`).
- CLI: `zentrale adapter` (Anschluss, Art, speist, Brücke = Inhaber + bis
  wann, Status), `zentrale adapter setup` (KI-Schlüssel + vorhandene
  vdirsyncer-Konfiguration → Anschluss `google-kalender`; **der bewusste
  Umstieg**), `zentrale status` zeigt „Adapter — always synced".
- Tests: `tests/test_adapter.py`, `test_adapter_geheim.py`,
  `test_abgleich_ics.py`, `test_kalender_cloud.py` (zwei Geräte, Cloud,
  echtes vdirsyncer gegen einen Ordner als „Google").

## Offen

- Uhren: der Vertrag vergleicht Uhrzeiten zweier Geräte; mehr als ein paar
  Minuten Abweichung verkürzen ihn.
- `vdirsyncer discover` fragt bei einer fehlenden Sammlung nach — die
  Brücke bricht dann ab (Zustand „nicht eingerichtet") statt anzulegen.
- `password.fetch` (CalDAV mit Passwort-Programm) reist nicht — das
  Programm müsste auf jedem Gerät sein.
- Langfristig (Hub-Plan) liegen KI-Schlüssel auf Sashas Server; dann zeigt
  der Anschluss dorthin.

## Historie

- **2026-10-24** — Plan nach dem Beitritt des Mini-PCs; gebaut, die Brücke
  als Mietvertrag mit nahtlosem Wechsel (Sasha: kein festes Gerät).
