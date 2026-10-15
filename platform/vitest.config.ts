// Unit tests run offline; integration tests (tests/*.integration.test.ts) need SANDBOX_INTEGRATION=1.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    pool: "forks",
    include: ["tests/**/*.test.ts"],
    testTimeout: 20_000,
    hookTimeout: 60_000,
  },
});
