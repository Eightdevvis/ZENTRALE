# Key change leaves old cloud data readable with the old key

**Stand 2026-10-30:** Open, waits for Sasha (pick a direction). Sasha finds
the current key change unsatisfying („meh"); recorded at his request.

## What

`core/key_rotation.py` (build step 8, `d1dc8fd`) re-encrypts the *current*
Mitte under a new account key and swaps the head. Everything older stays on
the server as it was: earlier stands, superseded blobs in R2, and on the
old rsync path the whole repository history — all encrypted with the
**old** key. `besitz` (`/v1/besitz`) is not re-encrypted either.

## Why it matters

The key change is offered exactly for a lost or stolen device. That device
still holds the old key in `konto.json`. Its sessions are ended, so today it
cannot fetch anything — but whoever gets a session, a copy of the R2
bucket, a clone of the old repository or a server-side leak can read the
full history up to the change with the old key. The change protects the
future, not the past.

## Possible directions

1. **Purge after rotation:** the server deletes every stand and blob not
   referenced by the new head once `PUT /v1/konto/schluessel` succeeds
   (and the old rsync path's history is rewritten or dropped).
2. **Per-epoch keys:** each key change starts an epoch; old epochs are
   re-wrapped or explicitly dropped, so "keep history" is a choice.
3. **Server-side deletion of superseded objects** in general (garbage
   collection of unreferenced blobs), which also helps the free R2 quota.

Related: [node_lifecycle_followups.md](node_lifecycle_followups.md),
[../hub/knoten_beitritt.md](../hub/knoten_beitritt.md) (key change).
