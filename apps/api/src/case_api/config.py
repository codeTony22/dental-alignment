"""Where the case API reads cases and run dirs. Same two roots the BFF uses."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    data_root: Path
    product_root: Path


def default_settings() -> Settings:
    return Settings(
        data_root=_REPO / "apps" / "worker" / "data" / "real",
        product_root=_REPO / "apps" / "worker" / "reports" / "product",
    )
