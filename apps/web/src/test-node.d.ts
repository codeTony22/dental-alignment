/**
 * Minimal ambient typing for the ONE node builtin a test file reads the stylesheet with
 * (noticeOverlay.test.ts — review 2026-07-26: the notice overlay's pointer contract can
 * only be pinned as CSS text; vitest stubs `.css?raw` imports to "" in this node-env
 * suite). The app bundle never imports node builtins, and @types/node stays out of the
 * app's type surface on purpose — this declares exactly what that test calls, no more.
 */
declare module "node:fs" {
  export function readFileSync(path: string | URL, encoding: "utf8"): string;
}
