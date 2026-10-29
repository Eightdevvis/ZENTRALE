# Persona: nudging vs. „Du bietest dich nicht an“, servant phrases

**Stand 2026-10-29:** Open. **Waits for Sasha** (how, when and why she
nudges). The contradiction itself is bible B-01
([../ki/bibel/baustellen.md](../ki/bibel/baustellen.md)) — not repeated here.

New evidence since B-01 was written:

- The phrase „Was davon soll ich konkret für dich tun?“ came despite „Kein
  Dienstbotentum“ (conversation `20261026-201032-04ec42`, qwen; see the scene
  „Bei ihr einchecken“ in [../leitbild.md](../leitbild.md)).
- `core/profil/gross.py` ~104–106 cuts the „## Floskel-Stopliste“ out of the
  klein prompt, so gross has no phrase stop list. Gross's length guard is at
  5,472 of 5,600 characters (`tests/test_profil.py` ~146) — little room.
- `data/gedaechtnis/themen/person/ziele.md` describes the KI as „Sekretärin
  und Lehrerin“, which shapes her as a service provider.
- Focus check chain: KL-02 ([../ki/bibel/klassifikatoren.md](../ki/bibel/klassifikatoren.md)).

Related: [ai_initiative.md](ai_initiative.md) (part e, tone „partner check-in“).
