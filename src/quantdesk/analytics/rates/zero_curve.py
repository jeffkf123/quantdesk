from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Tuple
import math

@dataclass
class CurvePoint:
    t: float   # years
    cc: float  # continuous-compounded zero rate at t

def _sorted_points(points: Iterable[Tuple[float, float]]) -> List[CurvePoint]:
    ps = [CurvePoint(float(t), float(cc)) for (t, cc) in points if float(t) > 0 and float(cc) == float(cc)]
    ps.sort(key=lambda x: x.t)
    # Deduplicate by t (keep last)
    out: List[CurvePoint] = []
    last_t = None
    for p in ps:
        if last_t is None or abs(p.t - last_t) > 1e-12:
            out.append(p)
            last_t = p.t
        else:
            out[-1] = p
    return out

class LogDFPiecewiseLinear:
    """Piecewise linear spline in log(DF). Stable & monotone if inputs are."""
    def __init__(self, points: Iterable[Tuple[float, float]]):
        pts = _sorted_points(points)
        if not pts:
            raise ValueError("No points for zero curve fit.")
        self.nodes: List[CurvePoint] = pts
        self.logdfs = [-p.cc * p.t for p in pts]

    def df(self, t: float) -> float:
        if t <= 0:
            return 1.0
        nodes = self.nodes
        logdfs = self.logdfs
        if t <= nodes[0].t:
            if len(nodes) == 1:
                return math.exp(logdfs[0] * t / nodes[0].t)
            t0, t1 = nodes[0].t, nodes[1].t
            y0, y1 = logdfs[0], logdfs[1]
            slope = (y1 - y0) / (t1 - t0)
            y = y0 + slope * (t - t0)
            return float(min(1.0, math.exp(y)))
        if t >= nodes[-1].t:
            if len(nodes) == 1:
                return math.exp(logdfs[0] * t / nodes[0].t)
            t0, t1 = nodes[-2].t, nodes[-1].t
            y0, y1 = logdfs[-2], logdfs[-1]
            slope = (y1 - y0) / (t1 - t0)
            y = y1 + slope * (t - t1)
            return float(math.exp(y))
        # interpolate inside
        for i in range(1, len(nodes)):
            if t <= nodes[i].t:
                t0, t1 = nodes[i-1].t, nodes[i].t
                y0, y1 = logdfs[i-1], logdfs[i]
                w = (t - t0) / (t1 - t0)
                y = (1 - w) * y0 + w * y1
                return float(math.exp(y))
        return float(math.exp(self.logdfs[-1]))

    def zero_cc(self, t: float) -> float:
        if t <= 0:
            return 0.0
        df = self.df(t)
        return -math.log(df) / t

    def fwd_cc(self, t1: float, t2: float) -> float:
        if t2 <= t1:
            raise ValueError("t2 must be > t1")
        r1 = self.zero_cc(t1)
        r2 = self.zero_cc(t2)
        return (r2 * t2 - r1 * t1) / (t2 - t1)

def make_curve_from_cc_points(points: Iterable[Tuple[float, float]]) -> LogDFPiecewiseLinear:
    return LogDFPiecewiseLinear(points)

def dv01_zero(t: float, curve: LogDFPiecewiseLinear) -> float:
    """DV01 for a $1 zero at t under cc comp: DV01 ≈ t * DF * 1e-4"""
    if t <= 0:
        return 0.0
    df = curve.df(t)
    return t * df * 1e-4
