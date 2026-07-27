"""Implant pose domain types and the ubiquitous-language enums."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from case_prep.domain.geometry import Axis


class Retention(str, Enum):
    """How the restoration attaches. Drives the difficulty of the case.

    CEMENT needs position + axis only (no screw channel) — the automatable wedge.
    SCREW additionally needs accurate rotational clocking for the screw access channel.
    """

    CEMENT = "cement"
    SCREW = "screw"


@dataclass(frozen=True)
class Pose6DoF:
    """Recovered implant-platform pose: where the healing cap / restoration seats.

    ``clocking_degrees`` is the rotational index about the axis; it is meaningful
    only for screw-retained sites and is None for cement-retained ones.
    """

    position: "list | object"  # 3-vector (np.ndarray); kept loose to avoid a hard numpy import here
    axis: Axis
    clocking_degrees: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.axis, Axis):
            raise TypeError("Pose6DoF.axis must be an Axis")
