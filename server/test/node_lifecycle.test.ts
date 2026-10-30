// Build steps 7 and 8 (memory/hub/building_kit_plan.md): insecure releases
// keep syncing with `Deprecation` + `Link` (never `Sunset`); removing a
// device ends its sessions with 401 device_removed and leaves a tombstone;
// changing the account key swaps wraps and Mitte in one transaction.
import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, b64u, blobHoch, bytesText, fernet, jsonVon, kontoAnlegen, neueIp, rufen, shaHex, zufall } from "./hilfe";

const b64 = (s: string) => btoa(s);
const description = (name: string, programm: string) => ({ name, sorte: "vollknoten", programm });

async function markInsecure(version: string, since = Date.UTC(2026, 9, 30)) {
  await env.DB.prepare("INSERT OR REPLACE INTO insecure_releases (version, since, link, reason) VALUES (?, ?, ?, ?)")
    .bind(version, since, "https://example.test/advisory", "Broken crypto.").run();
}

describe("insecure release", () => {
  it("marked → Deprecation + Link on every answer, sync keeps working, never Sunset", async () => {
    await markInsecure("39");
    const k = await kontoAnlegen();
    const t = await anmelden(k, "mini");
    const old = { "Zentrale-Release": "39" };

    const r = await rufen("POST", "/v1/mitte/stand", { token: t, kopf: old, json: { basis: null, schreiben: { "inhalt.enc": b64("x") } } });
    expect(r.status).toBe(200);
    expect(r.headers.get("Deprecation")).toBe(`@${Date.UTC(2026, 9, 30) / 1000}`);
    expect(r.headers.get("Link")).toBe('<https://example.test/advisory>; rel="deprecation"; type="text/html"');
    expect(r.headers.get("Sunset")).toBeNull();
    const h = await rufen("GET", "/v1/mitte", { token: t, kopf: old });
    expect(h.status).toBe(200);
    expect(h.headers.get("Deprecation")).not.toBeNull();
    // Errors carry it too (the device still hears it).
    expect((await rufen("GET", "/v1/mitte", { kopf: old })).headers.get("Deprecation")).not.toBeNull();

    // Another release, or none told: nothing.
    for (const kopf of [{ "Zentrale-Release": "40" }, {}] as Record<string, string>[]) {
      const ok = await rufen("GET", "/v1/mitte", { token: t, kopf });
      expect(ok.status).toBe(200);
      expect(ok.headers.get("Deprecation")).toBeNull();
      expect(ok.headers.get("Link")).toBeNull();
    }
  });

  it("GET /v1/knoten flags devices on an insecure release (computed, not stored)", async () => {
    await markInsecure("38");
    const k = await kontoAnlegen();
    const mini = await anmelden(k, "mini");
    const laptop = await anmelden(k, "laptop");
    await rufen("PUT", "/v1/knoten/mini", { token: mini, json: { ...description("mini", "38"), insecure: "forged" } });
    await rufen("PUT", "/v1/knoten/laptop", { token: laptop, json: description("laptop", "45") });
    const list = (await jsonVon(await rufen("GET", "/v1/knoten", { token: laptop }))).knoten;
    expect(list[0].insecure).toBeUndefined();
    expect(list[1].insecure).toEqual({ since: "2026-10-30T00:00:00.000Z", link: "https://example.test/advisory", reason: "Broken crypto." });
    await env.DB.prepare("DELETE FROM insecure_releases WHERE version = '38'").run();
    const again = (await jsonVon(await rufen("GET", "/v1/knoten", { token: laptop }))).knoten;
    expect(again[1].insecure).toBeUndefined();
  });
});

describe("remove a device", () => {
  it("ends its sessions (401 device_removed), tombstone visible, others keep working, login adds it back", async () => {
    const k = await kontoAnlegen();
    const laptop = await anmelden(k, "laptop");
    const mini = await anmelden(k, "mini");
    const mini2 = await anmelden(k, "mini");
    await rufen("PUT", "/v1/knoten/mini", { token: mini, json: description("mini", "41") });

    const r = await rufen("DELETE", "/v1/knoten/mini", { token: laptop });
    expect(r.status).toBe(200);
    const d = await jsonVon(r);
    expect(d.name).toBe("mini");
    expect(d.sessions_ended).toBe(2);

    for (const t of [mini, mini2]) {
      const weg = await rufen("GET", "/v1/mitte", { token: t });
      expect(weg.status).toBe(401);
      expect((await jsonVon(weg)).fehler).toBe("device_removed");
    }
    // Not even a password change works with it.
    expect((await jsonVon(await rufen("PUT", "/v1/konto/passwort", { token: mini, json: {} }))).fehler).toBe("device_removed");
    expect((await rufen("GET", "/v1/mitte", { token: laptop })).status).toBe(200);

    const list = (await jsonVon(await rufen("GET", "/v1/knoten", { token: laptop }))).knoten;
    const tomb = list.find((x: { name: string }) => x.name === "mini");
    expect(tomb.removed).toMatch(/^20\d\d-/);
    expect(tomb.removed_by).toBe("laptop");
    expect(tomb.programm).toBe("41");

    // Unknown device → 404; foreign account never sees it.
    expect((await jsonVon(await rufen("DELETE", "/v1/knoten/toaster", { token: laptop }))).fehler).toBe("unknown_device");
    const other = await anmelden(await kontoAnlegen(), "mini");
    expect((await rufen("GET", "/v1/mitte", { token: other })).status).toBe(200);

    // Logging in again adds it back: the new description replaces the tombstone.
    const back = await anmelden(k, "mini");
    await rufen("PUT", "/v1/knoten/mini", { token: back, json: description("mini", "42") });
    const after = (await jsonVon(await rufen("GET", "/v1/knoten", { token: laptop }))).knoten;
    expect(after.find((x: { name: string }) => x.name === "mini").removed).toBeUndefined();
  });

  it("a device may remove itself (zentrale leave)", async () => {
    const k = await kontoAnlegen();
    const mini = await anmelden(k, "mini");
    expect((await rufen("DELETE", "/v1/knoten/mini", { token: mini })).status).toBe(200);
    expect((await jsonVon(await rufen("GET", "/v1/knoten", { token: mini }))).fehler).toBe("device_removed");
  });
});

describe("change the account key", () => {
  async function body(k: { anmelde_schluessel: string }, basis: string | null, verweise: Record<string, string>, loeschen: string[]) {
    return {
      salz: b64u(zufall(16)), kdf: { name: "argon2id", t: 3, m: 65536, p: 4 },
      anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet(),
      verpackt_notfall: fernet(), notfall_beweis: b64u(zufall()),
      altes_anmelde_schluessel: k.anmelde_schluessel,
      stand: { basis, verweise, loeschen },
    };
  }

  it("swaps wraps and Mitte at once, ends all other sessions, old login and emergency key stop working", async () => {
    const k = await kontoAnlegen();
    const laptop = await anmelden(k, "laptop");
    const pc = await anmelden(k, "pc");
    const s1 = await jsonVon(await rufen("POST", "/v1/mitte/stand", { token: laptop, json: { basis: null, schreiben: { "inhalt.enc": b64("old"), "d/aa.enc": b64("A") } } }));
    const neu = new TextEncoder().encode("new-inhalt");
    const neuA = new TextEncoder().encode("new-A");
    await blobHoch(laptop, neu);
    await blobHoch(laptop, neuA);
    const b = await body(k, s1.kennung, { "inhalt.enc": await shaHex(neu), "d/bb.enc": await shaHex(neuA) }, ["d/aa.enc"]);

    // Wrong password → 401, nothing changed.
    const falsch = await rufen("PUT", "/v1/konto/schluessel", { token: laptop, ip: neueIp(), json: { ...b, altes_anmelde_schluessel: b64u(zufall()) } });
    expect(falsch.status).toBe(401);
    expect((await jsonVon(await rufen("GET", "/v1/mitte", { token: pc }))).kennung).toBe(s1.kennung);

    const r = await rufen("PUT", "/v1/konto/schluessel", { token: laptop, ip: neueIp(), json: b });
    expect(r.status, await r.clone().text()).toBe(200);
    const kennung = (await jsonVon(r)).kennung;
    const m = await jsonVon(await rufen("GET", "/v1/mitte", { token: laptop }));
    expect(m).toEqual({ kennung, namen: ["d/bb.enc", "inhalt.enc"] });
    expect(await bytesText(await rufen("GET", "/v1/mitte/datei/inhalt.enc", { token: laptop }))).toBe("new-inhalt");
    expect((await rufen("GET", "/v1/mitte", { token: pc })).status).toBe(401);

    // New password logs in and gets the new wrap; the old one does not.
    const alt = await rufen("POST", "/v1/sitzung", { ip: neueIp(), json: { name: k.name, anmelde_schluessel: k.anmelde_schluessel, knoten: "pc" } });
    expect(alt.status).toBe(401);
    const login = await rufen("POST", "/v1/sitzung", { ip: neueIp(), json: { name: k.name, anmelde_schluessel: b.anmelde_schluessel, knoten: "pc" } });
    expect((await jsonVon(login)).verpackt_passwort).toBe(b.verpackt_passwort);
    expect((await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { name: k.name, notfall_beweis: k.notfall_beweis } })).status).toBe(401);
    const nf = await jsonVon(await rufen("POST", "/v1/notfall", { ip: neueIp(), json: { name: k.name, notfall_beweis: b.notfall_beweis } }));
    expect(nf.verpackt_notfall).toBe(b.verpackt_notfall);
  });

  it("someone synced in between → 409 and nothing changed", async () => {
    const k = await kontoAnlegen();
    const laptop = await anmelden(k, "laptop");
    const s1 = await jsonVon(await rufen("POST", "/v1/mitte/stand", { token: laptop, json: { basis: null, schreiben: { "inhalt.enc": b64("1") } } }));
    await rufen("POST", "/v1/mitte/stand", { token: laptop, json: { basis: s1.kennung, schreiben: { "inhalt.enc": b64("2") } } });
    const r = await rufen("PUT", "/v1/konto/schluessel", { token: laptop, ip: neueIp(), json: await body(k, s1.kennung, {}, []) });
    expect(r.status).toBe(409);
    const login = await rufen("POST", "/v1/sitzung", { ip: neueIp(), json: { name: k.name, anmelde_schluessel: k.anmelde_schluessel, knoten: "pc" } });
    expect(login.status).toBe(200);
    expect((await jsonVon(login)).verpackt_passwort).toBe(k.verpackt_passwort);
  });
});
