import { describe, expect, it } from "vitest";
import { anmelden, blobHoch, bytesText, jsonVon, kontoAnlegen, rufen, shaHex } from "./hilfe";

describe("Konten sind getrennt", () => {
  it("B sieht nichts von A", async () => {
    const a = await anmelden(await kontoAnlegen(), "geraet");
    const b = await anmelden(await kontoAnlegen(), "geraet");

    const r = await rufen("POST", "/v1/mitte/stand", { token: a, json: { basis: null, schreiben: { "inhalt.enc": btoa("geheim-a") } } });
    const kennungA = (await jsonVon(r)).kennung;
    await rufen("PUT", "/v1/knoten/geraet", { token: a, json: { name: "geraet", sorte: "vollknoten" } });
    await rufen("PUT", "/v1/besitz", { token: a, json: { besitz: "gAAAAABbesitz-a" } });

    expect(await jsonVon(await rufen("GET", "/v1/mitte", { token: b }))).toEqual({ kennung: null, namen: [] });
    expect((await rufen("GET", "/v1/mitte/datei/inhalt.enc", { token: b })).status).toBe(404);
    expect((await jsonVon(await rufen("GET", `/v1/mitte/enthaelt/${kennungA}`, { token: b }))).enthaelt).toBe(false);
    expect((await jsonVon(await rufen("GET", "/v1/knoten", { token: b }))).knoten).toEqual([]);
    expect((await jsonVon(await rufen("GET", "/v1/besitz", { token: b }))).besitz).toBeNull();

    // B kann A's Kopf nicht als Basis benutzen, und sein eigener Stand berührt A nicht.
    expect((await rufen("POST", "/v1/mitte/stand", { token: b, json: { basis: kennungA, schreiben: {} } })).status).toBe(409);
    const rb = await rufen("POST", "/v1/mitte/stand", { token: b, json: { basis: null, schreiben: { "inhalt.enc": btoa("geheim-b") } } });
    expect(rb.status).toBe(200);
    expect((await jsonVon(await rufen("GET", "/v1/mitte", { token: a }))).kennung).toBe(kennungA);
    expect(await bytesText(await rufen("GET", "/v1/mitte/datei/inhalt.enc", { token: a }))).toBe("geheim-a");
    expect(await bytesText(await rufen("GET", "/v1/mitte/datei/inhalt.enc", { token: b }))).toBe("geheim-b");

    // Blobs: A's Upload zählt für B nicht, B kann nicht darauf verweisen.
    const blob = new TextEncoder().encode("blob-von-a");
    const h = await shaHex(blob);
    expect((await blobHoch(a, blob)).status).toBe(204);
    expect((await jsonVon(await rufen("POST", "/v1/mitte/fehlende", { token: b, json: { sha256: [h] } }))).fehlen).toEqual([h]);
    const kopfB = (await jsonVon(await rufen("GET", "/v1/mitte", { token: b }))).kennung;
    const r2 = await rufen("POST", "/v1/mitte/stand", { token: b, json: { basis: kopfB, verweise: { "d/x.enc": h } } });
    expect(r2.status).toBe(400);
    expect((await jsonVon(r2)).fehler).toBe("blob_fehlt");
  });
});
