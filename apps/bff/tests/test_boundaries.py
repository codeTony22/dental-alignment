"""THE ARCHITECTURAL KEYSTONES, enforced (plan §3, grill AM-2).

Not style preferences: the grill traced a concrete failure to each. They inspect the AST — a
docstring is allowed to NAME the forbidden module (this file's own doc does); an import
statement or a path literal is what actually violates the boundary, and the first version of
these tests learned that distinction by failing on its own documentation.
"""
from __future__ import annotations

import ast
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _bff_modules():
    for path in SRC.rglob("*.py"):
        yield path, ast.parse(path.read_text())


def test_the_frozen_demo_server_is_never_imported():
    """`case_prep.server` boots the demo's module state (case table, CORS, caches) and its
    always-emit handlers point at the demo's data plane. The BFF talks to the layer below."""
    offenders = []
    for path, tree in _bff_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.startswith("case_prep.server") for a in node.names):
                    offenders.append(str(path.relative_to(SRC)))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith("case_prep.server") or (
                    mod == "case_prep" and any(a.name == "server" for a in node.names)
                ):
                    offenders.append(str(path.relative_to(SRC)))
    assert offenders == [], f"forbidden import of the frozen demo's server module in: {offenders}"


def test_the_bff_never_writes_into_the_demos_data_plane():
    """Every path the BFF touches lives under reports/product; reports/live-demo is part of
    the freeze. Checked on STRING LITERALS, so prose may explain the rule without breaking it.
    (Slice 1 adds the behavioural byte-identical guard on top of this static one.)"""
    offenders = []
    for path, tree in _bff_modules():
        # A docstring is prose ABOUT the rule, not a path that breaks it — collect the ids of
        # every docstring constant (first Expr of a module/class/function body) and skip them.
        docstrings = set()
        for scope in ast.walk(tree):
            if isinstance(scope, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = scope.body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings and "live-demo" in node.value):
                offenders.append(f"{path.relative_to(SRC)}: {node.value[:60]!r}")
    assert offenders == [], f"demo data-plane path literal in: {offenders}"


def test_health_endpoint_answers():
    sys.path.insert(0, str(SRC))
    from fastapi.testclient import TestClient

    from bff.main import app

    assert TestClient(app).get("/health").json()["ok"] is True
