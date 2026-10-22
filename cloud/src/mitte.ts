// The Mitte (sync star) over HTTP — same semantics as GitMitte in
// core/abgleich_mitte.py:
//
//   holen       GET  /v1/mitte                     {kennung|null, namen}
//               GET  /v1/mitte/datei/{name}        bytes of a file in the current stand
//   vorbereiten + senden
//               POST /v1/mitte/fehlende            which blobs does the server still need?
//               PUT  /v1/mitte/blob/{sha256}       upload one blob (raw, ≤ 24 MiB)
//               POST /v1/mitte/stand               compare-and-swap on the head
//   enthaelt    GET  /v1/mitte/enthaelt/{kennung}  was this stand ever the head?
//
// A stand is a full snapshot: name → blob. Blobs are opaque (already
// encrypted on the device) and stored content-addressed per account in R2
// (mitte/<konto_id>/<sha256>), so an unchanged file is stored only once.
// Big files go up one by one as blobs and the stand only refers to them
// (`verweise`); small changes may still travel inline (`schreiben`).

import { HttpFehler, MB, b64Lesen, hex, json, jsonLesen, roh, ungueltig } from "./hilfe";

const SHA = /^[0-9a-f]{64}$/;
import { neueKennung } from "./krypto";

/** JSON body of POST /v1/mitte/stand (inline files + references). */
export const MAX_STAND = 4 * MB;
/** Inline files (`schreiben`) per stand, decoded. Bigger → blobs. Keeps
 *  base64 + SHA-256 in the Worker to a few ms of CPU. */
export const MAX_INLINE = 256 * 1024;
/** One blob upload (streamed to R2, never held in memory). */
export const MAX_BLOB = 24 * MB;
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

export async function mitteFehlende(env: Env, anfrage: Request, konto: string): Promise<Response> {
  const d = await jsonLesen(anfrage, 2 * MB);
  const liste = d.sha256;
  if (!Array.isArray(liste) || liste.length > MAX_NAMEN || !liste.every((h) => typeof h === "string" && SHA.test(h))) {
    throw ungueltig(`'sha256' must be a list of at most ${MAX_NAMEN} lower-case hex SHA-256 values.`);
  }
  const fehlen = await fehlendeBlobs(env.DB, konto, liste as string[]);
  return json({ fehlen });
}

async function fehlendeBlobs(db: D1Database, konto: string, liste: string[]): Promise<string[]> {
  if (liste.length === 0) return [];
  const r = await db
    .prepare(
      `SELECT DISTINCT value AS h FROM json_each(?)
        WHERE value NOT IN (SELECT sha256 FROM mitte_blobs WHERE konto_id = ?)`,
    )
    .bind(JSON.stringify(liste), konto).all<{ h: string }>();
  return r.results.map((z) => z.h);
}

export async function mitteBlob(env: Env, anfrage: Request, konto: string, sha: string, jetzt: number): Promise<Response> {
  if (!SHA.test(sha)) throw ungueltig("The address must end in a lower-case hex SHA-256.");
  const laenge = anfrage.headers.get("Content-Length");
  if (laenge === null || !/^\d+$/.test(laenge)) {
    throw new HttpFehler(411, "laenge_fehlt", "Send the blob with a Content-Length header.");
  }
  const groesse = Number(laenge);
  if (groesse > MAX_BLOB) throw new HttpFehler(413, "zu_gross", `A blob may be at most ${MAX_BLOB} bytes.`);
  const da = await env.DB.prepare("SELECT 1 AS ja FROM mitte_blobs WHERE konto_id = ? AND sha256 = ?")
    .bind(konto, sha).first();
  if (da) {
    await anfrage.body?.cancel();
    return new Response(null, { status: 204 });
  }
  // Streamed straight to R2; R2 checks the SHA-256 itself (no hashing CPU in
  // the Worker, nothing stored if it does not match).
  try {
    await env.R2.put(blobSchluessel(konto, sha), anfrage.body ?? new Uint8Array(0), { sha256: sha });
  } catch (e) {
    if (/sha-?256|checksum|digest/i.test(String(e))) {
      throw new HttpFehler(400, "pruefsumme", "The blob does not match its SHA-256.");
    }
    throw e;
  }
  await env.DB.prepare("INSERT OR IGNORE INTO mitte_blobs (konto_id, sha256, groesse, erstellt) VALUES (?, ?, ?, ?)")
    .bind(konto, sha, groesse, jetzt).run();
  return new Response(null, { status: 204 });
}

export async function mitteStand(env: Env, anfrage: Request, konto: string, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_STAND);
  const basis = d.basis ?? null;
  if (basis !== null && typeof basis !== "string") throw ungueltig("'basis' must be a stand id or null.");
  const objekt = (feld: string) => {
    const w = d[feld] ?? {};
    if (w === null || typeof w !== "object" || Array.isArray(w)) throw ungueltig(`'${feld}' must be an object.`);
    return Object.entries(w as Record<string, unknown>);
  };
  const schreiben = objekt("schreiben");
  const verweise = objekt("verweise");
  const loeschen = d.loeschen ?? [];
  if (!Array.isArray(loeschen)) throw ungueltig("'loeschen' must be a list of names.");
  if (schreiben.length + verweise.length + loeschen.length > MAX_NAMEN) throw ungueltig("Too many files in one stand.");
  const gesehen = new Set<string>();
  for (const n of [...schreiben.map((e) => e[0]), ...verweise.map((e) => e[0]), ...loeschen]) {
    if (typeof n !== "string" || !nameOk(n)) throw ungueltig(`The name '${String(n).slice(0, 80)}' is not valid.`);
    if (gesehen.has(n)) throw ungueltig(`'${n}' appears more than once (schreiben/verweise/loeschen).`);
    gesehen.add(n);
  }
  let inline = 0;
  for (const [n, wert] of schreiben) {
    if (typeof wert !== "string") throw ungueltig(`'schreiben.${n}' must be base64.`);
    inline += Math.floor((wert.length * 3) / 4);
  }
  if (inline > MAX_INLINE) {
    throw new HttpFehler(413, "inline_zu_gross",
      `Inline files ('schreiben') may total at most ${MAX_INLINE} bytes; upload bigger ones as blobs and use 'verweise'.`);
  }
  for (const [n, h] of verweise) {
    if (typeof h !== "string" || !SHA.test(h)) throw ungueltig(`'verweise.${n}' must be a lower-case hex SHA-256.`);
  }

  // Cheap early answer; the real check is the transaction below.
  if ((await kopf(env.DB, konto)) !== basis) throw schneller();

  // Referenced blobs must already be uploaded.
  const verwiesen = verweise.map(([, h]) => h as string);
  const fehlen = await fehlendeBlobs(env.DB, konto, verwiesen);
  if (fehlen.length) {
    throw new HttpFehler(400, "blob_fehlt", "Some referenced blobs were not uploaded yet.", {}, { fehlen });
  }
  const groessen = new Map<string, number>();
  if (verwiesen.length) {
    const r = await env.DB
      .prepare("SELECT sha256, groesse FROM mitte_blobs WHERE konto_id = ? AND sha256 IN (SELECT value FROM json_each(?))")
      .bind(konto, JSON.stringify(verwiesen)).all<{ sha256: string; groesse: number }>();
    for (const z of r.results) groessen.set(z.sha256, z.groesse);
  }

  // Inline blobs first (content-addressed, so writing them is harmless even
  // if the compare-and-swap below loses).
  const neu: Neu[] = verweise.map(([n, h]) => ({ n, h: h as string, g: groessen.get(h as string) ?? 0 }));
  const blobZeilen: D1PreparedStatement[] = [];
  for (const [n, wert] of schreiben) {
    const bytes = b64Lesen(wert as string);
    const h = hex(await crypto.subtle.digest("SHA-256", bytes));
    neu.push({ n, h, g: bytes.byteLength });
    const k = blobSchluessel(konto, h);
    if (!(await env.R2.head(k))) await env.R2.put(k, bytes);
    blobZeilen.push(env.DB.prepare(
      "INSERT OR IGNORE INTO mitte_blobs (konto_id, sha256, groesse, erstellt) VALUES (?, ?, ?, ?)",
    ).bind(konto, h, bytes.byteLength, jetzt));
  }
  if (blobZeilen.length) await env.DB.batch(blobZeilen);

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
