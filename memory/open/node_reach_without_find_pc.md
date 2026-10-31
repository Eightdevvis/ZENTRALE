# Reach a node without find-pc

**Stand 2026-10-31:** Open. Found by the access-hardening agent (`ee2e519`);
Sasha: bridges like this should only be handled by ZENTRALE itself.

- `find-pc` is a script on the laptop, outside the repo. It found the PC via
  `GET /api/state`, which now answers 401 to other devices (access mode
  "an"); finding it by MAC address still works.
- Target: ZENTRALE knows how to reach and wake its own nodes (address, wake
  info) from the node description (`core/knoten.py`, `PUT /v1/knoten/<name>`,
  [../hub/knoten_beitritt.md](../hub/knoten_beitritt.md)), so no private
  helper script is needed. Today the node description carries no address.
- Then `find-pc` can go. Related: `scripts/wake_pc.sh` on the Pi.
