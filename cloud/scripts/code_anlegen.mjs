#!/usr/bin/env node
// Invite codes for the private beta.
//
//   node scripts/code_anlegen.mjs --local|--remote [--anzahl 3] [--notiz "for Alex"]
//   node scripts/code_anlegen.mjs --local|--remote --sperren ZB-XXXX-XXXX-XXXX-XXXX
//
// The codes are printed ONCE; the database only keeps their SHA-256
// (same normalization as the Worker: no spaces, upper case).
import { createHash, randomInt } from "node:crypto";
import { DB, wert, wrangler, ziel } from "./_wrangler.mjs";

const argv = process.argv.slice(2);
const wo = ziel(argv);
// Crockford-style alphabet: no 0/O, 1/I/L, U — easy to read aloud and type.
const ZEICHEN = "ABCDEFGHJKMNPQRSTVWXYZ23456789";

const normal = (code) => code.replace(/\s+/g, "").toUpperCase();
const hash = (code) => createHash("sha256").update(normal(code)).digest("hex");
const sql = (text) => "'" + String(text).replace(/'/g, "''") + "'";

function neuerCode() {
  const gruppen = [];
  for (let g = 0; g < 4; g++) {
    let s = "";
    for (let i = 0; i < 4; i++) s += ZEICHEN[randomInt(ZEICHEN.length)];
    gruppen.push(s);
  }
  return "ZB-" + gruppen.join("-");   // 16 × log2(30) ≈ 78 bits
}

const sperren = wert(argv, "--sperren");
if (sperren) {
  wrangler(["d1", "execute", DB, wo, "--yes", "--command",
    `UPDATE codes SET gesperrt = 1 WHERE code_hash = ${sql(hash(sperren))}`], { still: true });
  console.log("Blocked (if it existed).");
  process.exit(0);
}

const anzahl = Number(wert(argv, "--anzahl", "1"));
if (!Number.isInteger(anzahl) || anzahl < 1 || anzahl > 100) {
  console.error("--anzahl must be 1 to 100.");
  process.exit(2);
}
const notiz = wert(argv, "--notiz", "");
const codes = Array.from({ length: anzahl }, neuerCode);
const jetzt = Date.now();
const werte = codes.map((c) => `(${sql(hash(c))}, ${sql(notiz)}, ${jetzt})`).join(", ");
wrangler(["d1", "execute", DB, wo, "--yes", "--command",
  `INSERT INTO codes (code_hash, notiz, erstellt) VALUES ${werte}`], { still: true });
console.log(`Invite code${anzahl > 1 ? "s" : ""} (${wo.slice(2)}) — shown only now:`);
for (const c of codes) console.log("  " + c);
