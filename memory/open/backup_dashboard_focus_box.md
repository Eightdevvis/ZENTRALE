# Backup dashboard still draws the old focus box

**Stand 2026-10-29:** Open, **waits for Sasha** (decide). Found by Claude after
the list rebuild on 11.10.2026 (`b53ded0`, `8c69f10`).

The backup dashboard (`/dashboard an`) still draws the focus box through
`proj_render` with the pink bars (`tui/ansichten/dashboard.py`, around line
86), not through the shared list image `core/listen_bild.py`.

Sasha decides: move it onto the shared list image too, or leave the backup
as it is.
