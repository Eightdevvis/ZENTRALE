// Devices and ownership of an account.
//
//   PUT /v1/knoten/{name}   the device description (plain metadata, no content);
//                           a session may only write its own device (the name
//                           it logged in with) — "only the device writes its file"
//   GET /v1/knoten          {knoten: [description, …]}; a device on an insecure
//                           release carries `insecure: {since, link, reason}` (src/release.ts)
//   DELETE /v1/knoten/{name} remove a device (build step 8): its sessions turn
//                           into "removed" ones (next call → 401 device_removed)
//                           and its description becomes a tombstone
//                           {…, removed, removed_by}. Any session of the account
//                           may do it, also for itself (`zentrale leave`).
//   GET /v1/besitz          {besitz: string|null, aktualisiert: iso|null}
//   PUT /v1/besitz          {besitz: string}  (schema.org ItemList, encrypted on
//                           the device into one opaque string, e.g. a Fernet token)

import { HttpFehler, KB, json, jsonLesen, ungueltig } from "./hilfe";
import { KNOTEN_NAME, type Sitzung } from "./konto";
import { insecureField, insecureVersions } from "./release";

const MAX_KNOTEN = 16 * KB;
const MAX_BESITZ = 1024 * KB;
const MAX_KNOTEN_JE_KONTO = 100;

export async function knotenSetzen(env: Env, anfrage: Request, s: Sitzung, name: string, jetzt: number): Promise<Response> {
  if (!KNOTEN_NAME.test(name)) throw ungueltig("The device name is not valid.");
  if (name !== s.knoten) {
    throw new HttpFehler(403, "fremder_knoten", "A device may only write its own description.");
  }
  const d = await jsonLesen(anfrage, MAX_KNOTEN);
  if (d.name !== undefined && d.name !== name) throw ungueltig("'name' in the body does not match the address.");
  const anzahl = await env.DB.prepare("SELECT COUNT(*) AS n FROM knoten WHERE konto_id = ? AND name != ?")
    .bind(s.konto_id, name).first<{ n: number }>();
  if ((anzahl?.n ?? 0) >= MAX_KNOTEN_JE_KONTO) throw ungueltig("Too many devices on this account.");
  await env.DB
    .prepare(
      `INSERT INTO knoten (konto_id, name, beschreibung, aktualisiert) VALUES (?, ?, ?, ?)
       ON CONFLICT(konto_id, name) DO UPDATE SET beschreibung = excluded.beschreibung, aktualisiert = excluded.aktualisiert`,
    )
    .bind(s.konto_id, name, JSON.stringify({ ...d, name }), jetzt)
    .run();
  return json({ name, aktualisiert: new Date(jetzt).toISOString() });
}

export async function knotenListe(env: Env, s: Sitzung): Promise<Response> {
  const r = await env.DB.prepare("SELECT beschreibung FROM knoten WHERE konto_id = ? ORDER BY name")
    .bind(s.konto_id).all<{ beschreibung: string }>();
  const knoten = r.results.map((z) => JSON.parse(z.beschreibung) as Record<string, unknown>);
  // Computed on every read, never stored: marking or unmarking a release
  // shows on every device at once, also on devices that have not synced since.
  const insecure = await insecureVersions(env.DB, knoten.map((k) => k.programm as string));
  for (const k of knoten) {
    delete k.insecure;
    const i = insecure.get(k.programm as string);
    if (i) k.insecure = insecureField(i);
  }
  return json({ knoten });
}

export async function knotenEntfernen(env: Env, s: Sitzung, name: string, jetzt: number): Promise<Response> {
  if (!KNOTEN_NAME.test(name)) throw ungueltig("The device name is not valid.");
  const alt = await env.DB.prepare("SELECT beschreibung FROM knoten WHERE konto_id = ? AND name = ?")
    .bind(s.konto_id, name).first<{ beschreibung: string }>();
  const sitzungen = await env.DB
    .prepare("SELECT COUNT(*) AS n FROM sitzungen WHERE konto_id = ? AND knoten = ? AND art = 'normal'")
    .bind(s.konto_id, name).first<{ n: number }>();
  if (!alt && !(sitzungen?.n)) {
    throw new HttpFehler(404, "unknown_device", "There is no device with this name on your account.");
  }
  const removed = new Date(jetzt).toISOString();
  const grabstein = { ...(alt ? JSON.parse(alt.beschreibung) : {}), name, removed, removed_by: s.knoten };
  // One transaction: the sessions turn into "removed" ones (kept until they
  // expire, so the device hears why — 401 device_removed), the tombstone is written.
  const r = await env.DB.batch([
    env.DB.prepare("UPDATE sitzungen SET art = 'removed' WHERE konto_id = ? AND knoten = ? AND art = 'normal'")
      .bind(s.konto_id, name),
    env.DB.prepare(
      `INSERT INTO knoten (konto_id, name, beschreibung, aktualisiert) VALUES (?, ?, ?, ?)
       ON CONFLICT(konto_id, name) DO UPDATE SET beschreibung = excluded.beschreibung, aktualisiert = excluded.aktualisiert`,
    ).bind(s.konto_id, name, JSON.stringify(grabstein), jetzt),
  ]);
  return json({ name, removed, sessions_ended: r[0].meta.changes });
}

export async function besitzHolen(env: Env, s: Sitzung): Promise<Response> {
  const r = await env.DB.prepare("SELECT daten, aktualisiert FROM besitz WHERE konto_id = ?")
    .bind(s.konto_id).first<{ daten: string; aktualisiert: number }>();
  return json({
    besitz: r?.daten ?? null,
    aktualisiert: r ? new Date(r.aktualisiert).toISOString() : null,
  });
}

export async function besitzSetzen(env: Env, anfrage: Request, s: Sitzung, jetzt: number): Promise<Response> {
  const d = await jsonLesen(anfrage, MAX_BESITZ);
  if (typeof d.besitz !== "string" || d.besitz === "") throw ungueltig("'besitz' must be a non-empty string.");
  await env.DB
    .prepare(
      `INSERT INTO besitz (konto_id, daten, aktualisiert) VALUES (?, ?, ?)
       ON CONFLICT(konto_id) DO UPDATE SET daten = excluded.daten, aktualisiert = excluded.aktualisiert`,
    )
    .bind(s.konto_id, d.besitz, jetzt)
    .run();
  return json({ aktualisiert: new Date(jetzt).toISOString() });
}
