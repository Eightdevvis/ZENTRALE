# KI-Bibel — Baustellen

**Stand 2026-10-22:** Fünf offene Punkte (B-01 bis B-05), die keine Regel von
außen sind, sondern Widersprüche und Reste im eigenen Bau. Legende und
Pflegeregeln: [README.md](README.md).

---

### B-01 „Du bietest dich nicht an“ gegen „darf anstupsen“

- **Regel:** Die Persona verbietet, sich anzubieten; der Steckbrief erlaubt
  Anstupsen. Sasha will das Anstupsen. Wie, wann und warum klärt er eigens,
  vorher nichts ändern.
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen — `core/profil/klein.py` ~135 (Persona, gilt auch für gross)
- **Heute bei ZENTRALE:** Beide Sätze stehen im Prompt.

### B-02 „Sasha“ fest im Gedächtnis-Kopf

- **Regel:** Der Name kommt aus `nutzer_name`, nicht fest aus dem Code.
- **Zitat:** —
- **Quelle:** Sasha, 2026-10-09 (Platzhalter für den leeren Erststart,
  `memory/ki/prompt_aufbau.md`)
- **Gilt für:** alle
- **Status:** offen — `core/gedaechtnis.py` ~137–141
- **Heute bei ZENTRALE:** Persona und Meta-Regeln haben Platzhalter, der
  Gedächtnis-Kopf nicht.

### B-03 Alarm-Block passt nicht zu gross

- **Regel:** Der Alarm-Block verweist auf gross auf das Dashboard und auf
  `[[bild: alarm]]`, die es dort nicht gibt, und nutzt Großbuchstaben.
- **Zitat:** —
- **Quelle:** Sasha (Befund im Code), 14.10.2026; Ton: P-02 in [prompt.md](prompt.md)
- **Gilt für:** claude-gross
- **Status:** offen — `core/ki_prompt.py` `_alarm_prompt` (~161–177, geteilt mit klein)
- **Heute bei ZENTRALE:** Unverändert.

### B-04 Ausweichweg ohne erzeugte Werkzeuge fällt weg

- **Regel:** Der Weg `werkzeuge_erzeugt = aus` auf gross kann keine Deadlines
  und soll entfernt werden.
- **Zitat:** —
- **Quelle:** Sasha, 2026-10
- **Gilt für:** claude-gross
- **Status:** offen — `core/werkzeug_register.py`, `core/ki_kalender_adapter.py`
- **Heute bei ZENTRALE:** Beide Wege bestehen (`memory/ki/werkzeug_erzeuger.md`).

### B-05 Budget-Rückfall auf qwen

- **Regel:** Ist das Monatsbudget voll, wechselt ZENTRALE automatisch von
  Claude zu qwen. Die Qualität auf qwen muss mitgedacht werden. Der Werkzeug-
  Zuschnitt für qwen entfernt Felder mit `schwach=False`, auch nötige.
- **Zitat:** —
- **Quelle:** Sasha, 22.10.2026 (8,61 € von 8,00 € verbraucht)
- **Gilt für:** qwen
- **Status:** offen — `core/profil/modelle/qwen.py` ~121–129
  (`werkzeug_erzeuger.zuschneiden(..., "schwach", ...)`)
- **Heute bei ZENTRALE:** Seit 22.10. läuft qwen; PR-10 in
  [pruefung.md](pruefung.md) ist dort passiert. Profil: `memory/ki/modell_profile.md`.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
