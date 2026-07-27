import { ProposePanel } from "./ProposePanel";
import { ConfirmPanel } from "./ConfirmPanel";
import { SelectionColumn, type SelectionColumnProps } from "./SelectionColumn";

type ProposePanelProps = Parameters<typeof ProposePanel>[0];
type ConfirmPanelProps = Parameters<typeof ConfirmPanel>[0];

export interface MarkDeclareStageProps {
  readonly propose: ProposePanelProps;
  readonly confirm: ConfirmPanelProps;
  readonly selectionColumn: SelectionColumnProps;
}

/**
 * STEP 2, AS ONE FLOW (client, 2026-07-26: "it feels like two flows … let's have ONE cohesive
 * flow, include all the features"). The old shape sent the operator to a separate
 * Library-selection stage that spoke the product's real language (system cards, variant cards
 * with Ø×height, the superseded shelf) while step 2 kept a plain <select> dialect of the same
 * choice. The fix is to DELETE THE SEAM: this component stacks, in order,
 *
 *   detect (unchanged, an aid to marking) → the mark/declare table (minus the retired
 *   implant-system select) → the SAME SelectionColumn the verify dialog mounts.
 *
 * ONE COMPONENT, TWO MOUNTS: SelectionColumn is not forked or re-skinned here — the dialog and
 * the workbench render the identical column over the identical LibrarySelection, wired through
 * the shared selectionColumnHandlers builder, so a choice made in either place IS the other's.
 */
export function MarkDeclareStage({ propose, confirm, selectionColumn }: MarkDeclareStageProps) {
  return (
    <>
      {/* Detection is an AID to marking, not a stage of its own: the client's sequence is
          "load case -> mark cap(s)", and a proposal the doctor never confirms changes nothing. */}
      <ProposePanel {...propose} />
      <ConfirmPanel {...confirm} />
      {/* The absorbed Library selection — a SECTION of step 2 now, never a stop of its own.
          The variant cards declare for the ACTIVE site (the tooth chart and the table rows move
          that cursor); the ceiling, clamps and achieved-relief read-outs ride along unchanged. */}
      <section className="panel mark-selection" aria-labelledby="mark-selection-heading">
        <h2 id="mark-selection-heading" className="panel__title">
          Library selection
          {selectionColumn.activeTooth !== null && (
            <span className="panel__title-case"> — declaring for tooth {selectionColumn.activeTooth}</span>
          )}
        </h2>
        <SelectionColumn {...selectionColumn} />
      </section>
    </>
  );
}
