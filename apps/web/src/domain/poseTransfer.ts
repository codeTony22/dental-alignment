/**
 * POSE IMPORT / EXPORT — a seated alignment as a portable, auditable document.
 *
 * Client gap (RealGUIDE screenshot parity, 2026-07-25): their workflow can carry an alignment
 * between sessions and machines. Ours could not — a seat lived only in the run folder that
 * produced it, so a case reopened on another workstation started from zero even though the
 * pose was already earned.
 *
 * WHAT A POSE FILE MUST CARRY, and why each part is not optional:
 *  - THE POSE MATRIX. A 4x4 rigid transform in the jaw's world frame, exactly as
 *    "<case>-<tooth>-implant.json" writes it (row-major; rotation columns + translation).
 *  - THE SELECTION THAT PRODUCED IT. A pose is meaningless without the part it poses: implant
 *    system, cap variant, construction part, jaw, gingival relief. Restoring a matrix against a
 *    DIFFERENT part is not "restoring an alignment", it is seating the wrong object precisely.
 *    That is why the system and the jaw are import BLOCKERS rather than warnings.
 *  - THE PROVENANCE. Which operator adjustments the pose already contains (rotation nudge total,
 *    which instrument anchored the rotation and whether it was verifiable, the doctor's sign-off)
 *    — so the receiving operator reads a seat's history rather than inheriting an anonymous
 *    matrix. Audit data only: never a computation input.
 *
 * IMPORT IS AN OPERATOR WRITE, so it obeys the same rule as the nudge, align-to-mark and
 * correspondence flows: the client PROPOSES, the server's gates judge, the write is audited.
 * Nothing in this module applies a pose — it builds, parses and JUDGES COMPATIBILITY, which is
 * the client's half of that contract (catching what the operator can see before a round trip).
 *
 * Framework-free and pure: no React, no fetch, no clock (the export timestamp is passed in).
 */
import type { Jaw, SeatMethod, SeedSource, Vec3 } from "./types";
import { asJaw } from "./types";

/** The envelope's discriminator: a file that does not say this is not one of ours. */
export const POSE_TRANSFER_FORMAT = "artech.pose-transfer";
/** The schema version this build writes AND the newest it can read. */
export const POSE_TRANSFER_VERSION = 1;

/**
 * How far a hand-edited matrix may drift from rigid before it is refused. A pose transfer must
 * be a RIGID motion — a matrix that scales or shears would silently resize the library part
 * against the scan, which is exactly the "precisely wrong" failure the format exists to avoid.
 * 1e-3 passes ordinary float round-tripping through JSON and refuses anything meaningful.
 */
export const POSE_RIGID_TOLERANCE = 1e-3;

export type PoseRow4 = readonly [number, number, number, number];
export type PoseMatrix = readonly [PoseRow4, PoseRow4, PoseRow4, PoseRow4];

/** The choices the pose was produced under (LibrarySelection's shipped half, per document). */
export interface PoseTransferSelection {
  readonly model: string | null;
  readonly constructionPathId: string | null;
  readonly jaw: Jaw;
  readonly gingivalOffsetMm: number;
}

/** Which operator adjustments the exported pose already contains. Audit read-out only. */
export interface PoseTransferProvenance {
  readonly seedSource: SeedSource | null;
  readonly seatMethod: SeatMethod | null;
  /** The operator's running rotation total on this site (null = never nudged). */
  readonly nudgeCumulativeDeg: number | null;
  readonly rotationUnverified: boolean | null;
  readonly clockEvidence: string | null;
  /** What the automation MEASURED the cap to be — kept beside the declared variant so a
   *  disagreement travels with the pose instead of being lost at the export boundary. */
  readonly identifiedVariant: string | null;
  readonly doctorConfirmed: boolean | null;
  readonly doctorNote: string | null;
  readonly doctorConfirmedAt: string | null;
}

export interface PoseTransferSite {
  readonly tooth: number;
  /** The DECLARED cap for this site — the operator's choice, not the measurement. */
  readonly variantId: string | null;
  readonly poseMatrix: PoseMatrix;
  readonly provenance: PoseTransferProvenance;
}

export interface PoseTransferDocument {
  readonly format: string;
  readonly version: number;
  readonly caseId: string;
  readonly exportedAt: string;
  readonly selection: PoseTransferSelection;
  readonly sites: readonly PoseTransferSite[];
}

// ---- BUILDING (export) ----------------------------------------------------------------------

/** The seated pose as the viewer already holds it (api/mappers' `mapImplantPose` output). */
export interface SeatedPose {
  readonly position: Vec3;
  readonly axisX: Vec3;
  readonly axisY: Vec3;
  readonly axisZ: Vec3;
}

/**
 * The 4x4 row-major matrix for a seated pose — the exact inverse of the column extraction
 * `mapImplantPose` performs on implant.json, so a pose exported here reads back identical to
 * the file the pipeline wrote (pinned by a round-trip test).
 */
export function poseMatrixFrom(pose: SeatedPose): PoseMatrix {
  const row = (i: 0 | 1 | 2): PoseRow4 => [
    pose.axisX[i],
    pose.axisY[i],
    pose.axisZ[i],
    pose.position[i],
  ];
  return [row(0), row(1), row(2), [0, 0, 0, 1]];
}

/** A run row, as far as the provenance cares (structurally satisfied by RunSiteResult). */
export interface PoseSourceRow {
  readonly tooth: number;
  readonly seedSource: SeedSource;
  readonly seatMethod: SeatMethod | null;
  readonly clocking: { readonly rotationUnverified: boolean; readonly evidence: string } | null;
  readonly nudge: { readonly cumulativeDeg: number } | null;
  readonly doctorConfirmation:
    | { readonly confirmed: boolean; readonly note: string | null; readonly ts: string }
    | null;
  readonly variant: { readonly declared: string | null; readonly identified: string };
}

/** Everything absent, for a site exported without a run row behind it (never happens through
 *  the UI — a pose only exists after a run — but the shape must be total, not thrown. */
const EMPTY_PROVENANCE: PoseTransferProvenance = {
  seedSource: null,
  seatMethod: null,
  nudgeCumulativeDeg: null,
  rotationUnverified: null,
  clockEvidence: null,
  identifiedVariant: null,
  doctorConfirmed: null,
  doctorNote: null,
  doctorConfirmedAt: null,
};

export function provenanceFrom(row: PoseSourceRow | null): PoseTransferProvenance {
  if (row === null) return EMPTY_PROVENANCE;
  return {
    seedSource: row.seedSource,
    seatMethod: row.seatMethod,
    nudgeCumulativeDeg: row.nudge?.cumulativeDeg ?? null,
    rotationUnverified: row.clocking?.rotationUnverified ?? null,
    clockEvidence: row.clocking?.evidence ?? null,
    identifiedVariant: row.variant.identified,
    doctorConfirmed: row.doctorConfirmation?.confirmed ?? null,
    doctorNote: row.doctorConfirmation?.note ?? null,
    doctorConfirmedAt: row.doctorConfirmation?.ts ?? null,
  };
}

export interface PoseTransferSource {
  readonly caseId: string;
  /** Passed in, never read from the ambient clock — the builder stays a pure function. */
  readonly exportedAt: Date;
  readonly selection: PoseTransferSelection;
  readonly rows: readonly PoseSourceRow[];
  /** tooth -> the seated pose the viewer fetched for its triad; a tooth absent here has no
   *  exportable pose (no run yet, or implant.json could not be read). */
  readonly poses: ReadonlyMap<number, SeatedPose>;
  /** tooth -> the operator's declared cap (the confirm row / library selection). */
  readonly declaredByTooth: ReadonlyMap<number, string | null>;
  /** Restrict the export to these teeth; omit for the whole case. */
  readonly onlyTeeth?: readonly number[];
}

export interface PoseTransferBuild {
  readonly document: PoseTransferDocument;
  /** Teeth that were asked for but have no pose to export — reported, never silently dropped. */
  readonly skippedTeeth: readonly number[];
}

/**
 * Build the document for one site or the whole case. Sites without a seated pose are SKIPPED
 * AND REPORTED: an export that quietly contained three of four sites would be discovered on
 * the importing machine, which is the worst possible place to discover it.
 */
export function buildPoseTransfer(source: PoseTransferSource): PoseTransferBuild {
  const wanted =
    source.onlyTeeth === undefined
      ? source.rows.map((r) => r.tooth)
      : source.rows.map((r) => r.tooth).filter((t) => source.onlyTeeth?.includes(t));
  const sites: PoseTransferSite[] = [];
  const skippedTeeth: number[] = [];
  for (const tooth of wanted) {
    const pose = source.poses.get(tooth);
    if (pose === undefined) {
      skippedTeeth.push(tooth);
      continue;
    }
    const row = source.rows.find((r) => r.tooth === tooth) ?? null;
    sites.push({
      tooth,
      variantId: source.declaredByTooth.get(tooth) ?? row?.variant.declared ?? null,
      poseMatrix: poseMatrixFrom(pose),
      provenance: provenanceFrom(row),
    });
  }
  return {
    document: {
      format: POSE_TRANSFER_FORMAT,
      version: POSE_TRANSFER_VERSION,
      caseId: source.caseId,
      exportedAt: source.exportedAt.toISOString(),
      selection: source.selection,
      sites,
    },
    skippedTeeth,
  };
}

/** The document as a file's contents: stable key order (the interfaces' own), 2-space indent —
 *  two exports of the same state differ only in `exportedAt`, so files stay diffable. */
export function serializePoseTransfer(doc: PoseTransferDocument): string {
  return `${JSON.stringify(doc, null, 2)}\n`;
}

/** "276794487-zimmer-4.5-3-pose.json" for one site, "…-pose.json" for the case. Path
 *  separators are stripped — a case id is a folder name, and a filename is not a path. */
export function poseTransferFilename(caseId: string, tooth: number | null): string {
  const safe = caseId.replace(/[/\\]/g, "-");
  return tooth === null ? `${safe}-pose.json` : `${safe}-${tooth}-pose.json`;
}

// ---- PARSING (import) -----------------------------------------------------------------------

export type PoseTransferParse =
  | { readonly kind: "ok"; readonly document: PoseTransferDocument }
  | { readonly kind: "error"; readonly message: string };

function err(message: string): PoseTransferParse {
  return { kind: "error", message };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

/** A closed-set field read back as its own union — an unrecognised value becomes null rather
 *  than being cast into a type it does not belong to. */
function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : null;
}

/** A 4x4 of finite numbers whose bottom row is [0,0,0,1] and whose rotation block is RIGID
 *  (orthonormal columns, right-handed). Returns the matrix, or the sentence to show. */
export function parsePoseMatrix(value: unknown, where: string): PoseMatrix | string {
  if (!Array.isArray(value) || value.length !== 4) return `${where}: the pose matrix must be 4 rows.`;
  const rows: PoseRow4[] = [];
  for (const raw of value) {
    if (!Array.isArray(raw) || raw.length !== 4) return `${where}: every pose matrix row needs 4 numbers.`;
    const [a, b, c, d] = [
      finiteNumber(raw[0]),
      finiteNumber(raw[1]),
      finiteNumber(raw[2]),
      finiteNumber(raw[3]),
    ];
    if (a === null || b === null || c === null || d === null) {
      return `${where}: the pose matrix holds a value that is not a number.`;
    }
    rows.push([a, b, c, d]);
  }
  // built element-by-element rather than cast: the tuple type is earned, not asserted
  const [r0, r1, r2, r3] = rows;
  if (r0 === undefined || r1 === undefined || r2 === undefined || r3 === undefined) {
    return `${where}: the pose matrix must be 4 rows.`;
  }
  const matrix: PoseMatrix = [r0, r1, r2, r3];
  const bottom = matrix[3];
  if (
    Math.abs(bottom[0]) > POSE_RIGID_TOLERANCE ||
    Math.abs(bottom[1]) > POSE_RIGID_TOLERANCE ||
    Math.abs(bottom[2]) > POSE_RIGID_TOLERANCE ||
    Math.abs(bottom[3] - 1) > POSE_RIGID_TOLERANCE
  ) {
    return `${where}: the pose matrix's last row must be [0, 0, 0, 1] — this is not a rigid placement.`;
  }
  if (!rotationIsRigid(matrix)) {
    return `${where}: the pose matrix scales or shears the part — a pose transfer must be a rigid placement.`;
  }
  return matrix;
}

function column(m: PoseMatrix, j: 0 | 1 | 2): Vec3 {
  return [m[0][j], m[1][j], m[2][j]];
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/** Orthonormal columns with a right-handed (det ≈ +1) triple — i.e. a rotation, not a mirror,
 *  a scale or a shear. Checked directly rather than trusting the writer. */
function rotationIsRigid(m: PoseMatrix): boolean {
  const x = column(m, 0);
  const y = column(m, 1);
  const z = column(m, 2);
  for (const axis of [x, y, z]) {
    if (Math.abs(Math.sqrt(dot(axis, axis)) - 1) > POSE_RIGID_TOLERANCE) return false;
  }
  if (Math.abs(dot(x, y)) > POSE_RIGID_TOLERANCE) return false;
  if (Math.abs(dot(x, z)) > POSE_RIGID_TOLERANCE) return false;
  if (Math.abs(dot(y, z)) > POSE_RIGID_TOLERANCE) return false;
  const cross: Vec3 = [
    x[1] * y[2] - x[2] * y[1],
    x[2] * y[0] - x[0] * y[2],
    x[0] * y[1] - x[1] * y[0],
  ];
  return Math.abs(dot(cross, z) - 1) <= POSE_RIGID_TOLERANCE;
}

/**
 * Read a pose file. Every refusal is a sentence an operator can act on — "not an ArTech pose
 * file", "written by a newer build", "the matrix shears the part" — never a parser stack.
 */
export function parsePoseTransfer(text: string): PoseTransferParse {
  let raw: unknown;
  try {
    raw = JSON.parse(text) as unknown;
  } catch {
    return err("That file is not JSON — pick a pose file exported from this app.");
  }
  if (!isRecord(raw)) return err("That file is not an ArTech pose transfer (expected a JSON object).");
  if (raw.format !== POSE_TRANSFER_FORMAT) {
    return err(
      `That file is not an ArTech pose transfer (its format is “${String(raw.format ?? "missing")}”).`,
    );
  }
  const version = finiteNumber(raw.version);
  if (version === null) return err("The pose file does not say which version it was written in.");
  if (version > POSE_TRANSFER_VERSION) {
    return err(
      `That pose file was written by a newer build (v${version}); this one reads up to v${POSE_TRANSFER_VERSION}.`,
    );
  }
  const caseId = optionalString(raw.caseId);
  if (caseId === null) return err("The pose file does not name the case it came from.");
  const selectionRaw = raw.selection;
  if (!isRecord(selectionRaw)) {
    return err("The pose file carries no selection — a pose without its part cannot be restored.");
  }
  if (selectionRaw.jaw !== "upper" && selectionRaw.jaw !== "lower") {
    return err("The pose file does not say which jaw it was produced for.");
  }
  const selection: PoseTransferSelection = {
    model: optionalString(selectionRaw.model),
    constructionPathId: optionalString(selectionRaw.constructionPathId),
    jaw: asJaw(selectionRaw.jaw),
    gingivalOffsetMm: finiteNumber(selectionRaw.gingivalOffsetMm) ?? 0,
  };
  if (!Array.isArray(raw.sites) || raw.sites.length === 0) {
    return err("The pose file holds no sites.");
  }
  const sites: PoseTransferSite[] = [];
  for (const siteRaw of raw.sites) {
    if (!isRecord(siteRaw)) return err("The pose file holds a site that is not an object.");
    const tooth = finiteNumber(siteRaw.tooth);
    if (tooth === null || !Number.isInteger(tooth)) {
      return err("The pose file holds a site with no tooth number.");
    }
    const matrix = parsePoseMatrix(siteRaw.poseMatrix, `Tooth ${tooth}`);
    if (typeof matrix === "string") return err(matrix);
    const prov = isRecord(siteRaw.provenance) ? siteRaw.provenance : {};
    sites.push({
      tooth,
      variantId: optionalString(siteRaw.variantId),
      poseMatrix: matrix,
      provenance: {
        seedSource: oneOf<SeedSource>(prov.seedSource, ["brush", "marks", "click"]),
        seatMethod: oneOf<SeatMethod>(prov.seatMethod, ["rim", "icp"]),
        nudgeCumulativeDeg: finiteNumber(prov.nudgeCumulativeDeg),
        rotationUnverified: typeof prov.rotationUnverified === "boolean" ? prov.rotationUnverified : null,
        clockEvidence: optionalString(prov.clockEvidence),
        identifiedVariant: optionalString(prov.identifiedVariant),
        doctorConfirmed: typeof prov.doctorConfirmed === "boolean" ? prov.doctorConfirmed : null,
        doctorNote: optionalString(prov.doctorNote),
        doctorConfirmedAt: optionalString(prov.doctorConfirmedAt),
      },
    });
  }
  return {
    kind: "ok",
    document: {
      format: POSE_TRANSFER_FORMAT,
      version,
      caseId,
      exportedAt: optionalString(raw.exportedAt) ?? "",
      selection,
      sites,
    },
  };
}

// ---- COMPATIBILITY (the client's half of the gate) -------------------------------------------

/** The case the file is about to be imported INTO. */
export interface ImportTarget {
  readonly caseId: string;
  readonly selection: PoseTransferSelection;
  /** The teeth that currently have confirm rows — a pose can only land on an existing site. */
  readonly siteTeeth: readonly number[];
  readonly declaredByTooth: ReadonlyMap<number, string | null>;
}

export interface ImportCompatibility {
  /** Reasons the import must not be proposed at all. */
  readonly blockers: readonly string[];
  /** Differences the operator should see but which do not by themselves make it wrong. */
  readonly warnings: readonly string[];
  /** The teeth that would actually be proposed (present in both the file and the case). */
  readonly teeth: readonly number[];
}

/**
 * Judge a parsed file against the case in front of the operator. The two BLOCKERS are the two
 * ways a restored matrix would seat the wrong object precisely: a different implant system (the
 * variant ids belong to one system's catalog) and a different jaw (a pose is expressed in that
 * jaw's world frame). Everything else is a warning the operator reads and decides on.
 *
 * The server judges this again — this is the client half, so the operator sees the mismatch
 * before a round trip, exactly like `missingSelections` does for the run.
 */
export function importCompatibility(
  doc: PoseTransferDocument,
  target: ImportTarget,
): ImportCompatibility {
  const blockers: string[] = [];
  const warnings: string[] = [];

  if (doc.selection.jaw !== target.selection.jaw) {
    blockers.push(
      `the file was produced for the ${doc.selection.jaw} jaw, this case is selected for the ${target.selection.jaw} jaw`,
    );
  }
  if (doc.selection.model !== target.selection.model) {
    blockers.push(
      `the file names implant system “${doc.selection.model ?? "none"}”, this case is set to “${target.selection.model ?? "none"}”`,
    );
  }
  const matched = doc.sites.map((s) => s.tooth).filter((t) => target.siteTeeth.includes(t));
  const unmatched = doc.sites.map((s) => s.tooth).filter((t) => !target.siteTeeth.includes(t));
  if (matched.length === 0) {
    blockers.push(
      `none of the file's teeth (${doc.sites.map((s) => s.tooth).join(", ")}) has a site in this case`,
    );
  }

  if (doc.caseId !== target.caseId) {
    warnings.push(`the file was exported from case ${doc.caseId}, not ${target.caseId}`);
  }
  if (doc.selection.constructionPathId !== target.selection.constructionPathId) {
    warnings.push(
      `the construction part differs (file: ${doc.selection.constructionPathId ?? "none"}, case: ${target.selection.constructionPathId ?? "none"})`,
    );
  }
  if (doc.selection.gingivalOffsetMm !== target.selection.gingivalOffsetMm) {
    warnings.push(
      `the gingival relief differs (file: ${doc.selection.gingivalOffsetMm} mm, case: ${target.selection.gingivalOffsetMm} mm)`,
    );
  }
  if (unmatched.length > 0) {
    warnings.push(`tooth ${unmatched.join(", ")} has no site in this case and will be skipped`);
  }
  for (const site of doc.sites) {
    if (!matched.includes(site.tooth)) continue;
    const here = target.declaredByTooth.get(site.tooth) ?? null;
    if (site.variantId !== here) {
      warnings.push(
        `tooth ${site.tooth} declares “${here ?? "no cap"}” here but “${site.variantId ?? "no cap"}” in the file`,
      );
    }
  }
  return { blockers, warnings, teeth: matched };
}

export function canImport(compatibility: ImportCompatibility): boolean {
  return compatibility.blockers.length === 0;
}

/** One line per site for the panel's "what this file holds" summary — the adjustments the pose
 *  already contains, in the operator's language. */
export function describeImportSite(site: PoseTransferSite): string {
  const parts: string[] = [`tooth ${site.tooth}`, site.variantId ?? "no cap declared"];
  if (site.provenance.seatMethod !== null) parts.push(`${site.provenance.seatMethod} seat`);
  if (site.provenance.nudgeCumulativeDeg !== null && site.provenance.nudgeCumulativeDeg !== 0) {
    parts.push(`operator rotation ${site.provenance.nudgeCumulativeDeg > 0 ? "+" : ""}${site.provenance.nudgeCumulativeDeg}°`);
  }
  if (site.provenance.rotationUnverified === true) parts.push("rotation unverified");
  if (site.provenance.doctorConfirmed === true) parts.push("doctor-confirmed");
  return parts.join(" · ");
}
