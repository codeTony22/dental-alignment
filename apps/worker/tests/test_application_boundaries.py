"""THE APPLICATION PACKAGE MAY NOT IMPORT THE FROZEN SERVER — enforced, worker-side.

Same keystone as apps/bff/tests/test_boundaries.py, applied one layer down (plan §3, grill
AM-2): ``case_prep/application/`` exists precisely so the product never touches
``case_prep.server`` — importing it boots the demo's module state (its case table, app,
CORS, caches) and its always-emit handlers aimed at the demo's data plane. An application
module that imported the server would silently re-couple the product to the freeze.

AST-level, like the bff twin: a docstring may NAME the forbidden module (this one does);
an import statement is what violates the boundary.
"""
from __future__ import annotations

import ast
import pathlib

APPLICATION = (pathlib.Path(__file__).resolve().parents[1]
               / "src" / "case_prep" / "application")


def test_the_application_package_exists():
    assert APPLICATION.is_dir(), "case_prep/application is the product's seam (plan §3)"


def test_application_never_imports_the_frozen_server():
    offenders = []
    for path in APPLICATION.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.startswith("case_prep.server") for a in node.names):
                    offenders.append(path.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("case_prep.server") or (
                        mod == "case_prep" and any(a.name == "server" for a in node.names)):
                    offenders.append(path.name)
    assert offenders == [], f"application/ imports the frozen server in: {offenders}"
