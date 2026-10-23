#!/usr/bin/env node
// Publish a release to R2.
//
//   node scripts/paket_hochladen.mjs --local|--remote [--dist ../dist] [--install ../deploy/install.sh] [--ohne-bremse]
//
// Expects dist/neueste.json ({version, sha256, groesse}) and
// dist/zentrale-<version>.tar.gz (built by scripts/paket_bauen.py). Checks
// sha256 + size, uploads the package to pakete/<version>.tar.gz FIRST and
// pakete/neueste.json LAST (so the pointer never names a missing file), then
// install.sh. Paths are relative to cloud/.
//
// Brake (like PUT /v1/mitte/blob): refused with "speicher_voll" if the package
// would push R2 over the free storage (src/grenzen.ts). Afterwards the stored
// bytes in D1 (nutzung_wert 'r2_bytes') go up by the package size; the daily
// cron recount corrects any drift (e.g. a re-uploaded version).
// --ohne-bremse skips the check (the upload then may cost money).
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { BUCKET, CLOUD, DB, wert, wrangler, wranglerVersuch, ziel } from "./_wrangler.mjs";
import { GRENZEN } from "../src/grenzen.ts";

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

// Stored bytes as the Worker counts them (null: table missing / unreadable).
function gespeichert() {
  const aus = wranglerVersuch(["d1", "execute", DB, wo, "--json", "--command",
    "SELECT MAX(wert) AS b FROM nutzung_wert WHERE name IN ('r2_bytes', 'cf:r2_speicher')"]);
  try {
    const b = JSON.parse(aus)[0].results[0].b;
    return typeof b === "number" ? b : null;
  } catch {
    return null;
  }
}

const grenze = GRENZEN.find((g) => g.id === "r2_speicher").grenze;
const dazu = groesse + (existsSync(install) ? statSync(install).size : 0);
if (!argv.includes("--ohne-bremse")) {
  const jetzt = gespeichert();
  if (jetzt === null) {
    console.log("(usage table not readable — apply migration 0002 first; uploading without the storage check)");
  } else if (jetzt + dazu > grenze) {
    console.error(`speicher_voll: R2 holds ${jetzt} bytes; ${dazu} more would go over the free ${grenze} bytes.`);
    console.error("Nothing uploaded. Free space first, or pass --ohne-bremse (then it may cost money).");
    process.exit(1);
  }
}

const hoch = (schluessel, datei, typ) => {
  console.log(`→ ${schluessel}`);
  wrangler(["r2", "object", "put", `${BUCKET}/${schluessel}`, wo, "--file", datei, "--content-type", typ], { still: true });
};
hoch(`pakete/${info.version}.tar.gz`, paket, "application/gzip");
hoch("pakete/neueste.json", zeiger, "application/json");
if (existsSync(install)) hoch("install.sh", install, "text/plain; charset=utf-8");
else console.log(`(no ${install} — install.sh not uploaded)`);
// Keep the Worker's byte count close (integer only, no user text in SQL).
wranglerVersuch(["d1", "execute", DB, wo, "--command",
  `UPDATE nutzung_wert SET wert = wert + ${Math.trunc(dazu)} WHERE name = 'r2_bytes'`]);
console.log(`Published ${info.version} (${wo.slice(2)}).`);
