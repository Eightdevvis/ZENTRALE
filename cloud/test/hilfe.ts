// Test helpers: call the Worker like a client would, make codes and accounts.
import { env, exports } from "cloudflare:workers";
import { expect } from "vitest";

let ipZaehler = 0;
/** A fresh client IP per call site, so per-IP rate limits do not bleed between tests. */
export function neueIp(): string {
  ipZaehler += 1;
  return `198.51.100.${ipZaehler % 250}`;
}

export interface Optionen {
  json?: unknown;
  body?: BodyInit;
  token?: string;
  ip?: string;
  kopf?: Record<string, string>;
}

export async function rufen(methode: string, pfad: string, o: Optionen = {}): Promise<Response> {
  const kopf: Record<string, string> = { "CF-Connecting-IP": o.ip ?? "203.0.113.1", ...(o.kopf ?? {}) };
  let body: BodyInit | undefined = o.body;
  if (o.json !== undefined) {
    body = JSON.stringify(o.json);
    kopf["Content-Type"] = "application/json";
  }
  if (o.token) kopf.Authorization = `Bearer ${o.token}`;
  return exports.default.fetch(new Request(`https://cloud.test${pfad}`, { method: methode, headers: kopf, body }));
}

export async function jsonVon(r: Response): Promise<Record<string, any>> {
  return (await r.json()) as Record<string, any>;
}

export function b64u(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function zufall(n = 32): Uint8Array {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

export const fernet = () => "gAAAAAB" + b64u(zufall(60));

export async function codeAnlegen(code = "BETA-" + b64u(zufall(9)).toUpperCase()): Promise<string> {
  const norm = code.replace(/\s+/g, "").toUpperCase();
  const h = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(norm))))
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  await env.DB.prepare("INSERT INTO codes (code_hash, notiz, erstellt) VALUES (?, 'test', ?)").bind(h, Date.now()).run();
  return code;
}

export interface Konto {
  mail: string;
  anmelde_schluessel: string;
  notfall_beweis: string;
  verpackt_passwort: string;
  verpackt_notfall: string;
  salz: string;
  code: string;
}

let kontoZaehler = 0;

export async function kontoAnlegen(mail?: string): Promise<Konto> {
  kontoZaehler += 1;
  const k: Konto = {
    mail: mail ?? `nutzer${kontoZaehler}-${b64u(zufall(4)).toLowerCase()}@example.org`,
    anmelde_schluessel: b64u(zufall()),
    notfall_beweis: b64u(zufall()),
    verpackt_passwort: fernet(),
    verpackt_notfall: fernet(),
    salz: b64u(zufall(16)),
    code: await codeAnlegen(),
  };
  const r = await rufen("POST", "/v1/konto", {
    ip: neueIp(),
    json: {
      mail: k.mail, code: k.code, salz: k.salz, kdf: { name: "argon2id", t: 3, m: 65536, p: 4 },
      anmelde_schluessel: k.anmelde_schluessel, verpackt_passwort: k.verpackt_passwort,
      verpackt_notfall: k.verpackt_notfall, notfall_beweis: k.notfall_beweis,
    },
  });
  expect(r.status, await r.clone().text()).toBe(201);
  return k;
}

export async function anmelden(k: Konto, knoten = "laptop"): Promise<string> {
  const r = await rufen("POST", "/v1/sitzung", {
    ip: neueIp(),
    json: { mail: k.mail, anmelde_schluessel: k.anmelde_schluessel, knoten },
  });
  expect(r.status, await r.clone().text()).toBe(200);
  return (await jsonVon(r)).token as string;
}

/** Opaque bytes from the Mitte as text (test content is ASCII). */
export async function bytesText(r: Response): Promise<string> {
  return new TextDecoder().decode(await r.arrayBuffer());
}
