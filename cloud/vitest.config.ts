import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

export default defineConfig(async () => {
  const migrations = await readD1Migrations("./migrations");
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: "./wrangler.jsonc" },
        miniflare: {
          // Test-only values; the real secret is set with `wrangler secret put`.
          bindings: { VORAB_GEHEIMNIS: "nur-fuer-tests", BETREIBER_NAMEN: "betreiber-test", TEST_MIGRATIONS: migrations },
        },
      }),
    ],
    test: {
      setupFiles: ["./test/einrichten.ts"],
      testTimeout: 60_000,
    },
  };
});
