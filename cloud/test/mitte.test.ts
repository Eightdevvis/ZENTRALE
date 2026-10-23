import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { anmelden, blobHoch, bytesText, jsonVon, kontoAnlegen, rufen, shaHex } from "./hilfe";

const b64 = (s: string) => btoa(s);

async function stand(token: string, basis: string | null, schreiben: Record<string, string>, loeschen: string[] = []) {
  return rufen("POST", "/v1/mitte/stand", { token, json: { basis, schreiben, loeschen } });
}

async function holen(token: string) {
  return jsonVon(await rufen("GET", "/v1/mitte", { token }));
}

describe("Mitte", () => {
  it("leer, erster Stand, Dateien lesen, Compare-and-Swap, enthaelt", async () => {
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    expect(await holen(t)).toEqual({ kennung: null, namen: [] });

    // Erster Stand auf die leere Mitte.
    const r1 = await stand(t, null, { "inhalt.enc": b64("inhalt-1"), "d/aa.enc": b64("A"), "knoten/minipc/bb.enc": b64("B") });
    expect(r1.status).toBe(200);
    const k1 = (await jsonVon(r1)).kennung as string;
    expect(await holen(t)).toEqual({ kennung: k1, namen: ["d/aa.enc", "inhalt.enc", "knoten/minipc/bb.enc"] });

    const datei = await rufen("GET", "/v1/mitte/datei/knoten/minipc/bb.enc", { token: t });
    expect(datei.status).toBe(200);
    expect(datei.headers.get("Content-Type")).toBe("application/octet-stream");
    expect(await bytesText(datei)).toBe("B");
    expect((await rufen("GET", "/v1/mitte/datei/d/gibtsnicht.enc", { token: t })).status).toBe(404);

    // Noch einmal auf die leere Mitte → jemand war schneller.
    const spaet = await stand(t, null, { "inhalt.enc": b64("x") });
    expect(spaet.status).toBe(409);
    expect((await jsonVon(spaet)).fehler).toBe("jemand_schneller");

    // Zweiter Stand: eine Datei ändern, eine löschen, eine bleibt.
    const r2 = await stand(t, k1, { "inhalt.enc": b64("inhalt-2") }, ["d/aa.enc"]);
    expect(r2.status).toBe(200);
    const k2 = (await jsonVon(r2)).kennung as string;
    expect(k2).not.toBe(k1);
    expect(await holen(t)).toEqual({ kennung: k2, namen: ["inhalt.enc", "knoten/minipc/bb.enc"] });
    expect(await bytesText(await rufen("GET", "/v1/mitte/datei/inhalt.enc", { token: t }))).toBe("inhalt-2");
    expect(await bytesText(await rufen("GET", "/v1/mitte/datei/knoten/minipc/bb.enc", { token: t }))).toBe("B");
    expect((await rufen("GET", "/v1/mitte/datei/d/aa.enc", { token: t })).status).toBe(404);

    // Veraltete Basis → 409, Kopf bleibt.
    expect((await stand(t, k1, { "inhalt.enc": b64("verloren") })).status).toBe(409);
    expect((await stand(t, "erfunden", { "inhalt.enc": b64("verloren") })).status).toBe(409);
    expect((await holen(t)).kennung).toBe(k2);

    // enthaelt: jeder Stand, der je Kopf war.
    const enthaelt = async (kennung: string) =>
      (await jsonVon(await rufen("GET", `/v1/mitte/enthaelt/${encodeURIComponent(kennung)}`, { token: t }))).enthaelt;
    expect(await enthaelt(k1)).toBe(true);
    expect(await enthaelt(k2)).toBe(true);
    expect(await enthaelt("vorlaeufig-abc")).toBe(false);
  });

  it("speichert gleiche Inhalte nur einmal (nach Prüfsumme)", async () => {
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    const r1 = await stand(t, null, { "d/a.enc": b64("gleich"), "d/b.enc": b64("gleich") });
    const k1 = (await jsonVon(r1)).kennung;
    await stand(t, k1, { "d/c.enc": b64("gleich") });
    const konto = await env.DB.prepare("SELECT id FROM konten WHERE name = ?").bind(k.name).first<{ id: string }>();
    const liste = await env.R2.list({ prefix: `mitte/${konto!.id}/` });
    expect(liste.objects.length).toBe(1);
  });

  it("nimmt auch URL-sicheres base64 und weist schlechte Namen ab", async () => {
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    const bytes = new Uint8Array([251, 255, 0, 62, 63]);
    const urlsicher = btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const r = await stand(t, null, { "d/bin.enc": urlsicher });
    expect(r.status).toBe(200);
    const zurueck = new Uint8Array(await (await rufen("GET", "/v1/mitte/datei/d/bin.enc", { token: t })).arrayBuffer());
    expect(Array.from(zurueck)).toEqual(Array.from(bytes));

    const kopf = (await holen(t)).kennung;
    for (const name of ["../geheim", "/abs", "d//x", "d/../x", "a b"]) {
      expect((await stand(t, kopf, { [name]: b64("x") })).status, name).toBe(400);
    }
    expect((await stand(t, kopf, { "d/x.enc": "nicht base64!" })).status).toBe(400);
    expect((await stand(t, kopf, { "d/x.enc": b64("x") }, ["d/x.enc"])).status).toBe(400);
    expect((await rufen("GET", "/v1/mitte")).status).toBe(401);
  });

  it("große Dateien: fehlende fragen, Blobs hochladen, Stand verweist", async () => {
    const k = await kontoAnlegen();
    const t = await anmelden(k);
    const gross = new Uint8Array(3 * 1024 * 1024).map((_, i) => i % 251);
    const klein = new TextEncoder().encode("klein");
    const hg = await shaHex(gross);
    const hk = await shaHex(klein);

    let r = await rufen("POST", "/v1/mitte/fehlende", { token: t, json: { sha256: [hg, hk, hg] } });
    expect(r.status).toBe(200);
    expect(((await jsonVon(r)).fehlen as string[]).sort()).toEqual([hg, hk].sort());

    // Verweis auf etwas, das noch nicht oben ist → blob_fehlt mit Liste.
    r = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: null, verweise: { "d/gross.enc": hg } } });
    expect(r.status).toBe(400);
    expect(await jsonVon(r)).toMatchObject({ fehler: "blob_fehlt", fehlen: [hg] });

    // Falsche Prüfsumme wird abgewiesen und nicht gespeichert.
    r = await blobHoch(t, klein, hg);
    expect(r.status).toBe(400);
    expect((await jsonVon(r)).fehler).toBe("pruefsumme");
    expect((await rufen("PUT", "/v1/mitte/blob/NICHTHEX", { token: t, body: klein })).status).toBe(400);
    expect((await blobHoch("", klein)).status).toBe(401);

    expect((await blobHoch(t, gross)).status).toBe(204);
    expect((await blobHoch(t, gross)).status).toBe(204); // schon da: nichts zu tun
    r = await rufen("POST", "/v1/mitte/fehlende", { token: t, json: { sha256: [hg, hk] } });
    expect((await jsonVon(r)).fehlen).toEqual([hk]);

    // Stand mit Verweis + kleinem Inline-Teil.
    r = await rufen("POST", "/v1/mitte/stand", {
      token: t, json: { basis: null, verweise: { "d/gross.enc": hg }, schreiben: { "inhalt.enc": b64("klein") } },
    });
    expect(r.status).toBe(200);
    const k1 = (await jsonVon(r)).kennung;
    expect((await holen(t)).namen).toEqual(["d/gross.enc", "inhalt.enc"]);
    const zurueck = new Uint8Array(await (await rufen("GET", "/v1/mitte/datei/d/gross.enc", { token: t })).arrayBuffer());
    expect(zurueck.byteLength).toBe(gross.byteLength);
    expect(await shaHex(zurueck)).toBe(hg);
    // Inline geschriebene Dateien zählen danach auch als vorhanden.
    expect((await jsonVon(await rufen("POST", "/v1/mitte/fehlende", { token: t, json: { sha256: [hk] } }))).fehlen).toEqual([]);
    // … und dürfen im nächsten Stand verwiesen werden.
    r = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: k1, verweise: { "d/kopie.enc": hk } } });
    expect(r.status).toBe(200);

    // Ein Name darf nur einmal vorkommen; der Stand-Body ist auf 4 MiB begrenzt.
    const kopf = (await holen(t)).kennung;
    r = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: kopf, verweise: { "d/x.enc": hk }, schreiben: { "d/x.enc": b64("x") } } });
    expect(r.status).toBe(400);
    r = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: kopf, schreiben: { "d/riesig.enc": "A".repeat(5 * 1024 * 1024) } } });
    expect(r.status).toBe(413);
    expect((await jsonVon(r)).fehler).toBe("zu_gross");
    r = await rufen("POST", "/v1/mitte/stand", { token: t, json: { basis: kopf, schreiben: { "d/mittel.enc": "A".repeat(400 * 1024) } } });
    expect(r.status).toBe(413);
    expect((await jsonVon(r)).fehler).toBe("inline_zu_gross");
    r = await rufen("POST", "/v1/mitte/fehlende", { token: t, json: { sha256: ["xyz"] } });
    expect(r.status).toBe(400);
  });
});
