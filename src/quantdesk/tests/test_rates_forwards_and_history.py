
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.config import settings
from quantdesk.api.main import app

@pytest.fixture
def tmp_curve_range(tmp_path: Path):
    # Create 3 consecutive business-like days: 2025-08-04..2025-08-06
    base = tmp_path / "treasury" / "par_yield" / "2025" / "08"
    base.mkdir(parents=True, exist_ok=True)
    # 8/04
    pd.DataFrame([
        {"date": date(2025,8,4), "bc_code":"BC_3MONTH", "tenor_years":0.25, "par_yield_pct":4.30, "cc_rate_approx":0.0421, "source":"test"},
        {"date": date(2025,8,4), "bc_code":"BC_2YEAR",  "tenor_years":2.0,  "par_yield_pct":3.90, "cc_rate_approx":0.0383, "source":"test"},
        {"date": date(2025,8,4), "bc_code":"BC_10YEAR", "tenor_years":10.0, "par_yield_pct":3.45, "cc_rate_approx":0.0339, "source":"test"},
    ]).to_parquet(base / "04.parquet", index=False)
    # 8/05
    pd.DataFrame([
        {"date": date(2025,8,5), "bc_code":"BC_3MONTH", "tenor_years":0.25, "par_yield_pct":4.35, "cc_rate_approx":0.0426, "source":"test"},
        {"date": date(2025,8,5), "bc_code":"BC_2YEAR",  "tenor_years":2.0,  "par_yield_pct":3.95, "cc_rate_approx":0.0388, "source":"test"},
        {"date": date(2025,8,5), "bc_code":"BC_10YEAR", "tenor_years":10.0, "par_yield_pct":3.40, "cc_rate_approx":0.0334, "source":"test"},
    ]).to_parquet(base / "05.parquet", index=False)
    # 8/06 (missing 3m on purpose)
    pd.DataFrame([
        {"date": date(2025,8,6), "bc_code":"BC_2YEAR",  "tenor_years":2.0,  "par_yield_pct":3.92, "cc_rate_approx":0.0386, "source":"test"},
        {"date": date(2025,8,6), "bc_code":"BC_10YEAR", "tenor_years":10.0, "par_yield_pct":3.42, "cc_rate_approx":0.0336, "source":"test"},
    ]).to_parquet(base / "06.parquet", index=False)

    settings.parquet_dir = tmp_path
    return tmp_path

def test_forwards_endpoint(tmp_curve_range):
    client = TestClient(app)
    # Request two pairs explicitly
    r = client.get("/rates/forwards", params={"date": "2025-08-05", "pairs": "2,10;0.25,10", "base_dir": str(tmp_curve_range)})
    assert r.status_code == 200
    data = r.json()
    fwd = { (round(x["t1"],3), round(x["t2"],3)): x["fwd_cc"] for x in data["forwards"] }
    assert (2.0, 10.0) in fwd and (0.25, 10.0) in fwd
    # Simple sanity: forward between r1<r2 should be between them for increasing maturities (approx behavior)
    assert min(0.0334, 0.0388) <= fwd[(2.0,10.0)] <= max(0.0334, 0.0388)

def test_history_endpoint(tmp_curve_range):
    client = TestClient(app)
    r = client.get("/rates/history", params={"tenor": 10.0, "start": "2025-08-04", "end": "2025-08-06", "base_dir": str(tmp_curve_range)})
    assert r.status_code == 200
    series = r.json()["series"]
    # We should get three entries (one per day) for 10y
    assert len(series) == 3
    dates = [x["date"] for x in series]
    assert dates == ["2025-08-04", "2025-08-05", "2025-08-06"]
    vals = [round(x["par_yield_pct"], 2) for x in series]
    assert vals == [3.45, 3.40, 3.42]
