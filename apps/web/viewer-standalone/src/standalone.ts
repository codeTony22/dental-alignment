/**
 * Entry point for the standalone offline case viewer. The Python emitter writes
 * `window.__CASE__ = { caseId, parts, meta }` into the generated view.html BEFORE this bundle
 * runs (as a plain <script> tag ahead of this one), then this file takes over: parse every
 * inlined STL, build the three staged deliverable views, and render them with the same
 * color-coded composition the demo app uses. No network access, no server — everything the
 * page needs is already in memory as window.__CASE__.
 */
import type { CaseData } from "./caseData";
import { buildStagedViews } from "./caseData";
import { buildShell } from "./ui";
import { StandaloneScene } from "./scene";
// `?inline` makes Vite return the compiled CSS as a plain string instead of emitting a
// separate .css asset — the deliverable must be ONE self-contained JS file, so styles are
// injected as a <style> tag at runtime rather than linked.
import stylesCss from "./styles.css?inline";

declare global {
  interface Window {
    __CASE__?: CaseData;
  }
}

function injectStyles(): void {
  const style = document.createElement("style");
  style.textContent = stylesCss;
  document.head.appendChild(style);
}

function renderError(root: HTMLElement, message: string): void {
  root.innerHTML = "";
  const pre = document.createElement("pre");
  pre.className = "case-error";
  pre.textContent = message;
  root.appendChild(pre);
}

function main(): void {
  injectStyles();

  const root = document.getElementById("root");
  if (!root) return;

  const caseData = window.__CASE__;
  if (!caseData) {
    renderError(
      root,
      "No case data found (window.__CASE__ is missing). This file must be opened as the " +
        "generated view.html, not standalone-viewer.iife.js directly.",
    );
    return;
  }

  const views = buildStagedViews(caseData.parts, caseData.meta);
  if (views.length === 0) {
    renderError(root, "This case has no viewable parts.");
    return;
  }

  const shell = buildShell(root, caseData.caseId, caseData.meta, views, (view) => {
    scene.showParts(view.parts);
    shell.setActiveView(view);
  });

  const scene = new StandaloneScene(shell.viewerContainer);

  // The reveal: auto-load the first staged view (healing-cap alignment) on open, same as the
  // app auto-loading stage 1 right after a run — the doctor/lab should never see an empty scene.
  const firstView = views[0];
  if (firstView) {
    scene.showParts(firstView.parts);
    shell.setActiveView(firstView);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main);
} else {
  main();
}
