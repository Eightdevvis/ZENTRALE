# Browser UI in today's ZENTRALE style

**Stand 2026-10-29:** Open, **waits for Sasha** (pick the approach, see below).
Asked for on 13.10.2026, never started.

**What Sasha asked for:** put the old dashboard design (the "monolith" page)
back into the archive and rebuild the browser UI so it looks and works like
ZENTRALE does today — the TUI, *„die ui komplett im jetzigen stil"*.

**What exists now** (since `0ec988a`, 12.10.2026):

- The old front is live again at http://localhost:5000/zentrale (`/` redirects
  there): `ui/templates/monolith.html`, `ui/static/{engine.js,viz.js,ascii.js,fonts/}`,
  route file `ui/routen/browser.py`, tests `tests/test_browser_front.py`.
- Every timer goes through `wiederholen()` in `engine.js` and pauses while the
  tab is hidden — keep that in the new front.
- The laptop backend listens on 127.0.0.1 only (`ZENTRALE_HOST`, see
  [../betrieb/zugang.md](../betrieb/zugang.md), section „Wer lauscht wo").
- The design drafts are still in `memory/archive/browser_front/entwuerfe/`.
- Photos for the ASCII filter still sit in `data/_beiseite/photos/`.

**Decision for Sasha** (affects how much work it is):

1. **TUI in the browser** — the page shows the real TUI through a terminal
   in the browser. Same look, all programs at once, nothing copied, so it
   cannot drift. It stays a terminal (no real images, no free mouse layout).
2. **Own browser front in TUI style** — HTML/JS per program, looking like the
   TUI. More freedom, but every program gets a second drawing → drifts
   (against „Programme + Kacheln synchron" / „dasselbe Objekt").
3. **One shared description, two renderers** — each program describes its
   view once, the TUI and the browser both draw from it. The right shape for
   „ZENTRALE überall deploybar", but a big rebuild of the TUI programs.

Claude's recommendation: 1 now (fast, no drift), 3 as the long-term path.

**When done:** move the monolith page back to `memory/archive/browser_front/`,
update `memory/system/dashboard.md` and the archive note, delete this file and
its INDEX line.
