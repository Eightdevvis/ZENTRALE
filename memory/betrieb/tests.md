# Testarchitektur — warum die Suite langsam war und welche Regeln gelten

**Stand 2026-10-11:** Jeder Test bekommt genau einen Wegwerf-Ordner
(`_test_ordner` in `tests/conftest.py`), alle Umlenkungen liegen als
Unterordner darin. PTY-Tests warten auf den Schirm statt fest zu schlafen.
Die sieben Regeln unten gelten für jeden neuen Test; Regel 1 und 2 prüft
`tests/test_testarchitektur.py`.

## Was schiefging (Anlass 10.10.2026)

Die volle Suite brauchte **16+ Minuten**, etwa die Hälfte davon ging nicht
auf das, was die Tests prüfen, sondern auf die Fixture-Architektur.

- **Hauptursache:** In `tests/conftest.py` holten sich 8 autouse-Fixtures
  (Kalender, Gespräche, Ablage, Rückmeldungen, Klassifikator-Beispiele,
  Desk + Apps, Shop, Listen/Graphen) ihren Ordner jede selbst per
  `tmp_path_factory.mktemp()` — **9 Aufrufe bei JEDEM Test**. pytest 9
  (`_pytest/pathlib.py`, `make_numbered_dir`) liest bei jedem Aufruf den
  ganzen Basetemp-Ordner, um die nächste freie Nummer zu finden. Der hatte
  am Ende der Suite 30–37 Tsd. Einträge → jeder Test wurde teurer als der
  vorige, die Kosten wuchsen **quadratisch**. Beleg: Median pro Test 0,06 s
  im ersten Zehntel der Suite, ~0,41 s ab dem sechsten; ein reiner Test
  0,04 s allein, 0,34 s im vollen Lauf.
- Jede neue Umlenkung kam als eigene Fixture mit eigenem `mktemp` dazu —
  einzeln harmlos, zusammen der Bremsklotz. Niemand hat es gemerkt, weil
  jeder Test für sich schnell war.
- Dazu kleinere Posten: ein Test mit 980 Parametrize-Fällen (jeder Fall
  zahlte die Fixtures), eine Regex über eine 26-kB-base64-Schrift (11 s),
  ein Wächter, der den kompletten TUI-Fuzzer als Subprozess fuhr, PTY-Tests
  mit festen Schlafzeiten (2,5 s Start + 1,2 s + 0,35 s pro Taste …), eine
  dateiweite Marke `kalender_beide`, die Tests ohne Kalenderbezug doppelt
  laufen ließ, ein immer übersprungener Test, ein doppelter Test.

## Was jetzt gilt (Umbau 11.10.2026)

- `conftest.py`: **ein** `mktemp` pro Sitzung (`_sitzungs_wurzel`), pro
  Test **ein** Ordner per `tempfile.mkdtemp` darin (`_test_ordner`,
  zufälliger Name, kein Verzeichnis-Scan), die Umlenkungen als Unterordner
  per `_frisch(_test_ordner, "name")`. Schutzwirkung unverändert: jede
  Umlenkung ist pro Test frisch, leer und isoliert; Tests, die selbst
  umbiegen, gewinnen weiter.
- PTY-Tests warten auf den Schirm: `warte_auf(bedingung)` und
  `warte_auf_antwort(laenge, vorher)` in `tests/_tui_fuzz.py`.

## Messwerte

Volle Suite, `-m "not kostet_geld"`, 4-Kern-Laptop. Die Maschine war nie
leer — parallel liefen Suiten anderer Sessions; Last als 1-min-Mittel.

| Lauf | Tests | Ergebnis | Last (Median) |
|---|---|---|---|
| vorher, 11.10. 10:16 | 5549 | nach 40 min Zeitlimit abgebrochen bei 83 % | 6,5 (bis 3 fremde Suiten) |
| vorher, 11.10. 11:11 | 5549 | nach 21 min erst bei 62 %, dann wegen Speichermangel beendet | 5,4 (fremde Suiten) |
| nachher, 11.10. 10:57 | 4522 | **8 min 35 s** komplett | 2,8 (fast allein) |

Die Last war beim Nachher-Lauf niedriger, der Vergleich ist also nicht
1:1 — der quadratische Anteil zeigt sich aber an der Kurve: vorher wurde
jeder Test teurer (siehe oben), nachher nicht. Ausgangswert vom 10.10.:
16+ min auf ruhigerer Maschine. Weniger Tests nachher, ohne dass eine
Prüfung wegfiel: 980 Gitterfälle → 1 Test, 50 doppelte Läufe ohne
Kalenderbezug, 2 tote/doppelte Tests weg, 4 Wächter neu.

Einzelposten: `test_fraunces_nur_fuer_die_ueberschrift` 10,9 s → unter
0,1 s; Fuzz-Wächter ~10 s → 6 s; `test_kalender_ansichten_tui` ~7,5 s →
3 s pro Test; `test_tui_perm_wrap` ~8 s → 2,5–3,5 s; `test_herumtasten_wirft_nie`
~17 s → 8–10 s.

## Regeln für neue Tests

1. **Autouse-Fixtures in `conftest.py` legen keinen eigenen Ordner an.**
   Neue Umlenkung = Unterordner im Testordner:
   `def _x_frisch(_test_ordner, monkeypatch): … _frisch(_test_ordner, "x")`.
   Nie `tmp_path`/`tmp_path_factory` in einer conftest-Autouse-Fixture.
2. **`tmp_path_factory.mktemp` nie im Funktions-Scope** (nur `scope="session"`
   oder `"module"`). Ein Test darf `tmp_path` nehmen — das ist sein *einer*
   Ordner.
3. **Keine festen Sleeps in PTY-Tests.** Auf Inhalt warten (`warte_auf`:
   „ZENTRALE" = erster Frame, dann der erwartete Text), nach einer Taste auf
   die Antwort der TUI (`warte_auf_antwort`). Ein festes Fenster nur, wo
   geprüft wird, dass etwas NICHT kommt. Neue PTY-Tests mehrmals laufen
   lassen, auch unter Last.
4. **Parametrize nur, wo die Fälle einzeln etwas bedeuten.** Ein Property-
   Gitter (alle Kombinationen dürfen nicht werfen) ist *ein* Test mit
   Schleife, dessen Meldung die Kombination nennt.
5. **Teure Regex/Datei-Arbeit nicht über eingebettete Blobs** (base64-
   Schriften, Bilder): vorher durch einen Platzhalter ersetzen.
6. **Marke `kalender_beide` nur an Tests, die den Kalender-Speicher
   anfassen** (eigener `cal`-Fixture, `add_entry`, `imprint_for_prompt` …),
   nicht dateiweit über `pytestmark`. Ohne Speicherzugriff ist der zweite
   Lauf derselbe.
7. **Wächter, die die Suite in einem Subprozess fahren, fahren die kleinste
   Runde, die ihren Zweck erfüllt** (z. B. `ZTUI_FUZZ_SESSIONS=2`).
8. **Kein Ergebnis darf vom heutigen Datum abhängen.** Wer `date.today()`
   braucht, formuliert die Erwartung so, dass Wochentag und Fixture-Routinen
   egal sind (z. B. Zählstart hinter andere Termine legen), oder nimmt ein
   festes Datum. Anlass 19.10.2026: montags kam die Dienstags-Routine
   „Geigenstunde" vor „Probe", `test_phasen_machen_keine_alarme…` war rot.
   Zeitabhängiges selbst prüfen (z. B. über Mitternacht) mit gestellter Uhr:
   `uhr.gestellt(...)` + `uhr.vorstellen(...)` (core/uhr.py, Gefahrzone
   [../system/gefahrzonen.md](../system/gefahrzonen.md)).
9. **Fakes are shared, not rewritten per test** (since 2026-10-30): the fake
   cloud (`devkit/fake_cloud.py`) and the fake `systemctl`
   (`devkit/fake_systemd.py`) are the ones `zentrale dev` profiles use
   ([dev_mode.md](dev_mode.md)) — what Sasha clicks through is what CI checks.
   A new behaviour goes into the shared fake.

Regeln 1 und 2 prüft `tests/test_testarchitektur.py` statisch (AST); der
Wächter wird rot, sobald eine Funktions-Fixture `mktemp` ruft oder eine
conftest-Autouse-Fixture `tmp_path`/`tmp_path_factory` nimmt.
