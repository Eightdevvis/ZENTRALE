# KI-Bibel — Baustellen

**Stand 2026-10-22:** Fünf Punkte (B-01 bis B-05; B-03 umgesetzt, B-05 teilweise), die keine Regel von
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
- **Szene dazu:** „Bei ihr einchecken“ (26.10.2026) in
  [../../leitbild.md](../../leitbild.md#szenen-sasha-2026-10-24) — sanft
  anstupsen als Frage, kein Service-Nachklapp.

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
- **Status:** umgesetzt — `core/ki_prompt.py` `_alarm_prompt(gross=True)` →
  `_alarm_gross` (`_ALARM_GROSS`), gerufen aus `cloud._volatile_text`; 0446ae5.
  klein byte-gleich (Schnappschuss `tests/test_prompt_nutzer.py`).
- **Heute bei ZENTRALE:** Auf gross: „## Offene Erinnerungen“, die Liste und
  ein Absatz in normaler Schreibung — einmal ansprechen, wenn es passt; bei
  einem Termin in einer Reise oder einer nötigen Absage rückversichern,
  warnen und per ask_choice nachhaken. Kein Dashboard, kein [[bild: alarm]].
  Die Absage-Regel stand vorher auch in read_calendar; dort ist sie raus.

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
- **Status:** teilweise — `core/profil/modelle/qwen.py` (Zuschnitt
  `werkzeug_erzeuger.zuschneiden(..., "schwach", ...)`, Regel 5); c3955c0
- **Heute bei ZENTRALE:** Seit 22.10. läuft qwen. Die drei Fehler aus dem
  Gespräch 20261022-111358-dd6127 (Wochentag im Titel, erfundener Zeitraum,
  falsches „uncommitted“) fängt jetzt Python für alle Modelle (PR-10, PR-12,
  PR-13 in [pruefung.md](pruefung.md)); die Texte sagen „nur, was Sasha gesagt
  hat“ (W-14), qwen hat dazu einen Satz in Regel 5. Der Zuschnitt erhält die
  neuen Texte (`einfach` von add_calendar_entry nachgezogen). Offen: nicht
  gemessen (Prüfstand mit qwen kostet), und `schwach=False` blendet weiter
  Felder aus. Profil: `memory/ki/modell_profile.md`.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
- **2026-10-22** — B-05 auf teilweise (Kalender-Nachprüfung, c3955c0).
- **2026-10-22** — B-03 umgesetzt (Durchgang Werkzeuge, 0446ae5).
- **2026-10-26** — B-01: Verweis auf die Szene „Bei ihr einchecken“.
