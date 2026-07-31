/**
 * The product's route table (plan §4, §7 slice 2): the worklist is home, a case
 * lives at /case/:id/:stage, and every URL nobody owns goes home. /case/:id without
 * a stage resumes at the session's furthest stage — the shell's route guard decides
 * once the payload is in hand, so the resume rule has one home (domain/flow.ts).
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { CaseShell } from "./pages/CaseShell";
import { Shell } from "./pages/Shell";
import { TermsPage } from "./pages/TermsPage";
import { WorklistPage } from "./pages/Worklist";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Shell />,
    children: [
      { index: true, element: <WorklistPage /> },
      // the terms are CASE-INDEPENDENT and versioned: /terms is the current text,
      // /terms/:version resolves the exact one a confirmation recorded
      { path: "terms", element: <TermsPage /> },
      { path: "terms/:version", element: <TermsPage /> },
      { path: "case/:id/:stage", element: <CaseShell /> },
      { path: "case/:id", element: <CaseShell /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
