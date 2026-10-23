// Free-tier usage: how close is the cloud to the Cloudflare free limits?
//
//   GET /v1/nutzung   Bearer, only for accounts in BETREIBER_MAILS (else 403)
//                     → {zeit, grenzen_geprueft, grenzen: [...], warnungen: [...]}
//
// Self-metering: every request runs against a counting view of D1 and R2
// (zaehlendeUmgebung). D1 rows come from `meta.rows_read/rows_written` of each
// result, the database size from `meta.size_after`; R2 operations are counted
// per call (Class A: put, list, multipart; Class B: get, head; delete is free).
// After the answer is built, ONE upsert adds the numbers to today's row
// (ctx.waitUntil, errors are logged and never reach the client).
//
// Stored R2 bytes: + size on every put, − size on delete (through the Worker),
// and the daily cron recounts the whole bucket from an R2 list (packages are
// uploaded with wrangler, outside the Worker; the recount picks them up).
//
// Optional truth from Cloudflare: with secret CF_ANALYTICS_TOKEN and var
// CF_ACCOUNT_ID the hourly cron asks the GraphQL Analytics API (account-wide
// numbers) and stores them; reports take the larger of both.
//
// Brake: PUT /v1/mitte/blob and inline files of a stand are refused with 507
// `speicher_voll` when they would push stored bytes over the free R2 storage
// (var BREMSE_SPEICHER = "an" | "aus"). Only R2 costs money above free;
// Workers and D1 simply fail when their daily limit is used up.

import { HttpFehler, json } from "./hilfe";
import type { Sitzung } from "./konto";

import { GRENZEN, GRENZEN_GEPRUEFT, type Grenze, type Stufe, type Zeitraum, stufe } from "./grenzen";

export { GRENZEN, GRENZEN_GEPRUEFT, stufe };

const grenze = (id: string): Grenze => GRENZEN.find((g) => g.id === id)!;
export const R2_SPEICHER_GRENZE = grenze("r2_speicher").grenze;

const RANG: Record<Stufe, number> = { ok: 0, "50": 1, "80": 2, "95": 3, voll: 4 };

// ── Self-metering ────────────────────────────────────────────────────────

export interface Zaehler {
  d1Gelesen: number;
  d1Geschrieben: number;
  /** Last database size seen in a result (0 = none). */
  d1Bytes: number;
  r2A: number;
  r2B: number;
  /** Change of stored R2 bytes in this request. */
  r2Bytes: number;
}

export function neuerZaehler(): Zaehler {
  return { d1Gelesen: 0, d1Geschrieben: 0, d1Bytes: 0, r2A: 0, r2B: 0, r2Bytes: 0 };
}

function d1Merken(z: Zaehler, r: D1Result<unknown> | undefined): void {
  const m = r?.meta;
  if (!m) return;
  z.d1Gelesen += m.rows_read ?? 0;
  z.d1Geschrieben += m.rows_written ?? 0;
  if (m.size_after) z.d1Bytes = m.size_after;
}

/** D1 that counts rows. `first()` runs as `all()` because only results carry meta. */
function d1Zaehlend(db: D1Database, z: Zaehler): D1Database {
  const echt = new WeakMap<object, D1PreparedStatement>();
  const satz = (s: D1PreparedStatement): D1PreparedStatement => {
    const p = new Proxy(s, {
      get(t, k) {
        if (k === "bind") return (...werte: unknown[]) => satz(t.bind(...werte));
        if (k === "all" || k === "run") {
          return async () => {
            const r = await t[k]();
            d1Merken(z, r);
            return r;
          };
        }
        if (k === "first") {
          return async (spalte?: string) => {
            const r = await t.all<Record<string, unknown>>();
            d1Merken(z, r);
            const zeile = r.results[0];
            if (!zeile) return null;
            return spalte === undefined ? zeile : (zeile[spalte] ?? null);
          };
        }
        const w = Reflect.get(t, k, t);
        return typeof w === "function" ? w.bind(t) : w;
      },
    });
    echt.set(p, s);
    return p;
  };
  return new Proxy(db, {
    get(t, k) {
      if (k === "prepare") return (sql: string) => satz(t.prepare(sql));
      if (k === "batch") {
        return async (liste: D1PreparedStatement[]) => {
          const r = await t.batch(liste.map((s) => echt.get(s) ?? s));
          for (const e of r) d1Merken(z, e);
          return r;
        };
      }
      const w = Reflect.get(t, k, t);
      return typeof w === "function" ? w.bind(t) : w;
    },
  });
}

/** R2 that counts operations and stored bytes. */
function r2Zaehlend(r2: R2Bucket, z: Zaehler): R2Bucket {
  const hochladen = (u: R2MultipartUpload): R2MultipartUpload => new Proxy(u, {
    get(t, k) {
      if (k === "uploadPart") {
        return (...a: Parameters<R2MultipartUpload["uploadPart"]>) => {
          z.r2A += 1;
          return t.uploadPart(...a);
        };
      }
      if (k === "complete") {
        return async (teile: R2UploadedPart[]) => {
          z.r2A += 1;
          const o = await t.complete(teile);
          z.r2Bytes += o.size;
          return o;
        };
      }
      const w = Reflect.get(t, k, t);
      return typeof w === "function" ? w.bind(t) : w;
    },
  });
  return new Proxy(r2, {
    get(t, k) {
      switch (k) {
        case "get":
        case "head":
          return (...a: unknown[]) => {
            z.r2B += 1;
            return Reflect.apply(t[k], t, a);
          };
        case "list":
          return (...a: Parameters<R2Bucket["list"]>) => {
            z.r2A += 1;
            return t.list(...a);
          };
        case "put":
          return async (...a: unknown[]) => {
            z.r2A += 1;
            const o = (await Reflect.apply(t.put, t, a)) as R2Object | null;
            if (o) z.r2Bytes += o.size;
            return o;
          };
        case "delete":
          // Delete is free, but the size is only known from a head (Class B).
          return async (schluessel: string | string[]) => {
            for (const s of Array.isArray(schluessel) ? schluessel : [schluessel]) {
              z.r2B += 1;
              const o = await t.head(s);
              if (o) z.r2Bytes -= o.size;
            }
            await t.delete(schluessel);
          };
        case "createMultipartUpload":
          return async (...a: Parameters<R2Bucket["createMultipartUpload"]>) => {
            z.r2A += 1;
            return hochladen(await t.createMultipartUpload(...a));
          };
        case "resumeMultipartUpload":
          return (...a: Parameters<R2Bucket["resumeMultipartUpload"]>) => hochladen(t.resumeMultipartUpload(...a));
        default: {
          const w = Reflect.get(t, k, t);
          return typeof w === "function" ? w.bind(t) : w;
        }
      }
    },
  });
}

/** This request's env with counting DB and R2. Built per request (no global state). */
export function zaehlendeUmgebung(env: Env, z: Zaehler): Env {
  return { ...env, DB: d1Zaehlend(env.DB, z), R2: r2Zaehlend(env.R2, z) };
}

const tagVon = (t: number) => new Date(t).toISOString().slice(0, 10);
const monatVon = (t: number) => new Date(t).toISOString().slice(0, 7);

/** What the meter's own upsert costs: measured locally 0 read / 1 written
 *  (test/nutzung.test.ts); reads are counted as 1 to stay on the safe side. */
export const EIGEN_GELESEN = 1;
export const EIGEN_GESCHRIEBEN = 1;

const HOCHZAEHLEN = `INSERT INTO nutzung_tag (tag, anfragen, d1_gelesen, d1_geschrieben, r2_a, r2_b, d1_bytes)
  VALUES (?, ?, ?, ?, ?, ?, ?)
  ON CONFLICT(tag) DO UPDATE SET
    anfragen       = anfragen + excluded.anfragen,
    d1_gelesen     = d1_gelesen + excluded.d1_gelesen,
    d1_geschrieben = d1_geschrieben + excluded.d1_geschrieben,
    r2_a           = r2_a + excluded.r2_a,
    r2_b           = r2_b + excluded.r2_b,
    d1_bytes       = CASE WHEN excluded.d1_bytes > 0 THEN excluded.d1_bytes ELSE d1_bytes END`;

/**
 * Add one request's numbers to today's row. One statement; a second one in
 * the same batch only when stored R2 bytes changed. Never throws.
 * `db` must be the raw binding (the meter does not count itself twice).
 */
export async function zaehlerSchreiben(db: D1Database, z: Zaehler, jetzt: number, anfragen: number): Promise<void> {
  try {
    const zeile = db.prepare(HOCHZAEHLEN).bind(tagVon(jetzt), anfragen, z.d1Gelesen + EIGEN_GELESEN,
      z.d1Geschrieben + EIGEN_GESCHRIEBEN, z.r2A, z.r2B, z.d1Bytes);
    if (z.r2Bytes === 0) {
      await zeile.run();
      return;
    }
    await db.batch([
      zeile,
      db.prepare("UPDATE nutzung_wert SET wert = MAX(0, wert + ?), aktualisiert = ? WHERE name = 'r2_bytes'")
        .bind(z.r2Bytes, jetzt),
    ]);
  } catch (e) {
    console.error(JSON.stringify({ nachricht: "Nutzung nicht gezählt", fehler: e instanceof Error ? e.message : String(e) }));
  }
}

// ── Brake ────────────────────────────────────────────────────────────────

/** 507 if `dazu` more bytes would push R2 over the free storage. */
export async function speicherPruefen(env: Env, dazu: number): Promise<void> {
  if ((env.BREMSE_SPEICHER ?? "an").trim().toLowerCase() === "aus") return;
  const r = await env.DB
    .prepare("SELECT MAX(wert) AS b FROM nutzung_wert WHERE name IN ('r2_bytes', 'cf:r2_speicher')")
    .first<{ b: number | null }>();
  if ((r?.b ?? 0) + dazu > R2_SPEICHER_GRENZE) {
    throw new HttpFehler(507, "speicher_voll",
      "The cloud storage is full (free limit reached). Nothing was stored. Please tell the operator.");
  }
}

// ── Report ───────────────────────────────────────────────────────────────

export interface Posten {
  id: string;
  name: string;
  used: number;
  limit: number;
  unit: Grenze["einheit"];
  period: Zeitraum;
  percent: number;
  level: Stufe;
  source: "self" | "cloudflare";
  self: number;
  cloudflare: number | null;
  cloudflare_at: string | null;
  costs_money: boolean;
}

export interface Warnung {
  id: string;
  name: string;
  level: Stufe;
  percent: number;
  text: string;
}

export interface Bericht {
  zeit: string;
  grenzen_geprueft: string;
  grenzen: Posten[];
  warnungen: Warnung[];
}

function zahl(n: number, einheit: Grenze["einheit"]): string {
  if (einheit !== "bytes") return n.toLocaleString("en-US");
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} kB`;
}

/** Numbers for all limits, self-counted and (if stored) from Cloudflare. */
export async function berichtErstellen(env: Env, jetzt: number): Promise<Bericht> {
  const tag = tagVon(jetzt);
  const monat = monatVon(jetzt);
  const [heute, imMonat, groesse, werte] = await env.DB.batch([
    env.DB.prepare("SELECT anfragen, d1_gelesen, d1_geschrieben FROM nutzung_tag WHERE tag = ?").bind(tag),
    env.DB.prepare("SELECT COALESCE(SUM(r2_a), 0) AS r2_a, COALESCE(SUM(r2_b), 0) AS r2_b FROM nutzung_tag WHERE tag >= ? AND tag <= ?")
      .bind(`${monat}-01`, `${monat}-31`),
    env.DB.prepare("SELECT d1_bytes FROM nutzung_tag WHERE d1_bytes > 0 ORDER BY tag DESC LIMIT 1"),
    env.DB.prepare("SELECT name, wert, zeitraum, aktualisiert FROM nutzung_wert"),
  ]);
  const h = (heute.results[0] ?? {}) as Record<string, number>;
  const m = (imMonat.results[0] ?? {}) as Record<string, number>;
  const g = (groesse.results[0] ?? {}) as Record<string, number>;
  const w = new Map((werte.results as { name: string; wert: number; zeitraum: string; aktualisiert: number }[])
    .map((z) => [z.name, z]));
  const selbst: Record<string, number> = {
    worker_anfragen: h.anfragen ?? 0,
    d1_gelesen: h.d1_gelesen ?? 0,
    d1_geschrieben: h.d1_geschrieben ?? 0,
    d1_speicher: g.d1_bytes ?? 0,
    r2_speicher: w.get("r2_bytes")?.wert ?? 0,
    r2_a: m.r2_a ?? 0,
    r2_b: m.r2_b ?? 0,
  };
  const grenzen: Posten[] = GRENZEN.map((gr) => {
    const cf = w.get(`cf:${gr.id}`);
    // A Cloudflare number only counts for the period it covers.
    const passt = cf && (gr.zeitraum === "day" ? cf.zeitraum === tag
      : gr.zeitraum === "month" ? cf.zeitraum === monat
        : jetzt - cf.aktualisiert < 26 * 60 * 60 * 1000);
    const cfWert = passt ? cf.wert : null;
    const eigen = selbst[gr.id] ?? 0;
    const used = Math.max(eigen, cfWert ?? 0);
    const percent = Math.round((used / gr.grenze) * 1000) / 10;
    return {
      id: gr.id, name: gr.name, used, limit: gr.grenze, unit: gr.einheit, period: gr.zeitraum,
      percent, level: stufe(percent), source: cfWert !== null && cfWert > eigen ? "cloudflare" : "self",
      self: eigen, cloudflare: cfWert, cloudflare_at: passt ? new Date(cf.aktualisiert).toISOString() : null,
      costs_money: gr.kostet,
    };
  });
  const warnungen: Warnung[] = grenzen
    .filter((p) => p.level !== "ok")
    .sort((a, b) => RANG[b.level] - RANG[a.level] || b.percent - a.percent)
    .map((p) => ({
      id: p.id, name: p.name, level: p.level, percent: p.percent,
      text: `${p.name} at ${p.percent} % (${zahl(p.used, p.unit)} of ${zahl(p.limit, p.unit)})`
        + (p.level === "voll" ? (p.costs_money ? " — above free, this now costs money." : " — used up, requests fail.") : "."),
    }));
  return { zeit: new Date(jetzt).toISOString(), grenzen_geprueft: GRENZEN_GEPRUEFT, grenzen, warnungen };
}

export function betreiber(env: Env, mail: string): boolean {
  return (env.BETREIBER_MAILS ?? "").split(",").map((m) => m.trim().toLowerCase()).filter(Boolean)
    .includes(mail.toLowerCase());
}

export async function nutzungRoute(env: Env, s: Sitzung, jetzt: number): Promise<Response> {
  const k = await env.DB.prepare("SELECT mail FROM konten WHERE id = ?").bind(s.konto_id).first<{ mail: string }>();
  if (!k || !betreiber(env, k.mail)) {
    throw new HttpFehler(403, "nur_betreiber", "Usage figures are only for the operator of this cloud.");
  }
  return json(await berichtErstellen(env, jetzt));
}

// ── Cron: recount R2, ask Cloudflare ─────────────────────────────────────

/** Sum of all object sizes in the bucket (one Class A op per 1000 objects). */
export async function speicherNachzaehlen(env: Env, jetzt: number): Promise<number> {
  let summe = 0;
  let cursor: string | undefined;
  for (;;) {
    const l = await env.R2.list({ cursor, limit: 1000 });
    for (const o of l.objects) summe += o.size;
    if (!l.truncated) break;
    cursor = l.cursor;
  }
  await env.DB.prepare(
    `INSERT INTO nutzung_wert (name, wert, zeitraum, aktualisiert) VALUES ('r2_bytes', ?, '', ?)
     ON CONFLICT(name) DO UPDATE SET wert = excluded.wert, aktualisiert = excluded.aktualisiert`,
  ).bind(summe, jetzt).run();
  return summe;
}

export const GRAPHQL = "https://api.cloudflare.com/client/v4/graphql";

type Holen = (url: string, init: RequestInit) => Promise<Response>;

/** Walk into a JSON value; undefined when the shape is not as expected. */
function teil(d: unknown, ...pfad: (string | number)[]): unknown {
  let x = d;
  for (const k of pfad) {
    if (x === null || typeof x !== "object") return undefined;
    x = (x as Record<string | number, unknown>)[k];
  }
  return x;
}

const nummer = (x: unknown): number => (typeof x === "number" && Number.isFinite(x) ? x : 0);

async function gql(holen: Holen, token: string, abfrage: string, variablen: Record<string, string>): Promise<unknown[] | null> {
  try {
    const r = await holen(GRAPHQL, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: abfrage, variables: variablen }),
    });
    const d: unknown = await r.json();
    const fehler = teil(d, "errors");
    if (!r.ok || (Array.isArray(fehler) && fehler.length)) {
      console.error(JSON.stringify({ nachricht: "GraphQL-Abfrage fehlgeschlagen", status: r.status,
        fehler: Array.isArray(fehler) ? fehler.map((f) => String(teil(f, "message"))).slice(0, 3) : null }));
      return null;
    }
    const gruppen = teil(d, "data", "viewer", "accounts", 0, "g");
    return Array.isArray(gruppen) ? gruppen : [];
  } catch (e) {
    console.error(JSON.stringify({ nachricht: "GraphQL nicht erreichbar", fehler: e instanceof Error ? e.message : String(e) }));
    return null;
  }
}

const KONTO = (datensatz: string, filter: string, felder: string) =>
  `query($a: string!, $von: Time!, $bis: Time!, $tag: Date!) { viewer { accounts(filter: {accountTag: $a}) {
    g: ${datensatz}(limit: 10000, filter: {${filter}}) { ${felder} } } } }`;

const ZEIT = "datetime_geq: $von, datetime_leq: $bis";
const DATUM = "date_geq: $tag, date_leq: $tag";

/** R2 actionType → class: Get… and Head… = B, Delete… and AbortMultipartUpload = free, everything else A (safe side). */
export function r2Klasse(aktion: string): "a" | "b" | "frei" {
  if (/^(Get|Head)/.test(aktion)) return "b";
  if (/^(Delete|AbortMultipartUpload)/.test(aktion)) return "frei";
  return "a";
}

/**
 * Ask the GraphQL Analytics API (account-wide) and store the numbers as
 * cf:<limit>. Does nothing without CF_ANALYTICS_TOKEN + CF_ACCOUNT_ID. Each
 * dataset is its own query, so one unknown field does not lose the others.
 * → the stored values (for tests and logs).
 */
export async function cloudflareAbfragen(env: Env, jetzt: number, holen: Holen = fetch): Promise<Record<string, number>> {
  const token = env.CF_ANALYTICS_TOKEN?.trim();
  const konto = env.CF_ACCOUNT_ID?.trim();
  if (!token || !konto) return {};
  const tag = tagVon(jetzt);
  const monat = monatVon(jetzt);
  const bis = new Date(jetzt).toISOString();
  const v = (von: string) => ({ a: konto, von, bis, tag });
  const tagesbeginn = `${tag}T00:00:00Z`;
  const monatsbeginn = `${monat}-01T00:00:00Z`;
  const gestern = new Date(jetzt - 24 * 60 * 60 * 1000).toISOString();

  const [workers, d1, d1s, r2ops, r2s] = await Promise.all([
    gql(holen, token, KONTO("workersInvocationsAdaptive", ZEIT, "sum { requests }"), v(tagesbeginn)),
    gql(holen, token, KONTO("d1AnalyticsAdaptiveGroups", DATUM, "sum { rowsRead rowsWritten }"), v(tagesbeginn)),
    gql(holen, token, KONTO("d1StorageAdaptiveGroups", DATUM, "max { databaseSizeBytes } dimensions { databaseId }"), v(tagesbeginn)),
    gql(holen, token, KONTO("r2OperationsAdaptiveGroups", ZEIT, "sum { requests } dimensions { actionType }"), v(monatsbeginn)),
    gql(holen, token, KONTO("r2StorageAdaptiveGroups", ZEIT, "max { payloadSize metadataSize } dimensions { bucketName }"), v(gestern)),
  ]);

  const neu: { id: string; wert: number; zeitraum: string }[] = [];
  const summe = (g: unknown[], ...pfad: string[]) => g.reduce<number>((s, x) => s + nummer(teil(x, ...pfad)), 0);
  if (workers) neu.push({ id: "worker_anfragen", wert: summe(workers, "sum", "requests"), zeitraum: tag });
  if (d1) {
    neu.push({ id: "d1_gelesen", wert: summe(d1, "sum", "rowsRead"), zeitraum: tag });
    neu.push({ id: "d1_geschrieben", wert: summe(d1, "sum", "rowsWritten"), zeitraum: tag });
  }
  if (d1s) {
    // The limit is per database: the biggest one counts.
    neu.push({ id: "d1_speicher", wert: d1s.reduce<number>((m, x) => Math.max(m, nummer(teil(x, "max", "databaseSizeBytes"))), 0), zeitraum: tag });
  }
  if (r2ops) {
    let a = 0;
    let b = 0;
    for (const x of r2ops) {
      const k = r2Klasse(String(teil(x, "dimensions", "actionType") ?? ""));
      if (k === "a") a += nummer(teil(x, "sum", "requests"));
      if (k === "b") b += nummer(teil(x, "sum", "requests"));
    }
    neu.push({ id: "r2_a", wert: a, zeitraum: monat }, { id: "r2_b", wert: b, zeitraum: monat });
  }
  if (r2s) {
    // Peak of the last 24 h per bucket, summed over buckets (free storage is per account).
    neu.push({ id: "r2_speicher", wert: summe(r2s, "max", "payloadSize") + summe(r2s, "max", "metadataSize"), zeitraum: tag });
  }
  if (neu.length) {
    await env.DB.batch(neu.map((n) => env.DB.prepare(
      `INSERT INTO nutzung_wert (name, wert, zeitraum, aktualisiert) VALUES (?, ?, ?, ?)
       ON CONFLICT(name) DO UPDATE SET wert = excluded.wert, zeitraum = excluded.zeitraum, aktualisiert = excluded.aktualisiert`,
    ).bind(`cf:${n.id}`, n.wert, n.zeitraum, jetzt)));
  }
  return Object.fromEntries(neu.map((n) => [n.id, n.wert]));
}
