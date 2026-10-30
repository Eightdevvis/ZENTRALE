-- Build step 7 (memory/hub/building_kit_plan.md 2.3): a released version can
-- be marked insecure — as data, not code. Every version keeps syncing
-- forever; an insecure one only gets the warning headers `Deprecation`
-- (RFC 9745, "@<unix seconds>") and `Link: <link>; rel="deprecation"`.
-- `Sunset` is never sent. The client tells its version in `Zentrale-Release`.
--
-- Marking one (operator, by hand, see server/README.md):
--   INSERT INTO insecure_releases (version, since, link, reason)
--   VALUES ('41', <ms since epoch>, 'https://…/advisory', 'One English sentence.');
CREATE TABLE insecure_releases (
  version TEXT PRIMARY KEY,          -- as the client reports it (VERSION of the package)
  since   INTEGER NOT NULL,          -- ms since the epoch: when it was marked
  link    TEXT NOT NULL,             -- page explaining why and what to do
  reason  TEXT NOT NULL DEFAULT ''   -- one English sentence (for Schematix / devices)
);
