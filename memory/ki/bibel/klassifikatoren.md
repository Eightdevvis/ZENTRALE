# KI-Bibel — Klassifikatoren (Ideenecke, noch nicht bauen)

**Stand 2026-10-22:** Drei Ideen (KL-01 bis KL-03). Nichts davon wird jetzt
gebaut. Sie kommen nach der Grund-KI dran. Größere Visionen dazu:
`memory/ki/zukunftsvisionen.md`. Legende und Pflegeregeln: [README.md](README.md).

---

### KL-01 Nachricht abtasten und Werkzeuge vorab einlegen

- **Regel:** Ein Klassifikator liest Sashas Nachricht und legt passende
  Werkzeuge oder Skills schon vor dem ersten Modell-Aufruf ein.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026. Anthropic macht das nach heutigem Wissen
  nicht, dort sucht das Modell selbst (https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool).
- **Gilt für:** alle
- **Status:** offen — Schnittstelle `vorab(verlauf, index)` existiert
  (`core/werkzeug_gruppen.py`, `memory/ki/werkzeug_suche.md`); heute nur die
  Schlagwort-Logik des qwen-Profils
- **Heute bei ZENTRALE:** qwen bekommt eine Vorauswahl per Schlagwort, gross
  nicht.

### KL-02 Fokus-Prüfkette

- **Regel:** Statt des gestrichenen Satzes „gegen den spontanen Wunsch“: erst
  den aktuellen Fokus prüfen, dann Sashas Nachricht abwägen, dann entscheiden,
  ob das Gewünschte den Fokus stört.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026 (`memory/ki/zukunftsvisionen.md`)
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Der Satz ist gestrichen (cb8c662), Ersatz gibt es
  nicht.

### KL-03 Modell als Richter

- **Regel:** Ein Modell prüft drei Fragen, die der Python-Prüfer nicht kann:
  Passt die Antwort zum Wunsch? Wurde genug nachgelesen? Stimmen behauptete
  Taten mit den Aufrufen überein?
- **Zitat:** —
- **Quelle:** Sasha, 22.10.2026; Regeln für Richter: PR-02 in
  [pruefung.md](pruefung.md)
- **Gilt für:** alle
- **Status:** offen
- **Heute bei ZENTRALE:** Kein Richter im Live-Betrieb.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
