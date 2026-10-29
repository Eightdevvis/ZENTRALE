// Accounts and sessions (zero-knowledge: the server only sees values the
// client derived from the password; it stores salted HMAC-SHA256 of them).
// Anonymous: an account is a username or a 16-digit number (src/name.ts),
// never an email.
//
//   POST   /v1/konto           create (uses up the invite code)
//   POST   /v1/vorab           salt + kdf for a name (fake but stable if unknown)
//   POST   /v1/sitzung         log in → token
//   DELETE /v1/sitzung         log out
//   POST   /v1/notfall         emergency key → verpackt_notfall + restricted token
//   PUT    /v1/konto/passwort  new salt/kdf/anmelde_schluessel/verpackt_passwort

import { drossel, erfolg, fehlschlag, ip, pruefen } from "./drossel";
import { HttpFehler, KB, b64Lesen, b64u, json, jsonLesen, text, ungueltig } from "./hilfe";
import { HASH_ART, gleich, hmac, neuerHash, neuesToken, schluesselHash, sha256Hex, zufall } from "./krypto";
import { nameLesen, neuerNameLesen } from "./name";
import { codeHash } from "./paket";

export const SITZUNG_TAGE = 90;
export const NOTFALL_MINUTEN = 15;
const TAG_MS = 24 * 60 * 60 * 1000;
const MAX_JSON = 16 * KB;

export const KDF_VORGABE = { name: "argon2id", t: 3, m: 65536, p: 4 } as const;
export type Kdf = { name: "argon2id"; t: number; m: number; p: number };

export interface Sitzung {
  token_hash: string;
  konto_id: string;
  knoten: string;
  art: "normal" | "notfall";
}

interface KontoZeile {
  id: string;
  name: string;
  salz: string;
  kdf: string;
  anmelde_hash: string;
  anmelde_salz: string;
  notfall_hash: string;
  notfall_salz: string;
  hash_art: string;
  verpackt_passwort: string;
  verpackt_notfall: string;
}

// ── Field checks ─────────────────────────────────────────────────────────

const FERNET = /^[A-Za-z0-9_=-]+$/;
export const KNOTEN_NAME = /^[\p{L}\p{N}@._-]{1,64}$/u;

/** A 32-byte key from the client (base64url) → its bytes. */
function schluesselLesen(daten: Record<string, unknown>, feld: string): Uint8Array {
  const bytes = b64Lesen(text(daten, feld, 128));
  if (bytes.byteLength !== 32) throw ungueltig(`The field '${feld}' must be 32 bytes (base64url).`);
  return bytes;
}

function salzLesen(daten: Record<string, unknown>): string {
  const wert = text(daten, "salz", 128);
  const n = b64Lesen(wert).byteLength;
  if (n < 16 || n > 64) throw ungueltig("The field 'salz' must be 16 to 64 bytes (base64url).");
  return wert;
}

function verpacktLesen(daten: Record<string, unknown>, feld: string): string {
  const wert = text(daten, feld, 2048);
  if (!FERNET.test(wert)) throw ungueltig(`The field '${feld}' is not a Fernet token.`);
  return wert;
}

function ganz(wert: unknown, min: number, max: number, feld: string): number {
  if (typeof wert !== "number" || !Number.isInteger(wert) || wert < min || wert > max) {
    throw ungueltig(`kdf.${feld} must be an integer from ${min} to ${max}.`);
  }
  return wert;
}

/** Argon2id only; lower bounds follow OWASP (m ≥ 19 MiB). */
function kdfLesen(daten: Record<string, unknown>): Kdf {
  const k = daten.kdf;
  if (k === null || typeof k !== "object" || Array.isArray(k)) throw ungueltig("The field 'kdf' is missing.");
  const o = k as Record<string, unknown>;
  if (o.name !== "argon2id") throw ungueltig("kdf.name must be 'argon2id'.");
  return {
    name: "argon2id",
    t: ganz(o.t, 1, 20, "t"),
    m: ganz(o.m, 19456, 4194304, "m"),
    p: ganz(o.p, 1, 16, "p"),
  };
}

export function knotenLesen(daten: Record<string, unknown>): string {
  const name = text(daten, "knoten", 64);
  if (!KNOTEN_NAME.test(name)) throw ungueltig("The device name may only contain letters, digits, '@', '.', '_' and '-'.");
  return name;
}

// ── Sessions ─────────────────────────────────────────────────────────────

function bearer(anfrage: Request): string | null {
  const kopf = anfrage.headers.get("Authorization") ?? "";
  const m = /^Bearer ([A-Za-z0-9_-]{20,128})$/.exec(kopf.trim());
  return m ? m[1] : null;
}

const NICHT_ANGEMELDET = () =>
  new HttpFehler(401, "nicht_angemeldet", "You are not logged in (or the session has expired).",
    { "WWW-Authenticate": "Bearer" });

/** The session of this request, or null (no / unknown / expired token). */
export async function sitzungFinden(db: D1Database, anfrage: Request, jetzt: number): Promise<Sitzung | null> {
  const token = bearer(anfrage);
  if (!token) return null;
  const token_hash = await sha256Hex(token);
  return db
    .prepare("SELECT token_hash, konto_id, knoten, art FROM sitzungen WHERE token_hash = ? AND laeuft_ab > ?")
    .bind(token_hash, jetzt)
    .first<Sitzung>();
}

/** A full session (not the restricted emergency one), else 401/403. */
export async function angemeldet(db: D1Database, anfrage: Request, jetzt: number): Promise<Sitzung> {
  const s = await sitzungFinden(db, anfrage, jetzt);
  if (!s) throw NICHT_ANGEMELDET();
  if (s.art !== "normal") {
    throw new HttpFehler(403, "nur_passwort", "This session may only set a new password.");
  }
  return s;
}

async function sitzungAnlegen(db: D1Database, konto_id: string, knoten: string, art: "normal" | "notfall",
                              dauer: number, jetzt: number): Promise<{ token: string; laeuft_ab: number }> {
  const token = neuesToken();
  const laeuft_ab = jetzt + dauer;
  await db
    .prepare("INSERT INTO sitzungen (token_hash, konto_id, knoten, art, erstellt, laeuft_ab) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(await sha256Hex(token), konto_id, knoten, art, jetzt, laeuft_ab)
    .run();
  return { token, laeuft_ab };
}

const iso = (ms: number) => new Date(ms).toISOString();

// ── Routes ───────────────────────────────────────────────────────────────

export async function kontoAnlegen(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_JSON);
  const name = neuerNameLesen(d);
  const code = text(d, "code", 128);
  const salz = salzLesen(d);
  const kdf = kdfLesen(d);
  const anmelde = schluesselLesen(d, "anmelde_schluessel");
  const beweis = schluesselLesen(d, "notfall_beweis");
  const verpackt_passwort = verpacktLesen(d, "verpackt_passwort");
  const verpackt_notfall = verpacktLesen(d, "verpackt_notfall");

  const ch = await codeHash(code);
  const frei = await env.DB
    .prepare("SELECT 1 AS ok FROM codes WHERE code_hash = ? AND gesperrt = 0 AND verbraucht_von IS NULL")
    .bind(ch).first();
  if (!frei) throw new HttpFehler(403, "code_ungueltig", "This invite code is not valid or was already used.");

  const ah = await neuerHash(anmelde);
  const nh = await neuerHash(beweis);
  const id = crypto.randomUUID();

  // One transaction: the account only appears if the code is still free, and
  // the code is used up by exactly this account.
  let ergebnis: D1Result[];
  try {
    ergebnis = await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO konten (id, name, salz, kdf, anmelde_hash, anmelde_salz, notfall_hash, notfall_salz,
                             hash_art, verpackt_passwort, verpackt_notfall, erstellt, geaendert)
         SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
          WHERE EXISTS (SELECT 1 FROM codes WHERE code_hash = ? AND gesperrt = 0 AND verbraucht_von IS NULL)`,
      ).bind(id, name, salz, JSON.stringify(kdf), ah.hash, ah.salz, nh.hash, nh.salz, HASH_ART,
        verpackt_passwort, verpackt_notfall, jetzt, jetzt, ch),
      env.DB.prepare(
        `UPDATE codes SET verbraucht_von = ?, verbraucht_am = ?
          WHERE code_hash = ? AND verbraucht_von IS NULL AND EXISTS (SELECT 1 FROM konten WHERE id = ?)`,
      ).bind(id, jetzt, ch, id),
      env.DB.prepare("INSERT INTO mitte_kopf (konto_id, kennung) SELECT ?, NULL WHERE EXISTS (SELECT 1 FROM konten WHERE id = ?)")
        .bind(id, id),
    ]);
  } catch (e) {
    // Necessarily tells that this name exists — the only route that does.
    if (String(e).includes("UNIQUE")) {
      throw new HttpFehler(409, "name_vergeben", "This name is already taken. Please choose another one.");
    }
    throw e;
  }
  if (ergebnis[0].meta.changes !== 1) {
    throw new HttpFehler(403, "code_ungueltig", "This invite code is not valid or was already used.");
  }
  return json({ name, erstellt: iso(jetzt) }, 201);
}

export async function vorab(env: Env, anfrage: Request): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_JSON);
  const name = nameLesen(d);
  const k = await env.DB.prepare("SELECT salz, kdf FROM konten WHERE name = ?").bind(name)
    .first<{ salz: string; kdf: string }>();
  if (k) return json({ salz: k.salz, kdf: JSON.parse(k.kdf) });
  // Unknown name: invented values that stay the same for this name, so the
  // answer does not reveal whether the account exists.
  if (!env.VORAB_GEHEIMNIS) {
    throw new HttpFehler(503, "nicht_eingerichtet", "The server is not fully configured.");
  }
  const h = await hmac(env.VORAB_GEHEIMNIS, `zentrale/vorab/v1|${name}`);
  return json({ salz: b64u(h.slice(0, 16)), kdf: KDF_VORGABE });
}

/** Verify `wert` against the stored hash. Unknown account → same work, false. */
async function pruefeHash(wert: Uint8Array, k: { hash: string; salz: string; art: string } | null): Promise<boolean> {
  if (k === null) {
    await schluesselHash(wert, zufall(32));
    return false;
  }
  if (k.art !== HASH_ART) throw new Error(`unknown hash_art ${k.art}`);
  const ist = await schluesselHash(wert, b64Lesen(k.salz));
  return gleich(ist, b64Lesen(k.hash));
}

const anmeldeHash = (k: KontoZeile | null) =>
  k ? { hash: k.anmelde_hash, salz: k.anmelde_salz, art: k.hash_art } : null;
const notfallHash = (k: KontoZeile | null) =>
  k ? { hash: k.notfall_hash, salz: k.notfall_salz, art: k.hash_art } : null;

export async function anmelden(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_JSON);
  const name = nameLesen(d);
  const anmelde = schluesselLesen(d, "anmelde_schluessel");
  const knoten = knotenLesen(d);

  const dr = await drossel(env, "sitzung", name, ip(anfrage), jetzt);
  await pruefen(env.DB, dr, jetzt);
  const k = await env.DB.prepare("SELECT * FROM konten WHERE name = ?").bind(name).first<KontoZeile>();
  const ok = await pruefeHash(anmelde, anmeldeHash(k));
  if (!ok || !k) {
    await fehlschlag(env.DB, dr, jetzt);
    throw new HttpFehler(401, "falsche_anmeldung", "Wrong name or password.");
  }
  await erfolg(env.DB, dr);
  const s = await sitzungAnlegen(env.DB, k.id, knoten, "normal", SITZUNG_TAGE * TAG_MS, jetzt);
  return json({ token: s.token, laeuft_ab: iso(s.laeuft_ab), verpackt_passwort: k.verpackt_passwort });
}

export async function abmelden(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  const s = await sitzungFinden(env.DB, anfrage, jetzt);
  if (!s) throw NICHT_ANGEMELDET();
  await env.DB.prepare("DELETE FROM sitzungen WHERE token_hash = ?").bind(s.token_hash).run();
  return json({ abgemeldet: true });
}

export async function notfall(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_JSON);
  const name = nameLesen(d);
  const beweis = schluesselLesen(d, "notfall_beweis");

  const dr = await drossel(env, "notfall", name, ip(anfrage), jetzt);
  await pruefen(env.DB, dr, jetzt);
  const k = await env.DB.prepare("SELECT * FROM konten WHERE name = ?").bind(name).first<KontoZeile>();
  const ok = await pruefeHash(beweis, notfallHash(k));
  if (!ok || !k) {
    await fehlschlag(env.DB, dr, jetzt);
    throw new HttpFehler(401, "falscher_notfallschluessel", "This emergency key does not match this account.");
  }
  await erfolg(env.DB, dr);
  // Restricted session: may only set a new password, valid for 15 minutes.
  const s = await sitzungAnlegen(env.DB, k.id, "notfall", "notfall", NOTFALL_MINUTEN * 60 * 1000, jetzt);
  return json({ verpackt_notfall: k.verpackt_notfall, token: s.token, laeuft_ab: iso(s.laeuft_ab) });
}

export async function passwortSetzen(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  const s = await sitzungFinden(env.DB, anfrage, jetzt);
  if (!s) throw NICHT_ANGEMELDET();
  const d = await jsonLesen(anfrage, MAX_JSON);
  const salz = salzLesen(d);
  const kdf = kdfLesen(d);
  const anmelde = schluesselLesen(d, "anmelde_schluessel");
  const verpackt_passwort = verpacktLesen(d, "verpackt_passwort");
  const k = await env.DB.prepare("SELECT * FROM konten WHERE id = ?").bind(s.konto_id).first<KontoZeile>();
  if (!k) throw NICHT_ANGEMELDET();

  // A normal session must prove the old password (a stolen session alone
  // cannot lock the owner out). The 15-minute emergency session already
  // proved the emergency key.
  if (s.art === "normal") {
    const alt = schluesselLesen(d, "altes_anmelde_schluessel");
    const dr = await drossel(env, "passwort", k.name, ip(anfrage), jetzt);
    await pruefen(env.DB, dr, jetzt);
    if (!(await pruefeHash(alt, anmeldeHash(k)))) {
      await fehlschlag(env.DB, dr, jetzt);
      throw new HttpFehler(401, "falsche_anmeldung", "The old password is wrong.");
    }
    await erfolg(env.DB, dr);
  }
  const h = await neuerHash(anmelde);

  // All other sessions end: whoever knew the old password is logged out.
  // After an emergency reset, the restricted session ends too.
  const behalten = s.art === "normal" ? s.token_hash : "";
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE konten SET salz = ?, kdf = ?, anmelde_hash = ?, anmelde_salz = ?, hash_art = ?, verpackt_passwort = ?,
                         geaendert = ?
        WHERE id = ?`,
    ).bind(salz, JSON.stringify(kdf), h.hash, h.salz, HASH_ART, verpackt_passwort, jetzt, s.konto_id),
    env.DB.prepare("DELETE FROM sitzungen WHERE konto_id = ? AND token_hash != ?").bind(s.konto_id, behalten),
  ]);
  return json({ geaendert: iso(jetzt) });
}
