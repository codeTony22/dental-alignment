import { defineConfig } from "vite";

// This config's own directory — used to pin `root`/`outDir` to absolute paths so the build
// output lands in viewer-standalone/dist/ regardless of which directory `vite build --config
// viewer-standalone/vite.config.ts` is invoked from (it must NEVER land in the main app's
// dist/, since the two build targets are deliberately not entangled).
const configDir = new URL(".", import.meta.url).pathname;

/**
 * Separate, standalone build target — deliberately NOT entangled with the main app's
 * vite.config.ts. Produces exactly one self-contained IIFE JS file (three.js + OrbitControls +
 * STLLoader + this viewer's code, CSS inlined via `?inline` imports at the source level) with
 * no external runtime dependencies, so the Python emitter can inline it verbatim into a
 * generated view.html that works fully offline from file://.
 */
export default defineConfig({
  root: configDir,
  build: {
    outDir: `${configDir}dist`,
    emptyOutDir: true,
    cssCodeSplit: false,
    // No code splitting, no dynamic-import chunks — everything collapses into one file.
    lib: {
      entry: `${configDir}src/standalone.ts`,
      name: "ArtechStandaloneViewer",
      formats: ["iife"],
      fileName: () => "standalone-viewer.iife.js",
    },
    rollupOptions: {
      // No externals: three/OrbitControls/STLLoader must be bundled IN, not left as globals,
      // since the generated view.html has no <script src> for them and no network access.
      // (Vite's lib/iife build already disables code splitting and inlines dynamic imports by
      // default; explicit inlineDynamicImports is redundant here and triggers a build warning.)
      external: [],
    },
    // A single ~30-60MB view.html (base64 STLs dominate) is expected and acceptable for a lab
    // desktop target — don't let vite's default chunk-size warning noise up a clean build.
    chunkSizeWarningLimit: 10_000,
  },
});
