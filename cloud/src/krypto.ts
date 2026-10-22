// WebCrypto building blocks. PBKDF2-SHA256 over values the client already
// derived (anmelde_schluessel, notfall_beweis), constant-time comparison,
// random tokens stored only as SHA-256.

import { b64u, hex } from "./hilfe";

/** OWASP 2023+ recommendation for PBKDF2-HMAC-SHA256. */
export const RUNDEN = 600_000;
/** Fallback if the runtime refuses RUNDEN (older Workers capped at 100k). */
export const RUNDEN_NOTFALL = 100_000;

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

export async function pbkdf2(wert: string, salz: Uint8Array, runden: number): Promise<Uint8Array> {
  const k = await crypto.subtle.importKey("raw", enc.encode(wert), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: salz, iterations: runden }, k, 256);
  return new Uint8Array(bits);
}

/** A new hash with fresh server salt. → {hash, salz, runden} (base64url). */
export async function neuerHash(wert: string): Promise<{ hash: string; salz: string; runden: number }> {
  const salz = zufall(16);
  let runden = RUNDEN;
  let h: Uint8Array;
  try {
    h = await pbkdf2(wert, salz, runden);
  } catch {
    runden = RUNDEN_NOTFALL;
    h = await pbkdf2(wert, salz, runden);
  }
  return { hash: b64u(h), salz: b64u(salz), runden };
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
