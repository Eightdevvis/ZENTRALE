// Insecure releases (build step 7, memory/hub/building_kit_plan.md 2.3).
//
// Every released version keeps syncing forever. The one exception is
// security, and even it does not force: a version found insecure is marked
// in D1 (`insecure_releases`, data, not code) and keeps working. A client
// that tells its version in the `Zentrale-Release` header gets two extra
// headers on every answer:
//
//   Deprecation: @<unix seconds>                       RFC 9745 (structured Date)
//   Link: <link>; rel="deprecation"; type="text/html"  RFC 9745 section 3
//
// `Sunset` is never sent: nothing is ever switched off. GET /v1/knoten adds
// `insecure: {since, link, reason}` to each device whose `programm` is marked,
// so every device (and later Schematix) can show it for the others too.

export const RELEASE_HEADER = "Zentrale-Release";
const VERSION = /^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$/;

export interface Insecure {
  version: string;
  since: number;
  link: string;
  reason: string;
}

export async function insecureVersions(db: D1Database, versions: string[]): Promise<Map<string, Insecure>> {
  const wanted = [...new Set(versions.filter((v) => typeof v === "string" && VERSION.test(v)))];
  const found = new Map<string, Insecure>();
  if (!wanted.length) return found;
  const r = await db
    .prepare("SELECT version, since, link, reason FROM insecure_releases WHERE version IN (SELECT value FROM json_each(?))")
    .bind(JSON.stringify(wanted)).all<Insecure>();
  for (const row of r.results) found.set(row.version, row);
  return found;
}

export function deprecationHeaders(i: Insecure): Record<string, string> {
  return {
    Deprecation: `@${Math.floor(i.since / 1000)}`,
    Link: `<${i.link}>; rel="deprecation"; type="text/html"`,
  };
}

/** Add the warning headers when the calling release is marked insecure.
 *  Never fails the request: on any error the answer goes out unchanged. */
export async function markInsecure(env: Env, request: Request, response: Response): Promise<Response> {
  const version = request.headers.get(RELEASE_HEADER)?.trim();
  if (!version || !VERSION.test(version)) return response;
  let i: Insecure | undefined;
  try {
    i = (await insecureVersions(env.DB, [version])).get(version);
  } catch {
    return response;
  }
  if (!i) return response;
  const marked = new Response(response.body, response);
  for (const [k, v] of Object.entries(deprecationHeaders(i))) marked.headers.set(k, v);
  return marked;
}

/** The `insecure` field of a device description (GET /v1/knoten). */
export function insecureField(i: Insecure): { since: string; link: string; reason: string } {
  return { since: new Date(i.since).toISOString(), link: i.link, reason: i.reason };
}
