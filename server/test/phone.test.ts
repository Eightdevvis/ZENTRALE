import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, jsonVon, kontoAnlegen, rufen, shaHex, zufall } from "./hilfe";

const OPERATOR = "betreiber-test"; // vitest.config.ts: BETREIBER_NAMEN

// Storage is shared inside this file: the operator account exists once.
let operator: Promise<string> | null = null;
const operatorToken = () => (operator ??= kontoAnlegen(OPERATOR).then((k) => anmelden(k)));

async function uploadApk(token: string, code: number, bytes: Uint8Array, sha?: string): Promise<Response> {
  return rufen("PUT", `/v1/phone/release/${code}.apk?sha256=${sha ?? (await shaHex(bytes))}`, {
    token, body: bytes, kopf: { "Content-Type": "application/octet-stream" },
  });
}

async function publish(token: string, code: number, bytes: Uint8Array, extra: Record<string, unknown> = {}) {
  return rufen("PUT", "/v1/phone/release", {
    token,
    json: { version: `0.${code}.0`, version_code: code, sha256: await shaHex(bytes), size: bytes.byteLength, notes: "test", ...extra },
  });
}

describe("phone app release", () => {
  it("needs a session; 404 before the first release", async () => {
    expect((await rufen("GET", "/v1/phone/release")).status).toBe(401);
    expect((await rufen("GET", "/v1/phone/release/1.apk")).status).toBe(401);
    const user = await anmelden(await kontoAnlegen());
    const r = await rufen("GET", "/v1/phone/release", { token: user });
    expect(r.status).toBe(404);
    expect((await jsonVon(r)).fehler).toBe("no_release");
  });

  it("only the operator may upload and publish", async () => {
    const user = await anmelden(await kontoAnlegen());
    const apk = zufall(100);
    const up = await uploadApk(user, 5, apk);
    expect(up.status).toBe(403);
    expect((await jsonVon(up)).fehler).toBe("operator_only");
    expect((await publish(user, 5, apk)).status).toBe(403);
    expect(await env.R2.head("phone/apk/5.apk")).toBeNull();
  });

  it("upload, publish, download; the manifest only names a matching APK", async () => {
    const op = await operatorToken();
    const apk = zufall(4096);

    // Manifest before the APK → apk_missing.
    const fehlt = await publish(op, 10, apk);
    expect(fehlt.status).toBe(409);
    expect((await jsonVon(fehlt)).fehler).toBe("apk_missing");

    // Wrong checksum → nothing stored.
    const falsch = await uploadApk(op, 10, apk, "00".repeat(32));
    expect(falsch.status).toBe(400);
    expect((await jsonVon(falsch)).fehler).toBe("pruefsumme");
    expect(await env.R2.head("phone/apk/10.apk")).toBeNull();

    expect((await uploadApk(op, 10, apk)).status).toBe(204);
    // A manifest whose sha256 or size differs from the stored APK is refused.
    const anders = await publish(op, 10, apk, { sha256: "ab".repeat(32) });
    expect((await jsonVon(anders)).fehler).toBe("apk_mismatch");
    expect((await jsonVon(await publish(op, 10, apk, { size: 4095 }))).fehler).toBe("apk_mismatch");

    const ok = await publish(op, 10, apk);
    expect(ok.status, await ok.clone().text()).toBe(200);
    const m = await jsonVon(ok);
    expect(m).toMatchObject({ version: "0.10.0", version_code: 10, sha256: await shaHex(apk), size: 4096, notes: "test" });
    expect(Date.parse(m.published_at)).toBeGreaterThan(0);

    const user = await anmelden(await kontoAnlegen());
    expect(await jsonVon(await rufen("GET", "/v1/phone/release", { token: user }))).toEqual(m);
    const d = await rufen("GET", "/v1/phone/release/10.apk", { token: user });
    expect(d.status).toBe(200);
    expect(d.headers.get("Content-Type")).toBe("application/vnd.android.package-archive");
    expect(new Uint8Array(await d.arrayBuffer())).toEqual(apk);
    expect((await rufen("GET", "/v1/phone/release/11.apk", { token: user })).status).toBe(404);
    expect((await rufen("GET", "/v1/phone/release/abc.apk", { token: user })).status).toBe(404);
  });

  it("the version code must grow; APKs older than the previous release are deleted", async () => {
    const op = await operatorToken();
    const a = zufall(10), b = zufall(11), c = zufall(12);
    for (const [code, bytes] of [[20, a], [21, b], [22, c]] as const) {
      expect((await uploadApk(op, code, bytes)).status).toBe(204);
    }
    expect((await publish(op, 20, a)).status).toBe(200);
    const alt = await publish(op, 20, a);
    expect(alt.status).toBe(409);
    expect(await jsonVon(alt)).toMatchObject({ fehler: "version_not_newer", current_version_code: 20 });
    expect((await publish(op, 22, c)).status).toBe(200);
    const keys = (await env.R2.list({ prefix: "phone/apk/" })).objects.map((o) => o.key).sort();
    // 10 (from the test before) is older than the previous release (20) → gone;
    // 21 was uploaded but never published and is newer than 20 → still there.
    expect(keys).toEqual(["phone/apk/20.apk", "phone/apk/21.apk", "phone/apk/22.apk"]);
    expect((await publish(op, 21, b)).status).toBe(409);
  });

  it("checks the input", async () => {
    const op = await operatorToken();
    const ohneSha = await rufen("PUT", "/v1/phone/release/30.apk", { token: op, body: zufall(5) });
    expect(ohneSha.status).toBe(400);
    const leer = await uploadApk(op, 30, new Uint8Array(0));
    expect(leer.status).toBe(400);
    const gross = await rufen("PUT", `/v1/phone/release/30.apk?sha256=${"00".repeat(32)}`, {
      token: op, body: zufall(5), kopf: { "Content-Length": String(200 * 1024 * 1024) },
    });
    expect(gross.status).toBe(413);
    for (const extra of [{ version: "../x" }, { version_code: 0 }, { version_code: 1.5 }, { notes: "x".repeat(2001) }]) {
      expect((await publish(op, 30, zufall(5), extra)).status).toBe(400);
    }
  });
});
