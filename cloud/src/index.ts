// ZENTRALE cloud — Cloudflare Worker.
// Contract: memory/hub/knoten_beitritt.md ("Bauplan v1"), cloud/openapi.yaml.
// Answers are JSON; errors are {"fehler": "<code>", "text": "<English sentence>"}.
// No CORS: the clients are the CLI and the installer, not browsers.

import { HttpFehler, fehlerAntwort, jetzt } from "./hilfe";
import { abmelden, angemeldet, anmelden, kontoAnlegen, notfall, passwortSetzen, vorab } from "./konto";
import { besitzHolen, besitzSetzen, knotenListe, knotenSetzen } from "./knoten";
import { mitteBlob, mitteDatei, mitteEnthaelt, mitteFehlende, mitteHolen, mitteStand } from "./mitte";
import { neuerZaehler, nutzungRoute, zaehlendeUmgebung, zaehlerSchreiben, speicherNachzaehlen, cloudflareAbfragen } from "./nutzung";
import { installSh, paketDatei, paketInfo } from "./paket";
import { apkGet, apkPut, releaseGet, releasePut } from "./phone";

type Handler = (env: Env, anfrage: Request, p: Record<string, string>, t: number) => Promise<Response>;

interface Route {
  methode: string;
  /** OpenAPI-style path; cloud/openapi.yaml must list exactly these. */
  pfad: string;
  handler: Handler;
}

const auth = (f: (env: Env, a: Request, s: Awaited<ReturnType<typeof angemeldet>>, p: Record<string, string>, t: number) => Promise<Response>): Handler =>
  async (env, a, p, t) => f(env, a, await angemeldet(env.DB, a, t), p, t);

export const ROUTEN: Route[] = [
  { methode: "GET", pfad: "/install.sh", handler: (env) => installSh(env) },
  { methode: "GET", pfad: "/v1/paket", handler: (env, a, _p, t) => paketInfo(env, a, t) },
  { methode: "GET", pfad: "/v1/paket/{version}.tar.gz", handler: (env, a, p, t) => paketDatei(env, a, t, p.version) },
  { methode: "POST", pfad: "/v1/konto", handler: (env, a, _p, t) => kontoAnlegen(env, a, t) },
  { methode: "POST", pfad: "/v1/vorab", handler: (env, a) => vorab(env, a) },
  { methode: "POST", pfad: "/v1/sitzung", handler: (env, a, _p, t) => anmelden(env, a, t) },
  { methode: "DELETE", pfad: "/v1/sitzung", handler: (env, a, _p, t) => abmelden(env, a, t) },
  { methode: "POST", pfad: "/v1/notfall", handler: (env, a, _p, t) => notfall(env, a, t) },
  { methode: "PUT", pfad: "/v1/konto/passwort", handler: (env, a, _p, t) => passwortSetzen(env, a, t) },
  { methode: "GET", pfad: "/v1/mitte", handler: auth((env, _a, s) => mitteHolen(env, s.konto_id)) },
  { methode: "GET", pfad: "/v1/mitte/datei/{name}", handler: auth((env, _a, s, p) => mitteDatei(env, s.konto_id, p.name)) },
  { methode: "POST", pfad: "/v1/mitte/fehlende", handler: auth((env, a, s) => mitteFehlende(env, a, s.konto_id)) },
  { methode: "PUT", pfad: "/v1/mitte/blob/{sha256}", handler: auth((env, a, s, p, t) => mitteBlob(env, a, s.konto_id, p.sha256, t)) },
  { methode: "POST", pfad: "/v1/mitte/stand", handler: auth((env, a, s, _p, t) => mitteStand(env, a, s.konto_id, t)) },
  { methode: "GET", pfad: "/v1/mitte/enthaelt/{kennung}", handler: auth((env, _a, s, p) => mitteEnthaelt(env, s.konto_id, p.kennung)) },
  { methode: "GET", pfad: "/v1/knoten", handler: auth((env, _a, s) => knotenListe(env, s)) },
  { methode: "PUT", pfad: "/v1/knoten/{name}", handler: auth((env, a, s, p, t) => knotenSetzen(env, a, s, p.name, t)) },
  { methode: "GET", pfad: "/v1/besitz", handler: auth((env, _a, s) => besitzHolen(env, s)) },
  { methode: "PUT", pfad: "/v1/besitz", handler: auth((env, a, s, _p, t) => besitzSetzen(env, a, s, t)) },
  { methode: "GET", pfad: "/v1/nutzung", handler: auth((env, _a, s, _p, t) => nutzungRoute(env, s, t)) },
  { methode: "GET", pfad: "/v1/phone/release", handler: auth((env) => releaseGet(env)) },
  { methode: "PUT", pfad: "/v1/phone/release", handler: auth((env, a, s, _p, t) => releasePut(env, a, s, t)) },
  { methode: "GET", pfad: "/v1/phone/release/{code}.apk", handler: auth((env, _a, _s, p) => apkGet(env, p.code)) },
  { methode: "PUT", pfad: "/v1/phone/release/{code}.apk", handler: auth((env, a, s, p) => apkPut(env, a, s, p.code)) },
];

/** `{name}` in /v1/mitte/datei/ may span several path segments (d/<hmac>.enc). */
const MEHRTEILIG = new Set(["/v1/mitte/datei/{name}"]);

const MUSTER = ROUTEN.map((r) => {
  const teile = r.pfad.split(/(\{[a-z0-9]+\})/);
  const namen: string[] = [];
  const quelle = teile.map((t) => {
    const m = /^\{([a-z0-9]+)\}$/.exec(t);
    if (!m) return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    namen.push(m[1]);
    return MEHRTEILIG.has(r.pfad) ? "(.+)" : "([^/]+)";
  }).join("");
  return { route: r, re: new RegExp(`^${quelle}$`), namen };
});

async function bearbeiten(anfrage: Request, env: Env): Promise<Response> {
  const pfad = new URL(anfrage.url).pathname;
  const erlaubt: string[] = [];
  for (const { route, re, namen } of MUSTER) {
    const m = re.exec(pfad);
    if (!m) continue;
    if (route.methode !== anfrage.method) {
      erlaubt.push(route.methode);
      continue;
    }
    const p: Record<string, string> = {};
    try {
      namen.forEach((n, i) => (p[n] = decodeURIComponent(m[i + 1])));
    } catch {
      throw new HttpFehler(400, "ungueltig", "The address is not valid.");
    }
    return route.handler(env, anfrage, p, jetzt());
  }
  if (erlaubt.length) {
    throw new HttpFehler(405, "methode_falsch", "This method is not allowed here.", { Allow: erlaubt.join(", ") });
  }
  throw new HttpFehler(404, "nicht_gefunden", "There is nothing at this address.");
}

/** The route pattern of a path ("/v1/knoten/{name}"), never the path itself:
 *  device names and file names stay out of the logs. */
export function routeVon(pfad: string): string {
  return MUSTER.find((m) => m.re.test(pfad))?.route.pfad ?? "(unbekannt)";
}

async function antworten(anfrage: Request, env: Env): Promise<Response> {
  try {
    return await bearbeiten(anfrage, env);
  } catch (e) {
    if (e instanceof HttpFehler) return fehlerAntwort(e);
    // Never log request bodies, tokens, keys, names, IPs or raw paths —
    // only what went wrong on which route.
    console.error(JSON.stringify({
      nachricht: "unerwarteter Fehler",
      route: routeVon(new URL(anfrage.url).pathname),
      methode: anfrage.method,
      fehler: e instanceof Error ? e.message : String(e),
    }));
    return fehlerAntwort(new HttpFehler(500, "serverfehler", "Something went wrong on the server. Please try again."));
  }
}

/** Cron "17 3 * * *": daily cleanup + R2 recount (+ Cloudflare numbers). */
export const CRON_TAEGLICH = "17 3 * * *";

export default {
  async fetch(anfrage, env, ctx): Promise<Response> {
    // Self-metering: count D1 rows and R2 ops of this request, write them
    // after the answer (one upsert, never fails the request).
    const z = neuerZaehler();
    const antwort = await antworten(anfrage, zaehlendeUmgebung(env, z));
    ctx.waitUntil(zaehlerSchreiben(env.DB, z, jetzt(), 1));
    return antwort;
  },

  /** Daily: cleanup + recount; hourly: Cloudflare analytics (only with token). */
  async scheduled(ereignis, env, ctx): Promise<void> {
    const t = jetzt();
    const z = neuerZaehler();
    const zenv = zaehlendeUmgebung(env, z);
    try {
      if (ereignis.cron === CRON_TAEGLICH) {
        await zenv.DB.batch([
          zenv.DB.prepare("DELETE FROM sitzungen WHERE laeuft_ab <= ?").bind(t),
          zenv.DB.prepare("DELETE FROM drossel WHERE start <= ?").bind(t - 24 * 60 * 60 * 1000),
          // Keep usage rows for about 13 months.
          zenv.DB.prepare("DELETE FROM nutzung_tag WHERE tag < ?").bind(new Date(t - 400 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)),
        ]);
        await speicherNachzaehlen(zenv, t);
      }
      await cloudflareAbfragen(zenv, t);
    } finally {
      ctx.waitUntil(zaehlerSchreiben(env.DB, z, t, 0));
    }
  },
} satisfies ExportedHandler<Env>;
