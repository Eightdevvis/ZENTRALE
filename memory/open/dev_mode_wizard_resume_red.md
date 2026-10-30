# tests/test_dev_mode.py::test_wizard_step_n_picks_up_there is red on main

**Stand 2026-10-30:** Open, does not wait for Sasha. Found by the agent that
built building kit steps 10 and 12; red on `main` at `ac17cdd` (after steps
9/9b, `6a63d16`), green before (at `7c02929`).

A dev profile resumed at wizard step 3 gets the answers "2, Enter, Enter"
(auto-update off). Afterwards `zentrale status` in that profile does not show
auto-update "off". Suspect: the sync choice now goes through the Run gate
(`befehle.choose_sync` → `core/generations.py`/`core/wires.py`) and something
on that path loses or overwrites the `auto_update` setting written a step
earlier, or stdin is consumed differently. Not investigated further.
