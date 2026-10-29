// Rate limit for login-like routes: 5 failed attempts per 15 minutes, counted
// separately per account name and per client IP. Neither is stored: a key is
// HMAC(tageskey, value), where tageskey = HMAC(VORAB_GEHEIMNIS, UTC date)
// changes every day. A plain SHA-256 of an IPv4 address could be reversed by
// trying all 2^32; this cannot without the secret, and yesterday's keys are
// useless today. Price: a counter starts fresh at 00:00 UTC (at most 2×5
// attempts around midnight). Only failures count; a success clears the name
// counter. Old rows go with the daily cron.

import { HttpFehler, hex } from "./hilfe";
import { hmac } from "./krypto";

export const MAX_FEHLVERSUCHE = 5;
export const FENSTER_MS = 15 * 60 * 1000;

export interface Drossel {
  schluessel: string[];
}

export function ip(anfrage: Request): string {
  return anfrage.headers.get("CF-Connecting-IP") ?? "unbekannt";
}

export const utcTag = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** The key of today (UTC) for hashing names and IPs; 503 without the secret. */
async function tagesSchluessel(env: Env, jetzt: number): Promise<string> {
  if (!env.VORAB_GEHEIMNIS) {
    throw new HttpFehler(503, "nicht_eingerichtet", "The server is not fully configured.");
  }
  return hex(await hmac(env.VORAB_GEHEIMNIS, `zentrale/drossel/v1|${utcTag(jetzt)}`));
}

export async function drossel(env: Env, route: string, name: string, adresse: string,
                              jetzt: number): Promise<Drossel> {
  const tag = await tagesSchluessel(env, jetzt);
  return {
    schluessel: [
      `${route}:name:${hex(await hmac(tag, `name|${name}`))}`,
      `${route}:ip:${hex(await hmac(tag, `ip|${adresse}`))}`,
    ],
  };
}

/** 429 if any counter is full within its window. */
export async function pruefen(db: D1Database, d: Drossel, jetzt: number): Promise<void> {
  const grenze = jetzt - FENSTER_MS;
  const r = await db
    .prepare(
      `SELECT start, anzahl FROM drossel
        WHERE schluessel IN (?, ?) AND start > ? AND anzahl >= ?
        ORDER BY start LIMIT 1`,
    )
    .bind(d.schluessel[0], d.schluessel[1], grenze, MAX_FEHLVERSUCHE)
    .first<{ start: number; anzahl: number }>();
  if (r) {
    const sekunden = Math.max(1, Math.ceil((r.start + FENSTER_MS - jetzt) / 1000));
    throw new HttpFehler(429, "zu_viele_versuche",
      "Too many failed attempts. Please wait a few minutes and try again.",
      { "Retry-After": String(sekunden) });
  }
}

export async function fehlschlag(db: D1Database, d: Drossel, jetzt: number): Promise<void> {
  const grenze = jetzt - FENSTER_MS;
  const sql = `INSERT INTO drossel (schluessel, start, anzahl) VALUES (?, ?, 1)
    ON CONFLICT(schluessel) DO UPDATE SET
      anzahl = CASE WHEN drossel.start <= ? THEN 1 ELSE drossel.anzahl + 1 END,
      start  = CASE WHEN drossel.start <= ? THEN excluded.start ELSE drossel.start END`;
  await db.batch(d.schluessel.map((s) => db.prepare(sql).bind(s, jetzt, grenze, grenze)));
}

export async function erfolg(db: D1Database, d: Drossel): Promise<void> {
  await db.prepare("DELETE FROM drossel WHERE schluessel = ?").bind(d.schluessel[0]).run();
}
