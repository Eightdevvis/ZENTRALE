// The Mitte (sync star) over HTTP — same semantics as GitMitte in
// core/abgleich_mitte.py:
//
//   holen       GET  /v1/mitte                     {kennung|null, namen}
//               GET  /v1/mitte/datei/{name}        bytes of a file in the current stand
//   vorbereiten + senden
//               POST /v1/mitte/stand               compare-and-swap on the head
//   enthaelt    GET  /v1/mitte/enthaelt/{kennung}  was this stand ever the head?
//
// A stand is a full snapshot: name → blob. Blobs are opaque (already
// encrypted on the device) and stored content-addressed per account in R2
// (mitte/<konto_id>/<sha256>), so an unchanged file is stored only once.

import { HttpFehler, MB, b64Lesen, hex, json, jsonLesen, roh, ungueltig } from "./hilfe";
import { neueKennung } from "./krypto";

// Whole request in memory (JSON + base64 + decoded): stay well below 128 MB.
export const MAX_STAND = 24 * MB;
export const MAX_NAMEN = 20_000;
/** File lists are kept for the newest stands; older ones keep only their id. */
export const DATEILISTEN_BEHALTEN = 10;

const NAME = /^[\p{L}\p{N}._@-]+(\/[\p{L}\p{N}._@-]+)*$/u;

export function nameOk(name: string): boolean {
  return name.length <= 512 && NAME.test(name) && !name.split("/").some((t) => t === "." || t === "..");
}

const blobSchluessel = (konto: string, sha: string) => `mitte/${konto}/${sha}`;

async function kopf(db: D1Database, konto: string): Promise<string | null> {
  const r = await db.prepare("SELECT kennung FROM mitte_kopf WHERE konto_id = ?").bind(konto)
    .first<{ kennung: string | null }>();
  return r?.kennung ?? null;
}

export async function mitteHolen(env: Env, konto: string): Promise<Response> {
  const kennung = await kopf(env.DB, konto);
  if (kennung === null) return json({ kennung: null, namen: [] });
  const r = await env.DB
    .prepare("SELECT name FROM mitte_dateien WHERE konto_id = ? AND kennung = ? ORDER BY name")
    .bind(konto, kennung).all<{ name: string }>();
  return json({ kennung, namen: r.results.map((z) => z.name) });
}

export async function mitteDatei(env: Env, konto: string, name: string): Promise<Response> {
  const fehlt = () => new HttpFehler(404, "nicht_gefunden", "This file is not in the current stand.");
  if (!nameOk(name)) throw fehlt();
  const r = await env.DB
    .prepare(
      `SELECT d.sha256 FROM mitte_dateien d JOIN mitte_kopf k
          ON k.konto_id = d.konto_id AND k.kennung = d.kennung
        WHERE d.konto_id = ? AND d.name = ?`,
    )
    .bind(konto, name).first<{ sha256: string }>();
  if (!r) throw fehlt();
  const o = await env.R2.get(blobSchluessel(konto, r.sha256));
  if (!o) throw fehlt();
  return roh(o.body, "application/octet-stream", { "Content-Length": String(o.size) });
}

export async function mitteEnthaelt(env: Env, konto: string, kennung: string): Promise<Response> {
  const r = await env.DB.prepare("SELECT 1 AS ja FROM mitte_staende WHERE konto_id = ? AND kennung = ?")
    .bind(konto, kennung).first();
  return json({ enthaelt: r !== null });
}

interface Neu {
  n: string;
  h: string;
  g: number;
}

export async function mitteStand(env: Env, anfrage: Request, konto: string, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_STAND);
  const basis = d.basis ?? null;
  if (basis !== null && typeof basis !== "string") throw ungueltig("'basis' must be a stand id or null.");
  const schreiben = d.schreiben ?? {};
  const loeschen = d.loeschen ?? [];
  if (schreiben === null || typeof schreiben !== "object" || Array.isArray(schreiben)) {
    throw ungueltig("'schreiben' must be an object {name: base64}.");
  }
  if (!Array.isArray(loeschen)) throw ungueltig("'loeschen' must be a list of names.");
  const eintraege = Object.entries(schreiben as Record<string, unknown>);
  if (eintraege.length + loeschen.length > MAX_NAMEN) throw ungueltig("Too many files in one stand.");
  for (const n of loeschen) {
    if (typeof n !== "string" || !nameOk(n)) throw ungueltig("A name in 'loeschen' is not valid.");
    if (n in (schreiben as object)) throw ungueltig(`'${n}' is both written and deleted.`);
  }

  // Cheap early answer; the real check is the transaction below.
  if ((await kopf(env.DB, konto)) !== basis) throw schneller();

  // Blobs first (content-addressed, so writing them is harmless even if the
  // compare-and-swap below loses).
  const neu: Neu[] = [];
  for (const [n, wert] of eintraege) {
    if (!nameOk(n)) throw ungueltig(`The name '${n.slice(0, 80)}' is not valid.`);
    if (typeof wert !== "string") throw ungueltig(`'schreiben.${n}' must be base64.`);
    const bytes = b64Lesen(wert);
    const h = hex(await crypto.subtle.digest("SHA-256", bytes));
    neu.push({ n, h, g: bytes.byteLength });
    const k = blobSchluessel(konto, h);
    if (!(await env.R2.head(k))) await env.R2.put(k, bytes);
  }

  const kennung = neueKennung();
  const namen = JSON.stringify([...neu.map((x) => x.n), ...(loeschen as string[])]);
  // Every statement runs only while the head is still `basis`; the head moves
  // last. D1 runs a batch as one transaction, so it is all or nothing.
  const bedingung = "EXISTS (SELECT 1 FROM mitte_kopf WHERE konto_id = ? AND kennung IS ?)";
  const db = env.DB;
  const r = await db.batch([
    db.prepare("INSERT OR IGNORE INTO mitte_kopf (konto_id, kennung) VALUES (?, NULL)").bind(konto),
    db.prepare(`INSERT INTO mitte_staende (konto_id, kennung, basis, erstellt) SELECT ?, ?, ?, ? WHERE ${bedingung}`)
      .bind(konto, kennung, basis, jetzt, konto, basis),
    db.prepare(
      `INSERT INTO mitte_dateien (konto_id, kennung, name, sha256, groesse)
       SELECT konto_id, ?, name, sha256, groesse FROM mitte_dateien
        WHERE konto_id = ? AND kennung IS ? AND name NOT IN (SELECT value FROM json_each(?)) AND ${bedingung}`,
    ).bind(kennung, konto, basis, namen, konto, basis),
    db.prepare(
      `INSERT INTO mitte_dateien (konto_id, kennung, name, sha256, groesse)
       SELECT ?, ?, json_extract(value, '$.n'), json_extract(value, '$.h'), json_extract(value, '$.g')
         FROM json_each(?) WHERE ${bedingung}`,
    ).bind(konto, kennung, JSON.stringify(neu), konto, basis),
    db.prepare("UPDATE mitte_kopf SET kennung = ? WHERE konto_id = ? AND kennung IS ?").bind(kennung, konto, basis),
  ]);
  if (r[4].meta.changes !== 1) throw schneller();

  // Housekeeping: drop file lists of old stands (their ids stay for enthaelt).
  await db.prepare(
    `DELETE FROM mitte_dateien WHERE konto_id = ? AND kennung IN (
       SELECT kennung FROM mitte_staende WHERE konto_id = ? ORDER BY nr DESC LIMIT -1 OFFSET ?)`,
  ).bind(konto, konto, DATEILISTEN_BEHALTEN).run();

  return json({ kennung });
}

function schneller(): HttpFehler {
  return new HttpFehler(409, "jemand_schneller",
    "Someone else changed the data first. Fetch the current stand and merge again.");
}
