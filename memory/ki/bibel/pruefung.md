# KI-Bibel — Prüfung: Richter, Evals, unser Python-Prüfer

**Stand 2026-10-22:** Dreizehn Einträge (PR-01 bis PR-13). Der Live-Prüfer ist ein
Python-Satzmuster-Prüfer (`core/ehrlichkeit.py`, `core/ehrlichkeit_erkennen.py`)
und kennt nur Kalender und Dateien. Seit PR-10/12/13 prüft er nach Kalender-
Schreibaufrufen auch, WAS geschrieben wurde (`core/ehrlichkeit_kalender.py`). Recherche-Qualität und „passt die Antwort
zum Wunsch?“ sieht er nicht. Wie er heute arbeitet:
`memory/ki/ehrlichkeit_live.md`, der Prüfstand: `memory/ki/pruefstand.md`.
Ein Modell als Richter steht in der Ideenecke ([klassifikatoren.md](klassifikatoren.md)).
Legende und Pflegeregeln: [README.md](README.md).

---

### PR-01 Prüfschleife nur mit klaren Kriterien

- **Regel:** Ein Prüfer, der Antworten zurückschickt (Evaluator-Optimizer),
  lohnt nur mit klaren Kriterien und messbarem Nutzen. Beispiel: Der Prüfer
  entscheidet, ob weiter gesucht wird.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/building-effective-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Der Python-Prüfer schickt bei Befund eine
  Korrekturrunde; für Recherche gibt es keine.

### PR-02 Regeln für Richter (Modell als Prüfer)

- **Regel:** Richter sind nicht deterministisch: mit Sashas Urteil abgleichen,
  ein Richter pro Kriterium, „Unknown“ als Antwort erlauben, das Ergebnis
  bewerten statt den Weg.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen — der Prüfstand hat einen Richter (`memory/ki/pruefstand.md`),
  ob er diese Regeln erfüllt, ist nicht geprüft
- **Heute bei ZENTRALE:** Live gibt es keinen Richter.

### PR-03 Werkzeuge per Evals verbessern

- **Regel:** Werkzeug-Beschreibungen und -Zuschnitt werden mit Evals gemessen
  und daran verbessert, nicht nach Gefühl.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents,
  https://www.anthropic.com/engineering/writing-tools-for-agents — offiziell,
  erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen — erster Fall wäre W-09 in [werkzeuge.md](werkzeuge.md)
- **Heute bei ZENTRALE:** Der Prüfstand existiert, wird für Werkzeug-Texte
  nicht genutzt.

### PR-04 Der Prüfer ist blind für Recherche und Passung

- **Regel:** Der Prüfer muss auch prüfen, ob genug nachgelesen wurde und ob
  die Antwort zum Wunsch passt.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 14.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit.py`, `core/ehrlichkeit_erkennen.py`
  (nur Kalender/Dateien)
- **Heute bei ZENTRALE:** Satzmuster in Python; Recherche fällt durch.

### PR-05 Nicht jede Suche ist eine Tat

- **Regel:** Eine Suche belegt nicht, dass eine behauptete Tat lief.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit.py` ~410 (`tat_lief`)
- **Heute bei ZENTRALE:** Jede Suche zählt als Tat und löscht damit Befunde.

### PR-06 „oder“ ist nicht immer eine Auswahlfrage

- **Regel:** Ein „oder“ im Satz macht ihn nicht zur Auswahlfrage.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit_erkennen.py` ~394 (`_WAHL`) und ~506
- **Heute bei ZENTRALE:** Falschtreffer möglich.

### PR-07 Erlaubnis-Befund nur eine Runde je Zug

- **Regel:** Zu prüfen, ob der Erlaubnis-Befund (WEICH) mehr als eine
  Korrekturrunde je Zug braucht.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit.py`
- **Heute bei ZENTRALE:** Eine Runde, danach geht die Antwort durch.

### PR-08 Bestandene Prüfung sichtbar speichern

- **Regel:** Auch eine bestandene Prüfung wird als Feld gespeichert und für
  Sasha sichtbar.
- **Zitat:** —
- **Quelle:** Sasha, 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit.py` ~853 (ohne Befund `return None`),
  `ui/routen/ki.py` ~270–287 (`_pruefung_felder`)
- **Heute bei ZENTRALE:** Ohne Befund wird nichts gespeichert; man sieht
  nicht, dass geprüft wurde.

### PR-09 Befunde aus Runde 1 nicht überschreiben

- **Regel:** Die Befunde der ersten Runde bleiben erhalten, wenn Runde 2
  läuft.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — `core/ehrlichkeit.py` ~755 (`self.befunde = b`)
- **Heute bei ZENTRALE:** Runde 2 überschreibt `befunde`.

### PR-10 Behauptete Werkzeug-Argumente gegen die echten Aufrufe

- **Regel:** Sagt die KI „alle mit 'uncommitted' angelegt“, prüft der Prüfer
  die Argumente der echten Aufrufe, nicht nur, ob ein Aufruf lief.
- **Zitat:** —
- **Quelle:** Sasha, 22.10.2026 — Gespräch 20261022-111358-dd6127 (qwen
  behauptete „uncommitted“, kein layer war gesetzt)
- **Gilt für:** qwen, claude-gross
- **Status:** umgesetzt (Kalender) — `core/ehrlichkeit_kalender.py`
  `behauptung_befunde` (~247), eingehängt in `ehrlichkeit.befunde` (~467); c3955c0
- **Heute bei ZENTRALE:** Nach einem Kalender-Schreibaufruf prüft Python jede
  Aussage über die Einträge gegen Argumente und Ergebnisse: Ebene vielleicht/
  uncommitted, Typ Deadline, mehr angelegte Einträge als Aufrufe, eine
  Zeitspanne, die nirgends steht. Befund „behauptung“ → Korrekturrunden wie
  bei „tat“, danach Warnung. Fragen und Verneinungen zählen nicht.

### PR-11 Prüf-Statuszeile verschwindet, sobald die Antwort steht

- **Regel:** Die rote Prüf-Meldung bleibt nicht hängen.
- **Zitat:** —
- **Quelle:** Sasha, 2026-10
- **Gilt für:** alle
- **Status:** umgesetzt — e892b8e
- **Heute bei ZENTRALE:** Behoben.

### PR-12 Kalender-Werte ohne Grundlage

- **Regel:** Nach einem Kalender-Schreibaufruf prüft Python, ob von, bis und
  ende in Sashas Text (oder im Gespräch, oder in einem gelesenen Ergebnis)
  stehen — als Datum/Uhrzeit, auch normalisiert („26.10.“, „17 Uhr“, „halb
  sechs“). Steht etwas Ungefähres da („ab nächster Woche“, „bis Semesterende“,
  „zwei Stunden“), gibt es keinen Befund. Im Zweifel Befund statt Abbruch.
- **Zitat:** —
- **Quelle:** Sasha/Kalender-Session, 22.10.2026 — Gespräch
  20261022-111358-dd6127 (von=2026-10-26, bis=2026-12-20 erfunden)
- **Gilt für:** claude-gross, qwen
- **Status:** umgesetzt — `core/ehrlichkeit_kalender.py` `grundlos_befunde`
  (~174); c3955c0
- **Heute bei ZENTRALE:** Befund „grundlos“: EINE Korrekturrunde je Zug (die
  KI soll den Wert als angenommen nennen und nachfragen), danach eine Warnung
  „⚠ Angenommen, nicht von dir: …“, falls die Antwort den Wert nicht nennt.
  von zwischen heute und in sieben Tagen gilt als „ab jetzt“. ende nur beim
  Anlegen (beim Verschieben wandert es mit).

### PR-13 Wochentag im Titel gegen Regel und Datum

- **Regel:** Nennt ein Titel einen Wochentag, an dem der Eintrag nicht
  stattfindet, wird nichts gespeichert. Erkannt wird nur Sicheres
  (ausgeschriebene Namen, Kürzel in Klammern oder als Anhang), damit „To Do“
  oder „Montagsrunde“ nie anschlagen.
- **Zitat:** —
- **Quelle:** Sasha/Kalender-Session, 22.10.2026 — Gespräch
  20261022-111358-dd6127 („Sprechstunde Jonas Schömer (Mo)“ an BYDAY=WE)
- **Gilt für:** claude-gross, qwen
- **Status:** umgesetzt — `core/titel_wochentag.py`,
  `core/ki_kalender_adapter.py` `_wochentag_passt` (~76; Anlegen und
  neuer_titel), Code `K-TITEL-WOCHENTAG` in `core/fehlercodes.py`; c3955c0
- **Heute bei ZENTRALE:** Abbruch vor dem Speichern mit „Was tun“. Eine
  Warnung des Kalender-Kerns für schon gespeicherte Einträge (z. B. wenn eine
  Serie den Tag wechselt und der Titel bleibt) fehlt noch — Wunsch an die
  Kalender-Session.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
- **2026-10-22** — PR-12, PR-13 neu und umgesetzt, PR-10 umgesetzt (Kalender), c3955c0.
