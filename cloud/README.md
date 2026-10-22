# ZENTRALE cloud

The backend for logging in to ZENTRALE and syncing across devices: a
Cloudflare Worker (TypeScript) with D1 (accounts, sessions, invite codes,
rate-limit counters, the sync head and stand history, devices, ownership)
and R2 (encrypted sync blobs, release packages, `install.sh`).

**Zero-knowledge.** The server never sees a password, a key or plain
content. The client derives `anmelde_schluessel` and `notfall_beweis` from the
password / emergency key (Argon2id + HKDF); the server stores only
PBKDF2-SHA256 hashes of them (600 000 iterations, per-account server salt).
Synced files arrive already encrypted (Fernet) under HMAC'd names.

- API: [`openapi.yaml`](openapi.yaml) (OpenAPI 3.1). A test checks that it
  lists exactly the routes in `src/index.ts`.
- Contract and key scheme: `memory/hub/knoten_beitritt.md`, section
  "Bauplan v1". Operations notes (German): `memory/betrieb/cloud.md`.

## Layout

| Path | What |
|---|---|
| `src/index.ts` | route table, error handling, daily cleanup (cron) |
| `src/konto.ts` | account, `vorab`, login/logout, emergency key, password change |
| `src/mitte.ts` | the sync "Mitte": snapshot stands, compare-and-swap head, `enthaelt` |
| `src/knoten.ts` | device descriptions and account ownership |
| `src/paket.ts` | `install.sh`, release packages, invite-code check |
| `src/drossel.ts` | rate limit: 5 failures / 15 min per mail and per IP |
| `src/krypto.ts` | PBKDF2, constant-time compare, tokens |
| `migrations/` | D1 schema |
| `scripts/` | admin: invite codes, publishing a release |
| `test/` | vitest inside the Workers runtime (`@cloudflare/vitest-plugin`) |

## Behaviour worth knowing

- **Sessions**: 32 random bytes, stored only as SHA-256, valid 90 days,
  bound to the device name given at login (a session may only write its
  own device description). Changing the password ends all other sessions.
- **Emergency key** (`POST /v1/notfall`): returns `verpackt_notfall` and a
  15-minute token that can only call `PUT /v1/konto/passwort`; that call ends
  every session of the account, including the emergency one.
- **`/v1/vorab`** for an unknown mail returns a salt derived with
  HMAC(`VORAB_GEHEIMNIS`, mail) and the default KDF, so the answer does not
  reveal whether an account exists.
- **Invite codes** are stored as SHA-256 (upper case, no spaces). Creating an
  account uses one up; downloading the package does not.
- **Mitte**: a stand is a full snapshot `name → blob`. Blobs live in R2 at
  `mitte/<account>/<sha256>` (an unchanged file is stored once).
  `POST /v1/mitte/stand` is compare-and-swap on the head in one D1
  transaction (409 `jemand_schneller` otherwise). Every stand that was ever
  the head is kept for `enthaelt`; file lists are kept for the newest 10.
- **Limits**: JSON bodies 16 KiB, ownership 1 MiB, device description 16 KiB,
  one stand request 24 MiB (the whole request is held in memory).
- No CORS, no request bodies or tokens in logs.

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

Never in the repo. Local `wrangler dev` reads it from `.dev.vars`
(gitignored).

## Deploy

Needs the **Workers Paid** plan: one login costs one PBKDF2 with 600 000
iterations (~100–500 ms CPU), far above the Free plan's 10 ms per request.

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
node scripts/code_anlegen.mjs --remote --notiz "first code"
```

Later deploys: `npx wrangler deploy`; new migrations:
`npx wrangler d1 migrations apply zentrale --remote`; rotate the secret:
`npx wrangler secret put VORAB_GEHEIMNIS`.

## Admin scripts

```
node scripts/code_anlegen.mjs --local|--remote [--anzahl N] [--notiz TEXT]
node scripts/code_anlegen.mjs --local|--remote --sperren ZB-XXXX-XXXX-XXXX-XXXX
node scripts/paket_hochladen.mjs --local|--remote [--dist ../dist] [--install ../deploy/install.sh]
```

`--local` targets the storage of `wrangler dev` (apply migrations there first
with `npx wrangler d1 migrations apply zentrale --local`).
