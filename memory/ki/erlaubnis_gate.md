# Erlaubnis-Gate und Knopf-Dialog

**Stand 2026-10-11:** Werkzeuge mit `erlaubnis` im Register fängt Python **vor
der Ausführung** ab und fragt Sasha mit Knöpfen („ja, nur dieses mal" / „ja, für
dieses gespräch" / „ja, immer" / „nein"); keine Antwort heißt nein. `ask_choice`
(auf `klein` `frage_knopf`) ist dagegen ein Rückfrage-Werkzeug, das die KI selbst
ruft. Beides blockiert im selben Zug.

**Warum:** nicht modellgetrieben — ein 9b würde ein `frage_erlaubnis` nicht
zuverlässig vor jedem Eingriff rufen; ein hart verdrahtetes Gate ist robust.
Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Knopf-Dialog: Auto-Gate + `frage_knopf`

Das Dashboard kann die Konsolen-Eingabe gegen **2–4 Knöpfe** tauschen
(navigierbar per Pfeiltasten + Enter, Kiosk ohne Maus). Zwei Auslöser, ein
geteilter Mechanismus (blockierender `state.wait_permission`):

**(A) Auto-Gate für sensible Tools** — bestätigungspflichtige Tools
(Feld `erlaubnis` im Werkzeug-Register, z. B. die Kalender-Schreiber
`add_calendar_entry`, `add_calendar_routine`, `edit_calendar_routine`,
`add_calendar_pause`, `delete_calendar_entry` **plus** die Internet-Pipe `web_suche`, `hole_url`) fängt das Backend **vor der
Ausführung** ab und zeigt **JA / NEIN**. Nur bei „ja" läuft das Tool, bei
„nein"/Timeout wird es übersprungen. Lokales Lesen/Auskunft (`read_calendar`,
`read_file`, …) bleibt ungated; alles was Daten schreibt oder das LAN verlässt
ist gegatet.

> **Nicht modellgetrieben – Absicht.** Die KI ruft ihr Schreib-Tool ganz
> normal; das Gate kommt automatisch davor. Frühere Idee war ein Tool
> `frage_erlaubnis`, das die KI von sich aus ruft – verworfen, weil ein 9b
> das **nicht zuverlässig** vor jedem Eingriff täte ([[feedback_permission_gate_backend]],
> [[project_history_vergiftung]]). Ein hart verdrahtetes Gate auf der Tool-
> Liste ist robust statt vom Modellverhalten abhängig.

**(B) `frage_knopf` – KI-initiiert** — braucht die KI mitten in einer Aufgabe
eine knappe diskrete Entscheidung (statt auf freien Text zu warten), ruft sie
**selbst** `frage_knopf(frage, optionen=[…])`. Ohne `optionen` = Ja/Nein, sonst
2–4 eigene Labels (z.B. `["Deutsch","Englisch"]`). Das gewählte Label kommt als
`tool`-Result zurück, die KI macht im selben Zug weiter. Anders als das Gate ist
das bewusst modellgetrieben – es ist kein Sicherheits-Riegel, sondern ein
Rückfrage-Werkzeug, das die KI gezielt einsetzt.

**Mechanik – blockierend, nahtlos (ein Zug):**

1. **Gate (A):** Im Tool-Loop (`chat_stream`) greift VOR `active_exec` der
   Check `erlaubnis.braucht_erlaubnis(name, args)`; `erlaubnis.frage(name,
   args)` baut die Frage („Soll ich »Zahnarzt« am … eintragen?"), Optionen =
   Default Ja/Nein. **`frage_knopf` (B):** eigener Branch baut Frage + Optionen
   aus den Call-Args (sanitisiert: ≥2, max 4). Beide rufen
   `state.request_permission(options, timeout_default)`, yielden ein
   **permission-Event** (`{"permission": {"frage", "optionen"}}`) und
   **blockieren** in `state.wait_permission()`.
2. `ui/routen/ki.py` macht ein SSE `permission` daraus; das Frontend zeigt die Frage als
   KI-Zeile (+ TTS) und baut die Knopf-Leiste dynamisch aus `optionen` (fehlt →
   JA/NEIN). Der SSE-Reader läuft **nicht** zu Ende – die Verbindung bleibt offen.
3. Klick → `POST /api/permission_answer {answer}` (eigener Thread), gegen die
   angebotenen Labels validiert (case-insensitiv, kanonisches Label zurück) →
   `state.answer_permission()` setzt das `threading.Event` → der blockierte
   `chat_stream` wacht auf. Gate: bei „ja" durchfallen zur Ausführung, sonst
   abschlägiger `tool`-Result. `frage_knopf`: gewähltes Label als `tool`-Result.
   Beides im **selben Zug**.

Das funktioniert nur, weil Flask **multi-threaded** läuft
(`app.run(threaded=True)`, explizit) – sonst käme der Antwort-Request am
blockierten Stream nicht vorbei → Deadlock. `wait_permission` (180 s Timeout)
gibt den bei `request_permission` gesetzten `timeout_default` zurück: bei
Gate **und** `frage_knopf` `None` (seit 2026-10-11 auch beim Gate; vorher „nein").
Zeitablauf ist kein Nein: das Werkzeug läuft nicht, das Ergebnis ist
`[ergebnis: keine_antwort]` („Sasha hat nicht geantwortet … frag im Text nach"),
die Erledigt-Zeile sagt „keine Antwort (Zeit abgelaufen)", der Zug-Ablauf
„(keine Antwort, Zeit abgelaufen)". Ein echtes Nein bleibt `abgelehnt`. Grund:
Zeitablauf ist keine Ablehnung. Bei `frage_knopf` Ergebnis `[ergebnis: keine_antwort]` (seit 2026-10-08,
s. „Belegt oder gesagt" in [werkzeuge.md](werkzeuge.md)). Log: `AI → ERLAUBNIS?`/`FRAGE …`
bzw. `AI ← ERLAUBNIS:`/`WAHL: …`. Frontend-Details (perm-bar, N-Knopf-Nav):
[memory/system/dashboard.md](../system/dashboard.md). Tutor-Modus: beides aus (fremdes Tool-Set). Neues
Tool gaten = `erlaubnis=` + `frage=` + `alltag=` in seinem Eintrag im Werkzeug-Register.

### Geltungsbereiche: einmal / dieses Gespräch / immer (seit 2026-10-07)

Sasha: „beides einstellbar machen" (wie bei Claude Code). Die Gate-Frage hat
seitdem Knöpfe statt Ja/Nein: **„ja, nur dieses mal"**, **„ja, für dieses
gespräch"**, **„ja, immer"**, **„nein"** (das permission-Event trägt
`optionen`, `erlaubnis: true` und `geltung: [einmal, gespraech, immer,
nein]`; j = erster Ja-Knopf, n/Esc = nein wie bisher). Logik in
`core/erlaubnis.py` (`optionen`, `deuten`, `vorab`, `merken`,
`zuruecknehmen`), aufgerufen in `werkzeug_schleife._ask_permission`:

- **einmal** — das alte Ja. Ein Client, der nur „ja" schickt, bekommt das
  (`/api/permission_answer` übersetzt).
- **für dieses Gespräch** — nur im Arbeitsspeicher, an die Gesprächs-id des
  Zugs (`core/zug.py`) gebunden. Aufgehoben, sobald ein anderes Gespräch
  dran ist: `erlaubnis.gespraech_beginnt(gid)` in `/api/chat`,
  `/api/gespraeche` (neu), `/api/gespraeche/aktiv`, `/api/chat/clear`. Ohne
  Gespräch (Erinnerungen vom Takt) kein Knopf dafür. Neustart = weg.
- **immer** — `ai_config` Schlüssel `immer_erlaubt` (Liste kanonischer
  Namen, `data/ai_config.json`, synct mit den anderen Einstellungen).
  Zurücknehmen: `/erlaubnis` im Chat (`GET /api/erlaubnis`,
  `POST /api/erlaubnis/zuruecknehmen`).
- **Kein „immer"** (Register `immer_erlaubbar=False`): Kernakten
  (`write_note` auf Hausregeln/Steckbrief/Ziele — steuern die KI auf Dauer),
  alles was löscht oder überschreibt (`delete_calendar_entry`,
  `edit_calendar_routine`, `rewrite_note`, `edit_skill`, `fetch_document`
  bei gleichem Namen) und `save_from_sandbox` (nur auf Sashas Initiative).
  Auch beim Prüfen: steht so ein Werkzeug von Hand in der Liste, wird
  trotzdem gefragt.
- **Nur „einmal"** (Register `nur_einmal(args)`): `run_code` über 120 s.
- Pro Werkzeug, nicht pro Argument („run_code immer" = jedes Programm bis
  2 Minuten). Erlaubt ohne Frage steht als `AI ✓ ERLAUBT (immer|gespraech)`
  im Log.

`save_memory` ist mit dem Legacy-Pfad rausgeflogen – der Graph-Extraktor
läuft eh nach jedem Turn automatisch. Kalender-Tools (`read_calendar`,
`add_entry`, `add_routine`) kommen mit dem Kalender-System (siehe
[memory/werkzeuge/kalender_system.md](../werkzeuge/kalender_system.md)).

## Historie

- **2026-06** — Auto-Gate und `frage_knopf`.
- **2026-10-07** — Geltungsbereiche einmal / dieses Gespräch / immer.
- **2026-10-08** — `ask_choice` ohne Antwort → `keine_antwort`.
- **2026-10-11** — Gate-Zeitablauf = `keine_antwort`, nicht `abgelehnt`.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
