#!/usr/bin/env node
// Publish one app package to R2 (memory/hub/app_delivery_plan.md step 4b).
//
//   node scripts/app_hochladen.mjs --local|--remote <dist>/<name>-<version>.tar.gz [--ohne-bremse]
//
// Expects the package and its <name>-<version>.json ({name, version, sha256,
// size}) next to it, both written by scripts/app_paket_bauen.py. Checks
// sha256 + size, uploads apps/<name>/<version>.tar.gz FIRST and
// apps/<name>/index.json LAST (so the index never names a missing file).
// The new version goes to the top of the index ("newest first" = upload
// order). A version already published with a different sha256 is refused:
// a published version never changes (nodes check its sha256).
//
// Brake: like scripts/paket_hochladen.mjs, refused with "speicher_voll" if
// the package would push R2 over the free storage; --ohne-bremse skips it.
import { createHash } from "node:crypto";
import { existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { BUCKET, DB, wrangler, wranglerVersuch, ziel } from "./_wrangler.mjs";
import { GRENZEN } from "../src/grenzen.ts";

const NAME = /^[a-z][a-z0-9_-]{0,31}$/;
const VERSION = /^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$/;

const argv = process.argv.slice(2);
const wo = ziel(argv);
const paket = argv.find((a) => a.endsWith(".tar.gz"));
if (!paket || !existsSync(paket)) {
  console.error("Name the package: node scripts/app_hochladen.mjs --local|--remote <name>-<version>.tar.gz");
  process.exit(2);
}
const infoDatei = join(dirname(resolve(paket)), basename(paket).replace(/\.tar\.gz$/, ".json"));
if (!existsSync(infoDatei)) {
  console.error(`Missing ${infoDatei} — build with scripts/app_paket_bauen.py.`);
  process.exit(1);
}
const info = JSON.parse(readFileSync(infoDatei, "utf8"));
if (!NAME.test(String(info.name)) || !VERSION.test(String(info.version))) {
  console.error(`${infoDatei} has no valid name/version.`);
  process.exit(1);
}
if (basename(paket) !== `${info.name}-${info.version}.tar.gz`) {
  console.error(`${basename(paket)} does not match ${info.name}-${info.version}.`);
  process.exit(1);
}
const bytes = readFileSync(paket);
const sha = createHash("sha256").update(bytes).digest("hex");
const size = statSync(paket).size;
if (sha !== info.sha256 || size !== info.size) {
  console.error(`${basename(infoDatei)} does not match the package (sha256 ${sha}, ${size} bytes).`);
  process.exit(1);
}

const indexKey = `apps/${info.name}/index.json`;
let versions = [];
const alt = wranglerVersuch(["r2", "object", "get", `${BUCKET}/${indexKey}`, wo, "--pipe"]);
if (alt) {
  try {
    versions = JSON.parse(alt).versions ?? [];
  } catch {
    console.error(`${indexKey} in R2 is not JSON — fix it by hand first. Nothing uploaded.`);
    process.exit(1);
  }
}
const da = versions.find((v) => v.version === info.version);
if (da && da.sha256 !== sha) {
  console.error(`${info.name} ${info.version} is already published with another sha256. Raise the version. Nothing uploaded.`);
  process.exit(1);
}

if (!argv.includes("--ohne-bremse") && !da) {
  const aus = wranglerVersuch(["d1", "execute", DB, wo, "--json", "--command",
    "SELECT MAX(wert) AS b FROM nutzung_wert WHERE name IN ('r2_bytes', 'cf:r2_speicher')"]);
  let jetzt = null;
  try {
    const b = JSON.parse(aus)[0].results[0].b;
    jetzt = typeof b === "number" ? b : null;
  } catch { /* table missing */ }
  const grenze = GRENZEN.find((g) => g.id === "r2_speicher").grenze;
  if (jetzt !== null && jetzt + size > grenze) {
    console.error(`speicher_voll: R2 holds ${jetzt} bytes; ${size} more would go over the free ${grenze} bytes.`);
    console.error("Nothing uploaded. Free space first, or pass --ohne-bremse (then it may cost money).");
    process.exit(1);
  }
}

const neu = { name: info.name,
  versions: [{ version: info.version, sha256: sha, size }, ...versions.filter((v) => v.version !== info.version)] };
const tmp = mkdtempSync(join(tmpdir(), "app-index-"));
const indexDatei = join(tmp, "index.json");
writeFileSync(indexDatei, JSON.stringify(neu, null, 2) + "\n");
const hoch = (schluessel, datei, typ) => {
  console.log(`→ ${schluessel}`);
  wrangler(["r2", "object", "put", `${BUCKET}/${schluessel}`, wo, "--file", datei, "--content-type", typ], { still: true });
};
try {
  hoch(`apps/${info.name}/${info.version}.tar.gz`, resolve(paket), "application/gzip");
  hoch(indexKey, indexDatei, "application/json");
} finally {
  rmSync(tmp, { recursive: true, force: true });
}
if (!da) {
  wranglerVersuch(["d1", "execute", DB, wo, "--command",
    `UPDATE nutzung_wert SET wert = wert + ${Math.trunc(size)} WHERE name = 'r2_bytes'`]);
}
console.log(`Published ${info.name} ${info.version} (${wo.slice(2)}).`);
