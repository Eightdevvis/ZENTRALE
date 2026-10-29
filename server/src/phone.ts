// Self-update of the phone app (memory/system/zen_mobile.md "Self-update").
//
//   GET /v1/phone/release                    session → the current release manifest
//   GET /v1/phone/release/{code}.apk         session → the APK of that version code
//   PUT /v1/phone/release/{code}.apk?sha256= operator only; raw APK, streamed to R2
//   PUT /v1/phone/release                    operator only; publishes the manifest
//                                            (keeps the previous APK, deletes older ones)
//
// R2: phone/release.json (the manifest) + phone/apk/<version_code>.apk.
//
// Trust: only accounts in BETREIBER_NAMEN can write (scripts/publish_phone_app.py
// with Sasha's session). The app reads the manifest only from the cloud it is
// logged in to, with its own session, and never follows a URL from the
// manifest — the APK address is built from the version code. Integrity: R2
// checks the SHA-256 on upload; the manifest may only name an APK whose stored
// checksum and size match; the app checks the SHA-256 again before handing the
// file to Android, and Android itself refuses an update signed with another key.

import { HttpFehler, json, jsonLesen, roh, ungueltig } from "./hilfe";
import { betreiber, speicherPruefen } from "./nutzung";
import type { Sitzung } from "./konto";

/** Cloudflare Workers accept request bodies up to 100 MB on the Free plan. */
export const MAX_APK = 96 * 1024 * 1024;
export const MAX_NOTES = 2000;
export const MANIFEST_KEY = "phone/release.json";
export const apkKey = (code: number) => `phone/apk/${code}.apk`;

const SHA = /^[0-9a-f]{64}$/;
const VERSION_NAME = /^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$/;
const CODE = /^[1-9][0-9]{0,9}$/;
/** Android's versionCode is at most 2100000000. */
const MAX_CODE = 2_100_000_000;

export interface Manifest {
  version: string;
  version_code: number;
  sha256: string;
  size: number;
  notes: string;
  published_at: string;
}

function versionCode(text: string): number {
  if (!CODE.test(text) || Number(text) > MAX_CODE) {
    throw new HttpFehler(404, "nicht_gefunden", "There is no such release.");
  }
  return Number(text);
}

async function operatorOnly(env: Env, s: Sitzung): Promise<void> {
  const k = await env.DB.prepare("SELECT name FROM konten WHERE id = ?").bind(s.konto_id).first<{ name: string }>();
  if (!k || !betreiber(env, k.name)) {
    throw new HttpFehler(403, "operator_only", "Only the operator of this cloud can publish app releases.");
  }
}

async function current(env: Env): Promise<Manifest | null> {
  const o = await env.R2.get(MANIFEST_KEY);
  if (!o) return null;
  try {
    return JSON.parse(await o.text()) as Manifest;
  } catch {
    return null;
  }
}

export async function releaseGet(env: Env): Promise<Response> {
  const m = await current(env);
  if (!m) throw new HttpFehler(404, "no_release", "No phone app release has been published yet.");
  return json(m);
}

export async function apkGet(env: Env, codeText: string): Promise<Response> {
  const o = await env.R2.get(apkKey(versionCode(codeText)));
  if (!o) throw new HttpFehler(404, "nicht_gefunden", "There is no such release.");
  return roh(o.body, "application/vnd.android.package-archive", {
    "Content-Length": String(o.size),
    "Content-Disposition": `attachment; filename="zentrale-${codeText}.apk"`,
  });
}

export async function apkPut(env: Env, anfrage: Request, s: Sitzung, codeText: string): Promise<Response> {
  await operatorOnly(env, s);
  const code = versionCode(codeText);
  const sha = new URL(anfrage.url).searchParams.get("sha256") ?? "";
  if (!SHA.test(sha)) throw ungueltig("Send the APK's lower-case hex SHA-256 as ?sha256=.");
  const laenge = anfrage.headers.get("Content-Length");
  if (laenge === null || !/^\d+$/.test(laenge)) {
    throw new HttpFehler(411, "laenge_fehlt", "Send the APK with a Content-Length header.");
  }
  const size = Number(laenge);
  if (size === 0) throw ungueltig("The APK is empty.");
  if (size > MAX_APK) throw new HttpFehler(413, "zu_gross", `An APK may be at most ${MAX_APK} bytes.`);
  await speicherPruefen(env, size);
  // Streamed straight to R2; R2 checks the SHA-256 (nothing stored on mismatch).
  try {
    await env.R2.put(apkKey(code), anfrage.body ?? new Uint8Array(0), { sha256: sha });
  } catch (e) {
    if (/sha-?256|checksum|digest/i.test(String(e))) {
      throw new HttpFehler(400, "pruefsumme", "The APK does not match its SHA-256.");
    }
    throw e;
  }
  return new Response(null, { status: 204 });
}

function hexOf(b: ArrayBuffer | undefined): string {
  return b ? Array.from(new Uint8Array(b), (x) => x.toString(16).padStart(2, "0")).join("") : "";
}

export async function releasePut(env: Env, anfrage: Request, s: Sitzung, jetzt: number): Promise<Response> {
  await operatorOnly(env, s);
  const d = await jsonLesen(anfrage, 16 * 1024);
  const version = d.version;
  if (typeof version !== "string" || !VERSION_NAME.test(version)) throw ungueltig("'version' is not a valid version name.");
  const code = d.version_code;
  if (typeof code !== "number" || !Number.isInteger(code) || code < 1 || code > MAX_CODE) {
    throw ungueltig("'version_code' must be a positive whole number.");
  }
  const sha = d.sha256;
  if (typeof sha !== "string" || !SHA.test(sha)) throw ungueltig("'sha256' must be a lower-case hex SHA-256.");
  const size = d.size;
  if (typeof size !== "number" || !Number.isInteger(size) || size < 1 || size > MAX_APK) {
    throw ungueltig("'size' must be the APK size in bytes.");
  }
  const notes = d.notes ?? "";
  if (typeof notes !== "string" || notes.length > MAX_NOTES) throw ungueltig(`'notes' must be text of at most ${MAX_NOTES} characters.`);

  const alt = await current(env);
  if (alt && code <= alt.version_code) {
    throw new HttpFehler(409, "version_not_newer",
      `The version code must be higher than the published one (${alt.version_code}).`,
      {}, { current_version_code: alt.version_code });
  }
  const apk = await env.R2.head(apkKey(code));
  if (!apk) throw new HttpFehler(409, "apk_missing", "Upload the APK for this version code first.");
  if (apk.size !== size || hexOf(apk.checksums.sha256) !== sha) {
    throw new HttpFehler(409, "apk_mismatch", "The uploaded APK does not match 'size' and 'sha256'.");
  }

  const m: Manifest = {
    version, version_code: code, sha256: sha, size, notes: notes.trim(),
    published_at: new Date(jetzt).toISOString(),
  };
  await env.R2.put(MANIFEST_KEY, JSON.stringify(m), { httpMetadata: { contentType: "application/json" } });
  // Keep the new APK, the one before it (a phone may still be downloading it)
  // and any newer upload not published yet; older ones go.
  const grenze = alt?.version_code ?? code;
  const liste = await env.R2.list({ prefix: "phone/apk/" });
  const weg = liste.objects.map((o) => o.key).filter((k) => {
    const c = Number(/^phone\/apk\/(\d+)\.apk$/.exec(k)?.[1] ?? NaN);
    return Number.isFinite(c) && c < grenze;
  });
  if (weg.length) await env.R2.delete(weg);
  return json(m);
}
