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
    base = tmp_path / "curated" / "treasury" / "par_yield" / "2025" / "08"
    base.mkdir(parents=True, exist_ok=True)
    rows = []
    import numpy as np
    tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    for t in tenors:
        cc = 0.035 - 0.004 * min(t,10)/10.0
        rows.append({
            "date": date(2025,8,5), "bc_code":"SIM", "tenor_years":float(t),
            "par_yield_pct": (np.exp(cc)-1)*100.0, "cc_rate_approx": cc, "source":"test"
        })
    pd.DataFrame(rows).to_parquet(base / "05.parquet", index=False)
    settings.parquet_dir = tmp_path
    return tmp_path

def test_rates_zero(tmp_curve_for_zero):
    client = TestClient(app)
    r = client.get("/rates/zero", params={"date": "2025-08-05", "grid": "0.25,1,2,10,30", "base_dir": str(tmp_curve_for_zero)})
    assert r.status_code == 200
    payload = r.json()
    assert "error" not in payload
    G = payload["grid"]; Z = payload["zeros_cc"]; DF = payload["dfs"]
    assert len(G) == len(Z) == len(DF) == 5
    assert DF[0] > DF[-1]           # DF should decline with maturity
    for z in Z:
        assert 0.0 <= z <= 0.05     # rates in a reasonable band

def test_rates_dv01(tmp_curve_for_zero):
    client = TestClient(app)
    r = client.get("/rates/dv01", params={"date": "2025-08-05", "keys": "0.25,2,5,10,30", "base_dir": str(tmp_curve_for_zero)})
    assert r.status_code == 200
    payload = r.json()
    assert "error" not in payload
    K = payload["keys"]; DV = payload["dv01"]
    assert len(K) == len(DV) == 5
    assert all(d > 0 for d in DV)   # DV01 must be positive
    assert DV[0] < DV[-1]           # generally grows with maturity (t * DF shape)
