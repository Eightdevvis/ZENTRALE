# Run gate: what is not wired yet (building kit 9b)

**Stand 2026-10-30:** found while building steps 9/9b
([../hub/port_types.md](../hub/port_types.md)). Does not wait for Sasha.
Items 1 (apply agent on the keeper), 2 (`adapter calendar` through the gate,
guard test) and 4 (node wires in the node description) were done with step 11.

- **The compiler's graph rules are Python only.** The phone checks items
  (`mobile/test/ports_test.dart`); the 17 sketch cases in
  `contracts/ports/1/port_vectors.json` are ready for a Dart port when the
  phone gets a wiring view.
