import { describe, expect, it } from "vitest";
import { anmelden, jsonVon, kontoAnlegen, rufen } from "./hilfe";

const beschreibung = (name: string) => ({
  name, sorte: "vollknoten", beigetreten: "2026-10-22T18:00:00+00:00",
  hardware: { gpu: false, bildschirm: true }, dienste: ["tui"], programm: "2026-10-22.1",
});

describe("Knoten", () => {
  it("jeder Knoten schreibt nur sich selbst, alle sehen alle", async () => {
    const k = await kontoAnlegen();
    const laptop = await anmelden(k, "laptop");
    const minipc = await anmelden(k, "minipc");

    expect((await rufen("PUT", "/v1/knoten/laptop", { token: laptop, json: beschreibung("laptop") })).status).toBe(200);
    expect((await rufen("PUT", "/v1/knoten/minipc", { token: minipc, json: beschreibung("minipc") })).status).toBe(200);
    // Nochmal schreiben ersetzt.
    expect((await rufen("PUT", "/v1/knoten/minipc", { token: minipc, json: { ...beschreibung("minipc"), sorte: "gehirn" } })).status).toBe(200);

    const fremd = await rufen("PUT", "/v1/knoten/minipc", { token: laptop, json: beschreibung("minipc") });
    expect(fremd.status).toBe(403);
    expect((await jsonVon(fremd)).fehler).toBe("fremder_knoten");
    expect((await rufen("PUT", "/v1/knoten/laptop", { token: laptop, json: beschreibung("anders") })).status).toBe(400);

    const liste = (await jsonVon(await rufen("GET", "/v1/knoten", { token: laptop }))).knoten;
    expect(liste.map((x: { name: string }) => x.name)).toEqual(["laptop", "minipc"]);
    expect(liste[1].sorte).toBe("gehirn");
  });
});

describe("Besitz", () => {
  it("leer, setzen, lesen von jedem Gerät", async () => {
    const k = await kontoAnlegen();
    const a = await anmelden(k, "laptop");
    const b = await anmelden(k, "pc");
    expect(await jsonVon(await rufen("GET", "/v1/besitz", { token: a }))).toEqual({ besitz: null, aktualisiert: null });
    expect((await rufen("PUT", "/v1/besitz", { token: a, json: { besitz: "gAAAAABverschluesselt" } })).status).toBe(200);
    const d = await jsonVon(await rufen("GET", "/v1/besitz", { token: b }));
    expect(d.besitz).toBe("gAAAAABverschluesselt");
    expect(typeof d.aktualisiert).toBe("string");
    expect((await rufen("PUT", "/v1/besitz", { token: a, json: { besitz: 3 } })).status).toBe(400);
    expect((await rufen("GET", "/v1/besitz")).status).toBe(401);
  });
});
