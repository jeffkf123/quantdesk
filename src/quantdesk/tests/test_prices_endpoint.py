from pathlib import Path
from datetime import date
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.api.main import app
from quantdesk.config import settings

@pytest.fixture
def tmp_prices(tmp_path: Path):
    base = tmp_path / "prices"
    base.mkdir(parents=True, exist_ok=True)
    p = base / "stooq_daily.parquet"
    df = pd.DataFrame({
        "symbol": ["spy.us"]*5,
        "date": pd.date_range("2024-01-02", periods=5, freq="D"),
        "open": [100,101,102,103,104],
        "high": [101,102,103,104,105],
        "low":  [ 99,100,101,102,103],
        "close":[101,102,103,104,105],
        "volume":[1000,1100,1200,1300,1400],
        "adjusted_close":[101,102,103,104,105],
    })
    df.to_parquet(p, index=False)
    settings.parquet_dir = tmp_path
    return tmp_path

def test_prices_daily_endpoint(tmp_prices):
    client = TestClient(app)
    r = client.get("/prices/daily", params={"symbol":"SPY","start":"2024-01-02","end":"2024-01-06","adjusted":True,"base_dir":str(tmp_prices)})
    assert r.status_code == 200
    payload = r.json()
    assert payload["symbol"] == "SPY"
    assert payload["count"] == 5
    # Check ret_1d exists and first is null (no prior)
    assert payload["data"][0]["ret_1d"] is None
    assert payload["data"][1]["ret_1d"] == pytest.approx((102-101)/101)
