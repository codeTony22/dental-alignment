/**
 * The copied components keep their dev-only debug registries (__artechScene /
 * __artechVerifyScenes) behind the same `import.meta.env.DEV` guard they shipped with in
 * apps/web — fidelity first (grill AM-5). apps/web gets this type from vite/client; this
 * package is not a vite app, so the ONE field the guard reads is declared here rather than
 * pulling vite in as a dependency for a type. Vite (in the consuming app) and vitest both
 * define the value at runtime/build time.
 */
interface ImportMetaEnv {
  readonly DEV: boolean;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
