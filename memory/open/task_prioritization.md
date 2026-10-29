# KI prioritises dumped tasks herself instead of asking

**Stand 2026-10-30:** Open, nothing built. Found by Sasha (20./21.08.2026):
he dumped a pile of ideas and duties, some marked urgent, and she replied
with a question — „catalogue as ideas, do nothing, or sort by urgency
first?“. Sasha: she must not ask that; understanding what to prioritise
right now and filing the rest in the catalogue is a core reason she exists.
**Waits for Sasha** (one decision, below).

## Why she asks

1. **The prompt forbids it.** `core/profil/gross.py` ~200, answer behaviour:
   „was Vorrang vor was hat, ordnest du nicht ungefragt ein“. Written after
   Sasha's complaint of 20.08. („bei fokus-vorrang würde ich es eh nicht
   vors studium schieben … NO SHIT“). It does not separate two things:
   ranking his *life* unasked (unwanted) vs. sorting *material he just
   handed over* (wanted).
2. **No procedure, no current state.** Deciding a status needs to know what
   is `in_schedule` right now and what the calendar holds. Nothing tells her
   to look first.
3. With sorting forbidden, `ask_choice` is the only legal move left.

## Sasha's model (not a field — a judgement)

Urgency is not a label or a number. She looks at what the thing *is* and
decides the existing `status` (`idee → priorisiert → queued → in_schedule`):

- Things compete for schedule slots. No free slot → `queued`.
- Without deadline pressure the order is free („Bad putzen“ may go first).
- Deadline close (e.g. Immatrikulation in a few days) → it gets
  `in_schedule` no matter what: the least important item leaves the
  schedule, or it goes into free time.

## Proposed shape

- **Procedure as a document, read on demand** (a „skill“ in ZENTRALE form),
  read via `read_note` when he dumps several things. Not in the cached
  prefix, editable by Sasha, one trigger line in the prompt. Draft steps:
  capture first without asking → per item „what happens if it does not
  happen?“ → a fixed deadline goes to the calendar → read current
  `in_schedule` + calendar → assign (deadline close / slot free / else
  `queued`) → report in one sentence what moved in, what got dropped, what
  waits.
- **Cut the prompt rule, don't delete it:** still no unasked judgement about
  his life; but dumped material is sorted, and what a deadline forces is
  said without asking.
- Sasha's idea: draft the procedure in the Claude chat first, then harden it
  here against `scripts/pruefstand.py` with his real catalogues and calendar.

## Decision for Sasha

When a close deadline pushes something out of the schedule: does she decide
herself and report, or stop at exactly that one point and ask?

Related: [persona_nudging.md](persona_nudging.md),
[skills_review.md](skills_review.md),
[../ki/gedaechtnis_dateien.md](../ki/gedaechtnis_dateien.md).
