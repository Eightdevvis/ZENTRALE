// WebCrypto building blocks: salted HMAC over values the client already
// derived (anmelde_schluessel, notfall_beweis), constant-time comparison,
// random tokens stored only as SHA-256.
//
// Why no slow hash on the server: the client runs Argon2id (64 MiB) on the
// password and sends a 256-bit derived key. A dictionary attack has to go
// through Argon2id anyway, and a 256-bit secret cannot be brute-forced, so a
// fast salted HMAC is enough — and keeps every request far below 10 ms CPU.

import { b64u, hex } from "./hilfe";

/** Current scheme name, stored per account in konten.hash_art. */
export const HASH_ART = "hmac-sha256";

const enc = new TextEncoder();

export function zufall(n: number): Uint8Array {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

export async function sha256(daten: Uint8Array | string): Promise<Uint8Array> {
  const roh = typeof daten === "string" ? enc.encode(daten) : daten;
  return new Uint8Array(await crypto.subtle.digest("SHA-256", roh));
}

export async function sha256Hex(daten: Uint8Array | string): Promise<string> {
  return hex(await sha256(daten));
}

export async function hmac(geheimnis: string, nachricht: string): Promise<Uint8Array> {
  const k = await crypto.subtle.importKey("raw", enc.encode(geheimnis),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(nachricht)));
}

/** HMAC-SHA256(key = server salt, msg = the client's derived key bytes). */
export async function schluesselHash(wert: Uint8Array, salz: Uint8Array): Promise<Uint8Array> {
  const k = await crypto.subtle.importKey("raw", salz, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, wert));
}

/** A new hash with a fresh 32-byte server salt. → {hash, salz} (base64url). */
export async function neuerHash(wert: Uint8Array): Promise<{ hash: string; salz: string }> {
  const salz = zufall(32);
  return { hash: b64u(await schluesselHash(wert, salz)), salz: b64u(salz) };
}

export function gleich(a: Uint8Array, b: Uint8Array): boolean {
  if (a.byteLength !== b.byteLength) {
    // Still spend a comparison so lengths do not shortcut timing.
    crypto.subtle.timingSafeEqual(a, a);
    return false;
  }
  return crypto.subtle.timingSafeEqual(a, b);
}

/** A session token: 32 random bytes as base64url. Stored only as SHA-256. */
export function neuesToken(): string {
  return b64u(zufall(32));
}

export function neueKennung(): string {
  return hex(zufall(16));
}
