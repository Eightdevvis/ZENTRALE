# Gefahrzonen — Fehler, die versteckt wiederkommen

Hier stehen Fehlerarten, die nicht mit einem Fix erledigt sind: das Muster
taucht beim nächsten neuen Code wieder auf, oft an einer Stelle, an die
niemand denkt. Je Gefahrzone: was der Fehler ist, woran man ihn erkennt,
wo er sich versteckt, wie es richtig geht, welcher Wächter ihn fängt und
die bekannten Funde (damit sich das Muster wiedererkennen lässt).

## 1. Eingefrorener Tag (seit 20.10.2026)

**Was:** „heute" wird einmal berechnet (beim Import, beim Start, beim
Öffnen einer Ansicht) und danach nie erneuert. Solange man ZENTRALE jeden
Tag neu startet, fällt es nicht auf. Im Dauerbetrieb (TUI läuft über Nacht,
Backend bald als Server) steht nach Mitternacht alles auf dem Vortag.
Anlass: Sasha am 20.10.2026: „zentrale steht immer noch auf 19.10. böse
falle, vorallem wenn zentrale künftig auf nem server bald im dauerzustand
weiterlaufen soll."

**Woran man es erkennt:**
- Nach Mitternacht steht „heute" auf dem Vortag (Kalender-Markierung,
  gewählter Tag, „heute · Montag …"-Kopf), bis man die Ansicht neu öffnet
  oder neu startet.
- Alarme vom Vortag bleiben stehen (der Konflikt von gestern ist keiner
  mehr), neue erscheinen verspätet.
- „Schon gezeigt"/„weggeklickt" gilt für die Sitzung statt für den Tag:
  am neuen Tag bleibt eine Erinnerung stumm.
- Ein Puffer, dessen Schlüssel kein Datum hat, liefert die Antwort von
  gestern (mit ihrem `today`).
- Nach einem Hot Reload kurz nach Mitternacht springt eine Ansicht auf
  gestern zurück (der mitgereiste Tag war „heute" von gestern).

**Typische Verstecke:**
- Konstanten auf Modulebene: `HEUTE = date.today()`, `_JAHR = …now().year`.
- `__init__`: `self.tag = date.today()` — gilt für die ganze Lebenszeit.
- Defaults in Signaturen: `def f(tag=date.today())` — ausgewertet EINMAL
  beim `def`, nicht beim Aufruf. Richtig: `tag=None` und im Rumpf
  `tag = tag or uhr.heute()`.
- Caches: `@lru_cache`/`@cache` über einer Funktion, die „heute" fragt;
  eigene Puffer-Dicts, deren Schlüssel den Tag nicht enthält.
- Hintergrund-Schleifen, die etwas Tagesbezogenes nur beim Start oder nur
  in langen Abständen neu rechnen.
- Gespeicherte Anker in der TUI: `K["ref"]`, `W["tag"]`, gemerkte Stände je
  Ansicht, „einmal je Sitzung"-Mengen, Hot-Reload-Übergaben.

**Wie richtig:**
1. „heute"/„jetzt" kommen aus **der einen Uhr**, `core/uhr.py`:
   `uhr.heute()`, `uhr.jetzt()` — gefragt bei jedem Gebrauch. In Tests
   stellbar: `with uhr.gestellt(datetime(2026, 10, 19, 23, 59)):` und
   `uhr.vorstellen(minutes=2)`. Die TUI darf sie importieren (Tür in
   [bauplan_kern.md](bauplan_kern.md)). Ältere Stellen mit `date.today()`
   im Funktionsrumpf sind in Ordnung (sie fragen jedes Mal) und werden beim
   Anfassen umgestellt.
2. Wer sich etwas mit Tagesbezug **merkt**, meldet sich beim
   **Tageswechsel-Ereignis** an: `uhr.Tageswechsel` — `pruefen()` in jedem
   Schleifendurchlauf, Hörer bekommen `(alt, neu)` genau einmal (auch nach
   Tagen Ruhezustand). Angemeldet sind:
   - TUI (`tui/zentrale_tui.tageswechsel_verkabeln`): Kalender (Puffer
     fällt; was auf dem alten Heute stand, rückt mit — auch gemerkte Stände
     der Ansichten A/B/C; ein bewusst gewählter anderer Tag bleibt stehen),
     Graphen (Zyklus-Vorhersage neu), Graph-Reminder (weggeklickt gilt für
     den Tag), Lebenslauf-Zeile `TAGESWECHSEL`.
   - Backend (`core/main.tageswechsel_verkabeln`): Alarme sofort neu
     rechnen, Event `DAY_CHANGED` in den Loop, Log-Zeile.
3. Puffer mit Tagesbezug tragen den Tag im Schlüssel (wie
   `Bedienung.daten()`: `(stil, ref, heute)`) — dann stimmt es auch, wenn
   das Ereignis einmal nicht zugestellt wird.
4. Hot Reload: nicht den Tag mitgeben, sondern „stand auf heute" (siehe
   `Kalender.stand_fuer_neustart`).

**Wächter:** `tests/test_tageswechsel.py::test_waechter_kein_eingefrorener_tag`
(AST über `core/`, `ui/`, `tui/`): meldet `date.today()`, `datetime.now()`/
`today()`/`utcnow()`, `uhr.heute()`/`jetzt()` auf Modul-/Klassenebene, in
`__init__`, als Default einer Signatur und in gecachten Funktionen.
Begründete Ausnahmen stehen in `AUSNAHMEN` im Test (heute nur die
Vorbelegung von `Kalender.__init__`); veraltete Ausnahmen meldet
`test_waechter_ausnahmen_gibt_es_noch`. Gespeicherte Anker in Dicts und
Puffer ohne Datumsschlüssel findet er NICHT — dafür die Verstecke oben
und die Tests über Mitternacht im selben Test (`uhr.gestellt` +
`vorstellen`). Für Test-Erwartungen gilt außerdem Regel 8 in
[../betrieb/tests.md](../betrieb/tests.md): kein Ergebnis darf vom heutigen
Datum abhängen.

**Bekannte Funde (20.10.2026, alle behoben):**

| Stelle | Was hielt den Tag fest | Wirkung |
|---|---|---|
| `tui/ansichten/kalender.py` `Kalender.__init__` / `oeffnen()` | `K["ref"]` und `W["tag"]` beim Öffnen auf `date.today()`, danach nie bewegt | **Sashas 19.10.:** TUI lud am 19.10. 19:12 neu und öffnete den Kalender wieder; über Mitternacht blieb er dort |
| `tui/ansichten/kalender_bedienung.py` `Bedienung.daten()` | Puffer-Schlüssel `(stil, ref)` ohne Datum; die Antwort trägt `today` | **Sashas 19.10.:** auch die Heute-Markierung blieb auf dem Vortag |
| `tui/zentrale_tui.py` Hot-Reload-Übergabe des Kalenders | gab den Tag mit, nicht „stand auf heute" | ein Neuladen nach Mitternacht hätte auf gestern zurückgestellt |
| `tui/ansichten/erinnerung.py` `nag_dismissed` | weggeklickt „bis Sitzungsende" | am neuen Tag kein „bitte eintragen" |
| `tui/ansichten/graphen.py` `G["cyc"]` | Zyklus-Vorhersage nur beim Öffnen geholt | „in 3 Tagen" stimmt nach Mitternacht nicht mehr |
| `core/main.py` Alarm-Heartbeat | Alarme nur alle ~5 min neu | bis zu 5 min Alarme vom Vortag |
| `core/map/layers/viina.py` `_YEAR`/`_URL` | Jahr auf Modulebene | im Dauerbetrieb über Silvester das alte Jahr |

Nicht betroffen (geprüft): `/api/calendar` (`today` bei jedem Aufruf —
live am 20.10. richtig), Imprint und Alarme im Kern (`kalender_konflikte`,
rechnen ab heute bei jedem Aufruf), Jetzt-Block des Prompts
(`ki_prompt`), Morgenblick, Kachel „mitlaufend" (`kachel_kalender`, ttl
60 s), Kopfzeilen-Uhr der TUI.

## 2. Stumme Leere (seit 20.10.2026)

**Was:** eine Rechnung liefert „nichts" — ob es wirklich nichts gibt, ob
die Daten fehlen oder ob sie abgestürzt ist, sieht man nicht. Ein
`except Exception: x = {}` oder ein leeres Ergebnis ohne Grund macht aus
einem Fehler eine leere Fläche, die wie „gerade nichts los" aussieht.

**Woran man es erkennt:** ein Feld war einmal da und ist seitdem einfach
weg, ohne Meldung im Log; die API liefert `{}`/`[]`, obwohl Daten da sind.

**Wie richtig:** nie crashen, aber nie stumm: ein leeres Ergebnis trägt
einen kurzen Grund (`{"fehler": "…"}` unter einem Schlüssel, den die
Fronten ignorieren), ein abgefangener Absturz zusätzlich eine Log-Zeile
(`state.push_log`). Und bei Vorhersagen prüfen, was passiert, wenn die
Vorhersage selbst in der Vergangenheit liegt.

**Bekannte Funde:**

| Stelle | Was war stumm | Wirkung |
|---|---|---|
| `ui/routen/kalender.py` `cycle` + `core/cycle.day_marks` | `except: {}`; markiert wurde nur der EINE nächste Start — verstrichen und nichts neu geloggt → jeder spätere Monat leer, ohne Grund | **Sashas 20.10.:** „periodentracker im kalender wurde einmal angezeigt, danach nie wieder" (behoben: fortgeschrieben + `fehler`) |

## 3. Standard liest anders als wir (seit 22.10.2026)

**Was:** ZENTRALE rechnet ein Format nach seiner eigenen Lesart (oft der
einer Bibliothek), der Standard meint etwas anderes. Bei uns unsichtbar,
sichtbar erst bei Google/am Handy.

**Woran man es erkennt:** Google oder das Handy zeigen einen Termin, den
ZENTRALE nicht zeigt (oder umgekehrt) — fast immer am Rand einer Serie
(erster Tag, letzter Tag, Zeitzone, Ganztags-Ende).

**Wie richtig:** beim Schreiben nach .ics die Standard-Semantik herstellen
(nicht unsere), unsere Lesart verlustfrei in `X-ZENTRALE-*` aufheben, und
beim Lesen prüfen, ob die X-Property noch zum Standard-Feld passt (sonst gilt
das Standard-Feld). Test: Vorkommen nach RFC (DTSTART zählt) == Vorkommen in
ZENTRALE.

**Bekannte Funde:**

| Stelle | Was wich ab | Wirkung |
|---|---|---|
| `kalender_ics_abbildung.routine_kalender` | DTSTART = `seit`; dateutil überspringt einen Anfang ohne Regel-Tag, RFC 5545 zählt ihn | Phantom-Termine bei Google am Starttag (z. B. „ExPhy Tutorium" Do statt nur Fr); behoben 22.10.2026: DTSTART = erstes Vorkommen, `X-ZENTRALE-SEIT` |
