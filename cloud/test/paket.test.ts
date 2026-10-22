import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, b64u, codeAnlegen, fernet, jsonVon, kontoAnlegen, rufen, zufall } from "./hilfe";

describe("install.sh", () => {
  it("Platzhalter, dann die hochgeladene Fassung", async () => {
    const leer = await rufen("GET", "/install.sh");
    expect(leer.status).toBe(200);
    expect(await leer.text()).toContain("exit 1");
    await env.R2.put("install.sh", "#!/bin/sh\necho echt\n");
    expect(await (await rufen("GET", "/install.sh")).text()).toBe("#!/bin/sh\necho echt\n");
  });
});

describe("Paket", () => {
  it("nur mit Code oder Sitzung; Download verbraucht den Code nicht", async () => {
    const code = await codeAnlegen("BETA-ABCD-EFGH");

    expect((await rufen("GET", "/v1/paket?code=" + code)).status).toBe(404); // noch nichts veröffentlicht
    await env.R2.put("pakete/2026-10-22.1.tar.gz", new Uint8Array([31, 139, 8, 0, 1, 2, 3]));
    await env.R2.put("pakete/neueste.json", JSON.stringify({ version: "2026-10-22.1", sha256: "ab".repeat(32), groesse: 7 }));

    const ohne = await rufen("GET", "/v1/paket");
    expect(ohne.status).toBe(401);
    expect((await jsonVon(ohne)).fehler).toBe("code_noetig");
    expect((await rufen("GET", "/v1/paket?code=FALSCH")).status).toBe(403);
    expect((await rufen("GET", "/v1/paket/2026-10-22.1.tar.gz")).status).toBe(401);

    // Code ohne Rücksicht auf Groß/Klein und Leerzeichen.
    const info = await rufen("GET", "/v1/paket?code=" + encodeURIComponent(" beta-abcd-efgh "));
    expect(info.status).toBe(200);
    expect(await jsonVon(info)).toEqual({ version: "2026-10-22.1", sha256: "ab".repeat(32), groesse: 7 });

    const datei = await rufen("GET", "/v1/paket/2026-10-22.1.tar.gz?code=" + code);
    expect(datei.status).toBe(200);
    expect(datei.headers.get("Content-Type")).toBe("application/gzip");
    expect(Array.from(new Uint8Array(await datei.arrayBuffer()))).toEqual([31, 139, 8, 0, 1, 2, 3]);
    expect((await rufen("GET", "/v1/paket/gibtsnicht.tar.gz?code=" + code)).status).toBe(404);

    // Der Code ist nach dem Download noch frei für ein Konto …
    const konto = await rufen("POST", "/v1/konto", {
      json: {
        mail: "paket@example.org", code, salz: b64u(zufall(16)), kdf: { name: "argon2id", t: 3, m: 65536, p: 4 },
        anmelde_schluessel: b64u(zufall()), verpackt_passwort: fernet(), verpackt_notfall: fernet(),
        notfall_beweis: b64u(zufall()),
      },
    });
    expect(konto.status).toBe(201);
    // … und lädt danach weiterhin (nur Konto-Anlegen verbraucht ihn).
    expect((await rufen("GET", "/v1/paket?code=" + code)).status).toBe(200);

    // Gesperrter Code geht nicht mehr.
    await env.DB.prepare("UPDATE codes SET gesperrt = 1").run();
    expect((await rufen("GET", "/v1/paket?code=" + code)).status).toBe(403);

    // Mit Sitzung statt Code.
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    expect((await rufen("GET", "/v1/paket", { token: t })).status).toBe(200);
    expect((await rufen("GET", "/v1/paket/2026-10-22.1.tar.gz", { token: t })).status).toBe(200);
  });
});
