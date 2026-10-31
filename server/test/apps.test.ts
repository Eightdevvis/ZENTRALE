import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, codeAnlegen, jsonVon, kontoAnlegen, rufen } from "./hilfe";

// memory/hub/app_delivery_plan.md step 4b: our app packages, login only (Q2).

const PAKET = new Uint8Array([31, 139, 8, 0, 9, 8, 7]);

async function sha256(b: Uint8Array): Promise<string> {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", b));
  return Array.from(h, (x) => x.toString(16).padStart(2, "0")).join("");
}

async function veroeffentlichen(): Promise<string> {
  const sha = await sha256(PAKET);
  await env.R2.put("apps/budget/1.0.0.tar.gz", PAKET);
  await env.R2.put("apps/budget/index.json", JSON.stringify({
    name: "budget",
    versions: [
      { version: "1.0.0", sha256: sha, size: PAKET.length },
      { version: "kaputt", sha256: "nope", size: 1 },
    ],
  }));
  return sha;
}

describe("App packages", () => {
  it("only with a login session — an invite code is not enough", async () => {
    await veroeffentlichen();
    const code = await codeAnlegen("BETA-APPS-0001");
    for (const pfad of ["/v1/apps/budget", "/v1/apps/budget/1.0.0.tar.gz"]) {
      const ohne = await rufen("GET", pfad);
      expect(ohne.status).toBe(401);
      expect((await jsonVon(ohne)).fehler).toBe("nicht_angemeldet");
      expect((await rufen("GET", `${pfad}?code=${code}`)).status).toBe(401);
    }
  });

  it("lists the valid versions and serves the package with a matching sha256", async () => {
    const sha = await veroeffentlichen();
    const t = await anmelden(await kontoAnlegen());
    const info = await rufen("GET", "/v1/apps/budget", { token: t });
    expect(info.status).toBe(200);
    expect(await jsonVon(info)).toEqual({ name: "budget", versions: [{ version: "1.0.0", sha256: sha, size: 7 }] });

    const datei = await rufen("GET", "/v1/apps/budget/1.0.0.tar.gz", { token: t });
    expect(datei.status).toBe(200);
    expect(datei.headers.get("Content-Type")).toBe("application/gzip");
    expect(await sha256(new Uint8Array(await datei.arrayBuffer()))).toBe(sha);
  });

  it("404 for unknown apps, versions not in the index and invalid names", async () => {
    await veroeffentlichen();
    const t = await anmelden(await kontoAnlegen());
    for (const pfad of ["/v1/apps/gibtsnicht", "/v1/apps/gibtsnicht/1.0.0.tar.gz",
                        "/v1/apps/budget/2.0.0.tar.gz", "/v1/apps/budget/kaputt.tar.gz",
                        "/v1/apps/Budget"]) {
      const r = await rufen("GET", pfad, { token: t });
      expect(r.status, pfad).toBe(404);
    }
    // in R2 but not in the index → not served
    await env.R2.put("apps/budget/0.9.0.tar.gz", PAKET);
    expect((await rufen("GET", "/v1/apps/budget/0.9.0.tar.gz", { token: t })).status).toBe(404);
  });
});
