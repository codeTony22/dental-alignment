/**
 * Client-side part-mesh cache: fetch each library STL ONCE per session and hand the viewer a
 * blob object-URL thereafter, so flipping between catalog cards/tabs (and the compare pane
 * following the active site) feels instant instead of re-downloading the same immutable file. Library
 * CADs are immutable on disk and small (~200 KB each, ~26 files total), so entries are kept
 * for the session and never revoked — bounded by the catalog size, not by usage.
 *
 * Failures are NOT cached: a failed fetch is deleted from the map so the next attempt retries
 * (a transient network error must not permanently poison a part).
 *
 * Built as a factory (injectable fetch/createObjectURL) per the repo convention: the IO edges
 * are parameterized so the caching logic is unit-testable in the node test environment.
 */

export type MeshUrlResolver = (url: string) => Promise<string>;

interface MeshCacheDeps {
  readonly fetchFn: (url: string) => Promise<Pick<Response, "ok" | "status" | "statusText" | "blob">>;
  readonly createObjectURL: (blob: Blob) => string;
}

export function makeMeshUrlCache(deps: MeshCacheDeps): MeshUrlResolver {
  const cache = new Map<string, Promise<string>>();
  return (url: string): Promise<string> => {
    const existing = cache.get(url);
    if (existing !== undefined) return existing;
    const pending = (async () => {
      const res = await deps.fetchFn(url);
      if (!res.ok) {
        throw new Error(`Loading the part mesh failed (${res.status} ${res.statusText})`);
      }
      return deps.createObjectURL(await res.blob());
    })();
    cache.set(url, pending);
    pending.catch(() => cache.delete(url));
    return pending;
  };
}

/** The app's shared instance — browser fetch + real object URLs, one cache for the session. */
export const cachedMeshUrl: MeshUrlResolver = makeMeshUrlCache({
  fetchFn: (url) => fetch(url),
  createObjectURL: (blob) => URL.createObjectURL(blob),
});
