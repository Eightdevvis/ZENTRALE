# Calendar frames (pixel-art border styles)

**Stand 2026-10-29:** Open, **waits for Sasha** (pick the styles). Designed on
22.10.2026 by the ICONS session on request of the KALENDER session; nothing is
built yet — `core/stil.py`, `tui/ansichten/kalender_stil.py` and
`tui/bausteine/stylebox.py` contain none of it (checked 29.10.).

**What:** ornate pixel-art frames for calendar blocks as new `border-style`
values in the style box, plus a marker for the selected block and one for
"running now".

**Drafts (night + day, real block sizes 22×6 … 3×1, rendered like the TUI):**
https://claude.ai/artifact/7bAYPF3wzRSAQUVrc2ZEgm — private, Sasha can open it.

- Frames: `gold-barock`, `schlicht`, `ranke`, `jugendstil`, `perlenschnur`;
  colour comes from `border-color` (three tones light / mid / dark).
- Selection: `leuchtklammern` (recommended — green corner brackets with a
  contrast edge), `neonlinie`, `ameisen`.
- Running now: `fortschrittskante` (recommended — gold bar in the middle of
  the top edge, filled by progress, plus the ► notch on the left),
  `kerbe`, `glimmen`. Selection uses the corners, running uses the edges, so
  both can show at once.

**Spec for the build:** the page's section „Beschreibung für den Einbau" holds
a JSON (copy button): tiles `kh`/`kv`/`ecke`/`eckeGross`/`kappe` as fine-pixel
strings (2×3 per cell), tones relative to `border-color`, simplification
levels with thresholds (big corners from 10×5, small from 4×3, sides only,
end caps for one row), title rule, layer order, selection-vs-running rule.

**Next:** Sasha picks frames and markers → an agent builds them from the JSON
into `core/stil.py` (vocabulary) and `kalender_stil.py` (drawing). Note from
the drafts: `gold-barock` and `ranke` still look a bit noisy after the 2-colour
cell reduction — judge on the page.
