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
8. **Woher der Kalender kommt, ist ein Wert der Kalender-App** (seit
   29.10.2026): `quelle` ∈ google | zencloud | lokal — siehe „Die Quelle der
   Kalender-App" unten. Ein Anschluss trägt nur Zugangsdaten, nie die
   Entscheidung.

## Dateien

| Datei | was | gleicht ab | Sicherung (GitHub, Klartext) |
|---|---|---|---|
| `data/adapter/anschluesse/<id>.json` | Beschreibung, Schema `core/adapter_anschluss.schema.json` | ja | ja |
| `data/adapter/anschluesse/kalender-<id>.json` | **Einstellung der Kalender-App** `<id>`, Schema `core/kalender_einstellung.schema.json` | ja | ja |
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

Timer `zentrale-kalender-sync` → `zentrale adapter run` →
`scripts/kalender_sync.py zentrale` → `adapter_ablauf.bruecke_lauf`. Den
Timer legt `zentrale setup` bzw. `zentrale timers install` auf jedem Gerät an
([../betrieb/setup.md](../betrieb/setup.md) „Timer"); vorher hatte nur
Sashas Checkout ihn, ein neues Gerät nahm die Brücke nie.

1. kein vdirsyncer → nichts. Ohne Mitte (kein Konto/Schlüssel, rsync-Weg) →
   eigene Brücke, ohne Vertrag.
2. Quelle nicht google → nichts. Quelle google gesetzt (oder ohne Mitte) →
   jedes Gerät fährt selbst, ohne Vertrag (die Cloud trägt den Kalender
   dann nicht). Nur der alte Weg (keine Einstellung + Anschluss) geht weiter:
   Kalender noch nicht hier (die Basis des Abgleichs kennt ihn nicht) → erst
   abgleichen.
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

## Die Quelle der Kalender-App (seit 29.10.2026)

Ersetzt den Schalter `kalender-mitte` vom 28.10. (1f32e6a), den Sasha
verworfen hat: *„das soll doch alles dasselbe programm sein, überall eine
streamline keine divergenz"* und *„die wahl is auch nich für DEIN GANZES
KONTO sondern nur für deine eine kalender app in zentrale die du
installierst.. wenn du 2 installierst dann hast du halt 2 verschiedene..
aber zentrale selbst, dein konto, der hub is ja ne nackte shell an sich, die
hat nichts außer nen haufen pforten wo man sachen rumstöpselt"*.

- **Ein Wert, kein Code-Weg.** Je installierter Kalender-App (Instanz) EINE
  Datei, die **Einstellung der Kalender-App `<id>`**:
  `{format: "zentrale-kalender-app/1", id, quelle, ordner, titel, geaendert}`,
  Schema `core/kalender_einstellung.schema.json`, Code
  `core/kalender_einstellung.py`. `quelle`:
  - `google` — jedes Gerät gleicht seinen Ordner selbst mit Google ab
    (`zentrale adapter run`, `scripts/kalender_sync.py`), die Cloud trägt
    die Termine nicht;
  - `zencloud` — die Termine gleichen über die Cloud ab, niemand fährt Google;
  - `lokal` — weder noch.
  Heute nur `kalender-haupt` → `data/kalender`; eine zweite Instanz hat ihre
  eigene Datei, Quelle und Ordner (Schema und `instanzen()`/`mit_quelle()`
  tragen das; dass ihr Ordner abgleicht, braucht noch ein Muster in der
  Positivliste).
- **Wo die Datei liegt und warum:** `data/adapter/anschluesse/kalender-<id>.json`
  — der einzige Ort, der heute auf JEDES Gerät abgleicht und nie abgewählt
  wird (App `adapter`, pflicht). Die Kalender-App steckt sich an eine Pforte
  des Adapters; der Kern/Hub kennt keine Kalender-Einstellung. Nicht
  `data/kalender/**` (gleicht genau dann nicht ab, wenn die Quelle nicht
  zencloud ist), nicht `kalender_neben.json` (schreibt der Speicher dauernd,
  App abwählbar). `adapter.alle()` übergeht diese Dateien (sie sind keine
  Anschlüsse). **Übergang:** nach [standort_und_app.md](standort_und_app.md)
  gehört die Einstellung in den Datenbereich der App, nicht zum Gestell —
  Ziel ist ein eigenes Muster (z. B. `data/kalender_apps/*.json`) in der
  Positivliste `core/abgleich_auswahl.py` und in `eingebaute_apps`; dann
  zieht nur `kalender_einstellung._anschluesse()` um.
- **Überall gleich abgeleitet** (`core/adapter.py`):
  `kalender_ueber_cloud(ordner)` ⇔ die Instanz mit diesem Ordner hat
  `zencloud`; `kalender_google_an()` ⇔ `quelle == google`. Die
  vdirsyncer-Konfiguration eines Geräts (eigene oder aus dem Anschluss
  `google-kalender`) ist nur Zugang, keine Entscheidung.
- **Ohne Datei: wie vor dem 28.10.** (zählt als google): ohne
  Google-Anschluss fährt jedes Gerät seine eigene Konfiguration; mit
  Anschluss der alte Weg (Kalender über die Cloud, EINE Brücke per
  Mietvertrag, `kalender_mit_vertrag`). Nichts legt die Datei von selbst an.
- **Umstöpseln an einer Stelle:**
  `adapter_ablauf.kalender_quelle_setzen(id, quelle, wurzel)` bzw.
  `zentrale adapter calendar [google|zencloud|lokal]` (ohne Wort: zeigen;
  `zentrale adapter` zeigt die Quelle auch). Ändert nur den Wert, löscht nie
  eine Termin-Datei.
  - → `google`/`lokal`: Wert setzen, die Termine hier bleiben liegen.
  - → `zencloud`: erst die Mitte fragen —
    `abgleich.mitte_hat_kalender(ordner="data/kalender") -> bool|None`
    (ZEN-MOBIL, über `adapter_ablauf.mitte_hat_kalender`, wirft nie).
    None → Abbruch, nichts geändert. False → dieses Gerät füllt die Cloud:
    Wert setzen und gleich abgleichen im Block `adapter.kalender_fuellt()`
    (nur im Speicher dieses Prozesses); geht der Abgleich nicht hinaus, wird
    der Wert zurückgenommen (`offline`) — sonst legte der nächste Abgleich
    den eigenen Kalender beiseite. True → die Cloud gilt: der Ordner hier
    wandert nach `<abgleich>/kalender-vor-cloud/<zeit>/` (nie gelöscht, Sasha
    wählt dort selbst), dann abgleichen.
- **Die Cloud wird nie überschrieben — für jedes Gerät dieselbe Regel**
  (`adapter.vor_abgleich`, vor jedem Abgleich): gleicht der Kalender diesmal
  mit, kennt die Basis des Abgleichs (`<abgleich>/basis.json`) noch keine
  Datei aus `data/kalender/` und liegen hier Termine → Mitte fragen. True →
  beiseite; False → füllt; None → `MitteFehler`, kein Abgleich. Gilt auch
  für den alten Weg mit Google-Anschluss (wer ihn anlegt und die Cloud leer
  findet, füllt sie). Kein Merkzettel, kein Ursprung je Gerät mehr
  (`kalender_dabei.json`, `als_ursprung_merken`, `kalender_ursprung`,
  `eingerichtet.auf` als Ursprung: entfernt; alte Merkzettel liegen harmlos
  herum).
- **Die Frage kommt vom Abgleich:** der Adapter darf `abgleich` nicht
  importieren (Import-Kreis, `tests/test_kern_bauplan.py`).
  `vor_abgleich(…, mitte_hat_kalender=, basis_kennt=)` takes both as
  arguments; since 37e1a6f `core/abgleich._adapter_vorher` passes them
  (`_rueckfrage` and the adapter reading `basis.json` itself are gone;
  missing one → `MitteFehler`).
- **Altlast `kalender-mitte`:** liegt `data/adapter/anschluesse/kalender-mitte.json`
  noch, gilt sie als `kalender-haupt` mit `quelle=zencloud`; das nächste
  `kalender_quelle_setzen` schreibt die neue Datei und nimmt die alte weg. Auf
  dem Laptop gab es sie nie (geprüft 29.10.: nur `ki-anbieter.json`).
- **Achtung beim Zurück auf google:** Google sieht dann den Stand dieses
  Ordners; fehlen dort Termine, die Google noch hat, löscht vdirsyncer sie
  bei Google — die Löschsperre (mehr als 5 → Abbruch) fängt nur größere
  Mengen.
- **Offen:** ein Gerät, das früher schon den Kalender über die Cloud abglich
  (Basis kennt ihn), danach google/lokal fuhr und zurückkommt, gleicht
  normal dreiseitig ab (seine Löschungen gehen mit) statt beiseitezulegen. Stöpseln zwei Geräte im selben
  Augenblick auf zencloud um und finden beide die Cloud leer, füllen beide
  (der Abgleich führt je UID zusammen).
- **First fill: slow, interruptible, continuable (since 2026-10-29).**
  Occasion: Sasha switched the laptop; the first fill (590 files, normally
  ~13 s) hung for minutes without output, he pressed Ctrl-C, and running it
  again only said "already zencloud".
  - *Sign of life:* `kalender_quelle_setzen(…, report=)` reports `syncing`
    (n = files here, `upload` = filling the empty hub) and `done`; the CLI
    (`befehle.SignOfLife`) prints "Uploading the calendar to the cloud (N
    files) …" and every 15 s "… still syncing (n s)". Real progress (file n
    of N) needs a hook in core/abgleich*, not built (owned elsewhere):
    `abgleich.abgleichen(wurzel, …, progress=None)` passes it to the hub,
    and `HttpMitte._hochladen` (core/abgleich_mitte.py) calls
    `progress(done, total)` after each `PUT /v1/mitte/blob/<sha>` (total =
    `len(d["fehlen"])`). The CLI would then print it instead of the seconds.
  - *Ctrl-C keeps zencloud* (result `interrupted`, CLI exit 130). Safe,
    because the hub accepts a new state in ONE call (blobs first, then
    `POST /v1/mitte/stand`; the setting file goes in the same state): either
    nothing arrived (the hub's index has no calendar → the next sync asks,
    gets "empty" and fills) or all of it arrived (the next sync first
    finishes its plan, `_vorhaben_nachholen`, so the base knows the calendar
    before `vor_abgleich` asks — nothing is set aside). Rolling back to
    google would let the Google timer run again on a half-switched device.
    Checked live 2026-10-29: after Sasha's Ctrl-C the timer sync completed
    the fill, the base knows 596 `data/kalender` files, nothing set aside.
  - *Fill pending* = `adapter_ablauf.calendar_fill_pending()`: source
    zencloud, events here, the base knows none of them (derived, no marker
    file). `zentrale adapter` and `zentrale adapter calendar` show it.
  - *The same command again* continues instead of "already zencloud": it
    only runs a sync and decides nothing beforehand (the sync's own order:
    finish plan → `vor_abgleich` asks the hub → fill or set aside). →
    `continued` or `incomplete` (+ reason); a new set-aside folder is
    reported.
  - An error in the fill sync rolls the value back only if the hub has no
    calendar afterwards; otherwise the state went out (→ `fuellt` + error).
- **Google timer with zencloud/lokal (checked 2026-10-29):** the timer
  `zentrale-kalender-sync` keeps running every 3 min and refuses at once
  (`zentrale adapter run` → "Calendar source is 'zencloud', not google",
  exit 0; `scripts/kalender_sync.py` the same before any work): no
  vdirsyncer, no ghost cleanup, no Google backup or rotation, no state file,
  no file under the project touched
  (`tests/test_calendar_source_fill.py::test_no_google_and_no_ics_work`).
  **Deliberately not switched off by the source switch:** the setting
  travels to every device, the switch runs on one. A device whose timer was
  disabled there would stay disabled when another device switches back to
  google — it would never run Google again. Doing it right means every
  device reconciling its timer with the source (e.g. in `zentrale sync
  --automatic`); not worth it for a run that costs nothing.
- Tests: `tests/test_adapter.py` (`test_quelle_*`, `test_mitte_hat_kalender_vertrag`, `test_fuellen_*`, `test_der_fuellende_*`,
  `test_spaeteres_geraet_*`, `test_umstoepseln_*`, `test_alter_schalter_*`,
  `test_zwei_kalender_apps_*`, `test_cli_kalender_quelle`),
  `tests/test_kalender_cloud.py::test_zencloud_erster_fuellt_spaeterer_legt_beiseite`,
  `tests/test_calendar_source_fill.py` (Ctrl-C, continuing, sign of life,
  alarm, no Google with zencloud/lokal).

## Gebaut (2026-10-24)

- Module (Schicht 1): `core/adapter.py` (Anschlüsse, Kalender-Schalter,
  Kalender kommt einmal je Gerät dazu), `adapter_geheim.py`,
  `adapter_bruecke.py`, `adapter_vdirsyncer.py` (Vorlage ↔ Konfiguration:
  `{"$geheim"}`, `{"$datei"}` für token_file, `{"$ort": "kalender"}` für
  den Kalender-Ordner, ~-Pfade bleiben ~), `adapter_ablauf.py` (einrichten,
  bruecke_lauf), `abgleich_ics.py` (Termine je UID zusammenführen).
- Abgleich: `abgleich_apps.jetzt_erlaubt` schneidet `data/kalender/**` ohne
  Kalender-Anschluss und `geheim.enc` ohne Konto heraus. Vor dem Abgleich
  umschlüsseln und `adapter.vor_abgleich` (erstes Mal mit Kalender:
  beiseite, wenn die Cloud schon einen hat); danach KI-Schlüssel in die
  Umgebung. (Bis 29.10. auch ein Merkzettel `kalender_dabei.json`.)
- KI: Rangfolge echte Umgebung > Adapter > `ai_config.json`
  (`ai_config.injiziert`); `providers` legt beim Import ein;
  `ki_uebernehmen()` beim Start des Backends, bei `zentrale sync` und
  `zentrale adapter setup` — ein Schlüssel verlässt ai_config.json erst,
  wenn er im Adapter lesbar ist; ein abweichender bleibt dort (Rückfall).
- **Neue KI-Schlüssel und das laufende Backend** (geprüft 24.10.): das
  Backend liest sie nur beim Start (`core/main.py`, Import von
  `providers`), die SDK-Clients behalten den Schlüssel (`cloud.py`,
  `cloud_openai.py`); `zentrale sync` läuft in einem eigenen Prozess. Deshalb
  vergleicht `zentrale sync` die lesbaren Schlüssel vor/nach dem Abgleich:
  neu oder geändert → eine Zeile, und läuft `zentrale-kern.service`, wird er
  per `try-restart` neu gestartet (auch vom Timer); sonst der Rat, ZENTRALE
  neu zu starten.
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
- **2026-10-28** — Schalter `kalender-mitte`: Kalender über die Mitte ohne
  Google; Ursprung nur, wer zuerst einschaltet.
- **2026-10-29** — von Sasha verworfen (Zustand je Gerät, Wahl am Konto statt
  an der App). Neu: Einstellung der Kalender-App mit `quelle` google |
  zencloud | lokal, überall dieselbe Datei; Umstöpseln mit
  `kalender_quelle_setzen`; statt Ursprung die Frage „hat die Cloud schon
  einen Kalender?" + Beiseitelegen.
