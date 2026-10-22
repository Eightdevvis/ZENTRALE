// Rate limit for login-like routes: 5 failed attempts per 15 minutes, counted
// separately per mail and per client IP. Keys are hashed (no plain mail/IP in
// the table). Only failures count; a success clears the mail counter.

import { HttpFehler } from "./hilfe";
import { sha256Hex } from "./krypto";

export const MAX_FEHLVERSUCHE = 5;
export const FENSTER_MS = 15 * 60 * 1000;

export interface Drossel {
  schluessel: string[];
}

export function ip(anfrage: Request): string {
  return anfrage.headers.get("CF-Connecting-IP") ?? "unbekannt";
}

export async function drossel(route: string, mail: string, adresse: string): Promise<Drossel> {
  return {
    schluessel: [
      `${route}:mail:${await sha256Hex(mail)}`,
      `${route}:ip:${await sha256Hex(adresse)}`,
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
