# skill-creator in ZENTRALE

ZENTRALE ist weder Claude Code noch Claude.ai. Diese Datei sagt, was von
SKILL.md hier geht und was nicht. Sie ist ZENTRALEs Zusatz (2026-10-07),
nicht Teil des Originals von Anthropic. Wo SKILL.md und diese Datei sich
widersprechen, gilt diese.

## Werkzeuge statt Dateisystem

- **Lesen:** `load_skill(name)` liefert die SKILL.md eines aktiven Skills,
  `load_skill(name, datei="references/…")` eine Datei daraus.
- **Anlegen:** `propose_skill(name, beschreibung, inhalt)` — Sasha bestätigt.
  `beschreibung` wird die `description` im YAML-Kopf (Auslöser, ≤ 1024
  Zeichen, kein `<` `>`), `inhalt` der Text unter dem Kopf. Es entsteht nur
  die SKILL.md; zusätzliche Dateien (references/, scripts/) kann die KI noch
  nicht anlegen — schreib alles Nötige in die Anleitung oder sag Sasha, was
  dazugehört.
- **Ändern:** `edit_skill(name, inhalt)` ersetzt die Anleitung; der Kopf
  (name, description) bleibt. Die alte Fassung liegt als `SKILL.md.bak`
  daneben. Eine neue description kann nur Sasha eintragen.
- An/aus schaltet nur Sasha (Gedächtnis-Ansicht, `/skills`).

## Testläufe

Es gibt keine Unteragenten. Vorgehen wie im Abschnitt „Claude.ai-specific
instructions": die Testprompts nacheinander selbst ausführen, nach der
Anleitung des Skills, ohne Vergleichslauf ohne Skill. Ergebnisse nicht im
Browser zeigen (es gibt keinen), sondern im Gespräch und — wenn es mehr als
ein paar Zeilen sind — als Dokument in der Ablage (`create_document`),
damit Sasha sie in Ruhe lesen kann. Feedback im Gespräch erfragen.

Kein Benchmark, kein Blind-Vergleich, kein `eval-viewer`.

## Skripte

Programme aus `scripts/` laufen nur in der Sandbox: `run_code` mit
`skill="skill-creator"`. Der Skill-Ordner liegt dort **nur lesend** unter
`/skills/skill-creator`, geschrieben wird in den Arbeitsordner `/arbeit`. Kein Internet,
kein `claude`.

- Geht: `quick_validate.py` (prüft einen Skill-Ordner),
  `package_skill.py`, `aggregate_benchmark.py`. Beispiel (Shell):
  `python3 /skills/skill-creator/scripts/quick_validate.py /arbeit/<name>`
  für einen Skill, den du vorher als Dateien nach `/arbeit/<name>/`
  geschrieben hast. `package_skill.py` als Modul starten:
  `cd /skills/skill-creator && python3 -m scripts.package_skill /arbeit/<name> /arbeit`.
- Geht nicht: `run_eval.py`, `run_loop.py`, `improve_description.py` (rufen
  `claude -p`), `eval-viewer/generate_review.py` (öffnet einen Browser).

## Beschreibung optimieren

Der Abschnitt „Description Optimization" braucht `claude -p` — das gibt es
in ZENTRALE nicht. Überspringen. Kommt erst, wenn ZENTRALE einen eigenen
Weg dafür hat (geplant mit „ZENTRALE Code"). Bis dahin: eine gute
Beschreibung von Hand vorschlagen und Sasha zeigen.
