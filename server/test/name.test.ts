// Account names: the cases are shared with the device (tests/daten/konto_namen.json).
import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import faelleRoh from "../../tests/daten/konto_namen.json?raw";
import { routeVon } from "../src/index";
import { KEINE_MAIL, RESERVIERT, RESERVIERT_ANFANG, namePruefen, reserviert } from "../src/name";
import { betreiber } from "../src/nutzung";
import { anmelden, b64u, codeAnlegen, fernet, jsonVon, kontoAnlegen, neueIp, rufen, zufall } from "./hilfe";

const F = JSON.parse(faelleRoh) as {
  reserviert: string[]; reserviert_anfang: string[]; gut: [string, string][];
  reserviert_faelle: string[]; schlecht: string[]; mail: string[];
};
const KDF = { name: "argon2id", t: 3, m: 65536, p: 4 };

async function anlegen(name: string): Promise<Response> {
  return rufen("POST", "/v1/konto", { json: {
    name, code: await codeAnlegen(), salz: b64u(zufall(16)), kdf: KDF, anmelde_schluessel: b64u(zufall()),
    verpackt_passwort: fernet(), verpackt_notfall: fernet(), notfall_beweis: b64u(zufall()),
  } });
}

describe("Namensregeln", () => {
  it("Listen wie in der gemeinsamen Datei", () => {
    expect([...RESERVIERT].sort()).toEqual([...F.reserviert].sort());
    expect(RESERVIERT_ANFANG).toEqual(F.reserviert_anfang);
  });

  it("gute, schlechte und reservierte Fälle", () => {
    for (const [ein, aus] of F.gut) expect(namePruefen(ein)).toBe(aus);
    for (const s of F.schlecht) expect(() => namePruefen(s), s).toThrow();
    for (const r of [...F.reserviert, ...F.reserviert_faelle]) expect(reserviert(namePruefen(r)), r).toBe(true);
    for (const [, aus] of F.gut) expect(reserviert(aus)).toBe(false);
  });

  it("'@' → freundlicher Satz: keine Mail nötig", async () => {
    for (const m of F.mail) {
      const r = await anlegen(m);
      expect(r.status).toBe(400);
      expect((await jsonVon(r)).text).toBe(KEINE_MAIL);
    }
    const v = await jsonVon(await rufen("POST", "/v1/vorab", { json: { name: "jemand@example.org" } }));
    expect(v.text).toMatch(/No email needed/);
  });

  it("reservierte Namen nur beim Anlegen abgelehnt", async () => {
    const r = await anlegen("Zentrale-Team");
    expect(r.status).toBe(400);
    expect((await jsonVon(r)).text).toMatch(/reserved/);
    // Beim Anmelden/vorab sind sie nur unbekannte Namen (feste erfundene Werte).
    expect((await rufen("POST", "/v1/vorab", { json: { name: "admin" } })).status).toBe(200);
  });

  it("eine Mail-Spalte gibt es nicht mehr", async () => {
    const spalten = await env.DB.prepare("SELECT name FROM pragma_table_info('konten')").all<{ name: string }>();
    const namen = spalten.results.map((s) => s.name);
    expect(namen).toContain("name");
    expect(namen).not.toContain("mail");
  });
});

describe("Drossel ohne IP und Name im Klartext", () => {
  it("Schlüssel sind HMAC mit Tagesschlüssel, nicht SHA-256", async () => {
    const ip = "192.0.2.199";
    const k = await kontoAnlegen();
    await rufen("POST", "/v1/sitzung", { ip, json: { name: k.name, anmelde_schluessel: b64u(zufall()), knoten: "laptop" } });
    const zeilen = (await env.DB.prepare("SELECT schluessel FROM drossel").all<{ schluessel: string }>()).results
      .map((z) => z.schluessel);
    const sha = async (s: string) => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s))))
      .map((b) => b.toString(16).padStart(2, "0")).join("");
    const alles = zeilen.join("\n");
    expect(alles).not.toContain(ip);
    expect(alles).not.toContain(k.name);
    expect(alles).not.toContain(await sha(ip));
    expect(alles).not.toContain(await sha(k.name));
    expect(zeilen.filter((z) => /^sitzung:ip:[0-9a-f]{64}$/.test(z)).length).toBeGreaterThan(0);
    expect(zeilen.filter((z) => /^sitzung:name:[0-9a-f]{64}$/.test(z)).length).toBeGreaterThan(0);
  });

  it("dieselbe IP zählt am selben Tag zusammen", async () => {
    const ip = "192.0.2.201";
    for (let i = 0; i < 5; i++) {
      await rufen("POST", "/v1/sitzung", { ip, json: { name: `tag${i}`, anmelde_schluessel: b64u(zufall()), knoten: "laptop" } });
    }
    const k = await kontoAnlegen();
    const r = await rufen("POST", "/v1/sitzung", { ip, json: { name: k.name, anmelde_schluessel: k.anmelde_schluessel, knoten: "laptop" } });
    expect(r.status).toBe(429);
    expect(await anmelden(k)).toBeTruthy();         // andere IP: geht
  });

  it("ohne VORAB_GEHEIMNIS kein Login (503), nie ungeschützte Schlüssel", async () => {
    const { anmelden: route } = await import("../src/konto");
    const ohne = { ...env, VORAB_GEHEIMNIS: "" } as Env;
    const a = new Request("https://cloud.test/v1/sitzung", {
      method: "POST", headers: { "Content-Type": "application/json", "CF-Connecting-IP": neueIp() },
      body: JSON.stringify({ name: "jemand", anmelde_schluessel: b64u(zufall()), knoten: "laptop" }),
    });
    await expect(route(ohne, a, Date.now())).rejects.toMatchObject({ status: 503 });
  });
});

describe("Betreiber nach Name, Logs ohne Pfad", () => {
  it("BETREIBER_NAMEN: Komma-Liste, Schreibweise egal, leer = niemand", () => {
    const e = (v: string) => ({ ...env, BETREIBER_NAMEN: v }) as Env;
    expect(betreiber(e(" Sasha , anna"), "sasha")).toBe(true);
    expect(betreiber(e("sasha"), "SASHA ")).toBe(true);
    expect(betreiber(e("sasha"), "sasha2")).toBe(false);
    expect(betreiber(e(""), "sasha")).toBe(false);
    expect(betreiber(e(","), "")).toBe(false);
  });

  it("Logs nennen das Muster, nie Gerätenamen", () => {
    expect(routeVon("/v1/knoten/sashas-macbook")).toBe("/v1/knoten/{name}");
    expect(routeVon("/v1/mitte/datei/d/abc.enc")).toBe("/v1/mitte/datei/{name}");
    expect(routeVon("/gibts/nicht")).toBe("(unbekannt)");
  });
});
