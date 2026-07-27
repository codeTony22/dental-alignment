/**
 * Plain-DOM UI shell for the standalone viewer: header (caseId + meta table), legend, and the
 * staged-view buttons. No React here — the whole point of this bundle is to be small and
 * dependency-free enough to inline into a single offline HTML file.
 */
import { ROLE_LABEL, paletteHex, type PartRole } from "./palette";
import type { CaseMeta, CaseSiteMeta } from "./caseData";
import type { StagedView } from "./caseData";

const GUIDANCE_LABEL: Record<NonNullable<CaseSiteMeta["guidanceLevel"]>, string> = {
  ready: "READY",
  attention: "ATTENTION",
  "action-needed": "ACTION NEEDED",
};

function formatFit(site: CaseSiteMeta): string {
  if (site.fitAvgMm === null || site.fitMaxMm === null) return "—";
  return `${site.fitAvgMm.toFixed(2)} / ${site.fitMaxMm.toFixed(2)}`;
}

function buildMetaTable(meta: CaseMeta): HTMLTableElement {
  const table = document.createElement("table");
  table.className = "meta-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["Tooth", "Variant", "Fit avg/max (mm)", "Seat", "Gate"]) {
    const th = document.createElement("th");
    th.textContent = label;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const site of meta.sites) {
    const row = document.createElement("tr");

    const toothCell = document.createElement("td");
    toothCell.textContent = String(site.tooth);
    row.appendChild(toothCell);

    const variantCell = document.createElement("td");
    variantCell.textContent = site.variant;
    row.appendChild(variantCell);

    const fitCell = document.createElement("td");
    fitCell.textContent = formatFit(site);
    row.appendChild(fitCell);

    const seatCell = document.createElement("td");
    seatCell.textContent = site.seatMethod ?? "—";
    row.appendChild(seatCell);

    const gateCell = document.createElement("td");
    gateCell.textContent = site.guidanceLevel ? GUIDANCE_LABEL[site.guidanceLevel] : "—";
    row.appendChild(gateCell);

    tbody.appendChild(row);
  }
  table.appendChild(tbody);

  return table;
}

function buildLegend(roles: readonly PartRole[]): HTMLDivElement {
  const legend = document.createElement("div");
  legend.className = "viewer-legend";
  const distinct = [...new Set(roles)];
  for (const role of distinct) {
    const chip = document.createElement("span");
    chip.className = "chip legend-chip";

    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = paletteHex(role);
    chip.appendChild(swatch);

    chip.appendChild(document.createTextNode(ROLE_LABEL[role]));
    legend.appendChild(chip);
  }
  return legend;
}

export interface ViewerShell {
  readonly viewerContainer: HTMLDivElement;
  setActiveView(view: StagedView): void;
}

/**
 * Build the full page shell (header, meta table, view buttons, legend + viewer container) and
 * mount it into `root`. Clicking a view button calls `onSelectView`, which is expected to load
 * that view's parts into the 3D scene and then call setActiveView to refresh the legend and
 * the button's active state.
 */
export function buildShell(
  root: HTMLElement,
  caseId: string,
  meta: CaseMeta,
  views: readonly StagedView[],
  onSelectView: (view: StagedView) => void,
): ViewerShell {
  root.innerHTML = "";

  const header = document.createElement("header");
  header.className = "app-header";
  const title = document.createElement("h1");
  title.className = "app-title";
  title.textContent = `Case ${caseId}`;
  header.appendChild(title);
  header.appendChild(buildMetaTable(meta));
  root.appendChild(header);

  const buttonRow = document.createElement("div");
  buttonRow.className = "view-buttons";
  const buttons: HTMLButtonElement[] = [];

  const viewerWrap = document.createElement("div");
  viewerWrap.className = "viewer3d-wrap";
  const viewerContainer = document.createElement("div");
  viewerContainer.className = "viewer3d";
  viewerWrap.appendChild(viewerContainer);
  const legendSlot = document.createElement("div");
  legendSlot.className = "legend-slot";
  viewerWrap.appendChild(legendSlot);

  const shell: ViewerShell = {
    viewerContainer,
    setActiveView(view: StagedView) {
      buttons.forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.label === view.label);
      });
      legendSlot.innerHTML = "";
      legendSlot.appendChild(buildLegend(view.parts.map((p) => p.role)));
    },
  };

  for (const view of views) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "view-button";
    btn.textContent = view.label;
    btn.dataset.label = view.label;
    btn.addEventListener("click", () => onSelectView(view));
    buttons.push(btn);
    buttonRow.appendChild(btn);
  }

  root.appendChild(buttonRow);
  root.appendChild(viewerWrap);

  return shell;
}
