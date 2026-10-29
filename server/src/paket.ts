// Release packages and the installer.
//
//   GET /install.sh                     public; R2 key "install.sh"
//   GET /v1/paket                       ?code= or Bearer → {version, sha256, groesse}
//   GET /v1/paket/{version}.tar.gz      ?code= or Bearer → the package
//
// R2: pakete/neueste.json ({version, sha256, groesse}) + pakete/<version>.tar.gz.
// A download does NOT use up an invite code (only account creation does);
// a blocked code (gesperrt = 1) no longer works.

import { HttpFehler, json, roh } from "./hilfe";
import { sha256Hex } from "./krypto";
import { sitzungFinden } from "./konto";

const PLATZHALTER = `#!/bin/sh
# ZENTRALE installer — not uploaded yet.
echo "The ZENTRALE installer has not been published yet. Please try again later." >&2
exit 1
`;

export const VERSION = /^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$/;

/** Invite codes are compared case-insensitively, without spaces. */
export function codeNormal(code: string): string {
  return code.replace(/\s+/g, "").toUpperCase();
}

export async function codeHash(code: string): Promise<string> {
  return sha256Hex(codeNormal(code));
}

export async function installSh(env: Env): Promise<Response> {
  const o = await env.R2.get("install.sh");
  const kopf = { "Cache-Control": "no-cache" };
  if (!o) return roh(PLATZHALTER, "text/plain; charset=utf-8", kopf);
  return roh(o.body, "text/plain; charset=utf-8", { ...kopf, ETag: o.httpEtag });
}

/** Allowed with a valid (not blocked) invite code or a full session. */
async function zugang(env: Env, anfrage: Request, jetzt: number): Promise<void> {
  const code = new URL(anfrage.url).searchParams.get("code");
  if (code && code.length <= 128) {
    const ok = await env.DB.prepare("SELECT 1 AS ok FROM codes WHERE code_hash = ? AND gesperrt = 0")
      .bind(await codeHash(code)).first();
    if (ok) return;
    throw new HttpFehler(403, "code_ungueltig", "This invite code is not valid.");
  }
  const s = await sitzungFinden(env.DB, anfrage, jetzt);
  if (s && s.art === "normal") return;
  throw new HttpFehler(401, "code_noetig", "An invite code (?code=) or a login is required to download ZENTRALE.");
}

const KEIN_PAKET = () => new HttpFehler(404, "kein_paket", "No package has been published yet.");

export async function paketInfo(env: Env, anfrage: Request, jetzt: number): Promise<Response> {
  await zugang(env, anfrage, jetzt);
  const o = await env.R2.get("pakete/neueste.json");
  if (!o) throw KEIN_PAKET();
  let d: { version?: unknown; sha256?: unknown; groesse?: unknown };
  try {
    d = JSON.parse(await o.text());
  } catch {
    throw KEIN_PAKET();
  }
  if (typeof d.version !== "string" || !VERSION.test(d.version)) throw KEIN_PAKET();
  return json({ version: d.version, sha256: d.sha256, groesse: d.groesse });
}

export async function paketDatei(env: Env, anfrage: Request, jetzt: number, version: string): Promise<Response> {
  if (!VERSION.test(version)) throw new HttpFehler(404, "nicht_gefunden", "There is no such package.");
  await zugang(env, anfrage, jetzt);
  const o = await env.R2.get(`pakete/${version}.tar.gz`);
  if (!o) throw new HttpFehler(404, "nicht_gefunden", "There is no such package.");
  return roh(o.body, "application/gzip", {
    "Content-Length": String(o.size),
    "Content-Disposition": `attachment; filename="zentrale-${version}.tar.gz"`,
  });
}
