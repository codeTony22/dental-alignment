/**
 * THE SELECTION COLUMN'S HANDLERS, BUILT ONCE FOR BOTH MOUNTS (client, 2026-07-26: "one
 * cohesive flow"). SelectionColumn renders in two places — the verify dialog and the
 * Mark & declare stage — over the ONE LibrarySelection App owns. This builder is the single
 * wiring from the column's controls to the domain transitions, so the two mounts cannot
 * drift into different ideas of what a click means: a variant card always declares for the
 * ACTIVE site, a system click always clears the variants that belonged to the old system,
 * and everything lands in the same onSelectionChange (which App echoes back into the
 * confirm rows — see App.handleSelectionChange).
 */
import type { Jaw } from "../domain/types";
import type { LibrarySelection } from "../domain/librarySelection";
import {
  withConstruction,
  withJaw,
  withModel,
  withOffsetInput,
  withVariant,
} from "../domain/librarySelection";

export interface SelectionColumnHandlers {
  readonly onSelectModel: (model: string) => void;
  readonly onSelectVariant: (variantId: string) => void;
  readonly onSelectConstruction: (pathId: string) => void;
  readonly onSelectJaw: (jaw: Jaw) => void;
  readonly onChangeOffset: (raw: string) => void;
}

export function selectionColumnHandlers(
  selection: LibrarySelection,
  onSelectionChange: (next: LibrarySelection) => void,
): SelectionColumnHandlers {
  return {
    onSelectModel: (model) => onSelectionChange(withModel(selection, model)),
    onSelectVariant: (variantId) =>
      onSelectionChange(withVariant(selection, selection.activeSiteIndex, variantId)),
    // the dropdown's prompt option carries value "" — an explicit "nothing chosen", not a part id
    onSelectConstruction: (pathId) =>
      onSelectionChange(withConstruction(selection, pathId === "" ? null : pathId)),
    onSelectJaw: (jaw) => onSelectionChange(withJaw(selection, jaw)),
    onChangeOffset: (raw) => onSelectionChange(withOffsetInput(selection, raw)),
  };
}
