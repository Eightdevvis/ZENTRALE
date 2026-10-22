# KI-Bibel — Skills: Kurzfassung im Prompt, voller Text bei Bedarf

**Stand 2026-10-22:** Zwei Einträge (S-01, S-02). Die dreistufige Bauweise
ist gebaut, die Kurzfassung hängt am Schalter `werkzeug_suche` (aus). Wie
Skills heute funktionieren: `memory/ki/skills.md`. Legende und Pflegeregeln:
[README.md](README.md).

---

### S-01 Progressive disclosure: erst Name und Kurzbeschreibung

- **Regel:** Im Prompt steht je Skill nur Name und kurze Beschreibung (~100
  Tokens). Der volle Text (unter 5.000 Tokens) kommt beim Auslösen, weitere
  Dateien erst beim Lesen.
- **Zitat:** „until a Skill is triggered, only its name and description
  occupy context.“
- **Quelle:** https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview —
  offiziell, erfasst 22.10.2026
- **Gilt für:** claude-gross
- **Status:** teilweise — dreistufig gebaut; Kurzfassung (erster Satz,
  ≤ 160 Zeichen, `core/skills.py` `kurzzeile`) nur mit Schalter
  `werkzeug_suche` an
- **Heute bei ZENTRALE:** Schalter aus, also geht die volle Beschreibung
  jedes Skills mit (Skill-Liste ~5.800 Zeichen, `memory/ki/prompt_aufbau.md`).

### S-02 Skills nur nach Sashas Durchsicht entfernen oder kürzen

- **Regel:** Bevor ein Skill entfernt oder gekürzt wird, geht Sasha die Skills
  selbst durch, auch die importierten englischen claude.ai-Skills (je
  ~2.500 Zeichen).
- **Zitat:** —
- **Quelle:** Sasha, 14.10.2026
- **Gilt für:** alle
- **Status:** offen (Durchsicht steht aus)
- **Heute bei ZENTRALE:** Alle Skills sind aktiv; die importierten fallen in
  der Liste am stärksten ins Gewicht.

---

## Historie

- **2026-10-22** — angelegt (Bibel-Start).
