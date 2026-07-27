import { defineConfig } from "vitest/config";

// Same testing convention as apps/web, where these files were copied FROM (its
// vitest.config is the precedent): pure-function unit tests in a node environment —
// no jsdom/browser-event infra. The copied geometry/colour/routing tests run verbatim;
// WebGL construction-time behavior stays browser-only and is documented, not faked
// (see sceneController.characterization.test.ts's header for that boundary).
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
