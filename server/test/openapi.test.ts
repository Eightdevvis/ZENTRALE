import { describe, expect, it } from "vitest";
import { parse } from "yaml";
import spec from "../openapi.yaml?raw";
import { ROUTEN } from "../src/index";

describe("openapi.yaml", () => {
  it("beschreibt genau die Routen im Code", () => {
    const doc = parse(spec) as { openapi: string; paths: Record<string, Record<string, unknown>> };
    expect(doc.openapi).toMatch(/^3\.1/);
    const ausSpec = Object.entries(doc.paths)
      .flatMap(([pfad, ops]) => Object.keys(ops).filter((m) => ["get", "put", "post", "delete", "patch"].includes(m))
        .map((m) => `${m.toUpperCase()} ${pfad}`))
      .sort();
    const ausCode = ROUTEN.map((r) => `${r.methode} ${r.pfad}`).sort();
    expect(ausSpec).toEqual(ausCode);
  });
});
