"""The REST peer shares the BFF's import walls: no case_prep.server, no live-demo path."""
from __future__ import annotations

import ast
import pathlib
import sys

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def _modules():
    for path in SRC.rglob("*.py"):
        yield path, ast.parse(path.read_text())


def test_the_frozen_demo_server_is_never_imported():
    offenders = []
    for path, tree in _modules():
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
    assert offenders == [], f"forbidden import of case_prep.server in: {offenders}"


def test_the_api_never_writes_into_the_demos_data_plane():
    offenders = []
    for path, tree in _modules():
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

    from case_api.main import app

    assert TestClient(app).get("/health").json() == {"ok": True, "service": "case-api"}
