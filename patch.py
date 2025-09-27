
"""
Patch: Zero-curve + DV01
Usage:
  python patch.py

Run this from your repo root (the directory containing src/quantdesk).
What it does:
- Adds: src/quantdesk/analytics/rates/zero_curve.py
- Appends endpoints to: src/quantdesk/api/main.py  (/rates/zero, /rates/dv01)
- Adds tests: src/quantdesk/tests/test_zero_and_dv01_endpoints.py
"""

from __future__ import annotations
import sys, os, re
from pathlib import Path
from textwrap import dedent

ROOT = Path.cwd()
SRC = ROOT / "src" / "quantdesk"
API = SRC / "api" / "main.py"
AN_DIR = SRC / "analytics" / "rates"
TESTS_DIR = SRC / "tests"

ZERO_CURVE = AN_DIR / "zero_curve.py"
TEST_FILE = TESTS_DIR / "test_zero_and_dv01_endpoints.py"

ZERO_CURVE_CODE = dedent(\"\"\"
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
    \"\"\"Piecewise linear spline in log(DF). Stable & monotone if inputs are.\"\"\"
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
    \"\"\"DV01 for a $1 zero at t under cc comp: DV01 ≈ t * DF * 1e-4\"\"\"
    if t <= 0:
        return 0.0
    df = curve.df(t)
    return t * df * 1e-4
\"\"\")

ENDPOINTS_CODE = dedent(\"\"\"

# --- Zero curve and DV01 endpoints ---
from pathlib import Path
from quantdesk.data.store.treasury_reader import load_curve
from quantdesk.analytics.rates.zero_curve import make_curve_from_cc_points, dv01_zero

def _parse_grid(grid: str | None):
    if not grid:
        return [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
    out = []
    for x in grid.split(\",\"):
        x = x.strip()
        if x:
            out.append(float(x))
    return out

@app.get(\"/rates/zero\")
def rates_zero(date: str, grid: str | None = None, base_dir: str | None = None):
    \"\"\"Fit log-DF piecewise-linear zero curve from cc_rate_approx points.\"\"\"
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return {\"date\": date, \"grid\": [], \"zeros_cc\": [], \"dfs\": [], \"error\": str(e)}
    pts = [(float(r[\"tenor_years\"]), float(r[\"cc_rate_approx\"])) for _, r in df.iterrows() if float(r[\"tenor_years\"]) > 0]
    crv = make_curve_from_cc_points(pts)
    G = _parse_grid(grid)
    zeros = [crv.zero_cc(t) for t in G]
    dfs = [crv.df(t) for t in G]
    return {\"date\": date, \"grid\": G, \"zeros_cc\": zeros, \"dfs\": dfs, \"method\": \"logdf_piecewise_linear_from_cc_approx\"}

@app.get(\"/rates/dv01\")
def rates_dv01(date: str, keys: str | None = None, base_dir: str | None = None):
    \"\"\"Key-rate DV01 ladder for $1 zeros on selected keys (years).\"\"\"
    try:
        df = load_curve(date, base_dir=Path(base_dir) if base_dir else None)
    except FileNotFoundError as e:
        return {\"date\": date, \"keys\": [], \"dv01\": [], \"error\": str(e)}
    pts = [(float(r[\"tenor_years\"]), float(r[\"cc_rate_approx\"])) for _, r in df.iterrows() if float(r[\"tenor_years\"]) > 0]
    crv = make_curve_from_cc_points(pts)
    K = _parse_grid(keys) if keys else [0.25, 2.0, 5.0, 10.0, 30.0]
    dv = [dv01_zero(t, crv) for t in K]
    return {\"date\": date, \"keys\": K, \"dv01\": dv, \"method\": \"dv01_zero_from_logdf_curve\"}
\"\"\")

TESTS_CODE = dedent(\"\"\"
from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.api.main import app
from quantdesk.config import settings

@pytest.fixture
def tmp_curve_for_zero(tmp_path: Path):
    # Smooth decreasing cc curve: r(t) = 0.035 - 0.004 * (min(t,10)/10)
    base = tmp_path / \"curated\" / \"treasury\" / \"par_yield\" / \"2025\" / \"08\"
    base.mkdir(parents=True, exist_ok=True)
    rows = []
    import numpy as np
    tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    for t in tenors:
        cc = 0.035 - 0.004 * min(t,10)/10.0
        rows.append({
            \"date\": date(2025,8,5), \"bc_code\":\"SIM\", \"tenor_years\":float(t),
            \"par_yield_pct\": (np.exp(cc)-1)*100.0, \"cc_rate_approx\": cc, \"source\":\"test\"
        })
    pd.DataFrame(rows).to_parquet(base / \"05.parquet\", index=False)
    settings.parquet_dir = tmp_path
    return tmp_path

def test_rates_zero(tmp_curve_for_zero):
    client = TestClient(app)
    r = client.get(\"/rates/zero\", params={\"date\": \"2025-08-05\", \"grid\": \"0.25,1,2,10,30\", \"base_dir\": str(tmp_curve_for_zero)})
    assert r.status_code == 200
    payload = r.json()
    assert \"error\" not in payload
    G = payload[\"grid\"]; Z = payload[\"zeros_cc\"]; DF = payload[\"dfs\"]
    assert len(G) == len(Z) == len(DF) == 5
    assert DF[0] > DF[-1]
    for z in Z:
        assert 0.0 <= z <= 0.05

def test_rates_dv01(tmp_curve_for_zero):
    client = TestClient(app)
    r = client.get(\"/rates/dv01\", params={\"date\": \"2025-08-05\", \"keys\": \"0.25,2,5,10,30\", \"base_dir\": str(tmp_curve_for_zero)})
    assert r.status_code == 200
    payload = r.json()
    assert \"error\" not in payload
    K = payload[\"keys\"]; DV = payload[\"dv01\"]
    assert len(K) == len(DV) == 5
    assert all(d > 0 for d in DV)
    assert DV[0] < DV[-1]
\"\"\")

def ensure_dirs():
    if not SRC.exists():
        sys.exit(f\"[ERROR] Not in repo root. Expected src/quantdesk under: {ROOT}\")
    AN_DIR.mkdir(parents=True, exist_ok=True)
    TESTS_DIR.mkdir(parents=True, exist_ok=True)

def write_zero_curve():
    ZERO_CURVE.write_text(ZERO_CURVE_CODE, encoding=\"utf-8\")
    print(f\"[OK] wrote {ZERO_CURVE}\")

def append_endpoints():
    if not API.exists():
        sys.exit(f\"[ERROR] API file not found: {API}\")
    code = API.read_text(encoding=\"utf-8\")
    if \"/rates/zero\" in code and \"/rates/dv01\" in code:
        print(\"[SKIP] endpoints already present in api/main.py\")
        return
    if \"from pathlib import Path\" not in code:
        code += \"\\nfrom pathlib import Path\\n\"
    if \"quantdesk.data.store.treasury_reader import load_curve\" not in code:
        code += \"\\nfrom quantdesk.data.store.treasury_reader import load_curve\\n\"
    if \"quantdesk.analytics.rates.zero_curve import make_curve_from_cc_points, dv01_zero\" not in code:
        code += \"\\nfrom quantdesk.analytics.rates.zero_curve import make_curve_from_cc_points, dv01_zero\\n\"
    code += ENDPOINTS_CODE
    API.write_text(code, encoding=\"utf-8\")
    print(f\"[OK] appended endpoints to {API}\")

def write_tests():
    TEST_FILE.write_text(TESTS_CODE, encoding=\"utf-8\")
    print(f\"[OK] wrote {TEST_FILE}\")

def main():
    ensure_dirs()
    write_zero_curve()
    append_endpoints()
    write_tests()
    print(\"\\nPatch applied successfully. Run tests with: pytest -q\")

if __name__ == \"__main__\":
    main()
