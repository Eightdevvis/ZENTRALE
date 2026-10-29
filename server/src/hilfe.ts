// Small shared helpers: errors, JSON answers, size-limited body reading,
// base64. No secrets are ever logged; errors carry a code + English text.

export class HttpFehler extends Error {
  constructor(
    public status: number,
    public code: string,
    public text: string,
    public kopf: Record<string, string> = {},
    public extra: Record<string, unknown> = {},
  ) {
    super(code);
  }
}

const KOPF_SICHER: Record<string, string> = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
};

export function json(daten: unknown, status = 200, kopf: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(daten), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...KOPF_SICHER, ...kopf },
  });
}

export function roh(body: ReadableStream | ArrayBuffer | Uint8Array | string | null, typ: string,
                    kopf: Record<string, string> = {}, status = 200): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": typ, ...KOPF_SICHER, ...kopf },
  });
}

export function fehlerAntwort(f: HttpFehler): Response {
  return json({ ...f.extra, fehler: f.code, text: f.text }, f.status, f.kopf);
}

export const KB = 1024;
export const MB = 1024 * 1024;

/** Read the request body, at most `max` bytes (413 beyond). */
export async function bodyLesen(anfrage: Request, max: number): Promise<Uint8Array> {
  const laenge = anfrage.headers.get("Content-Length");
  if (laenge !== null && Number(laenge) > max) throw zuGross(max);
  if (!anfrage.body) return new Uint8Array(0);
  const leser = anfrage.body.getReader();
  const teile: Uint8Array[] = [];
  let summe = 0;
  for (;;) {
    const { done, value } = await leser.read();
    if (done) break;
    summe += value.byteLength;
    if (summe > max) {
      await leser.cancel();
      throw zuGross(max);
    }
    teile.push(value);
  }
  const alles = new Uint8Array(summe);
  let pos = 0;
  for (const t of teile) {
    alles.set(t, pos);
    pos += t.byteLength;
  }
  return alles;
}

function zuGross(max: number): HttpFehler {
  return new HttpFehler(413, "zu_gross", `The request body is larger than ${max} bytes.`);
}

/** Body as a JSON object (400 otherwise). */
export async function jsonLesen(anfrage: Request, max: number): Promise<Record<string, unknown>> {
  const bytes = await bodyLesen(anfrage, max);
  let daten: unknown;
  try {
    daten = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw ungueltig("The request body is not valid JSON.");
  }
  if (daten === null || typeof daten !== "object" || Array.isArray(daten)) {
    throw ungueltig("The request body must be a JSON object.");
  }
  return daten as Record<string, unknown>;
}

export function ungueltig(text: string): HttpFehler {
  return new HttpFehler(400, "ungueltig", text);
}

/** A required string field, trimmed, with a maximum length. */
export function text(daten: Record<string, unknown>, feld: string, max: number): string {
  const wert = daten[feld];
  if (typeof wert !== "string" || wert.trim() === "") throw ungueltig(`The field '${feld}' is missing.`);
  if (wert.length > max) throw ungueltig(`The field '${feld}' is too long.`);
  return wert.trim();
}

// ── base64 ──────────────────────────────────────────────────────────────

const B64 = /^[A-Za-z0-9+/_-]*={0,2}$/;

/** Accepts standard and URL-safe base64, with or without padding. */
export function b64Lesen(wert: string): Uint8Array {
  if (!B64.test(wert) || wert.replace(/=+$/, "").length % 4 === 1) {
    throw ungueltig("A value is not valid base64.");
  }
  const s = wert.replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
  return new Uint8Array(Buffer.from(s, "base64"));
}

/** base64url without padding. */
export function b64u(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64url");
}

export function hex(bytes: ArrayBuffer | Uint8Array): string {
  return Buffer.from(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)).toString("hex");
}

export function jetzt(): number {
  return Date.now();
}
