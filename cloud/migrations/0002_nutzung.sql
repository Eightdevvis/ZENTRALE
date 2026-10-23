-- Free-tier usage, counted by the Worker itself (src/nutzung.ts).
--
-- One row per UTC day. Every request adds its numbers to today's row with ONE
-- upsert (1 row written), so the meter itself costs one D1 row write per
-- request. Month figures (R2 operations) are the sum of the day rows.
CREATE TABLE nutzung_tag (
  tag            TEXT PRIMARY KEY,                 -- 'YYYY-MM-DD' (UTC)
  anfragen       INTEGER NOT NULL DEFAULT 0,       -- Worker requests
  d1_gelesen     INTEGER NOT NULL DEFAULT 0,       -- D1 rows read (meta.rows_read)
  d1_geschrieben INTEGER NOT NULL DEFAULT 0,       -- D1 rows written (meta.rows_written)
  r2_a           INTEGER NOT NULL DEFAULT 0,       -- R2 Class A ops (put, list, multipart)
  r2_b           INTEGER NOT NULL DEFAULT 0,       -- R2 Class B ops (get, head)
  d1_bytes       INTEGER NOT NULL DEFAULT 0        -- last seen database size (meta.size_after)
) WITHOUT ROWID;

-- Single values: 'r2_bytes' = bytes stored in R2 (exact on put/delete through
-- the Worker, recounted from an R2 list by the daily cron), and 'cf:<limit>'
-- = the numbers the Cloudflare GraphQL Analytics API reported (optional).
-- zeitraum = the day/month a cf value covers ('' for r2_bytes).
CREATE TABLE nutzung_wert (
  name         TEXT PRIMARY KEY,
  wert         INTEGER NOT NULL,
  zeitraum     TEXT NOT NULL DEFAULT '',
  aktualisiert INTEGER NOT NULL
) WITHOUT ROWID;

-- Start value until the first recount: the sync blobs D1 already knows.
INSERT INTO nutzung_wert (name, wert, zeitraum, aktualisiert)
  SELECT 'r2_bytes', COALESCE(SUM(groesse), 0), '', 0 FROM mitte_blobs;
