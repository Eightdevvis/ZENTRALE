import { createExecutionContext, createScheduledController, waitOnExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import worker, { CRON_TAEGLICH } from "../src/index";
import {
  EIGEN_GELESEN, EIGEN_GESCHRIEBEN, GRAPHQL, GRENZEN, R2_SPEICHER_GRENZE, cloudflareAbfragen, neuerZaehler,
  r2Klasse, stufe, zaehlendeUmgebung, zaehlerSchreiben,
} from "../src/nutzung";
import { anmelden, blobHoch, jsonVon, kontoAnlegen, rufen, rufenGezaehlt, shaHex } from "./hilfe";

const BETREIBER = "jenny_wolff@hotmail.com";
const heute = () => new Date().toISOString().slice(0, 10);

async function zeile() {
  return (await env.DB.prepare("SELECT * FROM nutzung_tag WHERE tag = ?").bind(heute()).first<Record<string, number>>())
    ?? { anfragen: 0, d1_gelesen: 0, d1_geschrieben: 0, r2_a: 0, r2_b: 0, d1_bytes: 0 };
}

async function r2Bytes(): Promise<number> {
  return (await env.DB.prepare("SELECT wert FROM nutzung_wert WHERE name = 'r2_bytes'").first<{ wert: number }>())!.wert;
}

async function setzeR2Bytes(n: number) {
  await env.DB.prepare("UPDATE nutzung_wert SET wert = ? WHERE name = 'r2_bytes'").bind(n).run();
}

// Storage is shared inside this file: the operator account exists once.
let betreiber: Promise<string> | null = null;
function betreiberToken() {
  betreiber ??= kontoAnlegen(BETREIBER).then((k) => anmelden(k));
  return betreiber;
}

describe("Grenzen und Stufen", () => {
  it("Tabelle mit Quelle; Stufen bei 50/80/95/100 %", () => {
    expect(GRENZEN.map((g) => g.id)).toEqual(
      ["worker_anfragen", "d1_gelesen", "d1_geschrieben", "d1_speicher", "r2_speicher", "r2_a", "r2_b"]);
    for (const g of GRENZEN) expect(g.quelle).toMatch(/^https:\/\/developers\.cloudflare\.com\//);
    expect(GRENZEN.filter((g) => g.kostet).map((g) => g.id)).toEqual(["r2_speicher", "r2_a", "r2_b"]);
    expect([0, 49.9, 50, 79.9, 80, 94.9, 95, 99.9, 100, 250].map(stufe))
      .toEqual(["ok", "ok", "50", "50", "80", "80", "95", "95", "voll", "voll"]);
    expect([r2Klasse("PutObject"), r2Klasse("ListObjects"), r2Klasse("GetObject"), r2Klasse("HeadObject"),
      r2Klasse("DeleteObject"), r2Klasse("AbortMultipartUpload"), r2Klasse("CompleteMultipartUpload")])
      .toEqual(["a", "a", "b", "b", "frei", "frei", "a"]);
  });
});

describe("Selbstzählung", () => {
  it("Anfragen, D1-Zeilen, R2-Operationen und gespeicherte Bytes", async () => {
    const t = await anmelden(await kontoAnlegen());
    const vorher = await zeile();
    const bytesVorher = await r2Bytes();

    expect((await rufenGezaehlt("GET", "/v1/mitte", { token: t })).status).toBe(200);
    const n1 = await zeile();
    expect(n1.anfragen).toBe(vorher.anfragen + 1);
    expect(n1.d1_gelesen).toBeGreaterThan(vorher.d1_gelesen + EIGEN_GELESEN);   // Sitzung + Kopf + Meter
    expect(n1.d1_geschrieben).toBeGreaterThanOrEqual(vorher.d1_geschrieben + EIGEN_GESCHRIEBEN);
    expect(n1.d1_bytes).toBeGreaterThan(0);                                      // meta.size_after
    expect(n1.r2_a).toBe(vorher.r2_a);

    // Blob hoch: 1 × Class A, Bytes genau dazu.
    const blob = new TextEncoder().encode("zwölf bytes!");
    const h = await shaHex(blob);
    expect((await rufenGezaehlt("PUT", `/v1/mitte/blob/${h}`, { token: t, body: blob })).status).toBe(204);
    const n2 = await zeile();
    expect(n2.r2_a).toBe(n1.r2_a + 1);
    expect(await r2Bytes()).toBe(bytesVorher + blob.byteLength);

    // Derselbe Blob noch einmal: schon da, nichts in R2, keine Bytes.
    expect((await rufenGezaehlt("PUT", `/v1/mitte/blob/${h}`, { token: t, body: blob })).status).toBe(204);
    expect((await zeile()).r2_a).toBe(n2.r2_a);
    expect(await r2Bytes()).toBe(bytesVorher + blob.byteLength);

    // Stand mit Verweis, dann Datei lesen: 1 × Class B.
    await rufenGezaehlt("POST", "/v1/mitte/stand", { token: t, json: { basis: null, verweise: { "d/x.enc": h } } });
    const n3 = await zeile();
    const datei = await rufenGezaehlt("GET", "/v1/mitte/datei/d/x.enc", { token: t });
    expect(datei.status).toBe(200);
    await datei.arrayBuffer();
    expect((await zeile()).r2_b).toBe(n3.r2_b + 1);

    // Auch Fehlerantworten zählen als Anfrage.
    const n4 = await zeile();
    expect((await rufenGezaehlt("GET", "/gibtsnicht")).status).toBe(404);
    expect((await zeile()).anfragen).toBe(n4.anfragen + 1);
  });

  it("der Zähler selbst kostet eine Zeile lesen + eine schreiben", async () => {
    await zaehlerSchreiben(env.DB, neuerZaehler(), Date.now(), 1);      // Zeile für heute gibt es schon
    const z = neuerZaehler();
    const gezaehlt = zaehlendeUmgebung(env, z);
    await zaehlerSchreiben(gezaehlt.DB, neuerZaehler(), Date.now(), 1);
    expect(z.d1Geschrieben).toBe(EIGEN_GESCHRIEBEN);
    expect(z.d1Gelesen).toBeLessThanOrEqual(EIGEN_GELESEN);   // lokal 0; die Konstante rechnet sicher mit 1
  });

  it("R2 löschen zieht die Größe ab", async () => {
    await env.R2.put("mitte/x/loeschen", "123456");
    const z = neuerZaehler();
    await zaehlendeUmgebung(env, z).R2.delete("mitte/x/loeschen");
    expect(z.r2Bytes).toBe(-6);
    expect(z.r2B).toBe(1);
    expect(z.r2A).toBe(0);
  });

  it("ein kaputter Zähler bricht keine Anfrage", async () => {
    const kaputt = new Proxy(env.DB, {
      get(t, k) {
        if (k === "prepare") return () => { throw new Error("D1 weg"); };
        return Reflect.get(t, k, t);
      },
    });
    await expect(zaehlerSchreiben(kaputt, neuerZaehler(), Date.now(), 1)).resolves.toBeUndefined();
    const umgebung = { ...env, DB: new Proxy(env.DB, {
      get(t, k) {
        if (k === "prepare") {
          return (sql: string) => {
            if (sql.includes("nutzung_tag")) throw new Error("D1 weg");
            return t.prepare(sql);
          };
        }
        return Reflect.get(t, k, t);
      },
    }) };
    const r = await rufenGezaehlt("GET", "/install.sh", {}, umgebung);
    expect(r.status).toBe(200);
  });
});

describe("GET /v1/nutzung", () => {
  it("nur für Betreiber; Stufen und Warnungen", async () => {
    const fremd = await anmelden(await kontoAnlegen());
    const nein = await rufen("GET", "/v1/nutzung", { token: fremd });
    expect(nein.status).toBe(403);
    expect((await jsonVon(nein)).fehler).toBe("nur_betreiber");
    expect((await rufen("GET", "/v1/nutzung")).status).toBe(401);

    const t = await betreiberToken();
    await env.DB.prepare(
      `INSERT INTO nutzung_tag (tag, anfragen, d1_gelesen, d1_geschrieben, r2_a, r2_b, d1_bytes) VALUES (?, 60000, 10, 85000, 0, 0, 0)
       ON CONFLICT(tag) DO UPDATE SET anfragen = 60000, d1_geschrieben = 85000`,
    ).bind(heute()).run();
    await setzeR2Bytes(9_600_000_000);

    const r = await rufen("GET", "/v1/nutzung", { token: t });
    expect(r.status).toBe(200);
    const d = await jsonVon(r);
    expect(d.grenzen_geprueft).toBe("2026-10-23");
    const p = Object.fromEntries((d.grenzen as any[]).map((g) => [g.id, g]));
    expect(Object.keys(p).sort()).toEqual(GRENZEN.map((g) => g.id).sort());
    expect(p.worker_anfragen).toMatchObject({ name: "Worker requests", limit: 100_000, unit: "requests", period: "day", level: "50", source: "self" });
    expect(p.worker_anfragen.used).toBeGreaterThanOrEqual(60000);
    expect(p.d1_geschrieben.level).toBe("80");
    expect(p.r2_speicher).toMatchObject({ used: 9_600_000_000, percent: 96, level: "95", period: "now", costs_money: true });
    expect(p.r2_a.level).toBe("ok");
    expect(d.warnungen.map((w: any) => w.id)).toEqual(["r2_speicher", "d1_geschrieben", "worker_anfragen"]);
    expect(d.warnungen[0].text).toBe("R2 storage at 96 % (9.60 GB of 10.00 GB).");

    await setzeR2Bytes(R2_SPEICHER_GRENZE + 1);
    const voll = await jsonVon(await rufen("GET", "/v1/nutzung", { token: t }));
    expect(voll.warnungen[0]).toMatchObject({ id: "r2_speicher", level: "voll" });
    expect(voll.warnungen[0].text).toContain("costs money");
  });
});

describe("Bremse", () => {
  it("507 speicher_voll für Blob und Inline-Dateien, aus mit BREMSE_SPEICHER=aus", async () => {
    const t = await anmelden(await kontoAnlegen());
    await setzeR2Bytes(R2_SPEICHER_GRENZE - 10);
    const gross = new TextEncoder().encode("zwanzig bytes lang!!");
    const r = await blobHoch(t, gross);
    expect(r.status).toBe(507);
    expect(await jsonVon(r)).toMatchObject({ fehler: "speicher_voll" });
    const sha = await shaHex(gross);
    expect((await env.R2.list({ prefix: "mitte/" })).objects.some((o) => o.key.endsWith(sha))).toBe(false);

    const klein = new TextEncoder().encode("fuenf");
    expect((await blobHoch(t, klein)).status).toBe(204);

    const stand = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: null, schreiben: { "a.enc": btoa("mehr als zehn bytes") } } });
    expect(stand.status).toBe(507);

    const aus = await rufenGezaehlt("PUT", `/v1/mitte/blob/${await shaHex(gross)}`, { token: t, body: gross },
      { ...env, BREMSE_SPEICHER: "aus" });
    expect(aus.status).toBe(204);
    await setzeR2Bytes(0);
  });
});

describe("Cron", () => {
  it("zählt R2 nach (auch Pakete von wrangler)", async () => {
    await env.R2.put("pakete/1.tar.gz", new Uint8Array(1000));
    await env.R2.put("mitte/k/abc", new Uint8Array(234));
    await setzeR2Bytes(5);
    const soll = (await env.R2.list()).objects.reduce((s, o) => s + o.size, 0);
    expect(soll).toBeGreaterThanOrEqual(1234);
    const ctx = createExecutionContext();
    await worker.scheduled(createScheduledController({ cron: CRON_TAEGLICH, scheduledTime: Date.now() }), env, ctx);
    await waitOnExecutionContext(ctx);
    expect(await r2Bytes()).toBe(soll);
  });

  it("GraphQL: ohne Token nichts; mit Token gespeichert und im Bericht", async () => {
    const aufrufe: { url: string; body: any; auth: string | null }[] = [];
    const holen = async (url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      aufrufe.push({ url, body, auth: new Headers(init.headers).get("Authorization") });
      const q = body.query as string;
      const g = q.includes("workersInvocationsAdaptive") ? [{ sum: { requests: 70000 } }]
        : q.includes("d1AnalyticsAdaptiveGroups") ? [{ sum: { rowsRead: 1000, rowsWritten: 400 } }, { sum: { rowsRead: 500, rowsWritten: 100 } }]
          : q.includes("d1StorageAdaptiveGroups") ? [{ max: { databaseSizeBytes: 300_000 }, dimensions: { databaseId: "a" } },
            { max: { databaseSizeBytes: 450_000_000 }, dimensions: { databaseId: "b" } }]
            : q.includes("r2OperationsAdaptiveGroups") ? [
              { sum: { requests: 900_000 }, dimensions: { actionType: "PutObject" } },
              { sum: { requests: 10 }, dimensions: { actionType: "ListObjects" } },
              { sum: { requests: 5 }, dimensions: { actionType: "GetObject" } },
              { sum: { requests: 99 }, dimensions: { actionType: "DeleteObject" } }]
              : null;
      if (g === null) return Response.json({ data: null, errors: [{ message: "unknown field" }] });
      return Response.json({ data: { viewer: { accounts: [{ g }] } }, errors: null });
    };

    expect(await cloudflareAbfragen(env, Date.now(), holen)).toEqual({});
    expect(aufrufe).toHaveLength(0);

    const mit = { ...env, CF_ANALYTICS_TOKEN: "tok-123", CF_ACCOUNT_ID: "acc-9" };
    const werte = await cloudflareAbfragen(mit, Date.now(), holen);
    expect(aufrufe).toHaveLength(5);
    expect(aufrufe.every((a) => a.url === GRAPHQL && a.auth === "Bearer tok-123" && a.body.variables.a === "acc-9")).toBe(true);
    // r2StorageAdaptiveGroups gab einen Fehler → fehlt, der Rest ist da.
    expect(werte).toEqual({
      worker_anfragen: 70000, d1_gelesen: 1500, d1_geschrieben: 500, d1_speicher: 450_000_000, r2_a: 900_010, r2_b: 5,
    });

    const d = await jsonVon(await rufen("GET", "/v1/nutzung", { token: await betreiberToken() }));
    const p = Object.fromEntries((d.grenzen as any[]).map((g) => [g.id, g]));
    expect(p.worker_anfragen).toMatchObject({ used: 70000, source: "cloudflare", cloudflare: 70000, level: "50" });
    expect(p.worker_anfragen.cloudflare_at).toMatch(/^\d{4}-/);
    expect(p.r2_a).toMatchObject({ used: 900_010, source: "cloudflare", level: "80" });
    expect(p.d1_speicher).toMatchObject({ source: "cloudflare", level: "80" });
    expect(p.r2_speicher.cloudflare).toBeNull();
  });
});
