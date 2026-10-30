# Run gate: what is not wired yet (building kit 9b)

**Stand 2026-10-30:** found while building steps 9/9b
([../hub/port_types.md](../hub/port_types.md)). Does not wait for Sasha.

1. **Apply agent not on the keeper timer.** `generations.reconcile` runs only
   right after a switch. On the 5-minute sync timer it would revert settings
   written by paths that do not pass the gate yet (item 2). Wire it in once
   every writer goes through `generations.run`.
2. **`zentrale adapter calendar` writes `quelle` around the gate**
   (`adapter_ablauf.kalender_quelle_setzen` directly, with its own progress
   output). `PUT /api/wires/calendar-source/<id>` already goes through the
   gate; the CLI command should build the wire and call `generations.run`.
3. **The compiler's graph rules are Python only.** The phone checks items
   (`mobile/test/ports_test.dart`); the 17 sketch cases in
   `contracts/ports/1/port_vectors.json` are ready for a Dart port when the
   phone gets a wiring view.
4. **Each node projects only its own sync wires.** Other nodes' `abgleich_apps`
   are per node and not in the cloud; Schematix (step 13) needs them, e.g. in
   the node description.
