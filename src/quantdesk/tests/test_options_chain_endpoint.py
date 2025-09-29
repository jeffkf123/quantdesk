from pathlib import Path
from datetime import datetime
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantdesk.api.main import app
from quantdesk.config import settings

@pytest.fixture
def tmp_options_chain(tmp_path: Path):
    base = tmp_path / "options" / "yahoo" / "SPY" / "2025-08-05"
    base.mkdir(parents=True, exist_ok=True)
    p = base / "2025-09-20.parquet"
    df = pd.DataFrame([
        # minimal call row
        {"symbol":"SPY","asof":"2025-08-05","expiration":"2025-09-20","type":"call","contract":"SPY250920C00450000",
         "last_trade": pd.Timestamp("2025-08-05"), "strike":450.0,"last":5.10,"bid":5.00,"ask":5.20,"mid":5.10,
         "volume":100,"open_interest":1000,"iv":0.20,"in_the_money":False,"spot_hint": 440.0},
        # minimal put row
        {"symbol":"SPY","asof":"2025-08-05","expiration":"2025-09-20","type":"put","contract":"SPY250920P00450000",
         "last_trade": pd.Timestamp("2025-08-05"), "strike":450.0,"last":14.80,"bid":14.70,"ask":14.90,"mid":14.80,
         "volume":120,"open_interest":900,"iv":0.22,"in_the_money":True,"spot_hint": 440.0},
    ])
    df.to_parquet(p, index=False)
    settings.parquet_dir = tmp_path
    return tmp_path

def test_options_meta(tmp_options_chain):
    client = TestClient(app)
    r = client.get("/options/meta", params={"symbol":"SPY","base_dir": str(tmp_options_chain)})
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "SPY"
    assert "2025-08-05" in d["asofs"]
    assert "2025-09-20" in d["expirations_latest"]

def test_options_chain(tmp_options_chain):
    client = TestClient(app)
    r = client.get("/options/chain", params={
        "symbol":"SPY","expiration":"2025-09-20","asof":"2025-08-05","with_greeks": True,
        "r_annual": 0.04, "q_annual": 0.01, "base_dir": str(tmp_options_chain)
    })
    assert r.status_code == 200
    payload = r.json()
    assert payload["symbol"] == "SPY"
    assert payload["expiration"] == "2025-09-20"
    assert len(payload["rows"]) == 2
    # rows should include optional fields like mid/iv and (optionally) theo
    assert "mid" in payload["rows"][0]
    assert "iv" in payload["rows"][0]
