# KI-Bibel — Kontext klein halten

**Stand 2026-10-22:** Sechs Einträge (KT-01 bis KT-06). Kennung „KT“, damit
sie nicht mit den Fehlercodes `K-…` (`core/fehlercodes.py`) verwechselt wird.
Teilweise umgesetzt: Budget, Verweise statt Daten, alte Werkzeug-Ergebnisse
zwischen den Zügen. Offen: Kompaktierung. Achtung: Was vorne aus dem Verlauf
fällt, bricht den Prompt-Cache (`memory/ki/prompt_aufbau.md`). Legende und
Pflegeregeln: [README.md](README.md).

---

### KT-01 Die kleinste Menge Tokens mit dem meisten Gehalt

- **Regel:** Im Kontext steht nur, was für das Ergebnis zählt. Jedes Token
  mehr verdünnt die Aufmerksamkeit (context rot).
- **Zitat:** „find the smallest set of high-signal tokens that maximize the
  likelihood of your desired outcome“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — fester Prompt per Budget begrenzt
  (`tests/test_prompt_budget.py`); Werkzeug-Schema (~47.000 Zeichen) nicht
- **Heute bei ZENTRALE:** Der Prompt ist begrenzt, die Werkzeuge erst mit
  der Werkzeug-Suche (W-07 in [werkzeuge.md](werkzeuge.md)).

### KT-02 Knapp heißt nicht kurz

- **Regel:** Was nötig ist, bleibt drin, auch wenn es lang ist. Gekürzt wird
  Rauschen, nicht Inhalt.
- **Zitat:** „minimal does not necessarily mean short“
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** offen (Leitlinie, keine Fundstelle)
- **Heute bei ZENTRALE:** Gilt als Gegengewicht zu KT-01 und P-01.

### KT-03 Verweise statt Daten, bei Bedarf laden

- **Regel:** Im Kontext stehen Verweise (Dateinamen, Index, Kennungen), die
  Inhalte lädt die KI erst, wenn sie sie braucht.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Gedächtnis-Index im Kopf + read_note
  (`memory/ki/gedaechtnis.md`), Skills dreistufig (S-01 in [skills.md](skills.md))
- **Heute bei ZENTRALE:** Gedächtnis und Skills arbeiten so; Steckbrief und
  Ziele stehen vollständig im Kopf.

### KT-04 Alte Werkzeug-Ergebnisse raus

- **Regel:** Ergebnisse älterer Werkzeug-Aufrufe werden aus dem Kontext
  gelöscht, wenn sie nicht mehr gebraucht werden.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — zwischen den Zügen bleibt nur eine Spur-Zeile je
  Antwort (`anhang.verlauf_einsetzen`, `memory/ki/prompt_aufbau.md`); innerhalb
  eines Zugs bleibt alles
- **Heute bei ZENTRALE:** In einem langen Zug mit vielen Seiten wächst der
  Kontext ungebremst.

### KT-05 Kompaktierung

- **Regel:** Wird der Verlauf zu lang, wird er zusammengefasst und neu
  begonnen (compaction).
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** offen — keine Kompaktierung im Cloud-Pfad gefunden
- **Heute bei ZENTRALE:** Das Fenster wird bewusst nicht beschnitten
  (Cache); `cloud.kappen()` kürzt nur einzelne lange Nachrichten.

### KT-06 Notizen außerhalb des Kontexts

- **Regel:** Was über lange Arbeit hinweg zählt, schreibt die KI in Notizen
  außerhalb des Kontexts und liest es bei Bedarf wieder.
- **Zitat:** —
- **Quelle:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents —
  offiziell, erfasst 22.10.2026
- **Gilt für:** alle
- **Status:** teilweise — Datei-Gedächtnis mit write_note/read_note
  (`memory/ki/gedaechtnis.md`); keine Arbeitsnotizen für eine laufende Recherche
  (R-09 in [recherche.md](recherche.md))
- **Heute bei ZENTRALE:** Für Wissen über Sasha ja, für die Arbeit an einer
  Aufgabe nein.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
