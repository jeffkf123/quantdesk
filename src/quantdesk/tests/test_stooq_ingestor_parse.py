from datetime import datetime
import io
import pandas as pd
import pytest

from quantdesk.data.ingest import stooq as stooq_mod

class DummyResp:
    def __init__(self, text): self._text = text
    def raise_for_status(self): return None
    @property
    def content(self): return self._text.encode("utf-8")

class DummyClient:
    def __init__(self, payload): self.payload = payload
    def get(self, url, params=None): return DummyResp(self.payload)
    def close(self): pass

def test_fetch_daily_csv_parses_minimal_csv():
    csv = "Date,Open,High,Low,Close,Volume\n2024-01-02,100,102,99,101,123456\n"
    client = DummyClient(csv)
    df = stooq_mod.fetch_daily_csv("SPY", client=client)
    assert len(df) == 1
    assert list(df.columns) == ["symbol","date","open","high","low","close","volume","adjusted_close"]
    assert df.loc[0,"symbol"] == "spy.us"
    assert float(df.loc[0,"close"]) == 101.0
