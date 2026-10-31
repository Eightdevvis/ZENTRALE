# Canvas navigation model — pan the surface, not the cursor

**Stand 2026-10-31:** Open, waits for the end of the core move
([kern_auszug_inventur.md](../hub/kern_auszug_inventur.md)); Sasha paused all
building until then. Docs only, nothing built.

Sasha, 2026-10-31 (verbatim): *„das touchpad funktioniert gut nach unten
scrollen aber es soll ja in alle richtungen gehen. mit pfeil oder wasd den
cursor steuern ist cool, aber an sich sollte es sein dass pfeil/wasd einfach
die fläche steuert, mit cursor mittig oder da wo man ihn abgelegt hat, mit
alt festhalten kann man den cursor dann steuern."*

## To do (shared block `tui/bausteine/canvas.py` + `sgr_mouse.py`)

1. **Touchpad/wheel pans in all four directions** — today only down works.
   Find the root cause first, candidates: an initial clamp at the top bound;
   a tmux binding eating WheelUp; sign or burst handling of wheel events.
2. **Arrows/wasd pan the surface.** The cursor keeps its screen spot (centre,
   or where it was put); the piece under it gets focus.
3. **Modifier + arrows/wasd moves the cursor.** Sasha said Alt, but Alt is
   unreliable on his Mac keyboard (memory note `mac-keyboard-xfce`) and may
   be caught by tmux or i3 — verify; otherwise pick a mainstream,
   collision-free alternative and tell Sasha.

## Possibly reusable

A started-and-stopped attempt may exist on branch
`worktree-agent-a39f99b21a770ba61` (unreviewed, unmerged). Look at it before
starting; do not treat it as done.
