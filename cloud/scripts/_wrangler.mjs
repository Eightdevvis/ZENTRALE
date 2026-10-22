// Shared bits for the admin scripts: --local/--remote, running npx wrangler
// (arguments as a list, no shell), paths relative to cloud/.
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const CLOUD = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const DB = "zentrale";
export const BUCKET = "zentrale";

export function ziel(argv) {
  const lokal = argv.includes("--local");
  const fern = argv.includes("--remote");
  if (lokal === fern) {
    console.error("Say where: --local (wrangler dev storage) or --remote (Cloudflare).");
    process.exit(2);
  }
  return lokal ? "--local" : "--remote";
}

export function wert(argv, name, vorgabe = undefined) {
  const i = argv.indexOf(name);
  return i >= 0 && i + 1 < argv.length ? argv[i + 1] : vorgabe;
}

export function wrangler(args, { still = false } = {}) {
  const r = spawnSync("npx", ["wrangler", ...args], {
    cwd: CLOUD,
    stdio: still ? ["ignore", "pipe", "pipe"] : "inherit",
    encoding: "utf8",
  });
  if (r.status !== 0) {
    if (still) process.stderr.write((r.stdout || "") + (r.stderr || ""));
    console.error(`wrangler ${args[0]} ${args[1] ?? ""} failed (exit ${r.status}).`);
    process.exit(r.status || 1);
  }
  return r.stdout;
}
