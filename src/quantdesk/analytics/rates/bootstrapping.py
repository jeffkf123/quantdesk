from __future__ import annotations
from math import exp, log

def discount_factor(r: float, t: float) -> float:
    """Continuous comp discount factor DF(t) = exp(-r*t)."""
    if t <= 0:
        return 1.0
    return exp(-r * t)

def zero_from_df(df: float, t: float) -> float:
    if t <= 0:
        return 0.0
    return -log(df) / t

def forward_rate(t1: float, t2: float, r1: float, r2: float) -> float:
    """Instantaneous forward between t1 and t2 from two zero points (cc rates)."""
    if t2 <= t1:
        raise ValueError("t2 must be > t1")
    return (r2 * t2 - r1 * t1) / (t2 - t1)

def dv01_zero_ladder(tenors: list[float], zeros: list[float]) -> list[float]:
    """Approximate DV01 for $1 notional at each tenor under zero curve shifts.
    DV01 ≈ ∂(DF)/∂y * 1bp = t * DF * 1e-4 for cc zero y at tenor t.
    """
    if len(tenors) != len(zeros):
        raise ValueError("Mismatched lengths")
    out = []
    for t, r in zip(tenors, zeros):
        df = discount_factor(r, t)
        out.append(t * df * 1e-4)
    return out
