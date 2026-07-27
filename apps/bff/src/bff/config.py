"""Where the BFF reads and writes. Two paths, both explicit, both injectable.

The defaults locate the repo from this file's own position — no environment variable is
required to run the local morning. Tests inject a ``Settings`` with tmp paths through
``create_app``; the SQS-era deployment will build one from its environment. The product
data plane is ``reports/product`` and NOTHING else (plan §3, grill AM-2): the frozen
demo's output directory is not named here, and the static boundary test plus the
behavioural freeze guard keep it that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    data_root: Path       # the worker's case/library tree (read-only to the BFF)
    product_root: Path    # the product data plane: reports/product/<case>/session.json


def default_settings() -> Settings:
    return Settings(
        data_root=_REPO / "apps" / "worker" / "data" / "real",
        product_root=_REPO / "apps" / "worker" / "reports" / "product",
    )
