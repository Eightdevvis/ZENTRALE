# Modell-Profile — eine eigene Umgebung je Modell

**Stand 2026-10-10.** Anlass: Am 09.10. fiel der Chat wegen des Budget-Deckels
auf qwen-plus zurück (Gespräch `20261009-150713-e03002`). qwen rief kein
Werkzeug, schrieb „Alles korrigiert: alle Vorlesungen … laufen jetzt exakt vom
12.10. bis 18.12.2026" und erfand Kennungen. Sasha: *„schwache modelle brauchen
manchmal strategien, die starke modelle wiederum stören … qwen eine eigene
einstellung geben, sodass nicht nur modell geswitched wird, sondern umgebung,
config, usw."*

## Mechanik

`core/profil/modelle/` — ein **Profil** legt sich über die Schiene (`gross`).
Die Schiene bleibt, was Ausführer und Prüfer wissen (Kennungen, Prüfer-Strenge,
Umschlag); das Profil darf für EIN Modell überschreiben:

| Was | Profil-Attribut | Wo es greift |
|---|---|---|
| fester Kopf | `system(text)` | `cloud._static_system(…, schiene=)` |
| Erinnerung am Ende jeder Nachricht | `erinnerung(verlauf)` | letzter Absatz im Kontext-Umschlag (`ModellSchiene.erinnerung`) |
| Werkzeug-Beschreibungen/-Felder | `werkzeuge(tools)` | einmal beim Bau (Kopien, `gross.TOOLS` bleibt) |
| Werkzeug-Auswahl je Gespräch | `auswahl(tools, verlauf)` | `cloud_openai.chat_stream` |
| Pflicht-Werkzeug je Runde | `tool_choice(nr=, verlauf=, tools=)` | `_OpenAIAdapter._extra` |
| Temperatur, Ausgabe-Länge, Zusätze | `TEMPERATUR`, `MAX_TOKENS`, `EXTRA` | `_OpenAIAdapter` (ein Wert des Aufrufers geht vor) |
| Zusatz-Prüfer | `pruefer(basis, messages=, werkzeuge=)` | legt sich um `ehrlichkeit.Pruefer` |

Welches Modell welches Profil bekommt: Einstellung **`modell_profile`**
(`ai_config.setting`, Env `ZENTRALE_MODELL_PROFILE` als JSON), z. B.
`{"qwen-plus": "qwen", "qwen-*": "qwen"}` — genauer Name vor Muster (fnmatch),
`{}` schaltet alles ab. Standard (`modelle.STANDARD`): `{"qwen-*": "qwen"}`.

**Ohne Profil kommt die Schiene selbst zurück** — dasselbe Objekt; Claude fährt
byte-gleich wie vorher (`tests/test_modell_profile.py`: Kopf, Werkzeuge,
Aufruf ohne `tool_choice`/`extra_body`, Temperatur/Länge wie vorher).
Gebaut ist es nur im OpenAI-kompatiblen Weg (`cloud_openai`), denn nur dort
fährt heute ein Modell, das es braucht; der Anthropic-Weg nimmt das Profil
nicht an (`cloud._profil()` ohne Modell).

Ein weiteres Modell zähmen: Datei neben `qwen.py` anlegen, in `PROFILE`
eintragen, in `modell_profile` zuordnen. Was ein Profil nicht setzt, kommt von
der Schiene.

## Das qwen-Profil (`core/profil/modelle/qwen.py`, `zusatzpruefer.py`)

1. **Arbeitsweise vorn, Erinnerung hinten.** Acht kurze Pflichten VOR der
   Persona: bei klarem Änderungswunsch sofort das Werkzeug (die Ja/Nein-Frage
   stellt ZENTRALE), „ok" heißt ausführen, erst `read_calendar` (mit `suche`,
   ohne Zeitraum; „Was ansteht" ist nicht der Kalender; leere Stichwort-Suche
   → ohne `suche` lesen), Erfolg nur mit `[ergebnis: ok]`, nichts erfinden
   (auch kein Serien-Ende, Suchtreffer kennzeichnen), „halb X" = eine halbe
   Stunde vor X und das Ende wandert mit, nur ändern, was verlangt ist, kurz
   antworten mit Quelle. Eine Zeile Erinnerung als letzter Absatz jeder
   Nachricht — mit den Uhrzeiten der neuesten Nachricht, von Python
   übersetzt („halb sieben" = 6:30 oder 18:30). Name und Pronomen als
   Platzhalter ({nutzer}, {er} …, `core/nutzer_angaben.py`) wie in gross.
2. **Werkzeuge entschärft.** `read_calendar` ohne `layers` (qwen filterte auf
   „routinen" und fand nichts); `edit_calendar_*` mit „Ende mitschieben" und
   „von/bis nur, wenn sich der Zeitraum ändert".
3. **Zusatz-Prüfer** (Python, je Fehlerart höchstens eine Korrekturrunde,
   nur wenn der Prüfer der Schiene nichts hat): ~~*Erlaubnis statt Tat*~~
   (seit 2026-10-10 im Prüfer der Schiene für ALLE Modelle,
   `ehrlichkeit.erlaubnis_befund` — hier entfernt, sonst doppelt), *Aufruf als Text*
   (`read_calendar(zeitraum=…)` als Antwort), *nur Stichwort gesucht* („gibt
   es nicht" nach leerer `suche`), *Tat ohne Werkzeug* („ist gelöscht",
   „Alles korrigiert" ohne schreibendes Werkzeug — strenger als der
   Tat-Prüfer der Schiene, der auf wenige Falschtreffer gebaut ist),
   *Zeit nicht belegt* (nach einer Änderung nennt die Antwort eine
   Zeitspanne, die kein Werkzeug-Ergebnis zeigt).
4. **Erst lesen erzwungen.** In der ersten Runde eines Zugs, in dem Sasha den
   Kalender ändern will oder einer Frage zustimmt (nicht bei „nix eintragen",
   „nur nachschauen"): `tool_choice = read_calendar`.
4b. **antwort als Pflicht (Schalter, Standard aus, 2026-10-10).** Mit der
   Einstellung `antwort_pflicht` = an muss qwen in jeder Runde ein Werkzeug
   rufen (`tool_choice "required"`, außer Runde 0 mit erzwungenem
   `read_calendar`) — die Antwort selbst dann über `antwort` mit den Feldern
   der Selbstauskunft ([ehrlichkeit_live.md](ehrlichkeit_live.md)). Anders
   als „irgendein Werkzeug" in Runde 6 hat qwen damit einen Ausgang, der
   nichts ändert. Ungemessen; messen mit
   `--einstellung antwort_pflicht=an` gegen ohne (f01k).
5. **Werkzeug-Auswahl je Gespräch.** Fester Kern (Kalender, Notizen, Suche,
   Netz, Knopf …) plus Gruppen (Browser, Dateien, Dokumente, Post,
   Messreihen, Skills), die erst bei passenden Wörtern in Sashas Nachrichten
   dazukommen: Kalender-Zug 21 statt 54 Werkzeuge, ~16.600 statt ~32.000
   Zeichen. Die Liste wächst im Gespräch nur (Präfix-Cache). Ein Werkzeug
   ohne Gruppe ist immer dabei.

## Gemessen (Nacht 09./10.10.2026, qwen-plus, Prüfstand)

Neue Prüfstand-Optionen dafür: `--anbieter qwen --modell qwen-plus`,
`--einstellung NAME=WERT` (nur in der Wegwerf-Kopie der Einstellungen),
`--faelle tests/pruefstand/faelle_modelle` (vier Fälle aus den qwen-Fehlern:
m01 „ok" muss ausführen, m02 klarer Auftrag ohne Rückfrage, m03 löschen +
nachlesen, m04 „halb acht" mit Dauer). Ein Lauf je Fall, meist ohne Richter
(Endzustand + Transkripte), Abschluss mit Haiku-Richter.

Grundmessung (ohne Profil, main f85f625) gegen Abschlusslauf (mit Profil,
Stand Runde 10, main af52937), beide mit Haiku als Richter, ein Lauf je Fall:

| f01–f07 | ohne Profil | mit Profil |
|---|---|---|
| Fälle ganz richtig | 5/7 | 5/7 |
| Endzustand-Prüfungen | 21/28 | **25/28** |
| f01 (das Gespräch vom 08.10.) | 4/9 | **7/9** |
| schreibende Aufrufe (wo verlangt) | 6 | 16 |
| Behauptungen belegt / unbelegt / **falsch** | 34 / 18 / **6** | 54 / 23 / **1** |
| Modell-Kosten | 0,33 € | 0,25 € (f01: 0,24 → 0,15 €) |

Dazu im Abschlusslauf f08–f11 3/4 (17/18; ohne Profil ebenfalls 3/4, 17/18 —
aber f10 ohne Profil sah nie in den Kalender und fragte „welche Uni-Sachen?",
mit Profil fand es die drei Serien) und die Modell-Fälle m01–m04: ohne
Profil 2/4 (9/11), mit Profil 3/4 im Abschlusslauf, **4/4 (11/11)** nach
Runde 12. Runde 12 (Uhrzeiten vorgerechnet, Zeit-Prüfer, „nur nachschauen"
heißt berichten) danach auf f03, f08, m01–m04: alle ganz richtig (22/22).

Gezählt „unbelegt" steigt mit, weil mit Profil mehr gesagt und getan wird
(78 statt 58 Behauptungen); der Anteil bleibt (31 % → 29 %), „falsch" fällt
von 6 auf 1. Der Rest „unbelegt" ist fast ganz f01 (Browser-Seiten, die
Haiku nicht als Beleg zuordnet) — für Urteile, auf die es ankommt, Sonnet
richten.

Was die Runden zeigten (Einzelheiten und alle Zahlen: Protokoll der Nacht,
`~/.claude/jobs/938c900a/tmp/qwen_nacht/`):

- **Prompt allein reicht nicht.** Der Arbeitsweise-Block brachte den größten
  Sprung (Runde 1: 7/8 Fälle statt 5/7), aber „frag nicht ‚soll ich‘" griff
  nur zufällig — dieselbe Fehlerart wechselte von Lauf zu Lauf den Fall
  (Runde 3). Was Python sehen kann, prüft deshalb Python (Zusatz-Prüfer).
- **Krücken haben Nebenwirkungen.** Ein Beispiel mit konkreten Werten
  („19:00–20:00, halb acht → 19:30–20:30") reparierte m04 und machte in f03
  aus „halb sieben" 19:30 (Runde 6) — Beispiele nur mit neutralen Werten.
  `tool_choice="required"` (irgendein Werkzeug) zwang qwen bei fehlender
  Angabe zum Erfinden (Serie mit `bis = von`); gezielt `read_calendar`
  erzwingen schadet nie. Und erzwungenes Lesen auf „noch nix EINTRAGEN" lenkte
  vom LSF ab (Runde 9) — Verneinung ausnehmen.
- **Mehr Tat heißt auch mehr Übertat.** Mit Profil handelt qwen — in f01
  trug es dann auch eine nicht gewählte Übungsgruppe ein und löschte
  ungefragt; Regel 7 („nur, was verlangt ist") kam dafür dazu.
- **Streuung ist groß.** Ein Fall kippt zwischen zwei Läufen ohne Änderung
  (f02 ohne Profil einmal 2/4, einmal 4/4). Entschieden wurde nach
  wiederkehrenden Mustern in den Transkripten, nicht nach Einzelfällen.
- **Was Python rechnen kann, rechnet Python.** „halb sieben" blieb trotz
  Regel mit Beispielen unzuverlässig (Abschlusslauf: wieder 19:30); seit
  Runde 12 steht die Übersetzung („= 6:30 oder 18:30") als Zeile in der
  Erinnerung am Ende. Ebenso der Zeit-Prüfer: nach einer Änderung muss jede
  genannte Zeitspanne in einem Werkzeug-Ergebnis stehen.
- `tool_choice="required"` nimmt DashScope an, obwohl die Doku nur
  auto/none/Funktion nennt (geprüft 09.10.); `enable_thinking` mit Werkzeugen
  geht über `extra_body` (nicht eingesetzt — nicht gemessen).

Offen: Ein Lauf je Fall — die Zahlen sind Stichproben. m01 Zug 2 erfand einmal eine Serie, die es nicht gibt (Aussage über
den Kalender ohne Erledigt-Wort — kein Prüfer fängt das); f10 nennt „z. B.
18.12." als Beispiel-Ende, statt die Vorlesungszeit per Websuche
nachzusehen; f06 verlangt seit den Routinen mit von/bis (main bc304c9) ein
Ende, das der Fall nicht nennt — qwen rät es (31.03./31.07.2027), statt zu
fragen. Zier-Symbole (✦ ★ ❄) streut qwen in fast jede Antwort (Persona:
„darfst du streuen") — ob das so bleiben soll, entscheidet Sasha.

## Quellen

- Alibaba Model Studio, Function Calling (tool_choice, parallel_tool_calls):
  https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling
- Alibaba Model Studio, Deep thinking (enable_thinking/thinking_budget):
  https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- Qwen-Doku, Function Calling: https://qwen.readthedocs.io/en/latest/framework/function_call.html
- OpenAI, Function calling (wenige Werkzeuge, „unter 20"):
  https://developers.openai.com/api/docs/guides/function-calling
- „Less is More: Optimizing Function Calling for LLM Execution on Edge
  Devices" (dynamisch verkleinerte Werkzeug-Liste): https://arxiv.org/abs/2411.15399
- Anthropic, Writing effective tools for agents:
  https://www.anthropic.com/engineering/writing-tools-for-agents
- Erfundene Werkzeug-Ergebnisse gegen das Protokoll prüfen (NabaOS):
  https://arxiv.org/html/2603.10060

## Wo der Code liegt

`core/profil/modelle/__init__.py` (Zuordnung, `ModellSchiene`),
`core/profil/modelle/qwen.py` (das Profil), `core/profil/modelle/zusatzpruefer.py`
(Zusatz-Prüfer, Änderungswunsch-Erkennung), Haken in `core/cloud_openai.py`
und `core/cloud.py` (`_static_system(…, schiene=)`, `_profil(modell)`).
Tests: `tests/test_modell_profile.py`. Fälle: `tests/pruefstand/faelle_modelle/`.
