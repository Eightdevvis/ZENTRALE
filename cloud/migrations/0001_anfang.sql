-- ZENTRALE cloud, schema v1. Every user table carries konto_id and every
-- query filters on it: one account never sees another account's rows.
-- Times are milliseconds since the epoch (UTC).

-- Accounts. The server never sees the password: it stores a PBKDF2 hash over
-- the client's anmelde_schluessel and over the notfall_beweis, each with its
-- own server salt. salz/kdf/verpackt_* are opaque client values.
CREATE TABLE konten (
  id                TEXT PRIMARY KEY,
  mail              TEXT NOT NULL UNIQUE,          -- lower case
  salz              TEXT NOT NULL,                 -- client salt (base64url)
  kdf               TEXT NOT NULL,                 -- JSON, e.g. {"name":"argon2id","t":3,"m":65536,"p":4}
  anmelde_hash      TEXT NOT NULL,                 -- base64url PBKDF2-SHA256
  anmelde_salz      TEXT NOT NULL,                 -- server salt (base64url)
  notfall_hash      TEXT NOT NULL,
  notfall_salz      TEXT NOT NULL,
  runden            INTEGER NOT NULL,              -- PBKDF2 iterations used for both hashes
  verpackt_passwort TEXT NOT NULL,
  verpackt_notfall  TEXT NOT NULL,
  erstellt          INTEGER NOT NULL,
  geaendert         INTEGER NOT NULL
);

-- Sessions: only the SHA-256 of the token is stored.
-- art 'normal' = full session; 'notfall' = may only set a new password.
CREATE TABLE sitzungen (
  token_hash TEXT PRIMARY KEY,
  konto_id   TEXT NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
  knoten     TEXT NOT NULL,
  art        TEXT NOT NULL DEFAULT 'normal',
  erstellt   INTEGER NOT NULL,
  laeuft_ab  INTEGER NOT NULL
);
CREATE INDEX sitzungen_konto ON sitzungen(konto_id);
CREATE INDEX sitzungen_ablauf ON sitzungen(laeuft_ab);

-- Invite codes (stored as SHA-256 of the normalized code). One account per
-- code; downloading the package does not use a code up.
CREATE TABLE codes (
  code_hash      TEXT PRIMARY KEY,
  notiz          TEXT NOT NULL DEFAULT '',
  erstellt       INTEGER NOT NULL,
  gesperrt       INTEGER NOT NULL DEFAULT 0,
  verbraucht_von TEXT,                              -- konten.id
  verbraucht_am  INTEGER
);

-- Failed-attempt counters (fixed 15-minute window). schluessel is
-- "<route>:mail:<sha256>" or "<route>:ip:<sha256>" — no plain mail/IP.
CREATE TABLE drossel (
  schluessel TEXT PRIMARY KEY,
  start      INTEGER NOT NULL,
  anzahl     INTEGER NOT NULL
);

-- The Mitte (sync star), per account: the head, every stand that was ever the
-- head (for enthaelt), and the file list (name -> blob) of recent stands.
CREATE TABLE mitte_kopf (
  konto_id TEXT PRIMARY KEY REFERENCES konten(id) ON DELETE CASCADE,
  kennung  TEXT
);

CREATE TABLE mitte_staende (
  nr       INTEGER PRIMARY KEY AUTOINCREMENT,
  konto_id TEXT NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
  kennung  TEXT NOT NULL,
  basis    TEXT,
  erstellt INTEGER NOT NULL,
  UNIQUE (konto_id, kennung)
);

CREATE TABLE mitte_dateien (
  konto_id TEXT NOT NULL,
  kennung  TEXT NOT NULL,
  name     TEXT NOT NULL,
  sha256   TEXT NOT NULL,                           -- R2 key mitte/<konto_id>/<sha256>
  groesse  INTEGER NOT NULL,
  PRIMARY KEY (konto_id, kennung, name)
);

-- Device descriptions (plain metadata, no content), one per device name.
CREATE TABLE knoten (
  konto_id     TEXT NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  beschreibung TEXT NOT NULL,                       -- JSON object
  aktualisiert INTEGER NOT NULL,
  PRIMARY KEY (konto_id, name)
);

-- Ownership of the account (schema.org ItemList, encrypted client-side).
CREATE TABLE besitz (
  konto_id     TEXT PRIMARY KEY REFERENCES konten(id) ON DELETE CASCADE,
  daten        TEXT NOT NULL,
  aktualisiert INTEGER NOT NULL
);
