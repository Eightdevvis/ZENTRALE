# ZENTRALE cloud

The backend for logging in to ZENTRALE and syncing across devices: a
Cloudflare Worker (TypeScript) with D1 (accounts, sessions, invite codes,
rate-limit counters, the sync head and stand history, devices, ownership)
and R2 (encrypted sync blobs, release packages, `install.sh`).

**Zero-knowledge.** The server never sees a password, a key or plain
content. The client derives `anmelde_schluessel` and `notfall_beweis` from the
password / emergency key (Argon2id with 64 MiB + HKDF); the server stores only
HMAC-SHA256 of them, keyed with a random 32-byte salt per account
(`konten.hash_art = 'hmac-sha256'`). No slow hash on the server: a
dictionary attack has to go through the client's Argon2id anyway, and a
256-bit derived key cannot be brute-forced. This keeps every request within
the Free plan's 10 ms CPU.
Synced files arrive already encrypted (Fernet) under HMAC'd names.

- API: [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1). A test checks that it
  lists exactly the routes in `src/index.ts`.
- Contract and key scheme: `memory/hub/knoten_beitritt.md`, section
  "Bauplan v1". Operations notes (German): `memory/betrieb/cloud.md`.

## Layout

| Path | What |
|---|---|
| `src/index.ts` | route table, error handling, usage meter per request, crons |
| `src/konto.ts` | account, `vorab`, login/logout, emergency key, password change |
| `src/mitte.ts` | the sync "Mitte": snapshot stands, compare-and-swap head, `enthaelt` |
| `src/knoten.ts` | device descriptions and account ownership |
| `src/paket.ts` | `install.sh`, release packages, invite-code check |
| `src/drossel.ts` | rate limit: 5 failures / 15 min per name and per IP (keys: daily HMAC, no plain IP) |
| `src/name.ts` | account names: usernames only, reserved names, no email |
| `src/krypto.ts` | salted HMAC, constant-time compare, tokens |
| `src/grenzen.ts` | the Cloudflare free-tier limits (one table, with sources) |
| `src/nutzung.ts` | self-metering, `GET /v1/nutzung`, storage brake, R2 recount, GraphQL |
| `migrations/` | D1 schema |
| `scripts/` | admin: invite codes, publishing a release |
| `test/` | vitest inside the Workers runtime (`@cloudflare/vitest-plugin`) |

## Behaviour worth knowing

- **Anonymous accounts**: an account is a username (3–32 characters
  `a-z 0-9 . _ -`, starting with a letter, NFC + lower case; reserved names
  refused on creation; anything with `@` is refused with "No email needed").
  No email is asked or stored. No generated account numbers either: one path
  for everyone, so the choice itself is not metadata. A taken name answers
  409 `name_vergeben` — the only answer that reveals a name exists, and only
  to someone holding an unused invite code.
- **No IPs, no names in logs or counters**: rate-limit keys are
  HMAC(daily key, name/IP), daily key = HMAC(`VORAB_GEHEIMNIS`, UTC date).
  Logs carry the route pattern only; invocation logs are off and query
  strings redacted (`wrangler.jsonc`). Cloudflare itself still sees client
  IPs at the edge.

- **Sessions**: 32 random bytes, stored only as SHA-256, valid 90 days,
  bound to the device name given at login (a session may only write its
  own device description). Changing the password with a normal session
  needs `altes_anmelde_schluessel` (checked like a login, rate limited) and
  ends all other sessions.
- **Emergency key** (`POST /v1/notfall`): returns `verpackt_notfall` and a
  15-minute token that can only call `PUT /v1/konto/passwort`; that call ends
  every session of the account, including the emergency one.
- **`/v1/vorab`** for an unknown name returns a salt derived with
  HMAC(`VORAB_GEHEIMNIS`, name) and the default KDF, so the answer does not
  reveal whether an account exists.
- **Invite codes** are stored as SHA-256 (upper case, no spaces). Creating an
  account uses one up; downloading the package does not. `--notiz` is
  optional — never put personal data there: a used code points to its account.
- **Mitte**: a stand is a full snapshot `name → blob`. Blobs live in R2 at
  `mitte/<account>/<sha256>` (an unchanged file is stored once) and are
  listed in D1 (`mitte_blobs`). Sending a stand:
  1. `POST /v1/mitte/fehlende {sha256: [...]}` → which blobs the server lacks,
  2. `PUT /v1/mitte/blob/<sha256>` for each (raw bytes, ≤ 24 MiB, streamed to
     R2; R2 checks the SHA-256 → 400 `pruefsumme` on mismatch),
  3. `POST /v1/mitte/stand {basis, verweise: {name: sha256}, schreiben: {name: base64}, loeschen}`.
     Small files may go inline in `schreiben` (≤ 256 KiB in total).
     A referenced blob that is not there → 400 `blob_fehlt` with `fehlen`.
  The stand is compare-and-swap on the head in one D1 transaction (409
  `jemand_schneller` otherwise). Every stand that was ever the head is kept
  for `enthaelt`; file lists are kept for the newest 10.
- **Limits**: JSON bodies 16 KiB, ownership 1 MiB, device description 16 KiB,
  stand JSON 4 MiB (inline part 256 KiB), blob 24 MiB, 20 000 names per
  stand / `fehlende` call.
- No CORS, no request bodies or tokens in logs.

## Free-tier usage

Only R2 costs money above the free tier; Workers and D1 just fail until the
next UTC day. The limits live in `src/grenzen.ts`, checked **2026-10-23**
against the Cloudflare docs (GB taken as 10^9 bytes — the docs do not say;
decimal is the smaller, safer number):

| id | Limit (Workers Free) | Period | Source |
|---|---|---|---|
| `worker_anfragen` | 100,000 requests | day (UTC) | https://developers.cloudflare.com/workers/platform/limits/ |
| `d1_gelesen` | 5,000,000 rows read | day (UTC) | https://developers.cloudflare.com/d1/platform/pricing/ |
| `d1_geschrieben` | 100,000 rows written | day (UTC) | https://developers.cloudflare.com/d1/platform/pricing/ |
| `d1_speicher` | 500 MB per database (5 GB per account) | now | https://developers.cloudflare.com/d1/platform/limits/ |
| `r2_speicher` | 10 GB-month storage | now (current bytes) | https://developers.cloudflare.com/r2/pricing/ |
| `r2_a` | 1,000,000 Class A ops (put, list, multipart) | month (UTC) | https://developers.cloudflare.com/r2/pricing/ |
| `r2_b` | 10,000,000 Class B ops (get, head) | month (UTC) | https://developers.cloudflare.com/r2/pricing/ |

- **Self-metering**: each request runs against a counting view of D1 and R2
  (`meta.rows_read/rows_written/size_after`; R2 ops per call; stored bytes
  exact on put/delete). After the answer, ONE upsert adds them to today's row
  in `nutzung_tag` (`ctx.waitUntil`; a failure is logged, never returned).
  The meter itself costs 1 D1 row write per request. Measured CPU overhead
  (Node, mocked bindings): about 5 µs per request.
- **Crons**: `17 3 * * *` cleans up and recounts all R2 bytes from a bucket
  list (catches packages uploaded by wrangler). `47 * * * *` asks the
  GraphQL Analytics API — only if the secret `CF_ANALYTICS_TOKEN` and the var
  `CF_ACCOUNT_ID` are set. Those numbers are account-wide; the report takes
  the larger of self-counted and Cloudflare and shows both.
- **`GET /v1/nutzung`**: only for accounts listed in the var `BETREIBER_NAMEN`
  (others 403 `nur_betreiber`). Per limit: used, limit, unit, period, percent,
  level (`ok`, `50`, `80`, `95`, `voll`), source; plus `warnungen`.
  Client: `zentrale cloud usage`; `zentrale status` and the start of
  `zentrale` print one warning line at ≥ 50 % (cached 1 h).
- **Brake**: with `BREMSE_SPEICHER` = `an` (default), `PUT /v1/mitte/blob`
  and inline files of a stand answer 507 `speicher_voll` when they would push
  stored R2 bytes over 10 GB; `scripts/paket_hochladen.mjs` refuses the same
  way (unless `--ohne-bremse`) and adds the package size to the count.
- Months are UTC calendar months; Cloudflare's billing month may be shifted.

### Optional: Cloudflare analytics token

Create a custom API token in the Cloudflare dashboard (Account API tokens →
Create Token → Custom token) with exactly one permission: **Account →
Account Analytics → Read**, limited to this account. Store it as the Worker
secret `CF_ANALYTICS_TOKEN` and put the account id into `vars.CF_ACCOUNT_ID`
in `wrangler.jsonc`, then deploy.

## Tests

```
npm ci
npm test          # vitest, fully local (Miniflare), no Cloudflare account needed
npm run typecheck
```

## Secrets

| Name | What |
|---|---|
| `VORAB_GEHEIMNIS` | HMAC key for the fake `vorab` answers. Any long random string. |
| `CF_ANALYTICS_TOKEN` | optional: API token with "Account Analytics: Read" for the usage numbers. |

Never in the repo. Local `wrangler dev` reads it from `.dev.vars`
(gitignored).

## Deploy

Runs on the **Workers Free** plan (10 ms CPU per request). Measured locally
on a slow laptop (pure CPU, D1/R2 time is I/O and not counted): login/account
hash 0.04 ms; usage meter ~0.005 ms per request; a stand with 100 / 1 100 / 2 000 references 1.3 / 5.3 / 7.6 ms;
inline 256 KiB 4.3 ms; blob upload is streamed (no hashing in the Worker).
Only a stand with far more than ~2 000 new names at once would go over.

```
cd cloud
npm ci
npx wrangler login
# First deploy: the Worker does not exist yet, so the secret goes in with it.
# Put one line VORAB_GEHEIMNIS=<long random string> into .secrets.env (gitignored).
npx wrangler deploy --secrets-file .secrets.env   # also creates D1 "zentrale" + R2 "zentrale"
rm .secrets.env
npx wrangler d1 migrations apply zentrale --remote
node scripts/paket_hochladen.mjs --remote          # dist/ + ../deploy/install.sh
node scripts/code_anlegen.mjs --remote --notiz "batch 1"     # no personal data in notes
```

Vars (in `wrangler.jsonc`): `BETREIBER_NAMEN` (account names that may read usage; empty = nobody),
`BREMSE_SPEICHER` (`an`/`aus`), `CF_ACCOUNT_ID` (optional, for analytics).
After changing them run `npm run types`.

Later deploys: `npx wrangler deploy`; new migrations:
`npx wrangler d1 migrations apply zentrale --remote`; rotate the secret:
`npx wrangler secret put VORAB_GEHEIMNIS`.

## Admin scripts

```
node scripts/code_anlegen.mjs --local|--remote [--anzahl N] [--notiz TEXT]
node scripts/code_anlegen.mjs --local|--remote --sperren ZB-XXXX-XXXX-XXXX-XXXX
node scripts/paket_hochladen.mjs --local|--remote [--dist ../dist] [--install ../deploy/install.sh] [--ohne-bremse]
```

`--local` targets the storage of `wrangler dev` (apply migrations there first
with `npx wrangler d1 migrations apply zentrale --local`).
