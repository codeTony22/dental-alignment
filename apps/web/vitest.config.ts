import { defineConfig } from "vitest/config";

// Pure-function unit tests plus static-markup component tests (renderToStaticMarkup in a
// node environment — no jsdom/browser-event infra; interaction logic lives in pure
// functions/handlers with their own tests). Also covers viewer-standalone/src (its own
// vite BUILD target, but sharing this one test runner keeps `pnpm test` a single green
// gate for the whole package).
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}", "viewer-standalone/src/**/*.test.ts"],
  },
});
