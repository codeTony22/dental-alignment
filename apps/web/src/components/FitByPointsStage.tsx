import { useEffect, useMemo, useState } from "react";
import type { Vec3 } from "../domain/types";
import type { PartFeature } from "../domain/partFeatures";
import { anchorableFeatures, canAddFreePoint, freePointNumber } from "../domain/correspondence";
import { CorrespondencePanel, type CorrespondenceControls } from "./CorrespondencePanel";
import { CAP_REGION_RADIUS_MM, cropTrianglesNear } from "../viewer/meshCrop";
import { canonicalFromRaw, computePartFrame, rawFromCanonical, rawFromFeature } from "../viewer/partFrame";
import { FEATURE_COLOR, FREE_POINT_COLOR, PALETTE } from "../viewer/palette";
import { scanPositionsFor } from "../viewer/scanPositions";
import { loadStlPositions, type VerifyMarker } from "../viewer/verifyScene";
import { cachedMeshUrl } from "../api/meshCache";
import { VerifyViewer } from "../viewer/VerifyViewer";

export interface FitByPointsStageProps {
  readonly caseId: string;
  readonly tooth: number;
  /** The library part being matched: the catalog model + entry id the row actually shipped. */
  readonly model: string;
  readonly variant: string;
  /** That part's mesh, so the LEFT pane can show the very file the marks were placed on.
   *  Null when the catalog could not resolve it — the pane says so rather than showing nothing. */
  readonly partMeshUrl: string | null;
  /** Where on the arch this site is — the RIGHT pane's crop centre (the operator's own mark). */
  readonly siteCenter: Vec3 | null;
  /** Everything the pair list needs; the same controls the in-table panel used to take, so the
   *  arm/place/apply transitions still live in App (repo convention). */
  readonly controls: CorrespondenceControls;
  /** A click on the SCAN pane, in world coordinates — the placement half of the flow. */
  readonly onPickScanPoint: (point: Vec3) => void;
  readonly onClose: () => void;
}

/** Pair k and library feature k must wear the SAME number — that is the whole legibility of the
 *  flow, and it is why the numbering is derived here (once) rather than per pane. Free points
 *  carry their own positional numbers (freePointNumber) in the free-point color, so the two
 *  numbering runs cannot be mistaken for one another. */
function numbering(features: readonly PartFeature[]): ReadonlyMap<string, string> {
  const map = new Map<string, string>();
  anchorableFeatures(features).forEach((f, i) => map.set(f.id, String(i + 1)));
  return map;
}

/**
 * The part pane's overlay, or null when the pane needs none — extracted pure so the
 * frame-refused reason (which a static render cannot reach: positions only load in effects)
 * is still pinned by a unit test. A refused frame DISABLES free-point placement, and this
 * sentence is the stated reason the spec demands instead of a silent no-op.
 *
 * TWO TONES (review 2026-07-26): "veil" states why the pane has nothing usable beneath and
 * may cover it; "invite" asks for a click ON the pane it sits over, so it renders as a
 * non-blocking strip — the full-bleed veil used to swallow exactly the click it invited,
 * leaving a zero-anchorable part inert. The invitation also clears once the operator has a
 * free point placed or armed: the caption counts the points from there.
 */
export function partPaneNotice(args: {
  readonly partError: string | null;
  readonly partMeshUrl: string | null;
  readonly hasPositions: boolean;
  readonly hasFrame: boolean;
  readonly featureMarkerCount: number;
  readonly freePointCount: number;
  readonly model: string;
  readonly variant: string;
}): { readonly text: string; readonly tone: "veil" | "invite" } | null {
  if (args.partError) return { text: args.partError, tone: "veil" };
  if (args.partMeshUrl === null) {
    return {
      text: `The library part for ${args.model}/${args.variant} is not in the catalog.`,
      tone: "veil",
    };
  }
  if (!args.hasPositions) return { text: "loading the library part…", tone: "veil" };
  if (!args.hasFrame) {
    return {
      text:
        "This part's geometry gives no derivable frame — its marks cannot be drawn here, " +
        "and free points cannot be placed on it.",
      tone: "veil",
    };
  }
  if (args.featureMarkerCount === 0 && args.freePointCount === 0) {
    return {
      text:
        "This part carries no feature that can anchor a rotation — click the part itself " +
        "to place a free numbered point.",
      tone: "invite",
    };
  }
  return null;
}

/**
 * FIT BY POINTS — the correspondence flow as the client actually described it (2026-07-26):
 * "numbered points on the scan AND on the library part, side by side".
 *
 * The machinery behind it shipped in 2026-07-24 (GET/PUT library features, POST
 * align-to-correspondence) but lived inside a rotation control, inside a cell, inside a
 * fifteen-column table that scrolls sideways — the client could not find it. Nothing about the
 * contract changes here; what changes is that it is a STAGE: the part on the left with its marked
 * features numbered, the scanned cap on the right where the matching spots are clicked, and the
 * pair list between them.
 *
 * The two panes are deliberately unlinked. Their frames are unrelated (a 6 mm part in its own
 * local frame, a cap region out in the scanner's world) and, more to the point, the operator is
 * looking for the SAME landmark from whatever angle shows it best in each — mirroring the orbit
 * would fight that.
 *
 * FREE POINTS (client ask 2026-07-26: "only let me mark one point of the trench, but the other
 * software adds to like the picture I once gave you"): clicking the part pane DIRECTLY places
 * the next numbered free point there — partFrame maps the raw click into the canonical frame
 * the server measures in — and immediately arms the scan pane for its match, exactly like the
 * feature flow. On this catalog the detector reads ONE rotation-defining feature, so without
 * free points the operator was stranded at one pair while the part visibly carries a second
 * cutout.
 */
export function FitByPointsStage({
  caseId,
  tooth,
  model,
  variant,
  partMeshUrl,
  siteCenter,
  controls,
  onPickScanPoint,
  onClose,
}: FitByPointsStageProps) {
  const [scanPositions, setScanPositions] = useState<Float32Array | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [partPositions, setPartPositions] = useState<Float32Array | null>(null);
  const [partError, setPartError] = useState<string | null>(null);

  /**
   * Escape backs out ONE level: an armed pick (a named feature OR a free point waiting for its
   * scan match) is disarmed, otherwise the stage closes. Registered in the CAPTURE phase and
   * propagation-stopped so the workflow's own global Escape handler never also fires — it would
   * cancel this flow's arm behind the stage's back, leaving the pane still saying "waiting for
   * point 2".
   */
  const armedFeatureId = controls.armedFeatureId;
  const armedFreePoint = controls.armedFreePoint;
  const onCancelArm = controls.onCancelArm;
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      if (armedFeatureId !== null || armedFreePoint !== null) onCancelArm();
      else onClose();
    };
    window.addEventListener("keydown", handler, true);
    return () => window.removeEventListener("keydown", handler, true);
  }, [armedFeatureId, armedFreePoint, onCancelArm, onClose]);

  useEffect(() => {
    let cancelled = false;
    setScanError(null);
    scanPositionsFor(caseId)
      .then((positions) => {
        if (!cancelled) setScanPositions(positions);
      })
      .catch((err: unknown) => {
        if (!cancelled) setScanError(err instanceof Error ? err.message : "Failed to load the scan.");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  useEffect(() => {
    if (partMeshUrl === null) {
      setPartPositions(null);
      return undefined;
    }
    let cancelled = false;
    setPartError(null);
    cachedMeshUrl(partMeshUrl)
      .then((url) => loadStlPositions(url))
      .then((positions) => {
        if (!cancelled) setPartPositions(positions);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPartError(err instanceof Error ? err.message : "Failed to load the library part.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [partMeshUrl]);

  const scanCrop = useMemo(() => {
    if (scanPositions === null || siteCenter === null) return null;
    return cropTrianglesNear(scanPositions, siteCenter, CAP_REGION_RADIUS_MM);
  }, [scanPositions, siteCenter]);

  const scanLayers = useMemo(
    () => [
      {
        id: "scan",
        geometry:
          scanCrop && scanCrop.length > 0 ? { positions: scanCrop, color: PALETTE.arch } : null,
        visible: true,
        opacity: 1,
      },
    ],
    [scanCrop],
  );

  const partLayers = useMemo(
    () => [
      {
        id: "part",
        geometry: partPositions ? { positions: partPositions, color: PALETTE.cap } : null,
        visible: true,
        opacity: 1,
      },
    ],
    [partPositions],
  );

  const labels = useMemo(() => numbering(controls.features), [controls.features]);

  /**
   * The library part's numbered marks, drawn on the very mesh they were placed on. The frame is
   * DERIVED from that mesh (see viewer/partFrame): a part whose geometry cannot justify a frame
   * gets no markers and the pane says why, rather than putting numbers somewhere plausible.
   */
  const partFrame = useMemo(
    () => (partPositions ? computePartFrame(partPositions) : null),
    [partPositions],
  );

  /** How many free points are already placed — the next free click becomes point N+1. */
  const freeCount = controls.pairs.filter((p) => p.featureId === null).length;

  const featureMarkers: readonly VerifyMarker[] = useMemo(() => {
    if (partFrame === null) return [];
    const paired = new Set(
      controls.pairs.map((p) => p.featureId).filter((id): id is string => id !== null),
    );
    return anchorableFeatures(controls.features).map((feature) => ({
      key: feature.id,
      position: rawFromFeature(partFrame, feature),
      color: FEATURE_COLOR[feature.kind],
      label: labels.get(feature.id) ?? "•",
      // a feature not yet matched on the scan reads as an OFFER, not as a recorded pair
      pending: !paired.has(feature.id),
    }));
  }, [partFrame, controls.features, controls.pairs, labels]);

  /**
   * The FREE POINTS on the part pane (client ask 2026-07-26): every recorded free pair's part
   * click mapped back onto the previewed mesh, plus — while a free point waits for its scan
   * match — the armed click itself, pending, already wearing the number its pair will get.
   * Same positional numbers the pair list and the server's audit labels use.
   */
  const freePartMarkers: readonly VerifyMarker[] = useMemo(() => {
    if (partFrame === null) return [];
    const placed: VerifyMarker[] = controls.pairs.flatMap((pair, index) => {
      if (pair.partPoint === null) return [];
      const n = freePointNumber(controls.pairs, index) ?? index + 1;
      return [
        {
          key: `point-${n}`,
          position: rawFromCanonical(partFrame, pair.partPoint),
          color: FREE_POINT_COLOR,
          label: String(n),
        },
      ];
    });
    if (controls.armedFreePoint !== null) {
      placed.push({
        key: "point-armed",
        position: rawFromCanonical(partFrame, controls.armedFreePoint),
        color: FREE_POINT_COLOR,
        label: String(freeCount + 1),
        // its scan match is still awaited — an offer in flight, not a recorded pair
        pending: true,
      });
    }
    return placed;
  }, [partFrame, controls.pairs, controls.armedFreePoint, freeCount]);

  const partMarkers: readonly VerifyMarker[] = useMemo(
    () => [...featureMarkers, ...freePartMarkers],
    [featureMarkers, freePartMarkers],
  );

  const scanMarkers: readonly VerifyMarker[] = useMemo(
    () =>
      controls.pairs.map((pair, index) => {
        if (pair.featureId !== null) {
          return {
            key: pair.featureId,
            position: pair.scanPoint,
            color: pair.kind !== null ? FEATURE_COLOR[pair.kind] : FREE_POINT_COLOR,
            label: labels.get(pair.featureId) ?? "•",
          };
        }
        const n = freePointNumber(controls.pairs, index) ?? index + 1;
        return {
          key: `point-${n}`,
          position: pair.scanPoint,
          color: FREE_POINT_COLOR,
          label: String(n),
        };
      }),
    [controls.pairs, labels],
  );

  const armedLabel =
    controls.armedFeatureId !== null
      ? labels.get(controls.armedFeatureId) ?? "•"
      : controls.armedFreePoint !== null
        ? String(freeCount + 1)
        : null;

  const partNotice = partPaneNotice({
    partError,
    partMeshUrl,
    hasPositions: partPositions !== null,
    hasFrame: partFrame !== null,
    featureMarkerCount: featureMarkers.length,
    // placed free pairs plus an armed one — either means the invitation has been taken up
    freePointCount: freeCount + (controls.armedFreePoint !== null ? 1 : 0),
    model,
    variant,
  });

  const scanNotice = (() => {
    if (scanError) return scanError;
    if (siteCenter === null) return "This site has no marked centre.";
    if (scanPositions === null) return "loading the scan…";
    if (scanCrop !== null && scanCrop.length === 0) {
      return `No scan surface within ${CAP_REGION_RADIUS_MM} mm of this site's mark.`;
    }
    return null;
  })();

  return (
    <div className="decode-dialog-backdrop">
      <section
        className="fit-points"
        role="dialog"
        aria-modal="true"
        aria-labelledby="fit-points-heading"
      >
        <header className="fit-points__header">
          <div>
            <h2 id="fit-points-heading" className="decode-dialog__title">
              Fit by points — tooth {tooth}
            </h2>
            <p className="decode-dialog__subject">
              {caseId} · {model}/{variant} — pick a numbered feature on the part, or click
              anywhere on it to place a free point, then click the same spot on the scan
            </p>
          </div>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={onClose}
            title="Close without aligning (Esc) — recorded marks are discarded"
          >
            ✕ close
          </button>
        </header>

        <div className="fit-points__body">
          <div className="fit-points__panes">
            <article className="verify-panel fit-points__pane">
              <header className="verify-panel__header">
                <h4 className="verify-panel__title">Library part — the marked features</h4>
                <p className="verify-panel__caption">
                  {model}/{variant} · {partMarkers.length} numbered feature
                  {partMarkers.length === 1 ? "" : "s"}
                </p>
              </header>
              <div className="verify-panel__stage">
                <VerifyViewer
                  layers={partLayers}
                  frame={null}
                  markers={partMarkers}
                  onPick={
                    // FREE POINTS (client ask 2026-07-26): a click on the part itself places
                    // the next numbered point. Gated on the derived frame — without it a raw
                    // click cannot be mapped to the canonical frame the server measures in,
                    // and partPaneNotice states that reason (never a silent no-op).
                    partFrame !== null && !controls.busy && canAddFreePoint(controls.pairs)
                      ? (point) => controls.onPickPartPoint(canonicalFromRaw(partFrame, point))
                      : null
                  }
                  ariaLabel="The library part — its features numbered; click it to place a free point"
                />
                {partNotice && (
                  <div
                    className={`verify-panel__overlay verify-panel__overlay--notice${
                      partNotice.tone === "invite" ? " verify-panel__overlay--invite" : ""
                    }`}
                    role="status"
                  >
                    <span>{partNotice.text}</span>
                  </div>
                )}
              </div>
            </article>

            <article className="verify-panel fit-points__pane">
              <header className="verify-panel__header">
                <h4 className="verify-panel__title">Scanned cap — click the matching spot</h4>
                <p className="verify-panel__caption">
                  {controls.pairs.length} point{controls.pairs.length === 1 ? "" : "s"} placed
                  {armedLabel !== null ? ` · waiting for point ${armedLabel}` : ""}
                </p>
              </header>
              <div
                className={`verify-panel__stage${
                  armedLabel !== null ? " verify-panel__stage--armed" : ""
                }`}
              >
                <VerifyViewer
                  layers={scanLayers}
                  frame={siteCenter ? { center: siteCenter, radiusMm: CAP_REGION_RADIUS_MM } : null}
                  markers={scanMarkers}
                  onPick={
                    (controls.armedFeatureId !== null || controls.armedFreePoint !== null) &&
                    !controls.busy
                      ? (point) => onPickScanPoint(point)
                      : null
                  }
                  ariaLabel="The scanned cap region — click to place the matching point"
                />
                {scanNotice && (
                  <div className="verify-panel__overlay verify-panel__overlay--notice" role="status">
                    <span>{scanNotice}</span>
                  </div>
                )}
              </div>
              {armedLabel !== null && (
                <p className="fit-points__arm-hint" role="status">
                  click point {armedLabel} on the scan — drag still orbits; Esc cancels
                </p>
              )}
            </article>
          </div>

          {/* The pair list, the picker, the residuals and Apply — the same panel this flow has
              always had, moved out from inside a table cell and given the two views it needs. */}
          <aside className="fit-points__rail">
            <CorrespondencePanel controls={controls} />
          </aside>
        </div>
      </section>
    </div>
  );
}
