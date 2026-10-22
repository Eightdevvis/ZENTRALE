// Devices and ownership of an account.
//
//   PUT /v1/knoten/{name}   the device description (plain metadata, no content);
//                           a session may only write its own device (the name
//                           it logged in with) — "only the device writes its file"
//   GET /v1/knoten          {knoten: [description, …]}
//   GET /v1/besitz          {besitz: string|null, aktualisiert: iso|null}
//   PUT /v1/besitz          {besitz: string}  (schema.org ItemList, encrypted on
//                           the device into one opaque string, e.g. a Fernet token)

import { HttpFehler, KB, json, jsonLesen, ungueltig } from "./hilfe";
import { KNOTEN_NAME, type Sitzung } from "./konto";

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
  return json({ knoten: r.results.map((z) => JSON.parse(z.beschreibung)) });
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
