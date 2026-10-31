# Abuse resistance while staying anonymous and open

**Stand 2026-10-31:** Open, **waits for Sasha** (adopt as a design principle
or not). Nothing decided. Question: how ZENTRALE resists abuse while staying
anonymous, privacy-first, open source and hackable — explicitly not a
surveillance Google clone (pillars in `memory/leitbild.md`).

## Realistic risks

ZENTRALE runs locally today; there is **no server** yet.

1. **Surveillance inside the household:** a home system that hears, sees and
   speaks can become stalkerware against partners, kids, flatmates.
2. **Third-party apps** (store, pluggable apps) that siphon data.
3. **Only once an own server/cloud/shop runs** (planned: subscription sales
   via own server, cloud as storage): operator duties such as a report
   channel and notice-and-takedown. Not relevant before that.

## Proposed principle: separate private from public

- **Private** (own notes, calendar, home sensor data): stays on own devices
  or end-to-end encrypted. Nobody looks in, not even the developer. No
  moderation needed — it reaches no one else.
- **Public** (store apps, foreign shops in the portal world, anything shared
  with others): publisher has a stable identity (pseudonym with signature is
  enough, no real name), report button, items can be delisted.
- **Why:** harm almost always happens when something reaches others, so
  accountability applies only to the public part; private stays fully
  anonymous.

## Other proposed mitigations

- **No hidden mode:** everyone in the household sees which sensors run and
  who has access.
- **Apps get only explicitly granted, visible capabilities** and are signed
  (fits the adapter/capability model, `memory/hub/adapter.md`;
  [package_signing.md](package_signing.md)).
- **Licence** (AGPL-3.0 proposal, [release_before_public.md](release_before_public.md))
  keeps derivatives open but does not prevent abuse.

Related: [app_engine_decisions.md](app_engine_decisions.md),
`memory/hub/shop.md`.
