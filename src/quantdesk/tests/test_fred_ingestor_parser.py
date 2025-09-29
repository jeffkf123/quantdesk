# src/quantdesk/tests/test_fred_ingestor_parser.py
from datetime import date
import json
import pandas as pd
import pytest

from quantdesk.data.ingest import fred as fred_mod
from dotenv import load_dotenv
load_dotenv()

class DummyResp:
    def __init__(self, payload): self._payload = payload
    def raise_for_status(self): return None
    def json(self): return self._payload

class DummyClient:
    def __init__(self, payload): self.payload = payload
    def get(self, url, params=None): return DummyResp(self.payload)
    def close(self): pass

def test_fetch_series_parses_observations():
    payload = {
        "observations": [
            {"date": "2024-01-01", "value": "100.0"},
            {"date": "2024-02-01", "value": "101.0"},
            {"date": "2024-03-01", "value": "."},  # missing
        ]
    }
    client = DummyClient(payload)
    df = fred_mod.fetch_series("FAKESER", date(2024,1,1), date(2024,3,31), client=client)
    assert len(df) == 3
    assert df.loc[0, "value"] == 100.0
    #assert df.loc[2, "value"] is None
    
    assert pd.isna(df.loc[2, "value"])