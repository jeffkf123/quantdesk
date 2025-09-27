import json
from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.config import settings
from quantdesk.api.main import app

@pytest.fixture
def tmp_curve(tmp_path: Path):
    # Create a fake partition with 3m, 2y, 10y points
    base = tmp_path / "treasury" / "par_yield" / "2025" / "08"
    base.mkdir(parents=True, exist_ok=True)
    p = base / "05.parquet"
    df = pd.DataFrame([
        {"date": date(2025,8,5), "bc_code":"BC_3MONTH", "tenor_years":0.25, "par_yield_pct":4.35, "cc_rate_approx":0.0426, "source":"test"},
        {"date": date(2025,8,5), "bc_code":"BC_2YEAR",  "tenor_years":2.0,  "par_yield_pct":3.95, "cc_rate_approx":0.0388, "source":"test"},
        {"date": date(2025,8,5), "bc_code":"BC_10YEAR", "tenor_years":10.0, "par_yield_pct":3.40, "cc_rate_approx":0.0334, "source":"test"},
    ])
    df.to_parquet(p, index=False)
    # Point settings.parquet_dir to tmp base
    settings.parquet_dir = tmp_path
    return p

def test_rates_curve_endpoint(tmp_curve):
    client = TestClient(app)
    base_dir = str(tmp_curve.parents[4])
    r = client.get("/rates/curve", params={"date": "2025-08-05", "base_dir": base_dir})
    assert r.status_code == 200
    payload = r.json()
    assert payload["date"] == "2025-08-05"
    assert "points" in payload and "spreads" in payload
    # 3 points expected
    assert len(payload["points"]) == 3
    # spreads
    sp = payload["spreads"]
    # 2s10s = 10y - 2y = 3.40 - 3.95 = -0.55
    assert abs(sp["2s10s"] - (-0.55)) < 1e-9
    # 3m10y = 10y - 3m = 3.40 - 4.35 = -0.95
    assert abs(sp["3m10y"] - (-0.95)) < 1e-9
