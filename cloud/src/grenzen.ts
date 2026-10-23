// The Cloudflare free-tier limits — the ONE table (Worker: src/nutzung.ts;
// admin script: scripts/paket_hochladen.mjs imports this file directly, so it
// must stay plain, import-free TypeScript that Node can strip).
//
// Verified 2026-10-23 against the Cloudflare docs (URLs per line). GB is taken
// as 10^9 bytes (the docs do not say; decimal is the smaller, safer reading).

export const GRENZEN_GEPRUEFT = "2026-10-23";

export type Zeitraum = "day" | "month" | "now";

export interface Grenze {
  id: string;
  name: string;
  grenze: number;
  einheit: "requests" | "rows" | "bytes" | "operations";
  zeitraum: Zeitraum;
  /** true: going over costs money (R2); false: the service just stops. */
  kostet: boolean;
  quelle: string;
}

const Q_WORKERS = "https://developers.cloudflare.com/workers/platform/limits/";
const Q_D1 = "https://developers.cloudflare.com/d1/platform/pricing/";
const Q_D1_GRENZEN = "https://developers.cloudflare.com/d1/platform/limits/";
const Q_R2 = "https://developers.cloudflare.com/r2/pricing/";

export const GRENZEN: readonly Grenze[] = [
  // 100,000 requests/day, reset 00:00 UTC; beyond: error 1027.
  { id: "worker_anfragen", name: "Worker requests", grenze: 100_000, einheit: "requests", zeitraum: "day", kostet: false, quelle: Q_WORKERS },
  // 5 million rows read/day, 100,000 rows written/day, reset 00:00 UTC; beyond: queries fail.
  { id: "d1_gelesen", name: "D1 rows read", grenze: 5_000_000, einheit: "rows", zeitraum: "day", kostet: false, quelle: Q_D1 },
  { id: "d1_geschrieben", name: "D1 rows written", grenze: 100_000, einheit: "rows", zeitraum: "day", kostet: false, quelle: Q_D1 },
  // 500 MB per database on Free (the account total is 5 GB; one database hits 500 MB first).
  { id: "d1_speicher", name: "D1 database size", grenze: 500_000_000, einheit: "bytes", zeitraum: "now", kostet: false, quelle: Q_D1_GRENZEN },
  // 10 GB-month storage, 1 million Class A, 10 million Class B per month; beyond: billed.
  { id: "r2_speicher", name: "R2 storage", grenze: 10_000_000_000, einheit: "bytes", zeitraum: "now", kostet: true, quelle: Q_R2 },
  { id: "r2_a", name: "R2 Class A operations", grenze: 1_000_000, einheit: "operations", zeitraum: "month", kostet: true, quelle: Q_R2 },
  { id: "r2_b", name: "R2 Class B operations", grenze: 10_000_000, einheit: "operations", zeitraum: "month", kostet: true, quelle: Q_R2 },
];

export type Stufe = "ok" | "50" | "80" | "95" | "voll";
export const SCHWELLEN = [50, 80, 95] as const;

export function stufe(prozent: number): Stufe {
  if (prozent >= 100) return "voll";
  if (prozent >= 95) return "95";
  if (prozent >= 80) return "80";
  if (prozent >= 50) return "50";
  return "ok";
}

