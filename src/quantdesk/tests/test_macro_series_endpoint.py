# src/quantdesk/tests/test_macro_series_endpoint.py
from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.api.main import app
from quantdesk.config import settings

@pytest.fixture
def tmp_fred_series(tmp_path: Path):
    base = tmp_path / "macro" / "fred"
    base.mkdir(parents=True, exist_ok=True)
    p = base / "CPIAUCSL.parquet"
    df = pd.DataFrame({
        "series_id": ["CPIAUCSL"]*15,
        "date": pd.date_range("2023-01-01", periods=15, freq="MS"),
        "value": [300.0 + i for i in range(15)],
    })
    df.to_parquet(p, index=False)
    settings.parquet_dir = tmp_path
    return tmp_path

def test_macro_series_endpoint(tmp_fred_series):
    client = TestClient(app)
    r = client.get("/macro/series/CPIAUCSL", params={"start": "2023-06-01", "end": "2024-03-01", "features": True, "base_dir": str(tmp_fred_series)})
    assert r.status_code == 200
    payload = r.json()
    assert payload["series_id"] == "CPIAUCSL"
    assert payload["count"] > 0
    # Check that features fields exist in entries (may be NaN for early rows due to insufficient lag)
    sample = payload["data"][0]
    assert "value_yoy" in sample and "value_3m_ann" in sample
