"""Periodic minimum-cost path on a (θ, r) cylinder.

Finds the ring as

    minimise  Σ_i [ −w(θ_i, r_i) − outer_bias · r_i  + λ |r_i − r_{i−1}| ]
    subject to  r_0 = r_N     and     |r_i − r_{i−1}| ≤ max_step

Closure is a constraint, not a post-hoc test. ``outer_bias`` is the analog of
taking the OUTER edge of a closed run — among two circular ridges, the larger
radius wins by a small, explicit margin.

``gap_fraction`` is the share of bearings whose chosen cell is below
``occupied_threshold``: how much of the ring was inferred across a gap.
``bearing_margin`` is, per θ, the chosen (biased) weight minus the next-best
radius bin — the same quantity capture_gate measures as rim-arc occupancy,
reported here as a DP cost margin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

_INF = 1.0e30


@dataclass(frozen=True)
class PeriodicPath:
    r_index: np.ndarray          # (T,) int — radius-bin at each theta
    cost: float
    gap_fraction: float          # share of thetas with w < occupied_threshold
    bearing_margin: np.ndarray   # (T,) chosen biased-w minus next-best at that theta


def periodic_min_path(
    weight: np.ndarray,
    lam: float = 0.35,
    max_step: int = 2,
    outer_bias: float = 0.04,
    occupied_threshold: float = 0.5,
) -> Optional[PeriodicPath]:
    """``weight`` is (N_θ, N_r), higher better. None when the field is empty."""
    w = np.nan_to_num(np.asarray(weight, dtype=float), nan=0.0)
    if w.ndim != 2 or w.shape[0] < 2 or w.shape[1] < 1:
        return None
    if float(w.max()) <= 0.0:
        return None
    n_theta, n_r = int(w.shape[0]), int(w.shape[1])
    step = max(int(max_step), 0)
    radii = np.arange(n_r, dtype=float)
    biased = w + float(outer_bias) * radii[None, :]

    best_cost = _INF
    best_path: Optional[np.ndarray] = None

    for start in range(n_r):
        dp = np.full((n_theta, n_r), _INF)
        prev = np.full((n_theta, n_r), -1, dtype=np.int32)
        dp[0, start] = -biased[0, start]
        for t in range(1, n_theta):
            for r in range(n_r):
                lo = r - step
                hi = r + step
                if lo < 0:
                    lo = 0
                if hi >= n_r:
                    hi = n_r - 1
                node = -biased[t, r]
                best = _INF
                arg = -1
                for rp in range(lo, hi + 1):
                    cand = dp[t - 1, rp] + lam * abs(r - rp) + node
                    if cand < best:
                        best = cand
                        arg = rp
                dp[t, r] = best
                prev[t, r] = arg
        for end in range(n_r):
            if abs(end - start) > step:
                continue
            total = dp[n_theta - 1, end] + lam * abs(end - start)
            if total >= best_cost:
                continue
            path = np.empty(n_theta, dtype=np.int32)
            path[n_theta - 1] = end
            ok = True
            for t in range(n_theta - 1, 0, -1):
                p = int(prev[t, path[t]])
                if p < 0:
                    ok = False
                    break
                path[t - 1] = p
            if not ok or int(path[0]) != start:
                continue
            best_cost = float(total)
            best_path = path

    if best_path is None:
        return None

    occupied = w[np.arange(n_theta), best_path]
    gap_fraction = float(np.mean(occupied < occupied_threshold))
    margins = np.empty(n_theta, dtype=float)
    for t in range(n_theta):
        row = biased[t]
        chosen = float(row[best_path[t]])
        rest = np.delete(row, int(best_path[t]))
        margins[t] = chosen - float(rest.max()) if rest.size else chosen
    return PeriodicPath(
        r_index=best_path,
        cost=float(best_cost),
        gap_fraction=gap_fraction,
        bearing_margin=margins,
    )
