import { defineConfig } from "vitest/config";

// Same testing convention as apps/web (its vitest.config is the precedent): pure-function
// unit tests plus static-markup component tests (renderToStaticMarkup in a node
// environment — no jsdom/browser-event infra; interaction logic lives in pure
// functions/handlers with their own tests).
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
