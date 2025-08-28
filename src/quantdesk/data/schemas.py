from __future__ import annotations
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class Bar(BaseModel):
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    volume: float | None = None

class OptionQuote(BaseModel):
    underlying: str
    expiry: datetime
    strike: float
    right: Literal["call", "put"]
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    open_interest: int | None = None
    iv: float | None = None

class CurvePoint(BaseModel):
    ts: datetime
    tenor_years: float
    rate: float  # continuous comp annualized
