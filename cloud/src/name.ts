// Account names (anonymous since 2026-10-23: no email anywhere).
//
// One uniform kind of name for everyone: a self-chosen username, 3 to 32
// characters a-z 0-9 . _ -, starting with a letter, stored NFC-normalized and
// lower case. (No "anonymous option" such as generated numbers: a choice
// would itself be metadata — Tor principle, Sasha 23.10.2026.)
// Same rules in core/konto.py; shared cases in tests/daten/konto_namen.json.

import { text, ungueltig } from "./hilfe";

const BENUTZERNAME = /^[a-z][a-z0-9._-]{2,31}$/;

/** Exactly these may not be taken (plus everything starting with RESERVIERT_ANFANG). */
export const RESERVIERT = new Set([
  "abuse", "admin", "administrator", "anonym", "anonymous", "api", "betreiber", "cloudflare",
  "contact", "help", "hilfe", "hostmaster", "info", "kontakt", "mod", "moderator", "no-reply",
  "noreply", "null", "official", "offiziell", "operator", "owner", "postmaster", "root",
  "security", "sicherheit", "staff", "superuser", "support", "sysadmin", "system", "team",
  "undefined", "webmaster", "zentrale",
]);
export const RESERVIERT_ANFANG = ["admin", "zentrale"];

export const KEINE_MAIL =
  "No email needed — ZENTRALE accounts are anonymous. Use a username instead " +
  "(3–32 characters: a–z, 0–9, '.', '_', '-', starting with a letter).";

/** trim + NFC + lower case. Never throws. */
export function nameNormal(roh: string): string {
  return roh.trim().normalize("NFC").toLowerCase();
}

/** The normalized name, or 400 with a sentence a person understands. */
export function namePruefen(roh: string): string {
  if (roh.includes("@")) throw ungueltig(KEINE_MAIL);
  const name = nameNormal(roh);
  if (!BENUTZERNAME.test(name)) {
    throw ungueltig("A username has 3–32 characters (a–z, 0–9, '.', '_', '-') and starts with a letter.");
  }
  return name;
}

export function reserviert(name: string): boolean {
  return RESERVIERT.has(name) || RESERVIERT_ANFANG.some((a) => name.startsWith(a));
}

/** The field `name` of a request body (login, vorab, emergency). */
export function nameLesen(daten: Record<string, unknown>): string {
  return namePruefen(text(daten, "name", 64));
}

/** Like nameLesen, but for a new account: reserved names are refused too. */
export function neuerNameLesen(daten: Record<string, unknown>): string {
  const name = nameLesen(daten);
  if (reserviert(name)) throw ungueltig("This username is reserved. Please choose another one.");
  return name;
}
