-- Anonymous accounts (2026-10-23): no email anywhere. The account is a
-- username (rules in src/name.ts), the same kind for everyone. Production
-- had no accounts yet; the rename keeps any row and the UNIQUE constraint.
ALTER TABLE konten RENAME COLUMN mail TO name;   -- username, lower case, NFC

-- Rate-limit keys were SHA-256 of mail/IP (an IPv4 hash is reversible by
-- trying all addresses). New keys are HMAC with a daily key from
-- VORAB_GEHEIMNIS ("<route>:name:<hex>" / "<route>:ip:<hex>", src/drossel.ts).
-- The old rows cannot be rehashed and are only 15-minute counters: drop them.
DELETE FROM drossel;
