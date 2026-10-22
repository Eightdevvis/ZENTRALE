#!/usr/bin/env node
// Publish a release to R2.
//
//   node scripts/paket_hochladen.mjs --local|--remote [--dist ../dist] [--install ../deploy/install.sh]
//
// Expects dist/neueste.json ({version, sha256, groesse}) and
// dist/zentrale-<version>.tar.gz (built by scripts/paket_bauen.py). Checks
// sha256 + size, uploads the package to pakete/<version>.tar.gz FIRST and
// pakete/neueste.json LAST (so the pointer never names a missing file), then
// install.sh. Paths are relative to cloud/.
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { BUCKET, CLOUD, wert, wrangler, ziel } from "./_wrangler.mjs";

const argv = process.argv.slice(2);
const wo = ziel(argv);
const dist = resolve(CLOUD, wert(argv, "--dist", "../dist"));
const install = resolve(CLOUD, wert(argv, "--install", "../deploy/install.sh"));

const zeiger = resolve(dist, "neueste.json");
if (!existsSync(zeiger)) {
  console.error(`Missing ${zeiger} — build the package first.`);
  process.exit(1);
}
const info = JSON.parse(readFileSync(zeiger, "utf8"));
if (typeof info.version !== "string" || !/^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$/.test(info.version)) {
  console.error("neueste.json has no valid 'version'.");
  process.exit(1);
}
const paket = resolve(dist, `zentrale-${info.version}.tar.gz`);
if (!existsSync(paket)) {
  console.error(`Missing ${paket}.`);
  process.exit(1);
}
const sha = createHash("sha256").update(readFileSync(paket)).digest("hex");
const groesse = statSync(paket).size;
if (sha !== info.sha256 || groesse !== info.groesse) {
  console.error(`neueste.json does not match the package (sha256 ${sha}, ${groesse} bytes).`);
  process.exit(1);
}

const hoch = (schluessel, datei, typ) => {
  console.log(`→ ${schluessel}`);
  wrangler(["r2", "object", "put", `${BUCKET}/${schluessel}`, wo, "--file", datei, "--content-type", typ], { still: true });
};
hoch(`pakete/${info.version}.tar.gz`, paket, "application/gzip");
hoch("pakete/neueste.json", zeiger, "application/json");
if (existsSync(install)) hoch("install.sh", install, "text/plain; charset=utf-8");
else console.log(`(no ${install} — install.sh not uploaded)`);
console.log(`Published ${info.version} (${wo.slice(2)}).`);
