"""MCP talks to case_prep.application / caseflow only.

A docstring may NAME the forbidden modules; an import statement is the
violation. Same AST distinction the BFF boundary tests learned the hard way.
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _modules():
    for path in SRC.rglob("*.py"):
        yield path, ast.parse(path.read_text())


def _imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            yield mod
            if mod:
                for alias in node.names:
                    yield f"{mod}.{alias.name}"


def test_mcp_never_imports_the_bff():
    offenders = []
    for path, tree in _modules():
        for name in _imports(tree):
            if name == "bff" or name.startswith("bff."):
                offenders.append(str(path.relative_to(SRC)))
    assert offenders == [], f"forbidden bff import in: {offenders}"


def test_mcp_never_imports_the_frozen_demo_server():
    offenders = []
    for path, tree in _modules():
        for name in _imports(tree):
            if name == "case_prep.server" or name.startswith("case_prep.server"):
                offenders.append(str(path.relative_to(SRC)))
            if name == "case_prep" and any(
                isinstance(node, ast.ImportFrom)
                and (node.module or "") == "case_prep"
                and any(a.name == "server" for a in node.names)
                for node in ast.walk(tree)
            ):
                offenders.append(str(path.relative_to(SRC)))
    assert offenders == [], f"forbidden case_prep.server import in: {offenders}"


def test_every_tool_declares_a_boundary_class():
    from alignment_mcp.tools import COMMIT, DRY_RUN, READ, TOOLS
    classes = {READ, DRY_RUN, COMMIT}
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))
    for tool in TOOLS:
        assert tool.classification in classes, tool.name
    assert "get_site_signals" in names
    assert "run_alignment_technique" in names
    assert {t.name for t in TOOLS if t.classification == READ} >= {
        "list_cases", "get_case", "get_site_signals", "get_seated",
        "get_landmarks", "get_acceptance",
    }
    assert {t.name for t in TOOLS if t.classification == DRY_RUN} >= {
        "dry_run_best_fit", "dry_run_repreview",
    }
    assert {t.name for t in TOOLS if t.classification == COMMIT} >= {
        "commit_best_fit", "commit_rotation", "commit_mark_trench",
        "commit_fit_by_points", "run_alignment_technique",
    }
