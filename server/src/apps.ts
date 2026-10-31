// Our own app packages (memory/hub/app_delivery_plan.md step 4b).
//
//   GET /v1/apps/{name}                     session → {name, versions: [{version, sha256, size}]} newest first
//   GET /v1/apps/{name}/{version}.tar.gz    session → the package
//
// R2: apps/<name>/index.json ({name, versions}) + apps/<name>/<version>.tar.gz,
// written by scripts/app_hochladen.mjs (package FIRST, index LAST, so the
// index never names a missing file). Packages are built by
// scripts/app_paket_bauen.py.
//
// Access (Sasha 2026-10-31, plan Q2): while nothing is public, only a full
// login session fetches our packages — no invite code. Foreign sources need
// no account at all; ours open without one on the day ZENTRALE goes public.

import { HttpFehler, json, roh } from "./hilfe";
import { angemeldet } from "./konto";

export const APP_NAME = /^[a-z][a-z0-9_-]{0,31}$/;
export const APP_VERSION = /^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$/;
const SHA256 = /^[0-9a-f]{64}$/;

interface Version {
  version: string;
  sha256: string;
  size: number;
}

const NOT_FOUND = () => new HttpFehler(404, "nicht_gefunden", "There is no such app package.");

async function index(env: Env, name: string): Promise<Version[]> {
  const o = await env.R2.get(`apps/${name}/index.json`);
  if (!o) throw NOT_FOUND();
  let d: { versions?: unknown };
  try {
    d = JSON.parse(await o.text());
  } catch {
    throw NOT_FOUND();
  }
  const versions = Array.isArray(d.versions) ? d.versions : [];
  return versions.filter((v): v is Version =>
    !!v && typeof v.version === "string" && APP_VERSION.test(v.version)
    && typeof v.sha256 === "string" && SHA256.test(v.sha256)
    && Number.isInteger(v.size) && v.size > 0);
}

export async function appInfo(env: Env, anfrage: Request, jetzt: number, name: string): Promise<Response> {
  if (!APP_NAME.test(name)) throw NOT_FOUND();
  await angemeldet(env.DB, anfrage, jetzt);
  const versions = await index(env, name);
  if (!versions.length) throw NOT_FOUND();
  return json({ name, versions: versions.map(({ version, sha256, size }) => ({ version, sha256, size })) });
}

export async function appFile(env: Env, anfrage: Request, jetzt: number, name: string, version: string): Promise<Response> {
  if (!APP_NAME.test(name) || !APP_VERSION.test(version)) throw NOT_FOUND();
  await angemeldet(env.DB, anfrage, jetzt);
  if (!(await index(env, name)).some((v) => v.version === version)) throw NOT_FOUND();
  const o = await env.R2.get(`apps/${name}/${version}.tar.gz`);
  if (!o) throw NOT_FOUND();
  return roh(o.body, "application/gzip", {
    "Content-Length": String(o.size),
    "Content-Disposition": `attachment; filename="${name}-${version}.tar.gz"`,
  });
}
