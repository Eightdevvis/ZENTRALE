# Calendar edits from the phone: merge limits

**Stand 2026-10-29:** Open, does not wait for Sasha. Property-level three-way merge since `89c9b62` (`core/vevent_merge.py`, `core/abgleich_vorschlaege.py`; spec in `memory/betrieb/abgleich_fremde_knoten.md` „Termine vom Handy").

1. Mitte switches off occurrence A of a series, phone switches off occurrence B → rejected as conflict, because both are in the time group. Could merge EXDATE/X-ZENTRALE-AUS as sets.
2. The phone cannot remove a DESCRIPTION or the last alarm by leaving it out; it has to send it empty. Documented, but easy to get wrong on the phone side.
