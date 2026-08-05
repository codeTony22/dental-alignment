/**
 * THE PANE WORKSPACE'S SHARED POLICY — what Alignment's and Adjustment's three-pane
 * workspaces agree on before either stage adds its own rules.
 */

/**
 * THE LINK'S OPENING STATE (client 2026-08-04: "Alignment and adjustment panels do
 * not share a global camera … create a toggle of this functionality").
 *
 * The toggle EXISTED on both stages (the viewer's OrbitLinkGroup mirrors a user
 * orbit into the sibling panes, each around its own content) — and it opened OFF
 * behind a terse "⛓ link" chip, which is how a built feature gets reported as
 * missing. The panes are read side by side; rotating together is the reading the
 * comparison exists for, so LINKED is the opening state and unlinking is the
 * deliberate act. One constant, imported by both stages, so they cannot open in
 * different moods.
 */
export const PANES_OPEN_LINKED = true;

/** The toggle's face, shared by both stages for the same reason. */
export function paneLinkLabel(linked: boolean): string {
  return linked ? "⛓ rotating together" : "⛓ link panes";
}
