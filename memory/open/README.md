# Open items — how this folder works

**Stand 2026-10-29:** Collecting folder for concrete open items (Sasha,
29.10.2026: *„wir brauchen nen sammelordner wo so offene sachen reingeschmissen
werden als md einfach"*). One open item = one `.md` file here. Not the tracker.

## Rules

1. **One item, one file.** The file name says what it is about
   (`docs_test_hook.md`, not `item_3.md`). Add a line to [INDEX.md](INDEX.md)
   — `tests/test_memory_index.py` fails otherwise.
2. **Short content:** what is open, why it matters, where (files, commits,
   evidence), since when, who found it, and — if so — **waits for Sasha**.
   Start with the `**Stand <date>:**` block like every `memory/` file.
3. **Found it, not doing it → file it here.** Any session or agent that finds
   something open and does not fix it right away creates a file here instead
   of leaving it in the chat, in auto-memory or in some collection file.
4. **Done = delete the file** (git keeps it) and its INDEX line, in the same
   commit as the fix.
5. **Only concrete, workable items.** Plans and visions stay where they are
   (`memory/ki/zukunftsvisionen.md`, the `*_plan.md` files).
6. **Not a replacement for the tracker `l_zentrale`.** Sasha alone keeps that
   list (CLAUDE.md, „Feature-Tracking"); nothing from here is copied into it.

## Why

Open items used to end up in chat summaries and Claude's private auto-memory,
where neither Sasha nor the next agent finds them. A file in the repo is
visible, lands on every node with the next push, and disappears with the fix.
