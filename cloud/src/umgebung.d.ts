// Optional secret, not in wrangler.jsonc "secrets.required" (so `wrangler
// types` does not know it): a Cloudflare API token with "Account Analytics:
// Read" for the GraphQL usage numbers (src/nutzung.ts).
interface Env {
  CF_ANALYTICS_TOKEN?: string;
}
