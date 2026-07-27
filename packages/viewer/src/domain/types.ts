/**
 * THE VIEWER'S DOMAIN-TYPE CLOSURE — the subset of the frozen demo's domain/types.ts that
 * the copied viewer stack actually imports (copy-debt ledger row 3; plan §3/AM-5).
 *
 * The demo's types.ts is 1,008 lines of workflow vocabulary (cases, sites, runs, guidance,
 * capture verdicts…). The viewer modules import exactly ONE name from it — Vec3, used by
 * VerifyViewer's frame prop and siteRouting's coordinates — so exactly one name is copied.
 * Copying the rest would smuggle the demo's workflow model into a package whose whole point
 * is to stay presentational (plan §1.3: presentation may not do the physics); the product
 * app already models its own payloads against the BFF's shapes.
 */

export type Vec3 = readonly [number, number, number];
