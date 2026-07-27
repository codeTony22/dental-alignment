/**
 * The library-browser data path: catalog wire mapping (snake_case -> domain), the client's
 * 404-means-old-backend contract (the panel's restart hint keys off ApiError.status), and
 * the session mesh cache that makes card/tab flipping instant (one fetch per part, failures
 * retryable).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchLibraryCatalog, ApiError } from "./client";
import { mapLibraryCatalog } from "./mappers";
import { makeMeshUrlCache } from "./meshCache";
import type { WireLibraryCatalogGroup } from "./wireTypes";

function makeWireGroups(): WireLibraryCatalogGroup[] {
  return [
    {
      model: "zimmer-4.5",
      legacy: false,
      variants: [
        {
          id: "6020",
          variant: "6020",
          label: "zimmer-4.5-6020",
          rim_diameter_mm: 6.16,
          height_mm: 3.38,
          filename: "zimmer-4.5-6020.stl",
          sha256: "deadbeef",
          flags: ["duplicate"],
          duplicate_of: ["neodent-gm/6020"],
          mesh_url: "/api/library/zimmer-4.5/6020/mesh",
        },
        {
          id: "broken",
          variant: "broken",
          label: "broken",
          rim_diameter_mm: null,
          height_mm: null,
          filename: "broken.stl",
          sha256: "beef",
          flags: ["unloadable"],
          duplicate_of: [],
          mesh_url: "/api/library/zimmer-4.5/broken/mesh",
        },
      ],
    },
  ];
}

describe("mapLibraryCatalog", () => {
  it("maps groups and entries snake_case -> domain, nulls preserved", () => {
    const groups = mapLibraryCatalog(makeWireGroups());
    expect(groups).toHaveLength(1);
    const group = groups[0]!;
    expect(group.model).toBe("zimmer-4.5");
    expect(group.legacy).toBe(false);
    expect(group.variants).toHaveLength(2);
    const [dup, broken] = group.variants as [
      (typeof group.variants)[number],
      (typeof group.variants)[number],
    ];
    expect(dup).toEqual({
      id: "6020",
      variant: "6020",
      label: "zimmer-4.5-6020",
      rimDiameterMm: 6.16,
      heightMm: 3.38,
      filename: "zimmer-4.5-6020.stl",
      sha256: "deadbeef",
      flags: ["duplicate"],
      duplicateOf: ["neodent-gm/6020"],
      meshUrl: "/api/library/zimmer-4.5/6020/mesh",
    });
    expect(broken.rimDiameterMm).toBeNull();
    expect(broken.heightMm).toBeNull();
  });
});

describe("fetchLibraryCatalog", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("GETs /api/library and maps the catalog", async () => {
    const spy = vi.fn(async () => new Response(JSON.stringify(makeWireGroups()), { status: 200 }));
    vi.stubGlobal("fetch", spy);
    const groups = await fetchLibraryCatalog();
    const firstCall = spy.mock.calls[0] as unknown as [string];
    expect(firstCall[0]).toBe("/api/library");
    expect(groups[0]?.variants[0]?.duplicateOf).toEqual(["neodent-gm/6020"]);
  });

  it("surfaces a 404 as an ApiError CARRYING status 404 — the old-backend signal the panel's restart hint keys off", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Not Found", { status: 404 })));
    try {
      await fetchLibraryCatalog();
      expect.unreachable("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    }
  });
});

describe("makeMeshUrlCache", () => {
  it("fetches each URL once and hands back the same object URL thereafter", async () => {
    let fetches = 0;
    const cache = makeMeshUrlCache({
      fetchFn: async (url) => {
        fetches += 1;
        return { ok: true, status: 200, statusText: "OK", blob: async () => new Blob([url]) };
      },
      createObjectURL: (blob) => `blob:mock-${fetches}-${blob.size}`,
    });
    const first = await cache("/api/library/a/1/mesh");
    const again = await cache("/api/library/a/1/mesh");
    const other = await cache("/api/library/a/2/mesh");
    expect(first).toBe(again);
    expect(other).not.toBe(first);
    expect(fetches).toBe(2);
  });

  it("does NOT cache failures — the next attempt retries", async () => {
    let attempts = 0;
    const cache = makeMeshUrlCache({
      fetchFn: async () => {
        attempts += 1;
        if (attempts === 1) {
          return { ok: false, status: 500, statusText: "boom", blob: async () => new Blob() };
        }
        return { ok: true, status: 200, statusText: "OK", blob: async () => new Blob(["x"]) };
      },
      createObjectURL: () => "blob:recovered",
    });
    await expect(cache("/mesh")).rejects.toThrowError(/500 boom/);
    await expect(cache("/mesh")).resolves.toBe("blob:recovered");
    expect(attempts).toBe(2);
  });
});
